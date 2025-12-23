"""
Water Treatment Controller - System Status Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import os

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from sqlalchemy import func

from ...core.errors import build_success_response
from ...models.base import get_db
from ...models.rtu import RTU, RtuState
from ...models.alarm import AlarmEvent, AlarmState
from ...models.historian import HistorianSample

router = APIRouter()

# Track server start time
SERVER_START_TIME = datetime.now(timezone.utc)


class RtuSummary(BaseModel):
    """Summary of RTU states."""

    total: int
    running: int
    offline: int
    error: int


class AlarmSummary(BaseModel):
    """Summary of alarm states."""

    active: int
    unacknowledged: int


class HistorianSummary(BaseModel):
    """Summary of historian data."""

    samples_today: int
    storage_used_mb: float
    storage_available_mb: float


class ResourceSummary(BaseModel):
    """System resource usage."""

    cpu_percent: float
    memory_percent: float
    disk_percent: float


class SystemStatus(BaseModel):
    """Overall system health status."""

    uptime_seconds: int
    rtus: RtuSummary
    alarms: AlarmSummary
    historian: HistorianSummary
    resources: ResourceSummary


@router.get("/status")
async def get_system_status(
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get overall system health.
    """
    now = datetime.now(timezone.utc)
    uptime = int((now - SERVER_START_TIME).total_seconds())

    # RTU summary - single query with GROUP BY instead of 4 separate queries
    state_counts = dict(
        db.query(RTU.state, func.count(RTU.id))
        .group_by(RTU.state)
        .all()
    )
    total_rtus = sum(state_counts.values())

    rtu_summary = RtuSummary(
        total=total_rtus,
        running=state_counts.get(RtuState.RUNNING, 0),
        offline=state_counts.get(RtuState.OFFLINE, 0),
        error=state_counts.get(RtuState.ERROR, 0),
    )

    # Alarm summary
    active_alarms = db.query(AlarmEvent).filter(
        AlarmEvent.state.in_([AlarmState.ACTIVE, AlarmState.ACKNOWLEDGED])
    ).count()
    unack_alarms = db.query(AlarmEvent).filter(
        AlarmEvent.state == AlarmState.ACTIVE
    ).count()

    alarm_summary = AlarmSummary(
        active=active_alarms,
        unacknowledged=unack_alarms,
    )

    # Historian summary
    from datetime import timedelta
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    samples_today = db.query(HistorianSample).filter(
        HistorianSample.timestamp >= today_start
    ).count()

    # Estimate storage (rough)
    total_samples = db.query(HistorianSample).count()
    storage_used = total_samples * 16 / (1024 * 1024)  # ~16 bytes per sample

    historian_summary = HistorianSummary(
        samples_today=samples_today,
        storage_used_mb=round(storage_used, 2),
        storage_available_mb=1024.0,  # Placeholder
    )

    # Resource usage
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        disk = psutil.disk_usage("/")
        disk_percent = disk.percent
    except ImportError:
        cpu_percent = 0.0
        memory_percent = 0.0
        disk_percent = 0.0

    resource_summary = ResourceSummary(
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        disk_percent=disk_percent,
    )

    status = SystemStatus(
        uptime_seconds=uptime,
        rtus=rtu_summary,
        alarms=alarm_summary,
        historian=historian_summary,
        resources=resource_summary,
    )

    return build_success_response(status.model_dump())


@router.get("/logs")
async def get_system_logs(
    level: Optional[str] = Query(None, description="Filter by level"),
    hours: int = Query(24, ge=1, le=168, description="Hours to retrieve"),
    limit: int = Query(100, ge=1, le=1000, description="Max records"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get application logs.
    """
    # In a real implementation, this would read from log files or a log database
    # For now, return empty list
    return build_success_response({
        "logs": [],
        "meta": {
            "level": level,
            "hours": hours,
            "count": 0,
        }
    })
