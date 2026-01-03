# Tech Debt Audit Report
## Water Treatment Controller SCADA System
**Date:** 2026-01-03
**Auditor:** Claude Code (claude-opus-4-5-20251101)

---

## Executive Summary

| Section | Grade | Key Issues |
|---------|-------|------------|
| Overall Architecture | **A-** | Clean separation, good patterns |
| Backend Python Code | **B+** | Some duplication, legacy shims |
| Frontend TypeScript/React | **A-** | Well-structured, good constants |
| Database/Persistence | **B** | Dual model systems, redundancy |
| Docker/Infrastructure | **A** | Security-conscious, well-configured |
| Shell Scripts | **B+** | Comprehensive but verbose |
| Configuration Management | **A-** | Good env var usage, some hardcoding |
| Code Duplication | **C+** | Significant overlapping patterns |
| Error Handling | **A** | Excellent exception hierarchy |

**Overall Grade: B+**

---

## Section 1: Backend Python Code

### Grade: B+

#### Strengths
1. **Clean API structure** (`web/api/app/api/v1/`): Routes are thin, business logic delegated to services
2. **Comprehensive exception hierarchy** (`core/exceptions.py`): All errors follow a consistent pattern with `code`, `message`, `recoverable`, `suggested_action`
3. **Type hints throughout**: Modern Python 3.10+ typing syntax
4. **Environment-based configuration** (`core/config.py`): All timeouts/settings configurable via env vars
5. **Circuit breaker pattern** (`shm_client.py:942-1091`): Production-ready resilience

#### Issues Found

**ISSUE 1: Legacy Shim File - `db_persistence.py`**
- **Location:** `web/api/db_persistence.py:1-228`
- **Problem:** This file exists solely to re-export everything from `app.persistence`. It adds 228 lines of pure duplication.
- **Recommendation:** Add deprecation warnings, set a removal timeline, update imports across codebase

**ISSUE 2: Duplicate RTU State Definitions**
- **Location 1:** `web/api/app/models/rtu.py:27-102` (class `RtuState`)
- **Location 2:** `web/api/shm_client.py:90-105` (constants `CONN_STATE_*`)
- **Problem:** RTU states defined in two places with different naming conventions
- **Recommendation:** Create single source of truth, import in both locations

**ISSUE 3: Hardcoded Default Values in Persistence Layer**
- **Location:** `web/api/app/persistence/rtu.py:95-98`
```python
vendor_id=device.get('vendor_id', 1171),  # Magic number
device_id=device.get('device_id', 1),
slot_count=device.get('slot_count', 16),
```
- **Recommendation:** Move to constants file or configuration

**ISSUE 4: Similar `*_to_dict()` Conversion Patterns**
- **Locations:**
  - `persistence/rtu.py:17-68`
  - `services/alarm_service.py:174-194`
  - `services/rtu_service.py:143-167`
- **Problem:** Each module has its own `*_to_dict()` functions with similar logic
- **Recommendation:** Use Pydantic model's `.model_dump()` consistently, or create a mixin

---

## Section 2: Frontend TypeScript/React

### Grade: A-

#### Strengths
1. **Excellent constants organization** (`constants/index.ts`, `constants/rtu.ts`, `constants/timing.ts`)
2. **Type-safe state constants** with `as const` assertions
3. **ISA-101 compliance** for HMI design (documented in `page.tsx:1-13`)
4. **Comprehensive timing configuration** with embedded device variants
5. **Utility functions for state checking** (`isActiveState()`, `isErrorState()`)

#### Issues Found

**ISSUE 5: Frontend/Backend State Mismatch Risk**
- **Location:**
  - Frontend: `constants/rtu.ts:6-12` defines `RTU_STATES`
  - Backend: `models/rtu.py:77-81` defines `RtuState`
- **Problem:** States are defined independently on both ends
- **Recommendation:** Generate frontend types from backend schema, or use shared JSON Schema

**ISSUE 6: Hardcoded Polling Message**
- **Location:** `web/ui/src/app/page.tsx:153`
```tsx
<span>Polling Mode:</strong> WebSocket disconnected. Data updates every 5 seconds.</span>
```
- **Problem:** Hardcoded "5 seconds" when actual value is from `TIMING.POLLING.NORMAL`
- **Recommendation:** Interpolate the constant value

**ISSUE 7: Inline SVG Icons**
- **Location:** Multiple components in `page.tsx:184-207` and throughout components
- **Problem:** Same SVG paths repeated across components
- **Recommendation:** Use `components/icons/index.tsx` consistently

---

## Section 3: Database/Persistence Layer

### Grade: B

#### Strengths
1. **Well-modularized** (`persistence/base.py`, `persistence/rtu.py`, etc.)
2. **SQLAlchemy ORM with proper session management**
3. **Singleton pattern for config tables** (`_init_singleton_configs()`)
4. **Audit logging integrated** (`log_audit()` calls)

#### Issues Found

**ISSUE 8: Dual Model Systems**
- **Location 1:** `web/api/app/models/rtu.py` - SQLAlchemy ORM models (`RTU`, `Sensor`, `Control`)
- **Location 2:** `web/api/app/models/legacy.py` - Separate legacy models (`RtuDevice`, `RtuSensor`, `RtuControl`)
- **Location 3:** `web/api/app/persistence/rtu.py` - Uses legacy models
- **Problem:** Two parallel model hierarchies for the same entities
- **Recommendation:** Migrate fully to the new ORM models, deprecate legacy

**ISSUE 9: Context Manager Inconsistency**
- **Location 1:** `persistence/base.py:49-60` - `get_db()` is a context manager
- **Location 2:** `models/base.py` - Separate `get_db()` for FastAPI dependency injection
- **Problem:** Two different `get_db()` patterns cause confusion
- **Recommendation:** Unify or clearly namespace (e.g., `get_db_context()` vs `get_db_dependency()`)

---

## Section 4: Docker/Infrastructure

### Grade: A

#### Strengths
1. **Security hardening** (`user: "1000:1000"`, `user: "472:472"`)
2. **Resource limits** on all containers (DCK-H3 fixes noted in comments)
3. **Health checks** on all services
4. **Internal network for database** (not exposed to host)
5. **Environment-based port configuration**
6. **Profiles for optional services** (`profinet`)

#### Minor Issues

**ISSUE 10: Deprecated `version` Key**
- **Location:** `docker/docker-compose.yml:15`
```yaml
version: "3.9"
```
- **Problem:** Docker Compose v2 ignores this, it's deprecated
- **Recommendation:** Remove the `version` key

**ISSUE 11: Grafana Default Password**
- **Location:** `docker/docker-compose.yml:164`
```yaml
GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
```
- **Problem:** Default password "admin" is weak
- **Recommendation:** Require explicit password or generate random default

---

## Section 5: Shell Scripts

### Grade: B+

#### Strengths
1. **Comprehensive installation script** (`scripts/install.sh` - 1884 lines)
2. **Modular library structure** (`scripts/lib/`)
3. **Proper error handling** (`set -euo pipefail`)
4. **Dry-run mode** for safe testing
5. **Rollback capability** for upgrades
6. **Detailed logging** with timestamps

#### Issues Found

**ISSUE 12: Hardcoded Default Paths**
- **Location:** `scripts/install.sh:29-33`
```bash
readonly DEFAULT_INSTALL_DIR="/opt/water-controller"
readonly DEFAULT_CONFIG_DIR="/etc/water-controller"
readonly DEFAULT_DATA_DIR="/var/lib/water-controller"
```
- **Note:** These are appropriate for FHS compliance, but could be centralized

**ISSUE 13: Long Monolithic Functions**
- **Location:** `scripts/install.sh:1192-1413` (`do_uninstall()` - 221 lines)
- **Recommendation:** Break into smaller helper functions

**ISSUE 14: Duplicate Log Functions**
- **Location:** `scripts/install.sh:87-98` defines `_early_log*` functions
- **Problem:** These duplicate functionality in `lib/common.sh`
- **Recommendation:** Load common.sh earlier or consolidate

---

## Section 6: Code Duplication Analysis

### Grade: C+

#### Major Duplication Issues

| Pattern | Locations | Lines Affected |
|---------|-----------|----------------|
| RTU state definitions | 3 files | ~100 lines |
| `*_to_dict()` converters | 4 files | ~150 lines |
| Alarm listing logic | endpoint + service | ~80 lines |
| Database connection boilerplate | 2 patterns | ~40 lines |
| Legacy model re-exports | db_persistence.py | 228 lines |

**ISSUE 15: Alarm Query Duplication**
- **Location 1:** `api/v1/alarms.py:37-108` (`list_alarms()`)
- **Location 2:** `services/alarm_service.py:40-85` (`list_active_alarms()`)
- **Problem:** Nearly identical query logic in both places
- **Recommendation:** Route handler should call service exclusively

**ISSUE 16: Connection State Names Duplication**
- **Location 1:** `shm_client.py:98-105`
```python
CONNECTION_STATE_NAMES = {
    CONN_STATE_IDLE: "IDLE",
    CONN_STATE_CONNECTING: "CONNECTING",
    ...
}
```
- **Location 2:** `services/profinet_client.py:32-35`
```python
CONNECTION_STATE_NAMES = {
    0: "IDLE", 1: "CONNECTING", 2: "CONNECTED",
    3: "RUNNING", 4: "ERROR", 5: "OFFLINE"
}
```
- **Problem:** Same mapping defined twice
- **Recommendation:** Import from `shm_client` or create shared constants module

---

## Section 7: Hardcoded Strings/Values

### Grade: B

#### Values That Should Be Constants/Config

| Location | Hardcoded Value | Recommendation |
|----------|-----------------|----------------|
| `shm_client.py:51` | `MAX_SHM_RTUS = 64` | Good - named constant |
| `persistence/rtu.py:95` | `vendor_id=1171` | Move to `core/constants.py` |
| `persistence/rtu.py:97` | `slot_count=16` | Move to `core/constants.py` |
| `page.tsx:153` | `"5 seconds"` | Use `TIMING.POLLING.NORMAL / 1000` |
| `main.py:112` | `version="2.0.0"` | Load from `__version__` or pyproject.toml |
| `install.sh:23` | `INSTALLER_VERSION="1.0.0"` | Should match package version |
| `docker-compose.yml:164` | `admin` (password) | Require explicit configuration |

#### Well-Managed Constants
- Frontend timing config (`constants/timing.ts`) - **Excellent**
- Backend timeout config (`core/config.py`) - **Excellent**
- Shared memory protocol constants (`shm_client.py:47-89`) - **Good**
- RTU state machine (`models/rtu.py:27-102`) - **Good documentation**

---

## Section 8: Programmatic Improvements

### Areas Where Logic Can Replace Hardcoding

**ISSUE 17: State Machine Transition Validation**
- **Current:** `RtuState.can_connect()`, `can_disconnect()`, `can_delete()` are hardcoded lists
- **Improvement:** Use a state machine library or transition matrix
```python
# Instead of:
return current_state in (cls.OFFLINE, cls.ERROR)

# Use:
TRANSITIONS = {
    ('OFFLINE', 'connect'): 'CONNECTING',
    ('ERROR', 'connect'): 'CONNECTING',
    ...
}
def can_transition(from_state, action):
    return (from_state, action) in TRANSITIONS
```

**ISSUE 18: Sensor Quality Mapping**
- **Current:** `shm_client.py:118-129` and `profinet_client.py:37`
- **Improvement:** Derive names from constants programmatically
```python
# Instead of separate QUALITY_NAMES dict, use:
def quality_name(code: int) -> str:
    for name, value in vars(Quality).items():
        if value == code and not name.startswith('_'):
            return name.lower()
    return "unknown"
```

**ISSUE 19: Error Response Construction**
- **Current:** Each exception type constructs its response
- **Improvement:** Auto-generate from exception class attributes

---

## Section 9: Recommendations Summary

### High Priority (Technical Debt Impacting Development)

1. **Unify model systems** - Migrate from legacy models to ORM-only (`models/rtu.py`)
2. **Remove `db_persistence.py` shim** - Direct imports from `persistence/`
3. **Consolidate state definitions** - Single source of truth for RTU/connection states
4. **Fix alarm query duplication** - Route should only call service

### Medium Priority (Code Quality)

5. **Centralize default values** - Create `core/defaults.py` for magic numbers
6. **Standardize `*_to_dict()` patterns** - Use Pydantic exclusively
7. **Generate frontend types from backend** - Use OpenAPI schema
8. **Extract inline SVGs** - Consistent icon component usage

### Low Priority (Polish)

9. **Remove docker-compose `version` key**
10. **Require explicit Grafana password**
11. **Break up long shell functions**
12. **Version string consistency**

---

## Section 10: Positive Patterns to Preserve

1. **Exception hierarchy** in `core/exceptions.py` - Keep and extend
2. **Circuit breaker** in `shm_client.py` - Production-ready pattern
3. **Startup validation** in `main.py` - Critical for SCADA reliability
4. **Service layer pattern** (`services/rtu_service.py`) - Good separation
5. **Centralized port configuration** (`core/ports.py`) - Single source of truth
6. **Timing constants** in frontend - Well-organized, type-safe
7. **Docker security practices** - Non-root users, resource limits
8. **Comprehensive install script** - Professional deployment tooling

---

## Final Assessment

The Water-Controller codebase is **production-quality** with a mature architecture. The main technical debt stems from:

1. **Incomplete migration** from legacy persistence patterns
2. **Organic duplication** from rapid feature development
3. **Frontend/backend type synchronization** gaps

The codebase demonstrates strong engineering practices:
- Type safety (Python type hints, TypeScript)
- Error handling (comprehensive exception hierarchy)
- Configuration management (environment-based)
- Security consciousness (Docker hardening, auth patterns)

**Recommended next steps:**
1. Address High Priority items during next refactor sprint
2. Add deprecation warnings to legacy code paths
3. Set up automated type generation from OpenAPI schema
4. Consider adding a shared constants package (npm/pip)

---

*Report generated by Claude Code tech debt audit*
