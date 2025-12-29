# Water-Controller Documentation

This directory contains comprehensive documentation for the Water Treatment Controller SCADA system.

## Quick Links

| I want to... | Go to... |
|--------------|----------|
| Install the system | [INSTALL.md](INSTALL.md) |
| Deploy to production | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Upgrade an existing installation | [UPGRADE.md](UPGRADE.md) |
| Operate the system | [OPERATOR.md](OPERATOR.md) |
| Troubleshoot issues | [TROUBLESHOOTING_GUIDE.md](TROUBLESHOOTING_GUIDE.md) |
| Understand the API | [OPENAPI_SPECIFICATION.md](OPENAPI_SPECIFICATION.md) |
| Configure Modbus gateway | [MODBUS_GATEWAY_GUIDE.md](MODBUS_GATEWAY_GUIDE.md) |

---

## Documentation by Role

### For Operators

- [OPERATOR.md](OPERATOR.md) - Quick reference guide for daily operations
- [ALARM_RESPONSE_PROCEDURES.md](ALARM_RESPONSE_PROCEDURES.md) - ISA-18.2 compliant alarm handling
- [templates/commissioning-checklist.md](templates/commissioning-checklist.md) - System startup checklist

### For System Administrators

- [INSTALL.md](INSTALL.md) - Installation guide with prerequisites
- [DEPLOYMENT.md](DEPLOYMENT.md) - Comprehensive production deployment
- [UPGRADE.md](UPGRADE.md) - Version upgrade procedures with rollback
- [FIELD_UPGRADE_GUIDE.md](FIELD_UPGRADE_GUIDE.md) - In-field deployment updates
- [TROUBLESHOOTING_GUIDE.md](TROUBLESHOOTING_GUIDE.md) - Diagnostic commands and solutions
- [PERFORMANCE_TUNING_GUIDE.md](PERFORMANCE_TUNING_GUIDE.md) - System optimization

### For Developers

- [DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md) - Code standards and quality gates
- [INTERNALS.md](INTERNALS.md) - Internal architecture details
- [HARMONIOUS_SYSTEM_DESIGN.md](HARMONIOUS_SYSTEM_DESIGN.md) - Full system architecture
- [OPENAPI_SPECIFICATION.md](OPENAPI_SPECIFICATION.md) - REST API reference
- [ALARM_ARCHITECTURE.md](ALARM_ARCHITECTURE.md) - ISA-18.2 alarm system design

### For Integrators

- [MODBUS_GATEWAY_GUIDE.md](MODBUS_GATEWAY_GUIDE.md) - Modbus TCP/RTU integration
- [PROFINET_DATA_FORMAT_SPECIFICATION.md](PROFINET_DATA_FORMAT_SPECIFICATION.md) - PROFINET protocol details
- [CROSS_SYSTEM_GUIDELINES_ADDENDUM.md](CROSS_SYSTEM_GUIDELINES_ADDENDUM.md) - External system integration

---

## Documentation Categories

### Installation & Deployment

| Document | Description |
|----------|-------------|
| [INSTALL.md](INSTALL.md) | Quick installation guide with prerequisites |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Full production deployment (31KB comprehensive) |
| [UPGRADE.md](UPGRADE.md) | Version upgrades with zero-disk-write optimization |
| [FIELD_UPGRADE_GUIDE.md](FIELD_UPGRADE_GUIDE.md) | Live system upgrade procedures |
| [COMMISSIONING_PROCEDURE.md](COMMISSIONING_PROCEDURE.md) | New system commissioning steps |

### Operations & Procedures

| Document | Description |
|----------|-------------|
| [OPERATOR.md](OPERATOR.md) | Operator quick reference guide |
| [ALARM_RESPONSE_PROCEDURES.md](ALARM_RESPONSE_PROCEDURES.md) | Alarm handling workflows |
| [TROUBLESHOOTING_GUIDE.md](TROUBLESHOOTING_GUIDE.md) | Diagnostic commands and fixes |
| [PERFORMANCE_TUNING_GUIDE.md](PERFORMANCE_TUNING_GUIDE.md) | Optimization strategies |

### Technical Specifications

| Document | Description |
|----------|-------------|
| [OPENAPI_SPECIFICATION.md](OPENAPI_SPECIFICATION.md) | Complete REST API documentation |
| [PROFINET_DATA_FORMAT_SPECIFICATION.md](PROFINET_DATA_FORMAT_SPECIFICATION.md) | PROFINET frame structure |
| [MODBUS_GATEWAY_GUIDE.md](MODBUS_GATEWAY_GUIDE.md) | Modbus TCP/RTU configuration |
| [ALARM_ARCHITECTURE.md](ALARM_ARCHITECTURE.md) | ISA-18.2 alarm system design |

### Architecture & Design

| Document | Description |
|----------|-------------|
| [HARMONIOUS_SYSTEM_DESIGN.md](HARMONIOUS_SYSTEM_DESIGN.md) | Full system architecture (65KB) |
| [DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md) | Code standards and practices (61KB) |
| [INTERNALS.md](INTERNALS.md) | Internal component details |
| [ADR-001-SYSTEM-READINESS-GATES.md](ADR-001-SYSTEM-READINESS-GATES.md) | Architecture decision record |

### Templates

| Template | Purpose |
|----------|---------|
| [templates/commissioning-checklist.md](templates/commissioning-checklist.md) | Pre-startup validation |
| [templates/safety-interlocks-template.md](templates/safety-interlocks-template.md) | Safety logic documentation |
| [templates/calibration-record.md](templates/calibration-record.md) | Sensor calibration records |

---

## Network Ports Reference

| Port | Service | Description |
|------|---------|-------------|
| 3000 | Web UI | Next.js frontend application |
| 8080 | API | FastAPI backend REST/WebSocket |
| 502 | Modbus | Modbus TCP gateway |
| 34962-34964 | PROFINET | PROFINET RT communication |

---

## Related Resources

- [Main README](../README.md) - Project overview and quick start
- [CHANGELOG](../CHANGELOG.md) - Version history and release notes
- [Scripts README](../scripts/README.md) - Installation script documentation
- [GitHub Issues](https://github.com/mwilco03/Water-Controller/issues) - Bug reports and feature requests
