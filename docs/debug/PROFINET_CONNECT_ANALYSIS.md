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

### 1. Interface UUID Encoding

**Working (before 741b5c3):**
```
dea000016c9711d1827100a02442df7d (Big-endian)
```

**Current (after 741b5c3):**
```
0100a0de976cd111827100a02442df7d (Little-endian per DCE-RPC drep)
```

The change was made to follow DCE-RPC convention where drep=0x10 indicates
little-endian data representation. However, the RTU responded to big-endian
encoding in the working capture.

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

## Potential Remediation

### Option A: Revert Protocol Changes
Revert commits 741b5c3 and 315e1d2 to restore working protocol format:
- Big-endian UUID encoding
- No NDR header

### Option B: Use Full Slot Configuration
Change default profile from `DEVICE_PROFILE_TYPE_RTU_CPU_TEMP` to
`DEVICE_PROFILE_TYPE_WATER_TREAT` to match working configuration:

```c
// In profinet_controller.c:711
default_profile = device_config_get_profile(DEVICE_PROFILE_TYPE_WATER_TREAT);
```

### Option C: Investigate RTU Expectations
The RTU firmware (p-net based) may have specific expectations that differ from:
- Standard DCE-RPC UUID encoding
- Standard NDR header format

Need to verify what the actual RTU firmware expects.

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
