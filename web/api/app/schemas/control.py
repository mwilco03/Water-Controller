"""
Water Treatment Controller - Control/Actuator Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pydantic models for control/actuator endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .common import DataQuality


class ControlType(str, Enum):
    """Control output types."""

    DISCRETE = "discrete"  # On/Off binary output
    ANALOG = "analog"  # Variable output (0-100%, frequency, etc.)


class ControlConfig(BaseModel):
    """Control configuration within a slot."""

    channel: int = Field(description="Channel index in module")
    tag: str = Field(min_length=1, max_length=32, description="Control tag name")
    type: str = Field(description="Equipment type (pump, valve, vfd, etc.)")
    control_type: ControlType = Field(description="Control output type")


class ControlState(BaseModel):
    """Current control/actuator state."""

    tag: str = Field(description="Control tag name")
    type: str = Field(description="Equipment type")
    control_type: ControlType = Field(description="Control output type")

    # For discrete controls
    state: Optional[str] = Field(None, description="Current state (ON, OFF, etc.)")
    commanded_state: Optional[str] = Field(None, description="Last commanded state")

    # For analog controls
    value: Optional[float] = Field(None, description="Current output value")
    commanded_value: Optional[float] = Field(None, description="Last commanded value")
    unit: Optional[str] = Field(None, description="Output unit")
    min_value: Optional[float] = Field(None, description="Minimum allowed value")
    max_value: Optional[float] = Field(None, description="Maximum allowed value")

    quality: DataQuality = Field(description="Data quality indicator")
    timestamp: datetime = Field(description="State timestamp")
    interlock_active: bool = Field(False, description="Whether interlock is active")
    available_commands: List[str] = Field(
        default_factory=list,
        description="Commands available from current state"
    )


class DiscreteCommand(BaseModel):
    """Command for discrete control."""

    command: str = Field(description="Command (ON, OFF, START, STOP)")


class AnalogCommand(BaseModel):
    """Command for analog control."""

    value: float = Field(description="Setpoint value")
    ramp_seconds: Optional[float] = Field(None, ge=0, description="Ramp time in seconds")


class ControlCommand(BaseModel):
    """Generic control command (either discrete or analog)."""

    # For discrete controls
    command: Optional[str] = Field(None, description="Discrete command")

    # For analog controls
    value: Optional[float] = Field(None, description="Analog setpoint")
    ramp_seconds: Optional[float] = Field(None, ge=0, description="Ramp time")


class CoupledAction(BaseModel):
    """Action coupled to a command (e.g., VFD ramp on pump start)."""

    delay_ms: int = Field(description="Delay before action in ms")
    target: str = Field(description="Target control tag")
    action: str = Field(description="Action description")
    type: str = Field(description="Action type (automatic, manual)")


class CommandResponse(BaseModel):
    """Response for control command."""

    tag: str = Field(description="Control tag name")
    command: Optional[str] = Field(None, description="Command issued (discrete)")
    value: Optional[float] = Field(None, description="Value set (analog)")
    accepted: bool = Field(description="Whether command was accepted")
    previous_state: Optional[str] = Field(None, description="State before command")
    new_state: Optional[str] = Field(None, description="State after command")
    timestamp: datetime = Field(description="Command timestamp")
    coupled_actions: List[CoupledAction] = Field(
        default_factory=list,
        description="Coupled actions triggered"
    )


class ControlListMeta(BaseModel):
    """Metadata for control list response."""

    rtu_state: str = Field(description="RTU connection state")
    last_io_update: Optional[datetime] = Field(None, description="Last I/O cycle timestamp")


class ControlListResponse(BaseModel):
    """Response wrapper for control list."""

    data: List[ControlState]
    meta: ControlListMeta
