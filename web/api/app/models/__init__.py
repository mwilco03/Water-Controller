"""
Water Treatment Controller - Database Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for the Water Controller database.
"""

from .alarm import AlarmEvent, AlarmRule
from .audit import CommandAudit
from .base import Base, SessionLocal, engine, get_db
from .historian import HistorianSample, ProfinetDiagnostic
from .pid import PidLoop, PidMode
from .rtu import RTU, Control, Sensor, Slot
from .template import ConfigTemplate

__all__ = [
    "RTU",
    "AlarmEvent",
    "AlarmRule",
    "Base",
    "CommandAudit",
    "ConfigTemplate",
    "Control",
    "HistorianSample",
    "PidLoop",
    "PidMode",
    "ProfinetDiagnostic",
    "Sensor",
    "SessionLocal",
    "Slot",
    "engine",
    "get_db",
]
