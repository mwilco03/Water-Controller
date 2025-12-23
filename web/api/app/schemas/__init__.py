"""
Water Treatment Controller - Pydantic Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from .common import DataQuality, ResponseMeta, ErrorResponse, SuccessResponse
from .rtu import (
    RtuState,
    RtuCreate,
    RtuResponse,
    RtuListResponse,
    RtuDetailResponse,
    RtuStats,
    DeletionImpact,
    ConnectRequest,
    ConnectResponse,
    DisconnectResponse,
    DiscoverResponse,
    TestResponse,
)
from .sensor import (
    SensorConfig,
    SensorValue,
    SensorListResponse,
)
from .control import (
    ControlType,
    ControlConfig,
    ControlState,
    ControlCommand,
    CommandResponse,
    ControlListResponse,
)
from .slot import (
    SlotStatus,
    SlotConfig,
    SlotResponse,
    SlotListResponse,
    SlotConfigUpdate,
)
from .profinet import (
    CycleTimeStats,
    PacketStats,
    IoStatus,
    ProfinetStatus,
    ProfinetSlot,
    ProfinetDiagnostic,
)
from .alarm import (
    AlarmPriority,
    AlarmState,
    AlarmType,
    AlarmConfig,
    AlarmEvent,
    AlarmListResponse,
    AlarmAcknowledgeRequest,
)
from .trends import (
    TrendInterval,
    TrendAggregate,
    TrendPoint,
    TrendData,
    TrendQuery,
    TrendExportRequest,
)

__all__ = [
    # Common
    "DataQuality",
    "ResponseMeta",
    "ErrorResponse",
    "SuccessResponse",
    # RTU
    "RtuState",
    "RtuCreate",
    "RtuResponse",
    "RtuListResponse",
    "RtuDetailResponse",
    "RtuStats",
    "DeletionImpact",
    "ConnectRequest",
    "ConnectResponse",
    "DisconnectResponse",
    "DiscoverResponse",
    "TestResponse",
    # Sensor
    "SensorConfig",
    "SensorValue",
    "SensorListResponse",
    # Control
    "ControlType",
    "ControlConfig",
    "ControlState",
    "ControlCommand",
    "CommandResponse",
    "ControlListResponse",
    # Slot
    "SlotStatus",
    "SlotConfig",
    "SlotResponse",
    "SlotListResponse",
    "SlotConfigUpdate",
    # PROFINET
    "CycleTimeStats",
    "PacketStats",
    "IoStatus",
    "ProfinetStatus",
    "ProfinetSlot",
    "ProfinetDiagnostic",
    # Alarm
    "AlarmPriority",
    "AlarmState",
    "AlarmType",
    "AlarmConfig",
    "AlarmEvent",
    "AlarmListResponse",
    "AlarmAcknowledgeRequest",
    # Trends
    "TrendInterval",
    "TrendAggregate",
    "TrendPoint",
    "TrendData",
    "TrendQuery",
    "TrendExportRequest",
]
