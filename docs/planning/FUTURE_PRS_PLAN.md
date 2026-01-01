# Future PRs Plan - Water-Controller

> **Generated:** 2026-01-01
> **Branch:** claude/plan-future-prs-XTIyl
> **Status:** Planning Document

---

## Summary Table

| Part | Description | Status | Effort | Risk | Suggested PR Order |
|------|-------------|--------|--------|------|-------------------|
| PART 1 | Merge container-image-builds | ✅ **COMPLETED** | - | - | N/A (PR #65 merged) |
| PART 7 | OpenPLC Viewer (Read-Only) | ❌ Not Started | **Low-Medium** | Low | 4th |
| PART 8 | Bootstrap Script (Boolean Mode) | ⚠️ Partial | **Low** | Low | 1st |
| PART 10 | Documentation | ⚠️ Gaps Exist | **Low-Medium** | Low | 2nd |
| PART 11 | Integration Tests | ⚠️ Foundation Only | **Medium-High** | Low | 3rd |

**Recommended Order:** PART 8 → PART 10 → PART 11 → PART 7

---

## PART 1: Container-Image-Builds Branch Merge

### Status: ✅ ALREADY COMPLETED

**PR #65** (Merge commit: `68f7f57`) has already merged the container architecture work into main.

**What was delivered:**
- GitHub Actions workflow: `.github/workflows/docker.yml`
- Multi-stage Dockerfiles for all components (controller, API, UI)
- Docker Compose configurations (dev + prod)
- Multi-architecture support (amd64, arm64, armv7)
- Feature parity matrix: `docs/CONTAINER_FEATURE_PARITY.md`

**No further action required.**

---

## PART 7: OpenPLC Viewer (Read-Only)

### Status: ❌ NOT STARTED

### Overview
Add a **read-only** ladder logic viewer that renders in the browser and communicates with Modbus. This is NOT a full PLC runtime - it's a visualization/monitoring tool.

### Approach: Containerized OpenPLC Editor (Read-Only Mode)

Use an existing containerized solution to provide browser-based ladder logic viewing with Modbus communication.

### Option A: OpenPLC Editor in Container (Recommended)

**Container Setup:**
```yaml
# docker/docker-compose.yml - add service
services:
  openplc-editor:
    image: openplcproject/openplc_v3:latest
    container_name: wtc-openplc
    ports:
      - "${WTC_OPENPLC_PORT:-8081}:8080"
    volumes:
      - openplc_data:/workdir
    environment:
      - MODBUS_ENABLED=true
      - MODBUS_PORT=${WTC_MODBUS_TCP_PORT:-1502}
    restart: unless-stopped
    networks:
      - wtc-network
```

**Integration with Water-Controller:**
- OpenPLC Editor container runs alongside existing stack
- Connects to same Modbus port as existing controller
- Read-only access to I/O state via Modbus
- UI accessible at separate port (8081)

### Option B: Embedded Ladder Viewer Component

If a lighter-weight solution is preferred:

**New UI Component:**
```
web/ui/src/components/ladder/
├── LadderViewer.tsx      # Read-only ladder diagram viewer
├── ModbusStatus.tsx      # Live Modbus register display
└── LadderDiagram.tsx     # SVG rendering of ladder rungs
```

**API Endpoint (Read-Only):**
```python
# web/api/app/api/v1/ladder.py
@router.get("/ladder/view")
async def get_ladder_diagram():
    """Return ladder diagram for display (read-only)."""
    pass

@router.get("/ladder/modbus/registers")
async def get_modbus_registers():
    """Read current Modbus register values."""
    pass
```

### Scope (Simplified)

| Component | Action | Notes |
|-----------|--------|-------|
| Docker Compose | Add OpenPLC container | Pre-built image |
| config/ports.env | Add WTC_OPENPLC_PORT | Default: 8081 |
| UI Navigation | Add link to OpenPLC | External link or iframe |
| Documentation | Add OpenPLC section | How to access viewer |

### No Changes Required

- ❌ No C code changes
- ❌ No new database tables
- ❌ No ladder execution engine
- ❌ No IPC extensions

### Implementation Steps

1. Add OpenPLC container to docker-compose.yml
2. Configure Modbus connection to existing controller
3. Add port configuration to ports.env
4. Add navigation link in UI
5. Document access and usage

### Acceptance Criteria

- [ ] OpenPLC Editor container starts with docker compose
- [ ] Connects to Modbus and shows register values
- [ ] Ladder diagrams viewable in browser
- [ ] Read-only (no writes to controller)
- [ ] Documentation updated

---

## PART 8: Bootstrap Script (Boolean Deployment Mode)

### Status: ⚠️ PARTIAL - Enhancement Needed

### Overview
Simple boolean deployment mode: **bare-metal** OR **docker**. This is a POC - keep it simple.

### Current State

**Existing Files:**
- `bootstrap.sh` - Entry point with install/upgrade/remove commands
- `scripts/install.sh` - Full installation script

### Proposed Enhancement

#### Simple Boolean Mode

```bash
# Two modes only:
# 1. baremetal - Full system installed on host via systemd
# 2. docker    - Everything runs in containers

DEPLOYMENT_MODE="${DEPLOYMENT_MODE:-baremetal}"  # Default to bare-metal
```

#### Bootstrap.sh Updates

```bash
#!/usr/bin/env bash
# bootstrap.sh - Simple deployment mode selection

DEPLOYMENT_MODE="${1:-baremetal}"

show_help() {
    cat <<EOF
Water-Controller Bootstrap

Usage: bootstrap.sh [MODE] [OPTIONS]

MODES:
    baremetal    Install directly on host (systemd services)
    docker       Install using Docker containers

OPTIONS:
    --dry-run    Show what would be installed
    --help       Show this help

Examples:
    bootstrap.sh baremetal    # Install on host
    bootstrap.sh docker       # Install with Docker
EOF
}

main() {
    case "$1" in
        baremetal)
            validate_baremetal_requirements
            run_baremetal_install
            ;;
        docker)
            validate_docker_requirements
            run_docker_install
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo "Error: Invalid mode '$1'. Use 'baremetal' or 'docker'"
            show_help
            exit 1
            ;;
    esac
}

validate_baremetal_requirements() {
    command -v systemctl &>/dev/null || fatal "systemd required for bare-metal mode"
    command -v gcc &>/dev/null || fatal "gcc required for bare-metal mode"
}

validate_docker_requirements() {
    command -v docker &>/dev/null || fatal "Docker not installed"
    docker compose version &>/dev/null || fatal "Docker Compose not available"
}

run_baremetal_install() {
    export USE_DOCKER=0
    ./scripts/install.sh
}

run_docker_install() {
    export USE_DOCKER=1
    cd docker && docker compose up -d
}

main "$@"
```

#### Install.sh Mode Check

```bash
# Add to scripts/install.sh
if [[ "${USE_DOCKER:-0}" == "1" ]]; then
    log_info "Docker mode selected - skipping host installation"
    log_info "Use: cd docker && docker compose up -d"
    exit 0
fi

# Continue with bare-metal installation...
```

### Files to Modify

| File | Changes |
|------|---------|
| `bootstrap.sh` | Add simple mode argument (baremetal/docker) |
| `scripts/install.sh` | Add USE_DOCKER check at top |

### No New Files Required

The existing docker-compose.yml handles the Docker case. No additional compose variants needed for POC.

### Acceptance Criteria

- [ ] `bootstrap.sh baremetal` runs host installation
- [ ] `bootstrap.sh docker` runs docker compose
- [ ] Invalid mode shows error and help
- [ ] Documentation updated with mode examples

---

## PART 10: Documentation

### Status: ⚠️ GAPS EXIST

### Overview
Create missing documentation files and update existing ones for new features.

### New Documents to Create

#### 1. DOCKER_DEPLOYMENT.md

**Path:** `docs/guides/DOCKER_DEPLOYMENT.md`

**Outline:**
```markdown
# Docker Deployment Guide

## Overview
- When to use Docker deployment
- System requirements

## Quick Start
- docker compose up -d
- Accessing the UI
- Checking logs

## Configuration
- Environment variables
- Volume mounts
- Network configuration

## Production Deployment
- Using docker-compose.prod.yml
- Pre-built images from ghcr.io
- Security hardening
- Resource limits

## Multi-Architecture Support
- amd64 (x86_64)
- arm64 (Raspberry Pi 4/5)
- armv7 (Raspberry Pi 3)

## Hybrid Deployment
- Running controller on host
- Connecting containerized web to host controller
- Network considerations

## Maintenance
- Updating containers
- Backup and restore
- Viewing logs
- Health checks

## Troubleshooting
- Container won't start
- Database connection issues
- Network problems
- Permission errors
```

#### 2. MIGRATION.md

**Path:** `docs/guides/MIGRATION.md`

**Outline:**
```markdown
# Migration Guide

## Version Migration
- Pre-migration checklist
- Backup procedures
- Migration steps
- Post-migration validation
- Rollback procedures

## Deployment Mode Migration

### Bare-Metal to Docker
- Export configuration
- Stop services
- Deploy containers
- Import configuration
- Verify operation

### Docker to Bare-Metal
- Export data volumes
- Install on host
- Import data
- Configure services

### Upgrading Deployment Mode
- Within bare-metal
- Within Docker
- Cross-mode upgrade

## Database Migration
- SQLite to PostgreSQL
- Schema upgrades
- Data integrity verification

## Configuration Migration
- Environment variable changes
- Config file format changes
- Port configuration updates
```

### Documents to Update

#### 1. DEPLOYMENT.md

**Add sections:**
- Deployment mode selection guide
- Quick comparison table (bare-metal vs Docker vs hybrid)
- Mode-specific requirements
- Mode-specific troubleshooting

#### 2. INSTALL.md

**Add sections:**
- Deployment mode selection during install
- Mode-specific prerequisites
- Post-install verification by mode

#### 3. TROUBLESHOOTING_GUIDE.md

**Add sections:**
- Docker-specific issues
- Container networking problems
- Hybrid mode connectivity

### Files Summary

| File | Action | Priority |
|------|--------|----------|
| `docs/guides/DOCKER_DEPLOYMENT.md` | **Create** | High |
| `docs/guides/MIGRATION.md` | **Create** | High |
| `docs/guides/DEPLOYMENT.md` | Update | Medium |
| `docs/guides/INSTALL.md` | Update | Medium |
| `docs/guides/TROUBLESHOOTING_GUIDE.md` | Update | Low |

### Acceptance Criteria

- [ ] DOCKER_DEPLOYMENT.md covers all container scenarios
- [ ] MIGRATION.md covers version and mode migrations
- [ ] Existing docs updated for new deployment modes
- [ ] All code examples tested and working
- [ ] Screenshots/diagrams where helpful

---

## PART 11: Integration Tests

### Status: ⚠️ FOUNDATION ONLY

### Overview
Expand integration test coverage to include IPC, migrations, and OpenPLC functionality.

### Current Test Infrastructure

**Existing:**
- `tests/integration/test_e2e.py` - Basic E2E tests
- `web/api/tests/` - API unit tests
- `web/api/tests/integration/` - API integration tests
- Pytest fixtures with SQLite in-memory DB

### New Tests to Create

#### 1. IPC Integration Tests

**Path:** `tests/integration/test_ipc.py`

```python
"""IPC (Inter-Process Communication) integration tests.

Tests shared memory communication between C controller and Python API.
"""
import pytest
import posix_ipc
from unittest.mock import patch

class TestIPCSharedMemory:
    """Test shared memory operations."""

    def test_shm_creation(self):
        """Verify shared memory segment creation."""
        pass

    def test_shm_read_write(self):
        """Test reading/writing to shared memory."""
        pass

    def test_shm_concurrent_access(self):
        """Test concurrent access from multiple processes."""
        pass

    def test_shm_cleanup_on_exit(self):
        """Verify proper cleanup of shared memory."""
        pass

class TestIPCSemaphores:
    """Test semaphore synchronization."""

    def test_semaphore_acquisition(self):
        """Test acquiring semaphore lock."""
        pass

    def test_semaphore_timeout(self):
        """Test semaphore acquisition timeout."""
        pass

    def test_semaphore_release(self):
        """Test proper semaphore release."""
        pass

class TestIPCMessageQueue:
    """Test message queue operations."""

    def test_message_send_receive(self):
        """Test sending and receiving messages."""
        pass

    def test_message_queue_overflow(self):
        """Test behavior when queue is full."""
        pass
```

#### 2. Migration Integration Tests

**Path:** `tests/integration/test_migrations.py`

```python
"""Database migration integration tests.

Tests schema migrations and data integrity.
"""
import pytest
from alembic import command
from alembic.config import Config

class TestSchemaMigrations:
    """Test database schema migrations."""

    def test_fresh_migration(self, empty_db):
        """Test migration on fresh database."""
        pass

    def test_upgrade_from_v1(self, v1_db):
        """Test upgrade from version 1.x schema."""
        pass

    def test_upgrade_from_v2(self, v2_db):
        """Test upgrade from version 2.x schema."""
        pass

    def test_downgrade(self, current_db):
        """Test schema downgrade."""
        pass

    def test_migration_idempotency(self, db):
        """Test running same migration twice."""
        pass

class TestDataMigrations:
    """Test data migration integrity."""

    def test_rtu_data_preserved(self, migrated_db):
        """Verify RTU data after migration."""
        pass

    def test_sensor_data_preserved(self, migrated_db):
        """Verify sensor data after migration."""
        pass

    def test_historian_data_preserved(self, migrated_db):
        """Verify historical data after migration."""
        pass

class TestSQLiteToPostgres:
    """Test SQLite to PostgreSQL migration."""

    def test_export_sqlite(self, sqlite_db):
        """Test exporting data from SQLite."""
        pass

    def test_import_postgres(self, postgres_db, exported_data):
        """Test importing data to PostgreSQL."""
        pass

    def test_data_integrity_after_migration(self):
        """Verify all data intact after cross-DB migration."""
        pass
```

#### 3. OpenPLC Viewer Tests (Read-Only)

**Path:** `tests/integration/test_openplc.py`

```python
"""OpenPLC viewer integration tests.

Tests read-only ladder logic viewing and Modbus communication.
"""
import pytest
import httpx

class TestOpenPLCContainer:
    """Test OpenPLC container deployment."""

    def test_container_starts(self, docker_compose):
        """Test OpenPLC container starts successfully."""
        pass

    def test_web_ui_accessible(self):
        """Test OpenPLC web UI is accessible at configured port."""
        response = httpx.get("http://localhost:8081")
        assert response.status_code == 200

    def test_modbus_connection(self):
        """Test OpenPLC connects to Modbus."""
        pass

class TestModbusReadOnly:
    """Test Modbus read operations (no writes)."""

    def test_read_holding_registers(self, modbus_client):
        """Test reading holding registers."""
        pass

    def test_read_input_registers(self, modbus_client):
        """Test reading input registers."""
        pass

    def test_read_coils(self, modbus_client):
        """Test reading coil status."""
        pass
```

#### 4. Deployment Mode Tests (Boolean: Bare-Metal OR Docker)

**Path:** `tests/integration/test_deployment_modes.py`

```python
"""Deployment mode integration tests.

Tests the two deployment modes: bare-metal and docker.
"""
import pytest
import subprocess

class TestBareMetalDeployment:
    """Test bare-metal deployment mode."""

    @pytest.mark.bare_metal
    def test_systemd_service_startup(self):
        """Test services start via systemd."""
        pass

    @pytest.mark.bare_metal
    def test_controller_profinet_binding(self):
        """Test controller binds to PROFINET interface."""
        pass

    @pytest.mark.bare_metal
    def test_api_database_connection(self):
        """Test API connects to database."""
        pass

class TestDockerDeployment:
    """Test Docker deployment mode."""

    @pytest.mark.docker
    def test_compose_startup(self, docker_compose):
        """Test docker compose up succeeds."""
        pass

    @pytest.mark.docker
    def test_container_health_checks(self, docker_compose):
        """Test all containers pass health checks."""
        pass

    @pytest.mark.docker
    def test_volume_persistence(self, docker_compose):
        """Test data persists across restarts."""
        pass
```

#### 5. Test Fixtures

**Path:** `tests/integration/conftest.py` (extend)

```python
"""Shared fixtures for integration tests."""
import pytest
import docker
from pathlib import Path

@pytest.fixture(scope="session")
def docker_compose():
    """Start docker compose for test session."""
    client = docker.from_env()
    project_root = Path(__file__).parent.parent.parent

    # Start containers
    subprocess.run(
        ["docker", "compose", "-f", "docker/docker-compose.yml", "up", "-d"],
        cwd=project_root,
        check=True
    )

    # Wait for health
    yield client

    # Cleanup
    subprocess.run(
        ["docker", "compose", "-f", "docker/docker-compose.yml", "down", "-v"],
        cwd=project_root
    )

@pytest.fixture
def v1_db(tmp_path):
    """Create a v1 schema database for migration testing."""
    db_path = tmp_path / "v1.db"
    # Initialize with v1 schema
    return db_path

@pytest.fixture
def modbus_client():
    """Create Modbus client for read-only tests."""
    from pymodbus.client import ModbusTcpClient
    client = ModbusTcpClient('localhost', port=1502)
    client.connect()
    yield client
    client.close()
```

### Test Organization

```
tests/
├── integration/
│   ├── conftest.py              # Shared fixtures
│   ├── test_e2e.py              # Existing E2E tests
│   ├── test_ipc.py              # NEW: IPC tests
│   ├── test_migrations.py       # NEW: Migration tests
│   ├── test_openplc.py          # NEW: OpenPLC tests
│   ├── test_deployment_modes.py # NEW: Deployment tests
│   └── fault_injection.sh       # Existing fault injection
├── unit/
│   └── ...
└── pytest.ini                   # Pytest configuration
```

### Pytest Configuration Updates

**`pytest.ini`:**
```ini
[pytest]
testpaths = tests web/api/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    unit: Unit tests (fast, no external deps)
    integration: Integration tests (may need services)
    e2e: End-to-end tests (full stack)
    bare_metal: Requires bare-metal environment
    docker: Requires Docker environment
    slow: Slow tests (>10s)
addopts = -v --tb=short
asyncio_mode = auto
```

### Acceptance Criteria

- [ ] IPC tests cover shared memory operations
- [ ] Migration tests verify data integrity
- [ ] OpenPLC container tests verify read-only Modbus access
- [ ] Deployment mode tests for bare-metal and docker
- [ ] All tests pass in CI
- [ ] Tests documented in README

---

## Recommended PR Order

```
┌─────────────────────────────────────────────────────────────┐
│                    PR DEPENDENCY GRAPH                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   PART 8: Bootstrap (Boolean Mode)                           │
│   ───────────────────────────────                            │
│        │                                                     │
│        ▼                                                     │
│   PART 10: Documentation                                     │
│   (DOCKER_DEPLOYMENT.md, MIGRATION.md)                       │
│        │                                                     │
│        ▼                                                     │
│   PART 11: Integration Tests                                 │
│   (IPC, Migrations, Deployment Modes)                        │
│        │                                                     │
│        ▼                                                     │
│   PART 7: OpenPLC Viewer                                     │
│   (Read-Only Container + Modbus)                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Rationale

1. **PART 8 First**: Simple boolean mode (baremetal/docker) - foundation
2. **PART 10 Second**: Document the two deployment modes
3. **PART 11 Third**: Test infrastructure for both modes
4. **PART 7 Last**: Add OpenPLC container (simple addition to docker-compose)

---

## Notes

- Each PR should be self-contained and independently mergeable
- PRs can include partial implementations with feature flags
- All PRs require passing CI checks
- Documentation should be updated with each feature PR
