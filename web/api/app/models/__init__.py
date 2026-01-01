"""
Water Treatment Controller - Database Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for the Water Controller database.
"""

from .alarm import AlarmEvent, AlarmRule, ShelvedAlarm
from .audit import CommandAudit, CommandLog
from .base import Base, SessionLocal, engine, get_db
from .config import (
    ADConfig,
    Backup,
    LogForwardingConfig,
    ModbusDownstreamDevice,
    ModbusRegisterMapping,
    ModbusServerConfig,
)
from .discovery import DCPDiscoveryCache
from .historian import HistorianSample, HistorianTag, ProfinetDiagnostic, SlotConfig
from .legacy import RtuControl, RtuDevice, RtuSensor
from .pid import PidLoop, PidMode
from .rtu import RTU, Control, Sensor, Slot
from .template import ConfigTemplate
from .user import AuditLog, User, UserSession

__all__ = [
    # Base
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    # RTU
    "RTU",
    "Control",
    "Sensor",
    "Slot",
    # Alarms
    "AlarmEvent",
    "AlarmRule",
    "ShelvedAlarm",
    # Audit
    "AuditLog",
    "CommandAudit",
    "CommandLog",
    # Config
    "ADConfig",
    "Backup",
    "ConfigTemplate",
    "LogForwardingConfig",
    "ModbusDownstreamDevice",
    "ModbusRegisterMapping",
    "ModbusServerConfig",
    # Discovery
    "DCPDiscoveryCache",
    # Historian
    "HistorianSample",
    "HistorianTag",
    "ProfinetDiagnostic",
    "SlotConfig",
    # PID
    "PidLoop",
    "PidMode",
    # User
    "User",
    "UserSession",
    # Legacy (persistence layer compatible)
    "RtuControl",
    "RtuDevice",
    "RtuSensor",
]
