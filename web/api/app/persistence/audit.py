"""
Water Treatment Controller - Audit and Command Log Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Audit log and command log operations using SQLAlchemy.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func

from ..models.audit import CommandLog
from ..models.user import AuditLog
from .base import get_db

logger = logging.getLogger(__name__)


def _audit_to_dict(entry: AuditLog) -> dict[str, Any]:
    """Convert AuditLog model to dictionary."""
    return {
        "id": entry.id,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        "user": entry.user,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "details": entry.details,
        "ip_address": entry.ip_address,
    }


def _command_log_to_dict(entry: CommandLog) -> dict[str, Any]:
    """Convert CommandLog model to dictionary."""
    return {
        "id": entry.id,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        "username": entry.username,
        "rtu_station": entry.rtu_station,
        "control_id": entry.control_id,
        "command": entry.command,
        "command_value": entry.command_value,
        "result": entry.result,
        "error_message": entry.error_message,
        "source_ip": entry.source_ip,
        "session_token": entry.session_token,
    }


def log_audit(user: str, action: str, resource_type: str, resource_id: str,
              details: str, ip_address: str | None = None):
    """Log an audit event"""
    try:
        with get_db() as db:
            entry = AuditLog(
                user=user,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address,
            )
            db.add(entry)
            db.commit()
    except Exception as e:
        # [CONDITION] + [CONSEQUENCE] + [ACTION] per Section 1.9
        logger.error(
            f"Audit log write failed: {e}. "
            "Event not recorded for compliance. "
            "Check database connectivity and retry operation."
        )


def get_audit_log(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """Get audit log entries"""
    with get_db() as db:
        entries = db.query(AuditLog).order_by(
            AuditLog.timestamp.desc()
        ).limit(limit).offset(offset).all()
        return [_audit_to_dict(e) for e in entries]


# ============== Command Log Operations ==============

def log_command(
    username: str,
    rtu_station: str,
    control_id: str,
    command: str,
    command_value: float | None = None,
    source_ip: str | None = None,
    session_token: str | None = None
) -> int:
    """
    Log a control command attempt before execution.
    Returns the log entry ID for updating with result.
    """
    with get_db() as db:
        entry = CommandLog(
            username=username,
            rtu_station=rtu_station,
            control_id=control_id,
            command=command,
            command_value=command_value,
            source_ip=source_ip,
            session_token=session_token[:20] if session_token else None,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry.id


def update_command_result(log_id: int, result: str, error_message: str | None = None) -> bool:
    """Update a command log entry with execution result"""
    with get_db() as db:
        entry = db.query(CommandLog).filter(CommandLog.id == log_id).first()
        if entry:
            entry.result = result
            entry.error_message = error_message
            db.commit()
            return True
        return False


def get_command_log(
    rtu_station: str | None = None,
    username: str | None = None,
    limit: int = 100,
    offset: int = 0
) -> list[dict[str, Any]]:
    """Get command log entries with optional filtering."""
    with get_db() as db:
        query = db.query(CommandLog)

        if rtu_station:
            query = query.filter(CommandLog.rtu_station == rtu_station)
        if username:
            query = query.filter(CommandLog.username == username)

        entries = query.order_by(
            CommandLog.timestamp.desc()
        ).limit(limit).offset(offset).all()
        return [_command_log_to_dict(e) for e in entries]


def get_command_log_count(rtu_station: str | None = None, username: str | None = None) -> int:
    """Get total count of command log entries with optional filtering"""
    with get_db() as db:
        query = db.query(func.count(CommandLog.id))

        if rtu_station:
            query = query.filter(CommandLog.rtu_station == rtu_station)
        if username:
            query = query.filter(CommandLog.username == username)

        return query.scalar()


def clear_old_command_logs(days: int = 90) -> int:
    """Delete command logs older than specified days"""
    with get_db() as db:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        old_entries = db.query(CommandLog).filter(
            CommandLog.timestamp < cutoff
        ).all()
        count = len(old_entries)
        for entry in old_entries:
            db.delete(entry)
        db.commit()
        if count > 0:
            logger.info(f"Cleaned up {count} old command log entries")
        return count
