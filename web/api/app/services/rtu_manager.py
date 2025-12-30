"""
Water Treatment Controller - RTU Manager Service
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

RTU lifecycle management and state synchronization.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from ..models.rtu import RTU, RtuState
from .profinet_client import ProfinetClient, get_profinet_client

logger = logging.getLogger(__name__)


class RtuManager:
    """
    Manages RTU lifecycle and synchronizes state between
    database and PROFINET controller.
    """

    def __init__(self, profinet_client: ProfinetClient | None = None):
        self._profinet = profinet_client or get_profinet_client()
        self._state_cache: dict[str, str] = {}  # station_name -> state

    def sync_rtu_state(self, db: Session, station_name: str) -> str | None:
        """
        Sync RTU state from controller to database.

        Returns the current state.
        """
        # Get state from controller
        controller_state = self._profinet.get_rtu_state(station_name)

        # Get database record
        rtu = db.query(RTU).filter(RTU.station_name == station_name).first()
        if not rtu:
            return None

        # If controller has state, update database
        if controller_state and controller_state != rtu.state:
            old_state = rtu.state
            rtu.update_state(
                controller_state,
                reason=f"Controller state sync: {old_state} → {controller_state}"
            )
            db.commit()

        # Cache the state
        self._state_cache[station_name] = rtu.state

        return rtu.state

    def sync_all_rtu_states(self, db: Session) -> dict[str, str]:
        """
        Sync all RTU states from controller.

        Returns dict of station_name -> state.
        """
        rtus = db.query(RTU).all()
        states = {}

        for rtu in rtus:
            state = self.sync_rtu_state(db, rtu.station_name)
            if state:
                states[rtu.station_name] = state

        return states

    def get_cached_state(self, station_name: str) -> str | None:
        """Get cached RTU state without querying controller."""
        return self._state_cache.get(station_name)

    async def connect_rtu(self, db: Session, station_name: str,
                          requested_by: str = "system") -> bool:
        """
        Initiate RTU connection.

        Updates database state and sends command to controller.

        Args:
            db: Database session
            station_name: RTU station name
            requested_by: Who requested the connection (for audit trail)
        """
        rtu = db.query(RTU).filter(RTU.station_name == station_name).first()
        if not rtu:
            return False

        if rtu.state != RtuState.OFFLINE:
            return False

        # Update database state with reason
        rtu.update_state(
            RtuState.CONNECTING,
            reason=f"Connection requested by {requested_by}"
        )
        db.commit()

        # Send command to controller
        success = self._profinet.connect_rtu(station_name)

        if not success:
            # Revert state if command failed
            rtu.update_state(
                RtuState.OFFLINE,
                error="Failed to send connect command",
                reason="IPC command to controller failed"
            )
            db.commit()
            return False

        logger.info(f"RTU {station_name} connection initiated by {requested_by}")
        return True

    async def disconnect_rtu(self, db: Session, station_name: str,
                             requested_by: str = "system") -> bool:
        """
        Disconnect RTU.

        Updates database state and sends command to controller.

        Args:
            db: Database session
            station_name: RTU station name
            requested_by: Who requested the disconnection (for audit trail)
        """
        rtu = db.query(RTU).filter(RTU.station_name == station_name).first()
        if not rtu:
            return False

        if rtu.state == RtuState.OFFLINE:
            return False

        # Send command to controller
        self._profinet.disconnect_rtu(station_name)

        # Update database state with reason
        rtu.update_state(
            RtuState.OFFLINE,
            reason=f"Disconnection requested by {requested_by}"
        )
        db.commit()

        logger.info(f"RTU {station_name} disconnected by {requested_by}")
        return True

    def get_sensor_values(self, station_name: str) -> list[dict[str, Any]]:
        """Get real-time sensor values from controller."""
        return self._profinet.get_sensor_values(station_name)

    def get_actuator_states(self, station_name: str) -> list[dict[str, Any]]:
        """Get real-time actuator states from controller."""
        return self._profinet.get_actuator_states(station_name)

    def command_actuator(
        self,
        station_name: str,
        slot: int,
        command: int,
        pwm_duty: int = 0
    ) -> bool:
        """Send actuator command to controller."""
        return self._profinet.command_actuator(station_name, slot, command, pwm_duty)


# Global manager instance
_rtu_manager: RtuManager | None = None


def get_rtu_manager() -> RtuManager:
    """Get or create the RTU manager."""
    global _rtu_manager
    if _rtu_manager is None:
        _rtu_manager = RtuManager()
    return _rtu_manager
