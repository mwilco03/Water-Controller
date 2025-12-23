"""
Water Treatment Controller - Error Response Handlers
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Exception handlers and error response formatting.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from .exceptions import ScadaException

# Map error codes to HTTP status codes
ERROR_CODE_STATUS_MAP: Dict[str, int] = {
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


def get_request_id(request: Request) -> str:
    """Get or generate request ID for tracing."""
    return getattr(request.state, "request_id", str(uuid4()))


def build_error_response(
    error: ScadaException,
    request_id: Optional[str] = None
) -> Dict[str, Any]:
    """Build standardized error response envelope."""
    return {
        "error": error.to_dict(),
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id or str(uuid4()),
        }
    }


def build_success_response(
    data: Any,
    request_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build standardized success response envelope."""
    response = {"data": data}

    response_meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
