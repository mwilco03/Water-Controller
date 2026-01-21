# RTU Connectivity Protocol Questions

**Date:** 2026-01-21
**From:** Controller Team
**To:** RTU Team (Water-Treat)
**Status:** DRAFT - Awaiting RTU Team Response

---

## Document Purpose

This document captures cross-team questions about RTU connectivity, network joining, and provisioning protocols. Questions are organized by resolution status.

**Format for RTU Team:** Respond in JSON per the `open_questions` format below.

---

## RESOLVED ITEMS (No Action Needed)

### R1. Sensor Data Format - RESOLVED

**Decision:** 5-byte format (Float32 BE + Quality byte)

Per [WT-SPEC-001](/docs/architecture/PROFINET_SPEC.md):
- Bytes 0-3: IEEE 754 Float32, big-endian (network order)
- Byte 4: Quality indicator (0x00=GOOD, 0x40=UNCERTAIN, 0x80=BAD, 0xC0=NOT_CONNECTED)

**References:**
- PROFINET_SPEC.md Section 5.1
- Commit `69d1b44` - "feat: Implement real-time data streaming and quality tracking"
- IEC 61158-6 Section 4.10.3.3 (big-endian requirement)

**Status:** Implemented in both systems. No further discussion needed.

---

### R2. Station Name = Hostname - RESOLVED

**Decision:** RTU provides `station_name` to Controller via DCP discovery. Station name IS the hostname.

**Protocol (per PROFINET DCP spec):**
1. RTU responds to DCP Identify multicast with `DCP_SUBOPTION_DEVICE_NAME`
2. Controller uses station_name as primary identifier for AR establishment
3. Station name format per PROFINET spec: `^[a-z0-9][a-z0-9.-]{0,62}$` (max 63 chars, lowercase, DNS-compatible)

**Controller Behavior:**
- Case-sensitive comparison (`strcmp`)
- Max length: 64 chars (`WTC_MAX_STATION_NAME`)
- Used as lookup key in DCP cache before PROFINET connect

**RTU Responsibility:**
- RTU dynamically configures its hostname
- RTU provides this hostname in DCP response
- Controller does NOT set RTU hostname

**References:**
- Commit `f178e6c` - "fix(api): use rtu.station_name instead of rtu.name"
- Commit `ea57fa0` - "refactor(rtu): IP-only RTU add, auto-generate station_name"
- PROFINET System Description Section 4.6.2 (Station Name)

**Status:** Clarified. RTU team confirms hostname management.

---

### R3. Vendor ID / Device ID - RESOLVED (Lab Configuration)

**Decision:** Use `vendor_id=0x0493`, `device_id=0x0001` for lab environment.

**Controller Default:**
```python
# From shm_client.py:603-606
def add_rtu(self, station_name: str, ip_address: str,
            vendor_id: int = 0x0493, device_id: int = 0x0001,
            slot_count: int = 16) -> bool:
```

**Notes:**
- Not registered with PROFINET International (lab use only)
- Controller does not validate against DCP response (trust RTU)
- For production: Would need PI-assigned vendor ID

**Status:** Accepted for lab. No changes needed.

---

### R4. Actuator Output Format - RESOLVED

**Decision:** 2-byte format per [WT-SPEC-001] Section 5.3

```
Byte 0: Command (0x00=OFF, 0x01=ON, 0x02-0xFF=Reserved)
Byte 1: Reserved (set to 0x00)
```

**Note:** Earlier code referenced 4-byte format. Canonical spec is 2 bytes.

**Status:** Implemented per spec.

---

### R5. Config Sync Protocol - RESOLVED

**Decision:** PROFINET record indices allocated per [CROSS_SYSTEM.md](/docs/architecture/CROSS_SYSTEM.md):

| Index | Purpose | Direction |
|-------|---------|-----------|
| 0xF840 | User credentials sync | Controller → RTU |
| 0xF841 | Device configuration | Controller → RTU |
| 0xF842 | Sensor configuration | Controller → RTU |
| 0xF843 | Actuator configuration | Controller → RTU |
| 0xF844 | RTU status/health | RTU → Controller |
| 0xF845 | Enrollment/binding | Bidirectional |

**References:**
- Commit `4edea57` - "feat(registration): implement RTU self-registration protocol"
- shared/include/config_sync_protocol.h
- CROSS_SYSTEM.md Part 6 (test vectors)

**Status:** Protocol defined with test vectors.

---

## QUESTIONS FOR STEERING (Controller Team Decision)

Before passing to RTU team, please confirm:

### S1. DCP Discovery Failure Recovery

**Current Behavior:** If RTU not found in DCP cache, `/connect` fails silently.

**Options:**
1. **Auto-rediscovery**: Trigger DCP discovery if cache miss before failing
2. **Fail fast**: Return error immediately, require explicit `/discover` call
3. **Retry with backoff**: Attempt discovery up to N times with exponential backoff

**Recommendation:** Option 1 (auto-rediscovery) aligns with "fail safe" principle.

**Your Decision:** _______________

---

### S2. Automatic Reconnection After Error

**Current Behavior:** RTU enters ERROR state on watchdog timeout. Manual reconnection required.

**Options:**
1. **Manual only**: Operator must explicitly reconnect (current)
2. **Auto-reconnect**: Controller attempts reconnection with backoff (3 attempts, then alert)
3. **Configurable**: Per-RTU setting for auto-reconnect behavior

**Recommendation:** Option 3 (configurable) - some RTUs may need manual intervention.

**Your Decision:** _______________

---

### S3. Slot Configuration Source

**Current Behavior:** Slots are hardcoded (DAP=0, sensors=1-8, actuators=9-15).

**Options:**
1. **Static configuration**: Keep current hardcoded approach
2. **GSDML-driven**: Read expected slots from GSDML at connection time
3. **RTU-reported**: RTU reports slot configuration via 0xF844 status record

**Recommendation:** Option 1 for lab simplicity. Document slot layout as contract.

**Your Decision:** _______________

---

## OPEN QUESTIONS FOR RTU TEAM

These questions require RTU team input. Respond in JSON format.

```json
{
  "goal": "Clarify RTU-side connectivity behavior for Water-Controller integration",
  "context": [
    "Controller uses DCP discovery to find RTUs by station_name",
    "PROFINET AR cycle=1ms, watchdog=3000ms",
    "Slots: DAP=0, sensors=1-8 (5-byte), actuators=9-15 (2-byte)",
    "Config sync via records 0xF840-0xF845 defined in CROSS_SYSTEM.md"
  ],
  "decisions": [
    "5-byte sensor format confirmed (Float32 BE + quality)",
    "station_name = hostname, RTU provides via DCP",
    "vendor_id=0x0493, device_id=0x0001 for lab"
  ],
  "constraints": [
    "PROFINET RT Class 1, EtherType 0x8892",
    "Station name: lowercase, DNS-compatible, max 63 chars",
    "Static IP required (no DHCP negotiation in current impl)"
  ],
  "open_questions": [
    "Q1: RTU behavior on AR watchdog timeout - does RTU auto-close AR or wait for explicit release?",
    "Q2: RTU behavior when controller sends command to non-existent slot - ignore, NACK, or alarm?",
    "Q3: Does RTU support DCP Set for IP reconfiguration, or is IP always static?",
    "Q4: RTU minimum supported cycle time - can it go faster than 1ms?",
    "Q5: Does RTU implement authority handoff protocol (AUTONOMOUS → SUPERVISED transitions)?",
    "Q6: RTU behavior on enrollment token mismatch - reject AR or accept with warning?",
    "Q7: How does RTU report firmware version to controller? (DCP? 0xF844? HTTP registration?)",
    "Q8: Does RTU generate PROFINET diagnostic alarms? If so, which alarm types?",
    "Q9: RTU behavior on config sync CRC mismatch - reject payload or request retransmit?",
    "Q10: Maximum number of simultaneous controllers RTU supports (for redundancy planning)?"
  ],
  "next_action": "RTU team responds with concrete behaviors/values for each open_question"
}
```

---

## REFERENCE: PROFINET Spec Compliance Notes

Per IEC 61158-6-10 and PROFINET System Description:

| Requirement | Spec Reference | Controller Compliance |
|-------------|----------------|----------------------|
| Station name max length | IEC 61158-6 Table 587 | 63 chars (we use 64 with null) |
| Station name charset | PROFINET SD 4.6.2 | a-z, 0-9, hyphen, dot |
| DCP Identify All | IEC 61158-6 Section 5.3 | Implemented |
| DCP Identify by Name | IEC 61158-6 Section 5.3 | Implemented |
| AR Type IOCAR | IEC 61158-6 Section 5.2 | 0x0001 supported |
| Cycle time base | IEC 61784-2-3 Table 6 | 31.25us × reduction ratio |
| Big-endian data | IEC 61158-6 Section 4.10.3.3 | Implemented (htonl/ntohl) |

---

## Document History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-21 | Controller Team | Initial draft with resolved items and open questions |

---

*This document is maintained in `/docs/architecture/RTU_CONNECTIVITY_QUESTIONS.md`*
