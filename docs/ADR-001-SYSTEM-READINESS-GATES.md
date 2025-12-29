# ADR-001: System Readiness Gates and Anti-Pattern Remediation

**Status:** Implemented
**Date:** 2024-12-29
**Authors:** System Review Implementation

---

## Context

A full lifecycle review of the Water-Controller system identified fundamental anti-patterns causing the system to appear "installed", "running", and "reachable" while being **fundamentally non-functional**.

The core problem: The system was optimized for developer convenience and iterative experimentation, but was being used as production-grade field software.

---

## Decision

Shift the operational mindset from:
> "Did the process start?"

To:
> "Is the system actually usable?"

This requires implementing **readiness gates** at every layer.

---

## Anti-Patterns Addressed

### 1. "Install succeeds ≠ system usable"

**Problem:** Installation script reported "installed" even when:
- PROFINET build failed
- UI not built
- Runtime paths mismatched

**Solution:** Post-install verification gate (`verify_install_complete()` in `scripts/lib/validation.sh`)

```bash
# After install, BEFORE declaring success:
verify_install_complete || {
    log_error "Installation verification FAILED"
    exit 5
}
```

**Key checks:**
- Binaries exist at expected paths
- UI `.next/` build directory exists with `build-manifest.json`
- Database directory writable
- Python can import required modules
- P-Net library installed

---

### 2. "Process-alive ≠ System-ready"

**Problem:** `systemctl status` shows "active" but:
- UI assets may be missing
- IPC may be broken
- PROFINET may not be functional

**Solution:**
- Systemd `ConditionPathExists` for critical files
- `ExecStartPre` validation before service start
- Python startup validation (`app/core/startup.py`)

**Systemd service pattern:**
```ini
[Unit]
# Fail to start if critical files missing
ConditionPathExists=/opt/water-controller/venv/bin/uvicorn
ConditionPathExists=/opt/water-controller/app/app/main.py

[Service]
# Validate before starting
ExecStartPre=/bin/bash -c 'test -d /var/lib/water-controller || exit 1'
ExecStartPre=/bin/bash -c '/opt/water-controller/venv/bin/python3 -c "import fastapi" || exit 1'
```

**Python startup validation:**
```python
from app.core.startup import validate_startup, StartupMode

result = validate_startup(mode=StartupMode.PRODUCTION)
if not result.can_serve_traffic:
    result.log_all()
    sys.exit(1)
```

---

### 3. "Port open ≠ application usable"

**Problem:** Port opens, browser loads *something*, but:
- HTML shell loads with missing JS/CSS
- WebSocket fails silently
- Empty pages with no warning

**Solution:** Health endpoints validate actual functionality:
- `/health` includes UI asset verification
- `/api/v1/health/functional` checks all subsystems
- Returns degraded status with actionable guidance

**Health check pattern:**
```python
ui_status = get_ui_asset_status()
if not ui_status["available"]:
    return {
        "status": "unhealthy",
        "ui_assets": {
            "status": "error",
            "action": "Build UI: cd /opt/water-controller/web/ui && npm run build"
        }
    }
```

---

### 4. "UI treated as optional"

**Problem:** System allowed to start without built UI, leaving operators with no interface.

**Solution:**
- UI service has `ConditionPathExists` for build artifacts
- Health checks treat missing UI as **critical failure**
- Clear error messages guide operator to fix

**Critical paths for UI:**
```
/opt/water-controller/web/ui/.next/build-manifest.json
/opt/water-controller/web/ui/.next/static/
/opt/water-controller/web/ui/.next/server/
```

---

### 5. "Logs as developer artifacts"

**Problem:** Logs describe *what happened* but not:
- Why it matters
- What still works
- What the operator should do

**Solution:** Operator-focused logging (`app/core/logging.py`)

```python
from app.core.logging import operator_log

operator_log.error(
    what="Database connection failed",
    impact="Cannot store sensor readings. Configuration changes will not persist.",
    still_works="RTU monitoring and PROFINET communication continue.",
    action="Check database status: sqlite3 /var/lib/water-controller/wtc.db '.tables'"
)
```

**Log format:**
```
WHAT: Database connection failed | IMPACT: Cannot store sensor readings... | STILL WORKS: RTU monitoring... | ACTION: Check database...
```

---

### 6. "Silent fallbacks"

**Problem:** UI treats "no data" as "nothing to show" with no warning.

**Solution:** Explicit degraded mode states in UI (`SystemStatusIndicator.tsx`)

**States:**
- `connecting` - Initial connection attempt
- `connected` - Fully operational
- `reconnecting` - Lost connection, attempting recovery
- `stale` - Data older than threshold
- `degraded` - Partial functionality
- `disconnected` - No connection
- `error` - Error state

**Data freshness indicators show:**
- Time since last update
- Visual warning when stale (>30s)

---

### 7. Non-deterministic dependency resolution

**Problem:**
- Cloning live GitHub repos at install time
- Falling back to `master` branches
- Install results vary by day

**Solution:** Version manifest (`versions.json`)

```json
{
  "system": {
    "p_net": {
      "repo": "https://github.com/rtlabs-com/p-net.git",
      "commit": "v1.0.1",
      "_reason": "PROFINET stack - pinned to stable release"
    }
  }
}
```

---

## Port Configuration Reference

| Service | Port | Variable | Purpose |
|---------|------|----------|---------|
| API (FastAPI) | 8000 | `API_PORT` | REST API, WebSocket |
| UI (Next.js) | 8080 | `UI_PORT` | Operator HMI |
| Modbus TCP | 502 | - | SCADA integration |
| PROFINET | 34962-34964 | - | Industrial protocol |

**Environment file (`/etc/water-controller/environment`):**
```bash
API_PORT=8000
UI_PORT=8080
```

---

## Path Configuration Reference

| Purpose | Path | Variable |
|---------|------|----------|
| Installation | `/opt/water-controller` | `WTC_INSTALL_DIR` |
| Configuration | `/etc/water-controller` | `WTC_CONFIG_DIR` |
| Data/Database | `/var/lib/water-controller` | `WTC_DATA_DIR` |
| Logs | `/var/log/water-controller` | `WTC_LOG_DIR` |
| UI Build | `/opt/water-controller/web/ui/.next` | `WTC_UI_DIST_DIR` |
| Python venv | `/opt/water-controller/venv` | - |

All paths centralized in `app/core/paths.py` with validation.

---

## Files Modified/Created

### New Files
- `web/api/app/core/paths.py` - Centralized path configuration
- `web/api/app/core/startup.py` - Startup validation
- `web/ui/src/components/hmi/SystemStatusIndicator.tsx` - UI status display
- `versions.json` - Dependency version manifest
- `docs/ADR-001-SYSTEM-READINESS-GATES.md` - This document

### Modified Files
- `web/api/app/main.py` - Startup gate integration
- `web/api/app/api/v1/system.py` - UI asset health check
- `web/api/app/core/logging.py` - Operator logging
- `scripts/lib/validation.sh` - Post-install verification
- `scripts/install-hmi.sh` - Service startup, port fixes
- `systemd/water-controller-api.service` - Readiness checks
- `systemd/water-controller-ui.service` - Readiness checks
- `systemd/water-controller-hmi.service` - Port variable fix

---

## Verification Commands

### Check system readiness
```bash
# Full validation suite
/opt/water-controller/scripts/lib/validation.sh --full

# Quick health check
curl http://localhost:8000/health

# Functional health check
curl http://localhost:8000/api/v1/health/functional
```

### Check UI build
```bash
# Verify UI is built
test -f /opt/water-controller/web/ui/.next/build-manifest.json && echo "UI built" || echo "UI NOT BUILT"

# Rebuild if needed
cd /opt/water-controller/web/ui && npm run build
```

### Check service status
```bash
# Service status with startup validation
systemctl status water-controller-api
systemctl status water-controller-ui

# View startup validation errors
journalctl -u water-controller-api --since "5 min ago" | grep -E "(ERROR|ExecStartPre)"
```

---

## Consequences

### Positive
- System fails fast when not usable
- Clear operator guidance on failures
- Reproducible installations
- Explicit degraded states visible to operators

### Negative
- More startup checks = slightly longer startup time
- Stricter validation may block previously-tolerated misconfigurations
- Requires UI to be built before service can start

### Mitigation
- Development mode (`WTC_STARTUP_MODE=development`) allows degraded operation
- Clear error messages guide operators to resolution
- Pre-flight checks run in parallel where possible

---

## Related Documents

- `HARMONIOUS_SYSTEM_DESIGN.md` - Core design philosophy
- `DEPLOYMENT.md` - Deployment procedures
- `TROUBLESHOOTING_GUIDE.md` - Issue resolution
