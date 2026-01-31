# Statement to RTU Team: PROFINET Connection Status

**From:** Controller Team
**To:** RTU Team (Water-Treat firmware)
**Date:** 2026-01-31
**Re:** PROFINET RPC Connect — what we tried, what we saw, what we need from you

---

## What We Tried

We attempted a full PROFINET AR (Application Relationship) establishment
against the Water-Treat RTU. The controller has a 48-strategy brute-force
system that iterates through combinations of wire-format parameters to find
what works. We captured the attempt in `profi.pcapng`.

The captured attempt used:
- **DCP Identify** multicast — RTU responded in 1.58ms as `rtu-4b64`
- **RPC Connect Request** with:
  - OpNum = 0 (standard Connect per IEC 61158-6)
  - DREP = 0x10 (little-endian declaration)
  - No NDR header (PNIO blocks immediately after RPC header)
  - UUIDs in big-endian (as-stored from C arrays, no byte swap)
  - Full slot configuration: DAP (slot 0) + 8 input slots + 7 output slots
  - Default timing: SendClockFactor=32 (1ms), ReductionRatio=32 (32ms),
    WatchdogFactor=3 (96ms)
  - ARBlockReq, 2x IOCRBlockReq (input + output), AlarmCRBlockReq,
    ExpectedSubmoduleBlock

## What We Saw

**DCP worked.** The RTU responded to discovery with station name, IP, and
vendor/device ID. No issues here.

**RPC Connect failed.** The RTU returned an RPC Response with
`fragment_length=0` — an empty body with no PNIO blocks at all. This is
not a PNIO-level error (no error code, no Module-Diff-Block). The request
was rejected at the RPC/DCE layer before p-net's PNIO block parser ran.

**Root cause identified on our side:** Our RPC header serialization declared
DREP=0x10 (little-endian) but encoded all multi-byte header fields in
big-endian (`htonl`/`htons`). This caused p-net to read `fragment_length`
as 46,082 instead of 692, and `interface_version` as 16,777,216 instead of
1. We have since fixed this (commit `31ebf4a`).

**RTU response DREP anomaly observed:** The RTU's response had DREP=0x00
(declares big-endian), but the `interface_version` field bytes `01 00 00 00`
decode correctly only as little-endian (value=1). The Interface UUID in the
response was also in LE encoding (`01 00 a0 de 97 6c ...`). This suggests
p-net writes LE natively but declares DREP=0x00 in outgoing packets. Our
response parser now handles this with DREP-aware decoding, but we want to
confirm this is expected behavior from your side.

## What We Fixed

1. **RPC header byte order** — all multi-byte fields now encoded LE matching
   DREP=0x10 (commit `31ebf4a`)
2. **UUID wire encoding** — `uuid_swap_fields()` now converts UUIDs from BE
   storage to LE wire format per DCE-RPC spec
3. **DREP-aware response parsing** — `rpc_hdr_u16()`/`rpc_hdr_u32()` check
   the sender's DREP before decoding, handling both LE and BE responses
4. **IOCR block format** — rewrote to IEC 61158-6 with proper IOData objects
   (slot + subslot + frame_offset) and separate IOCS section
5. **NDR header support** — strategy system can insert or omit the 20-byte
   NDR request header

## What We Need From You

We have open questions that only the RTU team can answer. Our strategy system
can brute-force through 48 combinations, but confirming these would let us
converge on the first attempt instead of iterating:

### Q1. NDR Header — does p-net require it?

Our p-net source review indicates `pf_get_ndr_data_req()` expects a 20-byte
NDR header (ArgsMaximum, ArgsLength, MaxCount, Offset, ActualCount) between
the RPC header and the first PNIO block. The pcap capture did NOT include an
NDR header (that was our bug — we hadn't added it yet).

**Question:** Does your p-net build expect the NDR header on Connect requests?
Has it been tested with and without? We can send either way.

### Q2. UUID encoding — LE or BE?

p-net's `pf_get_uuid()` reads UUID fields using endian-aware accessors
(`pf_get_uint32`, `pf_get_uint16`), which means it should follow DREP.
With our DREP=0x10, p-net should expect:
- `data1` (time_low): 4 bytes little-endian
- `data2` (time_mid): 2 bytes little-endian
- `data3` (time_hi): 2 bytes little-endian
- `data4` (clock_seq + node): 8 bytes as-is

**Question:** Can you confirm p-net on the RTU reads UUIDs according to
DREP? Or does it hardcode one encoding? We observed your response uses LE
UUID encoding despite DREP=0x00 — is that intentional?

### Q3. DREP in RTU responses — 0x00 vs 0x10?

The pcap shows the RTU responds with DREP=0x00 (declares BE) but encodes
fields in LE. Our parser handles this, but we want to understand the intent.

**Question:** Is this a p-net configuration issue, a known p-net behavior,
or something in your build? What DREP should we expect from the RTU?

### Q4. Slot/Module configuration

We sent an ExpectedSubmoduleBlock with:
- Slot 0: DAP (module 0x00000001, submodule 0x00000001)
- Slots 1-8: Input sensors (module IDs 0x10-0x70, 5 bytes each: float32 + quality)
- Slots 9-15: Output actuators (module IDs 0x100-0x120, 4 bytes each)

**Question:** Does this match your GSDML and runtime slot configuration?
What slots/modules are actually plugged in your test RTU? A Module-Diff-Block
in the response would tell us, but we never got that far (empty response).

### Q5. Has the RTU successfully connected with any other controller?

If you have tested with a Siemens S7-1500, CODESYS, or any other PROFINET
controller, a pcap of a **successful** connection would be extremely valuable.
It would give us a known-good reference frame to compare against.

### Q6. p-net version and configuration

**Question:** Which version of p-net is the RTU built against? Have you
modified the default p-net RPC handling, or is it stock? Any custom callbacks
that might affect Connect request processing?

### Q7. Vendor/Device ID registration

The RTU currently reports vendor_id=0x0493 (rt-labs AB's ID from the p-net
sample app) and device_id=0x0001. This works for lab testing but could
cause issues if any other p-net sample devices are on the same network.

**Question:** Are there plans to register a PI vendor ID for the Water-Treat
project, or is 0x0493 the long-term plan for lab use?

---

## Current Controller Strategy State

Our brute-force strategy system iterates through 48 combinations across 5
dimensions. Based on our analysis, the most likely correct strategy for the
p-net-based RTU is:

```
Strategy index 1: "default op0: as-stored, +NDR, full"
  UUID:    LE encoding (single swap from BE storage, matching DREP=0x10)
  NDR:     20-byte NDR header present before PNIO blocks
  Slots:   Full configuration (DAP + sensors + actuators)
  Timing:  Default (1ms cycle, 32ms update, 96ms watchdog)
  OpNum:   0 (standard Connect)
```

If this doesn't work, the system automatically advances through all 48
strategies. But confirming the answers above would eliminate guesswork.

---

## Summary of What We Observed Worked Best

From the pcap and code analysis:

| What | Status | Confidence |
|------|--------|------------|
| DCP Discovery | Working | High — RTU responds correctly |
| RPC transport (UDP 34964) | Working | High — RTU sends RPC response |
| DREP byte order | Fixed on our side | High — root cause identified and resolved |
| UUID encoding (LE per DREP) | Untested post-fix | Medium — p-net source says yes, pcap was pre-fix |
| NDR header presence | Untested post-fix | Medium — p-net source says required, pcap was without |
| PNIO block format | Untested post-fix | Medium — rewrote to IEC 61158-6 spec |
| Full slot config | Untested post-fix | Low — never got past RPC layer |
| Cyclic data exchange | Not reached | N/A — need successful Connect first |

**Bottom line:** DCP works. RPC transport works. The RPC header encoding bug
that caused the empty response has been fixed. We need to validate the full
Connect sequence end-to-end, and the questions above would help us get there
on the first attempt rather than iterating through 48 strategy combinations.
