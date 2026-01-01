"""
Water Treatment Controller - Alarm Management Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Access Model:
- GET endpoints: View access (no authentication required)
- POST/PUT/DELETE endpoints: Control access (authentication required)
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from ...core.auth import log_control_action, require_control_access
from ...core.errors import build_success_response
from ...models.alarm import AlarmState
from ...models.base import get_db
from ...persistence import alarms as alarm_persistence
from ...schemas.alarm import (
    AlarmAcknowledgeRequest,
    AlarmListMeta,
    AlarmShelveRequest,
    ShelvedAlarm,
)
from ...schemas.alarm import (
    AlarmEvent as AlarmEventSchema,
)
from ...services.alarm_service import get_alarm_service

router = APIRouter()


@router.get("")
async def list_alarms(
    rtu: str | None = Query(None, description="Filter by RTU station name"),
    priority: str | None = Query(None, description="Filter by priority"),
    acknowledged: bool | None = Query(None, description="Filter by acknowledged status"),
    limit: int = Query(100, ge=1, le=1000, description="Max records"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    List active alarms across all RTUs.
    """
    service = get_alarm_service(db)
    events, stats = service.list_active_alarms(
        rtu_name=rtu,
        priority=priority,
        acknowledged=acknowledged,
        limit=limit,
    )

    result = [
        AlarmEventSchema(**service.event_to_dict(event)).model_dump()
        for event in events
    ]

    meta = AlarmListMeta(
        total=stats["total"],
        active=stats["active"],
        unacknowledged=stats["unacknowledged"],
    )

    return {
        "data": result,
        "meta": meta.model_dump(),
    }


@router.get("/history")
async def alarm_history(
    start: datetime | None = Query(None, description="Start time"),
    end: datetime | None = Query(None, description="End time"),
    rtu: str | None = Query(None, description="Filter by RTU"),
    priority: str | None = Query(None, description="Filter by priority"),
    limit: int = Query(100, ge=1, le=1000, description="Max records"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get historical alarm log.
    """
    service = get_alarm_service(db)
    events, total = service.get_alarm_history(
        start=start,
        end=end,
        rtu_name=rtu,
        priority=priority,
        limit=limit,
    )

    result = [
        AlarmEventSchema(**service.event_to_dict(event)).model_dump()
        for event in events
    ]

    # Determine actual time range used
    from datetime import UTC, timedelta
    now = datetime.now(UTC)
    actual_end = end or now
    actual_start = start or (actual_end - timedelta(hours=24))

    return {
        "data": result,
        "meta": {
            "total": total,
            "start": actual_start.isoformat(),
            "end": actual_end.isoformat(),
        },
    }


@router.post("/{alarm_id}/acknowledge")
async def acknowledge_alarm(
    alarm_id: int = Path(..., description="Alarm event ID"),
    request: AlarmAcknowledgeRequest | None = None,
    db: Session = Depends(get_db),
    session: dict = Depends(require_control_access)
) -> dict[str, Any]:
    """
    Acknowledge an alarm.

    **Authentication Required**: This is a control action requiring
    operator or admin role.
    """
    username = session.get("username", "unknown")
    service = get_alarm_service(db)

    event = service.get_alarm_event(alarm_id)

    if event.state == AlarmState.CLEARED:
        return build_success_response({
            "id": alarm_id,
            "state": event.state,
            "message": "Alarm already cleared"
        })

    event = service.acknowledge_alarm(
        alarm_id=alarm_id,
        username=username,
        note=request.note if request else None,
    )

    log_control_action(
        session=session,
        action="ALARM_ACK",
        target=f"alarm/{alarm_id}",
        details=request.note if request else None,
    )

    return build_success_response({
        "id": alarm_id,
        "state": event.state,
        "acknowledged_at": event.acknowledged_at.isoformat() if event.acknowledged_at else None,
        "acknowledged_by": event.acknowledged_by,
    })


@router.post("/acknowledge-all")
async def acknowledge_all_alarms(
    rtu: str | None = Query(None, description="Filter by RTU"),
    request: AlarmAcknowledgeRequest | None = None,
    db: Session = Depends(get_db),
    session: dict = Depends(require_control_access)
) -> dict[str, Any]:
    """
    Acknowledge all active alarms.

    **Authentication Required**: This is a control action requiring
    operator or admin role.
    """
    username = session.get("username", "unknown")
    service = get_alarm_service(db)

    count = service.acknowledge_all(
        username=username,
        rtu_name=rtu,
        note=request.note if request else None,
    )

    log_control_action(
        session=session,
        action="ALARM_ACK_ALL",
        target=f"alarms{'/'+rtu if rtu else ''}",
        details=f"Acknowledged {count} alarms",
    )

    return build_success_response({
        "acknowledged_count": count,
        "rtu_filter": rtu,
    })


# ============== Alarm Shelving Endpoints (ISA-18.2) ==============

@router.get("/shelved")
async def list_shelved_alarms(
    include_expired: bool = Query(False, description="Include expired shelved alarms"),
) -> dict[str, Any]:
    """
    List all shelved alarms.

    Shelved alarms are temporarily suppressed from notifications.
    Per ISA-18.2, shelving is for known issues being worked on.
    """
    shelved = alarm_persistence.get_shelved_alarms(include_expired=include_expired)

    result = []
    for shelf in shelved:
        result.append(ShelvedAlarm(
            id=shelf["id"],
            rtu_station=shelf["rtu_station"],
            slot=shelf["slot"],
            shelved_by=shelf["shelved_by"],
            shelved_at=shelf["shelved_at"],
            duration_minutes=shelf["shelf_duration_minutes"],
            expires_at=shelf["expires_at"],
            reason=shelf.get("reason"),
            active=bool(shelf["active"]),
        ).model_dump())

    return {
        "data": result,
        "meta": {
            "total": len(result),
            "include_expired": include_expired,
        },
    }


@router.post("/shelve/{rtu_station}/{slot}")
async def shelve_alarm(
    rtu_station: str = Path(..., description="RTU station name"),
    slot: int = Path(..., ge=0, description="Slot number"),
    request: AlarmShelveRequest = ...,
    session: dict = Depends(require_control_access)
) -> dict[str, Any]:
    """
    Shelve an alarm for a specified duration.

    Shelved alarms will not generate notifications until the shelf expires
    or is manually removed. Per HARMONIOUS_SYSTEM_DESIGN.md, version mismatch
    alarms and other known-issue alarms should be shelve-able.

    **Authentication Required**: This is a control action requiring
    operator or admin role.

    Duration: 1 to 1440 minutes (24 hours max)
    """
    username = session.get("username", "unknown")

    shelf_id = alarm_persistence.shelve_alarm(
        rtu_station=rtu_station,
        slot=slot,
        username=username,
        duration_minutes=request.duration_minutes,
        reason=request.reason,
    )

    log_control_action(
        session=session,
        action="ALARM_SHELVE",
        target=f"{rtu_station}/{slot}",
        details=f"Shelved for {request.duration_minutes} min: {request.reason or 'No reason'}",
    )

    return build_success_response({
        "shelf_id": shelf_id,
        "rtu_station": rtu_station,
        "slot": slot,
        "duration_minutes": request.duration_minutes,
        "message": f"Alarm shelved for {request.duration_minutes} minutes",
    })


@router.delete("/shelve/{shelf_id}")
async def unshelve_alarm(
    shelf_id: int = Path(..., description="Shelf entry ID"),
    session: dict = Depends(require_control_access)
) -> dict[str, Any]:
    """
    Remove an alarm from shelf before expiration.

    **Authentication Required**: This is a control action requiring
    operator or admin role.
    """
    username = session.get("username", "unknown")

    # Get shelf info before removing
    shelf = alarm_persistence.get_shelved_alarm(shelf_id)
    if not shelf:
        return build_success_response({
            "success": False,
            "message": f"Shelf entry {shelf_id} not found",
        })

    success = alarm_persistence.unshelve_alarm(shelf_id, username)

    if success:
        log_control_action(
            session=session,
            action="ALARM_UNSHELVE",
            target=f"{shelf['rtu_station']}/{shelf['slot']}",
            details=f"Manually unshelved shelf_id={shelf_id}",
        )

    return build_success_response({
        "success": success,
        "shelf_id": shelf_id,
        "message": "Alarm unshelved" if success else "Failed to unshelve alarm",
    })


@router.get("/shelved/check/{rtu_station}/{slot}")
async def check_alarm_shelved(
    rtu_station: str = Path(..., description="RTU station name"),
    slot: int = Path(..., ge=0, description="Slot number"),
) -> dict[str, Any]:
    """
    Check if a specific alarm is currently shelved.
    """
    is_shelved = alarm_persistence.is_alarm_shelved(rtu_station, slot)

    return build_success_response({
        "rtu_station": rtu_station,
        "slot": slot,
        "is_shelved": is_shelved,
    })
