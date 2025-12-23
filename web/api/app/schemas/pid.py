"""
Water Treatment Controller - PID Loop Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pydantic models for PID loop management.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class PidMode(str, Enum):
    """PID loop operating modes."""

    MANUAL = "MANUAL"
    AUTO = "AUTO"
    CASCADE = "CASCADE"


class PidLoopCreate(BaseModel):
    """Request to create a PID loop."""

    name: str = Field(min_length=1, max_length=64, description="Loop name")
    process_variable: str = Field(description="Sensor tag for PV")
    control_output: str = Field(description="Control tag for CV")
    setpoint: float = Field(description="Setpoint value")
    kp: float = Field(ge=0, description="Proportional gain")
    ki: float = Field(ge=0, description="Integral gain")
    kd: float = Field(ge=0, description="Derivative gain")
    output_min: float = Field(0.0, description="Minimum output value")
    output_max: float = Field(100.0, description="Maximum output value")
    mode: PidMode = Field(PidMode.AUTO, description="Operating mode")
    enabled: bool = Field(True, description="Whether loop is enabled")


class PidLoopUpdate(BaseModel):
    """Request to update a PID loop."""

    name: Optional[str] = Field(None, description="Loop name")
    setpoint: Optional[float] = Field(None, description="Setpoint value")
    kp: Optional[float] = Field(None, ge=0, description="Proportional gain")
    ki: Optional[float] = Field(None, ge=0, description="Integral gain")
    kd: Optional[float] = Field(None, ge=0, description="Derivative gain")
    output_min: Optional[float] = Field(None, description="Minimum output")
    output_max: Optional[float] = Field(None, description="Maximum output")
    mode: Optional[PidMode] = Field(None, description="Operating mode")
    enabled: Optional[bool] = Field(None, description="Whether enabled")


class PidLoopResponse(BaseModel):
    """PID loop response."""

    id: int = Field(description="Loop ID")
    name: str = Field(description="Loop name")
    process_variable: str = Field(description="PV sensor tag")
    control_output: str = Field(description="CV control tag")
    setpoint: float = Field(description="Current setpoint")
    kp: float = Field(description="Proportional gain")
    ki: float = Field(description="Integral gain")
    kd: float = Field(description="Derivative gain")
    output_min: float = Field(description="Minimum output")
    output_max: float = Field(description="Maximum output")
    mode: PidMode = Field(description="Operating mode")
    enabled: bool = Field(description="Whether enabled")
    pv: Optional[float] = Field(None, description="Current PV value")
    cv: Optional[float] = Field(None, description="Current CV value")
    error: Optional[float] = Field(None, description="Current error")


class SetpointRequest(BaseModel):
    """Request to change setpoint."""

    setpoint: float = Field(description="New setpoint value")


class TuningRequest(BaseModel):
    """Request to change tuning parameters."""

    kp: float = Field(ge=0, description="Proportional gain")
    ki: float = Field(ge=0, description="Integral gain")
    kd: float = Field(ge=0, description="Derivative gain")


class ModeRequest(BaseModel):
    """Request to change operating mode."""

    mode: PidMode = Field(description="New operating mode")


class AutoTuneRequest(BaseModel):
    """Request to auto-tune a PID loop."""

    method: str = Field("ziegler-nichols", description="Tuning method")
    step_size: float = Field(10.0, description="Step size for step test")
    settle_time: float = Field(300.0, description="Settle time in seconds")
