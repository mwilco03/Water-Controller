# PROFINET RPC Connect Timeout Investigation

**Date:** 2026-02-09
**Branch:** `claude/debug-profinet-response-dSDnr`
**Status:** Root cause analysis in progress

## Executive Summary

Both the C controller and Python test script experience identical RPC Connect timeouts when communicating with p-net RTU devices. The RPC/NDR headers are byte-perfect, indicating the issue lies in the PNIO block structure or content.

## Background

### What Works ✅
- **DCP Discovery**: Layer 2 multicast discovery successfully finds RTUs
- **RPC Header**: 80-byte DCE/RPC header is correctly formatted
- **NDR Header**: 20-byte NDR request header is present and valid
- **UUID Byte Ordering**: Interface/Object UUIDs correctly swapped to LE per DREP=0x10
- **Network Connectivity**: Packets reach RTU (confirmed by identical C/Python behavior)

### What Fails ❌
- **RPC Connect Response**: RTU silently drops Connect Request, no response received
- **Timeout**: Both implementations timeout after 5000ms
- **Silent Rejection**: No ICMP errors, no TCP RST, no application-level error response

## Technical Analysis

### 1. PROFINET Connection Sequence (IEC 61158-6-10)

```
IO Controller                                    IO Device (RTU)
     │                                                │
     │─── 1. DCP Identify Request (multicast) ───────►│ ✅ Working
     │◄────────── DCP Identify Response ──────────────│
     │                                                │
     │═══ 2. RPC Connect Request (UDP:34964) ════════►│ ❌ FAILING HERE
     │◄══════════ Connect Response ═══════════════════│    (no response)
     │                                                │
     │   (Steps 3-5 not reached due to Connect failure)
```

We are stuck at step 2 - the RTU receives the Connect Request but does not respond.

### 2. RPC Connect Request Structure

Per `src/profinet/profinet_rpc.c:510-825`:

```
[RPC Header (80 bytes)]
  ├─ Version: 4
  ├─ Packet Type: 0 (Request)
  ├─ Flags: PFC_FIRST_FRAG | PFC_LAST_FRAG
  ├─ OpNum: 0 (Connect)
  ├─ Activity UUID: generated per request
  ├─ Interface UUID: DEA00001-6C97-11D1-8271-... (LE-swapped)
  └─ Object UUID: AR UUID (LE-swapped)

[NDR Request Header (20 bytes)]
  ├─ Max Count: 16384
  ├─ Offset: 0
  └─ Actual Count: <PNIO payload length>

[ARBlockReq]
  ├─ Block Type: 0x0101
  ├─ Block Length: calculated
  ├─ AR Type: 0x0001
  ├─ AR UUID: 16 bytes
  ├─ Session Key: generated
  ├─ Controller MAC: 6 bytes
  ├─ Controller UUID (CMInitiatorObjectUUID): 16 bytes
  ├─ AR Properties: 0x00000060
  ├─ Activity Timeout: 100 (10 seconds)
  ├─ UDP Port: dynamic
  └─ CMInitiatorStationName: "controller-XXXX" (from MAC)

[IOCRBlockReq] × 2 (Input + Output)
  ├─ Block Type: 0x0102
  ├─ Block Length: calculated
  ├─ IOCR Type: 0x0001 (Input) or 0x0002 (Output)
  ├─ IOCR Properties: RT_CLASS_1
  ├─ Data Length: calculated
  ├─ Frame ID: 0xC000/0xC001
  ├─ Send Clock Factor: 64 (conservative)
  ├─ Reduction Ratio: 128
  ├─ Watchdog Factor: 10
  ├─ API List
  │   └─ API 0
  │       ├─ IODataObjects: slot/subslot/frame_offset tuples
  │       └─ IOCSObjects: consumer status bytes
  └─ (NO inter-block padding per Bug 0.1 fix)

[AlarmCRBlockReq]
  ├─ Block Type: 0x0103
  ├─ Block Length: calculated
  ├─ Alarm CR Type: 1
  ├─ Properties: 0
  ├─ RTA Timeout Factor: 100
  ├─ RTA Retries: 3
  ├─ Alarm Reference: 0x0001
  ├─ Max Alarm Data Length: 200
  └─ VLAN Priority Tags: 0xC000, 0xA000 (per Bug 0.2 fix)

[ExpectedSubmoduleBlock]
  ├─ Block Type: 0x0104
  ├─ Block Length: calculated
  ├─ Number of APIs: 1
  └─ API 0
      ├─ Number of Slots: N
      └─ For each slot:
          ├─ Slot Number
          ├─ Module Ident Number
          ├─ Module Properties: 0x0000
          ├─ Number of Subslots: M
          └─ For each subslot:
              ├─ Subslot Number
              ├─ Submodule Ident Number
              ├─ Submodule Properties: 0/1/2 (NO_IO/INPUT/OUTPUT)
              └─ Data Descriptions (if not NO_IO)
```

### 3. Known Fixed Issues

Previous debugging identified and fixed:

| Commit | Issue | Fix |
|--------|-------|-----|
| 7e0f01a | Inter-block padding | Removed padding between ARBlock and IOCR blocks |
| 9761d04 | IOCR block padding | Removed padding after IOCR blocks |
| 19e2d96 | Missing NDR header | Added mandatory 20-byte NDR header |
| 84649b6 | UUID byte order | Swapped first 8 bytes of UUIDs to LE |
| 956c594 | Object UUID wrong | Use AR UUID, not PNIO_UUID |
| d31a82d | PNIO_UUID constant | Fixed pre-swapped constant |
| 391b4dd | RPC header structure | Corrected field order, 80 bytes |

All these fixes are in the current code.

### 4. Potential Root Causes

#### 4.1 GSDML Inconsistency (HIGH PRIORITY)

**Finding:** The RTU GSDML file has conflicting submodule definitions.

**File:** `docs/config/GSDML-V2.4-WaterTreat-RTU-20241222.xml`

**Conflict:**

```xml
<!-- VirtualSubmoduleList (lines 94-113) -->
<VirtualSubmoduleItem ID="VSM_DAP" SubmoduleIdentNumber="0x00000001"/>
<VirtualSubmoduleItem ID="VSM_Port1" SubmoduleIdentNumber="0x00008000"/> ⚠️ SUSPICIOUS

<!-- SystemDefinedSubmoduleList (lines 115-136) -->
<InterfaceSubmoduleItem ID="ISM_1"
    SubmoduleIdentNumber="0x00000100"
    SubslotNumber="32768"/>  <!-- 0x8000 -->

<PortSubmoduleItem ID="PSM_1"
    SubmoduleIdentNumber="0x00000200"
    SubslotNumber="32769"/>  <!-- 0x8001 -->
```

**Issue:** `VSM_Port1` has `SubmoduleIdentNumber="0x00008000"`, which appears to conflate:
- Subslot number (0x8000 for Port 1)
- Submodule ident number (should be 0x00000200 per PROFINET standard)

**Controller Behavior:**

From `src/profinet/ar_manager.c:780-802`, the controller sends:

```c
// Slot 0, Subslot 0x0001: DAP
module_ident = 0x00000001;
submodule_ident = 0x00000001; ✅

// Slot 0, Subslot 0x8000: Interface
module_ident = 0x00000001;
submodule_ident = 0x00000100; ✅

// Slot 0, Subslot 0x8001: Port
module_ident = 0x00000001;
submodule_ident = 0x00000200; ✅ or ❌?
```

**Question:** Does the RTU (using this GSDML) expect:
- Standard: `submodule_ident = 0x00000200` for Port 1? (controller sends this)
- Non-standard: `submodule_ident = 0x00008000`? (GSDML VSM_Port1 suggests this)

**Impact:** If RTU expects 0x00008000 but controller sends 0x00000200, the ExpectedSubmoduleBlock will be rejected.

#### 4.2 Module Ident Mismatch

**From GSDML line 41:**
```xml
<DeviceIdentity VendorID="0x0493" DeviceID="0x0001">
```

**RTU Identity:**
- Vendor ID: 0x0493 (1171 decimal)
- Device ID: 0x0001 (1 decimal)

**Controller Identity (for CMInitiatorObjectUUID):**
- Vendor ID: 0x0272 (626 decimal) - from schema
- Device ID: 0x0C05 (3077 decimal) - from schema

This is correct - controller and device have separate identities.

#### 4.3 Data Length Miscalculation

**IOCR Data Length Enforcement:**

From `ar_manager.c:753-758`:
```c
uint16_t dl = (uint16_t)ar->iocr[i].data_length;
if (dl < IOCR_MIN_C_SDU_LENGTH) {
    dl = IOCR_MIN_C_SDU_LENGTH;  // 40 bytes minimum
}
params->iocr[params->iocr_count].data_length = dl;
```

**Question:** Is the data_length correctly calculated from IODataObjects + IOPS + IOCS?

**Frame Layout:**
```
[user_data_0][user_data_1]...[iops_0][iops_1]...[iocs_0][iocs_1]...
```

From `profinet_rpc.c:617-668`:
- IOData frame offset calculated as: `running_offset + iodata_count` (user data + IOPS bytes)
- IOCS frame offset calculated as: `iodata_frame_offset` (starts after IOData + IOPS)

#### 4.4 AR Properties Mismatch

**Controller sends (ar_manager.c:724):**
```c
params->ar_properties = AR_PROP_STATE_ACTIVE |
                        AR_PROP_PARAMETERIZATION_TYPE |
                        AR_PROP_STARTUP_MODE_LEGACY;
// = 0x00000060
```

**Breakdown:**
- Bit 5 (0x20): State = Active
- Bit 6 (0x40): ParameterizationServer = CM Initiator (controller)
- Bit 30: StartupMode = Legacy

**Question:** Does p-net device stack expect different AR properties?

#### 4.5 Timing Parameters Too Conservative?

**Current settings (timing_params_t CONSERVATIVE):**
```c
send_clock_factor = 64;   // 64 × 31.25μs = 2ms
reduction_ratio = 128;    // 2ms × 128 = 256ms actual cycle
watchdog_factor = 10;     // 256ms × 10 = 2.56s watchdog
```

**GSDML supports:**
```xml
<TimingProperties SendClock="32" ReductionRatio="1 2 4 8 16 32 64 128 256 512"/>
```

Our settings are within supported range.

### 5. P-Net Validation Points

From code comments referencing p-net source:

| File | Line | Validation |
|------|------|------------|
| pf_cmrpc.c | 4622-4634 | NDR header presence (✅ fixed) |
| pf_cmrpc.c | 1176 | Block length exact match (❓ unverified) |
| pf_cmdev.c | 4088-4098 | VLAN priority tags non-zero (✅ fixed, error code 11/12) |
| pf_cmdev.c | 3095 | Minimum c_sdu_length for RT_CLASS_1 (❓ unverified) |
| pf_cmdev.c | 3136 | Frame ID validation (❓ unverified) |
| pf_cmdev.c | 4660-4698 | Frame ID fixing logic (❓ unverified) |

## Immediate Next Steps

### 1. Verify GSDML Port Submodule Ident

**Test:** Modify controller to send `submodule_ident = 0x00008000` for Port 1 (subslot 0x8001) instead of 0x00000200.

**File:** `src/profinet/ar_manager.c:799`

```c
// Current:
params->expected_config[params->expected_count].submodule_ident = GSDML_SUBMOD_PORT; // 0x00000200

// Test:
params->expected_config[params->expected_count].submodule_ident = 0x00008000;
```

**Rationale:** If GSDML VSM_Port1 defines SubmoduleIdentNumber="0x00008000" and the RTU enforces this, our current value of 0x00000200 would cause rejection.

### 2. Enable P-Net Debug Logging on RTU

**Goal:** See why p-net is rejecting the Connect Request.

**Method:** If RTU is accessible, enable verbose logging in p-net stack to see validation failures.

### 3. Capture and Analyze Working PROFINET Traffic

**Goal:** Get a reference packet from a known-working PROFINET controller (e.g., TIA Portal, CODESYS).

**Method:**
- Set up Water-Treat RTU with commercial PROFINET controller
- Capture Connect Request with Wireshark
- Compare byte-by-byte with our implementation

### 4. Review P-Net Source Code

**Repository:** https://github.com/rtlabs-com/p-net (upstream)
**Fork:** https://github.com/mwilco03/p-net (our fork)

**Files to review:**
- `src/device/pf_cmrpc.c` - RPC request parsing
- `src/device/pf_cmdev.c` - Device validation logic
- `src/device/pf_block_reader.c` - Block parsing

**Focus:** Find exact validation that's failing.

### 5. Test with DAP-Only Connect

**Goal:** Simplify request to isolate issue.

**Method:** Send Connect Request with only DAP (slot 0) submodules, no user modules.

**File:** `src/profinet/ar_manager.c` - use `build_dap_connect_params` path

## References

- [CLAUDE.md](CLAUDE.md) - PROFINET connection sequence
- [experimental/profinet-rpc-debug/README.md](experimental/profinet-rpc-debug/README.md) - Previous debug work
- [IEC 61158-6-10:2023](https://webstore.iec.ch/publication/83457) - PROFINET Protocol
- [CODESYS PROFINET Connection](https://content.helpme-codesys.com/en/CODESYS%20PROFINET/_pnio_protocol_connection.html)
- [docs/troubleshooting/PROFINET_RPC_TIMEOUT.md](docs/troubleshooting/PROFINET_RPC_TIMEOUT.md) - Network troubleshooting

## Commit History

Recent PROFINET RPC work:
```
191c4c0 feat(profinet): auto-generate controller station names from MAC address
d3ecfe7 feat(experimental): add PROFINET RPC debug work with comprehensive findings
d31a82d fix(profinet): correct PNIO_UUID constant byte order
956c594 fix(profinet): use AR UUID as object_uuid, not PNIO_UUID
391b4dd fix(profinet): correct RPC header field order and size (80 bytes)
61f170b fix(profinet): swap UUID fields to little-endian
c68fec1 fix(profinet): remove hardcoded 0.0.0.0 source IP
19e2d96 fix(profinet): add mandatory 20-byte NDR header
9761d04 fix(profinet): remove IOCR padding causing p-net parse errors
7e0f01a fix(profinet): remove inter-block padding
```

All fixes are currently in the codebase. The timeout persists despite correct RPC/NDR headers.

## Conclusion

**HIGH CONFIDENCE:** The issue is in the PNIO blocks (ARBlockReq, IOCRBlockReq, AlarmCRBlockReq, or ExpectedSubmoduleBlock), not the RPC/NDR wrapper.

**LEADING HYPOTHESIS:** GSDML port submodule inconsistency - RTU may expect `submodule_ident = 0x00008000` for Port 1, but controller sends 0x00000200 per PROFINET standard.

**RECOMMENDED ACTION:** Test hypothesis by modifying ar_manager.c line 799 to send 0x00008000, rebuild, and test connection.
