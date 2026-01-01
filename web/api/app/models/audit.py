"""
Water Treatment Controller - Audit Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for command audit trail.
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
)

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

    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
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


class CommandLog(Base):
    """Command execution log for operator actions."""

    __tablename__ = "command_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    username = Column(String(64), nullable=False, index=True)
    rtu_station = Column(String(32), nullable=False, index=True)
    control_id = Column(String(32), nullable=False)
    command = Column(String(32), nullable=False)
    command_value = Column(Float, nullable=True)
    result = Column(String(16), nullable=True)
    error_message = Column(String(256), nullable=True)
    source_ip = Column(String(45), nullable=True)
    session_token = Column(String(64), nullable=True)

    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_command_log_timestamp", "timestamp"),
        Index("ix_command_log_rtu", "rtu_station"),
    )
