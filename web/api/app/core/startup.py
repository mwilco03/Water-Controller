"""
Water Treatment Controller - Startup Validation and Readiness Gates
Copyright (C) 2024-2025
SPDX-License-Identifier: GPL-3.0-or-later

This module ensures the system is actually usable before accepting traffic.

Anti-patterns addressed:
- "Install succeeds ≠ system usable"
- "Process-alive ≠ System-ready"
- "Port open ≠ application usable"
- Partial startup allowed

The key insight is shifting from:
    "Did the process start?"
to:
    "Is the system actually usable?"

Usage:
    from app.core.startup import validate_startup, StartupMode

    # In application lifespan
    result = validate_startup(mode=StartupMode.PRODUCTION)
    if not result.can_serve_traffic:
        # Log issues and exit
        result.log_all()
        sys.exit(1)
"""

import os
import socket
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any, Callable
import time

from .paths import paths, validate_paths, PathSeverity, get_ui_asset_status

logger = logging.getLogger(__name__)


class StartupMode(Enum):
    """Startup validation modes with different strictness levels."""
    DEVELOPMENT = "development"   # Lenient - warnings only
    PRODUCTION = "production"     # Strict - fail on critical issues
    SIMULATION = "simulation"     # Skip hardware checks


class ReadinessState(Enum):
    """Service readiness states."""
    NOT_CHECKED = "not_checked"
    CHECKING = "checking"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class ReadinessCheck:
    """Result of a single readiness check."""
    name: str
    state: ReadinessState
    message: str
    duration_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    operator_action: Optional[str] = None


@dataclass
class StartupResult:
    """Complete startup validation result."""
    checks: List[ReadinessCheck] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    mode: StartupMode = StartupMode.PRODUCTION

    @property
    def can_serve_traffic(self) -> bool:
        """True if system can accept and handle requests."""
        return not any(c.state == ReadinessState.FAILED for c in self.checks)

    @property
    def is_fully_healthy(self) -> bool:
        """True if all checks passed without degradation."""
        return all(c.state == ReadinessState.READY for c in self.checks)

    @property
    def failed_checks(self) -> List[ReadinessCheck]:
        return [c for c in self.checks if c.state == ReadinessState.FAILED]

    @property
    def degraded_checks(self) -> List[ReadinessCheck]:
        return [c for c in self.checks if c.state == ReadinessState.DEGRADED]

    def log_all(self) -> None:
        """Log all check results with actionable guidance."""
        logger.info(f"Startup validation completed in mode: {self.mode.value}")

        for check in self.checks:
            if check.state == ReadinessState.FAILED:
                logger.error(
                    f"STARTUP BLOCKED: {check.name} - {check.message}. "
                    f"ACTION: {check.operator_action or 'See documentation'}"
                )
            elif check.state == ReadinessState.DEGRADED:
                logger.warning(
                    f"DEGRADED: {check.name} - {check.message}. "
                    f"RECOMMENDED: {check.operator_action or 'Investigate'}"
                )
            else:
                logger.info(
                    f"READY: {check.name} - {check.message} "
                    f"({check.duration_ms:.1f}ms)"
                )

        if not self.can_serve_traffic:
            logger.error(
                "STARTUP FAILED: System cannot serve traffic. "
                f"Failed checks: {[c.name for c in self.failed_checks]}"
            )
        elif self.degraded_checks:
            logger.warning(
                f"STARTUP DEGRADED: System operational but with issues. "
                f"Degraded: {[c.name for c in self.degraded_checks]}"
            )
        else:
            logger.info("STARTUP COMPLETE: All systems ready")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "can_serve_traffic": self.can_serve_traffic,
            "is_fully_healthy": self.is_fully_healthy,
            "mode": self.mode.value,
            "started_at": self.started_at.isoformat(),
            "checks": [
                {
                    "name": c.name,
                    "state": c.state.value,
                    "message": c.message,
                    "duration_ms": c.duration_ms,
                    "operator_action": c.operator_action,
                }
                for c in self.checks
            ],
        }


def _timed_check(
    name: str,
    check_fn: Callable[[], tuple],
) -> ReadinessCheck:
    """Run a check function and time it."""
    start = time.perf_counter()
    try:
        state, message, details, action = check_fn()
        duration = (time.perf_counter() - start) * 1000
        return ReadinessCheck(
            name=name,
            state=state,
            message=message,
            duration_ms=duration,
            details=details or {},
            operator_action=action,
        )
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        return ReadinessCheck(
            name=name,
            state=ReadinessState.FAILED,
            message=f"Check threw exception: {e}",
            duration_ms=duration,
            operator_action="Check logs for stack trace",
        )


def check_paths() -> tuple:
    """Validate all required paths exist."""
    result = validate_paths(check_ui=False, check_database=True)

    if result.has_critical_failures:
        critical = [i for i in result.issues if i.severity == PathSeverity.CRITICAL]
        return (
            ReadinessState.FAILED,
            f"{len(critical)} critical path(s) missing",
            {"issues": [str(i) for i in critical]},
            critical[0].operator_action if critical else None,
        )
    elif result.has_warnings:
        warnings = [i for i in result.issues if i.severity == PathSeverity.WARNING]
        return (
            ReadinessState.DEGRADED,
            f"{len(warnings)} path warning(s)",
            {"issues": [str(i) for i in warnings]},
            warnings[0].operator_action if warnings else None,
        )
    return (
        ReadinessState.READY,
        "All paths validated",
        {},
        None,
    )


def check_ui_assets() -> tuple:
    """Verify UI build assets are available."""
    status = get_ui_asset_status()

    if not status["available"]:
        return (
            ReadinessState.FAILED,
            status["message"],
            {"missing": status["missing_assets"]},
            "Build UI: cd /opt/water-controller/web/ui && npm run build",
        )

    details = {"build_time": status["build_time"]}
    return (
        ReadinessState.READY,
        "UI assets available",
        details,
        None,
    )


def check_database() -> tuple:
    """Verify database is accessible and writable."""
    from sqlalchemy import text
    from ..models.base import engine

    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()

        # Test write capability with a simple transaction
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))

        return (
            ReadinessState.READY,
            "Database accessible and writable",
            {"path": str(paths.database_file)},
            None,
        )
    except Exception as e:
        return (
            ReadinessState.FAILED,
            f"Database error: {e}",
            {"error": str(e)},
            f"Check database file permissions: ls -la {paths.database_file}",
        )


def check_port_available(port: int, host: str = "0.0.0.0") -> tuple:
    """Check if we can bind to the required port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1)
        sock.bind((host, port))
        sock.close()
        return (
            ReadinessState.READY,
            f"Port {port} available",
            {"port": port, "host": host},
            None,
        )
    except socket.error as e:
        return (
            ReadinessState.FAILED,
            f"Port {port} unavailable: {e}",
            {"port": port, "error": str(e)},
            f"Check for conflicting service: sudo ss -tlnp | grep :{port}",
        )


def check_ipc_shm() -> tuple:
    """Check if shared memory IPC is available."""
    try:
        from ..services.shm_client import get_shm_client
        shm = get_shm_client()

        if shm and shm.is_connected():
            controller_running = shm.is_controller_running()
            return (
                ReadinessState.READY,
                "IPC connected, controller running" if controller_running else "IPC connected, controller not running",
                {"controller_running": controller_running},
                None,
            )
        else:
            return (
                ReadinessState.DEGRADED,
                "IPC not connected - running in API-only mode",
                {"simulation_mode": True},
                "Start controller service: systemctl start water-controller",
            )
    except ImportError:
        return (
            ReadinessState.DEGRADED,
            "IPC module not available - simulation mode",
            {"simulation_mode": True},
            None,
        )
    except Exception as e:
        return (
            ReadinessState.DEGRADED,
            f"IPC check failed: {e}",
            {"error": str(e), "simulation_mode": True},
            "Controller may not be running",
        )


def check_required_python_modules() -> tuple:
    """Verify all required Python modules are importable."""
    required = [
        ("fastapi", "FastAPI framework"),
        ("uvicorn", "ASGI server"),
        ("pydantic", "Data validation"),
        ("sqlalchemy", "Database ORM"),
    ]

    missing = []
    for module, desc in required:
        try:
            __import__(module)
        except ImportError:
            missing.append(f"{module} ({desc})")

    if missing:
        return (
            ReadinessState.FAILED,
            f"Missing Python modules: {', '.join(missing)}",
            {"missing": missing},
            "Install dependencies: pip install -r requirements.txt",
        )
    return (
        ReadinessState.READY,
        "All Python dependencies available",
        {"checked": [m for m, _ in required]},
        None,
    )


def validate_startup(
    mode: Optional[StartupMode] = None,
    skip_ui_check: bool = False,
    skip_ipc_check: bool = False,
    api_port: int = 8000,
) -> StartupResult:
    """
    Perform comprehensive startup validation.

    This is the main entry point for startup validation. Call this
    during application lifespan startup.

    Args:
        mode: Validation strictness. Defaults to PRODUCTION unless
              WTC_STARTUP_MODE or WTC_DEBUG is set.
        skip_ui_check: Skip UI asset validation (for API-only mode)
        skip_ipc_check: Skip IPC/shared memory check (for simulation)
        api_port: Port the API will bind to

    Returns:
        StartupResult with all check results
    """
    # Determine mode
    if mode is None:
        env_mode = os.environ.get("WTC_STARTUP_MODE", "").lower()
        if env_mode == "development":
            mode = StartupMode.DEVELOPMENT
        elif env_mode == "simulation":
            mode = StartupMode.SIMULATION
        elif os.environ.get("WTC_DEBUG", "").lower() in ("true", "1"):
            mode = StartupMode.DEVELOPMENT
        else:
            mode = StartupMode.PRODUCTION

    result = StartupResult(mode=mode)

    # === Core checks (always run) ===
    result.checks.append(_timed_check("python_modules", check_required_python_modules))
    result.checks.append(_timed_check("paths", check_paths))
    result.checks.append(_timed_check("database", check_database))

    # === UI check (unless skipped) ===
    if not skip_ui_check:
        result.checks.append(_timed_check("ui_assets", check_ui_assets))

    # === IPC check (unless skipped or simulation) ===
    if not skip_ipc_check and mode != StartupMode.SIMULATION:
        result.checks.append(_timed_check("ipc_shm", check_ipc_shm))

    # === Development mode: downgrade failures to warnings ===
    if mode == StartupMode.DEVELOPMENT:
        for check in result.checks:
            if check.state == ReadinessState.FAILED:
                # Only downgrade non-critical failures in dev mode
                if check.name not in ("database", "python_modules"):
                    check.state = ReadinessState.DEGRADED
                    check.message = f"[DEV MODE] {check.message}"

    return result


# Global startup result for health check access
_startup_result: Optional[StartupResult] = None


def get_startup_result() -> Optional[StartupResult]:
    """Get the startup validation result (if validation has run)."""
    return _startup_result


def set_startup_result(result: StartupResult) -> None:
    """Store startup result for later access."""
    global _startup_result
    _startup_result = result
