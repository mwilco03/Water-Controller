"""
Water Treatment Controller - Configuration Validation Module

This module provides startup validation to ensure configuration consistency
and prevent runtime errors from misconfiguration.

Usage:
    from app.core.config_validator import validate_configuration

    # At application startup
    validation_result = validate_configuration()
    if not validation_result.is_valid:
        for error in validation_result.errors:
            logger.error(f"Configuration error: {error}")
        sys.exit(1)
"""

import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .ports import (
    DEFAULTS,
    _find_ports_env,
    _load_config_defaults,
    get_api_port,
    get_db_port,
    get_modbus_tcp_port,
    get_profinet_udp_port,
    get_ui_port,
)


# -----------------------------------------------------------------------------
# Validation Result Types
# -----------------------------------------------------------------------------


@dataclass
class ValidationError:
    """A single validation error."""

    code: str
    message: str
    severity: str = "ERROR"  # ERROR, WARNING, INFO
    context: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of configuration validation."""

    is_valid: bool = True
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    def add_error(
        self, code: str, message: str, context: Optional[dict] = None
    ) -> None:
        """Add a validation error."""
        self.errors.append(
            ValidationError(
                code=code,
                message=message,
                severity="ERROR",
                context=context or {},
            )
        )
        self.is_valid = False

    def add_warning(
        self, code: str, message: str, context: Optional[dict] = None
    ) -> None:
        """Add a validation warning."""
        self.warnings.append(
            ValidationError(
                code=code,
                message=message,
                severity="WARNING",
                context=context or {},
            )
        )


# -----------------------------------------------------------------------------
# Validation Functions
# -----------------------------------------------------------------------------


def _validate_ports_env_exists(result: ValidationResult) -> None:
    """Validate that config/ports.env exists."""
    path = _find_ports_env()
    if path is None:
        result.add_warning(
            code="CFG-001",
            message=(
                "config/ports.env not found. Using hardcoded defaults. "
                "For production, ensure ports.env is installed at "
                "/opt/water-controller/config/ports.env"
            ),
        )


def _validate_required_env_vars(result: ValidationResult) -> None:
    """Validate that required environment variables are set for production."""
    # These are only required in production mode
    if os.environ.get("WTC_ENV", "development") != "production":
        return

    required_vars = [
        ("WTC_DB_PASSWORD", "Database password must be set in production"),
        ("WTC_SECRET_KEY", "Secret key for JWT must be set in production"),
    ]

    for var_name, error_msg in required_vars:
        if not os.environ.get(var_name):
            result.add_error(
                code="CFG-002",
                message=error_msg,
                context={"variable": var_name},
            )


def _validate_port_values(result: ValidationResult) -> None:
    """Validate that port values are in valid range."""
    port_checks = [
        ("API", get_api_port()),
        ("UI", get_ui_port()),
        ("Database", get_db_port()),
        ("PROFINET UDP", get_profinet_udp_port()),
        ("Modbus TCP", get_modbus_tcp_port()),
    ]

    for name, port in port_checks:
        if not (1 <= port <= 65535):
            result.add_error(
                code="CFG-003",
                message=f"{name} port {port} is outside valid range (1-65535)",
                context={"port_name": name, "port_value": port},
            )
        elif port < 1024 and os.getuid() != 0:
            # Non-root can't bind to privileged ports
            result.add_warning(
                code="CFG-004",
                message=(
                    f"{name} port {port} is privileged (< 1024). "
                    "Requires root or CAP_NET_BIND_SERVICE capability."
                ),
                context={"port_name": name, "port_value": port},
            )


def _validate_no_port_conflicts(result: ValidationResult) -> None:
    """Validate that configured ports don't conflict with each other."""
    ports = {
        "API": get_api_port(),
        "UI": get_ui_port(),
        "Grafana": DEFAULTS.GRAFANA,
    }

    # Check for conflicts
    seen = {}
    for name, port in ports.items():
        if port in seen:
            result.add_error(
                code="CFG-005",
                message=(
                    f"Port conflict: {name} ({port}) conflicts with {seen[port]} ({port})"
                ),
                context={"ports": {name: port, seen[port]: port}},
            )
        else:
            seen[port] = name


def _validate_port_availability(
    result: ValidationResult, check_ports: bool = False
) -> None:
    """
    Optionally check if ports are available for binding.

    This is disabled by default as it can cause issues if the service
    is already running or if called during reload.
    """
    if not check_ports:
        return

    ports_to_check = [
        ("API", get_api_port()),
    ]

    for name, port in ports_to_check:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("0.0.0.0", port))
            sock.close()
        except OSError:
            result.add_warning(
                code="CFG-006",
                message=(
                    f"{name} port {port} is already in use. "
                    "This may be expected if the service is reloading."
                ),
                context={"port_name": name, "port_value": port},
            )


def _validate_database_connection(result: ValidationResult) -> None:
    """Validate database connection settings."""
    db_host = os.environ.get("WTC_DB_HOST", "localhost")
    db_port = get_db_port()

    # Basic validation - we don't actually connect here
    if not db_host:
        result.add_error(
            code="CFG-007",
            message="Database host is empty",
        )

    # Check if in Docker and using localhost
    if os.path.exists("/.dockerenv") and db_host == "localhost":
        result.add_warning(
            code="CFG-008",
            message=(
                "Running in Docker but database host is 'localhost'. "
                "This typically should be the container name (e.g., 'database')."
            ),
        )


def _validate_config_file_consistency(result: ValidationResult) -> None:
    """Validate that runtime values match config file."""
    config = _load_config_defaults()
    if not config:
        return  # Already warned about missing config file

    runtime_vs_config = [
        ("WTC_API_PORT", get_api_port()),
        ("WTC_UI_PORT", get_ui_port()),
        ("WTC_DB_PORT", get_db_port()),
    ]

    for env_name, runtime_value in runtime_vs_config:
        config_value = config.get(env_name)
        if config_value and int(config_value) != runtime_value:
            # This means environment variable is overriding config file
            result.add_warning(
                code="CFG-009",
                message=(
                    f"{env_name} runtime value ({runtime_value}) differs from "
                    f"config file ({config_value}). Environment override in effect."
                ),
                context={
                    "variable": env_name,
                    "runtime": runtime_value,
                    "config_file": config_value,
                },
            )


def _validate_security_settings(result: ValidationResult) -> None:
    """Validate security-related configuration."""
    # Check for development-only settings in production
    if os.environ.get("WTC_ENV", "development") == "production":
        # Ensure debug mode is off
        if os.environ.get("WTC_DEBUG", "").lower() in ("true", "1", "yes"):
            result.add_error(
                code="SEC-001",
                message="Debug mode is enabled in production",
            )

        # Ensure CORS is not set to allow all origins
        cors_origins = os.environ.get("WTC_CORS_ORIGINS", "")
        if "*" in cors_origins:
            result.add_error(
                code="SEC-002",
                message="CORS allows all origins (*) in production",
            )

        # Check for default passwords
        db_password = os.environ.get("WTC_DB_PASSWORD", "")
        if db_password in ("", "password", "wtc_password", "admin"):
            result.add_error(
                code="SEC-003",
                message="Database password is empty or uses a default value",
            )


# -----------------------------------------------------------------------------
# Main Validation Function
# -----------------------------------------------------------------------------


def validate_configuration(
    check_port_availability: bool = False,
) -> ValidationResult:
    """
    Validate the application configuration.

    Args:
        check_port_availability: If True, check if ports are available for binding.
                                 Disabled by default to avoid issues during reload.

    Returns:
        ValidationResult with all errors and warnings found.

    Example:
        result = validate_configuration()
        if not result.is_valid:
            for error in result.errors:
                print(f"[{error.code}] {error.message}")
            sys.exit(1)
        for warning in result.warnings:
            print(f"[WARNING] [{warning.code}] {warning.message}")
    """
    result = ValidationResult()

    # Run all validation checks
    _validate_ports_env_exists(result)
    _validate_required_env_vars(result)
    _validate_port_values(result)
    _validate_no_port_conflicts(result)
    _validate_port_availability(result, check_port_availability)
    _validate_database_connection(result)
    _validate_config_file_consistency(result)
    _validate_security_settings(result)

    return result


def validate_or_exit(logger=None) -> None:
    """
    Validate configuration and exit if errors are found.

    This is a convenience function for use in application startup.

    Args:
        logger: Optional logger to use for output. If None, uses print().
    """
    import sys

    def log_error(msg: str) -> None:
        if logger:
            logger.error(msg)
        else:
            print(f"ERROR: {msg}", file=sys.stderr)

    def log_warning(msg: str) -> None:
        if logger:
            logger.warning(msg)
        else:
            print(f"WARNING: {msg}", file=sys.stderr)

    def log_info(msg: str) -> None:
        if logger:
            logger.info(msg)
        else:
            print(f"INFO: {msg}")

    result = validate_configuration()

    # Log warnings
    for warning in result.warnings:
        log_warning(f"[{warning.code}] {warning.message}")

    # Log errors and exit if any
    if not result.is_valid:
        for error in result.errors:
            log_error(f"[{error.code}] {error.message}")
        log_error("Configuration validation failed. Exiting.")
        sys.exit(1)

    log_info("Configuration validation passed")
