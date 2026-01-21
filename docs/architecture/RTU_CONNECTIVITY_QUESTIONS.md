# RTU Connectivity Protocol Questions

**Date:** 2026-01-21
**From:** Controller Team
**To:** RTU Team (Water-Treat)
**Status:** COMPLETE - All Questions Resolved

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

## RTU TEAM RESPONSE (2026-01-21)

**Source:** RTU Team (Water-Treat), commit `5f632ca`, `docs/CONTROLLER_INTEGRATION_NOTES.md`

### R6. DCP Behavior - RESOLVED (RTU Response)

**RTU Stack:** p-net v0.2.0 (DCP handled internally by stack)

| DCP Service | RTU Behavior |
|-------------|--------------|
| **DCP_IDENTIFY** | Always responds (station_name, vendor_id=0x0493, device_id=0x0001, MAC, IP) |
| **DCP_GET** | Always responds - any parameter readable |
| **DCP_SET_IP** | Accepted. DHCP mode = temporary (reverts on reboot). Static mode = persisted |
| **DCP_SET_NAME** | Accepted - station_name is mutable via DCP |

**Implication for Controller:** DCP Set IP works but is not reliable for permanent assignment in DHCP environments. Use for discovery only.

---

### R7. Device Identity Uniqueness - RESOLVED (RTU Response)

| Identifier | Unique? | Purpose |
|------------|---------|---------|
| **vendor_id + device_id** | NO | Product type (like model number). All Water-Treat RTUs share `0x0493:0x0001` |
| **station_name** | YES | Must be unique per L2 broadcast domain. Primary identifier for AR |
| **MAC address** | YES | Unique per physical device (hardware serial equivalent) |

**Implication for Controller:**
- Do NOT use vendor_id/device_id to differentiate RTUs
- Use station_name for logical identity
- Use MAC for physical device tracking

---

### R8. Station Name Constraints - RESOLVED (RTU Response)

**Format:** `^[a-z0-9][a-z0-9-]{0,62}$`
- Lowercase only (a-z, 0-9, hyphen)
- Max 63 chars
- **NO underscores** (DNS-compatible)
- NO dots (reserved for domain qualification)

**Controller Note:** Update validation regex - current allows dots, should be hyphen only.

---

## RTU TEAM RESPONSE - CONNECTIVITY BEHAVIOR (2026-01-21)

**Source:** RTU Team code review (profinet_callbacks.c, profinet_manager.c, config_sync.c)

### Quick Reference

| Q# | Question | Answer |
|----|----------|--------|
| Q1 | AR watchdog timeout | **WAIT** - passive, expects PNET_EVENT_ABORT |
| Q2 | Command to non-existent slot | **IGNORE** - silently skipped |
| Q3 | DCP Set IP | **SUPPORTED** - temporary in DHCP mode |
| Q4 | Minimum cycle time | **1ms** (PROFINET_TICK_INTERVAL_US=1000) |
| Q5 | Authority handoff | **STORED_NOT_ENFORCED** - TBD |
| Q6 | Enrollment token mismatch | **REJECT_PACKET** - AR continues |
| Q7 | Firmware version | **I&M0 @ 0x8000** (standard PROFINET) |
| Q8 | Diagnostic alarms | **MANUAL_ONLY** - API ready, none automatic |
| Q9 | Config sync CRC mismatch | **REJECT** - CRC16-CCITT |
| Q10 | Max simultaneous ARs | **1** (single-controller device) |

---

### Q1. AR Watchdog Timeout - RESOLVED

**Answer:** RTU **WAITS** (passive)

RTU receives `PNET_EVENT_ABORT` from p-net stack when watchdog expires. Calls `set_connected(false)`. Does NOT initiate AR close - p-net handles protocol.

**Controller Implication:** Expect RTU to be passive. Controller drives reconnection.

**Code ref:** `profinet_callbacks.c:99-100`

---

### Q2. Command to Non-Existent Slot - RESOLVED

**Answer:** **IGNORE** silently

`find_slot()` returns NULL for unknown slots. `poll_output_slots()` skips non-plugged slots silently. No NACK sent, no alarm generated.

**Controller Implication:** Controller receives no error response for invalid slots. Validate slot existence before sending commands.

**Code ref:** `profinet_manager.c:85-92, 105-136`

---

### Q4. Minimum Cycle Time - RESOLVED

**Answer:** **1ms**

`PROFINET_TICK_INTERVAL_US=1000`. `pnet_handle_periodic()` called every 1ms. `min_device_interval` configurable via config (default 32 = 1ms per PROFINET spec).

**Code ref:** `profinet_manager.c:24`

---

### Q5. Authority Handoff - RESOLVED (Partial)

**Answer:** **STORED_NOT_ENFORCED**

`authority_mode_t` enum exists (`AUTHORITY_AUTONOMOUS=0`, `AUTHORITY_SUPERVISED=1`). Value stored in `g_cfg.authority` and logged. **NO behavioral difference implemented** - RTU operates identically in both modes.

**Action Required:** Define SUPERVISED behavior if differentiation needed.

**Code ref:** `config_sync.c:43,96,106-109`

---

### Q6. Enrollment Token Mismatch - RESOLVED

**Answer:** **REJECT_PACKET_NOT_AR**

Invalid token → `validate_token()` fails → `RESULT_INVALID_PARAM` → PNIO error `0xCF/0x81`. AR continues normally. Only enrollment packet is rejected.

**Controller Implication:** Connection remains active even if enrollment fails.

**Code ref:** `rtu_registration.c:172-199,660-664`

---

### Q7. Firmware Version Reporting - RESOLVED

**Answer:** **I&M0 @ index 0x8000**

Standard PROFINET I&M0 at index `0x8000`. `software_revision={V,1,0,0}`. Mandatory per IEC 61158.

**Controller Implication:** Use standard acyclic read of index 0x8000. No custom index needed.

**Code ref:** `profinet_callbacks.c:56-76,165-168`

---

### Q8. PROFINET Diagnostic Alarms - RESOLVED

**Answer:** **MANUAL_ONLY**

`profinet_manager_send_alarm()` API available for process alarms. Currently NO automatic diagnostic alarms generated. Sensor faults set `quality=BAD` but don't trigger PROFINET alarm.

**Action Required:** Define which conditions should generate alarms if needed.

**Code ref:** `profinet_manager.c:934-962`

---

### Q9. Config Sync CRC Mismatch - RESOLVED

**Answer:** **REJECT**

CRC16-CCITT (poly=0x1021, init=0xFFFF). Mismatch → `RESULT_INVALID_PARAM` → PNIO status `0xCF/0x81`. Packet entirely ignored. Config not applied.

**Controller Implication:** Verify CRC parameters match. Failed config sync returns error, must retry.

**Code ref:** `config_sync.c:19-31,88-91`

---

### Q10. Max Simultaneous AR Connections - RESOLVED

**Answer:** **1**

Single `g_pn.arep` storage. RTU is single-controller device. Second AR attempt rejected by p-net stack (device busy).

**Controller Implication:** No redundancy via dual-AR. Only one controller can connect at a time.

**Code ref:** `profinet_manager.c:48`

---

## OPEN ACTION ITEMS

| Item | Owner | Status |
|------|-------|--------|
| Define SUPERVISED mode behavior | Controller Team | TBD |
| Specify which sensor faults should generate PROFINET alarms | Both Teams | TBD |
| Verify CRC16-CCITT parameters (poly=0x1021, init=0xFFFF) | Controller Team | Verify |
| Update station_name validation regex (no dots, hyphen only) | Controller Team | TODO |

---

## STEERING DECISIONS (Controller Team)

### S1. DCP Discovery Failure Recovery - PENDING DETAIL

**Current Behavior:** If RTU not found in DCP cache, `/connect` fails silently.

**Decision Direction:** Auto-rediscovery with backoff preferred.

**Backoff Options to Consider:**

| Strategy | Delays | Total Time | Use Case |
|----------|--------|------------|----------|
| **Fast retry** | 100ms, 200ms, 400ms | ~700ms | RTU just booted, quick recovery |
| **Standard** | 1s, 2s, 4s | ~7s | Normal network glitch |
| **Conservative** | 2s, 4s, 8s, 16s | ~30s | Flaky network, reduces DCP storm |

**Proposed Implementation:**
```
On /connect if DCP cache miss:
  1. Trigger targeted DCP Identify (by station_name, not broadcast)
  2. Wait up to 1s for response
  3. If no response: retry with 2s, then 4s delays (3 attempts total)
  4. If still not found: return 503 "RTU not discovered, check network"
  5. Log each retry for diagnostics
```

**Trade-offs:**
- Targeted DCP (by name) is less disruptive than broadcast
- Backoff prevents DCP storm if multiple connects fail simultaneously
- 7s total delay acceptable for commissioning, may be slow for auto-reconnect

**Decision:** Auto-rediscovery with standard backoff (1s, 2s, 4s). Revisit if latency becomes issue.

---

### S2. Automatic Reconnection After Error - DECIDED

**Decision:** Option 2 - Auto-reconnect with exponential backoff

**Implementation:**
```
On ERROR state (watchdog timeout, AR abort):
  1. Wait 3s (debounce)
  2. Attempt reconnect
  3. If fail: wait 6s, retry
  4. If fail: wait 12s, retry
  5. If fail: raise ALARM, stop retrying, require manual intervention
  6. On success: clear retry counter, resume normal operation
```

**Rationale:**
- Most network glitches are transient (cable bump, switch reboot)
- 3 retries over ~21s covers typical recovery scenarios
- Alarm ensures operator awareness if persistent failure
- Does NOT require per-RTU configuration (simplicity)

---

### S3. Slot Configuration Source - TABLED

**Decision:** RTU-reported configuration (Option 3) is the goal, but **tabled until PROFINET comms established**.

**Current State:** Hardcoded slots work for initial integration testing.

**Future Work:**
- RTU reports slot layout via 0xF844 status record after AR established
- Controller updates internal model based on RTU report
- Mismatch triggers warning but does not block operation

**Rationale:** Focus on getting basic PROFINET AR working first. Slot negotiation is a refinement.

---

## OPEN QUESTIONS FOR RTU TEAM

These questions require RTU team input. Respond in JSON format.

```json
{
  "goal": "Clarify RTU-side connectivity behavior for Water-Controller integration",
  "context": [
    "Controller uses DCP discovery to find RTUs by station_name (hostname)",
    "Controller will auto-rediscovery with backoff (1s,2s,4s) on cache miss",
    "Controller will auto-reconnect on ERROR with backoff (3s,6s,12s), then alarm",
    "PROFINET AR cycle=1ms, watchdog=3000ms",
    "Slot configuration tabled - using hardcoded layout for initial testing",
    "Config sync records 0xF840-0xF845 defined in CROSS_SYSTEM.md"
  ],
  "decisions": [
    "5-byte sensor format (Float32 BE + quality) - WT-SPEC-001 authoritative",
    "station_name = hostname, RTU provides via DCP DEVICE_NAME",
    "vendor_id=0x0493, device_id=0x0001 for lab",
    "2-byte actuator format (command + reserved)"
  ],
  "constraints": [
    "PROFINET RT Class 1, EtherType 0x8892",
    "Station name: lowercase, DNS-compatible, max 63 chars per IEC 61158-6",
    "Static IP (DCP Set for IP is optional enhancement)"
  ],
  "open_questions": [
    "Q1: AR watchdog timeout behavior - RTU auto-closes AR or waits for release RPC?",
    "Q2: Command to non-existent slot - ignore silently, return NACK, or generate alarm?",
    "Q3: DCP Set for IP supported? (nice-to-have, not blocking)",
    "Q4: Minimum cycle time supported? (1ms default, can RTU handle faster?)",
    "Q5: Authority handoff (AUTONOMOUS/SUPERVISED) - implemented or future?",
    "Q6: Enrollment token validation - reject AR on mismatch or log warning?",
    "Q7: Firmware version reporting - via DCP DEVICE_OPTIONS or 0xF844?",
    "Q8: PROFINET diagnostic alarms generated? Which types?",
    "Q9: Config sync CRC mismatch - reject and return error code, or silent ignore?",
    "Q10: Max simultaneous AR connections? (redundancy/testing scenarios)"
  ],
  "next_action": "Provide concrete behavior/value per question. Use 'TBD' if not yet implemented."
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
| 2026-01-21 | Controller Team | Added steering decisions: S1 auto-rediscovery w/backoff, S2 auto-reconnect, S3 tabled |
| 2026-01-21 | RTU Team | Response: DCP behavior, device identity uniqueness, station_name constraints |
| 2026-01-21 | RTU Team | Response: All connectivity questions (Q1-Q10) resolved with code refs |

---

*This document is maintained in `/docs/architecture/RTU_CONNECTIVITY_QUESTIONS.md`*
