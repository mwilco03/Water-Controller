"""
Water Treatment Controller - Configuration Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for system configuration: Modbus, log forwarding, AD, backups.
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
)

from .base import Base


# ============== Modbus Configuration ==============


class ModbusServerConfig(Base):
    """Modbus server configuration (singleton - id=1)."""

    __tablename__ = "modbus_server_config"

    id = Column(Integer, primary_key=True, default=1)

    # TCP settings
    tcp_enabled = Column(Boolean, default=True)
    tcp_port = Column(Integer, default=502)
    tcp_bind_address = Column(String(45), default="0.0.0.0")

    # RTU/Serial settings
    rtu_enabled = Column(Boolean, default=False)
    rtu_device = Column(String(64), default="/dev/ttyUSB0")
    rtu_baud_rate = Column(Integer, default=9600)
    rtu_parity = Column(String(1), default="N")
    rtu_data_bits = Column(Integer, default=8)
    rtu_stop_bits = Column(Integer, default=1)
    rtu_slave_addr = Column(Integer, default=1)

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )


class ModbusDownstreamDevice(Base):
    """Downstream Modbus device configuration."""

    __tablename__ = "modbus_downstream_devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    transport = Column(String(16), nullable=False)  # tcp, rtu

    # TCP settings
    tcp_host = Column(String(64), nullable=True)
    tcp_port = Column(Integer, default=502)

    # RTU/Serial settings
    rtu_device = Column(String(64), nullable=True)
    rtu_baud_rate = Column(Integer, default=9600)

    # Common settings
    slave_addr = Column(Integer, nullable=False)
    poll_interval_ms = Column(Integer, default=1000)
    timeout_ms = Column(Integer, default=1000)
    enabled = Column(Boolean, default=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )


class ModbusRegisterMapping(Base):
    """Modbus register to RTU slot mapping."""

    __tablename__ = "modbus_register_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    modbus_addr = Column(Integer, nullable=False)
    register_type = Column(String(16), nullable=False)  # holding, input, coil, discrete
    data_type = Column(String(16), nullable=False)  # uint16, int16, float32, etc.
    source_type = Column(String(16), nullable=False)  # sensor, control
    rtu_station = Column(String(32), nullable=False)
    slot = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)

    # Scaling configuration
    scaling_enabled = Column(Boolean, default=False)
    scale_raw_min = Column(Float, default=0)
    scale_raw_max = Column(Float, default=65535)
    scale_eng_min = Column(Float, default=0)
    scale_eng_max = Column(Float, default=100)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("uix_modbus_addr_type", "modbus_addr", "register_type", unique=True),
    )


# ============== Log Forwarding Configuration ==============


class LogForwardingConfig(Base):
    """Log forwarding configuration (singleton - id=1)."""

    __tablename__ = "log_forwarding_config"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, default=False)
    forward_type = Column(String(16), default="syslog")  # syslog, splunk, elastic
    host = Column(String(128), default="localhost")
    port = Column(Integer, default=514)
    protocol = Column(String(8), default="udp")  # udp, tcp

    # Optional for Splunk/Elastic
    index_name = Column(String(64), nullable=True)
    api_key = Column(String(256), nullable=True)

    # TLS settings
    tls_enabled = Column(Boolean, default=False)
    tls_verify = Column(Boolean, default=True)

    # What to forward
    include_alarms = Column(Boolean, default=True)
    include_events = Column(Boolean, default=True)
    include_audit = Column(Boolean, default=True)
    log_level = Column(String(8), default="INFO")

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )


# ============== Active Directory Configuration ==============


class ADConfig(Base):
    """Active Directory/LDAP configuration (singleton - id=1)."""

    __tablename__ = "ad_config"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, default=False)
    server = Column(String(128), default="")
    port = Column(Integer, default=389)
    use_ssl = Column(Boolean, default=False)
    base_dn = Column(String(256), default="")
    admin_group = Column(String(64), default="WTC-Admins")
    bind_user = Column(String(128), nullable=True)
    bind_password = Column(String(256), nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )


# ============== Backup Metadata ==============


class Backup(Base):
    """Backup file metadata."""

    __tablename__ = "backups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    backup_id = Column(String(64), unique=True, nullable=False, index=True)
    filename = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    size_bytes = Column(Integer, default=0)
    includes_historian = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
