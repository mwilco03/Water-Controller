# Safety Interlock Documentation Template

**System:** [System Name]
**Site:** [Site Name]
**Document Version:** [X.Y]
**Last Updated:** [Date]
**Approved By:** [Name, Title]

---

## Document Purpose

This document defines all safety interlocks implemented in the water treatment control system. Interlocks are safety-critical functions that automatically protect equipment and personnel by forcing actuators to safe states when dangerous conditions are detected.

**CRITICAL:** Interlocks execute on the RTU (SBC #2), NOT the Controller (SBC #1). This ensures they operate even when network communication is lost.

---

## Interlock Summary Table

| ID | Name | Sensor | Threshold | Target | Action | Delay | Override |
|----|------|--------|-----------|--------|--------|-------|----------|
| IL-001 | | | | | | | |
| IL-002 | | | | | | | |
| IL-003 | | | | | | | |
| IL-004 | | | | | | | |
| IL-005 | | | | | | | |

---

## Interlock Detailed Specifications

### IL-001: [Interlock Name]

#### Purpose
[Describe what this interlock protects and why it is necessary]

#### Configuration

| Parameter | Value | Units | Notes |
|-----------|-------|-------|-------|
| Interlock ID | IL-001 | | |
| Monitored Sensor | | | Slot: |
| Condition | ABOVE / BELOW | | |
| Trip Threshold | | | |
| Reset Threshold | | | With hysteresis |
| Target Actuator | | | Slot: |
| Interlock Action | OFF / ON / PWM | | |
| Trip Delay | | ms | |
| Allow Override | YES / NO | | |
| Auto-Reset | YES / NO | | |

#### Behavior Diagram

```
                    Trip Threshold
                         │
    Normal Operation     │     Trip Zone
         ◄───────────────┼──────────────►
                         │
                    ┌────┴────┐
                    │ Sensor  │
                    │  Value  │
                    └────┬────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              │              ▼
    Value < Threshold    │       Value ≥ Threshold
          │              │              │
          ▼              │              ▼
    No Action            │       Wait [Delay]
                         │              │
                         │              ▼
                         │       Force [Actuator] to [State]
                         │              │
                         │              ▼
                         │       Log Event
                         │              │
                         │       Value < Reset Threshold?
                         │              │
                         ├──────────────┘
                         │       YES (with auto-reset)
                         ▼
                    Release Interlock
```

#### Test Procedure

1. **Preparation:**
   - Ensure safe conditions for testing
   - Notify operations personnel
   - Record current process state

2. **Test Execution:**
   - Gradually increase/decrease sensor value toward threshold
   - OR simulate sensor value using test input
   - Verify actuator trips within specified delay
   - Record response time: __________ ms

3. **Recovery Test:**
   - Return sensor to normal range
   - Verify interlock releases (if auto-reset) OR requires acknowledgment
   - Verify actuator returns to normal control

4. **Documentation:**
   - Record test date: __________
   - Tested by: __________
   - Result: PASS / FAIL

#### Failure Modes

| Failure | Detection | Response |
|---------|-----------|----------|
| Sensor failure | Quality = BAD | Trip interlock (fail-safe) |
| Communication loss | PROFINET timeout | Maintain tripped state |
| Actuator failure | Feedback mismatch | Generate alarm |

---

### IL-002: [Interlock Name]

[Repeat structure from IL-001]

---

## Interlock Categories

### Equipment Protection Interlocks

These interlocks protect physical equipment from damage:

| ID | Protected Equipment | Hazard |
|----|-------------------|--------|
| | | |

### Process Protection Interlocks

These interlocks maintain process integrity:

| ID | Process Boundary | Consequence if Exceeded |
|----|-----------------|------------------------|
| | | |

### Environmental Protection Interlocks

These interlocks prevent environmental release:

| ID | Containment | Release Type |
|----|------------|--------------|
| | | |

---

## Interlock Priority Matrix

When multiple interlocks affect the same actuator:

| Priority | Interlock IDs | Rationale |
|----------|--------------|-----------|
| 1 (Highest) | | |
| 2 | | |
| 3 (Lowest) | | |

**Rule:** Higher priority interlocks override lower priority. An actuator remains in its tripped state until ALL interlocks affecting it have cleared.

---

## Maintenance Requirements

### Periodic Testing

| Interlock | Test Frequency | Last Test | Next Test | Responsible |
|-----------|---------------|-----------|-----------|-------------|
| | Monthly / Quarterly / Annual | | | |

### Calibration Dependencies

| Interlock | Dependent Sensors | Calibration Schedule |
|-----------|------------------|---------------------|
| | | |

---

## Change Management

### Modification Procedure

1. Document proposed change with justification
2. Perform hazard analysis (HAZOP/LOPA as appropriate)
3. Obtain approval from [Authority]
4. Implement change in test environment
5. Verify interlock function
6. Deploy to production during planned outage
7. Update this documentation
8. Conduct operator training if needed

### Change Log

| Date | Interlock | Change | Authorized By | Reference |
|------|-----------|--------|--------------|-----------|
| | | | | |

---

## Emergency Procedures

### Interlock Bypass

**WARNING:** Bypassing interlocks removes safety protection. Only authorized personnel may bypass interlocks, and only with appropriate compensating measures in place.

**Bypass Authorization:** [Title/Role authorized to approve]

**Bypass Documentation:**
- Reason for bypass: __________
- Compensating measures: __________
- Duration: __________
- Authorized by: __________
- Returned to service: __________

### Interlock Failure Response

If an interlock fails to function correctly:

1. Immediately place system in safe state manually
2. Notify operations supervision
3. Do not restart until interlock is repaired and tested
4. Document failure and root cause

---

## Appendix A: Interlock Logic Diagrams

[Include logic diagrams for complex interlocks]

## Appendix B: Interlock Test Records

[Attach or reference test record forms]

## Appendix C: Reference Standards

- IEC 61511: Functional Safety - Safety Instrumented Systems
- ISA-84: Application of Safety Instrumented Systems
- IEC 62443: Industrial Automation Security

---

*This document is controlled. Printed copies are for reference only.*
*Master copy location: [Repository/System]*
