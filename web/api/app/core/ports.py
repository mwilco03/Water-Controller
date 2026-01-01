"""
Water Treatment Controller - Centralized Port Configuration

DRY-COMPLIANT PORT CONFIGURATION
================================
This module reads port defaults from config/ports.env to ensure a single
source of truth. Environment variables can still override at runtime.

Environment variables can override defaults:
- WTC_API_PORT: API server port (default: 8000)
- WTC_UI_PORT: UI server port (default: 8080)
- WTC_DB_PORT: Database port (default: 5432)

The config/ports.env file is the SINGLE SOURCE OF TRUTH for default values.
"""

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


# -----------------------------------------------------------------------------
# Load Defaults from Central Config File
# -----------------------------------------------------------------------------

def _find_ports_env() -> Optional[Path]:
    """
    Find the ports.env configuration file.

    Search order:
    1. WTC_CONFIG_DIR environment variable
    2. /opt/water-controller/config/ports.env (production)
    3. Relative paths from this file (development)
    """
    # Check explicit config directory
    config_dir = os.environ.get("WTC_CONFIG_DIR")
    if config_dir:
        path = Path(config_dir) / "ports.env"
        if path.exists():
            return path

    # Production location
    prod_path = Path("/opt/water-controller/config/ports.env")
    if prod_path.exists():
        return prod_path

    # Development: relative to this file
    # web/api/app/core/ports.py -> config/ports.env
    this_file = Path(__file__).resolve()
    dev_path = this_file.parent.parent.parent.parent.parent / "config" / "ports.env"
    if dev_path.exists():
        return dev_path

    return None


def _parse_ports_env(path: Path) -> dict[str, str]:
    """Parse a ports.env file and return key-value pairs."""
    result = {}
    try:
        content = path.read_text()
        for line in content.splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Parse KEY=VALUE
            match = re.match(r'^([A-Z_][A-Z0-9_]*)=(.*)$', line)
            if match:
                key, value = match.groups()
                # Handle ${VAR} references (just use value as-is for now)
                # Strip quotes if present
                value = value.strip('"').strip("'")
                result[key] = value
    except Exception:
        pass  # If file can't be read, return empty dict
    return result


@lru_cache(maxsize=1)
def _load_config_defaults() -> dict[str, str]:
    """Load defaults from ports.env file (cached)."""
    path = _find_ports_env()
    if path:
        return _parse_ports_env(path)
    return {}


def _get_default(key: str, fallback: int) -> int:
    """Get a default value from config file or use hardcoded fallback."""
    config = _load_config_defaults()
    if key in config:
        try:
            return int(config[key])
        except ValueError:
            pass
    return fallback


# -----------------------------------------------------------------------------
# Port Defaults (loaded from config/ports.env)
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class PortDefaults:
    """
    Default port numbers loaded from config/ports.env.

    IMPORTANT: The hardcoded fallbacks here should match config/ports.env
    and are only used if the config file cannot be found.
    """

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


# Create defaults with values from config file
DEFAULTS = PortDefaults(
    API=_get_default("WTC_API_PORT", 8000),
    UI=_get_default("WTC_UI_PORT", 8080),
    UI_HTTPS=_get_default("WTC_UI_HTTPS_PORT", 8443),
    DOCKER_UI_INTERNAL=_get_default("WTC_DOCKER_UI_INTERNAL_PORT", 3000),
    DATABASE=_get_default("WTC_DB_PORT", 5432),
    PROFINET_UDP=_get_default("WTC_PROFINET_UDP_PORT", 34964),
    PROFINET_TCP_START=_get_default("WTC_PROFINET_TCP_PORT_START", 34962),
    PROFINET_TCP_END=_get_default("WTC_PROFINET_TCP_PORT_END", 34963),
    MODBUS_TCP=_get_default("WTC_MODBUS_TCP_PORT", 1502),
    GRAYLOG=_get_default("WTC_GRAYLOG_PORT", 12201),
    REDIS=_get_default("WTC_REDIS_PORT", 6379),
    GRAFANA=_get_default("WTC_GRAFANA_PORT", 3000),
)


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

    Uses WTC_DATABASE_URL if set, otherwise constructs from components.
    """
    # Check for explicit database URL
    db_url = os.environ.get("WTC_DATABASE_URL")
    if db_url:
        return db_url

    # Construct from components
    host = get_db_host()
    port = get_db_port()
    user = os.environ.get("WTC_DB_USER", "wtc")
    password = os.environ.get("WTC_DB_PASSWORD", "")
    database = os.environ.get("WTC_DB_NAME", "water_treatment")

    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return f"postgresql://{user}@{host}:{port}/{database}"


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
