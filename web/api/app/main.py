"""
Water Treatment Controller - FastAPI Application
Copyright (C) 2024-2025
SPDX-License-Identifier: GPL-3.0-or-later

Main FastAPI application entry point with startup validation.

Key principle: The system must be actually usable before accepting traffic.
This means validating paths, UI assets, database, and IPC at startup.
"""

import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .api.v1 import api_router
from .api.websocket import router as websocket_router
from .core.errors import generic_exception_handler, scada_exception_handler
from .core.exceptions import ScadaException
from .core.logging import (
    get_logger,
    set_correlation_id,
    setup_logging,
)
from .core.rate_limit import RateLimitMiddleware
from .core.startup import (
    StartupMode,
    get_startup_result,
    set_startup_result,
    validate_startup,
)
from .models.base import engine, get_db
from .persistence.base import initialize as init_persistence
from .persistence.base import is_initialized
from .persistence.users import ensure_default_admin
from .services.profinet_client import get_profinet_client
from .services.websocket_publisher import (
    publisher_lifespan_startup,
    publisher_lifespan_shutdown,
)
from .services.controller_heartbeat import (
    heartbeat_lifespan_startup,
    heartbeat_lifespan_shutdown,
)
from .services.pn_controller import (
    init_controller as pn_controller_init,
    shutdown_controller as pn_controller_shutdown,
    get_controller as get_pn_controller,
)
from .core.ports import get_allowed_origins

# Setup logging
LOG_LEVEL = os.environ.get("WTC_LOG_LEVEL", "INFO")
LOG_STRUCTURED = os.environ.get("WTC_LOG_STRUCTURED", "false").lower() == "true"
setup_logging(level=LOG_LEVEL, structured=LOG_STRUCTURED)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    # Startup
    logger.info("Starting Water Treatment Controller API")

    # === STARTUP VALIDATION (Readiness Gate) ===
    # This ensures the system is actually usable before accepting traffic.
    # Anti-pattern addressed: "Process-alive ≠ System-ready"
    startup_result = validate_startup(
        skip_ui_check=os.environ.get("WTC_API_ONLY", "").lower() in ("true", "1"),
        skip_ipc_check=os.environ.get("WTC_SIMULATION_MODE", "").lower() in ("true", "1"),
    )
    set_startup_result(startup_result)
    startup_result.log_all()

    if not startup_result.can_serve_traffic:
        logger.error(
            "STARTUP ABORTED: Critical startup checks failed. "
            "The system cannot function correctly. "
            "Review the errors above and take corrective action."
        )
        # In production, we should exit. In development, we continue with warnings.
        if startup_result.mode == StartupMode.PRODUCTION:
            # Give operator time to see the error
            logger.error("Exiting in 5 seconds... Set WTC_STARTUP_MODE=development to continue anyway.")
            time.sleep(5)
            sys.exit(1)
        else:
            logger.warning("Continuing despite failures (development mode)")

    # Initialize database (unified SQLAlchemy for both SQLite and PostgreSQL)
    # This creates all tables and initializes singleton configs
    init_persistence()
    logger.info("Database initialized (SQLAlchemy)")

    # Ensure default admin user exists
    ensure_default_admin()
    logger.info("Default admin user verified")

    # Start WebSocket data publisher for real-time updates
    await publisher_lifespan_startup()

    # Start controller heartbeat for automatic reconnection
    await heartbeat_lifespan_startup()

    # Initialize Python PROFINET controller
    # This replaces the C controller + shared memory architecture
    pn_ctrl = pn_controller_init()
    logger.info("Python PROFINET controller initialized")

    # RTUs are added via DCP discovery or API - no hardcoded defaults
    # Use POST /api/v1/discover/rtu to find devices on network
    # Use POST /api/v1/rtus/add-by-ip to add discovered devices
    logger.info("RTU discovery available via /api/v1/discover/rtu")

    # Log final startup status
    if startup_result.is_fully_healthy:
        logger.info("STARTUP COMPLETE: All systems operational")
    else:
        degraded = [c.name for c in startup_result.degraded_checks]
        logger.warning(f"STARTUP COMPLETE: System operational but degraded: {degraded}")

    yield

    # Shutdown
    logger.info("Shutting down Water Treatment Controller API")

    # Stop Python PROFINET controller
    pn_controller_shutdown()
    logger.info("Python PROFINET controller stopped")

    # Stop controller heartbeat
    await heartbeat_lifespan_shutdown()

    # Stop WebSocket data publisher
    await publisher_lifespan_shutdown()


# OpenAPI tags for documentation organization
openapi_tags = [
    {
        "name": "RTUs",
        "description": "RTU (Remote Terminal Unit) configuration and connection management. "
                       "RTUs are PROFINET IO devices that provide analog/digital I/O."
    },
    {
        "name": "Sensors",
        "description": "Sensor configuration and real-time values. "
                       "Sensors are analog inputs from RTU modules (level, flow, pressure, temperature)."
    },
    {
        "name": "Controls",
        "description": "Control/actuator configuration and commands. "
                       "Controls are digital/analog outputs (pumps, valves, VFDs)."
    },
    {
        "name": "Alarms",
        "description": "Alarm configuration and event management following ISA-18.2 standards. "
                       "Includes alarm rules, shelving, and acknowledgment."
    },
    {
        "name": "PID",
        "description": "PID loop configuration and tuning. "
                       "Closed-loop process control for level, flow, and pressure regulation."
    },
    {
        "name": "PROFINET",
        "description": "PROFINET diagnostics and module discovery. "
                       "Low-level communication status with industrial Ethernet devices."
    },
    {
        "name": "System",
        "description": "System configuration, health monitoring, and administration. "
                       "Includes backup/restore, user management, and audit logs."
    },
    {
        "name": "Historian",
        "description": "Time-series data storage and trending. "
                       "Query historical process values for analysis and reporting."
    },
    {
        "name": "Authentication",
        "description": "User authentication and session management. "
                       "Supports local accounts and Active Directory integration."
    },
]

# Create FastAPI application
app = FastAPI(
    title="Water Treatment Controller API",
    description="""
## Water Treatment SCADA Backend

This API provides a RESTful interface for controlling and monitoring water treatment
facilities via PROFINET IO.

### Key Features
- **RTU Management**: Configure and connect to PROFINET IO devices
- **Real-time Monitoring**: WebSocket streaming of sensor values and alarms
- **Process Control**: PID loops, setpoint management, and control commands
- **Alarm Management**: ISA-18.2 compliant alarm handling
- **Data Historian**: Time-series data storage with configurable retention

### State Machine
RTUs follow a connection state machine:
`OFFLINE → CONNECTING → DISCOVERY → RUNNING`

### Authentication
All endpoints except /health require authentication via Bearer token.
Obtain tokens via POST /api/v1/auth/login.

### WebSocket
Real-time updates available at `/api/v1/ws/{rtu_name}`.
    """,
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    openapi_tags=openapi_tags,
    contact={
        "name": "Water Controller Support",
        "url": "https://github.com/mwilco03/Water-Controller",
    },
    license_info={
        "name": "GPL-3.0-or-later",
        "url": "https://www.gnu.org/licenses/gpl-3.0.html",
    },
)

# CORS configuration from centralized port config
# Production: Set WTC_CORS_ORIGINS to comma-separated list of allowed origins
# Example: WTC_CORS_ORIGINS=https://scada.example.com,https://backup.example.com
# Default: Uses UI port from WTC_UI_PORT (default 8080)
# See: app/core/ports.py for centralized port configuration
allowed_origins = get_allowed_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID", "X-Request-ID"],
)

# Rate limiting middleware
# Configurable via WTC_RATE_LIMIT_ENABLED, WTC_RATE_LIMIT_REQUESTS, WTC_RATE_LIMIT_WINDOW
app.add_middleware(RateLimitMiddleware)


# Correlation ID middleware
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    """Add correlation ID to each request for distributed tracing."""
    # Check for incoming correlation ID from client or upstream service
    # Support both X-Correlation-ID (preferred) and X-Request-ID (legacy)
    correlation_id = (
        request.headers.get("X-Correlation-ID") or
        request.headers.get("X-Request-ID") or
        str(uuid4())
    )

    # Store in request state for access in route handlers
    request.state.correlation_id = correlation_id
    request.state.request_id = correlation_id  # Legacy compatibility

    # Set correlation ID for logging context
    set_correlation_id(correlation_id)

    # Log request start
    logger.debug(
        f"Request started: {request.method} {request.url.path}",
        extra={"correlation_id": correlation_id}
    )

    try:
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Request-ID"] = correlation_id  # Legacy compatibility

        return response
    finally:
        # Clear correlation ID after request completes
        set_correlation_id(None)


# Exception handlers
app.add_exception_handler(ScadaException, scada_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


# Include routers
app.include_router(api_router, prefix="/api/v1")
app.include_router(websocket_router, prefix="/api/v1")


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Health check endpoint with subsystem status including startup validation.

    Returns overall system health and individual subsystem status for:
    - startup: Startup validation result
    - ui_assets: Whether UI build is available
    - database: SQLite/SQLAlchemy connection
    - profinet_controller: PROFINET IPC via shared memory
    - persistence: Authentication/session storage

    Useful for:
    - Load balancer health checks
    - Operator diagnostics
    - Monitoring systems

    Anti-pattern addressed: "Port open ≠ application usable"
    """
    from .core.paths import get_ui_asset_status

    subsystems = {}
    overall_healthy = True
    degraded_components = []

    # Check startup validation result
    startup_result = get_startup_result()
    if startup_result:
        if startup_result.is_fully_healthy:
            subsystems["startup"] = {"status": "ok", "mode": startup_result.mode.value}
        elif startup_result.can_serve_traffic:
            subsystems["startup"] = {
                "status": "degraded",
                "mode": startup_result.mode.value,
                "degraded": [c.name for c in startup_result.degraded_checks],
            }
            degraded_components.append("startup")
        else:
            subsystems["startup"] = {
                "status": "error",
                "failed": [c.name for c in startup_result.failed_checks],
            }
            overall_healthy = False
    else:
        subsystems["startup"] = {"status": "not_run"}

    # Check UI assets - critical for operator interface (unless API-only mode)
    api_only_mode = os.environ.get("WTC_API_ONLY", "").lower() in ("true", "1")
    ui_status = get_ui_asset_status()
    if ui_status["available"]:
        subsystems["ui_assets"] = {
            "status": "ok",
            "build_time": ui_status["build_time"],
        }
    elif api_only_mode:
        # In API-only mode, UI not available is expected, not an error
        subsystems["ui_assets"] = {
            "status": "skipped",
            "reason": "API-only mode enabled",
        }
    else:
        subsystems["ui_assets"] = {
            "status": "error",
            "message": ui_status["message"],
            "missing": ui_status["missing_assets"],
            "action": "Build UI: cd /opt/water-controller/web/ui && npm run build",
        }
        # UI missing is critical - operators can't see the system
        overall_healthy = False

    # Check database (SQLAlchemy ORM)
    try:
        start = time.perf_counter()
        db = next(get_db())
        db.execute(text("SELECT 1"))
        db.close()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        subsystems["database"] = {"status": "ok", "latency_ms": latency_ms}
    except Exception as e:
        subsystems["database"] = {"status": "error", "error": str(e)}
        overall_healthy = False

    # Check PROFINET controller (shared memory IPC)
    # Note: is_connected() performs lazy reconnect if disconnected
    try:
        profinet = get_profinet_client()
        was_connected = profinet._client is not None and profinet._client.is_connected() if hasattr(profinet, '_client') else False

        # is_connected() attempts lazy reconnect
        now_connected = profinet.is_connected()

        if now_connected:
            controller_status = profinet.get_status()
            if controller_status.get("simulation_mode") or controller_status.get("demo_mode"):
                subsystems["profinet_controller"] = {
                    "status": "simulation",
                    "note": "Running without hardware controller"
                }
                degraded_components.append("profinet_controller")
            else:
                subsystems["profinet_controller"] = {
                    "status": "ok",
                    "controller_running": profinet.is_controller_running(),
                    "reconnected": not was_connected and now_connected,
                }
        else:
            # Explicitly attempt reconnect on health check
            reconnect_success = profinet.reconnect(force=False)
            subsystems["profinet_controller"] = {
                "status": "disconnected",
                "reconnect_attempted": True,
                "reconnect_success": reconnect_success,
            }
            degraded_components.append("profinet_controller")
    except Exception as e:
        subsystems["profinet_controller"] = {"status": "error", "error": str(e)}
        degraded_components.append("profinet_controller")
        # Don't mark as unhealthy - can operate in simulation mode

    # Check persistence layer (SQLite direct for auth)
    if is_initialized():
        subsystems["persistence"] = {"status": "ok"}
    else:
        subsystems["persistence"] = {"status": "uninitialized"}
        overall_healthy = False

    # Determine overall status
    if not overall_healthy:
        status = "unhealthy"
    elif degraded_components:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "timestamp": datetime.now(UTC).isoformat(),
        "subsystems": subsystems,
        "degraded_components": degraded_components if degraded_components else None,
    }


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Water Treatment Controller API",
        "version": "2.0.0",
        "docs": "/api/docs",
        "health": "/health",
    }
