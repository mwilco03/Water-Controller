# PROFINET Controller Exhaustive Code Audit

**Date:** 2026-02-03
**Scope:** Full audit of PROFINET controller, AR manager, RTU registry, IPC shared memory, and dead code
**Severity Scale:** CRITICAL > HIGH > MEDIUM > LOW

---

## Executive Summary

Seven areas were audited. **3 critical bugs**, **2 high-severity issues**, and **2 medium findings** were identified:

| # | Area | Severity | Summary |
|---|------|----------|---------|
| 1 | Connection flow | OK | `ar_connect_with_discovery()` correctly discovers real module layout; no silent fallback to default slots |
| 2 | Input/output offsets | **CRITICAL** | `read_input()` and `write_output()` use hardcoded arithmetic; recv thread uses proper running offsets |
| 3 | Lock contention | **CRITICAL** | `read_record()` and `write_record()` hold `ctrl->lock` during 5-second blocking RPC calls |
| 4 | RTU registry thread safety | **CRITICAL** | `get_device()` returns raw pointer after releasing lock — use-after-free race |
| 5 | IPC shared memory | OK | Field layout matches between C and Python ctypes; command sequence protocol is sound |
| 6 | Module discovery wiring | **HIGH** | Three discovery paths exist; only PROFINET Record Read actually produces correct slot_info |
| 7 | Dead code | **HIGH** | `slot_manager.c` is fully dead; 5 coordination modules compiled but never initialized |

---

## 1. PROFINET Controller Connection Flow

**Files:** `src/profinet/profinet_controller.c:756-943`, `src/profinet/ar_manager.c:1388-1510`

### Verdict: OK — Discovery pipeline is correctly implemented

When `profinet_controller_connect()` is called with NULL slots (the auto-connect path from DCP discovery), it:

1. Builds a default 15-slot config (8 input, 7 output) as a template
2. Detects that these are defaults (`slots == default_slots`)
3. Calls `ar_connect_with_discovery()` instead of `ar_send_connect_request()`

`ar_connect_with_discovery()` implements a 6-phase pipeline:

| Phase | Action | Fallback |
|-------|--------|----------|
| 1 | GSDML cache lookup | Skip to Phase 2 |
| 2 | DAP-only RPC connect | HTTP `/slots` fallback |
| 3 | Record Read 0xF844 (real identification) | Fatal error |
| 4 | Full connect with discovered modules | Fatal error |
| 5 | Background GSDML fetch for cache | Non-fatal |
| 6 | HTTP fallback (if Phase 2 failed) | Fatal error |

**If discovery fails, connection fails.** There is no silent fallback to the default 15 slots. This is correct behavior per CLAUDE.md: "Return HTTP 503/501 when systems unavailable—never fake data."

The discovered modules are stored into `ar->slot_info[]` via `ar_build_full_connect_params()` (`ar_manager.c:1348-1380`), which maps GSDML module identifiers to measurement/actuator types.

---

## 2. Input/Output Offset Calculation

**Files:** `src/profinet/profinet_controller.c:982-1069`

### Verdict: CRITICAL — Hardcoded offsets disagree with recv thread's running offsets

#### The Problem

**`profinet_controller_read_input()`** at line 1012:
```c
size_t offset = (slot - 1) * 5;  /* 5 bytes per sensor slot */
```

**`profinet_controller_write_output()`** at line 1058:
```c
size_t offset = slot * 4;  /* 4 bytes per actuator slot */
```

Both functions assume:
- All slots are contiguous (no gaps)
- All input slots are exactly 5 bytes
- All output slots are exactly 4 bytes
- Input slots are 1-indexed, output slots are 0-indexed

**The receive thread** at `profinet_controller.c:362-386` uses a **correct running offset**:
```c
uint16_t offset = 0;
for (int s = 0; s < ar->slot_count; s++) {
    if (ar->slot_info[s].type == SLOT_TYPE_SENSOR) {
        /* callback at data_buffer + offset */
        offset += GSDML_INPUT_DATA_SIZE;
    }
}
```

This iterates `ar->slot_info[]`, accumulates offset only for SENSOR-type slots, and correctly skips non-sensor slots. If an RTU has non-contiguous slots or mixed types, the recv thread gets the right data while `read_input()` reads wrong buffer positions.

#### Impact

- If RTU slots are `[1: sensor, 2: actuator, 3: sensor]`, the recv thread correctly maps slot 3 at offset 5 (one sensor before it). But `read_input(slot=3)` calculates offset `(3-1)*5 = 10`, reading garbage.
- `write_output()` uses 0-based indexing while `read_input()` uses 1-based — inconsistent API.

#### Fix Required

Both functions must iterate `ar->slot_info[]` with a running offset to find the correct buffer position for the requested slot number, matching the recv thread's logic.

---

## 3. Lock Contention in read_record / write_record

**Files:** `src/profinet/profinet_controller.c:1227-1395`

### Verdict: CRITICAL — Lock held during 5-second blocking RPC call

#### The Problem

**`profinet_controller_read_record()`** (lines 1239-1276):
```c
pthread_mutex_lock(&controller->lock);          // Line 1239: LOCK ACQUIRED

/* ... build request ... */

result = send_rpc_request(controller->rpc_socket, ar->device_ip,
                           request, req_len, response, &resp_len);
                                                 // Lines 1273-1274: BLOCKING CALL (up to 5s)

pthread_mutex_unlock(&controller->lock);         // Line 1276: LOCK RELEASED
```

**`profinet_controller_write_record()`** (lines 1336-1373): Same pattern — lock held from line 1336 through `send_rpc_request()` at lines 1370-1371 until line 1373.

**`send_rpc_request()`** (lines 1180-1225) blocks via `poll()` with `RPC_TIMEOUT_MS = 5000` (5 seconds).

#### Impact

- `controller->lock` is the single mutex protecting ALL controller state
- While one thread blocks in `read_record()` for up to 5 seconds, ALL other operations are starved:
  - The cyclic receive thread cannot process incoming frames (held at `profinet_controller.c:393`)
  - `read_input()` and `write_output()` are blocked
  - Other `read_record()`/`write_record()` calls to different RTUs are blocked
- This causes cyclic watchdog timeouts (3 seconds default) on ALL connected RTUs, not just the target

#### Fix Required

Copy AR fields (ar_uuid, session_key, device_ip) under lock, release lock, perform blocking RPC without lock, re-acquire lock to update state if needed.

---

## 4. RTU Registry Thread Safety

**Files:** `src/registry/rtu_registry.c:228-262`

### Verdict: CRITICAL — Use-after-free race condition

#### The Problem

**`rtu_registry_get_device()`** (lines 228-243):
```c
pthread_mutex_lock(&registry->lock);
for (int i = 0; i < registry->device_count; i++) {
    if (strcmp(registry->devices[i]->station_name, station_name) == 0) {
        pthread_mutex_unlock(&registry->lock);   // LOCK RELEASED
        return registry->devices[i];              // RAW POINTER RETURNED
    }
}
pthread_mutex_unlock(&registry->lock);
return NULL;
```

**`rtu_registry_get_device_by_index()`** (lines 245-262): Same pattern — lock released before returning raw pointer.

#### Race Condition Sequence

```
Thread A                              Thread B
  get_device("rtu-01")
    lock()
    find devices[5]
    unlock()
                                        remove_device("rtu-01")
                                          lock()
                                          free(devices[5])
                                          shift array, count--
                                          unlock()
    return devices[5]  → DANGLING
  device->connection_state = ...  → USE AFTER FREE
```

#### Affected Call Sites

All functions that call `get_device()` and then access the returned pointer are vulnerable:
- `rtu_registry_set_device_state()` (line 426)
- `rtu_registry_update_sensor()` (line 456)
- `rtu_registry_update_actuator()` (line 485)
- `rtu_registry_get_sensor()` (line 509)
- `rtu_registry_get_actuator()` (line 538)

#### Safe Pattern Already Exists

`rtu_registry_list_devices()` (lines 264-342) correctly performs a **deep copy while holding the lock**, including dynamic arrays (slots, sensors, actuators). This pattern should be extended to the single-device getters.

#### Fix Options

1. **Deep copy**: Return a copy of the device struct (caller frees)
2. **Reference counting**: Add refcount to `rtu_device_t`, increment under lock, caller decrements when done
3. **Lock-holding API**: Provide `rtu_registry_lock_device()` / `rtu_registry_unlock_device()` that keeps the lock held while the caller operates on the pointer

---

## 5. IPC Shared Memory Wiring

**Files:** `src/ipc/ipc_server.c:198-251`, `src/ipc/ipc_server.h`, `web/api/shm_client.py`

### Verdict: OK — Struct layout matches; command protocol is sound

#### Data Flow: C → Shared Memory → Python

`update_rtu_data()` maps registry data into shared memory:
- Uses `rtu_registry_list_devices()` (deep copy — safe)
- Maps fields 1:1: station_name, ip_address, vendor_id, device_id, connection_state, slot_count
- Sensor data: value (float), status (int), quality (uint8), timestamp_ms (uint64)
- Actuator data: command (uint8), pwm_duty (uint8), forced (bool)

#### Struct Alignment

C `shm_rtu_t` fields match Python `ShmRtu` ctypes structure field-by-field:
- `station_name`: char[64] ↔ c_char * 64
- `ip_address`: char[16] ↔ c_char * 16
- `vendor_id`: uint16_t ↔ c_uint16
- `sensors[32]`: struct{int,float,int,uint8,uint64} ↔ ShmSensor * 32
- `actuators[32]`: struct{int,uint8,uint8,bool} ↔ ShmActuator * 32

Both sides log their computed offsets at startup for verification:
- C: `LOG_INFO("SHM size=%zu, command offset=%zu, command_sequence offset=%zu", ...)` (`ipc_server.c:113-116`)
- Python: `logger.info(f"Python SHM struct: size={_py_shm_size}, ...")` (`shm_client.py:452-472`)

#### Command Sequence Protocol

1. Python increments `_command_seq`, writes command struct, sets `shm->command_sequence`
2. C detects `command_sequence != last_command_seq`, dispatches command
3. C sets `command_ack = command_sequence`, clears `command_type`

This is a standard single-producer single-consumer sequence protocol. The C side holds `shm->lock` (pthread_mutex_t) during command processing. The Python side uses `SHM_COMMAND_OFFSET_OVERRIDE` if ctypes alignment differs from C's `offsetof()`.

---

## 6. Controller-to-RTU Module Discovery Wiring

**Files:** `src/profinet/ar_manager.c:1224-1510`

### Verdict: HIGH — Three discovery paths with unclear precedence

#### The Three Paths

| Path | Source | Produces correct slot_info? |
|------|--------|---------------------------|
| PROFINET Record Read 0xF844 | `ar_read_real_identification()` | **YES** — reads actual module identifiers from device |
| HTTP POST /api/v1/rtu/register | RTU self-registration (sensor_count, actuator_count) | **PARTIAL** — provides counts but not module identifiers |
| Default slot assumption | `profinet_controller_connect()` default_slots | **NO** — overridden by discovery pipeline |

The PROFINET Record Read path is the one that actually works. It:
1. Sends RPC Record Read request with index 0xF844 (RealIdentificationData)
2. Parses response into `ar_discovered_module_t` array (module_ident, slot, subslot)
3. Maps module identifiers to measurement/actuator types via `ar_build_full_connect_params()`

#### Issue: HTTP Registration Path

When an RTU registers via HTTP (`POST /api/v1/rtu/register`), it provides `sensor_count` and `actuator_count`. These counts create registry entries but do NOT provide GSDML module identifiers. The registry device's `slot_config_t` entries may differ from the AR's `slot_info[]` entries that come from PROFINET discovery.

This means:
- Registry says "RTU has 5 sensors and 3 actuators"
- AR slot_info says "slot 1 = pH, slot 2 = TDS, slot 3 = temperature, ..."
- If the HTTP registration count doesn't match the PROFINET discovery count, the cyclic data callback (`on_data_received`) may update sensor indices that don't align with the registry's sensor array

#### Cyclic Data Mapping

After connection, the recv thread callback at `profinet_controller.c:362-386` invokes `on_data_received(station_name, slot_number, data, len, ctx)`. The callback handler (in main.c) must correctly map `slot_number` to the registry's `sensor_data_t[index]`. If the slot numbering from PROFINET doesn't match the registry's sensor array indexing, values end up in wrong slots.

---

## 7. Dead Code and Stubs

**Files:** Multiple

### Verdict: HIGH — Compiled dead code violates project rules

#### 7a. `slot_manager.c` — FULLY DEAD

**File:** `src/registry/slot_manager.c` (170 lines, 6672 bytes)
**Status:** Compiled via CMakeLists.txt (line 129) but **zero references anywhere in the codebase**

Contains:
- `create_sensor_slot_config()`
- `create_actuator_slot_config()`
- `create_water_treatment_rtu_config()`
- `get_measurement_info()`

No header file exists (no `.h` counterpart). No other file includes or calls any of these functions. This is dead weight that was never integrated.

#### 7b. `rpc_strategy.c` — Passively Referenced

**File:** `src/profinet/rpc_strategy.c` (50 lines, 2761 bytes)
**Status:** Compiled, referenced by `ar_manager.c`

Contains timing profile definitions (`DEFAULT`, `AGGRESSIVE`, `CONSERVATIVE`) for RPC operations. This is a legitimate utility module.

#### 7c. Coordination Modules — Compiled, Never Initialized

Five coordination modules are compiled and linked but **never called from `main.c`**:

| Module | File | Lines | Integrated in main.c? |
|--------|------|-------|----------------------|
| `coordination.c` | `src/coordination/coordination.c` | 191 | **NO** |
| `authority_manager.c` | `src/coordination/authority_manager.c` | 478 | **NO** |
| `cascade_control.c` | `src/coordination/cascade_control.c` | 225 | **NO** |
| `load_balance.c` | `src/coordination/load_balance.c` | 310 | **NO** |
| `state_reconciliation.c` | `src/coordination/state_reconciliation.c` | 611 | **NO** |
| `failover.c` | `src/coordination/failover.c` | 359 | **YES** |

Only `failover.c` is properly integrated into `main.c` startup (init at line 710, start at line 786, process in main loop).

The other 5 modules total **1,815 lines** of compiled but unreachable code. `coordination.c` has a `coordination_init()` function that would aggregate the sub-modules, but it is never called.

#### 7d. TODO/FIXME/Stub Search

- **C code**: Zero TODO or FIXME comments found in any `.c` file
- **Python code**: Zero bare `pass` stubs or `raise NotImplementedError` in production code
- `scripts/validate_integration.py:38` has `raise NotImplementedError` in a base class — this is correct abstract base class usage

---

## 8. Additional Finding: ar_manager_process() Data Race

**File:** `src/profinet/ar_manager.c:510-599`

### Severity: HIGH

`ar_manager_process()` iterates the AR array without holding any lock:

```c
for (int i = 0; i < manager->ar_count; i++) {
    profinet_ar_t *ar = manager->ars[i];
    if (!ar || ar->connecting) continue;
    /* ... state machine processing ... */
}
```

Concurrently, `ar_manager_delete_ar()` (lines 354-382) holds the lock and can:
- Modify `manager->ar_count`
- Shift `manager->ars[]` entries
- Free AR structures

This creates a use-after-free if an AR is deleted while `ar_manager_process()` is iterating.

Additionally, `ar->connecting` is read without a memory barrier or lock, risking torn reads on some architectures.

---

## Summary of Required Fixes

### Critical (Must Fix)

1. **Offset calculation** (`profinet_controller.c:1012,1058`): Replace hardcoded `(slot-1)*5` and `slot*4` with running offset iteration over `ar->slot_info[]`, matching the recv thread logic
2. **Lock contention** (`profinet_controller.c:1239-1276, 1336-1373`): Copy AR fields under lock, release, do blocking RPC, re-acquire to update state
3. **Registry use-after-free** (`rtu_registry.c:228-262`): Return deep copies or implement reference counting for `get_device()` / `get_device_by_index()`

### High (Should Fix)

4. **ar_manager_process() race** (`ar_manager.c:510-599`): Hold lock during AR array iteration or use RCU
5. **Dead code removal**: Delete `slot_manager.c` from CMakeLists.txt; decide on coordination modules (integrate or remove)
6. **Discovery path alignment**: Ensure HTTP registration counts match PROFINET-discovered module layout

### Medium (Should Address)

7. **Inconsistent slot indexing**: `read_input()` uses 1-based slots, `write_output()` uses 0-based — standardize
8. **ar_build_full_connect_params() unsynchronized**: Writes to `ar->slot_info[]` without holding manager lock while other threads may read it
