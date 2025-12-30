"""
Water Treatment Controller - PROFINET Client Service
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Integration with the C controller via shared memory.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

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
    logger.warning("Shared memory client not available - running in simulation mode")


class ProfinetClient:
    """
    Client for interacting with the PROFINET controller.

    When the C controller is running, communicates via shared memory.
    Otherwise, operates in simulation mode for development/testing.
    """

    def __init__(self):
        self._client: Any | None = None
        self._simulation_mode = not SHM_AVAILABLE

    def connect(self) -> bool:
        """Connect to the PROFINET controller."""
        if self._simulation_mode:
            logger.info("Running in simulation mode (no controller)")
            return True

        try:
            self._client = get_client()
            if self._client.is_connected():
                logger.info("Connected to PROFINET controller via shared memory")
                return True
            else:
                logger.warning("Failed to connect to shared memory")
                return False
        except Exception as e:
            logger.error(f"Error connecting to PROFINET controller: {e}")
            return False

    def is_connected(self) -> bool:
        """Check if connected to the controller."""
        if self._simulation_mode:
            return True
        return self._client is not None and self._client.is_connected()

    def is_controller_running(self) -> bool:
        """Check if the PROFINET controller is running."""
        if self._simulation_mode:
            return False
        if not self._client:
            return False
        return self._client.is_controller_running()

    def get_status(self) -> dict[str, Any]:
        """Get controller status."""
        if self._simulation_mode:
            return {
                "connected": False,
                "simulation_mode": True,
                "controller_running": False,
            }

        if not self._client or not self._client.is_connected():
            return {"connected": False}

        return self._client.get_status()

    def get_rtu_state(self, station_name: str) -> str | None:
        """Get RTU connection state from controller."""
        if self._simulation_mode:
            return None

        if not self._client or not self._client.is_connected():
            return None

        rtu = self._client.get_rtu(station_name)
        if rtu:
            state_code = rtu.get("connection_state", CONN_STATE_OFFLINE)
            return CONNECTION_STATE_NAMES.get(state_code, "UNKNOWN")
        return None

    def get_sensor_values(self, station_name: str) -> list[dict[str, Any]]:
        """Get sensor values from controller."""
        if self._simulation_mode:
            return []

        if not self._client or not self._client.is_connected():
            return []

        return self._client.get_sensors(station_name)

    def get_actuator_states(self, station_name: str) -> list[dict[str, Any]]:
        """Get actuator states from controller."""
        if self._simulation_mode:
            return []

        if not self._client or not self._client.is_connected():
            return []

        return self._client.get_actuators(station_name)

    def command_actuator(
        self,
        station_name: str,
        slot: int,
        command: int,
        pwm_duty: int = 0
    ) -> bool:
        """Send actuator command to controller."""
        if self._simulation_mode:
            logger.info(f"[SIM] Actuator command: {station_name}/{slot} = {command}")
            return True

        if not self._client or not self._client.is_connected():
            return False

        return self._client.command_actuator(station_name, slot, command, pwm_duty)

    def connect_rtu(self, station_name: str) -> bool:
        """Send RTU connect command to controller."""
        if self._simulation_mode:
            logger.info(f"[SIM] Connect RTU: {station_name}")
            return True

        if not self._client or not self._client.is_connected():
            return False

        return self._client.connect_rtu(station_name)

    def disconnect_rtu(self, station_name: str) -> bool:
        """Send RTU disconnect command to controller."""
        if self._simulation_mode:
            logger.info(f"[SIM] Disconnect RTU: {station_name}")
            return True

        if not self._client or not self._client.is_connected():
            return False

        return self._client.disconnect_rtu(station_name)

    def add_rtu(
        self,
        station_name: str,
        ip_address: str,
        vendor_id: int,
        device_id: int,
        slot_count: int
    ) -> bool:
        """Add RTU to controller."""
        if self._simulation_mode:
            logger.info(f"[SIM] Add RTU: {station_name} at {ip_address}")
            return True

        if not self._client or not self._client.is_connected():
            return False

        return self._client.add_rtu(station_name, ip_address, vendor_id, device_id, slot_count)

    def remove_rtu(self, station_name: str) -> bool:
        """Remove RTU from controller."""
        if self._simulation_mode:
            logger.info(f"[SIM] Remove RTU: {station_name}")
            return True

        if not self._client or not self._client.is_connected():
            return False

        return self._client.remove_rtu(station_name)

    def dcp_discover(self, timeout_ms: int = 5000) -> list[dict[str, Any]]:
        """Discover PROFINET devices on network."""
        if self._simulation_mode:
            logger.info(f"[SIM] DCP discovery (timeout: {timeout_ms}ms)")
            return []

        if not self._client or not self._client.is_connected():
            return []

        return self._client.dcp_discover(timeout_ms)

    def get_pid_loops(self) -> list[dict[str, Any]]:
        """Get PID loop states from controller."""
        if self._simulation_mode:
            return []

        if not self._client or not self._client.is_connected():
            return []

        return self._client.get_pid_loops()

    def set_setpoint(self, loop_id: int, setpoint: float) -> bool:
        """Set PID loop setpoint."""
        if self._simulation_mode:
            logger.info(f"[SIM] Set setpoint: loop {loop_id} = {setpoint}")
            return True

        if not self._client or not self._client.is_connected():
            return False

        return self._client.set_setpoint(loop_id, setpoint)

    def set_pid_mode(self, loop_id: int, mode: int) -> bool:
        """Set PID loop mode."""
        if self._simulation_mode:
            logger.info(f"[SIM] Set PID mode: loop {loop_id} = {mode}")
            return True

        if not self._client or not self._client.is_connected():
            return False

        return self._client.set_pid_mode(loop_id, mode)

    def get_alarms(self) -> list[dict[str, Any]]:
        """Get active alarms from controller."""
        if self._simulation_mode:
            return []

        if not self._client or not self._client.is_connected():
            return []

        return self._client.get_alarms()

    def acknowledge_alarm(self, alarm_id: int, user: str) -> bool:
        """Acknowledge alarm."""
        if self._simulation_mode:
            logger.info(f"[SIM] Acknowledge alarm: {alarm_id} by {user}")
            return True

        if not self._client or not self._client.is_connected():
            return False

        return self._client.acknowledge_alarm(alarm_id, user)


# Global client instance
_profinet_client: ProfinetClient | None = None


def get_profinet_client() -> ProfinetClient:
    """Get or create the PROFINET client."""
    global _profinet_client
    if _profinet_client is None:
        _profinet_client = ProfinetClient()
        _profinet_client.connect()
    return _profinet_client
