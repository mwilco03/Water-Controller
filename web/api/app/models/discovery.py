"""
Water Treatment Controller - Discovery Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for PROFINET DCP device discovery.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
)

from .base import Base


class DCPDiscoveryCache(Base):
    """Cached results from PROFINET DCP discovery."""

    __tablename__ = "dcp_discovery_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mac_address = Column(String(17), unique=True, nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)
    device_name = Column(String(64), nullable=True)
    vendor_name = Column(String(64), nullable=True)
    device_type = Column(String(64), nullable=True)
    profinet_device_id = Column(Integer, nullable=True)
    profinet_vendor_id = Column(Integer, nullable=True)

    first_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    added_as_rtu = Column(Boolean, default=False)
