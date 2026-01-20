"""
Water Treatment Controller - Alarm Service
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Service layer for alarm operations - encapsulates business logic
and database operations for testability.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..core.exceptions import AlarmNotFoundError, RtuNotFoundError
from ..models.alarm import AlarmEvent, AlarmPriority, AlarmRule, AlarmState
from ..models.rtu import RTU


class AlarmService:
    """Service for alarm operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_rtu_by_name(self, name: str) -> RTU:
        """Get RTU by name or raise 404."""
        rtu = self.db.query(RTU).filter(RTU.station_name == name).first()
        if not rtu:
            raise RtuNotFoundError(name)
        return rtu

    def get_alarm_event(self, alarm_id: int) -> AlarmEvent:
        """Get alarm event by ID or raise 404."""
        event = self.db.query(AlarmEvent).filter(AlarmEvent.id == alarm_id).first()
        if not event:
            raise AlarmNotFoundError(alarm_id)
        return event

    def list_active_alarms(
        self,
        rtu_name: str | None = None,
        priority: str | None = None,
        acknowledged: bool | None = None,
        limit: int = 100,
    ) -> tuple[list[AlarmEvent], dict[str, int]]:
        """
        List active alarms with optional filters.

        Returns:
            Tuple of (list of events, stats dict with counts)
        """
        query = self.db.query(AlarmEvent).filter(AlarmEvent.state != AlarmState.CLEARED)

        if rtu_name:
            query = query.filter(AlarmEvent.rtu_station == rtu_name)

        if priority:
            query = query.join(AlarmRule).filter(AlarmRule.severity == priority.upper())

        if acknowledged is not None:
            if acknowledged:
                query = query.filter(AlarmEvent.state == AlarmState.ACKNOWLEDGED)
            else:
                query = query.filter(AlarmEvent.state == AlarmState.ACTIVE)

        total = query.count()
        active_count = self.db.query(AlarmEvent).filter(
            AlarmEvent.state == AlarmState.ACTIVE
        ).count()
        unack_count = self.db.query(AlarmEvent).filter(
            AlarmEvent.state == AlarmState.ACTIVE,
            AlarmEvent.acknowledged_at.is_(None)
        ).count()

        events = query.order_by(AlarmEvent.activated_at.desc()).limit(limit).all()

        stats = {
            "total": total,
            "active": active_count,
            "unacknowledged": unack_count,
        }

        return events, stats

    def get_alarm_history(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        rtu_name: str | None = None,
        priority: str | None = None,
        limit: int = 100,
    ) -> tuple[list[AlarmEvent], int]:
        """
        Get historical alarm log.

        Returns:
            Tuple of (list of events, total count)
        """
        now = datetime.now(UTC)
        if not end:
            end = now
        if not start:
            start = end - timedelta(hours=24)

        query = self.db.query(AlarmEvent).filter(
            AlarmEvent.activated_at >= start,
            AlarmEvent.activated_at <= end
        )

        if rtu_name:
            query = query.filter(AlarmEvent.rtu_station == rtu_name)

        if priority:
            query = query.join(AlarmRule).filter(AlarmRule.severity == priority.upper())

        total = query.count()
        events = query.order_by(AlarmEvent.activated_at.desc()).limit(limit).all()

        return events, total

    def acknowledge_alarm(
        self,
        alarm_id: int,
        username: str,
        note: str | None = None
    ) -> AlarmEvent:
        """
        Acknowledge an alarm.

        Returns:
            Updated alarm event
        """
        event = self.get_alarm_event(alarm_id)

        if event.state != AlarmState.CLEARED:
            event.acknowledge(user=username, note=note)
            self.db.commit()

        return event

    def acknowledge_all(
        self,
        username: str,
        rtu_name: str | None = None,
        note: str | None = None
    ) -> int:
        """
        Acknowledge all active alarms.

        Returns:
            Count of acknowledged alarms
        """
        query = self.db.query(AlarmEvent).filter(AlarmEvent.state == AlarmState.ACTIVE)

        if rtu_name:
            query = query.filter(AlarmEvent.rtu_station == rtu_name)

        events = query.all()
        count = 0

        for event in events:
            event.acknowledge(user=username, note=note)
            count += 1

        self.db.commit()
        return count

    def event_to_dict(self, event: AlarmEvent) -> dict[str, Any]:
        """Convert alarm event to dictionary for API response."""
        # Query for the associated rule if we have an alarm_rule_id
        rule = None
        if event.alarm_rule_id:
            rule = self.db.query(AlarmRule).filter(AlarmRule.id == event.alarm_rule_id).first()

        return {
            "id": event.id,
            "rtu": event.rtu_station,
            "name": rule.name if rule else "unknown",
            "severity": rule.severity if rule else "MEDIUM",
            "condition": rule.condition if rule else "unknown",
            "threshold": rule.threshold if rule else 0.0,
            "message": event.message or "",
            "value": event.value_at_activation,
            "slot": event.slot,
            "state": event.state,
            "activated_at": event.activated_at,
            "acknowledged_at": event.acknowledged_at,
            "acknowledged_by": event.acknowledged_by,
            "cleared_at": event.cleared_at,
        }


def get_alarm_service(db: Session) -> AlarmService:
    """Factory function for AlarmService."""
    return AlarmService(db)
