# PROFINET RPC Bug Fix Journey

## Achievement: Full PROFINET Cyclic Data Exchange (2026-02-10)

On February 9-10, 2026, the Water Treatment Controller achieved **full PROFINET
cyclic data exchange** with an RTU running p-net v0.2.0. Starting from zero (silent
RPC drops), 17 bugs were found and fixed across two sessions to reach stable I/O:

```
Controller (192.168.6.13)                    RTU rtu-ec3b (192.168.6.21)
     |                                             |
     |─── DCP Identify Request (multicast) ───────>|
     |<────────── DCP Identify Response ───────────|  ✅ Always worked
     |                                             |
     |═══ RPC Connect Request (UDP 34964) ════════>|
     |<══════════ Connect Response ════════════════|  ✅ Bug #1-#10
     |         PNIOStatus = 0x00000000             |
     |                                             |
     |═══ RPC PrmEnd (IODControlReq) ═════════════>|
     |<════════ PrmEnd Response ══════════════════ |  ✅ Bug #11
     |         PNIOStatus = 0x00000000             |
     |                                             |
     |◄══ ApplicationReady (IOCControlReq) ═══════ |  ✅ Bug #12-#15
     |═══ ApplicationReady Response (CControl) ══=>|
     |                                             |
     |◄══════════ Cyclic Input Data (0xC001) ═════ |  ✅ Bug #16-#17
     |═══════════ Cyclic Output Data (0xC000) ════>|
     |           (VLAN-tagged RT frames)           |
```

**RTU log confirming full DATA state:**
```
Connect call-back. Status: 0x00 0x00 0x00 0x00
State transition: W_CIND -> W_PEIND
PrmEnd call-back. AREP: 1, result: 0
State transition: W_PEIND -> W_PERES
State transition: W_PERES -> W_ARDY
State transition: W_ARDY -> W_ARDYCNF
CMIO: WDATA -> DATA
CPM: FRUN -> RUN
CMDEV: WDATA -> DATA
```

---

## Bug Index

### Session 1: RPC Connect + PrmEnd (Bugs #1-#10)

| # | Bug | Symptom | Root Cause | Fix |
|---|-----|---------|------------|-----|
| 1 | [Inter-block padding](#bug-1-inter-block-padding) | Silent drop (timeout) | Alignment bytes between blocks | Remove all padding |
| 2 | [UUID byte ordering](#bug-2-uuid-byte-ordering) | Silent drop (timeout) | Interface UUID not LE-swapped | Swap fields 1-3 per DREP |
| 3 | [Missing NDR header](#bug-3-missing-ndr-header) | Silent drop (timeout) | No NDR header before PNIO | Add 20-byte NDR request header |
| 4 | [IOCRTagHeader value](#bug-4-iocr-tag-header) | Silent drop (timeout) | VLAN priority 0 instead of 6 | Set high bits to 0xC000 |
| 5 | [ARProperties bit position](#bug-5-arproperties-bit-position) | Silent drop (timeout) | Wrong bit for parameterization server | Use bit 4 (0x00000010) |
| 6 | [ExpectedSubmoduleBlockReq format](#bug-6-expectedsubmoduleblockreq-format) | Silent drop (timeout) | Wrong wire format layout | Full rewrite to IEC 61158-6 |
| 7 | [IOCR IOData/IOCS NO_IO placement](#bug-7-iocr-iodataiocs-no_io-placement) | 0xDB 0x81 0x02 0x1B | DAP submodules in wrong IOCR | IOData→INPUT, IOCS→OUTPUT |
| 8 | [IOCR frame offset overlap](#bug-8-iocr-frame-offset-overlap) | 0xDB 0x81 0x02 0x18 | Overlapping IOPS bytes | Advance offset by data_length+1 |
| 9 | [AlarmCR rta_timeout_factor](#bug-9-alarmcr-rta_timeout_factor) | 0xDB 0x81 0x04 0x07 | Factor 200 > spec max 100 | Clamp to 100 |
| 10 | [NDR response parser format](#bug-10-ndr-response-parser-format) | False "error 0x46000000" | Wrong response header layout | Fix to 20-byte PNIOStatus-first |

### Session 2: ApplicationReady + Cyclic Data Exchange (Bugs #11-#17)

| # | Bug | Symptom | Root Cause | Fix |
|---|-----|---------|------------|-----|
| 11 | [Activity UUID reuse](#bug-11-activity-uuid-reuse) | "Out of session resources" | New UUID per RPC op exhausted pool | Reuse Connect's UUID for all ops |
| 12 | [Connect response block alignment](#bug-12-connect-response-block-alignment) | FrameID stuck at 0xFFFF | `align_to_4()` skipped IOCRBlockRes | Remove inter-block alignment in parser |
| 13 | [ModuleDiffBlock retry logic](#bug-13-modulediffblock-retry-logic) | Infinite retry loop | DAP diffs triggered retry | DAP-only diffs are informational |
| 14 | [CControl response format](#bug-14-ccontrol-response-format) | "Unknown activity UUID" | Missing NDR header, wrong block type | Add NDR, use 0x8112, DONE cmd, DREP-aware UUID |
| 15 | [ControlCommand bitfield values](#bug-15-controlcommand-bitfield-values) | Wrong Release command | Sequential enum vs bitfield | Fix to IEC 61158-6 Table 777 bitfield |
| 16 | [VLAN tag on output frames](#bug-16-vlan-tag-on-output-frames) | CPM rejects frames | Missing 802.1Q VLAN tag | Add 4-byte VLAN tag (PCP=6) |
| 17 | [DataStatus + VLAN receive offset](#bug-17-datastatus-and-vlan-receive) | DataStatus 0x15 / wrong parse offset | Missing StationProblem bit; hardcoded offset | Add 0x20 bit; detect VLAN tag in parser |

---

## Bug Details

### Bug #1: Inter-block Padding

**Symptom:** RTU silently drops Connect request. No response, 5s timeout.

**Root cause:** The original implementation added `align_to_4()` padding bytes
between PNIO blocks (ARBlockReq, IOCRBlockReq, AlarmCRBlockReq,
ExpectedSubmoduleBlockReq). p-net's block reader advances by exactly
`4 + BlockLength` bytes — any extra padding bytes between blocks cause the
parser to misalign and reject the entire request.

**Fix (`profinet_rpc.c:568`):**
```c
/* NOTE: NO inter-block padding. p-net advances by (4 + BlockLength) only.
 * Any padding between blocks would cause parser offset mismatch. */
```

**Key insight:** PROFINET block parsing is strictly contiguous. The block type (2
bytes) + block length (2 bytes) + content (BlockLength bytes) must be immediately
followed by the next block type. No alignment, no gaps.

**Reference:** `pf_cmrpc.c` Connect request parsing loop at line 1155.

---

### Bug #2: UUID Byte Ordering

**Symptom:** RTU silently drops Connect request. No response, 5s timeout.

**Root cause:** DCE/RPC specifies Data Representation (DREP) byte 0 = 0x10 for
little-endian. Per the DCE/RPC spec, UUID fields 1-3 (`time_low`, `time_mid`,
`time_hi_and_version`) must be byte-swapped to match DREP. The controller was
sending UUIDs in big-endian (network byte order), causing the RTU's UUID
comparison to fail.

**Fix (`profinet_rpc.c:200,217,221` + `rpc_strategy.c:65-80`):**
```c
/* In RPC header construction */
uuid_swap_fields(hdr->object_uuid);     /* AR UUID */
uuid_swap_fields(hdr->interface_uuid);  /* PNIO Device UUID */
uuid_swap_fields(hdr->activity_uuid);   /* Activity UUID */
```

```c
/* rpc_strategy.c - uuid_swap_fields() */
void uuid_swap_fields(uint8_t *uuid) {
    /* time_low (bytes 0-3): reverse 4 bytes */
    /* time_mid (bytes 4-5): reverse 2 bytes */
    /* time_hi_and_version (bytes 6-7): reverse 2 bytes */
    /* bytes 8-15: unchanged */
}
```

**Key insight:** UUID byte swapping is per DREP and affects the RPC header only,
not PNIO block payloads. The swap applies to `time_low` (4 bytes), `time_mid` (2
bytes), and `time_hi_and_version` (2 bytes). Bytes 8-15 (`clock_seq` and `node`)
are always network order.

---

### Bug #3: Missing NDR Header

**Symptom:** RTU silently drops Connect request. No response, 5s timeout.

**Root cause:** Between the 80-byte DCE/RPC header and the first PNIO block, a
20-byte NDR (Network Data Representation) header is mandatory. p-net's
`pf_cmrpc_rm_connect_ind()` reads these 20 bytes before parsing any blocks.
Without NDR, the first PNIO block bytes are consumed as NDR fields, and
subsequent block parsing fails silently.

**Fix (`profinet_rpc.c:526-535`):**
```c
/* Bug 0.4 fix: NDR header is mandatory — p-net rejects requests without
 * it.  The NDR header sits between the RPC header and the PNIO blocks:
 *
 *   [RPC Header][NDR Header][AR Block][IOCR Block(s)][AlarmCR][ExpSubmod]
 */
size_t ndr_header_pos = pos;
pos += NDR_REQUEST_HEADER_SIZE;  /* Reserve 20 bytes for NDR */
```

**NDR request header format (20 bytes, all LE):**

| Offset | Field | Description |
|--------|-------|-------------|
| +0 | ArgsMaximum | Max response size caller accepts |
| +4 | ArgsLength | Actual PNIO payload length |
| +8 | MaxCount | NDR conformant array max (= ArgsLength) |
| +12 | Offset | NDR array offset (always 0) |
| +16 | ActualCount | NDR array actual (= ArgsLength) |

**Key insight:** NDR is required for ALL RPC operations (Connect, Control/PrmEnd,
Read). The same pattern applies to the ParameterEnd request (`profinet_rpc.c:1167`)
and Record Read request (`profinet_rpc.c:1937`).

---

### Bug #4: IOCR Tag Header

**Symptom:** RTU silently drops Connect request. No response, 5s timeout.

**Root cause:** IOCR blocks contain a `TagHeader` field for VLAN tagging.
p-net requires VLAN priority 6 (bits 15-13 = 110) in the high tag header,
corresponding to value 0xC000. The original code used 0x0000 (priority 0),
which p-net rejects.

**Fix (`profinet_rpc.c:591,718-721`):**
```c
write_u16_be(buffer, IOCR_TAG_HEADER_HIGH, &pos);  /* VLAN prio 6 */
write_u16_be(buffer, IOCR_TAG_HEADER_LOW, &pos);   /* VLAN prio 5 */
```

Where `IOCR_TAG_HEADER_HIGH = 0xC000` and `IOCR_TAG_HEADER_LOW = 0xA000`.

**Key insight:** PROFINET RT Class 1 frames use VLAN priority 6 (real-time) for
cyclic data. This is a hard requirement in p-net's IOCR validation.

---

### Bug #5: ARProperties Bit Position

**Symptom:** RTU silently drops Connect request. No response, 5s timeout.

**Root cause:** The AR Properties field uses bit 4 (value 0x00000010) to indicate
"parameterization server" type. The original code used bit 1 (value 0x00000002),
which p-net interpreted as an invalid AR type combination.

**Fix:** Changed AR properties from `0x00000002` to `0x00000010`.

**Reference:** IEC 61158-6-10 Table 539: ARProperties bit assignments.

---

### Bug #6: ExpectedSubmoduleBlockReq Format

**Symptom:** RTU silently drops Connect request. No response, 5s timeout.

**Root cause:** The ExpectedSubmoduleBlockReq (block type 0x0104) had an
incorrect wire format. The field ordering, nesting of APIs/slots/subslots, and
data description format did not match IEC 61158-6 §5.2.3.6. This required a
complete rewrite.

**Fix (`profinet_rpc.c:733+`):** Full rewrite to match the spec's nested structure:
```
ExpectedSubmoduleBlockReq:
  NumberOfAPIs (u16)
  For each API:
    API (u32)
    NumberOfSlots (u16=SlotNumber)
    For each Slot:
      SlotNumber (u16)
      ModuleIdentNumber (u32)
      ModuleProperties (u16)
      NumberOfSubslots (u16=SubslotNumber)
      For each Subslot:
        SubslotNumber (u16)
        SubmoduleIdentNumber (u32)
        SubmoduleProperties (u16)
        DataDescription[] (variable)
```

**Key insight:** The nesting is API → Slot → Subslot → DataDescription. Getting
any level wrong causes p-net's `pf_get_exp_sub()` parser to misalign on all
subsequent fields.

---

### Bug #7: IOCR IOData/IOCS NO_IO Placement

**Symptom:** Error `0xDB 0x81 0x02 0x1B` — "IOCR direction 1 not found."

**Root cause:** DAP submodules (slot 0, subslots 0x0001, 0x8000, 0x8001) are
NO_IO — they carry no process data. However, IOCR data descriptors must still
reference them correctly:
- **IOData** entries for NO_IO submodules go in the **Input IOCR** only
- **IOCS** entries for NO_IO submodules go in the **Output IOCR** only

The original code put both IOData and IOCS in both IOCRs, which p-net rejected
because it couldn't find the expected direction.

**Fix (`profinet_rpc.c:629-652`):**
```c
bool no_io = (params->expected_config[j].data_length == 0);
bool include;
if (no_io) {
    include = is_input_iocr;    /* IOData in INPUT only */
} else {
    include = (params->expected_config[j].is_input == is_input_iocr);
}
```

**Key insight:** NO_IO is the first real PNIO error (previous bugs caused silent
drops). p-net actually parsed the request far enough to validate IOCR contents,
proving bugs #1-#6 were all fixed. Error code `0x1B` = 27 decimal maps to the
direction check in `pf_cmdev.c`.

---

### Bug #8: IOCR Frame Offset Overlap

**Symptom:** Error `0xDB 0x81 0x02 0x18` — straddle/overlap check failure (error
code 24).

**Root cause:** Every IOData entry in an IOCR carries both data bytes AND an IOPS
(IO Provider Status) byte. p-net calculates:
```c
iops_offset = data_offset + data_length   /* pf_cmdev.c:2406 */
```

For NO_IO submodules (DAP), `data_length = 0`, so `iops_offset = data_offset`.
If all three DAP submodules have `frame_offset = 0`, their IOPS bytes (1 byte
each, starting at offset 0) overlap — which p-net detects in
`pf_cmdev_check_no_straddle()`.

**Fix (`profinet_rpc.c:648`):**
```c
/* Advance past data + 1 byte for IOPS.  p-net calculates each
 * submodule's iops_offset = data_offset + data_length, so every
 * IOData entry (including NO_IO with data_length=0) must occupy
 * at least 1 byte for its IOPS to avoid overlap. */
running_offset += params->expected_config[j].data_length + 1;
```

**Frame offset layout after fix (Input IOCR with 3 DAP + 1 sensor):**
```
Offset 0: DAP subslot 0x0001 (data=0, IOPS at 0)
Offset 1: DAP subslot 0x8000 (data=0, IOPS at 1)
Offset 2: DAP subslot 0x8001 (data=0, IOPS at 2)
Offset 3: Sensor subslot 0x0001 (data=5 bytes, IOPS at 8)
           [5 data bytes at offsets 3-7] [IOPS at 8]
```

**Key insight:** Even zero-length data entries need unique frame offsets because
the IOPS byte occupies 1 byte at `data_offset + data_length`. The `+1` accounts
for this IOPS byte.

---

### Bug #9: AlarmCR rta_timeout_factor

**Symptom:** Error `0xDB 0x81 0x04 0x07` — faulty AlarmCR Block.

**Root cause:** The TIMING_CONSERVATIVE profile had `rta_timeout_factor = 200`.
Per IEC 61158-6, the valid range is 1..100 (§5.2.3.5). p-net validates this at
`pf_cmdev.c:4126`:
```c
if (p_alarm_cr->rta_timeout_factor < 1 ||
    p_alarm_cr->rta_timeout_factor > 0x0064) {
    pf_set_error(..., 7);
}
```

**Fix (`rpc_strategy.c:47` + `profinet_rpc.c:712-713`):**
```c
/* rpc_strategy.c - TIMING_CONSERVATIVE */
.rta_timeout_factor = 100,  /* 10s alarm timeout (max per IEC 61158-6) */

/* profinet_rpc.c - safety clamp */
uint16_t rta_tf = params->rta_timeout_factor ? params->rta_timeout_factor : 100;
if (rta_tf > 100) rta_tf = 100;  /* IEC 61158-6 max */
```

**Key insight:** This was the first AlarmCR-related error (error_code_1 = 0x04),
proving the IOCR blocks were now fully accepted. The factor 200 was an oversight —
the comment said "20s" but `200 * 100ms = 20s` exceeds the spec limit.

---

### Bug #10: NDR Response Parser Format

**Symptom:** Controller logs `Connect response PNIO error: 0x46 0x00 0x00 0x00`
despite RTU showing success (`PNIOStatus = 0x00000000`).

**Root cause:** The response parser assumed a 24-byte NDR response header:
```
WRONG: ArgsMaximum(4) + ErrorStatus1(4) + ErrorStatus2(4) +
       MaxCount(4) + Offset(4) + ActualCount(4)
```

p-net actually sends a 20-byte header with PNIOStatus first:
```
CORRECT: PNIOStatus(4) + ArgsLength(4) +
         MaxCount(4) + Offset(4) + ActualCount(4)
```

The controller was reading `ArgsLength = 70 bytes = 0x46` and interpreting it as
`ErrorStatus1 = 0x46000000` — a false error.

**Discovery method:** Reading p-net source:
- `pf_cmrpc.c:1710-1744` — `pf_cmrpc_rm_connect_rsp()` writes PNIOStatus via
  `pf_put_pnet_status()`, then 4 NDR array fields
- `pf_block_writer.c:1418-1431` — `pf_put_pnet_status()` packs as:
  `error_code * 0x01000000 + error_decode * 0x10000 + error_code_1 * 0x100 + error_code_2`

**Fix (`profinet_rpc.c:933-991,1249-1272,2091-2117`):**

All three response parsers (Connect, Control/PrmEnd, Read) were updated:
```c
/* p-net NDR Response Header (20 bytes, all LE per DREP):
 *
 *   Offset  Field          Description
 *   ------  -------------- --------------------------
 *   +0      PNIOStatus     error_code<<24 | error_decode<<16
 *                          | error_code_1<<8 | error_code_2
 *   +4      ArgsLength     Byte count of PNIO payload
 *   +8      MaximumCount   NDR conformance (== ArgsLength)
 *   +12     Offset         Always 0
 *   +16     ActualCount    NDR actual (== ArgsLength)
 *
 * p-net writes PNIOStatus FIRST via pf_put_pnet_status().
 * There is no separate ArgsMaximum or ErrorStatus1/ErrorStatus2.
 */

/* 1. PNIOStatus (4 bytes LE) */
uint32_t pnio_status = buffer[pos] | (buffer[pos+1] << 8) |
                        (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
pos += 4;

if (pnio_status != 0) {
    uint8_t err_code   = (pnio_status >> 24) & 0xFF;
    uint8_t err_decode = (pnio_status >> 16) & 0xFF;
    uint8_t err_code1  = (pnio_status >> 8)  & 0xFF;
    uint8_t err_code2  = pnio_status & 0xFF;
    LOG_ERROR("PNIO error: 0x%02X 0x%02X 0x%02X 0x%02X",
              err_code, err_decode, err_code1, err_code2);
}
```

**Key insight:** This bug was invisible until bugs #1-#9 were fixed because the
RTU never responded before. Once the RTU sent a valid response, the parser
misinterpreted the success response as an error. Without reading the p-net source
(specifically `pf_cmrpc_rm_connect_rsp()`), this would have been extremely
difficult to diagnose — the RTU was saying "success" but the controller heard
"error 0x46."

---

## PNIO Error Code Reference

When p-net rejects a Connect request, it returns a 4-byte PNIOStatus:

```
Byte 0 (error_code):    0xDB = Connect, 0xDD = Control, 0xDE = Read
Byte 1 (error_decode):  0x80 = PNIORW, 0x81 = PNIO
Byte 2 (error_code_1):  Block type that failed:
                         0x02 = Faulty IOCR Block
                         0x04 = Faulty Alarm CR Block
                         0x05 = Faulty AR Block
Byte 3 (error_code_2):  Function-specific sub-error
```

To find the meaning of `error_code_2`, search p-net source:
```bash
grep -n 'pf_set_error.*error_code_1_value' pf_cmdev.c
```

Common error_code_2 values for IOCR (error_code_1 = 0x02):
- 0x18 (24): IOCR data descriptor overlap/straddle
- 0x1B (27): IOCR direction not found

Common error_code_2 values for AlarmCR (error_code_1 = 0x04):
- 0x07: Parameter out of range (rta_timeout_factor, rta_retries, etc.)

---

## Lessons Learned

### 1. p-net fails silently
Bugs #1-#6 all produced the same symptom: complete silence, 5-second timeout. No
error, no reject, no RST. p-net simply drops malformed packets before reaching
the block validation phase. Only after the packet structure is correct enough to
reach block parsing does p-net return meaningful error codes.

### 2. Trust the code, not the documentation
The IEC 61158-6 specification was invaluable for field layouts, but the p-net
source code was the ultimate authority. Several fixes were discovered only by
reading p-net's parser functions (e.g., `pf_cmdev_check_no_straddle()` for bug
#8, `pf_cmrpc_rm_connect_rsp()` for bug #10).

### 3. Debug p-net library on RTU is essential
Installing a debug-enabled libprofinet.so on the RTU (with `-DCMAKE_BUILD_TYPE=Debug`
and `-DLOG_LEVEL=3`) provided the RTU-side logs that confirmed bugs #7-#9.
Without these logs, the error codes would have been opaque.

### 4. Each fix reveals the next bug
The bugs cascaded — fixing the silent drops (#1-#6) revealed the IOCR errors
(#7-#8), fixing those revealed the AlarmCR error (#9), and fixing that revealed
the response parser error (#10). This is normal for implementing a complex
protocol from scratch.

### 5. NDR format differs between request and response
**Request:** ArgsMaximum + ArgsLength + MaxCount + Offset + ActualCount (20 bytes)
**Response:** PNIOStatus + ArgsLength + MaxCount + Offset + ActualCount (20 bytes)

Both are 20 bytes, but the first field is different. The request declares buffer
capacity (ArgsMaximum); the response carries the status (PNIOStatus). This
asymmetry caused bug #10.

### 6. IOPS bytes matter for frame offset calculation
Every IOData entry in an IOCR occupies `data_length + 1` bytes in the frame, even
if `data_length = 0` (NO_IO). The extra byte is the IOPS. The controller must
account for this when assigning frame offsets, or offsets overlap.

### 7. Activity UUID is a session identifier
DCE RPC uses the activity UUID to identify a session. All operations within a
PROFINET AR (Connect, PrmEnd, ApplicationReady, Release, Read) must use the SAME
activity UUID. Creating a new UUID per request exhausts p-net's session pool
(`PF_MAX_SESSION = 5`), and leaked sessions persist until the p-net process restarts.

### 8. Response block alignment differs from request
Bug #1 removed inter-block padding from requests. Bug #12 found the same issue in
the response parser — `align_to_4()` between parsed blocks skipped IOCRBlockRes.
Both sides must treat PNIO blocks as contiguous per IEC 61158-6-10.

### 9. CControl response is NOT a simple echo
The CControl response (ApplicationReady acknowledgment) requires:
- 20-byte NDR response header (not just raw block data)
- Block type 0x8112 (IOCControlRes), not 0x8110
- ControlCommand = DONE (0x0008), not echo of request command
- Interface UUID echoed from incoming request (not hardcoded)
- DREP-aware UUID field swapping when incoming DREP differs

### 10. VLAN tags are required for cyclic RT frames
PROFINET RT Class 1 frames must carry an 802.1Q VLAN tag with PCP=6 (priority
for real-time traffic). Both send (output) and receive (input) paths must handle
VLAN-tagged frames. The tag adds 4 bytes between SrcMAC and EtherType.

---

### Bug #11: Activity UUID Reuse
**Symptom:** PrmEnd gets "RPC CONTROL TIMEOUT". RTU logs: "Out of session resources for incoming frame."

**Root cause:** `rpc_build_control_request()`, `rpc_build_release_request()`, and `rpc_build_read_request()` each called `rpc_generate_uuid(ctx->activity_uuid)` to create a fresh activity UUID. In DCE RPC, all operations within an Application Relationship must use the **same** activity UUID established during Connect. p-net allocates session slots by activity UUID — a new UUID per request allocates a new session, quickly exhausting the pool (`PF_MAX_SESSION = 2*PNET_MAX_AR+1 = 5`).

**Fix (`profinet_rpc.c`, 3 locations):** Remove `rpc_generate_uuid()` calls from Control, Release, and Read request builders. Only Connect generates a new activity UUID.

---

### Bug #12: Connect Response Block Alignment
**Symptom:** Output frames sent with FrameID 0xFFFF instead of device-assigned 0xC000.

**Root cause:** The Connect response parser had `align_to_4(&pos)` between blocks. p-net writes response blocks contiguously with NO padding. After the 34-byte ARBlockRes, `align_to_4(134)` → 136, skipping 2 bytes into the IOCRBlockRes. This triggered "Block extends past buffer end", breaking out of the parse loop before IOCRBlockRes (containing FrameID 0xC000) was parsed.

**Fix (`profinet_rpc.c:1159`):** Remove `align_to_4(&pos)` from the response block parser. Same principle as Bug #1 (request-side), but this time on the response side.

---

### Bug #13: ModuleDiffBlock Retry Logic
**Symptom:** Connect succeeds but controller retries 3 times, then gives up.

**Root cause:** With Bug #12 fixed, the Connect response parser now correctly finds the ModuleDiffBlock. DAP subslots (slot 0, subslots 0x8000/0x8001) always report as "substitute" because our expected idents differ from the device's configured idents. The old code treated ALL diffs as errors requiring retry. But DAP-only diffs are informational — the device accepts the connection regardless.

**Fix (`ar_manager.c:982-1020`):** Check if diffs are DAP-only (all slots == 0). If so, log and proceed to PrmEnd. Only retry for application module diffs (slot > 0).

---

### Bug #14: CControl Response Format
**Symptom:** RTU logs "Unknown incoming activity UUID" and ApplicationReady times out.

**Root cause:** The CControl response (ApplicationReady acknowledgment) had multiple issues:
1. Missing 20-byte NDR response header between RPC header and PNIO block
2. Block type hardcoded to IODControlRes (0x8110) instead of IOCControlRes (0x8112)
3. ControlCommand echoed from request instead of using DONE (0x0008)
4. Interface UUID hardcoded instead of echoed from incoming request
5. DREP mismatch: if incoming request used different DREP, UUID fields needed swapping

**Fix (`profinet_rpc.c:1988-2061`):** Complete rewrite of `rpc_build_control_response()`:
- Add 20-byte NDR response header
- Use correct block type (0x8112 for CControl, 0x8110 for DControl)
- ControlCommand = DONE (0x0008) in response
- Echo interface_uuid and activity_uuid from incoming request
- DREP-aware UUID field swapping

---

### Bug #15: ControlCommand Bitfield Values
**Symptom:** Release command sent with value 0x0003 instead of 0x0004.

**Root cause:** ControlCommand constants were defined as sequential enum values (1,2,3,4,5,6) instead of the IEC 61158-6-10 Table 777 bitfield values (0x0001, 0x0002, 0x0004, 0x0008, 0x0010, 0x0020, 0x0040).

**Fix (`profinet_rpc.h:131-137`):** Correct all ControlCommand defines to bitfield values.

---

### Bug #16: VLAN Tag on Output Frames
**Symptom:** p-net CPM rejects output frames; no CPM state transition.

**Root cause:** Output frames were built as `[DstMAC][SrcMAC][0x8892][FrameID]...` (untagged). p-net's CPM expects VLAN-tagged frames because the IOCR negotiation specifies `TagHeader = 0xC000` (PCP=6, VLAN priority for RT Class 1).

**Fix (`ar_manager.c:134-141`):** Insert 4-byte 802.1Q VLAN tag between SrcMAC and EtherType:
```
[DstMAC 6][SrcMAC 6][0x8100 2][0xC000 2][0x8892 2][FrameID 2][C-SDU...][CycleCounter 2][DataStatus 1][TransferStatus 1]
```

---

### Bug #17: DataStatus + VLAN Receive Offset
**Symptom:** DataStatus 0x15 missing StationProblemIndicator; input frame parser at wrong offset.

**Root cause (DataStatus):** DataStatus byte was `STATE|VALID|RUN = 0x01|0x04|0x10 = 0x15`. Missing bit 5 `STATION_PROBLEM_NORMAL` (0x20). Without this bit, p-net interprets a station problem.

**Root cause (receive offset):** `ar_handle_rt_frame()` used hardcoded `ETH_HEADER_LEN` (14) to find FrameID. p-net sends VLAN-tagged PPM frames, so FrameID is at offset 18, not 14.

**Fix (`ar_manager.c`):**
- DataStatus: Add `PROFINET_DATA_STATUS_STATION_PROBLEM` (0x20) → 0x35
- Receive: Detect VLAN tag (EtherType 0x8100 at offset 12) and adjust offset to 18

---

## Current Status (2026-02-10)

| Operation | Status | Notes |
|-----------|--------|-------|
| DCP Discovery | ✅ Working | Always worked |
| RPC Connect (DAP-only) | ✅ Working | Bugs #1-#10 |
| RPC PrmEnd | ✅ Working | Bug #10-#11 |
| ApplicationReady | ✅ Working | Bugs #12-#15 (CControl response) |
| Cyclic Output (FrameID 0xC000) | ✅ Working | Bugs #12, #16-#17 (VLAN, DataStatus) |
| Cyclic Input (FrameID 0xC001) | ✅ Working | Bug #17 (VLAN offset) |
| p-net DATA state | ✅ Stable | CMDEV WDATA→DATA, no timeouts |

### Per-IOCR Send Timing

The controller's main loop runs at 1000ms (configurable via `-t` flag), but
PROFINET cyclic period is 256ms (`SCF=64 × RR=128 × 31.25µs`). Rather than
changing the global cycle time (which affects Modbus, alarms, etc.), the output
send function checks per-IOCR timing: only send when `now - last_frame_time_us >= period_us`.

With CONSERVATIVE profile: watchdog_factor=10 → 2.56s, data_hold_factor=5 → 1.28s.
The 1000ms controller cycle fits within both thresholds.

### Next Steps

1. **Full Connect with application modules** — Include discovered slot modules
   (not just DAP) in ExpectedSubmoduleBlockReq
2. **Process I/O data** — Map cyclic frame data to SCADA process variables
3. **Handle connection loss/recovery** — Detect CPM timeout, re-establish AR

---

## File Reference

| File | Role |
|------|------|
| `src/profinet/profinet_rpc.c` | RPC packet construction + response parsing |
| `src/profinet/profinet_rpc.h` | Block types, control commands, data structures |
| `src/profinet/rpc_strategy.c` | Timing profiles + UUID swap utility |
| `src/profinet/ar_manager.c` | AR lifecycle, cyclic frame send/receive |
| `src/profinet/ar_manager.h` | AR manager interface |
| `src/profinet/profinet_controller.c` | Main controller, RT frame recv thread |
| `src/profinet/profinet_controller.h` | IOCR struct (frame_id, timing fields) |
| `src/profinet/profinet_frame.h` | RPC header struct definition (80 bytes) |
| `shared/include/profinet_identity.h` | Record indices, module discovery types |

### p-net Source Reference (READ ONLY — on RTU)

| File | Key Functions |
|------|--------------|
| `pf_cmrpc.c` | Connect request parser, response builder |
| `pf_cmdev.c` | IOCR validation, AlarmCR validation, error codes |
| `pf_block_reader.c` | Block field parsers |
| `pf_block_writer.c` | `pf_put_pnet_status()` — PNIOStatus encoding |
| `pnet_api.h` | Error code constants |
