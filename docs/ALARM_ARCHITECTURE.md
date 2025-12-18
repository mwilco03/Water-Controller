# Alarm and Interlock Architecture

## Core Principle

**Interlocks live ONLY on the RTU. The Controller generates notifications only.**

This is not negotiable for safety reasons.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      CONTROLLER (HMI)                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Alarm Manager (Notifications Only)                       │   │
│  │                                                           │   │
│  │ CAN:                                                      │   │
│  │ - Generate operator notifications (alerts, emails)       │   │
│  │ - Display interlock status (read from RTU)               │   │
│  │ - Configure RTU interlocks (push config TO RTU)          │   │
│  │ - Log interlock events to historian                      │   │
│  │ - Evaluate complex conditions (rate-of-change, trend)    │   │
│  │                                                           │   │
│  │ CANNOT:                                                   │   │
│  │ - Execute interlock logic                                │   │
│  │ - Force actuator states for safety purposes              │   │
│  │ - Override RTU interlock decisions                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                     │
│              Read status / Push config (not commands)            │
│                            │                                     │
└────────────────────────────│─────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                           RTU                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ INTERLOCK ENGINE (Authoritative - runs locally ALWAYS)  │   │
│  │                                                           │   │
│  │ - Evaluates conditions every scan cycle (<10ms)          │   │
│  │ - Forces actuator states IMMEDIATELY                     │   │
│  │ - Works with OR without controller connection            │   │
│  │ - Reports status to controller (informational only)      │   │
│  │ - Controller CANNOT override safety interlocks           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Why Interlocks Must Live on RTU

### The Failure Scenario

If interlocks lived on the controller:

```
Tank level reaches 95%
         │
Controller decides "turn off pump"
         │
         ▼
    ┌─────────┐
    │ Network │  ← Network cable unplugged
    │         │  ← Controller rebooting
    │         │  ← Controller crashed
    │         │  ← Network switch failed
    └─────────┘
         │
         X  Command never arrives
         │
    Pump keeps running
         │
    Tank overflows
```

### The Correct Behavior

With interlocks on RTU:

```
Tank level reaches 95%
         │
RTU interlock engine (local)
         │
    ┌───────────────────┐
    │ Immediate action  │  ← No network dependency
    │ Pump forced OFF   │  ← Sub-10ms response
    │ Status → Controller│  ← Informational only
    └───────────────────┘
         │
    Tank safe
```

## What Each System Does

### Controller (Water-Controller)

| Function | Description |
|----------|-------------|
| **Alarm notifications** | Alert operators when conditions exceed thresholds |
| **Display interlock status** | Show which interlocks are tripped (read from RTU) |
| **Configure RTU interlocks** | Push interlock setpoints to RTU database |
| **Log events** | Record interlock trips/resets in historian |
| **Trend analysis** | Detect patterns that predict future problems |
| **Cross-RTU monitoring** | Alert if Tank A AND Tank B both have issues |

The controller alarm rule structure:

```python
class AlarmRule:
    rule_id: int
    rtu_station: str
    slot: int
    condition: str      # HIGH, LOW, RATE_OF_CHANGE
    threshold: float
    severity: str       # LOW, MEDIUM, HIGH, EMERGENCY
    delay_ms: int
    message: str
    enabled: bool
    # NO interlock fields - that's the RTU's job
```

### RTU (Water-Treat)

| Function | Description |
|----------|-------------|
| **Interlock evaluation** | Check conditions every scan (<10ms) |
| **Actuator forcing** | Immediately force outputs when tripped |
| **Failsafe behavior** | Safe state when sensor fails or comms lost |
| **Local persistence** | Interlock config survives reboot |
| **Status reporting** | Tell controller what's tripped (informational) |

RTU interlock structure:

```c
typedef struct {
    int interlock_id;
    int sensor_slot;           // What to monitor
    float high_cutoff;         // Above this → trip
    float low_cutoff;          // Below this → trip
    int target_actuator;       // What to force
    uint8_t force_state;       // OFF, ON, or specific value
    uint32_t delay_ms;         // Time before trip (debounce)
    bool allow_override;       // false for safety-critical
    bool tripped;              // Current state
} interlock_t;
```

## Configuration Flow

### Setting Up an Interlock

1. **Operator uses Controller HMI** to define interlock parameters
2. **Controller pushes config to RTU** via PROFINET write
3. **RTU stores config in local SQLite** database
4. **RTU executes interlock logic** locally from then on
5. **Controller can READ status** but cannot COMMAND interlock release

```
┌────────────┐     Config push      ┌────────────┐
│ Controller │ ─────────────────────▶│    RTU     │
│    HMI     │                       │ (stores &  │
│            │ ◀───────────────────── │  executes) │
└────────────┘     Status read       └────────────┘
```

### Operator Acknowledgment

When an interlock trips and the condition clears:

1. RTU detects condition is clear
2. RTU does NOT automatically release (requires ack)
3. Operator acknowledges via HMI
4. Controller sends "reset request" to RTU
5. RTU validates conditions are still clear
6. RTU releases interlock

This prevents "bump and run" where an operator quickly resets without fixing the problem.

## Example: Tank Level Protection

### RTU Interlock (Safety Layer)

```json
{
  "interlock_id": 1,
  "sensor_slot": 7,
  "name": "Tank High Level Cutoff",
  "high_cutoff": 95.0,
  "low_cutoff": 5.0,
  "target_actuator": 9,
  "force_state": "OFF",
  "delay_ms": 0,
  "allow_override": false
}
```

- Level > 95% → IMMEDIATELY turn off inlet pump
- Level < 5% → IMMEDIATELY turn off outlet pump (dry run protection)
- No delay, no network dependency, no override possible

### Controller Alarm (Notification Layer)

```json
{
  "rule_id": 1,
  "name": "Tank High Level Warning",
  "rtu_station": "water-treat-rtu-1",
  "slot": 7,
  "condition": "HIGH",
  "threshold": 85.0,
  "severity": "MEDIUM",
  "delay_ms": 10000,
  "message": "Tank 1 level approaching high limit"
}
```

- Level > 85% for 10 seconds → Generate alarm notification
- Operator can investigate before the RTU safety interlock kicks in at 95%
- This is informational only - does not control anything

## Summary

| Aspect | Controller | RTU |
|--------|------------|-----|
| **Purpose** | Monitor, notify, log | Protect equipment/process |
| **Response time** | Seconds | Milliseconds |
| **Network required** | Yes | No |
| **Executes interlocks** | NO | YES |
| **Can override** | Cannot override RTU | N/A |
| **Failure mode** | Alarms stop, nothing breaks | Interlocks keep running |

## FAQ

**Q: Can the controller ever control an actuator?**
A: Yes, for normal operation (setpoints, manual commands). But NOT for safety interlocks.

**Q: What if I want the controller to turn off a pump based on complex logic?**
A: Send a normal command to the RTU. The RTU will execute it unless an interlock prevents it.

**Q: What if the RTU and controller disagree?**
A: The RTU wins. Its interlock engine has final authority over actuator states.

**Q: Can I disable an interlock from the controller?**
A: You can push a config change that disables it, but the RTU must accept and store that change. For safety-critical interlocks, `allow_override=false` prevents even this.
