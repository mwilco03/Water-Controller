# Alarm Rules Architecture Decision

## Overview

This document discusses the architectural decision for where alarm rules should be implemented in the Water Treatment Controller/RTU system.

## The Question

**Where should alarm rules live: Controller, RTU (Sensor), or Both?**

## Analysis

### Option 1: Alarm Rules on RTU Only

**Pros:**
- Immediate response time - alarms evaluated at data source
- Works even if controller connection is lost
- Reduces network traffic - only sends alarm states
- Local safety interlocks can act instantly

**Cons:**
- Limited coordination between multiple RTUs
- Each RTU needs configuration interface
- Hard to implement cross-RTU conditions
- More complex RTU firmware

**Best for:** Safety-critical alarms that need immediate local action

### Option 2: Alarm Rules on Controller Only

**Pros:**
- Centralized configuration and management
- Cross-RTU alarm conditions possible
- Easier to implement complex logic
- Single point of configuration
- Full visibility into all process data

**Cons:**
- Dependent on network connectivity
- Latency added to alarm detection
- Single point of failure
- Safety interlocks may be too slow

**Best for:** Process optimization alarms, cross-system coordination

### Option 3: Blended Approach (Recommended)

This is the recommended architecture that provides defense-in-depth:

```
┌─────────────────────────────────────────────────────────────────┐
│                      CONTROLLER                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Alarm Manager (Supervisory)                              │   │
│  │ - Cross-RTU alarm conditions                            │   │
│  │ - Complex logic (rate-of-change, deviation)             │   │
│  │ - Alarm shelving, suppression rules                     │   │
│  │ - Historical analysis and reporting                     │   │
│  │ - Alarm with Interlock option (forces actuator via IPC) │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                     │
│                   PROFINET/Modbus                                │
│                            │                                     │
└────────────────────────────│─────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│     RTU-1     │    │     RTU-2     │    │     RTU-3     │
│ ┌───────────┐ │    │ ┌───────────┐ │    │ ┌───────────┐ │
│ │ Watchdog  │ │    │ │ Watchdog  │ │    │ │ Watchdog  │ │
│ │ Interlocks│ │    │ │ Interlocks│ │    │ │ Interlocks│ │
│ └───────────┘ │    │ └───────────┘ │    │ └───────────┘ │
│ - High/Low    │    │ - High/Low    │    │ - High/Low    │
│   cutoffs     │    │   cutoffs     │    │   cutoffs     │
│ - Sensor fail │    │ - Sensor fail │    │ - Sensor fail │
│   failsafe    │    │   failsafe    │    │   failsafe    │
└───────────────┘    └───────────────┘    └───────────────┘
```

## Implementation Strategy

### 1. RTU-Level (Water-Treat): Safety Watchdogs

The RTU implements hardware-level safety watchdogs that cannot be overridden by the controller:

```c
// On RTU: src/safety/watchdog.c

typedef struct {
    int slot;
    float high_cutoff;      // Above this, force actuator OFF
    float low_cutoff;       // Below this, force actuator OFF (freeze protection)
    int target_actuator;    // Which actuator to control
    bool allow_controller_override; // false for safety-critical
} watchdog_rule_t;

// Example: Tank level high - turn off inlet pump
// This runs locally even if controller connection is lost
```

**RTU watchdogs handle:**
- High-high and low-low cutoffs (immediate safety)
- Sensor failure detection (bad quality → failsafe)
- Communication loss failsafe (controller heartbeat timeout)
- Equipment protection (motor overload, overheat)

### 2. Controller-Level (Water-Controller): Process Alarms

The controller implements process-level alarms with optional interlock actions:

```c
// On Controller: src/alarms/alarm_rules.c

typedef struct {
    int rule_id;
    char name[64];
    char rtu_station[64];
    int slot;
    alarm_condition_t condition;  // HIGH, LOW, HIGH_HIGH, RATE_OF_CHANGE, etc.
    float threshold;
    uint32_t delay_ms;
    alarm_severity_t severity;

    // Optional interlock action
    bool interlock_enabled;
    char target_rtu[64];
    int target_slot;
    interlock_action_t interlock_action; // FORCE_OFF, FORCE_ON, SET_VALUE
    float interlock_value;
    bool auto_release;  // Release when alarm clears
} alarm_rule_t;
```

**Controller alarms handle:**
- Process deviations (PH out of range, temperature drift)
- Pre-warnings (approaching limit, trending toward alarm)
- Cross-RTU conditions (if tank A level high AND pump B running)
- Rate-of-change alarms (sudden level drop = leak detection)
- Operator notifications and acknowledgment

### 3. Interlock Coordination

When a controller alarm has an interlock action configured:

```
                Controller Alarm Triggers
                         │
                         ▼
            ┌────────────────────────┐
            │ Interlock Configured?  │
            └───────────┬────────────┘
                        │ Yes
                        ▼
            ┌────────────────────────┐
            │ Send force command to  │
            │ RTU via PROFINET/IPC   │
            └───────────┬────────────┘
                        │
                        ▼
            ┌────────────────────────┐
            │ RTU receives command:  │
            │ "Force slot 9 OFF"     │
            └───────────┬────────────┘
                        │
                        ▼
            ┌────────────────────────┐
            │ RTU locks actuator     │
            │ until release command  │
            │ OR controller timeout  │
            └────────────────────────┘
```

### 4. Configuration Persistence

Both systems store their configurations in their respective databases:

**RTU Database (SQLite on RTU):**
```sql
CREATE TABLE watchdog_rules (
    id INTEGER PRIMARY KEY,
    slot INTEGER NOT NULL,
    high_cutoff REAL,
    low_cutoff REAL,
    target_actuator INTEGER NOT NULL,
    failsafe_state TEXT DEFAULT 'OFF',
    enabled INTEGER DEFAULT 1
);
```

**Controller Database (SQLite on Controller):**
```sql
CREATE TABLE alarm_rules (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    rtu_station TEXT NOT NULL,
    slot INTEGER NOT NULL,
    condition TEXT NOT NULL,
    threshold REAL NOT NULL,
    severity TEXT NOT NULL,
    delay_ms INTEGER DEFAULT 0,
    message TEXT,
    enabled INTEGER DEFAULT 1,
    -- Interlock extension
    interlock_enabled INTEGER DEFAULT 0,
    target_rtu TEXT,
    target_slot INTEGER,
    interlock_action TEXT,
    interlock_value REAL,
    auto_release INTEGER DEFAULT 1
);
```

## Example: Tank Level Protection

### RTU Watchdog (Safety Layer)
```json
{
  "slot": 7,
  "description": "Tank 1 Level",
  "high_cutoff": 95.0,
  "low_cutoff": 5.0,
  "target_actuator": 9,
  "failsafe_state": "OFF",
  "allow_controller_override": false
}
```
- If level > 95% → IMMEDIATELY turn off inlet pump (slot 9)
- If level < 5% → IMMEDIATELY turn off outlet pump to prevent dry run
- Controller CANNOT override this (safety critical)

### Controller Alarm (Process Layer)
```json
{
  "name": "Tank 1 High Level Warning",
  "rtu_station": "water-treat-rtu-1",
  "slot": 7,
  "condition": "HIGH",
  "threshold": 85.0,
  "severity": "MEDIUM",
  "delay_ms": 10000,
  "message": "Tank 1 level approaching high limit",
  "interlock_enabled": true,
  "target_rtu": "water-treat-rtu-1",
  "target_slot": 9,
  "interlock_action": "FORCE_OFF",
  "auto_release": true
}
```
- If level > 85% for 10 seconds → Raise warning alarm
- Optionally force inlet pump OFF (with 10s delay for gradual control)
- Auto-release when level drops below threshold
- This is the "soft" protection before the "hard" RTU watchdog

## UI Configuration

The web interface provides separate views for each layer:

### RTU Configuration (via RTU web interface or Controller proxy)
```
┌─────────────────────────────────────────────────────────┐
│ RTU Safety Watchdogs                                     │
├─────────────────────────────────────────────────────────┤
│ Slot │ Description    │ High Cutoff │ Low Cutoff │ Act │
│───────────────────────────────────────────────────────  │
│  7   │ Tank Level     │    95%      │    5%      │  9  │
│  3   │ Temperature    │    80°C     │    0°C     │ 11  │
│  2   │ pH             │    14.0     │    0.0     │ 12  │
└─────────────────────────────────────────────────────────┘
```

### Controller Alarm Rules (web/ui/src/app/alarms/rules/page.tsx)
```
┌─────────────────────────────────────────────────────────────────┐
│ Alarm Rules                                     [+ Add Rule]    │
├─────────────────────────────────────────────────────────────────┤
│ Name               │ Source        │ Condition │ Interlock     │
│─────────────────────────────────────────────────────────────────│
│ Tank 1 High        │ RTU-1:Slot 7  │ > 85%     │ Force OFF:9   │
│ Temperature High   │ RTU-1:Slot 3  │ > 60°C    │ Alarm Only    │
│ pH Low             │ RTU-1:Slot 2  │ < 6.5     │ Force OFF:12  │
└─────────────────────────────────────────────────────────────────┘
```

## Summary

| Feature | RTU (Water-Treat) | Controller (Water-Controller) |
|---------|------------------|-------------------------------|
| Response Time | Immediate (<10ms) | Depends on scan rate (~1s) |
| Network Independent | Yes | No |
| Cross-RTU Logic | No | Yes |
| Complex Conditions | No | Yes (rate-of-change, deviation) |
| Safety Critical | Yes | No (process optimization) |
| Configuration UI | Local TUI/API | Web HMI |
| Override by Controller | Configurable | N/A |

## Recommendation

1. **Always implement safety-critical cutoffs on the RTU** as watchdogs that cannot be overridden
2. **Use controller alarms for process optimization** with optional interlock actions
3. **Document the alarm philosophy** for each installation
4. **Test both layers** during commissioning
5. **Regular review** of alarm setpoints and interlock configurations
