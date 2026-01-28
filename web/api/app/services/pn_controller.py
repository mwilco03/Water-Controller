"""
PROFINET Controller Service - C Controller IPC Integration

This module provides the PROFINET controller interface for the FastAPI backend.
It communicates with the C PROFINET IO Controller via shared memory IPC.

Architecture:
  FastAPI Backend → pn_controller.py → shm_client.py → Shared Memory → C Controller

The C controller (water_treat_controller) handles:
- DCP discovery and device identification
- PROFINET AR setup (Connect, PrmEnd, ApplicationReady)
- Cyclic I/O data exchange
- Alarm handling and state management

Copyright (C) 2024-2026
SPDX-License-Identifier: GPL-3.0-or-later
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Import shared memory client for C controller IPC
# shm_client.py is at web/api/shm_client.py (outside app package)
try:
    import sys
    import os
    # Add parent directory to path for shm_client import
    _api_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _api_dir not in sys.path:
        sys.path.insert(0, _api_dir)

    from shm_client import (
        WtcShmClient,
        get_client,
        CONN_STATE_IDLE,
        CONN_STATE_CONNECTING,
        CONN_STATE_CONNECTED,
        CONN_STATE_RUNNING,
        CONN_STATE_ERROR,
        CONN_STATE_OFFLINE,
        CONNECTION_STATE_NAMES,
        QUALITY_GOOD,
        QUALITY_UNCERTAIN,
        QUALITY_BAD,
    )
    SHM_CLIENT_AVAILABLE = True
except ImportError as e:
    SHM_CLIENT_AVAILABLE = False
    logger.warning(f"Shared memory client not available: {e}")
    # Fallback constants
    CONN_STATE_IDLE = 0
    CONN_STATE_CONNECTING = 1
    CONN_STATE_CONNECTED = 2
    CONN_STATE_RUNNING = 3
    CONN_STATE_ERROR = 4
    CONN_STATE_OFFLINE = 5
    CONNECTION_STATE_NAMES = {
        0: "IDLE", 1: "CONNECTING", 2: "CONNECTED",
        3: "RUNNING", 4: "ERROR", 5: "OFFLINE"
    }
    QUALITY_GOOD = 0x00
    QUALITY_UNCERTAIN = 0x40
    QUALITY_BAD = 0x80


# Data Quality Constants (OPC UA compatible) - for external use
QUALITY_SIMULATED = 0x41


@dataclass
class SensorReading:
    """Sensor data with quality - API-compatible format."""
    slot: int
    value: float
    quality: int = QUALITY_GOOD
    timestamp: float = field(default_factory=time.time)


@dataclass
class RTUState:
    """RTU state - API-compatible format."""
    station_name: str
    ip_address: str
    mac_address: str = ""
    connected: bool = False
    state: str = "OFFLINE"  # OFFLINE, CONNECTING, CONNECTED, RUNNING, ERROR
    sensors: Dict[int, SensorReading] = field(default_factory=dict)
    last_update: float = 0.0
    error_message: str = ""


def _conn_state_to_str(conn_state: int) -> str:
    """Convert connection state int to string."""
    return CONNECTION_STATE_NAMES.get(conn_state, "UNKNOWN")


def _conn_state_is_connected(conn_state: int) -> bool:
    """Check if connection state represents connected."""
    return conn_state in (CONN_STATE_CONNECTED, CONN_STATE_RUNNING)


class PNController:
    """
    PROFINET IO Controller - FastAPI Integration Layer

    Communicates with the C PROFINET controller via shared memory IPC.
    Provides: add_rtu, connect_rtu, disconnect_rtu, get_rtu_state, get_all_rtus
    """

    def __init__(self):
        self._running = False
        self._lock = threading.RLock()
        self._shm_client: Optional[WtcShmClient] = None

        # Initialize shared memory client
        if SHM_CLIENT_AVAILABLE:
            try:
                self._shm_client = get_client(max_retries=3, retry_delay=1.0)
                if self._shm_client.is_connected():
                    logger.info("Connected to C controller via shared memory")
                else:
                    logger.warning("Shared memory client created but not connected - controller may not be running")
            except Exception as e:
                logger.error(f"Failed to initialize shared memory client: {e}")
                self._shm_client = None
        else:
            logger.warning("Shared memory client not available - PROFINET operations will fail")

    def _ensure_connected(self) -> bool:
        """Ensure shared memory client is connected."""
        if not self._shm_client:
            return False
        if not self._shm_client.is_connected():
            return self._shm_client.connect()
        return True

    def start(self):
        """Start controller."""
        if self._running:
            return
        self._running = True
        self._ensure_connected()
        logger.info("PROFINET Controller service started (C controller IPC mode)")

    def stop(self):
        """Stop controller."""
        self._running = False
        if self._shm_client:
            self._shm_client.disconnect()
        logger.info("PROFINET Controller service stopped")

    def add_rtu(self, station_name: str, ip_address: str, mac_address: str = "") -> bool:
        """
        Add RTU to C controller for management.

        Sends IPC command to C controller which will:
        1. Add RTU to its internal list
        2. Optionally trigger DCP identification
        """
        if not self._ensure_connected():
            logger.error("Cannot add RTU: not connected to C controller")
            return False

        try:
            success = self._shm_client.add_rtu(
                station_name=station_name,
                ip_address=ip_address,
                vendor_id=0x0493,  # Default Water-Treat vendor ID
                device_id=0x0001   # Default device ID
            )
            if success:
                logger.info(f"Added RTU via IPC: {station_name} at {ip_address}")
            else:
                logger.error(f"Failed to add RTU via IPC: {station_name}")
            return success
        except Exception as e:
            logger.error(f"Exception adding RTU: {e}")
            return False

    def get_rtu_state(self, station_name: str) -> Optional[RTUState]:
        """Get RTU state from C controller via shared memory."""
        if not self._ensure_connected():
            return None

        try:
            rtu_data = self._shm_client.get_rtu(station_name)
            if not rtu_data:
                return None

            # Convert shared memory data to RTUState
            conn_state = rtu_data.get("connection_state", CONN_STATE_OFFLINE)

            rtu_state = RTUState(
                station_name=rtu_data.get("station_name", station_name),
                ip_address=rtu_data.get("ip_address", ""),
                mac_address="",  # MAC not stored in current SHM struct
                connected=_conn_state_is_connected(conn_state),
                state=_conn_state_to_str(conn_state),
                last_update=time.time(),
            )

            # Convert sensors
            for sensor in rtu_data.get("sensors", []):
                slot = sensor.get("slot", 0)
                rtu_state.sensors[slot] = SensorReading(
                    slot=slot,
                    value=sensor.get("value", 0.0),
                    quality=sensor.get("quality", QUALITY_GOOD),
                    timestamp=sensor.get("timestamp_ms", 0) / 1000.0
                )

            return rtu_state

        except Exception as e:
            logger.error(f"Failed to get RTU state: {e}")
            return None

    def get_all_rtus(self) -> List[RTUState]:
        """Get all RTU states from C controller via shared memory."""
        if not self._ensure_connected():
            return []

        try:
            rtus_data = self._shm_client.get_rtus()
            rtu_states = []

            for rtu_data in rtus_data:
                conn_state = rtu_data.get("connection_state", CONN_STATE_OFFLINE)

                rtu_state = RTUState(
                    station_name=rtu_data.get("station_name", ""),
                    ip_address=rtu_data.get("ip_address", ""),
                    mac_address="",
                    connected=_conn_state_is_connected(conn_state),
                    state=_conn_state_to_str(conn_state),
                    last_update=time.time(),
                )

                # Convert sensors
                for sensor in rtu_data.get("sensors", []):
                    slot = sensor.get("slot", 0)
                    rtu_state.sensors[slot] = SensorReading(
                        slot=slot,
                        value=sensor.get("value", 0.0),
                        quality=sensor.get("quality", QUALITY_GOOD),
                        timestamp=sensor.get("timestamp_ms", 0) / 1000.0
                    )

                rtu_states.append(rtu_state)

            return rtu_states

        except Exception as e:
            logger.error(f"Failed to get all RTUs: {e}")
            return []

    async def connect_rtu(self, station_name: str) -> bool:
        """
        Connect to RTU via C controller.

        Sends IPC command to C controller which will:
        1. Perform DCP identification if needed
        2. Establish PROFINET AR (Connect, PrmEnd, ApplicationReady)
        3. Start cyclic I/O data exchange
        """
        if not self._ensure_connected():
            logger.error("Cannot connect RTU: not connected to C controller")
            return False

        try:
            logger.info(f"[{station_name}] Sending connect command to C controller")
            success = self._shm_client.connect_rtu(station_name)
            if success:
                logger.info(f"[{station_name}] Connect command sent successfully")
            else:
                logger.error(f"[{station_name}] Failed to send connect command")
            return success
        except Exception as e:
            logger.error(f"[{station_name}] Connect exception: {e}")
            return False

    def disconnect_rtu(self, station_name: str) -> bool:
        """
        Disconnect RTU via C controller.

        Sends IPC command to C controller which will:
        1. Send PROFINET Release request
        2. Close the AR gracefully
        3. Stop cyclic I/O
        """
        if not self._ensure_connected():
            logger.error("Cannot disconnect RTU: not connected to C controller")
            return False

        try:
            logger.info(f"[{station_name}] Sending disconnect command to C controller")
            success = self._shm_client.disconnect_rtu(station_name)
            if success:
                logger.info(f"[{station_name}] Disconnect command sent")
            return success
        except Exception as e:
            logger.error(f"[{station_name}] Disconnect exception: {e}")
            return False

    def get_sensor_value(self, station_name: str, slot: int) -> Optional[SensorReading]:
        """Get sensor reading from RTU via shared memory."""
        if not self._ensure_connected():
            return None

        try:
            sensor_data = self._shm_client.get_sensor_value(station_name, slot)
            if not sensor_data:
                return None

            return SensorReading(
                slot=sensor_data.get("slot", slot),
                value=sensor_data.get("value", 0.0),
                quality=sensor_data.get("quality_code", QUALITY_GOOD),
                timestamp=sensor_data.get("timestamp_ms", 0) / 1000.0
            )
        except Exception as e:
            logger.error(f"Failed to get sensor value: {e}")
            return None

    def discover_devices(self, timeout_s: float = 5.0) -> List[Dict[str, Any]]:
        """
        Discover PROFINET devices via C controller DCP.

        Sends IPC command to C controller which performs DCP Identify All.
        Returns list of discovered devices.
        """
        if not self._ensure_connected():
            logger.warning("Cannot discover: not connected to C controller")
            return []

        try:
            timeout_ms = int(timeout_s * 1000)
            devices = self._shm_client.dcp_discover(timeout_ms=timeout_ms)

            # Convert to standard format
            result = []
            for dev in devices:
                result.append({
                    "station_name": dev.get("station_name", ""),
                    "ip_address": dev.get("ip_address", ""),
                    "mac_address": dev.get("mac_address", ""),
                    "vendor_id": dev.get("profinet_vendor_id", 0),
                    "device_id": dev.get("profinet_device_id", 0),
                    "reachable": dev.get("reachable", False),
                })
            return result

        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            return []

    def get_controller_status(self) -> Dict[str, Any]:
        """Get C controller status via shared memory."""
        if not self._ensure_connected():
            return {
                "connected": False,
                "controller_running": False,
                "mode": "disconnected",
            }

        try:
            status = self._shm_client.get_status()
            return {
                "connected": status.get("connected", False),
                "controller_running": status.get("controller_running", False),
                "mode": "c_controller",
                "total_rtus": status.get("total_rtus", 0),
                "connected_rtus": status.get("connected_rtus", 0),
                "active_alarms": status.get("active_alarms", 0),
            }
        except Exception as e:
            logger.error(f"Failed to get controller status: {e}")
            return {
                "connected": False,
                "controller_running": False,
                "mode": "error",
                "error": str(e),
            }

    def command_actuator(self, station_name: str, slot: int,
                         command: int, pwm_duty: int = 0) -> bool:
        """Send actuator command via C controller."""
        if not self._ensure_connected():
            return False

        try:
            return self._shm_client.command_actuator(
                station=station_name,
                slot=slot,
                command=command,
                pwm_duty=pwm_duty
            )
        except Exception as e:
            logger.error(f"Actuator command failed: {e}")
            return False


# Singleton instance with thread-safe double-check locking
_controller: Optional[PNController] = None
_controller_lock = threading.Lock()


def get_controller() -> PNController:
    """Get or create controller instance (thread-safe)."""
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:
                _controller = PNController()
    return _controller


def init_controller():
    """Initialize controller on startup."""
    ctrl = get_controller()
    ctrl.start()
    return ctrl


def shutdown_controller():
    """Shutdown controller."""
    global _controller
    if _controller:
        _controller.stop()
        _controller = None
