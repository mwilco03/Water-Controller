# Water-Controller Operator Guide

**For Field Operators and Plant Personnel**

---

## Quick Reference

| Need To... | Go To | Page Section |
|------------|-------|--------------|
| Check system status | Dashboard (home page) | [Dashboard](#dashboard) |
| Acknowledge an alarm | Alarms page | [Acknowledging Alarms](#acknowledging-alarms) |
| View sensor history | Trends page | [Viewing Trends](#viewing-trends) |
| Control a pump/valve | RTU detail page | [Manual Control](#manual-control) |
| Check RTU connection | System > Network | [Network Status](#network-status) |
| Contact support | System > About | [Getting Help](#getting-help) |

---

## What is This System?

Water-Controller is the supervisory system for your water treatment plant. It:

- **Monitors** all sensors across your RTUs (Remote Terminal Units)
- **Displays** current values, historical trends, and alarms
- **Allows** operators to send commands to actuators (pumps, valves)
- **Records** all data for analysis and reporting

**What it does NOT do:**

- It does NOT directly control equipment (the RTUs do that)
- It does NOT execute safety interlocks (the RTUs do that locally)
- If this system goes offline, your RTUs continue operating safely

---

## Understanding System States

### Overall System Health

The top of every page shows system status:

| Indicator | Meaning | Action Required |
|-----------|---------|-----------------|
| **Green checkmark** | All systems normal | None |
| **Yellow warning** | Some components degraded | Check System page for details |
| **Red alert** | Critical component offline | Contact support immediately |

### RTU Connection Status

Each RTU on the dashboard shows its connection state:

| State | Indicator | Meaning |
|-------|-----------|---------|
| **CONNECTED** | Green | RTU is communicating normally |
| **CONNECTING** | Yellow pulse | Establishing connection |
| **OFFLINE** | Red | No communication with RTU |

**If an RTU shows OFFLINE:**
1. Check the physical network cable to the RTU
2. Verify the RTU has power (lights on front panel)
3. Contact your network administrator
4. The RTU continues operating safely with its local settings

---

## Understanding Sensor Data Quality

Every sensor reading shows data quality. This tells you how trustworthy the value is.

### Quality Indicators

| Quality | Display | Meaning | What to Do |
|---------|---------|---------|------------|
| **GOOD** | Normal display | Fresh, valid reading | Normal operation |
| **UNCERTAIN** | Yellow background, ⚠ | May be stale or degraded | Monitor closely |
| **BAD** | Red background, ✕ | Sensor failure | Check sensor, call maintenance |
| **NOT CONNECTED** | Grey, ? | Cannot reach sensor | Check RTU connection |

### Reading a Sensor Display

```
┌────────────────────────────────┐
│  pH Level                      │  ← Sensor name
│  ⚠ 7.24 pH                    │  ← Quality indicator + value + units
│  Tank-01 / Slot 3              │  ← Source RTU and slot
│  Updated 5s ago                │  ← Data freshness
└────────────────────────────────┘
```

**IMPORTANT:** Never rely on a sensor showing BAD or NOT CONNECTED quality for operational decisions. These values may be incorrect or stale.

---

## Dashboard

The dashboard shows an overview of your entire system.

### RTU Summary Cards

Each RTU has a summary card showing:
- Connection status (CONNECTED/OFFLINE)
- Key sensor values
- Active alarm count
- Last communication time

### Clicking an RTU Card

Click any RTU card to see:
- All sensors on that RTU
- All actuators and their states
- Recent alarms for that RTU
- Control buttons for manual operation

---

## Alarms

### Understanding Alarm Levels

| Level | Color | Meaning | Response Time |
|-------|-------|---------|---------------|
| **EMERGENCY** | Red flashing | Immediate safety concern | Respond within minutes |
| **HIGH** | Red solid | Equipment at risk | Respond within 15 minutes |
| **MEDIUM** | Orange | Attention needed | Respond within 1 hour |
| **LOW** | Yellow | Informational | Respond when convenient |

### Alarm States

| State | Meaning |
|-------|---------|
| **ACTIVE - UNACKNOWLEDGED** | New alarm, operator has not seen it |
| **ACTIVE - ACKNOWLEDGED** | Operator has seen it, condition still exists |
| **CLEARED - UNACKNOWLEDGED** | Condition cleared, needs acknowledgment |
| **CLEARED** | Alarm resolved and acknowledged |

### Acknowledging Alarms

Acknowledging an alarm tells the system you have seen it:

1. Go to the Alarms page
2. Click the **Acknowledge** button next to the alarm
3. The alarm changes from "UNACKNOWLEDGED" to "ACKNOWLEDGED"

**IMPORTANT:** Acknowledging an alarm does NOT fix the problem. It only indicates you have seen it. The alarm remains active until the condition that caused it is resolved.

### Alarm Shelving

If an alarm is known and being worked on, you can shelve it temporarily:

1. Click the **Shelve** button next to the alarm
2. Select a shelve duration (1 hour, 8 hours, 24 hours)
3. The alarm will not notify you during the shelve period
4. The alarm returns to normal after the shelve expires

**WARNING:** Shelving is for known issues only. Never shelve an alarm you don't understand.

---

## Viewing Trends

The Trends page shows historical data for any sensor.

### Creating a Trend View

1. Go to Trends page
2. Select the RTU from the dropdown
3. Select the sensor (slot) to view
4. Choose a time range (last hour, day, week, month)
5. Click **Load Trend**

### Reading a Trend Chart

- **X-axis**: Time
- **Y-axis**: Sensor value in engineering units
- **Color bands**: Alarm thresholds (if configured)
  - Green zone: Normal operating range
  - Yellow zone: Warning range
  - Red zone: Alarm range

### Data Quality on Trends

Trend charts show data quality:
- **Solid line**: GOOD quality data
- **Dotted line**: UNCERTAIN quality data
- **Gaps**: BAD or NOT_CONNECTED periods (no data recorded)

---

## Manual Control

### Safety First

Before operating any equipment manually:

1. Verify you are controlling the correct RTU and actuator
2. Check for any active interlocks that may prevent operation
3. Ensure personnel are clear of the equipment
4. Notify other operators if needed

### Sending a Command

1. Navigate to the RTU detail page
2. Find the actuator you want to control
3. Click **Start** or **Stop** (or adjust setpoint)
4. Watch for the confirmation:
   - **Success**: Actuator state updates within seconds
   - **Pending**: Command sent, waiting for RTU response
   - **Rejected**: RTU refused the command (check interlocks)

### Why Was My Command Rejected?

Commands may be rejected for these reasons:

| Reason | Meaning | What to Do |
|--------|---------|------------|
| **Interlock Active** | Safety condition prevents operation | Resolve the interlock condition first |
| **RTU Offline** | Cannot reach the RTU | Check RTU connection |
| **Authority Denied** | Another operator has control | Coordinate with other operators |
| **Equipment Fault** | RTU reports equipment problem | Contact maintenance |

### Understanding Interlocks

Interlocks are safety protections that prevent equipment damage:

- **High Level**: Pump stops when tank is too full
- **Low Level**: Pump stops when tank is too empty (dry run protection)
- **High Pressure**: Valve closes when pressure exceeds limit
- **Emergency Stop**: All equipment in zone stops

**CRITICAL:** Interlocks CANNOT be overridden from this system. They are enforced by the RTU locally for safety. If an interlock is preventing operation, the underlying condition must be resolved.

---

## Network Status

### Checking Connectivity

Go to **System > Network** to see:

- All RTUs and their connection states
- Network latency to each RTU
- Last successful communication time
- Any active communication alarms

### Troubleshooting Connection Issues

If an RTU shows as OFFLINE:

1. **Check physical connections**
   - Network cable connected at both ends?
   - Any cable damage?
   - Switch port lights active?

2. **Check RTU power**
   - RTU power indicator lit?
   - Any recent power events?

3. **Check this controller**
   - Are other RTUs connected?
   - Any system alarms?

4. **Escalate if needed**
   - Contact network administrator
   - Contact system support

---

## Common Tasks

### Shift Handover Checklist

At the start of each shift:

1. [ ] Check dashboard for any OFFLINE RTUs
2. [ ] Review active alarms and acknowledge as appropriate
3. [ ] Note any alarms that carried over from previous shift
4. [ ] Check system status indicator (green/yellow/red)
5. [ ] Review recent events in the log
6. [ ] Confirm communication with all critical RTUs

### Responding to a High-Level Alarm

1. **Acknowledge** the alarm to indicate you've seen it
2. **Verify** the reading on the local gauge if available
3. **Check** if the condition is real or a sensor issue
4. **Take action** per your operating procedures:
   - Reduce inflow if level rising
   - Increase outflow if possible
   - Prepare for potential overflow containment
5. **Document** actions taken in the log

### Restarting After Power Outage

After power is restored:

1. **Wait** for systems to initialize (may take 2-3 minutes)
2. **Check** dashboard for RTU connection status
3. **Expect** some initial alarms as sensors stabilize
4. **Verify** key process values are within range
5. **Acknowledge** startup alarms as appropriate
6. **Monitor** closely for the first 15 minutes

---

## Getting Help

### System Information

Go to **System > About** to find:
- Software version
- System identifier
- Support contact information
- Last update date

### Before Calling Support

Have this information ready:
1. What were you trying to do?
2. What error message did you see?
3. What RTU or sensor is affected?
4. When did the problem start?
5. Has this happened before?

### Emergency Contacts

| Issue | Contact |
|-------|---------|
| Equipment emergency | [Your plant emergency number] |
| System not responding | [Your IT support number] |
| Software questions | [Vendor support number] |

---

## Glossary

| Term | Definition |
|------|------------|
| **RTU** | Remote Terminal Unit - the device at the equipment that reads sensors and controls actuators |
| **Slot** | A numbered position on an RTU where a sensor or actuator is connected |
| **Interlock** | An automatic safety protection that prevents unsafe equipment operation |
| **Setpoint** | The target value for automatic control (e.g., pH target of 7.0) |
| **Quality** | An indicator of how trustworthy a sensor reading is |
| **Acknowledge** | Confirm you have seen an alarm (does not clear it) |
| **Shelve** | Temporarily suppress an alarm for a known issue |
| **Historian** | The system that stores historical sensor data |
| **PROFINET** | The industrial network protocol connecting controller to RTUs |

---

## Quick Troubleshooting

### "I can't see any data"

1. Check the connection status banner at the top
2. If disconnected, wait for automatic reconnection
3. Try refreshing the page (F5)
4. Check if other operators can see data
5. Contact support if problem persists

### "A sensor shows '---'"

This means the value is not available:
- Check the quality indicator (BAD or NOT CONNECTED)
- Verify RTU connection status
- Contact maintenance if sensor may be faulty

### "My command isn't working"

1. Check for "Rejected" message and reason
2. Look for active interlocks on that equipment
3. Verify the RTU is CONNECTED
4. Try again after a few seconds
5. Contact support if repeated failures

### "Too many alarms"

1. Focus on EMERGENCY and HIGH priority first
2. Acknowledge alarms you've addressed
3. Consider shelving known issues being worked on
4. Do not silence alarms without understanding them
5. Contact support if alarm flood continues

---

*This guide covers normal operation. For detailed procedures, consult your plant operating procedures. For technical issues, contact your system administrator.*
