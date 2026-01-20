"""
Water Treatment Controller - Configuration Template Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pydantic models for RTU configuration templates.

Architecture Decision (2026-01): Slots are NOT database entities.
SlotTemplate class removed - slots are PROFINET frame positions.
See CLAUDE.md "Slots Architecture Decision" for rationale.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class SensorTemplate(BaseModel):
    """Sensor configuration template."""

    tag: str = Field(description="Sensor tag name")
    slot_number: int = Field(description="Slot number")
    channel: int = Field(ge=0, description="Channel on slot")
    sensor_type: str = Field(description="Sensor type (level, pressure, flow, etc.)")
    unit: str = Field(description="Engineering unit")
    scale_min: float = Field(0.0, description="Raw value minimum")
    scale_max: float = Field(4095.0, description="Raw value maximum")
    eng_min: float = Field(0.0, description="Engineering minimum")
    eng_max: float = Field(100.0, description="Engineering maximum")


class ControlTemplate(BaseModel):
    """Control configuration template."""

    tag: str = Field(description="Control tag name")
    slot_number: int = Field(description="Slot number")
    channel: int = Field(ge=0, description="Channel on slot")
    control_type: str = Field(description="Control type (discrete, analog, pwm)")
    equipment_type: str = Field(description="Equipment type (pump, valve, motor)")
    min_value: float | None = Field(None, description="Minimum output")
    max_value: float | None = Field(None, description="Maximum output")


class AlarmTemplate(BaseModel):
    """Alarm rule template."""

    name: str = Field(description="Alarm name")
    slot: int = Field(description="Slot to monitor")
    condition: str = Field(description="Condition operator (>, <, >=, <=, ==)")
    threshold: float = Field(description="Alarm threshold value")
    severity: str = Field("MEDIUM", description="Alarm severity (LOW, MEDIUM, HIGH, CRITICAL)")
    delay_ms: int = Field(0, description="Delay before activation in milliseconds")
    message: str | None = Field(None, description="Alarm message")


class PidTemplate(BaseModel):
    """PID loop template."""

    name: str = Field(description="Loop name")
    input_rtu: str = Field(description="Input RTU station name")
    input_slot: int = Field(description="Input slot number (PV source)")
    output_rtu: str = Field(description="Output RTU station name")
    output_slot: int = Field(description="Output slot number (CV target)")
    kp: float = Field(1.0, ge=0, description="Proportional gain")
    ki: float = Field(0.0, ge=0, description="Integral gain")
    kd: float = Field(0.0, ge=0, description="Derivative gain")
    setpoint: float = Field(0, description="Default setpoint")
    output_min: float = Field(0.0, description="Minimum output")
    output_max: float = Field(100.0, description="Maximum output")


class TemplateCreate(BaseModel):
    """Request to create a configuration template."""

    name: str = Field(min_length=1, max_length=64, description="Template name")
    description: str | None = Field(None, max_length=256, description="Description")
    category: str = Field("general", description="Template category")
    vendor_id: int | None = Field(None, description="Target vendor ID")
    device_id: int | None = Field(None, description="Target device ID")
    slot_count: int = Field(16, ge=1, le=32, description="Number of PROFINET slots (metadata)")
    sensors: list[SensorTemplate] = Field(default_factory=list, description="Sensor configs")
    controls: list[ControlTemplate] = Field(default_factory=list, description="Control configs")
    alarms: list[AlarmTemplate] = Field(default_factory=list, description="Alarm rules")
    pid_loops: list[PidTemplate] = Field(default_factory=list, description="PID loops")


class TemplateResponse(BaseModel):
    """Configuration template response."""

    id: int = Field(description="Template ID")
    name: str = Field(description="Template name")
    description: str | None = Field(None, description="Description")
    category: str = Field(description="Template category")
    vendor_id: int | str | None = Field(None, description="Target vendor ID")
    device_id: int | str | None = Field(None, description="Target device ID")
    slot_count: int = Field(description="Number of PROFINET slots (metadata)")
    sensors: list[SensorTemplate] = Field(description="Sensor configs")
    controls: list[ControlTemplate] = Field(description="Control configs")
    alarms: list[AlarmTemplate] = Field(description="Alarm rules")
    pid_loops: list[PidTemplate] = Field(description="PID loops")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class ApplyTemplateRequest(BaseModel):
    """Request to apply template to an RTU."""

    template_id: int = Field(description="Template ID to apply")
    overwrite: bool = Field(False, description="Overwrite existing configuration")
