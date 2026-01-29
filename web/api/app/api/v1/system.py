"""
Water Treatment Controller - System Status Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Health Check Hierarchy (per HARMONIOUS_SYSTEM_DESIGN.md Principle 9):
- /health/live: Is the process running? (5s check interval)
- /health/ready: Can it accept traffic? (10s check interval)
- /health/functional: Is it working correctly? (30s check interval)
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...models.alarm import AlarmEvent, AlarmState
from ...models.base import get_db
from ...models.historian import HistorianSample
from ...models.audit import CommandAudit
from ...models.rtu import RTU, RtuState

router = APIRouter()
logger = logging.getLogger(__name__)

# Track server start time
SERVER_START_TIME = datetime.now(UTC)

# Controller version for version negotiation
CONTROLLER_VERSION = "1.2.1"

# Path to version file written by bootstrap.sh
VERSION_FILE_PATH = "/opt/water-controller/.version"


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
) -> dict[str, Any]:
    """
    Get overall system health.
    """
    now = datetime.now(UTC)
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
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    samples_today = db.query(HistorianSample).filter(
        HistorianSample.timestamp >= today_start
    ).count()

    # Estimate storage (rough)
    total_samples = db.query(HistorianSample).count()
    storage_used = total_samples * 16 / (1024 * 1024)  # ~16 bytes per sample

    # Get actual available disk space
    try:
        import psutil
        disk = psutil.disk_usage("/")
        storage_available = disk.free / (1024 * 1024)  # Convert to MB
    except ImportError:
        storage_available = 0.0

    historian_summary = HistorianSummary(
        samples_today=samples_today,
        storage_used_mb=round(storage_used, 2),
        storage_available_mb=round(storage_available, 2),
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
    level: str | None = Query(None, description="Filter by level"),
    hours: int = Query(24, ge=1, le=168, description="Hours to retrieve"),
    limit: int = Query(100, ge=1, le=1000, description="Max records"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get application logs.

    Log storage is handled via Python's logging framework. For centralized
    logging in production, configure Loki/Promtail or Elasticsearch.
    """
    # Logs are handled by Python logging framework
    # For centralized logging, configure external log aggregation
    return build_success_response({
        "logs": [],
        "meta": {
            "level": level,
            "hours": hours,
            "count": 0,
            "note": "Use external log aggregation (Loki/Promtail or Elasticsearch) for production",
        }
    })


class ClientLogEntry(BaseModel):
    """Log entry from frontend client."""
    level: str
    message: str
    timestamp: str | None = None
    source: str | None = None
    data: dict | list | str | None = None


# Logger for client-side logs
client_logger = logging.getLogger("wtc.client")


@router.post("/logs")
async def post_client_log(entry: ClientLogEntry) -> dict[str, Any]:
    """
    Receive log entries from frontend clients.

    Logs are forwarded to Python logging framework for centralized handling.
    """
    level = entry.level.upper()
    source = entry.source or "frontend"
    msg = f"[{source}] {entry.message}"

    if level == "ERROR":
        client_logger.error(msg, extra={"client_data": entry.data})
    elif level == "WARN" or level == "WARNING":
        client_logger.warning(msg, extra={"client_data": entry.data})
    elif level == "INFO":
        client_logger.info(msg, extra={"client_data": entry.data})
    else:
        client_logger.debug(msg, extra={"client_data": entry.data})

    return build_success_response({"received": True})


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
            "timestamp": datetime.now(UTC).isoformat(),
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
        db.execute(text("SELECT 1"))
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
            "timestamp": datetime.now(UTC).isoformat(),
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

    now = datetime.now(UTC)
    checks = {}
    degraded_components = []
    critical_failure = False

    # UI assets check - operators need the interface to work (unless API-only mode)
    api_only_mode = os.environ.get("WTC_API_ONLY", "").lower() in ("true", "1")
    ui_status = get_ui_asset_status()
    if ui_status["available"]:
        checks["ui_assets"] = {
            "status": "ok",
            "build_time": ui_status["build_time"],
        }
    elif api_only_mode:
        checks["ui_assets"] = {
            "status": "skipped",
            "reason": "API-only mode enabled",
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
        start = datetime.now(UTC)
        db.execute(text("SELECT 1"))
        latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
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
async def get_version() -> dict[str, Any]:
    """
    Get controller version information including build details.

    Used for version negotiation with RTUs per HARMONIOUS_SYSTEM_DESIGN.md
    Field Deployment Reality section.

    Returns:
        version: Software version (e.g., "1.2.1")
        api_version: API version (e.g., "v1")
        started_at: Server start timestamp
        build: Build info from installation (commit, date, etc.) if available
    """
    import json
    import os

    build_info = None
    if os.path.exists(VERSION_FILE_PATH):
        try:
            with open(VERSION_FILE_PATH, "r") as f:
                version_data = json.load(f)
                build_info = {
                    "commit": version_data.get("commit_short", ""),
                    "commit_full": version_data.get("commit_sha", ""),
                    "commit_date": version_data.get("commit_date", ""),
                    "commit_message": version_data.get("commit_subject", ""),
                    "branch": version_data.get("branch", ""),
                    "installed_at": version_data.get("installed_at_local", ""),
                }
        except Exception as e:
            logger.warning(f"Failed to read version file: {e}")

    return build_success_response({
        "version": CONTROLLER_VERSION,
        "api_version": "v1",
        "started_at": SERVER_START_TIME.isoformat(),
        "build": build_info,
    })


# ============== System Configuration ==============


@router.get("/config")
async def get_system_config(
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Export system configuration.

    Returns current system configuration including:
    - RTU configurations
    - Alarm settings
    - System parameters

    Used for backup and configuration transfer between systems.
    """
    from ...models.alarm import AlarmConfig

    # Gather RTU configurations
    rtus = db.query(RTU).all()
    rtu_configs = []
    for rtu in rtus:
        rtu_configs.append({
            "station_name": rtu.station_name,
            "ip_address": rtu.ip_address,
            "description": rtu.description,
            "slot_count": rtu.slot_count,
            "enabled": rtu.enabled,
        })

    # Gather alarm configurations
    alarm_configs = db.query(AlarmConfig).all()
    alarm_settings = []
    for alarm in alarm_configs:
        alarm_settings.append({
            "tag": alarm.tag,
            "description": alarm.description,
            "priority": alarm.priority,
            "setpoint": alarm.setpoint,
            "deadband": alarm.deadband,
            "delay_seconds": alarm.delay_seconds,
            "enabled": alarm.enabled,
        })

    config = {
        "version": CONTROLLER_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "rtus": rtu_configs,
        "alarms": alarm_settings,
        "system": {
            "historian_retention_days": 90,
            "alarm_retention_days": 365,
            "audit_retention_days": 730,
        },
    }

    return build_success_response(config)


class ConfigImport(BaseModel):
    """Configuration import request."""
    rtus: list[dict] | None = None
    alarms: list[dict] | None = None
    system: dict | None = None


@router.post("/config")
async def import_system_config(
    config: ConfigImport,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Import system configuration.

    Merges or replaces configuration based on provided data.
    RTUs and alarms are matched by their unique identifiers.

    Note: This is a partial import - only specified sections are updated.
    """
    imported = {"rtus": 0, "alarms": 0}

    # Import RTU configurations
    if config.rtus:
        for rtu_data in config.rtus:
            station_name = rtu_data.get("station_name")
            if not station_name:
                continue

            existing = db.query(RTU).filter(RTU.station_name == station_name).first()
            if existing:
                # Update existing
                for key, value in rtu_data.items():
                    if hasattr(existing, key) and key != "station_name":
                        setattr(existing, key, value)
            else:
                # Create new
                new_rtu = RTU(**rtu_data)
                db.add(new_rtu)

            imported["rtus"] += 1

    # Import alarm configurations
    if config.alarms:
        from ...models.alarm import AlarmConfig

        for alarm_data in config.alarms:
            tag = alarm_data.get("tag")
            if not tag:
                continue

            existing = db.query(AlarmConfig).filter(AlarmConfig.tag == tag).first()
            if existing:
                for key, value in alarm_data.items():
                    if hasattr(existing, key) and key != "tag":
                        setattr(existing, key, value)
            else:
                new_alarm = AlarmConfig(**alarm_data)
                db.add(new_alarm)

            imported["alarms"] += 1

    db.commit()
    logger.info(f"Configuration imported: {imported}")

    return build_success_response({
        "success": True,
        "imported": imported,
    })


# ============== Audit Trail ==============


@router.get("/audit")
async def get_audit_trail(
    limit: int = Query(50, ge=1, le=500, description="Max records to return"),
    rtu_name: str | None = Query(None, description="Filter by RTU name"),
    user: str | None = Query(None, description="Filter by username"),
    hours: int = Query(24, ge=1, le=720, description="Hours of history"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get command audit trail.

    Returns history of operator control commands with results.
    Required for ISA-62443 compliance (audit trail for control actions).
    """
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    query = db.query(CommandAudit).filter(CommandAudit.timestamp >= cutoff)

    if rtu_name:
        query = query.filter(CommandAudit.rtu_name == rtu_name)
    if user:
        query = query.filter(CommandAudit.user == user)

    query = query.order_by(CommandAudit.timestamp.desc()).limit(limit)
    records = query.all()

    audit_entries = []
    for record in records:
        audit_entries.append({
            "id": record.id,
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
            "rtu_name": record.rtu_name,
            "control_tag": record.control_tag,
            "command": record.command,
            "value": record.value,
            "result": record.result,
            "rejection_reason": record.rejection_reason,
            "user": record.user,
            "source_ip": record.source_ip,
        })

    return build_success_response({
        "entries": audit_entries,
        "count": len(audit_entries),
        "hours": hours,
    })


# ============== Network Configuration ==============


# In-memory storage (in production, persist to config file)
_network_config: dict[str, Any] = {
    "mode": "dhcp",
    "ip_address": "",
    "netmask": "255.255.255.0",
    "gateway": "",
    "dns_primary": "",
    "dns_secondary": "",
    "hostname": "water-controller",
}

_web_config: dict[str, Any] = {
    "port": 3000,
    "bind_address": "0.0.0.0",
    "https_enabled": False,
    "https_port": 3443,
}


class NetworkConfig(BaseModel):
    """Network configuration."""
    mode: str = "dhcp"
    ip_address: str = ""
    netmask: str = "255.255.255.0"
    gateway: str = ""
    dns_primary: str = ""
    dns_secondary: str = ""
    hostname: str = "water-controller"


class WebServerConfig(BaseModel):
    """Web server configuration."""
    port: int = 3000
    bind_address: str = "0.0.0.0"
    https_enabled: bool = False
    https_port: int = 3443


@router.get("/network")
async def get_network_config() -> dict[str, Any]:
    """
    Get network configuration.

    Returns current IP, DHCP, gateway, DNS settings.
    """
    import socket
    import subprocess

    config = {**_network_config}

    # Try to detect current network state
    try:
        hostname = socket.gethostname()
        config["hostname"] = hostname

        # Get current IP from socket (best effort - may fail if no network route)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        try:
            s.connect(("8.8.8.8", 80))
            config["ip_address"] = s.getsockname()[0]
        except OSError as e:
            # Network unreachable, no route, etc - leave IP blank
            logger.debug(f"Could not detect IP address via socket: {e}")
        finally:
            s.close()

    except Exception as e:
        logger.debug(f"Could not detect network config: {e}")

    return build_success_response(config)


@router.put("/network")
async def update_network_config(
    config: NetworkConfig
) -> dict[str, Any]:
    """
    Update network configuration.

    Note: Changing IP address may disconnect your current session.
    In Docker deployments, network changes affect the container only.
    """
    global _network_config

    # Validate IP format
    import re
    ip_pattern = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")

    if config.mode == "static":
        if not ip_pattern.match(config.ip_address):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid IP address format")
        if not ip_pattern.match(config.netmask):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid netmask format")

    _network_config = config.model_dump()
    logger.info(f"Network config updated: mode={config.mode}")

    # Note: Actually applying network changes would require system-level commands
    # and is deployment-specific (Docker vs bare metal)

    return build_success_response(_network_config)


@router.get("/web")
async def get_web_config() -> dict[str, Any]:
    """
    Get web server configuration.

    Returns current port, bind address, and HTTPS settings.
    """
    return build_success_response(_web_config)


@router.put("/web")
async def update_web_config(
    config: WebServerConfig
) -> dict[str, Any]:
    """
    Update web server configuration.

    Note: Port changes require a server restart to take effect.
    """
    global _web_config

    if config.port < 1 or config.port > 65535:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Port must be between 1 and 65535")

    _web_config = config.model_dump()
    logger.info(f"Web config updated: port={config.port}")

    return build_success_response(_web_config)


# ============== Controller Diagnostics ==============


@router.get("/diagnostics/controller")
async def get_controller_diagnostics(
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get detailed PROFINET controller diagnostics.

    Shows:
    - Shared memory connection status
    - Controller state (running/stopped)
    - RTUs registered in controller vs database
    - Command queue status
    - IPC health

    Use this to debug why PROFINET communications aren't working.
    """
    from ...services.profinet_client import get_profinet_client, SHM_AVAILABLE
    from ...services.shm_client import get_shm_client

    diag = {
        "timestamp": datetime.now(UTC).isoformat(),
        "shm_module_available": SHM_AVAILABLE,
        "shm_connected": False,
        "controller_running": False,
        "demo_mode": False,
        "rtus_in_controller": [],
        "rtus_in_database": [],
        "mismatches": [],
        "last_update_ms": None,
        "command_sequence": None,
        "command_ack": None,
        "ipc_health": "unknown",
    }

    # Check profinet client status
    try:
        profinet = get_profinet_client()
        diag["demo_mode"] = profinet.is_demo_mode()
        diag["shm_connected"] = profinet.is_connected()
        diag["controller_running"] = profinet.is_controller_running()

        # Get status from profinet client
        status = profinet.get_status()
        diag["profinet_status"] = status
    except Exception as e:
        diag["profinet_client_error"] = str(e)

    # Get detailed shared memory info
    try:
        shm = get_shm_client()
        if shm and shm.is_connected():
            diag["shm_connected"] = True

            # Get full status
            shm_status = shm.get_status()
            diag["last_update_ms"] = shm_status.get("last_update_ms")
            diag["controller_running"] = shm_status.get("controller_running", False)
            diag["total_rtus_in_shm"] = shm_status.get("total_rtus", 0)
            diag["connected_rtus_in_shm"] = shm_status.get("connected_rtus", 0)

            # Get RTUs from controller's shared memory
            shm_rtus = shm.get_rtus()
            for rtu in shm_rtus:
                state_code = rtu.get("connection_state", 5)
                from ...services.profinet_client import CONNECTION_STATE_NAMES
                state_name = CONNECTION_STATE_NAMES.get(state_code, f"UNKNOWN({state_code})")
                diag["rtus_in_controller"].append({
                    "station_name": rtu.get("station_name"),
                    "ip_address": rtu.get("ip_address"),
                    "connection_state": state_name,
                    "connection_state_code": state_code,
                    "vendor_id": rtu.get("vendor_id"),
                    "device_id": rtu.get("device_id"),
                    "sensor_count": len(rtu.get("sensors", [])),
                    "actuator_count": len(rtu.get("actuators", [])),
                })

            # Check command queue state
            # Read raw command sequence and ack values
            import struct
            import ctypes
            try:
                from shm_client import WtcSharedMemory

                # Calculate offsets for command_sequence and command_ack
                # They are at the end of the struct after the command
                cmd_seq_offset = ctypes.sizeof(WtcSharedMemory) - 8
                shm.mm.seek(cmd_seq_offset)
                seq_data = shm.mm.read(8)
                if len(seq_data) >= 8:
                    cmd_seq, cmd_ack = struct.unpack('II', seq_data)
                    diag["command_sequence"] = cmd_seq
                    diag["command_ack"] = cmd_ack
                    diag["commands_pending"] = cmd_seq - cmd_ack if cmd_seq >= cmd_ack else 0
            except ImportError as ie:
                diag["command_queue_error"] = f"Could not import shm structures: {ie}"

            diag["ipc_health"] = "healthy" if diag["controller_running"] else "controller_stopped"
        else:
            diag["ipc_health"] = "disconnected"
            diag["shm_error"] = "Shared memory not connected - C controller may not be running"
    except Exception as e:
        diag["shm_error"] = str(e)
        diag["ipc_health"] = "error"

    # Get RTUs from database
    try:
        db_rtus = db.query(RTU).all()
        for rtu in db_rtus:
            diag["rtus_in_database"].append({
                "station_name": rtu.station_name,
                "ip_address": rtu.ip_address,
                "state": rtu.state,
                "vendor_id": rtu.vendor_id,
                "device_id": rtu.device_id,
            })
    except Exception as e:
        diag["database_error"] = str(e)

    # Find mismatches between controller and database
    controller_names = {r["station_name"] for r in diag["rtus_in_controller"]}
    database_names = {r["station_name"] for r in diag["rtus_in_database"]}

    in_db_not_controller = database_names - controller_names
    in_controller_not_db = controller_names - database_names

    if in_db_not_controller:
        diag["mismatches"].append({
            "issue": "RTUs in database but NOT in controller",
            "rtus": list(in_db_not_controller),
            "action": "These RTUs need to be registered with the controller via add_rtu command",
        })

    if in_controller_not_db:
        diag["mismatches"].append({
            "issue": "RTUs in controller but NOT in database",
            "rtus": list(in_controller_not_db),
            "action": "These RTUs exist in controller memory but not in database",
        })

    # Check for state mismatches
    for db_rtu in diag["rtus_in_database"]:
        for ctrl_rtu in diag["rtus_in_controller"]:
            if db_rtu["station_name"] == ctrl_rtu["station_name"]:
                db_state = db_rtu["state"]
                ctrl_state = ctrl_rtu["connection_state"]
                if db_state != ctrl_state:
                    diag["mismatches"].append({
                        "issue": "State mismatch",
                        "rtu": db_rtu["station_name"],
                        "database_state": db_state,
                        "controller_state": ctrl_state,
                    })

    return build_success_response(diag)


@router.post("/diagnostics/reconnect")
async def trigger_controller_reconnect(
    force: bool = Query(True, description="Force reconnect, ignoring cooldown")
) -> dict[str, Any]:
    """
    Manually trigger a reconnection to the PROFINET controller.

    Use this when:
    - The C controller was started after the API
    - Connection was lost and you want to reconnect immediately
    - Debugging connection issues

    Args:
        force: If True (default), ignore reconnect cooldown and try immediately.

    Returns:
        Connection status before and after the reconnect attempt.
    """
    from ...services.controller_heartbeat import get_heartbeat
    from ...services.profinet_client import get_profinet_client

    # Get current state before reconnect
    profinet = get_profinet_client()
    was_connected = profinet.is_connected()
    was_controller_running = profinet.is_controller_running()

    # Trigger reconnect via heartbeat service (logs and tracks attempts)
    heartbeat = get_heartbeat()
    result = await heartbeat.trigger_reconnect(force=force)

    # Get state after reconnect
    now_connected = profinet.is_connected()
    now_controller_running = profinet.is_controller_running()

    response = {
        "before": {
            "connected": was_connected,
            "controller_running": was_controller_running,
        },
        "after": {
            "connected": now_connected,
            "controller_running": now_controller_running,
        },
        "reconnect_attempted": True,
        "success": now_connected and not was_connected,
        "heartbeat_stats": heartbeat.get_status(),
    }

    if now_connected and not was_connected:
        logger.info("Manual reconnect successful - controller now connected")
    elif now_connected:
        logger.info("Manual reconnect: already connected")
    else:
        logger.warning("Manual reconnect failed - controller still not available")

    return build_success_response(response)


@router.get("/diagnostics/heartbeat")
async def get_heartbeat_status() -> dict[str, Any]:
    """
    Get the controller heartbeat service status.

    Shows:
    - Whether heartbeat is running
    - Current backoff interval
    - Reconnect attempt statistics
    - Last known controller state
    """
    from ...services.controller_heartbeat import get_heartbeat

    heartbeat = get_heartbeat()
    return build_success_response(heartbeat.get_status())


@router.get("/interfaces")
async def get_network_interfaces() -> dict[str, Any]:
    """
    Get available network interfaces.

    Returns list of interfaces with IP, MAC, and state.
    """
    interfaces = []

    try:
        import socket
        import subprocess

        # Use ip command to get interface info
        result = subprocess.run(
            ["ip", "-j", "addr"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)

            for iface in data:
                name = iface.get("ifname", "")
                if name == "lo":  # Skip loopback
                    continue

                ip_addr = ""
                netmask = ""
                for addr_info in iface.get("addr_info", []):
                    if addr_info.get("family") == "inet":
                        ip_addr = addr_info.get("local", "")
                        prefix = addr_info.get("prefixlen", 24)
                        # Convert prefix to netmask
                        netmask = ".".join([
                            str((0xffffffff << (32 - prefix) >> i) & 0xff)
                            for i in [24, 16, 8, 0]
                        ])
                        break

                interfaces.append({
                    "name": name,
                    "ip_address": ip_addr,
                    "netmask": netmask,
                    "mac_address": iface.get("address", ""),
                    "state": iface.get("operstate", "UNKNOWN").upper(),
                    "speed": "",  # Would need ethtool for this
                })

    except FileNotFoundError:
        # ip command not available, try psutil
        try:
            import psutil
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

            for name, addr_list in addrs.items():
                if name == "lo":
                    continue

                ip_addr = ""
                netmask = ""
                mac_addr = ""

                for addr in addr_list:
                    if addr.family == socket.AF_INET:
                        ip_addr = addr.address
                        netmask = addr.netmask or ""
                    elif addr.family == psutil.AF_LINK:
                        mac_addr = addr.address

                stat = stats.get(name)
                state = "UP" if stat and stat.isup else "DOWN"
                speed = f"{stat.speed}Mbps" if stat and stat.speed else ""

                interfaces.append({
                    "name": name,
                    "ip_address": ip_addr,
                    "netmask": netmask,
                    "mac_address": mac_addr,
                    "state": state,
                    "speed": speed,
                })

        except ImportError:
            logger.warning("Neither ip command nor psutil available for interface detection")

    except Exception as e:
        logger.warning(f"Failed to get network interfaces: {e}")

    return build_success_response(interfaces)
