# Water Treatment Controller

A PROFINET IO Controller for Water Treatment RTU Networks, implementing industrial-grade process control, alarm management, and data historian functionality.

## Overview

This project implements a complete SCADA/DCS system for water treatment facilities, featuring:

- **PROFINET IO Controller**: Real-time communication with RTU devices using PROFINET RT Class 1
- **RTU Registry**: Device discovery, configuration, and state management
- **Control Engine**: PID loops, interlocks, and sequence control for automated process operation
- **Alarm Management**: ISA-18.2 compliant alarm system with acknowledgment, suppression, and shelving
- **Data Historian**: Time-series data storage with deadband and swinging-door compression
- **Modbus Gateway**: Protocol bridge for PROFINET-to-Modbus TCP/RTU translation
- **Web HMI**: FastAPI backend with REST API and WebSocket real-time streaming
- **Backup/Restore**: Configuration backup with import/export functionality
- **systemd Integration**: Full service management with systemctl

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

## Two-Plane Architecture

This system implements a clear separation between **two operational planes**:

### RTU/Sensor Plane (Field Layer)

The RTU plane contains all physical I/O devices directly connected to the process:

- **Sensors**: pH probes, temperature sensors, flow meters, level transmitters, pressure transducers
- **Actuators**: Pumps, valves, heaters, aerators, mixers, dosing systems

**Important**: Actuators and sensors are NOT directly controlled by this controller. All physical I/O is managed through the RTU (Remote Terminal Unit). Commands to actuators are sent **to the RTU**, which then controls the physical device. This provides:

- Electrical isolation between control systems and field devices
- Local safety interlocks on the RTU
- Continued operation during controller communication loss
- Standardized PROFINET interface regardless of physical I/O type

```
[Physical World]
      |
      v
+-----------------+
|   RTU Device    |  <-- Physical sensors/actuators connect HERE
|  (Water-Treat)  |
+-----------------+
      |
      | PROFINET
      v
+-----------------+
|   Controller    |  <-- This codebase (commands flow THROUGH RTU)
|  (This Project) |
+-----------------+
```

### Controller Plane (Management Layer)

The controller plane provides supervisory functions:

| Function | Description |
|----------|-------------|
| **HMI/Web Interface** | Real-time visualization, operator interaction |
| **Data Collection** | Historian, trending, long-term storage |
| **State Monitoring** | Connection status, configuration drift detection |
| **Alarm Management** | ISA-18.2 compliant alarm handling, notifications |
| **Control Logic** | PID loops, sequences (commands sent via RTU) |
| **External Communication** | Modbus gateway, log forwarding, SIEM integration |
| **Failover Management** | RTU health monitoring, reconnection handling |
| **Configuration Management** | Database-backed config, backup/restore |
| **Authentication** | User access control, AD group integration |

### Communication Flow

```
User Action (e.g., "Turn on pump")
            |
            v
    [Web HMI / API]
            |
            v
    [Controller Engine]
            |
            v
    [PROFINET IO Controller]
            |
            | Cyclic I/O Frame
            v
    [RTU Device] <-- Command processed HERE
            |
            v
    [Physical Actuator] <-- Pump turns on
```

### Failover Behavior

When communication is lost to an RTU:

1. **Controller Side**: Marks RTU as OFFLINE, triggers alarms, continues monitoring
2. **RTU Side**: Maintains last known state or enters safe mode (RTU firmware responsibility)
3. **On Reconnection**: Controller detects RTU online, resumes cyclic data exchange, clears communication alarms

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

## Quick Start

```bash
# Clone and build
git clone https://github.com/mwilco03/Water-Controller.git
cd Water-Controller

# Install (as root)
sudo ./scripts/install.sh

# Start services
sudo systemctl start water-controller

# Access web UI
open http://localhost:3000
```

For detailed deployment instructions, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

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

### Modbus Gateway

- `GET /api/v1/modbus/config` - Get Modbus gateway configuration
- `PUT /api/v1/modbus/config` - Update configuration
- `GET /api/v1/modbus/mappings` - List register mappings
- `POST /api/v1/modbus/mappings` - Create register mapping
- `GET /api/v1/modbus/downstream` - List downstream devices
- `POST /api/v1/modbus/downstream` - Add downstream device
- `GET /api/v1/modbus/stats` - Get gateway statistics

### Backup/Restore

- `GET /api/v1/backups` - List available backups
- `POST /api/v1/backups` - Create new backup
- `GET /api/v1/backups/{id}/download` - Download backup
- `POST /api/v1/backups/{id}/restore` - Restore from backup
- `GET /api/v1/system/config` - Export configuration
- `POST /api/v1/system/config` - Import configuration

### Services

- `GET /api/v1/services` - List service status
- `POST /api/v1/services/{name}/{action}` - Control service (start/stop/restart)

### Authentication

- `POST /api/v1/auth/login` - Authenticate user (AD or local)
- `POST /api/v1/auth/logout` - Logout and invalidate session
- `GET /api/v1/auth/session` - Validate session token
- `GET /api/v1/auth/ad-config` - Get AD configuration
- `PUT /api/v1/auth/ad-config` - Update AD configuration

### Log Forwarding

- `GET /api/v1/logging/config` - Get log forwarding configuration
- `PUT /api/v1/logging/config` - Update log forwarding configuration
- `POST /api/v1/logging/test` - Send test log message
- `GET /api/v1/logging/destinations` - List available log destinations (Syslog, Elastic, Graylog)

### WebSocket Endpoints

- `WS /ws/realtime` - Real-time sensor data streaming
- `WS /ws/alarms` - Alarm notifications

## Project Structure

```
Water-Controller/
├── CMakeLists.txt
├── README.md
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
│   ├── modbus/                   # Modbus gateway
│   │   ├── modbus_common.c/h     # CRC, PDU builders
│   │   ├── modbus_tcp.c/h        # TCP client/server
│   │   ├── modbus_rtu.c/h        # RTU serial client/server
│   │   ├── register_map.c/h      # Register mapping
│   │   └── modbus_gateway.c/h    # Gateway engine
│   └── utils/                    # Utility functions
│       ├── logger.c/h
│       ├── time_utils.c/h
│       ├── buffer.c/h
│       └── crc.c/h
├── web/
│   ├── api/
│   │   ├── main.py               # FastAPI application
│   │   ├── shm_client.py         # Shared memory IPC
│   │   └── requirements.txt
│   └── ui/
│       └── src/app/              # Next.js React UI
│           ├── page.tsx          # Dashboard
│           ├── alarms/           # Alarm management
│           ├── control/          # PID control
│           ├── rtus/             # RTU management
│           ├── trends/           # Historical trends
│           ├── login/            # Authentication
│           └── settings/         # Configuration, backup, log forwarding
├── systemd/
│   ├── water-controller.service
│   ├── water-controller-api.service
│   ├── water-controller-ui.service
│   └── water-controller-modbus.service
├── scripts/
│   └── install.sh                # Installation script
├── docs/
│   └── DEPLOYMENT.md             # Deployment guide
├── docker/
│   ├── docker-compose.yml
│   ├── Dockerfile.controller
│   └── Dockerfile.web
└── tests/
    └── *.c                       # Unit tests
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
