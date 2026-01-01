# Migration Guide

This guide covers migrating between Water Treatment Controller versions and deployment modes.

## Table of Contents

- [Version Migration](#version-migration)
- [Deployment Mode Migration](#deployment-mode-migration)
- [Database Migration](#database-migration)
- [Configuration Migration](#configuration-migration)

---

## Version Migration

### Pre-Migration Checklist

Before upgrading to a new version:

- [ ] Review the [CHANGELOG](../../CHANGELOG.md) for breaking changes
- [ ] Backup your database
- [ ] Backup your configuration files
- [ ] Note your current version: `cat /opt/water-controller/.version`
- [ ] Ensure adequate disk space (at least 2GB free)
- [ ] Plan for downtime (typically 5-15 minutes)

### Backup Procedures

#### Bare-Metal Backup

```bash
# Create timestamped backup
BACKUP_DIR="/var/backups/water-controller/$(date +%Y%m%d_%H%M%S)"
sudo mkdir -p "$BACKUP_DIR"

# Backup configuration
sudo cp -r /etc/water-controller "$BACKUP_DIR/config"

# Backup database
sudo cp /var/lib/water-controller/water_treatment.db "$BACKUP_DIR/"

# Backup version info
sudo cp /opt/water-controller/.version "$BACKUP_DIR/"

echo "Backup created: $BACKUP_DIR"
```

#### Docker Backup

```bash
# Backup database
docker compose exec database pg_dump -U wtc water_treatment > backup_$(date +%Y%m%d).sql

# Backup configuration
cp -r config/ backup_config_$(date +%Y%m%d)/
```

### Migration Steps

#### Bare-Metal Upgrade

```bash
# Stop services
sudo systemctl stop water-controller

# Run upgrade
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | bash -s -- upgrade

# Verify
sudo systemctl status water-controller
curl http://localhost:8000/health
```

#### Docker Upgrade

```bash
cd docker

# Pull new images
docker compose pull

# Stop and restart with new images
docker compose down
docker compose up -d

# Verify
docker compose ps
curl http://localhost:8000/health
```

### Post-Migration Validation

After upgrading, verify:

```bash
# Check API health
curl http://localhost:8000/health

# Check version
curl http://localhost:8000/api/v1/system/version

# Check database connectivity
curl http://localhost:8000/api/v1/rtus

# Review logs for errors
journalctl -u water-controller --since "10 minutes ago"  # bare-metal
docker compose logs --since 10m  # docker
```

### Rollback Procedures

If issues occur after upgrade:

#### Bare-Metal Rollback

```bash
# Stop service
sudo systemctl stop water-controller

# Restore from backup
BACKUP_DIR="/var/backups/water-controller/YYYYMMDD_HHMMSS"  # your backup
sudo cp -r "$BACKUP_DIR/config/"* /etc/water-controller/
sudo cp "$BACKUP_DIR/water_treatment.db" /var/lib/water-controller/

# Reinstall previous version
curl -fsSL .../bootstrap.sh | bash -s -- install --force --branch v1.x.x

# Start service
sudo systemctl start water-controller
```

#### Docker Rollback

```bash
# Restore database
docker compose exec -T database psql -U wtc water_treatment < backup_YYYYMMDD.sql

# Use previous image version
# Edit docker-compose.yml to specify version tag
# image: ghcr.io/mwilco03/water-controller/api:v1.x.x

docker compose up -d
```

---

## Deployment Mode Migration

### Bare-Metal to Docker

Migrate from systemd services to Docker containers.

#### Step 1: Export Data

```bash
# Stop services
sudo systemctl stop water-controller

# Export database
sudo sqlite3 /var/lib/water-controller/water_treatment.db .dump > export.sql

# Copy configuration
cp -r /etc/water-controller ./config_backup
```

#### Step 2: Deploy Docker

```bash
# Clone repository
git clone https://github.com/mwilco03/Water-Controller.git
cd Water-Controller/docker

# Start containers
docker compose up -d

# Wait for database
sleep 10
```

#### Step 3: Import Data

```bash
# Import to PostgreSQL (requires conversion from SQLite)
# First, convert SQL syntax differences
sed -i 's/AUTOINCREMENT/SERIAL/g' export.sql
sed -i 's/INTEGER PRIMARY KEY/SERIAL PRIMARY KEY/g' export.sql

# Import
docker compose exec -T database psql -U wtc water_treatment < export.sql
```

#### Step 4: Verify and Cleanup

```bash
# Verify
curl http://localhost:8000/health

# Disable old services
sudo systemctl disable water-controller
sudo systemctl disable water-controller-api

# Optionally remove old installation
# sudo rm -rf /opt/water-controller
```

### Docker to Bare-Metal

Migrate from Docker containers to systemd services.

#### Step 1: Export Data

```bash
cd docker

# Export database
docker compose exec database pg_dump -U wtc water_treatment > export.sql

# Stop containers
docker compose down
```

#### Step 2: Install Bare-Metal

```bash
# Run installer
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | bash -s -- install --mode baremetal

# Wait for installation
```

#### Step 3: Import Data

```bash
# Convert PostgreSQL dump to SQLite (if needed)
# This is complex - recommend using the API to re-configure RTUs instead

# Or if staying with PostgreSQL:
# Install PostgreSQL on host and import
sudo -u postgres psql water_treatment < export.sql
```

#### Step 4: Verify

```bash
# Check service
sudo systemctl status water-controller

# Check API
curl http://localhost:8000/health
```

---

## Database Migration

### SQLite to PostgreSQL

The application supports both databases. To migrate:

#### Export from SQLite

```bash
# Dump all data
sqlite3 /var/lib/water-controller/water_treatment.db .dump > sqlite_export.sql

# Or export as CSV for cleaner import
sqlite3 /var/lib/water-controller/water_treatment.db \
  ".mode csv" \
  ".headers on" \
  ".output rtus.csv" \
  "SELECT * FROM rtus;"
```

#### Import to PostgreSQL

```bash
# Create database (if not exists)
sudo -u postgres createdb water_treatment

# Import using psql
sudo -u postgres psql water_treatment < sqlite_export.sql

# Or use CSV import
sudo -u postgres psql water_treatment -c "\copy rtus FROM 'rtus.csv' CSV HEADER"
```

### Schema Upgrades

Schema migrations are handled automatically. To run manually:

```bash
# Bare-metal
cd /opt/water-controller
source venv/bin/activate
alembic upgrade head

# Docker
docker compose exec api alembic upgrade head
```

### Data Integrity Verification

After migration, verify data:

```bash
# Count records
curl http://localhost:8000/api/v1/rtus | jq 'length'
curl http://localhost:8000/api/v1/sensors | jq 'length'

# Compare with source count
sqlite3 old_database.db "SELECT COUNT(*) FROM rtus;"
```

---

## Configuration Migration

### Environment Variable Changes

If environment variables have changed between versions:

| Old Variable | New Variable | Notes |
|--------------|--------------|-------|
| `API_PORT` | `WTC_API_PORT` | Prefixed with WTC_ |
| `UI_PORT` | `WTC_UI_PORT` | Prefixed with WTC_ |
| `DB_PORT` | `WTC_DB_PORT` | Prefixed with WTC_ |

Update your configuration:

```bash
# Update ports.env
sed -i 's/API_PORT/WTC_API_PORT/g' config/ports.env
sed -i 's/UI_PORT/WTC_UI_PORT/g' config/ports.env
```

### Config File Format Changes

If config file format has changed, convert:

```bash
# Backup old config
cp /etc/water-controller/config.yaml /etc/water-controller/config.yaml.old

# The installer will generate a new template
# Manually merge your customizations
```

### Port Configuration Updates

All ports are now centralized in `config/ports.env`:

```bash
# Copy template
cp config/ports.env.example config/ports.env

# Edit with your values
vi config/ports.env

# Restart services
sudo systemctl restart water-controller  # bare-metal
docker compose restart  # docker
```

---

## Troubleshooting Migration Issues

### Data Not Appearing

1. Check database connection:
   ```bash
   curl http://localhost:8000/api/v1/system/database
   ```

2. Verify data was imported:
   ```bash
   # Docker
   docker compose exec database psql -U wtc -c "SELECT COUNT(*) FROM rtus;"
   ```

### Service Won't Start After Migration

1. Check logs:
   ```bash
   journalctl -u water-controller -n 50  # bare-metal
   docker compose logs api  # docker
   ```

2. Verify configuration:
   ```bash
   cat /etc/water-controller/config.yaml  # bare-metal
   docker compose config  # docker
   ```

### Permission Errors

```bash
# Fix bare-metal permissions
sudo chown -R water-controller:water-controller /var/lib/water-controller

# Fix docker permissions
sudo chown -R 1000:1000 ./data
```

---

## Getting Help

If you encounter issues during migration:

1. Check the [Troubleshooting Guide](./TROUBLESHOOTING_GUIDE.md)
2. Review logs for specific error messages
3. Open an issue on GitHub with:
   - Source version
   - Target version
   - Migration type (version/mode)
   - Error messages
   - Steps to reproduce
