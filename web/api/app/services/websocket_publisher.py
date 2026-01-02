"""
Water Treatment Controller - WebSocket Publisher Service
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Background service that polls Modbus/PROFINET data and broadcasts
updates to WebSocket subscribers for real-time dashboard updates.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Polling configuration
DEFAULT_POLL_INTERVAL_MS = 1000  # 1 second
FAST_POLL_INTERVAL_MS = 100     # 100ms for high-priority channels
BATCH_SIZE = 50                  # Max updates per broadcast


class DataPublisher:
    """
    Background publisher that polls data sources and broadcasts to WebSocket.

    Channels:
    - sensors: Sensor values from PROFINET/Modbus
    - controls: Actuator states
    - alarms: Active alarms
    - rtu_state: RTU connection states
    - modbus: Modbus register values
    """

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None
        self._poll_interval_ms = DEFAULT_POLL_INTERVAL_MS
        self._last_values: dict[str, dict[str, Any]] = {}
        self._subscribers_count = 0

    async def start(self) -> None:
        """Start the background publishing loop."""
        if self._running:
            logger.warning("DataPublisher already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._publish_loop())
        logger.info("DataPublisher started")

    async def stop(self) -> None:
        """Stop the background publishing loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("DataPublisher stopped")

    @property
    def is_running(self) -> bool:
        """Check if publisher is running."""
        return self._running

    def set_poll_interval(self, interval_ms: int) -> None:
        """Set polling interval in milliseconds."""
        self._poll_interval_ms = max(50, min(interval_ms, 10000))

    async def _publish_loop(self) -> None:
        """Main publishing loop."""
        from ..api.websocket import manager

        logger.info(f"Starting publish loop with {self._poll_interval_ms}ms interval")

        while self._running:
            try:
                # Only poll if there are subscribers
                if manager.connection_count > 0:
                    await self._poll_and_broadcast()

                # Wait for next poll cycle
                await asyncio.sleep(self._poll_interval_ms / 1000.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in publish loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)  # Back off on error

    async def _poll_and_broadcast(self) -> None:
        """Poll all data sources and broadcast updates."""
        from ..api.websocket import (
            broadcast_sensor_update,
            broadcast_control_update,
            broadcast_alarm,
            broadcast_rtu_state_change,
            manager,
        )

        try:
            # Get data from services
            sensors, controls, alarms, rtu_states, modbus = await asyncio.gather(
                self._get_sensor_data(),
                self._get_control_data(),
                self._get_alarm_data(),
                self._get_rtu_states(),
                self._get_modbus_data(),
                return_exceptions=True
            )

            # Broadcast sensor updates (grouped by RTU)
            if isinstance(sensors, dict):
                for rtu, sensor_list in sensors.items():
                    if self._has_changes("sensors", rtu, sensor_list):
                        await broadcast_sensor_update(rtu, sensor_list)

            # Broadcast control updates (grouped by RTU)
            if isinstance(controls, dict):
                for rtu, control_list in controls.items():
                    if self._has_changes("controls", rtu, control_list):
                        await broadcast_control_update(rtu, control_list)

            # Broadcast alarm updates
            if isinstance(alarms, list):
                for alarm in alarms:
                    if self._is_new_alarm(alarm):
                        await broadcast_alarm("activated", alarm)

            # Broadcast RTU state changes
            if isinstance(rtu_states, dict):
                for rtu, state in rtu_states.items():
                    prev_state = self._last_values.get("rtu_state", {}).get(rtu)
                    if prev_state and prev_state != state:
                        await broadcast_rtu_state_change(rtu, prev_state, state)
                self._last_values["rtu_state"] = rtu_states

            # Broadcast Modbus register updates
            if isinstance(modbus, dict):
                await self._broadcast_modbus_updates(modbus)

        except Exception as e:
            logger.error(f"Error polling data: {e}", exc_info=True)

    async def _get_sensor_data(self) -> dict[str, list[dict[str, Any]]]:
        """Get sensor data from PROFINET client."""
        try:
            from ..services.profinet_client import get_profinet_client
            from ..persistence.rtu import get_all_rtus

            client = get_profinet_client()
            rtus = get_all_rtus()

            result = {}
            for rtu in rtus:
                station = rtu.get("station_name", "")
                if station:
                    sensors = client.get_sensor_values(station)
                    if sensors:
                        result[station] = sensors

            return result
        except Exception as e:
            logger.debug(f"Error getting sensor data: {e}")
            return {}

    async def _get_control_data(self) -> dict[str, list[dict[str, Any]]]:
        """Get actuator/control data from PROFINET client."""
        try:
            from ..services.profinet_client import get_profinet_client
            from ..persistence.rtu import get_all_rtus

            client = get_profinet_client()
            rtus = get_all_rtus()

            result = {}
            for rtu in rtus:
                station = rtu.get("station_name", "")
                if station:
                    actuators = client.get_actuator_states(station)
                    if actuators:
                        result[station] = actuators

            return result
        except Exception as e:
            logger.debug(f"Error getting control data: {e}")
            return {}

    async def _get_alarm_data(self) -> list[dict[str, Any]]:
        """Get active alarms from PROFINET client."""
        try:
            from ..services.profinet_client import get_profinet_client

            client = get_profinet_client()
            return client.get_alarms()
        except Exception as e:
            logger.debug(f"Error getting alarm data: {e}")
            return []

    async def _get_rtu_states(self) -> dict[str, str]:
        """Get RTU connection states."""
        try:
            from ..services.profinet_client import get_profinet_client
            from ..persistence.rtu import get_all_rtus

            client = get_profinet_client()
            rtus = get_all_rtus()

            result = {}
            for rtu in rtus:
                station = rtu.get("station_name", "")
                if station:
                    state = client.get_rtu_state(station)
                    if state:
                        result[station] = state

            return result
        except Exception as e:
            logger.debug(f"Error getting RTU states: {e}")
            return {}

    async def _get_modbus_data(self) -> dict[str, list[dict[str, Any]]]:
        """Get Modbus register data from downstream devices."""
        try:
            from ..services.modbus_service import get_modbus_service

            service = get_modbus_service()
            devices = service.get_devices()

            result = {}
            for device in devices:
                if not device.get("enabled", True):
                    continue

                name = device.get("name", "")
                if not name:
                    continue

                try:
                    # Read first 10 holding registers as sample
                    # In production, this should be based on register mappings
                    registers = service.read_registers(name, "holding", 0, 10)
                    result[name] = registers
                except Exception as e:
                    logger.debug(f"Error reading Modbus device {name}: {e}")

            return result
        except Exception as e:
            logger.debug(f"Error getting Modbus data: {e}")
            return {}

    async def _broadcast_modbus_updates(self, modbus_data: dict[str, list]) -> None:
        """Broadcast Modbus register updates."""
        from ..api.websocket import manager

        for device, registers in modbus_data.items():
            cache_key = f"modbus:{device}"
            if self._has_changes("modbus", device, registers):
                await manager.broadcast("modbus", {
                    "device": device,
                    "registers": registers,
                }, rtu=None)

    def _has_changes(
        self,
        channel: str,
        key: str,
        new_value: Any
    ) -> bool:
        """Check if value has changed since last broadcast."""
        cache_key = f"{channel}:{key}"
        old_value = self._last_values.get(cache_key)

        # Always broadcast if no previous value
        if old_value is None:
            self._last_values[cache_key] = new_value
            return True

        # Compare values
        if new_value != old_value:
            self._last_values[cache_key] = new_value
            return True

        return False

    def _is_new_alarm(self, alarm: dict[str, Any]) -> bool:
        """Check if alarm is new (not seen before)."""
        alarm_id = alarm.get("id") or alarm.get("alarm_id")
        if not alarm_id:
            return True

        known_alarms = self._last_values.get("known_alarms", set())
        if alarm_id not in known_alarms:
            known_alarms.add(alarm_id)
            self._last_values["known_alarms"] = known_alarms
            return True

        return False


# Global publisher instance
_publisher: DataPublisher | None = None


def get_publisher() -> DataPublisher:
    """Get or create the global data publisher."""
    global _publisher
    if _publisher is None:
        _publisher = DataPublisher()
    return _publisher


async def start_publisher() -> None:
    """Start the global data publisher."""
    publisher = get_publisher()
    await publisher.start()


async def stop_publisher() -> None:
    """Stop the global data publisher."""
    publisher = get_publisher()
    await publisher.stop()


# FastAPI lifespan integration
async def publisher_lifespan_startup() -> None:
    """Called during FastAPI startup."""
    await start_publisher()
    logger.info("WebSocket data publisher initialized")


async def publisher_lifespan_shutdown() -> None:
    """Called during FastAPI shutdown."""
    await stop_publisher()
    logger.info("WebSocket data publisher stopped")
