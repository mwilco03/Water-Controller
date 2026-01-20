"""
Water Treatment Controller - PROFINET Client Service
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Integration with the C controller via shared memory.

Priority order:
1. Real C controller via shared memory (if running)
2. Demo mode (only if WTC_DEMO_MODE=1 explicitly set)
3. Real network operations (DCP discovery, ping) without controller

Demo mode must be explicitly enabled - it does NOT auto-enable.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Demo mode only when explicitly requested
_DEMO_MODE_ENV = os.environ.get("WTC_DEMO_MODE", "").lower() in ("1", "true", "yes")
DEMO_ENABLED = _DEMO_MODE_ENV

if DEMO_ENABLED:
    logger.info("Demo mode enabled via WTC_DEMO_MODE environment variable")

# Try to import the shared memory client
try:
    import sys
    from pathlib import Path
    # Add parent directory to path for legacy module imports
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from shm_client import (
        CONN_STATE_OFFLINE,
        CONN_STATE_RUNNING,
        CONNECTION_STATE_NAMES,
        QUALITY_NAMES,
        SENSOR_STATUS_NAMES,
        get_client,
    )
    SHM_AVAILABLE = True
    logger.info("Shared memory client available for C controller integration")
except ImportError:
    SHM_AVAILABLE = False
    CONNECTION_STATE_NAMES = {
        0: "IDLE", 1: "CONNECTING", 2: "CONNECTED",
        3: "RUNNING", 4: "ERROR", 5: "OFFLINE"
    }
    SENSOR_STATUS_NAMES = {0: "good", 1: "bad", 2: "uncertain"}
    QUALITY_NAMES = {0: "good", 0x40: "uncertain", 0x80: "bad", 0xC0: "not_connected"}
    CONN_STATE_RUNNING = 3
    CONN_STATE_OFFLINE = 5
    logger.info("Shared memory client not available - using direct network operations")


def _get_demo_service():
    """Lazily import demo service to avoid circular imports."""
    try:
        from .demo_mode import get_demo_service
        return get_demo_service()
    except ImportError:
        return None


class ProfinetClient:
    """
    Client for interacting with the PROFINET controller.

    Priority order:
    1. Real C controller via shared memory (if running)
    2. Demo mode (only if WTC_DEMO_MODE=1)
    3. Direct network operations without controller

    Demo mode does NOT auto-enable. It must be explicitly requested
    via WTC_DEMO_MODE=1 environment variable.
    """

    def __init__(self):
        self._client: Any | None = None
        self._demo_mode = DEMO_ENABLED

        # Only enable demo service when explicitly requested
        if self._demo_mode:
            demo = _get_demo_service()
            if demo and not demo.enabled:
                scenario = os.environ.get("WTC_DEMO_SCENARIO", "water_treatment_plant")
                try:
                    from .demo_mode import DemoScenario
                    demo.enable(DemoScenario(scenario))
                    logger.info(f"Demo mode enabled with scenario: {scenario}")
                except (ValueError, ImportError) as e:
                    logger.warning(f"Could not enable demo scenario '{scenario}': {e}")

    def connect(self) -> bool:
        """Connect to the PROFINET controller."""
        if self._demo_mode:
            logger.info("Running in demo mode")
            return True

        if not SHM_AVAILABLE:
            logger.warning("Shared memory module not available - cannot connect to C controller")
            return False

        try:
            self._client = get_client()
            if self._client.is_connected():
                logger.info("Connected to PROFINET controller via shared memory")
                return True
            else:
                logger.warning("Shared memory client failed to connect - C controller may not be running")
                return False
        except Exception as e:
            logger.error(f"Could not connect to PROFINET controller: {e}")
            return False

    def is_connected(self) -> bool:
        """Check if connected to the controller."""
        if self._demo_mode:
            demo = _get_demo_service()
            return demo is not None and demo.enabled

        if self._client:
            try:
                return self._client.is_connected()
            except Exception:
                return False
        return False

    def is_demo_mode(self) -> bool:
        """Check if running in demo mode."""
        return self._demo_mode

    def is_controller_running(self) -> bool:
        """Check if the PROFINET controller is running."""
        # Check real controller first
        if not self._demo_mode and self._client:
            try:
                if self._client.is_controller_running():
                    return True
            except Exception:
                pass

        # Check demo mode
        if self._demo_mode:
            demo = _get_demo_service()
            if demo and demo.enabled:
                return demo.is_controller_running()

        return False

    def get_status(self) -> dict[str, Any]:
        """Get controller status."""
        # Try real controller first
        if not self._demo_mode and self._client:
            try:
                if self._client.is_connected():
                    status = self._client.get_status()
                    if status.get("connected"):
                        return status
            except Exception:
                pass

        # Try demo mode
        if self._demo_mode:
            demo = _get_demo_service()
            if demo and demo.enabled:
                demo_status = demo.get_status()
                return {
                    "connected": True,
                    "demo_mode": True,
                    "controller_running": True,
                    **demo_status,
                }

        # No controller, no demo - not connected
        return {
            "connected": False,
            "demo_mode": False,
            "controller_running": False,
            "error": "No controller connection and demo mode not enabled",
        }

    def get_rtu_state(self, station_name: str) -> str | None:
        """Get RTU connection state from controller."""
        # Try real controller first
        if not self._demo_mode and self._client and self._client.is_connected():
            rtu = self._client.get_rtu(station_name)
            if rtu:
                state_code = rtu.get("connection_state", CONN_STATE_OFFLINE)
                return CONNECTION_STATE_NAMES.get(state_code, "UNKNOWN")

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            rtu = demo.get_rtu(station_name)
            if rtu:
                state_code = rtu.get("connection_state", CONN_STATE_OFFLINE)
                return CONNECTION_STATE_NAMES.get(state_code, "UNKNOWN")

        return None

    def get_sensor_values(self, station_name: str) -> list[dict[str, Any]]:
        """Get sensor values from controller."""
        # Try real controller first
        if not self._demo_mode and self._client and self._client.is_connected():
            sensors = self._client.get_sensors(station_name)
            if sensors:
                return sensors

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.get_sensors(station_name)

        return []

    def get_actuator_states(self, station_name: str) -> list[dict[str, Any]]:
        """Get actuator states from controller."""
        # Try real controller first
        if not self._demo_mode and self._client and self._client.is_connected():
            actuators = self._client.get_actuators(station_name)
            if actuators:
                return actuators

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.get_actuators(station_name)

        return []

    def command_actuator(
        self,
        station_name: str,
        slot: int,
        command: int,
        pwm_duty: int = 0
    ) -> bool:
        """Send actuator command to controller."""
        # Try real controller first
        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.command_actuator(station_name, slot, command, pwm_duty)

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.command_actuator(station_name, slot, command, pwm_duty)

        logger.error(f"Cannot command actuator {station_name}/{slot}: no controller connection")
        return False

    def connect_rtu(self, station_name: str) -> bool:
        """Send RTU connect command to controller."""
        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.connect_rtu(station_name)

        # Demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            logger.info(f"[DEMO] Connect RTU: {station_name}")
            return True

        logger.error(f"Cannot connect RTU {station_name}: no controller connection")
        return False

    def disconnect_rtu(self, station_name: str) -> bool:
        """Send RTU disconnect command to controller."""
        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.disconnect_rtu(station_name)

        # Demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            logger.info(f"[DEMO] Disconnect RTU: {station_name}")
            return True

        logger.error(f"Cannot disconnect RTU {station_name}: no controller connection")
        return False

    def add_rtu(
        self,
        station_name: str,
        ip_address: str,
        vendor_id: int,
        device_id: int,
        slot_count: int
    ) -> bool:
        """Add RTU to controller."""
        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.add_rtu(station_name, ip_address, vendor_id, device_id, slot_count)

        # Demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            logger.info(f"[DEMO] Add RTU: {station_name} at {ip_address}")
            return True

        logger.error(f"Cannot add RTU {station_name}: no controller connection")
        return False

    def remove_rtu(self, station_name: str) -> bool:
        """Remove RTU from controller."""
        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.remove_rtu(station_name)

        # Demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            logger.info(f"[DEMO] Remove RTU: {station_name}")
            return True

        logger.error(f"Cannot remove RTU {station_name}: no controller connection")
        return False

    def dcp_discover(self, timeout_ms: int = 5000) -> list[dict[str, Any]]:
        """Discover PROFINET devices on network."""
        # Try real controller first
        if not self._demo_mode and self._client and self._client.is_connected():
            devices = self._client.dcp_discover(timeout_ms)
            if devices:
                return devices

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.dcp_discover(timeout_ms)

        # No controller - try direct network discovery
        try:
            from .dcp_discovery import discover_profinet_devices_sync
            from ..core.network import get_profinet_interface
            interface = get_profinet_interface()
            devices = discover_profinet_devices_sync(interface, timeout_ms / 1000.0)
            return [d.to_dict() for d in devices]
        except Exception as e:
            logger.warning(f"Direct DCP discovery failed: {e}")
            return []

    def get_pid_loops(self) -> list[dict[str, Any]]:
        """Get PID loop states from controller."""
        # Try real controller first
        if not self._demo_mode and self._client and self._client.is_connected():
            loops = self._client.get_pid_loops()
            if loops:
                return loops

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.get_pid_loops()

        return []

    def set_setpoint(self, loop_id: int, setpoint: float) -> bool:
        """Set PID loop setpoint."""
        # Try real controller first
        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.set_setpoint(loop_id, setpoint)

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.set_setpoint(loop_id, setpoint)

        logger.error(f"Cannot set setpoint for loop {loop_id}: no controller connection")
        return False

    def set_pid_mode(self, loop_id: int, mode: int) -> bool:
        """Set PID loop mode."""
        # Try real controller first
        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.set_pid_mode(loop_id, mode)

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.set_pid_mode(loop_id, mode)

        logger.error(f"Cannot set PID mode for loop {loop_id}: no controller connection")
        return False

    def get_alarms(self) -> list[dict[str, Any]]:
        """Get active alarms from controller."""
        # Try real controller first
        if not self._demo_mode and self._client and self._client.is_connected():
            alarms = self._client.get_alarms()
            if alarms:
                return alarms

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.get_alarms()

        return []

    def acknowledge_alarm(self, alarm_id: int, user: str) -> bool:
        """Acknowledge alarm."""
        # Try real controller first
        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.acknowledge_alarm(alarm_id, user)

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.acknowledge_alarm(alarm_id, user)

        logger.error(f"Cannot acknowledge alarm {alarm_id}: no controller connection")
        return False


# Global client instance
_profinet_client: ProfinetClient | None = None


def get_profinet_client() -> ProfinetClient:
    """Get or create the PROFINET client."""
    global _profinet_client
    if _profinet_client is None:
        _profinet_client = ProfinetClient()
        _profinet_client.connect()
    return _profinet_client
