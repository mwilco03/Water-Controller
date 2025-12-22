# Water Treatment Controller - Commissioning Procedure

**Document ID:** WT-COMM-001
**Version:** 1.0.0
**Last Updated:** 2024-12-22

---

## Purpose

This document provides step-by-step procedures for commissioning a Water Treatment Controller installation. It supplements the checklist template in `/docs/templates/commissioning-checklist.md`.

---

## Prerequisites

Before beginning commissioning:

1. **Physical Installation Complete**
   - Controller SBC mounted and powered
   - RTU SBC mounted and powered
   - Network infrastructure in place
   - All sensors and actuators connected

2. **Software Installation Complete**
   - Controller software installed per DEPLOYMENT.md
   - RTU software installed and configured
   - Web UI accessible

3. **Documentation Available**
   - Wiring diagrams
   - P&ID (Process and Instrumentation Diagram)
   - Sensor specifications and ranges
   - Interlock requirements
   - Alarm setpoints

4. **Personnel**
   - Commissioning engineer
   - Electrical technician (for wiring verification)
   - Operations representative
   - Safety representative (for interlock testing)

---

## Phase 1: Pre-Power Verification

### 1.1 Physical Installation Check

**Time: 30-60 minutes**

1. **Controller Mounting**
   - Verify controller SBC is securely mounted
   - Check ventilation clearance
   - Verify power supply voltage: _______V (expected: 5V ±5%)

2. **RTU Mounting**
   - Verify RTU SBC is securely mounted
   - Check environmental protection (IP rating if applicable)
   - Verify power supply voltage: _______V (expected: 5V ±5%)

3. **Network Cabling**
   - Inspect all Ethernet cables for damage
   - Verify proper termination (use cable tester)
   - Confirm cable category meets requirements (Cat5e minimum)
   - Document cable runs:

   | From | To | Cable ID | Length | Test Result |
   |------|-----|----------|--------|-------------|
   | | | | | |

4. **Sensor Wiring Verification**

   For each sensor, verify:
   - Correct cable type used
   - Proper shielding and grounding
   - Polarity correct (where applicable)
   - No visible damage

   | Sensor | Cable Type | Polarity | Shield Grounded | Notes |
   |--------|------------|----------|-----------------|-------|
   | | | ☐ | ☐ | |

5. **Actuator Wiring Verification**

   For each actuator, verify:
   - Correct wire gauge for current rating
   - Overcurrent protection installed
   - Safe state wiring correct

   | Actuator | Wire Gauge | Protection | Safe State | Notes |
   |----------|------------|------------|------------|-------|
   | | | | OFF/ON | |

---

## Phase 2: Initial Power-Up

### 2.1 Staged Power Application

**Time: 30 minutes**

**CAUTION:** Apply power in stages to identify issues before full energization.

1. **Power Control Panel**
   - Verify emergency stop accessible and functional
   - Close main disconnect

2. **Power Controller SBC**
   - Apply 5V power
   - Observe boot sequence (LEDs)
   - Wait for boot completion (typically 30-60 seconds)
   - Verify SSH access: `ssh wtc@<controller-ip>`
   - Verify Web UI: `http://<controller-ip>:3000`

3. **Power RTU SBC**
   - Apply 5V power
   - Observe boot sequence (LEDs)
   - Wait for boot completion
   - Verify RTU TUI accessible (if applicable)

4. **Record Boot Times**
   | Device | Boot Start | Boot Complete | Total Time |
   |--------|------------|---------------|------------|
   | Controller | | | |
   | RTU | | | |

### 2.2 Service Verification

**On Controller:**

```bash
# Check all services
sudo systemctl status water-controller water-controller-api water-controller-ui

# Verify no errors in logs
sudo journalctl -u water-controller -n 50 --no-pager | grep -i error
sudo journalctl -u water-controller-api -n 50 --no-pager | grep -i error

# Check API health
curl http://localhost:8080/api/v1/system/health
```

**Expected Results:**
- [ ] All services show "active (running)"
- [ ] No errors in logs
- [ ] Health endpoint returns status "healthy"

---

## Phase 3: Network Communication

### 3.1 Basic Connectivity

**Time: 15-30 minutes**

```bash
# On Controller - verify network interface
ip addr show eth0

# Verify RTU reachable
ping -c 5 <rtu-ip-address>
```

### 3.2 PROFINET Discovery

**From Controller Web UI or CLI:**

```bash
# Trigger DCP scan
curl -X POST http://localhost:8080/api/v1/discover/rtu

# Check discovered devices
curl http://localhost:8080/api/v1/discover/cached
```

**Expected Results:**
- [ ] RTU appears in discovery results
- [ ] Station name correct: _______________
- [ ] IP address correct: _______________
- [ ] Vendor/Device ID correct: _______________

### 3.3 PROFINET Connection

1. Add RTU to controller:
   ```bash
   curl -X POST http://localhost:8080/api/v1/rtus \
     -H "Content-Type: application/json" \
     -d '{"station_name": "<station-name>"}'
   ```

2. Initiate connection:
   ```bash
   curl -X POST http://localhost:8080/api/v1/rtus/<station-name>/connect
   ```

3. Verify connection state:
   ```bash
   curl http://localhost:8080/api/v1/rtus/<station-name>
   ```

**Expected Results:**
- [ ] RTU added successfully
- [ ] Connection state progresses: IDLE → CONNECTING → CONNECTED → RUNNING
- [ ] Connection established within 30 seconds

### 3.4 Wireshark Verification (Optional)

For detailed protocol verification:

1. Capture PROFINET traffic:
   ```bash
   sudo tcpdump -i eth0 -w /tmp/profinet_commissioning.pcap \
     'udp port 34962 or udp port 34963 or udp port 34964' &
   ```

2. Allow 60 seconds of capture during normal operation

3. Stop capture:
   ```bash
   sudo pkill tcpdump
   ```

4. Analyze in Wireshark:
   - Verify cyclic I/O frames present
   - Confirm 5-byte sensor data format
   - Check for errors or retransmissions

---

## Phase 4: Sensor Verification

### 4.1 Sensor Reading Check

**Time: 30-60 minutes**

For each sensor, verify readings are reasonable:

```bash
# Get all sensor readings
curl http://localhost:8080/api/v1/rtus/<station-name>/sensors | jq
```

| Sensor | Slot | Expected Range | Actual Reading | Quality | Pass/Fail |
|--------|------|----------------|----------------|---------|-----------|
| pH | | 0-14 | | | |
| TDS | | 0-5000 ppm | | | |
| Temp 1 | | -10 to 100°C | | | |
| Level | | 0-100% | | | |
| Flow | | 0-1000 L/min | | | |
| Pressure | | 0-10 bar | | | |

### 4.2 Sensor Fault Simulation

For each sensor, temporarily disconnect and verify:

1. Disconnect sensor wiring
2. Wait 5 seconds
3. Check API:
   ```bash
   curl http://localhost:8080/api/v1/rtus/<station-name>/sensors | \
     jq '.[] | select(.slot == <slot>) | .status'
   ```
4. Verify status shows "BAD" or "NOT_CONNECTED"
5. Reconnect sensor
6. Verify status returns to "GOOD"

| Sensor | Disconnect Response | Reconnect Response | Pass/Fail |
|--------|--------------------|--------------------|-----------|
| | | | |

### 4.3 Sensor Calibration

Refer to `/docs/templates/calibration-record.md` for detailed procedure.

**pH Sensor Calibration:**
1. Place sensor in pH 7.0 buffer
2. Record reading: _______
3. Adjust offset if needed
4. Place sensor in pH 4.0 buffer
5. Record reading: _______
6. Adjust slope if needed
7. Verify calibration with pH 10.0 buffer: _______

---

## Phase 5: Actuator Verification

### 5.1 Manual Control Test

**WARNING:** Ensure safe conditions before actuating. Clear all personnel from hazard zones.

**Time: 30-60 minutes**

For each actuator:

1. **Pre-Test Safety Check**
   - [ ] Area clear of personnel
   - [ ] Downstream equipment ready
   - [ ] Emergency stop accessible

2. **Command ON:**
   ```bash
   curl -X POST http://localhost:8080/api/v1/rtus/<station-name>/actuators/<slot> \
     -H "Content-Type: application/json" \
     -d '{"command": "ON"}'
   ```

3. **Verify actuator responds**
   - Visual confirmation
   - Feedback signal (if applicable)

4. **Command OFF:**
   ```bash
   curl -X POST http://localhost:8080/api/v1/rtus/<station-name>/actuators/<slot> \
     -H "Content-Type: application/json" \
     -d '{"command": "OFF"}'
   ```

5. **Verify actuator stops**

| Actuator | Slot | ON Response | OFF Response | Feedback OK | Pass/Fail |
|----------|------|-------------|--------------|-------------|-----------|
| | | | | | |

### 5.2 PWM Control Test (If Applicable)

For variable speed devices:

```bash
# Set 50% output
curl -X POST http://localhost:8080/api/v1/rtus/<station-name>/actuators/<slot> \
  -H "Content-Type: application/json" \
  -d '{"command": "PWM", "pwm_duty": 50}'
```

| Actuator | 0% Verified | 50% Verified | 100% Verified | Pass/Fail |
|----------|-------------|--------------|---------------|-----------|
| | | | | |

---

## Phase 6: Safety Interlock Verification

**CRITICAL PHASE - Document all tests thoroughly**

**Time: 1-2 hours**

### 6.1 Interlock Configuration Review

Before testing, verify interlock configuration on RTU:

| Interlock ID | Sensor | Trip Point | Target Actuator | Action | Configured |
|--------------|--------|------------|-----------------|--------|------------|
| | | | | | ☐ |

### 6.2 Interlock Trip Testing

**For each safety interlock:**

1. **Prepare Test**
   - Document current process state
   - Ensure safe test conditions
   - Have personnel ready to observe

2. **Simulate Trip Condition**
   - Method: _______________
   - (e.g., inject test signal, drain tank to low level, etc.)

3. **Verify Response**
   - Target actuator forced to safe state: ☐ Yes ☐ No
   - Response time: _______ms (should be <100ms)
   - HMI displays interlock status: ☐ Yes ☐ No
   - Alarm generated: ☐ Yes ☐ No

4. **Verify Cannot Override**
   - Attempt to command actuator via HMI
   - Command should be rejected: ☐ Yes ☐ No

5. **Clear Trip Condition**
   - Return process to normal state
   - Interlock should NOT auto-reset

6. **Test Reset Procedure**
   - Request reset via HMI
   - RTU validates conditions are clear
   - Interlock releases: ☐ Yes ☐ No

| Interlock | Trip Test | Override Blocked | Reset Test | Pass/Fail |
|-----------|-----------|------------------|------------|-----------|
| | | | | |

### 6.3 Communication Loss Test

**Test RTU behavior when controller connection is lost:**

1. Record current interlock states
2. Disconnect Ethernet cable from controller
3. Wait 30 seconds
4. Verify on RTU (via TUI or direct):
   - [ ] RTU continues operating
   - [ ] Interlocks remain active
   - [ ] Actuators hold last safe state

5. Trigger an interlock trip condition:
   - [ ] RTU responds locally without controller

6. Reconnect Ethernet cable
7. Verify:
   - [ ] Connection re-establishes
   - [ ] Data quality returns to GOOD
   - [ ] Interlock status syncs to controller

---

## Phase 7: Alarm System Verification

### 7.1 Alarm Rule Configuration

Configure alarm rules for each monitored point:

```bash
curl -X POST http://localhost:8080/api/v1/alarms/rules \
  -H "Content-Type: application/json" \
  -d '{
    "rtu_station": "<station-name>",
    "slot": 1,
    "condition": "HIGH",
    "threshold": 8.5,
    "severity": "MEDIUM",
    "delay_ms": 5000,
    "message": "pH High Warning"
  }'
```

| Alarm | Sensor | Condition | Threshold | Severity | Configured |
|-------|--------|-----------|-----------|----------|------------|
| | | | | | ☐ |

### 7.2 Alarm Trip Test

For each alarm rule:

1. Create condition that exceeds threshold
2. Wait for delay period
3. Verify:
   - [ ] Alarm appears in active alarms list
   - [ ] WebSocket notification received
   - [ ] Severity is correct
   - [ ] Message is correct

4. Acknowledge alarm:
   ```bash
   curl -X POST http://localhost:8080/api/v1/alarms/<alarm_id>/acknowledge \
     -H "Content-Type: application/json" \
     -d '{"user": "commissioning_engineer"}'
   ```

5. Clear condition
6. Verify:
   - [ ] Alarm moves to cleared state
   - [ ] Appears in alarm history

---

## Phase 8: Historian Verification

### 8.1 Tag Configuration

Create historian tags for all points to be trended:

```bash
curl -X POST http://localhost:8080/api/v1/trends/tags \
  -H "Content-Type: application/json" \
  -d '{
    "rtu_station": "<station-name>",
    "slot": 1,
    "tag_name": "Tank1_pH",
    "sample_rate_ms": 1000,
    "enabled": true
  }'
```

### 8.2 Data Collection Verification

1. Wait 5 minutes for data collection
2. Query historian:
   ```bash
   curl "http://localhost:8080/api/v1/trends/1?start=$(date -d '-5 minutes' -Iseconds)&end=$(date -Iseconds)"
   ```
3. Verify:
   - [ ] Data points present
   - [ ] Values match current readings
   - [ ] Quality codes correct

### 8.3 Trend Display Verification

1. Open Web UI Trends page
2. Select historian tag
3. Verify trend displays correctly
4. Test zoom and pan functions

---

## Phase 9: Backup and Recovery

### 9.1 Backup Test

1. Create backup via Web UI or CLI:
   ```bash
   curl -X POST http://localhost:8080/api/v1/backups \
     -H "Content-Type: application/json" \
     -d '{"description": "Commissioning backup", "include_historian": true}'
   ```

2. Verify backup created:
   ```bash
   curl http://localhost:8080/api/v1/backups
   ```

3. Download backup:
   ```bash
   curl -O http://localhost:8080/api/v1/backups/<backup_id>/download
   ```

4. Verify backup file is valid:
   ```bash
   tar -tzf wtc_config_*.tar.gz
   ```

### 9.2 Recovery Test (Optional - Destructive)

**WARNING:** This will overwrite current configuration.

1. Make a deliberate configuration change
2. Restore from backup:
   ```bash
   curl -X POST http://localhost:8080/api/v1/backups/<backup_id>/restore
   ```
3. Verify original configuration restored

---

## Phase 10: Final Verification

### 10.1 System Status Check

```bash
# Full system health
curl http://localhost:8080/api/v1/system/health | jq

# All RTUs connected
curl http://localhost:8080/api/v1/rtus | jq '.[].connection_state'

# No active alarms
curl http://localhost:8080/api/v1/alarms | jq 'length'
```

### 10.2 Extended Run Test

Allow system to run for 24 hours under normal conditions:

- [ ] All services remain running
- [ ] No unexpected alarms
- [ ] Historian collecting data continuously
- [ ] No communication dropouts
- [ ] CPU usage stable
- [ ] Memory usage stable
- [ ] Disk usage as expected

---

## Phase 11: Documentation and Handover

### 11.1 As-Built Documentation

Update or create:
- [ ] Final network diagram
- [ ] Final I/O list with slot assignments
- [ ] Sensor calibration records
- [ ] Interlock configuration document
- [ ] Alarm setpoint document
- [ ] Historian tag list

### 11.2 Operator Training

- [ ] HMI navigation
- [ ] Alarm acknowledgment
- [ ] Manual control procedures
- [ ] Interlock reset procedure
- [ ] Emergency procedures
- [ ] Shift handover procedures

### 11.3 Handover

Complete sign-off in commissioning checklist template.

---

## Troubleshooting During Commissioning

| Issue | Possible Cause | Resolution |
|-------|----------------|------------|
| RTU not discovered | Wrong network interface | Check `interface` in config |
| Connection fails | Station name mismatch | Verify names match exactly |
| Sensors show BAD | Wiring issue | Check sensor connections |
| Actuator no response | Interlock active | Check interlock status |
| No historian data | Tags not configured | Create historian tags |

For detailed troubleshooting, see `/docs/TROUBLESHOOTING_GUIDE.md`.

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2024-12-22 | Initial | Initial release |

---

*This procedure should be performed by qualified personnel familiar with the Water Treatment Controller system and process equipment.*
