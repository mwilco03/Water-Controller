"""
Water Treatment Controller - Structured Logging Setup
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Configure structured logging for SCADA operations.
No console pollution - all output goes through proper logging.
Includes correlation ID support for distributed tracing.
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

# Correlation ID context variable (thread-safe and async-safe)
_correlation_id: ContextVar[str | None] = ContextVar('correlation_id', default=None)
_operation_name: ContextVar[str | None] = ContextVar('operation_name', default=None)
_operation_start: ContextVar[float | None] = ContextVar('operation_start', default=None)


def get_correlation_id() -> str | None:
    """Get the current correlation ID."""
    return _correlation_id.get()


def set_correlation_id(correlation_id: str | None) -> None:
    """Set the correlation ID for the current context."""
    _correlation_id.set(correlation_id)


def generate_correlation_id() -> str:
    """Generate a new correlation ID (UUID format matching C controller)."""
    return str(uuid.uuid4())


def start_operation(operation: str) -> str:
    """
    Start a new correlated operation.
    Returns the generated correlation ID.
    """
    cid = generate_correlation_id()
    _correlation_id.set(cid)
    _operation_name.set(operation)
    _operation_start.set(time.monotonic())
    return cid


def end_operation() -> float | None:
    """
    End the current correlated operation.
    Returns the duration in milliseconds, or None if no operation was started.
    """
    start = _operation_start.get()
    duration_ms = None
    if start is not None:
        duration_ms = (time.monotonic() - start) * 1000

    _correlation_id.set(None)
    _operation_name.set(None)
    _operation_start.set(None)

    return duration_ms


class CorrelationIdFilter(logging.Filter):
    """Logging filter that adds correlation ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _correlation_id.get() or ""
        record.operation_name = _operation_name.get() or ""
        return True


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter for production use."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if present (highest priority for tracing)
        if hasattr(record, "correlation_id") and record.correlation_id:
            log_entry["correlation_id"] = record.correlation_id
        if hasattr(record, "operation_name") and record.operation_name:
            log_entry["operation_name"] = record.operation_name

        # Add extra fields if present
        if hasattr(record, "rtu"):
            log_entry["rtu"] = record.rtu
        if hasattr(record, "operation"):
            log_entry["operation"] = record.operation
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "user"):
            log_entry["user"] = record.user
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        # Build correlation ID prefix
        cid_prefix = ""
        if hasattr(record, "correlation_id") and record.correlation_id:
            # Use short form of UUID for readability
            short_cid = record.correlation_id[:8] if len(record.correlation_id) >= 8 else record.correlation_id
            cid_prefix = f"[{short_cid}] "

        # Build context string from extra fields
        context_parts = []
        if hasattr(record, "rtu"):
            context_parts.append(f"rtu={record.rtu}")
        if hasattr(record, "operation"):
            context_parts.append(f"op={record.operation}")
        if hasattr(record, "operation_name") and record.operation_name:
            context_parts.append(f"op={record.operation_name}")
        if hasattr(record, "duration_ms"):
            context_parts.append(f"dur={record.duration_ms}ms")
        if hasattr(record, "user"):
            context_parts.append(f"user={record.user}")

        context = f" [{', '.join(context_parts)}]" if context_parts else ""

        base = f"{timestamp} {record.levelname:8} {cid_prefix}{record.name}: {record.getMessage()}{context}"

        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)

        return base


def setup_logging(
    level: str = "INFO",
    structured: bool = False,
    log_file: str | None = None
) -> logging.Logger:
    """
    Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        structured: Use JSON structured logging (for production)
        log_file: Optional file path for log output

    Returns:
        Root logger configured for the application
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Add correlation ID filter to root logger
    correlation_filter = CorrelationIdFilter()
    root_logger.addFilter(correlation_filter)

    # Choose formatter
    formatter = StructuredFormatter() if structured else HumanReadableFormatter()

    # Console handler (stderr to avoid console pollution on stdout)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(correlation_filter)
    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(correlation_filter)
        root_logger.addHandler(file_handler)

    # Suppress noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name."""
    return logging.getLogger(name)


# =============================================================================
# Operator-Focused Logging
# =============================================================================
# Anti-pattern addressed: "Logs as developer artifacts"
#
# Standard logs describe *what happened*.
# Operator logs must answer:
#   - What failed
#   - Why it matters
#   - What still works
#   - What the operator should do


class OperatorLogEntry:
    """
    Structured log entry for operator-actionable events.

    Usage:
        from app.core.logging import operator_log

        operator_log.error(
            what="Database connection failed",
            impact="Cannot store new sensor readings. Historical data unavailable.",
            still_works="RTU monitoring and alarm detection continue",
            action="Check database server status: systemctl status postgresql"
        )
    """

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _format_operator_message(
        self,
        what: str,
        impact: str = "",
        still_works: str = "",
        action: str = "",
    ) -> str:
        """Format a message with operator guidance."""
        parts = [f"WHAT: {what}"]
        if impact:
            parts.append(f"IMPACT: {impact}")
        if still_works:
            parts.append(f"STILL WORKS: {still_works}")
        if action:
            parts.append(f"ACTION: {action}")
        return " | ".join(parts)

    def info(
        self,
        what: str,
        impact: str = "",
        still_works: str = "",
        action: str = "",
        **extra
    ) -> None:
        """Log informational operator message."""
        msg = self._format_operator_message(what, impact, still_works, action)
        self._logger.info(msg, extra=extra)

    def warning(
        self,
        what: str,
        impact: str,
        still_works: str = "",
        action: str = "",
        **extra
    ) -> None:
        """Log warning with impact and recommended action."""
        msg = self._format_operator_message(what, impact, still_works, action)
        self._logger.warning(msg, extra=extra)

    def error(
        self,
        what: str,
        impact: str,
        still_works: str = "",
        action: str = "",
        **extra
    ) -> None:
        """Log error with impact and required action."""
        msg = self._format_operator_message(what, impact, still_works, action)
        self._logger.error(msg, extra=extra)

    def critical(
        self,
        what: str,
        impact: str,
        action: str,
        **extra
    ) -> None:
        """Log critical error requiring immediate action."""
        msg = self._format_operator_message(what, impact, "", action)
        self._logger.critical(msg, extra=extra)


# Pre-configured operator logger
operator_log = OperatorLogEntry(logging.getLogger("operator"))


# =============================================================================
# Common Operator Log Messages
# =============================================================================
# Pre-defined messages for common failure scenarios with guidance.

def log_database_failure(error: Exception) -> None:
    """Log database connection failure with operator guidance."""
    operator_log.error(
        what=f"Database connection failed: {error}",
        impact="Cannot store sensor readings or historian data. Configuration changes will not persist.",
        still_works="RTU monitoring, alarm detection, and PROFINET communication continue.",
        action="Check database status: sqlite3 /var/lib/water-controller/wtc.db '.tables'",
    )


def log_profinet_failure(error: str, rtu_name: str = "") -> None:
    """Log PROFINET communication failure with operator guidance."""
    rtu_info = f" for RTU '{rtu_name}'" if rtu_name else ""
    operator_log.error(
        what=f"PROFINET communication lost{rtu_info}: {error}",
        impact=f"Cannot read sensors or control actuators{rtu_info}. Data will show as stale.",
        still_works="Other RTUs, alarm history, and web interface remain operational.",
        action="Check network connectivity and RTU power. Verify PROFINET interface: ip link show eth0",
        rtu=rtu_name,
    )


def log_ipc_failure(error: str) -> None:
    """Log IPC/shared memory failure with operator guidance."""
    operator_log.error(
        what=f"IPC connection to controller failed: {error}",
        impact="API cannot communicate with PROFINET controller. Operating in simulation mode.",
        still_works="Web interface, historical data viewing, and configuration management.",
        action="Check controller service: systemctl status water-controller",
    )


def log_ui_build_missing() -> None:
    """Log missing UI build with operator guidance."""
    operator_log.critical(
        what="UI assets not found - web interface will not load",
        impact="Operators cannot access the HMI. System is effectively headless.",
        action="Build UI: cd /opt/water-controller/web/ui && npm install && npm run build",
    )


def log_startup_degraded(components: list) -> None:
    """Log degraded startup with operator guidance."""
    operator_log.warning(
        what="System started in degraded mode",
        impact=f"Some features may not work correctly. Degraded: {', '.join(components)}",
        still_works="Core monitoring and basic operations remain available.",
        action="Review startup logs for specific issues: journalctl -u water-controller-api -n 100",
    )


def log_data_stale(rtu_name: str, age_seconds: int) -> None:
    """Log stale data with operator guidance."""
    operator_log.warning(
        what=f"Data from RTU '{rtu_name}' is stale ({age_seconds}s old)",
        impact="Displayed values may not reflect current conditions.",
        still_works="Alarm thresholds based on last known values. Manual refresh may help.",
        action="Check RTU connectivity: ping <rtu-ip>. Check PROFINET status in System page.",
        rtu=rtu_name,
    )
