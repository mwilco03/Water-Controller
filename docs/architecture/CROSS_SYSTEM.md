<!--
  DOCUMENT CLASS: Architecture (Stable Reference)

  This document defines the CONTRACT between Water-Controller and Water-Treat.
  Changes here require coordinated updates to BOTH repositories.

  Before editing: Ensure both teams are aware of proposed changes.
-->

# Cross-System Development Guidelines Addendum

## PROFINET Data Exchange Standards

**Document ID:** WT-GUIDE-002  
**Applies To:** Water-Treat (RTU), Water-Controller  
**Authority:** WT-SPEC-001 (PROFINET Data Format Specification)  

---

## Preamble

This addendum establishes enforceable cross-system standards for PROFINET data exchange between Water-Treat RTU and Water-Controller. These guidelines supplement the system-specific DEVELOPMENT_GUIDELINES.md in each repository.

**Core Principle:** The two codebases are coupled at the wire protocol level. Changes to data format, byte ordering, or quality semantics in one system REQUIRE coordinated changes in the other. Unilateral changes will cause silent data corruption.

---

## Part 1: Normative Requirements

### 1.1 Sensor Data Format (RTU → Controller)

Per [WT-SPEC-001] Section 5.1, sensor data SHALL be 5 bytes:

```
┌─────────────────────────────────────────────────────────────────┐
│  CANONICAL SENSOR DATA FORMAT                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Offset  │ Size │ Content              │ Encoding               │
│  ────────┼──────┼──────────────────────┼──────────────────────  │
│  0       │ 4    │ Sensor Value         │ IEEE 754 Float32       │
│          │      │                      │ Big-endian (network)   │
│  4       │ 1    │ Quality Indicator    │ Per Section 1.2        │
│                                                                  │
│  Total: 5 bytes per sensor submodule                            │
│                                                                  │
│  NORMATIVE REFERENCES:                                           │
│    [IEC-61158-6] Section 4.10.3.3 - Big-endian requirement      │
│    [IEEE-754] Section 3.4 - Binary32 interchange format         │
│    [GSDML-SPEC] Table 18 - Float32 data type                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Quality Byte Encoding

| Value | Constant | C Enum | Python Enum | Meaning |
|-------|----------|--------|-------------|---------|
| 0x00 | QUALITY_GOOD | `QUALITY_GOOD` | `DataQuality.GOOD` | Valid measurement |
| 0x40 | QUALITY_UNCERTAIN | `QUALITY_UNCERTAIN` | `DataQuality.UNCERTAIN` | Degraded/stale |
| 0x80 | QUALITY_BAD | `QUALITY_BAD` | `DataQuality.BAD` | Sensor failure |
| 0xC0 | QUALITY_NOT_CONNECTED | `QUALITY_NOT_CONNECTED` | `DataQuality.NOT_CONNECTED` | No communication |

**Encoding Rationale:**
- Bit 7 (0x80): BAD flag
- Bit 6 (0x40): UNCERTAIN flag  
- Bits 0-5: Reserved for future substatus codes
- Aligns with OPC UA StatusCode major categories for interoperability

### 1.3 Protocol-Level Quality (IOPS)

IOPS is handled by the PROFINET stack and is SEPARATE from application quality:

| Mechanism | Scope | Set By | Meaning |
|-----------|-------|--------|---------|
| IOPS | Per-subslot | p-net stack via API | Communication health |
| Quality byte | Per-sensor | Application logic | Measurement quality |

**IOPS SHALL be GOOD (0x80) when:**
- RTU is operational
- PROFINET AR is established
- Submodule is producing data

**IOPS SHALL be BAD (0x00) when:**
- RTU initialization incomplete
- Hardware fault affecting submodule
- AR termination in progress

---

## Part 2: Water-Treat (RTU) Implementation Standards

### 2.1 Required Type Definitions

**File:** `include/common.h`

```c
/**
 * @brief Data quality indicators per WT-SPEC-001 Section 5.2
 * 
 * Encoding aligned with OPC UA StatusCode for interoperability.
 * Bit 7 = BAD, Bit 6 = UNCERTAIN, Bits 0-5 = Reserved.
 * 
 * Reference: [IEC-62541-4] OPC UA Part 4: Services
 */
typedef enum {
    QUALITY_GOOD          = 0x00,  /**< Fresh, valid measurement */
    QUALITY_UNCERTAIN     = 0x40,  /**< Stale, degraded, or at limits */
    QUALITY_BAD           = 0x80,  /**< Sensor failure, invalid data */
    QUALITY_NOT_CONNECTED = 0xC0,  /**< No communication with sensor */
} data_quality_t;

/**
 * @brief Sensor reading with quality metadata.
 * 
 * This structure represents a single sensor measurement with
 * associated quality information for propagation through the
 * system per WT-SPEC-001.
 */
typedef struct {
    float value;              /**< Measured value in engineering units */
    data_quality_t quality;   /**< Quality indicator */
    uint64_t timestamp_us;    /**< Measurement timestamp (microseconds since boot) */
} sensor_reading_t;
```

### 2.2 PROFINET Data Packing

**File:** `src/profinet/profinet_manager.c`

```c
/**
 * @brief Pack sensor reading into PROFINET cyclic data buffer.
 * 
 * Converts sensor reading to wire format per WT-SPEC-001:
 *   - Float32 in big-endian (network byte order)
 *   - Quality byte appended
 * 
 * @param[in]  reading  Source sensor reading
 * @param[out] buffer   Destination buffer (must be >= 5 bytes)
 * @param[in]  size     Buffer size for bounds checking
 * 
 * @return Number of bytes written (5), or -1 on error
 * 
 * @pre reading != NULL
 * @pre buffer != NULL
 * @pre size >= 5
 * 
 * @note Thread safety: SAFE (no shared state)
 */
int pack_sensor_to_profinet(const sensor_reading_t *reading,
                            uint8_t *buffer,
                            size_t size)
{
    if (reading == NULL || buffer == NULL || size < 5) {
        return -1;
    }
    
    /* Convert float to big-endian per [IEC-61158-6] */
    uint32_t float_bits;
    memcpy(&float_bits, &reading->value, sizeof(float_bits));
    float_bits = htonl(float_bits);
    
    /* Pack: bytes 0-3 = float, byte 4 = quality */
    memcpy(buffer, &float_bits, 4);
    buffer[4] = (uint8_t)reading->quality;
    
    return 5;
}
```

### 2.3 Quality Derivation

Quality SHALL be derived from actual sensor state, not defaulted:

```c
/**
 * @brief Derive quality indicator from sensor diagnostic state.
 * 
 * Quality derivation rules per WT-SPEC-001:
 *   1. Hardware fault → BAD
 *   2. Communication timeout → NOT_CONNECTED
 *   3. Value at range limit → UNCERTAIN
 *   4. Stale (age > threshold) → UNCERTAIN
 *   5. Otherwise → GOOD
 * 
 * @param[in] sensor  Sensor instance with diagnostic state
 * @return Appropriate quality indicator
 */
data_quality_t derive_sensor_quality(const sensor_instance_t *sensor)
{
    if (sensor == NULL) {
        return QUALITY_NOT_CONNECTED;
    }
    
    /* Check hardware fault flags */
    if (sensor->fault_flags & SENSOR_FAULT_HARDWARE) {
        return QUALITY_BAD;
    }
    
    /* Check communication state */
    if (sensor->fault_flags & SENSOR_FAULT_COMM_TIMEOUT) {
        return QUALITY_NOT_CONNECTED;
    }
    
    /* Check for range limiting */
    if (sensor->value <= sensor->range_min || 
        sensor->value >= sensor->range_max) {
        return QUALITY_UNCERTAIN;
    }
    
    /* Check staleness */
    uint64_t now = get_monotonic_time_us();
    uint64_t age_ms = (now - sensor->last_update_us) / 1000;
    if (age_ms > sensor->stale_threshold_ms) {
        return QUALITY_UNCERTAIN;
    }
    
    return QUALITY_GOOD;
}
```

### 2.4 GSDML Requirements

**File:** `gsd/GSDML-V2.4-WaterTreat-RTU-*.xml`

Each sensor submodule MUST declare 5 bytes of input data:

```xml
<!-- CORRECT: 5 bytes per WT-SPEC-001 -->
<VirtualSubmoduleItem ID="sensor_pH" SubmoduleIdentNumber="0x00000010">
    <IOData>
        <Input>
            <DataItem DataType="Float32" TextId="IDT_pH_Value"/>
            <DataItem DataType="Unsigned8" TextId="IDT_pH_Quality"/>
        </Input>
    </IOData>
</VirtualSubmoduleItem>

<!-- PROHIBITED: Old 4-byte format -->
<!-- <DataItem DataType="Float32" TextId="IDT_pH"/> -->
```

### 2.5 Compliance Checklist (RTU)

```
WATER-TREAT PRE-COMMIT VERIFICATION
═══════════════════════════════════════════════════════════════════

DATA FORMAT COMPLIANCE
  [ ] data_quality_t enum defined in common.h with correct values
  [ ] sensor_reading_t struct includes quality field
  [ ] pack_sensor_to_profinet() produces exactly 5 bytes
  [ ] Float conversion uses htonl() for big-endian
  [ ] Quality byte placed at offset 4

QUALITY DERIVATION
  [ ] derive_sensor_quality() implemented (not stub)
  [ ] All quality states reachable (GOOD, UNCERTAIN, BAD, NOT_CONNECTED)
  [ ] Quality reflects actual sensor state (not hardcoded GOOD)
  [ ] Fault injection tests verify quality transitions

GSDML ALIGNMENT
  [ ] GSDML declares 5 bytes input per sensor submodule
  [ ] GSDML validated with PI Checker (zero errors)
  [ ] GSDML version date updated
  [ ] GSDML file name matches convention

PROFINET STACK INTEGRATION
  [ ] slot->input_size = 5 (not 4)
  [ ] pnet_input_set_data_and_iops() called correctly
  [ ] IOPS set to GOOD when submodule operational

═══════════════════════════════════════════════════════════════════
```

### 2.6 RTU HTTP API Endpoints

The RTU exposes a REST API for configuration, diagnostics, and GSDML retrieval.
All endpoints are at the root path (no `/api/v1/` prefix).

**Base URL:** `http://<rtu_ip>:9081`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (returns 200 OK when operational) |
| `/metrics` | GET | Prometheus-compatible metrics |
| `/ready` | GET | Readiness probe (PROFINET stack initialized) |
| `/live` | GET | Liveness probe (process responsive) |
| `/config` | GET | PROFINET configuration (vendor_id, device_id, station_name) |
| `/slots` | GET | Slot configuration (slot_count, module/submodule IDs) |
| `/gsdml` | GET | GSDML XML file for this RTU |

**Example `/config` response:**
```json
{
  "profinet": {
    "station_name": "rtu-ec3b",
    "vendor_id": 626,
    "device_id": 3520,
    "product_name": "Water Treatment RTU",
    "enabled": true
  }
}
```

**Example `/slots` response:**
```json
{
  "slot_count": 8,
  "slots": [
    {
      "slot": 1,
      "subslot": 1,
      "module_ident": 1,
      "submodule_ident": 1,
      "direction": "input",
      "data_size": 5
    }
  ]
}
```

**Controller Integration:**
- Controller fetches `/config` for PROFINET identity (vendor_id, device_id)
- Controller fetches `/slots` for slot count and module configuration
- Controller fetches `/gsdml` during RTU discovery for module catalog

---

## Part 3: Water-Controller Implementation Standards

### 3.1 Required Type Definitions

**File:** `include/profinet/data_types.h` (C controller core)

```c
/**
 * @brief Data quality indicators per WT-SPEC-001 Section 5.2
 * 
 * MUST match Water-Treat RTU encoding exactly.
 */
typedef enum {
    QUALITY_GOOD          = 0x00,
    QUALITY_UNCERTAIN     = 0x40,
    QUALITY_BAD           = 0x80,
    QUALITY_NOT_CONNECTED = 0xC0,
} data_quality_t;

typedef struct {
    float value;
    data_quality_t quality;
    uint64_t timestamp_us;
    uint16_t source_slot;
    char source_rtu[64];
} qualified_sensor_value_t;
```

**File:** `src/api/models/sensor.py` (Python API)

```python
from enum import IntEnum
from dataclasses import dataclass
from datetime import datetime

class DataQuality(IntEnum):
    """
    Data quality indicators per WT-SPEC-001 Section 5.2.
    
    MUST match Water-Treat RTU encoding exactly.
    """
    GOOD = 0x00
    UNCERTAIN = 0x40
    BAD = 0x80
    NOT_CONNECTED = 0xC0

@dataclass(frozen=True)
class QualifiedSensorValue:
    """Immutable sensor value with quality metadata."""
    value: float
    quality: DataQuality
    timestamp: datetime
    source_rtu: str
    slot: int
    
    @property
    def is_usable(self) -> bool:
        """True if value can be used for control/alarming."""
        return self.quality in (DataQuality.GOOD, DataQuality.UNCERTAIN)
```

### 3.2 PROFINET Data Unpacking

**File:** `src/profinet/profinet_manager.c`

```c
/**
 * @brief Unpack sensor data from PROFINET cyclic buffer.
 * 
 * Parses wire format per WT-SPEC-001:
 *   - Bytes 0-3: Float32, big-endian
 *   - Byte 4: Quality indicator
 * 
 * @param[in]  buffer   Source buffer from PROFINET (>= 5 bytes)
 * @param[in]  size     Buffer size for validation
 * @param[out] value    Parsed sensor value
 * 
 * @return 0 on success, -1 on error
 */
int unpack_sensor_from_profinet(const uint8_t *buffer,
                                 size_t size,
                                 qualified_sensor_value_t *value)
{
    if (buffer == NULL || value == NULL || size < 5) {
        return -1;
    }
    
    /* Extract big-endian float from bytes 0-3 */
    uint32_t float_bits;
    memcpy(&float_bits, buffer, 4);
    float_bits = ntohl(float_bits);
    memcpy(&value->value, &float_bits, sizeof(float));
    
    /* Extract quality from byte 4 */
    value->quality = (data_quality_t)buffer[4];
    
    /* Validate quality code */
    switch (value->quality) {
        case QUALITY_GOOD:
        case QUALITY_UNCERTAIN:
        case QUALITY_BAD:
        case QUALITY_NOT_CONNECTED:
            break;
        default:
            /* Unknown quality code - treat as BAD */
            log_warn("Unknown quality code 0x%02X, treating as BAD", 
                     buffer[4]);
            value->quality = QUALITY_BAD;
            break;
    }
    
    value->timestamp_us = get_monotonic_time_us();
    
    return 0;
}
```

### 3.3 Quality Propagation Requirements

Quality MUST be propagated through all system layers:

```
┌─────────────────────────────────────────────────────────────────┐
│                    QUALITY PROPAGATION PATH                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  PROFINET Frame                                                  │
│       │                                                          │
│       ▼                                                          │
│  C Controller (unpack_sensor_from_profinet)                      │
│       │                                                          │
│       ▼                                                          │
│  Shared Memory (include quality in struct)                       │
│       │                                                          │
│       ├──────────────────┬──────────────────┐                   │
│       ▼                  ▼                  ▼                   │
│  Python API         Historian           Alarm Manager           │
│  (REST/WS)          (PostgreSQL)        (ISA-18.2)              │
│       │                  │                  │                   │
│       ▼                  ▼                  ▼                   │
│  JSON Response     quality column      suppress on BAD          │
│  includes quality  in historian_data   quality data             │
│       │                                                          │
│       ▼                                                          │
│  React HMI (visual indication per quality)                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 HMI Quality Visualization

**File:** `src/components/SensorDisplay.tsx`

```typescript
interface SensorDisplayProps {
    value: number;
    quality: 'GOOD' | 'UNCERTAIN' | 'BAD' | 'NOT_CONNECTED';
    units: string;
    label: string;
}

/**
 * Visual indication per WT-SPEC-001 Section 5.2:
 *   GOOD: Normal display
 *   UNCERTAIN: Yellow background
 *   BAD: Red background, "X" indicator
 *   NOT_CONNECTED: Grey/disabled, "?" indicator
 */
const qualityStyles: Record<string, React.CSSProperties> = {
    GOOD: {},
    UNCERTAIN: { backgroundColor: '#FFF3CD', borderColor: '#FFC107' },
    BAD: { backgroundColor: '#F8D7DA', borderColor: '#DC3545', color: '#721C24' },
    NOT_CONNECTED: { backgroundColor: '#E2E3E5', color: '#6C757D' },
};

const qualityIndicators: Record<string, string> = {
    GOOD: '',
    UNCERTAIN: '⚠',
    BAD: '✕',
    NOT_CONNECTED: '?',
};

export function SensorDisplay({ value, quality, units, label }: SensorDisplayProps) {
    const displayValue = quality === 'BAD' || quality === 'NOT_CONNECTED'
        ? '---'
        : value.toFixed(2);
    
    return (
        <div style={qualityStyles[quality]} className="sensor-display">
            <span className="sensor-label">{label}</span>
            <span className="sensor-value">
                {qualityIndicators[quality]} {displayValue} {units}
            </span>
        </div>
    );
}
```

### 3.5 Historian Quality Storage

**File:** `docker/init.sql`

```sql
-- Quality stored as integer per WT-SPEC-001 encoding
CREATE TABLE historian_data (
    time        TIMESTAMPTZ NOT NULL,
    rtu_name    TEXT NOT NULL,
    slot        INTEGER NOT NULL,
    value       DOUBLE PRECISION,
    quality     SMALLINT NOT NULL DEFAULT 0,  -- 0=GOOD, 64=UNCERTAIN, 128=BAD, 192=NOT_CONNECTED
    
    PRIMARY KEY (time, rtu_name, slot)
);

-- Index for quality-filtered queries
CREATE INDEX idx_historian_quality ON historian_data (quality) WHERE quality != 0;

-- Quality values reference
COMMENT ON COLUMN historian_data.quality IS 
    'Data quality per WT-SPEC-001: 0=GOOD, 64=UNCERTAIN, 128=BAD, 192=NOT_CONNECTED';
```

### 3.6 Alarm Suppression on Bad Quality

**File:** `src/alarms/alarm_manager.py`

```python
def evaluate_limit_alarm(
    reading: QualifiedSensorValue,
    alarm_config: AlarmConfiguration,
) -> Optional[AlarmEvent]:
    """
    Evaluate reading against alarm limits.
    
    Per ISA-18.2 and WT-SPEC-001: Suppress value-based alarms
    when data quality is BAD or NOT_CONNECTED. A separate
    "sensor fault" alarm may be raised instead.
    """
    # Do not alarm on unusable data
    if not reading.is_usable:
        logger.debug(
            "Suppressing alarm evaluation for %s/%d: quality=%s",
            reading.source_rtu, reading.slot, reading.quality.name
        )
        return None
    
    # Normal alarm evaluation
    if reading.value >= alarm_config.high_high_limit:
        return AlarmEvent(
            priority=AlarmPriority.CRITICAL,
            type=AlarmType.HIGH_HIGH,
            # ...
        )
    # ... etc
```

### 3.7 Compliance Checklist (Controller)

```
WATER-CONTROLLER PRE-COMMIT VERIFICATION
═══════════════════════════════════════════════════════════════════

DATA FORMAT COMPLIANCE
  [ ] data_quality_t enum matches RTU values exactly
  [ ] DataQuality Python enum matches RTU values exactly
  [ ] unpack_sensor_from_profinet() expects exactly 5 bytes
  [ ] Float conversion uses ntohl() for big-endian
  [ ] Quality extracted from byte 4

QUALITY PROPAGATION
  [ ] Shared memory struct includes quality field
  [ ] API response JSON includes quality field
  [ ] WebSocket messages include quality field
  [ ] Historian stores quality in database

HMI QUALITY DISPLAY
  [ ] All 4 quality states have distinct visual indication
  [ ] BAD/NOT_CONNECTED show placeholder instead of stale value
  [ ] Quality indicator visible without hovering

ALARM INTEGRATION
  [ ] Alarm evaluation checks quality before comparing values
  [ ] BAD quality suppresses value-based alarms
  [ ] Separate "sensor fault" alarm exists for BAD quality sensors

HISTORIAN
  [ ] quality column exists in historian_data table
  [ ] quality values match WT-SPEC-001 encoding
  [ ] Trend queries can filter by quality

═══════════════════════════════════════════════════════════════════
```

---

## Part 4: Cross-System Compliance Verification

### 4.1 Pre-Release Cross-Check

Before releasing either system, verify cross-compatibility:

```
CROSS-SYSTEM COMPLIANCE GATE
═══════════════════════════════════════════════════════════════════

BYTE-LEVEL ALIGNMENT
  [ ] Water-Treat input_size = 5
  [ ] Water-Controller expected input size = 5
  [ ] Both use htonl/ntohl for float conversion
  [ ] Quality byte at identical offset (4)

QUALITY ENCODING
  [ ] QUALITY_GOOD value identical (0x00)
  [ ] QUALITY_UNCERTAIN value identical (0x40)
  [ ] QUALITY_BAD value identical (0x80)
  [ ] QUALITY_NOT_CONNECTED value identical (0xC0)

GSDML CONSISTENCY
  [ ] Controller imports RTU's GSDML file
  [ ] GSDML declares 5-byte input
  [ ] Module/submodule IDs match expected configuration

INTEGRATION TESTS
  [ ] End-to-end test: RTU → Controller → HMI displays value
  [ ] Quality propagation test: All 4 states verified visually
  [ ] Wireshark capture confirms 5-byte payload

DEPLOYMENT COORDINATION
  [ ] Both systems updated in same release window
  [ ] Rollback plan documented for both systems
  [ ] Version compatibility matrix updated

═══════════════════════════════════════════════════════════════════
```

### 4.2 Wireshark Verification Procedure

```
PROCEDURE: Verify PROFINET Cyclic Data Format
═══════════════════════════════════════════════════════════════════

1. Capture Setup
   - Wireshark on PROFINET network interface
   - Filter: pn_rt (PROFINET Real-Time)
   - Identify Input IOCR frames from RTU

2. Frame Analysis
   - Locate cyclic data payload (after APDU header)
   - Identify submodule data by offset (from AR establishment)
   
3. Verify Sensor Data
   Expected structure per submodule:
   
   Offset  Bytes  Content
   ──────  ─────  ───────────────────────────
   0       4      Float32 value (big-endian)
   4       1      Quality byte
   5       1      IOPS (set by stack)
   
4. Verify Float Encoding
   - Inject known value (e.g., 7.0 pH)
   - Expected bytes: 0x40 0xE0 0x00 0x00 (7.0 in IEEE 754 BE)
   
5. Verify Quality States
   - Trigger each quality state on RTU
   - Confirm byte 4 changes: 0x00 → 0x40 → 0x80 → 0xC0

═══════════════════════════════════════════════════════════════════
```

---

## Part 5: User Sync Protocol (Controller → RTU)

### 5.1 Overview

The User Sync Protocol enables the SCADA Controller to push user credentials to RTU devices for local TUI/HMI authentication. This allows field operators to authenticate directly at RTU panels when controller connectivity is unavailable.

**Data Flow:**
```
Controller                                RTU
┌─────────────────┐                      ┌─────────────────┐
│ User Database   │                      │ NV User Store   │
│ (PostgreSQL)    │                      │ (EEPROM/Flash)  │
└────────┬────────┘                      └────────▲────────┘
         │                                        │
         ▼                                        │
┌─────────────────┐    PROFINET Acyclic    ┌─────┴─────────┐
│ API /users/sync │ ──────────────────────►│ Record Handler│
│ user_sync.c     │    Index: 0xF840       │ user_store.c  │
└─────────────────┘                        └───────────────┘
```

### 5.2 Wire Protocol

**PROFINET Record Index:** `0xF840` (vendor-specific range)

**Payload Structure:**
```c
/* Header: 12 bytes */
typedef struct __attribute__((packed)) {
    uint8_t  version;       /* Protocol version (1) */
    uint8_t  user_count;    /* Number of users (0-16) */
    uint16_t checksum;      /* CRC16-CCITT of user records */
    uint32_t timestamp;     /* Unix timestamp (seconds) */
    uint32_t nonce;         /* Replay protection nonce */
} user_sync_header_t;

/* User Record: 100 bytes each */
typedef struct __attribute__((packed)) {
    char     username[32];       /* Null-terminated */
    char     password_hash[64];  /* Format: "DJB2:%08X:%08X" */
    uint8_t  role;               /* 0=viewer, 1=operator, 2=engineer, 3=admin */
    uint8_t  flags;              /* Bit 0: active */
    uint8_t  reserved[2];        /* Alignment */
} user_sync_record_t;
```

**Maximum Payload Size:** 12 + (100 × 16) = 1612 bytes

### 5.3 Password Hash Format

**Algorithm:** DJB2 with salt prefix

```c
uint32_t djb2_hash(const char *str) {
    uint32_t hash = 5381;
    int c;
    while ((c = *str++)) {
        hash = ((hash << 5) + hash) + c;
    }
    return hash;
}
```

**Salt:** `"NaCl4Life"` (prepended to password before hashing)

**Wire Format:** `"DJB2:%08X:%08X"` where:
- First hex: DJB2 hash of salt alone
- Second hex: DJB2 hash of salt + password

**Example:**
```
Password: "secret123"
Salt hash: DJB2("NaCl4Life") = 0x1A3C1FD7
Full hash: DJB2("NaCl4Lifesecret123") = 0x6A245633
Wire format: "DJB2:1A3C1FD7:6A245633"
```

**Test Vectors (verified):**
```
DJB2("NaCl4Life")              = 0x1A3C1FD7  (salt)
DJB2("NaCl4Lifetest123")       = 0xF82B0BED
DJB2("NaCl4Lifesecret123")     = 0x6A245633
DJB2("NaCl4Lifeadmin")         = 0x2C409AA0
```

### 5.4 RTU Implementation Requirements

**Storage Constraints:**
- Maximum 16 users (embedded memory limit)
- Must persist to non-volatile memory
- Load stored users on RTU boot

**Security Requirements:**
- Use constant-time comparison for password hashes
- Verify CRC before processing payload
- Track nonce for replay protection (optional)

**Shared Headers (in shared/include/):**
- `user_sync_protocol.h` - Wire protocol definitions
- Copy to Water-Treat RTU's shared include path

**RTU Implementation Files (in shared/rtu/):**
- `user_store.h` / `user_store.c` - User storage and authentication
- `profinet_user_handler.h` / `profinet_user_handler.c` - PROFINET integration

### 5.5 API Endpoints (Controller)

**Get users for sync:**
```http
GET /api/v1/users/sync
Authorization: Bearer <admin_token>

Response:
{
  "data": [
    {
      "id": 1,
      "username": "admin",
      "password_hash": "DJB2:1A3C1FD7:2C409AA0",
      "role": "admin",
      "active": true
    }
  ]
}
```

**Trigger sync to RTU:**
```http
POST /api/v1/users/sync/{station_name}
Authorization: Bearer <admin_token>

Response:
{
  "data": {
    "status": "ok",
    "synced_users": 3
  }
}
```

### 5.6 Cross-System Checklist

When implementing or modifying user sync:

**Controller Side (Water-Controller):**
- [ ] Verify DJB2 hash matches `shared/include/user_sync_protocol.h`
- [ ] Verify salt constant is `"NaCl4Life"`
- [ ] Verify wire format is `"DJB2:%08X:%08X"`
- [ ] CRC16-CCITT polynomial is `0x1021`, init `0xFFFF`
- [ ] Payload sent to record index `0xF840`

**RTU Side (Water-Treat):**
- [ ] Copy `shared/include/user_sync_protocol.h` to RTU include path
- [ ] Integrate `shared/rtu/user_store.c` with NV storage backend
- [ ] Register handler for record index `0xF840`
- [ ] Verify hash computation matches controller
- [ ] Use constant-time comparison for password verification

---

## Part 6: Development Prompt Addendum

Add the following to system prompts for AI-assisted development:

```
PROFINET DATA EXCHANGE CONSTRAINTS (per WT-SPEC-001)
════════════════════════════════════════════════════════════════════

When working on Water-Treat RTU or Water-Controller code involving
PROFINET cyclic data:

DATA FORMAT:
- Sensor input: 5 bytes (4-byte Float32 big-endian + 1-byte quality)
- Actuator output: 2 bytes (1-byte command + 1-byte reserved)
- Byte order: Big-endian (network order) per IEC 61158-6
- Use htonl()/ntohl() for float byte swapping

QUALITY ENCODING:
- 0x00 = QUALITY_GOOD (valid measurement)
- 0x40 = QUALITY_UNCERTAIN (degraded/stale)
- 0x80 = QUALITY_BAD (sensor failure)
- 0xC0 = QUALITY_NOT_CONNECTED (no communication)

IOPS vs APPLICATION QUALITY:
- IOPS is protocol-level (handled by p-net stack)
- Quality byte is application-level (set by sensor logic)
- Both MUST be set independently - they are NOT redundant

CROSS-SYSTEM COUPLING:
- Changes to data format require coordinated updates to BOTH systems
- GSDML must match implementation (5 bytes per sensor)
- Controller must expect same byte layout as RTU produces

QUALITY PROPAGATION:
- Quality flows: RTU → Controller → Shared Memory → API → HMI
- Historian stores quality alongside value
- Alarms suppress on BAD/NOT_CONNECTED quality

COMPLIANCE REFERENCES:
- [IEC-61158-6] Section 4.10.3.3 (byte order)
- [GSDML-SPEC] Table 18 (data types)
- [PI-PROFIDRIVE] Section 6.3 (embedded status precedent)
- [WT-SPEC-001] (project specification)

════════════════════════════════════════════════════════════════════
```

---

## Part 6: Configuration Sync Protocol Test Vectors

This section provides verified byte-level test vectors for config sync packets.
Both Controller and RTU implementations MUST produce/parse these exact bytes.

### 6.1 CRC16-CCITT Reference Implementation

```c
// CRC16-CCITT-FALSE: Polynomial 0x1021, Init 0xFFFF
// No input/output reflection, no XOR-out
uint16_t crc16_ccitt(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int j = 0; j < 8; j++) {
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
        }
        crc &= 0xFFFF;
    }
    return crc;
}

// VERIFIED test vectors (run against both C and Python):
// CRC16(empty)            = 0xFFFF
// CRC16([0x00])           = 0xE1F0
// CRC16([0x01,0x02,0x03]) = 0xADAD
// CRC16("NaCl4Life")      = 0x9311
// CRC16("test")           = 0xD219
// CRC16("123456789")      = 0x29B1  (standard CCITT-FALSE check value)
```

### 6.2 Device Config (0xF841) - 52 bytes

```c
// Test case: rtu-tank-1 with 8 sensors, 7 actuators
// timestamp = 0x65A1B2C3 (Unix seconds)

device_config_payload_t test_device_config = {
    .version = 0x01,
    .flags = 0x01,              // config_changed
    .crc16 = 0x?????,           // Calculated below
    .config_timestamp = 0x65A1B2C3,
    .station_name = "rtu-tank-1\0...",  // 32 bytes, null-padded
    .sensor_count = 8,
    .actuator_count = 7,
    .authority_mode = 0x01,     // SUPERVISED
    .reserved = 0x00,
    .watchdog_ms = 3000         // 0x00000BB8
};

// Wire bytes (52 total, big-endian multi-byte values):
// Offset 00: 01 01 XX XX                      // version, flags, crc16
// Offset 04: 65 A1 B2 C3                      // timestamp (BE)
// Offset 08: 72 74 75 2D 74 61 6E 6B 2D 31 00 00 00 00 00 00  // "rtu-tank-1"
// Offset 24: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  // padding
// Offset 40: 00 08                            // sensor_count (BE)
// Offset 42: 00 07                            // actuator_count (BE)
// Offset 44: 01                               // authority_mode
// Offset 45: 00                               // reserved
// Offset 46: 00 00 0B B8                      // watchdog_ms (BE) = 3000

// CRC scope: bytes 4-51 (48 bytes, after crc16 field)
```

### 6.3 Sensor Config (0xF842) - Header + 42-byte entries

```c
// Test case: 2 sensors

// Header (4 bytes):
// Offset 00: 01              // version
// Offset 01: 02              // count = 2
// Offset 02: XX XX           // crc16 (over entries only)

// Entry 0 (42 bytes): pH sensor in slot 1
sensor_config_entry_t sensor0 = {
    .slot = 1,
    .sensor_type = 0,         // MEASUREMENT_PH
    .name = "pH\0............",  // 16 bytes
    .unit = "pH\0.....",         // 8 bytes
    .scale_min = 0.0f,        // 0x00000000
    .scale_max = 14.0f,       // 0x41600000
    .alarm_low = 6.5f,        // 0x40D00000
    .alarm_high = 8.5f        // 0x41080000
};

// Entry 0 wire bytes (42 bytes):
// Offset 00: 01 00                            // slot, type
// Offset 02: 70 48 00 00 00 00 00 00 00 00 00 00 00 00 00 00  // "pH" + padding
// Offset 18: 70 48 00 00 00 00 00 00          // "pH" unit + padding
// Offset 26: 00 00 00 00                      // scale_min (0.0f BE)
// Offset 30: 41 60 00 00                      // scale_max (14.0f BE)
// Offset 34: 40 D0 00 00                      // alarm_low (6.5f BE)
// Offset 38: 41 08 00 00                      // alarm_high (8.5f BE)

// Entry 1 (42 bytes): Temperature sensor in slot 2
sensor_config_entry_t sensor1 = {
    .slot = 2,
    .sensor_type = 1,         // MEASUREMENT_TEMPERATURE
    .name = "Temp\0...........", // 16 bytes
    .unit = "degC\0...",        // 8 bytes
    .scale_min = 0.0f,
    .scale_max = 100.0f,      // 0x42C80000
    .alarm_low = 5.0f,        // 0x40A00000
    .alarm_high = 40.0f       // 0x42200000
};

// CRC scope: all entry bytes (84 bytes for 2 entries)
```

### 6.4 Actuator Config (0xF843) - Header + 22-byte entries

```c
// Test case: 1 actuator (pump in slot 9)

// Header (4 bytes):
// Offset 00: 01              // version
// Offset 01: 01              // count = 1
// Offset 02: XX XX           // crc16 (over entries only)

// Entry 0 (22 bytes):
actuator_config_entry_t actuator0 = {
    .slot = 9,
    .actuator_type = 2,       // ACTUATOR_PUMP
    .name = "Pump1\0..........", // 16 bytes
    .default_state = 0x00,    // OFF
    .reserved = 0x00,
    .interlock_mask = 0x0000
};

// Entry 0 wire bytes (22 bytes):
// Offset 00: 09 02                            // slot, type
// Offset 02: 50 75 6D 70 31 00 00 00 00 00 00 00 00 00 00 00  // "Pump1"
// Offset 18: 00                               // default_state
// Offset 19: 00                               // reserved
// Offset 20: 00 00                            // interlock_mask (BE)
```

### 6.5 Enrollment (0xF845) - 80 bytes

```c
// Test case: BIND operation with token

enrollment_payload_t test_enrollment = {
    .magic = 0x454E524C,      // "ENRL" in network order
    .version = 0x01,
    .operation = 0x01,        // BIND
    .crc16 = 0x????,          // Calculated below
    .enrollment_token = "wtc-enroll-0123456789abcdef0123456789abcdef\0...",  // 64 bytes
    .controller_id = 0x0001C0DE,
    .reserved = 0x00000000
};

// Wire bytes (80 total):
// Offset 00: 45 4E 52 4C                      // magic "ENRL"
// Offset 04: 01                               // version
// Offset 05: 01                               // operation (BIND)
// Offset 06: XX XX                            // crc16
// Offset 08: 77 74 63 2D 65 6E 72 6F 6C 6C 2D // "wtc-enroll-"
//            30 31 32 33 34 35 36 37 38 39 61 62 63 64 65 66  // "0123456789abcdef"
//            30 31 32 33 34 35 36 37 38 39 61 62 63 64 65 66  // "0123456789abcdef"
//            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  // null padding to 64
//            00 00 00 00 00 00 00 00 00 00 00 00 00          // (continued)
// Offset 72: 00 01 C0 DE                      // controller_id (BE)
// Offset 76: 00 00 00 00                      // reserved

// CRC scope: bytes 8-79 (72 bytes: token + controller_id + reserved)
```

### 6.6 Float32 Big-Endian Test Vectors

```c
// IEEE 754 Float32, network byte order (big-endian)

float value     | Hex (LE memory) | Wire bytes (BE)
----------------|-----------------|------------------
0.0f            | 0x00000000      | 00 00 00 00
1.0f            | 0x3F800000      | 3F 80 00 00
-1.0f           | 0xBF800000      | BF 80 00 00
14.0f           | 0x41600000      | 41 60 00 00
100.0f          | 0x42C80000      | 42 C8 00 00
6.5f            | 0x40D00000      | 40 D0 00 00
8.5f            | 0x41080000      | 41 08 00 00
3.14159f        | 0x40490FDB      | 40 49 0F DB

// Conversion functions:
// Controller (C): Use htonl(*(uint32_t*)&value) for sending
// RTU (C): Use ntohl() then cast back to float for receiving
```

### 6.7 Validation Checklist

Both implementations MUST verify:

- [ ] CRC16-CCITT with poly=0x1021, init=0xFFFF
- [ ] All multi-byte integers in network byte order (big-endian)
- [ ] All floats in IEEE 754 big-endian
- [ ] Strings null-terminated and zero-padded to field length
- [ ] Packet sizes: 0xF841=52, 0xF842=4+42n, 0xF843=4+22n, 0xF845=80
- [ ] Magic number 0x454E524C for enrollment packets
- [ ] Version field = 0x01 for all packets

---

## Appendix: Version Compatibility Matrix

| Water-Treat Version | Water-Controller Version | Data Format | Compatible |
|---------------------|--------------------------|-------------|------------|
| < 1.0.0 | < 1.0.0 | 4-byte (Float32 only) | Yes |
| ≥ 1.0.0 | < 1.0.0 | Mixed | **NO** |
| < 1.0.0 | ≥ 1.0.0 | Mixed | **NO** |
| ≥ 1.0.0 | ≥ 1.0.0 | 5-byte (Float32 + Quality) | Yes |

**Critical:** Version 1.0.0 introduces breaking wire format change. Both systems MUST be updated together.

---

*This addendum is authoritative for cross-system data exchange. Deviations require documented justification and updates to WT-SPEC-001.*
