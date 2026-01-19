"""
Water Treatment Controller - Core Module
Error handling, exceptions, and logging utilities
"""

from .errors import ERROR_CODE_STATUS_MAP
from .exceptions import (
    CommandRejectedError,
    CommandTimeoutError,
    ControlNotFoundError,
    InternalError,
    ProfinetError,
    RtuAlreadyExistsError,
    RtuBusyError,
    RtuNotConnectedError,
    RtuNotFoundError,
    ScadaException,
    ValidationError,
)

__all__ = [
    "ERROR_CODE_STATUS_MAP",
    "CommandRejectedError",
    "CommandTimeoutError",
    "ControlNotFoundError",
    "InternalError",
    "ProfinetError",
    "RtuAlreadyExistsError",
    "RtuBusyError",
    "RtuNotConnectedError",
    "RtuNotFoundError",
    "ScadaException",
    "ValidationError",
]
