<!--
  DOCUMENT CLASS: Guide (Living Document)

  This document contains DIAGNOSTIC PROCEDURES.
  Update when new error conditions are identified or fixes change.
-->

# Water Treatment Controller - Troubleshooting Guide

**Document ID:** WT-MAINT-001
**Version:** 1.0.0
**Last Updated:** 2024-12-22

---

## Quick Diagnostic Commands

```bash
# System health check
curl http://localhost:8000/health

# Service status
sudo systemctl status water-controller water-controller-api water-controller-ui

# View logs (last 100 lines)
sudo journalctl -u water-controller -n 100

# Real-time log monitoring
sudo journalctl -u water-controller -f

# Network interfaces
ip addr show

# PROFINET and service ports
sudo netstat -tulnp | grep -E ':(34962|34963|34964|8000|8080|502)'

# Process check
pgrep -a water_treat
```

---

## Common Issues and Solutions

### 1. Controller Service Issues

#### Controller Won't Start

**Symptoms:**
- `systemctl status water-controller` shows "failed"
- No process visible with `pgrep water_treat`

**Diagnostic Steps:**

```bash
# Check for error messages
sudo journalctl -u water-controller --no-pager | tail -50

# Verify binary exists and is executable
ls -la /opt/water-controller/bin/water_treat_controller

# Check library dependencies
ldd /opt/water-controller/bin/water_treat_controller

# Verify config file syntax
cat /etc/water-controller/controller.conf
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Missing shared libraries | Run `sudo ldconfig` or reinstall |
| Config file syntax error | Check for typos, especially in interface name |
| Network interface not found | Verify interface exists with `ip link show` |
| Port already in use | Check `netstat -tlnp` for conflicts |
| Permissions issue | Check user `wtc` owns required directories |
| Corrupted binary | Rebuild or reinstall from package |

**Permission Fix:**
```bash
sudo chown -R wtc:wtc /var/lib/water-controller /var/log/water-controller
sudo chmod 755 /opt/water-controller/bin/water_treat_controller
```

#### Controller Starts Then Crashes

**Symptoms:**
- Service starts but dies within seconds
- Repeated restart attempts visible in journalctl

**Diagnostic Steps:**

```bash
# Look for segfault or error
sudo dmesg | grep -i water

# Check for core dump
ls -la /var/crash/ 2>/dev/null || ls -la /tmp/core* 2>/dev/null

# Run manually with debug logging
sudo -u wtc /opt/water-controller/bin/water_treat_controller \
  -c /etc/water-controller/controller.conf \
  -l DEBUG
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Raw socket permission | Add CAP_NET_RAW capability or run as root |
| Memory exhaustion | Check `free -m`, increase swap if needed |
| Database corruption | Restore from backup or reinitialize |
| Infinite loop in config | Simplify config, add RTUs one at a time |

---

### 2. PROFINET Communication Issues

#### RTU Not Discovered

**Symptoms:**
- RTU not appearing in device list
- DCP scan returns empty results

**Diagnostic Steps:**

```bash
# Verify network interface
ip addr show eth0  # Replace with your interface

# Check for PROFINET traffic
sudo tcpdump -i eth0 -n port 34964 -c 10

# Verify multicast routing
ip mroute show

# Check firewall
sudo iptables -L -n
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Wrong interface configured | Update `interface` in controller.conf |
| RTU not powered | Verify RTU power and status LEDs |
| RTU on different VLAN | Ensure same Layer 2 network |
| Firewall blocking multicast | Allow UDP ports 34962-34964 |
| Network switch issue | Try direct cable connection |
| RTU in wrong mode | Check RTU configuration |

**Firewall Rules:**
```bash
sudo iptables -A INPUT -p udp --dport 34962:34964 -j ACCEPT
sudo iptables -A INPUT -p udp -d 224.0.0.0/4 -j ACCEPT
```

#### AR (Application Relationship) Not Establishing

**Symptoms:**
- RTU discovered but connection fails
- State stuck at "CONNECTING"

**Diagnostic Steps:**

```bash
# Capture PROFINET negotiation
sudo tcpdump -i eth0 -w /tmp/profinet.pcap -n \
  'udp port 34962 or udp port 34963 or udp port 34964'

# Open in Wireshark with PROFINET dissector
wireshark /tmp/profinet.pcap
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Station name mismatch | Verify station_name matches RTU config |
| Vendor/Device ID mismatch | Check GSDML matches RTU firmware |
| Slot configuration wrong | Verify slot count and types |
| RTU already connected | Only one controller can connect to RTU |
| Timing issues | Increase connection timeout |

#### Cyclic Data Not Updating

**Symptoms:**
- Connection shows "RUNNING"
- Sensor values frozen or always zero
- Quality showing NOT_CONNECTED

**Diagnostic Steps:**

```bash
# Check API for sensor data
curl http://localhost:8000/api/v1/rtus/{station_name}/sensors

# Monitor in real-time
watch -n 1 'curl -s http://localhost:8000/api/v1/rtus/{station_name}/sensors | jq'

# Check system health
curl http://localhost:8000/health | jq
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| IOPS = BAD | RTU submodule has error - check RTU logs |
| Slot misconfiguration | Verify slot assignments match RTU |
| Byte order issue | Check big-endian float interpretation |
| Network packet loss | Check switch, cables, reduce cycle time |

---

### 3. API/Web Interface Issues

#### API Not Responding (Port 8000)

**Symptoms:**
- `curl http://localhost:8000/health` fails
- Web UI shows "Connection Error"

**Diagnostic Steps:**

```bash
# Check service
sudo systemctl status water-controller-api

# Check port binding
sudo netstat -tlnp | grep 8000

# Check Python environment
/opt/water-controller/venv/bin/python --version

# View API logs
sudo journalctl -u water-controller-api -n 50
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Service not started | `sudo systemctl start water-controller-api` |
| Python venv missing | Recreate with `python3 -m venv venv` |
| Missing dependencies | `pip install -r requirements.txt` |
| Port conflict | Change port in config or stop conflicting service |
| Shared memory not available | Start controller first |

#### Web UI Not Loading (Port 8080)

**Symptoms:**
- Browser shows connection refused on port 8080
- API works but UI doesn't

**Diagnostic Steps:**

```bash
# Check service
sudo systemctl status water-controller-ui

# Check Node.js
node --version

# Check if built
ls -la /opt/water-controller/web/ui/.next/

# View UI logs
sudo journalctl -u water-controller-ui -n 50
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Not built | Run `npm run build` in web/ui directory |
| Node.js too old | Install Node.js 18+ |
| Missing node_modules | Run `npm install` |
| Port conflict | Change port or stop conflicting service |

#### WebSocket Connection Failing

**Symptoms:**
- Real-time updates not working
- Console shows WebSocket errors
- Sensors update only on page refresh

**Diagnostic Steps:**

```bash
# Test WebSocket with wscat
npm install -g wscat
wscat -c ws://localhost:8000/ws

# Check for proxy interference
curl -v http://localhost:8000/ws
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Reverse proxy blocking | Configure proxy for WebSocket upgrade |
| CORS issue | Check CORS settings in main.py |
| Firewall | Allow WebSocket connections |

---

### 4. Modbus Gateway Issues

#### Modbus TCP Not Responding (Port 502)

**Symptoms:**
- External SCADA can't connect
- `nc -zv localhost 502` fails

**Diagnostic Steps:**

```bash
# Check service
sudo systemctl status water-controller-modbus

# Check port
sudo netstat -tlnp | grep 502

# Test locally
modpoll -m tcp -t 4 -r 1 -c 10 localhost
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Service not running | Start modbus service |
| Port requires root | Run on port > 1024 or use setcap |
| Firewall | Allow port 502 |
| No mappings configured | Add register mappings via API |

**Port Capability (to run on 502 without root):**
```bash
sudo setcap 'cap_net_bind_service=+ep' /opt/water-controller/bin/water_treat_controller
```

#### Wrong Values in Modbus Registers

**Symptoms:**
- SCADA shows unexpected values
- Values don't match HMI display

**Diagnostic Steps:**

```bash
# Check mapping configuration
curl http://localhost:8000/api/v1/modbus/mappings | jq

# Verify register directly
modpoll -m tcp -t 4:float -r 100 -c 1 localhost
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Wrong data type | Check FLOAT32 vs INT16 mapping |
| Byte order | Configure byte/word swap for your device |
| Scaling error | Verify scale factors in mapping |
| Wrong address | Check 0-based vs 1-based addressing |

---

### 5. Database/Historian Issues

#### Historian Not Recording Data

**Symptoms:**
- Trends show no data
- Historian stats show 0 records

**Diagnostic Steps:**

```bash
# Check PostgreSQL
sudo systemctl status postgresql
psql -U wtc -d water_controller -c "SELECT COUNT(*) FROM historian_data;"

# Check SQLite (fallback)
sqlite3 /var/lib/water-controller/controller.db "SELECT COUNT(*) FROM historian_data;"

# Check tag configuration
curl http://localhost:8000/api/v1/trends/tags | jq
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| No tags configured | Create historian tags via API |
| Database not initialized | Run init.sql script |
| Disk full | Free up space, archive old data |
| PostgreSQL not running | Start PostgreSQL service |
| Connection string wrong | Check DATABASE_URL environment variable |

#### High Disk Usage from Historian

**Symptoms:**
- Disk filling up quickly
- `/var/lib/water-controller` very large

**Solutions:**

```bash
# Check historian size
du -sh /var/lib/water-controller/

# Archive old data (PostgreSQL)
psql -U wtc -d water_controller -c "
  DELETE FROM historian_data
  WHERE time < NOW() - INTERVAL '30 days';
"

# Vacuum to reclaim space
psql -U wtc -d water_controller -c "VACUUM FULL historian_data;"

# Adjust retention in config
# historian.retention_days = 30
```

---

### 6. Authentication Issues

#### Can't Log In

**Symptoms:**
- Login fails with "Invalid credentials"
- 401 errors from API

**Diagnostic Steps:**

```bash
# Check if auth is enabled
grep AUTH /etc/water-controller/environment

# Test with auth disabled temporarily
export WTC_AUTH_ENABLED=false
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Wrong password | Reset password in database |
| Session expired | Log in again |
| AD connection failed | Check AD server connectivity |
| Clock skew | Sync system time with NTP |

**Reset Local User Password:**
```bash
# Generate new password hash
python3 -c "from passlib.hash import bcrypt; print(bcrypt.hash('newpassword'))"

# Update in database
sqlite3 /var/lib/water-controller/controller.db "
  UPDATE users SET password_hash='...' WHERE username='admin';
"
```

#### Active Directory Integration Failing

**Symptoms:**
- AD users can't log in
- Local users work fine

**Diagnostic Steps:**

```bash
# Test LDAP connectivity
ldapsearch -H ldap://your-ad-server -x -b "dc=example,dc=com" "(sAMAccountName=testuser)"

# Check AD config
curl http://localhost:8000/api/v1/auth/ad-config
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Wrong server address | Verify AD server IP/hostname |
| Wrong bind credentials | Check service account password |
| SSL certificate issue | Import AD CA certificate |
| Firewall blocking | Allow ports 389/636 to AD server |

---

### 7. Performance Issues

#### High CPU Usage

**Symptoms:**
- Controller using > 80% CPU
- System sluggish

**Diagnostic Steps:**

```bash
# Check process CPU
top -p $(pgrep water_treat)

# Check system health
curl http://localhost:8000/health | jq

# Profile (if compiled with debug)
perf top -p $(pgrep water_treat)
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Cycle time too fast | Increase to 1000ms+ |
| Too many RTUs | Reduce connected RTU count |
| PID loop instability | Check tuning parameters |
| Historian sampling too fast | Increase sample rate |
| Excessive logging | Set log level to INFO or WARN |

#### High Memory Usage

**Symptoms:**
- OOM killer terminating processes
- Swap usage high

**Diagnostic Steps:**

```bash
# Check memory
free -m
ps aux --sort=-%mem | head

# Check historian cache
curl http://localhost:8000/api/v1/trends/stats | jq
```

**Solutions:**

- Reduce historian retention
- Disable unused features
- Add swap space
- Upgrade RAM

---

### 8. Network Issues

#### Cannot Reach Controller from Remote Machine

**Diagnostic Steps:**

```bash
# From remote machine
ping <controller-ip>
nc -zv <controller-ip> 8000
curl http://<controller-ip>:8000/api/v1/system/health

# On controller
sudo iptables -L -n
ip route show
```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Firewall blocking | Open ports 8000, 8080 |
| Binding to localhost only | Configure to bind 0.0.0.0 |
| Wrong network/subnet | Check IP configuration |
| No route to host | Verify routing and gateway |

---

## Log Analysis

### Important Log Patterns

```bash
# Find errors
sudo journalctl -u water-controller | grep -i error

# Find warnings
sudo journalctl -u water-controller | grep -i warn

# Find connection issues
sudo journalctl -u water-controller | grep -i "disconnect\|timeout\|failed"

# Find performance issues
sudo journalctl -u water-controller | grep -i "cycle\|overrun"
```

### Log Levels

Configure in `/etc/water-controller/controller.conf`:

| Level | Use Case |
|-------|----------|
| ERROR | Production - errors only |
| WARN | Production - errors and warnings |
| INFO | Normal operation (default) |
| DEBUG | Troubleshooting - verbose |
| TRACE | Development - very verbose |

---

## Recovery Procedures

### Emergency Recovery from Backup

```bash
# Stop services
sudo systemctl stop water-controller water-controller-api water-controller-ui

# Restore configuration
sudo wtc-ctl restore /var/lib/water-controller/backups/wtc_backup_YYYYMMDD.tar.gz

# Start services
sudo systemctl start water-controller
```

### Factory Reset (Last Resort)

```bash
# Stop services
sudo systemctl stop water-controller water-controller-api water-controller-ui

# Backup current config (just in case)
sudo cp -r /etc/water-controller /etc/water-controller.bak
sudo cp -r /var/lib/water-controller /var/lib/water-controller.bak

# Remove data
sudo rm -rf /var/lib/water-controller/*
sudo rm /etc/water-controller/*.conf

# Reinstall
cd /path/to/Water-Controller
sudo ./scripts/install.sh

# Reconfigure from scratch
```

---

## Getting Help

If you cannot resolve the issue:

1. Collect diagnostics:
   ```bash
   sudo ./scripts/collect-diagnostics.sh > diagnostics.tar.gz
   ```

2. Include in support request:
   - System information (OS, architecture)
   - Error messages from logs
   - Steps to reproduce
   - Diagnostics package

3. Contact:
   - GitHub Issues: https://github.com/mwilco03/Water-Controller/issues

---

*This troubleshooting guide covers common issues. For complex problems, consult the development team or create a GitHub issue with detailed diagnostics.*
