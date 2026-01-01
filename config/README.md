# Centralized Configuration

This directory contains the single source of truth for all network ports and related configuration used throughout the Water Treatment Controller system.

## Port Configuration

### Files

| File | Purpose | Usage |
|------|---------|-------|
| `ports.env` | Environment variable definitions | Docker, systemd, direct sourcing |
| `ports.sh` | Shell script with helper functions | Bash scripts, installation |

### How to Use

#### Shell Scripts

```bash
# Source the configuration
source /opt/water-controller/config/ports.sh

# Use the variables
echo "API running on ${WTC_API_URL}"
echo "UI available at ${WTC_UI_URL}"

# Use helper functions
wtc_print_ports
wtc_wait_for_port localhost ${WTC_API_PORT}
```

#### Docker Compose

```bash
# Load from env file
docker compose --env-file config/ports.env up -d

# Or set individual variables
WTC_API_PORT=8000 WTC_UI_PORT=8080 docker compose up -d
```

#### Systemd Services

The systemd service files load from:
1. `/opt/water-controller/config/ports.env` (centralized defaults)
2. `/etc/water-controller/environment` (local overrides)

#### Next.js (Frontend)

```typescript
import { PORTS, URLS } from '@/config/ports';

// Access port numbers
console.log(`API port: ${PORTS.api}`);

// Access URLs
fetch(`${URLS.api}/v1/rtus`);
```

#### FastAPI (Backend)

```python
from app.core.ports import get_api_port, get_allowed_origins

port = get_api_port()  # Returns WTC_API_PORT or 8000
origins = get_allowed_origins()  # Returns CORS origins
```

## Environment Variables

### Primary Port Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `WTC_API_PORT` | 8000 | FastAPI backend port |
| `WTC_UI_PORT` | 8080 | Next.js frontend port |
| `WTC_UI_HTTPS_PORT` | 8443 | HTTPS port (if enabled) |
| `WTC_DB_PORT` | 5432 | PostgreSQL port |

### Industrial Protocols

| Variable | Default | Description |
|----------|---------|-------------|
| `WTC_PROFINET_UDP_PORT` | 34964 | PROFINET discovery |
| `WTC_MODBUS_TCP_PORT` | 1502 | Modbus TCP (non-root) |

### Monitoring

| Variable | Default | Description |
|----------|---------|-------------|
| `WTC_GRAFANA_PORT` | 3000 | Grafana dashboard |
| `WTC_GRAYLOG_PORT` | 12201 | Graylog GELF input |

### Derived URLs

| Variable | Default | Description |
|----------|---------|-------------|
| `WTC_API_URL` | `http://localhost:8000` | Full API URL |
| `WTC_UI_URL` | `http://localhost:8080` | Full UI URL |
| `WTC_WS_URL` | `ws://localhost:8000/api/v1/ws/live` | WebSocket URL |

## Overriding Defaults

### Development

Set environment variables before starting:

```bash
export WTC_API_PORT=9000
export WTC_UI_PORT=9080
npm run dev
```

### Production

1. Edit `/opt/water-controller/config/ports.env` for system-wide changes
2. Edit `/etc/water-controller/environment` for deployment-specific overrides

### Docker

Pass environment variables to `docker compose`:

```bash
WTC_API_PORT=8001 docker compose up -d
```

Or use an env file:

```bash
docker compose --env-file ./my-ports.env up -d
```

## Anti-Pattern Prevention

### DO NOT

- Hardcode port numbers in source files
- Use magic numbers like `8080`, `8000`, `3000`
- Duplicate port definitions across files

### DO

- Import from `@/config/ports` (frontend)
- Import from `app.core.ports` (backend)
- Source `config/ports.sh` (shell scripts)
- Use `${WTC_*}` environment variables (Docker/systemd)

## File Locations

| Context | Config File Location |
|---------|---------------------|
| Development | `./config/ports.env` |
| Installed | `/opt/water-controller/config/ports.env` |
| Frontend | `web/ui/src/config/ports.ts` |
| Backend | `web/api/app/core/ports.py` |
