# Quick Reference

One-page operational reference for Water-Controller.

---

## Installation

```bash
# Fresh install
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | sudo bash -s -- fresh

# Uninstall
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | sudo bash -s -- wipe

# Reinstall (preserves config)
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | sudo bash -s -- reinstall
```

---

## Service Commands

```bash
# Status
sudo systemctl status water-controller water-controller-api water-controller-ui

# Restart all
sudo systemctl restart water-controller water-controller-api water-controller-ui

# Logs
sudo journalctl -fu water-controller
sudo journalctl -fu water-controller-api

# Docker
docker compose up -d          # Start
docker compose down           # Stop
docker compose logs -f api    # Logs
```

---

## Network Ports

| Port | Service | Protocol |
|------|---------|----------|
| 8000 | API | HTTP/WS |
| 8080 | HMI | HTTP |
| 1502 | Modbus | TCP |
| 3000 | Grafana | HTTP |
| 5432 | PostgreSQL | Internal |
| 34962-34964 | PROFINET | RT |

---

## API Endpoints

```bash
# Health check
curl http://localhost:8000/api/v1/health

# List RTUs
curl http://localhost:8000/api/v1/rtus

# Get RTU sensors
curl http://localhost:8000/api/v1/rtus/{name}/sensors

# Command actuator
curl -X POST http://localhost:8000/api/v1/rtus/{name}/actuators/{slot} \
  -H "Content-Type: application/json" \
  -d '{"command": "ON"}'

# Active alarms
curl http://localhost:8000/api/v1/alarms

# API docs
open http://localhost:8000/docs
```

---

## Data Quality Codes

| Code | Meaning | HMI Display |
|------|---------|-------------|
| GOOD (0x00) | Valid, fresh | Normal |
| UNCERTAIN (0x40) | May be stale | Yellow |
| BAD (0x80) | Sensor failure | Red + X |
| NOT_CONNECTED (0xC0) | Comm loss | Grey + ? |

---

## Alarm Severity (ISA-18.2)

| Level | Response Time | Action |
|-------|---------------|--------|
| EMERGENCY | Immediate | Evacuate/shutdown |
| HIGH | < 10 min | Correct immediately |
| MEDIUM | < 30 min | Correct soon |
| LOW | < shift end | Awareness |

---

## Troubleshooting

```bash
# Check process
pgrep -a water_controller

# Check shared memory
ls -la /dev/shm/water_controller*

# Database connection
docker exec -it wtc-db psql -U wtc -d water_treatment -c "SELECT 1"

# PROFINET interface
ip link show eth0
sudo tcpdump -i eth0 -n ether proto 0x8892

# API errors
docker compose logs api --tail=100
```

---

## Database Credentials

```
Host: localhost (or wtc-db in Docker)
Port: 5432
Database: water_treatment
User: wtc
Password: wtc_password
```

---

## Common Issues

| Symptom | Check | Fix |
|---------|-------|-----|
| HMI blank | API running? | `systemctl restart water-controller-api` |
| RTU offline | Network? | `ping <rtu-ip>`, check cables |
| No data | Controller? | `systemctl status water-controller` |
| Alarms stuck | DB? | Check PostgreSQL connection |
| Slow trends | TimescaleDB? | Check compression policy |

---

## File Locations

```
/opt/water-controller/          # Installation
/etc/water-controller/          # Configuration
/var/log/water-controller/      # Logs
/var/lib/water-controller/      # Data
```

Docker:
```
/home/user/Water-Controller/docker/docker-compose.yml
/home/user/Water-Controller/config/
```

---

## Build Commands

```bash
make build          # Build controller
make test           # Run tests
make validate       # Validate schemas
make generate       # Generate from schemas
make generate-docs  # Generate config docs
```

---

## Emergency Procedures

**RTU Communication Loss:**
1. Check physical network
2. Verify RTU power
3. Check PROFINET interface: `ip link show eth0`
4. Restart controller: `systemctl restart water-controller`

**Database Unavailable:**
1. Check PostgreSQL: `docker ps | grep db`
2. Check disk space: `df -h`
3. Restart: `docker compose restart db`

**Complete System Recovery:**
```bash
# Backup current state
./scripts/backup.sh

# Reinstall
curl -fsSL .../bootstrap.sh | sudo bash -s -- reinstall
```

---

See [INDEX.md](INDEX.md) for complete documentation.
