# Controller Team Response: RTU Registration/Enrollment

**Date:** 2026-01-20
**From:** Controller Team
**To:** RTU Team
**Re:** RTU Registration Protocol Questions

---

## Executive Summary

Thank you for the detailed analysis. Your gap identification is accurate - the Controller currently
operates in **passive discovery mode** with no active registration, binding, or comprehensive
config sync. This document confirms what we have, clarifies what we don't have, and proposes
designs for the missing pieces.

**Current State Summary:**

| Feature | Status | Notes |
|---------|--------|-------|
| RTU Discovery (DCP) | ✅ Implemented | Controller discovers RTUs via PROFINET DCP |
| RTU Registration API | ❌ Missing | RTUs added via web UI only |
| Device Binding | ❌ Missing | Same security concern you identified |
| mDNS Advertisement | ❌ Missing | Controller doesn't advertise itself |
| Config Sync | ⚠️ Partial | Users only (0xF840), no sensor/actuator config |
| HTTP API for RTU | ❌ Missing | No endpoints for RTU→Controller calls |

---

## Question-by-Question Response

### Section 1: RTU Registration Protocol

| Question | Answer |
|----------|--------|
| **Q1.1** Does controller have registration API? | **NO.** Currently RTUs are added via `POST /api/v1/rtus` from web UI only. No endpoint exists for RTU self-registration. |
| **Q1.2** What data should RTU send? | Proposed: station_name, serial_number, vendor_id, device_id, firmware_version, mac_address, capabilities bitfield |
| **Q1.3** One-time or periodic renewal? | Propose: One-time registration with periodic heartbeat (via PROFINET cyclic data, not HTTP) |
| **Q1.4** Duplicate station names? | Controller returns HTTP 409 Conflict. See `rtu_service.py:75-77` |
| **Q1.5** Registration token required? | **NOT CURRENTLY.** We should add enrollment token support. |

**Assumption A1 Correction:** Controller does NOT have a registration endpoint. We need to add
`POST /api/v1/rtus/register` for RTU self-registration.

**Proposed Registration Endpoint:**
```
POST /api/v1/rtus/register
Content-Type: application/json

{
    "station_name": "rtu-tank-1",
    "serial_number": "WT-2024-001",
    "vendor_id": 1171,
    "device_id": 1,
    "firmware_version": "1.2.3",
    "mac_address": "00:1A:2B:3C:4D:5E",
    "capabilities": 15,
    "sensor_count": 8,
    "actuator_count": 6
}

Response (201 Created):
{
    "rtu_id": 42,
    "enrollment_token": "wtc-enroll-abc123...",
    "controller_name": "water-treat-controller",
    "requires_approval": true,
    "config_version": 0
}
```

---

### Section 2: Device Discovery Flow

| Question | Answer |
|----------|--------|
| **Q2.1** Does controller advertise via mDNS? | **NO.** Not currently implemented. Good idea - we should add this. |
| **Q2.2** HTTP registration after mDNS? | Yes, once we implement both registration endpoint and mDNS advertisement |
| **Q2.3** DHCP option for controller IP? | Not implemented. Could use option 224-254 (site-specific) |
| **Q2.4** How does controller discover RTUs? | PROFINET DCP multicast only (see `dcp_discovery.c`). RTU does NOT announce. |

**Assumption A2 Correction:** Controller does NOT advertise via mDNS. We should add:
- Service: `_profinet-controller._tcp.local`
- TXT records: `version=0.0.1`, `capabilities=0x0F`, `api_port=8000`

**Relevant Code:**
- Discovery endpoint: `web/api/app/api/v1/discover.py:79-196`
- DCP service: `web/api/app/services/dcp_discovery.py`
- C-side DCP: `src/profinet/dcp_discovery.c`

---

### Section 3: Device Binding/Pairing

| Question | Answer |
|----------|--------|
| **Q3.1** Pairing protocol? | **NOT IMPLEMENTED.** Critical security gap you correctly identified. |
| **Q3.2** Reject non-bound controllers? | RTU should implement this after binding is designed |
| **Q3.3** Binding persistence? | Propose: RTU stores controller ID + enrollment token |
| **Q3.4** Multiple controllers? | Not currently supported. Could add primary/backup binding. |

**Assumption A3 Confirmed:** Enrollment token approach is correct. Proposed design:

1. Admin creates RTU in web UI → generates unique enrollment token
2. Token displayed in UI (one-time view or QR code)
3. Technician enters token on RTU TUI during commissioning
4. RTU stores token and validates against PROFINET AR parameters
5. RTU rejects connections without matching binding

**PROFINET Binding Verification:**
```c
// In RTU PROFINET connect callback:
if (!validate_enrollment_token(ar_uuid, stored_token)) {
    return PROFINET_REJECT_CONNECTION;
}
```

---

### Section 4: Configuration Synchronization

| Question | Answer |
|----------|--------|
| **Q4.1** Push sensor/actuator config? | **NOT CURRENTLY.** Only user credentials sync (0xF840). |
| **Q4.2** What should sync? | Propose: names, units, scaling, alarm thresholds, calibration offsets |
| **Q4.3** Sync timing? | Propose: Full sync at registration, incremental during operation |
| **Q4.4** Conflict resolution? | Controller wins (master config). RTU logs conflict. |
| **Q4.5** PROFINET index for config? | **Need to allocate.** Propose: 0xF841 for device config, 0xF842 for sensor config |

**Assumption A4 Confirmed:** Controller maintains master config, pushes to RTU.

**Proposed PROFINET Index Allocation:**

| Index | Purpose | Direction | Status |
|-------|---------|-----------|--------|
| 0xF840 | User sync | Controller → RTU | ✅ Implemented |
| 0xF841 | Device config (name, thresholds) | Controller → RTU | Proposed |
| 0xF842 | Sensor config (names, units, scaling) | Controller → RTU | Proposed |
| 0xF843 | Actuator config | Controller → RTU | Proposed |
| 0xF844 | RTU status/health | RTU → Controller | Proposed |
| 0xF845 | Enrollment/binding | Bidirectional | Proposed |

**Config Sync Payload (0xF841):**
```c
typedef struct __attribute__((packed)) {
    uint8_t version;
    uint8_t flags;
    uint16_t config_crc;
    uint32_t config_timestamp;
    char station_name[32];
    uint16_t sensor_count;
    uint16_t actuator_count;
    // Followed by sensor_config_t[sensor_count]
    // Followed by actuator_config_t[actuator_count]
} device_config_payload_t;
```

---

### Section 5: Controller API for RTU

| Question | Answer |
|----------|--------|
| **Q5.1** REST API for RTU? | **NOT IMPLEMENTED.** No endpoints designed for RTU consumption. |
| **Q5.2** Authentication? | Propose: API key in header (`X-RTU-API-Key: <enrollment_token>`) |
| **Q5.3** Health reporting? | Propose: PROFINET only (via 0xF844 read). HTTP optional for diagnostics. |
| **Q5.4** WebSocket endpoint? | **NOT FOR RTU.** WebSocket exists for web UI (`/api/ws`), not RTU. |

**Assumption A5 Partial:** We can add RTU-facing endpoints, but they're not needed for normal
operation. PROFINET should be the primary channel. HTTP is backup/diagnostics only.

**Proposed RTU-Facing API (Optional):**
```
GET  /api/v1/rtu/config/{station_name}     # Get current config
POST /api/v1/rtu/status/{station_name}     # Report health status
POST /api/v1/rtu/register                   # Self-registration
GET  /api/v1/rtu/enrollment/{token}         # Validate enrollment token
```

Authentication: `X-RTU-API-Key` header with enrollment token.

---

### Section 6: Commissioning Workflow

| Question | Answer |
|----------|--------|
| **Q6.1** Expected workflow? | See proposed workflow below |
| **Q6.2** Configure RTU first or controller? | Controller first (creates enrollment token) |
| **Q6.3** Claim/adopt flow? | Yes, web UI shows discovered RTUs with "Adopt" button |
| **Q6.4** Decommissioning? | Disconnect via API, then factory reset RTU |

**Assumption A6 Confirmed (with modifications):**

**Proposed Commissioning Workflow:**

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   Controller     │    │   Technician     │    │      RTU         │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                       │                       │
         │  1. Create RTU in UI  │                       │
         │◄──────────────────────│                       │
         │                       │                       │
         │  2. Generate token    │                       │
         │  Display to tech      │                       │
         │──────────────────────►│                       │
         │                       │                       │
         │                       │  3. Power on RTU      │
         │                       │─────────────────────►│
         │                       │                       │
         │                       │  4. Enter token       │
         │                       │  via TUI              │
         │                       │─────────────────────►│
         │                       │                       │
         │  5. RTU discovers controller (mDNS/config)    │
         │◄──────────────────────────────────────────────│
         │                       │                       │
         │  6. RTU registers     │                       │
         │  POST /api/v1/rtu/register                    │
         │◄──────────────────────────────────────────────│
         │                       │                       │
         │  7. Validate token    │                       │
         │  Approve registration │                       │
         │─────────────────────────────────────────────►│
         │                       │                       │
         │  8. DCP discovery     │                       │
         │─────────────────────────────────────────────►│
         │                       │                       │
         │  9. PROFINET AR connect                       │
         │─────────────────────────────────────────────►│
         │                       │                       │
         │  10. Config sync (0xF841-0xF843)              │
         │─────────────────────────────────────────────►│
         │                       │                       │
         │  11. User sync (0xF840)                       │
         │─────────────────────────────────────────────►│
         │                       │                       │
         │  12. Begin cyclic I/O │                       │
         │◄────────────────────────────────────────────►│
         │                       │                       │
```

---

### Section 7: Security Considerations

| Question | Answer |
|----------|--------|
| **Q7.1** PROFINET security on roadmap? | Not currently. Pre-production system. |
| **Q7.2** HTTPS for RTU API? | Propose: Yes, self-signed OK for internal network |
| **Q7.3** API key management? | Per-RTU (enrollment token doubles as API key) |
| **Q7.4** HMAC/signature for packets? | PROFINET already has CRC. HMAC is overkill for internal network. |

**Assumption A7 Confirmed:** Start with API key over HTTPS (self-signed). mTLS is future work.

**Security Notes:**
- Enrollment token provides per-device authentication
- Token is 64 bytes, cryptographically random
- Token is one-time-view (admin can regenerate if lost)
- HTTPS protects token in transit
- PROFINET binding prevents rogue controller attacks

---

### Section 8: Data Structures

Your proposed structures are good. Here's the Controller-side complement:

**Controller Database Models (existing):**
```python
# web/api/app/models/rtu.py
class RTU(Base):
    id: int
    station_name: str         # Max 64 chars
    ip_address: str           # IPv4
    vendor_id: int            # PROFINET vendor ID
    device_id: int            # PROFINET device ID
    slot_count: int           # Optional
    state: RtuState           # OFFLINE, CONNECTING, RUNNING, ERROR
    state_since: datetime
    enrollment_token: str     # NEW - for binding (to be added)
    approved: bool            # NEW - requires admin approval (to be added)
    serial_number: str        # NEW - from registration (to be added)
    firmware_version: str     # NEW - from registration (to be added)
    mac_address: str          # NEW - from registration (to be added)
```

**Enrollment Token Generation (proposed):**
```python
import secrets

def generate_enrollment_token() -> str:
    """Generate cryptographically secure enrollment token."""
    # Format: wtc-enroll-{32 random hex chars}
    return f"wtc-enroll-{secrets.token_hex(16)}"
```

---

## Summary: What Needs Implementation

### Controller Side (Priority Order)

1. **HIGH: Registration Endpoint**
   - `POST /api/v1/rtu/register`
   - Add `enrollment_token`, `approved`, `serial_number` to RTU model
   - Generate token on RTU creation in web UI

2. **HIGH: mDNS Advertisement**
   - Service: `_profinet-controller._tcp.local`
   - Requires adding avahi/mDNS support to controller

3. **MEDIUM: Config Sync Protocol**
   - Define payloads for 0xF841, 0xF842, 0xF843
   - Implement write handlers in C controller
   - Add IPC commands for config push

4. **MEDIUM: Binding Verification**
   - Store enrollment token in PROFINET AR context
   - Validate on connection (optional - can defer to RTU side)

5. **LOW: RTU-Facing HTTPS API**
   - Optional diagnostic endpoints
   - Self-signed TLS setup

### RTU Side (Your Domain)

1. **HIGH: Enrollment Token Storage**
   - Persist in `/etc/water-treat/enrollment.conf`
   - Enter via TUI during commissioning

2. **HIGH: Binding Verification**
   - Validate controller ID on PROFINET connect
   - Reject unauthorized controllers

3. **MEDIUM: Controller Discovery**
   - mDNS lookup for `_profinet-controller._tcp.local`
   - Fall back to configured IP

4. **MEDIUM: HTTP Registration**
   - Call `POST /api/v1/rtu/register` after discovery
   - Handle approval pending state

5. **MEDIUM: Config Sync Handlers**
   - PROFINET record handlers for 0xF841-0xF843
   - Apply config and persist locally

---

## Next Steps

1. **Agreement on PROFINET Index Allocation** (0xF841-0xF845)
2. **Agreement on Enrollment Token Format** (proposed: `wtc-enroll-{32 hex}`)
3. **Agreement on Commissioning Workflow** (per Section 6)
4. **Create Shared Protocol Header** (like `user_sync_protocol.h`)

Please review and confirm the proposed designs. Happy to schedule a call to discuss details.

---

*Controller Team*
