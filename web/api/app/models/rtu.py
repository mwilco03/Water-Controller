"""
Water Treatment Controller - RTU Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for RTU, Slot, Sensor, and Control entities.
"""

from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship, Mapped

from .base import Base


class RtuState:
    """RTU connection state constants."""

    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    DISCOVERY = "DISCOVERY"
    RUNNING = "RUNNING"
    ERROR = "ERROR"


class SlotStatus:
    """Slot status constants."""

    OK = "OK"
    EMPTY = "EMPTY"
    FAULT = "FAULT"
    PULLED = "PULLED"
    WRONG_MODULE = "WRONG_MODULE"


class ControlType:
    """Control type constants."""

    DISCRETE = "discrete"
    ANALOG = "analog"


class RTU(Base):
    """RTU device configuration and state."""

    __tablename__ = "rtus"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_name = Column(String(32), unique=True, nullable=False, index=True)
    ip_address = Column(String(15), unique=True, nullable=False)
    vendor_id = Column(String(6), nullable=False)  # e.g., "0x002A"
    device_id = Column(String(6), nullable=False)  # e.g., "0x0405"
    slot_count = Column(Integer, nullable=False, default=8)

    # State tracking
    state = Column(String(20), nullable=False, default=RtuState.OFFLINE)
    state_since = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    slots = relationship("Slot", back_populates="rtu", cascade="all, delete-orphan")
    sensors = relationship("Sensor", back_populates="rtu", cascade="all, delete-orphan")
    controls = relationship("Control", back_populates="rtu", cascade="all, delete-orphan")
    alarm_rules = relationship("AlarmRule", back_populates="rtu", cascade="all, delete-orphan")
    alarm_events = relationship("AlarmEvent", back_populates="rtu", cascade="all, delete-orphan")

    def update_state(self, new_state: str, error: Optional[str] = None):
        """Update RTU state with timestamp."""
        self.state = new_state
        self.state_since = datetime.now(timezone.utc)
        if error:
            self.last_error = error
        elif new_state == RtuState.RUNNING:
            self.last_error = None


class Slot(Base):
    """RTU slot configuration."""

    __tablename__ = "slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_id = Column(Integer, ForeignKey("rtus.id", ondelete="CASCADE"), nullable=False)
    slot_number = Column(Integer, nullable=False)

    # Module information
    module_id = Column(String(6), nullable=True)  # e.g., "0x0032"
    module_type = Column(String(32), nullable=True)  # e.g., "AI-8"
    status = Column(String(20), default=SlotStatus.EMPTY)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    rtu = relationship("RTU", back_populates="slots")
    sensors = relationship("Sensor", back_populates="slot", cascade="all, delete-orphan")
    controls = relationship("Control", back_populates="slot", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("rtu_id", "slot_number", name="uix_rtu_slot"),
    )


class Sensor(Base):
    """Sensor configuration."""

    __tablename__ = "sensors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_id = Column(Integer, ForeignKey("rtus.id", ondelete="CASCADE"), nullable=False)
    slot_id = Column(Integer, ForeignKey("slots.id", ondelete="CASCADE"), nullable=False)

    tag = Column(String(32), unique=True, nullable=False, index=True)
    channel = Column(Integer, nullable=False)
    sensor_type = Column(String(32), nullable=False)  # level, flow, temp, pressure, etc.
    unit = Column(String(16), nullable=True)

    # Scaling
    scale_min = Column(Float, default=0.0)
    scale_max = Column(Float, default=100.0)
    eng_min = Column(Float, default=0.0)
    eng_max = Column(Float, default=100.0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    rtu = relationship("RTU", back_populates="sensors")
    slot = relationship("Slot", back_populates="sensors")


class Control(Base):
    """Control/actuator configuration."""

    __tablename__ = "controls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_id = Column(Integer, ForeignKey("rtus.id", ondelete="CASCADE"), nullable=False)
    slot_id = Column(Integer, ForeignKey("slots.id", ondelete="CASCADE"), nullable=False)

    tag = Column(String(32), unique=True, nullable=False, index=True)
    channel = Column(Integer, nullable=False)
    control_type = Column(String(16), nullable=False)  # discrete, analog
    equipment_type = Column(String(32), nullable=True)  # pump, valve, vfd, etc.

    # For analog controls
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    unit = Column(String(16), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    rtu = relationship("RTU", back_populates="controls")
    slot = relationship("Slot", back_populates="controls")
