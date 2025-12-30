"""
Water Treatment Controller - Alarm Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for alarm rules and events.
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
    """Alarm rule configuration."""

    __tablename__ = "alarm_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_id = Column(Integer, ForeignKey("rtus.id", ondelete="CASCADE"), nullable=False)
    sensor_id = Column(Integer, ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True)

    tag = Column(String(32), nullable=False)
    alarm_type = Column(String(32), nullable=False)  # HIGH, LOW, HIGH_HIGH, etc.
    priority = Column(String(16), nullable=False, default=AlarmPriority.MEDIUM)

    setpoint = Column(Float, nullable=False)
    deadband = Column(Float, default=0.0)
    message_template = Column(String(256), nullable=True)
    enabled = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    rtu = relationship("RTU", back_populates="alarm_rules")
    events = relationship("AlarmEvent", back_populates="rule", cascade="all, delete-orphan")


class AlarmEvent(Base):
    """Alarm event instance."""

    __tablename__ = "alarm_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alarm_id = Column(Integer, ForeignKey("alarm_rules.id", ondelete="CASCADE"), nullable=False)
    rtu_id = Column(Integer, ForeignKey("rtus.id", ondelete="CASCADE"), nullable=False)

    state = Column(String(16), nullable=False, default=AlarmState.ACTIVE)
    value_at_activation = Column(Float, nullable=True)
    message = Column(String(256), nullable=True)

    # Timestamps
    activated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(64), nullable=True)
    cleared_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=True)

    # Relationships
    rule = relationship("AlarmRule", back_populates="events")
    rtu = relationship("RTU", back_populates="alarm_events")

    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_alarm_events_state", "state"),
        Index("ix_alarm_events_activated_at", "activated_at"),
        Index("ix_alarm_events_rtu_state", "rtu_id", "state"),
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
