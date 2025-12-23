"""
Water Treatment Controller - Alarm Management Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from ...core.exceptions import AlarmNotFoundError, RtuNotFoundError
from ...core.errors import build_success_response
from ...models.base import get_db
from ...models.rtu import RTU
from ...models.alarm import AlarmRule, AlarmEvent, AlarmState, AlarmPriority
from ...schemas.alarm import (
    AlarmEvent as AlarmEventSchema,
    AlarmAcknowledgeRequest,
    AlarmListMeta,
)

router = APIRouter()


@router.get("")
async def list_alarms(
    rtu: Optional[str] = Query(None, description="Filter by RTU station name"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    acknowledged: Optional[bool] = Query(None, description="Filter by acknowledged status"),
    limit: int = Query(100, ge=1, le=1000, description="Max records"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    List active alarms across all RTUs.
    """
    query = db.query(AlarmEvent).filter(AlarmEvent.state != AlarmState.CLEARED)

    if rtu:
        rtu_obj = db.query(RTU).filter(RTU.station_name == rtu).first()
        if not rtu_obj:
            raise RtuNotFoundError(rtu)
        query = query.filter(AlarmEvent.rtu_id == rtu_obj.id)

    if priority:
        query = query.filter(
            AlarmRule.priority == priority.upper()
        ).join(AlarmRule)

    if acknowledged is not None:
        if acknowledged:
            query = query.filter(AlarmEvent.state == AlarmState.ACKNOWLEDGED)
        else:
            query = query.filter(AlarmEvent.state == AlarmState.ACTIVE)

    total = query.count()
    active_count = db.query(AlarmEvent).filter(AlarmEvent.state == AlarmState.ACTIVE).count()
    unack_count = db.query(AlarmEvent).filter(
        AlarmEvent.state == AlarmState.ACTIVE,
        AlarmEvent.acknowledged_at.is_(None)
    ).count()

    events = query.order_by(AlarmEvent.activated_at.desc()).limit(limit).all()

    result = []
    for event in events:
        rule = event.rule
        rtu_obj = event.rtu

        alarm_schema = AlarmEventSchema(
            id=event.id,
            rtu=rtu_obj.station_name if rtu_obj else "unknown",
            tag=rule.tag if rule else "unknown",
            priority=rule.priority if rule else AlarmPriority.MEDIUM,
            type=rule.alarm_type if rule else "UNKNOWN",
            message=event.message or "",
            value=event.value_at_activation,
            setpoint=rule.setpoint if rule else 0.0,
            unit=None,  # Would come from sensor
            state=event.state,
            activated_at=event.activated_at,
            acknowledged_at=event.acknowledged_at,
            acknowledged_by=event.acknowledged_by,
            cleared_at=event.cleared_at,
        )
        result.append(alarm_schema.model_dump())

    meta = AlarmListMeta(
        total=total,
        active=active_count,
        unacknowledged=unack_count,
    )

    return {
        "data": result,
        "meta": meta.model_dump(),
    }


@router.get("/history")
async def alarm_history(
    start: Optional[datetime] = Query(None, description="Start time"),
    end: Optional[datetime] = Query(None, description="End time"),
    rtu: Optional[str] = Query(None, description="Filter by RTU"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    limit: int = Query(100, ge=1, le=1000, description="Max records"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get historical alarm log.
    """
    # Default to last 24 hours
    now = datetime.now(timezone.utc)
    if not end:
        end = now
    if not start:
        start = end - timedelta(hours=24)

    query = db.query(AlarmEvent).filter(
        AlarmEvent.activated_at >= start,
        AlarmEvent.activated_at <= end
    )

    if rtu:
        rtu_obj = db.query(RTU).filter(RTU.station_name == rtu).first()
        if rtu_obj:
            query = query.filter(AlarmEvent.rtu_id == rtu_obj.id)

    if priority:
        query = query.join(AlarmRule).filter(AlarmRule.priority == priority.upper())

    total = query.count()
    events = query.order_by(AlarmEvent.activated_at.desc()).limit(limit).all()

    result = []
    for event in events:
        rule = event.rule
        rtu_obj = event.rtu

        alarm_schema = AlarmEventSchema(
            id=event.id,
            rtu=rtu_obj.station_name if rtu_obj else "unknown",
            tag=rule.tag if rule else "unknown",
            priority=rule.priority if rule else AlarmPriority.MEDIUM,
            type=rule.alarm_type if rule else "UNKNOWN",
            message=event.message or "",
            value=event.value_at_activation,
            setpoint=rule.setpoint if rule else 0.0,
            unit=None,
            state=event.state,
            activated_at=event.activated_at,
            acknowledged_at=event.acknowledged_at,
            acknowledged_by=event.acknowledged_by,
            cleared_at=event.cleared_at,
        )
        result.append(alarm_schema.model_dump())

    return {
        "data": result,
        "meta": {
            "total": total,
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
    }


@router.post("/{alarm_id}/acknowledge")
async def acknowledge_alarm(
    alarm_id: int = Path(..., description="Alarm event ID"),
    request: Optional[AlarmAcknowledgeRequest] = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Acknowledge an alarm.
    """
    event = db.query(AlarmEvent).filter(AlarmEvent.id == alarm_id).first()
    if not event:
        raise AlarmNotFoundError(alarm_id)

    if event.state == AlarmState.CLEARED:
        # Already cleared - nothing to acknowledge
        return build_success_response({
            "id": alarm_id,
            "state": event.state,
            "message": "Alarm already cleared"
        })

    # Acknowledge
    event.acknowledge(
        user="system",  # Would come from auth context
        note=request.note if request else None
    )
    db.commit()

    return build_success_response({
        "id": alarm_id,
        "state": event.state,
        "acknowledged_at": event.acknowledged_at.isoformat() if event.acknowledged_at else None,
        "acknowledged_by": event.acknowledged_by,
    })


@router.post("/acknowledge-all")
async def acknowledge_all_alarms(
    rtu: Optional[str] = Query(None, description="Filter by RTU"),
    request: Optional[AlarmAcknowledgeRequest] = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Acknowledge all active alarms.
    """
    query = db.query(AlarmEvent).filter(AlarmEvent.state == AlarmState.ACTIVE)

    if rtu:
        rtu_obj = db.query(RTU).filter(RTU.station_name == rtu).first()
        if rtu_obj:
            query = query.filter(AlarmEvent.rtu_id == rtu_obj.id)

    events = query.all()
    count = 0

    for event in events:
        event.acknowledge(
            user="system",  # Would come from auth context
            note=request.note if request else None
        )
        count += 1

    db.commit()

    return build_success_response({
        "acknowledged_count": count,
        "rtu_filter": rtu,
    })
