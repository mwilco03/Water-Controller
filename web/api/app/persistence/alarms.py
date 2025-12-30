"""
Water Treatment Controller - Alarms Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Alarm rules and shelved alarms (ISA-18.2) operations.
"""

import logging
from typing import Any

from .audit import log_audit
from .base import get_db

logger = logging.getLogger(__name__)


# ============== Alarm Rules Operations ==============

def get_alarm_rules() -> list[dict[str, Any]]:
    """Get all alarm rules"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM alarm_rules ORDER BY id')
        return [dict(row) for row in cursor.fetchall()]


def get_alarm_rule(rule_id: int) -> dict[str, Any] | None:
    """Get a single alarm rule"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM alarm_rules WHERE id = ?', (rule_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_alarm_rule(rule: dict[str, Any]) -> int:
    """
    Create a new alarm rule.

    NOTE: Alarm rules generate NOTIFICATIONS only.
    Interlocks are configured on the RTU directly.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO alarm_rules (name, rtu_station, slot, condition, threshold,
                severity, delay_ms, message, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (rule['name'], rule['rtu_station'], rule['slot'], rule['condition'],
              rule['threshold'], rule['severity'], rule.get('delay_ms', 0),
              rule.get('message', ''), rule.get('enabled', True)))
        conn.commit()
        log_audit('system', 'create', 'alarm_rule', str(cursor.lastrowid),
                  f"Created alarm rule {rule['name']}")
        return cursor.lastrowid


def update_alarm_rule(rule_id: int, rule: dict[str, Any]) -> bool:
    """
    Update an alarm rule.

    NOTE: Alarm rules generate NOTIFICATIONS only.
    Interlocks are configured on the RTU directly.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE alarm_rules
            SET name = ?, rtu_station = ?, slot = ?, condition = ?, threshold = ?,
                severity = ?, delay_ms = ?, message = ?, enabled = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (rule['name'], rule['rtu_station'], rule['slot'], rule['condition'],
              rule['threshold'], rule['severity'], rule.get('delay_ms', 0),
              rule.get('message', ''), rule.get('enabled', True), rule_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_alarm_rule(rule_id: int) -> bool:
    """Delete an alarm rule"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM alarm_rules WHERE id = ?', (rule_id,))
        conn.commit()
        log_audit('system', 'delete', 'alarm_rule', str(rule_id),
                  f"Deleted alarm rule {rule_id}")
        return cursor.rowcount > 0


# ============== Shelved Alarms Operations (ISA-18.2) ==============

def get_shelved_alarms(include_expired: bool = False) -> list[dict[str, Any]]:
    """Get all shelved alarms, optionally including expired ones"""
    with get_db() as conn:
        cursor = conn.cursor()
        if include_expired:
            cursor.execute('SELECT * FROM shelved_alarms ORDER BY shelved_at DESC')
        else:
            cursor.execute('''
                SELECT * FROM shelved_alarms
                WHERE active = 1 AND expires_at > datetime('now')
                ORDER BY shelved_at DESC
            ''')
        return [dict(row) for row in cursor.fetchall()]


def is_alarm_shelved(rtu_station: str, slot: int) -> bool:
    """Check if an alarm is currently shelved"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM shelved_alarms
            WHERE rtu_station = ? AND slot = ? AND active = 1
                AND expires_at > datetime('now')
        ''', (rtu_station, slot))
        return cursor.fetchone()[0] > 0


def shelve_alarm(rtu_station: str, slot: int, username: str,
                 duration_minutes: int, reason: str | None = None) -> int:
    """Shelve an alarm for a specified duration"""
    with get_db() as conn:
        cursor = conn.cursor()
        # First, deactivate any existing shelving for this alarm
        cursor.execute('''
            UPDATE shelved_alarms SET active = 0
            WHERE rtu_station = ? AND slot = ? AND active = 1
        ''', (rtu_station, slot))

        # Create new shelving entry
        cursor.execute('''
            INSERT INTO shelved_alarms (rtu_station, slot, shelved_by,
                shelf_duration_minutes, expires_at, reason)
            VALUES (?, ?, ?, ?, datetime('now', ? || ' minutes'), ?)
        ''', (rtu_station, slot, username, duration_minutes,
              f'+{duration_minutes}', reason))
        conn.commit()
        log_audit(username, 'shelve', 'alarm', f"{rtu_station}:{slot}",
                  f"Shelved alarm for {duration_minutes} min: {reason or 'No reason'}")
        return cursor.lastrowid


def unshelve_alarm(shelf_id: int, username: str) -> bool:
    """Manually unshelve an alarm before expiration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT rtu_station, slot FROM shelved_alarms WHERE id = ?',
                       (shelf_id,))
        row = cursor.fetchone()
        if not row:
            return False

        cursor.execute('UPDATE shelved_alarms SET active = 0 WHERE id = ?', (shelf_id,))
        conn.commit()
        log_audit(username, 'unshelve', 'alarm',
                  f"{row['rtu_station']}:{row['slot']}", "Manually unshelved")
        return cursor.rowcount > 0


def cleanup_expired_shelves() -> int:
    """Deactivate all expired shelved alarms"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE shelved_alarms SET active = 0
            WHERE active = 1 AND expires_at <= datetime('now')
        ''')
        conn.commit()
        count = cursor.rowcount
        if count > 0:
            logger.info(f"Cleaned up {count} expired shelved alarms")
        return count


def get_shelved_alarm(shelf_id: int) -> dict[str, Any] | None:
    """Get a single shelved alarm entry"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM shelved_alarms WHERE id = ?', (shelf_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
