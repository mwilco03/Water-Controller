"""
Water Treatment Controller - Structured Logging Setup
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Configure structured logging for SCADA operations.
No console pollution - all output goes through proper logging.
Includes correlation ID support for distributed tracing.
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional
import json
import time

# Correlation ID context variable (thread-safe and async-safe)
_correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
_operation_name: ContextVar[Optional[str]] = ContextVar('operation_name', default=None)
_operation_start: ContextVar[Optional[float]] = ContextVar('operation_start', default=None)


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID."""
    return _correlation_id.get()


def set_correlation_id(correlation_id: Optional[str]) -> None:
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


def end_operation() -> Optional[float]:
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

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
    log_file: Optional[str] = None
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
    if structured:
        formatter = StructuredFormatter()
    else:
        formatter = HumanReadableFormatter()

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
