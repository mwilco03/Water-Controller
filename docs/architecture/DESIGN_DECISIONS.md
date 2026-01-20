# Design Decisions

This document records architectural and implementation decisions for the Water-Controller project. Reference this to prevent regression.

---

## Table of Contents

1. [No Demo Mode Fallbacks](#2026-01-20-demo-mode-vs-no-fallback-policy)
2. [Slots Are Frame Positions](#2026-01-20-slots-architecture)
3. [RTU Discovery Methods](#2026-01-20-rtu-discovery-methods)
4. [Shared Memory IPC](#2026-01-20-shared-memory-ipc-architecture)
5. [C Controller Requirements](#2026-01-20-c-controller-runtime-requirements)
6. [API Error Handling](#2026-01-20-api-error-handling)
7. [Feature Status](#2026-01-20-feature-implementation-status)

---

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

### What is PROHIBITED (per CLAUDE.md)

- Implicit fallbacks that silently return fake data
- Auto-enabling simulation when real systems are unavailable
- Hiding system unavailability from operators
- Returning HTTP 200 with error messages (use proper status codes)

### What is ALLOWED

- Explicit `WTC_DEMO_MODE=1` for testing environments
- Demo data clearly marked as such in responses
- E2E test suites using demo mode

### Code Pattern

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

## 2026-01-20: Slots Architecture

### Decision

**Slots are PROFINET frame positions, NOT database entities.**

### Context

The Water-Treat RTU uses PROFINET slots 1-8 for inputs (sensors) and slots 9-15 for outputs (actuators). These are cyclic I/O frame positions, not physical entities that need their own database table.

### Why NOT to create a Slot table

- RTUs report their sensor/control configuration directly
- The slot position is just metadata (which byte offset in the PROFINET frame)
- A Slot table adds a required intermediary that blocks sensor/control creation
- The system worked without slots being populated - they were vestigial infrastructure

### Implementation

**DO NOT:**
- Create a separate `slots` or `slot_configs` table/model
- Make `slot_id` a required foreign key on sensors/controls
- Block sensor/control creation until slots exist
- Create empty slot entities when adding RTUs

**DO:**
- Store `slot_number` as an optional integer on sensors/controls (nullable)
- Let RTUs report their configuration dynamically
- Allow sensors/controls to exist with NULL slot_number
- Keep RTU `slot_count` as informational metadata

### Code Locations

- `web/api/app/models/rtu.py` - Sensor/Control have nullable slot_number
- `web/api/app/persistence/rtu.py` - No slot lookup required
- `docker/init.sql` - No slot_configs table

---

## 2026-01-20: RTU Discovery Methods

### Decision

**Support multiple discovery methods for different network scenarios.**

### Methods

| Method | Protocol | Port | Use Case |
|--------|----------|------|----------|
| DCP Discovery | Layer 2 Ethernet | N/A (EtherType 0x8892) | PROFINET devices on local segment |
| TCP Port Scan | TCP | 9081 (default) | Water-Treat RTUs with HTTP API |
| Ping Scan | ICMP | N/A | Network reachability check |

### PROFINET DCP Discovery

- Uses raw sockets at Layer 2
- Multicast to `01:0E:CF:00:00:00`
- Requires `CAP_NET_RAW` capability
- Requires `network_mode: host` in Docker
- Endpoint: `POST /api/v1/discover/rtu`

### TCP Port Scan (Water-Treat RTUs)

- Scans subnet for open TCP port (default 9081)
- Fetches RTU info from HTTP API if available
- Works across routed networks
- Endpoint: `POST /api/v1/discover/port-scan`

```json
{
  "subnet": "192.168.1.0/24",
  "port": 9081,
  "timeout_ms": 1000,
  "fetch_info": true
}
```

### When to Use Each

- **DCP**: RTU on same Layer 2 segment, PROFINET compliant
- **Port Scan**: RTU across routers, or when DCP fails
- **Ping Scan**: Verify network connectivity first

---

## 2026-01-20: Shared Memory IPC Architecture

### Decision

**C controller and Python API communicate via POSIX shared memory.**

### Implementation

| Component | Value |
|-----------|-------|
| SHM Path | `/wtc_shared_memory` |
| SHM Key | `0x57544301` |
| Version | 3 (must match C and Python) |
| Max RTUs | 64 |
| Max Alarms | 256 |
| Max Sensors/RTU | 32 |
| Max Actuators/RTU | 32 |

### Data Flow

```
C Controller                    Python API
     │                               │
     │ ◄─── Shared Memory ───►       │
     │      /wtc_shared_memory       │
     │                               │
     ├─ Writes sensor values         ├─ Reads sensor values
     ├─ Writes actuator states       ├─ Reads actuator states
     ├─ Writes alarm states          ├─ Sends commands
     └─ Processes commands           └─ Reads alarms
```

### Docker Requirements

Both containers need:
```yaml
ipc: host  # Share IPC namespace for shared memory
```

### Command Types (API → Controller)

| Command | Code | Purpose |
|---------|------|---------|
| SHM_CMD_ACTUATOR | 1 | Control actuator |
| SHM_CMD_SETPOINT | 2 | Set PID setpoint |
| SHM_CMD_PID_MODE | 3 | Change PID mode |
| SHM_CMD_ACK_ALARM | 4 | Acknowledge alarm |
| SHM_CMD_ADD_RTU | 6 | Add RTU to controller |
| SHM_CMD_CONNECT_RTU | 8 | Connect to RTU |
| SHM_CMD_DCP_DISCOVER | 10 | Trigger DCP discovery |

---

## 2026-01-20: C Controller Runtime Requirements

### Decision

**Document all runtime requirements to prevent deployment failures.**

### Docker Configuration

```yaml
controller:
  network_mode: host     # Access physical network interfaces
  ipc: host              # Share memory with API
  cap_add:
    - NET_ADMIN          # Network configuration
    - NET_RAW            # Raw sockets for PROFINET
  environment:
    - WTC_INTERFACE=auto # Or specific interface name
```

### Network Interface

- Auto-detected by `controller-entrypoint.sh`
- Skips: `lo`, `docker*`, `veth*`, `br-*`, `virbr*`
- Override with `WTC_INTERFACE=enp0s3`

### Common Failure: "pnet_init() failed"

**Cause**: Interface doesn't exist or isn't configured

**Fix**:
1. Check available interfaces: `ip link show`
2. Set correct interface: `WTC_INTERFACE=<your_interface>`
3. Ensure interface is UP with IP configured

### Health Check

```bash
# Controller running?
docker logs wtc-controller --tail 20

# Shared memory exists?
ls -la /dev/shm/wtc_shared_memory

# API can connect?
curl http://localhost:8000/api/v1/system/health
```

---

## 2026-01-20: API Error Handling

### Decision

**Return proper HTTP status codes, never 200 with error payload.**

### Status Code Usage

| Code | Meaning | When to Use |
|------|---------|-------------|
| 200 | Success | Operation completed |
| 201 | Created | Resource created |
| 400 | Bad Request | Invalid input |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | State conflict (e.g., RTU not RUNNING) |
| 501 | Not Implemented | Feature not built yet |
| 503 | Service Unavailable | Controller not connected |

### Code Pattern

```python
# WRONG - Returns 200 with error
return build_success_response({"error": "Not implemented"})

# CORRECT - Returns proper status code
raise HTTPException(status_code=501, detail="PDF export not implemented")
```

---

## 2026-01-20: Feature Implementation Status

### Implemented

| Feature | Endpoint | Notes |
|---------|----------|-------|
| PROFINET Slots | `GET /rtus/{name}/profinet/slots` | Via shared memory IPC |
| DCP Discovery | `POST /discover/rtu` | Layer 2 multicast |
| Port Scan | `POST /discover/port-scan` | TCP scan for RTU HTTP API |
| Ping Scan | `POST /discover/ping-scan` | ICMP reachability |
| User Management | `/api/v1/users/*` | CRUD with password policy |

### Not Implemented (501)

| Feature | Endpoint | Workaround |
|---------|----------|------------|
| PDF Export | `POST /trends/export` (format=pdf) | Use CSV export |

### Disabled Frontend Pages

| Page | Reason | Workaround |
|------|--------|------------|
| `/io-tags` | Needs refactor to use sensors/controls endpoints | RTU detail page |

---

## References

- `CLAUDE.md`: Project coding standards and rules
- `/docs/architecture/ALARM_PHILOSOPHY.md`: Alarm system design
- `/docs/architecture/SYSTEM_DESIGN.md`: Overall architecture
- `/web/api/shm_client.py`: Shared memory client implementation
- `/src/ipc/ipc_server.c`: C controller IPC implementation
