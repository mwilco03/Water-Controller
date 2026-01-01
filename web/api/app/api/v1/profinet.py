"""
Water Treatment Controller - PROFINET Status Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...core.rtu_utils import get_rtu_or_404
from ...models.base import get_db
from ...models.historian import ProfinetDiagnostic
from ...models.rtu import RtuState, Slot, SlotStatus
from ...schemas.common import DataQuality
from ...schemas.profinet import (
    CycleTimeStats,
    IoStatus,
    PacketStats,
    ProfinetDiagnosticListMeta,
    ProfinetSlot,
    ProfinetStatus,
    ProfinetSubslot,
)
from ...schemas.profinet import (
    ProfinetDiagnostic as ProfinetDiagnosticSchema,
)

router = APIRouter()


@router.get("/status")
async def get_profinet_status(
    name: str = Path(..., description="RTU station name"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get PROFINET connection health and I/O status.

    Returns minimal data if RTU not connected.
    """
    rtu = get_rtu_or_404(db, name)
    now = datetime.now(UTC)

    if rtu.state == RtuState.RUNNING:
        # Connected - return full status
        # In a real implementation, these values would come from shared memory
        status = ProfinetStatus(
            connected=True,
            ar_handle="0x0001",
            uptime_seconds=3600,  # Placeholder
            session_seconds=1800,  # Placeholder
            cycle_time=CycleTimeStats(
                target_ms=32.0,
                actual_ms=31.5,
                min_ms=30.1,
                max_ms=35.2,
            ),
            packet_stats=PacketStats(
                sent=112500,
                received=112498,
                lost=2,
                loss_percent=0.0018,
            ),
            jitter_ms=0.5,
            io_status=IoStatus(
                input_bytes=64,
                output_bytes=32,
                last_update=now,
                data_quality=DataQuality.GOOD,
            ),
            last_error=rtu.last_error,
            timestamp=now,
        )
    else:
        # Not connected - minimal status
        status = ProfinetStatus(
            connected=False,
            state=rtu.state,
            last_connected=rtu.state_since,
            last_error=rtu.last_error,
            timestamp=now,
        )

    return build_success_response(status.model_dump())


@router.get("/slots")
async def get_profinet_slots(
    name: str = Path(..., description="RTU station name"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get PROFINET slot-level diagnostics.
    """
    rtu = get_rtu_or_404(db, name)

    slots = db.query(Slot).filter(Slot.rtu_id == rtu.id).order_by(Slot.slot_number).all()

    result = []
    for slot in slots:
        # Build subslot info based on module type
        subslots = []
        if slot.module_type and slot.module_type.startswith("AI"):
            subslots.append(ProfinetSubslot(
                subslot=1,
                io_type="input",
                bytes=8,
                status="OK" if slot.status == SlotStatus.OK else "UNKNOWN",
                diag_info=None,
            ).model_dump())
        elif slot.module_type and slot.module_type.startswith("AO"):
            subslots.append(ProfinetSubslot(
                subslot=1,
                io_type="output",
                bytes=8,
                status="OK" if slot.status == SlotStatus.OK else "UNKNOWN",
                diag_info=None,
            ).model_dump())

        slot_info = ProfinetSlot(
            slot=slot.slot_number,
            module_id=slot.module_id or "0x0000",
            module_ident=None,  # Would come from PROFINET
            subslots=subslots,
            status=slot.status or SlotStatus.EMPTY,
            pulled=slot.status == SlotStatus.PULLED,
            wrong_module=slot.status == SlotStatus.WRONG_MODULE,
        )
        result.append(slot_info.model_dump())

    return build_success_response(result)


@router.get("/diagnostics")
async def get_profinet_diagnostics(
    name: str = Path(..., description="RTU station name"),
    hours: int = Query(24, ge=1, le=168, description="Hours to retrieve"),
    level: str | None = Query(None, description="Filter by level (INFO, WARNING, ERROR)"),
    limit: int = Query(100, ge=1, le=1000, description="Max records"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get PROFINET diagnostic message log.
    """
    rtu = get_rtu_or_404(db, name)

    # Calculate time range
    now = datetime.now(UTC)
    from datetime import timedelta
    start_time = now - timedelta(hours=hours)

    query = db.query(ProfinetDiagnostic).filter(
        ProfinetDiagnostic.rtu_id == rtu.id,
        ProfinetDiagnostic.timestamp >= start_time
    )

    if level:
        query = query.filter(ProfinetDiagnostic.level == level.upper())

    total = query.count()
    diagnostics = query.order_by(ProfinetDiagnostic.timestamp.desc()).limit(limit).all()

    result = []
    for diag in diagnostics:
        result.append(ProfinetDiagnosticSchema(
            id=diag.id,
            timestamp=diag.timestamp,
            level=diag.level,
            source=diag.source,
            message=diag.message,
            details=diag.details,
        ).model_dump())

    meta = ProfinetDiagnosticListMeta(
        total=total,
        filtered=len(result),
        hours=hours,
    )

    return {
        "data": result,
        "meta": meta.model_dump(),
    }
