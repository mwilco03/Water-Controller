# Failure Mode Analysis

This document describes how the Water-Controller SCADA system behaves under various failure conditions and the safe-state design decisions.

## Design Philosophy

**Fail-Safe First**: When in doubt, the system should fail to a safe state. For water treatment:
- Pumps OFF is safer than pumps ON (prevents overflow, chemical overdose)
- Valves CLOSED is generally safer (prevents uncontrolled flow)
- Alarms should trigger on sensor failure, not suppress

## Quality State Model

All sensor data carries a quality indicator (OPC UA compatible):

| Quality | Code | Meaning | Control Decision |
|---------|------|---------|------------------|
| GOOD | 0x00 | Fresh, validated data | Use for control |
| UNCERTAIN | 0x40 | Stale (5-60s) or degraded | Use with caution, log warning |
| BAD | 0x80 | Sensor fault or stale >60s | Do not use for control |
| NOT_CONNECTED | 0xC0 | No communication >5min | Do not use, fail-safe |

### Quality Propagation Path

```
RTU Sensor → PROFINET (5-byte format) → Controller Registry → Quality Check
                                                                    ↓
                                          ┌─────────────────────────┼─────────────────────────┐
                                          ↓                         ↓                         ↓
                                     Historian                 Alarm Manager            Control Engine
                                   (stores quality)          (quality-aware)          (quality-aware)
```

---

## Failure Mode 1: RTU Disconnect

### Symptoms
- PROFINET AR goes to OFFLINE state
- Sensor data stops updating
- Timestamp age increases

### Current Behavior
1. **Immediate** (0-5s): Data marked as GOOD, timestamp preserved
2. **Stale** (5-60s): Quality degrades to UNCERTAIN
3. **Extended** (60s-5min): Quality degrades to BAD
4. **Disconnected** (>5min): Quality set to NOT_CONNECTED

### Control Engine Response
- **PID Loops**: Hold last output for up to 10 seconds (COMM_LOSS_TIMEOUT_MS), then go to OFF
- **Interlocks**: Immediately trip on BAD/NOT_CONNECTED quality (fail-safe)

### Historian Behavior
- Continues recording last known value with degraded quality
- Samples flagged with actual quality state

### HMI Behavior
- Yellow indicator (UNCERTAIN)
- Red indicator (BAD)
- Grey with "?" (NOT_CONNECTED)
- Connection banner shows RTU offline

### Recovery
- Automatic on PROFINET AR reconnection
- Quality returns to GOOD when fresh data arrives
- PID loops resume after quality restored

---

## Failure Mode 2: Partial Fieldbus Failure

### Symptoms
- Some slots update, others don't
- Individual sensor IOPS goes BAD
- Intermittent communication

### Current Behavior
1. **Per-slot quality tracking**: Each sensor maintains independent quality
2. **Mixed quality allowed**: System continues with available sensors
3. **Affected sensors**: Individual quality degradation

### Control Engine Response
- PID loops with BAD input: Hold output, then go to safe state
- PID loops with GOOD input: Continue normal operation
- Interlocks with BAD input: Trip immediately (fail-safe)

### Alarm Manager Response
- Alarms suppressed for BAD quality (can't trust the value)
- Separate BAD_QUALITY alarm condition available

---

## Failure Mode 3: Historian/Database Write Failure

### Symptoms
- Disk full or I/O error
- Database connection lost
- Write timeouts

### Current Behavior
1. **Ring buffer overflow**: Oldest samples dropped, warning logged
2. **Flush failure**: Individual tag errors logged, other tags continue
3. **Directory creation**: Safe mkdir (no shell injection risk)

### Data Loss Prevention
- In-memory ring buffer provides 1000 samples per tag buffer
- At 1Hz sample rate: ~16 minutes of data retention
- Overflow warning logged at rate-limit of once per minute

### Recovery
- Automatic on storage availability
- No sample loss if buffer doesn't overflow
- System continues operation (non-blocking)

---

## Failure Mode 4: Controller Restart

### Symptoms
- All PROFINET ARs disconnect
- Configuration reload
- State machine reset

### Current Behavior

#### During Shutdown
1. Configuration saved to database
2. All components stopped in reverse order
3. PROFINET ARs closed gracefully

#### During Startup
1. Database connected (optional, runs without)
2. RTU registry initialized
3. PROFINET/Simulator started
4. Control engine started (PID loops in OFF mode)
5. Alarm manager started
6. Historian started
7. Configuration loaded from database

### RTU Behavior During Controller Restart
- RTU continues autonomous operation (interlocks active)
- Authority remains with RTU until controller reconnects
- Actuator states preserved at RTU level

### Recovery
- PROFINET discovery finds RTUs
- Authority handoff from AUTONOMOUS to SUPERVISED
- PID loops require manual restart (safety)

---

## Failure Mode 5: Sensor Fault

### Symptoms
- Value out of range (NaN, Inf)
- Quality byte indicates BAD
- No change over extended period

### Current Behavior
1. **PROFINET layer**: Sets quality to BAD
2. **RTU registry**: Preserves BAD quality
3. **Control engine**: Rejects BAD quality input
4. **Alarm manager**: Triggers BAD_QUALITY alarm

### PID Loop Response
- Input fault logged
- Output held for timeout period
- Safe state (OFF) after timeout

### Interlock Response
- Fail-safe: Treat BAD quality as trip condition
- Immediate action taken

---

## Failure Mode 6: Communication Loss Between Controller and RTU

### Symptoms
- Watchdog timeout on PROFINET AR
- No cyclic data exchange
- Controller cannot send commands

### RTU Behavior (Autonomous Mode)
- RTU maintains local control
- Local interlocks remain active
- Actuator states held (or go to configured safe state)

### Controller Behavior
- Quality degrades over time
- Alarms raised for offline RTUs
- Failover triggered (if configured)

### Authority Handoff
1. Controller sets `AUTHORITY_RELEASING`
2. RTU receives release, sets `AUTHORITY_AUTONOMOUS`
3. RTU operates independently
4. On reconnect: Controller requests `AUTHORITY_HANDOFF_PENDING`
5. RTU acknowledges, grants `AUTHORITY_SUPERVISED`

---

## Safe-State Configuration

### Actuator Default States

| Actuator Type | Default Safe State | Reason |
|---------------|-------------------|--------|
| Pump | OFF | Prevents overflow |
| Valve | CLOSED | Prevents uncontrolled flow |
| Relay | OFF | De-energized safe state |
| PWM Output | 0% | Minimum output |

### Interlock Fail-Safe Design
- Bad quality input triggers interlock (assumes worst case)
- Interlock trip is sticky (requires manual reset)
- Interlock bypass logged to audit trail

### PID Loop Fail-Safe Design
- Communication loss: Output to OFF after 10s timeout
- Watchdog: Output reduced to midpoint after 5s at limit
- Mode change: Bumpless transfer preserves integral

---

## Observability

### Key Metrics to Monitor

1. **Quality Distribution**: Percent of sensors in each quality state
2. **Staleness Age**: Maximum data age across all sensors
3. **Communication Health**: Packet loss, cycle overruns
4. **Alarm Rate**: Alarms per 10 minutes (ISA-18.2 flood detection)
5. **Buffer Utilization**: Historian ring buffer fill level

### Alerting Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Sensors UNCERTAIN | >10% | >25% |
| Sensors BAD | >0% | >5% |
| Sensors NOT_CONNECTED | >0% | >1% |
| Max Data Age | >30s | >60s |
| Packet Loss | >1% | >5% |
| Alarm Rate | >50/10min | >100/10min |

---

## Testing Failure Scenarios

### Simulation Mode
Use `--simulation` flag to test without hardware:
```bash
./water-controller --simulation --scenario alarms
```

### Scenarios Available
- `normal`: Steady-state operation
- `startup`: Initial system startup
- `alarms`: Various alarm conditions
- `high_load`: Stress testing
- `maintenance`: Maintenance mode simulation

### Recommended Tests
1. **RTU disconnect**: Kill RTU simulator, verify fail-safe
2. **Quality degradation**: Inject BAD quality, verify PID holds
3. **Interlock trip**: Inject out-of-range value, verify action
4. **Historian overflow**: Fill buffer, verify warning

---

## Recovery Procedures

### RTU Reconnection
1. Verify physical connection (network cable, power)
2. Check PROFINET discovery (`dcp_discover`)
3. Connect RTU via HMI or API
4. Verify quality returns to GOOD
5. Manually restart PID loops if needed

### Alarm Flood Recovery
1. Acknowledge critical alarms first
2. Identify root cause (often single sensor failure)
3. Shelve non-critical alarms temporarily
4. Fix root cause
5. Clear shelved alarms

### Database Recovery
1. Check disk space
2. Verify database connection
3. System will reconnect automatically
4. Data in ring buffer preserved if under 16 minutes

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-12-22 | Initial failure mode documentation |
