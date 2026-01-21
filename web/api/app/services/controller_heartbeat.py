"""
Water Treatment Controller - Controller Heartbeat Service
Copyright (C) 2024-2025
SPDX-License-Identifier: GPL-3.0-or-later

Background service that monitors the PROFINET controller connection
and automatically attempts to reconnect when the controller becomes available.

This solves the "restart required" problem where the API starts before
the C controller, caches a failed connection, and never retries.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Heartbeat configuration
DEFAULT_HEARTBEAT_INTERVAL_SEC = 10  # Check every 10 seconds
RECONNECT_BACKOFF_MAX_SEC = 60       # Max backoff between reconnect attempts
RECONNECT_BACKOFF_MULTIPLIER = 2     # Exponential backoff multiplier


class ControllerHeartbeat:
    """
    Background service that monitors controller connection and reconnects.

    Features:
    - Periodic health check of shared memory connection
    - Automatic reconnection with exponential backoff
    - State change logging for debugging
    - Manual reconnect trigger capability
    """

    def __init__(self, interval_sec: float = DEFAULT_HEARTBEAT_INTERVAL_SEC):
        self._running = False
        self._task: asyncio.Task | None = None
        self._interval_sec = interval_sec
        self._backoff_sec = interval_sec
        self._last_state: str | None = None
        self._last_check: datetime | None = None
        self._reconnect_count = 0
        self._successful_reconnects = 0

    async def start(self) -> None:
        """Start the background heartbeat loop."""
        if self._running:
            logger.warning("ControllerHeartbeat already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"ControllerHeartbeat started (interval: {self._interval_sec}s)")

    async def stop(self) -> None:
        """Stop the background heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ControllerHeartbeat stopped")

    @property
    def is_running(self) -> bool:
        """Check if heartbeat is running."""
        return self._running

    def get_status(self) -> dict[str, Any]:
        """Get heartbeat service status."""
        return {
            "running": self._running,
            "interval_sec": self._interval_sec,
            "current_backoff_sec": self._backoff_sec,
            "last_state": self._last_state,
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "reconnect_attempts": self._reconnect_count,
            "successful_reconnects": self._successful_reconnects,
        }

    async def trigger_reconnect(self, force: bool = True) -> dict[str, Any]:
        """
        Manually trigger a reconnection attempt.

        Args:
            force: If True, ignore backoff and reconnect immediately.

        Returns:
            Status dict with connection result.
        """
        from .profinet_client import get_profinet_client

        logger.info("Manual reconnect triggered")
        self._reconnect_count += 1

        profinet = get_profinet_client()
        was_connected = profinet.is_connected()

        # Force reconnect
        success = profinet.reconnect(force=force)

        if success and not was_connected:
            self._successful_reconnects += 1
            self._backoff_sec = self._interval_sec  # Reset backoff on success
            logger.info("Manual reconnect successful")

        return {
            "was_connected": was_connected,
            "now_connected": success,
            "reconnect_count": self._reconnect_count,
        }

    async def _heartbeat_loop(self) -> None:
        """Main heartbeat loop."""
        from .profinet_client import get_profinet_client

        logger.info("Starting controller heartbeat loop")

        while self._running:
            try:
                await self._check_and_reconnect()
                await asyncio.sleep(self._backoff_sec)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}", exc_info=True)
                await asyncio.sleep(self._interval_sec)

    async def _check_and_reconnect(self) -> None:
        """Check connection status and attempt reconnect if needed."""
        from .profinet_client import get_profinet_client
        from .shm_client import get_shm_client

        self._last_check = datetime.now(UTC)

        profinet = get_profinet_client()

        # Determine current state
        if profinet.is_demo_mode():
            current_state = "demo"
        elif profinet.is_connected():
            if profinet.is_controller_running():
                current_state = "connected_running"
            else:
                current_state = "connected_stopped"
        else:
            current_state = "disconnected"

        # Log state changes
        if current_state != self._last_state:
            logger.info(f"Controller state changed: {self._last_state} -> {current_state}")
            self._last_state = current_state

        # Attempt reconnect if disconnected
        if current_state == "disconnected":
            logger.debug(f"Attempting reconnect (backoff: {self._backoff_sec}s)")
            self._reconnect_count += 1

            # Try to reconnect via shm_client first (it has its own reconnect logic)
            try:
                shm = get_shm_client()
                if shm and shm.is_connected():
                    # SHM connected - profinet client should pick this up
                    success = profinet.reconnect(force=True)
                    if success:
                        self._successful_reconnects += 1
                        self._backoff_sec = self._interval_sec  # Reset backoff
                        logger.info("Background reconnect successful")
                    else:
                        # Increase backoff
                        self._backoff_sec = min(
                            self._backoff_sec * RECONNECT_BACKOFF_MULTIPLIER,
                            RECONNECT_BACKOFF_MAX_SEC
                        )
                else:
                    # SHM not available, increase backoff
                    self._backoff_sec = min(
                        self._backoff_sec * RECONNECT_BACKOFF_MULTIPLIER,
                        RECONNECT_BACKOFF_MAX_SEC
                    )
                    logger.debug(f"SHM not available, backoff now {self._backoff_sec}s")
            except Exception as e:
                logger.debug(f"Reconnect attempt failed: {e}")
                self._backoff_sec = min(
                    self._backoff_sec * RECONNECT_BACKOFF_MULTIPLIER,
                    RECONNECT_BACKOFF_MAX_SEC
                )
        else:
            # Connected - reset backoff
            self._backoff_sec = self._interval_sec


# Global heartbeat instance
_heartbeat: ControllerHeartbeat | None = None


def get_heartbeat() -> ControllerHeartbeat:
    """Get or create the global heartbeat service."""
    global _heartbeat
    if _heartbeat is None:
        _heartbeat = ControllerHeartbeat()
    return _heartbeat


async def start_heartbeat() -> None:
    """Start the global heartbeat service."""
    heartbeat = get_heartbeat()
    await heartbeat.start()


async def stop_heartbeat() -> None:
    """Stop the global heartbeat service."""
    heartbeat = get_heartbeat()
    await heartbeat.stop()


# FastAPI lifespan integration
async def heartbeat_lifespan_startup() -> None:
    """Called during FastAPI startup."""
    await start_heartbeat()
    logger.info("Controller heartbeat service initialized")


async def heartbeat_lifespan_shutdown() -> None:
    """Called during FastAPI shutdown."""
    await stop_heartbeat()
    logger.info("Controller heartbeat service stopped")
