# Network Discovery and RTU Communication Audit Report

**Date**: 2026-01-19
**Auditor**: Claude Code
**Scope**: Discovery endpoints, container networking, RTU health/inventory endpoints, WebSocket implementation, error handling

---

## Executive Summary

This audit examined the Water-Controller codebase to verify patterns related to mock/stub implementations, container network isolation, and missing endpoints. **The findings significantly differ from the initial assessment in several key areas:**

1. **Discovery Implementation**: The system is NOT returning hardcoded mock data by default. It uses a **fallback architecture** that prioritizes real controller data via shared memory, with demo mode as a configurable simulation layer.

2. **Container Networking**: The architecture is **intentionally designed** with API container isolation. Physical network access is handled by the C controller running with `network_mode: host`, communicating with the API via shared memory IPC.

3. **Missing Endpoints**: Two endpoints ARE confirmed missing: `/api/v1/rtus/{name}/health` and `/api/v1/rtus/{name}/inventory`. The UI calls these but they return 404.

4. **WebSocket**: The implementation is complete with proper publisher lifecycle management. Data flow depends on the PROFINET client/demo mode being active.

---

## 1. Discovery Endpoints Audit

### 1.1 POST /api/v1/discover/rtu (DCP Discovery)

**Location**: `web/api/app/api/v1/discover.py:73-167`

**Actual Behavior** (differs from initial assessment):

```
Priority Order:
1. IF controller running via shared memory → Real DCP discovery
2. ELSE → Return configured RTUs from database with "Simulation Mode" vendor name
```

**Key Finding**: The endpoint does NOT return fake "Demo-Vendor" devices on 192.168.1.x by default. The mock data only appears when:
- `WTC_DEMO_MODE=1` or `WTC_SIMULATION_MODE=1` environment variable is set
- The C controller is not running (shared memory unavailable)

**Evidence** (discover.py:103-129):
```python
# Try real DCP discovery via controller
profinet = get_profinet_client()
if profinet.is_controller_running():
    discovered = profinet.dcp_discover(timeout_ms)
    # ... processes real devices
else:
    # Controller not running - return configured RTUs for HMI testing
    # ... returns database RTUs with vendor_name="Simulation Mode"
```

**Demo Mode Behavior** (demo_mode.py:356-377):
When demo mode IS enabled, `dcp_discover()` returns simulated devices with:
- `vendor_name: "Demo-Vendor"`
- IPs: 192.168.1.10-14, 192.168.1.100

### 1.2 POST /api/v1/discover/ping-scan

**Location**: `web/api/app/api/v1/discover.py:279-320`

**Actual Behavior**: This is a **real implementation**, not a mock:

```python
async def ping_host(ip: str, timeout_ms: int) -> PingResult:
    proc = await asyncio.create_subprocess_exec(
        "ping", "-c", "1", "-W", str(max(1, int(timeout_sec))), ip,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
```

**Issue Confirmed**: The ping scan will fail to reach physical network hosts when:
- API container is running in Docker bridge network mode (default)
- Hosts are on a different subnet not routed through Docker

**Root Cause**: Not a mock implementation issue, but a **network routing** issue. The ping implementation is real, but container network isolation prevents reaching physical hosts.

---

## 2. Container Network Configuration Audit

### 2.1 Architecture Overview

The network architecture is **intentionally tiered**:

| Component | Network Mode | Purpose |
|-----------|--------------|---------|
| wtc-controller | `network_mode: host` | Direct physical network access for PROFINET |
| wtc-api | Bridge (wtc-network) | Isolated for security, IPC via shared memory |
| wtc-database | Bridge (internal) | Fully isolated |

**Key Finding**: This is a **security-conscious design**, not a bug. The API container should NOT have direct physical network access.

### 2.2 Controller Capabilities

**Location**: `docker/docker-compose.yml:100-103`
```yaml
controller:
  network_mode: host
  cap_add:
    - NET_ADMIN
    - NET_RAW
```

The C controller has proper capabilities for:
- `CAP_NET_RAW`: Required for raw socket operations (PROFINET DCP)
- `CAP_NET_ADMIN`: Required for interface configuration

### 2.3 API-Controller Communication

**Method**: Shared memory IPC via `/dev/shm/wtc`

The API container does NOT need physical network access because:
1. PROFINET communication is handled by the C controller
2. Controller writes data to shared memory
3. API reads from shared memory via `shm_client` module

**Evidence** (profinet_client.py:28-44):
```python
try:
    from shm_client import (
        get_client,
        # ...
    )
    SHM_AVAILABLE = True
except ImportError:
    SHM_AVAILABLE = False
    # Falls back to simulation mode
```

### 2.4 Impact on Ping Scan

The ping scan endpoint runs in the API container. To reach physical hosts on 192.168.6.0/24:

**Current State**: Pings from API container will only reach:
- Other Docker containers on wtc-network
- Host machine (via Docker gateway)
- Internet (if Docker network has outbound routing)

**Will NOT reach**: Physical devices on local LAN segments unless Docker network is configured with proper routing.

---

## 3. Missing Endpoints Audit

### 3.1 GET /api/v1/rtus/{name}/health - CONFIRMED MISSING

**UI Reference**: `web/ui/src/app/rtus/page.tsx:127`
```javascript
const res = await fetch(`/api/v1/rtus/${stationName}/health`);
```

**Expected Response** (from UI type):
```typescript
interface RTUHealth {
  station_name: string;
  connection_state: string;
  healthy: boolean;
  packet_loss_percent: number;
  consecutive_failures: number;
  in_failover: boolean;
}
```

**Current Behavior**: Returns 404 (no endpoint exists)

**Impact**: UI silently fails and shows incomplete RTU health information.

### 3.2 GET /api/v1/rtus/{name}/inventory - CONFIRMED MISSING

**UI Reference**: `web/ui/src/lib/api.ts:457-458`
```typescript
export async function getRTUInventory(stationName: string): Promise<RTUInventory> {
  return apiFetch<RTUInventory>(`/api/v1/rtus/${encodeURIComponent(stationName)}/inventory`);
}
```

**Current Behavior**: Returns 404 (no endpoint exists)

**Impact**: Cannot view RTU slot/module configuration through the UI.

### 3.3 Existing Related Endpoints

These endpoints DO exist and work:
- `GET /api/v1/rtus/{name}` - RTU details with stats
- `GET /api/v1/rtus/{name}/profinet/status` - PROFINET connection status
- `GET /api/v1/rtus/{name}/profinet/slots` - Returns empty array (TODO implementation)
- `POST /api/v1/rtus/{name}/discover` - Module discovery (returns empty)

---

## 4. WebSocket Implementation Audit

### 4.1 WebSocket Handler

**Location**: `web/api/app/api/websocket.py`

**Endpoint**: `GET /api/v1/ws/live`

**Status**: **Fully Implemented** - Not a stub

The implementation includes:
- Channel-based subscription model
- RTU filtering support
- Connection manager with automatic cleanup
- Heartbeat (ping/pong) support

### 4.2 Data Publisher

**Location**: `web/api/app/services/websocket_publisher.py`

**Status**: **Fully Implemented**

The `DataPublisher` class:
- Polls PROFINET client at configurable intervals (default 1000ms)
- Only polls when subscribers are connected (efficient)
- Broadcasts to channels: sensors, controls, alarms, rtu_state, modbus
- Tracks changes to avoid redundant broadcasts

### 4.3 Publisher Lifecycle

**Startup** (main.py:99-100):
```python
# Start WebSocket data publisher for real-time updates
await publisher_lifespan_startup()
```

**Shutdown** (main.py:115):
```python
await publisher_lifespan_shutdown()
```

**Finding**: Publisher lifecycle is properly managed. If no data flows, it's because:
1. No subscribers connected to channels
2. PROFINET client returns empty data (controller not running, demo mode disabled)
3. No RTUs configured in database

---

## 5. Error Response Patterns Audit

### 5.1 Error Handling Framework

**Location**: `web/api/app/core/exceptions.py` and `web/api/app/core/errors.py`

**Status**: **Well-designed** error handling exists

The codebase includes:
- Standardized `ScadaException` base class with:
  - `code`: Machine-readable error code
  - `message`: Technical description
  - `details`: Additional context
  - `recoverable`: Whether retry makes sense
  - `suggested_action`: What to do next

- Operator-friendly messages (errors.py:39-57):
```python
OPERATOR_MESSAGES = {
    "RTU_NOT_CONNECTED": "The device is offline. Check the network cable and verify the device has power.",
    # ... more mappings
}
```

### 5.2 Missing Error Detail

**Issue**: RTU state display shows generic "OFFLINE" without reason.

**Location**: The RTU list endpoint (`rtus.py:83-123`) returns `state` but not a `state_reason` field.

**Current Response**:
```json
{
  "state": "OFFLINE",
  "state_since": "2026-01-19T10:00:00Z"
}
```

**Desired Response**:
```json
{
  "state": "OFFLINE",
  "state_since": "2026-01-19T10:00:00Z",
  "state_reason": "PROFINET AR not established",
  "last_error": "Connection timeout after 5000ms"
}
```

---

## 6. Findings Summary

### 6.1 Validated Issues

| ID | Issue | Severity | Validated |
|----|-------|----------|-----------|
| M1 | Missing `/rtus/{name}/health` endpoint | HIGH | YES |
| M2 | Missing `/rtus/{name}/inventory` endpoint | MEDIUM | YES |
| M3 | Ping scan unreachable from container | MEDIUM | YES (by design) |
| M4 | RTU state lacks reason/detail | LOW | YES |
| M5 | PROFINET slots endpoint returns empty | LOW | YES (TODO in code) |

### 6.2 Invalidated/Clarified Issues

| ID | Claimed Issue | Actual Finding |
|----|---------------|----------------|
| C1 | DCP discovery returns mock data | FALSE - Only in demo mode, real DCP when controller runs |
| C2 | Ping scan returns fake data | FALSE - Real implementation, network routing issue |
| C3 | Container needs host network | FALSE - Intentional security architecture |
| C4 | WebSocket idle | CLARIFIED - Works when data sources active |
| C5 | Demo-Vendor on wrong subnet | CLARIFIED - Demo mode is opt-in, not default |

---

## 7. Recommended Remediations

### 7.1 Implement Missing Health Endpoint (HIGH Priority)

**File**: `web/api/app/api/v1/rtus.py`

```python
@router.get("/{name}/health")
async def get_rtu_health(
    name: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Get RTU health status from PROFINET client."""
    rtu = get_rtu_or_404(db, name)
    profinet = get_profinet_client()

    # Get live state from controller
    controller_state = profinet.get_rtu_state(name)

    return build_success_response({
        "station_name": rtu.station_name,
        "connection_state": controller_state or rtu.state,
        "healthy": rtu.state == RtuState.RUNNING,
        "packet_loss_percent": 0.0,  # From PROFINET stats when available
        "consecutive_failures": 0,
        "in_failover": False,
        "last_error": rtu.last_error,
    })
```

### 7.2 Implement Missing Inventory Endpoint (MEDIUM Priority)

**File**: `web/api/app/api/v1/rtus.py`

```python
@router.get("/{name}/inventory")
async def get_rtu_inventory(
    name: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Get RTU slot/module inventory from PROFINET or database."""
    rtu = get_rtu_or_404(db, name)

    # Get sensors and controls as inventory items
    sensors = db.query(Sensor).filter(Sensor.rtu_id == rtu.id).all()
    controls = db.query(Control).filter(Control.rtu_id == rtu.id).all()

    slots = []
    for sensor in sensors:
        slots.append({
            "slot": sensor.slot_number,
            "type": "input",
            "module_type": "analog_input",
            "tag": sensor.tag,
            "description": sensor.description,
        })
    for control in controls:
        slots.append({
            "slot": control.slot_number,
            "type": "output",
            "module_type": control.control_type,
            "tag": control.tag,
            "description": control.description,
        })

    return build_success_response({
        "station_name": rtu.station_name,
        "slot_count": rtu.slot_count or 0,
        "slots": sorted(slots, key=lambda x: x.get("slot") or 0),
        "last_updated": rtu.updated_at.isoformat() if rtu.updated_at else None,
    })
```

### 7.3 Add State Reason to RTU Response (LOW Priority)

Add `last_error` field to RTU list responses for operator visibility.

### 7.4 Network Diagnostics Enhancement (MEDIUM Priority)

Add a diagnostic endpoint that checks network reachability from the API container's perspective:

```python
@router.get("/diagnostics/network")
async def network_diagnostics() -> dict[str, Any]:
    """Check network reachability for debugging."""
    # Check what the API container can reach
    # Useful for operators debugging connectivity issues
```

---

## 8. Architecture Recommendations

### 8.1 Do NOT Change Container Network Mode

The current architecture is correct:
- C controller with host network for PROFINET
- API with bridge network for isolation
- Communication via shared memory

Adding `network_mode: host` to the API would:
- Reduce security isolation
- Potentially cause port conflicts
- Not be necessary if shared memory IPC works

### 8.2 Document the Architecture

Add clear documentation explaining:
1. Why API container doesn't have physical network access
2. How to verify shared memory communication is working
3. What demo mode does vs. real operation

### 8.3 Consider Proxy Pattern for Network Diagnostics

If ping scan needs to reach physical network, implement a proxy endpoint in the C controller that:
1. Receives requests via shared memory
2. Performs pings from host network namespace
3. Returns results via shared memory

This maintains security while enabling network diagnostics.

---

## 9. Verification Commands

```bash
# Verify controller has host network and capabilities
docker inspect wtc-controller | jq '.[0].HostConfig.NetworkMode'
# Expected: "host"

docker inspect wtc-controller | jq '.[0].HostConfig.CapAdd'
# Expected: ["NET_ADMIN", "NET_RAW"]

# Verify shared memory mount in production
docker inspect wtc-api | jq '.[0].Mounts[] | select(.Destination == "/dev/shm/wtc")'

# Test if demo mode is enabled
curl http://localhost:8000/api/v1/demo/status

# Test health endpoint (should 404 currently)
curl -s http://localhost:8000/api/v1/rtus/test-rtu/health
# Expected: {"detail":"Not Found"}
```

---

## 10. Conclusion

The initial assessment contained several misconceptions about the codebase architecture. The system is **not fundamentally broken** but has specific gaps that need addressing:

1. **Two missing endpoints** that the UI depends on
2. **Network diagnostics** limited by intentional container isolation
3. **State detail** could be improved for operator UX

The mock/demo system is a **feature**, not a bug - it enables testing and training without hardware. The key is ensuring it's clearly opt-in and not confused with production operation.

**Priority Order for Fixes**:
1. P0: Implement `/health` endpoint (UI depends on it)
2. P1: Implement `/inventory` endpoint (UI depends on it)
3. P2: Add state reason to RTU responses
4. P3: Document network architecture for operators
