"""
Water Treatment Controller - Slot Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pydantic models for slot configuration endpoints.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .control import ControlConfig
from .sensor import SensorConfig


class SlotStatus(str, Enum):
    """Slot status values."""

    OK = "OK"  # Module present and functioning
    EMPTY = "EMPTY"  # No module installed
    FAULT = "FAULT"  # Module fault detected
    PULLED = "PULLED"  # Module was removed
    WRONG_MODULE = "WRONG_MODULE"  # Different module than expected


class SlotSensorSummary(BaseModel):
    """Summary of sensor in slot."""

    id: int = Field(description="Sensor ID")
    tag: str = Field(description="Sensor tag")
    type: str = Field(description="Sensor type")


class SlotConfig(BaseModel):
    """Slot configuration with sensors and controls."""

    slot: int = Field(description="Slot number")
    module_id: str | None = Field(None, description="Module identifier (hex)")
    module_type: str | None = Field(None, description="Module type name")
    status: SlotStatus = Field(SlotStatus.EMPTY, description="Current status")
    configured: bool = Field(False, description="Whether slot is configured")
    sensors: list[SlotSensorSummary] = Field(
        default_factory=list,
        description="Sensors in this slot"
    )
    controls: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Controls in this slot"
    )


class SlotResponse(BaseModel):
    """Response for single slot configuration."""

    slot: int = Field(description="Slot number")
    module_type: str | None = Field(None, description="Module type")
    configured: bool = Field(description="Whether configured")
    sensors_configured: int = Field(0, description="Number of sensors")
    controls_configured: int = Field(0, description="Number of controls")


class SlotListResponse(BaseModel):
    """Response wrapper for slot list."""

    data: list[SlotConfig]


class SlotConfigUpdate(BaseModel):
    """Request to configure a slot."""

    module_type: str = Field(description="Module type identifier")
    sensors: list[SensorConfig] = Field(
        default_factory=list,
        description="Sensor configurations"
    )
    controls: list[ControlConfig] = Field(
        default_factory=list,
        description="Control configurations"
    )
