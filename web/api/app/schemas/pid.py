"""
Water Treatment Controller - PID Loop Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pydantic models for PID loop management.
"""

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class PidMode(str, Enum):
    """PID loop operating modes."""

    MANUAL = "MANUAL"
    AUTO = "AUTO"
    CASCADE = "CASCADE"


# PID coefficient limits - prevent unstable or unreasonable values
PID_KP_MAX = 1000.0  # Max proportional gain
PID_KI_MAX = 100.0   # Max integral gain
PID_KD_MAX = 100.0   # Max derivative gain


class PidLoopCreate(BaseModel):
    """Request to create a PID loop."""

    name: str = Field(min_length=1, max_length=64, description="Loop name")
    process_variable: str = Field(description="Sensor tag for PV")
    control_output: str = Field(description="Control tag for CV")
    setpoint: float = Field(description="Setpoint value")
    kp: float = Field(ge=0, le=PID_KP_MAX, description="Proportional gain (0-1000)")
    ki: float = Field(ge=0, le=PID_KI_MAX, description="Integral gain (0-100)")
    kd: float = Field(ge=0, le=PID_KD_MAX, description="Derivative gain (0-100)")
    output_min: float = Field(0.0, description="Minimum output value")
    output_max: float = Field(100.0, description="Maximum output value")
    mode: PidMode = Field(PidMode.AUTO, description="Operating mode")
    enabled: bool = Field(True, description="Whether loop is enabled")

    @model_validator(mode="after")
    def validate_output_range(self):
        """Ensure output_min < output_max."""
        if self.output_min >= self.output_max:
            raise ValueError(f"output_min ({self.output_min}) must be less than output_max ({self.output_max})")
        return self


class PidLoopUpdate(BaseModel):
    """Request to update a PID loop."""

    name: str | None = Field(None, description="Loop name")
    setpoint: float | None = Field(None, description="Setpoint value")
    kp: float | None = Field(None, ge=0, le=PID_KP_MAX, description="Proportional gain (0-1000)")
    ki: float | None = Field(None, ge=0, le=PID_KI_MAX, description="Integral gain (0-100)")
    kd: float | None = Field(None, ge=0, le=PID_KD_MAX, description="Derivative gain (0-100)")
    output_min: float | None = Field(None, description="Minimum output")
    output_max: float | None = Field(None, description="Maximum output")
    mode: PidMode | None = Field(None, description="Operating mode")
    enabled: bool | None = Field(None, description="Whether enabled")

    @model_validator(mode="after")
    def validate_output_range(self):
        """Ensure output_min < output_max when both are provided."""
        if self.output_min is not None and self.output_max is not None:
            if self.output_min >= self.output_max:
                raise ValueError(f"output_min ({self.output_min}) must be less than output_max ({self.output_max})")
        return self


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
    pv: float | None = Field(None, description="Current PV value")
    cv: float | None = Field(None, description="Current CV value")
    error: float | None = Field(None, description="Current error")


class SetpointRequest(BaseModel):
    """Request to change setpoint."""

    setpoint: float = Field(description="New setpoint value")


class TuningRequest(BaseModel):
    """Request to change tuning parameters."""

    kp: float = Field(ge=0, le=PID_KP_MAX, description="Proportional gain (0-1000)")
    ki: float = Field(ge=0, le=PID_KI_MAX, description="Integral gain (0-100)")
    kd: float = Field(ge=0, le=PID_KD_MAX, description="Derivative gain (0-100)")


class ModeRequest(BaseModel):
    """Request to change operating mode."""

    mode: PidMode = Field(description="New operating mode")


class AutoTuneRequest(BaseModel):
    """Request to auto-tune a PID loop."""

    method: str = Field("ziegler-nichols", description="Tuning method")
    step_size: float = Field(10.0, ge=1.0, le=50.0, description="Step size for step test")
    settle_time: float = Field(300.0, ge=60.0, le=1800.0, description="Settle time in seconds")


class AutoTuneResponse(BaseModel):
    """Response from auto-tune operation."""

    loop_id: int = Field(description="PID loop ID")
    method: str = Field(description="Tuning method used")
    status: str = Field(description="Tuning status: pending, running, completed, failed")
    old_tuning: dict | None = Field(None, description="Previous tuning parameters")
    new_tuning: dict | None = Field(None, description="Calculated tuning parameters")
    metrics: dict | None = Field(None, description="Process metrics from step test")
    message: str | None = Field(None, description="Status message")
