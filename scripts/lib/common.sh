#!/bin/bash
#
# Water Treatment Controller - Common Installation Utilities
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file contains shared variables and functions used by installation scripts.
# Source this file from install.sh and install-hmi.sh to avoid duplication.
#

# Prevent multiple sourcing
if [ -n "${_WTC_COMMON_LOADED:-}" ]; then
    return 0
fi
_WTC_COMMON_LOADED=1

# =============================================================================
# Standard Paths
# =============================================================================

export INSTALL_DIR="/opt/water-controller"
export CONFIG_DIR="/etc/water-controller"
export DATA_DIR="/var/lib/water-controller"
export LOG_DIR="/var/log/water-controller"
export SYSTEMD_DIR="/etc/systemd/system"
export BIN_DIR="/usr/local/bin"

# =============================================================================
# Service User Configuration
# =============================================================================

export SERVICE_USER="wtc"
export SERVICE_GROUP="wtc"

# =============================================================================
# Terminal Colors
# =============================================================================

export RED='\033[0;31m'
export GREEN='\033[0;32m'
export YELLOW='\033[1;33m'
export BLUE='\033[0;34m'
export NC='\033[0m'  # No Color

# =============================================================================
# Logging Functions
# =============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${YELLOW}$1${NC}"
}

log_header() {
    echo -e "${BLUE}"
    echo "=========================================="
    echo "  $1"
    echo "=========================================="
    echo -e "${NC}"
}

# =============================================================================
# Utility Functions
# =============================================================================

# Check if running as root
require_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root (sudo $0)"
        exit 1
    fi
}

# Create service user and group
create_service_user() {
    if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
        log_info "Creating service user: $SERVICE_USER"
        useradd --system --user-group --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
        usermod -a -G dialout "$SERVICE_USER"  # For serial port access
    else
        log_info "Service user already exists: $SERVICE_USER"
    fi
}

# Create standard directories
create_directories() {
    log_info "Creating directories..."
    mkdir -p "$INSTALL_DIR"/{bin,lib,web,config}
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$DATA_DIR"/{backups,historian,logs}
    mkdir -p "$LOG_DIR"
}

# Set ownership on data directories
set_permissions() {
    log_info "Setting permissions..."
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
    chmod 755 "$INSTALL_DIR"
    chmod 755 "$DATA_DIR"
    chmod 750 "$CONFIG_DIR"
    chmod 755 "$LOG_DIR"
}

# Setup Python virtual environment
setup_python_venv() {
    local requirements_file="${1:-$INSTALL_DIR/web/api/requirements.txt}"

    log_info "Setting up Python environment..."

    if [ ! -d "$INSTALL_DIR/venv" ]; then
        python3 -m venv "$INSTALL_DIR/venv"
    fi

    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip

    if [ -f "$requirements_file" ]; then
        "$INSTALL_DIR/venv/bin/pip" install -r "$requirements_file"
    else
        # Install minimum requirements if no requirements.txt
        "$INSTALL_DIR/venv/bin/pip" install fastapi uvicorn[standard] pydantic python-jose[cryptography] passlib[bcrypt] psutil
        log_warn "No requirements.txt found, installed minimum dependencies"
    fi
}

# Build Node.js UI
build_nodejs_ui() {
    if [ -d "$INSTALL_DIR/web/ui" ] && [ -f "$INSTALL_DIR/web/ui/package.json" ]; then
        log_info "Installing Node.js dependencies..."
        cd "$INSTALL_DIR/web/ui"
        if command -v npm &> /dev/null; then
            npm install --production=false
            npm run build
            log_info "Built UI application"
        else
            log_warn "npm not found, skipping UI build"
            log_warn "Install Node.js and run 'npm run build' manually"
        fi
        cd - > /dev/null
    fi
}

# Create default configuration files
create_default_config() {
    log_info "Creating default configuration files..."

    if [ ! -f "$CONFIG_DIR/controller.conf" ]; then
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

    chmod 640 "$CONFIG_DIR"/*.conf "$CONFIG_DIR"/environment 2>/dev/null || true
    chown root:"$SERVICE_GROUP" "$CONFIG_DIR"/*.conf "$CONFIG_DIR"/environment 2>/dev/null || true
}

# Install systemd services
install_systemd_services() {
    local source_dir="$1"

    log_info "Installing systemd services..."
    cp "$source_dir"/systemd/*.service "$SYSTEMD_DIR/"
    systemctl daemon-reload
}

# Enable systemd services
enable_services() {
    log_info "Enabling services..."
    systemctl enable water-controller.service
    systemctl enable water-controller-api.service
    systemctl enable water-controller-ui.service
}

# Create wtc-ctl management script
create_management_script() {
    log_info "Creating management scripts..."
    cat > "$BIN_DIR/wtc-ctl" << 'EOF'
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
    chmod +x "$BIN_DIR/wtc-ctl"
}

# Print installation complete message
print_completion_message() {
    log_info "Installation complete!"
    log_info ""
    log_info "Next steps:"
    log_info "  1. Edit configuration: $CONFIG_DIR/controller.conf"
    log_info "  2. Start services: systemctl start water-controller"
    log_info "  3. Access web UI: http://localhost:8080"
    log_info "  4. API documentation: http://localhost:8000/api/docs"
    log_info ""
    log_info "Management commands:"
    log_info "  wtc-ctl start|stop|restart|status|logs|backup|restore"
}

# Print HMI-specific completion message
print_hmi_completion_message() {
    echo ""
    log_header "Installation Complete!"
    echo ""
    echo "Service Status:"
    echo "  The water-controller-hmi service has been started."
    echo "  Check status: sudo systemctl status water-controller-hmi"
    echo ""
    echo "Access the HMI at:"
    echo "  http://localhost:8080"
    echo ""
    echo "Default credentials:"
    echo "  Username: admin"
    echo "  Password: H2OhYeah!"
    echo ""
    echo "Management commands:"
    echo "  sudo systemctl restart water-controller-hmi  # Restart"
    echo "  sudo systemctl stop water-controller-hmi     # Stop"
    echo "  sudo journalctl -u water-controller-hmi -f   # View logs"
    echo ""
    log_warn "IMPORTANT: First login will initialize the database."
    echo ""
}
