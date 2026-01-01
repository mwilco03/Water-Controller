# Future PRs Plan - Water-Controller

> **Generated:** 2026-01-01
> **Branch:** claude/plan-future-prs-XTIyl
> **Status:** Planning Document

---

## Summary Table

| Part | Description | Status | Effort | Risk | Suggested PR Order |
|------|-------------|--------|--------|------|-------------------|
| PART 1 | Merge container-image-builds | ✅ **COMPLETED** | - | - | N/A (PR #65 merged) |
| PART 7 | OpenPLC Integration | ❌ Not Started | **High** | Medium-High | 4th |
| PART 8 | Bootstrap Script Updates | ⚠️ Partial | **Medium** | Low | 1st |
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

## PART 7: OpenPLC Integration

### Status: ❌ NOT STARTED

### Overview
Integrate OpenPLC runtime to support IEC 61131-3 ladder logic programming alongside the existing PROFINET IO controller.

### Prerequisites
- Integration tests for IPC must be in place first (PART 11)
- Bootstrap dual-mode support should be complete (PART 8)
- Documentation framework updated (PART 10)

### Scope

#### 1. Backend Components (C Layer)

**New Source Files:**
```
src/openplc/
├── openplc.h           # Public interface
├── interpreter.c       # Ladder logic interpreter
├── loader.c            # .st/.ld file loader
├── runtime.c           # Execution engine
├── io_mapper.c         # Maps ladder variables to PROFINET I/O
└── cycle_manager.c     # Synchronizes with PROFINET cycle
```

**CMakeLists.txt Updates:**
```cmake
# Add to src/CMakeLists.txt
add_library(openplc
    openplc/interpreter.c
    openplc/loader.c
    openplc/runtime.c
    openplc/io_mapper.c
    openplc/cycle_manager.c
)
target_link_libraries(openplc PRIVATE profinet control)
```

**Integration Points:**
- `src/control/control.c` - Add OpenPLC runtime calls
- `src/profinet/profinet.c` - I/O data exchange with ladder variables
- `src/ipc/ipc.c` - Expose ladder state to API layer

#### 2. Backend API (Python FastAPI)

**New API Endpoints:**
```
web/api/app/api/v1/
├── ladder.py           # Ladder logic management
└── openplc.py          # Runtime control
```

**Endpoint Definitions:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/ladder/programs` | List uploaded ladder programs |
| POST | `/api/v1/ladder/upload` | Upload .st or .ld file |
| GET | `/api/v1/ladder/programs/{id}` | Get program details |
| DELETE | `/api/v1/ladder/programs/{id}` | Delete program |
| POST | `/api/v1/ladder/programs/{id}/activate` | Set active program |
| GET | `/api/v1/ladder/runtime/status` | Runtime status |
| POST | `/api/v1/ladder/runtime/start` | Start execution |
| POST | `/api/v1/ladder/runtime/stop` | Stop execution |
| GET | `/api/v1/ladder/runtime/variables` | Live variable state |
| PUT | `/api/v1/ladder/runtime/variables/{name}` | Force variable value |

**New Models:**
```python
# web/api/app/models/ladder.py
class LadderProgram(Base):
    __tablename__ = "ladder_programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str]  # "structured_text" or "ladder"
    source_code: Mapped[str] = mapped_column(Text)
    compiled_code: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

class LadderVariable(Base):
    __tablename__ = "ladder_variables"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("ladder_programs.id"))
    name: Mapped[str]
    data_type: Mapped[str]  # BOOL, INT, REAL, etc.
    io_binding: Mapped[str] = mapped_column(nullable=True)  # PROFINET I/O mapping
    initial_value: Mapped[str]
```

#### 3. Frontend UI (Next.js)

**New Components:**
```
web/ui/src/
├── components/ladder/
│   ├── LadderEditor.tsx       # Visual ladder editor
│   ├── LadderCanvas.tsx       # Rung rendering
│   ├── LadderToolbox.tsx      # Drag-drop elements
│   ├── VariableInspector.tsx  # Live variable view
│   └── IOMapper.tsx           # Variable-to-PROFINET mapping
├── pages/ladder/
│   ├── index.tsx              # Program list
│   ├── [id]/edit.tsx          # Editor page
│   └── [id]/runtime.tsx       # Runtime monitoring
└── hooks/
    └── useLadderRuntime.ts    # WebSocket hook for live data
```

**Navigation Update:**
- Add "Ladder Logic" section to main navigation
- Add runtime status indicator to header

#### 4. Database Schema

**New Tables:**
```sql
-- In docker/init.sql or migrations

CREATE TABLE ladder_programs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL CHECK (source_type IN ('structured_text', 'ladder')),
    source_code TEXT NOT NULL,
    compiled_code BYTEA,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ladder_variables (
    id SERIAL PRIMARY KEY,
    program_id INTEGER REFERENCES ladder_programs(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    io_binding VARCHAR(255),
    initial_value TEXT,
    UNIQUE(program_id, name)
);

CREATE TABLE ladder_execution_log (
    id SERIAL PRIMARY KEY,
    program_id INTEGER REFERENCES ladder_programs(id),
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    cycles_executed BIGINT,
    avg_cycle_time_us INTEGER,
    errors TEXT[]
);
```

#### 5. Configuration Schema

**New Schema File:**
```yaml
# schemas/config/openplc.schema.yaml
$schema: "https://json-schema.org/draft/2020-12/schema"
title: OpenPLC Configuration
type: object
properties:
  enabled:
    type: boolean
    default: false
    description: Enable OpenPLC runtime
  cycle_time_ms:
    type: integer
    minimum: 1
    maximum: 1000
    default: 10
    description: Ladder logic cycle time in milliseconds
  max_programs:
    type: integer
    minimum: 1
    maximum: 100
    default: 10
  variable_table_size:
    type: integer
    default: 1000
  sync_with_profinet:
    type: boolean
    default: true
    description: Synchronize ladder cycle with PROFINET cycle
```

#### 6. IPC Shared Memory Extension

**New IPC Structures:**
```c
// src/ipc/openplc_ipc.h
typedef struct {
    uint32_t cycle_count;
    uint32_t cycle_time_us;
    uint8_t  running;
    uint8_t  error_code;
    uint16_t active_program_id;
} openplc_status_t;

typedef struct {
    char name[64];
    uint8_t data_type;
    union {
        int32_t i;
        float f;
        uint8_t b;
    } value;
    uint8_t forced;
} openplc_variable_t;
```

### Implementation Steps

1. **Phase 1: Core Runtime** (Estimated: ~3 days effort)
   - Implement C interpreter for structured text subset
   - Create loader for .st files
   - Basic execution engine without I/O

2. **Phase 2: PROFINET Integration** (~2 days)
   - I/O mapper connecting variables to PROFINET data
   - Cycle synchronization
   - IPC structures for API access

3. **Phase 3: API Layer** (~2 days)
   - FastAPI endpoints for program management
   - WebSocket for live variable streaming
   - Database models and migrations

4. **Phase 4: Frontend** (~3 days)
   - Program list and upload
   - Visual ladder editor (basic)
   - Runtime monitoring dashboard

5. **Phase 5: Testing & Documentation** (~2 days)
   - Integration tests
   - API documentation
   - User guide

### Acceptance Criteria

- [ ] Upload structured text program via API
- [ ] Activate program and start execution
- [ ] View live variable values via WebSocket
- [ ] Force variable values from UI
- [ ] Map variables to PROFINET I/O points
- [ ] Cycle time < 10ms when synchronized
- [ ] Graceful degradation if OpenPLC disabled
- [ ] All integration tests pass

---

## PART 8: Bootstrap Script Updates (Dual Deployment Mode)

### Status: ⚠️ PARTIAL - Enhancement Needed

### Overview
Enhance `bootstrap.sh` and installation scripts to support explicit deployment mode selection with clear separation between bare-metal and containerized deployments.

### Current State

**Existing Files:**
- `bootstrap.sh` - Entry point with install/upgrade/remove commands
- `scripts/install.sh` - Full installation script
- `scripts/install-hmi.sh` - HMI-only installation

**Current Modes (Implicit):**
- Fresh install vs upgrade
- Dry-run mode
- Component skip flags (SKIP_DEPS, SKIP_BUILD, etc.)

### Proposed Enhancement

#### 1. Deployment Modes

```bash
# New deployment mode options
DEPLOYMENT_MODE="auto"  # auto, baremetal, docker, hybrid

# Sub-modes
BAREMETAL_FULL       # Full system on host
BAREMETAL_WEB_ONLY   # Web stack only (no controller)
DOCKER_FULL          # Everything containerized
DOCKER_WEB_ONLY      # Containerized web, no controller
HYBRID               # Host controller + containerized web
```

#### 2. New Files to Create

**`scripts/lib/deployment-modes.sh`:**
```bash
#!/usr/bin/env bash
# Deployment mode detection and configuration

detect_deployment_environment() {
    local score_baremetal=0
    local score_docker=0

    # Check for Docker
    command -v docker &>/dev/null && ((score_docker+=2))
    docker compose version &>/dev/null && ((score_docker+=1))

    # Check for bare-metal indicators
    systemctl --version &>/dev/null && ((score_baremetal+=1))
    [[ -d /opt ]] && ((score_baremetal+=1))

    # Check for PROFINET requirements
    has_profinet_nic && ((score_baremetal+=2))

    # Check memory (containers need more)
    local mem_gb=$(free -g | awk '/^Mem:/{print $2}')
    [[ $mem_gb -lt 2 ]] && ((score_baremetal+=1))
    [[ $mem_gb -ge 4 ]] && ((score_docker+=1))

    echo "baremetal:$score_baremetal docker:$score_docker"
}

recommend_deployment_mode() {
    local env=$(detect_deployment_environment)
    local baremetal=$(echo "$env" | cut -d: -f2 | cut -d' ' -f1)
    local docker=$(echo "$env" | cut -d: -f3)

    if [[ $docker -gt $baremetal ]]; then
        echo "docker"
    elif has_profinet_nic; then
        echo "hybrid"
    else
        echo "baremetal"
    fi
}

validate_mode_requirements() {
    local mode=$1

    case $mode in
        baremetal|hybrid)
            check_build_deps || return 1
            check_profinet_nic || warn "No PROFINET NIC detected"
            ;;
        docker|docker-web)
            command -v docker &>/dev/null || fatal "Docker not installed"
            docker compose version &>/dev/null || fatal "Docker Compose not available"
            ;;
    esac
    return 0
}

apply_mode_configuration() {
    local mode=$1

    case $mode in
        baremetal)
            export SKIP_DOCKER=1
            export ENABLE_SYSTEMD=1
            export BUILD_CONTROLLER=1
            ;;
        docker)
            export SKIP_BUILD=1
            export SKIP_NETWORK=1
            export USE_DOCKER=1
            ;;
        docker-web)
            export SKIP_BUILD=1
            export SKIP_CONTROLLER=1
            export USE_DOCKER=1
            ;;
        hybrid)
            export BUILD_CONTROLLER=1
            export USE_DOCKER=1
            export ENABLE_SYSTEMD=1
            export CONTROLLER_HOST=1
            ;;
    esac
}
```

#### 3. Bootstrap.sh Updates

```bash
# Add to bootstrap.sh help text
MODE COMMANDS:
    detect                  Detect recommended deployment mode
    install baremetal       Install full system on host (systemd)
    install docker          Install using Docker containers
    install docker-web      Install web stack only (containers)
    install hybrid          Host controller + containerized web

MODE OPTIONS:
    --mode <mode>           Force deployment mode
    --detect                Auto-detect and prompt

# Add mode selection to main()
main() {
    local mode="${DEPLOYMENT_MODE:-auto}"

    case "$1" in
        detect)
            detect_deployment_environment
            echo "Recommended: $(recommend_deployment_mode)"
            return 0
            ;;
        install)
            if [[ "$2" =~ ^(baremetal|docker|docker-web|hybrid)$ ]]; then
                mode="$2"
                shift 2
            elif [[ "$mode" == "auto" ]]; then
                mode=$(recommend_deployment_mode)
                echo "Auto-detected mode: $mode"
                read -p "Continue with $mode? [Y/n] " confirm
                [[ "$confirm" =~ ^[Nn] ]] && exit 0
            fi
            apply_mode_configuration "$mode"
            run_install "$@"
            ;;
    esac
}
```

#### 4. Install.sh Updates

```bash
# Add mode-aware installation sections

install_components() {
    # Controller build (bare-metal and hybrid only)
    if [[ "${BUILD_CONTROLLER:-0}" == "1" ]]; then
        log_info "Building PROFINET controller..."
        install_pnet
        build_controller
    fi

    # Web stack
    if [[ "${USE_DOCKER:-0}" == "1" ]]; then
        log_info "Setting up Docker containers..."
        setup_docker_compose
        docker compose up -d
    else
        log_info "Installing web stack on host..."
        install_python_deps
        install_node_deps
        setup_systemd_services
    fi
}

setup_docker_compose() {
    local compose_file="docker-compose.yml"

    # Select appropriate compose file
    if [[ "${CONTROLLER_HOST:-0}" == "1" ]]; then
        # Hybrid mode: exclude controller from compose
        compose_file="docker-compose.web-only.yml"
    fi

    # Copy compose file to install location
    cp "docker/$compose_file" "$INSTALL_DIR/docker-compose.yml"

    # Generate .env from configuration
    generate_docker_env > "$INSTALL_DIR/.env"
}
```

#### 5. New Docker Compose Variant

**`docker/docker-compose.web-only.yml`:**
```yaml
# Web stack only - for hybrid deployments
version: "3.8"

services:
  database:
    image: timescale/timescaledb:latest-pg15
    # ... (same as main compose)

  api:
    build:
      context: ..
      dockerfile: docker/Dockerfile.web
    environment:
      - CONTROLLER_HOST=host.docker.internal  # Connect to host controller
    # ...

  ui:
    build:
      context: ..
      dockerfile: docker/Dockerfile.ui
    # ...

# No controller service - runs on host
```

### Files to Modify

| File | Changes |
|------|---------|
| `bootstrap.sh` | Add mode commands, detection, mode-aware flow |
| `scripts/install.sh` | Add mode checks, conditional component install |
| `scripts/lib/dependencies.sh` | Mode-aware dependency lists |
| `scripts/lib/pnet.sh` | Skip if not needed for mode |

### Files to Create

| File | Purpose |
|------|---------|
| `scripts/lib/deployment-modes.sh` | Mode detection and configuration |
| `docker/docker-compose.web-only.yml` | Web-only Docker stack |

### Acceptance Criteria

- [ ] `bootstrap.sh detect` shows environment analysis
- [ ] Each mode installs only required components
- [ ] Mode requirements are validated before install
- [ ] Upgrade preserves deployment mode
- [ ] Documentation updated with mode selection guide
- [ ] Hybrid mode: host controller talks to containerized API

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

#### 3. OpenPLC Integration Tests

**Path:** `tests/integration/test_openplc.py`

```python
"""OpenPLC runtime integration tests.

Tests ladder logic execution and PROFINET integration.
"""
import pytest

class TestLadderProgramManagement:
    """Test ladder program CRUD operations."""

    def test_upload_structured_text(self, client):
        """Test uploading structured text program."""
        pass

    def test_upload_ladder_diagram(self, client):
        """Test uploading ladder diagram (.ld)."""
        pass

    def test_delete_program(self, client, sample_program):
        """Test deleting a ladder program."""
        pass

    def test_activate_program(self, client, sample_program):
        """Test activating a program for execution."""
        pass

class TestLadderExecution:
    """Test ladder logic execution."""

    def test_start_runtime(self, client, active_program):
        """Test starting ladder runtime."""
        pass

    def test_stop_runtime(self, client, running_runtime):
        """Test stopping ladder runtime."""
        pass

    def test_variable_read(self, client, running_runtime):
        """Test reading variable values."""
        pass

    def test_variable_force(self, client, running_runtime):
        """Test forcing variable values."""
        pass

    def test_cycle_time_constraint(self, client, running_runtime):
        """Verify cycle time stays within limits."""
        pass

class TestPROFINETIntegration:
    """Test OpenPLC integration with PROFINET."""

    def test_io_variable_mapping(self, runtime_with_io):
        """Test mapping ladder variables to PROFINET I/O."""
        pass

    def test_io_read_from_ladder(self, runtime_with_rtu):
        """Test reading PROFINET inputs in ladder logic."""
        pass

    def test_io_write_from_ladder(self, runtime_with_rtu):
        """Test writing PROFINET outputs from ladder."""
        pass

    def test_cycle_synchronization(self, runtime_with_rtu):
        """Test ladder/PROFINET cycle sync."""
        pass
```

#### 4. Deployment Mode Tests

**Path:** `tests/integration/test_deployment_modes.py`

```python
"""Deployment mode integration tests.

Tests different deployment configurations.
"""
import pytest
import subprocess
import docker

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

    @pytest.mark.docker
    def test_container_resource_limits(self, docker_compose):
        """Test containers respect resource limits."""
        pass

class TestHybridDeployment:
    """Test hybrid deployment mode."""

    @pytest.mark.hybrid
    def test_host_controller_startup(self):
        """Test host controller starts."""
        pass

    @pytest.mark.hybrid
    def test_container_api_connects_to_host(self):
        """Test containerized API connects to host controller."""
        pass

    @pytest.mark.hybrid
    def test_ipc_across_boundary(self):
        """Test IPC works across host/container boundary."""
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
def sample_ladder_program():
    """Sample structured text program."""
    return """
    PROGRAM main
    VAR
        input1 : BOOL;
        output1 : BOOL;
    END_VAR

    output1 := input1;
    END_PROGRAM
    """
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
    hybrid: Requires hybrid environment
    slow: Slow tests (>10s)
    openplc: OpenPLC-related tests
addopts = -v --tb=short
asyncio_mode = auto
```

### Acceptance Criteria

- [ ] IPC tests cover all shared memory operations
- [ ] Migration tests verify data integrity
- [ ] OpenPLC tests cover full lifecycle
- [ ] Deployment mode tests for each mode
- [ ] All tests pass in CI
- [ ] Test coverage report generated
- [ ] Tests documented in README

---

## Recommended PR Order

```
┌─────────────────────────────────────────────────────────────┐
│                    PR DEPENDENCY GRAPH                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   PART 8: Bootstrap                                          │
│   (Dual Mode)                                                │
│        │                                                     │
│        ▼                                                     │
│   PART 10: Documentation ◄──────────┐                        │
│   (DOCKER_DEPLOYMENT.md,            │                        │
│    MIGRATION.md)                    │                        │
│        │                            │                        │
│        ▼                            │                        │
│   PART 11: Integration Tests ───────┤                        │
│   (IPC, Migrations)                 │                        │
│        │                            │                        │
│        ▼                            │                        │
│   PART 7: OpenPLC ──────────────────┘                        │
│   (Full Integration)                                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Rationale

1. **PART 8 First**: Foundation for all deployment-related changes
2. **PART 10 Second**: Documents the modes before tests validate them
3. **PART 11 Third**: Tests infrastructure in place before major feature
4. **PART 7 Last**: Depends on all other parts being stable

---

## Notes

- Each PR should be self-contained and independently mergeable
- PRs can include partial implementations with feature flags
- All PRs require passing CI checks
- Documentation should be updated with each feature PR
