# PROFINET RPC Debug - Experimental Work

## Purpose
This directory contains experimental work debugging PROFINET RPC Connect timeouts.
Created: 2026-02-09

## Problem Statement
Both C controller and Python test script experience RPC Connect timeouts when communicating with p-net RTU device stack. RTU silently drops packets without responding.

## Files
- `test-profinet-scapy.py`: Python reference implementation for packet comparison
- This README documenting findings and fixes

## Key Findings

### 1. RPC Header Structure (CRITICAL)
**Issue**: Python was building 88-byte header vs C's 80-byte header
**Fix**: Corrected field order per `profinet_frame.h:84-104`
```
Offset 0-7:   version, packet_type, flags1, flags2, drep[3], serial_high
Offset 8-23:  object_uuid (AR UUID, not PNIO_UUID!)
Offset 24-39: interface_uuid (PNIO Device UUID constant)
Offset 40-55: activity_uuid
Offset 56-79: server_boot, if_version, seq_num, opnum, hints, frag_len, etc.
Total: 80 bytes
```

### 2. UUID Byte Swapping (CRITICAL)
**Issue**: UUIDs must be swapped to LE per DREP=0x10
**Fix**: Implemented `swap_uuid_fields()` per commit 84649b6
```python
def swap_uuid_fields(uuid_bytes):
    # Reverse first 8 bytes only:
    # time_low (0-3): reverse
    # time_mid (4-5): reverse
    # time_hi_and_version (6-7): reverse
    # Bytes 8-15: unchanged
```

### 3. PNIO_UUID Constant (CRITICAL)
**Issue**: Python constant was pre-swapped: `0x01, 0x00, 0xa0, 0xde`
**Should be**: `0xDE, 0xA0, 0x00, 0x01` (matching C constant in BE)
**Fix**: Corrected to match `src/profinet/profinet_rpc.c:44-46`

### 4. NDR Header (CRITICAL)
**Issue**: Missing 20-byte NDR header between RPC and PNIO blocks
**Fix**: Per commit 741bd70, p-net silently rejects requests without NDR
```
RPC Header (80 bytes)
NDR Header (20 bytes):  ← WAS MISSING!
  - ArgsMaximum (4 LE)
  - ArgsLength (4 LE)
  - MaxCount (4 LE)
  - Offset (4 LE)
  - ActualCount (4 LE)
PNIO Blocks (AR, IOCR, Alarm, ExpSubmod)
```

### 5. Other Fixes
- Source IP: Don't use 0.0.0.0 (prevents responses)
- flags1: 0x22 (LAST_FRAGMENT | IDEMPOTENT)
- Object UUID: Use AR UUID, not PNIO_UUID
- No inter-block padding (per commit 7e0f01a)

## Packet Comparison Results

### Python Packet (after all fixes):
```
Offset 24-31 (Interface UUID): 01 00 a0 de 97 6c d1 11
```

### C Controller Packet:
```
Offset 24-31 (Interface UUID): 01 00 A0 DE 97 6C D1 11
```

**MATCH!** ✓ Python RPC header now matches C controller byte-for-byte.

## Status: RESOLVED — DAP Connect + PrmEnd Succeeded (2026-02-09)

**The RPC header fixes documented above were necessary but not sufficient.**
After fixing the header issues (bugs #1-#3 below), additional PNIO block-level
bugs (#4-#10) were discovered and fixed. The full journey is documented in:

**[docs/development/PROFINET_RPC_BUG_FIXES.md](../../docs/development/PROFINET_RPC_BUG_FIXES.md)**

RTU log confirming success:
```
Connect call-back. Status: 0x00 0x00 0x00 0x00
State transition: W_CIND -> W_PEIND
PrmEnd call-back. AREP: 1, result: 0
```

### Additional bugs found after RPC header was fixed:
4. IOCRTagHeader VLAN priority (0x0000 → 0xC000)
5. ARProperties bit position (bit 1 → bit 4)
6. ExpectedSubmoduleBlockReq wire format (complete rewrite)
7. IOCR IOData/IOCS NO_IO placement (DAP in wrong IOCR direction)
8. IOCR frame offset overlap (IOPS byte not accounted for)
9. AlarmCR rta_timeout_factor > 100 (spec max exceeded)
10. NDR response parser format (20 bytes PNIOStatus-first, not 24 bytes)

## Commits Made (Session 014RJQ1WFeNeANju5fF24eoz)

1. **1ff56dd**: Version tracking
2. **19e2d96**: Add NDR header (20 bytes)
3. **c68fec1**: Fix source IP (0.0.0.0 → kernel routing)
4. **391b4dd**: Correct RPC header field order (80 bytes)
5. **61f170b**: Add UUID swapping to LE
6. **956c594**: Use AR UUID as object_uuid
7. **d31a82d**: Fix PNIO_UUID constant byte order

## Remaining Work

The DAP-only Connect + PrmEnd is proven. Next steps:

1. **Fix Record Read error handling** — graceful fallback when RTU rejects index 0xF844
2. **Test full Connect** with discovered modules in ExpectedSubmoduleBlockReq
3. **Handle ApplicationReady** — RTU-initiated, controller must respond
4. **Begin cyclic I/O exchange** on configured IOCRs

See [PROFINET_RPC_BUG_FIXES.md](../../docs/development/PROFINET_RPC_BUG_FIXES.md) for full details.

## References
- PROFINET spec: IEC 61158-6-10
- C implementation: `src/profinet/profinet_rpc.c`
- RPC header struct: `src/profinet/profinet_frame.h:84-104`
- UUID swapping: `src/profinet/rpc_strategy.c` (uuid_swap_fields)
- Bug 0.4 (NDR): Commit 741bd70
- UUID swap (Bug 0.6): Commit 84649b6
- Padding removal: Commit 7e0f01a

## Validation Command
```bash
# Verify script version
head -30 /home/user/Water-Controller/experimental/profinet-rpc-debug/test-profinet-scapy.py | grep VERSION

# Run test
python3 /home/user/Water-Controller/experimental/profinet-rpc-debug/test-profinet-scapy.py --interface enp0s3 --timeout 3
```

## Lessons Learned
1. Always check C struct definitions for exact field order
2. UUID swapping is per DREP, affects RPC header only (not PNIO blocks)
3. Constants must match C byte order BEFORE swapping
4. NDR header is mandatory (p-net silently drops without it)
5. When both implementations fail identically, look beyond what you've been fixing
