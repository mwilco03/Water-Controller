"""
Water Treatment Controller - Database Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for the Water Controller database.

Architecture Decision (2026-01): Slots are NOT database entities.
See CLAUDE.md "Slots Architecture Decision" for rationale.
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
from .historian import HistorianSample, HistorianTag, ProfinetDiagnostic
from .pid import PidLoop, PidMode
# Note: Slot model removed - slots are PROFINET frame positions, not database entities
from .rtu import RTU, Control, Sensor
from .template import ConfigTemplate
from .user import AuditLog, User, UserSession

__all__ = [
    # Base
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    # RTU (no Slot - see architecture decision)
    "RTU",
    "Control",
    "Sensor",
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
    # PID
    "PidLoop",
    "PidMode",
    # User
    "User",
    "UserSession",
]
