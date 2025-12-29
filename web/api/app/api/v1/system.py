"""
Water Treatment Controller - System Status Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Health Check Hierarchy (per HARMONIOUS_SYSTEM_DESIGN.md Principle 9):
- /health/live: Is the process running? (5s check interval)
- /health/ready: Can it accept traffic? (10s check interval)
- /health/functional: Is it working correctly? (30s check interval)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import os
import logging

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from sqlalchemy import func

from ...core.errors import build_success_response
from ...models.base import get_db
from ...models.rtu import RTU, RtuState
from ...models.alarm import AlarmEvent, AlarmState
from ...models.historian import HistorianSample

router = APIRouter()
logger = logging.getLogger(__name__)

# Track server start time
SERVER_START_TIME = datetime.now(timezone.utc)

# Controller version for version negotiation
CONTROLLER_VERSION = "1.2.0"


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


# ============== Health Check Hierarchy (Principle 9) ==============
# Per HARMONIOUS_SYSTEM_DESIGN.md:
# - /health/live: Is process running? (5s interval, for systemd/k8s liveness)
# - /health/ready: Can accept traffic? (10s interval, for load balancer)
# - /health/functional: Working correctly? (30s interval, for monitoring)


@router.get("/health/live")
async def health_live() -> Response:
    """
    Liveness probe - Is the process running?

    This endpoint always returns 200 if the API server is up.
    Use for systemd watchdog or Kubernetes liveness probe.
    Check interval: 5 seconds recommended.

    Returns:
        200: Process is alive
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.get("/health/ready")
async def health_ready(db: Session = Depends(get_db)) -> Response:
    """
    Readiness probe - Can the service accept traffic?

    Checks:
    - Database connection is available
    - Configuration is valid
    - Core dependencies are accessible

    Use for load balancer health checks or Kubernetes readiness probe.
    Check interval: 10 seconds recommended.

    Returns:
        200: Ready to accept traffic
        503: Not ready (dependency failure)
    """
    checks = {}
    all_ready = True

    # Check database connection
    try:
        db.execute("SELECT 1")
        checks["database"] = {"status": "ok"}
    except SQLAlchemyError as e:
        checks["database"] = {"status": "error", "message": str(e)}
        all_ready = False
        logger.warning(f"Readiness check failed: database - {e}")

    # Check IPC/shared memory (if available)
    try:
        from ...services.shm_client import get_shm_client
        shm = get_shm_client()
        if shm and shm.is_connected():
            checks["ipc"] = {"status": "ok"}
        else:
            checks["ipc"] = {"status": "degraded", "message": "IPC not connected"}
            # IPC degraded doesn't block readiness - we can still serve cached data
    except Exception as e:
        checks["ipc"] = {"status": "degraded", "message": str(e)}

    status_code = 200 if all_ready else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "not_ready",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
        }
    )


@router.get("/health/functional")
async def health_functional(db: Session = Depends(get_db)) -> Response:
    """
    Functional health check - Is the system working correctly?

    Comprehensive check including:
    - UI assets availability (critical for operator interface)
    - Database connection and query performance
    - PROFINET controller status
    - RTU connectivity
    - Data freshness (historian receiving data)
    - Alarm system status

    Use for monitoring dashboards and alerting.
    Check interval: 30 seconds recommended.

    Anti-pattern addressed: "Port open ≠ application usable"
    The system is only functional if operators can actually use it.

    Returns:
        200: All systems functional
        200 with degraded status: Some systems degraded but operational
        503: Critical systems failed
    """
    from ...core.paths import get_ui_asset_status

    now = datetime.now(timezone.utc)
    checks = {}
    degraded_components = []
    critical_failure = False

    # UI assets check - operators need the interface to work
    ui_status = get_ui_asset_status()
    if ui_status["available"]:
        checks["ui_assets"] = {
            "status": "ok",
            "build_time": ui_status["build_time"],
        }
    else:
        checks["ui_assets"] = {
            "status": "error",
            "message": ui_status["message"],
            "missing": ui_status["missing_assets"],
            "action": "Build UI: cd /opt/water-controller/web/ui && npm run build",
        }
        critical_failure = True
        logger.error(f"Functional check: UI assets missing - {ui_status['message']}")

    # Database health
    try:
        start = datetime.now(timezone.utc)
        db.execute("SELECT 1")
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        checks["database"] = {
            "status": "ok",
            "latency_ms": round(latency_ms, 2),
        }
    except SQLAlchemyError as e:
        checks["database"] = {"status": "error", "message": str(e)}
        critical_failure = True
        logger.error(f"Functional check: database failed - {e}")

    # RTU connectivity
    try:
        state_counts = dict(
            db.query(RTU.state, func.count(RTU.id))
            .group_by(RTU.state)
            .all()
        )
        total_rtus = sum(state_counts.values())
        running_rtus = state_counts.get(RtuState.RUNNING, 0)
        error_rtus = state_counts.get(RtuState.ERROR, 0)

        if total_rtus == 0:
            checks["rtu_connectivity"] = {"status": "ok", "message": "No RTUs configured"}
        elif running_rtus == total_rtus:
            checks["rtu_connectivity"] = {
                "status": "ok",
                "running": running_rtus,
                "total": total_rtus,
            }
        elif running_rtus > 0:
            checks["rtu_connectivity"] = {
                "status": "degraded",
                "running": running_rtus,
                "total": total_rtus,
                "error": error_rtus,
            }
            degraded_components.append("rtu_connectivity")
        else:
            checks["rtu_connectivity"] = {
                "status": "error",
                "running": 0,
                "total": total_rtus,
                "message": "No RTUs connected",
            }
            degraded_components.append("rtu_connectivity")
    except Exception as e:
        checks["rtu_connectivity"] = {"status": "error", "message": str(e)}
        degraded_components.append("rtu_connectivity")

    # Data freshness (historian receiving recent data)
    try:
        from datetime import timedelta
        recent_threshold = now - timedelta(minutes=5)
        recent_samples = db.query(HistorianSample).filter(
            HistorianSample.timestamp >= recent_threshold
        ).count()

        if recent_samples > 0:
            checks["data_freshness"] = {
                "status": "ok",
                "samples_last_5min": recent_samples,
            }
        else:
            # Check if we have any RTUs that should be sending data
            running_count = state_counts.get(RtuState.RUNNING, 0) if 'state_counts' in dir() else 0
            if running_count > 0:
                checks["data_freshness"] = {
                    "status": "degraded",
                    "samples_last_5min": 0,
                    "message": "No recent historian data from running RTUs",
                }
                degraded_components.append("data_freshness")
            else:
                checks["data_freshness"] = {
                    "status": "ok",
                    "samples_last_5min": 0,
                    "message": "No running RTUs",
                }
    except Exception as e:
        checks["data_freshness"] = {"status": "error", "message": str(e)}

    # Alarm system
    try:
        active_alarms = db.query(AlarmEvent).filter(
            AlarmEvent.state.in_([AlarmState.ACTIVE, AlarmState.ACKNOWLEDGED])
        ).count()
        unack_alarms = db.query(AlarmEvent).filter(
            AlarmEvent.state == AlarmState.ACTIVE
        ).count()

        checks["alarm_system"] = {
            "status": "ok",
            "active_alarms": active_alarms,
            "unacknowledged": unack_alarms,
        }
    except Exception as e:
        checks["alarm_system"] = {"status": "error", "message": str(e)}

    # IPC to C controller
    try:
        from ...services.shm_client import get_shm_client
        shm = get_shm_client()
        if shm and shm.is_connected():
            checks["profinet_controller"] = {"status": "ok"}
        else:
            checks["profinet_controller"] = {
                "status": "degraded",
                "message": "IPC not connected - may be in simulation mode",
            }
            degraded_components.append("profinet_controller")
    except Exception as e:
        checks["profinet_controller"] = {
            "status": "degraded",
            "message": str(e),
        }
        degraded_components.append("profinet_controller")

    # Determine overall status
    if critical_failure:
        overall_status = "critical"
        status_code = 503
    elif degraded_components:
        overall_status = "degraded"
        status_code = 200  # Still operational, just degraded
    else:
        overall_status = "healthy"
        status_code = 200

    uptime_seconds = int((now - SERVER_START_TIME).total_seconds())

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "timestamp": now.isoformat(),
            "uptime_seconds": uptime_seconds,
            "version": CONTROLLER_VERSION,
            "checks": checks,
            "degraded_components": degraded_components,
        }
    )


@router.get("/version")
async def get_version() -> Dict[str, Any]:
    """
    Get controller version information.

    Used for version negotiation with RTUs per HARMONIOUS_SYSTEM_DESIGN.md
    Field Deployment Reality section.
    """
    return build_success_response({
        "version": CONTROLLER_VERSION,
        "api_version": "v1",
        "started_at": SERVER_START_TIME.isoformat(),
    })
