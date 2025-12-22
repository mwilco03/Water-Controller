# Water-Controller Production Deployment Prompt

## System Instruction for Installation, Configuration, and Deployment

```
You are deploying and configuring Water-Controller, a production PROFINET IO Controller
for Water Treatment SCADA systems. This controller runs on SBC #1 and communicates with
Water-Treat RTU devices via PROFINET. The system includes FastAPI backend, React HMI,
data historian, and ISA-18.2 compliant alarm management.

Apply these deployment constraints without exception:

================================================================================
DEPLOYMENT PHILOSOPHY
================================================================================

This is critical infrastructure. Deployment errors can cause:
- Loss of process visibility (operator blindness)
- Environmental contamination (treatment failures)
- Equipment damage (uncontrolled actuators)
- Regulatory violations (audit trail gaps)

Every configuration choice must answer: "What happens when this fails?"

================================================================================
PRE-DEPLOYMENT VERIFICATION
================================================================================

HARDWARE REQUIREMENTS:
  [ ] Single Board Computer (Raspberry Pi 4/5, BeagleBone, or industrial SBC)
  [ ] Minimum 2GB RAM (4GB recommended for historian workloads)
  [ ] 32GB SD card (industrial-grade recommended for write endurance)
  [ ] Dedicated Ethernet interface for PROFINET (no shared traffic)
  [ ] Optional: Secondary Ethernet for HMI/API access
  [ ] Real-time clock with battery backup (critical for historian)
  [ ] UPS or graceful shutdown capability

NETWORK REQUIREMENTS:
  [ ] PROFINET network segment isolated from IT traffic
  [ ] Static IP addressing for controller and all RTUs
  [ ] Network time synchronization (NTP or PTP) configured
  [ ] Firewall rules defined for HMI access (port 3000, 8000)
  [ ] No DHCP on PROFINET segment

PRE-FLIGHT CHECKLIST:
  [ ] Target OS is Ubuntu 22.04/24.04 LTS or Raspberry Pi OS (64-bit)
  [ ] Root/sudo access available
  [ ] RTU devices powered and network-reachable
  [ ] Backup of any existing configuration exported
  [ ] Maintenance window scheduled with operations
  [ ] Rollback plan documented

================================================================================
INSTALLATION SEQUENCE
================================================================================

PHASE 1 - SYSTEM PREPARATION:

# Update system packages (security baseline)
sudo apt update && sudo apt upgrade -y

# Install required dependencies
sudo apt install -y \
    build-essential \
    cmake \
    libpq-dev \
    libjson-c-dev \
    python3.11 \
    python3.11-venv \
    python3-pip \
    postgresql \
    redis-server \
    nginx \
    git

# Configure system for real-time operation
echo 'net.core.rmem_max=16777216' | sudo tee -a /etc/sysctl.d/99-water-controller.conf
echo 'net.core.wmem_max=16777216' | sudo tee -a /etc/sysctl.d/99-water-controller.conf
sudo sysctl --system

# Create service user (non-root operation)
sudo useradd -r -s /usr/sbin/nologin water-controller
sudo usermod -aG dialout water-controller  # For serial Modbus if needed

PHASE 2 - APPLICATION DEPLOYMENT:

# Clone repository
cd /opt
sudo git clone https://github.com/mwilco03/Water-Controller.git
sudo chown -R water-controller:water-controller /opt/Water-Controller

# Build C components
cd /opt/Water-Controller
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
sudo make install

# Install Python backend
cd /opt/Water-Controller/web/api
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Build React frontend
cd /opt/Water-Controller/web/ui
npm install
npm run build

PHASE 3 - DATABASE INITIALIZATION:

# Create PostgreSQL database and user
sudo -u postgres psql <<EOF
CREATE USER water_controller WITH PASSWORD 'CHANGE_THIS_PASSWORD';
CREATE DATABASE water_controller OWNER water_controller;
GRANT ALL PRIVILEGES ON DATABASE water_controller TO water_controller;
\c water_controller
CREATE EXTENSION IF NOT EXISTS timescaledb;  -- Optional: for historian performance
EOF

# Run database migrations
cd /opt/Water-Controller
./scripts/migrate.sh

PHASE 4 - SERVICE INSTALLATION:

# Install systemd unit files
sudo cp /opt/Water-Controller/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable services for boot
sudo systemctl enable water-controller.service
sudo systemctl enable water-controller-api.service
sudo systemctl enable water-controller-ui.service
sudo systemctl enable water-controller-modbus.service  # If Modbus gateway needed

================================================================================
CONFIGURATION MANAGEMENT
================================================================================

CONFIGURATION FILE HIERARCHY:

/etc/water-controller/
├── controller.conf          # Main controller configuration
├── profinet.conf             # PROFINET network settings
├── rtus/                     # Per-RTU configuration files
│   ├── tank-1.conf
│   ├── pump-station.conf
│   └── filter-1.conf
├── alarms/                   # Alarm rule definitions
│   ├── process-alarms.json
│   └── system-alarms.json
├── historian.conf            # Data retention and compression settings
├── modbus.conf               # Modbus gateway mappings (if enabled)
├── auth.conf                 # Authentication settings (AD integration)
└── backup.conf               # Backup schedule and destinations

CRITICAL CONFIGURATION PARAMETERS:

# /etc/water-controller/controller.conf
[general]
station_name = "WTP-Controller-01"
log_level = INFO
log_retention_days = 90

[profinet]
interface = eth1              # Dedicated PROFINET interface
cycle_time_ms = 1000          # Match RTU cycle time
watchdog_factor = 3           # Cycles before RTU marked offline
dcp_discovery_interval = 60   # Seconds between discovery sweeps

[database]
connection_string = postgresql://water_controller:PASSWORD@localhost/water_controller
pool_size = 10
connection_timeout = 5

[redis]
url = redis://localhost:6379/0
# Used for real-time state caching and WebSocket pub/sub

[historian]
retention_days = 365
compression_enabled = true
deadband_default = 0.5        # Percent of span
flush_interval_seconds = 30   # Batch writes to protect SD

[alarms]
isa_18_2_compliant = true
max_active_alarms = 1000
alarm_rate_limit = 10         # Per tag per minute (chattering protection)

[security]
session_timeout_minutes = 480
require_https = true          # Enforce in production
api_rate_limit = 100          # Requests per minute per client

PROFINET INTERFACE CONFIGURATION:

# /etc/water-controller/profinet.conf
[network]
# Interface must be dedicated - no IP routing, no other traffic
interface = eth1
mac_filter = true             # Only accept frames from known RTUs

[timing]
cycle_time_ms = 1000
reduction_ratio = 1
send_clock_factor = 1

[discovery]
dcp_enabled = true
dcp_interval_seconds = 60
auto_register_rtus = false    # Require explicit RTU configuration

[failover]
connection_timeout_cycles = 3
reconnect_delay_ms = 5000
max_reconnect_attempts = 0    # 0 = infinite retry

RTU REGISTRATION:

# /etc/water-controller/rtus/tank-1.conf
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
# Slot configuration is reported by RTU at connection
# These are fallback/validation values
expected_slot_count = 8

[alarms]
communication_alarm_priority = HIGH
communication_alarm_delay_ms = 5000  # Debounce brief disconnects

================================================================================
SECURITY HARDENING
================================================================================

NETWORK SECURITY:

# Configure firewall (ufw example)
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow HMI access (restrict to operator network)
sudo ufw allow from 10.0.0.0/8 to any port 443   # HTTPS
sudo ufw allow from 10.0.0.0/8 to any port 3000  # React dev (disable in prod)

# Allow API access
sudo ufw allow from 10.0.0.0/8 to any port 8000

# PROFINET requires raw socket access - no firewall on that interface
# Instead, use separate network segment

sudo ufw enable

HTTPS CONFIGURATION:

# Generate or install TLS certificates
# For production, use proper CA-signed certificates
sudo mkdir -p /etc/water-controller/ssl

# Self-signed for initial deployment (replace in production)
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/water-controller/ssl/controller.key \
    -out /etc/water-controller/ssl/controller.crt \
    -subj "/CN=water-controller.local"

# Configure nginx as reverse proxy
# See /opt/Water-Controller/docs/nginx.conf.example

AUTHENTICATION SETUP:

# /etc/water-controller/auth.conf
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

================================================================================
SD CARD PROTECTION (WRITE ENDURANCE)
================================================================================

MOUNT OPTIONS:

# /etc/fstab additions for SD card protection
# Reduce writes by mounting /tmp and /var/log as tmpfs

tmpfs  /tmp      tmpfs  defaults,noatime,nosuid,size=256M  0 0
tmpfs  /var/log  tmpfs  defaults,noatime,nosuid,size=128M  0 0

# Note: Logs in tmpfs are lost on reboot
# Configure log forwarding to preserve critical logs (see LOG FORWARDING)

WRITE COALESCING CONFIGURATION:

# /etc/water-controller/controller.conf
[storage]
# All writes go through coalescing layer
write_debounce_seconds = 30
config_save_delay_seconds = 60    # Wait for rapid changes to settle
historian_batch_size = 1000       # Records before flush
historian_flush_interval = 60     # Seconds (even if batch not full)

# Dirty-state tracking
track_unsaved_changes = true
unsaved_indicator_visible = true  # Show in HMI status bar

LOG ROTATION AND FORWARDING:

# /etc/water-controller/logging.conf
[local]
ring_buffer_size = 10000      # In-memory log entries
persist_on_shutdown = true    # Flush to disk on graceful stop
persist_path = /var/lib/water-controller/logs/

[forwarding]
enabled = true
protocol = SYSLOG_TLS         # SYSLOG | SYSLOG_TLS | ELASTICSEARCH | GRAYLOG
destination = siem.example.com:6514
retry_queue_size = 5000
retry_interval_seconds = 30

================================================================================
SERVICE MANAGEMENT
================================================================================

SYSTEMD UNIT CONFIGURATION:

# /etc/systemd/system/water-controller.service
[Unit]
Description=Water Treatment PROFINET Controller
After=network-online.target postgresql.service redis.service
Wants=network-online.target
Requires=postgresql.service redis.service

[Service]
Type=simple
User=water-controller
Group=water-controller
WorkingDirectory=/opt/Water-Controller
ExecStart=/opt/Water-Controller/build/water_controller \
    --config /etc/water-controller/controller.conf
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=5
WatchdogSec=30

# Resource limits
MemoryMax=512M
CPUQuota=80%

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/water-controller /run/water-controller

# Capabilities for raw socket (PROFINET)
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN

[Install]
WantedBy=multi-user.target

SERVICE HEALTH CHECKS:

# Verify all services running
sudo systemctl status water-controller water-controller-api water-controller-ui

# Check for errors
sudo journalctl -u water-controller -p err --since "1 hour ago"

# Verify PROFINET connectivity
curl -s http://localhost:8000/api/v1/rtus | jq '.[] | {name, status}'

# Verify historian writing
curl -s http://localhost:8000/api/v1/trends/tags | jq 'length'

# Verify alarm system
curl -s http://localhost:8000/api/v1/alarms | jq 'length'

================================================================================
BACKUP AND RECOVERY
================================================================================

BACKUP CONFIGURATION:

# /etc/water-controller/backup.conf
[schedule]
config_backup_interval = daily
config_backup_retention = 30      # Days
historian_backup_interval = weekly
historian_backup_retention = 52   # Weeks

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
include_historian_data = false    # Large; handle separately
include_user_preferences = true

MANUAL BACKUP:

# Create immediate backup
curl -X POST http://localhost:8000/api/v1/backups \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"description": "Pre-maintenance backup"}'

# Export configuration only
curl -s http://localhost:8000/api/v1/system/config \
    -H "Authorization: Bearer $TOKEN" \
    > config-export-$(date +%Y%m%d).json

RECOVERY PROCEDURE:

# 1. Stop services
sudo systemctl stop water-controller water-controller-api water-controller-ui

# 2. Restore configuration
curl -X POST http://localhost:8000/api/v1/system/config \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d @config-export-backup.json

# 3. Restore database (if needed)
sudo -u postgres pg_restore -d water_controller backup.dump

# 4. Restart services
sudo systemctl start water-controller water-controller-api water-controller-ui

# 5. Verify RTU connectivity
curl -s http://localhost:8000/api/v1/rtus | jq '.[] | {name, status}'

================================================================================
DEPLOYMENT VERIFICATION
================================================================================

POST-DEPLOYMENT CHECKLIST:

PROFINET CONNECTIVITY:
  [ ] All configured RTUs discovered via DCP
  [ ] All RTUs show status ONLINE
  [ ] Cyclic data exchange active (verify in HMI)
  [ ] No communication alarms present

HISTORIAN:
  [ ] Tags auto-created for all RTU sensors
  [ ] Data points being recorded (check trend display)
  [ ] Compression working (check storage growth rate)
  [ ] Retention policy applied (verify old data pruned)

ALARMS:
  [ ] Alarm rules loaded from configuration
  [ ] Test alarm triggers correctly (simulate out-of-range)
  [ ] Alarm acknowledgment works
  [ ] Alarm history recording to database

HMI:
  [ ] Web interface accessible via browser
  [ ] Real-time values updating (WebSocket active)
  [ ] User authentication working
  [ ] All pages rendering correctly

SECURITY:
  [ ] HTTPS certificate valid
  [ ] Non-admin users restricted appropriately
  [ ] API rate limiting active
  [ ] Audit logging capturing access

INTEGRATION:
  [ ] Log forwarding to SIEM verified
  [ ] Backup job scheduled and tested
  [ ] Modbus gateway responding (if enabled)
  [ ] NTP synchronization confirmed

PERFORMANCE BASELINE:

# Capture baseline metrics
curl -s http://localhost:8000/api/v1/system/diagnostics | jq > baseline.json

# Should include:
# - Memory usage (should be stable, not growing)
# - CPU usage (should be low between cycles)
# - PROFINET cycle time jitter (should be < 10% of cycle time)
# - Database connection pool status
# - Active WebSocket connections

================================================================================
OPERATIONAL HANDOFF
================================================================================

DOCUMENTATION TO PROVIDE:

1. Network diagram showing controller, RTUs, and network segments
2. IP address assignments for all devices
3. User accounts created and their roles
4. Alarm rule summary with expected trigger conditions
5. Backup schedule and restore procedure
6. Escalation contacts for system issues
7. Known limitations or deferred configuration

OPERATOR TRAINING TOPICS:

1. HMI navigation and process overview
2. Alarm acknowledgment and response procedures
3. How to identify RTU communication issues
4. Where to find historian trends
5. How to recognize "unsaved changes" indicator
6. Who to contact for different issue types
7. What NOT to touch (configuration vs. operation)

SCHEDULED MAINTENANCE TASKS:

Weekly:
  - Review alarm history for patterns
  - Verify backup completion
  - Check disk space (if not using tmpfs for logs)

Monthly:
  - Review and prune old historian data if needed
  - Update passwords for service accounts
  - Review audit logs for anomalies

Quarterly:
  - Test backup restore procedure
  - Review and update alarm rules
  - Security patch assessment

Annually:
  - Full system backup and archive
  - Review PROFINET timing and performance
  - Plan hardware refresh if needed

================================================================================
TROUBLESHOOTING QUICK REFERENCE
================================================================================

SYMPTOM: RTU shows OFFLINE status
  1. Verify RTU is powered and network link is up
  2. Check RTU IP address matches configuration
  3. Verify PROFINET interface is correct in profinet.conf
  4. Check for duplicate IP addresses on network
  5. Review controller logs: journalctl -u water-controller | grep -i profinet

SYMPTOM: HMI not loading
  1. Verify water-controller-ui service running
  2. Check nginx configuration and logs
  3. Verify React build completed successfully
  4. Check browser console for JavaScript errors
  5. Verify API service responding: curl http://localhost:8000/api/v1/health

SYMPTOM: Historian not recording
  1. Verify PostgreSQL service running
  2. Check database connection in controller.conf
  3. Verify disk space available
  4. Check historian flush interval settings
  5. Review API logs: journalctl -u water-controller-api | grep -i historian

SYMPTOM: Alarms not triggering
  1. Verify alarm rules loaded: GET /api/v1/alarms/rules
  2. Check data quality - bad quality suppresses alarms
  3. Verify alarm priorities match filter settings
  4. Check alarm rate limiting (chattering protection)
  5. Review alarm manager logs for rule evaluation errors

SYMPTOM: High memory usage
  1. Check historian cache size settings
  2. Review ring buffer depths
  3. Look for WebSocket connection leaks
  4. Check for excessive alarm count
  5. Restart services if memory leak suspected (and report bug)

SYMPTOM: SD card write warnings
  1. Reduce historian flush frequency
  2. Increase write debounce intervals
  3. Move logs to tmpfs if not already
  4. Enable log forwarding to reduce local writes
  5. Consider industrial SD card upgrade

================================================================================
EMERGENCY PROCEDURES
================================================================================

CONTROLLER FAILURE:

If controller fails completely:
1. RTUs continue operating with last known state or safe mode
2. Process continues but without supervisory control
3. Local RTU interlocks remain active
4. Replace/recover controller and restore from backup

DO NOT attempt to bypass RTU and control actuators directly.
The two-plane architecture exists for safety.

GRACEFUL SHUTDOWN:

sudo systemctl stop water-controller-ui
sudo systemctl stop water-controller-api
sudo systemctl stop water-controller

# This allows:
# - Pending writes to flush
# - Active alarms to persist
# - RTUs to detect disconnect gracefully

EMERGENCY STOP:

# If immediate stop required:
sudo systemctl kill water-controller

# Note: Unsaved changes may be lost
# RTUs will detect communication loss and enter safe state
```

================================================================================
END OF DEPLOYMENT PROMPT
================================================================================

## Usage Notes

This prompt is designed to be used as a system instruction or reference document when:

1. **Deploying new controller instances** - Follow the installation sequence exactly
2. **Troubleshooting production issues** - Reference the troubleshooting section
3. **Training deployment engineers** - Use as curriculum structure
4. **Auditing existing deployments** - Use checklists for verification
5. **Planning maintenance windows** - Reference scheduled maintenance tasks

## Integration with Development Guidelines

This deployment prompt complements the SCADA Development Guidelines by:

- Implementing SD card protection through mount options and write coalescing
- Enforcing the two-plane architecture (controller never directly controls actuators)
- Establishing graceful degradation through service health checks
- Providing operator transparency through status indicators and diagnostics
- Ensuring data quality propagation through historian configuration
- Supporting log forwarding for audit trail preservation

## Version Control

Track changes to this deployment prompt alongside the codebase. Configuration changes should be:
- Documented in CHANGELOG.md
- Tested in staging environment
- Applied with rollback plan ready
