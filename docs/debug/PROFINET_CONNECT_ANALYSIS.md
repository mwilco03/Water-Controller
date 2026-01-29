# PROFINET Connect Request Analysis

## Summary

Analysis of historical pcap captures to identify why PROFINET Connect Requests
stopped receiving responses from the RTU.

## Timeline

| Timestamp | Commit | Event |
|-----------|--------|-------|
| Jan 23, 10:55am EST | ff2bd7d | **Working pcap** - Connect Response received |
| Jan 23, 1:18pm EST | c491a08 | Mid pcap - Also working format |
| Jan 23, 7:02pm UTC | 741b5c3 | Changed UUID encoding to little-endian |
| Jan 23, 7:06pm UTC | 315e1d2 | Added NDR header to requests |
| Jan 28, 9:33am | 55e0ce8 | **Current pcap** - NO Connect Response |

## Key Differences Found

### 1. Interface UUID Encoding (CONFIRMED ROOT CAUSE)

**Working (before 741b5c3):**
```
Wire bytes: DE A0 00 01 6C 97 11 D1 82 71 00 A0 24 42 DF 7D
Format: BIG-ENDIAN (despite drep=0x10 claiming little-endian)
Decodes as BE: data1=0xDEA00001, data2=0x6C97, data3=0x11D1 ✓ MATCH
```

**Current (after 741b5c3):**
```
Wire bytes: 01 00 A0 DE 97 6C D1 11 82 71 00 A0 24 42 DF 7D
Format: LITTLE-ENDIAN (correct per drep=0x10)
Decodes as LE: data1=0xDEA00001, data2=0x6C97, data3=0x11D1 ✓ MATCH
```

**The paradox:**
- Working pcap: drep=LE, UUID wire format=BE (VIOLATES DCE-RPC SPEC)
- Current pcap: drep=LE, UUID wire format=LE (CORRECT per DCE-RPC spec)
- RTU accepts: The WRONG format and rejects the CORRECT format

**Root cause:** The RTU's p-net firmware appears to ignore the drep byte order
flag and always expects UUIDs in big-endian wire format. This is either a bug
in the RTU firmware or intentional behavior for compatibility with controllers
that send big-endian UUIDs.

### 2. NDR Header

**Working:** No NDR header - payload starts directly with ARBlockReq (0x0101)
```
01 01 00 44 01 00 00 01 2E DB 39 C5 ...
```

**Current:** 20-byte NDR header before PNIO blocks
```
92 00 00 00 92 00 00 00 92 00 00 00 00 00 00 00 92 00 00 00 01 01 00 3E ...
```

### 3. Default Slot Configuration

**Working:** 15 slots (8 inputs + 7 outputs) + DAP
- Module identifiers: 0x70/0x71 (Generic AI), 0x120/0x121 (Generic DO)

**Current:** 2 slots only (DAP + Temperature)
- Module identifier: 0x40/0x41 (Temperature)

### 4. Other Changes (may or may not be significant)

- IOCR Phase value: 0 → 1
- Alarm CR Tag Headers: 0x0000 → 0xC000/0xA000
- RPC header fields: htonl/htons → htole32/htole16

## Commits Involved

### 741b5c3 - UUID Encoding Change
```
fix: encode UUIDs in little-endian for drep=0x10 (DCE-RPC convention)

DCE-RPC UUIDs have mixed-endianness on the wire:
- data1 (uint32), data2 (uint16), data3 (uint16): follow drep field
- data4 (8 bytes): always big-endian / unchanged

Since we declare drep=0x10 (little-endian), the first 3 fields must be
little-endian. Previously sent big-endian, causing p-net's memcmp to
fail after parsing, resulting in empty response (unknown interface).
```

**NOTE:** The commit claims big-endian caused failures, but the working pcap
shows big-endian encoding DID receive a response. This is contradictory.

### 315e1d2 - NDR Header Addition
```
fix: add NDR header to Connect/Control requests (LE per drep)

p-net's pf_get_ndr_data_req() expects 20-byte NDR header before PNIO blocks
```

**NOTE:** The working pcap shows successful communication WITHOUT NDR header.

## Recommended Fix

### Primary Fix: Revert UUID Encoding to Big-Endian

The RTU firmware expects big-endian UUIDs regardless of drep setting. Change
the UUID constants in `src/profinet/profinet_rpc.c` back to big-endian:

```c
// BEFORE (current - spec-compliant but RTU-incompatible):
const uint8_t PNIO_DEVICE_INTERFACE_UUID[16] = {
    0x01, 0x00, 0xA0, 0xDE,  /* data1 LE */
    0x97, 0x6C,              /* data2 LE */
    0xD1, 0x11,              /* data3 LE */
    0x82, 0x71, 0x00, 0xA0, 0x24, 0x42, 0xDF, 0x7D
};

// AFTER (revert to RTU-compatible big-endian):
const uint8_t PNIO_DEVICE_INTERFACE_UUID[16] = {
    0xDE, 0xA0, 0x00, 0x01,  /* data1 BE */
    0x6C, 0x97,              /* data2 BE */
    0x11, 0xD1,              /* data3 BE */
    0x82, 0x71, 0x00, 0xA0, 0x24, 0x42, 0xDF, 0x7D
};
```

Apply same change to `PNIO_CONTROLLER_INTERFACE_UUID`.

### Secondary Fix: Investigate NDR Header

The working capture had no NDR header. Consider:
1. Removing the 20-byte NDR header from Connect/Control requests
2. OR verifying the RTU actually parses the NDR header correctly

### Additional Fix: Use Full Slot Configuration

Change default profile to match working configuration:

```c
// In profinet_controller.c:711
default_profile = device_config_get_profile(DEVICE_PROFILE_TYPE_WATER_TREAT);
```

## Files to Investigate

1. `src/profinet/profinet_rpc.c` - UUID constants, NDR header building
2. `src/profinet/profinet_controller.c` - Default profile selection
3. RTU firmware (Water-Treat repo) - p-net configuration

## Verification Steps

1. Capture with working format to confirm it still works
2. Test each change individually to isolate root cause
3. Check p-net source code for actual requirements

---

*Analysis performed: 2026-01-29*
*Captures analyzed: ff2bd7d (working), c491a08 (mid), 55e0ce8 (current)*
