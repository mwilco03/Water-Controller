"""
Water Treatment Controller - PROFINET Client Service
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Integration with the C controller via shared memory.
Supports simulation mode for testing and training without real hardware.

Simulation mode can be enabled via:
  - Environment variable: WTC_SIMULATION_MODE=1 or WTC_DEMO_MODE=1
  - When shared memory is not available (controller not running)

In simulation mode, the client uses demo_mode.py to generate realistic
water treatment plant data matching the C simulator scenarios.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Check for simulation mode via environment
_SIMULATION_MODE_ENV = os.environ.get("WTC_SIMULATION_MODE", "").lower() in ("1", "true", "yes")
_DEMO_MODE_ENV = os.environ.get("WTC_DEMO_MODE", "").lower() in ("1", "true", "yes")
SIMULATION_ENABLED = _SIMULATION_MODE_ENV or _DEMO_MODE_ENV

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
    1. Real C controller via shared memory (if running and not in simulation mode)
    2. Simulation/Demo mode - provides realistic simulated data
    3. Empty data fallback

    Simulation mode is automatically enabled when:
    - WTC_SIMULATION_MODE=1 or WTC_DEMO_MODE=1 environment variable is set
    - Shared memory client is not available
    """

    def __init__(self):
        self._client: Any | None = None
        self._simulation_mode = not SHM_AVAILABLE or SIMULATION_ENABLED

        # Auto-enable demo service when in simulation mode
        if self._simulation_mode:
            demo = _get_demo_service()
            if demo and not demo.enabled:
                scenario = os.environ.get("WTC_SIMULATION_SCENARIO",
                          os.environ.get("WTC_DEMO_SCENARIO", "water_treatment_plant"))
                try:
                    from .demo_mode import DemoScenario
                    demo.enable(DemoScenario(scenario))
                    logger.info(f"Simulation mode enabled with scenario: {scenario}")
                except (ValueError, ImportError) as e:
                    logger.warning(f"Could not enable demo scenario '{scenario}': {e}")

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
            demo = _get_demo_service()
            return demo is not None and demo.enabled
        return self._client is not None and self._client.is_connected()

    def is_simulation_mode(self) -> bool:
        """Check if running in simulation mode."""
        return self._simulation_mode

    def is_controller_running(self) -> bool:
        """Check if the PROFINET controller is running."""
        # Check real controller first
        if not self._simulation_mode and self._client:
            if self._client.is_controller_running():
                return True

        # Check demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.is_controller_running()

        return False

    def get_status(self) -> dict[str, Any]:
        """Get controller status."""
        # Try real controller first
        if not self._simulation_mode and self._client and self._client.is_connected():
            status = self._client.get_status()
            if status.get("connected"):
                return status

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            demo_status = demo.get_status()
            return {
                "connected": True,
                "demo_mode": True,
                "controller_running": True,
                **demo_status,
            }

        return {
            "connected": False,
            "simulation_mode": True,
            "controller_running": False,
        }

    def get_rtu_state(self, station_name: str) -> str | None:
        """Get RTU connection state from controller."""
        # Try real controller first
        if not self._simulation_mode and self._client and self._client.is_connected():
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
        if not self._simulation_mode and self._client and self._client.is_connected():
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
        if not self._simulation_mode and self._client and self._client.is_connected():
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
        if not self._simulation_mode and self._client and self._client.is_connected():
            return self._client.command_actuator(station_name, slot, command, pwm_duty)

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.command_actuator(station_name, slot, command, pwm_duty)

        logger.info(f"[SIM] Actuator command: {station_name}/{slot} = {command}")
        return True

    def connect_rtu(self, station_name: str) -> bool:
        """Send RTU connect command to controller."""
        if not self._simulation_mode and self._client and self._client.is_connected():
            return self._client.connect_rtu(station_name)

        logger.info(f"[SIM] Connect RTU: {station_name}")
        return True

    def disconnect_rtu(self, station_name: str) -> bool:
        """Send RTU disconnect command to controller."""
        if not self._simulation_mode and self._client and self._client.is_connected():
            return self._client.disconnect_rtu(station_name)

        logger.info(f"[SIM] Disconnect RTU: {station_name}")
        return True

    def add_rtu(
        self,
        station_name: str,
        ip_address: str,
        vendor_id: int,
        device_id: int,
        slot_count: int
    ) -> bool:
        """Add RTU to controller."""
        if not self._simulation_mode and self._client and self._client.is_connected():
            return self._client.add_rtu(station_name, ip_address, vendor_id, device_id, slot_count)

        logger.info(f"[SIM] Add RTU: {station_name} at {ip_address}")
        return True

    def remove_rtu(self, station_name: str) -> bool:
        """Remove RTU from controller."""
        if not self._simulation_mode and self._client and self._client.is_connected():
            return self._client.remove_rtu(station_name)

        logger.info(f"[SIM] Remove RTU: {station_name}")
        return True

    def dcp_discover(self, timeout_ms: int = 5000) -> list[dict[str, Any]]:
        """Discover PROFINET devices on network."""
        # Try real controller first
        if not self._simulation_mode and self._client and self._client.is_connected():
            devices = self._client.dcp_discover(timeout_ms)
            if devices:
                return devices

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.dcp_discover(timeout_ms)

        logger.info(f"[SIM] DCP discovery (timeout: {timeout_ms}ms)")
        return []

    def get_pid_loops(self) -> list[dict[str, Any]]:
        """Get PID loop states from controller."""
        # Try real controller first
        if not self._simulation_mode and self._client and self._client.is_connected():
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
        if not self._simulation_mode and self._client and self._client.is_connected():
            return self._client.set_setpoint(loop_id, setpoint)

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.set_setpoint(loop_id, setpoint)

        logger.info(f"[SIM] Set setpoint: loop {loop_id} = {setpoint}")
        return True

    def set_pid_mode(self, loop_id: int, mode: int) -> bool:
        """Set PID loop mode."""
        # Try real controller first
        if not self._simulation_mode and self._client and self._client.is_connected():
            return self._client.set_pid_mode(loop_id, mode)

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.set_pid_mode(loop_id, mode)

        logger.info(f"[SIM] Set PID mode: loop {loop_id} = {mode}")
        return True

    def get_alarms(self) -> list[dict[str, Any]]:
        """Get active alarms from controller."""
        # Try real controller first
        if not self._simulation_mode and self._client and self._client.is_connected():
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
        if not self._simulation_mode and self._client and self._client.is_connected():
            return self._client.acknowledge_alarm(alarm_id, user)

        # Try demo mode
        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.acknowledge_alarm(alarm_id, user)

        logger.info(f"[SIM] Acknowledge alarm: {alarm_id} by {user}")
        return True


# Global client instance
_profinet_client: ProfinetClient | None = None


def get_profinet_client() -> ProfinetClient:
    """Get or create the PROFINET client."""
    global _profinet_client
    if _profinet_client is None:
        _profinet_client = ProfinetClient()
        _profinet_client.connect()
    return _profinet_client
