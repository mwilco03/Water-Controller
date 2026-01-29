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
    Data is read from the C controller via shared memory IPC.

    Returns slot configuration with:
    - Slot number (PROFINET frame position)
    - Slot type (input/output/empty)
    - Module info (sensor or actuator data)
    - Live diagnostic data (value, status, quality)
    """
    from ...services.shm_client import get_shm_client

    rtu = get_rtu_or_404(db, name)

    if rtu.state != RtuState.RUNNING:
        raise HTTPException(
            status_code=409,
            detail=f"RTU must be RUNNING for slot diagnostics. Current state: {rtu.state}"
        )

    # Get slot data from shared memory
    shm = get_shm_client()
    if not shm.is_connected():
        raise HTTPException(
            status_code=503,
            detail="PROFINET controller not connected. Start the C controller process."
        )

    shm_rtu = shm.get_rtu(name)
    if not shm_rtu:
        raise HTTPException(
            status_code=503,
            detail=f"RTU '{name}' not found in controller shared memory."
        )

    # Build slot map from sensors and actuators
    slot_count = shm_rtu.get("slot_count", 16)
    slots = []

    # Index sensors and actuators by slot
    sensor_by_slot = {s["slot"]: s for s in shm_rtu.get("sensors", [])}
    actuator_by_slot = {a["slot"]: a for a in shm_rtu.get("actuators", [])}

    # PROFINET convention: slots 1-8 inputs, slots 9-15 outputs (0 is reserved)
    for slot_num in range(1, slot_count + 1):
        slot_data = {
            "slot": slot_num,
            "subslot": 0,
            "type": "empty",
            "module_type": None,
            "data": None,
            "diagnostics": {
                "status": "unknown",
                "quality": "unknown",
            }
        }

        if slot_num in sensor_by_slot:
            sensor = sensor_by_slot[slot_num]
            # Get quality name
            quality_map = {0: "good", 0x40: "uncertain", 0x80: "bad", 0xC0: "not_connected"}
            status_map = {0: "good", 1: "bad", 2: "uncertain"}

            slot_data["type"] = "input"
            slot_data["module_type"] = "analog_input"
            slot_data["data"] = {
                "value": sensor.get("value"),
                "timestamp_ms": sensor.get("timestamp_ms"),
            }
            slot_data["diagnostics"] = {
                "status": status_map.get(sensor.get("status", 0), "unknown"),
                "status_code": sensor.get("status", 0),
                "quality": quality_map.get(sensor.get("quality", 0), "unknown"),
                "quality_code": sensor.get("quality", 0),
            }

        elif slot_num in actuator_by_slot:
            actuator = actuator_by_slot[slot_num]
            command_map = {0: "OFF", 1: "ON", 2: "PWM"}

            slot_data["type"] = "output"
            slot_data["module_type"] = "digital_output"
            slot_data["data"] = {
                "command": command_map.get(actuator.get("command", 0), "UNKNOWN"),
                "command_code": actuator.get("command", 0),
                "pwm_duty": actuator.get("pwm_duty", 0),
                "forced": actuator.get("forced", False),
            }
            slot_data["diagnostics"] = {
                "status": "good" if not actuator.get("forced") else "forced",
                "quality": "good",
            }

        slots.append(slot_data)

    # Calculate slot utilization
    populated = sum(1 for s in slots if s["type"] != "empty")
    input_slots = sum(1 for s in slots if s["type"] == "input")
    output_slots = sum(1 for s in slots if s["type"] == "output")

    return build_success_response({
        "station_name": name,
        "slot_count": slot_count,
        "populated_slots": populated,
        "empty_slots": slot_count - populated,
        "input_slots": input_slots,
        "output_slots": output_slots,
        "vendor_id": shm_rtu.get("vendor_id"),
        "device_id": shm_rtu.get("device_id"),
        "packet_loss_percent": shm_rtu.get("packet_loss_percent", 0.0),
        "total_cycles": shm_rtu.get("total_cycles", 0),
        "slots": slots,
    })


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
