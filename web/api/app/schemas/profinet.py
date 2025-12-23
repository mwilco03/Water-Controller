"""
Water Treatment Controller - PROFINET Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pydantic models for PROFINET status and diagnostics.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .common import DataQuality


class DiagnosticLevel(str, Enum):
    """Diagnostic message severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class CycleTimeStats(BaseModel):
    """PROFINET cycle time statistics."""

    target_ms: float = Field(description="Configured cycle time")
    actual_ms: float = Field(description="Measured cycle time")
    min_ms: float = Field(description="Minimum observed")
    max_ms: float = Field(description="Maximum observed")


class PacketStats(BaseModel):
    """PROFINET packet statistics."""

    sent: int = Field(description="Total packets sent")
    received: int = Field(description="Total packets received")
    lost: int = Field(description="Packets lost")
    loss_percent: float = Field(description="Packet loss percentage")


class IoStatus(BaseModel):
    """PROFINET I/O data status."""

    input_bytes: int = Field(description="Input data size in bytes")
    output_bytes: int = Field(description="Output data size in bytes")
    last_update: datetime = Field(description="Last I/O update timestamp")
    data_quality: DataQuality = Field(description="Overall data quality")


class ProfinetStatusConnected(BaseModel):
    """PROFINET status when connected."""

    connected: bool = Field(True, description="Connection status")
    ar_handle: str = Field(description="Application Relationship handle")
    uptime_seconds: int = Field(description="Total RTU uptime")
    session_seconds: int = Field(description="Current session duration")
    cycle_time: CycleTimeStats = Field(description="Cycle time statistics")
    packet_stats: PacketStats = Field(description="Packet statistics")
    jitter_ms: float = Field(description="Timing jitter in ms")
    last_error: Optional[str] = Field(None, description="Last error if any")
    io_status: IoStatus = Field(description="I/O data status")
    timestamp: datetime = Field(description="Status timestamp")


class ProfinetStatusDisconnected(BaseModel):
    """PROFINET status when disconnected."""

    connected: bool = Field(False, description="Connection status")
    state: str = Field(description="Current RTU state")
    last_connected: Optional[datetime] = Field(None, description="Last connection time")
    last_error: Optional[str] = Field(None, description="Last error message")
    timestamp: datetime = Field(description="Status timestamp")


class ProfinetStatus(BaseModel):
    """PROFINET connection status (connected or disconnected)."""

    connected: bool = Field(description="Whether RTU is connected")

    # Connected fields
    ar_handle: Optional[str] = Field(None, description="AR handle when connected")
    uptime_seconds: Optional[int] = Field(None, description="RTU uptime")
    session_seconds: Optional[int] = Field(None, description="Session duration")
    cycle_time: Optional[CycleTimeStats] = Field(None, description="Cycle time stats")
    packet_stats: Optional[PacketStats] = Field(None, description="Packet stats")
    jitter_ms: Optional[float] = Field(None, description="Timing jitter")
    io_status: Optional[IoStatus] = Field(None, description="I/O status")

    # Disconnected fields
    state: Optional[str] = Field(None, description="State when disconnected")
    last_connected: Optional[datetime] = Field(None, description="Last connection time")

    # Common fields
    last_error: Optional[str] = Field(None, description="Last error")
    timestamp: datetime = Field(description="Status timestamp")


class ProfinetSubslot(BaseModel):
    """PROFINET subslot information."""

    subslot: int = Field(description="Subslot number")
    io_type: str = Field(description="I/O type (input, output)")
    bytes: int = Field(description="Data size in bytes")
    status: str = Field(description="Subslot status")
    diag_info: Optional[str] = Field(None, description="Diagnostic info")


class ProfinetSlot(BaseModel):
    """PROFINET slot diagnostic information."""

    slot: int = Field(description="Slot number")
    module_id: str = Field(description="Module identifier")
    module_ident: Optional[str] = Field(None, description="Module identification string")
    subslots: List[ProfinetSubslot] = Field(default_factory=list, description="Subslot info")
    status: str = Field(description="Slot status")
    pulled: bool = Field(False, description="Module was pulled")
    wrong_module: bool = Field(False, description="Wrong module installed")


class ProfinetDiagnostic(BaseModel):
    """PROFINET diagnostic log entry."""

    id: int = Field(description="Diagnostic entry ID")
    timestamp: datetime = Field(description="Event timestamp")
    level: DiagnosticLevel = Field(description="Severity level")
    source: str = Field(description="Diagnostic source (AR, CYCLE, etc.)")
    message: str = Field(description="Diagnostic message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class ProfinetDiagnosticListMeta(BaseModel):
    """Metadata for diagnostic list response."""

    total: int = Field(description="Total entries matching filter")
    filtered: int = Field(description="Entries returned")
    hours: int = Field(description="Time range in hours")


class ProfinetDiagnosticListResponse(BaseModel):
    """Response wrapper for diagnostic list."""

    data: List[ProfinetDiagnostic]
    meta: ProfinetDiagnosticListMeta
