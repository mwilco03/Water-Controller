"""
Water Treatment Controller - User Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for user management and authentication.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)

from .base import Base


class UserRole:
    """User role constants."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class User(Base):
    """User account for authentication."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(16), nullable=False, default=UserRole.VIEWER)
    active = Column(Boolean, default=True)
    sync_to_rtus = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )
    last_login = Column(DateTime(timezone=True), nullable=True)


class UserSession(Base):
    """Active user session."""

    __tablename__ = "user_sessions"

    token = Column(String(256), primary_key=True)
    username = Column(String(64), nullable=False, index=True)
    role = Column(String(16), nullable=False, default=UserRole.VIEWER)
    groups = Column(Text, nullable=True)  # JSON-encoded list

    # Session metadata
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_activity = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(String(256), nullable=True)

    # Indexes for efficient session management
    __table_args__ = (
        Index("ix_user_sessions_expires", "expires_at"),
        Index("ix_user_sessions_username", "username"),
    )


class AuditLog(Base):
    """System audit log for compliance and debugging."""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    user = Column(String(64), nullable=True)
    action = Column(String(32), nullable=False)
    resource_type = Column(String(32), nullable=True)
    resource_id = Column(String(64), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)

    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_audit_log_user", "user"),
        Index("ix_audit_log_action", "action"),
        Index("ix_audit_log_resource", "resource_type", "resource_id"),
    )
