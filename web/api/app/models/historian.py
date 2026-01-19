"""
Water Treatment Controller - Historian Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for historian data and PROFINET diagnostics.

Architecture Decision (2026-01): SlotConfig model removed.
Slots are PROFINET frame positions, not database entities. The `slot` field
on HistorianTag is an integer indicating the PROFINET slot position.
See CLAUDE.md "Slots Architecture Decision" for rationale.
"""

from datetime import UTC, datetime

from sqlalchemy import (
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
