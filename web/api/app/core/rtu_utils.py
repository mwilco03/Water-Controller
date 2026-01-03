"""
Water Treatment Controller - Shared RTU Utilities
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Common utility functions for RTU operations used across multiple endpoints.
"""

from sqlalchemy.orm import Session

from ..models.rtu import RTU, RtuState, Slot
from ..schemas.common import DataQuality
from .exceptions import RtuNotFoundError, SlotNotFoundError


def get_rtu_or_404(db: Session, name: str) -> RTU:
    """
    Get RTU by station name or raise 404.

    Args:
        db: Database session
        name: Station name to look up

    Returns:
        RTU instance

    Raises:
        RtuNotFoundError: If no RTU with that name exists
    """
    rtu = db.query(RTU).filter(RTU.station_name == name).first()
    if not rtu:
        raise RtuNotFoundError(name)
    return rtu


def get_slot_or_404(db: Session, rtu: RTU, slot_number: int) -> Slot:
    """
    Get slot by number or raise 404.

    Args:
        db: Database session
        rtu: RTU instance
        slot_number: Slot number to look up

    Returns:
        Slot instance

    Raises:
        SlotNotFoundError: If no slot with that number exists
    """
    slot = db.query(Slot).filter(
        Slot.rtu_id == rtu.id,
        Slot.slot_number == slot_number
    ).first()
    if not slot:
        raise SlotNotFoundError(rtu.station_name, slot_number, rtu.slot_count)
    return slot


def get_data_quality(rtu_state: str) -> DataQuality:
    """
    Determine data quality based on RTU state.

    Maps RTU connection states to OPC UA-compatible quality codes:
    - RUNNING -> GOOD (0x00)
    - CONNECTING/DISCOVERY -> UNCERTAIN (0x40)
    - All others -> NOT_CONNECTED (0xC0)

    Args:
        rtu_state: Current RTU state string

    Returns:
        DataQuality enum value
    """
    if rtu_state == RtuState.RUNNING:
        return DataQuality.GOOD
    elif rtu_state in [RtuState.CONNECTING, RtuState.DISCOVERY]:
        return DataQuality.UNCERTAIN
    else:
        return DataQuality.NOT_CONNECTED


# Protocol-to-Application State Mapping
# =====================================
# The codebase uses two state systems:
#
# 1. Protocol Layer (shm_client.py CONN_STATE_*):
#    These are numeric codes from the C controller shared memory.
#    Values: IDLE=0, CONNECTING=1, CONNECTED=2, RUNNING=3, ERROR=4, OFFLINE=5
#
# 2. Application Layer (models/rtu.py RtuState):
#    These are string states stored in the database.
#    Values: OFFLINE, CONNECTING, DISCOVERY, RUNNING, ERROR
#
# The mapping below converts protocol states to application states:

PROTOCOL_TO_APP_STATE = {
    0: RtuState.OFFLINE,      # IDLE -> OFFLINE (not connected yet)
    1: RtuState.CONNECTING,   # CONNECTING -> CONNECTING
    2: RtuState.DISCOVERY,    # CONNECTED -> DISCOVERY (AR established, enumerating)
    3: RtuState.RUNNING,      # RUNNING -> RUNNING
    4: RtuState.ERROR,        # ERROR -> ERROR
    5: RtuState.OFFLINE,      # OFFLINE -> OFFLINE
}


def protocol_state_to_app_state(protocol_state: int) -> str:
    """
    Convert protocol-layer state code to application-layer state string.

    Args:
        protocol_state: Numeric state from shared memory (0-5)

    Returns:
        Application-layer state string (RtuState value)
    """
    return PROTOCOL_TO_APP_STATE.get(protocol_state, RtuState.OFFLINE)
