<!--
  DOCUMENT CLASS: Development (Developer Reference)

  This document describes the REST API.

  TODO: This should be auto-generated from FastAPI.
  Run: python -c "from web.api.main import app; import json; print(json.dumps(app.openapi()))"
-->

# Water Treatment Controller - OpenAPI Specification

**Document ID:** WT-API-001
**Version:** 1.0.0
**Last Updated:** 2024-12-22

---

## Overview

This document provides the OpenAPI 3.0 specification for the Water Treatment Controller REST API. The API provides programmatic access to RTU management, sensor data, actuator control, alarms, historian, and system configuration.

**Base URL:** `http://<controller-ip>:8000/api/v1`

---

## Authentication

The API uses session-based authentication with Bearer tokens.

### Login

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "operator",
  "password": "secure_password"
}
```

**Response:**
```json
{
  "token": "abc123...",
  "username": "operator",
  "role": "operator",
  "groups": ["operators"],
  "expires_at": "2024-12-23T12:00:00Z"
}
```

### Using the Token

Include the token in subsequent requests:

```http
Authorization: Bearer abc123...
```

### Roles

| Role | Access Level |
|------|--------------|
| `viewer` | Read-only access to sensors, alarms, trends |
| `operator` | Viewer + acknowledge alarms, manual actuator control |
| `engineer` | Operator + PID tuning, alarm rules, slot configuration |
| `admin` | Full access including user management, system config |

---

## OpenAPI 3.0 Specification

```yaml
openapi: 3.0.3
info:
  title: Water Treatment Controller API
  description: PROFINET IO Controller for Water Treatment RTU Network
  version: 1.0.0
  license:
    name: GPL-3.0-or-later
    url: https://www.gnu.org/licenses/gpl-3.0.html
  contact:
    name: Water Treatment Controller Project
    url: https://github.com/mwilco03/Water-Controller

servers:
  - url: http://localhost:8000/api/v1
    description: Local development server
  - url: http://{controller_ip}:8000/api/v1
    description: Production controller (API port 8000)
    variables:
      controller_ip:
        default: "192.168.1.100"
        description: Controller IP address

tags:
  - name: RTUs
    description: RTU device management and communication
  - name: Sensors
    description: Sensor data reading
  - name: Actuators
    description: Actuator control
  - name: Alarms
    description: Alarm management (ISA-18.2 compliant)
  - name: PID Control
    description: PID loop configuration and tuning
  - name: Historian
    description: Time-series data storage and retrieval
  - name: Modbus
    description: Modbus gateway configuration
  - name: System
    description: System configuration and health
  - name: Authentication
    description: User authentication and session management
  - name: Users
    description: User management

components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      description: Session token from /auth/login

  schemas:
    RTUDevice:
      type: object
      required:
        - station_name
        - ip_address
        - vendor_id
        - device_id
        - connection_state
        - slot_count
      properties:
        station_name:
          type: string
          description: PROFINET station name
          example: "water-treat-rtu-1"
        ip_address:
          type: string
          format: ipv4
          example: "192.168.1.10"
        vendor_id:
          type: integer
          example: 65535
        device_id:
          type: integer
          example: 1
        connection_state:
          type: string
          enum: [IDLE, CONNECTING, CONNECTED, RUNNING, ERROR, OFFLINE]
        slot_count:
          type: integer
          example: 16
        last_seen:
          type: string
          format: date-time

    SensorData:
      type: object
      required:
        - slot
        - name
        - value
        - unit
        - status
        - timestamp
      properties:
        slot:
          type: integer
          example: 1
        name:
          type: string
          example: "pH Sensor"
        value:
          type: number
          format: float
          example: 7.2
        unit:
          type: string
          example: "pH"
        status:
          type: string
          enum: [GOOD, UNCERTAIN, BAD, NOT_CONNECTED]
        quality:
          type: integer
          description: Raw quality byte (0x00=GOOD, 0x40=UNCERTAIN, 0x80=BAD, 0xC0=NOT_CONNECTED)
          example: 0
        timestamp:
          type: string
          format: date-time

    ActuatorState:
      type: object
      required:
        - slot
        - name
        - command
        - pwm_duty
        - forced
      properties:
        slot:
          type: integer
          example: 9
        name:
          type: string
          example: "Dosing Pump"
        command:
          type: string
          enum: [OFF, ON, PWM]
        pwm_duty:
          type: integer
          minimum: 0
          maximum: 100
          example: 50
        forced:
          type: boolean
          description: True if actuator is forced by RTU interlock

    ActuatorCommand:
      type: object
      required:
        - command
      properties:
        command:
          type: string
          enum: [OFF, ON, PWM]
        pwm_duty:
          type: integer
          minimum: 0
          maximum: 100
          default: 0

    AlarmRule:
      type: object
      required:
        - rtu_station
        - slot
        - condition
        - threshold
        - severity
        - message
      properties:
        rule_id:
          type: integer
          readOnly: true
        rtu_station:
          type: string
          example: "water-treat-rtu-1"
        slot:
          type: integer
          example: 1
        condition:
          type: string
          enum: [HIGH, LOW, HIGH_HIGH, LOW_LOW, RATE_OF_CHANGE]
        threshold:
          type: number
          format: float
          example: 8.5
        severity:
          type: string
          enum: [LOW, MEDIUM, HIGH, CRITICAL, EMERGENCY]
        delay_ms:
          type: integer
          default: 0
          description: Delay before alarm activates (debounce)
        message:
          type: string
          example: "pH High Alarm"
        enabled:
          type: boolean
          default: true

    Alarm:
      type: object
      properties:
        alarm_id:
          type: integer
        rule_id:
          type: integer
        rtu_station:
          type: string
        slot:
          type: integer
        severity:
          type: string
        state:
          type: string
          enum: [RAISED, ACKNOWLEDGED, CLEARED, RESET]
        message:
          type: string
        value:
          type: number
        threshold:
          type: number
        raise_time:
          type: string
          format: date-time
        ack_time:
          type: string
          format: date-time
        clear_time:
          type: string
          format: date-time
        ack_user:
          type: string

    PIDLoop:
      type: object
      required:
        - name
        - input_rtu
        - input_slot
        - output_rtu
        - output_slot
        - kp
        - ki
        - kd
        - setpoint
      properties:
        loop_id:
          type: integer
          readOnly: true
        name:
          type: string
          example: "pH Control Loop"
        enabled:
          type: boolean
          default: true
        input_rtu:
          type: string
          example: "water-treat-rtu-1"
        input_slot:
          type: integer
          example: 1
        output_rtu:
          type: string
          example: "water-treat-rtu-1"
        output_slot:
          type: integer
          example: 9
        kp:
          type: number
          format: float
          example: 1.0
        ki:
          type: number
          format: float
          example: 0.1
        kd:
          type: number
          format: float
          example: 0.05
        setpoint:
          type: number
          format: float
          example: 7.0
        output_min:
          type: number
          default: 0.0
        output_max:
          type: number
          default: 100.0
        mode:
          type: string
          enum: [AUTO, MANUAL]
          default: AUTO
        pv:
          type: number
          description: Process variable (current reading)
          readOnly: true
        cv:
          type: number
          description: Control variable (current output)
          readOnly: true

    HistorianTag:
      type: object
      required:
        - rtu_station
        - slot
        - tag_name
      properties:
        tag_id:
          type: integer
          readOnly: true
        rtu_station:
          type: string
        slot:
          type: integer
        tag_name:
          type: string
        sample_rate_ms:
          type: integer
          default: 1000
        deadband:
          type: number
          description: Minimum change to record
        enabled:
          type: boolean
          default: true

    TrendData:
      type: object
      properties:
        tag_id:
          type: integer
        tag_name:
          type: string
        start_time:
          type: string
          format: date-time
        end_time:
          type: string
          format: date-time
        data:
          type: array
          items:
            type: object
            properties:
              time:
                type: string
                format: date-time
              value:
                type: number
              quality:
                type: integer

    SystemHealth:
      type: object
      properties:
        status:
          type: string
          enum: [healthy, degraded, unhealthy]
        uptime_seconds:
          type: integer
        cycle_time_ms:
          type: number
        connected_rtus:
          type: integer
        total_rtus:
          type: integer
        active_alarms:
          type: integer
        cpu_usage:
          type: number
        memory_usage:
          type: number

    BackupMetadata:
      type: object
      properties:
        backup_id:
          type: string
        filename:
          type: string
        created_at:
          type: string
          format: date-time
        size_bytes:
          type: integer
        description:
          type: string
        includes_historian:
          type: boolean

    ModbusRegisterMapping:
      type: object
      properties:
        mapping_id:
          type: integer
        modbus_addr:
          type: integer
        register_type:
          type: string
          enum: [INPUT, HOLDING, COIL, DISCRETE]
        data_type:
          type: string
          enum: [INT16, UINT16, INT32, UINT32, FLOAT32]
        source_type:
          type: string
          enum: [PROFINET_SENSOR, PROFINET_ACTUATOR, PID_LOOP]
        rtu_station:
          type: string
        slot:
          type: integer

    Error:
      type: object
      properties:
        detail:
          type: string

paths:
  # ============== RTU Management ==============
  /rtus:
    get:
      summary: List all configured RTUs
      tags: [RTUs]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: List of RTU devices
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/RTUDevice'
    post:
      summary: Add a new RTU
      tags: [RTUs]
      security:
        - BearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - station_name
              properties:
                station_name:
                  type: string
                ip_address:
                  type: string
                vendor_id:
                  type: integer
                device_id:
                  type: integer
      responses:
        '200':
          description: RTU created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/RTUDevice'
        '409':
          description: RTU already exists

  /rtus/{station_name}:
    get:
      summary: Get RTU details
      tags: [RTUs]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: RTU details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/RTUDevice'
        '404':
          description: RTU not found
    put:
      summary: Update RTU configuration
      tags: [RTUs]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                ip_address:
                  type: string
                vendor_id:
                  type: integer
                device_id:
                  type: integer
      responses:
        '200':
          description: RTU updated
    delete:
      summary: Remove RTU
      tags: [RTUs]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: RTU removed

  /rtus/{station_name}/connect:
    post:
      summary: Establish PROFINET connection
      tags: [RTUs]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Connection initiated

  /rtus/{station_name}/disconnect:
    post:
      summary: Disconnect from RTU
      tags: [RTUs]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Disconnected

  /rtus/{station_name}/health:
    get:
      summary: Get RTU health status
      tags: [RTUs]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Health status

  # ============== Sensors ==============
  /rtus/{station_name}/sensors:
    get:
      summary: Get all sensor readings from RTU
      tags: [Sensors]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Sensor data
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/SensorData'

  # ============== Actuators ==============
  /rtus/{station_name}/actuators:
    get:
      summary: Get all actuator states from RTU
      tags: [Actuators]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Actuator states
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ActuatorState'

  /rtus/{station_name}/actuators/{slot}:
    post:
      summary: Send command to actuator
      description: |
        Send a control command to an actuator. Note that safety interlocks
        on the RTU may override commands - check the 'forced' field in the
        response to see if an interlock is active.
      tags: [Actuators]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
        - name: slot
          in: path
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ActuatorCommand'
      responses:
        '200':
          description: Command sent
        '403':
          description: Actuator is interlocked

  # ============== Alarms ==============
  /alarms:
    get:
      summary: Get active alarms
      tags: [Alarms]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Active alarms
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Alarm'

  /alarms/history:
    get:
      summary: Get alarm history
      tags: [Alarms]
      security:
        - BearerAuth: []
      parameters:
        - name: start
          in: query
          schema:
            type: string
            format: date-time
        - name: end
          in: query
          schema:
            type: string
            format: date-time
        - name: severity
          in: query
          schema:
            type: string
        - name: limit
          in: query
          schema:
            type: integer
            default: 100
      responses:
        '200':
          description: Alarm history

  /alarms/{alarm_id}/acknowledge:
    post:
      summary: Acknowledge an alarm
      tags: [Alarms]
      security:
        - BearerAuth: []
      parameters:
        - name: alarm_id
          in: path
          required: true
          schema:
            type: integer
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                user:
                  type: string
      responses:
        '200':
          description: Alarm acknowledged

  /alarms/rules:
    get:
      summary: List alarm rules
      tags: [Alarms]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Alarm rules
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/AlarmRule'
    post:
      summary: Create alarm rule
      tags: [Alarms]
      security:
        - BearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AlarmRule'
      responses:
        '200':
          description: Rule created

  /alarms/rules/{rule_id}:
    get:
      summary: Get alarm rule
      tags: [Alarms]
      security:
        - BearerAuth: []
      parameters:
        - name: rule_id
          in: path
          required: true
          schema:
            type: integer
      responses:
        '200':
          description: Alarm rule
    put:
      summary: Update alarm rule
      tags: [Alarms]
      security:
        - BearerAuth: []
      parameters:
        - name: rule_id
          in: path
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AlarmRule'
      responses:
        '200':
          description: Rule updated
    delete:
      summary: Delete alarm rule
      tags: [Alarms]
      security:
        - BearerAuth: []
      parameters:
        - name: rule_id
          in: path
          required: true
          schema:
            type: integer
      responses:
        '200':
          description: Rule deleted

  # ============== PID Control (Per-RTU) ==============
  # Note: PID loops are scoped to individual RTUs
  /rtus/{station_name}/pid:
    get:
      summary: List PID loops for an RTU
      tags: [PID Control]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: PID loops for the RTU
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items:
                      $ref: '#/components/schemas/PIDLoop'
    post:
      summary: Create PID loop for an RTU
      tags: [PID Control]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PIDLoop'
      responses:
        '201':
          description: Loop created

  /rtus/{station_name}/pid/{loop_id}:
    get:
      summary: Get PID loop details
      tags: [PID Control]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
        - name: loop_id
          in: path
          required: true
          schema:
            type: integer
      responses:
        '200':
          description: PID loop
    put:
      summary: Update PID loop
      tags: [PID Control]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
        - name: loop_id
          in: path
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PIDLoop'
      responses:
        '200':
          description: Loop updated
    delete:
      summary: Delete PID loop
      tags: [PID Control]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
        - name: loop_id
          in: path
          required: true
          schema:
            type: integer
      responses:
        '200':
          description: Loop deleted

  /rtus/{station_name}/pid/{loop_id}/setpoint:
    put:
      summary: Update PID setpoint
      tags: [PID Control]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
        - name: loop_id
          in: path
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - setpoint
              properties:
                setpoint:
                  type: number
      responses:
        '200':
          description: Setpoint updated

  /rtus/{station_name}/pid/{loop_id}/mode:
    put:
      summary: Update PID mode
      tags: [PID Control]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
        - name: loop_id
          in: path
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - mode
              properties:
                mode:
                  type: string
                  enum: [AUTO, MANUAL, CASCADE]
      responses:
        '200':
          description: Mode updated

  /rtus/{station_name}/pid/{loop_id}/tuning:
    put:
      summary: Update PID tuning parameters
      tags: [PID Control]
      security:
        - BearerAuth: []
      parameters:
        - name: station_name
          in: path
          required: true
          schema:
            type: string
        - name: loop_id
          in: path
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - kp
                - ki
                - kd
              properties:
                kp:
                  type: number
                ki:
                  type: number
                kd:
                  type: number
      responses:
        '200':
          description: Tuning updated

  # ============== Historian ==============
  /trends/tags:
    get:
      summary: List historian tags
      tags: [Historian]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Tags
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/HistorianTag'
    post:
      summary: Create historian tag
      tags: [Historian]
      security:
        - BearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/HistorianTag'
      responses:
        '200':
          description: Tag created

  /trends/{tag_id}:
    get:
      summary: Get trend data
      tags: [Historian]
      security:
        - BearerAuth: []
      parameters:
        - name: tag_id
          in: path
          required: true
          schema:
            type: integer
        - name: start
          in: query
          required: true
          schema:
            type: string
            format: date-time
        - name: end
          in: query
          required: true
          schema:
            type: string
            format: date-time
        - name: aggregation
          in: query
          schema:
            type: string
            enum: [none, avg, min, max, first, last]
            default: none
        - name: interval
          in: query
          schema:
            type: string
            description: Aggregation interval (e.g., "1m", "5m", "1h")
      responses:
        '200':
          description: Trend data
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TrendData'

  /trends/stats:
    get:
      summary: Get historian statistics
      tags: [Historian]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Storage statistics

  # ============== System ==============
  /system/health:
    get:
      summary: Get system health status
      tags: [System]
      responses:
        '200':
          description: Health status
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SystemHealth'

  /system/config:
    get:
      summary: Export system configuration
      tags: [System]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Full configuration JSON
    post:
      summary: Import system configuration
      tags: [System]
      security:
        - BearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
      responses:
        '200':
          description: Configuration imported

  # ============== Backup/Restore ==============
  # Note: Backups are created and returned immediately (no server-side storage)
  /system/:
    post:
      summary: Create and download backup
      description: |
        Creates a backup of the current configuration and immediately returns it
        as a ZIP file. There is no server-side backup storage - the backup is
        streamed directly to the client for download.
      tags: [System]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Backup ZIP file
          content:
            application/zip:
              schema:
                type: string
                format: binary

  /system/restore:
    post:
      summary: Restore from backup file
      description: |
        Restores the system configuration from an uploaded backup ZIP file.
        This will overwrite the current configuration.
      tags: [System]
      security:
        - BearerAuth: []
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              required:
                - file
              properties:
                file:
                  type: string
                  format: binary
                  description: Backup ZIP file to restore
      responses:
        '200':
          description: Restore completed
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  error:
                    type: string

  # ============== Modbus ==============
  /modbus/config:
    get:
      summary: Get Modbus gateway configuration
      tags: [Modbus]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Modbus config
    put:
      summary: Update Modbus gateway configuration
      tags: [Modbus]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Config updated

  /modbus/mappings:
    get:
      summary: List register mappings
      tags: [Modbus]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Mappings
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ModbusRegisterMapping'
    post:
      summary: Create register mapping
      tags: [Modbus]
      security:
        - BearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ModbusRegisterMapping'
      responses:
        '200':
          description: Mapping created

  /modbus/stats:
    get:
      summary: Get Modbus gateway statistics
      tags: [Modbus]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Gateway statistics

  # ============== Authentication ==============
  /auth/login:
    post:
      summary: Authenticate user
      tags: [Authentication]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - username
                - password
              properties:
                username:
                  type: string
                password:
                  type: string
                  format: password
      responses:
        '200':
          description: Login successful
          content:
            application/json:
              schema:
                type: object
                properties:
                  token:
                    type: string
                  username:
                    type: string
                  role:
                    type: string
                  expires_at:
                    type: string
                    format: date-time
        '401':
          description: Invalid credentials

  /auth/logout:
    post:
      summary: End session
      tags: [Authentication]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Logged out

  /auth/session:
    get:
      summary: Get current session info
      tags: [Authentication]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Session info

  # ============== Users ==============
  /users:
    get:
      summary: List users
      tags: [Users]
      security:
        - BearerAuth: []
      responses:
        '200':
          description: User list
    post:
      summary: Create user
      tags: [Users]
      security:
        - BearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - username
                - password
                - role
              properties:
                username:
                  type: string
                password:
                  type: string
                role:
                  type: string
                  enum: [viewer, operator, engineer, admin]
      responses:
        '200':
          description: User created

  /users/{user_id}:
    get:
      summary: Get user details
      tags: [Users]
      security:
        - BearerAuth: []
      parameters:
        - name: user_id
          in: path
          required: true
          schema:
            type: integer
      responses:
        '200':
          description: User details
    put:
      summary: Update user
      tags: [Users]
      security:
        - BearerAuth: []
      parameters:
        - name: user_id
          in: path
          required: true
          schema:
            type: integer
      responses:
        '200':
          description: User updated
    delete:
      summary: Delete user
      tags: [Users]
      security:
        - BearerAuth: []
      parameters:
        - name: user_id
          in: path
          required: true
          schema:
            type: integer
      responses:
        '200':
          description: User deleted

security:
  - BearerAuth: []
```

---

## Quick Reference

### Common Operations

| Operation | Method | Endpoint |
|-----------|--------|----------|
| List RTUs | GET | `/rtus` |
| Get sensor data | GET | `/rtus/{station}/sensors` |
| Control actuator | POST | `/rtus/{station}/controls/{tag}/command` |
| Get active alarms | GET | `/alarms` |
| Acknowledge alarm | POST | `/alarms/{id}/acknowledge` |
| List PID loops | GET | `/rtus/{station}/pid` |
| Update setpoint | PUT | `/rtus/{station}/pid/{loop_id}/setpoint` |
| Get trend data | GET | `/trends/{tag_id}?start=...&end=...` |
| System health | GET | `/health` |
| System status | GET | `/system/status` |
| Create backup | POST | `/system/` (returns ZIP) |
| Restore backup | POST | `/system/restore` (multipart/form-data) |

### Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (invalid parameters) |
| 401 | Authentication required |
| 403 | Insufficient permissions |
| 404 | Resource not found |
| 409 | Conflict (duplicate resource) |
| 500 | Internal server error |

---

## WebSocket API

Real-time updates are available via WebSocket at `ws://<controller-ip>:8000/api/v1/ws/live`.

### Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ws/live');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  // Backend sends 'channel', frontend may use 'type'
  const type = message.type || message.channel;
  console.log(type, message.data);
};
```

### Message Types

| Type | Description |
|------|-------------|
| `sensor_update` | Sensor value changed |
| `actuator_update` | Actuator state changed |
| `alarm_raised` | New alarm |
| `alarm_cleared` | Alarm cleared |
| `rtu_connected` | RTU connected |
| `rtu_disconnected` | RTU disconnected |

### Example Message

```json
{
  "type": "sensor_update",
  "data": {
    "rtu": "water-treat-rtu-1",
    "slot": 1,
    "value": 7.2,
    "quality": 0,
    "timestamp": "2024-12-22T10:30:00Z"
  }
}
```

---

*This specification follows OpenAPI 3.0 standards. For machine-readable format, extract the YAML block above.*
