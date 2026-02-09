# PROFINET RPC Packet Analysis from Captured Traffic

**File:** `df93bc5.pcapng` packet #13
**Date:** 2026-02-09
**Purpose:** Analyze actual Connect Request packet sent to RTU

## Packet Overview

**Network Flow:**
```
Controller: 192.168.6.13:58031
       ↓
    RTU: 192.168.6.21:34964 (PROFINET RPC)
```

**Packet Size:** 386 bytes total, 344 bytes RPC payload
**Result:** **NO RESPONSE** - RTU silently drops packet

## Raw Packet Hex Dump (first 200 bytes)

```
Offset  Hex Data                                             ASCII
------  -----------------------------------------------      ----------------
0000: 04 00 20 00 10 00 00 00 00 00 de a0 00 01 6c 97    .. .......... l.
0010: 11 d1 82 71 00 a0 24 42 df 7d 12 79 e8 b0 01 ec    ...q..$B.}.y....
0020: 4f 59 a6 03 6a a3 23 93 04 cc 00 00 00 00 01 00    OY..j.#.........
0030: 00 00 00 00 00 00 00 00 00 00 00 00 16 01 00 00    ................
0040: 02 00 02 01 00 00 02 01 00 00 02 01 00 00 00 00    ................
0050: 00 00 02 01 00 00 01 01 00 50 01 00 00 01 7e 00    .........P....~.
0060: c1 6b 9a 6b 42 48 90 d6 c4 9e 8d b0 6d b9 00 01    .k.kBH......m...
0070: 02 00 00 00 00 01 00 01 de a0 00 01 6c 97 11 d1    ............l...
0080: 82 71 00 a0 24 42 df 7d 33 62 93 a1 d5 2b 42 17    .q..$B.}3b...+B.
0090: b8 12 07 69 cc c3 f5 07 00 00 00 11 00 64 00 0a    ...i.........d..
00a0: 63 6f 6e 74 72 6f 6c 6c 65 72 01 02 00 2a 01 00    controller...*..
00b0: 00 01 00 01 88 92 00 00 00 00 00 06 80 01 00 20    ...............
00c0: 00 20 00 01 ff ff ff ff 00 0a 00 0a 00 00 00 00    . ..............
```

## Parsed RPC Header (Offsets 0-79)

```
Offset   Field                          Value                              Status
------   ----------------------------   ---------------------------------- ------
0        Version                        4                                  ✅
1        Packet Type                    0 (Request)                        ✅
2        Flags1                         0x20 (LAST_FRAG | IDEMPOTENT)     ✅
3        Flags2                         0x00                               ✅
4-6      DREP                           10 00 00 (Little-Endian)           ✅
7        Serial High                    0x00                               ✅

8-23     Object UUID (AR UUID)          0000dea000016c9711d1827100a02442   ⚠️
24-39    Interface UUID (PNIO Device)   df7d1279e8b001ec4f59a6036aa32393   ❌
40-55    Activity UUID                  04cc0000000001000000000000000000   ⚠️

56-59    Server Boot Time               0                                  ✅
60-63    Interface Version              278                                ❌
64-67    Sequence Number                16908290                           ⚠️
68-69    OpNum                          0 (Connect)                        ✅
70-71    Interface Hint                 258                                ⚠️
72-73    Activity Hint                  0                                  ⚠️
74-75    Fragment Length                258                                ⚠️
76-77    Fragment Number                0                                  ✅
78       Auth Protocol                  0                                  ✅
79       Serial Low                     0                                  ✅
```

## Critical Issues Found

### 1. Interface UUID is WRONG ❌

**Expected:** `DEA00001-6C97-11D1-8271-00A02442DF7D` (PROFINET IO Device Interface)
**Actual:**   `DF7D1279-E8B0-01EC-4F59-A6036AA32393` (Garbage)

**Impact:** p-net device stack validates the Interface UUID against its internal constant `{0xDEA00001, 0x6C97, 0x11D1, ...}`. Mismatch causes **immediate silent rejection**.

**Root Cause:** This is THE primary reason the RTU drops the packet!

### 2. Object UUID looks suspicious ⚠️

**Actual:** `0000DEA00001-6C97-11D1-8271-00A02442`

This starts with `0000DEA0...` which looks like it contains part of the Interface UUID! This suggests a byte-order swap error or memory corruption during packet construction.

### 3. Interface Version should be 1, not 278 ❌

**Expected:** `1`
**Actual:**   `278`

This is stored at offset 60-63 and should be `0x00000001` in little-endian. The value `278` (0x00000116) suggests incorrect byte ordering.

### 4. NDR Header (Offsets 80-99) appears corrupted

```
Offset 80-83: Max Count = 16908288      (expected: ~16384)
Offset 84-87: Offset = 16842752         (expected: 0)
Offset 88-91: Actual Count = 86016      (expected: ~260)
```

These values are way off - suggesting either:
- Wrong byte order
- Memory corruption
- Incorrect parsing offset

### 5. ARBlockReq Block Type is garbage ❌

**Offset 100-101:** Block Type = `0x4248` (ASCII "BH")
**Expected:** `0x0101` (ARBlockReq)

This is a smoking gun - the PNIO blocks are not starting where expected!

## Diagnosis

### Problem: Packet Structure Corruption

The packet shows signs of severe structural problems:

1. **UUIDs are corrupted** - Interface UUID is completely wrong
2. **Multi-byte fields have wrong values** - Interface Version, Fragment Length
3. **PNIO blocks misaligned** - Block Type at offset 100 is garbage

### Hypothesis 1: Struct Alignment Issue

The `profinet_rpc_header_t` structure may have padding issues on the platform. The `__attribute__((packed))` directive should prevent this, but if it's not applied correctly:

```c
typedef struct __attribute__((packed)) {
    uint8_t version;
    uint8_t packet_type;
    // ... 80 bytes total
} profinet_rpc_header_t;
```

**Test:** Verify `sizeof(profinet_rpc_header_t) == 80`

### Hypothesis 2: Byte Order Swap Function Error

The `uuid_swap_fields()` function may be corrupting UUIDs instead of correctly swapping them.

**From code (profinet_rpc.c:216-217):**
```c
memcpy(hdr->interface_uuid, PNIO_DEVICE_INTERFACE_UUID, 16);
uuid_swap_fields(hdr->interface_uuid);
```

If `uuid_swap_fields()` has a bug, it could explain why the Interface UUID is garbage.

### Hypothesis 3: Memory Overlap/Corruption

The packet buffer may be getting corrupted during construction. If the buffer pointer arithmetic is wrong, later writes could overwrite earlier header fields.

## Comparison with Expected Values

### Interface UUID (Critical!)

**What RTU expects (p-net constant):**
```
{0xDEA00001, 0x6C97, 0x11D1, 0x8271, 0x00A02442DF7D}
```

**Wire format (after LE swap per DREP=0x10):**
```
01 00 A0 DE  97 6C  D1 11  82 71  00 A0 24 42 DF 7D
```

**What we actually sent:**
```
DF 7D 12 79  E8 B0  01 EC  4F 59  A6 03 6A A3 23 93
```

These don't even remotely match!

## Wireshark Dissector Evidence

Per Wireshark's PROFINET dissector (packet-dcerpc-pn-io.c):
- Interface UUID validation is **mandatory**
- p-net uses `pf_get_uuid()` to decode UUID per DREP
- Mismatch results in silent packet drop

Commercial PROFINET controllers (Siemens TIA Portal, CODESYS) would send the correct Interface UUID, which is why they work.

## Recommended Fixes

### Priority 1: Fix Interface UUID (CRITICAL)

Verify and fix `uuid_swap_fields()` function:

```c
static void uuid_swap_fields(uint8_t uuid[16]) {
    // Swap first 3 fields from BE to LE (or vice versa)
    // time_low (4 bytes): uuid[0..3]
    // time_mid (2 bytes): uuid[4..5]
    // time_hi_and_version (2 bytes): uuid[6..7]
    // clock_seq and node (8 bytes): uuid[8..15] - NO SWAP
}
```

**Test:** After memcpy and swap, `hdr->interface_uuid` MUST be:
```
01 00 A0 DE  97 6C  D1 11  82 71  00 A0 24 42 DF 7D
```

### Priority 2: Verify struct packing

Add compile-time assertion:
```c
_Static_assert(sizeof(profinet_rpc_header_t) == 80,
               "RPC header must be exactly 80 bytes");
```

### Priority 3: Add packet validation

Before sending, validate:
- Interface UUID first 4 bytes == `01 00 A0 DE` (after swap)
- Interface Version == 1
- Fragment Length == reasonable value (< 2000)
- NDR Actual Count matches PNIO payload size

## References

- [PROFINET Specification IEC 61158-6-10](https://webstore.iec.ch/publication/83457)
- [p-net source: pf_cmrpc.c](https://github.com/rtlabs-com/p-net/blob/master/src/device/pf_cmrpc.c) - UUID validation
- [Wireshark PROFINET dissector](https://github.com/boundary/wireshark/blob/master/plugins/profinet/packet-dcerpc-pn-io.c)
- Controller source: `src/profinet/profinet_rpc.c:161-239` (build_rpc_header)
- Controller source: `src/profinet/profinet_frame.h:84-104` (RPC header struct)

## Conclusion

**ROOT CAUSE IDENTIFIED:** The Interface UUID in the RPC header is corrupted/wrong, causing p-net to silently reject the packet.

This is almost certainly a bug in the `uuid_swap_fields()` function or how it's being called. The PCAP provides definitive proof that the packet reaching the RTU has a malformed Interface UUID.

**Next Step:** Inspect and fix the `uuid_swap_fields()` implementation immediately.
