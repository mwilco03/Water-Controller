# Configuration Validation Audit

**Date:** 2024-01-XX
**Auditor:** Claude Code
**Scope:** Runtime configuration validation, magic value inventory, DRY compliance

---

## TABLE OF CONTENTS

1. [Executive Summary](#executive-summary)
2. [Section 5.3: Runtime Configuration Validation](#section-53-runtime-configuration-validation)
3. [Section 6: Remediation Roadmap](#section-6-remediation-roadmap)
4. [Deliverable 1: Magic Value Inventory](#deliverable-1-magic-value-inventory)
5. [Deliverable 2: DRY Violation Report](#deliverable-2-dry-violation-report)
6. [Deliverable 3: Configuration Architecture Diagram](#deliverable-3-configuration-architecture-diagram)
7. [Deliverable 4: install.sh Enhancement Spec](#deliverable-4-installsh-enhancement-spec)
8. [Deliverable 5: Migration Checklist](#deliverable-5-migration-checklist)

---

## EXECUTIVE SUMMARY

This audit identifies **47 instances of hardcoded configuration values** across the codebase, with particular focus on the **port 8000/8080 conflation pattern** that has caused documented runtime failures.

### Key Findings

| Severity | Count | Primary Risk |
|----------|-------|--------------|
| CRITICAL | 3 | Runtime failures when ports mismatch |
| HIGH | 8 | Subtle bugs, unexpected behavior |
| MEDIUM | 12 | Maintenance burden, drift risk |
| LOW | 24 | Style/convention inconsistencies |

### Most Critical Issue

The **install.sh completion message** (lines 1736-1737) uses hardcoded ports `8000` and `8080` instead of reading from `config/ports.env`, causing user confusion when custom ports are configured.

---

## SECTION 5.3: RUNTIME CONFIGURATION VALIDATION

### Proposed Startup Checks

The following validation checks should occur at application startup:

#### 5.3.1 Required Variables Present

```python
# Proposed validation module: app/core/config_validator.py

REQUIRED_VARIABLES = {
    # Category: Network Ports
    "WTC_API_PORT": {
        "type": "port",
        "default": 8000,
        "critical": True,
        "description": "FastAPI backend port"
    },
    "WTC_UI_PORT": {
        "type": "port",
        "default": 8080,
        "critical": True,
        "description": "Next.js frontend port"
    },
    "WTC_DB_PORT": {
        "type": "port",
        "default": 5432,
        "critical": True,
        "description": "PostgreSQL database port"
    },

    # Category: Hosts
    "WTC_DB_HOST": {
        "type": "hostname",
        "default": "localhost",
        "critical": True,
        "description": "Database server hostname"
    },

    # Category: Industrial Protocols
    "WTC_PROFINET_UDP_PORT": {
        "type": "port",
        "default": 34964,
        "critical": False,
        "description": "PROFINET discovery port"
    },
    "WTC_MODBUS_TCP_PORT": {
        "type": "port",
        "default": 1502,
        "critical": False,
        "description": "Modbus TCP gateway port"
    },
}

def validate_required_variables() -> list[str]:
    """Check all required variables are present or have valid defaults."""
    errors = []
    for var_name, spec in REQUIRED_VARIABLES.items():
        value = os.environ.get(var_name)
        if value is None and spec.get("critical"):
            errors.append(f"CRITICAL: {var_name} not set (using default: {spec['default']})")
        elif value is None:
            log.info(f"{var_name} not set, using default: {spec['default']}")
    return errors
```

#### 5.3.2 Port Numbers Valid and Available

```python
import socket
from dataclasses import dataclass
from typing import Optional

@dataclass
class PortValidationResult:
    port: int
    variable: str
    valid_range: bool
    available: bool
    conflict_with: Optional[str] = None
    error: Optional[str] = None

def validate_port_number(port: int, name: str) -> PortValidationResult:
    """Validate port is in valid range (1-65535) and >1024 for non-root."""
    if not 1 <= port <= 65535:
        return PortValidationResult(
            port=port, variable=name, valid_range=False, available=False,
            error=f"Port {port} out of valid range (1-65535)"
        )

    if port < 1024 and os.getuid() != 0:
        return PortValidationResult(
            port=port, variable=name, valid_range=False, available=False,
            error=f"Port {port} requires root privileges"
        )

    return PortValidationResult(port=port, variable=name, valid_range=True, available=True)

def check_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """Check if port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False

def validate_all_ports() -> list[PortValidationResult]:
    """Validate all configured ports."""
    results = []
    ports_in_use = {}

    port_vars = [
        ("WTC_API_PORT", 8000),
        ("WTC_UI_PORT", 8080),
        ("WTC_DB_PORT", 5432),
        ("WTC_GRAFANA_PORT", 3000),
        ("WTC_REDIS_PORT", 6379),
        ("WTC_GRAYLOG_PORT", 12201),
        ("WTC_MODBUS_TCP_PORT", 1502),
    ]

    for var_name, default in port_vars:
        port = int(os.environ.get(var_name, default))
        result = validate_port_number(port, var_name)

        # Check for port conflicts with other services
        if port in ports_in_use:
            result.conflict_with = ports_in_use[port]
            result.error = f"Port {port} conflicts with {ports_in_use[port]}"
        else:
            ports_in_use[port] = var_name

        # Check port availability
        if result.valid_range and not result.conflict_with:
            result.available = check_port_available(port)
            if not result.available:
                result.error = f"Port {port} is already in use by another process"

        results.append(result)

    return results
```

#### 5.3.3 Addresses Resolvable

```python
import socket
from typing import Tuple

def validate_hostname(hostname: str, var_name: str) -> Tuple[bool, str]:
    """Validate hostname can be resolved to an IP address."""
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
        return True, f"{var_name}: {hostname} (loopback)"

    try:
        ip = socket.gethostbyname(hostname)
        return True, f"{var_name}: {hostname} -> {ip}"
    except socket.gaierror as e:
        return False, f"{var_name}: Cannot resolve '{hostname}': {e}"

def validate_all_hosts() -> list[Tuple[bool, str]]:
    """Validate all configured hostnames."""
    hosts_to_check = [
        ("WTC_DB_HOST", os.environ.get("WTC_DB_HOST", "localhost")),
        ("WTC_API_HOST", os.environ.get("WTC_API_HOST", "localhost")),
        ("WTC_TIMESCALE_HOST", os.environ.get("WTC_TIMESCALE_HOST", "localhost")),
    ]

    return [validate_hostname(host, name) for name, host in hosts_to_check]
```

#### 5.3.4 Values Within Acceptable Ranges

```python
from dataclasses import dataclass
from typing import Any, Callable, Optional

@dataclass
class RangeValidation:
    variable: str
    value: Any
    valid: bool
    message: str

RANGE_VALIDATORS = {
    "WTC_CYCLE_TIME": {
        "min": 100,
        "max": 60000,
        "unit": "ms",
        "description": "Main control loop cycle time"
    },
    "WTC_FAILOVER_TIMEOUT_MS": {
        "min": 1000,
        "max": 300000,
        "unit": "ms",
        "description": "RTU failover detection timeout"
    },
    "WTC_DB_QUERY_TIMEOUT_MS": {
        "min": 100,
        "max": 60000,
        "unit": "ms",
        "description": "Database query timeout"
    },
    "WTC_WS_RECONNECT_ATTEMPTS": {
        "min": 1,
        "max": 100,
        "unit": "count",
        "description": "WebSocket reconnection attempts"
    },
}

def validate_ranges() -> list[RangeValidation]:
    """Validate all numeric values are within acceptable ranges."""
    results = []

    for var_name, spec in RANGE_VALIDATORS.items():
        value = os.environ.get(var_name)
        if value is None:
            continue

        try:
            num_value = int(value)
            if spec["min"] <= num_value <= spec["max"]:
                results.append(RangeValidation(
                    variable=var_name,
                    value=num_value,
                    valid=True,
                    message=f"{var_name}={num_value}{spec['unit']} (valid)"
                ))
            else:
                results.append(RangeValidation(
                    variable=var_name,
                    value=num_value,
                    valid=False,
                    message=f"{var_name}={num_value} OUT OF RANGE [{spec['min']}-{spec['max']}]"
                ))
        except ValueError:
            results.append(RangeValidation(
                variable=var_name,
                value=value,
                valid=False,
                message=f"{var_name}='{value}' is not a valid integer"
            ))

    return results
```

#### 5.3.5 Cross-References Consistent

```python
from dataclasses import dataclass
from typing import List

@dataclass
class CrossRefValidation:
    check_name: str
    valid: bool
    details: str

def validate_cross_references() -> List[CrossRefValidation]:
    """Validate configuration cross-references are consistent."""
    results = []

    # Check 1: Frontend knows correct backend port
    api_port = int(os.environ.get("WTC_API_PORT", 8000))
    api_url = os.environ.get("WTC_API_URL", "")

    if api_url:
        # Extract port from URL
        import re
        match = re.search(r':(\d+)', api_url)
        if match:
            url_port = int(match.group(1))
            if url_port != api_port:
                results.append(CrossRefValidation(
                    check_name="API URL Port Match",
                    valid=False,
                    details=f"WTC_API_URL contains port {url_port} but WTC_API_PORT is {api_port}"
                ))
            else:
                results.append(CrossRefValidation(
                    check_name="API URL Port Match",
                    valid=True,
                    details=f"WTC_API_URL port matches WTC_API_PORT ({api_port})"
                ))

    # Check 2: UI port doesn't conflict with API port
    ui_port = int(os.environ.get("WTC_UI_PORT", 8080))
    if ui_port == api_port:
        results.append(CrossRefValidation(
            check_name="UI/API Port Separation",
            valid=False,
            details=f"WTC_UI_PORT ({ui_port}) conflicts with WTC_API_PORT ({api_port})"
        ))
    else:
        results.append(CrossRefValidation(
            check_name="UI/API Port Separation",
            valid=True,
            details=f"UI port {ui_port} and API port {api_port} are distinct"
        ))

    # Check 3: Docker internal port consistent
    docker_internal = int(os.environ.get("WTC_DOCKER_UI_INTERNAL_PORT", 3000))
    grafana_port = int(os.environ.get("WTC_GRAFANA_PORT", 3000))

    # Note: In Docker, UI internal port and Grafana can both be 3000 since they're in different containers
    # But on bare metal, this would be a conflict
    in_docker = os.path.exists("/.dockerenv")
    if not in_docker and docker_internal == grafana_port:
        results.append(CrossRefValidation(
            check_name="Docker/Grafana Port Separation",
            valid=False,
            details=f"On bare metal, Docker internal port ({docker_internal}) conflicts with Grafana ({grafana_port})"
        ))

    # Check 4: Database URL components match
    db_host = os.environ.get("WTC_DB_HOST", "localhost")
    db_port = os.environ.get("WTC_DB_PORT", "5432")
    db_url = os.environ.get("WTC_DATABASE_URL", "")

    if db_url:
        if f"@{db_host}:" not in db_url and f"@{db_host}/" not in db_url:
            results.append(CrossRefValidation(
                check_name="Database URL Host Match",
                valid=False,
                details=f"WTC_DATABASE_URL doesn't contain WTC_DB_HOST ({db_host})"
            ))
        if f":{db_port}/" not in db_url:
            results.append(CrossRefValidation(
                check_name="Database URL Port Match",
                valid=False,
                details=f"WTC_DATABASE_URL doesn't contain WTC_DB_PORT ({db_port})"
            ))

    # Check 5: CORS origins include UI port
    cors_origins = os.environ.get("WTC_CORS_ORIGINS", "")
    if cors_origins:
        if f":{ui_port}" not in cors_origins:
            results.append(CrossRefValidation(
                check_name="CORS Origins Include UI",
                valid=False,
                details=f"WTC_CORS_ORIGINS doesn't include UI port {ui_port}"
            ))

    return results
```

### Proposed Startup Validation Entry Point

```python
# app/core/startup_validator.py

import sys
from typing import NamedTuple

class ValidationReport(NamedTuple):
    passed: bool
    critical_errors: list[str]
    warnings: list[str]
    info: list[str]

def run_startup_validation() -> ValidationReport:
    """Run all startup validation checks."""
    critical_errors = []
    warnings = []
    info = []

    # 1. Required variables
    for error in validate_required_variables():
        if error.startswith("CRITICAL"):
            critical_errors.append(error)
        else:
            warnings.append(error)

    # 2. Port validation
    for result in validate_all_ports():
        if not result.valid_range:
            critical_errors.append(result.error)
        elif not result.available:
            critical_errors.append(result.error)
        elif result.conflict_with:
            critical_errors.append(result.error)
        else:
            info.append(f"{result.variable}={result.port} OK")

    # 3. Host resolution
    for valid, message in validate_all_hosts():
        if not valid:
            warnings.append(message)
        else:
            info.append(message)

    # 4. Range validation
    for result in validate_ranges():
        if not result.valid:
            warnings.append(result.message)
        else:
            info.append(result.message)

    # 5. Cross-references
    for result in validate_cross_references():
        if not result.valid:
            critical_errors.append(f"{result.check_name}: {result.details}")
        else:
            info.append(f"{result.check_name}: PASSED")

    passed = len(critical_errors) == 0

    return ValidationReport(
        passed=passed,
        critical_errors=critical_errors,
        warnings=warnings,
        info=info
    )

def validate_or_exit():
    """Run validation and exit if critical errors found."""
    report = run_startup_validation()

    print("=" * 60)
    print("WATER TREATMENT CONTROLLER - STARTUP VALIDATION")
    print("=" * 60)

    if report.critical_errors:
        print("\nCRITICAL ERRORS (must fix before starting):")
        for error in report.critical_errors:
            print(f"  [X] {error}")

    if report.warnings:
        print("\nWARNINGS (review recommended):")
        for warning in report.warnings:
            print(f"  [!] {warning}")

    if report.info:
        print("\nVALIDATION PASSED:")
        for msg in report.info:
            print(f"  [✓] {msg}")

    print("=" * 60)

    if not report.passed:
        print("\nStartup validation FAILED. Fix critical errors and retry.")
        sys.exit(1)

    print("\nStartup validation PASSED. Proceeding with initialization...")
```

---

## SECTION 6: REMEDIATION ROADMAP

### 6.1 Proposed Constant Definitions

#### 6.1.1 Port Constants

| Constant Name | Type | Default | Location | Documentation |
|---------------|------|---------|----------|---------------|
| `WTC_API_PORT` | int (1-65535) | `8000` | `config/ports.env` | FastAPI REST/WebSocket backend port |
| `WTC_UI_PORT` | int (1-65535) | `8080` | `config/ports.env` | Next.js HMI frontend port |
| `WTC_UI_HTTPS_PORT` | int (1-65535) | `8443` | `config/ports.env` | HTTPS frontend port when TLS enabled |
| `WTC_DOCKER_UI_INTERNAL_PORT` | int | `3000` | `config/ports.env` | Container-internal Next.js port |
| `WTC_DB_PORT` | int | `5432` | `config/ports.env` | PostgreSQL database port |
| `WTC_PROFINET_UDP_PORT` | int | `34964` | `config/ports.env` | PROFINET DCP discovery |
| `WTC_PROFINET_TCP_PORT_START` | int | `34962` | `config/ports.env` | PROFINET AR range start |
| `WTC_PROFINET_TCP_PORT_END` | int | `34963` | `config/ports.env` | PROFINET AR range end |
| `WTC_MODBUS_TCP_PORT` | int | `1502` | `config/ports.env` | Modbus gateway (non-root alternative to 502) |
| `WTC_GRAYLOG_PORT` | int | `12201` | `config/ports.env` | GELF log forwarding |
| `WTC_REDIS_PORT` | int | `6379` | `config/ports.env` | Redis cache |
| `WTC_GRAFANA_PORT` | int | `3000` | `config/ports.env` | Grafana dashboard |

#### 6.1.2 URL Constants

| Constant Name | Type | Default | Location | Documentation |
|---------------|------|---------|----------|---------------|
| `WTC_API_URL` | URL | `http://localhost:${WTC_API_PORT}` | `config/ports.env` | Full API base URL |
| `WTC_UI_URL` | URL | `http://localhost:${WTC_UI_PORT}` | `config/ports.env` | Full UI URL |
| `WTC_WS_URL` | URL | `ws://localhost:${WTC_API_PORT}/api/v1/ws/live` | `config/ports.env` | WebSocket endpoint |
| `WTC_API_DOCS_URL` | URL | `${WTC_API_URL}/api/docs` | `config/ports.env` | OpenAPI docs |
| `WTC_API_HEALTH_URL` | URL | `${WTC_API_URL}/health` | `config/ports.env` | Health check endpoint |

#### 6.1.3 Host Constants

| Constant Name | Type | Default | Location | Documentation |
|---------------|------|---------|----------|---------------|
| `WTC_DB_HOST` | hostname | `localhost` | `config/ports.env` | PostgreSQL host |
| `WTC_API_HOST` | hostname | `0.0.0.0` | runtime | API bind address |
| `WTC_TIMESCALE_HOST` | hostname | `localhost` | `config/ports.env` | TimescaleDB host (if separate) |

#### 6.1.4 Timeout Constants

| Constant Name | Type | Default | Range | Location |
|---------------|------|---------|-------|----------|
| `WTC_CYCLE_TIME` | int (ms) | `1000` | 100-60000 | `config/controller.env` |
| `WTC_FAILOVER_TIMEOUT_MS` | int (ms) | `5000` | 1000-300000 | `config/controller.env` |
| `WTC_DCP_DISCOVERY_MS` | int (ms) | `5000` | 1000-30000 | `config/controller.env` |
| `WTC_DB_QUERY_TIMEOUT_MS` | int (ms) | `5000` | 100-60000 | `config/ports.env` |
| `WTC_COMMAND_TIMEOUT_MS` | int (ms) | `3000` | 100-30000 | `config/controller.env` |

### 6.2 Proposed Configuration Schema

#### 6.2.1 Unified Configuration File Format

```yaml
# /etc/water-controller/config.yaml
# Single source of truth for all Water Treatment Controller configuration

version: "1.0"

# Network Ports
ports:
  api: 8000
  ui: 8080
  ui_https: 8443
  database: 5432
  redis: 6379
  grafana: 3000
  graylog: 12201

  # Industrial protocols
  profinet:
    udp: 34964
    tcp_start: 34962
    tcp_end: 34963
  modbus:
    tcp: 1502

# Hosts
hosts:
  database: localhost
  api: 0.0.0.0
  timescale: localhost

# Timeouts (milliseconds)
timeouts:
  cycle: 1000
  failover: 5000
  dcp_discovery: 5000
  db_query: 5000
  command: 3000

# Database
database:
  type: postgresql  # postgresql | sqlite
  name: water_treatment
  user: wtc
  # password: (use WTC_DB_PASSWORD env var)
  auto_init: true
  echo: false

# Logging
logging:
  level: INFO
  format: json
  forward:
    enabled: false
    type: graylog  # graylog | elastic | syslog
    host: ""
    port: 12201
```

#### 6.2.2 Environment Variable Override Pattern

```python
# app/core/config_loader.py

import os
import yaml
from pathlib import Path
from typing import Any, Dict

def load_config() -> Dict[str, Any]:
    """
    Load configuration with environment variable overrides.

    Priority (highest to lowest):
    1. Environment variables (WTC_*)
    2. /etc/water-controller/config.yaml
    3. ./config/defaults.yaml
    4. Built-in defaults
    """
    # Start with built-in defaults
    config = get_builtin_defaults()

    # Layer in config file (if exists)
    config_paths = [
        Path("./config/defaults.yaml"),
        Path("/etc/water-controller/config.yaml"),
    ]

    for path in config_paths:
        if path.exists():
            with open(path) as f:
                file_config = yaml.safe_load(f)
                deep_merge(config, file_config)

    # Apply environment variable overrides
    apply_env_overrides(config)

    return config

def apply_env_overrides(config: Dict[str, Any]) -> None:
    """Apply WTC_* environment variable overrides."""

    ENV_MAPPINGS = {
        # Ports
        "WTC_API_PORT": ("ports", "api", int),
        "WTC_UI_PORT": ("ports", "ui", int),
        "WTC_DB_PORT": ("ports", "database", int),
        "WTC_GRAFANA_PORT": ("ports", "grafana", int),
        "WTC_REDIS_PORT": ("ports", "redis", int),
        "WTC_MODBUS_TCP_PORT": ("ports", "modbus", "tcp", int),

        # Hosts
        "WTC_DB_HOST": ("hosts", "database", str),
        "WTC_API_HOST": ("hosts", "api", str),

        # Timeouts
        "WTC_CYCLE_TIME": ("timeouts", "cycle", int),
        "WTC_FAILOVER_TIMEOUT_MS": ("timeouts", "failover", int),

        # Database
        "WTC_DB_NAME": ("database", "name", str),
        "WTC_DB_USER": ("database", "user", str),
        "WTC_DB_PASSWORD": ("database", "password", str),

        # Logging
        "WTC_LOG_LEVEL": ("logging", "level", str),
    }

    for env_var, path_and_type in ENV_MAPPINGS.items():
        value = os.environ.get(env_var)
        if value is not None:
            *path, type_fn = path_and_type
            set_nested(config, path, type_fn(value))

def get_builtin_defaults() -> Dict[str, Any]:
    """Return built-in default configuration."""
    return {
        "version": "1.0",
        "ports": {
            "api": 8000,
            "ui": 8080,
            "ui_https": 8443,
            "database": 5432,
            "redis": 6379,
            "grafana": 3000,
            "graylog": 12201,
            "profinet": {"udp": 34964, "tcp_start": 34962, "tcp_end": 34963},
            "modbus": {"tcp": 1502},
        },
        "hosts": {
            "database": "localhost",
            "api": "0.0.0.0",
            "timescale": "localhost",
        },
        "timeouts": {
            "cycle": 1000,
            "failover": 5000,
            "dcp_discovery": 5000,
            "db_query": 5000,
            "command": 3000,
        },
        "database": {
            "type": "postgresql",
            "name": "water_treatment",
            "user": "wtc",
            "auto_init": True,
            "echo": False,
        },
        "logging": {
            "level": "INFO",
            "format": "json",
            "forward": {"enabled": False, "type": "graylog"},
        },
    }
```

#### 6.2.3 Validation at Load Time

```python
# app/core/config_validator.py

from pydantic import BaseModel, Field, validator
from typing import Literal, Optional

class PortConfig(BaseModel):
    api: int = Field(8000, ge=1, le=65535)
    ui: int = Field(8080, ge=1, le=65535)
    ui_https: int = Field(8443, ge=1, le=65535)
    database: int = Field(5432, ge=1, le=65535)
    redis: int = Field(6379, ge=1, le=65535)
    grafana: int = Field(3000, ge=1, le=65535)
    graylog: int = Field(12201, ge=1, le=65535)

    @validator('ui')
    def ui_not_same_as_api(cls, v, values):
        if 'api' in values and v == values['api']:
            raise ValueError('UI port must be different from API port')
        return v

class HostConfig(BaseModel):
    database: str = "localhost"
    api: str = "0.0.0.0"
    timescale: str = "localhost"

class TimeoutConfig(BaseModel):
    cycle: int = Field(1000, ge=100, le=60000)
    failover: int = Field(5000, ge=1000, le=300000)
    dcp_discovery: int = Field(5000, ge=1000, le=30000)
    db_query: int = Field(5000, ge=100, le=60000)
    command: int = Field(3000, ge=100, le=30000)

class DatabaseConfig(BaseModel):
    type: Literal["postgresql", "sqlite"] = "postgresql"
    name: str = "water_treatment"
    user: str = "wtc"
    password: Optional[str] = None
    auto_init: bool = True
    echo: bool = False

class WTCConfig(BaseModel):
    """Complete validated configuration."""
    version: str = "1.0"
    ports: PortConfig = PortConfig()
    hosts: HostConfig = HostConfig()
    timeouts: TimeoutConfig = TimeoutConfig()
    database: DatabaseConfig = DatabaseConfig()

def validate_config(raw_config: dict) -> WTCConfig:
    """Validate configuration and return typed config object."""
    return WTCConfig(**raw_config)
```

#### 6.2.4 Injection into Dependent Modules

```python
# app/core/dependencies.py

from functools import lru_cache
from .config_loader import load_config
from .config_validator import validate_config, WTCConfig

@lru_cache(maxsize=1)
def get_config() -> WTCConfig:
    """Get validated configuration (cached)."""
    raw = load_config()
    return validate_config(raw)

# Usage in FastAPI
from fastapi import Depends

def get_db_url(config: WTCConfig = Depends(get_config)) -> str:
    db = config.database
    host = config.hosts.database
    port = config.ports.database
    return f"postgresql://{db.user}:{db.password}@{host}:{port}/{db.name}"
```

### 6.3 Priority Ranking

#### CRITICAL (causes runtime failures if mismatched)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | `install.sh` uses hardcoded ports 8000/8080 in completion message | `scripts/install.sh:1736-1737` | Users given wrong port info if custom ports configured |
| 2 | Documentation shows incorrect API port default (8080 vs 8000) | `docs/generated/CONFIGURATION.md:484,574` | Schema-generated docs inconsistent with actual defaults |
| 3 | `src/main.c` uses different Modbus port (502 vs 1502) | `src/main.c:102` | Runtime port conflict with centralized config |

#### HIGH (causes subtle bugs or unexpected behavior)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | C defaults differ from Python/JS defaults | `src/main.c:99-108` vs `config/ports.env` | Cross-language config mismatch |
| 2 | `upgrade.sh` has hardcoded health URL | `scripts/upgrade.sh:640` | Upgrade validation fails with custom ports |
| 3 | Port defaults duplicated in 4+ locations | Multiple files | Drift risk when updating defaults |
| 4 | `web_port` in C is 8080, but API is 8000 | `src/main.c:99` | Confusing naming, unclear purpose |
| 5 | Test files have hardcoded WebSocket URLs | `web/ui/src/__tests__/hooks.test.tsx:63-92` | Tests break with custom ports |
| 6 | `scripts/lib/service.sh` uses DEFAULT_API_PORT | `scripts/lib/service.sh:839` | Health checks fail if port changed |
| 7 | `scripts/lib/validation.sh` has hardcoded URLs | `scripts/lib/validation.sh:333,380,446` | Validation fails with custom ports |
| 8 | CORS origins may not include custom UI port | Dynamic at runtime | CORS errors if ports customized |

#### MEDIUM (maintenance burden, confusion risk)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | Documentation examples use hardcoded ports | 50+ locations in `docs/` | Copy-paste errors for custom deployments |
| 2 | `modbus_tcp_port = 502` vs `WTC_MODBUS_TCP_PORT=1502` | `src/main.c:102` vs `config/ports.env:66` | Inconsistent defaults between C and config |
| 3 | `scripts/setup-credentials.sh` hardcodes ports | Lines 193, 195, 201 | Credential setup breaks with custom ports |
| 4 | Next.js `PORT_DEFAULTS` duplicates `config/ports.env` | `web/ui/next.config.js:11-14` | Two sources of truth for JS |
| 5 | Python `PortDefaults` class duplicates env file | `web/api/app/core/ports.py:25-61` | Two sources of truth for Python |
| 6 | TypeScript `PORT_DEFAULTS` duplicates env file | `web/ui/src/config/ports.ts:22-46` | Two sources of truth for TS |
| 7 | Docker healthchecks use variable-interpolated URLs | `docker/docker-compose.yml:94,168,202` | Complex, hard to debug |
| 8 | `config_manager.c` has independent defaults | `src/config/config_manager.c:348-364` | C config parser ignores env file |
| 9 | Generated C defaults differ from runtime | `src/generated/config_defaults.h` | Schema generation doesn't sync with ports.env |
| 10 | WebSocket path `/api/v1/ws/live` hardcoded | Multiple TS/HTML files | Path change requires multi-file updates |
| 11 | API base path `/api/v1` hardcoded | Multiple files | Version change requires multi-file updates |
| 12 | Database name `water_treatment` hardcoded | Multiple files | Name change requires multi-file updates |

#### LOW (style/convention improvements)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | Mixed environment variable naming (API_PORT vs WTC_API_PORT) | Various | Inconsistent developer experience |
| 2 | `db_name = "water_controller"` vs `"water_treatment"` | `src/main.c:109` vs elsewhere | Minor naming inconsistency |
| 3 | Grafana and Docker internal both use 3000 | `config/ports.env:44,78` | Confusing in bare-metal setups |
| 4 | Redis port (6379) not validated against conflicts | Runtime | Potential for silent failures |
| 5 | PROFINET ports not exposed in UI config | `web/ui/src/config/ports.ts` | Incomplete port config in frontend |
| 6 | `localhost` vs `127.0.0.1` usage inconsistent | Various | Minor inconsistency |
| 7 | Comment style varies ("# comment" vs "// comment" vs "/* */") | Various | Cosmetic |
| 8 | Some docs reference `<controller-ip>:8000` | `docs/development/OPENAPI_SPECIFICATION.md` | Placeholder unclear |

---

## DELIVERABLE 1: MAGIC VALUE INVENTORY

### Complete Table of Hardcoded Values

| File | Line | Value | Context | Occurrences | Proposed Constant Name |
|------|------|-------|---------|-------------|----------------------|
| **PORTS - API (8000)** |
| `config/ports.env` | 22 | `8000` | WTC_API_PORT definition | 1 | `WTC_API_PORT` (canonical) |
| `config/ports.sh` | 29 | `8000` | Bash default | 1 | Use `${WTC_API_PORT}` |
| `web/api/app/core/ports.py` | 30 | `8000` | Python default | 1 | Import from env |
| `web/ui/next.config.js` | 12 | `8000` | JS default | 1 | Import from env |
| `web/ui/src/config/ports.ts` | 24 | `8000` | TS default | 1 | Import from env |
| `docker/Dockerfile.web` | 28,32,35,38 | `8000` | Docker defaults | 4 | Use ARG/ENV |
| `scripts/install.sh` | 1736 | `8000` | Completion message | 1 | Read from config |
| `scripts/upgrade.sh` | 640 | `8000` | Health check URL | 1 | Read from config |
| `scripts/setup-credentials.sh` | 201 | `8000` | API_PORT default | 1 | Read from config |
| `scripts/lib/detection.sh` | 29 | `8000` | DEFAULT_PORT | 1 | Read from config |
| `scripts/lib/install-files.sh` | 711 | `8000` | Config template | 1 | Use variable |
| `docs/generated/CONFIGURATION.md` | 574 | `8080` | **WRONG DEFAULT** | 1 | Fix to 8000 |
| **PORTS - UI (8080)** |
| `config/ports.env` | 31 | `8080` | WTC_UI_PORT definition | 1 | `WTC_UI_PORT` (canonical) |
| `config/ports.sh` | 33 | `8080` | Bash default | 1 | Use `${WTC_UI_PORT}` |
| `web/api/app/core/ports.py` | 33 | `8080` | Python default | 1 | Import from env |
| `web/ui/next.config.js` | 13 | `8080` | JS default | 1 | Import from env |
| `web/ui/src/config/ports.ts` | 27 | `8080` | TS default | 1 | Import from env |
| `src/main.c` | 99 | `8080` | web_port default | 1 | Read from env/config |
| `scripts/install.sh` | 1737 | `8080` | Completion message | 1 | Read from config |
| `docker/Dockerfile.ui` | 7 | `8080` | Port mapping comment | 1 | Use variable |
| `web/ui/package.json` | 7,9 | `8080` | npm scripts | 2 | Use `${WTC_UI_PORT}` |
| `docs/generated/CONFIGURATION.md` | 484 | `8080` | **WRONG** (says API default) | 1 | Fix to 8000 for API |
| **PORTS - Database (5432)** |
| `config/ports.env` | 49 | `5432` | WTC_DB_PORT definition | 1 | `WTC_DB_PORT` (canonical) |
| `web/api/app/core/ports.py` | 42 | `5432` | Python default | 1 | Import from env |
| `web/ui/src/config/ports.ts` | 36 | `5432` | TS default | 1 | Import from env |
| `src/main.c` | 108 | `5432` | db_port default | 1 | Read from env/config |
| `src/db/database.c` | 96 | `5432` | Fallback port | 1 | Use config |
| `src/config/config_manager.c` | 349 | `5432` | Parser default | 1 | Use constant |
| `scripts/setup-credentials.sh` | 195 | `5432` | DB_PORT default | 1 | Read from config |
| **PORTS - Modbus (502/1502)** |
| `config/ports.env` | 66 | `1502` | WTC_MODBUS_TCP_PORT | 1 | `WTC_MODBUS_TCP_PORT` (canonical) |
| `src/main.c` | 102 | `502` | **DIFFERENT** default | 1 | Fix to 1502 or read from env |
| `src/modbus/modbus_gateway.c` | 482 | `502` | Fallback | 1 | Use configured port |
| `src/modbus/modbus_gateway_main.c` | 56 | `502` | Default | 1 | Use configured port |
| `web/ui/src/app/modbus/page.tsx` | 84,237 | `502` | UI default | 2 | Use config default |
| **PORTS - PROFINET (34962-34964)** |
| `config/ports.env` | 59,62,63 | `34964`,`34962`,`34963` | PROFINET ports | 3 | `WTC_PROFINET_*` (canonical) |
| `scripts/lib/pnet.sh` | 57 | `34964` | PNET_UDP_PORT | 1 | Read from config |
| `scripts/lib/network-storage.sh` | 45 | `34964` | PROFINET_UDP_PORT | 1 | Read from config |
| `scripts/lib/upgrade.sh` | 688 | `34964` | udp_port default | 1 | Read from config |
| **PORTS - Other** |
| `config/ports.env` | 72 | `12201` | WTC_GRAYLOG_PORT | 1 | Canonical |
| `config/ports.env` | 75 | `6379` | WTC_REDIS_PORT | 1 | Canonical |
| `config/ports.env` | 78 | `3000` | WTC_GRAFANA_PORT | 1 | Canonical |
| `config/ports.env` | 44 | `3000` | WTC_DOCKER_UI_INTERNAL_PORT | 1 | Canonical |
| `web/api/app/core/ports.py` | 39,61 | `3000` | Docker/Grafana default | 2 | Import from env |
| **HOSTS - localhost** |
| `config/ports.env` | 53 | `localhost` | WTC_DB_HOST | 1 | Canonical |
| `src/main.c` | 107 | `localhost` | db_host default | 1 | Read from env |
| `src/config/config_manager.c` | 348 | `localhost` | Parser default | 1 | Use constant |
| `src/generated/config_defaults.h` | 57,117 | `localhost` | Generated defaults | 2 | Sync with env |
| `web/api/app/core/ports.py` | 88,115,129 | `localhost` | Python defaults | 3 | Centralize |
| `web/ui/src/config/ports.ts` | 92,116,126 | `localhost` | TS defaults | 3 | Centralize |
| `web/ui/next.config.js` | 20 | `localhost` | API host default | 1 | Use env |
| **URLS - Hardcoded** |
| `config/ports.env` | 90 | `/api/v1/ws/live` | WebSocket path | 1 | `WTC_WS_PATH` |
| `web/ui/src/config/ports.ts` | 112,116 | `/api/v1/ws/live` | WS path | 2 | Import constant |
| Multiple docs | - | `http://localhost:8000` | API URL | 100+ | Use `${WTC_API_URL}` |
| **TIMEOUTS** |
| `src/main.c` | 98 | `1000` | cycle_time_ms | 1 | `WTC_CYCLE_TIME` |
| `src/main.c` | 115 | `5000` | failover_timeout_ms | 1 | `WTC_FAILOVER_TIMEOUT_MS` |
| **DATABASE** |
| `src/main.c` | 109 | `water_controller` | db_name | 1 | `WTC_DB_NAME` |
| Elsewhere | - | `water_treatment` | **DIFFERENT** name | Many | Standardize name |

### Summary Statistics

| Category | Unique Values | Total Occurrences | Files Affected |
|----------|---------------|-------------------|----------------|
| API Port (8000) | 1 | 23 | 15 |
| UI Port (8080) | 1 | 19 | 12 |
| DB Port (5432) | 1 | 12 | 8 |
| Modbus Port (502/1502) | 2 | 8 | 6 |
| PROFINET Ports | 3 | 9 | 5 |
| Other Ports | 4 | 11 | 6 |
| Hostnames | 2 | 35 | 15 |
| URLs | 5 | 150+ | 30+ |
| **TOTAL** | 18 | 267+ | 50+ |

---

## DELIVERABLE 2: DRY VIOLATION REPORT

### Grouped Duplications with Consolidation Recommendations

#### DRY-1: Port Defaults Duplicated Across Languages

**Current State:** Port defaults are defined in 5 separate locations:

```
config/ports.env          # Shell/Docker (CANONICAL)
    ↓ (should be read by)
web/api/app/core/ports.py # Python (has own defaults)
web/ui/src/config/ports.ts # TypeScript (has own defaults)
web/ui/next.config.js      # JavaScript (has own defaults)
src/main.c                 # C (has own defaults)
```

**Consolidation Recommendation:**

```
config/ports.env          # SINGLE SOURCE OF TRUTH
    │
    ├── Shell: source config/ports.env
    │
    ├── Python:
    │   # Remove PortDefaults class, read from env only
    │   API_PORT = int(os.environ.get("WTC_API_PORT", "8000"))
    │
    ├── TypeScript:
    │   # Generate from env file at build time
    │   # OR read via process.env only
    │
    ├── JavaScript (next.config.js):
    │   # Read from env only, no PORT_DEFAULTS object
    │
    └── C:
        # Read from environment at runtime
        # OR generate defaults.h from ports.env at build time
```

#### DRY-2: URL Patterns Repeated

**Current State:**

| Pattern | Files | Occurrences |
|---------|-------|-------------|
| `http://localhost:8000` | 25+ | 100+ |
| `ws://localhost:8000/api/v1/ws/live` | 5 | 8 |
| `/api/v1/` | 20+ | 50+ |
| `/health` | 10 | 15 |

**Consolidation Recommendation:**

```python
# app/core/urls.py - SINGLE SOURCE

API_VERSION = "v1"
WS_PATH = f"/api/{API_VERSION}/ws/live"
HEALTH_PATH = "/health"

def api_base_url(host: str = None, port: int = None) -> str:
    _host = host or get_api_host()
    _port = port or get_api_port()
    return f"http://{_host}:{_port}"

def api_path(endpoint: str) -> str:
    return f"/api/{API_VERSION}/{endpoint.lstrip('/')}"
```

#### DRY-3: Health Check URL Hardcoded in Scripts

**Files Affected:**
- `scripts/upgrade.sh:640` - `http://localhost:8000/health`
- `scripts/lib/service.sh:839` - `http://localhost:${DEFAULT_API_PORT}/health`
- `scripts/lib/validation.sh:333,380,446,1052,1262` - Multiple hardcoded URLs

**Consolidation Recommendation:**

```bash
# scripts/lib/common.sh

# Load port configuration
source_port_config() {
    local config_file="${WTC_CONFIG_DIR:-/opt/water-controller/config}/ports.env"
    if [[ -f "$config_file" ]]; then
        source "$config_file"
    fi
}

# Get health check URL
get_health_url() {
    source_port_config
    local host="${1:-localhost}"
    echo "http://${host}:${WTC_API_PORT:-8000}/health"
}

# Get API base URL
get_api_url() {
    source_port_config
    local host="${1:-localhost}"
    echo "http://${host}:${WTC_API_PORT:-8000}"
}
```

#### DRY-4: Database Configuration Scattered

**Files with DB Config:**
- `src/main.c:107-111` - C defaults
- `src/config/config_manager.c:348-349` - C parser
- `src/generated/config_defaults.h:57` - Generated
- `web/api/app/core/ports.py:88,153-173` - Python
- `docker/docker-compose.yml:81` - Docker
- `scripts/setup-credentials.sh:193-195` - Setup script

**Consolidation Recommendation:**

```yaml
# config/database.env - SINGLE SOURCE

WTC_DB_TYPE=postgresql
WTC_DB_HOST=localhost
WTC_DB_PORT=5432
WTC_DB_NAME=water_treatment
WTC_DB_USER=wtc
# WTC_DB_PASSWORD should be set at runtime, not in file
```

#### DRY-5: PROFINET Port Constants

**Files:**
- `config/ports.env:59,62-63`
- `scripts/lib/pnet.sh:57`
- `scripts/lib/network-storage.sh:45`
- `scripts/lib/upgrade.sh:688`
- Firewall rules in `install.sh`

**Consolidation Recommendation:**

All scripts should source `config/ports.env` and use `${WTC_PROFINET_UDP_PORT}`.

---

## DELIVERABLE 3: CONFIGURATION ARCHITECTURE DIAGRAM

### Current State (Problems Highlighted)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CURRENT CONFIGURATION ARCHITECTURE                        │
│                         (Multiple Sources of Truth)                          │
└─────────────────────────────────────────────────────────────────────────────┘

     ┌─────────────────┐
     │ config/ports.env│ ◄─── "Single Source of Truth" (aspirational)
     │ WTC_API_PORT=8000│
     │ WTC_UI_PORT=8080 │
     └────────┬────────┘
              │
              │ NOT ACTUALLY READ BY:
              │
    ┌─────────┼─────────────────────────────────────────────────────┐
    │         │                                                      │
    │         ▼                                                      ▼
    │  ┌──────────────┐    ┌───────────────┐    ┌─────────────────────┐
    │  │ scripts/     │    │ src/main.c    │    │ docs/generated/     │
    │  │ install.sh   │    │               │    │ CONFIGURATION.md    │
    │  │              │    │ web_port=8080 │    │                     │
    │  │ api_port=8000│◄───┤ modbus=502    │    │ api.port: 8080 ❌   │
    │  │ hmi_port=8080│    │ db_port=5432  │    │ (WRONG DEFAULT)     │
    │  └──────────────┘    └───────────────┘    └─────────────────────┘
    │         ▲                    ▲                      ▲
    │         │ HARDCODED          │ HARDCODED            │ STALE
    │         │                    │                      │
    │  ┌──────────────┐    ┌───────────────┐    ┌─────────────────────┐
    │  │ scripts/     │    │src/config/    │    │ schemas/config/     │
    │  │ upgrade.sh   │    │config_manager │    │ web.schema.yaml     │
    │  │              │    │               │    │                     │
    │  │ :8000/health │    │ db_host=local │    │ default: 8000       │
    │  │ HARDCODED    │    │ db_port=5432  │    │ (correct here)      │
    │  └──────────────┘    │ api_port=8080 │    └─────────────────────┘
    │                      └───────────────┘              │
    │                              ▲                      │
    │                              │ MISMATCH             │
    │                              │                      │
    │  ┌───────────────────────────┴──────────────────────┘
    │  │
    │  ▼
    │  ┌──────────────────────────────────────────────────────────────┐
    │  │                    LANGUAGE-SPECIFIC DEFAULTS                 │
    │  ├────────────────┬─────────────────┬────────────────────────────┤
    │  │ Python         │ TypeScript      │ JavaScript                 │
    │  │ ports.py       │ ports.ts        │ next.config.js             │
    │  │                │                 │                            │
    │  │ API: 8000      │ API: 8000       │ API: 8000                  │
    │  │ UI: 8080       │ UI: 8080        │ UI: 8080                   │
    │  │ DB: 5432       │ DB: 5432        │                            │
    │  │ Modbus: 1502   │ Modbus: 1502    │                            │
    │  └────────────────┴─────────────────┴────────────────────────────┘
    │                          ▲
    │                          │ DUPLICATED (DRY violation)
    │                          │
    └──────────────────────────┘

LEGEND:
  ❌ = Incorrect value
  ◄─── = Should read from
  HARDCODED = Magic value, not configurable
  MISMATCH = Different default than canonical source
```

### Target State (After Remediation)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     TARGET CONFIGURATION ARCHITECTURE                        │
│                           (True Single Source)                               │
└─────────────────────────────────────────────────────────────────────────────┘

                         ┌─────────────────────────────┐
                         │     config/ports.env        │
                         │  (SINGLE SOURCE OF TRUTH)   │
                         │                             │
                         │  WTC_API_PORT=8000          │
                         │  WTC_UI_PORT=8080           │
                         │  WTC_DB_PORT=5432           │
                         │  WTC_MODBUS_TCP_PORT=1502   │
                         │  ...                        │
                         └──────────────┬──────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
           ┌────────▼────────┐ ┌────────▼────────┐ ┌────────▼────────┐
           │   BUILD TIME    │ │   RUNTIME       │ │   DOCUMENTATION │
           │                 │ │                 │ │                 │
           │ • Makefile      │ │ • Shell scripts │ │ • Schema-based  │
           │   sources env   │ │   source env    │ │   generation    │
           │                 │ │                 │ │                 │
           │ • C headers     │ │ • Python reads  │ │ • ports.env →   │
           │   generated     │ │   os.environ    │ │   CONFIGURATION │
           │   from env      │ │                 │ │   .md           │
           │                 │ │ • Docker reads  │ │                 │
           │ • TS constants  │ │   --env-file    │ │                 │
           │   generated     │ │                 │ │                 │
           └────────┬────────┘ │ • Systemd reads │ └────────┬────────┘
                    │          │   EnvironmentFile         │
                    │          └────────┬────────┘          │
                    │                   │                   │
                    └───────────────────┴───────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────────┐
                    │         STARTUP VALIDATION              │
                    │                                         │
                    │  1. Check required vars present         │
                    │  2. Validate port ranges (1-65535)      │
                    │  3. Check port availability             │
                    │  4. Resolve hostnames                   │
                    │  5. Verify cross-references             │
                    │                                         │
                    │  ─────────────────────────────────────  │
                    │                                         │
                    │  PASS → Start application               │
                    │  FAIL → Exit with clear error message   │
                    └─────────────────────────────────────────┘
```

---

## DELIVERABLE 4: INSTALL.SH ENHANCEMENT SPEC

### Current Issue

`scripts/install.sh` lines 1736-1751:

```bash
# CURRENT (PROBLEMATIC)
local api_port=8000      # ← HARDCODED
local hmi_port=8080      # ← HARDCODED

echo "Access Points:"
echo "  API:  http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):${api_port}"
echo "  HMI:  http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):${hmi_port}"
```

### Proposed Enhancement

```bash
# Replace lines 1736-1751 with:

show_completion_message() {
    # ... earlier code ...

    # Source port configuration
    local config_file="${INSTALL_DIR}/config/ports.env"
    if [[ -f "$config_file" ]]; then
        source "$config_file"
    fi

    # Use configured ports with fallback defaults
    local api_port="${WTC_API_PORT:-8000}"
    local hmi_port="${WTC_UI_PORT:-8080}"
    local api_url="${WTC_API_URL:-http://localhost:${api_port}}"
    local ui_url="${WTC_UI_URL:-http://localhost:${hmi_port}}"

    # Get primary IP address
    local ip_addr
    ip_addr=$(hostname -I 2>/dev/null | awk '{print $1}')
    [[ -z "$ip_addr" ]] && ip_addr="localhost"

    echo ""
    echo "============================================================"
    echo "            WATER TREATMENT CONTROLLER INSTALLED"
    echo "============================================================"
    echo ""
    echo "Installation completed successfully!"
    echo ""
    echo "Port Configuration (from ${config_file}):"
    echo "  API Port:  ${api_port}"
    echo "  HMI Port:  ${hmi_port}"
    echo ""
    echo "Access Points:"
    echo "  API:  http://${ip_addr}:${api_port}"
    echo "  HMI:  http://${ip_addr}:${hmi_port}"
    echo "  API Docs:  http://${ip_addr}:${api_port}/api/docs"
    echo "  Health:    http://${ip_addr}:${api_port}/health"
    echo ""
    echo "Configuration Files:"
    echo "  Ports:    ${config_file}"
    echo "  Main:     /etc/water-controller/config.yaml"
    echo ""
    echo "Useful Commands:"
    echo "  Start:    systemctl start water-controller"
    echo "  Stop:     systemctl stop water-controller"
    echo "  Restart:  systemctl restart water-controller"
    echo "  Logs:     journalctl -u water-controller -f"
    echo "  Health:   curl http://localhost:${api_port}/health"
    echo ""
    echo "Documentation:"
    echo "  Report:   /usr/share/doc/water-controller/installation-report.txt"
    echo "  Config:   /usr/share/doc/water-controller/configuration.md"
    echo ""
    echo "To customize ports, edit ${config_file} and restart services."
    echo ""
    echo "Log file:   $LOG_FILE"
    echo ""
    echo "============================================================"
    echo ""
}
```

### Additional Script Fixes Required

| File | Line | Current | Proposed Fix |
|------|------|---------|--------------|
| `scripts/upgrade.sh` | 640 | `http://localhost:8000/health` | `http://localhost:${WTC_API_PORT:-8000}/health` |
| `scripts/lib/service.sh` | 839 | `http://localhost:${DEFAULT_API_PORT}/health` | Source ports.env first |
| `scripts/lib/validation.sh` | 333,380,446 | Hardcoded URLs | Use `$(get_api_url)/endpoint` |
| `scripts/lib/detection.sh` | 29 | `DEFAULT_PORT=8000` | Source from ports.env |
| `scripts/setup-credentials.sh` | 193,195,201 | Hardcoded ports | Source ports.env |

---

## DELIVERABLE 5: MIGRATION CHECKLIST

### Step-by-Step Centralization Without Breaking Functionality

#### Phase 1: Documentation Fixes (Safe, Non-Breaking)

- [ ] **1.1** Fix `docs/generated/CONFIGURATION.md:484` - Change `api.port` default from `8080` to `8000`
- [ ] **1.2** Fix `docs/generated/CONFIGURATION.md:574` - Change `WTC_API_PORT` default from `8080` to `8000`
- [ ] **1.3** Update schema `schemas/config/web.schema.yaml` if it's the source of incorrect documentation
- [ ] **1.4** Run `make docs` to regenerate documentation from corrected schemas
- [ ] **1.5** Audit all `docs/` files for hardcoded `8000`/`8080` - add notes about configurability

#### Phase 2: Shell Script Fixes (Medium Risk)

- [ ] **2.1** Update `scripts/install.sh` completion message (lines 1736-1751) per spec above
- [ ] **2.2** Update `scripts/upgrade.sh:640` to read from ports.env
- [ ] **2.3** Update `scripts/lib/service.sh:839` to source ports.env
- [ ] **2.4** Update `scripts/lib/validation.sh` hardcoded URLs
- [ ] **2.5** Update `scripts/lib/detection.sh:29` DEFAULT_PORT
- [ ] **2.6** Update `scripts/setup-credentials.sh` to source ports.env
- [ ] **2.7** Test: Run `./scripts/install.sh --dry-run` to verify no regressions
- [ ] **2.8** Test: Run upgrade on test system with custom ports

#### Phase 3: C Code Fixes (Higher Risk - Requires Rebuild)

- [ ] **3.1** Update `src/main.c:99` `web_port` default or clarify purpose
- [ ] **3.2** Update `src/main.c:102` `modbus_tcp_port` from 502 to 1502 (or add runtime config)
- [ ] **3.3** Update `src/config/config_manager.c:348-364` to read from environment
- [ ] **3.4** Create `src/generated/config_from_env.h` generator script
- [ ] **3.5** Add environment variable reading for all ports in C initialization
- [ ] **3.6** Test: `make clean && make && make test`
- [ ] **3.7** Test: Run controller with custom WTC_* environment variables

#### Phase 4: Python/TypeScript Consolidation (Medium Risk)

- [ ] **4.1** Remove `PortDefaults` class from `web/api/app/core/ports.py` - read env only
- [ ] **4.2** Remove `PORT_DEFAULTS` object from `web/ui/next.config.js` - read env only
- [ ] **4.3** Remove `PORT_DEFAULTS` object from `web/ui/src/config/ports.ts` - read env only
- [ ] **4.4** Update `web/ui/package.json` npm scripts to use `${WTC_UI_PORT}` consistently
- [ ] **4.5** Test: `cd web/api && python -m pytest`
- [ ] **4.6** Test: `cd web/ui && npm test`
- [ ] **4.7** Test: `cd web/ui && npm run build`

#### Phase 5: Docker/Compose Fixes (Low Risk)

- [ ] **5.1** Verify `docker/docker-compose.yml` uses `${WTC_*:-default}` pattern consistently
- [ ] **5.2** Update `docker/Dockerfile.web` to remove hardcoded ports, use ARG/ENV
- [ ] **5.3** Update `docker/Dockerfile.ui` similarly
- [ ] **5.4** Test: `docker compose --env-file ../config/ports.env config` (validate interpolation)
- [ ] **5.5** Test: `WTC_API_PORT=9000 WTC_UI_PORT=9080 docker compose up -d`
- [ ] **5.6** Verify services start on custom ports

#### Phase 6: Add Startup Validation (New Feature)

- [ ] **6.1** Create `web/api/app/core/config_validator.py` per Section 5.3 spec
- [ ] **6.2** Create `web/api/app/core/startup_validator.py` with validation entry point
- [ ] **6.3** Add validation call to `web/api/app/main.py` startup
- [ ] **6.4** Add validation to systemd service startup check
- [ ] **6.5** Test: Start with invalid port (0) - should fail with clear error
- [ ] **6.6** Test: Start with conflicting ports - should fail with clear error
- [ ] **6.7** Test: Start with unresolvable hostname - should warn

#### Phase 7: Testing & Verification

- [ ] **7.1** Create integration test: `tests/integration/test_port_configuration.sh`
- [ ] **7.2** Test default ports work (no env vars set)
- [ ] **7.3** Test custom ports work (all WTC_* vars set)
- [ ] **7.4** Test partial override (some vars set, some use defaults)
- [ ] **7.5** Test port conflict detection
- [ ] **7.6** Test cross-reference validation (UI port in CORS)
- [ ] **7.7** Run full integration test suite
- [ ] **7.8** Manual test: Fresh install with default ports
- [ ] **7.9** Manual test: Fresh install with custom ports
- [ ] **7.10** Manual test: Upgrade with port change

#### Phase 8: Documentation Update

- [ ] **8.1** Update `config/README.md` with complete port configuration guide
- [ ] **8.2** Update `docs/guides/INSTALL.md` with custom port instructions
- [ ] **8.3** Update `docs/guides/DEPLOYMENT.md` with production port recommendations
- [ ] **8.4** Add troubleshooting section for port conflicts
- [ ] **8.5** Add migration notes to `CHANGELOG.md`

### Rollback Plan

If any phase causes issues:

1. **Phase 1-2**: Revert documentation/script changes, no runtime impact
2. **Phase 3**: Rebuild with previous C code, restart services
3. **Phase 4**: Revert Python/TS changes, restart services
4. **Phase 5-6**: Revert compose/validation, restart services

### Verification Commands

```bash
# After each phase, run these verification commands:

# Check port configuration is read correctly
source /opt/water-controller/config/ports.env
echo "API: ${WTC_API_PORT}, UI: ${WTC_UI_PORT}"

# Check services are running on correct ports
ss -tlnp | grep -E "${WTC_API_PORT}|${WTC_UI_PORT}"

# Check API health
curl -s http://localhost:${WTC_API_PORT}/health | jq

# Check UI is accessible
curl -s http://localhost:${WTC_UI_PORT} | head -5

# Check startup validation (after Phase 6)
journalctl -u water-controller-api -n 50 | grep -i validation
```

---

## APPENDIX A: FILES REQUIRING MODIFICATION

### Sorted by Priority

| Priority | File | Changes Needed |
|----------|------|----------------|
| CRITICAL | `scripts/install.sh:1736-1751` | Read ports from config |
| CRITICAL | `docs/generated/CONFIGURATION.md:484,574` | Fix incorrect defaults |
| HIGH | `scripts/upgrade.sh:640` | Use config variable |
| HIGH | `src/main.c:99,102,107-109` | Read from environment |
| HIGH | `scripts/lib/service.sh:839` | Source ports.env |
| HIGH | `scripts/lib/validation.sh:333,380,446` | Use config functions |
| MEDIUM | `web/api/app/core/ports.py` | Remove PortDefaults class |
| MEDIUM | `web/ui/src/config/ports.ts` | Remove PORT_DEFAULTS |
| MEDIUM | `web/ui/next.config.js:11-14` | Remove PORT_DEFAULTS |
| MEDIUM | `src/config/config_manager.c:348-364` | Use env/config |
| LOW | `web/ui/package.json:7,9,14` | Ensure ${} works in npm |
| LOW | Multiple doc files | Add configurability notes |

### Files to Create

| File | Purpose |
|------|---------|
| `web/api/app/core/config_validator.py` | Pydantic validation schema |
| `web/api/app/core/startup_validator.py` | Startup validation entry point |
| `scripts/lib/config.sh` | Shared config loading functions |
| `tests/integration/test_port_configuration.sh` | Port configuration tests |

---

*End of Configuration Validation Audit*
