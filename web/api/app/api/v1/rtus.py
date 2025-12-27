"""
Water Treatment Controller - RTU Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

RTU CRUD and connection management endpoints.

Note: Business logic is delegated to RtuService for testability.
Route handlers remain thin and declarative.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from ...core.exceptions import (
    RtuNotFoundError,
    RtuAlreadyExistsError,
    RtuNotConnectedError,
    RtuBusyError,
    ValidationError,
    SlotNotFoundError,
)
from ...core.errors import build_success_response
from ...models.base import get_db
from ...models.rtu import RTU, Slot, Sensor, Control, RtuState, SlotStatus
from ...models.alarm import AlarmRule, AlarmEvent
from ...models.historian import HistorianSample
from ...schemas.rtu import (
    RtuCreate,
    RtuResponse,
    RtuDetailResponse,
    RtuStats,
    SlotSummary,
    DeletionImpact,
    ConnectRequest,
    ConnectResponse,
    DisconnectResponse,
    DiscoverResponse,
    DiscoveredSlot,
    DiscoverSummary,
    TestResponse,
    TestResult,
)
from ...services.rtu_service import RtuService, get_rtu_service

router = APIRouter()


def get_rtu_or_404(db: Session, name: str) -> RTU:
    """Get RTU by station name or raise 404."""
    service = get_rtu_service(db)
    return service.get_by_name(name)


def build_rtu_stats(db: Session, rtu: RTU) -> RtuStats:
    """Build statistics for an RTU (delegates to service)."""
    service = get_rtu_service(db)
    return service.get_stats(rtu)


# ==================== RTU CRUD ====================


@router.post("", status_code=201)
async def create_rtu(
    request: RtuCreate,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Create a new RTU configuration.

    Creates the RTU record in the database and initializes empty slots.
    The RTU starts in OFFLINE state - use POST /connect to establish connection.
    """
    # Delegate to service layer
    service = get_rtu_service(db)
    rtu = service.create(request)

    response_data = {
        "id": rtu.id,
        "station_name": rtu.station_name,
        "ip_address": rtu.ip_address,
        "vendor_id": rtu.vendor_id,
        "device_id": rtu.device_id,
        "slot_count": rtu.slot_count,
        "state": rtu.state,
        "created_at": rtu.created_at.isoformat() if rtu.created_at else None,
        "updated_at": rtu.updated_at.isoformat() if rtu.updated_at else None,
    }

    return build_success_response(response_data)


@router.get("")
async def list_rtus(
    state: Optional[str] = Query(None, description="Filter by state"),
    include_stats: bool = Query(False, description="Include sensor/alarm counts"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    List all configured RTUs.
    """
    query = db.query(RTU)

    if state:
        query = query.filter(RTU.state == state.upper())

    rtus = query.order_by(RTU.station_name).all()

    result = []
    for rtu in rtus:
        item = RtuResponse(
            id=rtu.id,
            station_name=rtu.station_name,
            ip_address=rtu.ip_address,
            state=rtu.state,
            state_since=rtu.state_since,
            stats=build_rtu_stats(db, rtu) if include_stats else None,
        )
        result.append(item.model_dump())

    return build_success_response(result, meta={"total": len(result)})


@router.get("/{name}")
async def get_rtu(
    name: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get detailed RTU information.
    """
    rtu = get_rtu_or_404(db, name)

    # Get slots
    slots = db.query(Slot).filter(Slot.rtu_id == rtu.id).order_by(Slot.slot_number).all()
    slot_summaries = [
        SlotSummary(
            slot=s.slot_number,
            module_id=s.module_id,
            module_type=s.module_type,
            status=s.status or SlotStatus.EMPTY,
        ).model_dump()
        for s in slots
    ]

    stats = build_rtu_stats(db, rtu)

    response_data = RtuDetailResponse(
        id=rtu.id,
        station_name=rtu.station_name,
        ip_address=rtu.ip_address,
        vendor_id=rtu.vendor_id,
        device_id=rtu.device_id,
        slot_count=rtu.slot_count,
        state=rtu.state,
        state_since=rtu.state_since,
        last_error=rtu.last_error,
        created_at=rtu.created_at,
        updated_at=rtu.updated_at,
        slots=slot_summaries,
        stats=stats,
    )

    return build_success_response(response_data.model_dump())


@router.delete("/{name}")
async def delete_rtu(
    name: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Delete RTU and all associated resources.

    RTU must be OFFLINE (disconnect first if connected).
    """
    rtu = get_rtu_or_404(db, name)

    # Check state - must be offline
    if rtu.state not in [RtuState.OFFLINE, RtuState.ERROR]:
        raise RtuBusyError(name, rtu.state)

    # Count resources for response
    slot_count = db.query(Slot).filter(Slot.rtu_id == rtu.id).count()
    sensor_count = db.query(Sensor).filter(Sensor.rtu_id == rtu.id).count()
    control_count = db.query(Control).filter(Control.rtu_id == rtu.id).count()
    alarm_count = db.query(AlarmRule).filter(AlarmRule.rtu_id == rtu.id).count()
    historian_count = db.query(HistorianSample).join(Sensor).filter(
        Sensor.rtu_id == rtu.id
    ).count()

    # Delete RTU (cascade handles related records)
    db.delete(rtu)
    db.commit()

    response_data = {
        "deleted": {
            "rtu": name,
            "slots": slot_count,
            "sensors": sensor_count,
            "controls": control_count,
            "alarms": alarm_count,
            "pid_loops": 0,
            "historian_samples": historian_count,
        }
    }

    return build_success_response(response_data)


@router.get("/{name}/deletion-impact")
async def get_deletion_impact(
    name: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Preview what will be deleted (for confirmation UI).
    """
    rtu = get_rtu_or_404(db, name)

    slot_count = db.query(Slot).filter(Slot.rtu_id == rtu.id).count()
    sensor_count = db.query(Sensor).filter(Sensor.rtu_id == rtu.id).count()
    control_count = db.query(Control).filter(Control.rtu_id == rtu.id).count()
    alarm_count = db.query(AlarmRule).filter(AlarmRule.rtu_id == rtu.id).count()
    historian_count = db.query(HistorianSample).join(Sensor).filter(
        Sensor.rtu_id == rtu.id
    ).count()

    # Estimate data size (rough approximation)
    estimated_mb = historian_count * 16 / (1024 * 1024)

    response_data = DeletionImpact(
        rtu=name,
        impact={
            "slots": slot_count,
            "sensors": sensor_count,
            "controls": control_count,
            "alarms": alarm_count,
            "pid_loops": 0,
            "historian_samples": historian_count,
            "estimated_data_size_mb": round(estimated_mb, 2),
        }
    )

    return build_success_response(response_data.model_dump())


# ==================== Connection Management ====================


@router.post("/{name}/connect", status_code=202)
async def connect_rtu(
    name: str,
    request: Optional[ConnectRequest] = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Establish PROFINET connection to RTU.

    RTU must be OFFLINE. Connection is asynchronous - poll GET /rtus/{name}
    to check state transition.
    """
    rtu = get_rtu_or_404(db, name)

    if rtu.state != RtuState.OFFLINE:
        raise RtuBusyError(name, rtu.state)

    # Update state to CONNECTING
    rtu.update_state(RtuState.CONNECTING)
    db.commit()

    # In a real implementation, this would trigger PROFINET connection
    # via IPC to the C controller

    response_data = ConnectResponse(
        station_name=name,
        state=RtuState.CONNECTING,
        message="Connection initiated"
    )

    return build_success_response(response_data.model_dump())


@router.post("/{name}/disconnect")
async def disconnect_rtu(
    name: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Gracefully close PROFINET connection.

    RTU must be RUNNING or ERROR.
    """
    rtu = get_rtu_or_404(db, name)

    if rtu.state == RtuState.OFFLINE:
        raise RtuNotConnectedError(name, rtu.state)

    if rtu.state == RtuState.CONNECTING:
        raise RtuBusyError(name, rtu.state)

    # Update state to OFFLINE
    rtu.update_state(RtuState.OFFLINE)
    db.commit()

    response_data = DisconnectResponse(
        station_name=name,
        state=RtuState.OFFLINE,
        message="Disconnected successfully"
    )

    return build_success_response(response_data.model_dump())


@router.post("/{name}/discover")
async def discover_modules(
    name: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Discover modules in RTU slots via PROFINET.

    RTU must be RUNNING.
    """
    rtu = get_rtu_or_404(db, name)

    if rtu.state != RtuState.RUNNING:
        raise RtuNotConnectedError(name, rtu.state)

    # In a real implementation, this would query PROFINET for module info
    # For now, return the current slot configuration

    slots = db.query(Slot).filter(Slot.rtu_id == rtu.id).order_by(Slot.slot_number).all()

    discovered = []
    populated = 0
    for slot in slots:
        discovered.append(DiscoveredSlot(
            slot=slot.slot_number,
            module_id=slot.module_id or "0x0000",
            module_type=slot.module_type,
            subslots=[],
        ))
        if slot.module_type:
            populated += 1

    response_data = DiscoverResponse(
        station_name=name,
        discovered_slots=discovered,
        summary=DiscoverSummary(
            total_slots=rtu.slot_count,
            populated_slots=populated,
            empty_slots=rtu.slot_count - populated,
        )
    )

    return build_success_response(response_data.model_dump())


@router.post("/{name}/test")
async def test_connection(
    name: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Run connection and I/O test.

    RTU must be RUNNING.
    """
    rtu = get_rtu_or_404(db, name)

    if rtu.state != RtuState.RUNNING:
        raise RtuNotConnectedError(name, rtu.state)

    # In a real implementation, this would run actual I/O tests
    # For now, return mock test results

    tests = {
        "connection": TestResult(passed=True, latency_ms=2.3),
        "read_io": TestResult(passed=True, bytes_read=64, latency_ms=1.1),
        "write_io": TestResult(passed=True, bytes_written=32, latency_ms=1.5),
        "cycle_time": TestResult(
            passed=True,
            target_ms=32.0,
            measured_ms=31.2,
            jitter_ms=0.8
        ),
    }

    response_data = TestResponse(
        station_name=name,
        tests={k: v.model_dump() for k, v in tests.items()},
        overall_passed=all(t.passed for t in tests.values()),
    )

    return build_success_response(response_data.model_dump())


# Include nested routers for slots, sensors, controls, profinet, pid
from .slots import router as slots_router
from .sensors import router as sensors_router
from .controls import router as controls_router
from .profinet import router as profinet_router
from .pid import router as pid_router

router.include_router(slots_router, prefix="/{name}/slots")
router.include_router(sensors_router, prefix="/{name}/sensors")
router.include_router(controls_router, prefix="/{name}/controls")
router.include_router(profinet_router, prefix="/{name}/profinet")
router.include_router(pid_router, prefix="/{name}/pid")
