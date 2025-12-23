# Water-Controller HMI Portal Analysis

## Comprehensive SCADA Operator-First Design Review

**Analysis Date:** 2025-12-23
**Version:** 1.0
**Platform:** Next.js 14 + React 18 / FastAPI Backend

---

## 1. SCREEN MAP

```
                                    +------------------+
                                    |   LOGIN PAGE     |
                                    |   /login         |
                                    +--------+---------+
                                             |
                                             v
+-----------------------------------------------------------------------------------+
|                              MAIN APPLICATION LAYOUT                               |
|  +-----------------------------------------------------------------------------+  |
|  |  COMMAND MODE BANNER (when active - orange/yellow countdown)                |  |
|  +-----------------------------------------------------------------------------+  |
|  |  NAVIGATION BAR                                                              |  |
|  |  [Dashboard] [RTUs] [Alarms] [Trends] [Control] [Config v] [System]         |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
         |            |          |          |          |          |          |
         v            v          v          v          v          v          v
    +--------+   +--------+  +--------+  +--------+  +--------+  +--------+  +--------+
    |DASHBOARD|  | RTUs   |  |ALARMS  |  |TRENDS  |  |CONTROL |  |CONFIG  |  |SYSTEM  |
    |   /     |  | /rtus  |  |/alarms |  |/trends |  |/control|  |dropdown|  |/system |
    +--------+   +----+---+  +--------+  +--------+  +--------+  +---+----+  +--------+
                      |                                              |
                      v                                              |
              +----------------+                     +---------------+---------------+
              | RTU DETAIL     |                     |               |               |
              | /rtus/[name]   |                     v               v               v
              +----------------+               +---------+    +---------+    +---------+
                                               | I/O Tags|    | Network |    | Users   |
                                               |/io-tags |    |/network |    |/users   |
                                               +---------+    +---------+    +---------+
                                                     |
                                                     v
                                               +---------+    +---------+
                                               |Settings |    | Modbus  |
                                               |/settings|    |/modbus  |
                                               +---------+    +---------+

                              +------------------+
                              |  SETUP WIZARD    |
                              |    /wizard       |
                              | (7-step process) |
                              +------------------+
```

### Navigation Flow Summary

| From | To | Trigger |
|------|----|----|
| Any Page | Login | Session expired / Unauthorized |
| Login | Dashboard | Successful authentication |
| Dashboard | RTU Detail | Click RTU card |
| Dashboard | Alarms | Click alarm summary |
| RTU List | RTU Detail | Click "Details" button |
| RTU Detail | Trends | Click "View Trends" quick link |
| RTU Detail | Alarms | Click "View Alarms" quick link |
| RTU Detail | Control | Click "PID Control" quick link |
| Config Dropdown | Settings/Network/Users/IO-Tags | Menu selection |

---

## 2. SCREEN CATALOG

### 2.1 Login Page (`/login`)

```
+------------------------------------------------------------------+
|                         WATER CONTROLLER                          |
|                              LOGIN                                |
+------------------------------------------------------------------+
|                                                                   |
|                    [Logo/Title Area]                              |
|                                                                   |
|            +----------------------------------+                   |
|            | Username                         |                   |
|            +----------------------------------+                   |
|                                                                   |
|            +----------------------------------+                   |
|            | Password                         |                   |
|            +----------------------------------+                   |
|                                                                   |
|            +----------------------------------+                   |
|            |         [Sign In]                |                   |
|            +----------------------------------+                   |
|                                                                   |
|            [Error Message Display Area]                           |
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** Authenticate operators before accessing the HMI

**Data Displayed:**
- Login form
- Error messages on failed authentication

**Inputs:**
| Input | Type | Validation | Confirmation |
|-------|------|------------|--------------|
| Username | Text | Required | None |
| Password | Password | Required | None |
| Sign In | Button | N/A | Loading state |

**SCADA Compliance:**
- [COMPLIANT] Clear purpose identification
- [COMPLIANT] Error feedback on failure
- [MISSING] Account lockout indicator
- [MISSING] Session timeout warning

---

### 2.2 Dashboard (`/`)

```
+------------------------------------------------------------------+
|  COMMAND MODE BANNER (if active)                                  |
+------------------------------------------------------------------+
|  NAVIGATION: [Dashboard*] [RTUs] [Alarms] [Trends] [Control] ... |
+------------------------------------------------------------------+
|                                                                   |
|  +------------------+  +------------------+  +------------------+ |
|  | SYSTEM STATUS    |  | RTU STATUS       |  | ALARM SUMMARY   | |
|  | Connection: OK   |  | Online: 3        |  | Critical: 0     | |
|  | RTUs: 3          |  | Offline: 1       |  | Warning: 2      | |
|  | Alarms: 2        |  | Connecting: 0    |  | Info: 5         | |
|  | Time: HH:MM:SS   |  |                  |  |                 | |
|  +------------------+  +------------------+  +------------------+ |
|                                                                   |
|  +--------------------------------------------------------------+|
|  | RTU OVERVIEW TABLE                                            ||
|  | Status | Station Name | IP Address      | Slots | Actions    ||
|  |--------|--------------|-----------------|-------|------------|
|  | [*]    | WaterPlant1  | 192.168.1.100   | 4     | [Details]  ||
|  | [*]    | PumpStation  | 192.168.1.101   | 2     | [Details]  ||
|  +--------------------------------------------------------------+|
|                                                                   |
|  +--------------------------------------------------------------+|
|  | RECENT ALARMS                                                 ||
|  | [!] High Level Tank 1 - 2 min ago                  [ACK]     ||
|  | [!] Pump 2 Overcurrent - 15 min ago                [ACK]     ||
|  +--------------------------------------------------------------+|
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** Primary operator overview of entire system state

**Data Displayed:**
- System connection status
- RTU online/offline count
- Active alarm count by severity
- Current system time (real-time clock)
- RTU device table with states
- Recent alarm summary

**Real-time Updates:**
- WebSocket: `rtu_update`, `sensor_update`, `alarm_raised`, `alarm_cleared`
- Fallback: 5-second polling interval

**SCADA Compliance:**
- [COMPLIANT] At-a-glance system overview
- [COMPLIANT] Real-time clock display
- [COMPLIANT] Alarm severity color coding
- [COMPLIANT] Quick navigation to detailed views
- [MISSING] Last update timestamp display

---

### 2.3 RTU List (`/rtus`)

```
+------------------------------------------------------------------+
|  NAVIGATION: [Dashboard] [RTUs*] [Alarms] [Trends] [Control] ... |
+------------------------------------------------------------------+
|                                                                   |
|  RTU NETWORK STATUS                                              |
|  +--------------------------------------------------------------+|
|  | Status | Station Name  | IP Address      | Slots | Actions   ||
|  |--------|---------------|-----------------|-------|-----------|
|  | [*] ON | WaterPlant1   | 192.168.1.100   | 4     |[Det][Rec]||
|  | [*] ON | PumpStation   | 192.168.1.101   | 2     |[Det][Rec]||
|  | [!]OFF | TankFarm      | 192.168.1.102   | 6     |[Det][Rec]||
|  +--------------------------------------------------------------+|
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** View all RTU devices and their connection states

**Data Displayed:**
- Device connection status (RUNNING/CONNECTING/DISCOVERY/ERROR/OFFLINE)
- Station name, IP address, slot count

**Inputs:**
| Input | Type | Action |
|-------|------|--------|
| Details | Link | Navigate to RTU detail page |
| Reconnect | Button | Trigger RTU reconnection |

**Status Indicators:**
- Green (online) = RUNNING
- Yellow (connecting) = CONNECTING, DISCOVERY
- Red (offline) = ERROR, other

---

### 2.4 RTU Detail (`/rtus/[station_name]`)

```
+------------------------------------------------------------------+
|  [<Back] WaterPlant1 [*RUNNING]              [Live/Polling]      |
+------------------------------------------------------------------+
|                                                                   |
|  +--------------------------------------------------------------+|
|  | INVENTORY REFRESH                                             ||
|  | Last refresh: 2024-01-15 10:30:00    [Refresh Inventory]     ||
|  +--------------------------------------------------------------+|
|                                                                   |
|  +----------+  +----------+  +----------+  +----------+          |
|  | 4        |  | 12       |  | 6        |  | 3        |          |
|  | Slots    |  | Sensors  |  | Controls |  | Active   |          |
|  +----------+  +----------+  +----------+  +----------+          |
|                                                                   |
|  [Overview*] [Sensors (12)] [Controls (6)]                       |
|  +--------------------------------------------------------------+|
|                                                                   |
|  OVERVIEW TAB:                                                   |
|  Device Information:                                              |
|  +-------------+-------------+-------------+-------------+       |
|  |Vendor ID    |Device ID    |State        |Slots        |       |
|  |0x0123       |0x0456       |RUNNING      |4            |       |
|  +-------------+-------------+-------------+-------------+       |
|                                                                   |
|  Sensors Preview:              Controls Preview:                 |
|  [Gauge][Gauge][Gauge]...      [Switch][Switch]...               |
|  [View all ->]                 [View all ->]                     |
|                                                                   |
|  Quick Links: [View Trends] [View Alarms] [PID Control]          |
|                                                                   |
+------------------------------------------------------------------+

|  SENSORS TAB:                                                    |
|  +--------------------------------------------------------------+|
|  | Grouped by Type                                               ||
|  | TEMPERATURE                                                   ||
|  | [Gauge: 23.5°C] [Gauge: 24.1°C] [Gauge: 22.8°C]              ||
|  | PRESSURE                                                      ||
|  | [Gauge: 2.3 bar] [Gauge: 2.1 bar]                            ||
|  | LEVEL                                                         ||
|  | [Tank: 75%] [Tank: 82%]                                       ||
|  +--------------------------------------------------------------+|

|  CONTROLS TAB:                                                   |
|  +--------------------------------------------------------------+|
|  | VIEW MODE NOTICE (if not in command mode)                     ||
|  | [!] View Mode Active - Enter Command Mode to control          ||
|  |                                    [Enter Command Mode]       ||
|  +--------------------------------------------------------------+|
|  | Grouped by Type                                               ||
|  | PUMPS                                                         ||
|  | [Pump 1: OFF] [Pump 2: ON] [Pump 3: OFF]                     ||
|  | VALVES                                                        ||
|  | [Valve 1: CLOSED] [Valve 2: OPEN]                             ||
|  +--------------------------------------------------------------+|
```

**Purpose:** Detailed view and control of a single RTU

**Data Displayed:**
- RTU state, IP, vendor/device IDs
- Sensor values with quality indicators
- Control states (ON/OFF, OPEN/CLOSED)
- Slot/sensor/control counts

**Inputs:**
| Input | Type | Requires Command Mode | Confirmation |
|-------|------|----------------------|--------------|
| Refresh Inventory | Button | No | Loading state |
| Tab Selection | Tabs | No | Immediate switch |
| Control Toggle | Switch/Button | **Yes** | State change animation |
| View Trends | Link | No | Navigation |
| View Alarms | Link | No | Navigation |

**SCADA Compliance:**
- [COMPLIANT] Command mode requirement for control
- [COMPLIANT] Grouped sensor display
- [COMPLIANT] Quality indicator on gauges
- [MISSING] Confirmation dialog for control actions

---

### 2.5 Alarms Page (`/alarms`)

```
+------------------------------------------------------------------+
|  NAVIGATION: [Dashboard] [RTUs] [Alarms*] [Trends] [Control] ... |
+------------------------------------------------------------------+
|                                                                   |
|  ALARM MANAGEMENT                                                |
|  +--------------------------------------------------------------+|
|  | Filter: [All] [Active] [Unacknowledged]     [Acknowledge All]||
|  +--------------------------------------------------------------+|
|  | Sev | Alarm                    | Time        | State  | Act  ||
|  |-----|--------------------------|-------------|--------|------|
|  |[!!] | Tank 1 High Level        | 10:30:15    | ACTIVE | [ACK]||
|  |[!]  | Pump 2 Overcurrent       | 10:25:00    | ACTIVE | [ACK]||
|  |[i]  | Flow Meter Calibration   | 10:20:00    | CLEARED| [ACK]||
|  +--------------------------------------------------------------+|
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** View, filter, and acknowledge alarms

**Data Displayed:**
- Alarm severity (critical/emergency = red, warning = yellow, info = blue)
- Alarm message, timestamp, state
- Filter counts

**Inputs:**
| Input | Type | Action | Confirmation |
|-------|------|--------|--------------|
| Filter tabs | Tab | Filter alarm list | Immediate |
| Acknowledge | Button | Acknowledge single alarm | Button state change |
| Acknowledge All | Button | Acknowledge all visible | Button state change |

**Alarm States (ISA-18.2):**
- `ACTIVE_UNACK` - Active, needs acknowledgment
- `CLEARED_UNACK` - Cleared but unacknowledged
- `ACTIVE_ACK` - Active, acknowledged
- `CLEARED_ACK` - Cleared and acknowledged

**SCADA Compliance:**
- [COMPLIANT] ISA-18.2 alarm states
- [COMPLIANT] Severity color coding
- [COMPLIANT] Batch acknowledgment
- [MISSING] Alarm shelving capability
- [MISSING] Alarm history pagination

---

### 2.6 Trends Page (`/trends`)

```
+------------------------------------------------------------------+
|  NAVIGATION: [Dashboard] [RTUs] [Alarms] [Trends*] [Control] ... |
+------------------------------------------------------------------+
|                                                                   |
|  HISTORICAL TRENDS                                               |
|  +--------------------------------------------------------------+|
|  | RTU: [Select RTU v]  Sensor: [Select Sensor v]               ||
|  | Time Range: [1h] [6h] [24h] [7d] [Custom...]                 ||
|  +--------------------------------------------------------------+|
|                                                                   |
|  +--------------------------------------------------------------+|
|  |                    TREND CHART                                ||
|  |  ^                                                            ||
|  |  |     /\    /\                                              ||
|  |  |    /  \  /  \    /\                                       ||
|  |  |   /    \/    \  /  \                                      ||
|  |  +-------------------------------------------->               ||
|  |   10:00  10:15  10:30  10:45  11:00                          ||
|  +--------------------------------------------------------------+|
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** View historical sensor data trends

**Data Displayed:**
- Selectable RTU and sensor
- Time-series chart
- Value axis with units
- Time axis

**Inputs:**
| Input | Type | Action |
|-------|------|--------|
| RTU Selector | Dropdown | Filter sensors |
| Sensor Selector | Dropdown | Select data source |
| Time Range | Button group | Adjust time window |
| Custom Range | Date picker | Custom time bounds |

**SCADA Compliance:**
- [COMPLIANT] Historical data access
- [COMPLIANT] Adjustable time ranges
- [MISSING] Multi-sensor overlay
- [MISSING] Export functionality
- [MISSING] Trend zoom/pan

---

### 2.7 Control Page (`/control`)

```
+------------------------------------------------------------------+
|  NAVIGATION: [Dashboard] [RTUs] [Alarms] [Trends] [Control*] ... |
+------------------------------------------------------------------+
|                                                                   |
|  PID CONTROL                                                     |
|  +--------------------------------------------------------------+|
|  | Select RTU: [WaterPlant1 v]                                  ||
|  +--------------------------------------------------------------+|
|                                                                   |
|  +------------------------+  +--------------------------------+ |
|  | PID Controller         |  | Response Graph                 | |
|  | Setpoint: [____] %     |  |  ^                             | |
|  | Kp: [____]             |  |  |   SP  ---                   | |
|  | Ki: [____]             |  |  |  PV  /   \                  | |
|  | Kd: [____]             |  |  | ----      ---               | |
|  |                        |  |  +------------------>          | |
|  | [Apply Settings]       |  |                                 | |
|  +------------------------+  +--------------------------------+ |
|                                                                   |
|  +--------------------------------------------------------------+|
|  | Manual Override: [ ] Enable                                  ||
|  | Output: [====|====] 50%                                      ||
|  +--------------------------------------------------------------+|
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** Configure and monitor PID control loops

**Data Displayed:**
- Current PID parameters (Kp, Ki, Kd)
- Setpoint and process variable
- Control output
- Response visualization

**Inputs:**
| Input | Type | Requires Command Mode | Validation |
|-------|------|----------------------|------------|
| RTU Selector | Dropdown | No | N/A |
| Setpoint | Number | **Yes** | Range check |
| Kp/Ki/Kd | Number | **Yes** | Range check |
| Apply Settings | Button | **Yes** | Confirmation dialog |
| Manual Override | Checkbox | **Yes** | Toggle |
| Manual Output | Slider | **Yes** | 0-100% |

**SCADA Compliance:**
- [COMPLIANT] Command mode for changes
- [COMPLIANT] Visual process feedback
- [UNCLEAR] Parameter change logging
- [MISSING] Auto/Manual mode indication

---

### 2.8 Settings Page (`/settings`)

```
+------------------------------------------------------------------+
|  SETTINGS                                                        |
+------------------------------------------------------------------+
|                                                                   |
|  System Configuration                                            |
|  +--------------------------------------------------------------+|
|  | Polling Interval: [5] seconds                                ||
|  | WebSocket Reconnect: [3000] ms                               ||
|  | Command Mode Timeout: [5] minutes                            ||
|  +--------------------------------------------------------------+|
|                                                                   |
|  Display Options                                                 |
|  +--------------------------------------------------------------+|
|  | Theme: [Dark v]                                              ||
|  | Date Format: [YYYY-MM-DD v]                                  ||
|  | Temperature Unit: [Celsius v]                                ||
|  +--------------------------------------------------------------+|
|                                                                   |
|  [Save Settings]                                                 |
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** Configure application settings

**Inputs:**
| Input | Type | Validation | Requires Auth |
|-------|------|------------|---------------|
| Polling Interval | Number | Min 1 second | Yes (admin) |
| Reconnect Interval | Number | Min 1000ms | Yes (admin) |
| Theme | Dropdown | Enum | No |
| Save Settings | Button | N/A | Yes |

---

### 2.9 Network Page (`/network`)

```
+------------------------------------------------------------------+
|  NETWORK CONFIGURATION                                           |
+------------------------------------------------------------------+
|                                                                   |
|  Network Scan                                                    |
|  +--------------------------------------------------------------+|
|  | IP Range: [192.168.1.0/24]              [Start Scan]         ||
|  +--------------------------------------------------------------+|
|                                                                   |
|  Discovered Devices                                              |
|  +--------------------------------------------------------------+|
|  | IP Address      | MAC Address       | Type    | Action       ||
|  |-----------------|-------------------|---------|--------------|
|  | 192.168.1.100   | AA:BB:CC:DD:EE:01 | PROFINET| [Add RTU]   ||
|  | 192.168.1.101   | AA:BB:CC:DD:EE:02 | PROFINET| [Add RTU]   ||
|  +--------------------------------------------------------------+|
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** Discover and configure network devices

**Inputs:**
| Input | Type | Action | Confirmation |
|-------|------|--------|--------------|
| IP Range | Text | Set scan range | Validation |
| Start Scan | Button | Initiate network scan | Loading state |
| Add RTU | Button | Add discovered device | Navigation to wizard |

---

### 2.10 Users Page (`/users`)

```
+------------------------------------------------------------------+
|  USER MANAGEMENT                                                 |
+------------------------------------------------------------------+
|                                                                   |
|  Users                                         [+ Add User]      |
|  +--------------------------------------------------------------+|
|  | Username    | Role     | Last Login        | Actions         ||
|  |-------------|----------|-------------------|-----------------|
|  | admin       | admin    | 2024-01-15 09:00  | [Edit] [Delete] ||
|  | operator1   | operator | 2024-01-15 10:30  | [Edit] [Delete] ||
|  | viewer1     | viewer   | 2024-01-14 14:00  | [Edit] [Delete] ||
|  +--------------------------------------------------------------+|
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** Manage user accounts and roles

**Roles:**
- `admin` - Full system access
- `operator` - Can enter command mode
- `viewer` - View only

**Inputs:**
| Input | Type | Requires | Action |
|-------|------|----------|--------|
| Add User | Button | Admin | Open user form |
| Edit | Button | Admin | Open user form |
| Delete | Button | Admin | Confirmation dialog |

---

### 2.11 I/O Tags Page (`/io-tags`)

```
+------------------------------------------------------------------+
|  I/O TAG CONFIGURATION                                           |
+------------------------------------------------------------------+
|                                                                   |
|  +--------------------------------------------------------------+|
|  | RTU: [All v]  Type: [All v]  Search: [________]              ||
|  +--------------------------------------------------------------+|
|                                                                   |
|  +--------------------------------------------------------------+|
|  | Tag Name     | Type   | RTU        | Address | Scale | Unit  ||
|  |--------------|--------|------------|---------|-------|-------|
|  | TankLevel1   | AI     | WaterPlant | %IW0    | 0.1   | %     ||
|  | Pump1Status  | DI     | WaterPlant | %I0.0   | 1     | -     ||
|  | Pump1Cmd     | DO     | WaterPlant | %Q0.0   | 1     | -     ||
|  +--------------------------------------------------------------+|
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** Configure I/O tag mappings

**Data Displayed:**
- Tag name, type (AI/AO/DI/DO)
- Associated RTU
- Memory address, scaling, units

---

### 2.12 Modbus Page (`/modbus`)

```
+------------------------------------------------------------------+
|  MODBUS CONFIGURATION                                            |
+------------------------------------------------------------------+
|                                                                   |
|  Modbus Slaves                                [+ Add Slave]      |
|  +--------------------------------------------------------------+|
|  | Name        | Address | Port  | Protocol | Status | Actions  ||
|  |-------------|---------|-------|----------|--------|----------|
|  | FlowMeter1  | 1       | 502   | TCP      | [OK]   |[E][D][T] ||
|  | PowerMeter  | 2       | 502   | TCP      | [ERR]  |[E][D][T] ||
|  +--------------------------------------------------------------+|
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** Configure Modbus device connections

---

### 2.13 System Page (`/system`)

```
+------------------------------------------------------------------+
|  SYSTEM STATUS                                                   |
+------------------------------------------------------------------+
|                                                                   |
|  Backend Services                                                |
|  +--------------------------------------------------------------+|
|  | Service          | Status | Uptime    | Memory  | Actions    ||
|  |------------------|--------|-----------|---------|------------|
|  | FastAPI          | [OK]   | 5d 12h    | 256 MB  | [Restart]  ||
|  | PROFINET Driver  | [OK]   | 5d 12h    | 128 MB  | [Restart]  ||
|  | WebSocket Server | [OK]   | 5d 12h    | 64 MB   | [Restart]  ||
|  | Database         | [OK]   | 5d 12h    | 512 MB  | [Restart]  ||
|  +--------------------------------------------------------------+|
|                                                                   |
|  System Logs                                                     |
|  +--------------------------------------------------------------+|
|  | 10:30:15 [INFO] RTU WaterPlant1 connected                    ||
|  | 10:30:10 [WARN] Sensor calibration due                       ||
|  | 10:29:55 [INFO] User operator1 entered command mode          ||
|  +--------------------------------------------------------------+|
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** Monitor system health and services

---

### 2.14 Setup Wizard (`/wizard`)

```
+------------------------------------------------------------------+
|  RTU SETUP WIZARD                                                |
+------------------------------------------------------------------+
|                                                                   |
|  Progress: [1]--[2]--[3]--[4]--[5]--[6]--[7]                    |
|           Welcome Add  Connect Discover Config Test Complete     |
|                   RTU                                            |
|                                                                   |
|  Step 2: Add RTU                                                 |
|  +--------------------------------------------------------------+|
|  | Station Name: [________________]                              ||
|  | IP Address:   [________________]                              ||
|  | Slot Count:   [4 v]                                          ||
|  |                                                               ||
|  |                            [Back] [Next]                      ||
|  +--------------------------------------------------------------+|
|                                                                   |
+------------------------------------------------------------------+
```

**Purpose:** Guided RTU setup process

**Steps:**
1. Welcome - Introduction
2. Add RTU - Enter station details
3. Connect - Establish PROFINET connection
4. Discover - Auto-discover sensors/controls
5. Configure - Set tag names and scaling
6. Test - Verify communication
7. Complete - Summary and finish

---

## 3. WORKFLOW DIAGRAMS

### 3.1 Authentication Flow

```
+--------+     +------------+     +-------------+     +-----------+
| User   |---->| Login Page |---->| POST /login |---->| Validate  |
+--------+     +------------+     +-------------+     +-----------+
                                                           |
                    +--------------------------------------+
                    |                                      |
                    v                                      v
            +--------------+                      +----------------+
            | Store Token  |                      | Show Error     |
            | Set Session  |                      | "Invalid creds"|
            +--------------+                      +----------------+
                    |
                    v
            +---------------+
            | Redirect to   |
            | Dashboard     |
            +---------------+
```

**Session Details:**
- JWT token stored in HTTP-only cookie
- Session validated on each API request
- Automatic redirect to login on 401

---

### 3.2 Alarm Response Workflow

```
+-------------+     +----------------+     +------------------+
| Alarm Raised|---->| WebSocket Push |---->| UI Notification  |
| (backend)   |     | alarm_raised   |     | Update Dashboard |
+-------------+     +----------------+     +------------------+
                                                    |
                                                    v
                                           +------------------+
                                           | Operator Views   |
                                           | Alarm Details    |
                                           +------------------+
                                                    |
                                                    v
                                           +------------------+
                                           | Click [ACK]      |
                                           +------------------+
                                                    |
                                                    v
                                           +------------------+
                                           | POST /alarms/    |
                                           | {id}/acknowledge |
                                           +------------------+
                                                    |
                                                    v
                                           +------------------+
                                           | WebSocket Push   |
                                           | alarm_ack        |
                                           | Update UI        |
                                           +------------------+
```

**Alarm States (ISA-18.2):**
```
NORMAL --> ACTIVE_UNACK --> ACTIVE_ACK
                |               |
                v               v
        CLEARED_UNACK --> CLEARED_ACK --> NORMAL
```

---

### 3.3 Manual Actuator Control Workflow

```
+----------+     +-------------------+     +------------------+
| Operator |---->| View Mode Active  |---->| Cannot Control   |
+----------+     | (default state)   |     | Buttons Disabled |
     |           +-------------------+     +------------------+
     |
     v
+-------------------+     +-------------------+     +------------------+
| Click "Enter      |---->| Login Dialog      |---->| Validate User    |
| Command Mode"     |     | Username/Password |     | Check Role       |
+-------------------+     +-------------------+     +------------------+
                                                          |
                    +-------------------------------------+
                    |                                     |
                    v                                     v
          +------------------+               +-------------------+
          | Command Mode     |               | Error: Insufficient|
          | ACTIVE           |               | Permissions        |
          | 5 min countdown  |               +-------------------+
          +------------------+
                    |
                    v
          +------------------+     +------------------+     +------------------+
          | Control Enabled  |---->| Click Toggle/    |---->| POST /commands/  |
          | Buttons Active   |     | Button           |     | {rtu}/actuator   |
          +------------------+     +------------------+     +------------------+
                                                                   |
                                                                   v
                                                          +------------------+
                                                          | WebSocket:       |
                                                          | actuator_command |
                                                          | Update UI State  |
                                                          +------------------+
                    +------------------+
                    | 5 min timeout OR |
                    | Click Exit       |
                    +------------------+
                              |
                              v
                    +------------------+
                    | View Mode        |
                    | Controls Disabled|
                    +------------------+
```

**Command Mode Details:**
- Timeout: 5 minutes (300,000 ms)
- Activity extends timeout
- Visual countdown in banner
- Banner color changes at <60 seconds (yellow warning)
- Required role: `operator` or `admin`

---

### 3.4 Trend Analysis Workflow

```
+----------+     +-------------------+     +------------------+
| Operator |---->| Navigate to       |---->| Default View:    |
+----------+     | /trends           |     | Last 1 hour      |
                 +-------------------+     +------------------+
                                                    |
                                                    v
                                          +------------------+
                                          | Select RTU       |
                                          +------------------+
                                                    |
                                                    v
                                          +------------------+
                                          | Select Sensor    |
                                          +------------------+
                                                    |
                                                    v
                                          +------------------+
                                          | Select Time Range|
                                          | 1h/6h/24h/7d/    |
                                          | Custom           |
                                          +------------------+
                                                    |
                                                    v
                                          +------------------+
                                          | GET /trends/     |
                                          | ?sensor=X&from=  |
                                          +------------------+
                                                    |
                                                    v
                                          +------------------+
                                          | Render Chart     |
                                          +------------------+
```

---

### 3.5 RTU Reconnection Workflow

```
+-------------+     +------------------+     +------------------+
| RTU Offline |---->| Status: OFFLINE  |---->| Red indicator    |
| Detected    |     | in RTU table     |     | on dashboard     |
+-------------+     +------------------+     +------------------+
                                                      |
                                                      v
                                             +------------------+
                                             | Operator clicks  |
                                             | [Reconnect]      |
                                             +------------------+
                                                      |
                                                      v
                                             +------------------+
                                             | POST /rtus/      |
                                             | {name}/reconnect |
                                             +------------------+
                                                      |
                                                      v
                                             +------------------+
                                             | Status changes:  |
                                             | CONNECTING       |
                                             | Yellow indicator |
                                             +------------------+
                                                      |
                    +---------------------------------+
                    |                                 |
                    v                                 v
           +------------------+             +------------------+
           | Success:         |             | Failure:         |
           | RUNNING          |             | ERROR            |
           | Green indicator  |             | Red indicator    |
           +------------------+             +------------------+
                    |
                    v
           +------------------+
           | WebSocket:       |
           | rtu_update       |
           | UI refreshes     |
           +------------------+
```

---

### 3.6 Configuration Change Workflow

```
+----------+     +-------------------+     +------------------+
| Admin    |---->| Navigate to       |---->| Current Settings |
+----------+     | /settings OR      |     | Displayed        |
                 | /io-tags etc      |     +------------------+
                 +-------------------+              |
                                                   v
                                          +------------------+
                                          | Modify Values    |
                                          +------------------+
                                                   |
                                                   v
                                          +------------------+
                                          | Click [Save]     |
                                          +------------------+
                                                   |
                                                   v
                                          +------------------+
                                          | POST/PUT to API  |
                                          +------------------+
                                                   |
                    +---------------------------------+
                    |                                 |
                    v                                 v
           +------------------+             +------------------+
           | Success toast    |             | Error message    |
           | Settings saved   |             | Validation error |
           +------------------+             +------------------+
```

---

## 4. INPUT REFERENCE

### Complete Input Inventory

| Screen | Input | Type | Validation | Feedback | Keyboard | Command Mode |
|--------|-------|------|------------|----------|----------|--------------|
| **Login** |
| | Username | text | required | border highlight | Tab, Enter | N/A |
| | Password | password | required | border highlight | Tab, Enter | N/A |
| | Sign In | button | - | loading spinner | Enter | N/A |
| **Dashboard** |
| | RTU row click | link | - | hover highlight | - | No |
| | Alarm ACK | button | - | state change | - | No |
| **RTU List** |
| | Details | link | - | hover | - | No |
| | Reconnect | button | - | loading | - | No |
| **RTU Detail** |
| | Tab selection | tabs | - | immediate | - | No |
| | Refresh Inventory | button | - | loading spinner | - | No |
| | Control toggle | switch | device online | state animation | - | **Yes** |
| | Quick links | link | - | hover | - | No |
| **Alarms** |
| | Filter tabs | tabs | - | immediate | - | No |
| | Acknowledge | button | - | state change | - | No |
| | Acknowledge All | button | - | state change | - | No |
| **Trends** |
| | RTU selector | dropdown | - | immediate | - | No |
| | Sensor selector | dropdown | - | immediate | - | No |
| | Time range | buttons | - | immediate | - | No |
| | Custom range | datepicker | valid dates | - | - | No |
| **Control** |
| | RTU selector | dropdown | - | immediate | - | No |
| | Setpoint | number | range | - | - | **Yes** |
| | Kp/Ki/Kd | number | range | - | - | **Yes** |
| | Apply Settings | button | - | loading | - | **Yes** |
| | Manual override | checkbox | - | toggle | - | **Yes** |
| | Manual output | slider | 0-100 | live update | - | **Yes** |
| **Settings** |
| | Polling interval | number | min 1 | - | - | No |
| | Theme | dropdown | - | immediate | - | No |
| | Save | button | - | toast | - | Admin |
| **Network** |
| | IP range | text | CIDR format | validation | - | Admin |
| | Start scan | button | - | progress | - | Admin |
| | Add RTU | button | - | navigation | - | Admin |
| **Users** |
| | Add User | button | - | dialog | - | Admin |
| | Edit | button | - | dialog | - | Admin |
| | Delete | button | - | confirmation | - | Admin |
| **I/O Tags** |
| | Filter dropdowns | dropdown | - | immediate | - | No |
| | Search | text | - | live filter | - | No |
| **Wizard** |
| | Station name | text | required | validation | Tab | Admin |
| | IP address | text | IP format | validation | Tab | Admin |
| | Back/Next | buttons | step valid | navigation | - | Admin |
| **Command Mode Login** |
| | Username | text | required | border | Tab | N/A |
| | Password | password | required | border | Tab | N/A |
| | Enter | button | - | loading | Enter | N/A |
| | Cancel | button | - | close dialog | Escape | N/A |

---

## 5. FEEDBACK MATRIX

### Input-to-Feedback Mapping

| Input Action | Immediate Feedback | Processing Feedback | Completion Feedback | Error Feedback |
|--------------|-------------------|--------------------|--------------------|----------------|
| **Login submit** | Button disabled | "Authenticating..." text | Redirect to dashboard | Error message in form |
| **Control toggle** | Button state change | - | Visual state update | Error toast |
| **Alarm acknowledge** | Button disabled | - | Alarm row state change | Error toast |
| **RTU reconnect** | Button loading | Status → CONNECTING | Status → RUNNING | Status → ERROR |
| **Inventory refresh** | Button loading | Spinner | Updated counts | Error message |
| **Network scan** | Button loading | Progress indicator | Device list updates | Error message |
| **Settings save** | Button loading | - | Success toast | Error message |
| **PID apply** | Button loading | - | Graph updates | Error toast |
| **Filter change** | - | - | Immediate list filter | - |
| **Tab switch** | - | - | Immediate content swap | - |
| **Dropdown change** | - | - | Immediate selection | - |

### Real-Time Update Mechanisms

| Event Type | WebSocket Event | UI Update | Fallback |
|------------|-----------------|-----------|----------|
| Sensor value change | `sensor_update` | Gauge/tank animation | 5s polling |
| RTU state change | `rtu_update` | Status indicator | 5s polling |
| Alarm raised | `alarm_raised` | Dashboard counter, bell icon | 5s polling |
| Alarm cleared | `alarm_cleared` | List update | 5s polling |
| Alarm acknowledged | `alarm_acknowledged` | Row state change | 5s polling |
| Actuator command | `actuator_command` | Control state | 5s polling |
| PID update | `pid_update` | Chart update | 5s polling |
| Discovery complete | `discovery_complete` | Inventory counts | Manual refresh |
| Network scan complete | `network_scan_complete` | Device list | Manual check |

### Data Quality Indicators (ISA-101)

| Quality Code | Hex Value | Visual Indicator | Color |
|--------------|-----------|------------------|-------|
| GOOD | 0x00 | None | Green value |
| UNCERTAIN | 0x40 | "?" after label | Yellow |
| BAD | 0x80 | "X" after label | Red |
| NOT_CONNECTED | 0xC0 | "-" after label | Red |

---

## 6. COMPLIANCE ASSESSMENT

### SCADA HMI Guidelines Evaluation

| Guideline | Requirement | Status | Evidence | Gap |
|-----------|-------------|--------|----------|-----|
| **Visual Hierarchy** |
| G1.1 | At-a-glance system overview | [COMPLIANT] | Dashboard with summary cards | - |
| G1.2 | Alarm prominence | [COMPLIANT] | Color-coded severity, counter | - |
| G1.3 | Critical info above fold | [COMPLIANT] | Summary stats at top | - |
| G1.4 | Consistent layout | [COMPLIANT] | Common navigation, panels | - |
| **Color Usage** |
| G2.1 | Red = danger/alarm | [COMPLIANT] | #ef4444 for critical | - |
| G2.2 | Yellow = warning | [COMPLIANT] | #f59e0b for warning | - |
| G2.3 | Green = normal/OK | [COMPLIANT] | #10b981 for normal | - |
| G2.4 | Avoid color-only indicators | [PARTIAL] | Has text labels | Missing shape differentiation |
| G2.5 | Dark background | [COMPLIANT] | Dark theme (gray-900) | - |
| **Real-Time Updates** |
| G3.1 | Update latency < 2s | [COMPLIANT] | WebSocket push | - |
| G3.2 | Stale data indication | [PARTIAL] | Quality codes shown | No timestamp age indicator |
| G3.3 | Connection status visible | [COMPLIANT] | "Live/Polling" indicator | - |
| **Alarm Management** |
| G4.1 | ISA-18.2 compliance | [COMPLIANT] | 4-state model implemented | - |
| G4.2 | Alarm acknowledgment | [COMPLIANT] | Individual and batch ACK | - |
| G4.3 | Alarm shelving | [MISSING] | Not implemented | Add shelving feature |
| G4.4 | Alarm history | [PARTIAL] | List view only | No pagination, export |
| G4.5 | Alarm sounds | [MISSING] | No audio | Add audio notifications |
| **Operator Control** |
| G5.1 | Confirmation for critical actions | [MISSING] | No confirmation dialog | Add confirmation modals |
| G5.2 | Command mode concept | [COMPLIANT] | Explicit mode with timeout | - |
| G5.3 | Control feedback < 250ms | [COMPLIANT] | Immediate button state | - |
| G5.4 | Disable controls when offline | [COMPLIANT] | RTU state check | - |
| **Authentication** |
| G6.1 | Role-based access | [COMPLIANT] | admin/operator/viewer | - |
| G6.2 | Session timeout | [COMPLIANT] | Command mode 5 min | - |
| G6.3 | Audit logging | [UNCLEAR] | Code mentions logging | Verify implementation |
| **Keyboard/Accessibility** |
| G7.1 | Keyboard navigation | [PARTIAL] | Tab order works | Missing keyboard shortcuts |
| G7.2 | Focus indicators | [COMPLIANT] | Ring focus styles | - |
| G7.3 | Screen reader support | [UNCLEAR] | No ARIA evidence | Add ARIA labels |
| **Performance** |
| G8.1 | Page load < 3s | [UNCLEAR] | No metrics | Add performance monitoring |
| G8.2 | Smooth animations | [COMPLIANT] | CSS transitions | - |
| G8.3 | Responsive layout | [COMPLIANT] | Tailwind responsive | - |

### Timing Compliance Summary

| Operation | Requirement | Current | Status |
|-----------|-------------|---------|--------|
| WebSocket reconnect | < 5s | 3s (max 10 attempts) | [COMPLIANT] |
| Poll fallback interval | < 10s | 5s | [COMPLIANT] |
| Command mode timeout | Configurable | 5 min fixed | [PARTIAL] - should be configurable |
| Alarm update latency | < 2s | Real-time push | [COMPLIANT] |
| Control feedback | < 250ms | Immediate | [COMPLIANT] |
| Trend data load | < 5s | Depends on range | [UNCLEAR] |

---

## 7. COMPLIANCE GAPS

### Critical Gaps (Address Immediately)

| ID | Gap | Impact | Recommendation |
|----|-----|--------|----------------|
| GAP-01 | [MISSING] Confirmation dialogs for control actions | Risk of accidental actuation | Add modal confirmation for pump/valve commands |
| GAP-02 | [MISSING] Alarm audio notifications | Operators may miss critical alarms | Add configurable audio alerts |
| GAP-03 | [MISSING] Alarm shelving | Cannot suppress nuisance alarms | Implement ISA-18.2 shelving |

### Medium Priority Gaps

| ID | Gap | Impact | Recommendation |
|----|-----|--------|----------------|
| GAP-04 | [PARTIAL] No stale data age indicator | Unknown data freshness | Add "last updated X seconds ago" |
| GAP-05 | [MISSING] Keyboard shortcuts | Slower operator response | Add Ctrl+A for alarms, etc. |
| GAP-06 | [MISSING] Trend export | Cannot analyze offline | Add CSV/PDF export |
| GAP-07 | [MISSING] Multi-sensor trend overlay | Limited comparison | Add multiple trace support |
| GAP-08 | [PARTIAL] Color-only status | Accessibility concern | Add shape icons (circle/triangle/square) |

### Low Priority Gaps

| ID | Gap | Impact | Recommendation |
|----|-----|--------|----------------|
| GAP-09 | [UNCLEAR] Audit logging verification | Compliance uncertainty | Verify and document logging |
| GAP-10 | [MISSING] ARIA labels | Screen reader support | Add comprehensive ARIA |
| GAP-11 | [UNCLEAR] Performance monitoring | Unknown load times | Add performance metrics |
| GAP-12 | [PARTIAL] Fixed command mode timeout | Inflexible security | Make timeout configurable |

---

## 8. OPERATOR EXPERIENCE SUMMARY

### Strengths

1. **Clear Visual Hierarchy**
   - Dashboard provides immediate system overview
   - Summary cards show critical metrics at a glance
   - Consistent dark theme reduces eye strain

2. **Robust Real-Time Updates**
   - WebSocket for immediate data push
   - Automatic fallback to polling if WebSocket fails
   - Visual indication of connection method (Live/Polling)

3. **Strong Security Model**
   - Command Mode requires explicit authentication
   - 5-minute timeout prevents abandoned sessions
   - Role-based access (admin/operator/viewer)
   - Visual banner indicates active command mode

4. **SCADA-Appropriate Alarm Handling**
   - ISA-18.2 compliant state model
   - Severity color coding (red/yellow/blue)
   - Batch acknowledgment capability
   - Filter by state (all/active/unacknowledged)

5. **Data Quality Visibility**
   - OPC UA compatible quality codes
   - ISA-101 quality indicators (?, X, -)
   - Quality affects gauge color

6. **Guided Setup**
   - 7-step wizard for new RTU configuration
   - Progress indicator
   - Back/Next navigation

### Areas for Improvement

1. **Action Confirmation**
   - Control actions lack confirmation dialogs
   - Risk of accidental pump/valve commands
   - Recommend: Add "Are you sure?" modals

2. **Alarm Awareness**
   - No audio notifications
   - May miss critical alarms during other tasks
   - Recommend: Add configurable alarm sounds

3. **Data Staleness**
   - No visible "age" of displayed data
   - Unknown if data is current
   - Recommend: Add "Updated X seconds ago"

4. **Keyboard Efficiency**
   - No keyboard shortcuts
   - Reliance on mouse navigation
   - Recommend: Add hotkeys for common actions

5. **Trend Analysis**
   - Single sensor view only
   - No export functionality
   - Recommend: Multi-trace, CSV export

### Workflow Efficiency Score

| Workflow | Steps | Clicks | Time Est. | Rating |
|----------|-------|--------|-----------|--------|
| View system status | 1 | 0 | < 1s | Excellent |
| Acknowledge single alarm | 2 | 2 | < 3s | Good |
| Acknowledge all alarms | 2 | 2 | < 3s | Good |
| Toggle pump (from dashboard) | 4 | 4 | ~30s | Fair |
| View sensor trend | 3 | 4 | ~10s | Good |
| Add new RTU (wizard) | 7 | 15+ | ~5 min | Fair |
| Reconnect offline RTU | 2 | 2 | < 5s | Good |

### Recommended Improvements Priority

1. **High Priority** (Safety/Compliance)
   - Add confirmation dialogs for control actions
   - Add alarm audio notifications
   - Implement alarm shelving

2. **Medium Priority** (Efficiency)
   - Add keyboard shortcuts
   - Add stale data indicators
   - Add trend export/multi-trace

3. **Low Priority** (Polish)
   - Add ARIA accessibility
   - Add performance monitoring
   - Make command timeout configurable

---

## Appendix A: Component Reference

### Key UI Components

| Component | File | Purpose |
|-----------|------|---------|
| TankLevel | `components/TankLevel.tsx` | Animated water tank visualization |
| CircularGauge | `components/CircularGauge.tsx` | Radial gauge with quality indicator |
| RTUOverview | `components/RTUOverview.tsx` | RTU status table |
| AlarmSummary | `components/AlarmSummary.tsx` | Alarm list with filters |
| SystemStatus | `components/SystemStatus.tsx` | Header status bar |
| CommandModeBanner | `components/CommandModeBanner.tsx` | Command mode indicator |
| CommandModeLogin | `components/CommandModeLogin.tsx` | Command mode auth dialog |

### Key Hooks

| Hook | File | Purpose |
|------|------|---------|
| useWebSocket | `hooks/useWebSocket.ts` | Real-time data subscription |
| useCommandMode | `contexts/CommandModeContext.tsx` | Command mode state |

### API Endpoints (Referenced)

| Endpoint Pattern | Purpose |
|------------------|---------|
| POST /login | Authentication |
| GET /rtus | List RTU devices |
| GET /rtus/{name} | RTU details |
| POST /rtus/{name}/reconnect | Reconnect RTU |
| GET /rtus/{name}/inventory | Sensor/control list |
| POST /rtus/{name}/inventory/refresh | Refresh inventory |
| GET /alarms | List alarms |
| POST /alarms/{id}/acknowledge | Acknowledge alarm |
| GET /trends | Historical data |
| POST /commands/{rtu}/actuator | Send control command |

---

**Document End**
