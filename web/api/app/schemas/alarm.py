"""
Water Treatment Controller - Alarm Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pydantic models for alarm management endpoints.

IMPORTANT: These enums must stay in sync with:
- C definitions: shared/include/alarm_definitions.h
- Database schema: docker/init.sql
"""

from datetime import datetime
from enum import IntEnum, Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator


class AlarmSeverity(IntEnum):
    """
    Alarm severity levels (ISA-18.2 compatible).

    Values match C enum in shared/include/alarm_definitions.h:
        ALARM_SEVERITY_LOW = 0
        ALARM_SEVERITY_MEDIUM = 1
        ALARM_SEVERITY_HIGH = 2
        ALARM_SEVERITY_CRITICAL = 3
    """
    LOW = 0           # Low priority - informational
    MEDIUM = 1        # Medium priority - requires attention
    HIGH = 2          # High priority - requires prompt action
    CRITICAL = 3      # Critical - requires immediate action

    @classmethod
    def from_legacy(cls, legacy_value: int) -> "AlarmSeverity":
        """Convert legacy (1-4) severity to canonical (0-3)."""
        if legacy_value <= 0:
            return cls.LOW
        if legacy_value >= 4:
            return cls.CRITICAL
        return cls(legacy_value - 1)

    def to_legacy(self) -> int:
        """Convert to legacy (1-4) severity for backwards compatibility."""
        return self.value + 1

    def to_string(self) -> str:
        """Get string representation for API responses."""
        return self.name


# Alias for backwards compatibility
class AlarmPriority(str, Enum):
    """
    Alarm priority levels - string enum for API compatibility.
    Maps to AlarmSeverity integer values.
    """
    CRITICAL = "CRITICAL"  # Maps to AlarmSeverity.CRITICAL (3)
    HIGH = "HIGH"          # Maps to AlarmSeverity.HIGH (2)
    MEDIUM = "MEDIUM"      # Maps to AlarmSeverity.MEDIUM (1)
    LOW = "LOW"            # Maps to AlarmSeverity.LOW (0)

    @classmethod
    def from_severity(cls, severity: AlarmSeverity) -> "AlarmPriority":
        """Convert integer severity to string priority."""
        mapping = {
            AlarmSeverity.LOW: cls.LOW,
            AlarmSeverity.MEDIUM: cls.MEDIUM,
            AlarmSeverity.HIGH: cls.HIGH,
            AlarmSeverity.CRITICAL: cls.CRITICAL,
        }
        return mapping.get(severity, cls.LOW)

    def to_severity(self) -> AlarmSeverity:
        """Convert string priority to integer severity."""
        mapping = {
            self.LOW: AlarmSeverity.LOW,
            self.MEDIUM: AlarmSeverity.MEDIUM,
            self.HIGH: AlarmSeverity.HIGH,
            self.CRITICAL: AlarmSeverity.CRITICAL,
        }
        return mapping.get(self, AlarmSeverity.LOW)


class AlarmState(IntEnum):
    """
    Alarm states - ISA-18.2 four-state model.

    Values match C enum in shared/include/alarm_definitions.h:
        ALARM_STATE_CLEARED = 0
        ALARM_STATE_ACTIVE = 1
        ALARM_STATE_ACKNOWLEDGED = 2
        ALARM_STATE_CLEARED_UNACK = 3

    State Transitions:
        CLEARED -> ACTIVE (condition detected)
        ACTIVE -> ACKNOWLEDGED (operator acknowledges)
        ACKNOWLEDGED -> CLEARED_UNACK (condition clears)
        CLEARED_UNACK -> CLEARED (operator acknowledges)
        ACTIVE -> CLEARED (condition clears before ack - auto-clear disabled)
    """
    CLEARED = 0        # Condition resolved, acknowledged
    ACTIVE = 1         # Condition active, unacknowledged
    ACKNOWLEDGED = 2   # Condition active, acknowledged
    CLEARED_UNACK = 3  # Condition cleared but not acknowledged

    def is_active(self) -> bool:
        """Check if alarm condition is currently active."""
        return self in (AlarmState.ACTIVE, AlarmState.ACKNOWLEDGED)

    def needs_acknowledgment(self) -> bool:
        """Check if alarm requires operator acknowledgment."""
        return self in (AlarmState.ACTIVE, AlarmState.CLEARED_UNACK)

    def to_string(self) -> str:
        """Get string representation for API responses."""
        names = {
            self.CLEARED: "CLEARED",
            self.ACTIVE: "ACTIVE",
            self.ACKNOWLEDGED: "ACKNOWLEDGED",
            self.CLEARED_UNACK: "CLEARED_UNACK",
        }
        return names.get(self, "UNKNOWN")

    @classmethod
    def from_string(cls, s: str) -> "AlarmState":
        """Parse string representation."""
        mapping = {
            "CLEARED": cls.CLEARED,
            "ACTIVE": cls.ACTIVE,
            "ACTIVE_UNACK": cls.ACTIVE,  # Legacy alias
            "ACKNOWLEDGED": cls.ACKNOWLEDGED,
            "ACTIVE_ACK": cls.ACKNOWLEDGED,  # Legacy alias
            "CLEARED_UNACK": cls.CLEARED_UNACK,
        }
        return mapping.get(s.upper(), cls.CLEARED)


class AlarmCondition(IntEnum):
    """
    Alarm condition types - how sensor values are evaluated.

    Values match C enum in shared/include/alarm_definitions.h:
        ALARM_CONDITION_ABOVE = 0
        ALARM_CONDITION_BELOW = 1
        ALARM_CONDITION_OUT_OF_RANGE = 2
        ALARM_CONDITION_RATE_OF_CHANGE = 3
        ALARM_CONDITION_DEVIATION = 4
        ALARM_CONDITION_BAD_QUALITY = 5
    """
    ABOVE = 0          # Value > high threshold (HIGH, HIGH_HIGH)
    BELOW = 1          # Value < low threshold (LOW, LOW_LOW)
    OUT_OF_RANGE = 2   # Value outside (low, high) range
    RATE_OF_CHANGE = 3 # Rate of change exceeds limit
    DEVIATION = 4      # Deviation from setpoint exceeds limit
    BAD_QUALITY = 5    # Data quality is BAD or NOT_CONNECTED

    def to_string(self) -> str:
        """Get string representation for API responses."""
        return self.name


# String enum for API compatibility
class AlarmType(str, Enum):
    """
    Alarm condition types - string enum for API compatibility.
    Maps to AlarmCondition integer values.
    """
    HIGH_HIGH = "HIGH_HIGH"          # Maps to ABOVE with HH threshold
    HIGH = "HIGH"                     # Maps to ABOVE
    LOW = "LOW"                       # Maps to BELOW
    LOW_LOW = "LOW_LOW"              # Maps to BELOW with LL threshold
    RATE_OF_CHANGE = "RATE_OF_CHANGE"  # Maps to RATE_OF_CHANGE
    DEVIATION = "DEVIATION"          # Maps to DEVIATION
    BAD_QUALITY = "BAD_QUALITY"      # Maps to BAD_QUALITY (sensor fault)
    FAULT = "FAULT"                  # Alias for BAD_QUALITY

    @classmethod
    def from_condition(cls, condition: AlarmCondition) -> "AlarmType":
        """Convert integer condition to string type."""
        mapping = {
            AlarmCondition.ABOVE: cls.HIGH,
            AlarmCondition.BELOW: cls.LOW,
            AlarmCondition.OUT_OF_RANGE: cls.HIGH,  # Default representation
            AlarmCondition.RATE_OF_CHANGE: cls.RATE_OF_CHANGE,
            AlarmCondition.DEVIATION: cls.DEVIATION,
            AlarmCondition.BAD_QUALITY: cls.BAD_QUALITY,
        }
        return mapping.get(condition, cls.HIGH)

    def to_condition(self) -> AlarmCondition:
        """Convert string type to integer condition."""
        mapping = {
            self.HIGH_HIGH: AlarmCondition.ABOVE,
            self.HIGH: AlarmCondition.ABOVE,
            self.LOW: AlarmCondition.BELOW,
            self.LOW_LOW: AlarmCondition.BELOW,
            self.RATE_OF_CHANGE: AlarmCondition.RATE_OF_CHANGE,
            self.DEVIATION: AlarmCondition.DEVIATION,
            self.BAD_QUALITY: AlarmCondition.BAD_QUALITY,
            self.FAULT: AlarmCondition.BAD_QUALITY,
        }
        return mapping.get(self, AlarmCondition.ABOVE)


class AlarmSource(str, Enum):
    """
    Alarm source - distinguishes controller alarms from RTU interlocks.

    Controller alarms are notifications that require operator response.
    RTU interlocks are safety actions executed locally by the RTU.
    """
    CONTROLLER = "CONTROLLER"  # Generated by controller alarm manager
    RTU = "RTU"                # Status of RTU-side interlock


class AlarmConfig(BaseModel):
    """Alarm rule configuration."""

    id: Optional[int] = Field(None, description="Alarm rule ID")
    rtu: str = Field(description="RTU station name")
    tag: str = Field(description="Sensor/control tag")
    slot: Optional[int] = Field(None, description="Slot number (if tag not used)")
    priority: AlarmPriority = Field(description="Alarm priority")
    type: AlarmType = Field(description="Alarm type")
    setpoint: float = Field(description="Trigger setpoint value")
    deadband: float = Field(0.0, description="Hysteresis deadband")
    delay_ms: int = Field(0, description="Delay before alarm activates (ms)")
    message_template: str = Field(description="Message template")
    enabled: bool = Field(True, description="Whether alarm is enabled")

    @field_validator('priority', mode='before')
    @classmethod
    def validate_priority(cls, v):
        """Accept both string and integer priority values."""
        if isinstance(v, int):
            severity = AlarmSeverity(v) if 0 <= v <= 3 else AlarmSeverity.from_legacy(v)
            return AlarmPriority.from_severity(severity)
        return v


class AlarmEvent(BaseModel):
    """Active or historical alarm event."""

    id: int = Field(description="Alarm event ID")
    rtu: str = Field(description="RTU station name")
    tag: str = Field(description="Sensor/control tag")
    slot: Optional[int] = Field(None, description="Slot number")
    priority: AlarmPriority = Field(description="Alarm priority")
    severity: Optional[int] = Field(None, description="Numeric severity (0-3)")
    type: AlarmType = Field(description="Alarm type")
    message: str = Field(description="Alarm message")
    value: Optional[float] = Field(None, description="Value at activation")
    setpoint: float = Field(description="Trigger setpoint")
    unit: Optional[str] = Field(None, description="Engineering unit")
    state: str = Field(description="Current alarm state")
    state_code: Optional[int] = Field(None, description="Numeric state (0-3)")
    source: AlarmSource = Field(AlarmSource.CONTROLLER, description="Alarm source")
    activated_at: datetime = Field(description="Activation timestamp")
    acknowledged_at: Optional[datetime] = Field(None, description="Acknowledgment time")
    acknowledged_by: Optional[str] = Field(None, description="User who acknowledged")
    cleared_at: Optional[datetime] = Field(None, description="Clear timestamp")

    @field_validator('state', mode='before')
    @classmethod
    def validate_state(cls, v):
        """Accept both string and integer state values."""
        if isinstance(v, int):
            return AlarmState(v).to_string()
        return v

    @field_validator('priority', mode='before')
    @classmethod
    def validate_priority(cls, v):
        """Accept both string and integer priority values."""
        if isinstance(v, int):
            severity = AlarmSeverity(v) if 0 <= v <= 3 else AlarmSeverity.from_legacy(v)
            return AlarmPriority.from_severity(severity)
        return v


class AlarmAcknowledgeRequest(BaseModel):
    """Request to acknowledge an alarm."""

    note: Optional[str] = Field(None, max_length=256, description="Optional operator note")


class AlarmListMeta(BaseModel):
    """Metadata for alarm list response."""

    total: int = Field(description="Total alarms matching filter")
    active: int = Field(description="Active alarm count")
    unacknowledged: int = Field(description="Unacknowledged alarm count")
    cleared_unack: int = Field(0, description="Cleared but unacknowledged count")


class AlarmListResponse(BaseModel):
    """Response wrapper for alarm list."""

    data: List[AlarmEvent]
    meta: AlarmListMeta


# ============== Mapping Functions ==============

def severity_from_c(c_value: int) -> AlarmSeverity:
    """
    Convert C severity value to Python enum.

    C uses 0-3 in canonical definitions (alarm_definitions.h)
    or 1-4 in legacy code (types.h).
    """
    if c_value >= 0 and c_value <= 3:
        return AlarmSeverity(c_value)
    return AlarmSeverity.from_legacy(c_value)


def severity_to_c(severity: Union[AlarmSeverity, AlarmPriority]) -> int:
    """Convert Python severity to C value (0-3)."""
    if isinstance(severity, AlarmPriority):
        severity = severity.to_severity()
    return severity.value


def state_from_c(c_value: int) -> AlarmState:
    """Convert C alarm state to Python enum."""
    return AlarmState(c_value) if 0 <= c_value <= 3 else AlarmState.CLEARED


def state_to_c(state: AlarmState) -> int:
    """Convert Python alarm state to C value."""
    return state.value


def condition_from_c(c_value: int) -> AlarmCondition:
    """Convert C alarm condition to Python enum."""
    return AlarmCondition(c_value) if 0 <= c_value <= 5 else AlarmCondition.ABOVE


def condition_to_c(condition: AlarmCondition) -> int:
    """Convert Python alarm condition to C value."""
    return condition.value
