# Water Treatment Controller

A PROFINET IO Controller for Water Treatment RTU Networks, implementing industrial-grade process control, alarm management, and data historian functionality.

## Quick Start

```bash
# Fresh install (wipe + install from scratch)
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | sudo bash -s -- fresh

# Uninstall (complete removal)
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | sudo bash -s -- wipe

# Reinstall/Upgrade (wipe + install, preserve configs)
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | sudo bash -s -- reinstall
```

## Overview

This project implements a complete SCADA/DCS system for water treatment facilities, featuring:

- **PROFINET IO Controller**: Real-time communication with RTU devices using PROFINET RT Class 1
- **RTU Registry**: Device discovery, configuration, and state management
- **Control Engine**: PID loops, interlocks, and sequence control for automated process operation
- **Alarm Management**: ISA-18.2 compliant alarm system with acknowledgment, suppression, and shelving
- **Data Historian**: Time-series data storage with deadband and swinging-door compression
- **Modbus Gateway**: Protocol bridge for PROFINET-to-Modbus TCP/RTU translation
- **OpenPLC Integration**: Import and execute ladder logic with Modbus ↔ PROFINET translation
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

## OpenPLC Integration (Modbus ↔ PROFINET Translation)

This system supports **OpenPLC** as an optional ladder logic runtime with a clear architectural boundary:

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SYSTEM                                  │
│              (Ladder logic developed on engineering workstation)         │
│                                    │                                     │
│                            .st / .ld files                               │
│                                    ▼                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                          WATER-CONTROLLER                                │
│                                                                          │
│  ┌──────────────────┐       ┌─────────────────┐       ┌───────────────┐ │
│  │    OpenPLC       │  R/W  │     Modbus      │       │   PROFINET    │ │
│  │    Container     │◄─────►│   (TCP:1502)    │◄─────►│  Controller   │ │
│  │                  │       │                 │       │               │ │
│  │  • Import .st    │       │  Translation    │       │ • Device I/O  │ │
│  │  • Execute logic │       │     Layer       │       │ • RTU Comm    │ │
│  │  • Display state │       │                 │       │ • Cyclic Data │ │
│  └──────────────────┘       └─────────────────┘       └───────────────┘ │
│                                                               │          │
└───────────────────────────────────────────────────────────────┼──────────┘
                                                                │
                                                                ▼
                                                    ┌───────────────────┐
                                                    │   RTUs / PLCs     │
                                                    │   (Field Layer)   │
                                                    └───────────────────┘
```

### Key Design Principles

| Principle | Description |
|-----------|-------------|
| **Import Only** | Ladder logic (.st/.ld files) is developed on external engineering workstations, NOT on the controller |
| **No On-Controller Development** | The controller is a runtime environment, not a development environment |
| **Modbus as Bridge** | OpenPLC communicates via Modbus TCP; the controller translates to/from PROFINET |
| **Bidirectional Data** | Modbus R/W operations flow through the translation layer to PROFINET I/O |
| **Display & Translate** | Controller displays ladder state and translates protocol; logic executes in OpenPLC |

### Data Flow

```
1. Engineer develops ladder logic on external workstation
2. Ladder file (.st/.ld) exported and imported into OpenPLC container
3. OpenPLC executes logic, reads/writes Modbus registers
4. Controller translates Modbus ↔ PROFINET cyclic I/O
5. PROFINET communicates with field RTUs
6. Web HMI displays real-time state from both layers
```

### Enabling OpenPLC

```bash
# Start with OpenPLC profile
docker compose --profile openplc up -d

# Access OpenPLC web interface
open http://localhost:8081
```

### Modbus Register Mapping

The Modbus gateway exposes PROFINET I/O as Modbus registers:

| Register Range | Type | Mapping |
|----------------|------|---------|
| 0-999 | Holding | RTU sensor values (read) |
| 1000-1999 | Holding | RTU actuator commands (write) |
| 2000-2999 | Input | RTU status registers |
| 3000-3999 | Coils | Discrete I/O points |

See [Modbus Gateway Guide](docs/guides/MODBUS_GATEWAY_GUIDE.md) for complete mapping.

## Dynamic Slot Configuration

**The RTU dictates slot configuration; the controller adapts dynamically.**

There is **no fixed limit** on the number of slots. Each RTU reports its own configuration at connection time, including:

- Number of sensors and actuators
- Slot assignments (any slot can be sensor or actuator)
- Measurement types, units, and ranges
- Actuator types (relay, PWM, valve, pump)

The controller dynamically:
- Creates UI elements for reported slots
- Configures historian tags based on RTU metadata
- Sets up alarm rules using RTU-provided ranges
- Adapts to multiple RTUs with different configurations

### Example RTU Configuration

An RTU might report any slot layout, such as:

| Slot | Type | Function |
|------|------|----------|
| 0 | Sensor | pH (0-14) |
| 1 | Sensor | Temperature (0-100 C) |
| 2 | Actuator | Main Pump (On/Off) |
| 3 | Sensor | Flow Rate (0-500 L/min) |
| 4 | Actuator | Dosing Pump (PWM) |
| ... | ... | ... |

Slots are 0-indexed and can be assigned in any order. The controller does not assume any fixed layout.

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
open http://localhost:8080
```

For detailed deployment instructions, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

For a complete documentation index, see [docs/README.md](docs/README.md).

## Building

### Prerequisites

- CMake 3.16+
- GCC or Clang with C11 support
- libpq (PostgreSQL client library)
- libjson-c
- Python 3.9+ (for web backend)
- Node.js 18+ (for web UI)

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
# Install using bootstrap script
./bootstrap.sh install --mode docker

# Or manually with docker compose
cd docker
docker compose up -d

# Start with PROFINET controller (requires host network)
docker compose --profile profinet up -d

# Start with OpenPLC ladder logic runtime
docker compose --profile openplc up -d

# Start with both profiles
docker compose --profile profinet --profile openplc up -d
```

#### Startup Modes

The API service supports different startup validation modes:

| Mode | Description | Default |
|------|-------------|---------|
| `development` | Lenient validation - downgrades path/UI failures to warnings | docker-compose.yml |
| `production` | Strict validation - fails on critical issues | docker-compose.prod.yml |
| `simulation` | Skips hardware/IPC checks for testing | Set explicitly |

```bash
# Override startup mode via environment variable
WTC_STARTUP_MODE=production docker compose up -d

# For development without the C controller or UI assets
WTC_STARTUP_MODE=development WTC_SIMULATION_MODE=true docker compose up -d
```

For detailed Docker instructions, see [Docker Deployment Guide](docs/guides/DOCKER_DEPLOYMENT.md).

## Database Credentials

**IMPORTANT**: This system uses hardcoded database credentials for maximum deployment simplicity and consistency.

### PostgreSQL Credentials (Publicly Documented)

```
Database: water_treatment
Username: wtc
Password: wtc_password
```

These credentials are **hardcoded** in:
- `docker/docker-compose.yml`
- `docker/docker-compose.prod.yml`
- `docker/grafana/provisioning/datasources/datasources.yml`

### Security Model

This configuration is **intentionally designed** for industrial control systems that operate on:

1. **Isolated Networks**: Air-gapped or firewalled industrial networks with no internet access
2. **Physical Security**: Facilities with restricted physical access and security controls
3. **Network Segmentation**: Database runs on internal Docker network (`wtc-internal`) with no external exposure

The PostgreSQL database container:
- **NOT exposed** to external networks (internal Docker network only)
- **NOT accessible** from outside the Docker network
- Accessible only to other containers within the `wtc-internal` network
- Runs on port 5432 internally (not mapped to host)

### Deployment Benefits

- ✅ **Zero configuration** - works out of the box
- ✅ **Consistent passwords** - no environment variable mismatches
- ✅ **Simple backups** - predictable credentials for restore operations
- ✅ **Easy troubleshooting** - no "forgot password" scenarios
- ✅ **Documented publicly** - clear expectations, no hidden secrets

### When to Use Different Credentials

If you need different credentials (e.g., compliance requirements, defense-in-depth):

1. Edit the three files listed above and change `wtc_password` to your password
2. Remove existing database volume: `docker volume rm wtc-db-data`
3. Restart: `docker compose up -d`

For most water treatment facilities, the default hardcoded password is appropriate given the network isolation and physical security controls already in place.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WT_INTERFACE` | Network interface for PROFINET | `eth0` |
| `WT_CYCLE_TIME` | Cycle time in milliseconds | `1000` |
| `WT_LOG_LEVEL` | Logging level (DEBUG, INFO, WARN, ERROR) | `INFO` |
| `DATABASE_URL` | PostgreSQL connection string | SQLite default |
| `API_PORT` | API server port | `8000` |
| `UI_PORT` | Web UI server port | `8080` |

### Network Ports

| Port | Service | Description |
|------|---------|-------------|
| 8000 | API | FastAPI backend REST/WebSocket |
| 8080 | Web UI | Next.js frontend application |
| 8081 | OpenPLC | OpenPLC web interface (optional) |
| 1502 | Modbus | Modbus TCP gateway (non-root) |
| 3000 | Grafana | Visualization dashboards |
| 34962-34964 | PROFINET | PROFINET RT communication |

All ports are configurable via `config/ports.env`. See [Configuration Guide](docs/guides/DEPLOYMENT.md) for details.

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

### RTU Inventory

- `GET /api/v1/rtus/{station_name}/inventory` - Get complete sensor/control inventory
- `POST /api/v1/rtus/{station_name}/inventory/refresh` - Query RTU and refresh inventory
- `POST /api/v1/rtus/{station_name}/control/{control_id}` - Send command to control

### Network Discovery (DCP)

- `POST /api/v1/discover/rtu` - Trigger PROFINET network scan
- `GET /api/v1/discover/cached` - Get cached discovery results
- `DELETE /api/v1/discover/cache` - Clear discovery cache

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
- `GET /api/v1/auth/sessions` - List active sessions (admin)
- `DELETE /api/v1/auth/sessions/{token}` - Terminate session (admin)

### User Management

- `GET /api/v1/users` - List all users
- `POST /api/v1/users` - Create new user
- `GET /api/v1/users/{id}` - Get user details
- `PUT /api/v1/users/{id}` - Update user
- `DELETE /api/v1/users/{id}` - Delete user
- `POST /api/v1/users/sync` - Sync users to RTUs

### System Health

- `GET /api/v1/system/health` - Get system health metrics
- `GET /api/v1/system/logs` - Get system log entries
- `DELETE /api/v1/system/logs` - Clear system logs (admin)
- `GET /api/v1/system/audit` - Get audit log entries
- `GET /api/v1/system/network` - Get network configuration
- `PUT /api/v1/system/network` - Update network configuration
- `GET /api/v1/system/interfaces` - List network interfaces

### Network Scanning

- `POST /api/v1/network/scan` - Scan network for devices
- `GET /api/v1/network/scan/last` - Get last scan results
- `GET /api/v1/network/scan/status` - Get scan status
- `GET /api/v1/network/scan/config` - Get scan configuration
- `PUT /api/v1/network/scan/config` - Update scan configuration

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
│           ├── settings/         # Configuration, backup, log forwarding
│           ├── users/            # User management
│           ├── io-tags/          # I/O tag configuration
│           ├── network/          # Network configuration
│           ├── system/           # System status and logs
│           ├── modbus/           # Modbus gateway configuration
│           └── wizard/           # Setup wizard
├── systemd/
│   ├── water-controller.service
│   ├── water-controller-api.service
│   ├── water-controller-ui.service
│   ├── water-controller-modbus.service
│   └── water-controller-hmi.service  # Standalone HMI mode
├── scripts/
│   ├── install.sh                # Full installation script
│   ├── install-hmi.sh            # HMI-only installation
│   └── water-controller          # Service wrapper script
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

Copyright (C) 2024-2025

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

SPDX-License-Identifier: GPL-3.0-or-later

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Quick start:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes following our coding standards
4. Run tests: `make test`
5. Submit a pull request

## Documentation

| Guide | Description |
|-------|-------------|
| [Installation Guide](docs/INSTALL.md) | Quick installation with prerequisites |
| [Deployment Guide](docs/DEPLOYMENT.md) | Full production deployment |
| [Upgrade Guide](docs/UPGRADE.md) | Version upgrades with rollback |
| [Operator Guide](docs/OPERATOR.md) | Operator quick reference |
| [Troubleshooting](docs/TROUBLESHOOTING_GUIDE.md) | Diagnostic commands and fixes |
| [API Specification](docs/OPENAPI_SPECIFICATION.md) | REST API reference |
| [Documentation Index](docs/README.md) | Complete documentation listing |

## Support

For issues and questions, please open a GitHub issue.
