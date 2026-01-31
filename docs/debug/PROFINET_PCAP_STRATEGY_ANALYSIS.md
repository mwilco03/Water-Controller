# PROFINET pcap & Connection Strategy Analysis

Analysis of `profi.pcapng` cross-referenced against the 48-strategy brute-force
connection system in `src/profinet/rpc_strategy.c` and `src/profinet/profinet_rpc.c`.

## pcap Summary (profi.pcapng)

The capture contains **4 frames** between a VirtualBox controller
(`08:00:27:13:96:7e`) and a Raspberry Pi RTU (`b8:27:eb:5f:4b:64`,
station `rtu-4b64`):

| # | Delta    | Direction              | Protocol | Description |
|---|----------|------------------------|----------|-------------|
| 1 | 0.000s   | Controller -> Multicast | DCP Identify | Broadcast discovery, Xid `0xec11a0ee` |
| 2 | +1.58ms  | RTU -> Controller | DCP Identify Response | Station: `rtu-4b64`, Vendor: `0x0493` (rt-labs p-net default), Device: `0x0001` |
| 3 | +33.17s  | Controller -> RTU | RPC Connect Request | DCE/RPC Request, OpNum=0, 692 bytes PNIO payload |
| 4 | +33.18s  | RTU -> Controller | RPC Connect Response | DCE/RPC Response, **fragment_length=0**, empty body |

### Key Observation: The Response is Empty

Frame 4 has **fragment_length=0** and no PNIO blocks (no ARBlockRes, no
IOCRBlockRes, no AlarmCRBlockRes). The RTU acknowledged the RPC transaction
at the transport level but returned an empty payload body. The Connect
Request was rejected before the PNIO layer processed it.

### Vendor ID Clarification

Vendor `0x0493` is **rt-labs AB's** registered PI vendor ID (the company that
makes the p-net PROFINET stack). The Water-Treat RTU inherits this default
from the p-net sample application. It is not a Water-Treat-specific registration.
This is acceptable for lab use but would need a PI-assigned vendor ID for
production deployment.

---

## Root Cause: DREP/Byte-Order Mismatch

The pcap captures the exact bug later fixed in commit `31ebf4a`:

### Request (Frame 3) — Controller declared LE, encoded BE

```
RPC Header fields (at offset 0x2C):
  DREP[0] = 0x10  → "all multi-byte header fields are little-endian"

  interface_version wire bytes: 00 00 00 01
    Read as LE (per DREP): 0x01000000 = 16,777,216  ← WRONG
    Read as BE (intended):  0x00000001 = 1            ← correct

  fragment_length wire bytes: 02 b4
    Read as LE (per DREP): 0xB402 = 46,082  ← WRONG
    Read as BE (intended):  0x02B4 = 692     ← correct
```

The controller called `htonl()`/`htons()` (big-endian) for header fields
while declaring DREP=0x10 (little-endian). The RTU read DREP, decoded as
LE, got `fragment_length=46082`, and rejected the PDU.

### Response (Frame 4) — RTU declared BE, encoded LE

```
  DREP[0] = 0x00  → "all multi-byte header fields are big-endian"

  interface_version wire bytes: 01 00 00 00
    Read as BE (per DREP): 0x01000000 = 16M  ← wrong
    Read as LE (actual):    0x00000001 = 1    ← correct
```

The RTU's p-net stack writes LE regardless of its DREP declaration. This is
a known p-net behavior — the stack sets DREP=0x00 in responses but encodes
fields in native (LE) byte order.

**Both sides had inverted DREP declarations.** This is the primary failure mode.

---

## What Was Observed on the Wire

### UUIDs

| UUID | Wire Bytes | Encoding |
|------|-----------|----------|
| Object (AR) | `ed ba 2e 88 7b 0d 17 be 41 56 f8 c4 df 48 d8 79` | As-stored from C array (BE) |
| Interface | `de a0 00 01 6c 97 11 d1 82 71 00 a0 24 42 df 7d` | BE encoding of `DEA00001-6C97-11D1-8271-00A02442DF7D` |

The controller sent UUIDs in BE (as-stored). The RTU echoed the Object UUID
back (byte-swapped into its own LE encoding in the response), indicating the
RPC layer at least partially processed the request before the PNIO layer rejected it.

### PNIO Payload (Frame 3, 692 bytes)

| Block | Type | Key Parameters |
|-------|------|----------------|
| ARBlockReq | 0x0101 | AR type=IOCAR, session_key=1 |
| IOCRBlockReq | 0x0102 | Input IOCR: type=1, frame_id=0x8002, SCF=32, RR=32 |
| IOCRBlockReq | 0x0102 | Output IOCR: type=2, frame_id=0x8003, SCF=32, RR=32 |
| AlarmCRBlockReq | 0x0103 | RTA timeout=100 (10s), retries=3, max_alarm_data=200 |
| ExpectedSubmod | 0x0104 | DAP + 8 input slots + 7 output slots |

### What Was NOT in the Request

- **No NDR header** — PNIO blocks start immediately after the RPC header
- **No Write request** — only the Connect was attempted before the capture ended

---

## What the Strategy System Tried

The pcap captures a single Connect attempt. Based on the wire format observed:

| Dimension | Value Sent | Strategy Index |
|-----------|-----------|----------------|
| UUID format | AS_STORED (BE on wire) | 0 |
| NDR header | ABSENT | 0 |
| Slot scope | FULL (16 slots) | 0 |
| Timing | DEFAULT (SCF=32, RR=32, WD=3) | 0 |
| OpNum | STANDARD (0) | 0 |

This was **strategy index 0**: `"default op0: as-stored, no NDR, full"`.

It failed because of the DREP byte-order bug, not because of wrong strategy
parameters. The bug was in `build_rpc_header()` serialization — below the
strategy layer. All 48 strategies would have produced the same DREP mismatch.

---

## What p-net Actually Expects (from source review)

Reviewing the p-net stack source (`pf_cmrpc.c`, `pf_block_reader.c`):

| Dimension | p-net Expectation | Evidence |
|-----------|-------------------|----------|
| UUID encoding | **Respects DREP** — reads data1/data2/data3 using endian-aware `pf_get_uint32`/`pf_get_uint16` | `pf_get_uuid()` in pf_block_reader.c |
| NDR header | **Expected** — 20-byte NDR header before PNIO blocks | `pf_get_ndr_data_req()` parses ArgsMaximum, ArgsLength, MaxCount, Offset, ActualCount |
| RPC header fields | **Respects DREP** — all multi-byte fields decoded per DREP flag | Standard DCE-RPC parsing |
| PNIO block payloads | **Always big-endian** regardless of DREP | Per IEC 61158-6 |
| OpNum | **0 for Connect** | Standard PROFINET operation numbers |

### Corrected Optimal Strategy (Post-Fix)

After commit `31ebf4a` (which fixed the DREP mismatch), `build_rpc_header()`
now correctly:
- Encodes header fields in LE (matching DREP=0x10)
- Calls `uuid_swap_fields()` to convert UUIDs from BE storage to LE wire format

Since p-net reads UUIDs according to DREP, the correct strategy is:

```
Strategy index 1: "default op0: as-stored, +NDR, full"
  uuid_format:  UUID_WIRE_AS_STORED     ← build_rpc_header already swaps to LE
  ndr_mode:     NDR_REQUEST_PRESENT     ← p-net expects 20-byte NDR header
  slot_scope:   SLOT_SCOPE_FULL         ← full slot config
  timing:       TIMING_DEFAULT          ← SCF=32, RR=32, WD=3
  opnum:        OPNUM_STANDARD          ← OpNum=0 (Connect)
```

**The pcap showed no NDR header, but that was the failing request.** p-net's
source code shows it expects NDR. The absence of NDR may have been a
*secondary* failure cause masked by the DREP bug being the primary one.

---

## Ambiguity: UUID Encoding

There is genuine uncertainty about UUID handling:

1. **p-net source says**: read UUIDs per DREP → expects LE when DREP=0x10
   → `UUID_WIRE_AS_STORED` (single swap from build_rpc_header) = correct

2. **pcap RTU response shows**: DREP=0x00 (claims BE) but interface UUID
   bytes are `01 00 a0 de 97 6c d1 11...` which is LE encoding
   → p-net may ignore its own DREP declaration for outgoing UUIDs

3. **The pcap request sent BE UUIDs** and the RTU echoed the Object UUID
   back (in swapped form) → the RPC layer accepted the transaction despite
   the UUID being in the "wrong" encoding for DREP=0x10

This needs confirmation from the RTU team. The strategy system covers both
cases (indices 0-1 for AS_STORED/LE, indices 2-3 for SWAP_FIELDS/BE).

---

## Fix Timeline

| Commit | Change | Assessment |
|--------|--------|------------|
| `90adf01` | Reverted to BE UUIDs, removed NDR | Partially correct — preserved working UUID format but missed root cause |
| `375a698` | Changed to LE UUIDs, added NDR back | Spec-correct per p-net source |
| `31ebf4a` | **Fixed RPC header serialization to match DREP=0x10** | Root cause fix — all header fields now LE |
| `74f254e` | Added OpNum strategy dimension (24→48 strategies) | Expanded coverage for non-standard stacks |

---

## Strategy Effectiveness Ranking

For iterating to a working connection:

| Priority | Dimension | Impact if Wrong |
|----------|-----------|----------------|
| 1 | RPC header byte order | Silent rejection (empty response) — not a strategy dimension, fixed in code |
| 2 | OpNum (0 vs 3) | Silent drop or wrong handler |
| 3 | UUID format (AS_STORED vs SWAP) | Protocol rejection or wrong AR UUID |
| 4 | NDR header (ABSENT vs PRESENT) | Parse failure at PNIO layer |
| 5 | Slot scope (FULL vs DAP_ONLY) | Module diff block (recoverable) |
| 6 | Timing (DEFAULT/AGGRESSIVE/CONSERVATIVE) | Runtime watchdog, not connect rejection |

The current iteration order (wire-format combos innermost, timing/opnum outermost)
is reasonable — wire format is the most likely differentiator between firmware versions.
