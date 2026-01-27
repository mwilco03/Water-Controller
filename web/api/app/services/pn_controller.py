"""
PROFINET Controller Service - Scapy Integration

This module provides the PROFINET controller interface for the FastAPI backend.
It wraps the Scapy-based PROFINET IO Controller with the API expected by profinet_client.py.

The implementation uses Scapy's production-tested PROFINET protocol classes:
- ARBlockReq, IOCRBlockReq, AlarmCRBlockReq, ExpectedSubmoduleBlockReq
- IODControlReq for PrmEnd/ApplicationReady/Release
- ProfinetIO + PNIORealTimeCyclicPDU for cyclic I/O
- ProfinetDCP for device discovery

Copyright (C) 2024-2026
SPDX-License-Identifier: GPL-3.0-or-later
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..core.network import get_profinet_interface

logger = logging.getLogger(__name__)

# Try to import the Scapy-based controller
try:
    from .profinet_scapy import (
        ProfinetController as ScapyController,
        ARState,
        Quality,
        SensorReading as ScapySensorReading,
        DeviceInfo,
        SCAPY_AVAILABLE,
        PROFILE_RTU_CPU_TEMP,
    )
    SCAPY_CONTROLLER_AVAILABLE = SCAPY_AVAILABLE
except ImportError as e:
    SCAPY_CONTROLLER_AVAILABLE = False
    logger.warning(f"Scapy PROFINET controller not available: {e}")

    # Fallback types
    class ARState:
        INIT = "INIT"
        RUN = "RUN"
        ABORT = "ABORT"

    class Quality:
        GOOD = 0x00
        UNCERTAIN = 0x40
        BAD = 0x80
        SIMULATED = 0x41

# Data Quality Constants (OPC UA compatible) - for external use
QUALITY_GOOD = 0x00
QUALITY_UNCERTAIN = 0x40
QUALITY_BAD = 0x80
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


class PNController:
    """
    PROFINET IO Controller - FastAPI Integration Layer

    Wraps the Scapy-based ProfinetController with the API expected by profinet_client.py.
    Provides: add_rtu, connect_rtu, disconnect_rtu, get_rtu_state, get_all_rtus
    """

    def __init__(self):
        self.rtus: Dict[str, RTUState] = {}
        self._running = False
        self._lock = threading.RLock()

        # Get interface using the same detection as DCP discovery
        try:
            self._interface = get_profinet_interface()
            logger.info(f"Using network interface: {self._interface}")
        except RuntimeError as e:
            logger.warning(f"Interface detection failed: {e}, falling back to eth0")
            self._interface = "eth0"

        # Create Scapy controller if available
        self._scapy_ctrl: Optional[ScapyController] = None
        if SCAPY_CONTROLLER_AVAILABLE:
            try:
                self._scapy_ctrl = ScapyController(
                    interface=self._interface,
                    station_name="controller"
                )
                # Register callbacks
                self._scapy_ctrl.set_sensor_callback(self._on_sensor_data)
                self._scapy_ctrl.set_state_callback(self._on_state_change)
                logger.info(f"Scapy PROFINET controller initialized on {self._interface}")
            except Exception as e:
                logger.error(f"Failed to initialize Scapy controller: {e}")
                self._scapy_ctrl = None
        else:
            logger.warning("Scapy not available - PROFINET operations will fail")

    def _on_sensor_data(self, slot: int, value: float, quality: int):
        """Callback when sensor data received from Scapy controller."""
        # Find which RTU this belongs to (currently only one active connection)
        with self._lock:
            for rtu in self.rtus.values():
                if rtu.state == "RUNNING":
                    rtu.sensors[slot] = SensorReading(
                        slot=slot,
                        value=value,
                        quality=quality,
                        timestamp=time.time()
                    )
                    rtu.last_update = time.time()
                    break

    def _on_state_change(self, old_state: ARState, new_state: ARState):
        """Callback when connection state changes."""
        logger.info(f"AR State: {old_state.name if hasattr(old_state, 'name') else old_state} -> "
                   f"{new_state.name if hasattr(new_state, 'name') else new_state}")

    def start(self):
        """Start controller."""
        if self._running:
            return
        self._running = True
        logger.info("PROFINET Controller started")

    def stop(self):
        """Stop controller."""
        self._running = False

        # Disconnect all RTUs
        with self._lock:
            for station_name in list(self.rtus.keys()):
                try:
                    self.disconnect_rtu(station_name)
                except Exception:
                    pass

        logger.info("PROFINET Controller stopped")

    def add_rtu(self, station_name: str, ip_address: str, mac_address: str = "") -> bool:
        """Add RTU to manage."""
        with self._lock:
            if station_name in self.rtus:
                # Update existing
                self.rtus[station_name].ip_address = ip_address
                if mac_address:
                    self.rtus[station_name].mac_address = mac_address
                return True

            self.rtus[station_name] = RTUState(
                station_name=station_name,
                ip_address=ip_address,
                mac_address=mac_address
            )
            logger.info(f"Added RTU: {station_name} at {ip_address}")
        return True

    def get_rtu_state(self, station_name: str) -> Optional[RTUState]:
        """Get RTU state."""
        with self._lock:
            return self.rtus.get(station_name)

    def get_all_rtus(self) -> List[RTUState]:
        """Get all RTU states."""
        with self._lock:
            return list(self.rtus.values())

    async def connect_rtu(self, station_name: str) -> bool:
        """
        Connect to RTU - Full PROFINET handshake via Scapy.

        Sequence: Connect → PrmEnd → ApplicationReady → Cyclic I/O
        """
        with self._lock:
            rtu = self.rtus.get(station_name)
            if not rtu:
                logger.error(f"RTU {station_name} not found")
                return False
            rtu.state = "CONNECTING"
            rtu.error_message = ""

        if not self._scapy_ctrl:
            logger.error("Scapy controller not available")
            with self._lock:
                rtu.state = "ERROR"
                rtu.error_message = "Scapy controller not available"
            return False

        try:
            logger.info(f"[{station_name}] Starting PROFINET connection to {rtu.ip_address}")

            # First, try to discover the device to get MAC address
            if not rtu.mac_address:
                logger.info(f"[{station_name}] Discovering device...")
                devices = self._scapy_ctrl.discover(timeout_s=2.0, station_name=station_name)
                for dev in devices:
                    if dev.ip_address == rtu.ip_address or dev.station_name == station_name:
                        rtu.mac_address = dev.mac_address
                        logger.info(f"[{station_name}] Found MAC: {rtu.mac_address}")
                        break

            # Store device info in Scapy controller
            self._scapy_ctrl.device = DeviceInfo(
                station_name=station_name,
                ip_address=rtu.ip_address,
                mac_address=rtu.mac_address
            )

            # Connect using Scapy controller
            success = self._scapy_ctrl.connect(
                device_ip=rtu.ip_address,
                profile=PROFILE_RTU_CPU_TEMP
            )

            with self._lock:
                if success:
                    rtu.state = "RUNNING"
                    rtu.connected = True
                    logger.info(f"[{station_name}] *** PROFINET CONNECTION ESTABLISHED ***")
                else:
                    rtu.state = "ERROR"
                    rtu.connected = False
                    if self._scapy_ctrl.ar:
                        rtu.error_message = self._scapy_ctrl.ar.error_message
                    logger.error(f"[{station_name}] Connection failed")

            return success

        except Exception as e:
            logger.error(f"[{station_name}] Connect exception: {e}")
            with self._lock:
                rtu.state = "ERROR"
                rtu.error_message = str(e)
                rtu.connected = False
            return False

    def disconnect_rtu(self, station_name: str) -> bool:
        """Disconnect from RTU."""
        with self._lock:
            rtu = self.rtus.get(station_name)
            if not rtu:
                return False

        if self._scapy_ctrl:
            try:
                self._scapy_ctrl.disconnect()
            except Exception as e:
                logger.warning(f"Disconnect error: {e}")

        with self._lock:
            rtu.state = "OFFLINE"
            rtu.connected = False
            rtu.error_message = ""
            logger.info(f"[{station_name}] Disconnected")

        return True

    def get_sensor_value(self, station_name: str, slot: int) -> Optional[SensorReading]:
        """Get sensor reading from RTU."""
        with self._lock:
            rtu = self.rtus.get(station_name)
            if rtu:
                return rtu.sensors.get(slot)
        return None

    def discover_devices(self, timeout_s: float = 3.0) -> List[Dict]:
        """Discover PROFINET devices on network."""
        if not self._scapy_ctrl:
            logger.warning("Scapy controller not available for discovery")
            return []

        try:
            devices = self._scapy_ctrl.discover(timeout_s=timeout_s)
            return [dev.to_dict() for dev in devices]
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            return []


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
