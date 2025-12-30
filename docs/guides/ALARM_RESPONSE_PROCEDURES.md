# Alarm Response Procedures

**Document ID:** WT-OPS-001
**Version:** 1.0.0
**Last Updated:** 2024-12-22
**Classification:** Operations Manual

---

## Purpose

This document provides standardized response procedures for operators when alarms are raised by the Water Treatment Controller system. Following these procedures ensures consistent, safe, and effective responses to process deviations.

---

## Alarm Severity Levels

| Severity | Response Time | Escalation | Description |
|----------|---------------|------------|-------------|
| **EMERGENCY** | Immediate | Supervisor + Safety | Life safety or major environmental risk |
| **CRITICAL** | < 5 minutes | Supervisor | Equipment damage or process failure imminent |
| **HIGH** | < 15 minutes | Log + Investigate | Significant deviation requiring prompt attention |
| **MEDIUM** | < 1 hour | Log | Moderate deviation from normal operation |
| **LOW** | Next shift | Log | Minor issue, informational |

---

## General Response Protocol

### Step 1: Acknowledge

1. Identify the alarm on the HMI display
2. Note the alarm details:
   - RTU station and slot
   - Current value vs. threshold
   - Time alarm was raised
3. Click "Acknowledge" or press the ACK button
4. Your username and timestamp will be recorded

### Step 2: Investigate

1. Navigate to the affected sensor/actuator on HMI
2. Verify the reading is accurate (not a sensor fault)
3. Check the historian trend for context
4. Look for related alarms or upstream causes

### Step 3: Take Action

1. Follow the specific procedure for the alarm type (see below)
2. If unsure, consult the shift supervisor
3. Do NOT silence or disable alarms without authorization

### Step 4: Document

1. Record actions taken in the shift log
2. Note any abnormal conditions observed
3. Report recurring alarms to maintenance

---

## Specific Alarm Response Procedures

### pH Alarms

#### HIGH pH (> 8.5)

**Possible Causes:**
- Caustic dosing pump over-dosing
- Acid feed pump failure
- Incoming water quality change
- Sensor drift or fouling

**Response Procedure:**

1. **Verify** the reading:
   - Check if sensor quality is GOOD
   - Compare with portable meter if available
   - Check historian trend for sudden change

2. **Immediate Actions:**
   - Reduce or stop caustic dosing pump
   - Verify acid feed pump is running
   - Check chemical tank levels

3. **If RTU interlock trips (pH > 9.0):**
   - Dosing pump will be forced OFF by RTU
   - Do NOT attempt to override
   - Wait for pH to return to normal range
   - Request interlock reset after investigation

4. **Escalation:**
   - If pH > 9.5: Notify supervisor immediately
   - If pH > 10.0: Consider process shutdown

#### LOW pH (< 6.5)

**Possible Causes:**
- Acid dosing pump over-dosing
- Caustic feed pump failure
- CO2 injection issue
- Incoming water quality change

**Response Procedure:**

1. **Verify** the reading
2. **Immediate Actions:**
   - Reduce or stop acid dosing pump
   - Verify caustic feed pump is running
   - Check CO2 injection rate

3. **If RTU interlock trips (pH < 5.5):**
   - Dosing pump will be forced OFF by RTU
   - Wait for pH to recover before reset

4. **Escalation:**
   - If pH < 5.0: Notify supervisor immediately
   - If pH < 4.0: Consider process shutdown

---

### Level Alarms

#### HIGH LEVEL WARNING (> 85%)

**Possible Causes:**
- Outlet pump failure
- Downstream blockage
- Inlet flow rate too high
- Level sensor error

**Response Procedure:**

1. **Verify** level reading is accurate
2. **Immediate Actions:**
   - Check outlet pump status - start if stopped
   - Verify outlet valve is open
   - Consider reducing inlet flow
3. **Monitor** the trend - is level still rising?
4. **Prepare** for HIGH HIGH level interlock at 95%

#### HIGH HIGH LEVEL (> 95%) - INTERLOCK

**This is handled automatically by the RTU:**
- Inlet valve/pump will be forced CLOSED/OFF
- Controller receives notification only

**Operator Response:**

1. **Acknowledge** the alarm
2. **Investigate** root cause:
   - Why did level reach 95%?
   - Was the HIGH warning ignored?
   - Is outlet equipment functional?
3. **Restore** outlet flow if possible
4. **Request interlock reset** only after:
   - Level drops below 90%
   - Root cause is identified
   - Outlet path is confirmed clear

#### LOW LEVEL WARNING (< 15%)

**Possible Causes:**
- Outlet pump running with no inlet
- Inlet valve/pump failure
- Leak in system
- Level sensor error

**Response Procedure:**

1. **Verify** reading accuracy
2. **Immediate Actions:**
   - Check inlet pump/valve status
   - Consider reducing outlet flow
   - Look for visible leaks

#### LOW LOW LEVEL (< 5%) - INTERLOCK

**This is handled automatically by the RTU:**
- Outlet pump will be forced OFF (dry run protection)

**Operator Response:**

1. **Acknowledge** the alarm
2. **Do NOT** attempt to restart outlet pump
3. **Restore** inlet flow
4. **Wait** for level to rise above 10%
5. **Request** interlock reset

---

### Temperature Alarms

#### HIGH TEMPERATURE (> 60°C)

**Possible Causes:**
- Heater stuck on
- Heat exchanger failure
- Ambient conditions
- Sensor fault

**Response Procedure:**

1. **Verify** reading with secondary sensor if available
2. **Immediate Actions:**
   - Check heater status - turn OFF if possible
   - Increase cooling water flow if applicable
   - Check ventilation

3. **Equipment Protection:**
   - At 70°C: RTU interlock will force heater OFF
   - At 80°C: Consider emergency shutdown

#### LOW TEMPERATURE (< 5°C)

**Possible Causes:**
- Heater failure
- Extreme ambient conditions
- Freeze risk

**Response Procedure:**

1. **Verify** heater is calling for heat
2. **Check** gas/electric supply to heater
3. **Implement** freeze protection if applicable
4. **Consider** trace heating for pipes

---

### Flow Alarms

#### LOW FLOW (< setpoint)

**Possible Causes:**
- Pump failure
- Blocked line
- Valve partially closed
- Sensor fouling

**Response Procedure:**

1. **Verify** pump is running
2. **Check** inlet/outlet valves are open
3. **Inspect** strainers and filters
4. **Check** for visible blockages

#### HIGH FLOW (> setpoint)

**Possible Causes:**
- Control valve failure (stuck open)
- Pump running at wrong speed
- Bypass valve open
- Sensor error

**Response Procedure:**

1. **Verify** control valve position
2. **Check** VFD speed setpoint
3. **Close** any bypass valves
4. **Consider** manual throttling if needed

---

### Pressure Alarms

#### HIGH PRESSURE (> limit)

**Possible Causes:**
- Blocked filter
- Closed downstream valve
- Pump deadheading
- Pressure relief failure

**Response Procedure:**

1. **Immediate**: Check pump is not deadheading
2. **Verify** outlet path is open
3. **Check** pressure relief valves
4. **Reduce** pump speed if VFD controlled

**WARNING:** High pressure can cause pipe/equipment rupture. Take prompt action.

#### LOW PRESSURE (< limit)

**Possible Causes:**
- Pump failure
- Large leak
- Air entrainment
- Suction blockage

**Response Procedure:**

1. **Check** pump status and suction pressure
2. **Verify** no visible leaks
3. **Check** for air in system
4. **Prime** pump if necessary

---

### Communication Alarms

#### RTU DISCONNECTED

**Cause:** PROFINET communication lost with RTU

**Response Procedure:**

1. **Check** network connectivity:
   - Physical cable connections
   - Network switch status
   - Controller network interface

2. **Verify** RTU is powered and running:
   - Status LEDs on RTU
   - Can you ping the RTU?

3. **Important Safety Note:**
   - RTU interlocks continue to function locally
   - Safety is maintained even without controller
   - Operators should monitor equipment directly

4. **Escalation:**
   - If not restored within 5 minutes: Call maintenance
   - If safety-critical process: Consider manual control

#### SENSOR QUALITY BAD

**Cause:** RTU reports sensor hardware failure

**Response Procedure:**

1. **Do NOT** rely on displayed value - it is invalid
2. **Alarms** for this sensor are suppressed (bad data)
3. **Check** sensor wiring and connections
4. **Replace** sensor if hardware fault confirmed
5. **Use** manual measurements until restored

---

### System Alarms

#### CONTROLLER CPU HIGH (> 80%)

**Response:**
1. Check for runaway processes
2. Review historian sample rates
3. Consider reducing connected RTUs
4. Contact IT if persistent

#### CONTROLLER DISK FULL (> 90%)

**Response:**
1. Archive old historian data
2. Delete old backups
3. Check log rotation settings
4. Contact IT for storage expansion

---

## Interlock Reset Procedure

When an RTU safety interlock has tripped:

1. **Wait** for the trip condition to clear (value returns to safe range)
2. **Investigate** and document the root cause
3. **Verify** it is safe to resume operation
4. **Navigate** to the interlock status screen on HMI
5. **Select** the tripped interlock
6. **Click** "Request Reset"
7. **The RTU** will verify conditions are clear before releasing
8. **Monitor** for re-trip after reset

**Interlock Reset Authorization:**
| Interlock Type | Reset Authority |
|----------------|-----------------|
| Level interlocks | Operator |
| Pressure interlocks | Operator + Supervisor |
| Temperature interlocks | Operator |
| Emergency stops | Supervisor only |

---

## Alarm Flood Procedure

If multiple alarms occur simultaneously:

1. **Prioritize** by severity (EMERGENCY > CRITICAL > HIGH)
2. **Look** for a common cause (e.g., power failure)
3. **Address** root cause first, not individual symptoms
4. **Call** for assistance if overwhelmed
5. **Document** sequence of events for post-incident review

---

## Night/Weekend Response

For off-hours operation:

| Severity | Action |
|----------|--------|
| LOW | Log and continue monitoring |
| MEDIUM | Log and attempt resolution |
| HIGH | Attempt resolution, call on-call if unable |
| CRITICAL | Call on-call technician immediately |
| EMERGENCY | Call on-call + supervisor + emergency services if needed |

**On-Call Numbers:**
- Maintenance: _______________________
- Supervisor: _______________________
- Plant Manager: _______________________
- Emergency: _______________________

---

## Post-Alarm Review

After any CRITICAL or EMERGENCY alarm:

1. Complete incident report within 24 hours
2. Attach relevant historian trends
3. Document root cause and corrective actions
4. Review for recurring patterns
5. Update procedures if gaps identified

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2024-12-22 | Initial | Initial release |

---

*This document is part of the Water Treatment Controller operations manual. All operators must be trained on these procedures before assuming control responsibilities.*
