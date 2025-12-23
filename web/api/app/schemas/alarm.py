"""
Water Treatment Controller - Alarm Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pydantic models for alarm management endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AlarmPriority(str, Enum):
    """Alarm priority levels."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AlarmState(str, Enum):
    """Alarm state values."""

    ACTIVE = "ACTIVE"  # Alarm condition present, not acknowledged
    ACKNOWLEDGED = "ACKNOWLEDGED"  # Acknowledged but condition still present
    CLEARED = "CLEARED"  # Condition cleared


class AlarmType(str, Enum):
    """Alarm condition types."""

    HIGH_HIGH = "HIGH_HIGH"
    HIGH = "HIGH"
    LOW = "LOW"
    LOW_LOW = "LOW_LOW"
    RATE_OF_CHANGE = "RATE_OF_CHANGE"
    DEVIATION = "DEVIATION"
    FAULT = "FAULT"


class AlarmConfig(BaseModel):
    """Alarm rule configuration."""

    id: Optional[int] = Field(None, description="Alarm rule ID")
    rtu: str = Field(description="RTU station name")
    tag: str = Field(description="Sensor/control tag")
    priority: AlarmPriority = Field(description="Alarm priority")
    type: AlarmType = Field(description="Alarm type")
    setpoint: float = Field(description="Trigger setpoint value")
    deadband: float = Field(0.0, description="Hysteresis deadband")
    message_template: str = Field(description="Message template")
    enabled: bool = Field(True, description="Whether alarm is enabled")


class AlarmEvent(BaseModel):
    """Active or historical alarm event."""

    id: int = Field(description="Alarm event ID")
    rtu: str = Field(description="RTU station name")
    tag: str = Field(description="Sensor/control tag")
    priority: AlarmPriority = Field(description="Alarm priority")
    type: AlarmType = Field(description="Alarm type")
    message: str = Field(description="Alarm message")
    value: Optional[float] = Field(None, description="Value at activation")
    setpoint: float = Field(description="Trigger setpoint")
    unit: Optional[str] = Field(None, description="Engineering unit")
    state: AlarmState = Field(description="Current alarm state")
    activated_at: datetime = Field(description="Activation timestamp")
    acknowledged_at: Optional[datetime] = Field(None, description="Acknowledgment time")
    acknowledged_by: Optional[str] = Field(None, description="User who acknowledged")
    cleared_at: Optional[datetime] = Field(None, description="Clear timestamp")


class AlarmAcknowledgeRequest(BaseModel):
    """Request to acknowledge an alarm."""

    note: Optional[str] = Field(None, max_length=256, description="Optional operator note")


class AlarmListMeta(BaseModel):
    """Metadata for alarm list response."""

    total: int = Field(description="Total alarms matching filter")
    active: int = Field(description="Active alarm count")
    unacknowledged: int = Field(description="Unacknowledged alarm count")


class AlarmListResponse(BaseModel):
    """Response wrapper for alarm list."""

    data: List[AlarmEvent]
    meta: AlarmListMeta
