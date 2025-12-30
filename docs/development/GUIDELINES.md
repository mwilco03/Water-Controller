# Water-Controller Development, Validation, and Deployment Guidelines

## Preamble: Purpose and Scope

This document establishes enforceable standards for producing, validating, documenting, and deploying the Water-Controller SCADA system. These are not suggestions. They are constraints that produce deterministic, auditable, production-ready industrial control software.

**Target System:** Water-Controller (SBC #1)
- PROFINET IO Controller
- FastAPI REST/WebSocket Backend
- React/Next.js HMI
- PostgreSQL Historian
- ISA-18.2 Alarm Management
- Modbus Gateway
- systemd Service Integration

**Core Thesis:** A deployment that cannot be reproduced from documentation is a deployment waiting to fail. Every installation step must be scripted, every configuration must be version-controlled, and every failure mode must have a documented recovery path.

---

## Part 1: Production Standards

### 1.1 Code Production Workflow

All code changes follow this deterministic pipeline:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PRODUCTION PIPELINE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. REQUIREMENTS CAPTURE                                                 │
│     [ ] Functional requirement documented                                │
│     [ ] Acceptance criteria defined (testable)                          │
│     [ ] Affected modules identified                                      │
│     [ ] ICS/SCADA safety implications reviewed                          │
│                                                                          │
│  2. DESIGN                                                               │
│     [ ] Interface contracts specified                                    │
│     [ ] Data flow documented                                             │
│     [ ] Error handling strategy defined                                  │
│     [ ] Resource budget estimated (memory, CPU, network)                │
│                                                                          │
│  3. IMPLEMENTATION                                                       │
│     [ ] Code written per style guidelines                                │
│     [ ] Unit tests written BEFORE or WITH code                          │
│     [ ] No stubs, placeholders, or TODO markers                         │
│     [ ] All code paths implemented                                       │
│                                                                          │
│  4. VERIFICATION                                                         │
│     [ ] Build succeeds with zero warnings                                │
│     [ ] All tests pass                                                   │
│     [ ] Static analysis clean                                            │
│     [ ] Integration tests pass                                           │
│                                                                          │
│  5. REVIEW                                                               │
│     [ ] Code review completed                                            │
│     [ ] Documentation updated                                            │
│     [ ] CHANGELOG entry added                                            │
│     [ ] Version incremented appropriately                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Language-Specific Standards

#### C Code (Core Controller, PROFINET Stack)

| Requirement | Standard | Enforcement |
|-------------|----------|-------------|
| Compiler | GCC or Clang with C11 | CMake toolchain |
| Warnings | `-Wall -Wextra -Werror -pedantic` | CMakeLists.txt |
| Static Analysis | `cppcheck --enable=all --error-exitcode=1` | CI gate |
| Format | `clang-format` with project `.clang-format` | Pre-commit hook |
| Memory | Valgrind clean for all test runs | CI gate |
| Documentation | Doxygen comments on all public functions | Build step |

**C Code Structure Requirements:**

```c
/**
 * @brief One-line description of function purpose.
 *
 * @param[in]  param1  Description including valid range
 * @param[out] result  Description of output, including error conditions
 * @return 0 on success, negative error code on failure
 *
 * @note Thread safety: [SAFE|UNSAFE|LOCK_REQUIRED]
 * @note Memory: [ALLOCATES|NO_ALLOC|CALLER_FREES]
 */
int function_name(const input_t *param1, output_t *result);
```

**Prohibited Patterns:**

```c
// PROHIBITED: Magic numbers
if (timeout > 30000) { ... }

// REQUIRED: Named constants
#define PROFINET_WATCHDOG_TIMEOUT_MS 30000
if (timeout > PROFINET_WATCHDOG_TIMEOUT_MS) { ... }

// PROHIBITED: Silent error swallowing
result = do_thing();
// continues regardless of result

// REQUIRED: Explicit error handling
result = do_thing();
if (result < 0) {
    log_error("do_thing failed: %s", error_string(result));
    return result;  // or handle recovery
}

// PROHIBITED: Unbounded buffers
char buffer[MAX_SIZE];
strcpy(buffer, user_input);

// REQUIRED: Bounded operations
char buffer[MAX_SIZE];
int written = snprintf(buffer, sizeof(buffer), "%s", user_input);
if (written >= sizeof(buffer)) {
    log_warn("Input truncated: %d bytes lost", written - sizeof(buffer) + 1);
}
```

#### Python Code (FastAPI Backend)

| Requirement | Standard | Enforcement |
|-------------|----------|-------------|
| Version | Python 3.11+ | pyproject.toml |
| Type Hints | Required on all functions | mypy --strict |
| Linting | ruff check --select=ALL | CI gate |
| Format | ruff format | Pre-commit hook |
| Tests | pytest with >80% coverage | CI gate |
| Dependencies | Pinned versions in requirements.txt | Dependabot |

**Python Code Structure Requirements:**

```python
from typing import Optional
from dataclasses import dataclass

@dataclass
class SensorReading:
    """Immutable sensor reading with quality indicator.

    Attributes:
        value: The measured value in engineering units.
        quality: OPC UA quality code (GOOD=0, UNCERTAIN=1, BAD=2).
        timestamp: Unix timestamp of measurement.
        source_rtu: Station name of originating RTU.
    """
    value: float
    quality: int
    timestamp: float
    source_rtu: str


async def get_sensor_value(
    rtu_name: str,
    slot: int,
    timeout_ms: int = 5000,
) -> SensorReading:
    """Retrieve current sensor value from RTU.

    Args:
        rtu_name: Station name of target RTU.
        slot: Slot number (0-indexed) of sensor.
        timeout_ms: Maximum wait time for response.

    Returns:
        SensorReading with current value and quality.

    Raises:
        RTUOfflineError: RTU is not connected.
        SlotNotFoundError: Slot does not exist on RTU.
        TimeoutError: No response within timeout period.
    """
    ...
```

#### TypeScript/React Code (HMI)

| Requirement | Standard | Enforcement |
|-------------|----------|-------------|
| Version | TypeScript 5.x strict mode | tsconfig.json |
| Linting | ESLint with strict rules | CI gate |
| Format | Prettier | Pre-commit hook |
| Tests | Jest/Vitest with >70% coverage | CI gate |
| Accessibility | WCAG 2.1 AA compliance | axe-core in tests |

**React Component Requirements:**

```typescript
interface SensorDisplayProps {
  /** RTU station name */
  rtuName: string;
  /** Slot number on RTU */
  slot: number;
  /** Display label for operator */
  label: string;
  /** Engineering units (e.g., "°C", "pH", "L/min") */
  units: string;
  /** Alarm thresholds for visual indication */
  alarmLimits?: {
    lowLow?: number;
    low?: number;
    high?: number;
    highHigh?: number;
  };
}

/**
 * Displays a single sensor value with quality indication and alarm state.
 *
 * Visual states:
 * - GOOD quality: Normal display
 * - UNCERTAIN quality: Yellow background, "?" indicator
 * - BAD quality: Red background, "X" indicator, value greyed
 * - ALARM: Flashing border per ISA-18.2
 */
export function SensorDisplay({
  rtuName,
  slot,
  label,
  units,
  alarmLimits,
}: SensorDisplayProps): JSX.Element {
  // Implementation
}
```

### 1.3 Data Quality Propagation

**Non-negotiable:** All data flowing through the system carries quality metadata.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      DATA QUALITY FLOW                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  RTU Sensor ──► PROFINET Frame ──► Controller ──► Historian             │
│      │              │                  │              │                  │
│      │              │                  │              │                  │
│   quality        quality            quality        quality               │
│   (sensor)      (comms)            (merged)       (stored)              │
│                                                                          │
│  Quality Merging Rules:                                                  │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │ If sensor_quality == BAD:           return BAD                 │     │
│  │ If comms_quality == BAD:            return NOT_CONNECTED       │     │
│  │ If age > stale_threshold:           return UNCERTAIN           │     │
│  │ If sensor_quality == UNCERTAIN:     return UNCERTAIN           │     │
│  │ Otherwise:                          return GOOD                │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Quality Type Definition (C):**

```c
typedef enum {
    QUALITY_GOOD          = 0x00,  // Fresh, valid reading
    QUALITY_UNCERTAIN     = 0x40,  // May be stale or degraded
    QUALITY_BAD           = 0x80,  // Sensor failure
    QUALITY_NOT_CONNECTED = 0xC0,  // Communication loss
} data_quality_t;

typedef struct {
    float value;
    data_quality_t quality;
    uint64_t timestamp_us;
    uint16_t source_slot;
} sensor_reading_t;
```

**Quality Type Definition (Python):**

```python
from enum import IntEnum

class DataQuality(IntEnum):
    GOOD = 0x00
    UNCERTAIN = 0x40
    BAD = 0x80
    NOT_CONNECTED = 0xC0

@dataclass
class QualifiedValue:
    value: float
    quality: DataQuality
    timestamp: datetime
    source: str
```

### 1.4 Error Handling Architecture

**Principle:** Errors are data, not exceptions to normal flow. Every error is captured, classified, routed, and potentially recovered.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       ERROR HANDLING FLOW                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Error Occurs                                                            │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Error Classification                          │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │  RECOVERABLE        │  Retry with backoff, then degrade         │    │
│  │  DEGRADED           │  Continue with reduced functionality      │    │
│  │  FATAL              │  Log, alert, enter safe state             │    │
│  │  CONFIGURATION      │  Block startup, require operator action   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Error Context Capture                         │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │  - Error code (numeric, stable across versions)                 │    │
│  │  - Human-readable message                                        │    │
│  │  - Affected component/module                                     │    │
│  │  - Timestamp (monotonic and wall-clock)                         │    │
│  │  - Related identifiers (RTU name, slot, request ID)             │    │
│  │  - Recovery suggestion                                           │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│       │                                                                  │
│       ├──────────────────┬──────────────────┬──────────────────┐        │
│       ▼                  ▼                  ▼                  ▼        │
│   Structured Log     Alarm System      Metrics Counter    API Response  │
│   (JSON to file)     (if threshold)    (Prometheus)      (if request)   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Error Response Format (API):**

```json
{
  "error": {
    "code": "RTU_OFFLINE",
    "message": "RTU 'tank-level-01' is not responding",
    "details": {
      "rtu_name": "tank-level-01",
      "last_seen": "2024-12-22T10:15:30Z",
      "reconnect_attempts": 3
    },
    "recovery": "Check network connectivity to RTU. Verify RTU power status. Review PROFINET diagnostics.",
    "documentation": "https://docs.example.com/errors/RTU_OFFLINE"
  }
}
```

---

## Part 2: Validation Standards

### 2.1 Test Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TEST PYRAMID                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│                          ┌───────────┐                                   │
│                         /│  E2E      │\                                  │
│                        / │  Tests    │ \     (5-10 critical paths)      │
│                       /  │  (slow)   │  \                                │
│                      /   └───────────┘   \                               │
│                     /    ┌───────────┐    \                              │
│                    /    /│Integration│\    \  (50-100 module combos)    │
│                   /    / │  Tests    │ \    \                            │
│                  /    /  │ (medium)  │  \    \                           │
│                 /    /   └───────────┘   \    \                          │
│                /    /    ┌───────────┐    \    \                         │
│               /    /    /│   Unit    │\    \    \ (500+ functions)      │
│              /    /    / │   Tests   │ \    \    \                       │
│             /    /    /  │  (fast)   │  \    \    \                      │
│            └────┴────┴───┴───────────┴───┴────┴────┘                    │
│                                                                          │
│  Execution Time Budget:                                                  │
│    Unit tests:        < 60 seconds total                                │
│    Integration tests: < 5 minutes total                                 │
│    E2E tests:         < 15 minutes total                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Unit Test Requirements

Every function must have corresponding tests covering:

| Test Category | Description | Example |
|---------------|-------------|---------|
| Happy Path | Normal operation with valid inputs | `test_parse_profinet_frame_valid()` |
| Boundary | Edge cases at limits | `test_slot_number_at_max()` |
| Invalid Input | Malformed or null inputs | `test_parse_frame_null_buffer()` |
| Error Path | Failure conditions | `test_database_connection_timeout()` |
| Concurrency | Thread safety (if applicable) | `test_registry_concurrent_access()` |

**Test Naming Convention:**

```
test_<module>_<function>_<scenario>_<expected_outcome>

Examples:
  test_rtu_registry_add_device_duplicate_name_returns_error
  test_alarm_manager_acknowledge_nonexistent_alarm_raises_not_found
  test_historian_write_batch_full_triggers_flush
```

### 2.3 Integration Test Requirements

| Integration Point | Test Scope | Mock Boundary |
|-------------------|------------|---------------|
| PROFINET Controller ↔ RTU Registry | Device discovery, state sync | Network layer mocked |
| RTU Registry ↔ Historian | Data flow, quality propagation | Database mocked or test instance |
| Alarm Manager ↔ WebSocket | Real-time notifications | WebSocket client simulated |
| API ↔ Shared Memory | IPC correctness | Controller process mocked |
| Modbus Gateway ↔ PROFINET | Protocol translation | Both sides use test harness |

### 2.4 End-to-End Test Scenarios

**Mandatory E2E Tests:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CRITICAL PATH E2E TESTS                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. OPERATOR LOGIN AND DASHBOARD                                         │
│     - Authenticate via AD or local                                       │
│     - Load dashboard with live RTU data                                  │
│     - Verify data quality indicators display correctly                  │
│     - Assert: Response time < 2 seconds                                  │
│                                                                          │
│  2. ACTUATOR COMMAND FLOW                                                │
│     - Operator issues pump start command via HMI                         │
│     - Command flows through API → Controller → PROFINET → RTU           │
│     - RTU acknowledges command                                           │
│     - HMI reflects new state                                             │
│     - Assert: End-to-end latency < 500ms                                │
│                                                                          │
│  3. ALARM LIFECYCLE                                                      │
│     - Sensor value crosses high threshold                                │
│     - Alarm generated and sent to HMI via WebSocket                     │
│     - Operator acknowledges alarm                                        │
│     - Alarm state transitions correctly (UNACK → ACKED)                 │
│     - Value returns to normal, alarm clears                              │
│     - Assert: Alarm propagation < 500ms                                  │
│                                                                          │
│  4. RTU DISCONNECT/RECONNECT                                             │
│     - Simulate RTU network disconnect                                    │
│     - Controller detects offline within PROFINET watchdog timeout       │
│     - Communication alarm raised                                         │
│     - All RTU data marked NOT_CONNECTED quality                         │
│     - Reconnect RTU                                                      │
│     - Controller resumes cyclic exchange                                 │
│     - Quality returns to GOOD                                            │
│     - Assert: Detection < 3x cycle time, recovery automatic             │
│                                                                          │
│  5. HISTORIAN DATA INTEGRITY                                             │
│     - Generate known sensor data pattern                                 │
│     - Verify data appears in historian with correct timestamps          │
│     - Query trend data via API                                           │
│     - Verify compression does not lose significant data                  │
│     - Assert: Data loss < 1% with deadband compression                  │
│                                                                          │
│  6. BACKUP AND RESTORE                                                   │
│     - Create backup via API                                              │
│     - Modify configuration                                               │
│     - Restore from backup                                                │
│     - Verify configuration matches pre-modification state               │
│     - Assert: Restore completes without service interruption            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.5 Performance Validation

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| PROFINET cycle time | Configurable, default 1000ms | Wireshark capture analysis |
| API response time (p99) | < 200ms | Load test with k6/locust |
| WebSocket message latency | < 100ms | Instrumented client |
| Alarm propagation | < 500ms | Timestamp comparison |
| Historian write throughput | > 10,000 points/second | Benchmark harness |
| Memory usage (controller) | < 512MB RSS | `/proc/[pid]/status` monitoring |
| CPU usage (idle) | < 5% | `top` or Prometheus metrics |

### 2.6 Validation Checklist

Before any release:

```
PRE-RELEASE VALIDATION GATE
═══════════════════════════════════════════════════════════════════════════

BUILD VERIFICATION
  [ ] Clean build from fresh clone succeeds
  [ ] All compiler warnings resolved (warnings as errors)
  [ ] Static analysis passes (cppcheck, mypy, eslint)
  [ ] Dependency audit clean (no critical vulnerabilities)

TEST EXECUTION
  [ ] Unit tests: 100% pass, >80% coverage
  [ ] Integration tests: 100% pass
  [ ] E2E tests: 100% pass
  [ ] Performance benchmarks within targets

DOCUMENTATION VERIFICATION
  [ ] README accurate for current version
  [ ] API documentation generated and current
  [ ] CHANGELOG updated with all changes
  [ ] DEPLOYMENT.md tested on fresh system

DEPLOYMENT VERIFICATION
  [ ] Install script runs without errors on target OS
  [ ] All services start and pass health checks
  [ ] Upgrade path tested (previous version → current)
  [ ] Rollback path tested (current → previous)
  [ ] Backup/restore cycle verified

SECURITY VERIFICATION
  [ ] No hardcoded credentials in codebase
  [ ] Default passwords documented for change
  [ ] TLS configured for all external interfaces
  [ ] Authentication required for all API endpoints
  [ ] Input validation on all user-supplied data

═══════════════════════════════════════════════════════════════════════════
```

---

## Part 3: Documentation Standards

### 3.1 Documentation Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     DOCUMENTATION STRUCTURE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  docs/                                                                   │
│  ├── README.md                 # Project overview, quick start          │
│  ├── CHANGELOG.md              # Version history, migration notes       │
│  ├── DEPLOYMENT.md             # Installation and configuration         │
│  ├── ARCHITECTURE.md           # System design and data flow            │
│  ├── API.md                    # REST/WebSocket API reference           │
│  ├── OPERATOR_GUIDE.md         # HMI usage, alarm handling              │
│  ├── TROUBLESHOOTING.md        # Common issues and resolutions          │
│  ├── SECURITY.md               # Authentication, hardening              │
│  └── development/                                                        │
│      ├── CONTRIBUTING.md       # Development setup, PR process          │
│      ├── CODING_STANDARDS.md   # Style guides, patterns                 │
│      ├── TESTING.md            # Test writing, coverage requirements    │
│      └── RELEASE.md            # Release process, versioning            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 README.md Requirements

The README must contain:

| Section | Content | Purpose |
|---------|---------|---------|
| Title and Description | One-paragraph system overview | Orientation |
| Architecture Diagram | ASCII or linked image | Context |
| Quick Start | 5 commands or fewer to running system | Onboarding |
| Prerequisites | Exact versions, not ranges | Reproducibility |
| Configuration | Environment variables, config files | Customization |
| API Overview | Key endpoints with examples | Integration |
| License | SPDX identifier | Legal clarity |

### 3.3 DEPLOYMENT.md Requirements

**Mandatory Sections:**

```markdown
# Deployment Guide

## Prerequisites

### Hardware Requirements
- CPU: [minimum/recommended]
- RAM: [minimum/recommended]
- Storage: [minimum/recommended]
- Network: [requirements]

### Software Requirements
- Operating System: [exact version]
- Dependencies: [list with versions]

## Installation Methods

### Method 1: Automated Install Script (Recommended)
[Complete command sequence]

### Method 2: Docker Deployment
[Complete docker-compose instructions]

### Method 3: Manual Installation
[Step-by-step for all components]

## Configuration

### Required Configuration
[Must-change settings before production]

### Optional Configuration
[Tuning parameters with defaults and ranges]

### Environment Variables
[Complete list with descriptions]

## Verification

### Health Checks
[Commands to verify successful installation]

### Smoke Tests
[Minimal tests to confirm functionality]

## Upgrade Procedure

### From Version X.Y to X.Z
[Exact migration steps]

### Rollback Procedure
[How to revert if upgrade fails]

## Backup and Recovery

### Backup Procedure
[What to back up, how, frequency]

### Recovery Procedure
[Step-by-step restore process]

## Troubleshooting

### Installation Failures
[Common issues and resolutions]

### Runtime Issues
[Diagnostic commands and fixes]
```

### 3.4 API Documentation Requirements

Every API endpoint must document:

```yaml
# Example: OpenAPI specification format

/api/v1/rtus/{station_name}/actuators/{slot}:
  post:
    summary: Command actuator on RTU
    description: |
      Sends a command to an actuator connected to the specified RTU.
      Commands are forwarded via PROFINET cyclic I/O to the RTU,
      which controls the physical actuator.

      **Authorization:** Requires OPERATOR or ADMIN role.
      **Rate Limit:** 10 requests/second per user.

    parameters:
      - name: station_name
        in: path
        required: true
        schema:
          type: string
          pattern: "^[a-z0-9-]+$"
        description: PROFINET station name of target RTU
        example: "tank-level-01"

      - name: slot
        in: path
        required: true
        schema:
          type: integer
          minimum: 0
          maximum: 255
        description: Slot number of actuator (0-indexed)

    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - command
            properties:
              command:
                type: string
                enum: [ON, OFF, PWM]
                description: Actuator command
              pwm_duty:
                type: integer
                minimum: 0
                maximum: 255
                description: PWM duty cycle (required if command is PWM)
          examples:
            turn_on:
              summary: Turn pump on
              value:
                command: "ON"
            set_pwm:
              summary: Set variable speed
              value:
                command: "PWM"
                pwm_duty: 128

    responses:
      200:
        description: Command accepted and forwarded to RTU
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  enum: [ACCEPTED, PENDING, COMPLETED]
                rtu_ack_time_ms:
                  type: integer
                  description: Time for RTU acknowledgment

      400:
        description: Invalid request
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Error'
            example:
              error:
                code: "INVALID_COMMAND"
                message: "PWM command requires pwm_duty parameter"

      404:
        description: RTU or slot not found
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Error'
            example:
              error:
                code: "RTU_NOT_FOUND"
                message: "RTU 'tank-level-99' is not registered"

      503:
        description: RTU offline
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Error'
            example:
              error:
                code: "RTU_OFFLINE"
                message: "RTU 'tank-level-01' is not responding"
                recovery: "Check network connectivity. Verify RTU power."
```

### 3.5 CHANGELOG Requirements

Follow Keep a Changelog format:

```markdown
# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Feature descriptions with issue/PR references

### Changed
- Modification descriptions

### Deprecated
- Features to be removed in future versions

### Removed
- Features removed in this release

### Fixed
- Bug fixes with issue references

### Security
- Security-related changes

## [1.2.0] - 2024-12-22

### Added
- Modbus TCP gateway for third-party integrations (#123)
- Log forwarding to Syslog/Elastic/Graylog (#145)

### Changed
- Upgraded FastAPI to 0.109.0 (#156)
- Improved alarm propagation latency from 800ms to 400ms (#167)

### Fixed
- WebSocket reconnection race condition (#178)
- Historian data loss during high-frequency bursts (#189)

### Security
- Updated dependencies to address CVE-2024-XXXXX (#190)

## [1.1.0] - 2024-11-15
...
```

---

## Part 4: Installation Process Standards

### 4.1 Installation Philosophy

**Principles:**

1. **Idempotent:** Running the install script multiple times produces the same result
2. **Atomic:** Partial failures do not leave the system in an inconsistent state
3. **Reversible:** Every installation can be cleanly uninstalled
4. **Logged:** Every action is recorded for troubleshooting
5. **Verified:** Installation concludes with automated health checks

### 4.2 Installation Script Structure

```bash
#!/usr/bin/env bash
#
# Water-Controller Installation Script
#
# Usage: sudo ./install.sh [OPTIONS]
#
# Options:
#   --prefix PATH      Installation prefix (default: /opt/water-controller)
#   --config PATH      Configuration file (default: /etc/water-controller/config.yaml)
#   --skip-deps        Skip dependency installation
#   --skip-verify      Skip post-install verification
#   --uninstall        Remove installation
#   --upgrade          Upgrade existing installation
#   --dry-run          Show what would be done without executing
#   -h, --help         Show this help message
#
# Environment Variables:
#   WT_DB_HOST         PostgreSQL host (default: localhost)
#   WT_DB_PORT         PostgreSQL port (default: 5432)
#   WT_DB_NAME         Database name (default: water_controller)
#   WT_DB_USER         Database user (default: water_controller)
#   WT_DB_PASS         Database password (REQUIRED, no default)
#   WT_INTERFACE       PROFINET network interface (default: eth0)
#
# Exit Codes:
#   0   Success
#   1   General error
#   2   Invalid arguments
#   3   Missing dependencies
#   4   Permission denied
#   5   Configuration error
#   6   Service start failure
#   7   Verification failure

set -euo pipefail
IFS=$'\n\t'

# Logging setup
readonly LOG_FILE="/var/log/water-controller-install.log"
readonly TIMESTAMP=$(date +%Y%m%d_%H%M%S)

log() {
    local level="$1"
    shift
    local message="$*"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [${level}] ${message}" | tee -a "${LOG_FILE}"
}

log_info()  { log "INFO"  "$@"; }
log_warn()  { log "WARN"  "$@"; }
log_error() { log "ERROR" "$@"; }

die() {
    log_error "$@"
    exit 1
}

# Prerequisite checks
check_root() {
    [[ $EUID -eq 0 ]] || die "This script must be run as root"
}

check_os() {
    if [[ ! -f /etc/os-release ]]; then
        die "Cannot determine OS version"
    fi
    source /etc/os-release
    case "${ID}" in
        ubuntu|debian)
            [[ "${VERSION_ID}" =~ ^(22.04|24.04|12)$ ]] || \
                log_warn "Untested OS version: ${VERSION_ID}"
            ;;
        *)
            die "Unsupported OS: ${ID}"
            ;;
    esac
    log_info "Detected OS: ${PRETTY_NAME}"
}

check_architecture() {
    local arch
    arch=$(uname -m)
    case "${arch}" in
        x86_64|aarch64)
            log_info "Architecture: ${arch}"
            ;;
        *)
            die "Unsupported architecture: ${arch}"
            ;;
    esac
}

check_network_interface() {
    local interface="${WT_INTERFACE:-eth0}"
    if ! ip link show "${interface}" &>/dev/null; then
        die "Network interface not found: ${interface}"
    fi
    log_info "PROFINET interface: ${interface}"
}

# Installation steps (each is idempotent)
install_system_dependencies() {
    log_info "Installing system dependencies..."

    apt-get update
    apt-get install -y \
        build-essential \
        cmake \
        libpq-dev \
        libjson-c-dev \
        python3.11 \
        python3.11-venv \
        python3-pip \
        postgresql-client \
        redis-tools \
        nginx

    log_info "System dependencies installed"
}

create_system_user() {
    log_info "Creating system user..."

    if id water-controller &>/dev/null; then
        log_info "User already exists: water-controller"
    else
        useradd --system --shell /bin/false --home-dir /opt/water-controller water-controller
        log_info "Created user: water-controller"
    fi
}

create_directories() {
    local prefix="${1:-/opt/water-controller}"

    log_info "Creating directory structure..."

    mkdir -p "${prefix}"/{bin,lib,share,var/{log,run,data}}
    mkdir -p /etc/water-controller

    chown -R water-controller:water-controller "${prefix}/var"
    chmod 750 "${prefix}/var/data"

    log_info "Directories created at ${prefix}"
}

install_controller_binary() {
    local prefix="${1:-/opt/water-controller}"

    log_info "Installing controller binary..."

    # Build from source or copy pre-built binary
    if [[ -f build/water_controller ]]; then
        install -m 755 build/water_controller "${prefix}/bin/"
    else
        log_info "Building from source..."
        mkdir -p build && cd build
        cmake -DCMAKE_BUILD_TYPE=Release ..
        make -j"$(nproc)"
        install -m 755 water_controller "${prefix}/bin/"
        cd ..
    fi

    log_info "Controller binary installed"
}

install_python_backend() {
    local prefix="${1:-/opt/water-controller}"

    log_info "Installing Python backend..."

    python3.11 -m venv "${prefix}/venv"
    source "${prefix}/venv/bin/activate"

    pip install --upgrade pip wheel
    pip install -r web/api/requirements.txt

    cp -r web/api "${prefix}/share/"

    deactivate
    log_info "Python backend installed"
}

install_web_ui() {
    local prefix="${1:-/opt/water-controller}"

    log_info "Installing web UI..."

    cd web/ui
    npm ci --production
    npm run build

    cp -r .next/standalone "${prefix}/share/ui"
    cp -r .next/static "${prefix}/share/ui/.next/"
    cp -r public "${prefix}/share/ui/"

    cd ../..
    log_info "Web UI installed"
}

configure_database() {
    log_info "Configuring database..."

    local db_host="${WT_DB_HOST:-localhost}"
    local db_port="${WT_DB_PORT:-5432}"
    local db_name="${WT_DB_NAME:-water_controller}"
    local db_user="${WT_DB_USER:-water_controller}"
    local db_pass="${WT_DB_PASS:-}"

    if [[ -z "${db_pass}" ]]; then
        die "WT_DB_PASS environment variable is required"
    fi

    # Test connection
    if ! PGPASSWORD="${db_pass}" psql -h "${db_host}" -p "${db_port}" \
         -U "${db_user}" -d "${db_name}" -c "SELECT 1" &>/dev/null; then
        die "Cannot connect to database. Verify credentials and database exists."
    fi

    # Run migrations
    PGPASSWORD="${db_pass}" psql -h "${db_host}" -p "${db_port}" \
        -U "${db_user}" -d "${db_name}" -f scripts/schema.sql

    log_info "Database configured"
}

install_systemd_services() {
    log_info "Installing systemd services..."

    local services=(
        "water-controller.service"
        "water-controller-api.service"
        "water-controller-ui.service"
    )

    for service in "${services[@]}"; do
        install -m 644 "systemd/${service}" /etc/systemd/system/
    done

    systemctl daemon-reload

    for service in "${services[@]}"; do
        systemctl enable "${service}"
    done

    log_info "systemd services installed and enabled"
}

generate_configuration() {
    local config_file="${1:-/etc/water-controller/config.yaml}"

    log_info "Generating configuration..."

    if [[ -f "${config_file}" ]]; then
        log_warn "Configuration exists, backing up to ${config_file}.bak.${TIMESTAMP}"
        cp "${config_file}" "${config_file}.bak.${TIMESTAMP}"
    fi

    cat > "${config_file}" <<EOF
# Water-Controller Configuration
# Generated: $(date -Iseconds)
#
# WARNING: Review and customize before starting services

profinet:
  interface: ${WT_INTERFACE:-eth0}
  cycle_time_ms: 1000
  watchdog_factor: 3

database:
  host: ${WT_DB_HOST:-localhost}
  port: ${WT_DB_PORT:-5432}
  name: ${WT_DB_NAME:-water_controller}
  user: ${WT_DB_USER:-water_controller}
  # password: Set via WT_DB_PASS environment variable

historian:
  retention_days: 365
  compression:
    deadband_percent: 1.0
    max_interval_seconds: 60

alarms:
  propagation_timeout_ms: 500

api:
  host: 127.0.0.1
  port: 8000
  workers: 4

logging:
  level: INFO
  file: /opt/water-controller/var/log/controller.log
  max_size_mb: 100
  backup_count: 5
EOF

    chmod 640 "${config_file}"
    chown root:water-controller "${config_file}"

    log_info "Configuration generated at ${config_file}"
    log_warn "Review configuration before starting services"
}

start_services() {
    log_info "Starting services..."

    local services=(
        "water-controller.service"
        "water-controller-api.service"
        "water-controller-ui.service"
    )

    for service in "${services[@]}"; do
        if ! systemctl start "${service}"; then
            log_error "Failed to start ${service}"
            journalctl -u "${service}" --no-pager -n 50
            return 1
        fi
        log_info "Started ${service}"
    done

    log_info "All services started"
}

verify_installation() {
    log_info "Verifying installation..."

    local errors=0

    # Check service status
    local services=(
        "water-controller.service"
        "water-controller-api.service"
        "water-controller-ui.service"
    )

    for service in "${services[@]}"; do
        if ! systemctl is-active --quiet "${service}"; then
            log_error "Service not running: ${service}"
            ((errors++))
        fi
    done

    # Check API health
    sleep 5  # Allow services to initialize
    if ! curl -sf http://localhost:8000/api/v1/health > /dev/null; then
        log_error "API health check failed"
        ((errors++))
    fi

    # Check UI accessibility
    if ! curl -sf http://localhost:8080 > /dev/null; then
        log_error "UI not accessible"
        ((errors++))
    fi

    if [[ ${errors} -gt 0 ]]; then
        die "Verification failed with ${errors} error(s)"
    fi

    log_info "Installation verified successfully"
}

print_summary() {
    cat <<EOF

═══════════════════════════════════════════════════════════════════════════
                    WATER-CONTROLLER INSTALLATION COMPLETE
═══════════════════════════════════════════════════════════════════════════

  Installation Directory:  /opt/water-controller
  Configuration File:      /etc/water-controller/config.yaml
  Log Directory:           /opt/water-controller/var/log

  Services:
    water-controller       PROFINET IO Controller (C)
    water-controller-api   REST/WebSocket API (Python/FastAPI)
    water-controller-ui    Web HMI (Next.js)

  Access Points:
    Web HMI:               http://localhost:8080
    REST API:              http://localhost:8000/api/v1
    API Documentation:     http://localhost:8000/docs

  Default Credentials:
    Username: admin
    Password: [SET ON FIRST LOGIN]

  Next Steps:
    1. Review /etc/water-controller/config.yaml
    2. Configure PROFINET network interface
    3. Set up RTU devices in Web HMI
    4. Configure alarm rules
    5. Set up backup schedule

  Commands:
    sudo systemctl status water-controller    # Check status
    sudo journalctl -fu water-controller      # View logs
    sudo systemctl restart water-controller   # Restart

  Documentation:
    /opt/water-controller/share/docs/

═══════════════════════════════════════════════════════════════════════════

EOF
}

# Main installation flow
main() {
    log_info "Starting Water-Controller installation"

    check_root
    check_os
    check_architecture
    check_network_interface

    install_system_dependencies
    create_system_user
    create_directories
    install_controller_binary
    install_python_backend
    install_web_ui
    configure_database
    install_systemd_services
    generate_configuration
    start_services
    verify_installation

    print_summary

    log_info "Installation completed successfully"
}

main "$@"
```

### 4.3 Verification Procedures

Post-installation verification must confirm:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    POST-INSTALL VERIFICATION                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  PROCESS VERIFICATION                                                    │
│  ────────────────────                                                    │
│  [ ] water-controller process running                                    │
│  [ ] water-controller-api process running                                │
│  [ ] water-controller-ui process running                                 │
│  [ ] All processes owned by water-controller user                       │
│  [ ] PID files present in /opt/water-controller/var/run/                │
│                                                                          │
│  NETWORK VERIFICATION                                                    │
│  ────────────────────                                                    │
│  [ ] API listening on configured port (default 8000)                    │
│  [ ] UI listening on configured port (default 8080)                     │
│  [ ] PROFINET interface has raw socket capability                       │
│  [ ] No port conflicts with existing services                           │
│                                                                          │
│  DATABASE VERIFICATION                                                   │
│  ─────────────────────                                                   │
│  [ ] Database connection successful                                      │
│  [ ] Schema tables exist                                                 │
│  [ ] Migrations applied to current version                              │
│  [ ] Read/write permissions verified                                     │
│                                                                          │
│  API VERIFICATION                                                        │
│  ────────────────                                                        │
│  [ ] GET /api/v1/health returns 200                                     │
│  [ ] Authentication endpoints responding                                 │
│  [ ] WebSocket endpoint accepting connections                           │
│                                                                          │
│  UI VERIFICATION                                                         │
│  ───────────────                                                         │
│  [ ] Main page loads without JavaScript errors                          │
│  [ ] Static assets served correctly                                      │
│  [ ] Login page renders                                                  │
│                                                                          │
│  LOGGING VERIFICATION                                                    │
│  ────────────────────                                                    │
│  [ ] Log files created in configured directory                          │
│  [ ] Log rotation configured                                             │
│  [ ] Permissions allow service user to write                            │
│                                                                          │
│  SECURITY VERIFICATION                                                   │
│  ─────────────────────                                                   │
│  [ ] Default passwords not present in production config                 │
│  [ ] Configuration file permissions restricted (640)                    │
│  [ ] Service user has minimal required permissions                      │
│  [ ] Firewall rules applied if configured                               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.4 Upgrade Procedure

```bash
#!/usr/bin/env bash
# upgrade.sh - Water-Controller Upgrade Script

set -euo pipefail

CURRENT_VERSION=$(cat /opt/water-controller/VERSION 2>/dev/null || echo "unknown")
NEW_VERSION="${1:-}"

log_info() { echo "[INFO] $*"; }
log_error() { echo "[ERROR] $*" >&2; }

if [[ -z "${NEW_VERSION}" ]]; then
    echo "Usage: $0 <new_version>"
    exit 2
fi

log_info "Upgrading from ${CURRENT_VERSION} to ${NEW_VERSION}"

# Pre-upgrade backup
log_info "Creating pre-upgrade backup..."
/opt/water-controller/bin/backup.sh --tag "pre-upgrade-${NEW_VERSION}"

# Stop services
log_info "Stopping services..."
systemctl stop water-controller-ui
systemctl stop water-controller-api
systemctl stop water-controller

# Database migration
log_info "Running database migrations..."
/opt/water-controller/bin/migrate.sh --to "${NEW_VERSION}"

# Install new version
log_info "Installing new version..."
# [Installation commands specific to upgrade path]

# Configuration migration
log_info "Migrating configuration..."
/opt/water-controller/bin/config-migrate.sh "${CURRENT_VERSION}" "${NEW_VERSION}"

# Start services
log_info "Starting services..."
systemctl start water-controller
systemctl start water-controller-api
systemctl start water-controller-ui

# Verify
log_info "Verifying upgrade..."
/opt/water-controller/bin/verify.sh

# Update version marker
echo "${NEW_VERSION}" > /opt/water-controller/VERSION

log_info "Upgrade complete: ${CURRENT_VERSION} -> ${NEW_VERSION}"
```

### 4.5 Rollback Procedure

```bash
#!/usr/bin/env bash
# rollback.sh - Water-Controller Rollback Script

set -euo pipefail

BACKUP_ID="${1:-}"

if [[ -z "${BACKUP_ID}" ]]; then
    echo "Usage: $0 <backup_id>"
    echo ""
    echo "Available backups:"
    ls -la /opt/water-controller/var/backups/
    exit 2
fi

BACKUP_PATH="/opt/water-controller/var/backups/${BACKUP_ID}"

if [[ ! -d "${BACKUP_PATH}" ]]; then
    echo "Backup not found: ${BACKUP_PATH}"
    exit 1
fi

log_info() { echo "[INFO] $*"; }

log_info "Rolling back to backup: ${BACKUP_ID}"

# Stop services
log_info "Stopping services..."
systemctl stop water-controller-ui water-controller-api water-controller

# Restore database
log_info "Restoring database..."
pg_restore --clean --if-exists -d water_controller "${BACKUP_PATH}/database.dump"

# Restore configuration
log_info "Restoring configuration..."
cp "${BACKUP_PATH}/config.yaml" /etc/water-controller/config.yaml

# Restore binaries if included
if [[ -d "${BACKUP_PATH}/bin" ]]; then
    log_info "Restoring binaries..."
    cp -r "${BACKUP_PATH}/bin/"* /opt/water-controller/bin/
fi

# Start services
log_info "Starting services..."
systemctl start water-controller water-controller-api water-controller-ui

# Verify
log_info "Verifying rollback..."
/opt/water-controller/bin/verify.sh

log_info "Rollback complete"
```

---

## Part 5: Development Prompt

Use this as a development prompt or system instruction for Water-Controller work:

```
You are developing software for the Water-Controller SCADA system.
This is SBC #1 in a two-tier Water Treatment architecture:
- PROFINET IO Controller communicating with Water-Treat RTUs
- FastAPI REST/WebSocket backend
- React/Next.js HMI
- PostgreSQL historian
- ISA-18.2 alarm management

Apply these non-negotiable constraints:

ARCHITECTURE:
- Controller sends commands THROUGH RTUs, never direct to actuators
- RTU dictates slot configuration; controller adapts dynamically
- Data quality (GOOD/UNCERTAIN/BAD/NOT_CONNECTED) propagates end-to-end
- Shared memory IPC between C controller and Python API

CODE QUALITY:
- C: -Wall -Wextra -Werror -pedantic, Valgrind clean
- Python: mypy --strict, ruff check, >80% coverage
- TypeScript: strict mode, ESLint, >70% coverage
- Zero stubs, TODO markers, or placeholder implementations
- All functions documented with purpose, params, returns, errors

ERROR HANDLING:
- Errors are classified: RECOVERABLE, DEGRADED, FATAL, CONFIGURATION
- All errors include: code, message, context, recovery suggestion
- API errors return structured JSON with documentation links
- Never swallow errors silently

DATA QUALITY:
- Every sensor reading carries quality metadata
- Quality merging: sensor quality + comms quality + staleness = merged quality
- HMI visually distinguishes GOOD/UNCERTAIN/BAD/NOT_CONNECTED
- Historian stores quality alongside values

TESTING:
- Unit tests cover happy path, boundaries, invalid input, error paths
- Integration tests verify module interactions with mocked boundaries
- E2E tests cover critical operator workflows
- Performance targets: API p99 <200ms, alarm propagation <500ms

DOCUMENTATION:
- README: overview, architecture diagram, quick start, prerequisites
- DEPLOYMENT.md: complete installation from bare OS to running system
- API.md: OpenAPI spec with examples and error documentation
- CHANGELOG.md: Keep a Changelog format, semantic versioning

INSTALLATION:
- Scripts are idempotent (re-runnable without side effects)
- Partial failures do not leave inconsistent state
- Every installation concludes with automated verification
- Upgrade and rollback procedures documented and tested

OPERATOR EXPERIENCE:
- All data displays show quality indicators
- Alarm propagation within 500ms
- Actuator command acknowledgment within 100ms
- Clear error messages with recovery guidance
- Pending operations show progress

SECURITY:
- No hardcoded credentials in code
- Configuration files have restricted permissions (640)
- All API endpoints require authentication
- Input validation on all user-supplied data

PRODUCTION CRITERIA:
Code is production-ready when:
- Build succeeds with zero warnings
- All test tiers pass
- Static analysis clean
- Documentation current
- Installation verified on fresh system
- Upgrade/rollback paths tested
- Security checklist completed
```

---

## Appendix: Quick Reference Checklists

### Pre-Commit Checklist

```
Before every commit:
  [ ] Code compiles without warnings
  [ ] All unit tests pass
  [ ] Static analysis clean (cppcheck/mypy/eslint)
  [ ] Format compliance verified
  [ ] No TODO/FIXME/stub code added
  [ ] Documentation updated if API changed
```

### Pre-Release Checklist

```
Before every release:
  [ ] All test tiers pass (unit, integration, E2E)
  [ ] Performance benchmarks within targets
  [ ] CHANGELOG updated
  [ ] Version incremented (semantic versioning)
  [ ] Documentation reviewed for accuracy
  [ ] Install script tested on fresh system
  [ ] Upgrade path tested from previous version
  [ ] Rollback procedure verified
  [ ] Security audit completed
  [ ] Dependency vulnerabilities addressed
```

### Deployment Checklist

```
For every deployment:
  [ ] Target system meets prerequisites
  [ ] Backup of existing installation created
  [ ] Configuration prepared and reviewed
  [ ] Database credentials available
  [ ] Network configuration verified
  [ ] Installation script executed
  [ ] Post-install verification passed
  [ ] Services confirmed running
  [ ] Health checks passing
  [ ] Smoke tests executed
  [ ] Rollback plan documented and tested
```

### Incident Response Checklist

```
When issues occur:
  [ ] Capture current state (logs, metrics, screenshots)
  [ ] Identify affected services
  [ ] Check recent changes (CHANGELOG, git log)
  [ ] Review relevant logs
  [ ] Escalate if safety-critical
  [ ] Document timeline and actions
  [ ] Implement fix or rollback
  [ ] Verify resolution
  [ ] Update documentation if needed
  [ ] Conduct post-incident review
```

---

*These guidelines establish the production, validation, documentation, and installation standards for the Water-Controller SCADA system. Deviations require documented justification and approval. The goal is reproducible, auditable, production-grade industrial control software.*
