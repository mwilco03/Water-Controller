"""
Water Treatment Controller - Control Couplings Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Endpoints for control couplings and interlocks.
Couplings define relationships between controls, PID loops, and alarms.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...models.base import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# In-memory storage for couplings (in production, use database)
# Couplings define relationships like:
# - PID output → Pump enable
# - Level high alarm → Valve close
# - Pump 1 run → Pump 2 standby
_couplings: list[dict] = []


@router.get("/couplings")
async def list_couplings(
    rtu: str | None = Query(None, description="Filter by RTU name"),
    active: bool | None = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    List control couplings and interlocks.

    Couplings define automated relationships between:
    - PID loops and controls (cascade, enable/disable)
    - Interlocks and controls (safety enable/disable)
    - Controls and other controls (sequencing)
    - Alarms and controls (protective actions)

    Returns all configured couplings, optionally filtered by RTU or status.
    """
    # Filter couplings
    result = _couplings

    if rtu:
        result = [c for c in result if c.get("target_rtu") == rtu]

    if active is not None:
        result = [c for c in result if c.get("active") == active]

    return build_success_response({
        "couplings": result,
        "count": len(result),
    })


@router.get("/couplings/{coupling_id}")
async def get_coupling(
    coupling_id: int,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get a specific coupling by ID.
    """
    from fastapi import HTTPException

    coupling = next((c for c in _couplings if c.get("coupling_id") == coupling_id), None)
    if not coupling:
        raise HTTPException(status_code=404, detail=f"Coupling {coupling_id} not found")

    return build_success_response(coupling)


@router.post("/couplings")
async def create_coupling(
    coupling: dict,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Create a new control coupling.

    Required fields:
    - name: Coupling name
    - source_type: 'pid', 'interlock', or 'control'
    - source_id: ID of source entity
    - target_type: 'control', 'pid', or 'alarm'
    - target_id: ID of target entity
    - target_rtu: RTU station name
    - coupling_type: 'enable', 'disable', 'limit', or 'cascade'
    """
    # Generate ID
    coupling_id = max((c.get("coupling_id", 0) for c in _couplings), default=0) + 1

    new_coupling = {
        "coupling_id": coupling_id,
        "name": coupling.get("name", f"Coupling {coupling_id}"),
        "description": coupling.get("description", ""),
        "source_type": coupling.get("source_type", "control"),
        "source_id": coupling.get("source_id"),
        "source_name": coupling.get("source_name", ""),
        "target_type": coupling.get("target_type", "control"),
        "target_id": coupling.get("target_id"),
        "target_name": coupling.get("target_name", ""),
        "target_rtu": coupling.get("target_rtu", ""),
        "target_slot": coupling.get("target_slot"),
        "coupling_type": coupling.get("coupling_type", "enable"),
        "condition": coupling.get("condition"),
        "active": coupling.get("active", True),
    }

    _couplings.append(new_coupling)
    logger.info(f"Created coupling: {new_coupling['name']}")

    return build_success_response(new_coupling)


@router.delete("/couplings/{coupling_id}")
async def delete_coupling(
    coupling_id: int,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Delete a coupling by ID.
    """
    from fastapi import HTTPException

    global _couplings
    original_count = len(_couplings)
    _couplings = [c for c in _couplings if c.get("coupling_id") != coupling_id]

    if len(_couplings) == original_count:
        raise HTTPException(status_code=404, detail=f"Coupling {coupling_id} not found")

    logger.info(f"Deleted coupling {coupling_id}")
    return build_success_response({"deleted": True, "coupling_id": coupling_id})
