"""
Water Treatment Controller - RTU Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pydantic models for RTU-related endpoints.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RtuState(str, Enum):
    """RTU connection states."""

    OFFLINE = "OFFLINE"  # Not connected
    CONNECTING = "CONNECTING"  # Connection in progress
    DISCOVERY = "DISCOVERY"  # Discovering modules
    RUNNING = "RUNNING"  # Connected and operational
    ERROR = "ERROR"  # Connection error


# Validation patterns
STATION_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,31}$")
HEX_ID_PATTERN = re.compile(r"^0x[0-9A-Fa-f]{4}$")


class RtuCreate(BaseModel):
    """Request model for creating a new RTU."""

    station_name: str = Field(
        ...,
        min_length=3,
        max_length=32,
        description="Unique station name (lowercase, starts with letter)"
    )
    ip_address: str = Field(..., description="IPv4 address of the RTU")
    vendor_id: str = Field(..., description="PROFINET vendor ID (hex string, e.g., '0x002A')")
    device_id: str = Field(..., description="PROFINET device ID (hex string, e.g., '0x0405')")
    slot_count: int = Field(8, ge=1, le=64, description="Number of I/O slots")

    @field_validator("station_name")
    @classmethod
    def validate_station_name(cls, v: str) -> str:
        if not STATION_NAME_PATTERN.match(v):
            raise ValueError(
                "station_name must be 3-32 characters, start with a letter, "
                "and contain only lowercase letters, numbers, and hyphens"
            )
        return v

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) != 4:
            raise ValueError("Invalid IPv4 address format")
        for part in parts:
            try:
                num = int(part)
                if num < 0 or num > 255:
                    raise ValueError("Invalid IPv4 address")
            except ValueError as err:
                raise ValueError("Invalid IPv4 address") from err
        return v

    @field_validator("vendor_id", "device_id")
    @classmethod
    def validate_hex_id(cls, v: str) -> str:
        if not HEX_ID_PATTERN.match(v):
            raise ValueError("Must be hex format 0x0000-0xFFFF")
        return v


class RtuStats(BaseModel):
    """Statistics for an RTU."""

    slot_count: int = Field(description="Total number of slots")
    configured_slots: int = Field(0, description="Slots with configuration")
    sensor_count: int = Field(0, description="Number of sensors")
    control_count: int = Field(0, description="Number of controls")
    alarm_count: int = Field(0, description="Total alarm rules")
    active_alarms: int = Field(0, description="Currently active alarms")
    pid_loop_count: int = Field(0, description="Number of PID loops")


class SlotSummary(BaseModel):
    """Summary of a slot for RTU detail view."""

    slot: int = Field(description="Slot number")
    module_id: str | None = Field(None, description="Module identifier")
    module_type: str | None = Field(None, description="Module type name")
    status: str = Field("EMPTY", description="Slot status")


class RtuResponse(BaseModel):
    """RTU response for list endpoint."""

    id: int = Field(description="Database ID")
    station_name: str = Field(description="Unique station name")
    ip_address: str = Field(description="IPv4 address")
    state: RtuState = Field(description="Current connection state")
    state_since: datetime | None = Field(None, description="Time of last state change")
    stats: RtuStats | None = Field(None, description="Optional statistics")


class RtuDetailResponse(BaseModel):
    """Detailed RTU response including slots and full stats."""

    id: int = Field(description="Database ID")
    station_name: str = Field(description="Unique station name")
    ip_address: str = Field(description="IPv4 address")
    vendor_id: str = Field(description="PROFINET vendor ID")
    device_id: str = Field(description="PROFINET device ID")
    slot_count: int = Field(description="Number of I/O slots")
    state: RtuState = Field(description="Current connection state")
    state_since: datetime | None = Field(None, description="Time of last state change")
    last_error: str | None = Field(None, description="Last error message")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    slots: list[SlotSummary] = Field(default_factory=list, description="Slot configurations")
    stats: RtuStats = Field(description="RTU statistics")


class RtuListResponse(BaseModel):
    """Response wrapper for RTU list."""

    data: list[RtuResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


class DeletionImpact(BaseModel):
    """Preview of what will be deleted with an RTU."""

    rtu: str = Field(description="RTU station name")
    impact: dict[str, Any] = Field(description="Resources to be deleted")


class ConnectRequest(BaseModel):
    """Request to connect to an RTU."""

    timeout_seconds: int = Field(30, ge=5, le=120, description="Connection timeout")
    auto_discover: bool = Field(False, description="Run discovery after connect")


class ConnectResponse(BaseModel):
    """Response for connect operation."""

    station_name: str = Field(description="RTU station name")
    state: RtuState = Field(description="New state (CONNECTING)")
    message: str = Field(description="Status message")


class DisconnectResponse(BaseModel):
    """Response for disconnect operation."""

    station_name: str = Field(description="RTU station name")
    state: RtuState = Field(description="New state (OFFLINE)")
    message: str = Field(description="Status message")


class DiscoveredSlot(BaseModel):
    """Slot discovered during module discovery."""

    slot: int = Field(description="Slot number")
    module_id: str = Field(description="Module identifier")
    module_type: str | None = Field(None, description="Module type name")
    subslots: list[dict[str, Any]] = Field(default_factory=list, description="Subslot info")


class DiscoverSummary(BaseModel):
    """Summary of discovery results."""

    total_slots: int = Field(description="Total slot count")
    populated_slots: int = Field(description="Slots with modules")
    empty_slots: int = Field(description="Empty slots")


class DiscoverResponse(BaseModel):
    """Response for module discovery."""

    station_name: str = Field(description="RTU station name")
    discovered_slots: list[DiscoveredSlot] = Field(description="Discovered modules")
    summary: DiscoverSummary = Field(description="Discovery summary")


class TestResult(BaseModel):
    """Individual test result."""

    passed: bool = Field(description="Whether test passed")
    latency_ms: float | None = Field(None, description="Test latency in ms")
    bytes_read: int | None = Field(None, description="Bytes read (for I/O tests)")
    bytes_written: int | None = Field(None, description="Bytes written (for I/O tests)")
    target_ms: float | None = Field(None, description="Target value (for cycle time)")
    measured_ms: float | None = Field(None, description="Measured value")
    jitter_ms: float | None = Field(None, description="Timing jitter")


class TestResponse(BaseModel):
    """Response for connection/I/O test."""

    station_name: str = Field(description="RTU station name")
    tests: dict[str, TestResult] = Field(description="Individual test results")
    overall_passed: bool = Field(description="Whether all tests passed")
