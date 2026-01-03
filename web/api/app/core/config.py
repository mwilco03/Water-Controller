"""
Water Treatment Controller - Configuration
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Centralized configuration with environment variable overrides.
All timeouts and tuning parameters are documented with their rationale.

Usage:
    from app.core.config import settings

    # Access values
    timeout = settings.command_timeout_ms
"""

import os


def _get_int_env(key: str, default: int) -> int:
    """Get integer from environment with default."""
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float_env(key: str, default: float) -> float:
    """Get float from environment with default."""
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_bool_env(key: str, default: bool) -> bool:
    """Get boolean from environment with default."""
    value = os.environ.get(key)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes")


class TimeoutConfig:
    """
    Timeout configuration for IPC and network operations.

    Rationale: These values were tuned for field conditions where
    network latency can reach 500ms due to industrial noise and
    shared memory access may be delayed by controller load.

    All values can be overridden via environment variables for
    site-specific tuning.
    """

    # Discovery timeout - how long to wait for DCP responses
    # Rationale: PROFINET DCP can take 2-3 seconds on congested networks
    DCP_DISCOVERY_MS: int = _get_int_env("WTC_DCP_DISCOVERY_MS", 5000)

    # Command execution timeout - max wait for actuator response
    # Rationale: Commands routed through RTU may take time to execute
    COMMAND_TIMEOUT_MS: int = _get_int_env("WTC_COMMAND_TIMEOUT_MS", 3000)

    # Shared memory read timeout
    # Rationale: Controller core may be busy with I/O cycle
    SHM_READ_TIMEOUT_MS: int = _get_int_env("WTC_SHM_READ_TIMEOUT_MS", 100)

    # WebSocket reconnect base interval
    # Rationale: Exponential backoff starts from this value
    WS_RECONNECT_BASE_MS: int = _get_int_env("WTC_WS_RECONNECT_MS", 1000)

    # Maximum WebSocket reconnect attempts
    WS_RECONNECT_MAX_ATTEMPTS: int = _get_int_env("WTC_WS_RECONNECT_ATTEMPTS", 10)

    # Database query timeout
    # Rationale: SQLite operations should be fast; long queries indicate issues
    DB_QUERY_TIMEOUT_MS: int = _get_int_env("WTC_DB_QUERY_TIMEOUT_MS", 5000)


class PollingConfig:
    """
    Polling configuration for UI updates.

    Rationale: Balance between responsiveness and power consumption
    for field deployments on constrained hardware.
    """

    # Default polling interval when WebSocket unavailable
    DEFAULT_POLL_INTERVAL_MS: int = _get_int_env("WTC_POLL_INTERVAL_MS", 5000)

    # Reduced polling interval when many RTUs are configured
    MANY_RTUS_POLL_INTERVAL_MS: int = _get_int_env("WTC_MANY_RTUS_POLL_MS", 10000)

    # RTU count threshold for switching to reduced polling
    MANY_RTUS_THRESHOLD: int = _get_int_env("WTC_MANY_RTUS_THRESHOLD", 10)


class CircuitBreakerConfig:
    """
    Circuit breaker configuration for resilience.

    Rationale: Prevent cascade failures when controller core
    becomes unresponsive.
    """

    # Number of failures before opening circuit
    FAILURE_THRESHOLD: int = _get_int_env("WTC_CB_FAILURE_THRESHOLD", 5)

    # Time to wait before attempting reset
    RESET_TIMEOUT_SECONDS: int = _get_int_env("WTC_CB_RESET_TIMEOUT", 30)

    # Number of successful calls to close circuit
    SUCCESS_THRESHOLD: int = _get_int_env("WTC_CB_SUCCESS_THRESHOLD", 3)


class HistorianConfig:
    """
    Historian configuration for data retention.

    Rationale: Balance storage usage with data retention needs
    for constrained deployments.
    """

    # Default sample retention period in days
    DEFAULT_RETENTION_DAYS: int = _get_int_env("WTC_HISTORIAN_RETENTION_DAYS", 90)

    # Maximum samples per tag (prevents unbounded growth)
    MAX_SAMPLES_PER_TAG: int = _get_int_env("WTC_HISTORIAN_MAX_SAMPLES", 1000000)


class RtuDefaults:
    """
    RTU default configuration values.

    Rationale: These defaults are based on standard PROFINET device
    configurations and can be overridden per-device at creation time.

    - VENDOR_ID 0x002A (42): Real-Time Automation (RTA) - common for
      water treatment PLCs
    - DEVICE_ID 0x0405 (1029): Generic PROFINET IO device
    - SLOT_COUNT 16: Typical modular RTU configuration
    """

    # Default PROFINET vendor ID (RTA = 0x002A = 42)
    VENDOR_ID: int = _get_int_env("WTC_DEFAULT_VENDOR_ID", 0x002A)

    # Default PROFINET device ID (generic = 0x0405 = 1029)
    DEVICE_ID: int = _get_int_env("WTC_DEFAULT_DEVICE_ID", 0x0405)

    # Default slot count for modular RTUs
    SLOT_COUNT: int = _get_int_env("WTC_DEFAULT_SLOT_COUNT", 16)


class Settings:
    """Aggregated settings for the application."""

    def __init__(self):
        self.timeouts = TimeoutConfig()
        self.polling = PollingConfig()
        self.circuit_breaker = CircuitBreakerConfig()
        self.historian = HistorianConfig()
        self.rtu_defaults = RtuDefaults()

        # Convenience accessors for common values
        self.command_timeout_ms = self.timeouts.COMMAND_TIMEOUT_MS
        self.dcp_discovery_ms = self.timeouts.DCP_DISCOVERY_MS
        self.poll_interval_ms = self.polling.DEFAULT_POLL_INTERVAL_MS

        # Feature flags
        self.simulation_mode = _get_bool_env("WTC_SIMULATION_MODE", False)
        self.debug_mode = _get_bool_env("WTC_DEBUG", False)


# Singleton instance
settings = Settings()
