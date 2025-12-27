"""
Water Treatment Controller - Audit Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for command audit trail.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.orm import relationship

from .base import Base


class CommandResult:
    """Command result constants."""

    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class CommandAudit(Base):
    """Audit trail for control commands."""

    __tablename__ = "command_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    control_id = Column(Integer, ForeignKey("controls.id", ondelete="SET NULL"), nullable=True)

    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    command = Column(String(32), nullable=False)
    value = Column(Float, nullable=True)  # For analog commands
    result = Column(String(16), nullable=False)
    rejection_reason = Column(String(256), nullable=True)
    user = Column(String(64), nullable=True)

    # Idempotency support for safe retries
    idempotency_key = Column(String(64), nullable=True, unique=True, index=True)

    # Additional context
    rtu_name = Column(String(32), nullable=False)
    control_tag = Column(String(32), nullable=False)
    source_ip = Column(String(45), nullable=True)  # IPv6 compatible

    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_command_audit_timestamp", "timestamp"),
        Index("ix_command_audit_user", "user"),
        Index("ix_command_audit_rtu", "rtu_name"),
    )
