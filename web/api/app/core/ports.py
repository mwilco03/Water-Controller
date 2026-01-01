"""
Water Treatment Controller - Centralized Port Configuration

SINGLE SOURCE OF TRUTH for all network ports used by the backend.

All ports should be accessed through this module. Never hardcode port values
elsewhere in the codebase.

Environment variables can override defaults:
- WTC_API_PORT: API server port (default: 8000)
- WTC_UI_PORT: UI server port (default: 8080)
- WTC_DB_PORT: Database port (default: 5432)
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


# -----------------------------------------------------------------------------
# Port Defaults
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class PortDefaults:
    """Default port numbers - MODIFY ONLY HERE if changing defaults."""

    # FastAPI backend port
    API: int = 8000

    # Next.js UI port
    UI: int = 8080

    # UI HTTPS port (when TLS enabled)
    UI_HTTPS: int = 8443

    # Docker internal UI port
    DOCKER_UI_INTERNAL: int = 3000

    # PostgreSQL database port
    DATABASE: int = 5432

    # PROFINET UDP discovery
    PROFINET_UDP: int = 34964

    # PROFINET TCP range
    PROFINET_TCP_START: int = 34962
    PROFINET_TCP_END: int = 34963

    # Modbus TCP
    MODBUS_TCP: int = 1502

    # Graylog GELF
    GRAYLOG: int = 12201

    # Redis cache
    REDIS: int = 6379

    # Grafana
    GRAFANA: int = 3000


DEFAULTS = PortDefaults()


# -----------------------------------------------------------------------------
# Runtime Port Configuration
# -----------------------------------------------------------------------------

def get_api_port() -> int:
    """Get the API server port from environment or default."""
    return int(os.environ.get("WTC_API_PORT", DEFAULTS.API))


def get_ui_port() -> int:
    """Get the UI server port from environment or default."""
    return int(os.environ.get("WTC_UI_PORT", DEFAULTS.UI))


def get_db_port() -> int:
    """Get the database port from environment or default."""
    return int(os.environ.get("WTC_DB_PORT", DEFAULTS.DATABASE))


def get_db_host() -> str:
    """Get the database host from environment or default."""
    return os.environ.get("WTC_DB_HOST", "localhost")


def get_profinet_udp_port() -> int:
    """Get the PROFINET UDP port from environment or default."""
    return int(os.environ.get("WTC_PROFINET_UDP_PORT", DEFAULTS.PROFINET_UDP))


def get_modbus_tcp_port() -> int:
    """Get the Modbus TCP port from environment or default."""
    return int(os.environ.get("WTC_MODBUS_TCP_PORT", DEFAULTS.MODBUS_TCP))


# -----------------------------------------------------------------------------
# URL Construction
# -----------------------------------------------------------------------------

def get_api_url(host: Optional[str] = None) -> str:
    """
    Get the full API URL.

    Args:
        host: Override host (default: localhost)

    Returns:
        Full API URL like http://localhost:8000
    """
    _host = host or os.environ.get("WTC_API_HOST", "localhost")
    return f"http://{_host}:{get_api_port()}"


def get_ui_url(host: Optional[str] = None) -> str:
    """
    Get the full UI URL.

    Args:
        host: Override host (default: localhost)

    Returns:
        Full UI URL like http://localhost:8080
    """
    _host = host or os.environ.get("WTC_UI_HOST", "localhost")
    return f"http://{_host}:{get_ui_port()}"


def get_allowed_origins() -> list[str]:
    """
    Get CORS allowed origins based on configured ports.

    Returns:
        List of allowed origin URLs
    """
    # Check for explicit CORS origins
    cors_origins = os.environ.get("WTC_CORS_ORIGINS", "").strip()
    if cors_origins:
        return [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

    # Default: allow UI on configured port
    ui_port = get_ui_port()
    return [
        f"http://localhost:{ui_port}",
        f"http://127.0.0.1:{ui_port}",
    ]


def get_database_url() -> str:
    """
    Get the full database connection URL.

    Priority order:
    1. DATABASE_URL (Docker/production standard)
    2. WTC_DATABASE_URL (explicit override)
    3. Construct PostgreSQL URL from WTC_DB_* components
    4. Fall back to SQLite with WTC_DB_PATH

    For SQLite (development): sqlite:////var/lib/water-controller/wtc.db
    For PostgreSQL (production): postgresql://user:pass@host:port/database
    """
    # Check for explicit DATABASE_URL (Docker standard)
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        return db_url

    # Check for WTC-prefixed override
    db_url = os.environ.get("WTC_DATABASE_URL")
    if db_url:
        return db_url

    # Check if PostgreSQL components are configured
    db_host = os.environ.get("WTC_DB_HOST")
    if db_host:
        # Construct PostgreSQL URL from components
        port = get_db_port()
        user = os.environ.get("WTC_DB_USER", "wtc")
        password = os.environ.get("WTC_DB_PASSWORD", "")
        database = os.environ.get("WTC_DB_NAME", "water_treatment")

        if password:
            return f"postgresql://{user}:{password}@{db_host}:{port}/{database}"
        return f"postgresql://{user}@{db_host}:{port}/{database}"

    # Fall back to SQLite for local development
    db_path = os.environ.get("WTC_DB_PATH", "/var/lib/water-controller/wtc.db")
    return f"sqlite:///{db_path}"


# -----------------------------------------------------------------------------
# Configuration Class
# -----------------------------------------------------------------------------

@dataclass
class PortConfig:
    """Complete port configuration for the application."""

    api_port: int
    ui_port: int
    ui_https_port: int
    db_port: int
    db_host: str
    profinet_udp_port: int
    modbus_tcp_port: int
    api_url: str
    ui_url: str
    allowed_origins: list[str]

    @classmethod
    def from_environment(cls) -> "PortConfig":
        """Create configuration from environment variables."""
        return cls(
            api_port=get_api_port(),
            ui_port=get_ui_port(),
            ui_https_port=DEFAULTS.UI_HTTPS,
            db_port=get_db_port(),
            db_host=get_db_host(),
            profinet_udp_port=get_profinet_udp_port(),
            modbus_tcp_port=get_modbus_tcp_port(),
            api_url=get_api_url(),
            ui_url=get_ui_url(),
            allowed_origins=get_allowed_origins(),
        )


@lru_cache(maxsize=1)
def get_port_config() -> PortConfig:
    """Get the cached port configuration."""
    return PortConfig.from_environment()


# Convenience alias
PORTS = get_port_config
