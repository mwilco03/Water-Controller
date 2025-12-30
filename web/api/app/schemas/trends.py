"""
Water Treatment Controller - Trends/Historian Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pydantic models for historian/trends endpoints.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .common import DataQuality


class TrendInterval(str, Enum):
    """Data aggregation intervals."""

    ONE_SECOND = "1s"
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"


class TrendAggregate(str, Enum):
    """Aggregation functions."""

    MIN = "min"
    MAX = "max"
    AVG = "avg"
    FIRST = "first"
    LAST = "last"


class TrendPointValue(BaseModel):
    """Value with quality for a single tag at a point in time."""

    value: float | None = Field(None, description="Aggregated value")
    quality: DataQuality = Field(description="Data quality")


class TrendPoint(BaseModel):
    """Single point in trend data."""

    timestamp: datetime = Field(description="Point timestamp")
    values: dict[str, TrendPointValue] = Field(description="Values by tag")


class TrendData(BaseModel):
    """Trend data response."""

    tags: list[str] = Field(description="Tags included in data")
    interval: TrendInterval = Field(description="Aggregation interval")
    points: list[TrendPoint] = Field(description="Data points")


class TrendMeta(BaseModel):
    """Metadata for trend response."""

    point_count: int = Field(description="Number of points returned")
    start: datetime = Field(description="Actual start time")
    end: datetime = Field(description="Actual end time")


class TrendResponse(BaseModel):
    """Response wrapper for trend data."""

    data: TrendData
    meta: TrendMeta


class TrendQuery(BaseModel):
    """Query parameters for trend data."""

    tags: list[str] = Field(description="Sensor tags to retrieve")
    start: datetime = Field(description="Start time")
    end: datetime = Field(description="End time")
    interval: TrendInterval = Field(TrendInterval.ONE_MINUTE, description="Aggregation interval")
    aggregate: TrendAggregate = Field(TrendAggregate.AVG, description="Aggregation function")


class ExportFormat(str, Enum):
    """Export file formats."""

    CSV = "csv"
    PDF = "pdf"


class TrendExportRequest(BaseModel):
    """Request to export trend data."""

    format: ExportFormat = Field(description="Export file format")
    tags: list[str] = Field(description="Sensor tags to export")
    start: datetime = Field(description="Start time")
    end: datetime = Field(description="End time")
    include_metadata: bool = Field(True, description="Include tag metadata")
