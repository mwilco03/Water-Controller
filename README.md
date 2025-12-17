# Water Treatment Controller

A PROFINET IO Controller for Water Treatment RTU Networks, implementing industrial-grade process control, alarm management, and data historian functionality.

## Overview

This project implements a complete SCADA/DCS system for water treatment facilities, featuring:

- **PROFINET IO Controller**: Real-time communication with RTU devices using PROFINET RT Class 1
- **RTU Registry**: Device discovery, configuration, and state management
- **Control Engine**: PID loops, interlocks, and sequence control for automated process operation
- **Alarm Management**: ISA-18.2 compliant alarm system with acknowledgment, suppression, and shelving
- **Data Historian**: Time-series data storage with deadband and swinging-door compression
- **Web HMI**: FastAPI backend with REST API and WebSocket real-time streaming

## Architecture

```
+------------------+     +------------------+     +------------------+
|   Web HMI/API    |     |   Control Engine |     |  Alarm Manager   |
|   (FastAPI)      |     |   (PID/Interlock)|     |  (ISA-18.2)      |
+--------+---------+     +--------+---------+     +--------+---------+
         |                        |                        |
         +------------------------+------------------------+
                                  |
                    +-------------+-------------+
                    |       RTU Registry        |
                    |    (Device Management)    |
                    +-------------+-------------+
                                  |
                    +-------------+-------------+
                    |   PROFINET Controller     |
                    |  (DCP, AR, Cyclic I/O)    |
                    +-------------+-------------+
                                  |
         +------------------------+------------------------+
         |                        |                        |
+--------+--------+    +----------+--------+    +----------+--------+
|  RTU Tank 1     |    |  RTU Pump Station |    |  RTU Filter 1     |
|  192.168.1.100  |    |  192.168.1.101    |    |  192.168.1.102    |
+-----------------+    +-------------------+    +-------------------+
```

## RTU Slot Architecture

Each Water Treatment RTU supports 16 I/O slots:

| Slot | Type | Function |
|------|------|----------|
| 1 | Sensor | pH (0-14) |
| 2 | Sensor | Temperature (0-100 C) |
| 3 | Sensor | Turbidity (0-1000 NTU) |
| 4 | Sensor | TDS (0-2000 ppm) |
| 5 | Sensor | Dissolved Oxygen (0-20 mg/L) |
| 6 | Sensor | Flow Rate (0-500 L/min) |
| 7 | Sensor | Level (0-100%) |
| 8 | Sensor | Pressure (0-10 bar) |
| 9 | Actuator | Main Pump (On/Off) |
| 10 | Actuator | Inlet Valve (On/Off) |
| 11 | Actuator | Outlet Valve (On/Off) |
| 12 | Actuator | Dosing Pump (PWM) |
| 13 | Actuator | Aerator (On/Off) |
| 14 | Actuator | Heater (PWM) |
| 15 | Actuator | Mixer (On/Off) |
| 16 | Actuator | Spare |

## Building

### Prerequisites

- CMake 3.16+
- GCC or Clang with C11 support
- libpq (PostgreSQL client library)
- libjson-c
- Python 3.11+ (for web backend)

### Build Commands

```bash
# Create build directory
mkdir build && cd build

# Configure
cmake -DCMAKE_BUILD_TYPE=Release ..

# Build
make -j$(nproc)

# Run tests
make test
```

### Docker Deployment

```bash
# Start all services
cd docker
docker-compose up -d

# Start with PROFINET controller (requires host network)
docker-compose --profile profinet up -d
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WT_INTERFACE` | Network interface for PROFINET | `eth0` |
| `WT_CYCLE_TIME` | Cycle time in milliseconds | `1000` |
| `WT_LOG_LEVEL` | Logging level (DEBUG, INFO, WARN, ERROR) | `INFO` |
| `DATABASE_URL` | PostgreSQL connection string | - |
| `REDIS_URL` | Redis connection string | - |

### Command Line Options

```
water_treat_controller [OPTIONS]

Options:
  -i, --interface <name>    Network interface for PROFINET
  -t, --cycle-time <ms>     Cycle time in milliseconds
  -c, --config <file>       Configuration file path
  -v, --verbose             Enable verbose logging
  -h, --help                Show help message
```

## API Endpoints

### RTU Management

- `GET /api/v1/rtus` - List all RTUs
- `GET /api/v1/rtus/{station_name}` - Get RTU details
- `GET /api/v1/rtus/{station_name}/sensors` - Get sensor values
- `GET /api/v1/rtus/{station_name}/actuators` - Get actuator states
- `POST /api/v1/rtus/{station_name}/actuators/{slot}` - Command actuator

### Alarm Management

- `GET /api/v1/alarms` - Get active alarms
- `GET /api/v1/alarms/history` - Get alarm history
- `POST /api/v1/alarms/{alarm_id}/acknowledge` - Acknowledge alarm
- `GET /api/v1/alarms/rules` - List alarm rules
- `POST /api/v1/alarms/rules` - Create alarm rule

### Control Loops

- `GET /api/v1/control/pid` - List PID loops
- `GET /api/v1/control/pid/{loop_id}` - Get PID loop details
- `PUT /api/v1/control/pid/{loop_id}/setpoint` - Update setpoint
- `PUT /api/v1/control/pid/{loop_id}/tuning` - Update tuning parameters

### Trends/Historian

- `GET /api/v1/trends/tags` - List historian tags
- `GET /api/v1/trends/{tag_id}` - Get trend data

### WebSocket Endpoints

- `WS /ws/realtime` - Real-time sensor data streaming
- `WS /ws/alarms` - Alarm notifications

## Project Structure

```
Water-Controller/
├── CMakeLists.txt
├── src/
│   ├── main.c                    # Application entry point
│   ├── types.h                   # Common type definitions
│   ├── profinet/                 # PROFINET controller stack
│   │   ├── profinet_controller.c/h
│   │   ├── dcp_discovery.c/h
│   │   ├── ar_manager.c/h
│   │   ├── profinet_frame.c/h
│   │   └── cyclic_exchange.c
│   ├── registry/                 # RTU device registry
│   │   ├── rtu_registry.c/h
│   │   └── slot_manager.c
│   ├── control/                  # Control logic engine
│   │   ├── control_engine.c/h
│   │   ├── pid_loop.c
│   │   ├── interlock_manager.c
│   │   └── sequence_engine.c
│   ├── alarms/                   # Alarm management
│   │   └── alarm_manager.c/h
│   ├── historian/                # Data historian
│   │   └── historian.c/h
│   └── utils/                    # Utility functions
│       ├── logger.c/h
│       ├── time_utils.c/h
│       ├── buffer.c/h
│       └── crc.c/h
├── web/
│   └── api/
│       ├── main.py               # FastAPI application
│       └── requirements.txt
├── docker/
│   ├── docker-compose.yml
│   ├── Dockerfile.controller
│   └── Dockerfile.web
└── tests/
    ├── test_profinet.c
    ├── test_control.c
    ├── test_alarms.c
    ├── test_historian.c
    └── test_registry.c
```

## Standards Compliance

- **PROFINET**: IEC 61158, IEC 61784
- **Alarm Management**: ISA-18.2 / IEC 62682
- **OPC Quality Codes**: OPC UA Part 8
- **Data Compression**: Swinging Door Trending (SDT)

## License

Copyright (C) 2024

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

SPDX-License-Identifier: GPL-3.0-or-later

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `make test`
5. Submit a pull request

## Support

For issues and questions, please open a GitHub issue.
