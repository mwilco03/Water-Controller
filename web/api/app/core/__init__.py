"""
Water Treatment Controller - Core Module
Error handling, exceptions, and logging utilities
"""

from .exceptions import (
    ScadaException,
    ValidationError,
    RtuNotFoundError,
    RtuAlreadyExistsError,
    RtuNotConnectedError,
    RtuBusyError,
    SlotNotFoundError,
    ControlNotFoundError,
    CommandRejectedError,
    CommandTimeoutError,
    ProfinetError,
    InternalError,
)
from .errors import ERROR_CODE_STATUS_MAP

__all__ = [
    "ScadaException",
    "ValidationError",
    "RtuNotFoundError",
    "RtuAlreadyExistsError",
    "RtuNotConnectedError",
    "RtuBusyError",
    "SlotNotFoundError",
    "ControlNotFoundError",
    "CommandRejectedError",
    "CommandTimeoutError",
    "ProfinetError",
    "InternalError",
    "ERROR_CODE_STATUS_MAP",
]
