# Scapy PROFINET Test - Reference Implementation

> **Note (2026-02-09):** The RPC Connect issue has been **resolved**. The root
> cause was 10 code bugs in the C controller's packet construction, not the
> Scapy reference. See
> [PROFINET_RPC_BUG_FIXES.md](../development/PROFINET_RPC_BUG_FIXES.md).

This document describes how to use the Scapy reference implementation to debug PROFINET RPC communication issues.

## Purpose

The `test-profinet-scapy.py` script provides a **working reference implementation** of PROFINET RPC Connect using Scapy. This allows packet-level comparison between:
- **Scapy packets** (known working implementation)
- **C controller packets** (currently broken with RPC timeout)

By comparing the raw bytes, we can identify exactly where the C implementation diverges from the specification.

## Prerequisites

```bash
# Install Scapy
pip3 install scapy

# Or in a virtual environment
python3 -m venv venv
source venv/bin/activate
pip install scapy
```

## Usage

### Basic Discovery and Connect

```bash
# Run as root (required for raw socket access)
sudo python3 scripts/test-profinet-scapy.py

# Specify interface
sudo python3 scripts/test-profinet-scapy.py --interface eth0

# Target specific RTU
sudo python3 scripts/test-profinet-scapy.py --station-name rtu-967e
```

### Capture Packets for Analysis

Run tcpdump in one terminal:

```bash
sudo tcpdump -i eth0 -w /tmp/scapy-profinet.pcap udp port 34964
```

Run the Scapy test in another terminal:

```bash
sudo python3 scripts/test-profinet-scapy.py --interface eth0
```

### Compare with C Controller

1. **Capture Scapy packets** (working):
   ```bash
   sudo tcpdump -i eth0 -w /tmp/scapy-profinet.pcap udp port 34964 &
   sudo python3 scripts/test-profinet-scapy.py --interface eth0
   ```

2. **Capture C controller packets** (broken):
   ```bash
   sudo tcpdump -i eth0 -w /tmp/c-profinet.pcap udp port 34964 &
   docker logs wtc-controller -f
   # Trigger a connection attempt
   ```

3. **Compare packets** with Wireshark or `tcpdump -X`:
   ```bash
   # Scapy packet (reference)
   tcpdump -r /tmp/scapy-profinet.pcap -X | less

   # C controller packet (broken)
   tcpdump -r /tmp/c-profinet.pcap -X | less
   ```

4. **Look for differences**:
   - Block ordering
   - Block lengths
   - Inter-block padding (or lack thereof)
   - UUID byte ordering
   - Field alignment
   - Total packet size

## Expected Output

### Success Case

```
[INFO] Controller initialized on eth0 (MAC: aa:bb:cc:dd:ee:ff)
[INFO] === Phase 1: DCP Discovery (timeout=3.0s) ===
[INFO] Searching for all devices
[INFO] Sending DCP Identify Request to 01:0e:cf:00:00:00
[INFO] ✓ Discovered: rtu-967e @ 192.168.6.21 (00:11:22:33:44:55) VID:0272 DID:0c05
[INFO] Discovery complete: found 1 device(s)

[INFO] === Phase 2: RPC Connect to rtu-967e (192.168.6.21) ===
[INFO] Sending RPC Connect Request to 192.168.6.21:34964
[INFO]   AR UUID: a1b2c3d4e5f6...
[INFO]   Activity UUID: 11223344...
[INFO]   Session Key: 1

[INFO] Packet structure:
###[ IP ]###
  ...
###[ UDP ]###
  sport= 34964
  dport= 34964
###[ DceRpc4 ]###
  ...

[INFO] Total packet size: 512 bytes
[INFO] Hex dump:
  0000: 45 00 01 f4 00 01 00 00 40 11 ...
  ...

[INFO] ✓ Sent 470 bytes
[INFO] Waiting for Connect Response...
[INFO] ✓ Received 234 bytes from ('192.168.6.21', 34964)

[INFO] ✓✓✓ SUCCESS ✓✓✓
[INFO] RPC Connect completed successfully!
```

### Failure Case

```
[INFO] ✓ Sent 470 bytes
[INFO] Waiting for Connect Response...
[ERROR] ✗ Connect timeout - no response from RTU
[ERROR]   This means RTU rejected the packet or couldn't parse it

[ERROR] ✗✗✗ FAILED ✗✗✗
```

## Packet Structure Reference

The Connect Request contains these blocks in order:

```
IP Header (20 bytes)
  └─ src: controller IP
  └─ dst: RTU IP

UDP Header (8 bytes)
  └─ sport: 34964
  └─ dport: 34964

DCE/RPC Header (~80 bytes)
  └─ ptype: 0x00 (Request)
  └─ opnum: 0x00 (Connect)
  └─ object_uuid: PNIO UUID
  └─ if_uuid: PNIO UUID
  └─ activity_uuid: random

[PADDING?? 20 bytes NDR header??]

ARBlockReq (~60 bytes)
  └─ BlockType: 0x0101
  └─ BlockLength: (calculated)
  └─ AR UUID, Session Key, MACs, etc.

[PADDING??]

IOCRBlockReq Input (~50 bytes)
  └─ BlockType: 0x0102
  └─ IOCRType: 0x0001 (Input)
  └─ Frame ID: 0x8001

[PADDING??]

IOCRBlockReq Output (~50 bytes)
  └─ BlockType: 0x0102
  └─ IOCRType: 0x0002 (Output)
  └─ Frame ID: 0x8000

[PADDING??]

AlarmCRBlockReq (~20 bytes)
  └─ BlockType: 0x0103

[PADDING??]

ExpectedSubmoduleBlockReq (~80 bytes)
  └─ BlockType: 0x0104
  └─ API 0, 2 slots (DAP + Temp)
```

**KEY QUESTION**: Where does padding go?

- Option 1: NO padding (contiguous blocks)
- Option 2: `align_to_4()` after each block
- Option 3: Padding AFTER calculating BlockLength
- Option 4: 20-byte NDR header between RPC and first block

## Known Issues in C Implementation

Based on commit history, these issues have been encountered:

1. **Inter-block padding** (commit 7e0f01a):
   - Initially added padding with `align_to_4()` between blocks
   - Later removed because p-net advances by `(4 + BlockLength)` only
   - Padding causes offset mismatch in p-net parser

2. **UUID byte ordering** (commit 84649b6):
   - UUIDs must be little-endian per DREP=0x10
   - Some fields need byte swapping

3. **Missing NDR header** (commit 741bd70):
   - 20-byte NDR header may be required between RPC and PNIO blocks
   - C implementation may be missing this

4. **BlockLength calculation**:
   - Should be calculated BEFORE or AFTER padding?
   - Conflicting documentation in RTU docs vs p-net source

## Debugging Tips

### Wireshark Filters

```
# PROFINET traffic
pn_dcp or pn_rt or dcerpc

# RPC Connect specifically
dcerpc.opnum == 0

# By IP
ip.addr == 192.168.6.21 and udp.port == 34964
```

### Compare Byte-by-Byte

```bash
# Extract just the UDP payload (no headers)
tcpdump -r /tmp/scapy-profinet.pcap -X | grep '0x' > scapy.txt
tcpdump -r /tmp/c-profinet.pcap -X | grep '0x' > c.txt

# Diff them
diff -u scapy.txt c.txt
```

### Check Block Boundaries

Look for block headers (first 4 bytes of each block):
- `01 01` = ARBlockReq
- `01 02` = IOCRBlockReq
- `01 03` = AlarmCRBlockReq
- `01 04` = ExpectedSubmoduleBlockReq

If these appear at wrong offsets → padding issue!

## Next Steps

If the Scapy test **succeeds** but C test **fails**:

1. Compare the hex dumps byte-by-byte
2. Identify the first byte where they differ
3. Check if the difference is:
   - Missing/extra padding
   - Wrong BlockLength
   - Byte order (endianness)
   - Missing NDR header
   - UUID format

4. Fix the C code to match Scapy exactly

## References

- [IEC 61158-6-10](https://webstore.iec.ch/publication/83457) - PROFINET specification
- [Scapy PROFINET](https://scapy.readthedocs.io/en/latest/api/scapy.contrib.pnio.html) - Scapy docs
- [p-net source](https://github.com/rtlabs-com/p-net) - Device stack implementation
- [PROFINET RPC Timeout](./PROFINET_RPC_TIMEOUT.md) - Troubleshooting guide

## Support

If this test reveals differences, update:
1. `src/profinet/profinet_rpc.c` - Fix block building
2. `CLAUDE.md` - Document the fix
3. This file - Add findings to "Known Issues"
