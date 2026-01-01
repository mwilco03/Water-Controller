"""
Water Treatment Controller - Historian Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for historian data, slot configuration, and PROFINET diagnostics.
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
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import JSON

from .base import Base


class DataQuality:
    """Data quality constants."""

    GOOD = "GOOD"
    UNCERTAIN = "UNCERTAIN"
    BAD = "BAD"


class DiagnosticLevel:
    """Diagnostic level constants."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class HistorianSample(Base):
    """Time-series data sample."""

    __tablename__ = "historian_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sensor_id = Column(Integer, ForeignKey("sensors.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    value = Column(Float, nullable=True)
    quality = Column(String(16), default=DataQuality.GOOD)

    # Composite index for efficient time-range queries per sensor
    __table_args__ = (
        Index("ix_historian_sensor_time", "sensor_id", "timestamp"),
    )


class ProfinetDiagnostic(Base):
    """PROFINET diagnostic log entry."""

    __tablename__ = "profinet_diagnostics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_id = Column(Integer, ForeignKey("rtus.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    level = Column(String(16), nullable=False, default=DiagnosticLevel.INFO)
    source = Column(String(32), nullable=False)  # AR, CYCLE, IO, etc.
    message = Column(String(256), nullable=False)
    details = Column(JSON, nullable=True)

    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_profinet_diag_rtu_time", "rtu_id", "timestamp"),
        Index("ix_profinet_diag_level", "level"),
    )


class SlotConfig(Base):
    """Slot configuration for RTU I/O modules."""

    __tablename__ = "slot_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_station = Column(String(32), nullable=False, index=True)
    slot = Column(Integer, nullable=False)
    subslot = Column(Integer, default=1)
    slot_type = Column(String(16), nullable=False)  # AI, AO, DI, DO
    name = Column(String(64), nullable=True)
    unit = Column(String(16), nullable=True)
    measurement_type = Column(String(32), nullable=True)  # level, flow, temp, pressure
    actuator_type = Column(String(32), nullable=True)  # pump, valve, vfd

    # Scaling
    scale_min = Column(Float, default=0)
    scale_max = Column(Float, default=100)

    # Alarm setpoints
    alarm_low = Column(Float, nullable=True)
    alarm_high = Column(Float, nullable=True)
    alarm_low_low = Column(Float, nullable=True)
    alarm_high_high = Column(Float, nullable=True)
    warning_low = Column(Float, nullable=True)
    warning_high = Column(Float, nullable=True)
    deadband = Column(Float, default=0)

    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("rtu_station", "slot", name="uix_slot_config_rtu_slot"),
    )


class HistorianTag(Base):
    """Historian tag configuration for data trending."""

    __tablename__ = "historian_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_station = Column(String(32), nullable=False, index=True)
    slot = Column(Integer, nullable=False)
    tag_name = Column(String(64), unique=True, nullable=False, index=True)
    unit = Column(String(16), nullable=True)
    sample_rate_ms = Column(Integer, default=1000)
    deadband = Column(Float, default=0.1)
    compression = Column(String(16), default="swinging_door")  # swinging_door, none
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("rtu_station", "slot", name="uix_historian_tag_rtu_slot"),
    )
