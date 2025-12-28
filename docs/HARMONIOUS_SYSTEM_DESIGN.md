# Harmonious System Design

**Controller + RTU + HMI Integration Philosophy**

---

## Document Purpose

This document establishes the design philosophy for programming and evolving the Water-Controller + Water-Treat system as a **single coherent organism**, not as separate projects. It applies industrial control principles tuned for field deployment, austere environments, and mixed web + embedded systems.

**Authority:** This document is normative. Deviations require documented justification.

**Scope:**
- Water-Controller (SBC #1): PROFINET IO Controller, FastAPI API, React/Next.js HMI
- Water-Treat (SBC #2): RTU, PROFINET IO Device, local sensor/actuator control
- All integration points between them

---

## Core Thesis

> **Code is an implementation of documented intent — never the source of truth.**

The system must be:
- **Coherent**, not just functional
- **Trustworthy**, not just clever
- **Operable**, not just buildable

---

## Principle 0: Always Begin With Documentation

### The Non-Negotiable Rule

Before implementing or modifying any behavior:

1. **Read** the relevant documentation:
   - `README.md` - System overview
   - `OPERATOR.md` - Operator expectations
   - `ALARM_ARCHITECTURE.md` - Safety philosophy
   - `PROFINET_DATA_FORMAT_SPECIFICATION.md` - Wire protocol
   - `CROSS_SYSTEM_GUIDELINES_ADDENDUM.md` - Integration contracts

2. **Derive** from documentation:
   - System responsibilities (what each layer MUST do)
   - Failure modes (what happens when things break)
   - Operator expectations (what "healthy" means to humans)

3. **Refuse** to implement behavior that is not documented.

### Documentation-First Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DOCUMENTATION-FIRST WORKFLOW                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. REQUIREMENT ARRIVES                                              │
│     │                                                                │
│     ▼                                                                │
│  2. CHECK: Is this behavior documented?                              │
│     │                                                                │
│     ├── YES → Implement per documentation                            │
│     │                                                                │
│     └── NO  → STOP. Document first.                                  │
│              │                                                       │
│              ▼                                                       │
│           a. Write specification                                     │
│           b. Review with stakeholders                                │
│           c. Update affected docs                                    │
│           d. THEN implement                                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Questions Before Any Change

| Question | Source Document |
|----------|-----------------|
| What does the operator expect to see? | `OPERATOR.md` |
| What happens if this fails? | `ALARM_ARCHITECTURE.md` |
| How does this cross the RTU/Controller boundary? | `CROSS_SYSTEM_GUIDELINES_ADDENDUM.md` |
| What is the wire format? | `PROFINET_DATA_FORMAT_SPECIFICATION.md` |
| How is this deployed? | `DEPLOYMENT.md` |

---

## Principle 1: Design for Failure Before Designing for Features

### The Core Truth

> **Failure is not an exception — it is a first-class runtime state.**

Every component operates in one of these states:

```
┌─────────────────────────────────────────────────────────────────────┐
│                       COMPONENT STATE MODEL                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐       │
│  │ STARTING │───▶│ HEALTHY  │───▶│ DEGRADED │───▶│ FAILED   │       │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘       │
│       │              │  ▲            │  ▲            │              │
│       │              │  │            │  │            │              │
│       │              └──┼────────────┘  │            │              │
│       │                 │               │            │              │
│       │                 └───────────────┘            │              │
│       │                                              │              │
│       ▼                                              ▼              │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │                     STARTUP_FAILED                        │       │
│  │  (Cannot proceed - requires operator intervention)        │       │
│  └──────────────────────────────────────────────────────────┘       │
│                                                                      │
│  Transitions:                                                        │
│    STARTING → HEALTHY:      All initialization checks pass          │
│    STARTING → STARTUP_FAILED: Critical dependency unavailable       │
│    HEALTHY → DEGRADED:      Non-critical component fails            │
│    DEGRADED → HEALTHY:      Failed component recovers               │
│    DEGRADED → FAILED:       Critical threshold exceeded             │
│    FAILED → STARTING:       Operator-initiated restart              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Failure Design by Layer

#### RTU (Water-Treat) Failure Design

| Failure Mode | Behavior | Recovery |
|--------------|----------|----------|
| **Sensor fault** | Mark quality BAD, continue operation | Automatic when sensor recovers |
| **Controller disconnect** | Continue local control, interlocks active | Automatic reconnect |
| **Power cycle** | Resume with last-known-good config | Automatic |
| **Database corruption** | Fall back to compiled defaults | Operator reconfiguration |

**Critical Invariant:** RTU NEVER stops protecting equipment. Interlocks run regardless of controller state.

#### Controller (Water-Controller) Failure Design

| Failure Mode | Behavior | Recovery |
|--------------|----------|----------|
| **RTU offline** | Mark all RTU data NOT_CONNECTED, raise alarm | Automatic when RTU reconnects |
| **Database unavailable** | Continue with cached data, disable historian writes | Automatic reconnect with backfill |
| **API crash** | HMI shows stale data with timestamp, controller continues | Automatic restart via systemd |
| **IPC failure** | API returns 503, controller logs warning | Automatic reconnect |

**Critical Invariant:** Controller failure does NOT affect RTU safety functions.

#### HMI Failure Design

| Failure Mode | Behavior | Recovery |
|--------------|----------|----------|
| **WebSocket disconnect** | Show disconnection banner, last-known values greyed | Automatic reconnect |
| **API unavailable** | Show error state with timestamp of last good data | Retry on interval |
| **Authentication expired** | Redirect to login, preserve context | Re-authenticate |
| **Stale data** | Yellow background, timestamp visible | Automatic when data refreshes |

**Critical Invariant:** HMI NEVER shows false confidence. Uncertainty is always visible.

### Failure Visibility Requirements

Every degraded state MUST be:

1. **Logged** with structured data
2. **Alarmed** if operator action needed
3. **Visible** in HMI with clear indication
4. **Recoverable** without restart when possible

```typescript
// HMI: Degraded state MUST be visible
interface SystemHealthBanner {
  state: 'HEALTHY' | 'DEGRADED' | 'FAILED';
  degradedComponents: string[];
  lastUpdate: Date;
  message: string;
}

// PROHIBITED: Hidden degradation
// REQUIRED: Explicit degradation display
<SystemHealthBanner
  state="DEGRADED"
  degradedComponents={['RTU-01', 'Historian']}
  lastUpdate={new Date()}
  message="2 components degraded. Monitoring continues with reduced functionality."
/>
```

---

## Principle 2: Separation of Responsibility Without Fragmentation

### The Boundary Contract

Each layer has exclusive responsibilities. No layer assumes behavior of another.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    RESPONSIBILITY BOUNDARIES                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                          HMI LAYER                           │    │
│  │                                                              │    │
│  │  OWNS:                         DELEGATES TO:                 │    │
│  │  • Visualization               • Controller: data retrieval  │    │
│  │  • Intent expression           • Controller: command routing │    │
│  │  • Operator feedback           • Controller: alarm state     │    │
│  │  • Session management                                        │    │
│  │  • UI state                                                  │    │
│  │                                                              │    │
│  │  NEVER:                                                      │    │
│  │  • Caches data beyond display                                │    │
│  │  • Makes control decisions                                   │    │
│  │  • Bypasses API for data                                     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                      │
│                               ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      CONTROLLER LAYER                        │    │
│  │                                                              │    │
│  │  OWNS:                         DELEGATES TO:                 │    │
│  │  • RTU orchestration           • RTU: physical I/O           │    │
│  │  • Data aggregation            • RTU: interlock execution    │    │
│  │  • Command validation          • RTU: local control loops    │    │
│  │  • Alarm notifications         • Database: persistence       │    │
│  │  • Historian collection                                      │    │
│  │  • Cross-RTU coordination                                    │    │
│  │                                                              │    │
│  │  NEVER:                                                      │    │
│  │  • Executes safety interlocks                                │    │
│  │  • Controls actuators directly (only through RTU)            │    │
│  │  • Assumes RTU slot configuration                            │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                      │
│                               ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                         RTU LAYER                            │    │
│  │                                                              │    │
│  │  OWNS:                         REPORTS TO:                   │    │
│  │  • Physical I/O                • Controller: sensor values   │    │
│  │  • Interlock execution         • Controller: interlock state │    │
│  │  • Real-time control           • Controller: diagnostics     │    │
│  │  • Safe defaults                                             │    │
│  │  • Hardware truth                                            │    │
│  │                                                              │    │
│  │  NEVER:                                                      │    │
│  │  • Waits for controller for safety actions                   │    │
│  │  • Trusts controller over local sensors                      │    │
│  │  • Accepts controller override of safety interlocks          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Interface Contracts

#### RTU → Controller (PROFINET Cyclic Data)

```c
// Wire format: 5 bytes per sensor (WT-SPEC-001)
// Bytes 0-3: IEEE 754 Float32, big-endian
// Byte 4: Quality indicator

typedef struct {
    float value;              // Engineering units
    data_quality_t quality;   // GOOD=0x00, UNCERTAIN=0x40, BAD=0x80, NOT_CONNECTED=0xC0
} sensor_data_t;

// Controller MUST NOT assume sensor position
// RTU dictates slot configuration via GSDML
```

#### Controller → RTU (PROFINET Cyclic Data)

```c
// Wire format: 2 bytes per actuator
// Byte 0: Command (ON=1, OFF=0, PWM=2)
// Byte 1: Value (0-255 for PWM duty)

typedef struct {
    uint8_t command;
    uint8_t value;
} actuator_command_t;

// RTU MAY reject command if interlock active
// Controller MUST handle rejection gracefully
```

#### Controller → HMI (REST/WebSocket)

```python
# Every sensor value includes quality
class SensorReading(BaseModel):
    rtu_name: str
    slot: int
    value: float
    quality: Literal['GOOD', 'UNCERTAIN', 'BAD', 'NOT_CONNECTED']
    timestamp: datetime
    units: str

# HMI MUST display quality
# HMI MUST NOT display BAD/NOT_CONNECTED values as valid
```

### Crossing Boundaries Correctly

**Correct Pattern:**
```
Operator clicks "Start Pump"
    │
    ▼
HMI sends: POST /api/v1/rtus/tank-01/actuators/5 {"command": "ON"}
    │
    ▼
Controller validates request
Controller checks RTU connectivity
Controller sends command via PROFINET
    │
    ▼
RTU receives command
RTU checks interlocks
RTU activates actuator (if safe)
RTU reports new state in next cycle
    │
    ▼
Controller receives updated state
Controller sends via WebSocket
    │
    ▼
HMI displays new actuator state
```

**Prohibited Pattern:**
```
❌ HMI sends command directly to RTU
❌ Controller assumes actuator state without RTU confirmation
❌ RTU waits for controller before executing interlock
❌ HMI caches sensor values beyond single render
```

---

## Principle 3: Determinism Over Convenience

### Build Determinism

Every build produces identical output given identical inputs.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     DETERMINISTIC BUILD REQUIREMENTS                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  SOURCE CONTROL                                                      │
│  ──────────────                                                      │
│  • All dependencies pinned to exact versions                        │
│  • Lock files committed (package-lock.json, requirements.txt)       │
│  • Submodule commits locked                                         │
│  • No "latest" or range specifiers                                  │
│                                                                      │
│  BUILD PROCESS                                                       │
│  ─────────────                                                       │
│  • Offline-capable (no network fetches during build)                │
│  • Reproducible across machines                                     │
│  • Timestamped build artifacts                                      │
│  • Build metadata embedded (git hash, date, builder)                │
│                                                                      │
│  DEPLOYMENT                                                          │
│  ──────────                                                          │
│  • Same startup path in dev, test, and production                   │
│  • Configuration explicit, not discovered                           │
│  • No silent fallbacks or auto-detection                            │
│  • Missing config = startup failure (not default behavior)          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Configuration Determinism

```yaml
# PROHIBITED: Implicit defaults
# database:
#   host: ${DB_HOST}  # What if unset?

# REQUIRED: Explicit with validation
database:
  host: ${DB_HOST:?DB_HOST environment variable is required}
  port: ${DB_PORT:-5432}  # Explicit default with documentation
  name: water_controller
  user: ${DB_USER:?DB_USER environment variable is required}
  password: ${DB_PASS:?DB_PASS environment variable is required}

# Startup MUST fail if required config missing
# Startup MUST NOT silently use defaults for critical settings
```

### Behavioral Determinism

```c
// PROHIBITED: Time-dependent behavior without documentation
if (get_uptime_seconds() > 300) {
    // Different behavior after 5 minutes
}

// REQUIRED: Documented, testable state transitions
typedef enum {
    STARTUP_PHASE,      // First 60 seconds: reduced logging
    NORMAL_PHASE,       // After startup: full operation
    SHUTDOWN_PHASE,     // Graceful termination
} operational_phase_t;

// Phase transitions are logged and visible
void transition_to_phase(operational_phase_t new_phase) {
    log_info("Phase transition: %s → %s",
             phase_name(current_phase),
             phase_name(new_phase));
    current_phase = new_phase;
}
```

---

## Principle 4: Explicit State, Not Implicit Assumptions

### Observable State Requirements

Every meaningful system state MUST be:

1. **Queryable** via API
2. **Visible** in HMI
3. **Logged** at transitions
4. **Actionable** (operator knows what to do)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    STATE VISIBILITY MATRIX                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  STATE                 API          HMI          LOG                 │
│  ─────                 ───          ───          ───                 │
│  RTU connected         ✓            ✓            ✓                   │
│  RTU disconnected      ✓            ✓            ✓                   │
│  Sensor GOOD           ✓            normal       (none)              │
│  Sensor UNCERTAIN      ✓            yellow       ✓                   │
│  Sensor BAD            ✓            red + X      ✓                   │
│  Sensor NOT_CONNECTED  ✓            grey + ?     ✓                   │
│  Interlock active      ✓            ✓            ✓                   │
│  Alarm active          ✓            ✓            ✓                   │
│  Command pending       ✓            spinner      ✓                   │
│  Command rejected      ✓            error msg    ✓                   │
│  Data stale            ✓            timestamp    ✓                   │
│                                                                      │
│  PROHIBITED STATES (must not exist):                                 │
│  • Empty display with no explanation                                 │
│  • "Loading..." that never resolves                                  │
│  • Stale data displayed as current                                   │
│  • Error swallowed without indication                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### State Transition Logging

```c
// Every state transition is logged with context
void rtu_set_state(rtu_t *rtu, rtu_state_t new_state) {
    if (rtu->state == new_state) return;  // No-op

    log_info("RTU %s: %s → %s (reason: %s)",
             rtu->station_name,
             rtu_state_name(rtu->state),
             rtu_state_name(new_state),
             rtu->transition_reason);

    rtu_state_t old_state = rtu->state;
    rtu->state = new_state;
    rtu->state_changed_at = get_monotonic_time();

    // Notify callbacks
    invoke_state_callbacks(rtu, old_state, new_state);
}
```

### No Silent Defaults

```python
# PROHIBITED: Silent fallback
def get_cycle_time() -> int:
    return config.get('cycle_time', 1000)  # Where is 1000 documented?

# REQUIRED: Explicit default with documentation
CYCLE_TIME_DEFAULT_MS: Final[int] = 1000  # Default per PROFINET spec
CYCLE_TIME_MIN_MS: Final[int] = 100       # Hardware limit
CYCLE_TIME_MAX_MS: Final[int] = 10000     # Watchdog constraint

def get_cycle_time() -> int:
    """Get configured PROFINET cycle time.

    Returns:
        Cycle time in milliseconds. Defaults to 1000ms per IEC 61158.

    Raises:
        ConfigurationError: If configured value outside valid range.
    """
    value = config.get('cycle_time', CYCLE_TIME_DEFAULT_MS)
    if not CYCLE_TIME_MIN_MS <= value <= CYCLE_TIME_MAX_MS:
        raise ConfigurationError(
            f"cycle_time must be {CYCLE_TIME_MIN_MS}-{CYCLE_TIME_MAX_MS}ms, got {value}"
        )
    return value
```

---

## Principle 5: Program for the Least Experienced Maintainer

### Clarity Over Cleverness

The system will be maintained by someone who:
- Did not write it
- Is reading it under stress (3 AM production issue)
- Has limited context on design decisions
- Needs to fix it NOW

```c
// PROHIBITED: Clever but opaque
#define QUALITY_MASK(q) ((q) & 0xC0)
bool is_usable = !(QUALITY_MASK(quality) & 0x80);

// REQUIRED: Clear and searchable
bool sensor_quality_is_usable(data_quality_t quality) {
    // Only GOOD (0x00) and UNCERTAIN (0x40) are usable for control
    // BAD (0x80) and NOT_CONNECTED (0xC0) indicate sensor failure
    return quality == QUALITY_GOOD || quality == QUALITY_UNCERTAIN;
}
```

### Naming Conventions

| Entity | Convention | Example |
|--------|------------|---------|
| Functions | `verb_noun_qualifier` | `rtu_registry_add_device()` |
| Types | `noun_type_t` | `sensor_reading_t` |
| Constants | `SCOPE_NAME` | `PROFINET_CYCLE_TIME_MS` |
| Error codes | `ERR_SCOPE_CONDITION` | `ERR_RTU_NOT_FOUND` |
| Config keys | `scope.subsystem.setting` | `profinet.watchdog.timeout_ms` |

### Error Messages for Humans

```c
// PROHIBITED: Technical but unhelpful
log_error("Error 0x8004: Operation failed");

// REQUIRED: Actionable guidance
log_error(
    "RTU '%s' disconnected after watchdog timeout (%d ms). "
    "Check network cable to RTU. Verify RTU power status. "
    "Review PROFINET diagnostics in HMI → System → Network.",
    rtu->station_name,
    watchdog_timeout_ms
);
```

```json
// API error response
{
  "error": {
    "code": "RTU_OFFLINE",
    "message": "Cannot send command: RTU 'tank-01' is not connected",
    "details": {
      "rtu_name": "tank-01",
      "last_seen": "2024-12-22T10:15:30Z",
      "reconnect_attempts": 3
    },
    "recovery": [
      "Check network connectivity between controller and RTU",
      "Verify RTU power status",
      "Review PROFINET diagnostics at /system/network"
    ]
  }
}
```

### Linear Control Flow

```python
# PROHIBITED: Complex branching
async def handle_command(cmd):
    if cmd.type == 'actuator':
        if await check_rtu(cmd.rtu):
            if not await check_interlock(cmd):
                result = await send_to_rtu(cmd)
                if result.success:
                    return {"status": "ok"}
                else:
                    return {"status": "failed", "reason": result.error}
            else:
                return {"status": "blocked", "reason": "interlock active"}
        else:
            return {"status": "failed", "reason": "RTU offline"}
    else:
        return {"status": "invalid", "reason": "unknown command type"}

# REQUIRED: Linear flow with early returns
async def handle_command(cmd: ActuatorCommand) -> CommandResult:
    """Execute actuator command on RTU.

    Returns immediately on any failure with clear reason.
    """
    # Validate command type
    if cmd.type != 'actuator':
        return CommandResult.invalid(f"Unknown command type: {cmd.type}")

    # Check RTU connectivity
    rtu = await get_rtu(cmd.rtu_name)
    if not rtu.is_connected:
        return CommandResult.failed(f"RTU '{cmd.rtu_name}' is offline")

    # Check interlocks
    interlock = await check_interlock(cmd.rtu_name, cmd.actuator_slot)
    if interlock.is_active:
        return CommandResult.blocked(
            f"Interlock '{interlock.name}' is active: {interlock.reason}"
        )

    # Send command
    result = await send_command_to_rtu(rtu, cmd)
    if not result.acknowledged:
        return CommandResult.failed(f"RTU rejected command: {result.reason}")

    return CommandResult.success(f"Command sent to {cmd.rtu_name}")
```

---

## Principle 6: Power, Resource, and Time Are Finite

### Resource Budget

Field-deployed systems operate under constraints:

| Resource | Constraint | Implication |
|----------|------------|-------------|
| **Power** | Battery/solar backup | Minimize idle CPU usage |
| **CPU** | Shared with other services | No busy loops |
| **Memory** | 2-4 GB typical | Bounded buffer sizes |
| **Storage** | SD card with limited writes | Efficient logging |
| **Network** | Potentially unreliable | Graceful degradation |
| **Thermal** | No active cooling | Avoid sustained high load |

### Efficient Patterns

```c
// PROHIBITED: Busy polling
while (1) {
    check_for_data();
    usleep(1000);  // Still burns CPU
}

// REQUIRED: Event-driven
// Use epoll/select/kqueue or condition variables
int epfd = epoll_create1(0);
// ... add descriptors ...
while (running) {
    int n = epoll_wait(epfd, events, MAX_EVENTS, timeout_ms);
    for (int i = 0; i < n; i++) {
        handle_event(&events[i]);
    }
}
```

```python
# PROHIBITED: Polling database
while True:
    alarms = await db.query("SELECT * FROM alarms WHERE active = true")
    await broadcast_alarms(alarms)
    await asyncio.sleep(1.0)

# REQUIRED: Change notification
async def alarm_change_listener():
    async with db.listen('alarm_changes') as listener:
        async for notification in listener:
            alarm = await db.get_alarm(notification.alarm_id)
            await broadcast_alarm(alarm)
```

### Historian Efficiency

```sql
-- Use TimescaleDB hypertables for efficient time-series storage
SELECT create_hypertable('historian_data', 'time', chunk_time_interval => INTERVAL '1 day');

-- Compression for old data
ALTER TABLE historian_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'rtu_name, slot'
);

SELECT add_compression_policy('historian_data', INTERVAL '7 days');

-- Retention policy (keeps 1 year, adjust per requirements)
SELECT add_retention_policy('historian_data', INTERVAL '365 days');
```

---

## Principle 7: Harmonize Development, Testing, and Deployment

### Same Paths Everywhere

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ENVIRONMENT PARITY                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  DEVELOPMENT           TESTING              PRODUCTION               │
│  ───────────           ───────              ──────────               │
│                                                                      │
│  Same startup:         Same startup:        Same startup:            │
│  ./start.sh            ./start.sh           ./start.sh               │
│                                                                      │
│  Same config format:   Same config format:  Same config format:      │
│  config.yaml           config.yaml          config.yaml              │
│                                                                      │
│  Same dependencies:    Same dependencies:   Same dependencies:       │
│  requirements.txt      requirements.txt     requirements.txt         │
│                                                                      │
│  ONLY DIFFERENCES:                                                   │
│  • Environment variables (hostnames, credentials)                    │
│  • Log verbosity level                                               │
│  • Performance tuning parameters                                     │
│                                                                      │
│  NEVER DIFFERENT:                                                    │
│  • Code paths                                                        │
│  • Configuration schema                                              │
│  • API contracts                                                     │
│  • Database schema                                                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Readiness Gating

Services must pass readiness checks before accepting traffic:

```python
@app.on_event("startup")
async def startup():
    """Startup sequence with readiness gating.

    Service does not accept requests until ALL checks pass.
    Failure blocks startup (no silent degradation on start).
    """
    checks = [
        ("database", check_database_connection),
        ("ipc", check_ipc_connection),
        ("config", validate_configuration),
    ]

    for name, check_fn in checks:
        try:
            await check_fn()
            logger.info(f"Readiness check passed: {name}")
        except Exception as e:
            logger.critical(f"Readiness check failed: {name} - {e}")
            # Do not start - exit immediately
            sys.exit(1)

    logger.info("All readiness checks passed, accepting requests")
```

### Testing Degraded Modes

```python
@pytest.mark.integration
class TestDegradedModes:
    """Explicit tests for degraded operation scenarios."""

    async def test_rtu_disconnect_handled(self, controller):
        """Verify correct behavior when RTU disconnects."""
        # Arrange
        await controller.connect_rtu("test-rtu")

        # Act - simulate disconnect
        await controller.simulate_rtu_disconnect("test-rtu")

        # Assert
        rtu_state = await controller.get_rtu_state("test-rtu")
        assert rtu_state == "OFFLINE"

        sensor_data = await controller.get_sensor_data("test-rtu", slot=1)
        assert sensor_data.quality == "NOT_CONNECTED"

        alarms = await controller.get_active_alarms()
        assert any(a.type == "RTU_COMMUNICATION_FAILURE" for a in alarms)

    async def test_database_unavailable_continues(self, controller):
        """Verify controller continues when historian unavailable."""
        # Arrange
        await controller.simulate_database_disconnect()

        # Act - send sensor data
        await controller.receive_sensor_data(
            rtu="test-rtu", slot=1, value=7.0, quality="GOOD"
        )

        # Assert - data available via IPC even without historian
        current = await controller.get_current_value("test-rtu", slot=1)
        assert current.value == 7.0
        assert controller.historian_state == "DEGRADED"
```

---

## Principle 8: UI Is Part of the Control System, Not Decoration

### HMI as Operational Surface

The HMI is not a dashboard. It is an operational control surface where incorrect display can cause physical harm.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    HMI OPERATIONAL REQUIREMENTS                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  EVERY DISPLAY MUST SHOW:                                            │
│  ─────────────────────────                                           │
│  1. Data value (or placeholder for bad data)                        │
│  2. Data quality (color coding per ISA-101)                         │
│  3. Data freshness (timestamp or age indicator)                     │
│  4. Source (which RTU/sensor)                                       │
│                                                                      │
│  QUALITY INDICATORS:                                                 │
│  ───────────────────                                                 │
│  ┌──────────────┬─────────────┬──────────────────────────┐          │
│  │   Quality    │   Visual    │   Meaning                │          │
│  ├──────────────┼─────────────┼──────────────────────────┤          │
│  │ GOOD         │ Normal      │ Fresh, valid data        │          │
│  │ UNCERTAIN    │ Yellow bg   │ May be stale/degraded    │          │
│  │ BAD          │ Red bg, X   │ Sensor failure           │          │
│  │ NOT_CONNECTED│ Grey, ?     │ Communication lost       │          │
│  └──────────────┴─────────────┴──────────────────────────┘          │
│                                                                      │
│  TIMESTAMP RULES:                                                    │
│  ────────────────                                                    │
│  • < 5 seconds: Show nothing (assumed current)                      │
│  • 5-60 seconds: Show "Xs ago"                                      │
│  • > 60 seconds: Show timestamp + yellow indicator                  │
│  • > 5 minutes: Show timestamp + "STALE" badge                      │
│                                                                      │
│  CONNECTIVITY DISPLAY:                                               │
│  ─────────────────────                                               │
│  • Top banner shows overall connectivity status                      │
│  • Per-RTU indicators on dashboard                                   │
│  • WebSocket status visible                                          │
│                                                                      │
│  PROHIBITED:                                                         │
│  ───────────                                                         │
│  • Empty displays without explanation                                │
│  • Stale data displayed as current                                   │
│  • Bad quality hidden from operator                                  │
│  • "Loading..." that never resolves                                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Sensor Display Component

```tsx
interface SensorDisplayProps {
  rtuName: string;
  slot: number;
  label: string;
  units: string;
  value: number | null;
  quality: 'GOOD' | 'UNCERTAIN' | 'BAD' | 'NOT_CONNECTED';
  timestamp: Date;
  alarmState?: 'NORMAL' | 'LOW' | 'HIGH' | 'LOW_LOW' | 'HIGH_HIGH';
}

export function SensorDisplay({
  rtuName,
  slot,
  label,
  units,
  value,
  quality,
  timestamp,
  alarmState = 'NORMAL',
}: SensorDisplayProps) {
  const age = Date.now() - timestamp.getTime();
  const isStale = age > 60000;  // 1 minute

  // Quality-based styling
  const qualityStyles = {
    GOOD: 'bg-white',
    UNCERTAIN: 'bg-yellow-100 border-yellow-400',
    BAD: 'bg-red-100 border-red-500',
    NOT_CONNECTED: 'bg-gray-200 text-gray-500',
  };

  // Quality indicators
  const qualityBadges = {
    GOOD: null,
    UNCERTAIN: <span className="text-yellow-600">⚠</span>,
    BAD: <span className="text-red-600">✕</span>,
    NOT_CONNECTED: <span className="text-gray-500">?</span>,
  };

  // Display value or placeholder
  const displayValue =
    quality === 'BAD' || quality === 'NOT_CONNECTED'
      ? '---'
      : value?.toFixed(2) ?? '---';

  return (
    <div
      className={`sensor-display ${qualityStyles[quality]} ${
        alarmState !== 'NORMAL' ? 'alarm-flash' : ''
      }`}
      role="status"
      aria-label={`${label}: ${displayValue} ${units}, quality ${quality}`}
    >
      <div className="sensor-label">{label}</div>
      <div className="sensor-value">
        {qualityBadges[quality]}
        {displayValue} {units}
      </div>
      {isStale && (
        <div className="sensor-stale">
          Last update: {formatTimestamp(timestamp)}
        </div>
      )}
      <div className="sensor-source">
        {rtuName} / Slot {slot}
      </div>
    </div>
  );
}
```

### Connection Status Banner

```tsx
interface ConnectionBannerProps {
  websocketState: 'CONNECTED' | 'CONNECTING' | 'DISCONNECTED';
  lastMessage: Date | null;
  degradedComponents: string[];
}

export function ConnectionBanner({
  websocketState,
  lastMessage,
  degradedComponents,
}: ConnectionBannerProps) {
  if (websocketState === 'CONNECTED' && degradedComponents.length === 0) {
    return null;  // Don't show banner when everything is fine
  }

  return (
    <div
      className={`connection-banner ${
        websocketState === 'DISCONNECTED' ? 'bg-red-600' : 'bg-yellow-500'
      }`}
      role="alert"
    >
      {websocketState === 'DISCONNECTED' && (
        <>
          <span className="font-bold">Disconnected from server</span>
          <span>
            Last data received: {lastMessage
              ? formatTimestamp(lastMessage)
              : 'Never'
            }
          </span>
          <span>Attempting to reconnect...</span>
        </>
      )}

      {websocketState === 'CONNECTING' && (
        <span>Connecting to server...</span>
      )}

      {degradedComponents.length > 0 && (
        <span>
          Degraded: {degradedComponents.join(', ')}
        </span>
      )}
    </div>
  );
}
```

---

## Principle 9: Validate Continuously, Not Just at Startup

### Health Check Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CONTINUOUS VALIDATION                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  LAYER 1: LIVENESS (Is the process running?)                        │
│  ─────────────────────────────────────────────                       │
│  • Responds to systemd watchdog                                      │
│  • HTTP /health/live returns 200                                     │
│  • Process exists with correct PID                                   │
│  Check interval: 5 seconds                                           │
│                                                                      │
│  LAYER 2: READINESS (Can it accept traffic?)                        │
│  ───────────────────────────────────────────                         │
│  • Database connection active                                        │
│  • IPC channel open                                                  │
│  • Configuration valid                                               │
│  Check interval: 10 seconds                                          │
│  HTTP /health/ready returns 200 or 503                               │
│                                                                      │
│  LAYER 3: FUNCTIONAL (Is it working correctly?)                     │
│  ─────────────────────────────────────────────                       │
│  • PROFINET communication active                                     │
│  • Data flowing from RTUs                                            │
│  • Historian writes succeeding                                       │
│  • Alarm propagation within SLA                                      │
│  Check interval: 30 seconds                                          │
│  HTTP /health/functional returns detailed status                     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Freshness Validation

```c
/**
 * @brief Validate sensor reading is fresh.
 *
 * Staleness detection per WT-SPEC-001:
 *   - < stale_threshold: GOOD
 *   - stale_threshold to 2x: UNCERTAIN
 *   - > 2x stale_threshold: BAD
 *
 * @param reading    Sensor reading to validate
 * @param threshold  Stale threshold in milliseconds
 * @return Updated quality code
 */
data_quality_t validate_freshness(
    const sensor_reading_t *reading,
    uint64_t threshold_ms)
{
    uint64_t now = get_monotonic_time_us();
    uint64_t age_ms = (now - reading->timestamp_us) / 1000;

    if (age_ms < threshold_ms) {
        return reading->quality;  // Fresh - keep original quality
    }

    if (age_ms < threshold_ms * 2) {
        // Stale but recent - degrade to UNCERTAIN
        if (reading->quality == QUALITY_GOOD) {
            return QUALITY_UNCERTAIN;
        }
        return reading->quality;
    }

    // Very stale - mark as BAD
    return QUALITY_BAD;
}
```

### Assertion-Based Validation

```c
// Assertions for impossible states
void process_sensor_data(rtu_t *rtu, int slot, const uint8_t *data) {
    // Precondition assertions
    assert(rtu != NULL && "RTU pointer must not be NULL");
    assert(slot >= 0 && slot < MAX_SLOTS && "Slot out of valid range");
    assert(data != NULL && "Data pointer must not be NULL");
    assert(rtu->state == RTU_RUNNING && "RTU must be running to process data");

    // Process data...
    sensor_reading_t reading;
    unpack_sensor_from_profinet(data, 5, &reading);

    // Postcondition assertions
    assert(reading.quality <= QUALITY_NOT_CONNECTED &&
           "Quality code out of valid range");
}
```

### Log Coherence

```python
# Structured logging for coherent story
import structlog

logger = structlog.get_logger()

async def handle_actuator_command(cmd: ActuatorCommand) -> CommandResult:
    log = logger.bind(
        rtu_name=cmd.rtu_name,
        slot=cmd.slot,
        command=cmd.command,
        request_id=cmd.request_id,
    )

    log.info("actuator_command_received")

    # Check RTU
    rtu = await get_rtu(cmd.rtu_name)
    if not rtu.is_connected:
        log.warning("actuator_command_failed", reason="rtu_offline")
        return CommandResult.failed("RTU offline")

    # Check interlock
    interlock = await check_interlock(cmd)
    if interlock.is_active:
        log.warning("actuator_command_blocked",
                   interlock_name=interlock.name)
        return CommandResult.blocked(f"Interlock active: {interlock.name}")

    # Send command
    result = await send_to_rtu(rtu, cmd)

    if result.acknowledged:
        log.info("actuator_command_acknowledged",
                ack_time_ms=result.ack_time_ms)
        return CommandResult.success()
    else:
        log.error("actuator_command_rejected",
                 rejection_reason=result.reason)
        return CommandResult.failed(result.reason)
```

---

## Principle 10: Measure Success by Operational Calm

### Definition of Operational Calm

A calm system:
- Requires no heroics to operate
- Produces no surprises
- Fails obviously, not mysteriously
- Recovers automatically when possible
- Guides operators to correct action when manual intervention needed

### Anti-Patterns to Eliminate

| Anti-Pattern | Symptom | Solution |
|--------------|---------|----------|
| **Mystery failures** | "It just stopped working" | Explicit state logging, health checks |
| **Silent degradation** | "We didn't know X was broken" | Mandatory degradation visibility |
| **Operator confusion** | "I don't know what to do" | Actionable error messages |
| **Alert fatigue** | "There are too many alarms" | Alarm rationalization, priority levels |
| **Manual recovery** | "Restart the service to fix it" | Automatic recovery with backoff |
| **Tribal knowledge** | "Ask Bob, he knows" | Documentation-first culture |

### Calm System Checklist

```
┌─────────────────────────────────────────────────────────────────────┐
│                    OPERATIONAL CALM CHECKLIST                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  OBSERVABILITY                                                       │
│  [ ] Every component has a health endpoint                          │
│  [ ] Every state transition is logged                               │
│  [ ] Every error includes recovery guidance                         │
│  [ ] Metrics available for trending                                  │
│                                                                      │
│  SELF-HEALING                                                        │
│  [ ] Network disconnects trigger automatic reconnect                 │
│  [ ] Database unavailability triggers retry with backoff            │
│  [ ] Crashed services restart automatically (systemd)               │
│  [ ] Stale data is detected and marked                              │
│                                                                      │
│  OPERATOR SUPPORT                                                    │
│  [ ] Alarms are actionable (what happened, what to do)              │
│  [ ] Runbooks exist for common scenarios                            │
│  [ ] Documentation is current and accessible                        │
│  [ ] Training materials match deployed version                       │
│                                                                      │
│  PREDICTABILITY                                                      │
│  [ ] Same code behaves same way everywhere                          │
│  [ ] Configuration changes are logged                               │
│  [ ] Deployment is automated and repeatable                         │
│  [ ] Rollback is tested and documented                              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Roadmap

### Current State Assessment

Based on codebase analysis, current implementation status:

| Principle | Status | Priority Actions |
|-----------|--------|------------------|
| 0. Documentation | ✅ Strong | Keep current |
| 1. Failure design | ⚠️ Partial | Add HMI degradation visibility |
| 2. Separation | ✅ Strong | Formalize API contracts |
| 3. Determinism | ✅ Strong | Add reproducible build CI |
| 4. Explicit state | ⚠️ Partial | Add state transition logging |
| 5. Maintainability | ✅ Strong | Keep current |
| 6. Efficiency | ✅ Strong | Monitor in production |
| 7. Environment parity | ⚠️ Partial | Unify startup paths |
| 8. HMI as control | ⚠️ Partial | Add quality indicators |
| 9. Continuous validation | ⚠️ Partial | Add health check hierarchy |
| 10. Operational calm | ⚠️ Partial | Add runbooks |

### Priority Implementation Tasks

**Immediate (Safety-Critical):**
1. HMI quality indicator display for all sensor values
2. Connection status banner in HMI
3. Staleness detection and display

**Short-Term (Operational):**
1. Structured logging with state transitions
2. Health check hierarchy (/health/live, /health/ready, /health/functional)
3. Automatic reconnection with backoff

**Medium-Term (Sustainability):**
1. Runbook documentation for common scenarios
2. Alarm rationalization and priority review
3. Environment parity validation in CI

---

## Appendix: Quick Reference

### State Visibility Cheat Sheet

```
When implementing any feature, ask:

✓ What state does this create or modify?
✓ How is this state visible in the API?
✓ How is this state visible in the HMI?
✓ What gets logged when state changes?
✓ What happens when this state is corrupted?
✓ How does an operator know this is working correctly?
```

### Error Handling Cheat Sheet

```
When handling any error:

✓ What error code identifies this uniquely?
✓ What message explains this to an operator?
✓ What context helps diagnose the root cause?
✓ What recovery actions are available?
✓ Where is this documented?
✓ Does this trigger an alarm if persistent?
```

### Cross-Layer Communication Cheat Sheet

```
When data crosses a layer boundary:

✓ Is quality metadata preserved?
✓ Is the timestamp preserved?
✓ Is the source (RTU/slot) preserved?
✓ What happens if the receiving layer is unavailable?
✓ Is this documented in the API contract?
```

---

*This document establishes the design philosophy for harmonious system development. All contributors are expected to internalize these principles and apply them consistently. Questions about interpretation should be raised and resolved before implementation.*
