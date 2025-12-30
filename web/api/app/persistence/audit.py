"""
Water Treatment Controller - Audit and Command Log Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Audit log and command log operations.
"""

import logging
from typing import Any

from .base import get_db

logger = logging.getLogger(__name__)


def log_audit(user: str, action: str, resource_type: str, resource_id: str,
              details: str, ip_address: str | None = None):
    """Log an audit event"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO audit_log (user, action, resource_type, resource_id, details, ip_address)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user, action, resource_type, resource_id, details, ip_address))
            conn.commit()
    except Exception as e:
        # [CONDITION] + [CONSEQUENCE] + [ACTION] per Section 1.9
        logger.error(
            f"Audit log write failed: {e}. "
            "Event not recorded for compliance. "
            "Check database connectivity and retry operation."
        )


def get_audit_log(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """Get audit log entries"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ? OFFSET ?
        ''', (limit, offset))
        return [dict(row) for row in cursor.fetchall()]


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
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO command_log (username, rtu_station, control_id, command,
                command_value, source_ip, session_token)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (username, rtu_station, control_id, command, command_value,
              source_ip, session_token[:20] if session_token else None))
        conn.commit()
        return cursor.lastrowid


def update_command_result(log_id: int, result: str, error_message: str | None = None) -> bool:
    """Update a command log entry with execution result"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE command_log SET result = ?, error_message = ?
            WHERE id = ?
        ''', (result, error_message, log_id))
        conn.commit()
        return cursor.rowcount > 0


def get_command_log(
    rtu_station: str | None = None,
    username: str | None = None,
    limit: int = 100,
    offset: int = 0
) -> list[dict[str, Any]]:
    """Get command log entries with optional filtering."""
    with get_db() as conn:
        cursor = conn.cursor()

        where_clauses = []
        params = []

        if rtu_station:
            where_clauses.append("rtu_station = ?")
            params.append(rtu_station)
        if username:
            where_clauses.append("username = ?")
            params.append(username)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        params.extend([limit, offset])

        cursor.execute(f'''
            SELECT * FROM command_log
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        ''', tuple(params))
        return [dict(row) for row in cursor.fetchall()]


def get_command_log_count(rtu_station: str | None = None, username: str | None = None) -> int:
    """Get total count of command log entries with optional filtering"""
    with get_db() as conn:
        cursor = conn.cursor()

        where_clauses = []
        params = []

        if rtu_station:
            where_clauses.append("rtu_station = ?")
            params.append(rtu_station)
        if username:
            where_clauses.append("username = ?")
            params.append(username)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        cursor.execute(f'SELECT COUNT(*) FROM command_log {where_sql}', tuple(params))
        return cursor.fetchone()[0]


def clear_old_command_logs(days: int = 90) -> int:
    """Delete command logs older than specified days"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM command_log
            WHERE timestamp < datetime('now', ? || ' days')
        ''', (f'-{days}',))
        conn.commit()
        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old command log entries")
        return deleted
