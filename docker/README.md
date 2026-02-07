# Water Treatment Controller - Docker Deployment

This directory contains Docker configuration for the Water Treatment Controller SCADA system.

## Quick Start

```bash
# Generate build environment with git version info
./generate-build-env.sh

# Build and start all services
docker compose up -d --build

# View logs
docker compose logs -f controller
docker compose logs -f api
docker compose logs -f ui
```

## Version Information in Builds

The controller binary embeds git commit SHA and build date for traceability. To ensure this information is properly embedded:

### Automatic (Recommended)

Run `generate-build-env.sh` before building:

```bash
./generate-build-env.sh
docker compose build
```

This script:
- Detects the current git commit SHA and date
- Generates a `.env` file with build variables
- Docker Compose automatically loads `.env` for all builds

### Bootstrap (Production)

When using `bootstrap.sh` for production deployment, the build environment is generated automatically. No manual steps required.

### Manual (Advanced)

Set environment variables before building:

```bash
export GIT_COMMIT=$(git rev-parse --short=7 HEAD)
export GIT_DATE=$(git log -1 --format=%ci)
docker compose build controller
```

## Services

- **controller**: C PROFINET controller (port 4840 for OPC UA)
- **api**: FastAPI backend (port 8000)
- **ui**: Next.js HMI frontend (port 8080)
- **database**: TimescaleDB (port 5432, localhost only)
- **grafana**: Visualization (port 3000)
- **loki**: Log aggregation (internal)
- **promtail**: Log collector (internal)
- **openplc**: Ladder logic viewer (port 8081, optional - use `--profile openplc`)

## Environment Variables

All services support configuration via environment variables. See `.env` (auto-generated) or set manually:

- `WTC_INTERFACE`: Network interface (auto-detected if unset)
- `WTC_CYCLE_TIME`: Controller cycle time in ms (default: 1000)
- `WTC_LOG_LEVEL`: Log level (default: INFO)
- `WTC_API_PORT`: API HTTP port (default: 8000)
- `WTC_UI_PORT`: UI HTTP port (default: 8080)
- `GIT_COMMIT`: Git commit SHA for build traceability
- `GIT_DATE`: Git commit date for build traceability

## Rebuilding Services

```bash
# Rebuild specific service
./generate-build-env.sh
docker compose build controller
docker compose up -d controller

# Rebuild all services
./generate-build-env.sh
docker compose build
docker compose up -d

# Force clean rebuild (no cache)
./generate-build-env.sh
docker compose build --no-cache
docker compose up -d --force-recreate
```

## Health Checks

All services include health checks. View status:

```bash
docker compose ps
```

Wait for all services to become healthy (bootstrap does this automatically):

```bash
# Check controller health
docker inspect --format='{{.State.Health.Status}}' wtc-controller

# View controller version
docker logs wtc-controller 2>&1 | grep "Starting Water"
```

## Network Configuration

The controller and API run in **host network mode** to enable:
- PROFINET DCP discovery (raw Ethernet Layer 2 frames)
- Direct access to physical network RTUs
- POSIX shared memory IPC between controller and API

Required capabilities:
- `NET_RAW`: For raw sockets (DCP discovery)
- `NET_ADMIN`: For network interface configuration

## Passwords (Development/Test Only)

Per `CLAUDE.md`, passwords are intentionally hardcoded for development:
- Database: `wtc` / `wtc_password`
- Grafana: `admin` / `admin`

**DO NOT** change these or externalize to environment variables. See [CLAUDE.md](../CLAUDE.md) for rationale.

## Common Issues

### "build unknown" in controller logs

The controller shows "build unknown" when git version information is not embedded. Fix:

```bash
./generate-build-env.sh
docker compose build controller --no-cache
docker compose up -d controller
```

### Controller can't discover RTUs

Check network interface auto-detection:

```bash
docker logs wtc-controller | grep "Interface"
```

Override if needed:

```bash
WTC_INTERFACE=eth0 docker compose up -d controller
```

### Health check failures

View detailed status:

```bash
docker compose ps
docker logs wtc-controller
docker logs wtc-api
```

## Architecture

See [CLAUDE.md](../CLAUDE.md) and [docs/architecture/SYSTEM_DESIGN.md](../docs/architecture/SYSTEM_DESIGN.md) for:
- PROFINET connection sequence
- Docker deployment architecture
- Component interaction diagrams
- Build system design

## Development

For development with live code reloading, see [docs/development/GUIDELINES.md](../docs/development/GUIDELINES.md).

For testing, use the test suite:

```bash
cd ..
make test  # Run all tests (C, Python, JS, integration)
```
