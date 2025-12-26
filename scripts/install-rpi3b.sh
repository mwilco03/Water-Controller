#!/bin/bash
#
# Water Treatment Controller - Raspberry Pi 3B Installation Script
# Non-interactive, controller-only deployment
#
# Usage: curl -sSL <url> | sudo bash
#    or: sudo ./install-rpi3b.sh [OPTIONS]
#
# Options:
#   --no-api        Skip Python API installation (controller daemon only)
#   --no-swap       Skip swap file creation
#   --interface=X   Set PROFINET network interface (default: eth0)
#

set -e

# =============================================================================
# Configuration
# =============================================================================

INSTALL_DIR="/opt/water-controller"
CONFIG_DIR="/etc/water-controller"
DATA_DIR="/var/lib/water-controller"
LOG_DIR="/var/log/water-controller"
SERVICE_USER="wtc"
SWAP_SIZE="2G"
PROFINET_INTERFACE="eth0"
INSTALL_API=true
CREATE_SWAP=true

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# =============================================================================
# Parse Arguments
# =============================================================================

for arg in "$@"; do
    case $arg in
        --no-api) INSTALL_API=false ;;
        --no-swap) CREATE_SWAP=false ;;
        --interface=*) PROFINET_INTERFACE="${arg#*=}" ;;
        --help)
            echo "Usage: sudo $0 [--no-api] [--no-swap] [--interface=eth0]"
            exit 0
            ;;
    esac
done

# =============================================================================
# Helper Functions
# =============================================================================

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root: sudo $0"
        exit 1
    fi
}

check_architecture() {
    ARCH=$(uname -m)
    log_info "Detected architecture: $ARCH"

    if [[ "$ARCH" != "armv7l" && "$ARCH" != "aarch64" ]]; then
        log_warn "This script is optimized for Raspberry Pi (ARM). Detected: $ARCH"
    fi

    # Check if it's a Raspberry Pi
    if [ -f /proc/device-tree/model ]; then
        MODEL=$(cat /proc/device-tree/model | tr -d '\0')
        log_info "Board: $MODEL"
    fi
}

# =============================================================================
# Main Installation Steps
# =============================================================================

echo ""
echo "=========================================="
echo "  Water Controller - RPi 3B Installer"
echo "=========================================="
echo ""

check_root
check_architecture

# Get source directory (handle both git clone and curl|bash scenarios)
if [ -f "$(dirname "$0")/lib/common.sh" ]; then
    SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
    log_info "Installing from local source: $SOURCE_DIR"
elif [ -d "/tmp/Water-Controller" ]; then
    SOURCE_DIR="/tmp/Water-Controller"
else
    log_info "Cloning repository..."
    apt-get update -qq
    apt-get install -y -qq git
    git clone --depth 1 https://github.com/mwilco03/Water-Controller.git /tmp/Water-Controller
    SOURCE_DIR="/tmp/Water-Controller"
fi

# -----------------------------------------------------------------------------
# Step 1: Create swap (helps with compilation on 1GB RAM)
# -----------------------------------------------------------------------------

if [ "$CREATE_SWAP" = true ]; then
    log_info "Setting up swap file for compilation..."
    if [ ! -f /swapfile ]; then
        fallocate -l $SWAP_SIZE /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
        chmod 600 /swapfile
        mkswap /swapfile >/dev/null
        swapon /swapfile
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
        log_info "Created ${SWAP_SIZE} swap file"
    else
        swapon /swapfile 2>/dev/null || true
        log_info "Swap file already exists"
    fi
fi

# -----------------------------------------------------------------------------
# Step 2: Install system dependencies
# -----------------------------------------------------------------------------

log_info "Installing system dependencies..."
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq \
    build-essential \
    cmake \
    pkg-config \
    libjson-c-dev \
    libsqlite3-dev \
    python3 \
    python3-venv \
    python3-pip \
    libcap2-bin

# -----------------------------------------------------------------------------
# Step 3: Create service user and directories
# -----------------------------------------------------------------------------

log_info "Creating service user and directories..."

if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    usermod -a -G dialout "$SERVICE_USER"
fi

mkdir -p "$INSTALL_DIR"/{bin,lib,config}
mkdir -p "$CONFIG_DIR"
mkdir -p "$DATA_DIR"/{backups,historian}
mkdir -p "$LOG_DIR"

chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR" "$LOG_DIR"
chmod 755 "$INSTALL_DIR" "$DATA_DIR" "$LOG_DIR"
chmod 750 "$CONFIG_DIR"

# -----------------------------------------------------------------------------
# Step 4: Build C controller (reduced parallelism for RPi)
# -----------------------------------------------------------------------------

log_info "Building controller (this may take 5-10 minutes on RPi 3B)..."

cd "$SOURCE_DIR"
mkdir -p build && cd build

# Use -j2 instead of -j4 to reduce memory pressure
cmake -DCMAKE_BUILD_TYPE=Release .. >/dev/null
make -j2

# Install binaries
cp water_treat_controller "$INSTALL_DIR/bin/"
cp lib*.so "$INSTALL_DIR/lib/" 2>/dev/null || true

log_info "Controller built successfully"

# -----------------------------------------------------------------------------
# Step 5: Install Python API (optional)
# -----------------------------------------------------------------------------

if [ "$INSTALL_API" = true ]; then
    log_info "Setting up Python API..."

    cp -r "$SOURCE_DIR/web/api" "$INSTALL_DIR/web/"

    python3 -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
    "$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/web/api/requirements.txt"

    log_info "Python API installed"
fi

# -----------------------------------------------------------------------------
# Step 6: Create RPi-optimized configuration
# -----------------------------------------------------------------------------

log_info "Creating RPi 3B optimized configuration..."

cat > "$CONFIG_DIR/controller.conf" << EOF
# Water Treatment Controller - RPi 3B Optimized Configuration
# Generated by install-rpi3b.sh on $(date)

[general]
# Reduced logging for lower disk I/O
log_level = WARN
log_max_size = 5242880
log_max_files = 3

# 1000ms cycle time (recommended for RPi 3B)
cycle_time_ms = 1000

[profinet]
interface = ${PROFINET_INTERFACE}
station_name = wtc-rpi3b
# Watchdog factor for slower hardware
watchdog_factor = 3

[historian]
enabled = true
# 5000ms sample rate reduces disk writes
sample_rate_ms = 5000
retention_days = 30
# Deadband compression to reduce storage
deadband = 0.5
compression = swinging_door

[database]
# SQLite is recommended for RPi 3B (no PostgreSQL)
# Database stored in: /var/lib/water-controller/wtc.db
EOF

cat > "$CONFIG_DIR/environment" << EOF
# Environment variables for Water Treatment Controller
WT_LOG_LEVEL=WARN
WT_CONFIG_DIR=/etc/water-controller
WT_DATA_DIR=/var/lib/water-controller
WT_INTERFACE=${PROFINET_INTERFACE}
EOF

chmod 640 "$CONFIG_DIR"/*.conf "$CONFIG_DIR"/environment
chown root:"$SERVICE_USER" "$CONFIG_DIR"/*.conf "$CONFIG_DIR"/environment

# -----------------------------------------------------------------------------
# Step 7: Install systemd services (controller-only)
# -----------------------------------------------------------------------------

log_info "Installing systemd services..."

# Main controller service
cat > /etc/systemd/system/water-controller.service << 'EOF'
[Unit]
Description=Water Treatment PROFINET Controller
After=network.target

[Service]
Type=simple
User=wtc
Group=wtc
WorkingDirectory=/opt/water-controller
ExecStart=/opt/water-controller/bin/water_treat_controller -c /etc/water-controller/controller.conf
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=water-controller

# Security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/water-controller /var/log/water-controller /dev/shm

# Network capabilities for PROFINET
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN

EnvironmentFile=-/etc/water-controller/environment

[Install]
WantedBy=multi-user.target
EOF

# API service (if installed)
if [ "$INSTALL_API" = true ]; then
    cat > /etc/systemd/system/water-controller-api.service << 'EOF'
[Unit]
Description=Water Treatment Controller API
After=network.target water-controller.service
BindsTo=water-controller.service

[Service]
Type=simple
User=wtc
Group=wtc
WorkingDirectory=/opt/water-controller/web/api
# Single worker for RPi 3B (reduced from 2)
ExecStart=/opt/water-controller/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080 --workers 1
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=water-controller-api

NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/water-controller /var/log/water-controller /dev/shm

Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/etc/water-controller/environment

[Install]
WantedBy=multi-user.target
EOF
fi

systemctl daemon-reload
systemctl enable water-controller.service
[ "$INSTALL_API" = true ] && systemctl enable water-controller-api.service

# -----------------------------------------------------------------------------
# Step 8: Create management script
# -----------------------------------------------------------------------------

cat > /usr/local/bin/wtc-ctl << 'SCRIPT'
#!/bin/bash
case "$1" in
    start)   systemctl start water-controller water-controller-api 2>/dev/null ;;
    stop)    systemctl stop water-controller-api water-controller 2>/dev/null ;;
    restart) systemctl restart water-controller water-controller-api 2>/dev/null ;;
    status)  systemctl status water-controller water-controller-api --no-pager 2>/dev/null ;;
    logs)    journalctl -u water-controller -u water-controller-api -f ;;
    *)       echo "Usage: wtc-ctl {start|stop|restart|status|logs}" ;;
esac
SCRIPT
chmod +x /usr/local/bin/wtc-ctl

# -----------------------------------------------------------------------------
# Step 9: Verify installation
# -----------------------------------------------------------------------------

log_info "Verifying installation..."

if [ -x "$INSTALL_DIR/bin/water_treat_controller" ]; then
    log_info "Controller binary: OK"
else
    log_error "Controller binary not found!"
    exit 1
fi

if [ "$INSTALL_API" = true ] && [ -f "$INSTALL_DIR/venv/bin/uvicorn" ]; then
    log_info "Python API: OK"
fi

# -----------------------------------------------------------------------------
# Complete
# -----------------------------------------------------------------------------

echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Configuration: $CONFIG_DIR/controller.conf"
echo "Data storage:  $DATA_DIR"
echo "Logs:          journalctl -u water-controller -f"
echo ""
echo "Commands:"
echo "  sudo systemctl start water-controller    # Start controller"
echo "  sudo wtc-ctl status                      # Check status"
echo "  sudo wtc-ctl logs                        # View logs"
echo ""
if [ "$INSTALL_API" = true ]; then
echo "API endpoint:  http://$(hostname -I | awk '{print $1}'):8080"
echo "API docs:      http://$(hostname -I | awk '{print $1}'):8080/docs"
echo ""
fi
echo "Edit $CONFIG_DIR/controller.conf to set your PROFINET interface"
echo "and RTU configuration before starting the service."
echo ""
