# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1] - 2024-12-19

### Added

- **PROFINET IO Controller**: Real-time communication with RTU devices using PROFINET RT Class 1
  - DCP discovery for automatic device detection
  - Application Relationship (AR) management
  - Cyclic I/O data exchange
  - Frame building and parsing utilities

- **RTU Registry**: Device discovery, configuration, and state management
  - Dynamic slot configuration (RTU dictates layout)
  - Health monitoring and connection state tracking
  - Topology persistence

- **Control Engine**: Process control functionality
  - PID loops with anti-windup and derivative filtering
  - Sequence engine for automated procedures
  - Interlock monitoring (safety logic on RTU, notifications on controller)
  - Output forcing for maintenance

- **Alarm Management**: ISA-18.2 compliant alarm system
  - Multiple alarm types: HIGH, LOW, HIGH_HIGH, LOW_LOW, ROC, DEVIATION
  - Alarm states: ACTIVE_UNACK, ACTIVE_ACK, CLEARED_UNACK, CLEARED
  - Acknowledgment, suppression, and shelving
  - Alarm flood detection

- **Data Historian**: Time-series data storage
  - Deadband and swinging-door compression algorithms
  - Tag management with configurable sample rates
  - Query support with aggregation

- **Coordination Engine**: Multi-RTU orchestration
  - Failover management with health monitoring
  - Cascade control for interconnected loops
  - Load balancing across RTU groups

- **Modbus Gateway**: Protocol bridging
  - PROFINET-to-Modbus TCP translation
  - PROFINET-to-Modbus RTU (serial) translation
  - Configurable register mapping
  - Downstream device polling

- **IPC Server**: Shared memory interface for Python API integration

- **Web Backend** (FastAPI):
  - REST API for all controller functions
  - WebSocket real-time data streaming
  - Session-based authentication
  - Active Directory integration support

- **Web Frontend** (Next.js/React):
  - Dashboard with system overview
  - RTU management and discovery
  - Alarm monitoring and acknowledgment
  - PID loop tuning interface
  - Historical trend visualization
  - Modbus gateway configuration
  - Settings and backup/restore

- **Infrastructure**:
  - CMake build system with cross-compilation support (ARM32, ARM64, x86_64)
  - Docker deployment with docker-compose
  - systemd service files
  - GitHub Actions CI/CD workflows
  - Installation script

### Fixed

- Build errors in test files (API signature mismatches)
- Missing `cyclic_exchange.h` header file
- Thread safety in API shared resources

### Security

- Removed vulnerable npm package dependency

### Notes

This is the initial release. The system implements a two-plane architecture:
- **RTU Plane**: Physical sensors/actuators with local safety interlocks
- **Controller Plane**: Supervisory functions, HMI, data collection, alarm management

Safety-critical interlocks execute on the RTU, not the controller, ensuring continued protection during communication loss.
