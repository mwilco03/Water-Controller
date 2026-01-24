# Water-Controller Documentation

## Quick Links

| I need to... | Go to |
|--------------|-------|
| **Install** | [INSTALL.md](guides/INSTALL.md) |
| **Deploy to production** | [DEPLOYMENT.md](guides/DEPLOYMENT.md) |
| **Operate the system** | [OPERATOR.md](guides/OPERATOR.md) |
| **Troubleshoot** | [TROUBLESHOOTING_GUIDE.md](guides/TROUBLESHOOTING_GUIDE.md) |
| **Understand the architecture** | [SYSTEM_DESIGN.md](architecture/SYSTEM_DESIGN.md) |
| **Write code** | [GUIDELINES.md](development/GUIDELINES.md) |

---

## Documentation Map

```
docs/
├── guides/           # HOW-TO: Installation, operations, troubleshooting
├── architecture/     # WHY: Design decisions, system philosophy
├── development/      # STANDARDS: Code quality, testing, API specs
├── templates/        # FORMS: Commissioning, calibration records
├── generated/        # AUTO: Schema-generated config docs
└── audits/           # REPORTS: Code quality audits
```

---

## By Role

### Operators
- [Operator Guide](guides/OPERATOR.md) — Daily operations
- [Alarm Response](guides/ALARM_RESPONSE_PROCEDURES.md) — ISA-18.2 procedures
- [Troubleshooting](guides/TROUBLESHOOTING_GUIDE.md) — Diagnostics

### Administrators
- [Installation](guides/INSTALL.md) — Quick setup
- [Docker Deployment](guides/DOCKER_DEPLOYMENT.md) — Container deployment
- [Upgrade Guide](guides/UPGRADE.md) — Version upgrades
- [Configuration](generated/CONFIGURATION.md) — All settings

### Developers
- [Development Guidelines](development/GUIDELINES.md) — Code standards
- [API Specification](development/OPENAPI_SPECIFICATION.md) — REST API
- [System Design](architecture/SYSTEM_DESIGN.md) — Architecture
- [HMI Analysis](development/HMI-ANALYSIS.md) — UI components

### Integrators
- [PROFINET Spec](architecture/PROFINET_SPEC.md) — Wire protocol
- [Modbus Gateway](guides/MODBUS_GATEWAY_GUIDE.md) — Protocol bridge
- [Cross-System](architecture/CROSS_SYSTEM.md) — RTU integration

---

## Guides (How-To)

| Guide | Purpose |
|-------|---------|
| [INSTALL.md](guides/INSTALL.md) | Quick installation |
| [DEPLOYMENT.md](guides/DEPLOYMENT.md) | Production deployment |
| [DOCKER_DEPLOYMENT.md](guides/DOCKER_DEPLOYMENT.md) | Container deployment |
| [UPGRADE.md](guides/UPGRADE.md) | Version upgrades |
| [OPERATOR.md](guides/OPERATOR.md) | Daily operations |
| [ALARM_RESPONSE_PROCEDURES.md](guides/ALARM_RESPONSE_PROCEDURES.md) | Alarm handling |
| [TROUBLESHOOTING_GUIDE.md](guides/TROUBLESHOOTING_GUIDE.md) | Diagnostics |
| [COMMISSIONING_PROCEDURE.md](guides/COMMISSIONING_PROCEDURE.md) | New system startup |
| [MODBUS_GATEWAY_GUIDE.md](guides/MODBUS_GATEWAY_GUIDE.md) | Modbus integration |
| [PERFORMANCE_TUNING_GUIDE.md](guides/PERFORMANCE_TUNING_GUIDE.md) | Optimization |

---

## Architecture (Design Philosophy)

| Document | Purpose |
|----------|---------|
| [SYSTEM_DESIGN.md](architecture/SYSTEM_DESIGN.md) | Core philosophy, failure design |
| [ALARM_PHILOSOPHY.md](architecture/ALARM_PHILOSOPHY.md) | ISA-18.2 alarm system |
| [PROFINET_SPEC.md](architecture/PROFINET_SPEC.md) | Wire protocol (5-byte format) |
| [CROSS_SYSTEM.md](architecture/CROSS_SYSTEM.md) | Controller↔RTU contracts |
| [DESIGN_DECISIONS.md](architecture/DESIGN_DECISIONS.md) | ADRs |

---

## Development (Standards)

| Document | Purpose |
|----------|---------|
| [GUIDELINES.md](development/GUIDELINES.md) | Code standards, quality gates |
| [OPENAPI_SPECIFICATION.md](development/OPENAPI_SPECIFICATION.md) | REST API reference |
| [INTERNALS.md](development/INTERNALS.md) | Build system, bootstrap.sh |
| [HMI-ANALYSIS.md](development/HMI-ANALYSIS.md) | UI component design |

---

## Templates

| Template | Purpose |
|----------|---------|
| [commissioning-checklist.md](templates/commissioning-checklist.md) | Startup validation |
| [safety-interlocks-template.md](templates/safety-interlocks-template.md) | Interlock documentation |
| [calibration-record.md](templates/calibration-record.md) | Sensor calibration |

---

## Network Ports

| Port | Service |
|------|---------|
| 8000 | API (REST/WebSocket) |
| 8080 | HMI (Web UI) |
| 1502 | Modbus TCP |
| 3000 | Grafana |
| 34962-34964 | PROFINET RT |

---

## Related

- [Main README](../README.md)
- [CHANGELOG](../CHANGELOG.md)
- [CONTRIBUTING](../CONTRIBUTING.md)
- [CLAUDE.md](../CLAUDE.md) — AI assistant context
