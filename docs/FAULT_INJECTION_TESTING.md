# Fault Injection Testing Procedures

## Document Control

| Property | Value |
|----------|-------|
| Document ID | WT-TEST-001 |
| Version | 1.0 |
| Status | APPROVED |
| Classification | Engineering |

---

## 1. Overview

This document provides procedures for testing Water-Controller fault tolerance and recovery behaviors. These tests validate that the system behaves correctly under adverse conditions.

### Prerequisites

- Linux system with `tc`, `iptables`, and `iproute2` installed
- Root/sudo access for network manipulation
- Water-Controller and Water-Treat systems deployed
- Access to controller logs and RTU console

---

## 2. Network Partition Testing

### 2.1 Complete Network Partition

**Purpose:** Verify RTU enters safe state and Controller detects disconnection.

**Procedure:**

```bash
# On Controller host - block all traffic to RTU IP
RTU_IP=192.168.1.50

# Create partition
sudo iptables -A OUTPUT -d $RTU_IP -j DROP
sudo iptables -A INPUT -s $RTU_IP -j DROP

# Monitor logs
journalctl -u water-controller -f
```

**Expected Behavior:**

1. Controller should detect connection loss within 3 seconds (AR watchdog)
2. Controller should transition AR to ABORT state
3. RTU should enter safe state (actuators OFF) within 10 seconds
4. Controller logs: "AR watchdog timeout"
5. Authority should release to RTU (AUTHORITY_AUTONOMOUS)

**Verification:**

```bash
# Check controller state
curl http://localhost:8000/api/v1/rtus/$RTU_STATION/status

# Expected: connection_state = "OFFLINE" or "ERROR"
```

**Recovery:**

```bash
# Remove iptables rules
sudo iptables -D OUTPUT -d $RTU_IP -j DROP
sudo iptables -D INPUT -s $RTU_IP -j DROP
```

**Expected Recovery:**

1. Controller should attempt reconnection after 5 seconds
2. State reconciliation should occur
3. Authority handoff should complete

---

### 2.2 Asymmetric Partition (Controller -> RTU blocked)

**Purpose:** Verify RTU safe state when it cannot receive commands.

**Procedure:**

```bash
# Block only outbound to RTU (RTU can still send to Controller)
sudo iptables -A OUTPUT -d $RTU_IP -j DROP
```

**Expected Behavior:**

1. RTU continues sending sensor data
2. RTU enters safe state when no valid commands received for 10s
3. Controller may show stale data warning

---

### 2.3 Packet Loss Simulation

**Purpose:** Verify system handles degraded network conditions.

**Procedure:**

```bash
# Add 10% packet loss on interface
INTERFACE=eth0
sudo tc qdisc add dev $INTERFACE root netem loss 10%

# Run for 5 minutes, then observe behavior
sleep 300

# Remove
sudo tc qdisc del dev $INTERFACE root
```

**Expected Behavior:**

1. Increased `packet_loss_percent` in RTU stats
2. No spurious alarms due to single packet loss
3. Quality may degrade to UNCERTAIN temporarily
4. No control actions interrupted for brief losses

**Verification:**

```bash
# Check packet loss stats
curl http://localhost:8000/api/v1/rtus/$RTU_STATION/stats
```

---

### 2.4 Latency Injection

**Purpose:** Verify system handles high-latency networks.

**Procedure:**

```bash
# Add 500ms latency
sudo tc qdisc add dev $INTERFACE root netem delay 500ms

# Observe for 2 minutes
sleep 120

# Remove
sudo tc qdisc del dev $INTERFACE root
```

**Expected Behavior:**

1. Control loop performance degraded
2. No safety interlocks triggered by latency alone
3. Historian shows increased cycle times
4. Alarms should not trigger on delayed data

---

## 3. Power Cycling Tests

### 3.1 Controller Power Cycle

**Purpose:** Verify RTU autonomous operation during Controller restart.

**Procedure:**

1. Note current RTU actuator states
2. Stop Controller: `sudo systemctl stop water-controller`
3. Wait 60 seconds
4. Observe RTU behavior
5. Restart Controller: `sudo systemctl start water-controller`

**Expected Behavior:**

1. RTU continues operating autonomously
2. RTU enters safe state if configured (depends on process)
3. No data loss in RTU local state
4. Controller reconnects within 30 seconds of restart
5. State reconciliation occurs

**Verification Checklist:**

- [ ] RTU TUI shows "Controller: OFFLINE"
- [ ] RTU actuators in expected state (safe or last commanded)
- [ ] Controller log shows "Reconnecting to RTU"
- [ ] State reconciliation log entry

---

### 3.2 RTU Power Cycle

**Purpose:** Verify Controller handles RTU restart gracefully.

**Procedure:**

1. Power cycle RTU (or `sudo reboot` on RTU)
2. Monitor Controller logs

**Expected Behavior:**

1. Controller detects RTU disconnect within 3 seconds
2. Controller shows RTU as OFFLINE
3. Controller attempts reconnection every 5 seconds
4. RTU reconnects after boot (30-60 seconds)
5. Authority handoff completes

**Verification:**

```bash
# Watch controller logs during RTU reboot
journalctl -u water-controller -f | grep -E "(disconnect|reconnect|authority)"
```

---

### 3.3 Simultaneous Power Cycle

**Purpose:** Verify system recovers from complete restart.

**Procedure:**

1. Stop both Controller and RTU
2. Wait 30 seconds
3. Start RTU first
4. Wait for RTU to be running
5. Start Controller

**Expected Behavior:**

1. RTU enters autonomous mode
2. Controller discovers RTU via DCP
3. AR establishment completes
4. Authority handoff completes
5. State synchronized

---

## 4. Component Failure Tests

### 4.1 Database Disconnection

**Purpose:** Verify Controller operates without database.

**Procedure:**

```bash
# Stop database
sudo systemctl stop postgresql

# Observe Controller behavior for 5 minutes
sleep 300

# Restart database
sudo systemctl start postgresql
```

**Expected Behavior:**

1. Controller continues running (no crash)
2. Historian stops recording (with warning log)
3. Control operations continue
4. API returns cached data or errors gracefully
5. Database reconnects automatically

**Verification:**

```bash
# Check health endpoint
curl http://localhost:8000/api/v1/health

# Expected: database component shows UNHEALTHY
```

---

### 4.2 IPC Server Failure Simulation

**Purpose:** Verify API handles IPC failure gracefully.

**Procedure:**

1. Stop Controller: `sudo systemctl stop water-controller`
2. Try API endpoints
3. Restart Controller

**Expected Behavior:**

1. API returns 503 Service Unavailable
2. API does not crash
3. API reconnects when Controller restarts

---

### 4.3 Memory Pressure Test

**Purpose:** Verify system handles low memory conditions.

**Procedure:**

```bash
# Fill memory (be careful - this can crash the system)
stress-ng --vm 2 --vm-bytes 80% --timeout 60s
```

**Expected Behavior:**

1. Controller may slow down but not crash
2. No safety-critical operations missed
3. System recovers after stress ends

---

## 5. Authority Handoff Tests

### 5.1 Authority Request During Operation

**Purpose:** Verify authority handoff during active control.

**Procedure:**

1. Ensure Controller is connected and controlling
2. Issue authority release via API:
   ```bash
   curl -X POST http://localhost:8000/api/v1/rtus/$RTU_STATION/authority/release
   ```
3. Observe RTU behavior
4. Re-request authority:
   ```bash
   curl -X POST http://localhost:8000/api/v1/rtus/$RTU_STATION/authority/request
   ```

**Expected Behavior:**

1. RTU transitions to AUTONOMOUS
2. RTU maintains current actuator states
3. Authority epoch increments
4. Re-request succeeds with new epoch

---

### 5.2 Stale Command Rejection

**Purpose:** Verify commands with wrong epoch are rejected.

**Procedure:**

1. Note current authority epoch
2. Simulate disconnect/reconnect
3. Send command with old epoch

**Expected Behavior:**

1. Command rejected with WTC_ERROR_PERMISSION
2. Log shows "stale epoch" warning
3. RTU state unchanged

---

## 6. State Reconciliation Tests

### 6.1 State Mismatch After Partition

**Purpose:** Verify reconciliation handles state differences.

**Procedure:**

1. Establish connection with known state
2. Create network partition
3. Manually change actuator on RTU (via TUI)
4. Remove partition

**Expected Behavior:**

1. Reconciliation detects mismatch
2. Conflict callback invoked
3. Operator can choose to accept RTU state or force Controller state

---

### 6.2 State Persistence Test

**Purpose:** Verify state survives Controller restart.

**Procedure:**

1. Set specific actuator states
2. Stop Controller
3. Delete state files: `sudo rm /var/lib/wtc/state/*.state`
4. Restart Controller

**Expected Behavior:**

1. Controller should read state from RTU
2. No unexpected actuator changes
3. State files recreated

---

## 7. Alarm System Tests

### 7.1 Alarm Flood Detection

**Purpose:** Verify alarm flood detection triggers.

**Procedure:**

1. Configure alarm with very short delay
2. Create oscillating sensor value (above/below threshold rapidly)

**Expected Behavior:**

1. Alarm flood detected after 100 alarms in 10 minutes
2. Alarm suppression activated
3. "Alarm flood" warning in logs

---

### 7.2 Bad Quality Alarm Suppression

**Purpose:** Verify alarms don't trigger on bad quality data.

**Procedure:**

1. Configure sensor alarm
2. Force sensor quality to BAD (disconnect sensor on RTU)

**Expected Behavior:**

1. Value-based alarm does NOT trigger
2. BAD_QUALITY/FAULT alarm may trigger
3. Sensor shows quality = BAD in UI

---

## 8. Test Automation

### 8.1 Automated Test Script

```bash
#!/bin/bash
# fault_test.sh - Automated fault injection test suite

RTU_IP=${1:-192.168.1.50}
RTU_STATION=${2:-water-treat-rtu-01}
API_BASE="http://localhost:8000/api/v1"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

check_health() {
    curl -s "$API_BASE/health" | jq -r '.status'
}

test_network_partition() {
    log "TEST: Network partition"

    log "Creating partition..."
    sudo iptables -A OUTPUT -d $RTU_IP -j DROP
    sudo iptables -A INPUT -s $RTU_IP -j DROP

    log "Waiting for detection (10s)..."
    sleep 10

    # Check RTU status
    status=$(curl -s "$API_BASE/rtus/$RTU_STATION" | jq -r '.connection_state')
    if [[ "$status" == "OFFLINE" ]] || [[ "$status" == "ERROR" ]]; then
        log "PASS: RTU detected as offline"
    else
        log "FAIL: RTU status is $status (expected OFFLINE)"
    fi

    log "Removing partition..."
    sudo iptables -D OUTPUT -d $RTU_IP -j DROP
    sudo iptables -D INPUT -s $RTU_IP -j DROP

    log "Waiting for recovery (30s)..."
    sleep 30

    status=$(curl -s "$API_BASE/rtus/$RTU_STATION" | jq -r '.connection_state')
    if [[ "$status" == "RUNNING" ]]; then
        log "PASS: RTU reconnected"
    else
        log "FAIL: RTU did not reconnect (status: $status)"
    fi
}

test_latency() {
    log "TEST: High latency"

    log "Adding 500ms latency..."
    sudo tc qdisc add dev eth0 root netem delay 500ms

    sleep 30

    health=$(check_health)
    log "System health during latency: $health"

    sudo tc qdisc del dev eth0 root

    sleep 10
    health=$(check_health)
    log "System health after recovery: $health"
}

# Run tests
log "Starting fault injection tests"
log "RTU IP: $RTU_IP, Station: $RTU_STATION"

test_network_partition
test_latency

log "Tests complete"
```

---

## 9. Test Log Template

| Test Case | Date | Tester | Result | Notes |
|-----------|------|--------|--------|-------|
| 2.1 Complete Partition | | | Pass/Fail | |
| 2.2 Asymmetric Partition | | | Pass/Fail | |
| 2.3 Packet Loss | | | Pass/Fail | |
| 2.4 Latency | | | Pass/Fail | |
| 3.1 Controller Power Cycle | | | Pass/Fail | |
| 3.2 RTU Power Cycle | | | Pass/Fail | |
| 4.1 Database Disconnect | | | Pass/Fail | |
| 5.1 Authority Handoff | | | Pass/Fail | |
| 6.1 State Mismatch | | | Pass/Fail | |

---

## 10. Safety Considerations

1. **Never run fault injection on production systems without authorization**
2. **Ensure process is in safe state before testing**
3. **Have physical access to equipment for emergency stop**
4. **Document all changes made during testing**
5. **Restore all configurations after testing**

---

*Document prepared for Water-Controller production readiness*
