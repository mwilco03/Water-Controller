"""
Water Treatment Controller - Alarm Management Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Access Model:
- GET endpoints: View access (no authentication required)
- POST/PUT/DELETE endpoints: Control access (authentication required)
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from ...core.auth import log_control_action, require_control_access
from ...core.errors import build_success_response
from ...core.exceptions import AlarmNotFoundError
from ...models.alarm import AlarmEvent, AlarmState
from ...models.base import get_db
from ...persistence import alarms as alarm_persistence
from ...schemas.alarm import (
    AlarmAcknowledgeRequest,
    AlarmListMeta,
    AlarmShelveRequest,
    ScheduledMaintenanceCreate,
    ShelvedAlarm,
)
from ...services.alarm_service import AlarmService

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

    Uses AlarmService for query logic (single source of truth).
    """
    service = AlarmService(db)
    events, stats = service.list_active_alarms(
        rtu_name=rtu,
        priority=priority,
        acknowledged=acknowledged,
        limit=limit,
    )

    result = [service.event_to_dict(event) for event in events]

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

    Uses AlarmService for query logic (single source of truth).
    """
    service = AlarmService(db)
    events, total = service.get_alarm_history(
        start=start,
        end=end,
        rtu_name=rtu,
        priority=priority,
        limit=limit,
    )

    result = [service.event_to_dict(event) for event in events]

    # Calculate actual time range used
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

    Uses AlarmService for business logic (single source of truth).
    """
    username = session.get("username", "unknown")
    service = AlarmService(db)

    # Check if alarm exists first
    try:
        event = service.get_alarm_event(alarm_id)
    except AlarmNotFoundError:
        raise

    if event.state == AlarmState.CLEARED:
        # Already cleared - nothing to acknowledge
        return build_success_response({
            "id": alarm_id,
            "state": event.state,
            "message": "Alarm already cleared"
        })

    # Acknowledge with authenticated user via service
    event = service.acknowledge_alarm(
        alarm_id=alarm_id,
        username=username,
        note=request.note if request else None
    )

    # Log control action
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

    Uses AlarmService for business logic (single source of truth).
    """
    username = session.get("username", "unknown")
    service = AlarmService(db)

    count = service.acknowledge_all(
        username=username,
        rtu_name=rtu,
        note=request.note if request else None
    )

    # Log control action
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


# ============== Scheduled Maintenance Endpoints ==============

@router.get("/maintenance")
async def list_maintenance_windows(
    status: str | None = Query(None, description="Filter by status (SCHEDULED, ACTIVE, COMPLETED, CANCELLED)"),
    rtu: str | None = Query(None, description="Filter by RTU station"),
    include_past: bool = Query(False, description="Include completed/cancelled windows"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    List scheduled maintenance windows.

    Returns upcoming and active maintenance windows by default.
    Use include_past=true to see historical windows.
    """
    from ...models.alarm import ScheduledMaintenance

    query = db.query(ScheduledMaintenance)

    if status:
        query = query.filter(ScheduledMaintenance.status == status.upper())
    elif not include_past:
        query = query.filter(ScheduledMaintenance.status.in_(["SCHEDULED", "ACTIVE"]))

    if rtu:
        query = query.filter(ScheduledMaintenance.rtu_station == rtu)

    windows = query.order_by(ScheduledMaintenance.start_time).all()

    result = []
    for w in windows:
        result.append({
            "id": w.id,
            "rtu_station": w.rtu_station,
            "slot": w.slot,
            "scheduled_by": w.scheduled_by,
            "scheduled_at": w.scheduled_at.isoformat() if w.scheduled_at else None,
            "start_time": w.start_time.isoformat() if w.start_time else None,
            "end_time": w.end_time.isoformat() if w.end_time else None,
            "reason": w.reason,
            "work_order": w.work_order,
            "status": w.status,
            "activated_at": w.activated_at.isoformat() if w.activated_at else None,
            "completed_at": w.completed_at.isoformat() if w.completed_at else None,
            "cancelled_by": w.cancelled_by,
            "cancelled_at": w.cancelled_at.isoformat() if w.cancelled_at else None,
        })

    return {
        "data": result,
        "meta": {
            "total": len(result),
            "include_past": include_past,
        },
    }


@router.post("/maintenance")
async def create_maintenance_window(
    request: ScheduledMaintenanceCreate,
    db: Session = Depends(get_db),
    session: dict = Depends(require_control_access)
) -> dict[str, Any]:
    """
    Schedule a maintenance window for alarm suppression.

    **Authentication Required**: This is a control action requiring
    operator or admin role.

    During the scheduled window, alarms for the specified RTU/slot
    will be automatically shelved.
    """
    from ...models.alarm import ScheduledMaintenance

    username = session.get("username", "unknown")

    # Validate start time is in the future (with 1 minute grace)
    now = datetime.now(UTC)
    if request.start_time < now - timedelta(minutes=1):
        return build_success_response({
            "success": False,
            "message": "Start time must be in the future",
        })

    # Create the scheduled maintenance entry
    window = ScheduledMaintenance(
        rtu_station=request.rtu_station,
        slot=request.slot,
        scheduled_by=username,
        start_time=request.start_time,
        end_time=request.end_time,
        reason=request.reason,
        work_order=request.work_order,
        status="SCHEDULED",
    )
    db.add(window)
    db.commit()
    db.refresh(window)

    log_control_action(
        session=session,
        action="MAINTENANCE_SCHEDULE",
        target=f"{request.rtu_station}/{request.slot}",
        details=f"Scheduled {request.start_time} to {request.end_time}: {request.reason}",
    )

    return build_success_response({
        "id": window.id,
        "rtu_station": window.rtu_station,
        "slot": window.slot,
        "start_time": window.start_time.isoformat(),
        "end_time": window.end_time.isoformat(),
        "status": window.status,
        "message": "Maintenance window scheduled",
    })


@router.delete("/maintenance/{window_id}")
async def cancel_maintenance_window(
    window_id: int = Path(..., description="Maintenance window ID"),
    db: Session = Depends(get_db),
    session: dict = Depends(require_control_access)
) -> dict[str, Any]:
    """
    Cancel a scheduled maintenance window.

    **Authentication Required**: This is a control action requiring
    operator or admin role.

    Can only cancel windows that are SCHEDULED or ACTIVE.
    """
    from ...models.alarm import ScheduledMaintenance

    username = session.get("username", "unknown")

    window = db.query(ScheduledMaintenance).filter(ScheduledMaintenance.id == window_id).first()
    if not window:
        return build_success_response({
            "success": False,
            "message": f"Maintenance window {window_id} not found",
        })

    if window.status not in ("SCHEDULED", "ACTIVE"):
        return build_success_response({
            "success": False,
            "message": f"Cannot cancel window with status {window.status}",
        })

    window.status = "CANCELLED"
    window.cancelled_by = username
    window.cancelled_at = datetime.now(UTC)
    db.commit()

    log_control_action(
        session=session,
        action="MAINTENANCE_CANCEL",
        target=f"{window.rtu_station}/{window.slot}",
        details=f"Cancelled window {window_id}",
    )

    return build_success_response({
        "id": window_id,
        "status": "CANCELLED",
        "message": "Maintenance window cancelled",
    })


@router.get("/maintenance/{window_id}")
async def get_maintenance_window(
    window_id: int = Path(..., description="Maintenance window ID"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get details of a specific maintenance window.
    """
    from ...models.alarm import ScheduledMaintenance

    window = db.query(ScheduledMaintenance).filter(ScheduledMaintenance.id == window_id).first()
    if not window:
        return build_success_response({
            "success": False,
            "message": f"Maintenance window {window_id} not found",
        })

    return build_success_response({
        "id": window.id,
        "rtu_station": window.rtu_station,
        "slot": window.slot,
        "scheduled_by": window.scheduled_by,
        "scheduled_at": window.scheduled_at.isoformat() if window.scheduled_at else None,
        "start_time": window.start_time.isoformat() if window.start_time else None,
        "end_time": window.end_time.isoformat() if window.end_time else None,
        "reason": window.reason,
        "work_order": window.work_order,
        "status": window.status,
        "activated_at": window.activated_at.isoformat() if window.activated_at else None,
        "completed_at": window.completed_at.isoformat() if window.completed_at else None,
        "cancelled_by": window.cancelled_by,
        "cancelled_at": window.cancelled_at.isoformat() if window.cancelled_at else None,
    })
