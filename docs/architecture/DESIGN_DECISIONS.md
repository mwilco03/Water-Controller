# Design Decisions

This document records architectural and implementation decisions for the Water-Controller project.

## 2026-01-20: Demo Mode vs. No-Fallback Policy

### Context

CLAUDE.md establishes a strict "NO DEMO MODE FALLBACKS" policy for production code. However, the codebase contains a demo mode service used for testing.

### Decision

**Demo mode is ALLOWED but must be EXPLICITLY OPT-IN.**

The demo mode in `profinet_client.py` complies with CLAUDE.md because:

1. **Explicit opt-in only**: Requires `WTC_DEMO_MODE=1` environment variable
2. **Does not auto-enable**: When the C controller is unavailable, endpoints return proper errors (503) unless demo mode is explicitly enabled
3. **Clearly marked**: All demo responses include `"demo_mode": true` in the payload
4. **For testing only**: Used for E2E tests and UI development when hardware unavailable

**What is PROHIBITED** (per CLAUDE.md):
- Implicit fallbacks that silently return fake data
- Auto-enabling simulation when real systems are unavailable
- Hiding system unavailability from operators

**What is ALLOWED**:
- Explicit `WTC_DEMO_MODE=1` for testing environments
- Demo data clearly marked as such in responses
- E2E test suites using demo mode

### Implementation

```python
# WRONG - Implicit fallback (violates CLAUDE.md)
if not controller.is_connected():
    return fake_demo_data()  # Hides problem from operator!

# CORRECT - Explicit error when no demo mode
if not controller.is_connected():
    raise HTTPException(status_code=503, detail="Controller not connected")

# CORRECT - Demo mode only when explicitly enabled
if os.environ.get("WTC_DEMO_MODE") == "1":
    # Clearly marked demo data for testing
    return {"data": [...], "demo_mode": True}
```

---

## 2026-01-20: Disabled Frontend Pages

### Context

Two frontend pages were disabled because they called non-existent backend endpoints.

### I/O Tags Page (`/io-tags`)

**Status**: Placeholder with documented workaround

**Background**: Original implementation called `/api/v1/rtus/{name}/slots` endpoints. Per the Slots Architecture Decision in CLAUDE.md, slots are PROFINET frame positions, not database entities. The slots endpoints were removed.

**Workaround** (documented on page):
- View sensors: RTU details page -> Sensors tab
- View controls: RTU details page -> Controls tab
- Historian tags: Trends page -> Tag configuration

**Future implementation**: Refactor to use `/api/v1/rtus/{name}/sensors` and `/api/v1/rtus/{name}/controls` endpoints.

### User Management Page (`/users`)

**Status**: Placeholder with documented workaround

**Background**: No user management API exists. Per CLAUDE.md, passwords are hardcoded for dev/test systems.

**Workaround** (documented on page):
- Single hardcoded user for dev/test
- Session-based auth via `/auth/login`
- Control actions logged to `command_audit` table

**Future implementation options**:
1. `fastapi-users` library for simple user CRUD
2. Keycloak/Authentik for enterprise environments with LDAP/AD

**SCADA requirements** when implementing:
- Role-based access (viewer, operator, engineer, admin)
- Audit trail for all control actions (ISA-62443)
- Session management and timeout enforcement
- Password policies

---

## 2026-01-20: Unimplemented Features

### PDF Export (`/api/v1/trends/export`)

**Status**: Returns 501 Not Implemented

**Reason**: Requires additional library (reportlab, weasyprint, etc.)

**Workaround**: Use CSV export instead

**Implementation note**: When implemented, use proper PDF generation library, not just wrapped HTML.

### PROFINET Slot Diagnostics (`/api/v1/rtus/{name}/profinet/slots`)

**Status**: Implemented via shared memory IPC

**Implementation**: Reads slot data from C controller shared memory. Returns:
- Slot number (PROFINET frame position)
- Slot type (input/output/empty)
- Module info (sensor value or actuator command)
- Live diagnostic data (status, quality codes)

**Requirements**:
- RTU must be in RUNNING state
- C controller must be running with shared memory
- Returns 503 if controller not connected
- Returns 409 if RTU not in RUNNING state

---

## References

- CLAUDE.md: Project coding standards and rules
- `/docs/architecture/ALARM_PHILOSOPHY.md`: Alarm system design
- `/docs/architecture/SYSTEM_DESIGN.md`: Overall architecture
