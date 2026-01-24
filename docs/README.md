# Water-Controller Documentation

## Start Here

| Need | Document |
|------|----------|
| **Quick commands & troubleshooting** | [QUICK_REFERENCE.md](QUICK_REFERENCE.md) |
| **Full documentation index** | [INDEX.md](INDEX.md) |

---

## By Task

| I want to... | Go to |
|--------------|-------|
| Install the system | [guides/INSTALL.md](guides/INSTALL.md) |
| Deploy to production | [guides/DEPLOYMENT.md](guides/DEPLOYMENT.md) |
| Operate daily | [guides/OPERATOR.md](guides/OPERATOR.md) |
| Troubleshoot | [guides/TROUBLESHOOTING_GUIDE.md](guides/TROUBLESHOOTING_GUIDE.md) |
| Understand config options | [generated/CONFIGURATION.md](generated/CONFIGURATION.md) |
| Write code | [development/GUIDELINES.md](development/GUIDELINES.md) |

---

## Directory Structure

```
docs/
├── QUICK_REFERENCE.md   # One-page operational cheatsheet
├── INDEX.md             # Complete documentation map
├── guides/              # How-to guides (operations)
├── architecture/        # Design philosophy (rarely changes)
├── development/         # Developer standards
├── templates/           # Fill-in forms
└── generated/           # Auto-generated from schemas
```

---

## Network Ports

| Port | Service |
|------|---------|
| 8000 | API (REST/WebSocket) |
| 8080 | HMI (Web UI) |
| 1502 | Modbus TCP |
| 34962-34964 | PROFINET RT |

---

## Related

- [Main README](../README.md) — Project overview
- [CHANGELOG](../CHANGELOG.md) — Version history
- [CONTRIBUTING](../CONTRIBUTING.md) — Development guide
