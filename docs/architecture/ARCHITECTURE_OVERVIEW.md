# Architecture Overview

This document provides a high-level overview of the Water Treatment Controller (WTC) system architecture.

## System Overview

The WTC is a SCADA-like system for monitoring and controlling water treatment processes. It consists of three main layers:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           PRESENTATION LAYER                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │   React HMI     │  │    Grafana      │  │   OpenPLC Viewer       │  │
│  │   (Next.js)     │  │   Dashboards    │  │   (Ladder Logic)       │  │
│  └────────┬────────┘  └────────┬────────┘  └───────────┬─────────────┘  │
└───────────┼────────────────────┼───────────────────────┼────────────────┘
            │                    │                       │
            │ HTTP/WebSocket     │ SQL                   │ Modbus TCP
            ▼                    ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           APPLICATION LAYER                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      FastAPI REST/WebSocket                      │   │
│  │         /api/v1/rtus  /api/v1/sensors  /api/v1/alarms           │   │
│  └──────────────────────────────┬──────────────────────────────────┘   │
│                                 │                                       │
│  ┌──────────────────────────────┴──────────────────────────────────┐   │
│  │                    Shared Memory (IPC)                           │   │
│  │              POSIX-IPC / mmap for real-time data                 │   │
│  └──────────────────────────────┬──────────────────────────────────┘   │
└─────────────────────────────────┼───────────────────────────────────────┘
                                  │
┌─────────────────────────────────┼───────────────────────────────────────┐
│                           CONTROL LAYER                                 │
│  ┌──────────────────────────────┴──────────────────────────────────┐   │
│  │                    C Controller Core                             │   │
│  │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │   │
│  │   │   PID    │  │ Interlock│  │  Alarm   │  │  Historian   │    │   │
│  │   │  Loops   │  │  Logic   │  │  Engine  │  │   Buffer     │    │   │
│  │   └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘    │   │
│  └────────┼─────────────┼─────────────┼───────────────┼────────────┘   │
│           │             │             │               │                 │
│  ┌────────┴─────────────┴─────────────┴───────────────┴────────────┐   │
│  │                    PROFINET Controller                           │   │
│  │              (Real-time industrial protocol)                     │   │
│  └──────────────────────────────┬──────────────────────────────────┘   │
└─────────────────────────────────┼───────────────────────────────────────┘
                                  │ PROFINET
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           FIELD LAYER                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   RTU #1    │  │   RTU #2    │  │   RTU #3    │  │   RTU #N    │    │
│  │ Tank Level  │  │ Pump Station│  │ Filter Unit │  │   ...       │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### Presentation Layer

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| React HMI | Next.js 14 | Real-time process visualization, operator interface |
| Grafana | Grafana OSS | Historical trends, analytics dashboards |
| OpenPLC Viewer | OpenPLC v3 | Ladder logic visualization (import-only) |

### Application Layer

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| REST API | FastAPI | CRUD operations, configuration management |
| WebSocket | FastAPI | Real-time data streaming |
| Shared Memory | POSIX-IPC | High-performance IPC with controller |

### Control Layer

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| C Controller | C17 + p-net | Real-time control, deterministic timing |
| PID Loops | Custom C | Closed-loop process control |
| Interlocks | Custom C | Safety logic, equipment protection |
| Alarm Engine | Custom C | Alarm detection and management |
| Historian | Custom C | Time-series data collection |

### Field Layer

| Component | Protocol | Description |
|-----------|----------|-------------|
| RTUs | PROFINET | Remote Terminal Units with I/O |
| Sensors | 4-20mA/PROFINET | pH, temperature, flow, level, etc. |
| Actuators | PROFINET | Pumps, valves, motors |

## Data Flow

### Real-Time Path (< 1 second latency)

```
RTU → PROFINET → C Controller → Shared Memory → FastAPI WebSocket → React HMI
```

### Configuration Path

```
React HMI → REST API → Database → C Controller (on reload)
```

### Historical Path

```
C Controller → Historian Buffer → Shared Memory → FastAPI → TimescaleDB → Grafana
```

## Protocol Translation Layer

The system translates between industrial protocols:

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│    OpenPLC       │     │  Modbus Server   │     │   C Controller   │
│  (Import Only)   │────▶│  (Translation)   │────▶│   (PROFINET)     │
│                  │     │                  │     │                  │
│  Ladder Logic    │ R/W │  Registers ↔     │     │  RTU Control     │
│  Visualization   │────▶│  PROFINET Data   │────▶│  & Monitoring    │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

- **OpenPLC**: Import-only ladder logic viewer (no development on controller)
- **Modbus**: Bridge protocol for ladder logic integration
- **PROFINET**: Native industrial protocol for RTU communication

## Deployment Architecture

### Docker Deployment

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Host                               │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │   UI    │ │   API   │ │   DB    │ │ Grafana │ │ OpenPLC │   │
│  │ :8080   │ │ :8000   │ │ :5432   │ │ :3000   │ │ :8081   │   │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │
│       └──────────┬┴──────────┬┴──────────┬┴──────────┬┘        │
│                  │     wtc-network       │                      │
│  ┌───────────────┴───────────────────────┴──────────────────┐  │
│  │              Controller (host network)                    │  │
│  │                    PROFINET → RTUs                        │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Bare Metal Deployment

```
┌─────────────────────────────────────────────────────────────────┐
│                     Industrial PC / Edge Device                  │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ water_controller │  │   web_api        │                     │
│  │   (systemd)      │  │   (systemd)      │                     │
│  └────────┬─────────┘  └────────┬─────────┘                     │
│           │                     │                                │
│           └──────────┬──────────┘                                │
│                      │                                           │
│              Shared Memory (/dev/shm)                            │
│                                                                  │
│  PROFINET Interface (eth0) ────────────────▶ Industrial Network  │
└─────────────────────────────────────────────────────────────────┘
```

## Technology Stack

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| Frontend | Next.js | 14.x | React framework with SSR |
| Frontend | TypeScript | 5.x | Type-safe JavaScript |
| Frontend | Tailwind CSS | 3.x | Utility-first CSS |
| API | FastAPI | 0.100+ | Async Python web framework |
| API | Python | 3.11+ | API runtime |
| API | SQLAlchemy | 2.x | ORM and database toolkit |
| Controller | C17 | GCC 12+ | Control logic |
| Controller | p-net | 0.5+ | PROFINET stack |
| Database | PostgreSQL | 15 | Relational database |
| Database | TimescaleDB | 2.x | Time-series extension |
| Container | Docker | 24+ | Containerization |
| Container | Docker Compose | 2.x | Multi-container orchestration |

## Security Architecture

### Network Segmentation

```
┌─────────────────────┐     ┌─────────────────────┐
│   Corporate LAN     │     │   Industrial LAN    │
│   (IT Network)      │     │   (OT Network)      │
│                     │     │                     │
│   - React HMI       │     │   - PROFINET        │
│   - REST API        │◄───▶│   - RTUs            │
│   - Grafana         │     │   - Sensors         │
│                     │     │   - Actuators       │
└─────────────────────┘     └─────────────────────┘
                    │
                    ▼
           ┌───────────────┐
           │   Firewall    │
           │   (DMZ)       │
           └───────────────┘
```

### Authentication & Authorization

- JWT-based authentication for API
- Role-based access control (RBAC)
- API key authentication (optional)
- Network-level access control for PROFINET

### Data Protection

- TLS for all HTTP/WebSocket traffic
- Database encryption at rest (PostgreSQL)
- Secure secret management via environment variables

## Scalability Considerations

### Horizontal Scaling

- API layer can scale horizontally behind load balancer
- Database supports read replicas
- UI is stateless and CDN-compatible

### Vertical Scaling

- Controller requires dedicated hardware for real-time performance
- TimescaleDB optimized for time-series write performance

### Limits

| Resource | Limit | Notes |
|----------|-------|-------|
| RTUs | 64 | Per controller instance |
| Sensors | 1024 | Across all RTUs |
| Tags | 500 | Historian capacity |
| API Requests | 1000/s | Per instance |
| WebSocket Connections | 1000 | Per instance |

## Related Documents

- [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) - Detailed system design
- [CONFIGURATION.md](../guides/CONFIGURATION.md) - Configuration reference
- [ERROR_HANDLING.md](../guides/ERROR_HANDLING.md) - Error handling patterns
- [DOCKER_DEPLOYMENT.md](../guides/DOCKER_DEPLOYMENT.md) - Docker deployment guide
