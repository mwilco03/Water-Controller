"""
Water Treatment Controller - PROFINET Client Service
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Integration with PROFINET controller.

Priority order:
1. Python PROFINET controller (if enabled via WTC_USE_PYTHON_CONTROLLER=1)
2. Real C controller via shared memory (if running)
3. Demo mode (only if WTC_DEMO_MODE=1 explicitly set)
4. Real network operations (DCP discovery, ping) without controller

Demo mode must be explicitly enabled - it does NOT auto-enable.
"""

import asyncio
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)


class ControllerNotConnectedError(Exception):
    """Raised when an operation requires controller connection but none is available."""
    pass


# Python controller mode
_USE_PYTHON_CONTROLLER = os.environ.get("WTC_USE_PYTHON_CONTROLLER", "1").lower() in ("1", "true", "yes")
PYTHON_CONTROLLER_ENABLED = _USE_PYTHON_CONTROLLER

# Demo mode only when explicitly requested
_DEMO_MODE_ENV = os.environ.get("WTC_DEMO_MODE", "").lower() in ("1", "true", "yes")
DEMO_ENABLED = _DEMO_MODE_ENV

if PYTHON_CONTROLLER_ENABLED:
    logger.info("Python PROFINET controller enabled (WTC_USE_PYTHON_CONTROLLER=1)")
if DEMO_ENABLED:
    logger.info("Demo mode enabled via WTC_DEMO_MODE environment variable")

# Try to import Python controller and its constants
try:
    from .pn_controller import (
        get_controller as get_python_controller,
        QUALITY_GOOD,
        QUALITY_UNCERTAIN,
        QUALITY_BAD,
        QUALITY_SIMULATED,
    )
    PYTHON_CONTROLLER_AVAILABLE = True
except ImportError:
    PYTHON_CONTROLLER_AVAILABLE = False
    QUALITY_GOOD = 0x00
    QUALITY_UNCERTAIN = 0x40
    QUALITY_BAD = 0x80
    QUALITY_SIMULATED = 0x41
    logger.debug("Python controller module not available")

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
    # Extended quality names to include simulated
    QUALITY_NAMES = {
        QUALITY_GOOD: "good",
        QUALITY_UNCERTAIN: "uncertain",
        QUALITY_BAD: "bad",
        QUALITY_SIMULATED: "simulated",
        0xC0: "not_connected"
    }
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
    1. Python PROFINET controller (if WTC_USE_PYTHON_CONTROLLER=1)
    2. Real C controller via shared memory (if running)
    3. Demo mode (only if WTC_DEMO_MODE=1)
    4. Direct network operations without controller

    Demo mode does NOT auto-enable. It must be explicitly requested
    via WTC_DEMO_MODE=1 environment variable.
    """

    def __init__(self):
        self._client: Any | None = None
        self._python_controller = None
        self._use_python_controller = PYTHON_CONTROLLER_ENABLED and PYTHON_CONTROLLER_AVAILABLE
        self._demo_mode = DEMO_ENABLED
        self._last_reconnect_attempt: float = 0
        self._reconnect_cooldown: float = 5.0  # Minimum seconds between reconnect attempts
        self._pending_connections: dict[str, asyncio.Task] = {}

        # Try Python controller first
        if self._use_python_controller:
            try:
                self._python_controller = get_python_controller()
                logger.info("Using Python PROFINET controller")
            except Exception as e:
                logger.warning(f"Python controller unavailable: {e}")
                self._use_python_controller = False

        # Only enable demo service when explicitly requested
        if self._demo_mode and not self._use_python_controller:
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
        # Python controller is always "connected" when available
        if self._use_python_controller and self._python_controller:
            logger.info("Using Python PROFINET controller (always connected)")
            return True

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

    def reconnect(self, force: bool = False) -> bool:
        """
        Attempt to reconnect to the PROFINET controller.

        Args:
            force: If True, ignore cooldown and reconnect immediately.

        Returns:
            True if connected after attempt, False otherwise.
        """
        import time

        if self._demo_mode:
            return True

        if not SHM_AVAILABLE:
            return False

        # Respect cooldown unless forced
        now = time.time()
        if not force and (now - self._last_reconnect_attempt) < self._reconnect_cooldown:
            logger.debug("Reconnect cooldown active, skipping")
            return self._client is not None and self._client.is_connected()

        self._last_reconnect_attempt = now

        try:
            self._client = get_client()
            if self._client.is_connected():
                logger.info("Successfully reconnected to PROFINET controller")
                return True
            else:
                logger.debug("Reconnect attempt: shared memory still not available")
                return False
        except Exception as e:
            logger.warning(f"Reconnect failed: {e}")
            return False

    def _ensure_connected(self) -> bool:
        """Lazy reconnect: ensure we're connected before operations."""
        if self._demo_mode:
            return True

        if self._client and self._client.is_connected():
            return True

        return self.reconnect()

    def is_connected(self) -> bool:
        """Check if connected to the controller."""
        if self._use_python_controller and self._python_controller:
            return True

        if self._demo_mode:
            demo = _get_demo_service()
            return demo is not None and demo.enabled

        if not self._client or not self._client.is_connected():
            self._ensure_connected()

        if self._client:
            try:
                return self._client.is_connected()
            except Exception as e:
                logger.debug(f"is_connected check failed: {e}")
                return False
        return False

    def is_demo_mode(self) -> bool:
        """Check if running in demo mode."""
        return self._demo_mode

    def is_controller_running(self) -> bool:
        """Check if the PROFINET controller is running."""
        if self._use_python_controller and self._python_controller:
            return self._python_controller.is_running

        if not self._demo_mode and self._client:
            try:
                if self._client.is_controller_running():
                    return True
            except Exception as e:
                logger.debug(f"is_controller_running check failed: {e}")

        if self._demo_mode:
            demo = _get_demo_service()
            if demo and demo.enabled:
                return demo.is_controller_running()

        return False

    def get_status(self) -> dict[str, Any]:
        """Get controller status."""
        if self._use_python_controller and self._python_controller:
            rtus = self._python_controller.get_all_rtus()
            return {
                "connected": True,
                "python_controller": True,
                "controller_running": self._python_controller.is_running,
                "rtu_count": len(rtus),
                "rtus": [
                    {
                        "station_name": rtu.station_name,
                        "ip_address": rtu.ip_address,
                        "state": rtu.state,
                        "connected": rtu.connected,
                        "using_simulated_data": rtu.using_simulated_data,
                        "packet_loss_percent": rtu.packet_counters.loss_percent,
                    }
                    for rtu in rtus
                ],
            }

        if not self._demo_mode and self._client:
            try:
                if self._client.is_connected():
                    status = self._client.get_status()
                    if status.get("connected"):
                        return status
            except Exception as e:
                logger.debug(f"get_status from controller failed: {e}")

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

        return {
            "connected": False,
            "demo_mode": False,
            "controller_running": False,
            "error": "No controller connection and demo mode not enabled",
        }

    def get_rtu_state(self, station_name: str) -> str | None:
        """Get RTU connection state from controller."""
        if self._use_python_controller and self._python_controller:
            state = self._python_controller.get_rtu_state_str(station_name)
            return state

        if not self._demo_mode and self._client and self._client.is_connected():
            rtu = self._client.get_rtu(station_name)
            if rtu:
                state_code = rtu.get("connection_state", CONN_STATE_OFFLINE)
                return CONNECTION_STATE_NAMES.get(state_code, "UNKNOWN")

        demo = _get_demo_service()
        if demo and demo.enabled:
            rtu = demo.get_rtu(station_name)
            if rtu:
                state_code = rtu.get("connection_state", CONN_STATE_OFFLINE)
                return CONNECTION_STATE_NAMES.get(state_code, "UNKNOWN")

        return None

    def get_sensor_values(self, station_name: str) -> list[dict[str, Any]]:
        """Get sensor values from controller."""
        if self._use_python_controller and self._python_controller:
            rtu = self._python_controller.get_rtu_state(station_name)
            if rtu:
                return [
                    {
                        "slot": slot,
                        "value": reading.value,
                        "quality": QUALITY_NAMES.get(reading.quality, "unknown"),
                        "timestamp": reading.timestamp,
                        "is_simulated": reading.is_simulated,
                    }
                    for slot, reading in rtu.sensors.items()
                ]
            return []

        if not self._demo_mode and self._client and self._client.is_connected():
            sensors = self._client.get_sensors(station_name)
            if sensors:
                return sensors

        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.get_sensors(station_name)

        return []

    def get_actuator_states(self, station_name: str) -> list[dict[str, Any]]:
        """Get actuator states from controller."""
        # Try Python controller first
        if self._use_python_controller and self._python_controller:
            actuators = self._python_controller.get_all_actuators(station_name)
            if actuators:
                return [
                    {
                        "slot": slot,
                        "command": state.command,
                        "feedback": state.feedback,
                        "forced": state.forced,
                        "timestamp": state.timestamp,
                    }
                    for slot, state in actuators.items()
                ]
            return []

        if not self._demo_mode and self._client and self._client.is_connected():
            actuators = self._client.get_actuators(station_name)
            if actuators:
                return actuators

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
        # Try Python controller first
        if self._use_python_controller and self._python_controller:
            return self._python_controller.command_actuator(station_name, slot, command)

        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.command_actuator(station_name, slot, command, pwm_duty)

        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.command_actuator(station_name, slot, command, pwm_duty)

        raise ControllerNotConnectedError(
            f"Cannot command actuator {station_name}/{slot}: no controller connection. "
            "Start the PROFINET controller or enable demo mode (WTC_DEMO_MODE=1)."
        )

    def connect_rtu(self, station_name: str) -> bool:
        """
        Send RTU connect command to controller.

        For Python controller, this schedules the async connection and returns True
        if the connection was initiated. The actual connection happens asynchronously.
        Poll get_rtu_state() to check when connection completes.

        Returns:
            True if connection was initiated, False if failed to initiate.

        Raises:
            ControllerNotConnectedError: If no controller connection available.
        """
        if self._use_python_controller and self._python_controller:
            # Schedule the async connection properly
            try:
                # Try to get running loop
                try:
                    loop = asyncio.get_running_loop()
                    # We're in async context - schedule task
                    task = loop.create_task(
                        self._python_controller.connect_rtu(station_name)
                    )
                    self._pending_connections[station_name] = task
                    logger.info(f"Scheduled async connection for {station_name}")
                    return True
                except RuntimeError:
                    # No running loop - run synchronously
                    result = asyncio.run(
                        self._python_controller.connect_rtu(station_name)
                    )
                    return result
            except Exception as e:
                logger.error(f"Failed to initiate connection for {station_name}: {e}")
                return False

        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.connect_rtu(station_name)

        demo = _get_demo_service()
        if demo and demo.enabled:
            logger.info(f"[DEMO] Connect RTU: {station_name}")
            return True

        raise ControllerNotConnectedError(
            f"Cannot connect RTU {station_name}: no controller connection. "
            "Start the PROFINET controller or enable demo mode (WTC_DEMO_MODE=1)."
        )

    def disconnect_rtu(self, station_name: str) -> bool:
        """Send RTU disconnect command to controller."""
        if self._use_python_controller and self._python_controller:
            self._python_controller.set_rtu_disconnected(station_name, "User requested disconnect")
            return True

        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.disconnect_rtu(station_name)

        demo = _get_demo_service()
        if demo and demo.enabled:
            logger.info(f"[DEMO] Disconnect RTU: {station_name}")
            return True

        raise ControllerNotConnectedError(
            f"Cannot disconnect RTU {station_name}: no controller connection. "
            "Start the PROFINET controller or enable demo mode (WTC_DEMO_MODE=1)."
        )

    def add_rtu(
        self,
        station_name: str,
        ip_address: str,
        vendor_id: int = 0,
        device_id: int = 0,
        slot_count: int = 0
    ) -> bool:
        """Add RTU to controller."""
        if self._use_python_controller and self._python_controller:
            return self._python_controller.add_rtu(station_name, ip_address)

        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.add_rtu(station_name, ip_address, vendor_id, device_id, slot_count)

        demo = _get_demo_service()
        if demo and demo.enabled:
            logger.info(f"[DEMO] Add RTU: {station_name} at {ip_address}")
            return True

        raise ControllerNotConnectedError(
            f"Cannot add RTU {station_name}: no controller connection. "
            "Start the PROFINET controller or enable demo mode (WTC_DEMO_MODE=1)."
        )

    def remove_rtu(self, station_name: str) -> bool:
        """Remove RTU from controller."""
        if self._use_python_controller and self._python_controller:
            return self._python_controller.remove_rtu(station_name)

        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.remove_rtu(station_name)

        demo = _get_demo_service()
        if demo and demo.enabled:
            logger.info(f"[DEMO] Remove RTU: {station_name}")
            return True

        raise ControllerNotConnectedError(
            f"Cannot remove RTU {station_name}: no controller connection. "
            "Start the PROFINET controller or enable demo mode (WTC_DEMO_MODE=1)."
        )

    def get_packet_counters(self, station_name: str) -> dict[str, Any] | None:
        """Get real packet counters for an RTU."""
        if self._use_python_controller and self._python_controller:
            counters = self._python_controller.get_packet_counters(station_name)
            if counters:
                return {
                    "sent": counters.sent,
                    "received": counters.received,
                    "timeouts": counters.timeouts,
                    "errors": counters.errors,
                    "lost": counters.lost,
                    "loss_percent": counters.loss_percent,
                }
        return None

    def is_using_simulated_data(self, station_name: str) -> bool:
        """Check if RTU is using simulated data."""
        if self._use_python_controller and self._python_controller:
            return self._python_controller.is_using_simulated_data(station_name)
        return False

    def get_slot_config(self, station_name: str) -> list[dict[str, Any]]:
        """Get slot configuration for an RTU."""
        if self._use_python_controller and self._python_controller:
            slots = self._python_controller.get_slot_config(station_name)
            return [
                {
                    "slot_number": s.slot_number,
                    "subslot": s.subslot,
                    "slot_type": s.slot_type,
                    "module_id": f"0x{s.module_id:08X}",
                    "submodule_id": f"0x{s.submodule_id:08X}",
                    "data_length": s.data_length,
                    "description": s.description,
                }
                for s in slots
            ]
        return []

    def dcp_discover(self, timeout_ms: int = 5000) -> list[dict[str, Any]]:
        """Discover PROFINET devices on network."""
        if not self._demo_mode and self._client and self._client.is_connected():
            devices = self._client.dcp_discover(timeout_ms)
            if devices:
                return devices

        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.dcp_discover(timeout_ms)

        try:
            from .dcp_discovery import discover_profinet_devices_sync
            from ..core.network import get_profinet_interface
            interface = get_profinet_interface()
            devices = discover_profinet_devices_sync(interface, timeout_ms / 1000.0)
            return [d.to_dict() for d in devices]
        except PermissionError as e:
            logger.error(f"DCP discovery requires CAP_NET_RAW capability: {e}")
            raise
        except RuntimeError as e:
            logger.error(f"DCP discovery interface error: {e}")
            raise
        except OSError as e:
            logger.error(f"DCP discovery network error: {e}")
            raise

    def get_pid_loops(self) -> list[dict[str, Any]]:
        """Get PID loop states from controller."""
        if not self._demo_mode and self._client and self._client.is_connected():
            loops = self._client.get_pid_loops()
            if loops:
                return loops

        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.get_pid_loops()

        return []

    def set_setpoint(self, loop_id: int, setpoint: float) -> bool:
        """Set PID loop setpoint."""
        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.set_setpoint(loop_id, setpoint)

        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.set_setpoint(loop_id, setpoint)

        raise ControllerNotConnectedError(
            f"Cannot set setpoint for loop {loop_id}: no controller connection. "
            "Start the PROFINET controller or enable demo mode (WTC_DEMO_MODE=1)."
        )

    def set_pid_mode(self, loop_id: int, mode: int) -> bool:
        """Set PID loop mode."""
        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.set_pid_mode(loop_id, mode)

        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.set_pid_mode(loop_id, mode)

        raise ControllerNotConnectedError(
            f"Cannot set PID mode for loop {loop_id}: no controller connection. "
            "Start the PROFINET controller or enable demo mode (WTC_DEMO_MODE=1)."
        )

    def get_alarms(self) -> list[dict[str, Any]]:
        """Get active alarms from controller."""
        if not self._demo_mode and self._client and self._client.is_connected():
            alarms = self._client.get_alarms()
            if alarms:
                return alarms

        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.get_alarms()

        return []

    def acknowledge_alarm(self, alarm_id: int, user: str) -> bool:
        """Acknowledge alarm."""
        if not self._demo_mode and self._client and self._client.is_connected():
            return self._client.acknowledge_alarm(alarm_id, user)

        demo = _get_demo_service()
        if demo and demo.enabled:
            return demo.acknowledge_alarm(alarm_id, user)

        raise ControllerNotConnectedError(
            f"Cannot acknowledge alarm {alarm_id}: no controller connection. "
            "Start the PROFINET controller or enable demo mode (WTC_DEMO_MODE=1)."
        )


# Thread-safe singleton
_profinet_client: ProfinetClient | None = None
_client_lock = threading.Lock()


def get_profinet_client() -> ProfinetClient:
    """Get or create the PROFINET client (thread-safe)."""
    global _profinet_client
    if _profinet_client is None:
        with _client_lock:
            # Double-check locking
            if _profinet_client is None:
                _profinet_client = ProfinetClient()
                _profinet_client.connect()
    return _profinet_client
