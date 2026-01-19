"""
Water Treatment Controller - Pydantic Schemas
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from .alarm import (
    AlarmAcknowledgeRequest,
    AlarmConfig,
    AlarmEvent,
    AlarmListResponse,
    AlarmPriority,
    AlarmState,
    AlarmType,
    ScheduledMaintenanceCreate,
    ScheduledMaintenanceListResponse,
    ScheduledMaintenanceResponse,
    ScheduledMaintenanceStatus,
)
from .common import DataQuality, ErrorResponse, ResponseMeta, SuccessResponse
from .control import (
    CommandResponse,
    ControlCommand,
    ControlConfig,
    ControlListResponse,
    ControlState,
    ControlType,
)
from .profinet import (
    CycleTimeStats,
    IoStatus,
    PacketStats,
    ProfinetDiagnostic,
    ProfinetSlot,
    ProfinetStatus,
)
from .rtu import (
    ConnectRequest,
    ConnectResponse,
    DeletionImpact,
    DisconnectResponse,
    DiscoverResponse,
    RtuCreate,
    RtuDetailResponse,
    RtuListResponse,
    RtuResponse,
    RtuState,
    RtuStats,
    TestResponse,
)
from .sensor import (
    SensorConfig,
    SensorListResponse,
    SensorValue,
)
from .trends import (
    TrendAggregate,
    TrendData,
    TrendExportRequest,
    TrendInterval,
    TrendPoint,
    TrendQuery,
)

__all__ = [
    "AlarmAcknowledgeRequest",
    "AlarmConfig",
    "AlarmEvent",
    "AlarmListResponse",
    # Alarm
    "AlarmPriority",
    "AlarmState",
    "AlarmType",
    # Scheduled Maintenance
    "ScheduledMaintenanceCreate",
    "ScheduledMaintenanceListResponse",
    "ScheduledMaintenanceResponse",
    "ScheduledMaintenanceStatus",
    "CommandResponse",
    "ConnectRequest",
    "ConnectResponse",
    "ControlCommand",
    "ControlConfig",
    "ControlListResponse",
    "ControlState",
    # Control
    "ControlType",
    # PROFINET
    "CycleTimeStats",
    # Common
    "DataQuality",
    "DeletionImpact",
    "DisconnectResponse",
    "DiscoverResponse",
    "ErrorResponse",
    "IoStatus",
    "PacketStats",
    "ProfinetDiagnostic",
    "ProfinetSlot",
    "ProfinetStatus",
    "ResponseMeta",
    "RtuCreate",
    "RtuDetailResponse",
    "RtuListResponse",
    "RtuResponse",
    # RTU
    "RtuState",
    "RtuStats",
    # Sensor
    "SensorConfig",
    "SensorListResponse",
    "SensorValue",
    "SuccessResponse",
    "TestResponse",
    "TrendAggregate",
    "TrendData",
    "TrendExportRequest",
    # Trends
    "TrendInterval",
    "TrendPoint",
    "TrendQuery",
]
