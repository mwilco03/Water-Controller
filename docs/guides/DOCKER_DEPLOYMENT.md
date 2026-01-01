# Docker Deployment Guide

This guide covers deploying the Water Treatment Controller using Docker containers.

## Overview

Docker deployment provides:
- Isolated, reproducible environments
- Easy scaling and updates
- Simplified dependency management
- Multi-architecture support (amd64, arm64, armv7)

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 2 GB | 4 GB |
| Disk | 10 GB | 20 GB |
| Docker | 20.10+ | Latest |
| Docker Compose | v2.0+ | Latest |

## Quick Start

### 1. Install Docker

```bash
# Debian/Ubuntu
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Verify installation
docker --version
docker compose version
```

### 2. Clone Repository

```bash
git clone https://github.com/mwilco03/Water-Controller.git
cd Water-Controller
```

### 3. Start Services

```bash
# Using the bootstrap script
./bootstrap.sh install --mode docker

# Or directly with docker compose
cd docker
docker compose --env-file ../config/ports.env up -d
```

### 4. Verify Deployment

```bash
# Check container status
docker compose ps

# View logs
docker compose logs -f

# Check API health
curl http://localhost:8000/health
```

## Configuration

### Environment Variables

All ports are configured via `config/ports.env`:

```bash
# API Server
WTC_API_PORT=8000

# Web UI
WTC_UI_PORT=8080

# Database
WTC_DB_PORT=5432

# Grafana
WTC_GRAFANA_PORT=3000

# Modbus TCP
WTC_MODBUS_TCP_PORT=1502
```

### Database Password

Set the database password before starting:

```bash
export DB_PASSWORD=your_secure_password
docker compose up -d
```

Or create a `.env` file in the `docker/` directory:

```bash
DB_PASSWORD=your_secure_password
GRAFANA_PASSWORD=your_grafana_password
```

## Services

### Default Services

| Service | Description | Port |
|---------|-------------|------|
| database | PostgreSQL + TimescaleDB | 5432 (internal) |
| api | FastAPI backend | 8000 |
| ui | Next.js frontend | 8080 |
| grafana | Visualization | 3000 |

### Optional Services

#### PROFINET Controller

The PROFINET controller requires host network mode. Enable it with:

```bash
docker compose --profile profinet up -d
```

Configure the network interface:

```bash
export PROFINET_INTERFACE=eth0
docker compose --profile profinet up -d
```

## Production Deployment

For production, use the pre-built images:

```bash
cd docker
docker compose -f docker-compose.prod.yml up -d
```

### Security Hardening

1. **Use strong passwords**:
   ```bash
   DB_PASSWORD=$(openssl rand -base64 32)
   GRAFANA_PASSWORD=$(openssl rand -base64 32)
   ```

2. **Restrict exposed ports** - The database is not exposed externally by default

3. **Enable TLS** - Configure a reverse proxy (nginx, traefik) for HTTPS

4. **Resource limits** - Already configured in docker-compose.yml

## Multi-Architecture Support

Pre-built images support:
- `linux/amd64` - Standard x86_64 servers
- `linux/arm64` - Raspberry Pi 4/5, AWS Graviton
- `linux/arm/v7` - Raspberry Pi 3, older ARM devices

Docker automatically pulls the correct architecture.

## Maintenance

### Updating Containers

```bash
# Pull latest images
docker compose pull

# Restart with new images
docker compose up -d

# Remove old images
docker image prune -f
```

### Backup Database

```bash
# Backup
docker compose exec database pg_dump -U wtc water_treatment > backup.sql

# Restore
docker compose exec -T database psql -U wtc water_treatment < backup.sql
```

### Viewing Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api

# Last 100 lines
docker compose logs --tail 100 api
```

### Health Checks

All containers have health checks configured:

```bash
# Check health status
docker compose ps

# Detailed health info
docker inspect --format='{{.State.Health.Status}}' wtc-api
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs for errors
docker compose logs api

# Check container status
docker compose ps -a

# Restart specific service
docker compose restart api
```

### Database Connection Issues

```bash
# Verify database is healthy
docker compose exec database pg_isready -U wtc

# Check database logs
docker compose logs database
```

### Port Conflicts

If ports are already in use:

```bash
# Check what's using a port
sudo lsof -i :8000

# Change port in config/ports.env
WTC_API_PORT=8001

# Restart
docker compose down && docker compose up -d
```

### Permission Errors

```bash
# Fix volume permissions
sudo chown -R 1000:1000 ./data

# Or run with user mapping
docker compose down
docker compose up -d
```

## Removing Deployment

```bash
# Stop and remove containers
docker compose down

# Also remove volumes (WARNING: deletes data)
docker compose down -v

# Remove images
docker compose down --rmi all
```

## Comparison: Docker vs Bare-Metal

| Aspect | Docker | Bare-Metal |
|--------|--------|------------|
| Setup complexity | Low | Medium |
| Resource overhead | ~10% | None |
| Isolation | Full | Shared |
| Updates | Pull & restart | Reinstall |
| PROFINET support | Limited* | Full |
| SD card wear | Normal | Optimized |

*PROFINET requires host network mode, reducing isolation benefits.

## Next Steps

- [Migration Guide](./MIGRATION.md) - Migrating between deployment modes
- [Operator Guide](./OPERATOR.md) - Day-to-day operations
- [Troubleshooting Guide](./TROUBLESHOOTING_GUIDE.md) - Common issues
