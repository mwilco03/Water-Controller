# Water Treatment Controller - Deployment Guide

This guide covers installation, configuration, and deployment of the Water Treatment Controller system.

## Table of Contents

1. [Deployment Philosophy](#deployment-philosophy)
2. [System Requirements](#system-requirements)
3. [Pre-Deployment Checklist](#pre-deployment-checklist)
4. [Quick Installation](#quick-installation)
5. [Manual Installation](#manual-installation)
6. [Configuration](#configuration)
7. [Security Hardening](#security-hardening)
8. [SD Card Protection](#sd-card-protection)
9. [Service Management](#service-management)
10. [Backup and Restore](#backup-and-restore)
11. [Modbus Gateway](#modbus-gateway)
12. [Deployment Verification](#deployment-verification)
13. [Operational Handoff](#operational-handoff)
14. [Troubleshooting](#troubleshooting)
15. [Emergency Procedures](#emergency-procedures)
16. [Cross-Compilation](#cross-compilation)
17. [Board-Specific Installation](#board-specific-installation)

---

## Deployment Philosophy

This is critical infrastructure. Deployment errors can cause:
- Loss of process visibility (operator blindness)
- Environmental contamination (treatment failures)
- Equipment damage (uncontrolled actuators)
- Regulatory violations (audit trail gaps)

**Every configuration choice must answer: "What happens when this fails?"**

Key architectural principles:
- Two-plane architecture: controller commands flow THROUGH RTU, never direct to actuators
- RTUs maintain safe state during controller disconnect - this is by design
- Graceful degradation at every layer

---

## System Requirements

### Hardware

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | ARM Cortex-A53 or x86_64 | Multi-core |
| **RAM** | 2 GB | 4 GB (for historian workloads) |
| **Storage** | 32 GB SD card | Industrial-grade for write endurance |
| **Network** | Dedicated Ethernet for PROFINET | Secondary Ethernet for HMI/API |
| **RTC** | - | Battery backup (critical for historian) |
| **Power** | - | UPS or graceful shutdown capability |

### Software

- **OS**: Ubuntu 22.04/24.04 LTS, Debian 11+, or Raspberry Pi OS (64-bit)
- **Kernel**: Linux 4.19+ with PREEMPT_RT (recommended for real-time)
- **Python**: 3.9+
- **Node.js**: 18+ (for web UI)
- **CMake**: 3.16+
- **GCC**: 10+

### Dependencies

```bash
# Debian/Ubuntu
sudo apt update
sudo apt install -y \
    build-essential cmake pkg-config \
    libpq-dev libjson-c-dev \
    python3 python3-pip python3-venv \
    nodejs npm \
    postgresql redis-server nginx
```

---

## Pre-Deployment Checklist

### Hardware Verification

- [ ] Single Board Computer (Raspberry Pi 4/5, BeagleBone, or industrial SBC)
- [ ] Minimum 2GB RAM (4GB recommended for historian workloads)
- [ ] 32GB SD card (industrial-grade recommended for write endurance)
- [ ] Dedicated Ethernet interface for PROFINET (no shared traffic)
- [ ] Optional: Secondary Ethernet for HMI/API access
- [ ] Real-time clock with battery backup (critical for historian)
- [ ] UPS or graceful shutdown capability

### Network Requirements

- [ ] PROFINET network segment isolated from IT traffic
- [ ] Static IP addressing for controller and all RTUs
- [ ] Network time synchronization (NTP or PTP) configured
- [ ] Firewall rules defined for HMI access (port 3000, 8080)
- [ ] No DHCP on PROFINET segment

### Pre-Flight Checklist

- [ ] Target OS is Ubuntu 22.04/24.04 LTS or Raspberry Pi OS (64-bit)
- [ ] Root/sudo access available
- [ ] RTU devices powered and network-reachable
- [ ] Backup of any existing configuration exported
- [ ] Maintenance window scheduled with operations
- [ ] Rollback plan documented

---

## Quick Installation

The quickest way to install is using the installation script:

```bash
# Clone repository
git clone https://github.com/mwilco03/Water-Controller.git
cd Water-Controller

# Run installer (as root)
sudo ./scripts/install.sh
```

This will:
- Create service user `wtc`
- Build the controller binary
- Install Python and Node.js dependencies
- Set up systemd services
- Create default configuration

---

## Manual Installation

### Phase 1: System Preparation

```bash
# Update system packages (security baseline)
sudo apt update && sudo apt upgrade -y

# Configure system for real-time operation
echo 'net.core.rmem_max=16777216' | sudo tee -a /etc/sysctl.d/99-water-controller.conf
echo 'net.core.wmem_max=16777216' | sudo tee -a /etc/sysctl.d/99-water-controller.conf
sudo sysctl --system
```

### Phase 2: Build the Controller

```bash
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
```

### Phase 3: Install Files

```bash
# Create directories
sudo mkdir -p /opt/water-controller/{bin,lib,web}
sudo mkdir -p /etc/water-controller
sudo mkdir -p /var/lib/water-controller/{backups,historian}
sudo mkdir -p /var/log/water-controller

# Copy binaries
sudo cp build/water_treat_controller /opt/water-controller/bin/
sudo cp build/lib*.so /opt/water-controller/lib/

# Copy web files
sudo cp -r web /opt/water-controller/
```

### Phase 4: Create Service User

```bash
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin wtc
sudo usermod -a -G dialout wtc  # For serial port access
sudo chown -R wtc:wtc /var/lib/water-controller /var/log/water-controller
```

### Phase 5: Install Python Environment

```bash
cd /opt/water-controller
sudo python3 -m venv venv
sudo /opt/water-controller/venv/bin/pip install -r web/api/requirements.txt
```

### Phase 6: Install Node.js Dependencies

```bash
cd /opt/water-controller/web/ui
sudo npm install --production
sudo npm run build
```

### Phase 7: Database Initialization (Optional)

```bash
# Create PostgreSQL database and user
sudo -u postgres psql <<EOF
CREATE USER wtc WITH PASSWORD 'CHANGE_THIS_PASSWORD';
CREATE DATABASE water_controller OWNER wtc;
GRANT ALL PRIVILEGES ON DATABASE water_controller TO wtc;
\c water_controller
CREATE EXTENSION IF NOT EXISTS timescaledb;  -- Optional: for historian performance
EOF
```

### Phase 8: Install Systemd Services

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable water-controller water-controller-api water-controller-ui
```

---

## Configuration

### Configuration File Hierarchy

```
/etc/water-controller/
├── controller.conf          # Main controller configuration
├── profinet.conf            # PROFINET network settings
├── rtus/                    # Per-RTU configuration files
│   ├── tank-1.conf
│   ├── pump-station.conf
│   └── filter-1.conf
├── alarms/                  # Alarm rule definitions
│   ├── process-alarms.json
│   └── system-alarms.json
├── historian.conf           # Data retention and compression settings
├── modbus.conf              # Modbus gateway mappings (if enabled)
├── auth.conf                # Authentication settings (AD integration)
└── backup.conf              # Backup schedule and destinations
```

### Main Configuration File

Location: `/etc/water-controller/controller.conf`

```ini
[general]
station_name = "WTP-Controller-01"
log_level = INFO
log_retention_days = 90
cycle_time_ms = 1000

[profinet]
interface = eth0
station_name = wtc-controller
cycle_time_ms = 1000
watchdog_factor = 3
dcp_discovery_interval = 60

[database]
connection_string = postgresql://wtc:PASSWORD@localhost/water_controller
pool_size = 10
connection_timeout = 5

[redis]
url = redis://localhost:6379/0

[historian]
enabled = true
retention_days = 365
compression = swinging_door
compression_enabled = true
deadband_default = 0.5
flush_interval_seconds = 30

[alarms]
isa_18_2_compliant = true
max_active_alarms = 1000
alarm_rate_limit = 10

[modbus]
tcp_enabled = true
tcp_port = 502
rtu_enabled = false

[security]
session_timeout_minutes = 480
require_https = true
api_rate_limit = 100
```

### PROFINET Interface Configuration

Location: `/etc/water-controller/profinet.conf`

```ini
[network]
interface = eth0
mac_filter = true

[timing]
cycle_time_ms = 1000
reduction_ratio = 1
send_clock_factor = 1

[discovery]
dcp_enabled = true
dcp_interval_seconds = 60
auto_register_rtus = false

[failover]
connection_timeout_cycles = 3
reconnect_delay_ms = 5000
max_reconnect_attempts = 0
```

### RTU Registration

Location: `/etc/water-controller/rtus/tank-1.conf`

```ini
[identity]
station_name = "Tank-1"
ip_address = 192.168.1.100
mac_address = AA:BB:CC:DD:EE:01
vendor_id = 0x1234
device_id = 0x0001

[communication]
expected_cycle_time_ms = 1000
timeout_action = LAST_KNOWN   # LAST_KNOWN | SAFE_STATE | ALARM_ONLY

[slots]
expected_slot_count = 8

[alarms]
communication_alarm_priority = HIGH
communication_alarm_delay_ms = 5000
```

### Environment Variables

Location: `/etc/water-controller/environment`

| Variable | Description | Default |
|----------|-------------|---------|
| `WT_INTERFACE` | PROFINET network interface | `eth0` |
| `WT_CYCLE_TIME` | Scan cycle time (ms) | `1000` |
| `WT_LOG_LEVEL` | Log level | `INFO` |
| `WT_CONFIG_DIR` | Configuration directory | `/etc/water-controller` |
| `WT_DATA_DIR` | Data directory | `/var/lib/water-controller` |
| `DATABASE_URL` | PostgreSQL connection string | - |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |

### Modbus Configuration

Location: `/etc/water-controller/modbus.conf`

```ini
[server]
tcp_enabled = true
tcp_port = 502
tcp_bind_address = 0.0.0.0

rtu_enabled = false
rtu_device = /dev/ttyUSB0
rtu_baud_rate = 9600
rtu_slave_addr = 1

[mapping]
auto_generate = true
sensor_base_addr = 0
actuator_base_addr = 100
```

---

## Security Hardening

### Network Security

```bash
# Configure firewall (ufw example)
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow HMI access (restrict to operator network)
sudo ufw allow from 10.0.0.0/8 to any port 443   # HTTPS
sudo ufw allow from 10.0.0.0/8 to any port 3000  # Web UI
sudo ufw allow from 10.0.0.0/8 to any port 8080  # API

# PROFINET requires raw socket access - no firewall on that interface
# Instead, use separate network segment

sudo ufw enable
```

### HTTPS Configuration

```bash
# Generate or install TLS certificates
sudo mkdir -p /etc/water-controller/ssl

# Self-signed for initial deployment (replace in production)
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/water-controller/ssl/controller.key \
    -out /etc/water-controller/ssl/controller.crt \
    -subj "/CN=water-controller.local"
```

### Authentication Setup

Location: `/etc/water-controller/auth.conf`

```ini
[authentication]
method = LOCAL                # LOCAL | LDAP | AD
session_store = redis
password_min_length = 12
lockout_threshold = 5
lockout_duration_minutes = 30

[local_users]
# Initial admin user - change password immediately after first login
admin_password_hash = $argon2id$...  # Generated during install

[ldap]
# Uncomment and configure for Active Directory integration
# server = ldaps://dc.example.com:636
# base_dn = OU=SCADA,DC=example,DC=com
# bind_dn = CN=water-controller,OU=Service Accounts,DC=example,DC=com
# bind_password_file = /etc/water-controller/secrets/ldap.password
# user_filter = (&(objectClass=user)(sAMAccountName={username}))
# operator_group = CN=SCADA-Operators,OU=Groups,DC=example,DC=com
# admin_group = CN=SCADA-Admins,OU=Groups,DC=example,DC=com
```

---

## SD Card Protection

### Mount Options

Add to `/etc/fstab` for SD card protection:

```
tmpfs  /tmp      tmpfs  defaults,noatime,nosuid,size=256M  0 0
tmpfs  /var/log  tmpfs  defaults,noatime,nosuid,size=128M  0 0
```

**Note:** Logs in tmpfs are lost on reboot. Configure log forwarding to preserve critical logs.

### Write Coalescing Configuration

Add to `/etc/water-controller/controller.conf`:

```ini
[storage]
write_debounce_seconds = 30
config_save_delay_seconds = 60
historian_batch_size = 1000
historian_flush_interval = 60
track_unsaved_changes = true
unsaved_indicator_visible = true
```

### Log Forwarding

Location: `/etc/water-controller/logging.conf`

```ini
[local]
ring_buffer_size = 10000
persist_on_shutdown = true
persist_path = /var/lib/water-controller/logs/

[forwarding]
enabled = true
protocol = SYSLOG_TLS         # SYSLOG | SYSLOG_TLS | ELASTICSEARCH | GRAYLOG
destination = siem.example.com:6514
retry_queue_size = 5000
retry_interval_seconds = 30
```

---

## Service Management

### Using systemctl

```bash
# Start all services
sudo systemctl start water-controller

# Stop all services
sudo systemctl stop water-controller

# Restart controller
sudo systemctl restart water-controller

# View status
sudo systemctl status water-controller water-controller-api water-controller-ui

# View logs
sudo journalctl -u water-controller -f
```

### Using wtc-ctl

The `wtc-ctl` command provides convenient service management:

```bash
# Start all services
sudo wtc-ctl start

# Stop all services
sudo wtc-ctl stop

# Restart all services
sudo wtc-ctl restart

# View status
sudo wtc-ctl status

# Follow logs
sudo wtc-ctl logs

# Create backup
sudo wtc-ctl backup

# Restore from backup
sudo wtc-ctl restore /var/lib/water-controller/backups/wtc_backup_20240101_120000.tar.gz
```

### Service Dependencies

```
water-controller (main PROFINET controller)
    └── water-controller-api (REST API)
        └── water-controller-ui (Web UI)
    └── water-controller-modbus (Modbus gateway)
```

### Service Health Checks

```bash
# Verify all services running
sudo systemctl status water-controller water-controller-api water-controller-ui

# Check for errors
sudo journalctl -u water-controller -p err --since "1 hour ago"

# Verify PROFINET connectivity
curl -s http://localhost:8080/api/v1/rtus | jq '.[] | {name, status}'

# Verify historian writing
curl -s http://localhost:8080/api/v1/trends/tags | jq 'length'

# Verify alarm system
curl -s http://localhost:8080/api/v1/alarms | jq 'length'
```

---

## Backup and Restore

### Backup Configuration

Location: `/etc/water-controller/backup.conf`

```ini
[schedule]
config_backup_interval = daily
config_backup_retention = 30
historian_backup_interval = weekly
historian_backup_retention = 52

[destinations]
local_path = /var/backups/water-controller
remote_enabled = true
remote_type = S3                  # S3 | SFTP | NFS
remote_path = s3://bucket/water-controller-backups/
remote_credentials_file = /etc/water-controller/secrets/backup-creds

[content]
include_configuration = true
include_alarm_history = true
include_audit_log = true
include_historian_data = false
include_user_preferences = true
```

### Creating Backups

#### Via Web UI

1. Navigate to Settings > Backup & Restore
2. Enter optional description
3. Select "Include historian data" for full backup
4. Click "Create Backup"

#### Via API

```bash
# Create backup
curl -X POST http://localhost:8080/api/v1/backups \
  -H "Content-Type: application/json" \
  -d '{"description": "Pre-upgrade backup", "include_historian": false}'

# List backups
curl http://localhost:8080/api/v1/backups

# Download backup
curl -O http://localhost:8080/api/v1/backups/wtc_config_20240101_120000/download
```

#### Via Command Line

```bash
sudo wtc-ctl backup
```

### Restoring Backups

#### Via Web UI

1. Navigate to Settings > Backup & Restore
2. Find the backup in the list
3. Click "Restore"
4. Confirm the restoration

#### Via API

```bash
curl -X POST http://localhost:8080/api/v1/backups/wtc_config_20240101_120000/restore
```

#### Via Command Line

```bash
sudo wtc-ctl restore /var/lib/water-controller/backups/wtc_backup_20240101_120000.tar.gz
```

### Import/Export Configuration

#### Export

```bash
curl http://localhost:8080/api/v1/system/config > config_backup.json
```

#### Import

```bash
curl -X POST http://localhost:8080/api/v1/system/config \
  -H "Content-Type: application/json" \
  -d @config_backup.json
```

---

## Modbus Gateway

The Modbus gateway bridges PROFINET data to Modbus TCP/RTU, allowing integration with:
- SCADA systems
- HMI panels
- Building automation systems
- Third-party PLCs

### Register Mapping

Default mapping scheme:

| Modbus Type | Address Range | Data Source |
|-------------|---------------|-------------|
| Input Registers | 0-199 | PROFINET Sensors |
| Holding Registers | 100-299 | PROFINET Actuators |
| Input Registers | 200-299 | PID Loop Values |
| Coils | 0-99 | Actuator On/Off |

### Configuring Downstream Devices

Add Modbus slave devices that the gateway will poll:

```bash
curl -X POST http://localhost:8080/api/v1/modbus/downstream \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Energy Meter",
    "transport": "TCP",
    "tcp_host": "192.168.1.50",
    "tcp_port": 502,
    "slave_addr": 1,
    "poll_interval_ms": 5000,
    "enabled": true
  }'
```

### Custom Register Mapping

```bash
curl -X POST http://localhost:8080/api/v1/modbus/mappings \
  -H "Content-Type: application/json" \
  -d '{
    "modbus_addr": 100,
    "register_type": "HOLDING",
    "data_type": "FLOAT32",
    "source_type": "PROFINET_SENSOR",
    "rtu_station": "rtu-tank-1",
    "slot": 1,
    "description": "Tank 1 pH",
    "scaling_enabled": true,
    "scale_raw_min": 0,
    "scale_raw_max": 14,
    "scale_eng_min": 0,
    "scale_eng_max": 14000
  }'
```

---

## Deployment Verification

### Post-Deployment Checklist

#### PROFINET Connectivity
- [ ] All configured RTUs discovered via DCP
- [ ] All RTUs show status ONLINE
- [ ] Cyclic data exchange active (verify in HMI)
- [ ] No communication alarms present

#### Historian
- [ ] Tags auto-created for all RTU sensors
- [ ] Data points being recorded (check trend display)
- [ ] Compression working (check storage growth rate)
- [ ] Retention policy applied (verify old data pruned)

#### Alarms
- [ ] Alarm rules loaded from configuration
- [ ] Test alarm triggers correctly (simulate out-of-range)
- [ ] Alarm acknowledgment works
- [ ] Alarm history recording to database

#### HMI
- [ ] Web interface accessible via browser
- [ ] Real-time values updating (WebSocket active)
- [ ] User authentication working
- [ ] All pages rendering correctly

#### Security
- [ ] HTTPS certificate valid
- [ ] Non-admin users restricted appropriately
- [ ] API rate limiting active
- [ ] Audit logging capturing access

#### Integration
- [ ] Log forwarding to SIEM verified
- [ ] Backup job scheduled and tested
- [ ] Modbus gateway responding (if enabled)
- [ ] NTP synchronization confirmed

### Performance Baseline

```bash
# Capture baseline metrics
curl -s http://localhost:8080/api/v1/system/diagnostics | jq > baseline.json

# Should include:
# - Memory usage (should be stable, not growing)
# - CPU usage (should be low between cycles)
# - PROFINET cycle time jitter (should be < 10% of cycle time)
# - Database connection pool status
# - Active WebSocket connections
```

---

## Operational Handoff

### Documentation to Provide

1. Network diagram showing controller, RTUs, and network segments
2. IP address assignments for all devices
3. User accounts created and their roles
4. Alarm rule summary with expected trigger conditions
5. Backup schedule and restore procedure
6. Escalation contacts for system issues
7. Known limitations or deferred configuration

### Operator Training Topics

1. HMI navigation and process overview
2. Alarm acknowledgment and response procedures
3. How to identify RTU communication issues
4. Where to find historian trends
5. How to recognize "unsaved changes" indicator
6. Who to contact for different issue types
7. What NOT to touch (configuration vs. operation)

### Scheduled Maintenance Tasks

**Weekly:**
- Review alarm history for patterns
- Verify backup completion
- Check disk space (if not using tmpfs for logs)

**Monthly:**
- Review and prune old historian data if needed
- Update passwords for service accounts
- Review audit logs for anomalies

**Quarterly:**
- Test backup restore procedure
- Review and update alarm rules
- Security patch assessment

**Annually:**
- Full system backup and archive
- Review PROFINET timing and performance
- Plan hardware refresh if needed

---

## Troubleshooting

### Controller Won't Start

1. Check logs:
   ```bash
   sudo journalctl -u water-controller -n 100
   ```

2. Verify network interface:
   ```bash
   ip link show eth0
   ```

3. Check permissions:
   ```bash
   ls -la /dev/eth0  # Raw socket access
   ```

### RTU Shows OFFLINE Status

1. Verify RTU is powered and network link is up
2. Check RTU IP address matches configuration
3. Verify PROFINET interface is correct in profinet.conf
4. Check for duplicate IP addresses on network
5. Review controller logs:
   ```bash
   journalctl -u water-controller | grep -i profinet
   ```

### No PROFINET Communication

1. Verify interface is up:
   ```bash
   ip addr show eth0
   ```

2. Check firewall:
   ```bash
   sudo iptables -L
   ```

3. Verify RTU is powered and connected

### HMI Not Loading

1. Verify water-controller-ui service running
2. Check nginx configuration and logs
3. Verify React build completed successfully
4. Check browser console for JavaScript errors
5. Verify API service responding:
   ```bash
   curl http://localhost:8080/api/v1/health
   ```

### API Not Responding

1. Check if service is running:
   ```bash
   sudo systemctl status water-controller-api
   ```

2. Check port binding:
   ```bash
   sudo netstat -tlnp | grep 8080
   ```

3. View API logs:
   ```bash
   sudo journalctl -u water-controller-api -f
   ```

### Historian Not Recording

1. Verify PostgreSQL service running
2. Check database connection in controller.conf
3. Verify disk space available
4. Check historian flush interval settings
5. Review API logs:
   ```bash
   journalctl -u water-controller-api | grep -i historian
   ```

### Alarms Not Triggering

1. Verify alarm rules loaded: `GET /api/v1/alarms/rules`
2. Check data quality - bad quality suppresses alarms
3. Verify alarm priorities match filter settings
4. Check alarm rate limiting (chattering protection)
5. Review alarm manager logs for rule evaluation errors

### Modbus Connection Issues

1. Test TCP connectivity:
   ```bash
   nc -zv localhost 502
   ```

2. Check serial permissions (for RTU):
   ```bash
   ls -la /dev/ttyUSB0
   sudo usermod -a -G dialout wtc
   ```

3. View Modbus logs:
   ```bash
   sudo journalctl -u water-controller-modbus -f
   ```

### High Memory Usage

1. Check historian cache size settings
2. Review ring buffer depths
3. Look for WebSocket connection leaks
4. Check for excessive alarm count
5. Restart services if memory leak suspected (and report bug)

### SD Card Write Warnings

1. Reduce historian flush frequency
2. Increase write debounce intervals
3. Move logs to tmpfs if not already
4. Enable log forwarding to reduce local writes
5. Consider industrial SD card upgrade

### Performance Issues

1. Check CPU usage:
   ```bash
   top -p $(pgrep water_treat)
   ```

2. Monitor cycle time:
   ```bash
   curl http://localhost:8080/api/v1/system/health
   ```

3. Reduce historian sample rate if needed

---

## Emergency Procedures

### Controller Failure

If controller fails completely:
1. RTUs continue operating with last known state or safe mode
2. Process continues but without supervisory control
3. Local RTU interlocks remain active
4. Replace/recover controller and restore from backup

**DO NOT attempt to bypass RTU and control actuators directly.**
The two-plane architecture exists for safety.

### Graceful Shutdown

```bash
sudo systemctl stop water-controller-ui
sudo systemctl stop water-controller-api
sudo systemctl stop water-controller
```

This allows:
- Pending writes to flush
- Active alarms to persist
- RTUs to detect disconnect gracefully

### Emergency Stop

```bash
# If immediate stop required:
sudo systemctl kill water-controller
```

**Note:** Unsaved changes may be lost. RTUs will detect communication loss and enter safe state.

### Recovery Procedure

```bash
# 1. Stop services
sudo systemctl stop water-controller water-controller-api water-controller-ui

# 2. Restore configuration
sudo wtc-ctl restore /path/to/backup.tar.gz

# 3. Restart services
sudo systemctl start water-controller water-controller-api water-controller-ui

# 4. Verify RTU connectivity
curl -s http://localhost:8080/api/v1/rtus | jq '.[] | {name, status}'
```

---

## Network Ports

| Port | Service | Protocol |
|------|---------|----------|
| 502 | Modbus TCP | TCP |
| 8080 | REST API | HTTP |
| 3000 | Web UI | HTTP |
| 34962 | PROFINET RT | UDP |
| 34963 | PROFINET RT | UDP |
| 34964 | PROFINET DCP | UDP |

---

## Cross-Compilation

For deploying to embedded ARM boards, use the provided CMake toolchain files.

### Prerequisites (Build Host)

Install cross-compilation toolchains on your build host (x86_64 Linux):

```bash
# ARM64 (Raspberry Pi 4, Orange Pi, etc.)
sudo apt install gcc-aarch64-linux-gnu g++-aarch64-linux-gnu

# ARM32 hard float (Raspberry Pi 3, BeagleBone, etc.)
sudo apt install gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf

# ARM32 soft float (older boards)
sudo apt install gcc-arm-linux-gnueabi g++-arm-linux-gnueabi
```

### Building for ARM64

```bash
mkdir build-arm64 && cd build-arm64
cmake -DCMAKE_TOOLCHAIN_FILE=../cmake/toolchain-aarch64.cmake \
      -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
```

### Building for ARM32 (ARMv7)

```bash
mkdir build-arm32 && cd build-arm32
cmake -DCMAKE_TOOLCHAIN_FILE=../cmake/toolchain-arm.cmake \
      -DARM_ARCH=armv7hf \
      -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
```

Available ARM_ARCH options:
- `armv7hf` - ARMv7 with hard float (Raspberry Pi 3, BeagleBone Black)
- `armv7` - ARMv7 with soft float
- `armv6` - ARMv6 (Raspberry Pi Zero/1)
- `aarch64` - ARM64

### Building for Luckfox Lyra

The Luckfox Lyra uses Rockchip RV1103/RV1106 (ARM Cortex-A7):

```bash
# Option 1: Using standard ARM toolchain
mkdir build-luckfox && cd build-luckfox
cmake -DCMAKE_TOOLCHAIN_FILE=../cmake/toolchain-luckfox.cmake \
      -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)

# Option 2: Using Luckfox SDK (recommended)
export LUCKFOX_SDK_PATH=/path/to/luckfox-pico
mkdir build-luckfox && cd build-luckfox
cmake -DCMAKE_TOOLCHAIN_FILE=../cmake/toolchain-luckfox.cmake \
      -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
```

---

## Board-Specific Installation

### Raspberry Pi 4 / Raspberry Pi 5 (ARM64)

```bash
# On the Raspberry Pi
sudo apt update
sudo apt install -y build-essential cmake pkg-config \
    libpq-dev libjson-c-dev python3 python3-pip python3-venv nodejs npm

# Clone and build natively (or copy cross-compiled binary)
git clone https://github.com/mwilco03/Water-Controller.git
cd Water-Controller
sudo ./scripts/install.sh

# Configure network interface
sudo nano /etc/water-controller/controller.conf
# Set: interface = eth0  (or wlan0 for WiFi, not recommended for PROFINET)

# Enable real-time kernel (recommended)
sudo apt install linux-image-rt-arm64
```

### Raspberry Pi 3 / Zero 2 W (ARM32/ARM64)

```bash
# Same as Pi 4, but use ARMv7 toolchain for Pi 3 in 32-bit mode
# Note: Pi Zero 2 W supports ARM64, Pi Zero W is ARM32 only

# For Pi Zero W (ARM32, limited RAM)
# Consider disabling historian or reducing retention
```

### BeagleBone Black / BeagleBone AI

```bash
# On the BeagleBone
sudo apt update
sudo apt install -y build-essential cmake pkg-config \
    libpq-dev libjson-c-dev python3 python3-pip python3-venv

# Node.js may need manual installation on BeagleBone
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Clone and build
git clone https://github.com/mwilco03/Water-Controller.git
cd Water-Controller
sudo ./scripts/install.sh
```

### Luckfox Lyra (RV1103/RV1106)

The Luckfox Lyra has limited resources (64-256MB RAM). Use minimal configuration:

```bash
# Cross-compile on build host (see above)
# Then copy binary to device

# On the Luckfox
scp build-luckfox/water_treat_controller root@luckfox:/opt/water-controller/bin/

# Minimal configuration for low memory
cat > /etc/water-controller/controller.conf << 'EOF'
[general]
log_level = WARN
cycle_time_ms = 1000

[profinet]
interface = eth0

[historian]
enabled = false  # Disable to save memory

[modbus]
tcp_enabled = false
EOF

# Run directly (systemd optional on Luckfox)
/opt/water-controller/bin/water_treat_controller -c /etc/water-controller/controller.conf
```

### Orange Pi / Banana Pi / Other ARM SBCs

Most ARM single-board computers follow the Raspberry Pi pattern:

```bash
# Identify your architecture
uname -m
# aarch64 = ARM64, armv7l = ARM32

# Install dependencies (Debian/Ubuntu-based)
sudo apt update
sudo apt install -y build-essential cmake pkg-config \
    libpq-dev libjson-c-dev python3 python3-pip python3-venv nodejs npm

# Build and install
git clone https://github.com/mwilco03/Water-Controller.git
cd Water-Controller
sudo ./scripts/install.sh
```

### Network Interface Selection

PROFINET requires a dedicated Ethernet interface. WiFi is not recommended.

```bash
# List network interfaces
ip link show

# Common interface names:
# eth0    - First built-in Ethernet
# enp0s3  - PCI Ethernet (systemd naming)
# end0    - Device-tree Ethernet (some ARM boards)
# wlan0   - WiFi (NOT recommended for PROFINET)
```

Edit `/etc/water-controller/controller.conf`:

```ini
[profinet]
interface = eth0  # Change to your interface name
```

Network requirements:
- Dedicated Ethernet for PROFINET (not shared with management traffic)
- 100 Mbps minimum (1 Gbps recommended)
- Switch should support multicast (required for DCP)
- VLAN isolation recommended for production

---

## Support

- GitHub Issues: https://github.com/mwilco03/Water-Controller/issues
- Documentation: https://github.com/mwilco03/Water-Controller/wiki

---

## Appendix A: System Prompt Summary

Use this condensed version as a system instruction when working on Water-Controller deployment tasks:

```
You are deploying Water-Controller, a production PROFINET IO Controller for Water Treatment
SCADA systems. This is critical infrastructure - deployment errors have real consequences.

SYSTEM CONTEXT:
- Water-Controller runs on SBC #1, communicates with Water-Treat RTUs via PROFINET
- Components: C PROFINET stack, FastAPI backend, React HMI, PostgreSQL historian, Redis cache
- Two-plane architecture: controller commands flow THROUGH RTU, never direct to actuators
- RTUs maintain safe state during controller disconnect - this is by design

KEY CONSTRAINTS:
- Dedicated Ethernet interface for PROFINET (no shared traffic)
- Static IP addressing for controller and all RTUs
- Run services as non-root user (wtc)
- PROFINET requires CAP_NET_RAW, CAP_NET_ADMIN capabilities
- SD card protection: mount /tmp and /var/log as tmpfs, configure write debouncing

CRITICAL PARAMETERS:
- profinet.interface: Must be dedicated, no IP routing
- profinet.cycle_time_ms: Must match RTU configuration
- profinet.watchdog_factor: Cycles before RTU marked offline (default 3)
- historian.flush_interval: Balance data freshness vs SD writes
- alarms.alarm_rate_limit: Chattering protection (10/min/tag default)

NEVER:
- Deploy without testing backup/restore procedure
- Skip the post-deployment verification checklist
- Bypass RTU to control actuators directly
- Run production with default passwords

ALWAYS:
- Document IP assignments and network topology
- Verify NTP synchronization before deployment
- Create pre-deployment configuration backup
- Have rollback plan ready before changes
```
