# PROFINET Scapy Implementation Audit

## Reverse Engineering Comparison: C Implementation vs Scapy

This document provides a field-by-field comparison of the C PROFINET controller implementation
against the Scapy Python implementation, with confidence levels and citations.

---

## 1. RPC HEADER (80 bytes)

### C Implementation
**Source**: `src/profinet/profinet_frame.h:84-104`, `src/profinet/profinet_rpc.c:217-267`

```c
typedef struct __attribute__((packed)) {
    uint8_t version;           // Offset 0: 4
    uint8_t packet_type;       // Offset 1: 0 (request)
    uint8_t flags1;            // Offset 2: 0x22 (LAST_FRAGMENT | IDEMPOTENT)
    uint8_t flags2;            // Offset 3: 0
    uint8_t drep[3];           // Offset 4-6: 0x10, 0x00, 0x00 (little-endian, ASCII)
    uint8_t serial_high;       // Offset 7: 0
    uint8_t object_uuid[16];   // Offset 8-23: AR UUID
    uint8_t interface_uuid[16];// Offset 24-39: PNIO Device UUID (LE encoded)
    uint8_t activity_uuid[16]; // Offset 40-55: Activity UUID
    uint32_t server_boot;      // Offset 56-59: 0 (LE)
    uint32_t interface_version;// Offset 60-63: 1 (LE)
    uint32_t sequence_number;  // Offset 64-67: seq (LE)
    uint16_t opnum;            // Offset 68-69: 0 for connect (LE)
    uint16_t interface_hint;   // Offset 70-71: 0xFFFF (LE)
    uint16_t activity_hint;    // Offset 72-73: 0xFFFF (LE)
    uint16_t fragment_length;  // Offset 74-75: payload size (LE)
    uint16_t fragment_number;  // Offset 76-77: 0
    uint8_t auth_protocol;     // Offset 78: 0
    uint8_t serial_low;        // Offset 79: 0
} profinet_rpc_header_t;       // Total: 80 bytes
```

### Scapy Implementation
**Source**: `web/api/app/services/profinet_scapy.py:924-930`

```python
rpc = DceRpc4(
    ptype="request",
    flags1=0x22,  # Last Fragment (0x02) + Idempotent (0x20)
    opnum=RpcOpnum.CONNECT,
    if_id=PNIO_UUID,  # String: "dea00001-6c97-11d1-8271-00a02442df7d"
    act_id=self.ar.activity_uuid  # bytes
)
```

### COMPARISON TABLE

| Field | C Code Value | Scapy Value | Match | Confidence |
|-------|-------------|-------------|-------|------------|
| version | 4 | 4 (auto) | ✅ | 95% |
| packet_type | 0 (REQUEST) | "request" | ✅ | 95% |
| flags1 | 0x22 | 0x22 | ✅ FIXED | 90% |
| drep | 0x10,0,0 | 0x10,0,0 (auto) | ⚠️ VERIFY | 70% |
| object_uuid | AR_UUID bytes | self.ar.ar_uuid | ⚠️ VERIFY | 75% |
| interface_uuid | LE-encoded bytes | String UUID | ❌ SUSPECT | 50% |
| activity_uuid | bytes | uuid4().bytes | ✅ | 85% |
| server_boot | 0 | 0 (auto) | ✅ | 90% |
| interface_version | 1 (LE) | 1 (auto) | ⚠️ | 80% |
| sequence_number | seq++ (LE) | N/A (auto) | ⚠️ | 75% |
| opnum | 0 (LE) | RpcOpnum.CONNECT | ✅ | 90% |

### CRITICAL ISSUE: Interface UUID Encoding

**C Code** (`src/profinet/profinet_rpc.c:64-69`):
```c
const uint8_t PNIO_DEVICE_INTERFACE_UUID[16] = {
    0x01, 0x00, 0xA0, 0xDE,  // data1: 0xDEA00001 LE
    0x97, 0x6C,              // data2: 0x6C97 LE
    0xD1, 0x11,              // data3: 0x11D1 LE
    0x82, 0x71, 0x00, 0xA0, 0x24, 0x42, 0xDF, 0x7D
};
```

**Scapy Code**: `PNIO_UUID = "dea00001-6c97-11d1-8271-00a02442df7d"`

**Issue**: Scapy may convert string UUID to bytes differently than C's pre-encoded LE format.
**Confidence Fix Works**: 60% - Need to verify Scapy's UUIDField encoding matches LE format.

---

## 2. NDR HEADER (20 bytes after RPC header)

### C Implementation
**Source**: `src/profinet/profinet_rpc.c:380-397, 640-646`

```c
// Position: RPC_HEADER_SIZE (80) to RPC_HEADER_SIZE + 20 (100)
write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  // ArgsMaximum
write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  // ArgsLength
write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  // MaxCount
write_u32_le(buffer, 0, &ndr_pos);                // Offset (always 0)
write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  // ActualCount
```

### Scapy Implementation
**Source**: `web/api/app/services/profinet_scapy.py:916-918`

```python
pnio = PNIOServiceReqPDU(
    args_max=16384,  # Fixed value vs calculated
    blocks=[ar_block, iocr_input, iocr_output, alarm_cr, exp_submod]
)
```

### COMPARISON

| Field | C Code | Scapy | Match | Confidence |
|-------|--------|-------|-------|------------|
| ArgsMaximum | = pnio_len | 16384 (fixed) | ⚠️ | 70% |
| ArgsLength | = pnio_len | Auto-calculated | ⚠️ | 75% |
| MaxCount | = pnio_len | Auto-calculated | ⚠️ | 75% |
| Offset | 0 | 0 (auto) | ✅ | 90% |
| ActualCount | = pnio_len | Auto-calculated | ⚠️ | 75% |

**Risk**: Scapy's PNIOServiceReqPDU may not produce identical NDR header.
**Confidence Fix Works**: 70%

---

## 3. AR BLOCK REQUEST (Block Type 0x0101)

### C Implementation
**Source**: `src/profinet/profinet_rpc.c:402-431`

```c
// Block header: type(2) + length(2) + version(2) = 6 bytes
write_u16_be(buffer, (uint16_t)params->ar_type, &pos);     // AR type (1)
memcpy(buffer + pos, params->ar_uuid, 16);                  // AR UUID
write_u16_be(buffer, params->session_key, &pos);            // Session key
memcpy(buffer + pos, params->controller_mac, 6);            // MAC (6 raw bytes)
memcpy(buffer + pos, params->controller_uuid, 16);          // Controller UUID
write_u32_be(buffer, params->ar_properties, &pos);          // Properties (0x00000001)
write_u16_be(buffer, params->activity_timeout, &pos);       // Timeout factor
write_u16_be(buffer, ctx->controller_port, &pos);           // UDP port
write_u16_be(buffer, (uint16_t)name_len, &pos);             // Station name length
memcpy(buffer + pos, params->station_name, name_len);       // Station name
```

### Scapy Implementation
**Source**: `web/api/app/services/profinet_scapy.py:684-702`

```python
ar_block = ARBlockReq(
    ARType=ARType.IOCAR,                     # 1
    ARUUID=self.ar.ar_uuid,                  # bytes
    SessionKey=self.ar.session_key,          # int
    CMInitiatorMacAdd=self.mac,              # "02:00:00:00:00:01" FIXED
    CMInitiatorObjectUUID=uuid4().bytes,     # bytes
    ARProperties_ParametrizationServer=0,
    ARProperties_DeviceAccess=0,
    ARProperties_CompanionAR=0,
    ARProperties_AcknowledgeCompanionAR=0,
    ARProperties_reserved_1=0,
    ARProperties_SupervisorTakeoverAllowed=0,
    ARProperties_State=1,                    # Active
    CMInitiatorActivityTimeoutFactor=1000,
    CMInitiatorUDPRTPort=RPC_PORT,
    StationNameLength=len(self.station_name),
    CMInitiatorStationName=self.station_name.encode()
)
```

### COMPARISON

| Field | C Code | Scapy | Match | Confidence |
|-------|--------|-------|-------|------------|
| ARType | 1 | ARType.IOCAR (1) | ✅ | 95% |
| ARUUID | bytes | bytes | ✅ | 90% |
| SessionKey | 1 | 1 | ✅ | 95% |
| CMInitiatorMacAdd | 6 raw bytes | colon-separated string | ✅ FIXED | 85% |
| ARProperties | 0x00000001 (State=Active) | Bit fields → 0x00000001 | ⚠️ VERIFY | 75% |
| ActivityTimeout | 1000 | 1000 | ✅ | 95% |
| UDPRTPort | dynamic | 34964 | ⚠️ | 80% |

**Risk**: ARProperties bit field assembly may differ.
**Confidence Fix Works**: 80%

---

## 4. IOCR BLOCK REQUEST (Block Type 0x0102)

### C Implementation
**Source**: `src/profinet/profinet_rpc.c:433-515`

```c
write_u16_be(buffer, params->iocr[i].type, &pos);           // IOCR type (1 or 2)
write_u16_be(buffer, params->iocr[i].reference, &pos);      // Reference
write_u16_be(buffer, PROFINET_ETHERTYPE, &pos);             // LT = 0x8892
write_u32_be(buffer, IOCR_PROP_RT_CLASS_1, &pos);           // Props = 0x00000001
write_u16_be(buffer, params->iocr[i].data_length, &pos);    // Data length
write_u16_be(buffer, params->iocr[i].frame_id, &pos);       // Frame ID
write_u16_be(buffer, params->iocr[i].send_clock_factor, &pos); // Send clock
write_u16_be(buffer, params->iocr[i].reduction_ratio, &pos);// Reduction
write_u16_be(buffer, 1, &pos);                              // Phase = 1
write_u16_be(buffer, 0, &pos);                              // Sequence = 0
write_u32_be(buffer, 0, &pos);                              // FrameSendOffset = 0
write_u16_be(buffer, params->iocr[i].watchdog_factor, &pos);// Watchdog
write_u16_be(buffer, 3, &pos);                              // DataHoldFactor = 3
write_u16_be(buffer, 0, &pos);                              // TagHeader = 0
memset(buffer + pos, 0, 6);                                 // MulticastMAC = zeros

// API Section
write_u16_be(buffer, 1, &pos);                              // NumberOfAPIs = 1
write_u32_be(buffer, 0, &pos);                              // API = 0
write_u16_be(buffer, (uint16_t)io_data_count, &pos);        // NumberOfIODataObjects

// IODataObjects: slot(2) + subslot(2) + frame_offset(2) each
for each matching slot:
    write_u16_be(buffer, slot, &pos);
    write_u16_be(buffer, subslot, &pos);
    write_u16_be(buffer, frame_offset, &pos);

write_u16_be(buffer, (uint16_t)io_data_count, &pos);        // NumberOfIOCS
// IOCS: same structure
```

### Scapy Implementation
**Source**: `web/api/app/services/profinet_scapy.py:714-766`

```python
input_api = IOCRAPI(
    API=0,
    IODataObjects=input_io_data,  # List of IOCRAPIObject
    IOCSs=input_iocs              # List of IOCRAPIObject
)
iocr_input = IOCRBlockReq(
    IOCRType=IOCRType.INPUT,
    IOCRReference=0x0001,
    LT=PROFINET_ETHERTYPE,
    IOCRProperties_RTClass=1,
    IOCRProperties_reserved1=0,
    IOCRProperties_reserved2=0,
    IOCRProperties_reserved3=0,
    DataLength=input_len,
    FrameID=FRAME_ID_INPUT,
    SendClockFactor=32,
    ReductionRatio=32,
    Phase=1,
    Sequence=0,
    FrameSendOffset=0xFFFFFFFF,    # ❌ C uses 0!
    WatchdogFactor=10,
    DataHoldFactor=10,             # ❌ C uses 3!
    IOCRTagHeader_IOUserPriority=6,
    IOCRTagHeader_reserved=0,
    IOCRTagHeader_IOCRVLANID=0,
    IOCRMulticastMACAdd="01:0e:cf:00:00:00", # ❌ C uses zeros!
    APIs=[input_api]
)
```

### CRITICAL DIFFERENCES FOUND

| Field | C Code | Scapy | Match | Confidence |
|-------|--------|-------|-------|------------|
| IOCRType | 1/2 | 1/2 | ✅ | 95% |
| FrameSendOffset | **0** | **0xFFFFFFFF** | ❌ MISMATCH | 40% |
| DataHoldFactor | **3** | **10** | ❌ MISMATCH | 60% |
| TagHeader | **0** | **0xC000** (priority 6) | ❌ MISMATCH | 50% |
| MulticastMAC | **00:00:00:00:00:00** | **01:0e:cf:00:00:00** | ❌ MISMATCH | 40% |
| WatchdogFactor | varies | 10 | ⚠️ | 70% |

**Confidence Current Code Works**: 35%

---

## 5. ALARM CR BLOCK (Block Type 0x0103)

### C Implementation
**Source**: `src/profinet/profinet_rpc.c:517-540`

```c
write_u16_be(buffer, 1, &pos);                  // AlarmCRType = 1
write_u16_be(buffer, PROFINET_ETHERTYPE, &pos); // LT = 0x8892
write_u32_be(buffer, 0, &pos);                  // Properties = 0
write_u16_be(buffer, 100, &pos);                // RTATimeoutFactor = 100
write_u16_be(buffer, 3, &pos);                  // RTARetries = 3
write_u16_be(buffer, 0x0001, &pos);             // LocalAlarmRef = 1
write_u16_be(buffer, max_alarm_len, &pos);      // MaxAlarmDataLength
write_u16_be(buffer, 0xC000, &pos);             // TagHeaderHigh (priority 6)
write_u16_be(buffer, 0xA000, &pos);             // TagHeaderLow (priority 5)
```

### Scapy Implementation
**Source**: `web/api/app/services/profinet_scapy.py:823-835`

```python
alarm_cr = AlarmCRBlockReq(
    AlarmCRType=0x0001,
    LT=PROFINET_ETHERTYPE,
    AlarmCRProperties_Priority=0,
    AlarmCRProperties_Transport=0,
    AlarmCRProperties_Reserved1=0,
    AlarmCRProperties_Reserved2=0,
    RTATimeoutFactor=100,
    RTARetries=3,
    LocalAlarmReference=0x0001,
    MaxAlarmDataLength=128    # ⚠️ C uses params->max_alarm_data_length
)
```

### COMPARISON

| Field | C Code | Scapy | Match | Confidence |
|-------|--------|-------|-------|------------|
| AlarmCRType | 1 | 1 | ✅ | 95% |
| LT | 0x8892 | 0x8892 | ✅ | 95% |
| Properties | 0 | 0 (via bit fields) | ✅ | 90% |
| RTATimeoutFactor | 100 | 100 | ✅ | 95% |
| RTARetries | 3 | 3 | ✅ | 95% |
| LocalAlarmRef | 1 | 1 | ✅ | 95% |
| MaxAlarmDataLength | varies | 128 | ⚠️ | 80% |
| TagHeaderHigh | **0xC000** | **MISSING** | ❌ | 30% |
| TagHeaderLow | **0xA000** | **MISSING** | ❌ | 30% |

**Risk**: Scapy AlarmCRBlockReq may not include TagHeader fields.
**Confidence Fix Works**: 50%

---

## 6. EXPECTED SUBMODULE BLOCK (Block Type 0x0104)

### C Implementation
**Source**: `src/profinet/profinet_rpc.c:554-628`

```c
write_u16_be(buffer, 1, &pos);              // NumberOfAPIs = 1
write_u32_be(buffer, 0, &pos);              // API = 0
write_u16_be(buffer, unique_slots, &pos);   // NumberOfSlots

for each slot:
    write_u16_be(buffer, slot, &pos);           // SlotNumber
    write_u32_be(buffer, module_ident, &pos);   // ModuleIdentNumber
    write_u16_be(buffer, subslot_count, &pos);  // NumberOfSubmodules

    for each submodule:
        write_u16_be(buffer, subslot, &pos);        // SubslotNumber
        write_u32_be(buffer, submodule_ident, &pos);// SubmoduleIdentNumber
        write_u16_be(buffer, props, &pos);          // Props: 0x0001=input, 0x0002=output
        write_u16_be(buffer, data_length, &pos);    // DataDescription.SubmoduleDataLength
        write_u8(buffer, 1, pos++);                 // DataDescription.LengthIOCS = 1
        write_u8(buffer, 1, pos++);                 // DataDescription.LengthIOPS = 1
```

**C Code Structure per Submodule**: 2 + 4 + 2 + 2 + 1 + 1 = **12 bytes**

### Scapy Implementation
**Source**: `web/api/app/services/profinet_scapy.py:841-911`

```python
# Creates one ExpectedSubmoduleAPI per slot (not one API with all slots!)
for slot in profile:
    submod = ExpectedSubmodule(
        SubslotNumber=slot.subslot_number,
        SubmoduleIdentNumber=slot.submodule_ident,
        SubmoduleProperties_Type=submod_type,  # 0,1,2,3
        SubmoduleProperties_SharedInput=0,
        SubmoduleProperties_ReduceInputSubmoduleDataLength=0,
        SubmoduleProperties_ReduceOutputSubmoduleDataLength=0,
        SubmoduleProperties_DiscardIOXS=0,
        SubmoduleProperties_reserved_1=0,
        SubmoduleProperties_reserved_2=0,
        DataDescription=data_desc_list  # List of ExpectedSubmoduleDataDescription
    )

    api = ExpectedSubmoduleAPI(
        API=0,
        SlotNumber=slot.slot_number,
        ModuleIdentNumber=slot.module_ident,
        ModuleProperties=0,
        Submodules=[submod]
    )
    apis_list.append(api)

exp_submod = ExpectedSubmoduleBlockReq(
    NumberOfAPIs=len(apis_list),  # ❌ C uses 1!
    APIs=apis_list
)
```

### CRITICAL STRUCTURAL DIFFERENCES

| Aspect | C Code | Scapy | Match |
|--------|--------|-------|-------|
| NumberOfAPIs | **1** | **len(profile)** (2) | ❌ MISMATCH |
| Structure | 1 API → N slots → M submodules | N APIs (1 per slot) | ❌ MISMATCH |
| SubmoduleProperties | 2 bytes (0x0001 or 0x0002) | Multiple bit fields | ⚠️ |
| DataDescription | 4 bytes (len+IOCS+IOPS) | 6 bytes (type+len+IOCS+IOPS) | ❌ MISMATCH |

**C Code DataDescription per submodule** (4 bytes):
```
data_length(2) + IOCS_len(1) + IOPS_len(1) = 4 bytes
```

**Scapy DataDescription per submodule** (6 bytes):
```
DataDescription_type(2) + SubmoduleDataLength(2) + LengthIOCS(1) + LengthIOPS(1) = 6 bytes
```

**Confidence Current Code Works**: 25%

---

## 7. CYCLIC I/O FRAME STRUCTURE

### C Implementation
**Source**: `src/profinet/cyclic_exchange.c:33-97`

```c
// Frame structure:
// [Ethernet Header: 14] + [Frame ID: 2] + [Data] + [IOPS per slot: N] + [RT Header: 4]

// RT Header:
uint16_t net_cycle = htons(cycle_counter);           // Big-endian cycle counter
uint8_t data_status = STATE | VALID | RUN;           // 0x15 typically
uint8_t transfer_status = 0x00;
```

### Scapy Implementation
**Source**: `web/api/app/services/profinet_scapy.py:1522-1552`

```python
frame = (
    Ether(dst=self.ar.device_mac, src=self.mac, type=PROFINET_ETHERTYPE) /
    ProfinetIO(frameID=FRAME_ID_OUTPUT) /
    PNIORealTimeCyclicPDU(
        data=rt_data,
        cycleCounter=self._cycle_counter,
        dataStatus=data_status,        # 0x35
        transferStatus=transfer_status  # 0x00
    )
)
```

### COMPARISON

| Field | C Code | Scapy | Match | Confidence |
|-------|--------|-------|-------|------------|
| Ethernet header | Manual build | Ether() | ✅ | 90% |
| Frame ID | Big-endian | ProfinetIO.frameID | ⚠️ | 80% |
| Cycle counter | Big-endian htons() | PNIORealTimeCyclicPDU | ⚠️ | 75% |
| Data status | 0x15 typical | 0x35 | ⚠️ VERIFY | 70% |
| Transfer status | 0x00 | 0x00 | ✅ | 90% |

**Confidence Fix Works**: 75%

---

## SUMMARY: ISSUES RANKED BY SEVERITY

### CRITICAL (Must Fix Before Testing)

1. **IOCR FrameSendOffset**: C=0, Scapy=0xFFFFFFFF
   - **Confidence this breaks things**: 70%
   - **Citation**: `src/profinet/profinet_rpc.c:448`

2. **Expected Submodule Structure**: C has 1 API with all slots, Scapy has N APIs
   - **Confidence this breaks things**: 80%
   - **Citation**: `src/profinet/profinet_rpc.c:558-578`

3. **IOCR MulticastMAC**: C=zeros, Scapy=01:0e:cf:00:00:00
   - **Confidence this breaks things**: 60%
   - **Citation**: `src/profinet/profinet_rpc.c:452-453`

4. **IOCR TagHeader**: C=0, Scapy=priority-encoded
   - **Confidence this breaks things**: 50%
   - **Citation**: `src/profinet/profinet_rpc.c:451`

5. **DataDescription format**: C=4 bytes, Scapy=6 bytes (includes type field)
   - **Confidence this breaks things**: 75%
   - **Citation**: `src/profinet/profinet_rpc.c:616-621`

### MEDIUM (Should Verify)

6. **AlarmCR TagHeaders**: C includes them, Scapy may not
7. **DataHoldFactor**: C=3, Scapy=10
8. **Interface UUID encoding**: May differ between string and pre-encoded bytes

### LOW (Likely OK)

9. **MAC address format**: FIXED
10. **RPC flags**: FIXED

---

## TEST BATTERY PROPOSAL

```python
# File: tests/test_profinet_packet_comparison.py

class ProfinetPacketTests:
    """Battery of tests comparing Scapy output to C reference"""

    def test_01_rpc_header_size(self):
        """RPC header must be exactly 80 bytes"""
        # Expected: 80 bytes

    def test_02_rpc_header_flags(self):
        """flags1 must be 0x22"""
        # Citation: profinet_rpc.c:229

    def test_03_ndr_header_format(self):
        """NDR header must be 20 bytes, all LE"""
        # Citation: profinet_rpc.c:640-646

    def test_04_ar_block_mac_format(self):
        """MAC must be 6 raw bytes, not string"""
        # Citation: profinet_rpc.c:410

    def test_05_iocr_frame_send_offset(self):
        """FrameSendOffset should be 0, not 0xFFFFFFFF"""
        # Citation: profinet_rpc.c:448

    def test_06_iocr_multicast_mac_zeros(self):
        """MulticastMAC should be zeros"""
        # Citation: profinet_rpc.c:452-453

    def test_07_iocr_data_hold_factor(self):
        """DataHoldFactor should be 3"""
        # Citation: profinet_rpc.c:450

    def test_08_expected_submod_api_count(self):
        """NumberOfAPIs should be 1, not slot count"""
        # Citation: profinet_rpc.c:558

    def test_09_expected_submod_data_desc_size(self):
        """DataDescription should be 4 bytes (no type field)"""
        # Citation: profinet_rpc.c:616-621

    def test_10_alarm_cr_tag_headers(self):
        """AlarmCR must include TagHeaderHigh=0xC000, TagHeaderLow=0xA000"""
        # Citation: profinet_rpc.c:534-535

    def test_11_total_packet_size(self):
        """Total Connect Request should match C implementation size"""
        # Reference: Capture from working C controller
```

---

## RECOMMENDED FIXES

### Fix 1: IOCR Block Constants
```python
# Change in profinet_scapy.py
FrameSendOffset=0,           # Was 0xFFFFFFFF
DataHoldFactor=3,            # Was 10
IOCRTagHeader_IOUserPriority=0,  # Was 6
IOCRMulticastMACAdd="00:00:00:00:00:00",  # Was non-zero
```

### Fix 2: Expected Submodule Structure
```python
# Restructure to match C: 1 API with all slots
# Current: N APIs (one per slot)
# Required: 1 API containing N slots with M submodules each
```

### Fix 3: DataDescription Format
```python
# Don't use ExpectedSubmoduleDataDescription if C doesn't use type field
# Instead: manually build 4-byte structure (len + iocs + iops)
```

---

## OVERALL CONFIDENCE ASSESSMENT

| Component | Confidence Working | Primary Issue |
|-----------|-------------------|---------------|
| RPC Header | 85% | UUID encoding verify |
| NDR Header | 70% | Auto-calculation |
| AR Block | 80% | Properties assembly |
| IOCR Block | **35%** | Multiple mismatches |
| Alarm CR | 50% | Missing TagHeaders |
| Expected Submodule | **25%** | Structural mismatch |
| Cyclic I/O | 75% | Data status value |

**Overall Probability of Connection Working**: ~30%

The IOCR and Expected Submodule blocks have significant structural differences that
likely prevent the device from accepting the Connect Request.

---

*Generated: 2026-01-27*
*Author: Claude Code Audit*
