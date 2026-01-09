<!--
  DOCUMENT CLASS: Runbook (Living Document)

  This document contains OPERATIONAL PROCEDURES for system administration.
  Update when procedures change, new failure modes are identified,
  or operational best practices evolve.

  Related documents:
  - OPERATOR.md: End-user HMI guidance
  - TROUBLESHOOTING_GUIDE.md: Diagnostic procedures
  - DEPLOYMENT.md: Installation and configuration
-->

# Water Treatment Controller - Operations Runbook

**Document ID:** WT-OPS-001
**Version:** 1.0.0
**Last Updated:** 2025-01-09

---

## Quick Reference

### Essential Commands

```bash
# System Status
docker compose ps                              # Container status
curl http://localhost:8000/health              # API health
sudo systemctl status water-controller*        # Native service status

# Logs (last 5 minutes)
docker compose logs --since 5m                 # Docker
sudo journalctl -u water-controller --since "5 min ago"  # Native

# Emergency Stop
docker compose stop                            # Graceful (Docker)
sudo systemctl stop water-controller           # Graceful (Native)

# Restart All Services
docker compose restart                         # Docker
sudo systemctl restart water-controller        # Native
```

### Health Check URLs

| Endpoint | Expected Response | Meaning |
|----------|------------------|---------|
| `http://localhost:8000/health` | `{"status": "healthy"}` | API operational |
| `http://localhost:8000/api/v1/rtus` | JSON array | RTU list available |
| `http://localhost:8080` | HTML page | Web UI operational |
| `http://localhost:3000/api/health` (Grafana) | `{"database": "ok"}` | Monitoring operational |

---

## 1. Daily Operations

### 1.1 Shift Handover Checklist

Perform at the start of each operator shift:

- [ ] **Check Dashboard**: Open HMI at `http://<controller-ip>:8080`
  - All RTUs showing CONNECTED (green indicator)?
  - No EMERGENCY or HIGH priority alarms?
  - System status indicator green?

- [ ] **Review Active Alarms**: Navigate to Alarms page
  - Note any unacknowledged alarms
  - Review alarms from previous shift
  - Check for patterns (repeated alarms)

- [ ] **Verify Data Quality**: Check sensor displays
  - Any sensors showing BAD or NOT_CONNECTED quality?
  - Any sensors showing stale data (yellow ⚠)?

- [ ] **Check System Health**:
  ```bash
  curl -s http://localhost:8000/health | jq
  ```
  Expected: All components show "healthy"

- [ ] **Review Recent Events**:
  ```bash
  docker compose logs --since 8h api | grep -E "ERROR|WARN" | tail -20
  ```

- [ ] **Confirm Historian Recording**:
  ```bash
  curl -s http://localhost:8000/api/v1/trends/stats | jq '.sample_count_24h'
  ```
  Should be increasing steadily

### 1.2 Routine Monitoring

Every 4 hours, or as needed:

```bash
# Quick health check
curl -s http://localhost:8000/health | jq '.components'

# RTU connectivity
curl -s http://localhost:8000/api/v1/rtus | jq '.[] | {name: .station_name, state: .state}'

# Active alarm count
curl -s http://localhost:8000/api/v1/alarms/active | jq 'length'

# System resources
docker stats --no-stream
```

### 1.3 Acknowledging Alarms

#### Via HMI

1. Navigate to Alarms page
2. Click **Acknowledge** on the alarm
3. Optionally add a note explaining the response

#### Via API

```bash
# Acknowledge specific alarm
curl -X POST http://localhost:8000/api/v1/alarms/{alarm_id}/acknowledge \
  -H "Content-Type: application/json" \
  -d '{"operator": "jsmith", "comment": "Valve manual check completed"}'

# Acknowledge all active alarms (use with caution)
curl -X POST http://localhost:8000/api/v1/alarms/acknowledge-all \
  -H "Content-Type: application/json" \
  -d '{"operator": "jsmith", "comment": "Shift handover acknowledgment"}'
```

---

## 2. Startup Procedures

### 2.1 Cold Start (Full System Restart)

Use this procedure after power outage, maintenance, or system recovery.

**Pre-Start Checklist:**

- [ ] Verify network connectivity to RTUs
- [ ] Confirm database server is accessible (if external)
- [ ] Check available disk space: `df -h`
- [ ] Review any pending configuration changes

**Startup Sequence (Docker):**

```bash
cd /opt/water-controller/docker

# 1. Start database first
docker compose up -d database
sleep 10

# 2. Verify database health
docker compose exec database pg_isready -U wtc
# Expected: accepting connections

# 3. Start remaining services
docker compose up -d

# 4. Wait for initialization (60-90 seconds)
sleep 60

# 5. Verify all containers healthy
docker compose ps
# All should show "healthy" status

# 6. Check API health
curl http://localhost:8000/health
```

**Startup Sequence (Native):**

```bash
# 1. Ensure PostgreSQL is running
sudo systemctl start postgresql
sudo systemctl status postgresql

# 2. Start controller service
sudo systemctl start water-controller
sleep 30

# 3. Start API service
sudo systemctl start water-controller-api
sleep 10

# 4. Start UI service
sudo systemctl start water-controller-ui

# 5. Verify all services
sudo systemctl status water-controller water-controller-api water-controller-ui
```

**Post-Start Verification:**

```bash
# Check all RTUs connected
curl -s http://localhost:8000/api/v1/rtus | jq '.[] | {name: .station_name, state: .state}'

# Verify no startup alarms
curl -s http://localhost:8000/api/v1/alarms/active | jq 'length'

# Check historian is recording
curl -s http://localhost:8000/api/v1/trends/stats | jq '.last_sample_time'

# Monitor initial logs for errors
docker compose logs -f --since 2m  # Watch for 2-3 minutes
```

**Expected Startup Timeline:**

| Time | Event |
|------|-------|
| 0-10s | Database container starts |
| 10-30s | API container starts, connects to database |
| 30-60s | Controller initializes PROFINET stack |
| 60-90s | RTU discovery and AR establishment |
| 90-120s | Full cyclic data exchange |

### 2.2 Warm Start (Service Restart Only)

Use when restarting services without full system reboot:

```bash
# Docker
docker compose restart

# Native
sudo systemctl restart water-controller water-controller-api water-controller-ui

# Verify within 60 seconds
curl http://localhost:8000/health
```

### 2.3 RTU-Only Restart

If an individual RTU needs restart (power cycle, firmware update):

1. **Before RTU restart:**
   ```bash
   # Note current RTU state
   curl -s http://localhost:8000/api/v1/rtus/{station_name} | jq
   ```

2. **During RTU restart:**
   - Controller will show RTU as OFFLINE
   - Communication alarms will activate
   - Historian will record quality = NOT_CONNECTED

3. **After RTU comes back:**
   - Controller automatically reconnects (within 30-60 seconds)
   - Alarms auto-clear when communication restored
   - Verify data quality returns to GOOD

---

## 3. Shutdown Procedures

### 3.1 Planned Maintenance Shutdown

Use for scheduled maintenance windows:

```bash
# 1. Notify operators via system announcement
curl -X POST http://localhost:8000/api/v1/system/announcement \
  -H "Content-Type: application/json" \
  -d '{"message": "System shutdown for maintenance in 5 minutes", "severity": "warning"}'

# 2. Wait for operator acknowledgment

# 3. Create pre-shutdown backup
docker compose exec database pg_dump -U wtc water_treatment > /var/backups/pre-maintenance.sql

# 4. Graceful shutdown (allows pending writes to complete)
docker compose stop

# 5. Verify all containers stopped
docker compose ps
```

### 3.2 Emergency Shutdown

Use only when immediate stop is required:

```bash
# Immediate stop (Docker)
docker compose down

# Immediate stop (Native)
sudo systemctl stop water-controller water-controller-api water-controller-ui
```

**After emergency shutdown:**
- RTUs will detect communication loss within 3 cycles
- RTUs enter safe state (configurable per RTU)
- Local interlocks remain active on RTUs
- No data loss for committed historian records

### 3.3 Controlled Power Down

Before planned power outage:

```bash
# 1. Graceful shutdown
docker compose stop

# 2. Wait for container exit
docker compose ps  # Should show all "Exited"

# 3. Stop Docker daemon
sudo systemctl stop docker

# 4. Sync filesystem
sync

# 5. Power down
sudo poweroff
```

---

## 4. Health Monitoring

### 4.1 Key Metrics to Monitor

| Metric | Normal Range | Warning | Critical |
|--------|-------------|---------|----------|
| API response time | <100ms | >500ms | >2000ms |
| RTU cycle time | ≤configured | +10% | +50% |
| Active alarms | <10 | 10-50 | >50 |
| Memory usage | <70% | 70-85% | >85% |
| Disk usage | <70% | 70-85% | >85% |
| Database connections | <pool_size | =pool_size | Errors |
| WebSocket connections | <100 | 100-200 | >200 |

### 4.2 Automated Health Check Script

Create as `/opt/water-controller/scripts/health-check.sh`:

```bash
#!/bin/bash
set -e

API_URL="http://localhost:8000"
ALERT_EMAIL="ops@example.com"

# Check API health
api_status=$(curl -sf "${API_URL}/health" | jq -r '.status' 2>/dev/null || echo "failed")
if [ "$api_status" != "healthy" ]; then
    echo "CRITICAL: API health check failed" | mail -s "WTC Alert" $ALERT_EMAIL
    exit 1
fi

# Check RTU connectivity
offline_rtus=$(curl -sf "${API_URL}/api/v1/rtus" | jq '[.[] | select(.state != "RUNNING")] | length' 2>/dev/null || echo "error")
if [ "$offline_rtus" != "0" ] && [ "$offline_rtus" != "error" ]; then
    echo "WARNING: $offline_rtus RTU(s) offline" | mail -s "WTC Warning" $ALERT_EMAIL
fi

# Check active alarms
alarm_count=$(curl -sf "${API_URL}/api/v1/alarms/active" | jq 'length' 2>/dev/null || echo "0")
if [ "$alarm_count" -gt 50 ]; then
    echo "WARNING: High alarm count ($alarm_count)" | mail -s "WTC Warning" $ALERT_EMAIL
fi

# Check disk space
disk_usage=$(df /var/lib | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$disk_usage" -gt 85 ]; then
    echo "WARNING: Disk usage at ${disk_usage}%" | mail -s "WTC Warning" $ALERT_EMAIL
fi

echo "Health check passed at $(date)"
```

Schedule with cron:

```bash
# Run every 5 minutes
*/5 * * * * /opt/water-controller/scripts/health-check.sh >> /var/log/water-controller/health-check.log 2>&1
```

### 4.3 Grafana Dashboard

Access Grafana at `http://localhost:3000` (default: admin/admin)

**Key Panels to Configure:**

1. **System Overview**
   - All RTU connection states
   - Active alarm count by severity
   - API response time

2. **PROFINET Health**
   - Cycle time histogram
   - Communication errors
   - RTU uptime percentage

3. **Historian Status**
   - Samples per minute
   - Storage growth rate
   - Compression ratio

4. **Resource Usage**
   - CPU per container
   - Memory per container
   - Network I/O

---

## 5. Scheduled Maintenance

### 5.1 Daily Tasks (Automated)

These should run via cron or systemd timers:

```bash
# Rotate logs (logrotate handles this)
# Historian sample compression (automatic)
# Backup verification (see 5.4)
```

### 5.2 Weekly Tasks

**Every Monday:**

1. **Review Alarm Statistics**
   ```bash
   curl -s http://localhost:8000/api/v1/alarms/statistics?period=7d | jq
   ```
   Look for:
   - Most frequent alarms (potential nuisance alarms)
   - Alarm floods (>10/min sustained)
   - Standing alarms (>24 hours active)

2. **Check Backup Completion**
   ```bash
   ls -la /var/backups/water-controller/
   # Verify daily backups present
   ```

3. **Review System Logs for Patterns**
   ```bash
   docker compose logs --since 168h | grep -E "ERROR|WARN" | sort | uniq -c | sort -rn | head -20
   ```

4. **Check Disk Space Trends**
   ```bash
   df -h /var/lib /var/log
   ```

### 5.3 Monthly Tasks

**First Monday of each month:**

1. **Full System Health Audit**
   - Compare current metrics to baseline
   - Review all configuration changes
   - Verify all RTUs discoverable

2. **Historian Maintenance**
   ```bash
   # Check compression effectiveness
   curl -s http://localhost:8000/api/v1/trends/stats | jq '.compression_ratio'

   # Verify retention policy applied
   curl -s http://localhost:8000/api/v1/trends/tags | jq '.[] | {tag: .name, oldest: .oldest_sample}'
   ```

3. **Security Review**
   - Audit user access logs
   - Review failed login attempts
   - Update service account passwords if required

4. **Update Documentation**
   - Document any operational changes
   - Update runbook if procedures changed
   - Record lessons learned

### 5.4 Quarterly Tasks

1. **Backup Restore Test**
   ```bash
   # Create test environment
   docker compose -f docker-compose.test.yml up -d

   # Restore latest backup
   cat /var/backups/water-controller/latest.sql | \
     docker compose -f docker-compose.test.yml exec -T database psql -U wtc water_treatment

   # Verify data integrity
   curl http://localhost:8001/api/v1/rtus | jq 'length'

   # Clean up test environment
   docker compose -f docker-compose.test.yml down -v
   ```

2. **Performance Baseline Update**
   - Record current response times
   - Document resource usage
   - Compare to previous quarter

3. **Disaster Recovery Drill**
   - Practice recovery procedure
   - Time full restoration
   - Document any gaps

---

## 6. Backup and Recovery

### 6.1 Backup Schedule

| Backup Type | Frequency | Retention | Location |
|-------------|-----------|-----------|----------|
| Configuration | Daily | 30 days | `/var/backups/water-controller/config/` |
| Database (full) | Daily | 14 days | `/var/backups/water-controller/db/` |
| Database (incremental) | Hourly | 24 hours | `/var/backups/water-controller/db/hourly/` |
| Historian archive | Weekly | 52 weeks | Remote storage |

### 6.2 Manual Backup

```bash
# Configuration backup
sudo tar -czf /var/backups/water-controller/config/wtc-config-$(date +%Y%m%d).tar.gz \
  /etc/water-controller /opt/water-controller/docker/*.yml

# Database backup
docker compose exec database pg_dump -U wtc water_treatment | \
  gzip > /var/backups/water-controller/db/wtc-db-$(date +%Y%m%d).sql.gz

# Full backup (config + database)
sudo wtc-ctl backup /var/backups/water-controller/full/wtc-full-$(date +%Y%m%d).tar.gz
```

### 6.3 Recovery Procedure

**Full Recovery from Backup:**

```bash
# 1. Stop all services
docker compose down

# 2. Restore database
gunzip -c /var/backups/water-controller/db/wtc-db-YYYYMMDD.sql.gz | \
  docker compose exec -T database psql -U wtc water_treatment

# 3. Restore configuration
sudo tar -xzf /var/backups/water-controller/config/wtc-config-YYYYMMDD.tar.gz -C /

# 4. Start services
docker compose up -d

# 5. Verify recovery
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/rtus | jq 'length'
```

**Point-in-Time Recovery:**

If using TimescaleDB continuous aggregates or PostgreSQL WAL archiving:

```bash
# Restore to specific timestamp
docker compose exec database psql -U wtc -c \
  "SELECT timescaledb_post_restore();"
```

---

## 7. Emergency Procedures

### 7.1 RTU Communication Loss

**Symptoms:**
- RTU shows OFFLINE in HMI
- Communication alarm active
- Sensor quality shows NOT_CONNECTED

**Immediate Actions:**

1. Check RTU physical status (power, network lights)
2. Ping RTU from controller:
   ```bash
   ping <rtu-ip-address>
   ```
3. Check controller logs:
   ```bash
   docker compose logs --since 5m controller | grep <station-name>
   ```

**If RTU unreachable:**
- Check network switch port status
- Verify cable connections
- Contact field technician for physical inspection

**If RTU reachable but not connecting:**
- Verify station name matches configuration
- Check for IP conflicts
- Restart controller service:
  ```bash
  docker compose restart controller
  ```

### 7.2 High Alarm Count (Alarm Flood)

**Symptoms:**
- >50 active alarms
- Operators overwhelmed
- HMI sluggish

**Immediate Actions:**

1. **Identify root cause:**
   ```bash
   curl -s http://localhost:8000/api/v1/alarms/active | \
     jq 'group_by(.source) | map({source: .[0].source, count: length}) | sort_by(-.count)'
   ```

2. **If single RTU causing flood:**
   - Check RTU connectivity
   - Shelve RTU alarms temporarily:
     ```bash
     curl -X POST http://localhost:8000/api/v1/alarms/shelve \
       -H "Content-Type: application/json" \
       -d '{"filter": {"source": "<rtu-name>"}, "duration_minutes": 60}'
     ```

3. **If process upset causing flood:**
   - Address process issue first
   - Document the event
   - Review alarm configuration post-incident

### 7.3 Database Connection Failure

**Symptoms:**
- API returns 500 errors
- Historian not recording
- Login failures

**Immediate Actions:**

1. **Check database container:**
   ```bash
   docker compose ps database
   docker compose logs --since 5m database
   ```

2. **Test database connectivity:**
   ```bash
   docker compose exec database pg_isready -U wtc
   ```

3. **If database unresponsive:**
   ```bash
   docker compose restart database
   sleep 30
   docker compose restart api
   ```

4. **If disk full:**
   ```bash
   # Check disk usage
   docker compose exec database df -h /var/lib/postgresql

   # Emergency cleanup (older historian data)
   docker compose exec database psql -U wtc -c \
     "DELETE FROM historian_data WHERE time < NOW() - INTERVAL '7 days';"
   docker compose exec database psql -U wtc -c "VACUUM FULL;"
   ```

### 7.4 Complete System Failure

**If controller becomes completely unresponsive:**

1. **RTUs continue safely:**
   - RTUs operate independently
   - Local interlocks remain active
   - Safe state maintained

2. **Recovery priority:**
   1. Database (preserve data)
   2. Controller (PROFINET communication)
   3. API (web access)
   4. UI (operator visibility)

3. **Full restart procedure:**
   ```bash
   # Force stop all containers
   docker compose down

   # Check for resource issues
   free -m
   df -h

   # Clean restart
   docker compose up -d
   ```

---

## 8. Integration Points

### 8.1 External SCADA via Modbus

**Testing Modbus connectivity:**

```bash
# Install modpoll if needed
apt install modpoll  # or brew install modpoll

# Read holding registers
modpoll -m tcp -t 4:float -r 100 -c 10 localhost

# Expected: Float values for first 10 mapped sensors
```

**Troubleshooting Modbus:**

```bash
# Check Modbus service
docker compose logs modbus

# Verify port listening
netstat -tlnp | grep 502

# Test TCP connection
nc -zv localhost 502
```

### 8.2 Log Forwarding (Loki/Grafana)

**Verify log ingestion:**

1. Access Grafana at `http://localhost:3000`
2. Navigate to Explore
3. Select Loki data source
4. Query: `{container_name=~"wtc-.*"}`

**If logs not appearing:**

```bash
# Check Promtail status
docker compose logs promtail

# Check Loki health
curl http://localhost:3100/ready

# Verify Promtail can read Docker logs
docker compose exec promtail cat /var/lib/docker/containers/*/*-json.log | head
```

### 8.3 Alerting Configuration

**Grafana Alerts (for ops team):**

1. Create alert rule in Grafana
2. Configure notification channel (email, Slack, PagerDuty)
3. Set alert thresholds based on operational requirements

**Example alert rules:**

| Alert | Condition | Severity |
|-------|-----------|----------|
| RTU Offline | state != RUNNING for 5 min | High |
| High Alarm Count | active_alarms > 50 | Medium |
| API Response Slow | response_time > 2s | Medium |
| Disk Space Low | usage > 85% | High |

---

## 9. Operational Escalation

### 9.1 Escalation Matrix

| Issue | First Response | Escalate After | Contact |
|-------|---------------|----------------|---------|
| RTU offline | Check network | 30 min | Field technician |
| HMI unavailable | Restart services | 15 min | System admin |
| Database error | Check logs | 15 min | DBA |
| Alarm flood | Identify root cause | 30 min | Process engineer |
| Security incident | Isolate system | Immediately | Security team |

### 9.2 On-Call Procedures

**When called:**

1. Acknowledge the alert
2. SSH to controller: `ssh ops@<controller-ip>`
3. Run quick health check:
   ```bash
   curl -s http://localhost:8000/health | jq
   docker compose ps
   ```
4. Check recent logs:
   ```bash
   docker compose logs --since 10m | grep -E "ERROR|CRITICAL"
   ```
5. Follow appropriate emergency procedure
6. Document incident and resolution

**Post-Incident:**

1. Complete incident report
2. Update runbook if needed
3. Schedule post-mortem if significant

---

## 10. Appendix

### A. Common API Endpoints

```bash
# System
GET  /health                          # Health check
GET  /api/v1/system/info              # System information
GET  /api/v1/system/diagnostics       # Detailed diagnostics

# RTUs
GET  /api/v1/rtus                     # List all RTUs
GET  /api/v1/rtus/{name}              # Single RTU details
GET  /api/v1/rtus/{name}/sensors      # RTU sensor values

# Alarms
GET  /api/v1/alarms/active            # Active alarms
POST /api/v1/alarms/{id}/acknowledge  # Acknowledge alarm
GET  /api/v1/alarms/statistics        # Alarm statistics

# Historian
GET  /api/v1/trends/tags              # Available tags
GET  /api/v1/trends/stats             # Historian statistics
GET  /api/v1/trends/{tag}?start=&end= # Historical data
```

### B. Log Locations

| Service | Docker | Native |
|---------|--------|--------|
| Controller | `docker compose logs controller` | `/var/log/water-controller/controller.log` |
| API | `docker compose logs api` | `journalctl -u water-controller-api` |
| UI | `docker compose logs ui` | `journalctl -u water-controller-ui` |
| Database | `docker compose logs database` | `/var/log/postgresql/` |

### C. Configuration File Locations

| File | Purpose |
|------|---------|
| `/etc/water-controller/controller.conf` | Main controller configuration |
| `/etc/water-controller/profinet.conf` | PROFINET network settings |
| `/etc/water-controller/rtus/*.conf` | Per-RTU configuration |
| `/etc/water-controller/alarms/*.json` | Alarm rules |
| `docker/docker-compose.yml` | Container configuration |
| `config/ports.env` | Port assignments |

### D. Quick Diagnostic Commands

```bash
# One-liner health check
curl -sf http://localhost:8000/health && echo "OK" || echo "FAILED"

# Count RTUs by state
curl -s http://localhost:8000/api/v1/rtus | jq 'group_by(.state) | map({state: .[0].state, count: length})'

# Recent errors
docker compose logs --since 1h 2>&1 | grep -c ERROR

# Database size
docker compose exec database psql -U wtc -c "SELECT pg_size_pretty(pg_database_size('water_treatment'));"

# Active connections
docker compose exec database psql -U wtc -c "SELECT count(*) FROM pg_stat_activity;"
```

---

*This runbook is a living document. Update it whenever procedures change or new operational patterns emerge. Last reviewed: 2025-01-09*
