# Water-Controller Deployment Troubleshooting Guide

**Date:** 2026-01-17
**Version:** 1.0.0

---

## Quick Fix: Auth Failure

If wtc-api is failing to connect to PostgreSQL, run:

```bash
./scripts/fix-database-auth.sh
```

This script will:
1. Ensure the `wtc` user exists with password `wtc_password`
2. Grant all necessary permissions
3. Initialize the database schema
4. Restart the API container

---

## Complete Deployment Validation

To validate your entire deployment:

```bash
chmod +x scripts/validate-deployment.sh scripts/fix-database-auth.sh
./scripts/validate-deployment.sh
```

This checks:
- ✓ Docker environment
- ✓ Container status
- ✓ Database connectivity
- ✓ API health
- ✓ Web UI
- ✓ Grafana (optional)
- ✓ Network configuration
- ✓ Authentication

---

## Common Issues and Fixes

### Issue 1: API Cannot Connect to Database

**Symptoms:**
```
docker logs wtc-api
# Shows: sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection failed
# Or: FATAL: password authentication failed for user "wtc"
```

**Root Cause:**
The `wtc` database user doesn't exist or has wrong permissions.

**Fix:**
```bash
# Automatic fix
./scripts/fix-database-auth.sh

# Manual fix
docker exec wtc-database psql -U postgres -d water_treatment <<EOF
CREATE USER wtc WITH PASSWORD 'wtc_password' CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE water_treatment TO wtc;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO wtc;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO wtc;
ALTER SCHEMA public OWNER TO wtc;
EOF

docker restart wtc-api
```

**Verify:**
```bash
docker exec wtc-database psql -U wtc -d water_treatment -c "SELECT 1"
# Should return: 1
```

---

### Issue 2: Database Schema Mismatch

**Symptoms:**
```
API logs show: Table 'rtus' doesn't exist
Or: relation "rtus" does not exist
```

**Root Cause:**
The `init.sql` file has outdated table names that don't match SQLAlchemy models.

**Table Name Mapping:**

| init.sql (OLD) | SQLAlchemy Models (CURRENT) | Status |
|----------------|----------------------------|--------|
| `rtu_devices` | `rtus` | ⚠️ MISMATCH |
| `slot_configs` | `slots` | ⚠️ MISMATCH |
| `historian_data` | `historian_samples` | ⚠️ MISMATCH |
| `alarm_history` | `alarm_events` | ⚠️ MISMATCH |
| `users` | `users` | ✓ MATCH |
| `audit_log` | `audit_log` | ✓ MATCH |
| `pid_loops` | `pid_loops` | ✓ MATCH |
| `alarm_rules` | `alarm_rules` | ✓ MATCH |

**Fix:**

The SQLAlchemy models will auto-create tables on first run using the correct names. However, `init.sql` needs to be updated to match.

**Option A: Let SQLAlchemy Create Schema (Recommended)**
```bash
# Remove old database volume
docker compose down -v

# Remove init.sql from being mounted (or rename tables in init.sql)
# Edit docker-compose.yml and comment out:
#   - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro

# Restart with fresh database
docker compose up -d database

# Wait for healthy
sleep 10

# API will auto-create schema via SQLAlchemy
docker compose up -d api

# Verify
docker exec wtc-database psql -U wtc -d water_treatment -c "\dt"
```

**Option B: Update init.sql to Match Models**

The init.sql needs to be regenerated to match current SQLAlchemy models. Use Alembic migrations or manually update table names.

---

### Issue 3: Tables Missing Despite init.sql

**Symptoms:**
```
docker exec wtc-database psql -U wtc -d water_treatment -c "\dt"
# Shows: 0 tables
```

**Root Cause:**
- init.sql didn't run (volume already existed with data)
- Permission errors prevented table creation
- init.sql has SQL errors

**Fix:**
```bash
# Check if init.sql ran
docker logs wtc-database | grep "init.sql"

# Force re-initialization
docker compose down -v  # WARNING: Destroys all data!
docker compose up -d database

# Or manually run init.sql
docker exec -i wtc-database psql -U wtc -d water_treatment < docker/init.sql
```

---

### Issue 4: API Container Crashes on Startup

**Symptoms:**
```
docker ps
# wtc-api not listed or constantly restarting
```

**Diagnosis:**
```bash
docker logs wtc-api --tail 50

# Common errors:
# 1. "Connection refused" - Database not ready
# 2. "ModuleNotFoundError" - Missing Python dependencies
# 3. "Permission denied" - File permissions issue
```

**Fixes:**

**Connection Refused:**
```bash
# Database takes time to start
docker compose up -d database
sleep 15
docker compose up -d api
```

**Missing Dependencies:**
```bash
# Rebuild API container
docker compose build --no-cache api
docker compose up -d api
```

**Permission Issues:**
```bash
# Check if running as wrong user
docker exec wtc-api whoami
# Should be: wtc or uid 1000

# Fix ownership (if needed on host)
sudo chown -R 1000:1000 web/api
```

---

### Issue 5: SQLAlchemy Can't Create Tables

**Symptoms:**
```
API logs: permission denied for schema public
Or: must be owner of schema public
```

**Root Cause:**
User `wtc` doesn't own the `public` schema.

**Fix:**
```bash
docker exec wtc-database psql -U postgres -d water_treatment -c "ALTER SCHEMA public OWNER TO wtc;"
docker restart wtc-api
```

---

### Issue 6: TimescaleDB Extension Missing

**Symptoms:**
```
ERROR: extension "timescaledb" does not exist
```

**Fix:**
```bash
docker exec wtc-database psql -U postgres -d water_treatment -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"
```

---

### Issue 7: Default Admin User Missing

**Symptoms:**
Cannot login with `admin/admin`

**Fix:**
```bash
docker exec wtc-database psql -U wtc -d water_treatment <<EOF
INSERT INTO users (username, password_hash, role, active)
VALUES ('admin', '\$2b\$12\$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G5y5GJzfHJgP7.', 'admin', true)
ON CONFLICT (username) DO NOTHING;
EOF
```

The password hash is for `admin`.

---

## Step-by-Step Fresh Deployment

### 1. Prerequisites

```bash
# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo apt-get install docker-compose-plugin
```

### 2. Clone and Setup

```bash
git clone https://github.com/mwilco03/Water-Controller.git
cd Water-Controller
```

### 3. Environment Setup

```bash
# Use bootstrap script (recommended)
./bootstrap.sh install --mode docker

# Or manual setup
cd docker
cp ../config/ports.env .env
# Edit .env as needed
```

### 4. Start Services

```bash
cd docker
docker compose up -d
```

### 5. Monitor Startup

```bash
# Watch all logs
docker compose logs -f

# Or individual services
docker logs -f wtc-api
docker logs -f wtc-database
```

### 6. Validate Deployment

```bash
# Wait 30 seconds for all services to start
sleep 30

# Run validation
./scripts/validate-deployment.sh
```

### 7. Fix Any Issues

```bash
# If database auth fails
./scripts/fix-database-auth.sh

# If tables missing
docker exec -i wtc-database psql -U wtc -d water_treatment < docker/init.sql
```

### 8. Access Services

```bash
# API Documentation
open http://localhost:8000/docs

# Web UI
open http://localhost:8080

# Grafana
open http://localhost:3000
```

### 9. Test Authentication

```bash
# Default credentials: admin / admin
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'

# Should return: {"token":"...","username":"admin","role":"admin",...}
```

---

## Database Connection Debugging

### Check Database is Running

```bash
docker ps | grep wtc-database
# Should show: wtc-database ... Up ... 5432/tcp
```

### Check Database Accepts Connections

```bash
docker exec wtc-database pg_isready -U wtc -d water_treatment
# Should show: accepting connections
```

### Test Direct Connection

```bash
docker exec -it wtc-database psql -U wtc -d water_treatment
# Should get psql prompt
water_treatment=> \dt
# Lists tables
water_treatment=> \q
```

### Check User Permissions

```bash
docker exec wtc-database psql -U wtc -d water_treatment -c "
SELECT
    table_name,
    privilege_type
FROM information_schema.table_privileges
WHERE grantee = 'wtc'
AND table_schema = 'public'
LIMIT 10;
"
```

### Check API Database URL

```bash
docker exec wtc-api env | grep DATABASE_URL
# Should show: DATABASE_URL=postgresql://wtc:wtc_password@database:5432/water_treatment
```

### Check Network Connectivity

```bash
# From API container to database
docker exec wtc-api ping -c 3 database
# Should succeed

# Check DNS resolution
docker exec wtc-api nslookup database
# Should resolve to database container IP
```

---

## Container Logs

### API Logs

```bash
# Full logs
docker logs wtc-api

# Follow logs
docker logs -f wtc-api

# Last 50 lines
docker logs wtc-api --tail 50

# Show timestamps
docker logs -t wtc-api
```

### Database Logs

```bash
docker logs wtc-database | grep -i error
docker logs wtc-database | grep -i fatal
docker logs wtc-database | grep "init.sql"
```

### All Services

```bash
docker compose logs -f --tail 100
```

---

## Health Check Endpoints

### API Health

```bash
curl http://localhost:8000/health | jq
# Should show all subsystems "ok"
```

### Database Health

```bash
curl http://localhost:8000/health | jq '.subsystems.database'
# Should show: {"status": "ok", "latency_ms": <number>}
```

### Grafana Health

```bash
curl http://localhost:3000/api/health | jq
```

---

## Environment Variables

### Required for API

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://wtc:wtc_password@database:5432/water_treatment` | Full connection string |
| `WTC_API_PORT` | `8000` | API port |
| `WTC_LOG_LEVEL` | `INFO` | Logging level |

### Alternative: Component Variables

Instead of `DATABASE_URL`, you can use:

```bash
WTC_DB_HOST=database
WTC_DB_PORT=5432
WTC_DB_USER=wtc
WTC_DB_PASSWORD=wtc_password
WTC_DB_NAME=water_treatment
```

The API will construct the URL from these.

---

## Complete Reset

If everything is broken, start fresh:

```bash
# Stop and remove everything
docker compose down -v

# Remove all containers
docker rm -f $(docker ps -aq --filter "name=wtc")

# Remove volumes
docker volume rm $(docker volume ls -q --filter "name=water-controller")

# Clean build cache
docker builder prune -af

# Start fresh
docker compose up -d --build

# Wait for startup
sleep 30

# Initialize database
./scripts/fix-database-auth.sh

# Validate
./scripts/validate-deployment.sh
```

---

## Production Deployment Notes

### Security

1. **Change Default Passwords:**
   ```bash
   docker exec wtc-database psql -U wtc -d water_treatment
   \password admin
   ```

2. **Use Environment Variables for Secrets:**
   ```bash
   # Never commit passwords to git
   echo "wtc_password" > .secrets/db_password
   chmod 600 .secrets/db_password
   ```

3. **Enable TLS:**
   Use nginx or Caddy as reverse proxy with Let's Encrypt.

### Performance

1. **TimescaleDB Tuning:**
   ```sql
   -- Set retention policy
   SELECT add_retention_policy('historian_data', INTERVAL '90 days');

   -- Add continuous aggregates
   CREATE MATERIALIZED VIEW historian_hourly ...
   ```

2. **Connection Pooling:**
   Adjust SQLAlchemy pool settings in `web/api/app/models/base.py`.

### Monitoring

1. **Enable Prometheus Metrics:**
   ```bash
   curl http://localhost:8000/metrics
   ```

2. **Set up Grafana Dashboards:**
   Import dashboards from `docker/grafana/provisioning/dashboards/`.

3. **Configure Alerting:**
   Set up alert rules in `docker/grafana/provisioning/alerting/`.

---

## Getting Help

If issues persist:

1. Run validation: `./scripts/validate-deployment.sh`
2. Collect logs: `docker compose logs > deployment-logs.txt`
3. Check database: `docker exec wtc-database psql -U wtc -d water_treatment -c "\dt"`
4. Report issue: https://github.com/mwilco03/Water-Controller/issues

Include:
- Output of validation script
- Relevant container logs
- Docker version: `docker --version`
- OS: `uname -a`

---

**Last Updated:** 2026-01-17
