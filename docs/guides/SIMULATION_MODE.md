# Simulation Mode

Water Treatment Controller includes a comprehensive simulation mode for testing, training, and development without requiring physical PROFINET hardware or RTU devices.

## Overview

Simulation mode provides:

- **Virtual RTUs** - Simulated water treatment plant devices with realistic sensor data
- **Dynamic Values** - Time-varying sensor readings with configurable noise and trends
- **Alarm Generation** - Automatic alarm triggering based on threshold crossings
- **Actuator Response** - Commands are accepted and logged
- **Full API Compatibility** - All REST endpoints work normally with simulated data

## Quick Start

### Option 1: Command Line Flag

```bash
./water_treat_controller --simulation
```

### Option 2: Environment Variable

```bash
export WTC_SIMULATION_MODE=1
./water_treat_controller
```

### Option 3: Python API Only

```bash
export WTC_DEMO_MODE=1
cd web/api && uvicorn app.main:app
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WTC_SIMULATION_MODE` | Enable simulation mode (`1`, `true`, `yes`) | `false` |
| `WTC_SIMULATION_SCENARIO` | Scenario to load (see below) | `water_treatment_plant` |
| `WTC_DEMO_MODE` | Enable Python demo mode (alias for simulation) | `false` |
| `WTC_DEMO_SCENARIO` | Python demo scenario (alias) | `water_treatment_plant` |

### Command Line Options

```
-s, --simulation         Run in simulation mode (no real hardware)
--scenario <name>        Simulation scenario to load
```

## Available Scenarios

### `water_treatment_plant` (Default)

Full water treatment plant simulation with 5 RTUs:

| RTU | Description | Sensors | Actuators |
|-----|-------------|---------|-----------|
| `intake-rtu-01` | Raw water intake | RAW_FLOW, RAW_TURB, RAW_PH, INTAKE_LEVEL | INTAKE_VALVE, INTAKE_PUMP |
| `clarifier-rtu-01` | Clarification process | CLAR_TURB, SLUDGE_LEVEL, COAG_FLOW | COAG_PUMP, FLOC_MIXER, SLUDGE_VALVE |
| `filter-rtu-01` | Filtration system | FILT_TURB, FILT_DP, FILT_FLOW | FILT_INLET, BACKWASH |
| `disinfect-rtu-01` | Disinfection | CL2_RESIDUAL, CL2_FLOW, CONTACT_TIME | CL2_PUMP (PWM) |
| `distrib-rtu-01` | Distribution | CLEARWELL_LVL, DIST_PRESS, DIST_FLOW | HIGH_LIFT_1, HIGH_LIFT_2, DIST_VALVE |

### `normal`

Single demo RTU with basic sensors (temperature, pressure, flow, level).

### `alarms`

Normal scenario with sensors pre-configured to trigger alarms:
- High temperature alarm
- Low pressure alarm

### `high_load`

Water treatment plant with all values near alarm thresholds.

### `maintenance`

Water treatment plant with `clarifier-rtu-01` offline.

### `startup`

Normal scenario with RTU in CONNECTING state.

## Architecture

Simulation mode operates at two layers:

```
┌─────────────────────────────────────────────────────────────┐
│                    Web UI (React/Next.js)                   │
└─────────────────────────────┬───────────────────────────────┘
                              │
┌─────────────────────────────┴───────────────────────────────┐
│                   FastAPI Backend (Python)                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ profinet_client.py                                  │    │
│  │   ↓ (checks WTC_SIMULATION_MODE)                   │    │
│  │ demo_mode.py ← Generates sensor values, alarms     │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────┬───────────────────────────────┘
                              │ (Shared Memory IPC)
┌─────────────────────────────┴───────────────────────────────┐
│                   C Controller (Optional)                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ main.c --simulation                                 │    │
│  │   ↓                                                 │    │
│  │ simulator.c ← Populates RTU registry with virtual   │    │
│  │               devices, updates sensor values        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Python-Only Simulation

When running only the Python API (no C controller):
1. Set `WTC_DEMO_MODE=1`
2. `demo_mode.py` generates all data
3. No shared memory connection required
4. Full API functionality available

### Full Stack Simulation

When running the complete system in simulation mode:
1. C controller starts with `--simulation`
2. `simulator.c` creates virtual RTUs in the registry
3. IPC server exposes data via shared memory
4. Python API reads from shared memory (or falls back to demo mode)

## Sensor Value Generation

Simulated sensors use this formula:

```
value = base_value + trend + noise
```

Where:
- **base_value** - Nominal operating value
- **trend** - Sinusoidal variation: `amplitude * sin(2π * t / period)`
- **noise** - Random variation: `uniform(-amplitude, +amplitude)`

Values are clamped to configured min/max limits.

### Example: Raw Water Turbidity

```
Base: 12 NTU
Noise: ±2 NTU
Trend: ±3 NTU over 30 minute period
Range: 0-100 NTU
Alarm High: 25 NTU
```

## Alarm Simulation

Alarms are automatically triggered when:
- Sensor value exceeds `alarm_high` threshold
- Sensor value falls below `alarm_low` threshold

Alarms clear automatically when values return to normal range.

## Fault Injection (C Layer)

For training scenarios, faults can be injected via the C simulator API:

```c
// Inject communication fault on an RTU
simulator_inject_fault(simulator, "intake-rtu-01", FAULT_COMM_LOSS);

// Clear the fault
simulator_clear_fault(simulator, "intake-rtu-01");
```

Fault types:
- Communication loss (sensors show BAD quality)
- Sensor failure
- Actuator failure

## PID Loop Simulation

The demo mode includes simulated PID control loops:

| Loop | Description | Input | Output | Setpoint |
|------|-------------|-------|--------|----------|
| Chlorine Control | Maintains CL2 residual | CL2_RESIDUAL | CL2_PUMP PWM | 1.8 mg/L |
| Level Control | Maintains clearwell level | CLEARWELL_LVL | FILT_INLET | 80% |
| Pressure Control | Maintains distribution pressure | DIST_PRESS | HIGH_LIFT_1 | 55 PSI |

## API Usage

All standard API endpoints work in simulation mode:

```bash
# Get RTU list
curl http://localhost:8000/api/v1/rtus

# Get sensor values
curl http://localhost:8000/api/v1/rtus/intake-rtu-01/sensors

# Command actuator
curl -X POST http://localhost:8000/api/v1/rtus/intake-rtu-01/actuators/5/command \
  -H "Content-Type: application/json" \
  -d '{"command": 1}'

# Get active alarms
curl http://localhost:8000/api/v1/alarms

# Check simulation status
curl http://localhost:8000/api/v1/demo/status
```

## Demo Mode API Endpoints

When demo mode is enabled, additional endpoints are available:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/demo/status` | GET | Get simulation status and statistics |
| `/api/v1/demo/enable` | POST | Enable demo mode with scenario |
| `/api/v1/demo/disable` | POST | Disable demo mode |

## Use Cases

### Development

```bash
# Run API with simulation for frontend development
WTC_DEMO_MODE=1 WTC_DEMO_SCENARIO=water_treatment_plant \
  uvicorn app.main:app --reload
```

### Operator Training

```bash
# Full stack simulation for training
./water_treat_controller --simulation --scenario alarms
```

### Integration Testing

```bash
# E2E tests with consistent simulated data
WTC_SIMULATION_MODE=1 pytest tests/e2e/
```

### CI/CD Pipeline

```yaml
# GitHub Actions example
- name: Run API tests
  env:
    WTC_DEMO_MODE: "1"
  run: pytest tests/
```

## Limitations

- **No real I/O** - Actuator commands are logged but have no physical effect
- **Simplified physics** - Process dynamics are approximated, not modeled
- **No network simulation** - PROFINET protocol not exercised in simulation
- **Static topology** - RTU configuration is predefined per scenario

## Troubleshooting

### Simulation not starting

Check environment variables are set correctly:
```bash
echo $WTC_SIMULATION_MODE  # Should be "1" or "true"
```

### No data in API

Verify demo mode is enabled:
```bash
curl http://localhost:8000/api/v1/demo/status
# Should show: {"enabled": true, "scenario": "water_treatment_plant", ...}
```

### C controller not finding simulator

Ensure the `--simulation` flag is passed:
```bash
./water_treat_controller --simulation -v  # Verbose output
# Look for: "*** SIMULATION MODE ENABLED ***"
```
