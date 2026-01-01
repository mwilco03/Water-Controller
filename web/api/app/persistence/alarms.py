"""
Water Treatment Controller - Alarms Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Alarm rules and shelved alarms (ISA-18.2) operations using SQLAlchemy.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from ..models.alarm import AlarmRule, ShelvedAlarm
from .audit import log_audit
from .base import get_db

logger = logging.getLogger(__name__)


def _rule_to_dict(rule: AlarmRule) -> dict[str, Any]:
    """Convert AlarmRule to dictionary."""
    return {
        "id": rule.id,
        "name": rule.name,
        "rtu_station": rule.rtu_station,
        "slot": rule.slot,
        "condition": rule.condition,
        "threshold": rule.threshold,
        "severity": rule.severity,
        "delay_ms": rule.delay_ms,
        "message": rule.message,
        "enabled": rule.enabled,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _shelved_to_dict(shelved: ShelvedAlarm) -> dict[str, Any]:
    """Convert ShelvedAlarm to dictionary."""
    return {
        "id": shelved.id,
        "rtu_station": shelved.rtu_station,
        "slot": shelved.slot,
        "shelved_by": shelved.shelved_by,
        "shelved_at": shelved.shelved_at.isoformat() if shelved.shelved_at else None,
        "shelf_duration_minutes": shelved.shelf_duration_minutes,
        "expires_at": shelved.expires_at.isoformat() if shelved.expires_at else None,
        "reason": shelved.reason,
        "active": shelved.active,
    }


# ============== Alarm Rules Operations ==============

def get_alarm_rules() -> list[dict[str, Any]]:
    """Get all alarm rules"""
    with get_db() as db:
        rules = db.query(AlarmRule).order_by(AlarmRule.id).all()
        return [_rule_to_dict(r) for r in rules]


def get_alarm_rule(rule_id: int) -> dict[str, Any] | None:
    """Get a single alarm rule"""
    with get_db() as db:
        rule = db.query(AlarmRule).filter(AlarmRule.id == rule_id).first()
        return _rule_to_dict(rule) if rule else None


def create_alarm_rule(rule: dict[str, Any]) -> int:
    """
    Create a new alarm rule.

    NOTE: Alarm rules generate NOTIFICATIONS only.
    Interlocks are configured on the RTU directly.
    """
    with get_db() as db:
        new_rule = AlarmRule(
            name=rule['name'],
            rtu_station=rule['rtu_station'],
            slot=rule['slot'],
            condition=rule['condition'],
            threshold=rule['threshold'],
            severity=rule['severity'],
            delay_ms=rule.get('delay_ms', 0),
            message=rule.get('message', ''),
            enabled=rule.get('enabled', True),
        )
        db.add(new_rule)
        db.commit()
        db.refresh(new_rule)
        log_audit('system', 'create', 'alarm_rule', str(new_rule.id),
                  f"Created alarm rule {rule['name']}")
        return new_rule.id


def update_alarm_rule(rule_id: int, rule: dict[str, Any]) -> bool:
    """
    Update an alarm rule.

    NOTE: Alarm rules generate NOTIFICATIONS only.
    Interlocks are configured on the RTU directly.
    """
    with get_db() as db:
        existing = db.query(AlarmRule).filter(AlarmRule.id == rule_id).first()
        if not existing:
            return False

        existing.name = rule['name']
        existing.rtu_station = rule['rtu_station']
        existing.slot = rule['slot']
        existing.condition = rule['condition']
        existing.threshold = rule['threshold']
        existing.severity = rule['severity']
        existing.delay_ms = rule.get('delay_ms', 0)
        existing.message = rule.get('message', '')
        existing.enabled = rule.get('enabled', True)
        existing.updated_at = datetime.now(UTC)

        db.commit()
        return True


def delete_alarm_rule(rule_id: int) -> bool:
    """Delete an alarm rule"""
    with get_db() as db:
        rule = db.query(AlarmRule).filter(AlarmRule.id == rule_id).first()
        if not rule:
            return False
        db.delete(rule)
        db.commit()
        log_audit('system', 'delete', 'alarm_rule', str(rule_id),
                  f"Deleted alarm rule {rule_id}")
        return True


# ============== Shelved Alarms Operations (ISA-18.2) ==============

def get_shelved_alarms(include_expired: bool = False) -> list[dict[str, Any]]:
    """Get all shelved alarms, optionally including expired ones"""
    with get_db() as db:
        query = db.query(ShelvedAlarm)
        if not include_expired:
            query = query.filter(
                ShelvedAlarm.active == True,
                ShelvedAlarm.expires_at > datetime.now(UTC)
            )
        shelved = query.order_by(ShelvedAlarm.shelved_at.desc()).all()
        return [_shelved_to_dict(s) for s in shelved]


def is_alarm_shelved(rtu_station: str, slot: int) -> bool:
    """Check if an alarm is currently shelved"""
    with get_db() as db:
        count = db.query(ShelvedAlarm).filter(
            ShelvedAlarm.rtu_station == rtu_station,
            ShelvedAlarm.slot == slot,
            ShelvedAlarm.active == True,
            ShelvedAlarm.expires_at > datetime.now(UTC)
        ).count()
        return count > 0


def shelve_alarm(rtu_station: str, slot: int, username: str,
                 duration_minutes: int, reason: str | None = None) -> int:
    """Shelve an alarm for a specified duration"""
    with get_db() as db:
        # First, deactivate any existing shelving for this alarm
        existing = db.query(ShelvedAlarm).filter(
            ShelvedAlarm.rtu_station == rtu_station,
            ShelvedAlarm.slot == slot,
            ShelvedAlarm.active == True
        ).all()
        for s in existing:
            s.active = False

        # Create new shelving entry
        expires_at = datetime.now(UTC) + timedelta(minutes=duration_minutes)
        new_shelved = ShelvedAlarm(
            rtu_station=rtu_station,
            slot=slot,
            shelved_by=username,
            shelf_duration_minutes=duration_minutes,
            expires_at=expires_at,
            reason=reason,
        )
        db.add(new_shelved)
        db.commit()
        db.refresh(new_shelved)
        log_audit(username, 'shelve', 'alarm', f"{rtu_station}:{slot}",
                  f"Shelved alarm for {duration_minutes} min: {reason or 'No reason'}")
        return new_shelved.id


def unshelve_alarm(shelf_id: int, username: str) -> bool:
    """Manually unshelve an alarm before expiration"""
    with get_db() as db:
        shelved = db.query(ShelvedAlarm).filter(ShelvedAlarm.id == shelf_id).first()
        if not shelved:
            return False

        rtu_station = shelved.rtu_station
        slot = shelved.slot
        shelved.active = False
        db.commit()
        log_audit(username, 'unshelve', 'alarm',
                  f"{rtu_station}:{slot}", "Manually unshelved")
        return True


def cleanup_expired_shelves() -> int:
    """Deactivate all expired shelved alarms"""
    with get_db() as db:
        expired = db.query(ShelvedAlarm).filter(
            ShelvedAlarm.active == True,
            ShelvedAlarm.expires_at <= datetime.now(UTC)
        ).all()
        count = len(expired)
        for s in expired:
            s.active = False
        db.commit()
        if count > 0:
            logger.info(f"Cleaned up {count} expired shelved alarms")
        return count


def get_shelved_alarm(shelf_id: int) -> dict[str, Any] | None:
    """Get a single shelved alarm entry"""
    with get_db() as db:
        shelved = db.query(ShelvedAlarm).filter(ShelvedAlarm.id == shelf_id).first()
        return _shelved_to_dict(shelved) if shelved else None
