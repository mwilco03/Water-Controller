"""
Water Treatment Controller - Configuration Template Model
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy model for RTU configuration templates.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.sqlite import JSON

from .base import Base


class ConfigTemplate(Base):
    """RTU configuration template."""

    __tablename__ = "config_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    description = Column(String(256), nullable=True)
    category = Column(String(32), nullable=False, default="general")

    # Target device specifications
    vendor_id = Column(Integer, nullable=True)
    device_id = Column(Integer, nullable=True)
    slot_count = Column(Integer, nullable=False, default=16)

    # Configuration data stored as JSON
    config_data = Column(JSON, nullable=False, default=dict)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
