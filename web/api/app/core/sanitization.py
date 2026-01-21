"""
Water Treatment Controller - Input Sanitization
Copyright (C) 2024-2025
SPDX-License-Identifier: GPL-3.0-or-later

Input validation and sanitization for control system commands.
Prevents injection attacks and ensures data integrity.

Critical for:
- Modbus register writes
- Setpoint changes
- RTU configuration
- User input
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .logging import get_logger

logger = get_logger(__name__)


class SanitizationError(Exception):
    """Raised when input fails sanitization."""

    def __init__(self, field: str, message: str, value: Any = None):
        self.field = field
        self.message = message
        self.value = value
        super().__init__(f"{field}: {message}")


class RegisterType(Enum):
    """Modbus register types with valid ranges."""
    COIL = ("coil", 0, 1)
    DISCRETE = ("discrete", 0, 1)
    HOLDING = ("holding", 0, 65535)
    INPUT = ("input", 0, 65535)


@dataclass
class ValidationResult:
    """Result of input validation."""
    valid: bool
    sanitized_value: Any = None
    error: str | None = None
    field: str | None = None


class InputSanitizer:
    """
    Sanitizes and validates input for control system operations.

    Design principles:
    - Fail closed: Invalid input is rejected, not "fixed"
    - Explicit bounds: All numeric inputs have defined ranges
    - No injection: String inputs are validated against patterns
    - Audit trail: All sanitization failures are logged
    """

    # Patterns for valid input
    # Per RTU team spec (IEC 61158-6): lowercase, digits, hyphen only. Max 63 chars.
    # NO dots, NO underscores, NO uppercase.
    STATION_NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]{0,62}$')
    IP_ADDRESS_PATTERN = re.compile(
        r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{2,31}$')
    TAG_NAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_./:-]{0,127}$')

    # Bounds for numeric inputs
    MODBUS_ADDRESS_MIN = 0
    MODBUS_ADDRESS_MAX = 65535
    MODBUS_VALUE_MIN = 0
    MODBUS_VALUE_MAX = 65535
    SLOT_MIN = 0
    SLOT_MAX = 255
    PWM_MIN = 0
    PWM_MAX = 100
    SETPOINT_MIN = -1e9
    SETPOINT_MAX = 1e9

    # PID tuning bounds (reasonable for water treatment)
    PID_KP_MIN = 0.0
    PID_KP_MAX = 1000.0
    PID_KI_MIN = 0.0
    PID_KI_MAX = 100.0
    PID_KD_MIN = 0.0
    PID_KD_MAX = 100.0

    def __init__(self, log_failures: bool = True):
        self.log_failures = log_failures

    def _log_failure(self, field: str, message: str, value: Any) -> None:
        """Log sanitization failure."""
        if self.log_failures:
            # Don't log actual value for sensitive fields
            sensitive_fields = {"password", "password_hash", "token", "secret"}
            log_value = "[REDACTED]" if field.lower() in sensitive_fields else repr(value)
            logger.warning(
                f"Input sanitization failed: {field}={log_value} - {message}",
                extra={"field": field, "error": message}
            )

    def validate_modbus_address(self, address: Any, field: str = "address") -> ValidationResult:
        """Validate Modbus register address."""
        try:
            addr = int(address)
            if not self.MODBUS_ADDRESS_MIN <= addr <= self.MODBUS_ADDRESS_MAX:
                self._log_failure(field, f"Address out of range [0, 65535]", address)
                return ValidationResult(False, error=f"Address must be 0-65535", field=field)
            return ValidationResult(True, sanitized_value=addr)
        except (ValueError, TypeError):
            self._log_failure(field, "Not a valid integer", address)
            return ValidationResult(False, error="Address must be an integer", field=field)

    def validate_modbus_value(
        self,
        value: Any,
        register_type: str = "holding",
        field: str = "value"
    ) -> ValidationResult:
        """
        Validate Modbus register value.

        Coils/discretes: 0 or 1
        Holdings/inputs: 0-65535
        """
        try:
            val = int(value)
        except (ValueError, TypeError):
            self._log_failure(field, "Not a valid integer", value)
            return ValidationResult(False, error="Value must be an integer", field=field)

        if register_type.lower() in ("coil", "discrete"):
            if val not in (0, 1):
                self._log_failure(field, "Coil value must be 0 or 1", value)
                return ValidationResult(False, error="Coil value must be 0 or 1", field=field)
        else:
            if not self.MODBUS_VALUE_MIN <= val <= self.MODBUS_VALUE_MAX:
                self._log_failure(field, f"Value out of range [0, 65535]", value)
                return ValidationResult(False, error="Value must be 0-65535", field=field)

        return ValidationResult(True, sanitized_value=val)

    def validate_station_name(self, name: Any, field: str = "station_name") -> ValidationResult:
        """
        Validate RTU station name.

        Rules:
        - 1-64 characters
        - Starts with letter
        - Only alphanumeric, underscore, hyphen
        """
        if not isinstance(name, str):
            self._log_failure(field, "Not a string", name)
            return ValidationResult(False, error="Station name must be a string", field=field)

        name = name.strip()

        if not name:
            self._log_failure(field, "Empty string", name)
            return ValidationResult(False, error="Station name cannot be empty", field=field)

        if not self.STATION_NAME_PATTERN.match(name):
            self._log_failure(field, "Invalid format", name)
            return ValidationResult(
                False,
                error="Station name must be 1-63 chars, start with letter/digit, contain only lowercase letters, digits, and hyphens",
                field=field
            )

        return ValidationResult(True, sanitized_value=name)

    def validate_ip_address(self, ip: Any, field: str = "ip_address") -> ValidationResult:
        """Validate IPv4 address."""
        if not isinstance(ip, str):
            self._log_failure(field, "Not a string", ip)
            return ValidationResult(False, error="IP address must be a string", field=field)

        ip = ip.strip()

        if not self.IP_ADDRESS_PATTERN.match(ip):
            self._log_failure(field, "Invalid IPv4 format", ip)
            return ValidationResult(False, error="Invalid IPv4 address format", field=field)

        return ValidationResult(True, sanitized_value=ip)

    def validate_slot(self, slot: Any, field: str = "slot") -> ValidationResult:
        """Validate slot number (0-255)."""
        try:
            s = int(slot)
            if not self.SLOT_MIN <= s <= self.SLOT_MAX:
                self._log_failure(field, f"Slot out of range [0, 255]", slot)
                return ValidationResult(False, error="Slot must be 0-255", field=field)
            return ValidationResult(True, sanitized_value=s)
        except (ValueError, TypeError):
            self._log_failure(field, "Not a valid integer", slot)
            return ValidationResult(False, error="Slot must be an integer", field=field)

    def validate_pwm_duty(self, duty: Any, field: str = "pwm_duty") -> ValidationResult:
        """Validate PWM duty cycle (0-100%)."""
        try:
            d = int(duty)
            if not self.PWM_MIN <= d <= self.PWM_MAX:
                self._log_failure(field, f"PWM out of range [0, 100]", duty)
                return ValidationResult(False, error="PWM duty must be 0-100", field=field)
            return ValidationResult(True, sanitized_value=d)
        except (ValueError, TypeError):
            self._log_failure(field, "Not a valid integer", duty)
            return ValidationResult(False, error="PWM duty must be an integer", field=field)

    def validate_setpoint(self, setpoint: Any, field: str = "setpoint") -> ValidationResult:
        """Validate setpoint value (floating point)."""
        try:
            sp = float(setpoint)
            if not self.SETPOINT_MIN <= sp <= self.SETPOINT_MAX:
                self._log_failure(field, "Setpoint out of reasonable range", setpoint)
                return ValidationResult(False, error="Setpoint value out of range", field=field)
            # Check for special values
            if sp != sp:  # NaN check
                self._log_failure(field, "NaN is not a valid setpoint", setpoint)
                return ValidationResult(False, error="NaN is not a valid setpoint", field=field)
            return ValidationResult(True, sanitized_value=sp)
        except (ValueError, TypeError):
            self._log_failure(field, "Not a valid number", setpoint)
            return ValidationResult(False, error="Setpoint must be a number", field=field)

    def validate_pid_tuning(
        self,
        kp: Any = None,
        ki: Any = None,
        kd: Any = None
    ) -> dict[str, ValidationResult]:
        """Validate PID tuning parameters."""
        results = {}

        if kp is not None:
            try:
                val = float(kp)
                if not self.PID_KP_MIN <= val <= self.PID_KP_MAX:
                    results["kp"] = ValidationResult(False, error="Kp out of range [0, 1000]", field="kp")
                else:
                    results["kp"] = ValidationResult(True, sanitized_value=val)
            except (ValueError, TypeError):
                results["kp"] = ValidationResult(False, error="Kp must be a number", field="kp")

        if ki is not None:
            try:
                val = float(ki)
                if not self.PID_KI_MIN <= val <= self.PID_KI_MAX:
                    results["ki"] = ValidationResult(False, error="Ki out of range [0, 100]", field="ki")
                else:
                    results["ki"] = ValidationResult(True, sanitized_value=val)
            except (ValueError, TypeError):
                results["ki"] = ValidationResult(False, error="Ki must be a number", field="ki")

        if kd is not None:
            try:
                val = float(kd)
                if not self.PID_KD_MIN <= val <= self.PID_KD_MAX:
                    results["kd"] = ValidationResult(False, error="Kd out of range [0, 100]", field="kd")
                else:
                    results["kd"] = ValidationResult(True, sanitized_value=val)
            except (ValueError, TypeError):
                results["kd"] = ValidationResult(False, error="Kd must be a number", field="kd")

        return results

    def validate_username(self, username: Any, field: str = "username") -> ValidationResult:
        """
        Validate username.

        Rules:
        - 3-32 characters
        - Starts with letter
        - Only alphanumeric and underscore
        """
        if not isinstance(username, str):
            self._log_failure(field, "Not a string", username)
            return ValidationResult(False, error="Username must be a string", field=field)

        username = username.strip()

        if not self.USERNAME_PATTERN.match(username):
            self._log_failure(field, "Invalid format", username)
            return ValidationResult(
                False,
                error="Username must be 3-32 characters, start with a letter, and contain only letters, numbers, and underscores",
                field=field
            )

        return ValidationResult(True, sanitized_value=username)

    def sanitize_string(
        self,
        value: Any,
        max_length: int = 255,
        allow_newlines: bool = False,
        field: str = "value"
    ) -> ValidationResult:
        """
        Sanitize general string input.

        Removes or escapes potentially dangerous characters.
        """
        if not isinstance(value, str):
            try:
                value = str(value)
            except Exception:
                self._log_failure(field, "Cannot convert to string", value)
                return ValidationResult(False, error="Value must be a string", field=field)

        # Truncate to max length
        if len(value) > max_length:
            value = value[:max_length]

        # Remove null bytes (potential injection)
        value = value.replace('\x00', '')

        # Remove control characters (except newline/tab if allowed)
        if allow_newlines:
            value = ''.join(c for c in value if c >= ' ' or c in '\n\r\t')
        else:
            value = ''.join(c for c in value if c >= ' ')

        # Strip leading/trailing whitespace
        value = value.strip()

        return ValidationResult(True, sanitized_value=value)


# Singleton instance
_sanitizer: InputSanitizer | None = None


def get_sanitizer() -> InputSanitizer:
    """Get the input sanitizer singleton."""
    global _sanitizer
    if _sanitizer is None:
        _sanitizer = InputSanitizer()
    return _sanitizer


# Convenience functions
def validate_modbus_write(
    address: Any,
    value: Any,
    register_type: str = "holding"
) -> tuple[bool, dict[str, Any], list[str]]:
    """
    Validate a Modbus write operation.

    Returns:
        (valid, sanitized_data, errors)
    """
    sanitizer = get_sanitizer()
    errors = []

    addr_result = sanitizer.validate_modbus_address(address)
    value_result = sanitizer.validate_modbus_value(value, register_type)

    if not addr_result.valid:
        errors.append(addr_result.error)
    if not value_result.valid:
        errors.append(value_result.error)

    if errors:
        return False, {}, errors

    return True, {
        "address": addr_result.sanitized_value,
        "value": value_result.sanitized_value
    }, []


def validate_rtu_config(
    station_name: Any,
    ip_address: Any,
    vendor_id: Any = None,
    device_id: Any = None
) -> tuple[bool, dict[str, Any], list[str]]:
    """
    Validate RTU configuration.

    Returns:
        (valid, sanitized_data, errors)
    """
    sanitizer = get_sanitizer()
    errors = []
    data = {}

    name_result = sanitizer.validate_station_name(station_name)
    if name_result.valid:
        data["station_name"] = name_result.sanitized_value
    else:
        errors.append(name_result.error)

    ip_result = sanitizer.validate_ip_address(ip_address)
    if ip_result.valid:
        data["ip_address"] = ip_result.sanitized_value
    else:
        errors.append(ip_result.error)

    if vendor_id is not None:
        try:
            vid = int(vendor_id, 16) if isinstance(vendor_id, str) else int(vendor_id)
            if 0 <= vid <= 0xFFFF:
                data["vendor_id"] = vid
            else:
                errors.append("Vendor ID must be 0x0000-0xFFFF")
        except (ValueError, TypeError):
            errors.append("Invalid vendor ID format")

    if device_id is not None:
        try:
            did = int(device_id, 16) if isinstance(device_id, str) else int(device_id)
            if 0 <= did <= 0xFFFF:
                data["device_id"] = did
            else:
                errors.append("Device ID must be 0x0000-0xFFFF")
        except (ValueError, TypeError):
            errors.append("Invalid device ID format")

    return len(errors) == 0, data, errors
