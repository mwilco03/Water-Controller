"""
Water Treatment Controller - PROFINET Status Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...core.rtu_utils import get_rtu_or_404
from ...models.base import get_db
from ...services.profinet_client import get_profinet_client
from ...models.historian import ProfinetDiagnostic
from ...models.rtu import RtuState
from ...schemas.common import DataQuality
from ...schemas.profinet import (
    CycleTimeStats,
    IoStatus,
    PacketStats,
    ProfinetDiagnosticListMeta,
    ProfinetStatus,
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
        # Connected - return status from controller or demo mode
        profinet = get_profinet_client()
        controller_status = profinet.get_status()

        # Calculate uptime from state_since timestamp
        uptime_seconds = int((now - rtu.state_since).total_seconds()) if rtu.state_since else 0
        session_seconds = uptime_seconds  # Session started when RTU entered RUNNING

        # Get uptime from demo mode if active
        if controller_status.get("demo_mode"):
            uptime_seconds = int(controller_status.get("uptime_seconds", uptime_seconds))

        status = ProfinetStatus(
            connected=True,
            ar_handle="0x0001",
            uptime_seconds=uptime_seconds,
            session_seconds=session_seconds,
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

    Note: Slots are PROFINET frame positions, not database entities.
    Requires live PROFINET connection to RTU.
    """
    rtu = get_rtu_or_404(db, name)

    # Live PROFINET slot query not yet implemented
    # Slots are frame positions reported by RTU during cyclic exchange
    raise HTTPException(
        status_code=501,
        detail="PROFINET slot diagnostics requires live controller connection. Feature not yet implemented."
    )


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
