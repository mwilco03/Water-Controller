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
from typing import Optional


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


class PathConfig:
    """
    Path configuration for installation directories and build artifacts.

    Single source of truth for all paths, matching scripts/lib/paths.sh.
    These paths are critical for:
    - UI build artifact validation
    - Health check endpoints
    - Service startup verification

    All values can be overridden via environment variables.
    """

    # Base installation directory
    INSTALL_BASE: str = os.environ.get("WTC_INSTALL_BASE", "/opt/water-controller")

    # Configuration directory
    CONFIG_DIR: str = os.environ.get("WTC_CONFIG_DIR", "/etc/water-controller")

    # Runtime state directory
    STATE_DIR: str = os.environ.get("WTC_STATE_DIR", "/var/lib/water-controller")

    # Log directory
    LOG_DIR: str = os.environ.get("WTC_LOG_DIR", "/var/log/water-controller")

    # Python virtual environment
    VENV_PATH: str = os.environ.get(
        "WTC_VENV_PATH",
        os.path.join(os.environ.get("WTC_INSTALL_BASE", "/opt/water-controller"), "venv")
    )

    # Backend paths
    API_PATH: str = os.environ.get(
        "WTC_API_PATH",
        os.path.join(os.environ.get("WTC_INSTALL_BASE", "/opt/water-controller"), "web/api")
    )

    # Database path (SQLite)
    DB_PATH: str = os.environ.get(
        "WTC_DB_PATH",
        os.path.join(os.environ.get("WTC_STATE_DIR", "/var/lib/water-controller"), "water_controller.db")
    )

    # Frontend (Next.js) paths - Critical for UI build validation
    UI_PATH: str = os.environ.get(
        "WTC_UI_PATH",
        os.path.join(os.environ.get("WTC_INSTALL_BASE", "/opt/water-controller"), "web/ui")
    )

    @classmethod
    def get_ui_next_dir(cls) -> str:
        """Get Next.js build output directory."""
        return os.environ.get("WTC_UI_NEXT_DIR", os.path.join(cls.UI_PATH, ".next"))

    @classmethod
    def get_ui_static_dir(cls) -> str:
        """Get Next.js static assets directory."""
        return os.environ.get("WTC_UI_STATIC_DIR", os.path.join(cls.get_ui_next_dir(), "static"))

    @classmethod
    def get_ui_standalone_dir(cls) -> str:
        """Get Next.js standalone server directory."""
        return os.environ.get("WTC_UI_STANDALONE_DIR", os.path.join(cls.get_ui_next_dir(), "standalone"))

    @classmethod
    def get_ui_server_js(cls) -> str:
        """Get Next.js server entry point."""
        return os.environ.get("WTC_UI_SERVER_JS", os.path.join(cls.UI_PATH, "server.js"))

    @classmethod
    def get_ui_public_dir(cls) -> str:
        """Get UI public assets directory."""
        return os.environ.get("WTC_UI_PUBLIC_DIR", os.path.join(cls.UI_PATH, "public"))

    # Service ports
    API_PORT: int = _get_int_env("WTC_API_PORT", 8080)
    UI_PORT: int = _get_int_env("WTC_UI_PORT", 3000)
    MODBUS_PORT: int = _get_int_env("WTC_MODBUS_PORT", 502)

    # Minimum expected file counts for UI validation
    MIN_STATIC_FILES: int = 10
    MIN_STANDALONE_FILES: int = 5

    @classmethod
    def validate_ui_build(cls) -> tuple[bool, str]:
        """
        Validate that UI build artifacts exist and are complete.

        Returns:
            Tuple of (is_valid, message)
        """
        static_dir = cls.get_ui_static_dir()
        server_js = cls.get_ui_server_js()

        # Check static directory exists
        if not os.path.isdir(static_dir):
            return False, f"Static assets directory missing: {static_dir}"

        # Check server.js exists
        if not os.path.isfile(server_js):
            return False, f"Server entry point missing: {server_js}"

        # Count JS files in static directory
        js_count = 0
        try:
            for root, _, files in os.walk(static_dir):
                for f in files:
                    if f.endswith('.js'):
                        js_count += 1
                        if js_count >= cls.MIN_STATIC_FILES:
                            break
                if js_count >= cls.MIN_STATIC_FILES:
                    break
        except OSError as e:
            return False, f"Error reading static directory: {e}"

        if js_count < cls.MIN_STATIC_FILES:
            return False, f"Insufficient JS bundles: found {js_count}, expected at least {cls.MIN_STATIC_FILES}"

        return True, f"UI build valid: {js_count}+ JS files found"


class Settings:
    """Aggregated settings for the application."""

    def __init__(self):
        self.timeouts = TimeoutConfig()
        self.polling = PollingConfig()
        self.circuit_breaker = CircuitBreakerConfig()
        self.historian = HistorianConfig()
        self.paths = PathConfig()

        # Convenience accessors for common values
        self.command_timeout_ms = self.timeouts.COMMAND_TIMEOUT_MS
        self.dcp_discovery_ms = self.timeouts.DCP_DISCOVERY_MS
        self.poll_interval_ms = self.polling.DEFAULT_POLL_INTERVAL_MS

        # Feature flags
        self.simulation_mode = _get_bool_env("WTC_SIMULATION_MODE", False)
        self.debug_mode = _get_bool_env("WTC_DEBUG", False)

    def validate_ui_build(self) -> tuple[bool, str]:
        """Validate UI build artifacts. Convenience wrapper."""
        return PathConfig.validate_ui_build()


# Singleton instance
settings = Settings()
