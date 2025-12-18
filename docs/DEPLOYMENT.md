# Water Treatment Controller - Deployment Guide

This guide covers installation, configuration, and deployment of the Water Treatment Controller system.

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Quick Installation](#quick-installation)
3. [Manual Installation](#manual-installation)
4. [Configuration](#configuration)
5. [Service Management](#service-management)
6. [Backup and Restore](#backup-and-restore)
7. [Modbus Gateway](#modbus-gateway)
8. [Troubleshooting](#troubleshooting)

## System Requirements

### Hardware

- **CPU**: ARM Cortex-A53 or x86_64 (multi-core recommended)
- **RAM**: 512 MB minimum, 2 GB recommended
- **Storage**: 1 GB minimum, 10 GB recommended for historian data
- **Network**: Ethernet interface for PROFINET communication

### Software

- **OS**: Debian 11+, Ubuntu 20.04+, or Raspberry Pi OS
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
    nodejs npm
```

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

## Manual Installation

### 1. Build the Controller

```bash
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
```

### 2. Install Files

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

### 3. Create Service User

```bash
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin wtc
sudo usermod -a -G dialout wtc  # For serial port access
sudo chown -R wtc:wtc /var/lib/water-controller /var/log/water-controller
```

### 4. Install Python Environment

```bash
cd /opt/water-controller
sudo python3 -m venv venv
sudo /opt/water-controller/venv/bin/pip install -r web/api/requirements.txt
```

### 5. Install Node.js Dependencies

```bash
cd /opt/water-controller/web/ui
sudo npm install --production
sudo npm run build
```

### 6. Install Systemd Services

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable water-controller water-controller-api water-controller-ui
```

## Configuration

### Main Configuration File

Location: `/etc/water-controller/controller.conf`

```ini
[general]
log_level = INFO
cycle_time_ms = 1000

[profinet]
interface = eth0
station_name = wtc-controller

[modbus]
tcp_enabled = true
tcp_port = 502
rtu_enabled = false

[historian]
enabled = true
retention_days = 365
compression = swinging_door

[database]
# PostgreSQL (optional)
# connection_string = postgresql://user:pass@localhost/wtc
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

## Backup and Restore

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

## Network Ports

| Port | Service | Protocol |
|------|---------|----------|
| 502 | Modbus TCP | TCP |
| 8080 | REST API | HTTP |
| 3000 | Web UI | HTTP |
| 34962 | PROFINET RT | UDP |
| 34963 | PROFINET RT | UDP |
| 34964 | PROFINET DCP | UDP |

## Security Considerations

1. **Network Isolation**: Place PROFINET network on isolated VLAN
2. **Firewall**: Restrict access to management ports (8080, 3000)
3. **Authentication**: Configure reverse proxy with authentication for web UI
4. **Updates**: Keep system and dependencies updated
5. **Backups**: Regular automated backups to off-site storage

## Support

- GitHub Issues: https://github.com/mwilco03/Water-Controller/issues
- Documentation: https://github.com/mwilco03/Water-Controller/wiki
