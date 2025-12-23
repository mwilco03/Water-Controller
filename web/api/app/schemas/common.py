"""
Water Treatment Controller - Common Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Shared Pydantic models used across all endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, Optional, TypeVar
from pydantic import BaseModel, Field


class DataQuality(str, Enum):
    """Data quality indicators for process values."""

    GOOD = "GOOD"  # Fresh, valid reading
    UNCERTAIN = "UNCERTAIN"  # May be stale or degraded
    BAD = "BAD"  # Sensor failure
    NOT_CONNECTED = "NOT_CONNECTED"  # No communication


class ResponseMeta(BaseModel):
    """Metadata included in all API responses."""

    timestamp: datetime = Field(description="Response timestamp in ISO 8601 format")
    request_id: Optional[str] = Field(None, description="Unique request identifier for tracing")


class ErrorDetail(BaseModel):
    """Detailed error information."""

    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error context")
    recoverable: bool = Field(True, description="Whether client can retry the operation")
    suggested_action: Optional[str] = Field(None, description="Suggested resolution")


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    error: ErrorDetail
    meta: ResponseMeta


# Generic type for response data
T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success response envelope."""

    data: Any = Field(description="Response payload")
    meta: Optional[ResponseMeta] = Field(None, description="Response metadata")


class PaginationMeta(BaseModel):
    """Pagination information for list responses."""

    total: int = Field(description="Total number of items")
    offset: int = Field(0, description="Current offset")
    limit: int = Field(description="Items per page")
    has_more: bool = Field(False, description="Whether more items exist")
