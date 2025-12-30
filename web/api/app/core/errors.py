"""
Water Treatment Controller - Error Response Handlers
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Exception handlers and error response formatting.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from .exceptions import ScadaException

# Map error codes to HTTP status codes
ERROR_CODE_STATUS_MAP: dict[str, int] = {
    "VALIDATION_ERROR": 400,
    "RTU_NOT_FOUND": 404,
    "RTU_ALREADY_EXISTS": 409,
    "RTU_NOT_CONNECTED": 409,
    "RTU_BUSY": 409,
    "SLOT_NOT_FOUND": 404,
    "CONTROL_NOT_FOUND": 404,
    "SENSOR_NOT_FOUND": 404,
    "ALARM_NOT_FOUND": 404,
    "PID_LOOP_NOT_FOUND": 404,
    "COMMAND_REJECTED": 422,
    "COMMAND_TIMEOUT": 504,
    "PROFINET_ERROR": 502,
    "INTERNAL_ERROR": 500,
}

# Operator-friendly error messages for low-skill environments
# These translations help field operators understand issues without technical knowledge
OPERATOR_MESSAGES: dict[str, str] = {
    "VALIDATION_ERROR": "The information provided is incomplete or incorrect. Please check your input.",
    "RTU_NOT_FOUND": "The requested device was not found. It may have been removed or renamed.",
    "RTU_ALREADY_EXISTS": "A device with this name already exists. Please use a different name.",
    "RTU_NOT_CONNECTED": "The device is offline. Check the network cable and verify the device has power.",
    "RTU_BUSY": "The device is busy processing another request. Please wait and try again.",
    "SLOT_NOT_FOUND": "The requested I/O slot was not found on this device.",
    "CONTROL_NOT_FOUND": "The requested control point was not found. It may have been removed.",
    "SENSOR_NOT_FOUND": "The requested sensor was not found. It may have been removed.",
    "ALARM_NOT_FOUND": "The alarm was not found. It may have already been cleared.",
    "PID_LOOP_NOT_FOUND": "The PID control loop was not found. It may have been deleted.",
    "COMMAND_REJECTED": "The command was not accepted. Check interlocks and device status.",
    "COMMAND_TIMEOUT": "The device did not respond in time. The network may be slow or the device may be overloaded.",
    "PROFINET_ERROR": "Cannot communicate with the device. Check the network cable and verify the device is powered on.",
    "INTERNAL_ERROR": "An unexpected error occurred. If this persists, contact support.",
}


def get_operator_message(error_code: str) -> str:
    """
    Get operator-friendly message for an error code.

    For use in field deployments where operators may not have
    technical expertise to interpret system error codes.
    """
    return OPERATOR_MESSAGES.get(error_code, "An error occurred. Please try again.")


def get_request_id(request: Request) -> str:
    """Get or generate request ID for tracing."""
    return getattr(request.state, "request_id", str(uuid4()))


def build_error_response(
    error: ScadaException,
    request_id: str | None = None
) -> dict[str, Any]:
    """Build standardized error response envelope with operator-friendly message."""
    error_dict = error.to_dict()
    # Add operator-friendly message for display in low-skill environments
    error_dict["operator_message"] = get_operator_message(error.code)

    return {
        "error": error_dict,
        "meta": {
            "timestamp": datetime.now(UTC).isoformat(),
            "request_id": request_id or str(uuid4()),
        }
    }


def build_success_response(
    data: Any,
    request_id: str | None = None,
    meta: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build standardized success response envelope."""
    response = {"data": data}

    response_meta = {
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if request_id:
        response_meta["request_id"] = request_id
    if meta:
        response_meta.update(meta)

    if response_meta:
        response["meta"] = response_meta

    return response


async def scada_exception_handler(request: Request, exc: ScadaException) -> JSONResponse:
    """Handle ScadaException and return formatted error response."""
    status_code = ERROR_CODE_STATUS_MAP.get(exc.code, 500)
    request_id = get_request_id(request)

    return JSONResponse(
        status_code=status_code,
        content=build_error_response(exc, request_id)
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    import logging
    logger = logging.getLogger(__name__)

    request_id = get_request_id(request)
    logger.error(f"Unhandled exception (request_id={request_id}): {exc}", exc_info=True)

    from .exceptions import InternalError
    internal_error = InternalError()

    return JSONResponse(
        status_code=500,
        content=build_error_response(internal_error, request_id)
    )
