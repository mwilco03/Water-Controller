"""
Water Treatment Controller - RTU Manager Service
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

RTU lifecycle management and state synchronization.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models.rtu import RTU, RtuState
from .profinet_client import ProfinetClient, get_profinet_client

logger = logging.getLogger(__name__)


class RtuManager:
    """
    Manages RTU lifecycle and synchronizes state between
    database and PROFINET controller.
    """

    def __init__(self, profinet_client: Optional[ProfinetClient] = None):
        self._profinet = profinet_client or get_profinet_client()
        self._state_cache: Dict[str, str] = {}  # station_name -> state

    def sync_rtu_state(self, db: Session, station_name: str) -> Optional[str]:
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
            rtu.update_state(controller_state)
            db.commit()
            logger.info(f"RTU {station_name} state synced: {rtu.state} -> {controller_state}")

        # Cache the state
        self._state_cache[station_name] = rtu.state

        return rtu.state

    def sync_all_rtu_states(self, db: Session) -> Dict[str, str]:
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

    def get_cached_state(self, station_name: str) -> Optional[str]:
        """Get cached RTU state without querying controller."""
        return self._state_cache.get(station_name)

    async def connect_rtu(self, db: Session, station_name: str) -> bool:
        """
        Initiate RTU connection.

        Updates database state and sends command to controller.
        """
        rtu = db.query(RTU).filter(RTU.station_name == station_name).first()
        if not rtu:
            return False

        if rtu.state != RtuState.OFFLINE:
            return False

        # Update database state
        rtu.update_state(RtuState.CONNECTING)
        db.commit()

        # Send command to controller
        success = self._profinet.connect_rtu(station_name)

        if not success:
            # Revert state if command failed
            rtu.update_state(RtuState.OFFLINE, error="Failed to send connect command")
            db.commit()
            return False

        logger.info(f"RTU {station_name} connection initiated")
        return True

    async def disconnect_rtu(self, db: Session, station_name: str) -> bool:
        """
        Disconnect RTU.

        Updates database state and sends command to controller.
        """
        rtu = db.query(RTU).filter(RTU.station_name == station_name).first()
        if not rtu:
            return False

        if rtu.state == RtuState.OFFLINE:
            return False

        # Send command to controller
        success = self._profinet.disconnect_rtu(station_name)

        # Update database state
        rtu.update_state(RtuState.OFFLINE)
        db.commit()

        logger.info(f"RTU {station_name} disconnected")
        return True

    def get_sensor_values(self, station_name: str) -> List[Dict[str, Any]]:
        """Get real-time sensor values from controller."""
        return self._profinet.get_sensor_values(station_name)

    def get_actuator_states(self, station_name: str) -> List[Dict[str, Any]]:
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
_rtu_manager: Optional[RtuManager] = None


def get_rtu_manager() -> RtuManager:
    """Get or create the RTU manager."""
    global _rtu_manager
    if _rtu_manager is None:
        _rtu_manager = RtuManager()
    return _rtu_manager
