# Commissioning Checklist Template

**System:** Water Treatment SCADA
**Site:** ____________________
**Date:** ____________________
**Commissioning Engineer:** ____________________

---

## 1. Pre-Power Verification

### 1.1 Physical Installation

| Item | Verified | Initials | Notes |
|------|----------|----------|-------|
| Controller (SBC #1) securely mounted | ☐ | | |
| RTU (SBC #2) securely mounted | ☐ | | |
| All cable connections secure | ☐ | | |
| Power supply within spec (5V ±5%) | ☐ | | |
| Ethernet cables properly terminated | ☐ | | |
| Network switch operational | ☐ | | |
| Environmental conditions acceptable | ☐ | | |

### 1.2 Sensor Connections

| Sensor | Location | Wiring Verified | Polarity Correct | Notes |
|--------|----------|-----------------|------------------|-------|
| pH Sensor | | ☐ | ☐ | |
| TDS Sensor | | ☐ | ☐ | |
| Temperature Sensor 1 | | ☐ | ☐ | |
| Temperature Sensor 2 | | ☐ | ☐ | |
| Level Sensor | | ☐ | ☐ | |
| Flow Sensor | | ☐ | ☐ | |
| Pressure Sensor | | ☐ | ☐ | |
| | | ☐ | ☐ | |

### 1.3 Actuator Connections

| Actuator | Location | Wiring Verified | Safe State | Notes |
|----------|----------|-----------------|------------|-------|
| Main Pump | | ☐ | OFF / ON / HOLD | |
| Dosing Pump 1 | | ☐ | OFF / ON / HOLD | |
| Dosing Pump 2 | | ☐ | OFF / ON / HOLD | |
| Inlet Valve | | ☐ | OFF / ON / HOLD | |
| Outlet Valve | | ☐ | OFF / ON / HOLD | |
| Drain Valve | | ☐ | OFF / ON / HOLD | |
| | | ☐ | OFF / ON / HOLD | |

---

## 2. Initial Power-Up

### 2.1 Controller (SBC #1) Boot

| Item | Expected | Actual | Pass/Fail |
|------|----------|--------|-----------|
| Power LED illuminates | Yes | | |
| Boot completes (no hang) | < 60s | | |
| Status LED green | Yes | | |
| SSH accessible | Yes | | |
| Web UI accessible | Yes | | |
| API health endpoint responds | HTTP 200 | | |

### 2.2 RTU (SBC #2) Boot

| Item | Expected | Actual | Pass/Fail |
|------|----------|--------|-----------|
| Power LED illuminates | Yes | | |
| Boot completes (no hang) | < 60s | | |
| Status LED green | Yes | | |
| TUI accessible | Yes | | |
| Health endpoint responds | HTTP 200 | | |

---

## 3. Network Communication

### 3.1 IP Configuration

| Device | Configured IP | Actual IP | Ping Test | Notes |
|--------|--------------|-----------|-----------|-------|
| Controller | | | ☐ OK | |
| RTU | | | ☐ OK | |
| Network Switch | | | ☐ OK | |

### 3.2 PROFINET Communication

| Item | Expected | Actual | Pass/Fail |
|------|----------|--------|-----------|
| RTU station name configured | | | |
| Controller discovers RTU | Yes | | |
| AR (Application Relationship) established | Yes | | |
| Cyclic I/O active | Yes | | |
| Cycle time stable | ≤ configured | | |
| IOPS = GOOD | 0x80 | | |

**PROFINET Diagnostic Capture:**
- Wireshark capture file: ____________________
- Capture duration: ____________________ seconds
- Packet loss observed: ____________________ %

---

## 4. Sensor Verification

### 4.1 Sensor Reading Verification

| Sensor | Slot | Expected Reading | Actual Reading | Quality | Pass/Fail |
|--------|------|------------------|----------------|---------|-----------|
| pH | | 7.0 ± 0.5 (tap water) | | | |
| TDS | | Per local water | | | |
| Temp 1 | | Ambient ± 2°C | | | |
| Temp 2 | | Ambient ± 2°C | | | |
| Level | | Known level | | | |
| Flow | | 0 (no flow) | | | |
| Pressure | | Atmospheric | | | |

### 4.2 Sensor Calibration

| Sensor | Calibration Standard | Cal Point 1 | Cal Point 2 | Date | Initials |
|--------|---------------------|-------------|-------------|------|----------|
| pH | pH 7.0 buffer | | | | |
| pH | pH 4.0 buffer | | | | |
| TDS | 1000 ppm standard | | | | |
| Level | Known depth | | | | |

---

## 5. Actuator Verification

### 5.1 Manual Control Test

**WARNING:** Ensure safe conditions before actuating. Verify no personnel in hazard zones.

| Actuator | Slot | Command Sent | Actuator Responded | Feedback Correct | Pass/Fail |
|----------|------|--------------|-------------------|------------------|-----------|
| Main Pump | | ON | ☐ | ☐ | |
| Main Pump | | OFF | ☐ | ☐ | |
| Dosing Pump 1 | | ON | ☐ | ☐ | |
| Dosing Pump 1 | | OFF | ☐ | ☐ | |
| Inlet Valve | | OPEN | ☐ | ☐ | |
| Inlet Valve | | CLOSE | ☐ | ☐ | |
| | | | ☐ | ☐ | |

### 5.2 PWM Control Test (if applicable)

| Actuator | Duty Cycle Set | Measured Output | Pass/Fail |
|----------|----------------|-----------------|-----------|
| | 0% | | |
| | 50% | | |
| | 100% | | |

---

## 6. Safety Interlock Verification

**CRITICAL:** All interlocks must be verified before operational handover.

### 6.1 Interlock Configuration Verification

| Interlock | Sensor | Threshold | Target Actuator | Action | Configured |
|-----------|--------|-----------|-----------------|--------|------------|
| High Level Cutoff | Level | 95% | Inlet Valve | CLOSE | ☐ |
| Low Level Cutoff | Level | 5% | Main Pump | OFF | ☐ |
| High Temperature | Temp 1 | 70°C | Heater | OFF | ☐ |
| High Pressure | Pressure | 10 bar | Main Pump | OFF | ☐ |
| | | | | | ☐ |

### 6.2 Interlock Functional Test

**PROCEDURE:** For each interlock, simulate the trip condition and verify response.

| Interlock | Trip Condition Simulated | Actuator Response | Response Time | Recovery Verified | Pass/Fail |
|-----------|-------------------------|-------------------|---------------|-------------------|-----------|
| High Level Cutoff | | | | ☐ | |
| Low Level Cutoff | | | | ☐ | |
| High Temperature | | | | ☐ | |
| High Pressure | | | | ☐ | |
| | | | | ☐ | |

**Interlock Test Notes:**
```
[Record any observations, anomalies, or adjustments made during interlock testing]




```

---

## 7. Alarm System Verification

### 7.1 Alarm Rule Configuration

| Alarm | Sensor | Condition | Threshold | Severity | Configured |
|-------|--------|-----------|-----------|----------|------------|
| High pH | pH | > | 8.5 | MEDIUM | ☐ |
| Low pH | pH | < | 6.5 | MEDIUM | ☐ |
| High Level Warning | Level | > | 85% | LOW | ☐ |
| High Temperature | Temp 1 | > | 60°C | HIGH | ☐ |
| | | | | | ☐ |

### 7.2 Alarm Propagation Test

| Alarm | Trip Condition | HMI Display | WebSocket Received | Acknowledge Test | Pass/Fail |
|-------|----------------|-------------|-------------------|------------------|-----------|
| | | ☐ | ☐ | ☐ | |
| | | ☐ | ☐ | ☐ | |
| | | ☐ | ☐ | ☐ | |

---

## 8. Data Historian Verification

### 8.1 Data Collection

| Item | Expected | Actual | Pass/Fail |
|------|----------|--------|-----------|
| Tags configured | Per sensor count | | |
| Sample rate | As configured | | |
| Data appearing in historian | Yes | | |
| Quality codes propagated | Yes | | |

### 8.2 Data Retrieval Test

| Query | Expected Result | Actual Result | Pass/Fail |
|-------|-----------------|---------------|-----------|
| Last 1 hour trend | Data returned | | |
| Aggregated query | Correct values | | |
| Quality filtering | Works correctly | | |

---

## 9. Backup and Recovery

### 9.1 Backup Test

| Item | Pass/Fail | Notes |
|------|-----------|-------|
| Configuration backup created | ☐ | |
| Backup downloadable | ☐ | |
| Backup file readable | ☐ | |

### 9.2 Recovery Test (Optional - Destructive)

| Item | Pass/Fail | Notes |
|------|-----------|-------|
| Configuration modified | ☐ | |
| Restore from backup | ☐ | |
| Configuration verified | ☐ | |

---

## 10. Communication Loss Test

### 10.1 Controller-RTU Disconnection

| Item | Expected | Actual | Pass/Fail |
|------|----------|--------|-----------|
| Disconnect Ethernet | | | |
| RTU enters degraded mode | Yes, within 30s | | |
| RTU maintains last state | Yes | | |
| Reconnect Ethernet | | | |
| Communication restored | Yes, within 60s | | |
| Data quality returns to GOOD | Yes | | |

### 10.2 Sensor Failure Simulation

| Item | Expected | Actual | Pass/Fail |
|------|----------|--------|-----------|
| Disconnect sensor | | | |
| Quality = BAD within | 5 seconds | | |
| Alarm generated | Yes | | |
| Reconnect sensor | | | |
| Quality = GOOD within | 5 seconds | | |

---

## 11. Final Verification

### 11.1 System Status Check

| Subsystem | Status | Notes |
|-----------|--------|-------|
| Controller C application | Running | |
| FastAPI backend | Running | |
| Web UI | Running | |
| PROFINET communication | Connected | |
| RTU application | Running | |
| All sensors reading | Yes | |
| All actuators responsive | Yes | |
| No active alarms | Yes | |
| Historian collecting | Yes | |

### 11.2 Documentation Verification

| Item | Complete | Location |
|------|----------|----------|
| Network diagram | ☐ | |
| Sensor calibration records | ☐ | |
| Interlock configuration | ☐ | |
| Alarm configuration | ☐ | |
| Operator training | ☐ | |
| Emergency procedures | ☐ | |

---

## Sign-Off

### Commissioning Complete

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Commissioning Engineer | | | |
| Operations Representative | | | |
| Safety Representative | | | |
| Project Manager | | | |

### Notes and Exceptions

```
[Document any deviations from standard configuration, known issues, or follow-up items]




```

---

**Document Control:**
- Template Version: 1.0
- Last Updated: 2024-12-22
- Applicable Standards: IEC 62443, ISA-18.2
