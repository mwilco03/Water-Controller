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
# Discovery-First Helper Functions
# =============================================================================
# These functions implement the "discovery-first" pattern:
# - Discover state BEFORE assuming failure reasons
# - Capture actual errors instead of swallowing them
# - Report what was DISCOVERED, not what was ASSUMED
# - Provide actionable remediation based on actual cause

# Store last discovery result for detailed error reporting
export _LAST_DISCOVERY_ERROR=""
export _LAST_DISCOVERY_METHOD=""

# Discover Docker accessibility - returns 0 if accessible, 1 if not
# Sets _LAST_DISCOVERY_ERROR with the actual reason for failure
discover_docker() {
    _LAST_DISCOVERY_ERROR=""
    _LAST_DISCOVERY_METHOD=""

    # Step 1: Is docker binary available?
    if ! command -v docker &>/dev/null; then
        _LAST_DISCOVERY_ERROR="Docker binary not found in PATH"
        _LAST_DISCOVERY_METHOD="command -v docker"
        return 1
    fi
    _LAST_DISCOVERY_METHOD="binary found via 'command -v docker'"

    # Step 2: Does the socket exist?
    local socket="/var/run/docker.sock"
    if [[ ! -e "$socket" ]]; then
        _LAST_DISCOVERY_ERROR="Docker socket does not exist at $socket - daemon not installed or not started"
        _LAST_DISCOVERY_METHOD="socket existence check"
        return 1
    fi

    # Step 3: Can we access the socket?
    if [[ ! -r "$socket" ]] || [[ ! -w "$socket" ]]; then
        if [[ $EUID -ne 0 ]]; then
            if ! id -nG 2>/dev/null | grep -qw docker; then
                _LAST_DISCOVERY_ERROR="Permission denied: user '$(whoami)' is not root and not in docker group"
                _LAST_DISCOVERY_METHOD="group membership check (id -nG | grep docker)"
                return 1
            fi
        fi
        _LAST_DISCOVERY_ERROR="Socket exists but not accessible (permissions: $(ls -la "$socket" 2>/dev/null | awk '{print $1}'))"
        _LAST_DISCOVERY_METHOD="socket permission check"
        return 1
    fi

    # Step 4: Can we actually talk to the daemon?
    local docker_error
    if ! docker_error=$(docker info 2>&1); then
        # Parse the actual error
        if [[ "$docker_error" == *"permission denied"* ]]; then
            _LAST_DISCOVERY_ERROR="Permission denied accessing Docker daemon: $docker_error"
        elif [[ "$docker_error" == *"Cannot connect"* ]] || [[ "$docker_error" == *"connection refused"* ]]; then
            _LAST_DISCOVERY_ERROR="Docker daemon not responding (socket exists but daemon may be stopped): $docker_error"
        elif [[ "$docker_error" == *"Is the docker daemon running"* ]]; then
            _LAST_DISCOVERY_ERROR="Docker daemon is not running"
        else
            _LAST_DISCOVERY_ERROR="Docker info failed: $docker_error"
        fi
        _LAST_DISCOVERY_METHOD="docker info command"
        return 1
    fi

    _LAST_DISCOVERY_METHOD="full verification (binary + socket + permissions + daemon response)"
    return 0
}

# Discover Docker Compose accessibility
discover_docker_compose() {
    _LAST_DISCOVERY_ERROR=""
    _LAST_DISCOVERY_METHOD=""

    # First verify Docker itself works
    if ! discover_docker; then
        _LAST_DISCOVERY_ERROR="Docker Compose requires Docker: $_LAST_DISCOVERY_ERROR"
        return 1
    fi

    # Check for docker compose (plugin) or docker-compose (standalone)
    local compose_error
    if docker compose version &>/dev/null; then
        _LAST_DISCOVERY_METHOD="docker compose plugin"
        return 0
    elif command -v docker-compose &>/dev/null; then
        if compose_error=$(docker-compose version 2>&1); then
            _LAST_DISCOVERY_METHOD="docker-compose standalone binary"
            return 0
        else
            _LAST_DISCOVERY_ERROR="docker-compose binary exists but failed: $compose_error"
            _LAST_DISCOVERY_METHOD="docker-compose version check"
            return 1
        fi
    else
        _LAST_DISCOVERY_ERROR="Neither 'docker compose' plugin nor 'docker-compose' standalone found"
        _LAST_DISCOVERY_METHOD="compose availability check"
        return 1
    fi
}

# Discover systemd service state - provides detailed status
# Usage: discover_service_state <service_name>
# Returns: 0 if running, 1 if not
# Sets _LAST_DISCOVERY_ERROR with details
discover_service_state() {
    local service="$1"
    _LAST_DISCOVERY_ERROR=""
    _LAST_DISCOVERY_METHOD=""

    if [[ -z "$service" ]]; then
        _LAST_DISCOVERY_ERROR="No service name provided"
        return 1
    fi

    # Check if systemctl is available
    if ! command -v systemctl &>/dev/null; then
        _LAST_DISCOVERY_ERROR="systemctl not available - not a systemd system?"
        _LAST_DISCOVERY_METHOD="command -v systemctl"
        return 1
    fi

    # Check if service unit exists
    if ! systemctl cat "$service" &>/dev/null; then
        _LAST_DISCOVERY_ERROR="Service unit '$service' does not exist"
        _LAST_DISCOVERY_METHOD="systemctl cat $service"
        return 1
    fi

    # Get detailed status
    local status
    status=$(systemctl is-active "$service" 2>&1)

    case "$status" in
        active)
            _LAST_DISCOVERY_METHOD="systemctl is-active $service"
            return 0
            ;;
        inactive)
            _LAST_DISCOVERY_ERROR="Service '$service' is inactive (stopped)"
            ;;
        failed)
            local fail_reason
            fail_reason=$(systemctl status "$service" 2>&1 | grep -E "(Main PID|Status:|Active:)" | head -3)
            _LAST_DISCOVERY_ERROR="Service '$service' has failed: $fail_reason"
            ;;
        activating)
            _LAST_DISCOVERY_ERROR="Service '$service' is still starting"
            ;;
        deactivating)
            _LAST_DISCOVERY_ERROR="Service '$service' is stopping"
            ;;
        *)
            _LAST_DISCOVERY_ERROR="Service '$service' is in state: $status"
            ;;
    esac

    _LAST_DISCOVERY_METHOD="systemctl is-active $service"
    return 1
}

# Discover Python module availability with detailed error
# Usage: discover_python_module <module_name>
discover_python_module() {
    local module="$1"
    _LAST_DISCOVERY_ERROR=""
    _LAST_DISCOVERY_METHOD=""

    # First check Python itself
    if ! command -v python3 &>/dev/null; then
        _LAST_DISCOVERY_ERROR="python3 not found in PATH"
        _LAST_DISCOVERY_METHOD="command -v python3"
        return 1
    fi

    local python_path python_version import_error
    python_path=$(command -v python3)
    python_version=$(python3 --version 2>&1)

    if ! import_error=$(python3 -c "import $module" 2>&1); then
        if [[ "$import_error" == *"No module named"* ]]; then
            _LAST_DISCOVERY_ERROR="Module '$module' not installed for $python_version at $python_path"
        elif [[ "$import_error" == *"Permission denied"* ]]; then
            _LAST_DISCOVERY_ERROR="Permission denied importing '$module' (check file permissions)"
        else
            _LAST_DISCOVERY_ERROR="Failed to import '$module': $import_error"
        fi
        _LAST_DISCOVERY_METHOD="python3 -c 'import $module'"
        return 1
    fi

    _LAST_DISCOVERY_METHOD="python3 -c 'import $module' using $python_version"
    return 0
}

# Discover PostgreSQL connectivity
# Usage: discover_postgres [host] [port] [user] [database]
discover_postgres() {
    local host="${1:-localhost}"
    local port="${2:-5432}"
    local user="${3:-wtc}"
    local database="${4:-water_treatment}"
    _LAST_DISCOVERY_ERROR=""
    _LAST_DISCOVERY_METHOD=""

    # Check if psql is available
    if ! command -v psql &>/dev/null; then
        _LAST_DISCOVERY_ERROR="psql client not found in PATH"
        _LAST_DISCOVERY_METHOD="command -v psql"
        return 1
    fi

    # Check if port is open
    if command -v ss &>/dev/null; then
        if ! ss -tuln 2>/dev/null | grep -q ":${port} "; then
            _LAST_DISCOVERY_ERROR="PostgreSQL port $port is not listening on $host"
            _LAST_DISCOVERY_METHOD="ss -tuln | grep :$port"
            return 1
        fi
    elif command -v netstat &>/dev/null; then
        if ! netstat -tuln 2>/dev/null | grep -q ":${port} "; then
            _LAST_DISCOVERY_ERROR="PostgreSQL port $port is not listening on $host"
            _LAST_DISCOVERY_METHOD="netstat -tuln | grep :$port"
            return 1
        fi
    fi

    # Try pg_isready if available (doesn't need auth)
    if command -v pg_isready &>/dev/null; then
        local pg_error
        if ! pg_error=$(pg_isready -h "$host" -p "$port" 2>&1); then
            if [[ "$pg_error" == *"no response"* ]]; then
                _LAST_DISCOVERY_ERROR="PostgreSQL at $host:$port not responding"
            elif [[ "$pg_error" == *"rejecting connections"* ]]; then
                _LAST_DISCOVERY_ERROR="PostgreSQL at $host:$port is rejecting connections (starting up?)"
            else
                _LAST_DISCOVERY_ERROR="PostgreSQL check failed: $pg_error"
            fi
            _LAST_DISCOVERY_METHOD="pg_isready -h $host -p $port"
            return 1
        fi
    fi

    _LAST_DISCOVERY_METHOD="PostgreSQL accepting connections at $host:$port"
    return 0
}

# Discover network connectivity to a host
# Usage: discover_network <url_or_host> [timeout_seconds]
discover_network() {
    local target="$1"
    local timeout="${2:-10}"
    _LAST_DISCOVERY_ERROR=""
    _LAST_DISCOVERY_METHOD=""

    if [[ -z "$target" ]]; then
        _LAST_DISCOVERY_ERROR="No target specified"
        return 1
    fi

    # If we're running from a piped curl, network is already proven
    if [[ ! -t 0 ]] && [[ "${BASH_SOURCE[-1]:-}" == "${0}" ]] && [[ "$target" == *"github.com"* ]]; then
        _LAST_DISCOVERY_METHOD="script was piped from remote source - network already verified"
        return 0
    fi

    # Try curl first
    if command -v curl &>/dev/null; then
        local curl_error
        if curl_error=$(curl -fsSL --connect-timeout "$timeout" --max-time "$timeout" "$target" -o /dev/null 2>&1); then
            _LAST_DISCOVERY_METHOD="curl --connect-timeout $timeout to $target"
            return 0
        else
            if [[ "$curl_error" == *"Could not resolve"* ]]; then
                _LAST_DISCOVERY_ERROR="DNS resolution failed for $target"
            elif [[ "$curl_error" == *"Connection refused"* ]]; then
                _LAST_DISCOVERY_ERROR="Connection refused by $target"
            elif [[ "$curl_error" == *"Connection timed out"* ]] || [[ "$curl_error" == *"timed out"* ]]; then
                _LAST_DISCOVERY_ERROR="Connection to $target timed out after ${timeout}s"
            elif [[ "$curl_error" == *"SSL"* ]] || [[ "$curl_error" == *"certificate"* ]]; then
                _LAST_DISCOVERY_ERROR="SSL/TLS error connecting to $target: $curl_error"
            else
                _LAST_DISCOVERY_ERROR="Failed to reach $target: $curl_error"
            fi
            _LAST_DISCOVERY_METHOD="curl to $target"
            return 1
        fi
    fi

    # Fallback to wget
    if command -v wget &>/dev/null; then
        if wget -q --timeout="$timeout" --spider "$target" 2>/dev/null; then
            _LAST_DISCOVERY_METHOD="wget --spider to $target"
            return 0
        fi
    fi

    _LAST_DISCOVERY_ERROR="No curl or wget available to test connectivity"
    _LAST_DISCOVERY_METHOD="tool availability check"
    return 1
}

# Run command and capture error for discovery
# Usage: run_with_discovery <command> [args...]
# Returns command exit code, sets _LAST_DISCOVERY_ERROR on failure
run_with_discovery() {
    local output
    local exit_code

    output=$("$@" 2>&1)
    exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        _LAST_DISCOVERY_ERROR="$output"
        _LAST_DISCOVERY_METHOD="$1 (exit code: $exit_code)"
    else
        _LAST_DISCOVERY_ERROR=""
        _LAST_DISCOVERY_METHOD="$1"
    fi

    return $exit_code
}

# Log a discovered error with context
log_discovered_error() {
    local context="$1"
    log_error "$context"
    if [[ -n "$_LAST_DISCOVERY_ERROR" ]]; then
        log_error "  Cause: $_LAST_DISCOVERY_ERROR"
    fi
    if [[ -n "$_LAST_DISCOVERY_METHOD" ]]; then
        log_info "  Discovered via: $_LAST_DISCOVERY_METHOD"
    fi
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
