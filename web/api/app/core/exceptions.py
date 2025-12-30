"""
Water Treatment Controller - Custom Exceptions
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Standardized exception classes for SCADA operations.
All exceptions follow the response envelope pattern.
"""

from typing import Any


class ScadaException(Exception):
    """Base exception for all SCADA-related errors."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        recoverable: bool = True,
        suggested_action: str | None = None
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.recoverable = recoverable
        self.suggested_action = suggested_action

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to error response dictionary."""
        result = {
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
        }
        if self.details:
            result["details"] = self.details
        if self.suggested_action:
            result["suggested_action"] = self.suggested_action
        return result


class ValidationError(ScadaException):
    """Request validation failed."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            details=details,
            recoverable=True,
            suggested_action="Check request parameters and try again"
        )


class RtuNotFoundError(ScadaException):
    """RTU does not exist."""

    def __init__(self, name: str):
        super().__init__(
            code="RTU_NOT_FOUND",
            message=f"RTU '{name}' not found",
            details={"rtu_name": name},
            recoverable=True,
            suggested_action="Verify RTU name or check RTU list"
        )


class RtuAlreadyExistsError(ScadaException):
    """RTU with same name or IP already exists."""

    def __init__(self, field: str, value: str):
        super().__init__(
            code="RTU_ALREADY_EXISTS",
            message=f"RTU with {field} '{value}' already exists",
            details={field: value},
            recoverable=True,
            suggested_action=f"Use a different {field}"
        )


class RtuNotConnectedError(ScadaException):
    """Operation requires connected RTU but RTU is not connected."""

    def __init__(self, name: str, current_state: str = "OFFLINE"):
        super().__init__(
            code="RTU_NOT_CONNECTED",
            message=f"RTU '{name}' is not connected (state: {current_state})",
            details={"rtu_name": name, "current_state": current_state},
            recoverable=True,
            suggested_action="Connect to RTU first using POST /api/v1/rtus/{name}/connect"
        )


class RtuBusyError(ScadaException):
    """RTU is in a transitional state."""

    def __init__(self, name: str, current_state: str):
        super().__init__(
            code="RTU_BUSY",
            message=f"RTU '{name}' is busy (state: {current_state})",
            details={"rtu_name": name, "current_state": current_state},
            recoverable=True,
            suggested_action="Wait for current operation to complete and try again"
        )


class SlotNotFoundError(ScadaException):
    """Slot index does not exist on RTU."""

    def __init__(self, rtu_name: str, slot: int, max_slot: int):
        super().__init__(
            code="SLOT_NOT_FOUND",
            message=f"Slot {slot} not found on RTU '{rtu_name}'",
            details={"rtu_name": rtu_name, "slot": slot, "max_slot": max_slot},
            recoverable=True,
            suggested_action=f"Use slot number between 1 and {max_slot}"
        )


class ControlNotFoundError(ScadaException):
    """Control/actuator does not exist."""

    def __init__(self, rtu_name: str, tag: str):
        super().__init__(
            code="CONTROL_NOT_FOUND",
            message=f"Control '{tag}' not found on RTU '{rtu_name}'",
            details={"rtu_name": rtu_name, "tag": tag},
            recoverable=True,
            suggested_action="Verify control tag name or check controls list"
        )


class CommandRejectedError(ScadaException):
    """Command blocked by interlock or safety logic."""

    def __init__(
        self,
        message: str,
        interlock: str | None = None,
        condition: str | None = None,
        current_value: float | None = None
    ):
        details = {}
        if interlock:
            details["interlock"] = interlock
        if condition:
            details["condition"] = condition
        if current_value is not None:
            details["current_value"] = current_value

        super().__init__(
            code="COMMAND_REJECTED",
            message=message,
            details=details,
            recoverable=False,
            suggested_action="Resolve interlock condition before retrying"
        )


class CommandTimeoutError(ScadaException):
    """RTU did not respond to command in time."""

    def __init__(self, operation: str, timeout_seconds: float):
        super().__init__(
            code="COMMAND_TIMEOUT",
            message=f"{operation} timed out after {timeout_seconds}s",
            details={"operation": operation, "timeout_seconds": timeout_seconds},
            recoverable=True,
            suggested_action="Check RTU connection and try again"
        )


class ProfinetError(ScadaException):
    """PROFINET communication failure."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            code="PROFINET_ERROR",
            message=message,
            details=details,
            recoverable=True,
            suggested_action="Check network connectivity and RTU status"
        )


class InternalError(ScadaException):
    """Unexpected server error."""

    def __init__(self, message: str = "An unexpected error occurred"):
        super().__init__(
            code="INTERNAL_ERROR",
            message=message,
            details={},
            recoverable=False,
            suggested_action="Contact system administrator"
        )


class AlarmNotFoundError(ScadaException):
    """Alarm does not exist."""

    def __init__(self, alarm_id: int):
        super().__init__(
            code="ALARM_NOT_FOUND",
            message=f"Alarm {alarm_id} not found",
            details={"alarm_id": alarm_id},
            recoverable=True,
            suggested_action="Verify alarm ID or check alarm list"
        )


class SensorNotFoundError(ScadaException):
    """Sensor does not exist."""

    def __init__(self, rtu_name: str, tag: str):
        super().__init__(
            code="SENSOR_NOT_FOUND",
            message=f"Sensor '{tag}' not found on RTU '{rtu_name}'",
            details={"rtu_name": rtu_name, "tag": tag},
            recoverable=True,
            suggested_action="Verify sensor tag name or check sensors list"
        )


class PidLoopNotFoundError(ScadaException):
    """PID loop does not exist."""

    def __init__(self, loop_id: int):
        super().__init__(
            code="PID_LOOP_NOT_FOUND",
            message=f"PID loop {loop_id} not found",
            details={"loop_id": loop_id},
            recoverable=True,
            suggested_action="Verify loop ID or check PID loops list"
        )
