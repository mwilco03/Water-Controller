"""
Water Treatment Controller - Alarm Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for alarm rules, events, and shelving.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .base import Base


class AlarmPriority:
    """Alarm priority constants."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AlarmState:
    """Alarm state constants."""

    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CLEARED = "CLEARED"


class AlarmRule(Base):
    """
    Alarm rule configuration.

    Note: These rules generate NOTIFICATIONS only.
    Interlocks are configured on the RTU directly.
    """

    __tablename__ = "alarm_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    rtu_station = Column(String(32), nullable=False, index=True)
    slot = Column(Integer, nullable=False)
    condition = Column(String(16), nullable=False)  # >, <, >=, <=, ==
    threshold = Column(Float, nullable=False)
    severity = Column(String(16), nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    delay_ms = Column(Integer, default=0)
    message = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )


class AlarmEvent(Base):
    """Alarm event instance (runtime alarm occurrences)."""

    __tablename__ = "alarm_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alarm_rule_id = Column(Integer, ForeignKey("alarm_rules.id", ondelete="CASCADE"), nullable=True)
    # Note: index defined in __table_args__ as ix_alarm_events_rtu_station
    rtu_station = Column(String(32), nullable=False)
    slot = Column(Integer, nullable=False)

    state = Column(String(16), nullable=False, default=AlarmState.ACTIVE)
    value_at_activation = Column(Float, nullable=True)
    message = Column(String(256), nullable=True)

    # Timestamps
    activated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(64), nullable=True)
    cleared_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=True)

    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_alarm_events_state", "state"),
        Index("ix_alarm_events_activated_at", "activated_at"),
        Index("ix_alarm_events_rtu_station", "rtu_station"),
    )

    def acknowledge(self, user: str, note: str | None = None):
        """Acknowledge the alarm."""
        self.state = AlarmState.ACKNOWLEDGED
        self.acknowledged_at = datetime.now(UTC)
        self.acknowledged_by = user
        if note:
            self.note = note

    def clear(self):
        """Clear the alarm."""
        self.state = AlarmState.CLEARED
        self.cleared_at = datetime.now(UTC)


class ShelvedAlarm(Base):
    """Shelved alarm entry per ISA-18.2 alarm management."""

    __tablename__ = "shelved_alarms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_station = Column(String(32), nullable=False, index=True)
    slot = Column(Integer, nullable=False)
    shelved_by = Column(String(64), nullable=False)
    shelved_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    shelf_duration_minutes = Column(Integer, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    reason = Column(Text, nullable=True)
    active = Column(Boolean, default=True)

    __table_args__ = (
        Index("ix_shelved_alarms_active_expires", "active", "expires_at"),
        Index("ix_shelved_alarms_rtu_slot", "rtu_station", "slot"),
    )


class ScheduledMaintenance(Base):
    """
    Scheduled maintenance window for pre-planned alarm suppression.

    Allows operators to schedule future maintenance periods where specific
    alarms or entire RTUs will be automatically shelved.

    Per ISA-18.2, scheduled shelving should:
    - Have clear start/end times
    - Be linked to work orders when possible
    - Notify incoming shifts of scheduled suppressions
    """

    __tablename__ = "scheduled_maintenance"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Target: can be specific slot or entire RTU (slot=-1)
    # Note: index defined in __table_args__ as ix_scheduled_maintenance_rtu
    rtu_station = Column(String(32), nullable=False)
    slot = Column(Integer, nullable=False)  # -1 means all slots for this RTU

    # Scheduling
    scheduled_by = Column(String(64), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    # Documentation
    reason = Column(Text, nullable=False)  # Required for audit trail
    work_order = Column(String(64), nullable=True)  # Optional link to maintenance system

    # Status
    status = Column(String(16), default="SCHEDULED")  # SCHEDULED, ACTIVE, COMPLETED, CANCELLED
    activated_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(String(64), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_scheduled_maintenance_status", "status"),
        Index("ix_scheduled_maintenance_start", "start_time"),
        Index("ix_scheduled_maintenance_rtu", "rtu_station"),
    )
