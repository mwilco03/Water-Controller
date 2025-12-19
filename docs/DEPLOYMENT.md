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
# Install the RT kernel for better PROFINET timing
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

# BeagleBone PRU notes:
# The PRU could be used for ultra-low-latency I/O if needed
# This requires additional configuration not covered here
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

## Network Interface Selection

PROFINET requires a dedicated Ethernet interface. WiFi is not recommended.

### Finding Available Interfaces

```bash
# List network interfaces
ip link show

# Common interface names:
# eth0    - First built-in Ethernet
# enp0s3  - PCI Ethernet (systemd naming)
# end0    - Device-tree Ethernet (some ARM boards)
# wlan0   - WiFi (NOT recommended for PROFINET)
```

### Configuration

Edit `/etc/water-controller/controller.conf`:

```ini
[profinet]
interface = eth0  # Change to your interface name
```

### Network Requirements

- Dedicated Ethernet for PROFINET (not shared with management traffic)
- 100 Mbps minimum (1 Gbps recommended)
- Switch should support multicast (required for DCP)
- VLAN isolation recommended for production

## Support

- GitHub Issues: https://github.com/mwilco03/Water-Controller/issues
- Documentation: https://github.com/mwilco03/Water-Controller/wiki
