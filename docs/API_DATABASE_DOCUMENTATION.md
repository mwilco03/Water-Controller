# Water Treatment Controller - API & Database Documentation

**Version:** 1.0.0
**Date:** 2026-01-17
**Base URL:** `http://<controller-ip>:8000`

---

## Table of Contents

1. [Overview](#overview)
2. [Entity Relationship Diagram](#entity-relationship-diagram)
3. [Database Schema](#database-schema)
4. [API Endpoints](#api-endpoints)
5. [Authentication](#authentication)
6. [WebSocket API](#websocket-api)
7. [Data Models](#data-models)

---

## Overview

The Water Treatment Controller API provides REST endpoints for:
- RTU management and PROFINET communication
- Real-time sensor data and actuator control
- Alarm management (ISA-18.2 compliant)
- PID loop configuration
- Time-series historian
- User authentication and audit logging

**Technology Stack:**
- FastAPI (Python 3.11+)
- SQLAlchemy ORM
- PostgreSQL/TimescaleDB (production) or SQLite (dev)
- WebSocket for real-time updates

---

## Entity Relationship Diagram

```
┌─────────────────┐         ┌─────────────────┐
│     users       │         │  user_sessions  │
├─────────────────┤         ├─────────────────┤
│ id (PK)         │         │ token (PK)      │
│ username (UQ)   │◄────────│ username        │
│ password_hash   │         │ role            │
│ role            │         │ groups (JSON)   │
│ active          │         │ created_at      │
│ sync_to_rtus    │         │ expires_at      │
│ created_at      │         │ ip_address      │
│ last_login      │         └─────────────────┘
└─────────────────┘
        │
        ▼
┌─────────────────┐
│   audit_log     │
├─────────────────┤
│ id (PK)         │
│ timestamp       │
│ user            │
│ action          │
│ resource_type   │
│ resource_id     │
│ details         │
│ ip_address      │
└─────────────────┘


┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│      rtus        │       │      slots       │       │     sensors      │
├──────────────────┤       ├──────────────────┤       ├──────────────────┤
│ id (PK)          │◄──────│ id (PK)          │◄──────│ id (PK)          │
│ station_name (UQ)│   1:N │ rtu_id (FK)      │   1:N │ rtu_id (FK)      │
│ ip_address (UQ)  │       │ slot_number      │       │ slot_id (FK)     │
│ vendor_id        │       │ module_id        │       │ tag (UQ)         │
│ device_id        │       │ module_type      │       │ channel          │
│ slot_count       │       │ status           │       │ sensor_type      │
│ state            │       │ created_at       │       │ unit             │
│ state_since      │       │ updated_at       │       │ scale_min/max    │
│ last_error       │       └──────────────────┘       │ eng_min/max      │
│ rtu_version      │               │                  │ created_at       │
│ version_mismatch │               │                  └──────────────────┘
│ created_at       │               │                           │
│ updated_at       │               │ 1:N                       │
└──────────────────┘               ▼                           │
        │                  ┌──────────────────┐               │
        │                  │    controls      │               │
        │                  ├──────────────────┤               │
        └──────────────────│ id (PK)          │               │
                       1:N │ rtu_id (FK)      │               │
                           │ slot_id (FK)     │               │
                           │ tag (UQ)         │               │
                           │ channel          │               │
                           │ control_type     │               │
                           │ equipment_type   │               │
                           │ min_value        │               │
                           │ max_value        │               │
                           │ unit             │               │
                           │ created_at       │               │
                           └──────────────────┘               │
                                                               │
                                                               ▼
                                                    ┌─────────────────────┐
                                                    │ historian_samples   │
                                                    ├─────────────────────┤
                                                    │ id (PK)             │
                                                    │ sensor_id (FK)      │
                                                    │ timestamp           │
                                                    │ value               │
                                                    │ quality             │
                                                    └─────────────────────┘


┌──────────────────┐       ┌──────────────────┐
│   alarm_rules    │       │  alarm_events    │
├──────────────────┤       ├──────────────────┤
│ id (PK)          │◄──────│ id (PK)          │
│ name             │   1:N │ alarm_rule_id(FK)│
│ rtu_station      │       │ rtu_station      │
│ slot             │       │ slot             │
│ condition        │       │ state            │
│ threshold        │       │ value_at_activ   │
│ severity         │       │ message          │
│ delay_ms         │       │ activated_at     │
│ message          │       │ acknowledged_at  │
│ enabled          │       │ acknowledged_by  │
│ created_at       │       │ cleared_at       │
│ updated_at       │       │ note             │
└──────────────────┘       └──────────────────┘


┌──────────────────┐       ┌──────────────────────┐
│ shelved_alarms   │       │ scheduled_maintenance│
├──────────────────┤       ├──────────────────────┤
│ id (PK)          │       │ id (PK)              │
│ rtu_station      │       │ rtu_station          │
│ slot             │       │ slot (-1 = all)      │
│ shelved_by       │       │ scheduled_by         │
│ shelved_at       │       │ scheduled_at         │
│ shelf_duration   │       │ start_time           │
│ expires_at       │       │ end_time             │
│ reason           │       │ reason               │
│ active           │       │ work_order           │
└──────────────────┘       │ status               │
                           │ activated_at         │
                           │ completed_at         │
                           │ cancelled_by         │
                           └──────────────────────┘


┌──────────────────┐       ┌──────────────────────┐
│    pid_loops     │       │   historian_tags     │
├──────────────────┤       ├──────────────────────┤
│ id (PK)          │       │ id (PK)              │
│ name             │       │ rtu_station          │
│ enabled          │       │ slot                 │
│ input_rtu        │       │ tag_name (UQ)        │
│ input_slot       │       │ unit                 │
│ output_rtu       │       │ sample_rate_ms       │
│ output_slot      │       │ deadband             │
│ kp, ki, kd       │       │ compression          │
│ setpoint         │       │ created_at           │
│ output_min/max   │       └──────────────────────┘
│ deadband         │
│ integral_limit   │       ┌──────────────────────┐
│ derivative_filter│       │  slot_configs        │
│ mode             │       ├──────────────────────┤
│ created_at       │       │ id (PK)              │
│ updated_at       │       │ rtu_station          │
└──────────────────┘       │ slot                 │
                           │ subslot              │
┌──────────────────────┐   │ slot_type            │
│ profinet_diagnostics │   │ name                 │
├──────────────────────┤   │ unit                 │
│ id (PK)              │   │ measurement_type     │
│ rtu_id (FK)          │   │ actuator_type        │
│ timestamp            │   │ scale_min/max        │
│ level                │   │ alarm setpoints      │
│ source               │   │ deadband             │
│ message              │   │ enabled              │
│ details (JSON)       │   │ created_at           │
└──────────────────────┘   └──────────────────────┘
```

**Legend:**
- `PK` = Primary Key
- `FK` = Foreign Key
- `UQ` = Unique Constraint
- `1:N` = One-to-Many relationship
- `(JSON)` = JSON-encoded field

---

## Database Schema

### Core Tables

#### `users`
User accounts for authentication and authorization.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | User ID |
| username | VARCHAR(64) | UNIQUE, NOT NULL | Login username |
| password_hash | VARCHAR(128) | NOT NULL | Bcrypt password hash |
| role | VARCHAR(16) | NOT NULL | admin, operator, viewer |
| active | BOOLEAN | DEFAULT TRUE | Account enabled |
| sync_to_rtus | BOOLEAN | DEFAULT TRUE | Sync to RTU user lists |
| created_at | TIMESTAMP | NOT NULL | Account creation time |
| updated_at | TIMESTAMP | NOT NULL | Last profile update |
| last_login | TIMESTAMP | NULL | Last successful login |

**Indexes:** `ix_users_username`

#### `user_sessions`
Active user sessions (token-based auth).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| token | VARCHAR(256) | PK | Session token (JWT-like) |
| username | VARCHAR(64) | NOT NULL | Associated user |
| role | VARCHAR(16) | NOT NULL | Cached role |
| groups | TEXT | NULL | JSON array of groups |
| created_at | TIMESTAMP | NOT NULL | Session start time |
| last_activity | TIMESTAMP | NOT NULL | Last API call |
| expires_at | TIMESTAMP | NOT NULL | Session expiration |
| ip_address | VARCHAR(45) | NULL | Client IP (IPv6 compatible) |
| user_agent | VARCHAR(256) | NULL | Client user agent |

**Indexes:** `ix_user_sessions_expires`, `ix_user_sessions_username`

#### `audit_log`
System audit trail for compliance.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Log entry ID |
| timestamp | TIMESTAMP | NOT NULL | Event time |
| user | VARCHAR(64) | NULL | User who performed action |
| action | VARCHAR(32) | NOT NULL | Action type |
| resource_type | VARCHAR(32) | NULL | Resource type affected |
| resource_id | VARCHAR(64) | NULL | Resource ID |
| details | TEXT | NULL | Additional context |
| ip_address | VARCHAR(45) | NULL | Client IP |

**Indexes:** `ix_audit_log_user`, `ix_audit_log_action`, `ix_audit_log_resource`

---

### RTU & I/O Tables

#### `rtus`
RTU device configuration and state.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | RTU ID |
| station_name | VARCHAR(32) | UNIQUE, NOT NULL | PROFINET station name |
| ip_address | VARCHAR(15) | UNIQUE, NOT NULL | RTU IPv4 address |
| vendor_id | VARCHAR(6) | NOT NULL | PROFINET vendor ID (hex) |
| device_id | VARCHAR(6) | NOT NULL | PROFINET device ID (hex) |
| slot_count | INTEGER | NOT NULL | Number of I/O slots |
| state | VARCHAR(20) | NOT NULL | OFFLINE, CONNECTING, RUNNING, ERROR |
| state_since | TIMESTAMP | NOT NULL | Last state change time |
| transition_reason | VARCHAR(256) | NULL | Why state changed |
| last_error | TEXT | NULL | Last error message |
| rtu_version | VARCHAR(32) | NULL | RTU firmware version |
| version_mismatch | BOOLEAN | DEFAULT FALSE | Version mismatch detected |
| created_at | TIMESTAMP | NOT NULL | RTU added to system |
| updated_at | TIMESTAMP | NOT NULL | Last config update |

**Indexes:** `ix_rtus_station_name`

**State Machine:**
```
OFFLINE → CONNECTING → DISCOVERY → RUNNING
   ↑           ↓            ↓          ↓
   └───────────────── ERROR ←──────────┘
```

#### `slots`
RTU slot/module configuration.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Slot ID |
| rtu_id | INTEGER | FK → rtus.id | Parent RTU |
| slot_number | INTEGER | NOT NULL | Physical slot number |
| module_id | VARCHAR(6) | NULL | Module ID (hex) |
| module_type | VARCHAR(32) | NULL | AI-8, DO-16, etc. |
| status | VARCHAR(20) | DEFAULT EMPTY | OK, EMPTY, FAULT, PULLED |
| created_at | TIMESTAMP | NOT NULL | Slot created |
| updated_at | TIMESTAMP | NOT NULL | Last update |

**Constraints:** `UNIQUE(rtu_id, slot_number)`
**Indexes:** `ix_slots_rtu_id`

#### `sensors`
Sensor/input configuration.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Sensor ID |
| rtu_id | INTEGER | FK → rtus.id | Parent RTU |
| slot_id | INTEGER | FK → slots.id | Parent slot |
| tag | VARCHAR(32) | UNIQUE, NOT NULL | Unique sensor tag |
| channel | INTEGER | NOT NULL | Channel within slot |
| sensor_type | VARCHAR(32) | NOT NULL | level, flow, temp, pressure |
| unit | VARCHAR(16) | NULL | Engineering unit |
| scale_min | FLOAT | DEFAULT 0.0 | Raw value min (e.g., 4mA) |
| scale_max | FLOAT | DEFAULT 100.0 | Raw value max (e.g., 20mA) |
| eng_min | FLOAT | DEFAULT 0.0 | Engineering min |
| eng_max | FLOAT | DEFAULT 100.0 | Engineering max |
| created_at | TIMESTAMP | NOT NULL | Sensor created |
| updated_at | TIMESTAMP | NOT NULL | Last update |

**Indexes:** `ix_sensors_tag`, `ix_sensors_rtu_id`, `ix_sensors_slot_id`

#### `controls`
Control/actuator configuration.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Control ID |
| rtu_id | INTEGER | FK → rtus.id | Parent RTU |
| slot_id | INTEGER | FK → slots.id | Parent slot |
| tag | VARCHAR(32) | UNIQUE, NOT NULL | Unique control tag |
| channel | INTEGER | NOT NULL | Channel within slot |
| control_type | VARCHAR(16) | NOT NULL | discrete, analog |
| equipment_type | VARCHAR(32) | NULL | pump, valve, vfd |
| min_value | FLOAT | NULL | Min output (analog only) |
| max_value | FLOAT | NULL | Max output (analog only) |
| unit | VARCHAR(16) | NULL | Engineering unit |
| created_at | TIMESTAMP | NOT NULL | Control created |
| updated_at | TIMESTAMP | NOT NULL | Last update |

**Indexes:** `ix_controls_tag`, `ix_controls_rtu_id`, `ix_controls_slot_id`

---

### Alarm Tables

#### `alarm_rules`
Alarm rule definitions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Rule ID |
| name | VARCHAR(64) | NOT NULL | Rule name |
| rtu_station | VARCHAR(32) | NOT NULL | Target RTU |
| slot | INTEGER | NOT NULL | Target slot |
| condition | VARCHAR(16) | NOT NULL | >, <, >=, <=, == |
| threshold | FLOAT | NOT NULL | Threshold value |
| severity | VARCHAR(16) | NOT NULL | LOW, MEDIUM, HIGH, CRITICAL |
| delay_ms | INTEGER | DEFAULT 0 | Delay before activation (debounce) |
| message | TEXT | NULL | Alarm message template |
| enabled | BOOLEAN | DEFAULT TRUE | Rule active |
| created_at | TIMESTAMP | NOT NULL | Rule created |
| updated_at | TIMESTAMP | NOT NULL | Last update |

**Indexes:** `ix_alarm_rules_rtu_station`

#### `alarm_events`
Alarm event instances (runtime).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Event ID |
| alarm_rule_id | INTEGER | FK → alarm_rules.id | Source rule (nullable) |
| rtu_station | VARCHAR(32) | NOT NULL | RTU where alarm occurred |
| slot | INTEGER | NOT NULL | Slot where alarm occurred |
| state | VARCHAR(16) | NOT NULL | ACTIVE, ACKNOWLEDGED, CLEARED |
| value_at_activation | FLOAT | NULL | Sensor value when activated |
| message | VARCHAR(256) | NULL | Alarm message |
| activated_at | TIMESTAMP | NOT NULL | When alarm raised |
| acknowledged_at | TIMESTAMP | NULL | When acknowledged |
| acknowledged_by | VARCHAR(64) | NULL | Who acknowledged |
| cleared_at | TIMESTAMP | NULL | When cleared |
| note | TEXT | NULL | Operator notes |

**Indexes:** `ix_alarm_events_state`, `ix_alarm_events_activated_at`, `ix_alarm_events_rtu_station`

#### `shelved_alarms`
Temporarily suppressed alarms (ISA-18.2).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Shelving ID |
| rtu_station | VARCHAR(32) | NOT NULL | RTU being shelved |
| slot | INTEGER | NOT NULL | Slot being shelved |
| shelved_by | VARCHAR(64) | NOT NULL | Who shelved |
| shelved_at | TIMESTAMP | NOT NULL | When shelved |
| shelf_duration_minutes | INTEGER | NOT NULL | Duration |
| expires_at | TIMESTAMP | NOT NULL | Auto-unshelve time |
| reason | TEXT | NULL | Why shelved |
| active | BOOLEAN | DEFAULT TRUE | Shelving active |

**Indexes:** `ix_shelved_alarms_active_expires`, `ix_shelved_alarms_rtu_slot`

#### `scheduled_maintenance`
Pre-planned alarm suppression windows.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Schedule ID |
| rtu_station | VARCHAR(32) | NOT NULL | RTU for maintenance |
| slot | INTEGER | NOT NULL | Slot (-1 = entire RTU) |
| scheduled_by | VARCHAR(64) | NOT NULL | Who scheduled |
| scheduled_at | TIMESTAMP | NOT NULL | When scheduled |
| start_time | TIMESTAMP | NOT NULL | Maintenance start |
| end_time | TIMESTAMP | NOT NULL | Maintenance end |
| reason | TEXT | NOT NULL | Work description |
| work_order | VARCHAR(64) | NULL | Work order number |
| status | VARCHAR(16) | DEFAULT SCHEDULED | SCHEDULED, ACTIVE, COMPLETED, CANCELLED |
| activated_at | TIMESTAMP | NULL | When started |
| completed_at | TIMESTAMP | NULL | When completed |
| cancelled_by | VARCHAR(64) | NULL | Who cancelled |
| cancelled_at | TIMESTAMP | NULL | When cancelled |

**Indexes:** `ix_scheduled_maintenance_status`, `ix_scheduled_maintenance_start`, `ix_scheduled_maintenance_rtu`

---

### Historian Tables

#### `historian_samples`
Time-series data samples.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Sample ID |
| sensor_id | INTEGER | FK → sensors.id | Source sensor |
| timestamp | TIMESTAMP | NOT NULL | Sample time |
| value | FLOAT | NULL | Measured value |
| quality | VARCHAR(16) | DEFAULT GOOD | GOOD, UNCERTAIN, BAD |

**Indexes:** `ix_historian_sensor_time(sensor_id, timestamp)` for efficient time-range queries

**Note:** For production, use TimescaleDB hypertable with automatic partitioning.

#### `historian_tags`
Historian tag configuration.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Tag ID |
| rtu_station | VARCHAR(32) | NOT NULL | Source RTU |
| slot | INTEGER | NOT NULL | Source slot |
| tag_name | VARCHAR(64) | UNIQUE, NOT NULL | Tag name |
| unit | VARCHAR(16) | NULL | Engineering unit |
| sample_rate_ms | INTEGER | DEFAULT 1000 | Sample interval |
| deadband | FLOAT | DEFAULT 0.1 | Min change to record |
| compression | VARCHAR(16) | DEFAULT swinging_door | Compression algorithm |
| created_at | TIMESTAMP | NOT NULL | Tag created |

**Constraints:** `UNIQUE(rtu_station, slot)`
**Indexes:** `ix_historian_tags_tag_name`, `ix_historian_tags_rtu_station`

#### `slot_configs`
Extended slot configuration for historian/alarms.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Config ID |
| rtu_station | VARCHAR(32) | NOT NULL | RTU name |
| slot | INTEGER | NOT NULL | Slot number |
| subslot | INTEGER | DEFAULT 1 | Subslot (for complex modules) |
| slot_type | VARCHAR(16) | NOT NULL | AI, AO, DI, DO |
| name | VARCHAR(64) | NULL | Human-readable name |
| unit | VARCHAR(16) | NULL | Engineering unit |
| measurement_type | VARCHAR(32) | NULL | level, flow, temp, pressure |
| actuator_type | VARCHAR(32) | NULL | pump, valve, vfd |
| scale_min | FLOAT | DEFAULT 0 | Scale min |
| scale_max | FLOAT | DEFAULT 100 | Scale max |
| alarm_low | FLOAT | NULL | Low alarm setpoint |
| alarm_high | FLOAT | NULL | High alarm setpoint |
| alarm_low_low | FLOAT | NULL | Low-low alarm setpoint |
| alarm_high_high | FLOAT | NULL | High-high alarm setpoint |
| warning_low | FLOAT | NULL | Low warning setpoint |
| warning_high | FLOAT | NULL | High warning setpoint |
| deadband | FLOAT | DEFAULT 0 | Alarm deadband |
| enabled | BOOLEAN | DEFAULT TRUE | Config active |
| created_at | TIMESTAMP | NOT NULL | Config created |

**Constraints:** `UNIQUE(rtu_station, slot)`
**Indexes:** `ix_slot_configs_rtu_station`

---

### Control Tables

#### `pid_loops`
PID control loop configuration.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Loop ID |
| name | VARCHAR(64) | NOT NULL | Loop name |
| enabled | BOOLEAN | DEFAULT TRUE | Loop active |
| input_rtu | VARCHAR(32) | NOT NULL | PV source RTU |
| input_slot | INTEGER | NOT NULL | PV source slot |
| output_rtu | VARCHAR(32) | NOT NULL | CV output RTU |
| output_slot | INTEGER | NOT NULL | CV output slot |
| kp | FLOAT | DEFAULT 1.0 | Proportional gain |
| ki | FLOAT | DEFAULT 0.0 | Integral gain |
| kd | FLOAT | DEFAULT 0.0 | Derivative gain |
| setpoint | FLOAT | DEFAULT 0 | Target value |
| output_min | FLOAT | DEFAULT 0 | Min output |
| output_max | FLOAT | DEFAULT 100 | Max output |
| deadband | FLOAT | DEFAULT 0 | Setpoint deadband |
| integral_limit | FLOAT | DEFAULT 100 | Anti-windup limit |
| derivative_filter | FLOAT | DEFAULT 0.1 | Derivative filter coefficient |
| mode | VARCHAR(16) | DEFAULT AUTO | MANUAL, AUTO, CASCADE |
| created_at | TIMESTAMP | NOT NULL | Loop created |
| updated_at | TIMESTAMP | NOT NULL | Last update |

**Indexes:** `ix_pid_loops_name`, `ix_pid_loops_input_rtu`, `ix_pid_loops_output_rtu`

---

### Diagnostics Tables

#### `profinet_diagnostics`
PROFINET communication diagnostics.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Diagnostic ID |
| rtu_id | INTEGER | FK → rtus.id | Related RTU |
| timestamp | TIMESTAMP | NOT NULL | Event time |
| level | VARCHAR(16) | DEFAULT INFO | INFO, WARNING, ERROR |
| source | VARCHAR(32) | NOT NULL | AR, CYCLE, IO, etc. |
| message | VARCHAR(256) | NOT NULL | Diagnostic message |
| details | JSON | NULL | Additional details |

**Indexes:** `ix_profinet_diag_rtu_time`, `ix_profinet_diag_level`

---

## API Endpoints

### Base URLs

- **API v1:** `/api/v1`
- **Health:** `/health`
- **Metrics:** `/metrics`
- **WebSocket:** `/ws/live`

### Authentication

#### POST `/api/v1/auth/login`
Authenticate user and create session.

**Request:**
```json
{
  "username": "operator",
  "password": "wtc_password"
}
```

**Response:**
```json
{
  "token": "abc123...",
  "username": "operator",
  "role": "operator",
  "expires_at": "2026-01-17T20:00:00Z"
}
```

#### POST `/api/v1/auth/logout`
End current session.

**Headers:** `Authorization: Bearer <token>`

**Response:** `200 OK`

#### GET `/api/v1/auth/session`
Get current session info.

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "username": "operator",
  "role": "operator",
  "created_at": "2026-01-17T12:00:00Z",
  "expires_at": "2026-01-17T20:00:00Z"
}
```

---

### RTU Management

#### GET `/api/v1/rtus`
List all configured RTUs.

**Response:**
```json
[
  {
    "id": 1,
    "station_name": "water-treat-rtu-1",
    "ip_address": "192.168.1.10",
    "vendor_id": "0x002A",
    "device_id": "0x0405",
    "slot_count": 8,
    "state": "RUNNING",
    "state_since": "2026-01-17T10:00:00Z",
    "last_error": null,
    "rtu_version": "1.0.0"
  }
]
```

#### POST `/api/v1/rtus`
Add new RTU.

**Request:**
```json
{
  "station_name": "water-treat-rtu-2",
  "ip_address": "192.168.1.11",
  "vendor_id": "0x002A",
  "device_id": "0x0405",
  "slot_count": 16
}
```

**Response:** `200 OK` with RTU object

#### GET `/api/v1/rtus/{station_name}`
Get RTU details.

**Response:** RTU object

#### PUT `/api/v1/rtus/{station_name}`
Update RTU configuration.

**Request:**
```json
{
  "ip_address": "192.168.1.12",
  "slot_count": 16
}
```

**Response:** `200 OK`

#### DELETE `/api/v1/rtus/{station_name}`
Remove RTU.

**Requires:** RTU must be in OFFLINE or ERROR state

**Response:** `200 OK`

#### POST `/api/v1/rtus/{station_name}/connect`
Establish PROFINET connection.

**Response:** `200 OK`

**Side Effects:**
- RTU state: OFFLINE → CONNECTING → RUNNING
- Triggers slot discovery
- Creates default slot/sensor/control entries

#### POST `/api/v1/rtus/{station_name}/disconnect`
Disconnect from RTU.

**Response:** `200 OK`

**Side Effects:**
- RTU state: RUNNING → OFFLINE
- Preserves configuration

#### GET `/api/v1/rtus/{station_name}/health`
Get RTU health status.

**Response:**
```json
{
  "state": "RUNNING",
  "uptime_seconds": 3600,
  "cycle_time_ms": 1000,
  "connected_slots": 8,
  "total_slots": 8,
  "errors": []
}
```

---

### Sensors

#### GET `/api/v1/rtus/{station_name}/sensors`
Get all sensor readings from RTU.

**Response:**
```json
[
  {
    "tag": "pH_SENSOR_1",
    "slot": 1,
    "channel": 0,
    "sensor_type": "pH",
    "value": 7.2,
    "unit": "pH",
    "quality": "GOOD",
    "timestamp": "2026-01-17T12:00:00Z"
  }
]
```

#### GET `/api/v1/sensors/{tag}`
Get sensor by tag.

**Response:** Sensor object

---

### Controls/Actuators

#### GET `/api/v1/rtus/{station_name}/actuators`
Get all actuator states from RTU.

**Response:**
```json
[
  {
    "tag": "PUMP_1",
    "slot": 9,
    "channel": 0,
    "control_type": "discrete",
    "equipment_type": "pump",
    "command": "ON",
    "forced": false
  }
]
```

#### POST `/api/v1/rtus/{station_name}/actuators/{slot}`
Send command to actuator.

**Request:**
```json
{
  "command": "ON"
}
```

or for PWM:
```json
{
  "command": "PWM",
  "pwm_duty": 75
}
```

**Response:** `200 OK`

**Errors:**
- `403` if actuator is interlocked by RTU

---

### Alarms

#### GET `/api/v1/alarms`
Get active alarms.

**Query Params:**
- `severity`: Filter by severity (LOW, MEDIUM, HIGH, CRITICAL)
- `rtu_station`: Filter by RTU
- `state`: Filter by state (ACTIVE, ACKNOWLEDGED, CLEARED)

**Response:**
```json
[
  {
    "id": 1,
    "alarm_rule_id": 5,
    "rtu_station": "water-treat-rtu-1",
    "slot": 1,
    "state": "ACTIVE",
    "severity": "HIGH",
    "message": "pH High Alarm",
    "value_at_activation": 8.5,
    "activated_at": "2026-01-17T11:30:00Z",
    "acknowledged_at": null,
    "acknowledged_by": null
  }
]
```

#### GET `/api/v1/alarms/history`
Get alarm history.

**Query Params:**
- `start`: Start timestamp (ISO 8601)
- `end`: End timestamp (ISO 8601)
- `severity`: Filter by severity
- `limit`: Max results (default 100)

**Response:** Array of alarm events

#### POST `/api/v1/alarms/{alarm_id}/acknowledge`
Acknowledge an alarm.

**Request:**
```json
{
  "note": "Maintenance scheduled"
}
```

**Response:** `200 OK`

#### GET `/api/v1/alarms/rules`
List alarm rules.

**Response:**
```json
[
  {
    "id": 5,
    "name": "pH High Alarm",
    "rtu_station": "water-treat-rtu-1",
    "slot": 1,
    "condition": ">",
    "threshold": 8.5,
    "severity": "HIGH",
    "delay_ms": 5000,
    "message": "pH value exceeds safe operating range",
    "enabled": true
  }
]
```

#### POST `/api/v1/alarms/rules`
Create alarm rule.

**Request:** AlarmRule object (see above)

**Response:** `200 OK` with created rule

#### GET `/api/v1/alarms/rules/{rule_id}`
Get specific alarm rule.

#### PUT `/api/v1/alarms/rules/{rule_id}`
Update alarm rule.

#### DELETE `/api/v1/alarms/rules/{rule_id}`
Delete alarm rule.

---

### PID Control

#### GET `/api/v1/rtus/{station_name}/pid`
List PID loops for RTU.

**Response:**
```json
{
  "data": [
    {
      "id": 1,
      "name": "pH Control Loop",
      "enabled": true,
      "input_rtu": "water-treat-rtu-1",
      "input_slot": 1,
      "output_rtu": "water-treat-rtu-1",
      "output_slot": 9,
      "kp": 1.0,
      "ki": 0.1,
      "kd": 0.05,
      "setpoint": 7.0,
      "output_min": 0,
      "output_max": 100,
      "mode": "AUTO"
    }
  ]
}
```

#### POST `/api/v1/rtus/{station_name}/pid`
Create PID loop.

**Request:** PIDLoop object

#### GET `/api/v1/rtus/{station_name}/pid/{loop_id}`
Get PID loop details.

#### PUT `/api/v1/rtus/{station_name}/pid/{loop_id}`
Update PID loop.

#### DELETE `/api/v1/rtus/{station_name}/pid/{loop_id}`
Delete PID loop.

#### PUT `/api/v1/rtus/{station_name}/pid/{loop_id}/setpoint`
Update PID setpoint only.

**Request:**
```json
{
  "setpoint": 7.5
}
```

#### PUT `/api/v1/rtus/{station_name}/pid/{loop_id}/mode`
Update PID mode.

**Request:**
```json
{
  "mode": "MANUAL"
}
```

#### PUT `/api/v1/rtus/{station_name}/pid/{loop_id}/tuning`
Update PID tuning parameters.

**Request:**
```json
{
  "kp": 1.5,
  "ki": 0.2,
  "kd": 0.1
}
```

---

### Historian/Trends

#### GET `/api/v1/trends/tags`
List historian tags.

**Response:**
```json
[
  {
    "id": 1,
    "rtu_station": "water-treat-rtu-1",
    "slot": 1,
    "tag_name": "pH_TREND",
    "unit": "pH",
    "sample_rate_ms": 1000,
    "deadband": 0.1,
    "compression": "swinging_door"
  }
]
```

#### POST `/api/v1/trends/tags`
Create historian tag.

**Request:** HistorianTag object

#### GET `/api/v1/trends/{tag_id}`
Get trend data for tag.

**Query Params:**
- `start`: Start timestamp (ISO 8601, required)
- `end`: End timestamp (ISO 8601, required)
- `aggregation`: none, avg, min, max, first, last (default: none)
- `interval`: Aggregation interval (e.g., "1m", "5m", "1h")

**Response:**
```json
{
  "tag_id": 1,
  "tag_name": "pH_TREND",
  "start_time": "2026-01-17T00:00:00Z",
  "end_time": "2026-01-17T12:00:00Z",
  "data": [
    {
      "time": "2026-01-17T00:00:00Z",
      "value": 7.0,
      "quality": "GOOD"
    },
    {
      "time": "2026-01-17T00:01:00Z",
      "value": 7.1,
      "quality": "GOOD"
    }
  ]
}
```

#### GET `/api/v1/trends/stats`
Get historian storage statistics.

**Response:**
```json
{
  "total_samples": 1000000,
  "oldest_sample": "2026-01-01T00:00:00Z",
  "newest_sample": "2026-01-17T12:00:00Z",
  "total_tags": 50,
  "database_size_mb": 250
}
```

---

### System

#### GET `/health`
System health check (no auth required).

**Response:**
```json
{
  "status": "ok",
  "subsystems": {
    "database": {
      "status": "ok",
      "latency_ms": 5
    },
    "ipc": {
      "status": "ok",
      "controller_connected": true
    }
  }
}
```

#### GET `/api/v1/system/status`
Detailed system status.

**Response:**
```json
{
  "status": "healthy",
  "uptime_seconds": 86400,
  "cycle_time_ms": 1000,
  "connected_rtus": 2,
  "total_rtus": 2,
  "active_alarms": 0,
  "cpu_usage": 15.5,
  "memory_usage": 45.2
}
```

#### GET `/api/v1/system/config`
Export system configuration as JSON.

**Response:** Complete system config

#### POST `/api/v1/system/config`
Import system configuration.

**Request:** JSON config object

**Response:** `200 OK`

#### POST `/api/v1/system/backup`
Create and download backup ZIP.

**Response:** `application/zip` file

**Content:**
- `config.json`: All configuration tables
- `historian.sql`: Time-series data (optional)
- `metadata.json`: Backup info

#### POST `/api/v1/system/restore`
Restore from backup ZIP.

**Content-Type:** `multipart/form-data`

**Request:**
```
file: <backup.zip>
```

**Response:**
```json
{
  "success": true,
  "restored_tables": ["rtus", "sensors", "controls", "alarm_rules"],
  "warnings": []
}
```

---

## WebSocket API

### Connection

**URL:** `ws://<controller-ip>:8000/ws/live`

**Protocol:** WebSocket

**Auth:** Not required (read-only access)

### Message Format

All messages are JSON:

```json
{
  "type": "sensor_update",
  "data": {
    "rtu": "water-treat-rtu-1",
    "slot": 1,
    "tag": "pH_SENSOR_1",
    "value": 7.2,
    "quality": "GOOD",
    "timestamp": "2026-01-17T12:00:00Z"
  }
}
```

### Message Types

| Type | Description | Data Fields |
|------|-------------|-------------|
| `sensor_update` | Sensor value changed | rtu, slot, tag, value, quality, timestamp |
| `actuator_update` | Actuator state changed | rtu, slot, tag, command, pwm_duty, forced |
| `alarm_raised` | New alarm activated | alarm_id, rtu_station, slot, severity, message |
| `alarm_acknowledged` | Alarm acknowledged | alarm_id, acknowledged_by |
| `alarm_cleared` | Alarm cleared | alarm_id |
| `rtu_connected` | RTU connected | station_name, ip_address |
| `rtu_disconnected` | RTU disconnected | station_name, reason |
| `rtu_state_change` | RTU state changed | station_name, old_state, new_state, reason |

### Example Client

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/live');

ws.onopen = () => {
  console.log('Connected to live data stream');
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log(`[${msg.type}]`, msg.data);

  switch(msg.type) {
    case 'sensor_update':
      updateSensorDisplay(msg.data);
      break;
    case 'alarm_raised':
      showAlarmNotification(msg.data);
      break;
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Disconnected, reconnecting in 5s...');
  setTimeout(() => connectWebSocket(), 5000);
};
```

---

## Data Models

### User Roles

| Role | Access |
|------|--------|
| `viewer` | Read-only access to sensors, alarms, trends |
| `operator` | Viewer + acknowledge alarms, manual actuator control |
| `admin` | Full access including user management, system config |

### RTU States

| State | Description | Can Connect | Can Disconnect | Can Delete |
|-------|-------------|-------------|----------------|------------|
| OFFLINE | No connection | Yes | No | Yes |
| CONNECTING | Establishing AR | No | Yes | No |
| DISCOVERY | Enumerating modules | No | Yes | No |
| RUNNING | Normal operation | No | Yes | No |
| ERROR | Communication failure | Yes | Yes | Yes |

### Alarm States

| State | Description | Can Acknowledge | Can Clear |
|-------|-------------|-----------------|-----------|
| ACTIVE | Alarm condition exists | Yes | Auto (when value returns to normal) |
| ACKNOWLEDGED | Operator aware | N/A | Auto |
| CLEARED | Condition resolved | N/A | N/A |

### Data Quality

| Quality | Description | OPC UA Equivalent |
|---------|-------------|-------------------|
| GOOD | Valid data | 0x00 |
| UNCERTAIN | Questionable | 0x40 |
| BAD | Invalid/stale | 0x80 |

---

## Response Codes

| Code | Meaning | When |
|------|---------|------|
| 200 | OK | Success |
| 201 | Created | Resource created |
| 400 | Bad Request | Invalid parameters |
| 401 | Unauthorized | No/invalid token |
| 403 | Forbidden | Insufficient permissions or interlocked |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Duplicate resource |
| 500 | Internal Error | Server error |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WTC_DB_HOST` | `localhost` | Database host |
| `WTC_DB_PORT` | `5432` | Database port |
| `WTC_DB_USER` | `wtc` | Database user |
| `WTC_DB_PASSWORD` | `wtc_password` | Database password |
| `WTC_DB_NAME` | `water_treatment` | Database name |
| `DATABASE_URL` | - | Full connection string (overrides above) |
| `WTC_API_PORT` | `8000` | API server port |
| `WTC_LOG_LEVEL` | `INFO` | Logging level |
| `WTC_LOG_STRUCTURED` | `false` | JSON logging |

---

## Notes

### TimescaleDB Integration

For production deployments, `historian_samples` should be converted to a hypertable:

```sql
SELECT create_hypertable('historian_samples', 'timestamp',
  chunk_time_interval => INTERVAL '1 day');
```

### Data Retention

Configure retention policies:

```sql
SELECT add_retention_policy('historian_samples',
  INTERVAL '90 days');
```

### Indexes

Critical indexes for performance:
- `historian_samples(sensor_id, timestamp)` - Time-range queries
- `alarm_events(state, activated_at)` - Active alarm queries
- `audit_log(timestamp, user)` - Audit queries

### Passwords

**IMPORTANT:** Default password `wtc_password` is HARDCODED for dev/test. Not for production use.

---

**Last Updated:** 2026-01-17
**Document Version:** 1.0.0
**API Version:** v1
