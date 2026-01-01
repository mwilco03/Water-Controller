"""
Water Treatment Controller - PID Loop Model
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy model for PID loop configuration.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
)

from .base import Base


class PidMode:
    """PID mode constants."""

    MANUAL = "MANUAL"
    AUTO = "AUTO"
    CASCADE = "CASCADE"


class PidLoop(Base):
    """PID control loop configuration."""

    __tablename__ = "pid_loops"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    enabled = Column(Boolean, default=True)

    # I/O references (by RTU station and slot)
    input_rtu = Column(String(32), nullable=False)
    input_slot = Column(Integer, nullable=False)
    output_rtu = Column(String(32), nullable=False)
    output_slot = Column(Integer, nullable=False)

    # Tuning parameters
    kp = Column(Float, default=1.0)
    ki = Column(Float, default=0.0)
    kd = Column(Float, default=0.0)

    # Setpoint and limits
    setpoint = Column(Float, default=0)
    output_min = Column(Float, default=0)
    output_max = Column(Float, default=100)
    deadband = Column(Float, default=0)
    integral_limit = Column(Float, default=100)
    derivative_filter = Column(Float, default=0.1)

    # Operating mode
    mode = Column(String(16), default=PidMode.AUTO)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )
