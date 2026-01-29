# Water-Controller Documentation

Documentation for the Water Treatment Controller SCADA system.

## Quick Links

| I want to... | Go to... |
|--------------|----------|
| Install the system | [guides/INSTALL.md](guides/INSTALL.md) |
| Deploy to production | [guides/DEPLOYMENT.md](guides/DEPLOYMENT.md) |
| Upgrade an existing installation | [guides/UPGRADE.md](guides/UPGRADE.md) |
| Operate the system | [guides/OPERATOR.md](guides/OPERATOR.md) |
| Troubleshoot issues | [guides/TROUBLESHOOTING_GUIDE.md](guides/TROUBLESHOOTING_GUIDE.md) |
| Understand configuration options | [generated/CONFIGURATION.md](generated/CONFIGURATION.md) |

---

## Documentation Structure

```
docs/
├── generated/      # AUTO-GENERATED - Do not edit manually
├── guides/         # Operational guides (how-to)
├── architecture/   # Design philosophy (rarely changes)
├── development/    # Developer reference
└── templates/      # Fill-in forms
```

---

## Guides (Operational How-To)

| Document | Description |
|----------|-------------|
| [INSTALL.md](guides/INSTALL.md) | Quick installation guide |
| [DEPLOYMENT.md](guides/DEPLOYMENT.md) | Production deployment |
| [UPGRADE.md](guides/UPGRADE.md) | Version upgrades with rollback |
| [OPERATOR.md](guides/OPERATOR.md) | Daily operations reference |
| [ALARM_RESPONSE_PROCEDURES.md](guides/ALARM_RESPONSE_PROCEDURES.md) | ISA-18.2 alarm handling |
| [TROUBLESHOOTING_GUIDE.md](guides/TROUBLESHOOTING_GUIDE.md) | Diagnostics and fixes |
| [PERFORMANCE_TUNING_GUIDE.md](guides/PERFORMANCE_TUNING_GUIDE.md) | Optimization |
| [COMMISSIONING_PROCEDURE.md](guides/COMMISSIONING_PROCEDURE.md) | New system startup |
| [MODBUS_GATEWAY_GUIDE.md](guides/MODBUS_GATEWAY_GUIDE.md) | Modbus integration |

---

## Generated (Auto-Generated from Schemas)

**Do not edit these files manually.** They are regenerated from `schemas/` on each build.

| Document | Source | Regenerate With |
|----------|--------|-----------------|
| [CONFIGURATION.md](generated/CONFIGURATION.md) | `schemas/config/*.yaml` | `make generate-docs` |

To modify generated docs, edit the source schemas and run the generator.

---

## Architecture (Design Philosophy)

Stable documentation that rarely changes. Defines system principles and contracts.

| Document | Description |
|----------|-------------|
| [SYSTEM_DESIGN.md](architecture/SYSTEM_DESIGN.md) | Full system architecture and philosophy |
| [ALARM_PHILOSOPHY.md](architecture/ALARM_PHILOSOPHY.md) | ISA-18.2 alarm system design |
| [PROFINET_SPEC.md](architecture/PROFINET_SPEC.md) | PROFINET wire protocol (5-byte format) |
| [CROSS_SYSTEM.md](architecture/CROSS_SYSTEM.md) | RTU integration contracts |

---

## Development (Developer Reference)

| Document | Description |
|----------|-------------|
| [GUIDELINES.md](development/GUIDELINES.md) | Code standards and quality gates |
| [INTERNALS.md](development/INTERNALS.md) | Build system internals |
| [OPENAPI_SPECIFICATION.md](development/OPENAPI_SPECIFICATION.md) | REST API reference |
| [HMI-ANALYSIS.md](development/HMI-ANALYSIS.md) | HMI component design |

---

## Templates (Fill-in Forms)

| Template | Purpose |
|----------|---------|
| [commissioning-checklist.md](templates/commissioning-checklist.md) | Pre-startup validation |
| [safety-interlocks-template.md](templates/safety-interlocks-template.md) | Safety logic documentation |
| [calibration-record.md](templates/calibration-record.md) | Sensor calibration records |

---

## Network Ports

| Port | Service | Description |
|------|---------|-------------|
| 8000 | API | FastAPI backend REST/WebSocket |
| 8080 | HMI | Web frontend application |
| 502 | Modbus | Modbus TCP gateway |
| 34962-34964 | PROFINET | PROFINET RT communication |

---

## Related Resources

- [Main README](../README.md) - Project overview
- [CHANGELOG](../CHANGELOG.md) - Version history
- [Scripts README](../scripts/README.md) - Installation scripts
- [Schemas](../schemas/) - Configuration schema definitions
