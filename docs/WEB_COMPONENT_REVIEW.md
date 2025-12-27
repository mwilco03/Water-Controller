# Web Component Review: Water Treatment Controller

**Review Date:** 2024-12-27
**Scope:** FastAPI Backend (`web/api/`) + Next.js Frontend (`web/ui/`)
**Deployment Context:** Field/austere environments, low operator skill, power-constrained hardware

---

## Executive Summary

The Water Treatment Controller web stack demonstrates a solid foundation with clear architectural intent. The system implements a layered architecture with schema-first validation, explicit error handling, and simulation fallbacks. However, several improvements are recommended to enhance field resilience, operational simplicity, and power efficiency.

**Overall Assessment:** Well-structured for industrial deployment with specific recommendations below.

---

## 1. Architecture & Separation of Concerns

### Current State

| Layer | Implementation | Quality |
|-------|---------------|---------|
| **Transport** | FastAPI routers (`app/api/v1/*.py`), WebSocket (`app/api/websocket.py`) | Good |
| **Business Logic** | Services layer (`app/services/`), partially in route handlers | Moderate |
| **Data Access** | Persistence layer (`app/persistence/`), SQLAlchemy models (`app/models/`) | Good |
| **IPC** | Shared memory client (`shm_client.py`), PROFINET client service | Good |
| **Presentation** | Next.js pages, React components with hooks | Good |

### Strengths

1. **Clear module boundaries** - Routes, models, schemas, and services are separated into distinct directories
2. **IPC abstraction** - `ProfinetClient` wraps shared memory access with simulation fallback (`profinet_client.py:44-56`)
3. **Response envelopes** - Standardized success/error responses via `build_success_response()` and `build_error_response()`
4. **WebSocket abstraction** - `ConnectionManager` handles subscriptions cleanly (`websocket.py:22-109`)

### Issues Identified

1. **Business logic in route handlers** - Some routes (e.g., `rtus.py:89-147`) contain database logic that should be in service layer
2. **Global singletons** - Multiple global clients (`_client`, `_rtu_manager`, `_profinet_client`) complicate testing and restart scenarios
3. **UI-API coupling** - Frontend makes assumptions about response structure (e.g., `data.station_name` in `page.tsx`)

### Recommendations

```python
# BEFORE: Logic in route handler (rtus.py)
@router.post("", status_code=201)
async def create_rtu(request: RtuCreate, db: Session = Depends(get_db)):
    existing = db.query(RTU).filter(RTU.station_name == request.station_name).first()
    if existing:
        raise RtuAlreadyExistsError("station_name", request.station_name)
    # ... more logic

# AFTER: Delegate to service
@router.post("", status_code=201)
async def create_rtu(
    request: RtuCreate,
    rtu_service: RtuService = Depends(get_rtu_service)
):
    rtu = await rtu_service.create(request)
    return build_success_response(rtu)
```

**Priority:** Medium - Extract business logic to service layer for testability and reusability.

---

## 2. Validation & Contract Enforcement

### Current State

- **Pydantic schemas** - Well-defined in `app/schemas/*.py` with field validators
- **Request validation** - FastAPI auto-validates request bodies against schemas
- **Response contracts** - Explicit response models with `Field()` descriptions

### Strengths

1. **Custom validators** - IP address, station name, hex ID patterns validated (`rtu.py:45-75`)
2. **Schema reuse** - Common schemas shared across endpoints (`common.py`)
3. **Error detail structure** - `ErrorDetail` includes recovery hints and suggested actions

### Issues Identified

1. **Missing OpenAPI spec generation** - Frontend may drift from backend contracts
2. **Partial response validation** - Some endpoints return `Dict[str, Any]` instead of typed models
3. **No schema versioning** - Breaking changes could affect field deployments

### Recommendations

```python
# Generate TypeScript types from OpenAPI
# package.json: "generate:types": "openapi-typescript http://localhost:8080/openapi.json -o src/lib/api-types.ts"

# Enforce response models
@router.get("", response_model=SuccessResponse[List[RtuResponse]])
async def list_rtus(...) -> SuccessResponse[List[RtuResponse]]:
    ...
```

**Priority:** High - Mechanical contract derivation prevents frontend/backend divergence.

---

## 3. Idempotency & Deterministic Behavior

### Current State

| Operation | Retry-Safe | Notes |
|-----------|-----------|-------|
| GET endpoints | Yes | Read-only queries |
| POST /rtus | No | Creates duplicate if retried |
| POST /rtus/{name}/connect | Partial | State checks prevent re-entry but no idempotency key |
| POST /rtus/{name}/disconnect | Yes | No-op if already offline |
| Actuator commands | No | Repeated commands may toggle state |

### Issues Identified

1. **No idempotency keys** - POST requests lack request deduplication
2. **State machine gaps** - Some transitions allow repeated entry (e.g., CONNECTING state)
3. **Command-query mixing** - Some queries have side effects (e.g., `get_sensors` may trigger shared memory read)

### Recommendations

```python
# Add idempotency support
class IdempotentRequest(BaseModel):
    idempotency_key: Optional[str] = Field(None, description="Unique request ID for deduplication")

@router.post("/{name}/actuators/{slot}")
async def command_actuator(
    name: str,
    slot: int,
    request: ActuatorCommand,
    db: Session = Depends(get_db)
):
    if request.idempotency_key:
        existing = db.query(CommandLog).filter(
            CommandLog.idempotency_key == request.idempotency_key
        ).first()
        if existing:
            return build_success_response(existing.result)
    # ... execute command
```

**Priority:** High - Network interruptions in field deployments require safe retry semantics.

---

## 4. Efficiency & Resource Utilization

### Current State

| Resource | Usage Pattern | Assessment |
|----------|--------------|------------|
| Memory | SQLite in-memory possible, bounded structures | Good |
| CPU | Async handlers, no blocking calls | Good |
| Network | WebSocket for real-time, REST for config | Good |
| Disk | SQLite file, historian samples | Moderate |

### Strengths

1. **WebSocket over polling** - `useWebSocket` hook replaces polling when connected (`useWebSocket.ts:55-171`)
2. **Fallback polling** - Graceful degradation when WebSocket unavailable
3. **Bounded connection manager** - Dead connections cleaned automatically (`websocket.py:100-104`)

### Issues Identified

1. **Unbounded historian** - No automatic data retention policy visible
2. **Redundant fetches** - UI fetches full RTU list on every update (`page.tsx:51-66`)
3. **N+1 queries** - `list_rtus` with `include_stats=True` queries per RTU

### Recommendations

```python
# Add pagination and selective updates
@router.get("")
async def list_rtus(
    offset: int = 0,
    limit: int = 50,
    changed_since: Optional[datetime] = None,  # Delta updates
    ...
):
    query = db.query(RTU)
    if changed_since:
        query = query.filter(RTU.updated_at > changed_since)
    # Use eager loading for stats
    query = query.options(selectinload(RTU.sensors), selectinload(RTU.controls))
```

**Priority:** Medium - Important for constrained hardware deployments.

---

## 5. Resilience & Fault Tolerance

### Current State

- **Simulation mode** - `ProfinetClient` operates without controller (`profinet_client.py:52-55`)
- **WebSocket reconnection** - Exponential backoff with max attempts (`useWebSocket.ts:117-121`)
- **Explicit exception hierarchy** - `ScadaException` with recovery hints

### Strengths

1. **Graceful degradation** - System operates in simulation mode when controller unavailable
2. **State machine tracking** - RTU states with timestamps (`rtu.py:89-96`)
3. **Error categorization** - Recoverable vs non-recoverable errors distinguished

### Issues Identified

1. **No circuit breaker** - Repeated shared memory failures could overwhelm system
2. **Missing health endpoint** - No consolidated health check for operators
3. **Silent failures** - Some error paths log but don't surface to UI

### Recommendations

```python
# Add health endpoint with subsystem status
@router.get("/health")
async def health_check():
    return {
        "status": "healthy" if all_ok else "degraded",
        "subsystems": {
            "database": {"status": "ok", "latency_ms": 2},
            "profinet_controller": {"status": "ok" if profinet.is_connected() else "unavailable"},
            "shared_memory": {"status": "ok" if shm.is_connected() else "unavailable"},
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# Add circuit breaker for shared memory
class ShmCircuitBreaker:
    def __init__(self, failure_threshold=5, reset_timeout=30):
        self._failures = 0
        self._state = "CLOSED"
        self._last_failure = None
```

**Priority:** High - Critical for unattended field operation.

---

## 6. Testing Strategy (Field-Oriented)

### Current State

| Test Type | Coverage | Field-Runnable |
|-----------|----------|---------------|
| Unit tests | Present for templates, PID | Yes |
| API tests | TestClient with SQLite in-memory | Yes |
| Integration tests | PROFINET live tests (requires hardware) | No |
| UI tests | None visible | N/A |

### Strengths

1. **In-memory database** - Tests use SQLite `:memory:` for speed (`conftest.py:29-35`)
2. **Fixture composition** - `sample_rtu`, `running_rtu` fixtures for state setup
3. **Schema contract tests** - Template tests verify structure

### Issues Identified

1. **No failure mode tests** - Happy path only in current test suite
2. **Missing idempotency tests** - No verification of retry safety
3. **No performance tests** - No validation of resource limits

### Recommendations

```python
# Add failure mode tests
class TestRtuFailureHandling:
    def test_connect_when_controller_unavailable(self, client, sample_rtu):
        # Should return graceful error, not crash
        ...

    def test_command_during_network_partition(self, client, running_rtu):
        # Simulate shared memory disconnect
        ...

# Add idempotency tests
class TestIdempotency:
    def test_duplicate_rtu_creation_rejected(self, client):
        ...

    def test_actuator_command_idempotent_with_key(self, client, running_rtu):
        ...
```

**Priority:** High - Failure tests essential for field confidence.

---

## 7. Dynamic Configuration & Runtime Adaptability

### Current State

- **RTU discovery** - DCP network scan via `POST /api/v1/discover/rtu`
- **Dynamic slot configuration** - RTU dictates slot layout, not controller
- **Template system** - Configuration templates for rapid deployment

### Strengths

1. **No fixed slot limits** - Slots dynamically created from RTU response
2. **Feature detection** - UI adapts to RTU capabilities (sensors, controls visible)
3. **Discovery cache** - Found devices cached for quick re-add

### Issues Identified

1. **Hardcoded timeouts** - 5000ms discovery timeout not configurable at runtime
2. **Static polling interval** - 5s poll interval in UI not adaptive
3. **No capability negotiation** - Frontend assumes all features available

### Recommendations

```typescript
// Adaptive polling based on conditions
function calculatePollInterval(rtuCount: number, wsConnected: boolean): number {
  if (wsConnected) return 0;  // No polling needed
  if (rtuCount > 10) return 10000;  // Slow down for many RTUs
  return 5000;  // Default
}

// Capability-based UI
const { capabilities } = await getRtuCapabilities(stationName);
if (capabilities.includes('pid')) {
  // Show PID controls
}
```

**Priority:** Medium - Improves adaptability across diverse deployments.

---

## 8. Operational Simplicity (Low Skill Environment)

### Current State

| Aspect | Implementation | Clarity |
|--------|---------------|---------|
| Error messages | Machine + human readable | Good |
| State visualization | Color-coded badges | Good |
| Setup wizard | `/wizard` page | Present |
| Logs | Structured logging | Moderate |

### Strengths

1. **Suggested actions** - Errors include `suggested_action` field
2. **Setup wizard** - Guided configuration for new deployments
3. **State badges** - Visual state indicators with color coding

### Issues Identified

1. **Technical error codes** - `PROFINET_ERROR` not meaningful to operators
2. **No guided troubleshooting** - Errors don't link to resolution steps
3. **Missing operator dashboard** - System overview requires navigation

### Recommendations

```python
# Operator-friendly error translations
OPERATOR_MESSAGES = {
    "PROFINET_ERROR": "Cannot communicate with RTU. Check network cable and power.",
    "RTU_NOT_CONNECTED": "RTU is offline. Press 'Connect' to establish communication.",
    "COMMAND_TIMEOUT": "RTU did not respond. The network may be slow.",
}

def get_operator_message(error: ScadaException) -> str:
    return OPERATOR_MESSAGES.get(error.code, error.message)
```

**Priority:** High - Critical for low-skill operator success.

---

## 9. Power Awareness & Energy Efficiency

### Current State

| Component | Idle Behavior | Assessment |
|-----------|--------------|------------|
| WebSocket | Keep-alive ping/pong | Moderate overhead |
| Polling | 5s interval when WS down | High overhead |
| UI rendering | Continuous React renders | Moderate overhead |
| Backend | Async, event-driven | Good |

### Strengths

1. **WebSocket preferred** - Event-driven updates reduce polling
2. **Polling fallback** - Only active when WebSocket disconnected
3. **No blocking operations** - Async handlers don't block threads

### Issues Identified

1. **No idle detection** - Updates continue even when tab inactive
2. **Fixed poll rate** - No reduction when system stable
3. **Logging verbosity** - Debug logs may cause disk writes

### Recommendations

```typescript
// Reduce updates when tab inactive
const [isVisible, setIsVisible] = useState(!document.hidden);

useEffect(() => {
  const handleVisibility = () => setIsVisible(!document.hidden);
  document.addEventListener('visibilitychange', handleVisibility);
  return () => document.removeEventListener('visibilitychange', handleVisibility);
}, []);

// Skip polling when hidden
useEffect(() => {
  if (!isVisible) return;
  const interval = setInterval(fetchData, pollInterval);
  return () => clearInterval(interval);
}, [isVisible, pollInterval]);
```

**Priority:** Medium - Important for battery-powered or solar deployments.

---

## 10. Long-Term Maintainability

### Current State

| Aspect | Implementation | Maintainability |
|--------|---------------|-----------------|
| Type annotations | Python 3.9+ typing, TypeScript | Good |
| Documentation | Docstrings present, inline comments | Moderate |
| Code organization | Clear directory structure | Good |
| Version info | Changelog maintained | Good |

### Strengths

1. **Type hints throughout** - Both Python and TypeScript use strong typing
2. **Descriptive schema fields** - Pydantic `Field()` with descriptions
3. **Modular structure** - Clear separation enables isolated changes

### Issues Identified

1. **Magic numbers** - Timeout values, retry counts embedded in code
2. **Implicit invariants** - Some state transitions undocumented
3. **Missing ADRs** - Architectural decisions not recorded

### Recommendations

```python
# Extract constants with documentation
class TimeoutConfig:
    """Timeout configuration for IPC operations.

    Rationale: These values were tuned for field conditions where
    network latency can reach 500ms due to industrial noise.
    """
    DCP_DISCOVERY_MS = 5000
    COMMAND_TIMEOUT_MS = 3000
    RECONNECT_BASE_MS = 1000
    RECONNECT_MAX_ATTEMPTS = 10

# Document state machine invariants
"""
RTU State Machine:
  OFFLINE -> CONNECTING (via /connect)
  CONNECTING -> RUNNING (on AR established)
  CONNECTING -> ERROR (on timeout)
  RUNNING -> OFFLINE (via /disconnect)
  RUNNING -> ERROR (on communication failure)
  ERROR -> OFFLINE (via /disconnect)
  ERROR -> CONNECTING (via /connect)

Invariant: Only one RTU can be in CONNECTING state at a time
           to prevent ARP conflicts during DCP.
"""
```

**Priority:** Medium - Important for future developer onboarding.

---

## Summary of Recommendations

### High Priority — ✅ COMPLETED
1. ✅ **Idempotency keys** for actuator commands and state changes
2. ✅ **Health endpoint** with subsystem status
3. ✅ **Failure mode tests** for network partitions and controller unavailability
4. ✅ **Operator-friendly error messages** with guided resolution

### Medium Priority — ✅ COMPLETED
5. ✅ **Extract business logic** from route handlers to service layer
6. ✅ **Schema-driven frontend** with generated TypeScript types
7. ✅ **Adaptive polling** based on system state and tab visibility
8. ✅ **Document state invariants** and architectural decisions

### Low Priority — ✅ COMPLETED
9. ✅ **Circuit breaker** for shared memory access
10. ⏳ **Capability negotiation** between frontend and backend (future)
11. ⏳ **Historian retention policies** with automatic cleanup (future)

---

## Appendix: Files Reviewed

| File | Purpose |
|------|---------|
| `web/api/app/api/v1/rtus.py` | RTU CRUD and connection endpoints |
| `web/api/app/api/v1/sensors.py` | Sensor value endpoints |
| `web/api/app/api/websocket.py` | WebSocket connection manager |
| `web/api/app/schemas/*.py` | Pydantic request/response models |
| `web/api/app/core/exceptions.py` | Custom exception hierarchy |
| `web/api/app/core/errors.py` | Error response handlers |
| `web/api/app/services/rtu_manager.py` | RTU lifecycle service |
| `web/api/app/services/profinet_client.py` | PROFINET/shared memory client |
| `web/api/app/persistence/base.py` | Database schema initialization |
| `web/api/app/models/rtu.py` | SQLAlchemy RTU models |
| `web/api/shm_client.py` | Shared memory IPC client |
| `web/api/tests/conftest.py` | Test fixtures |
| `web/api/tests/test_templates.py` | Template endpoint tests |
| `web/ui/src/app/rtus/page.tsx` | RTU list page |
| `web/ui/src/app/rtus/[station_name]/page.tsx` | RTU detail page |
| `web/ui/src/hooks/useWebSocket.ts` | WebSocket React hook |

---

## Appendix B: File-Level Mapping & Gap Analysis

This section maps each review prompt to specific files, comparing the assumed structure
with the actual implementation and providing specific line-reference findings.

### Repository Structure: Expected vs Actual

The mapping document assumed a simpler structure. The actual implementation is **more mature**:

```
ASSUMED:                              ACTUAL:
web/api/                              web/api/
├── main.py         ──────────────►   ├── app/
└── shm_client.py                     │   ├── main.py           ✓ Thin entry point
                                      │   ├── api/v1/           ✓ Routers separated
                                      │   ├── schemas/          ✓ Pydantic models
                                      │   ├── models/           ✓ SQLAlchemy ORM
                                      │   ├── services/         ✓ Service layer exists
                                      │   ├── persistence/      ✓ Data access layer
                                      │   └── core/             ✓ Cross-cutting concerns
                                      ├── shm_client.py         ✓ IPC abstraction
                                      └── tests/                ✓ Test suite exists
```

**Gap Status:** The assumed refactor targets are **already implemented**.

---

### 1. Architecture & Separation of Concerns — File Mapping

| File | Layer | Findings |
|------|-------|----------|
| `web/api/app/main.py:35-68` | Transport | ✅ Clean: Only wires routers and lifecycle |
| `web/api/app/api/v1/__init__.py` | Router wiring | ✅ Clean: Declarative router composition |
| `web/api/app/api/v1/rtus.py` | Route handlers | ⚠️ Some DB logic inline (lines 89-147) |
| `web/api/app/api/v1/controls.py:110-193` | Route handlers | ✅ Clean: Uses helpers like `get_control_or_404` |
| `web/api/app/services/profinet_client.py` | IPC | ✅ Clean abstraction with simulation mode |
| `web/api/shm_client.py` | IPC | ✅ Low-level shared memory, well-isolated |
| `web/ui/src/lib/api.ts` | API client | ✅ Centralized with typed interfaces |
| `web/ui/src/hooks/useWebSocket.ts` | Transport | ✅ Clean subscription model |

**Action Items:**
- [ ] Extract remaining DB logic from `rtus.py` to `services/rtu_service.py`
- [ ] Create facade for global singletons (`_profinet_client`, etc.)

---

### 2. Validation & Contract Enforcement — File Mapping

| File | Purpose | Findings |
|------|---------|----------|
| `web/api/app/schemas/rtu.py:45-75` | RTU validation | ✅ `@field_validator` for IP, station_name |
| `web/api/app/schemas/control.py` | Control schemas | ✅ Typed enums, `ControlCommand` model |
| `web/api/app/schemas/common.py` | Shared types | ✅ `DataQuality`, `ErrorDetail` with hints |
| `web/api/app/core/exceptions.py` | Error hierarchy | ✅ Custom exceptions with structured details |
| `web/ui/src/lib/api.ts:38-164` | Frontend types | ⚠️ Manually defined, not generated |

**Gap:**
```typescript
// web/ui/src/lib/api.ts:38-47 — Manual type definition
export interface RTUDevice {
  station_name: string;
  ip_address: string;
  // ... duplicates backend schema
}
```

**Action Items:**
- [ ] Add OpenAPI → TypeScript generation: `openapi-typescript /api/openapi.json`
- [ ] Replace manual types in `api.ts` with generated imports

---

### 3. Idempotency & Deterministic Behavior — File Mapping

| File | Operation | Retry-Safe |
|------|-----------|-----------|
| `web/api/app/api/v1/controls.py:110-193` | `POST /{tag}/command` | ⚠️ No idempotency key |
| `web/api/app/api/v1/rtus.py` | `POST /` (create RTU) | ⚠️ Creates duplicate on retry |
| `web/api/app/api/v1/alarms.py` | `POST /acknowledge` | ✅ Safe: Acknowledge is idempotent |
| `web/ui/src/app/page.tsx:239-262` | Acknowledge action | ✅ Relies on WebSocket update |

**Evidence of Issue:**
```python
# web/api/app/api/v1/controls.py:156-164
audit = CommandAudit(
    control_id=control.id,
    # ... no idempotency_key check before insert
)
db.add(audit)
```

**Action Items:**
- [ ] Add `idempotency_key` to `CommandAudit` model
- [ ] Add `CommandLog` deduplication in `controls.py:110`

---

### 4. Efficiency & Resource Utilization — File Mapping

| File | Pattern | Assessment |
|------|---------|-----------|
| `web/ui/src/app/page.tsx:46-89` | Full RTU fetch on update | ⚠️ Fetches all RTUs + inventory per RTU |
| `web/ui/src/app/alarms/page.tsx:134-167` | Parallel fetches | ✅ `Promise.all` for active/history/shelved |
| `web/ui/src/app/trends/page.tsx:130-146` | Sequential tag fetches | ⚠️ `for...of` loop, not parallelized |
| `web/api/app/api/websocket.py:100-104` | Connection cleanup | ✅ Dead connections removed |

**Efficiency Issue (trends/page.tsx:130-146):**
```typescript
for (const tagId of selectedTags) {
  // Sequential fetches — should use Promise.all
  const res = await fetch(`/api/v1/trends/${tagId}?...`);
}
```

**Action Items:**
- [ ] Parallelize trend data fetches with `Promise.all`
- [ ] Add `?fields=` parameter for selective RTU fetches

---

### 5. Resilience & Fault Tolerance — File Mapping

| File | Mechanism | Findings |
|------|-----------|----------|
| `web/api/app/services/profinet_client.py:52-79` | Simulation mode | ✅ Falls back cleanly |
| `web/api/app/main.py:104-110` | Health endpoint | ⚠️ Minimal: Only timestamp/status |
| `web/ui/src/hooks/useWebSocket.ts:117-121` | Reconnection | ✅ Exponential backoff |
| `web/ui/src/app/page.tsx:381-406` | Degraded mode UI | ✅ Shows polling/disconnected states |
| `web/ui/src/app/alarms/page.tsx:350-367` | Error display | ✅ Retry button with error details |

**Health Endpoint Gap (`main.py:104-110`):**
```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",  # Always "healthy" — no subsystem checks
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
```

**Action Items:**
- [ ] Expand health endpoint with subsystem status
- [ ] Add circuit breaker to `shm_client.py`

---

### 6. Testing Strategy — File Mapping

| File | Type | Field-Runnable |
|------|------|---------------|
| `web/api/tests/conftest.py` | Fixtures | ✅ In-memory SQLite |
| `web/api/tests/test_templates.py` | Unit | ✅ Schema validation tests |
| `web/api/tests/test_pid.py` | Unit | ✅ PID algorithm tests |
| `web/api/tests/test_backup.py` | Integration | ✅ Backup/restore flow |
| `web/api/tests/integration/test_profinet_live.py` | Integration | ❌ Requires hardware |

**Test Coverage Gaps:**
```
Missing:
├── test_failure_modes.py     # Controller unavailable, SHM disconnect
├── test_idempotency.py       # Duplicate command handling
├── test_performance.py       # Resource limits under load
└── web/ui/src/__tests__/     # No UI tests directory exists
```

**Action Items:**
- [ ] Add `test_failure_modes.py` with mocked SHM client
- [ ] Add UI component tests with React Testing Library

---

### 7. Dynamic Configuration — File Mapping

| File | Static Assumption | Impact |
|------|------------------|--------|
| `web/api/app/api/v1/discover.py` | 5000ms timeout | ⚠️ Hardcoded |
| `web/ui/src/app/page.tsx:229` | 5s poll interval | ⚠️ Fixed |
| `web/ui/src/hooks/useWebSocket.ts:61-62` | 3000ms reconnect, 10 attempts | ⚠️ Fixed |
| `web/ui/src/lib/api.ts:448` | 5000ms discovery timeout | ⚠️ Duplicated |

**Hardcoded Value Example:**
```typescript
// web/ui/src/app/page.tsx:229
pollIntervalRef.current = setInterval(fetchData, 5000);  // Fixed 5s
```

**Action Items:**
- [ ] Create `TimeoutConfig` class with env-var overrides
- [ ] Pass poll interval as prop/context in UI

---

### 8. Operational Simplicity — File Mapping

| File | Operator Impact | Findings |
|------|----------------|----------|
| `web/api/app/core/exceptions.py` | Error codes | ⚠️ Technical: `PROFINET_ERROR` |
| `web/api/app/core/errors.py:19-34` | Error mapping | ⚠️ HTTP codes, not operator guidance |
| `web/ui/src/app/wizard/page.tsx` | Setup wizard | ✅ Present |
| `web/ui/src/app/system/page.tsx` | System status | ⚠️ Requires navigation |
| `web/ui/src/app/page.tsx:286-304` | Error state | ✅ Retry button, clear message |

**Operator Message Gap:**
```python
# web/api/app/core/errors.py:19-34 — Maps to HTTP codes only
ERROR_CODE_STATUS_MAP = {
    "PROFINET_ERROR": 502,  # No human explanation
}
```

**Action Items:**
- [ ] Add `OPERATOR_MESSAGES` dict with plain-language descriptions
- [ ] Surface suggested_action in UI error displays

---

### 9. Power Awareness — File Mapping

| File | Idle Behavior | Findings |
|------|--------------|----------|
| `web/ui/src/app/page.tsx:225-236` | Polling always starts | ⚠️ No visibility check |
| `web/ui/src/app/alarms/page.tsx:222-231` | Same pattern | ⚠️ No idle detection |
| `web/ui/src/app/trends/page.tsx:209-222` | Auto-refresh toggle | ✅ User control |
| `web/ui/src/hooks/useWebSocket.ts:184-190` | Connect on mount | ✅ Disconnect on unmount |

**Power Issue (page.tsx:225-236):**
```typescript
useEffect(() => {
  fetchData();
  pollIntervalRef.current = setInterval(fetchData, 5000);
  // No document.hidden check — polls even when tab is hidden
  return () => { ... };
}, [fetchData]);
```

**Action Items:**
- [ ] Add `visibilitychange` listener to pause polling
- [ ] Reduce poll rate when system is stable (no recent changes)

---

### 10. Long-Term Maintainability — File Mapping

| File | Maintainability | Findings |
|------|----------------|----------|
| `web/api/app/models/rtu.py:30-48` | State constants | ✅ `RtuState`, `SlotStatus` classes |
| `web/api/app/services/profinet_client.py` | Documentation | ✅ Docstrings on all methods |
| `web/ui/src/hooks/useWebSocket.ts:21-53` | Usage docs | ✅ JSDoc with examples |
| `web/api/app/persistence/base.py` | Schema docs | ⚠️ Schema comments minimal |
| All | Magic numbers | ⚠️ Timeouts scattered |

**Scattered Magic Numbers:**
```python
# Found in multiple files:
# web/api/app/api/v1/discover.py: timeout_ms=5000
# web/ui/src/hooks/useWebSocket.ts: reconnectInterval = 3000
# web/ui/src/lib/api.ts: discoverRTUs(timeoutMs = 5000)
```

**Action Items:**
- [ ] Create `constants.py` for backend timeouts
- [ ] Create `config.ts` for frontend timeouts
- [ ] Document state machine in `models/rtu.py`

---

## Appendix C: Consolidated Action Items — ✅ ALL COMPLETED

### Immediate (High Priority) — ✅ COMPLETED

| Item | File | Action | Status |
|------|------|--------|--------|
| 1 | `controls.py` | Add idempotency key check | ✅ Done |
| 2 | `main.py` | Expand health endpoint with subsystems | ✅ Done |
| 3 | `package.json` | Add OpenAPI TypeScript generation | ✅ Done |
| 4 | `errors.py` | Add OPERATOR_MESSAGES mapping | ✅ Done |

### Short-Term (Medium Priority) — ✅ COMPLETED

| Item | File | Action | Status |
|------|------|--------|--------|
| 5 | `rtu_service.py` | Extract DB logic to service layer | ✅ Done |
| 6 | `trends/page.tsx` | Parallelize with `Promise.all` | ✅ Done |
| 7 | `page.tsx` | Add `visibilitychange` handler | ✅ Done |
| 8 | `test_failure_modes.py` | Add failure mode tests | ✅ Done |

### Long-Term (Low Priority) — ✅ COMPLETED

| Item | File | Action | Status |
|------|------|--------|--------|
| 9 | `config.py` | Create `TimeoutConfig` with env-var overrides | ✅ Done |
| 10 | `shm_client.py` | Add circuit breaker | ✅ Done |
| 11 | `rtu.py` | Document state machine invariants | ✅ Done |
| 12 | `jest.config.js` | Add UI component test infrastructure | ✅ Done |
