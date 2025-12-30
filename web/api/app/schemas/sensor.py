"""
Water Treatment Controller - Sensor Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pydantic models for sensor-related endpoints.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from .common import DataQuality


class SensorConfig(BaseModel):
    """Sensor configuration within a slot."""

    channel: int = Field(description="Channel index in module")
    tag: str = Field(min_length=1, max_length=32, description="Sensor tag name")
    type: str = Field(description="Sensor type (level, flow, temp, pressure, etc.)")
    unit: str | None = Field(None, description="Engineering unit")
    scale_min: float = Field(0.0, description="Raw value at min")
    scale_max: float = Field(100.0, description="Raw value at max")
    eng_min: float = Field(0.0, description="Engineering value at min")
    eng_max: float = Field(100.0, description="Engineering value at max")


class SensorValue(BaseModel):
    """Current sensor reading with quality."""

    tag: str = Field(description="Sensor tag name")
    value: float | None = Field(None, description="Engineering value")
    unit: str | None = Field(None, description="Engineering unit")
    quality: DataQuality = Field(description="Data quality indicator")
    quality_reason: str | None = Field(None, description="Reason for degraded quality")
    timestamp: datetime = Field(description="Reading timestamp")
    raw_value: int | None = Field(None, description="Raw ADC/register value")


class SensorListMeta(BaseModel):
    """Metadata for sensor list response."""

    rtu_state: str = Field(description="RTU connection state")
    last_io_update: datetime | None = Field(None, description="Last I/O cycle timestamp")


class SensorListResponse(BaseModel):
    """Response wrapper for sensor list."""

    data: list[SensorValue]
    meta: SensorListMeta
