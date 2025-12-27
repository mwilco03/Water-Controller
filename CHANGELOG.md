# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2025-12-27

### Added

- **ISA-101 Compliant HMI Components**:
  - `AlarmBanner.tsx` - Real-time alarm notification banner
  - `AuthenticationModal.tsx` - Login/session management modal
  - `ConnectionStatusIndicator.tsx` - Network connection status display
  - `ControlGuard.tsx` - Permission-based control protection
  - `DataQualityIndicator.tsx` - OPC UA quality code visualization
  - `RTUStatusCard.tsx` - RTU health and status cards
  - `SessionIndicator.tsx` - Active session display
  - `SystemStatusBar.tsx` - System-wide status bar

- **Authentication System**:
  - JWT token-based authentication (`web/api/app/core/auth.py`)
  - Auth API endpoints (`web/api/app/api/v1/auth.py`)
  - Token integration with React frontend

- **Alarm Manager ISA-18.2 Compliance**:
  - Alarm flood detection with rate limiting
  - Alarm shelving with time-based expiration
  - Suppression state management
  - First-out alarm tracking for sequences

- **Data Historian Improvements**:
  - Persistence layer with query safety
  - Parameterized queries to prevent SQL injection
  - Proper data flushing and retention

- **Modbus Gateway Enhancements**:
  - JSON loading for register maps
  - Downstream device polling loop with cache
  - Consecutive error tracking with auto-disconnect

- **Installation System**:
  - Upgrade modes (`--upgrade` flag)
  - Rollback support with automatic backup points
  - Uninstall with data preservation option (`--keep-data`)
  - Comprehensive test suite for installation scenarios

- **Docker Security Hardening**:
  - Resource limits (CPU and memory) for all containers
  - Non-root user execution for api, ui, and grafana
  - Health checks for controller, ui, and grafana containers

- **SystemD Security Hardening**:
  - `MemoryMax` and `MemoryHigh` limits
  - `CPUQuota` limits
  - `TasksMax` limits
  - `LimitNOFILE` and `LimitCORE` settings

### Changed

- **Web UI Dashboard**: Refactored with glassmorphism design and animated components
- **RTU Status Page**: Implemented ISA-101 compliant read-first access model
- **Alarms Page**: Added error state display with retry button and virtualized history
- **API Response Handling**: Improved error handling across all endpoints

### Fixed

- **Modbus TCP Connection**: Non-blocking connect with configurable timeout using `select()`
- **Modbus Gateway Race Conditions**: Hold lock during client iteration
- **PROFINET Acyclic Operations**: Full RPC-based read/write implementation
- **Database User Operations**: Complete PostgreSQL persistence (save, load, delete, list)
- **WebSocket Notifications**: Added notification queue for failover events
- **PID Loop Persistence**: Full database save/load with all tuning parameters
- **Interlock Persistence**: Database operations for interlock rules
- **React Hook Dependencies**: Fixed `useWebSocket` and `useCommandMode` hooks
- **Service Unit Generation**: Fixed duplicate generation causing file corruption
- **Installation Permissions**: Added missing sudo to privileged commands
- **Uninstall Script**: Added sudo to privileged removal commands

### Security

- Removed exposed ports for internal-only services (database, Redis) in Docker
- Added parameterized queries throughout to prevent SQL injection
- Proper session token validation and expiration

### Documentation

- Added comprehensive deployment guide with cross-compilation instructions
- Added board-specific installation guides (Raspberry Pi, BeagleBone, Luckfox)
- Added integration audit report with full wiring verification
- Added code completeness audit with all issues resolved
- Updated scripts README with modular installation reference

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
