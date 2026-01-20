# RTU Add Protocol Analysis

## Overview

This document captures the audit findings for the "Add RTU to Controller" flow, identifying
assumptions made by the Controller side that require coordination with the RTU team.

## Data Flow Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        RTU ADD FLOW                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [Web API]                                                                   │
│      │                                                                       │
│      ▼                                                                       │
│  POST /api/v1/rtus                                                          │
│      │ RtuCreate: station_name, ip_address, vendor_id, device_id, slot_count│
│      ▼                                                                       │
│  [RtuService.create()]                                                       │
│      │ Creates RTU record in PostgreSQL (state=OFFLINE)                     │
│      ▼                                                                       │
│  [ShmClient.add_rtu()]                                                       │
│      │ SHM_CMD_ADD_RTU via shared memory IPC                                │
│      ▼                                                                       │
│  [C Controller - ipc_server.c:handle_rtu_command()]                         │
│      │ SHM_CMD_ADD_RTU handler                                              │
│      ▼                                                                       │
│  [rtu_registry_add_device()]                                                │
│      │ Creates rtu_device_t struct, state=PROFINET_STATE_OFFLINE            │
│      ▼                                                                       │
│  (Optional) User triggers connect                                            │
│      │                                                                       │
│      ▼                                                                       │
│  [profinet_controller_connect()]                                            │
│      │ 1. Lookup device in DCP cache by station_name                        │
│      │ 2. If not found, discovery must have been run first                  │
│      │ 3. Create AR config from DCP device_info + slot_config               │
│      │ 4. Call ar_manager_create_ar()                                       │
│      │ 5. Call ar_send_connect_request()                                    │
│      ▼                                                                       │
│  [RTU: PROFINET Device Stack]                                               │
│      │ Receives Connect Request, negotiates AR                               │
│      │ Transitions through PROFINET state machine                           │
│      ▼                                                                       │
│  [AR_STATE_RUN]                                                              │
│      │ Cyclic I/O exchange begins                                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Files Audited

| File | Purpose |
|------|---------|
| `web/api/app/services/rtu_service.py:55-92` | RtuService.create() - DB record creation |
| `web/api/shm_client.py:603-616` | add_rtu() IPC command |
| `src/ipc/ipc_server.c:376-387` | SHM_CMD_ADD_RTU handler |
| `src/registry/rtu_registry.c:96-190` | rtu_registry_add_device() |
| `src/profinet/profinet_controller.c:498-569` | profinet_controller_connect() |
| `src/profinet/dcp_discovery.c` | DCP multicast discovery |
| `src/types.h:311-347` | rtu_device_t structure |

---

## Questions for RTU Team

### 1. Station Name Requirements

**Assumption**: The Controller uses the `station_name` as the primary identifier for DCP discovery and PROFINET AR establishment.

```c
// From profinet_controller.c:521-527
for (int i = 0; i < device_count; i++) {
    if (strcmp(devices[i].station_name, station_name) == 0) {
        device = &devices[i];
        break;
    }
}
```

**Questions**:
- What is the maximum station name length supported by the RTU? (Controller uses 64 chars: `WTC_MAX_STATION_NAME`)
- Are station names case-sensitive? (Controller uses `strcmp`, case-sensitive)
- What characters are valid in station names? (PROFINET spec allows `a-z`, `0-9`, `-`, length 1-63)
- Is the station name configurable on the RTU, or is it factory-set?
- How does the RTU respond if its station name doesn't match the requested name?

---

### 2. DCP Discovery Response Format

**Assumption**: The Controller expects these DCP response blocks from the RTU:

```c
// From dcp_discovery.c:150-195 - Expected DCP blocks
DCP_OPTION_IP:
    - DCP_SUBOPTION_IP_PARAMETER: IP, subnet mask, gateway (12 bytes after block info)
    - DCP_SUBOPTION_IP_MAC: MAC address

DCP_OPTION_DEVICE:
    - DCP_SUBOPTION_DEVICE_VENDOR: Vendor name string
    - DCP_SUBOPTION_DEVICE_NAME: Station name string
    - DCP_SUBOPTION_DEVICE_ID: vendor_id (2 bytes) + device_id (2 bytes)
    - DCP_SUBOPTION_DEVICE_ROLE: device role (2 bytes)
```

**Questions**:
- Does the RTU respond to DCP Identify All (multicast)?
- Does the RTU respond to DCP Identify by Station Name?
- What vendor_id and device_id values does the RTU report?
- Is the RTU's IP address configurable via DCP Set? Should it be?

---

### 3. Vendor ID and Device ID Coordination

**Assumption**: The Controller passes vendor_id and device_id from the API, but these must match what the RTU actually reports in DCP.

```python
# From shm_client.py:603-606
def add_rtu(self, station_name: str, ip_address: str,
            vendor_id: int = 0x0493, device_id: int = 0x0001,
            slot_count: int = 16) -> bool:
```

**Questions**:
- What vendor_id is assigned to the Water-Treat RTU? (Default suggests 0x0493)
- What device_id is assigned? (Default suggests 0x0001)
- Are these registered with PROFINET International?
- Should the Controller validate these against DCP response?

---

### 4. PROFINET Connection Sequence

**Assumption**: The Controller initiates AR establishment as follows:

```c
// From profinet_controller.c:551-561
// Create AR configuration
ar_config_t ar_config;
memset(&ar_config, 0, sizeof(ar_config));
strncpy(ar_config.station_name, station_name, ...);
memcpy(ar_config.device_mac, device->mac_address, 6);
ar_config.device_ip = device->ip_address;
ar_config.vendor_id = device->vendor_id;
ar_config.device_id = device->device_id;

memcpy(ar_config.slots, slots, slot_count * sizeof(slot_config_t));
ar_config.slot_count = slot_count;

ar_config.cycle_time_us = controller->config.cycle_time_us;  // Default 1ms
ar_config.watchdog_ms = 3000;  // 3 second watchdog

// Create AR and send connect request
ar_manager_create_ar(controller->ar_manager, &ar_config, &ar);
ar_send_connect_request(controller->ar_manager, ar);
```

**Questions**:
- What cycle time does the RTU support? (Controller defaults to 1ms)
- What is the RTU's minimum supported reduction ratio?
- Does the RTU support the 3-second watchdog interval?
- What Application Relationships (AR) types does the RTU support?
  - AR_TYPE_IOCAR (0x0001)?
  - AR_TYPE_SINGLE (0x0010)?
- What is the maximum number of simultaneous ARs the RTU supports?

---

### 5. Slot Configuration

**Assumption**: The Controller expects to configure slots at connection time:

```c
// From types.h:79-83
typedef enum {
    SLOT_TYPE_DAP = 0,    // Device Access Point (slot 0)
    SLOT_TYPE_SENSOR,     // Input data
    SLOT_TYPE_ACTUATOR,   // Output data
} slot_type_t;

// From profinet_controller.c:638-648 - 5-byte sensor format
// Slot index is 0-based; RTU dictates slot configuration
// Calculate offset for slot - 5 bytes per sensor slot
size_t offset = (slot - 1) * 5;
```

**Questions**:
- How many slots does the RTU support? (Reference mentions 1-8 input, 9-15 output)
- Is slot 0 reserved for DAP (Device Access Point)?
- What is the expected module/submodule configuration for each slot?
- Do sensor slots use the 5-byte format (Float32 BE + Quality byte)?
- What is the output data size per actuator slot? (Controller assumes 4 bytes)

---

### 6. GSDML File Requirements

**Assumption**: PROFINET connection requires a matching GSDML device description.

**Questions**:
- Where is the RTU's GSDML file located?
- What version of GSDML is used?
- Are there any vendor-specific extensions?
- How are module/submodule plugging rules defined?
- Is the GSDML shipped with the RTU firmware or separately?

---

### 7. IP Address Assignment

**Assumption**: The Controller expects the RTU to have a reachable IP address at connection time.

```python
# From rtu_service.py:65-67
existing_ip = self.db.query(RTU).filter(RTU.ip_address == request.ip_address).first()
if existing_ip:
    raise RtuAlreadyExistsError("ip_address", request.ip_address)
```

**Questions**:
- Does the RTU use static IP or DHCP?
- Can the Controller assign IP via DCP Set?
- What is the expected IP address range? (192.168.1.x? 10.x.x.x?)
- How should IP conflicts be handled?

---

### 8. Error Handling and Diagnostics

**Assumption**: The Controller tracks connection state through `profinet_state_t`:

```c
// From types.h:68-76
typedef enum {
    PROFINET_STATE_OFFLINE = 0,
    PROFINET_STATE_DISCOVERY,
    PROFINET_STATE_CONNECTING,
    PROFINET_STATE_CONNECTED,
    PROFINET_STATE_RUNNING,
    PROFINET_STATE_ERROR,
    PROFINET_STATE_DISCONNECT,
} profinet_state_t;
```

**Questions**:
- How does the RTU signal connection failures?
- What diagnostic data is available via record read (index 0xF80x)?
- How is the RTU's LED behavior during connection states?
- What PROFINET alarms/diagnostics does the RTU generate?

---

### 9. Authority Handoff Protocol

**Assumption**: The Controller implements an authority handoff protocol:

```c
// From types.h:231-248
typedef enum {
    AUTHORITY_AUTONOMOUS = 0,    // RTU is operating independently
    AUTHORITY_HANDOFF_PENDING,   // Controller requesting authority transfer
    AUTHORITY_SUPERVISED,        // Controller has authority
    AUTHORITY_RELEASING,         // Controller releasing authority
} authority_state_t;
```

**Questions**:
- Does the RTU implement the authority handoff protocol?
- What is the RTU's default behavior when Controller disconnects?
- How are stale commands rejected? (epoch-based? timestamp-based?)
- Is there a safe-state fallback when authority is unclear?

---

### 10. I/O Data Format

**Assumption**: The Controller uses these I/O data formats:

**Sensor Input (5-byte format)**:
```
Bytes 0-3: Float32 value (big-endian)
Byte 4:    Quality indicator (OPC UA compatible)
           0x00 = Good
           0x40 = Uncertain
           0x80 = Bad
           0xC0 = Not Connected
```

**Actuator Output (4-byte format)**:
```
Byte 0: Command (0=OFF, 1=ON, 2=PWM)
Byte 1: PWM duty cycle (0-255)
Bytes 2-3: Reserved
```

**Questions**:
- Does the RTU use big-endian or little-endian for Float32?
- Are the quality codes aligned with OPC UA?
- What PWM resolution does the RTU support?
- Are there any additional status bytes in the I/O frame?

---

## Integration Checklist

Before connecting a Water-Treat RTU to the Controller, verify:

- [ ] Station name is configured and matches expected format
- [ ] IP address is assigned and reachable
- [ ] DCP discovery returns expected device info
- [ ] vendor_id and device_id match GSDML
- [ ] GSDML is installed on Controller
- [ ] Slot configuration matches RTU modules
- [ ] Cycle time is compatible (default 1ms)
- [ ] Authority handoff behavior is understood
- [ ] User sync record handler is registered (index 0xF840)

---

## Simulated RTU Team Communication

### Email: Questions about RTU PROFINET Configuration

To: rtu-team@water-treat.local
Subject: [Integration] Controller ↔ RTU Connection Protocol Questions

RTU Team,

I've completed the audit of the "Add RTU" code flow on the Controller side. We need to
coordinate on several PROFINET protocol details before integration testing.

**Critical Items**:

1. **Station Name Format**: What format should we use for station names? The Controller
   uses case-sensitive comparison (strcmp). Recommend we agree on lowercase-only with
   hyphens, e.g., `water-treat-rtu-01`.

2. **Vendor/Device ID**: The Controller defaults to vendor_id=0x0493, device_id=0x0001.
   Please confirm these values match the RTU's DCP response and GSDML.

3. **Slot Layout**: The Controller assumes:
   - Slot 0: DAP
   - Slots 1-8: Sensors (5-byte format each: Float32 BE + Quality)
   - Slots 9-15: Actuators (4-byte format each)

   Please confirm this matches the RTU's module configuration.

4. **Cycle Time**: Default is 1ms (1000µs). What's the RTU's minimum supported cycle time?

5. **Authority Handoff**: The Controller implements AUTHORITY_AUTONOMOUS → AUTHORITY_SUPERVISED
   state transitions. Does the RTU firmware have matching logic?

**Action Requested**:
Please review and respond with either confirmations or corrections. Once aligned, I'll
create a test vector document similar to what we did for user sync.

Regards,
Controller Team

---

*Document generated by RTU Add Protocol audit*
