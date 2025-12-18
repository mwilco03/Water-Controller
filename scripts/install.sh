#!/bin/bash
#
# Water Treatment Controller - Installation Script
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#

set -e

# Configuration
INSTALL_DIR="/opt/water-controller"
CONFIG_DIR="/etc/water-controller"
DATA_DIR="/var/lib/water-controller"
LOG_DIR="/var/log/water-controller"
SERVICE_USER="wtc"
SERVICE_GROUP="wtc"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root"
    exit 1
fi

# Parse arguments
SKIP_BUILD=false
SKIP_SERVICES=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build) SKIP_BUILD=true; shift ;;
        --skip-services) SKIP_SERVICES=true; shift ;;
        --help)
            echo "Usage: $0 [--skip-build] [--skip-services]"
            exit 0
            ;;
        *) shift ;;
    esac
done

log_info "Water Treatment Controller Installation"
log_info "========================================"

# Create service user
if ! id -u $SERVICE_USER >/dev/null 2>&1; then
    log_info "Creating service user: $SERVICE_USER"
    useradd --system --user-group --no-create-home --shell /usr/sbin/nologin $SERVICE_USER
    usermod -a -G dialout $SERVICE_USER  # For serial port access
fi

# Create directories
log_info "Creating directories..."
mkdir -p $INSTALL_DIR/{bin,lib,web,config}
mkdir -p $CONFIG_DIR
mkdir -p $DATA_DIR/{backups,historian,logs}
mkdir -p $LOG_DIR

# Set ownership
chown -R $SERVICE_USER:$SERVICE_GROUP $DATA_DIR
chown -R $SERVICE_USER:$SERVICE_GROUP $LOG_DIR

# Build if not skipped
if [ "$SKIP_BUILD" = false ]; then
    log_info "Building controller..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SOURCE_DIR="$(dirname "$SCRIPT_DIR")"

    cd "$SOURCE_DIR"
    mkdir -p build && cd build
    cmake -DCMAKE_BUILD_TYPE=Release ..
    make -j$(nproc)

    # Install binaries
    log_info "Installing binaries..."
    cp water_treat_controller $INSTALL_DIR/bin/
    cp lib*.so $INSTALL_DIR/lib/ 2>/dev/null || true
fi

# Install web components
log_info "Installing web components..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"

cp -r "$SOURCE_DIR/web" $INSTALL_DIR/

# Create Python virtual environment
log_info "Setting up Python environment..."
python3 -m venv $INSTALL_DIR/venv
$INSTALL_DIR/venv/bin/pip install --upgrade pip
$INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/web/api/requirements.txt

# Install Node.js dependencies
if [ -f "$INSTALL_DIR/web/ui/package.json" ]; then
    log_info "Installing Node.js dependencies..."
    cd $INSTALL_DIR/web/ui
    npm install --production
    npm run build
fi

# Install configuration files
log_info "Installing configuration files..."
if [ ! -f "$CONFIG_DIR/controller.conf" ]; then
    cp "$SOURCE_DIR/config/controller.conf.example" "$CONFIG_DIR/controller.conf" 2>/dev/null || \
    cat > "$CONFIG_DIR/controller.conf" << 'EOF'
# Water Treatment Controller Configuration
# See documentation for all options

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
# PostgreSQL connection (optional)
# connection_string = postgresql://user:pass@localhost/wtc
EOF
fi

if [ ! -f "$CONFIG_DIR/modbus.conf" ]; then
    cat > "$CONFIG_DIR/modbus.conf" << 'EOF'
# Modbus Gateway Configuration

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

# Register map file (JSON format)
# register_map_file = /etc/water-controller/register_map.json
EOF
fi

if [ ! -f "$CONFIG_DIR/environment" ]; then
    cat > "$CONFIG_DIR/environment" << 'EOF'
# Environment variables for Water Treatment Controller services
WT_LOG_LEVEL=INFO
WT_CONFIG_DIR=/etc/water-controller
WT_DATA_DIR=/var/lib/water-controller
# DATABASE_URL=postgresql://user:pass@localhost/wtc
# REDIS_URL=redis://localhost:6379
EOF
fi

chmod 640 $CONFIG_DIR/*.conf $CONFIG_DIR/environment
chown root:$SERVICE_GROUP $CONFIG_DIR/*.conf $CONFIG_DIR/environment

# Install systemd services
if [ "$SKIP_SERVICES" = false ]; then
    log_info "Installing systemd services..."
    cp "$SOURCE_DIR/systemd/"*.service /etc/systemd/system/

    # Reload systemd
    systemctl daemon-reload

    # Enable services
    systemctl enable water-controller.service
    systemctl enable water-controller-api.service
    systemctl enable water-controller-ui.service

    log_info "Services installed. Start with: systemctl start water-controller"
fi

# Create management script
log_info "Creating management scripts..."
cat > /usr/local/bin/wtc-ctl << 'EOF'
#!/bin/bash
# Water Treatment Controller management script

case "$1" in
    start)
        systemctl start water-controller water-controller-api water-controller-ui
        ;;
    stop)
        systemctl stop water-controller-ui water-controller-api water-controller
        ;;
    restart)
        systemctl restart water-controller water-controller-api water-controller-ui
        ;;
    status)
        systemctl status water-controller water-controller-api water-controller-ui --no-pager
        ;;
    logs)
        journalctl -u water-controller -u water-controller-api -u water-controller-ui -f
        ;;
    backup)
        BACKUP_DIR="/var/lib/water-controller/backups"
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        BACKUP_FILE="$BACKUP_DIR/wtc_backup_$TIMESTAMP.tar.gz"

        echo "Creating backup: $BACKUP_FILE"
        tar -czf "$BACKUP_FILE" \
            /etc/water-controller \
            /var/lib/water-controller/historian \
            2>/dev/null
        echo "Backup complete: $BACKUP_FILE"
        ;;
    restore)
        if [ -z "$2" ]; then
            echo "Usage: wtc-ctl restore <backup_file>"
            exit 1
        fi
        echo "Restoring from: $2"
        systemctl stop water-controller water-controller-api
        tar -xzf "$2" -C /
        systemctl start water-controller water-controller-api
        echo "Restore complete"
        ;;
    *)
        echo "Usage: wtc-ctl {start|stop|restart|status|logs|backup|restore}"
        exit 1
        ;;
esac
EOF
chmod +x /usr/local/bin/wtc-ctl

log_info "Installation complete!"
log_info ""
log_info "Next steps:"
log_info "  1. Edit configuration: $CONFIG_DIR/controller.conf"
log_info "  2. Start services: systemctl start water-controller"
log_info "  3. Access web UI: http://localhost:3000"
log_info "  4. API documentation: http://localhost:8080/docs"
log_info ""
log_info "Management commands:"
log_info "  wtc-ctl start|stop|restart|status|logs|backup|restore"
