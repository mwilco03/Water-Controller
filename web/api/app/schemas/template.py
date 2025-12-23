"""
Water Treatment Controller - Configuration Template Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pydantic models for RTU configuration templates.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SlotTemplate(BaseModel):
    """Slot configuration template."""

    slot_number: int = Field(ge=0, le=31, description="Slot number")
    module_type: str = Field(description="Module type (analog_input, digital_output, etc.)")
    module_id: Optional[str] = Field(None, description="Module identifier")


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
    min_value: Optional[float] = Field(None, description="Minimum output")
    max_value: Optional[float] = Field(None, description="Maximum output")


class AlarmTemplate(BaseModel):
    """Alarm rule template."""

    tag: str = Field(description="Tag to monitor")
    alarm_type: str = Field(description="Alarm type (HIGH, LOW, RATE, etc.)")
    priority: str = Field("MEDIUM", description="Alarm priority")
    setpoint: float = Field(description="Alarm threshold")
    deadband: float = Field(0.0, description="Deadband for hysteresis")
    message_template: str = Field(description="Alarm message template")


class PidTemplate(BaseModel):
    """PID loop template."""

    name: str = Field(description="Loop name")
    pv_sensor_tag: str = Field(description="Process variable sensor tag")
    cv_control_tag: str = Field(description="Control variable tag")
    kp: float = Field(1.0, ge=0, description="Proportional gain")
    ki: float = Field(0.0, ge=0, description="Integral gain")
    kd: float = Field(0.0, ge=0, description="Derivative gain")
    setpoint: float = Field(description="Default setpoint")
    output_min: float = Field(0.0, description="Minimum output")
    output_max: float = Field(100.0, description="Maximum output")


class TemplateCreate(BaseModel):
    """Request to create a configuration template."""

    name: str = Field(min_length=1, max_length=64, description="Template name")
    description: Optional[str] = Field(None, max_length=256, description="Description")
    category: str = Field("general", description="Template category")
    vendor_id: Optional[int] = Field(None, description="Target vendor ID")
    device_id: Optional[int] = Field(None, description="Target device ID")
    slot_count: int = Field(16, ge=1, le=32, description="Number of slots")
    slots: List[SlotTemplate] = Field(default_factory=list, description="Slot configs")
    sensors: List[SensorTemplate] = Field(default_factory=list, description="Sensor configs")
    controls: List[ControlTemplate] = Field(default_factory=list, description="Control configs")
    alarms: List[AlarmTemplate] = Field(default_factory=list, description="Alarm rules")
    pid_loops: List[PidTemplate] = Field(default_factory=list, description="PID loops")


class TemplateResponse(BaseModel):
    """Configuration template response."""

    id: int = Field(description="Template ID")
    name: str = Field(description="Template name")
    description: Optional[str] = Field(None, description="Description")
    category: str = Field(description="Template category")
    vendor_id: Optional[int] = Field(None, description="Target vendor ID")
    device_id: Optional[int] = Field(None, description="Target device ID")
    slot_count: int = Field(description="Number of slots")
    slots: List[SlotTemplate] = Field(description="Slot configs")
    sensors: List[SensorTemplate] = Field(description="Sensor configs")
    controls: List[ControlTemplate] = Field(description="Control configs")
    alarms: List[AlarmTemplate] = Field(description="Alarm rules")
    pid_loops: List[PidTemplate] = Field(description="PID loops")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class ApplyTemplateRequest(BaseModel):
    """Request to apply template to an RTU."""

    template_id: int = Field(description="Template ID to apply")
    overwrite: bool = Field(False, description="Overwrite existing configuration")
