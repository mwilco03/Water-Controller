"""
Water Treatment Controller - Structured Logging Setup
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Configure structured logging for SCADA operations.
No console pollution - all output goes through proper logging.
"""

import logging
import sys
from datetime import datetime, timezone
from typing import Optional
import json


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter for production use."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

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

        # Build context string from extra fields
        context_parts = []
        if hasattr(record, "rtu"):
            context_parts.append(f"rtu={record.rtu}")
        if hasattr(record, "operation"):
            context_parts.append(f"op={record.operation}")
        if hasattr(record, "duration_ms"):
            context_parts.append(f"dur={record.duration_ms}ms")
        if hasattr(record, "user"):
            context_parts.append(f"user={record.user}")

        context = f" [{', '.join(context_parts)}]" if context_parts else ""

        base = f"{timestamp} {record.levelname:8} {record.name}: {record.getMessage()}{context}"

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

    # Choose formatter
    if structured:
        formatter = StructuredFormatter()
    else:
        formatter = HumanReadableFormatter()

    # Console handler (stderr to avoid console pollution on stdout)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Suppress noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name."""
    return logging.getLogger(name)
