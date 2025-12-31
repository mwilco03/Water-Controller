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
# Port Configuration - CENTRALIZED
# =============================================================================
# Source the centralized port configuration if available
# See config/ports.env for the single source of truth
#
# All port values should use the WTC_* variables defined below.
# DO NOT hardcode port values elsewhere in the codebase.

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd "$_SCRIPT_DIR/../.." && pwd)"

# Try to load from repository config first (development)
if [[ -f "${_REPO_ROOT}/config/ports.sh" ]]; then
    source "${_REPO_ROOT}/config/ports.sh"
# Then try installed location (production)
elif [[ -f "${INSTALL_DIR}/config/ports.sh" ]]; then
    source "${INSTALL_DIR}/config/ports.sh"
# Fallback to hardcoded defaults if no config file available
else
    export WTC_API_PORT="${WTC_API_PORT:-8000}"
    export WTC_UI_PORT="${WTC_UI_PORT:-8080}"
    export WTC_DB_PORT="${WTC_DB_PORT:-5432}"
    export WTC_PROFINET_UDP_PORT="${WTC_PROFINET_UDP_PORT:-34964}"
    export WTC_MODBUS_TCP_PORT="${WTC_MODBUS_TCP_PORT:-1502}"
fi

# Derived URLs (if not already set)
export WTC_API_URL="${WTC_API_URL:-http://localhost:${WTC_API_PORT}}"
export WTC_UI_URL="${WTC_UI_URL:-http://localhost:${WTC_UI_PORT}}"

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
        log_info "Building HMI user interface..."

        # Check for Node.js
        if ! command -v node &> /dev/null; then
            log_error "Node.js is not installed. HMI build cannot proceed."
            log_error "Install Node.js 18+ and retry: curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt-get install -y nodejs"
            return 1
        fi

        # Check for npm
        if ! command -v npm &> /dev/null; then
            log_error "npm is not installed. HMI build cannot proceed."
            log_error "npm should be included with Node.js. Reinstall Node.js and retry."
            return 1
        fi

        local node_version
        node_version=$(node --version 2>/dev/null)
        log_info "Using Node.js $node_version"

        cd "$INSTALL_DIR/web/ui"

        log_info "Installing npm dependencies (this may take several minutes)..."
        if ! npm install --production=false; then
            log_error "npm install failed. Check network connectivity and disk space."
            cd - > /dev/null
            return 1
        fi

        log_info "Building production bundle..."
        if ! npm run build; then
            log_error "npm build failed. Check for TypeScript or bundling errors above."
            cd - > /dev/null
            return 1
        fi

        # Verify build output exists
        if [ ! -d ".next" ]; then
            log_error "Build completed but .next directory not found. Build may have failed silently."
            cd - > /dev/null
            return 1
        fi

        log_info "HMI build complete: $(find .next -type f | wc -l) files generated"
        cd - > /dev/null
    else
        log_error "UI source not found at $INSTALL_DIR/web/ui. Cannot build HMI."
        return 1
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
    log_info "  3. Access web UI: ${WTC_UI_URL}"
    log_info "  4. API documentation: ${WTC_API_URL}/api/docs"
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
    echo "  ${WTC_UI_URL}"
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
