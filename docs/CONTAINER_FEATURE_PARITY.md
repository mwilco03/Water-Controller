# Container Feature Parity Matrix

This document maps every feature from the bare-metal `install.sh` system to the container-centric approach, ensuring 100% feature parity.

## Executive Summary

| Category | Bare-Metal Features | Container Equivalent | Parity Status |
|----------|--------------------|--------------------|---------------|
| System Detection | 4 functions | Not needed (image pre-built) | ✅ N/A |
| Dependencies | 5 functions | Baked into image | ✅ Covered |
| P-Net PROFINET | 8 functions | **HOST ONLY** | ⚠️ Separate |
| Build | 6 functions | CI/CD workflow | ✅ Covered |
| File Installation | 5 functions | Container volumes | ✅ Covered |
| Service Management | 8 functions | docker-compose | ✅ Covered |
| Network Config | 7 functions | Docker networks | ⚠️ Partial |
| Storage Config | 3 functions | Volumes + tmpfs | ✅ Covered |
| Logging | 4 functions | Docker logging | ✅ Covered |
| Upgrade | 12 functions | Image tags | ✅ Covered |
| Uninstall | 6 functions | docker-compose down | ✅ Covered |

---

## Detailed Feature Mapping

### 1. System Detection (`scripts/lib/detection.sh`)

| Function | Purpose | Container Equivalent |
|----------|---------|---------------------|
| `detect_system()` | Detect OS, arch, release | **Not needed** - Image is pre-built for target arch |
| `classify_hardware()` | Identify SBC type (Pi, x86, etc) | **Not needed** - Multi-arch images built in CI |
| `check_prerequisites()` | Verify system requirements | **Not needed** - Docker provides isolation |
| `init_logging()` | Initialize logging subsystem | Docker handles stdout/stderr → journald |

**Container Status:** ✅ **N/A** - Container images are architecture-specific and pre-built.

---

### 2. Dependencies (`scripts/lib/dependencies.sh`)

| Function | Purpose | Container Equivalent |
|----------|---------|---------------------|
| `install_python()` | Install Python 3.9+ | `Dockerfile.web` base image includes Python |
| `install_nodejs()` | Install Node.js 18+ | `Dockerfile.ui` base image includes Node.js |
| `install_build_deps()` | Install gcc, make, etc | Build stage only, not in final image |
| `install_profinet_deps()` | Install p-net dependencies | **HOST ONLY** - Not containerized |
| `verify_all_dependencies()` | Verify installations | Container healthchecks |

**Container Status:** ✅ **Covered** - Dependencies baked into images during CI build.

**Dockerfile.web:**
```dockerfile
FROM python:3.11-slim AS base
RUN pip install --no-cache-dir -r requirements.txt
```

**Dockerfile.ui:**
```dockerfile
FROM node:18-alpine AS base
RUN npm ci --legacy-peer-deps
```

---

### 3. P-Net PROFINET (`scripts/lib/pnet.sh`)

| Function | Purpose | Container Equivalent |
|----------|---------|---------------------|
| `install_pnet_full()` | Clone & build p-net | **HOST ONLY** |
| `verify_pnet_installation()` | Verify p-net libraries | **HOST ONLY** |
| `create_pnet_config()` | Create p-net config file | **HOST ONLY** |
| `configure_pnet_interface()` | Configure NIC for PROFINET | **HOST ONLY** |
| `load_pnet_modules()` | Load kernel modules | **HOST ONLY** |
| `install_pnet_sample()` | Install sample app | **HOST ONLY** |
| `diagnose_pnet()` | Diagnose p-net issues | **HOST ONLY** |

**Container Status:** ⚠️ **SEPARATE** - PROFINET controller MUST run on host.

**Reason:** PROFINET requires:
- Direct Layer 2 Ethernet access
- Kernel module loading
- Real-time scheduling
- Physical NIC binding

**Recommendation:** Keep `scripts/lib/pnet.sh` and `systemd/water-controller.service` for PROFINET controller on host.

---

### 4. Build (`scripts/lib/build.sh`)

| Function | Purpose | Container Equivalent |
|----------|---------|---------------------|
| `acquire_source()` | Clone or copy source | `actions/checkout@v4` in CI |
| `create_python_venv()` | Create virtualenv | `Dockerfile.web` RUN pip install |
| `build_python_backend()` | Install Python deps | `Dockerfile.web` multi-stage build |
| `build_react_frontend()` | npm install + build | `Dockerfile.ui` multi-stage build |
| `verify_build()` | Verify build artifacts | CI build success = verification |
| `apply_build_optimizations()` | Platform-specific opts | Multi-arch build handles this |

**Container Status:** ✅ **Covered** - `.github/workflows/docker.yml` handles all builds.

**CI Workflow:**
```yaml
- name: Build and push API image
  uses: docker/build-push-action@v5
  with:
    platforms: linux/amd64,linux/arm64,linux/arm/v7
```

---

### 5. File Installation (`scripts/lib/install-files.sh`)

| Function | Purpose | Container Equivalent |
|----------|---------|---------------------|
| `create_service_user()` | Create water-controller user | `Dockerfile` creates non-root user |
| `create_directory_structure()` | Create /opt, /etc, /var dirs | Docker volumes |
| `install_python_app()` | Copy Python files | `COPY` in Dockerfile |
| `install_frontend()` | Copy React build | `COPY` in Dockerfile |
| `install_config_template()` | Install default config | Volume mount `./config:/etc/water-controller` |

**Container Status:** ✅ **Covered**

**Volume Mapping (docker-compose.prod.yml):**
```yaml
volumes:
  - db_data:/var/lib/postgresql/data          # Database
  - redis_data:/data                          # Redis cache
  - grafana_data:/var/lib/grafana             # Grafana
  - ./config:/etc/water-controller:ro          # Config (read-only)
  - /dev/shm/wtc:/dev/shm/wtc:rw              # Shared memory IPC
```

**Directory Equivalents:**

| Bare-Metal Path | Container Equivalent |
|-----------------|---------------------|
| `/opt/water-controller` | Container filesystem (immutable) |
| `/etc/water-controller` | `./config:/etc/water-controller:ro` volume |
| `/var/lib/water-controller` | `db_data` named volume |
| `/var/log/water-controller` | Docker logging driver → journald |
| `/var/backups/water-controller` | External backup process |

---

### 6. Service Management (`scripts/lib/service.sh`)

| Function | Purpose | Container Equivalent |
|----------|---------|---------------------|
| `generate_service_unit()` | Create systemd unit | `docker-compose.prod.yml` service definition |
| `install_service()` | Install unit file | N/A - compose manages |
| `enable_service()` | Enable on boot | `restart: unless-stopped` |
| `start_service()` | Start service | `docker-compose up -d` |
| `stop_service()` | Stop service | `docker-compose stop` |
| `restart_service()` | Restart service | `docker-compose restart` |
| `check_service_health()` | Health check | `healthcheck:` in compose |
| `_calculate_resources()` | Calculate memory/CPU limits | `deploy.resources.limits` in compose |

**Container Status:** ✅ **Covered**

**Bare-Metal systemd:**
```ini
[Service]
MemoryMax=512M
MemoryHigh=400M
CPUQuota=150%
Restart=on-failure
RestartSec=10s
```

**Docker Equivalent:**
```yaml
services:
  api:
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
        reservations:
          memory: 128M
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

### 7. Network Configuration (`scripts/lib/network-storage.sh`)

| Function | Purpose | Container Equivalent |
|----------|---------|---------------------|
| `select_network_interface()` | Select Ethernet NIC | **HOST ONLY** for PROFINET |
| `configure_static_ip()` | Set static IP | **HOST ONLY** for PROFINET |
| `tune_network_interface()` | Disable WoL, coalescing | **HOST ONLY** for PROFINET |
| `configure_firewall()` | UFW/firewalld/iptables | Docker exposes ports, host firewall |
| `_configure_firewall_ufw()` | UFW rules | Host-level firewall |
| `_configure_firewall_firewalld()` | firewalld rules | Host-level firewall |
| `_configure_firewall_iptables()` | iptables rules | Docker manages iptables |

**Container Status:** ⚠️ **Partial**

**What Docker Handles:**
- Port exposure (`ports: "8080:8080"`)
- Internal networking (`networks: wtc-internal`)
- Service discovery (containers reach each other by name)

**What Remains on Host:**
- PROFINET NIC configuration
- Static IP for PROFINET network
- Host firewall (if enabled)

**Docker Network Isolation:**
```yaml
networks:
  wtc-internal:
    internal: true  # Database isolated - no external access
  wtc-external:
    # API/UI/Grafana accessible from host
```

---

### 8. Storage Configuration (`scripts/lib/network-storage.sh`)

| Function | Purpose | Container Equivalent |
|----------|---------|---------------------|
| `configure_tmpfs()` | SD card write endurance | `tmpfs` volume in compose |
| `configure_sqlite()` | SQLite WAL mode | TimescaleDB in container (better) |
| `configure_log_rotation()` | logrotate config | Docker logging driver rotation |

**Container Status:** ✅ **Covered** (and improved)

**tmpfs for Write Endurance:**
```yaml
services:
  api:
    volumes:
      - type: tmpfs
        target: /tmp
        tmpfs:
          size: 64M
```

**Database Upgrade:**
- Bare-metal: SQLite with WAL mode
- Container: TimescaleDB (PostgreSQL with time-series extension)
- **Improvement:** Better concurrent access, compression, retention policies

**Log Rotation:**
```yaml
services:
  api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"
```

Or use journald:
```yaml
services:
  api:
    logging:
      driver: "journald"
      options:
        tag: "wtc-api"
```

---

### 9. Logging

| Bare-Metal Feature | Container Equivalent |
|-------------------|---------------------|
| journald integration | `logging: driver: journald` |
| File logging to /var/log | `logging: driver: json-file` |
| Log rotation (daily, 7 days) | `max-size`, `max-file` options |
| Error capture for debugging | `docker logs wtc-api --tail 100` |

**Container Status:** ✅ **Covered**

**Access Logs:**
```bash
# View logs
docker-compose logs -f api

# View last 100 lines
docker logs wtc-api --tail 100

# Filter by time
docker logs wtc-api --since 1h

# If using journald driver
journalctl -u docker.service CONTAINER_NAME=wtc-api
```

---

### 10. Upgrade (`scripts/lib/upgrade.sh`)

| Function | Purpose | Container Equivalent |
|----------|---------|---------------------|
| `compare_versions()` | Compare installed vs new | Image tags (v1.0.0 vs v1.1.0) |
| `pre_upgrade_health_check()` | Verify system healthy | `docker-compose ps` |
| `verify_network_connectivity()` | Check network | Registry pull test |
| `create_rollback_point()` | Backup for rollback | Previous image tag |
| `perform_rollback()` | Restore from backup | `VERSION=1.0.0 docker-compose up -d` |
| `emergency_rollback()` | Emergency restore | Same as above |
| `snapshot_database_state()` | Backup database | `pg_dump` from container |
| `verify_database_migration()` | Check migrations | Application handles |
| `post_upgrade_validation()` | Verify upgrade worked | Healthchecks |
| `generate_upgrade_plan()` | Plan upgrade steps | N/A - just change tag |
| `generate_upgrade_report()` | Report upgrade result | `docker-compose ps` |
| `notify_upgrade_complete()` | Send notification | External webhook |

**Container Status:** ✅ **Covered** (and simpler)

**Upgrade Process:**
```bash
# 1. Pull new images
VERSION=1.1.0 docker-compose -f docker-compose.prod.yml pull

# 2. Backup database (optional)
docker exec wtc-database pg_dump -U wtc water_treatment > backup.sql

# 3. Upgrade
VERSION=1.1.0 docker-compose -f docker-compose.prod.yml up -d

# 4. Verify
docker-compose ps
docker logs wtc-api --tail 20
```

**Rollback:**
```bash
# Instant rollback to previous version
VERSION=1.0.0 docker-compose -f docker-compose.prod.yml up -d
```

---

### 11. Uninstall

| Function | Purpose | Container Equivalent |
|----------|---------|---------------------|
| `do_uninstall()` | Remove installation | `docker-compose down` |
| `_uninstall_pnet_libraries()` | Remove p-net | **HOST ONLY** |
| `_uninstall_firewall_rules()` | Remove firewall rules | Automatic when containers removed |
| `_uninstall_udev_rules()` | Remove udev rules | **HOST ONLY** |
| `_uninstall_network_config()` | Remove network config | **HOST ONLY** |
| Keep data option | Preserve data/config | Named volumes persist |

**Container Status:** ✅ **Covered**

**Uninstall Commands:**
```bash
# Stop and remove containers (keep volumes)
docker-compose -f docker-compose.prod.yml down

# Stop, remove containers AND volumes (destructive)
docker-compose -f docker-compose.prod.yml down -v

# Remove images too
docker-compose -f docker-compose.prod.yml down --rmi all -v
```

---

## Features NOT Containerized (Must Remain on Host)

### PROFINET Controller

The C PROFINET controller **cannot** be containerized due to:

1. **Layer 2 Ethernet Access** - PROFINET uses raw Ethernet frames, not IP
2. **Kernel Module Requirements** - Needs `pnet` kernel modules
3. **Real-Time Scheduling** - Requires RT kernel features
4. **Physical NIC Binding** - Must bind to specific hardware

**Host Deployment:**
```bash
# Install PROFINET controller on host
cd scripts
sudo ./install.sh --skip-deps --skip-build
# Only installs p-net and systemd service
```

**systemd Service (water-controller.service):**
```ini
[Unit]
Description=Water Treatment PROFINET Controller
After=network-online.target

[Service]
Type=exec
ExecStart=/opt/water-controller/bin/water-controller
Restart=on-failure
# Needs NET_RAW and NET_ADMIN capabilities
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN
```

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DEPLOYMENT TARGET                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   HOST (systemd)                  CONTAINERS (docker-compose)        │
│   ┌────────────────┐             ┌─────────────────────────────────┐│
│   │ PROFINET       │             │                                 ││
│   │ Controller     │◄───────────►│  API (ghcr.io/.../api:v1.0.0)   ││
│   │ (C binary)     │  IPC/shm    │  UI  (ghcr.io/.../ui:v1.0.0)    ││
│   │                │             │  TimescaleDB                    ││
│   │ Capabilities:  │             │  Grafana                        ││
│   │ - NET_RAW      │             │                                 ││
│   │ - NET_ADMIN    │             │                                 ││
│   └────────────────┘             └─────────────────────────────────┘│
│          │                                      │                    │
│          │ PROFINET (L2)                       │ HTTP/WS            │
│          ▼                                      ▼                    │
│   ┌────────────────┐             ┌─────────────────────────────────┐│
│   │ Physical NIC   │             │ Operator Browser / HMI Client   ││
│   │ (eth0)         │             │ http://host:3001 (UI)           ││
│   └────────────────┘             │ http://host:8080 (API)          ││
│                                  │ http://host:3000 (Grafana)      ││
│                                  └─────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

---

## Migration Checklist

### Before Migration

- [ ] Document current configuration (`/etc/water-controller/`)
- [ ] Export historian data (SQLite → pg_dump format)
- [ ] Note static IP configuration
- [ ] Backup alarm rules and thresholds

### During Migration

- [ ] Install Docker and docker-compose on target
- [ ] Pull container images
- [ ] Create config volume with migrated settings
- [ ] Import database to TimescaleDB
- [ ] Start containers
- [ ] Verify API health endpoint

### After Migration

- [ ] Verify all RTUs connecting (via API)
- [ ] Verify alarms functioning
- [ ] Verify historian recording
- [ ] Verify HMI displays correctly
- [ ] Update firewall rules if needed
- [ ] Document new deployment

---

## Quick Reference

### Bare-Metal Commands → Docker Commands

| Operation | Bare-Metal | Docker |
|-----------|------------|--------|
| Install | `./install.sh` | `docker-compose pull && docker-compose up -d` |
| Start | `systemctl start water-controller` | `docker-compose start` |
| Stop | `systemctl stop water-controller` | `docker-compose stop` |
| Restart | `systemctl restart water-controller` | `docker-compose restart` |
| Status | `systemctl status water-controller` | `docker-compose ps` |
| Logs | `journalctl -u water-controller` | `docker-compose logs -f` |
| Upgrade | `./install.sh --upgrade` | `VERSION=x.x.x docker-compose up -d` |
| Rollback | Manual restore from backup | `VERSION=prev docker-compose up -d` |
| Uninstall | `./install.sh --uninstall` | `docker-compose down -v` |
| Health | `systemctl status` + curl | `docker-compose ps` + healthchecks |

---

## Conclusion

**100% Feature Parity Achieved** for containerizable components:
- ✅ API (FastAPI)
- ✅ UI (Next.js)
- ✅ Database (TimescaleDB - upgrade from SQLite)
- ✅ Cache (Redis - for caching and pub/sub)
- ✅ Visualization (Grafana)
- ✅ Logging
- ✅ Health monitoring
- ✅ Resource limits
- ✅ Upgrade/rollback

**Must Remain on Host:**
- ⚠️ PROFINET Controller (hardware requirements)
- ⚠️ P-Net library and kernel modules
- ⚠️ Physical NIC configuration

The hybrid architecture (host PROFINET + containerized web stack) is the correct approach for industrial SCADA systems.
