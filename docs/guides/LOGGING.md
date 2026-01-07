# Centralized Logging Guide

This document describes the logging architecture for the Water Treatment Controller.

## Overview

Centralized logging aggregates logs from all services into a single searchable store (Loki) with visualization via Grafana.

**Purpose**: Post-incident analysis and troubleshooting, NOT real-time operational alerting.

> **Note**: This is infrastructure plumbing, separate from the ISA-18.2 process alarm workflow. Process alarms appear in the HMI. Infrastructure logs appear in Grafana.

## Architecture

### Docker Deployment (Full Stack)

When running via Docker Compose, logging is fully integrated:

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Host                          │
├─────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                 │
│  │   API   │  │   UI    │  │   DB    │                 │
│  └────┬────┘  └────┬────┘  └────┬────┘                 │
│       └────────────┼────────────┘                       │
│                    │ JSON logs via Docker               │
│                    ▼                                    │
│             ┌─────────────┐                             │
│             │  Promtail   │                             │
│             └──────┬──────┘                             │
│                    ▼                                    │
│             ┌─────────────┐      ┌─────────────┐       │
│             │    Loki     │◄─────│   Grafana   │       │
│             └─────────────┘      └─────────────┘       │
└─────────────────────────────────────────────────────────┘
```

**Start with:**
```bash
cd docker
docker compose --env-file ../config/ports.env -f docker-compose.prod.yml up -d
```

**Access Grafana:**
- URL: `http://<host>:3000`
- Dashboard: "Logs" in the "Water Controller" folder

### Bare Metal Deployment

Bare metal deployments do NOT include Loki/Grafana locally. Instead, they can:

1. **Use journalctl** (default) - Query logs directly on the device
2. **Ship to remote Loki** - Send logs to a centralized logging server

#### Option 1: Local Journalctl (No Setup Required)

```bash
# View all water-controller logs
journalctl -u 'water-controller*' -f

# View API logs only
journalctl -u water-controller-api -f

# View errors from last hour
journalctl -u 'water-controller*' -p err --since "1 hour ago"

# Export logs for analysis
journalctl -u 'water-controller*' --since "2024-01-01" -o json > logs.json
```

#### Option 2: Ship to Remote Loki

For multi-site deployments, install Promtail on each device to ship logs to a central Loki server:

```bash
# Install Promtail pointing to central Loki
sudo ./scripts/install-promtail.sh --loki-url http://logging-server.example.com:3100
```

See [Remote Logging Setup](#remote-logging-setup) below.

## Remote Logging Setup

### Central Loki Server

Run Loki on a central server (can be Docker):

```bash
# On the logging server
cd docker
docker compose --env-file ../config/ports.env -f docker-compose.prod.yml up -d loki grafana
```

Expose Loki port (3100) to your network or VPN.

### Remote Promtail on Bare Metal Devices

On each bare metal Water Controller device:

```bash
# Download and run the install script
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/scripts/install-promtail.sh | \
  sudo bash -s -- --loki-url http://logging-server.example.com:3100
```

Or manually:

```bash
cd /opt/water-controller
sudo ./scripts/install-promtail.sh \
  --loki-url http://logging-server.example.com:3100 \
  --site-name "Plant-A"
```

### Multi-Site Architecture

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Plant Site A  │  │   Plant Site B  │  │   Plant Site C  │
│  (Bare Metal)   │  │  (Bare Metal)   │  │  (Bare Metal)   │
├─────────────────┤  ├─────────────────┤  ├─────────────────┤
│ water-controller│  │ water-controller│  │ water-controller│
│ promtail ───────┼──┼─ promtail ──────┼──┼─ promtail ──────┤
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │   Central Log Server   │
                 │   (Docker or Cloud)    │
                 ├────────────────────────┤
                 │  Loki ◄─── Grafana     │
                 │  :3100      :3000      │
                 └────────────────────────┘
```

## Grafana Dashboard

The "Logs" dashboard provides:

| Panel | Description |
|-------|-------------|
| Log Volume by Level | Time series of log counts by severity |
| Errors (Period) | Count of errors in selected time range |
| Warnings (Period) | Count of warnings in selected time range |
| Total Logs (Period) | Total log volume |
| Active Services | Number of services logging |
| Log Stream | Live/historical log viewer with filtering |
| Operator Messages | Filtered view of actionable operator logs |

### Filtering

Use the dropdown filters at the top:
- **Service**: Filter by service (api, database, ui, etc.)
- **Level**: Filter by severity (debug, info, warning, error, critical)
- **Search**: Free-text search in log messages

### Useful Queries

In the Grafana Explore view, try these LogQL queries:

```logql
# All errors
{app="water-controller"} |= "error"

# Database connection issues
{app="water-controller"} |~ "(?i)database.*error|connection.*refused"

# PROFINET communication problems
{app="water-controller"} |~ "(?i)profinet.*(timeout|lost|error)"

# Logs from specific site (multi-site)
{app="water-controller", site="Plant-A"}

# High-cardinality search
{app="water-controller"} | json | level="error" | line_format "{{.message}}"
```

## Alert Rules (Disabled by Default)

Pre-configured alert rules exist but are **paused**. They are templates for when you define:
- Alert ownership (IT? Maintenance?)
- Notification channel (email, SMS, PagerDuty)
- Escalation policy

To enable: Grafana → Alerting → Alert rules → Edit → Toggle "Paused" off

| Alert | Trigger |
|-------|---------|
| High Error Rate | >10 errors in 5 minutes |
| Critical Errors | Any critical-level log |
| Database Errors | Database connection failures |
| PROFINET Errors | RTU communication issues |
| IPC Errors | Shared memory failures |
| Service Restart Loop | >3 restarts in 10 minutes |
| No Logs Received | No logs for 5 minutes |

## Retention

| Data | Retention | Location |
|------|-----------|----------|
| Loki logs | 30 days | Docker: `wtc-loki-data` volume |
| Historian data | 30 days | TimescaleDB |
| Alarm history | 365 days | TimescaleDB |

## Troubleshooting

### Logs Not Appearing in Grafana

1. Check Promtail is running:
   ```bash
   # Docker
   docker logs wtc-promtail

   # Bare metal
   journalctl -u water-controller-promtail -f
   ```

2. Check Loki is healthy:
   ```bash
   curl http://localhost:3100/ready
   ```

3. Verify Promtail can reach Loki:
   ```bash
   docker exec wtc-promtail wget -q -O- http://loki:3100/ready
   ```

### High Memory Usage

Loki is configured with conservative limits for SBC deployment:
- 512MB memory limit
- 100MB query cache

If memory is an issue, reduce in `docker/loki/loki-config.yml`:
```yaml
query_range:
  results_cache:
    cache:
      embedded_cache:
        max_size_mb: 50  # Reduce from 100
```

### Disk Usage

Check Loki storage:
```bash
docker exec wtc-loki du -sh /loki/chunks
```

Logs auto-expire after 30 days. To force cleanup:
```bash
docker restart wtc-loki
```
