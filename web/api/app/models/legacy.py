"""
Water Treatment Controller - Legacy Persistence Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

╔══════════════════════════════════════════════════════════════════════════════╗
║  DEPRECATED - SCHEDULED FOR REMOVAL                                          ║
║                                                                              ║
║  Migration Status: COMPLETE                                                  ║
║  - Persistence layer migrated to use RTU, Sensor, Control from models/rtu.py║
║  - No active code imports from this file                                     ║
║  - Legacy tables (rtu_devices, rtu_sensors, rtu_controls) no longer used    ║
║                                                                              ║
║  This file is retained only for reference. Delete after database migration  ║
║  removes the legacy tables.                                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

Legacy Table Names (for migration reference):
- rtu_devices   → rtus
- rtu_sensors   → sensors
- rtu_controls  → controls
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from .base import Base


class RtuDevice(Base):
    """Legacy RTU device configuration (persistence layer compatible)."""

    __tablename__ = "rtu_devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_name = Column(String(32), unique=True, nullable=False, index=True)
    ip_address = Column(String(45), nullable=False)
    vendor_id = Column(Integer, default=1171)
    device_id = Column(Integer, default=1)
    slot_count = Column(Integer, default=16)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )


class RtuSensor(Base):
    """Legacy RTU sensor inventory (persistence layer compatible)."""

    __tablename__ = "rtu_sensors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_station = Column(String(32), nullable=False, index=True)
    sensor_id = Column(String(32), nullable=False)
    sensor_type = Column(String(32), nullable=False)
    name = Column(String(64), nullable=False)
    unit = Column(String(16), nullable=True)
    register_address = Column(Integer, nullable=True)
    data_type = Column(String(16), default="FLOAT32")
    scale_min = Column(Float, default=0)
    scale_max = Column(Float, default=100)
    last_value = Column(Float, nullable=True)
    last_quality = Column(Integer, default=0)
    last_update = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("rtu_station", "sensor_id", name="uix_rtu_sensor"),
    )


class RtuControl(Base):
    """Legacy RTU control inventory (persistence layer compatible)."""

    __tablename__ = "rtu_controls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_station = Column(String(32), nullable=False, index=True)
    control_id = Column(String(32), nullable=False)
    control_type = Column(String(32), nullable=False)
    name = Column(String(64), nullable=False)
    command_type = Column(String(16), default="on_off")
    register_address = Column(Integer, nullable=True)
    feedback_register = Column(Integer, nullable=True)
    range_min = Column(Float, nullable=True)
    range_max = Column(Float, nullable=True)
    unit = Column(String(16), nullable=True)
    last_state = Column(String(32), nullable=True)
    last_update = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("rtu_station", "control_id", name="uix_rtu_control"),
    )


