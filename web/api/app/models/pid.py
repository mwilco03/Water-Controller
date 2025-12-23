"""
Water Treatment Controller - PID Loop Model
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy model for PID loop configuration.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship

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
    rtu_id = Column(Integer, ForeignKey("rtus.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(64), nullable=False)
    enabled = Column(Boolean, default=True)

    # Process variable (input)
    pv_sensor_tag = Column(String(32), nullable=False)

    # Control variable (output)
    cv_control_tag = Column(String(32), nullable=False)

    # Tuning parameters
    kp = Column(Float, nullable=False, default=1.0)
    ki = Column(Float, nullable=False, default=0.0)
    kd = Column(Float, nullable=False, default=0.0)

    # Setpoint and limits
    setpoint = Column(Float, nullable=False, default=0.0)
    output_min = Column(Float, nullable=False, default=0.0)
    output_max = Column(Float, nullable=False, default=100.0)

    # Operating mode
    mode = Column(String(16), nullable=False, default=PidMode.AUTO)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationship
    rtu = relationship("RTU")
