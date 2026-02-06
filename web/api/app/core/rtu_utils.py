"""
Water Treatment Controller - Shared RTU Utilities
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Common utility functions for RTU operations used across multiple endpoints.

Architecture Decision (2026-01): Slots are NOT database entities.
See CLAUDE.md "Slots Architecture Decision" for rationale.
The get_slot_or_404 function was removed - slots are PROFINET frame
positions, not database records.
"""

from sqlalchemy.orm import Session

from ..models.rtu import RTU, RtuState
from ..schemas.common import DataQuality
from .exceptions import RtuNotFoundError


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


def hex_string_to_int(hex_str: str | None, default: int = 0) -> int:
    """
    Convert hex string (e.g., "0x0493") to integer.

    Handles None values and invalid formats gracefully.
    Common pattern for vendor_id/device_id conversion.

    Args:
        hex_str: Hex string like "0x0493" or None
        default: Value to return if hex_str is None or invalid

    Returns:
        Integer value of hex string, or default if conversion fails

    Examples:
        >>> hex_string_to_int("0x0493")
        1171
        >>> hex_string_to_int(None)
        0
        >>> hex_string_to_int("0x002A", None)
        42
    """
    if not hex_str:
        return default
    try:
        return int(hex_str, 16)
    except (ValueError, TypeError):
        return default


def int_to_hex_string(value: int | None) -> str | None:
    """
    Convert integer to hex string format (e.g., "0x0493").

    Args:
        value: Integer value or None

    Returns:
        Hex string like "0x0493" or None if input is None

    Examples:
        >>> int_to_hex_string(1171)
        "0x0493"
        >>> int_to_hex_string(None)
        None
    """
    if value is None:
        return None
    return f"0x{value:04X}"


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
