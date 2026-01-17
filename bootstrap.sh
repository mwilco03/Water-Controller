#!/bin/bash
# =============================================================================
# Water-Controller Bootstrap Script
# =============================================================================
# One-liner entry point for installation, upgrade, and removal.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | bash
#   curl -fsSL .../bootstrap.sh | bash -s -- install
#   curl -fsSL .../bootstrap.sh | bash -s -- upgrade
#   curl -fsSL .../bootstrap.sh | bash -s -- remove
#   curl -fsSL .../bootstrap.sh | bash -s -- install --branch develop
#   curl -fsSL .../bootstrap.sh | bash -s -- upgrade --dry-run
#   curl -fsSL .../bootstrap.sh | bash -s -- remove --keep-config
#
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
# =============================================================================

set -euo pipefail

# =============================================================================
# Constants
# =============================================================================

readonly BOOTSTRAP_VERSION="1.1.0"
readonly REPO_URL="https://github.com/mwilco03/Water-Controller.git"
readonly REPO_RAW_URL="https://raw.githubusercontent.com/mwilco03/Water-Controller"
readonly INSTALL_DIR="/opt/water-controller"
readonly VERSION_FILE="$INSTALL_DIR/.version"
readonly MANIFEST_FILE="$INSTALL_DIR/.manifest"
readonly CONFIG_DIR="/etc/water-controller"
readonly DATA_DIR="/var/lib/water-controller"
readonly LOG_DIR="/var/log/water-controller"
readonly BACKUP_DIR="/var/backups/water-controller"
readonly BOOTSTRAP_LOG="/var/log/water-controller-bootstrap.log"
readonly MIN_DISK_SPACE_MB=2048
readonly REQUIRED_TOOLS=("git" "curl" "systemctl")
readonly CHECKSUM_FILE="SHA256SUMS"

# Global state
QUIET_MODE="false"
DEPLOYMENT_MODE=""  # baremetal or docker
CLEANUP_DIRS=()  # Stack of directories to clean up

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# =============================================================================
# Logging Functions
# =============================================================================

# Initialize log file
init_logging() {
    local log_dir
    log_dir=$(dirname "$BOOTSTRAP_LOG")
    if [[ -w "$log_dir" ]] || [[ $EUID -eq 0 ]]; then
        if [[ $EUID -ne 0 ]]; then
            sudo mkdir -p "$log_dir" 2>/dev/null || true
            sudo touch "$BOOTSTRAP_LOG" 2>/dev/null || true
            sudo chmod 644 "$BOOTSTRAP_LOG" 2>/dev/null || true
        else
            mkdir -p "$log_dir" 2>/dev/null || true
            touch "$BOOTSTRAP_LOG" 2>/dev/null || true
        fi
    fi
}

# Write to log file
write_log() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    if [[ -w "$BOOTSTRAP_LOG" ]] || [[ $EUID -eq 0 ]]; then
        if [[ $EUID -ne 0 ]]; then
            echo "[$timestamp] [$level] $message" | sudo tee -a "$BOOTSTRAP_LOG" >/dev/null 2>&1 || true
        else
            echo "[$timestamp] [$level] $message" >> "$BOOTSTRAP_LOG" 2>/dev/null || true
        fi
    fi
}

log_info() {
    write_log "INFO" "$1"
    if [[ "$QUIET_MODE" != "true" ]]; then
        echo -e "${GREEN}[INFO]${NC} $1" >&2
    fi
}

log_warn() {
    write_log "WARN" "$1"
    if [[ "$QUIET_MODE" != "true" ]]; then
        echo -e "${YELLOW}[WARN]${NC} $1" >&2
    fi
}

log_error() {
    write_log "ERROR" "$1"
    # Errors always shown even in quiet mode
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_step() {
    write_log "STEP" "$1"
    if [[ "$QUIET_MODE" != "true" ]]; then
        echo -e "${BLUE}[STEP]${NC} $1" >&2
    fi
}

log_debug() {
    write_log "DEBUG" "$1"
    # Debug only goes to log file, never to console
}

# =============================================================================
# Helper Functions
# =============================================================================

# Run command with appropriate privileges
run_privileged() {
    if [[ $EUID -ne 0 ]]; then
        sudo "$@"
    else
        "$@"
    fi
}

# Run command with privileges and environment preserved
run_privileged_env() {
    if [[ $EUID -ne 0 ]]; then
        sudo -E "$@"
    else
        "$@"
    fi
}

# Stacking cleanup handler - cleans up all registered directories
cleanup_all() {
    local dir
    for dir in "${CLEANUP_DIRS[@]}"; do
        if [[ -n "$dir" ]] && [[ -d "$dir" ]]; then
            log_debug "Cleaning up: $dir"
            rm -rf "$dir" 2>/dev/null || true
        fi
    done
    CLEANUP_DIRS=()
}

# Register a directory for cleanup (supports stacking)
register_cleanup() {
    local dir="$1"
    CLEANUP_DIRS+=("$dir")
    # Set trap only once
    trap cleanup_all EXIT
}

# Prompt user with /dev/tty fallback for piped execution
prompt_user() {
    local prompt="$1"
    local response=""

    # Try /dev/tty first (works when piped), fall back to stdin
    if [[ -t 0 ]]; then
        # stdin is a terminal
        read -r -p "$prompt" response
    elif [[ -e /dev/tty ]]; then
        # stdin is piped, but /dev/tty exists
        read -r -p "$prompt" response < /dev/tty
    else
        # No interactive input available
        log_warn "No interactive terminal available, assuming 'no'"
        response="n"
    fi

    echo "$response"
}

# =============================================================================
# System Detection
# =============================================================================

# Detect current system state
# Returns: fresh | installed | corrupted
detect_system_state() {
    if [[ ! -d "$INSTALL_DIR" ]]; then
        echo "fresh"
        return 0
    fi

    # Check for version file
    if [[ -f "$VERSION_FILE" ]]; then
        # Validate version file is valid JSON
        if command -v jq &>/dev/null && jq -e . "$VERSION_FILE" &>/dev/null; then
            echo "installed"
            return 0
        elif grep -q '"commit_sha"' "$VERSION_FILE" 2>/dev/null; then
            # Fallback for systems without jq
            echo "installed"
            return 0
        fi
    fi

    # Check for partial installation indicators
    if [[ -d "$INSTALL_DIR/venv" ]] || [[ -d "$INSTALL_DIR/web" ]] || \
       [[ -d "$INSTALL_DIR/app" ]] || [[ -f "/etc/systemd/system/water-controller.service" ]]; then
        echo "corrupted"
        return 0
    fi

    # Directory exists but empty or unknown
    # Use find instead of ls for more reliable empty check
    local file_count
    file_count=$(find "$INSTALL_DIR" -maxdepth 1 -mindepth 1 2>/dev/null | wc -l)
    if [[ "$file_count" -eq 0 ]]; then
        echo "fresh"
    else
        echo "corrupted"
    fi
}

# Get installed version info
get_installed_version() {
    if [[ ! -f "$VERSION_FILE" ]]; then
        echo ""
        return 1
    fi

    if command -v jq &>/dev/null; then
        jq -r '.version // "unknown"' "$VERSION_FILE" 2>/dev/null || echo "unknown"
    else
        grep -oP '"version"\s*:\s*"\K[^"]+' "$VERSION_FILE" 2>/dev/null || echo "unknown"
    fi
}

# Get installed commit SHA
get_installed_sha() {
    if [[ ! -f "$VERSION_FILE" ]]; then
        echo ""
        return 1
    fi

    if command -v jq &>/dev/null; then
        jq -r '.commit_sha // ""' "$VERSION_FILE" 2>/dev/null
    else
        grep -oP '"commit_sha"\s*:\s*"\K[^"]+' "$VERSION_FILE" 2>/dev/null
    fi
}

# =============================================================================
# Validation Functions
# =============================================================================

# Check if running as root or with sudo capability
check_root() {
    if [[ $EUID -ne 0 ]]; then
        if ! command -v sudo &>/dev/null; then
            log_error "sudo is not installed and not running as root"
            log_info "Run with: su -c 'curl -fsSL ... | bash'"
            return 1
        fi

        # Test actual sudo capability by running a harmless command
        # This handles both passwordless sudo and cached credentials
        if sudo -v 2>/dev/null; then
            log_info "Will use sudo for privileged operations"
            return 0
        else
            log_error "This script must be run as root or with sudo capability"
            log_info "Run with: sudo bash -c 'curl -fsSL ... | bash'"
            return 1
        fi
    fi
    return 0
}

# Check required tools are present
check_required_tools() {
    local missing=()
    local tool

    for tool in "${REQUIRED_TOOLS[@]}"; do
        if ! command -v "$tool" &>/dev/null; then
            missing+=("$tool")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing[*]}"
        log_info "Install with: sudo apt-get install ${missing[*]}"
        return 1
    fi

    log_debug "All required tools present: ${REQUIRED_TOOLS[*]}"
    return 0
}

# Check network connectivity to GitHub with retry
check_network() {
    log_info "Checking network connectivity..."

    local max_retries=3
    local retry_delay=2
    local attempt

    for ((attempt=1; attempt<=max_retries; attempt++)); do
        if curl -fsSL --connect-timeout 10 --retry 2 "https://github.com" &>/dev/null; then
            log_debug "Network connectivity confirmed on attempt $attempt"
            return 0
        fi

        if [[ $attempt -lt $max_retries ]]; then
            log_warn "Network check failed (attempt $attempt/$max_retries), retrying in ${retry_delay}s..."
            sleep "$retry_delay"
            retry_delay=$((retry_delay * 2))
        fi
    done

    log_error "Cannot reach GitHub after $max_retries attempts. Check your network connection."
    return 1
}

# Install Docker on the host system
install_docker() {
    log_step "Installing Docker..."

    # Detect OS
    if [[ ! -f /etc/os-release ]]; then
        log_error "Cannot detect OS distribution"
        return 1
    fi

    source /etc/os-release
    local distro="${ID:-unknown}"
    local version="${VERSION_CODENAME:-${VERSION_ID}}"

    log_info "Detected OS: $distro $version"

    case "$distro" in
        ubuntu|debian)
            log_info "Installing Docker using official repository method..."

            # Remove old versions
            run_privileged apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

            # Install prerequisites
            run_privileged apt-get update
            run_privileged apt-get install -y \
                ca-certificates \
                curl \
                gnupg \
                lsb-release

            # Add Docker GPG key
            run_privileged install -m 0755 -d /etc/apt/keyrings
            if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
                curl -fsSL "https://download.docker.com/linux/$distro/gpg" | \
                    run_privileged gpg --dearmor -o /etc/apt/keyrings/docker.gpg
                run_privileged chmod a+r /etc/apt/keyrings/docker.gpg
            fi

            # Add Docker repository
            local arch
            arch=$(dpkg --print-architecture)
            echo "deb [arch=$arch signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$distro $version stable" | \
                run_privileged tee /etc/apt/sources.list.d/docker.list > /dev/null

            # Install Docker
            run_privileged apt-get update
            run_privileged apt-get install -y \
                docker-ce \
                docker-ce-cli \
                containerd.io \
                docker-buildx-plugin \
                docker-compose-plugin

            ;;

        fedora|rhel|centos)
            log_info "Installing Docker using official repository method..."

            # Remove old versions
            run_privileged dnf remove -y docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine 2>/dev/null || true

            # Install prerequisites
            run_privileged dnf -y install dnf-plugins-core

            # Add Docker repository
            run_privileged dnf config-manager --add-repo "https://download.docker.com/linux/fedora/docker-ce.repo"

            # Install Docker
            run_privileged dnf install -y \
                docker-ce \
                docker-ce-cli \
                containerd.io \
                docker-buildx-plugin \
                docker-compose-plugin

            ;;

        *)
            log_error "Unsupported distribution: $distro"
            log_info "Please install Docker manually: https://docs.docker.com/engine/install/"
            return 1
            ;;
    esac

    # Start and enable Docker service
    log_info "Starting Docker service..."
    run_privileged systemctl start docker
    run_privileged systemctl enable docker

    # Verify installation
    if command -v docker &>/dev/null && docker compose version &>/dev/null; then
        log_info "Docker installed successfully"
        docker --version
        docker compose version
        return 0
    else
        log_error "Docker installation verification failed"
        return 1
    fi
}

# Validate Docker requirements for docker deployment mode
validate_docker_requirements() {
    log_info "Validating Docker requirements..."

    if ! command -v docker &>/dev/null; then
        log_warn "Docker is not installed"

        # Check if running in interactive mode
        if [[ -t 0 ]] || [[ -e /dev/tty ]]; then
            # Interactive: prompt user
            local response
            response=$(prompt_user "Would you like to install Docker now? [Y/n] ")
            if [[ "$response" =~ ^[Nn]$ ]]; then
                log_error "Docker is required for docker deployment mode"
                log_info "Install Docker manually: https://docs.docker.com/engine/install/"
                return 1
            fi
        else
            # Non-interactive (piped execution): install automatically
            log_info "Non-interactive mode detected, installing Docker automatically..."
        fi

        # Install Docker
        if ! install_docker; then
            log_error "Docker installation failed"
            return 1
        fi
    fi

    if ! docker compose version &>/dev/null; then
        log_error "Docker Compose is not available"
        log_info "Install Docker Compose plugin or standalone"
        return 1
    fi

    # Check if docker daemon is running
    if ! docker info &>/dev/null; then
        log_warn "Docker daemon is not running"
        log_info "Starting Docker daemon..."
        run_privileged systemctl start docker

        # Verify it started
        if ! docker info &>/dev/null; then
            log_error "Failed to start Docker daemon"
            log_info "Start Docker manually: sudo systemctl start docker"
            return 1
        fi
    fi

    log_info "Docker requirements validated"
    return 0
}

# Generate secure random password
generate_password() {
    local length="${1:-24}"

    # Try openssl first (most common)
    if command -v openssl &>/dev/null; then
        openssl rand -base64 "$length" | tr -d '\n'
        return 0
    fi

    # Fall back to /dev/urandom
    if [[ -r /dev/urandom ]]; then
        tr -dc 'A-Za-z0-9!@#$%^&*' < /dev/urandom | head -c "$length"
        return 0
    fi

    # Last resort: use date and random
    echo "$(date +%s)${RANDOM}${RANDOM}" | sha256sum | head -c "$length"
}

# Wait for container health checks
wait_for_health_checks() {
    local docker_dir="$1"
    local max_wait="${2:-120}"  # 2 minutes default

    log_step "Waiting for services to become healthy..."

    local start_time
    start_time=$(date +%s)
    local timeout_time=$((start_time + max_wait))

    local services=("wtc-database" "wtc-api" "wtc-ui" "wtc-loki" "wtc-grafana")
    local healthy_services=()

    while true; do
        local all_healthy=true
        healthy_services=()

        for svc in "${services[@]}"; do
            local health
            health=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "starting")

            if [[ "$health" == "healthy" ]]; then
                healthy_services+=("$svc")
            else
                all_healthy=false
            fi
        done

        if [[ "$all_healthy" == "true" ]]; then
            log_info "All services are healthy (${#healthy_services[@]}/${#services[@]})"
            return 0
        fi

        local current_time
        current_time=$(date +%s)
        if [[ "$current_time" -ge "$timeout_time" ]]; then
            log_warn "Timeout waiting for services to become healthy"
            log_info "Healthy services: ${#healthy_services[@]}/${#services[@]}"
            return 1
        fi

        log_debug "Waiting for services... (${#healthy_services[@]}/${#services[@]} healthy)"
        sleep 5
    done
}

# Verify endpoints are responding
verify_endpoints() {
    local api_port="${WTC_API_PORT:-8000}"
    local ui_port="${WTC_UI_PORT:-8080}"
    local grafana_port="${WTC_GRAFANA_PORT:-3000}"

    log_step "Verifying service endpoints..."

    local errors=0

    # Check API health endpoint
    if curl -sf "http://localhost:$api_port/health" >/dev/null 2>&1; then
        log_info "✓ API endpoint responding (port $api_port)"
    else
        log_error "✗ API endpoint not responding (port $api_port)"
        errors=$((errors + 1))
    fi

    # Check UI
    if curl -sf "http://localhost:$ui_port" >/dev/null 2>&1; then
        log_info "✓ UI endpoint responding (port $ui_port)"
    else
        log_error "✗ UI endpoint not responding (port $ui_port)"
        errors=$((errors + 1))
    fi

    # Check Grafana
    if curl -sf "http://localhost:$grafana_port/api/health" >/dev/null 2>&1; then
        log_info "✓ Grafana endpoint responding (port $grafana_port)"
    else
        log_warn "⚠ Grafana endpoint not responding yet (port $grafana_port)"
    fi

    return $errors
}

# Create systemd service for auto-start
create_systemd_service() {
    local docker_dir="$1"
    local service_file="/etc/systemd/system/water-controller-docker.service"
    local env_file="$docker_dir/.env"

    log_step "Creating systemd service for auto-start on boot..."

    # Create .env file with required environment variables for docker compose
    log_info "Creating environment file: $env_file"
    {
        echo "# Water-Controller Docker Environment Variables"
        echo "# Auto-generated by bootstrap.sh"
        echo "# $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo ""
        echo "GRAFANA_PASSWORD=${GRAFANA_PASSWORD}"
        echo "DB_PASSWORD=${DB_PASSWORD}"
        echo ""
        echo "# Port configuration (sourced from ports.env if exists)"
        echo "WTC_API_PORT=${WTC_API_PORT:-8000}"
        echo "WTC_UI_PORT=${WTC_UI_PORT:-8080}"
        echo "WTC_GRAFANA_PORT=${WTC_GRAFANA_PORT:-3000}"
        echo "WTC_DB_PORT=${WTC_DB_PORT:-5432}"
        echo "WTC_DOCKER_UI_INTERNAL_PORT=${WTC_DOCKER_UI_INTERNAL_PORT:-3000}"
    } | run_privileged tee "$env_file" > /dev/null
    run_privileged chmod 600 "$env_file"

    local service_content
    service_content=$(cat <<EOF
[Unit]
Description=Water-Controller Docker Stack
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$docker_dir
EnvironmentFile=$env_file
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
EOF
)

    echo "$service_content" | run_privileged tee "$service_file" > /dev/null

    # Enable service
    run_privileged systemctl daemon-reload
    run_privileged systemctl enable water-controller-docker.service

    log_info "Systemd service created and enabled for auto-start"
}

# Create quick commands helper script
create_quick_commands() {
    local install_dir="$1"
    local commands_file="$install_dir/docker-commands.sh"

    log_step "Creating quick commands helper..."

    local commands_content
    commands_content=$(cat <<'EOF'
#!/bin/bash
# Water-Controller Docker Quick Commands

DOCKER_DIR="/opt/water-controller/docker"

alias wtc-status='docker compose -f $DOCKER_DIR/docker-compose.yml ps'
alias wtc-logs='docker compose -f $DOCKER_DIR/docker-compose.yml logs -f'
alias wtc-restart='docker compose -f $DOCKER_DIR/docker-compose.yml restart'
alias wtc-stop='docker compose -f $DOCKER_DIR/docker-compose.yml stop'
alias wtc-start='docker compose -f $DOCKER_DIR/docker-compose.yml start'
alias wtc-down='docker compose -f $DOCKER_DIR/docker-compose.yml down'
alias wtc-pull='docker compose -f $DOCKER_DIR/docker-compose.yml pull'
alias wtc-rebuild='docker compose -f $DOCKER_DIR/docker-compose.yml up -d --build'

echo "Water-Controller Docker Commands loaded:"
echo "  wtc-status   - Show container status"
echo "  wtc-logs     - Follow container logs"
echo "  wtc-restart  - Restart all containers"
echo "  wtc-stop     - Stop all containers"
echo "  wtc-start    - Start all containers"
echo "  wtc-down     - Stop and remove containers"
echo "  wtc-pull     - Pull latest images"
echo "  wtc-rebuild  - Rebuild and restart containers"
EOF
)

    echo "$commands_content" | run_privileged tee "$commands_file" > /dev/null
    run_privileged chmod +x "$commands_file"

    log_info "Quick commands helper created: $commands_file"
    log_info "To use: source $commands_file"
}

# Run Docker deployment
do_docker_install() {
    log_step "Starting Docker deployment..."

    # Pre-deployment checks (non-blocking, warnings only)
    check_docker_resources || log_warn "Resource checks failed, proceeding anyway..."
    check_port_conflicts || log_warn "Port conflicts detected, proceeding anyway..."

    # Find docker directory
    local docker_dir=""
    local repo_dir=""
    if [[ -d "./docker" ]]; then
        docker_dir="./docker"
        repo_dir="."
    elif [[ -d "/opt/water-controller/docker" ]]; then
        docker_dir="/opt/water-controller/docker"
        repo_dir="/opt/water-controller"
    else
        # Clone repo first to get docker files
        local staging_dir
        staging_dir=$(create_staging_dir "docker-install")
        register_cleanup "$staging_dir"

        clone_to_staging "$staging_dir" "main" || return 1
        docker_dir="$staging_dir/repo/docker"
        repo_dir="$staging_dir/repo"

        # Copy to persistent location (including hidden files)
        log_info "Installing to /opt/water-controller..."
        run_privileged mkdir -p /opt/water-controller
        run_privileged cp -a "$staging_dir/repo/." /opt/water-controller/
        docker_dir="/opt/water-controller/docker"
        repo_dir="/opt/water-controller"
    fi

    log_info "Using Docker directory: $docker_dir"

    # Source ports.env if it exists
    local ports_env_file=""
    if [[ -f "$docker_dir/../config/ports.env" ]]; then
        ports_env_file="$docker_dir/../config/ports.env"
    elif [[ -f "./config/ports.env" ]]; then
        ports_env_file="./config/ports.env"
    fi

    if [[ -n "$ports_env_file" ]]; then
        log_info "Loading port configuration from: $ports_env_file"
        # Export variables from ports.env
        set -a
        source "$ports_env_file"
        set +a
    fi

    # Generate required passwords if not already set
    if [[ -z "${GRAFANA_PASSWORD:-}" ]]; then
        log_info "Generating secure Grafana password..."
        export GRAFANA_PASSWORD=$(generate_password 24)
    fi

    if [[ -z "${DB_PASSWORD:-}" ]]; then
        log_info "Generating secure database password..."
        export DB_PASSWORD=$(generate_password 32)
    fi

    # Save passwords to PERSISTENT location
    local creds_file="/opt/water-controller/config/.docker-credentials"
    log_info "Saving credentials to: $creds_file"
    run_privileged mkdir -p "$(dirname "$creds_file")"
    {
        echo "# Water-Controller Docker Credentials"
        echo "# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "# KEEP THIS FILE SECURE - Contains passwords"
        echo ""
        echo "GRAFANA_PASSWORD=$GRAFANA_PASSWORD"
        echo "DB_PASSWORD=$DB_PASSWORD"
        echo ""
        echo "# Grafana URL: http://localhost:\${WTC_GRAFANA_PORT:-3000}"
        echo "# Grafana User: admin"
        echo "# Grafana Password: (see above)"
    } | run_privileged tee "$creds_file" > /dev/null
    run_privileged chmod 600 "$creds_file"

    # Build images with visible progress
    log_step "Building Docker images (this may take 5-10 minutes)..."
    log_info "Building: api, ui, controller (3 images)"
    (
        cd "$docker_dir" || exit 1
        export GRAFANA_PASSWORD="$GRAFANA_PASSWORD"
        export DB_PASSWORD="$DB_PASSWORD"

        docker compose build --no-cache --progress=plain 2>&1 | while IFS= read -r line; do
            # Show meaningful build steps and progress
            if echo "$line" | grep -qE "Building|FROM|Step [0-9]+|writing image|FINISHED"; then
                echo "[BUILD] $line" >&2
            elif echo "$line" | grep -qE "=> \["; then
                # Show layer progress indicators
                echo "[BUILD] $line" >&2
            elif echo "$line" | grep -qiE "error|ERROR|failed|FAILED|posix-ipc|Python\.h|fatal"; then
                # Show error messages and posix-ipc related output
                echo "[BUILD ERROR] $line" >&2
            elif echo "$line" | grep -qE "Building wheel|pip install|gcc|collecting"; then
                # Show pip/gcc activity for debugging
                echo "[BUILD] $line" >&2
            fi
        done
    ) || {
        log_error "Docker image build failed"
        log_info "Check logs above for build errors"
        log_info "Common issues:"
        log_info "  - Missing build dependencies (should be auto-installed)"
        log_info "  - Network connectivity (required for package downloads)"
        log_info "  - Insufficient disk space"
        return 1
    }

    # Start containers
    log_step "Starting containers..."
    (
        cd "$docker_dir" || exit 1
        export GRAFANA_PASSWORD="$GRAFANA_PASSWORD"
        export DB_PASSWORD="$DB_PASSWORD"

        docker compose up -d
    )

    local result=$?
    if [[ $result -ne 0 ]]; then
        log_error "Docker deployment failed"
        return $result
    fi

    # Wait for health checks
    wait_for_health_checks "$docker_dir" 120

    # Verify endpoints
    verify_endpoints

    # Fix database authentication if needed
    log_step "Ensuring database authentication is configured..."
    if [[ -x "$INSTALL_DIR/scripts/fix-database-auth.sh" ]]; then
        "$INSTALL_DIR/scripts/fix-database-auth.sh" || log_warn "Database auth fix had warnings (check logs)"
    else
        log_warn "Database auth fix script not found, skipping"
    fi

    # Run comprehensive validation
    log_step "Running deployment validation..."
    if [[ -x "$INSTALL_DIR/scripts/validate-deployment.sh" ]]; then
        if "$INSTALL_DIR/scripts/validate-deployment.sh"; then
            log_info "✓ Deployment validation passed"
        else
            log_warn "⚠ Deployment validation had failures (see above)"
        fi
    else
        log_warn "Validation script not found, skipping comprehensive validation"
    fi

    # Create systemd service for auto-start
    create_systemd_service "$docker_dir"

    # Create quick commands helper
    create_quick_commands "/opt/water-controller"

    # Display deployment summary
    log_info ""
    log_info "╔════════════════════════════════════════════════════════════════╗"
    log_info "║          WATER-CONTROLLER DEPLOYMENT SUMMARY                  ║"
    log_info "╚════════════════════════════════════════════════════════════════╝"
    log_info ""
    log_info "✓ Docker installed: $(docker --version | cut -d' ' -f3 | tr -d ',')"
    log_info "✓ Docker Compose: $(docker compose version --short)"
    log_info "✓ Containers started successfully"
    log_info "✓ Auto-start enabled (systemd service)"
    log_info ""
    log_info "═══ ACCESS POINTS ═══"
    local ip_addr
    ip_addr=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
    log_info "  Web UI:      http://$ip_addr:${WTC_UI_PORT:-8080}"
    log_info "  API Docs:    http://$ip_addr:${WTC_API_PORT:-8000}/docs"
    log_info "  API Health:  http://$ip_addr:${WTC_API_PORT:-8000}/health"
    log_info "  Grafana:     http://$ip_addr:${WTC_GRAFANA_PORT:-3000}"
    log_info ""
    log_info "═══ CREDENTIALS ═══"
    log_info "  Grafana User:     admin"
    log_info "  Grafana Password: $GRAFANA_PASSWORD"
    log_info "  Credentials File: $creds_file"
    log_info ""
    log_info "═══ MANAGEMENT COMMANDS ═══"
    log_info "  Status:  docker compose -f $docker_dir/docker-compose.yml ps"
    log_info "  Logs:    docker compose -f $docker_dir/docker-compose.yml logs -f"
    log_info "  Restart: sudo systemctl restart water-controller-docker"
    log_info "  Stop:    sudo systemctl stop water-controller-docker"
    log_info ""
    log_info "  Quick commands: source /opt/water-controller/docker-commands.sh"
    log_info ""
    log_info "═══ TROUBLESHOOTING ═══"
    log_info "  Validate:  $INSTALL_DIR/scripts/validate-deployment.sh"
    log_info "  Fix Auth:  $INSTALL_DIR/scripts/fix-database-auth.sh"
    log_info "  Guide:     $INSTALL_DIR/docs/DEPLOYMENT_TROUBLESHOOTING.md"
    log_info ""
    log_info "═══ NEXT STEPS ═══"
    log_info "  1. Browse to http://$ip_addr:${WTC_UI_PORT:-8080}"
    log_info "  2. Save your Grafana password securely"
    log_info "  3. Configure firewall if accessing remotely"
    log_info "  4. Change default admin password (admin/admin)"
    log_info ""

    return 0
}

# Check disk space
check_disk_space() {
    local target_dir="${1:-/opt}"
    local required_mb="${2:-$MIN_DISK_SPACE_MB}"

    # Get parent directory if target doesn't exist
    while [[ ! -d "$target_dir" ]] && [[ "$target_dir" != "/" ]]; do
        target_dir="$(dirname "$target_dir")"
    done

    local available_mb
    available_mb=$(df -m "$target_dir" 2>/dev/null | awk 'NR==2 {print $4}')

    if [[ -z "$available_mb" ]] || [[ "$available_mb" -lt "$required_mb" ]]; then
        log_error "Insufficient disk space: ${available_mb:-0}MB available, ${required_mb}MB required"
        return 1
    fi

    log_info "Disk space check passed: ${available_mb}MB available"
    return 0
}

# Check system resources for Docker deployment
check_docker_resources() {
    log_step "Checking system resources..."

    local errors=0

    # Check RAM (minimum 2GB, recommended 4GB)
    local total_ram_mb
    total_ram_mb=$(free -m 2>/dev/null | awk 'NR==2 {print $2}')

    if [[ -n "$total_ram_mb" ]]; then
        if [[ "$total_ram_mb" -lt 2048 ]]; then
            log_error "Insufficient RAM: ${total_ram_mb}MB detected, 2048MB minimum required"
            errors=$((errors + 1))
        elif [[ "$total_ram_mb" -lt 4096 ]]; then
            log_warn "Low RAM: ${total_ram_mb}MB detected, 4096MB recommended for optimal performance"
        else
            log_info "RAM check passed: ${total_ram_mb}MB available"
        fi
    fi

    # Check CPU cores (minimum 2, recommended 4)
    local cpu_cores
    cpu_cores=$(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null || echo "0")

    if [[ "$cpu_cores" -lt 2 ]]; then
        log_error "Insufficient CPU cores: ${cpu_cores} detected, 2 minimum required"
        errors=$((errors + 1))
    elif [[ "$cpu_cores" -lt 4 ]]; then
        log_warn "Low CPU cores: ${cpu_cores} detected, 4 recommended for optimal performance"
    else
        log_info "CPU check passed: ${cpu_cores} cores available"
    fi

    # Check disk space (minimum 10GB for Docker images + data)
    local available_gb
    available_gb=$(df -BG / 2>/dev/null | awk 'NR==2 {print $4}' | tr -d 'G')

    if [[ -n "$available_gb" ]] && [[ "$available_gb" -lt 10 ]]; then
        log_error "Insufficient disk space: ${available_gb}GB available, 10GB minimum required for Docker deployment"
        errors=$((errors + 1))
    elif [[ -n "$available_gb" ]]; then
        log_info "Disk space check passed: ${available_gb}GB available"
    fi

    if [[ "$errors" -gt 0 ]]; then
        log_error "Resource checks failed. System does not meet minimum requirements."
        return 1
    fi

    return 0
}

# Check if ports are available
check_port_conflicts() {
    log_step "Checking for port conflicts..."

    local ports_to_check=(
        "${WTC_API_PORT:-8000}:API"
        "${WTC_UI_PORT:-8080}:UI"
        "${WTC_GRAFANA_PORT:-3000}:Grafana"
        "${WTC_DB_PORT:-5432}:Database"
    )

    local conflicts=()
    local port_desc
    local port

    for port_desc in "${ports_to_check[@]}"; do
        port="${port_desc%%:*}"
        local desc="${port_desc##*:}"

        # Check if port is in use
        if command -v ss &>/dev/null; then
            if ss -tuln 2>/dev/null | grep -q ":$port "; then
                conflicts+=("$port ($desc)")
            fi
        elif command -v netstat &>/dev/null; then
            if netstat -tuln 2>/dev/null | grep -q ":$port "; then
                conflicts+=("$port ($desc)")
            fi
        fi
    done

    if [[ ${#conflicts[@]} -gt 0 ]]; then
        log_error "Port conflicts detected. The following ports are already in use:"
        for conflict in "${conflicts[@]}"; do
            log_error "  - Port $conflict"
        done
        log_info "Stop services using these ports or modify config/ports.env to use different ports"
        return 1
    fi

    log_info "Port conflict check passed: all ports available"
    return 0
}

# Run all validation checks
validate_environment() {
    log_step "Validating environment..."

    check_root || return 1
    check_required_tools || return 1
    check_network || return 1
    check_disk_space "/opt" "$MIN_DISK_SPACE_MB" || return 1

    log_info "Environment validation passed"
    return 0
}

# =============================================================================
# Pre-Flight Version Check (Zero Disk Writes)
# =============================================================================

# Get remote ref SHA using git ls-remote (no disk writes)
# This is the preferred method for version checking
get_remote_sha() {
    local branch="${1:-main}"
    local ref="refs/heads/$branch"

    # Handle tag references
    if [[ "$branch" == v* ]]; then
        ref="refs/tags/$branch"
    fi

    git ls-remote "$REPO_URL" "$ref" 2>/dev/null | awk '{print $1}'
}

# Pre-flight check: determine if upgrade is needed
# Returns: 0 if upgrade needed, 1 if already current, 2 on error
preflight_version_check() {
    local target_branch="${1:-main}"

    log_step "Running pre-flight version check (no disk writes)..."

    local local_sha
    local remote_sha

    # Get installed version
    local_sha=$(get_installed_sha)
    if [[ -z "$local_sha" ]]; then
        log_info "No version file found, treating as fresh install"
        return 0
    fi

    log_info "Installed commit: ${local_sha:0:12}"

    # Get remote version using git ls-remote (no clone needed)
    remote_sha=$(get_remote_sha "$target_branch")
    if [[ -z "$remote_sha" ]]; then
        log_error "Could not fetch remote version - network error or invalid branch"
        return 2
    fi

    log_info "Remote commit:    ${remote_sha:0:12}"

    # Compare
    if [[ "$local_sha" == "$remote_sha" ]]; then
        log_info "Already at latest version (${remote_sha:0:12}), nothing to do"
        return 1
    fi

    log_info "Update available: ${local_sha:0:12} -> ${remote_sha:0:12}"
    return 0
}

# =============================================================================
# Staging Functions
# =============================================================================

# Create staging directory
create_staging_dir() {
    local action="${1:-install}"
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)

    # Compare /tmp and /var/tmp space, use the one with more available space
    local tmp_space var_tmp_space tmp_base
    tmp_space=$(df -m /tmp 2>/dev/null | awk 'NR==2 {print $4}') || tmp_space=0
    var_tmp_space=$(df -m /var/tmp 2>/dev/null | awk 'NR==2 {print $4}') || var_tmp_space=0

    # Default to /tmp, but switch to /var/tmp if it has more space or /tmp is low
    if [[ "${var_tmp_space:-0}" -gt "${tmp_space:-0}" ]] || [[ "${tmp_space:-0}" -lt 1024 ]]; then
        if [[ "${var_tmp_space:-0}" -ge 512 ]]; then
            tmp_base="/var/tmp"
            log_debug "Using /var/tmp (${var_tmp_space}MB) instead of /tmp (${tmp_space}MB)"
        else
            tmp_base="/tmp"
            log_warn "Both /tmp (${tmp_space}MB) and /var/tmp (${var_tmp_space}MB) have low space"
        fi
    else
        tmp_base="/tmp"
    fi

    local staging_dir="${tmp_base}/water-controller-${action}-${timestamp}-$$"
    mkdir -p "$staging_dir"
    echo "$staging_dir"
}

# Clone repository to staging
clone_to_staging() {
    local staging_dir="$1"
    local branch="${2:-main}"

    log_step "Cloning repository to staging..."

    local clone_output
    local clone_result

    # Capture both stdout and stderr, preserve exit code
    clone_output=$(git clone --depth 1 --branch "$branch" "$REPO_URL" "$staging_dir/repo" 2>&1) || clone_result=$?

    if [[ ${clone_result:-0} -ne 0 ]]; then
        log_error "Failed to clone repository"
        log_error "Git output: $clone_output"
        return 1
    fi

    log_debug "Clone output: $clone_output"

    # Verify clone integrity
    if [[ ! -d "$staging_dir/repo/.git" ]]; then
        log_error "Clone verification failed: .git directory missing"
        return 1
    fi

    # Get commit info
    local commit_sha
    commit_sha=$(cd "$staging_dir/repo" && git rev-parse HEAD)
    local commit_short="${commit_sha:0:7}"

    log_info "Cloned successfully: $commit_short"

    # Store commit info for later
    echo "$commit_sha" > "$staging_dir/.commit_sha"
    echo "$branch" > "$staging_dir/.branch"

    return 0
}

# Cleanup staging directory (legacy - prefer register_cleanup)
cleanup_staging() {
    local staging_dir="$1"

    if [[ -n "$staging_dir" ]] && [[ -d "$staging_dir" ]]; then
        log_info "Cleaning up staging directory..."
        rm -rf "$staging_dir"
    fi
}

# =============================================================================
# Checksum Verification
# =============================================================================

# Verify repository checksum if SHA256SUMS file exists
verify_checksum() {
    local staging_dir="$1"
    local branch="${2:-main}"

    local checksum_file="$staging_dir/repo/$CHECKSUM_FILE"

    if [[ ! -f "$checksum_file" ]]; then
        log_debug "No checksum file found at $checksum_file, skipping verification"
        return 0
    fi

    log_step "Verifying repository checksum..."

    # Verify the checksum file itself hasn't been tampered with
    # by checking if critical files match their checksums
    local verify_dir="$staging_dir/repo"

    if ! command -v sha256sum &>/dev/null; then
        log_warn "sha256sum not available, skipping checksum verification"
        return 0
    fi

    # Change to repo directory and verify
    (
        cd "$verify_dir" || exit 1
        if sha256sum --check --quiet "$CHECKSUM_FILE" 2>/dev/null; then
            log_info "Checksum verification passed"
            exit 0
        else
            log_warn "Some checksums did not match (files may have changed)"
            exit 1
        fi
    )

    return $?
}

# =============================================================================
# Backup and Rollback Functions
# =============================================================================

# Create a backup of current installation
create_backup() {
    local backup_reason="${1:-backup}"
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)

    local backup_path="${BACKUP_DIR}/${backup_reason}-${timestamp}"

    log_step "Creating backup..."

    # Ensure backup directory exists
    run_privileged mkdir -p "$BACKUP_DIR" || {
        log_error "Failed to create backup directory"
        return 1
    }

    # Copy installation directory
    if [[ -d "$INSTALL_DIR" ]]; then
        run_privileged cp -a "$INSTALL_DIR" "$backup_path" || {
            log_error "Failed to backup installation directory"
            return 1
        }

        # Also backup version file path
        echo "$INSTALL_DIR" | run_privileged tee "$backup_path/.original_path" >/dev/null

        log_info "Backup created: $backup_path"
        echo "$backup_path"
        return 0
    else
        log_warn "No installation directory to backup"
        return 1
    fi
}

# Clean up old backups, keeping the most recent N
cleanup_old_backups() {
    local keep_count="${1:-3}"

    if [[ ! -d "$BACKUP_DIR" ]]; then
        return 0
    fi

    log_debug "Cleaning up old backups (keeping $keep_count most recent)"

    # Find and remove old backups
    local backup_count
    backup_count=$(find "$BACKUP_DIR" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)

    if [[ "$backup_count" -le "$keep_count" ]]; then
        log_debug "Only $backup_count backups exist, nothing to clean"
        return 0
    fi

    # Remove oldest backups
    find "$BACKUP_DIR" -maxdepth 1 -mindepth 1 -type d -printf '%T@ %p\n' 2>/dev/null | \
        sort -n | \
        head -n -"$keep_count" | \
        cut -d' ' -f2- | \
        while read -r old_backup; do
            log_debug "Removing old backup: $old_backup"
            run_privileged rm -rf "$old_backup"
        done
}

# =============================================================================
# Action Handlers
# =============================================================================

# Install action
do_install() {
    local branch="${1:-main}"
    local force="${2:-false}"

    local state
    state=$(detect_system_state)

    case "$state" in
        fresh)
            log_info "Fresh system detected, proceeding with installation"
            ;;
        installed)
            if [[ "$force" == "true" ]]; then
                log_warn "Existing installation found, --force specified, reinstalling"
            else
                log_error "Water-Controller is already installed"
                log_info "Use 'upgrade' to update, or 'install --force' to reinstall"
                log_info "Current version: $(get_installed_version)"
                return 1
            fi
            ;;
        corrupted)
            log_warn "Corrupted installation detected, will attempt to fix"
            ;;
    esac

    # Create staging
    local staging_dir
    staging_dir=$(create_staging_dir "install")
    register_cleanup "$staging_dir"

    # Clone to staging
    clone_to_staging "$staging_dir" "$branch" || return 1

    # Verify checksum if available
    verify_checksum "$staging_dir" "$branch" || {
        log_warn "Checksum verification skipped or failed (non-fatal)"
    }

    # Execute install script from staging
    log_step "Running installation script..."

    local install_script="$staging_dir/repo/scripts/install.sh"
    if [[ ! -f "$install_script" ]]; then
        log_error "Install script not found in repository"
        return 1
    fi

    chmod +x "$install_script"

    # Pass source directory to install script
    export SOURCE_DIR="$staging_dir/repo"
    export BOOTSTRAP_MODE="true"

    run_privileged_env bash "$install_script" --source "$staging_dir/repo"

    local result=$?

    if [[ $result -eq 0 ]]; then
        # Write version file
        write_version_file "$staging_dir"
        log_info "Installation completed successfully!"
        log_info "Run 'systemctl status water-controller' to check service status"
    else
        log_error "Installation failed with exit code: $result"
    fi

    return $result
}

# Upgrade action
do_upgrade() {
    local branch="${1:-main}"
    local force="${2:-false}"
    local dry_run="${3:-false}"

    local state
    state=$(detect_system_state)

    case "$state" in
        fresh)
            log_error "No installation found. Use 'install' instead."
            return 1
            ;;
        installed)
            log_info "Existing installation found: $(get_installed_version)"
            ;;
        corrupted)
            log_warn "Corrupted installation detected. Consider 'install --force' instead."
            if [[ "$force" != "true" ]]; then
                return 1
            fi
            ;;
    esac

    # Pre-flight check (no disk writes yet)
    if [[ "$force" != "true" ]]; then
        local preflight_result
        preflight_version_check "$branch"
        preflight_result=$?

        if [[ $preflight_result -eq 1 ]]; then
            # Already at latest version
            return 0
        elif [[ $preflight_result -eq 2 ]]; then
            # Network error - abort unless forced
            log_error "Pre-flight check failed. Use --force to skip version check."
            return 1
        fi
        # preflight_result=0 means update available, continue
    fi

    if [[ "$dry_run" == "true" ]]; then
        log_info "Dry run: would upgrade from $(get_installed_sha | cut -c1-12) to latest"
        return 0
    fi

    # Create backup for rollback
    local backup_dir=""
    if [[ -d "$INSTALL_DIR" ]]; then
        backup_dir=$(create_backup "pre-upgrade")
        if [[ -z "$backup_dir" ]]; then
            log_warn "Could not create backup, upgrade will proceed without rollback capability"
        else
            log_info "Backup created: $backup_dir"
        fi
    fi

    # Create staging
    local staging_dir
    staging_dir=$(create_staging_dir "upgrade")
    register_cleanup "$staging_dir"

    # Clone to staging
    clone_to_staging "$staging_dir" "$branch" || return 1

    # Verify checksum if available
    verify_checksum "$staging_dir" "$branch" || {
        log_warn "Checksum verification skipped or failed (non-fatal)"
    }

    # Execute upgrade script from staging
    log_step "Running upgrade script..."

    local upgrade_script="$staging_dir/repo/scripts/upgrade.sh"
    if [[ ! -f "$upgrade_script" ]]; then
        # Fall back to install script with upgrade mode
        upgrade_script="$staging_dir/repo/scripts/install.sh"
        log_info "Using install script in upgrade mode"
    fi

    if [[ ! -f "$upgrade_script" ]]; then
        log_error "Neither upgrade.sh nor install.sh found in repository"
        return 1
    fi

    chmod +x "$upgrade_script"

    # Pass source directory to upgrade script
    export SOURCE_DIR="$staging_dir/repo"
    export BOOTSTRAP_MODE="true"
    export UPGRADE_MODE="true"

    run_privileged_env bash "$upgrade_script" --source "$staging_dir/repo" --upgrade

    local result=$?

    if [[ $result -eq 0 ]]; then
        # Write version file
        write_version_file "$staging_dir"
        log_info "Upgrade completed successfully!"
        # Clean up backup on success (keep last 2)
        cleanup_old_backups 2

        # Run validation after upgrade
        log_step "Validating upgraded deployment..."
        if [[ -x "$INSTALL_DIR/scripts/validate-deployment.sh" ]]; then
            if "$INSTALL_DIR/scripts/validate-deployment.sh"; then
                log_info "✓ Post-upgrade validation passed"
            else
                log_warn "⚠ Post-upgrade validation had failures"
                log_info "Run: $INSTALL_DIR/scripts/fix-database-auth.sh"
            fi
        fi
    else
        log_error "Upgrade failed with exit code: $result"
        if [[ -n "$backup_dir" ]] && [[ -d "$backup_dir" ]]; then
            log_warn "Backup available for manual rollback: $backup_dir"
            log_info "To rollback: sudo rm -rf $INSTALL_DIR && sudo cp -a $backup_dir $INSTALL_DIR"
        fi
    fi

    return $result
}

# Remove action
do_remove() {
    local keep_config="${1:-false}"
    local yes="${2:-false}"

    local state
    state=$(detect_system_state)

    if [[ "$state" == "fresh" ]]; then
        log_info "No installation found, nothing to remove"
        return 0
    fi

    if [[ "$yes" != "true" ]]; then
        echo ""
        echo "This will remove Water-Controller from this system."
        if [[ "$keep_config" == "true" ]]; then
            echo "Configuration files will be preserved."
        else
            echo "ALL data and configuration will be DELETED."
        fi
        echo ""
        local response
        response=$(prompt_user "Are you sure? [y/N] ")
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            log_info "Removal cancelled"
            return 0
        fi
    fi

    log_step "Removing Water-Controller..."

    # Stop and disable services
    log_info "Stopping services..."
    local services=(
        "water-controller"
        "water-controller-api"
        "water-controller-ui"
        "water-controller-frontend"
        "water-controller-hmi"
    )

    local svc
    for svc in "${services[@]}"; do
        if systemctl is-active "${svc}.service" &>/dev/null; then
            run_privileged systemctl stop "${svc}.service" 2>/dev/null || true
        fi
        if systemctl is-enabled "${svc}.service" &>/dev/null; then
            run_privileged systemctl disable "${svc}.service" 2>/dev/null || true
        fi
    done

    # Remove systemd unit files
    log_info "Removing systemd unit files..."
    for svc in "${services[@]}"; do
        local unit_file="/etc/systemd/system/${svc}.service"
        if [[ -f "$unit_file" ]]; then
            run_privileged rm -f "$unit_file"
        fi
    done

    # Reload systemd
    run_privileged systemctl daemon-reload 2>/dev/null || true

    # Backup config if requested
    local config_backup_dir=""
    if [[ "$keep_config" == "true" ]] && [[ -d "$CONFIG_DIR" ]]; then
        config_backup_dir="${BACKUP_DIR}/config-$(date +%Y%m%d_%H%M%S)"
        log_info "Backing up configuration to: $config_backup_dir"
        run_privileged mkdir -p "$config_backup_dir"
        run_privileged cp -r "$CONFIG_DIR" "$config_backup_dir/"
    fi

    # Remove installation directory
    log_info "Removing installation directory..."
    if [[ -d "$INSTALL_DIR" ]]; then
        run_privileged rm -rf "$INSTALL_DIR"
    fi

    # Remove config directory (unless keep_config)
    if [[ "$keep_config" != "true" ]] && [[ -d "$CONFIG_DIR" ]]; then
        log_info "Removing configuration directory..."
        run_privileged rm -rf "$CONFIG_DIR"
    fi

    # Remove data directory (unless keep_config)
    if [[ "$keep_config" != "true" ]] && [[ -d "$DATA_DIR" ]]; then
        log_info "Removing data directory..."
        run_privileged rm -rf "$DATA_DIR"
    fi

    # Remove log directory
    if [[ -d "$LOG_DIR" ]]; then
        log_info "Removing log directory..."
        run_privileged rm -rf "$LOG_DIR"
    fi

    log_info "Removal completed"

    if [[ "$keep_config" == "true" ]] && [[ -n "$config_backup_dir" ]]; then
        log_info "Configuration preserved in: $config_backup_dir"
    fi

    log_info "To reinstall: curl -fsSL $REPO_RAW_URL/main/bootstrap.sh | bash"

    return 0
}

# Extract version from JSON file without jq
# Handles escaped quotes and multiline properly
extract_json_value() {
    local file="$1"
    local key="$2"

    if command -v jq &>/dev/null; then
        jq -r ".$key // \"\"" "$file" 2>/dev/null
        return
    fi

    # Use Python if available (more reliable than grep for JSON)
    if command -v python3 &>/dev/null; then
        python3 -c "import json,sys; d=json.load(open('$file')); print(d.get('$key',''))" 2>/dev/null
        return
    fi

    if command -v python &>/dev/null; then
        python -c "import json,sys; d=json.load(open('$file')); print(d.get('$key',''))" 2>/dev/null
        return
    fi

    # Fallback to grep - handles simple cases
    # Use sed to extract value, handling potential escaped chars
    grep -o "\"$key\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$file" 2>/dev/null | \
        sed 's/.*:[[:space:]]*"\([^"]*\)"/\1/' | \
        head -1
}

# Write version metadata file
write_version_file() {
    local staging_dir="$1"

    local commit_sha=""
    local branch=""
    local version=""
    local tag=""

    if [[ -f "$staging_dir/.commit_sha" ]]; then
        commit_sha=$(cat "$staging_dir/.commit_sha")
    fi

    if [[ -f "$staging_dir/.branch" ]]; then
        branch=$(cat "$staging_dir/.branch")
    fi

    # Try to get version from package.json or pyproject.toml
    if [[ -f "$staging_dir/repo/package.json" ]]; then
        version=$(extract_json_value "$staging_dir/repo/package.json" "version")
        version="${version:-0.0.0}"
    fi

    # Get previous version info if exists
    local previous_version=""
    local previous_sha=""
    if [[ -f "$VERSION_FILE" ]]; then
        previous_version=$(extract_json_value "$VERSION_FILE" "version")
        previous_sha=$(extract_json_value "$VERSION_FILE" "commit_sha")
    fi

    # Write version file
    local version_content
    version_content=$(cat <<EOF
{
  "schema_version": 1,
  "package": "water-controller",
  "version": "${version:-0.0.0}",
  "commit_sha": "$commit_sha",
  "commit_short": "${commit_sha:0:7}",
  "branch": "$branch",
  "tag": "$tag",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "installed_by": "bootstrap.sh",
  "bootstrap_version": "$BOOTSTRAP_VERSION",
  "previous_version": "$previous_version",
  "previous_sha": "$previous_sha"
}
EOF
)

    echo "$version_content" | run_privileged tee "$VERSION_FILE" > /dev/null

    log_info "Version file written: $VERSION_FILE"
}

# =============================================================================
# Help and Usage
# =============================================================================

show_help() {
    cat <<EOF
Water-Controller Bootstrap Script v$BOOTSTRAP_VERSION

USAGE:
    bootstrap.sh [ACTION] [OPTIONS]

ACTIONS:
    install     Install Water-Controller (default for fresh systems)
    upgrade     Upgrade existing installation (default for installed systems)
    remove      Remove Water-Controller from this system

DEPLOYMENT MODE:
    --mode baremetal    Install directly on host (systemd services)
    --mode docker       Install using Docker containers

    If not specified, defaults to baremetal.

OPTIONS:
    --branch <name>     Use specific git branch (default: main)
    --force             Force action even if checks fail
    --dry-run           Show what would be done without making changes
    --keep-config       Keep configuration files when removing
    --yes, -y           Answer yes to all prompts
    --quiet, -q         Suppress non-essential output (errors still shown)
    --help, -h          Show this help message
    --version           Show version information

LOGGING:
    Bootstrap operations are logged to: $BOOTSTRAP_LOG
    Backups are stored in: $BACKUP_DIR

EXAMPLES:
    # Install with baremetal (default)
    curl -fsSL $REPO_RAW_URL/main/bootstrap.sh | bash -s -- install

    # Install with Docker
    curl -fsSL .../bootstrap.sh | bash -s -- install --mode docker

    # Install from develop branch
    curl -fsSL .../bootstrap.sh | bash -s -- install --branch develop

    # Upgrade with dry-run
    curl -fsSL .../bootstrap.sh | bash -s -- upgrade --dry-run

    # Force reinstall
    curl -fsSL .../bootstrap.sh | bash -s -- install --force

    # Remove but keep config
    curl -fsSL .../bootstrap.sh | bash -s -- remove --keep-config

ENVIRONMENT:
    INSTALL_DIR         Installation directory (default: /opt/water-controller)
    CONFIG_DIR          Configuration directory (default: /etc/water-controller)

For more information, see: https://github.com/mwilco03/Water-Controller
EOF
}

show_version() {
    echo "Water-Controller Bootstrap v$BOOTSTRAP_VERSION"

    local state
    state=$(detect_system_state)

    if [[ "$state" == "installed" ]]; then
        echo "Installed version: $(get_installed_version)"
        echo "Installed commit:  $(get_installed_sha | cut -c1-12)"
    else
        echo "Installation status: $state"
    fi
}

# =============================================================================
# Main Entry Point
# =============================================================================

main() {
    local action=""
    local branch="main"
    local force="false"
    local dry_run="false"
    local keep_config="false"
    local yes="false"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            install|upgrade|remove)
                action="$1"
                shift
                ;;
            --mode)
                if [[ "$2" == "baremetal" || "$2" == "docker" ]]; then
                    DEPLOYMENT_MODE="$2"
                    shift 2
                else
                    log_error "Invalid mode: $2. Use 'baremetal' or 'docker'"
                    exit 1
                fi
                ;;
            --branch)
                branch="$2"
                shift 2
                ;;
            --force)
                force="true"
                shift
                ;;
            --dry-run)
                dry_run="true"
                shift
                ;;
            --keep-config)
                keep_config="true"
                shift
                ;;
            --yes|-y)
                yes="true"
                shift
                ;;
            --quiet|-q)
                QUIET_MODE="true"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            --version)
                show_version
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Initialize logging
    init_logging
    log_debug "Bootstrap started with args: action=$action branch=$branch force=$force dry_run=$dry_run"

    # If no action specified, auto-detect based on system state
    if [[ -z "$action" ]]; then
        local state
        state=$(detect_system_state)

        case "$state" in
            fresh)
                action="install"
                log_info "Fresh system detected, will install"
                ;;
            installed)
                action="upgrade"
                log_info "Existing installation detected, will upgrade"
                ;;
            corrupted)
                log_warn "Corrupted installation detected"
                action="install"
                force="true"
                ;;
        esac
    fi

    # Validate environment (except for remove action which has its own checks)
    if [[ "$action" != "remove" ]]; then
        validate_environment || exit 1
    else
        check_root || exit 1
    fi

    # Handle deployment mode for install action
    if [[ "$action" == "install" && "$DEPLOYMENT_MODE" == "docker" ]]; then
        log_info "Deployment mode: Docker"
        validate_docker_requirements || exit 1
        do_docker_install
        exit $?
    fi

    # Default to baremetal for install if no mode specified
    if [[ "$action" == "install" && -z "$DEPLOYMENT_MODE" ]]; then
        DEPLOYMENT_MODE="baremetal"
        log_info "Deployment mode: Bare-metal (default)"
    fi

    # Execute action
    local exit_code=0
    case "$action" in
        install)
            do_install "$branch" "$force"
            exit_code=$?
            ;;
        upgrade)
            do_upgrade "$branch" "$force" "$dry_run"
            exit_code=$?
            ;;
        remove)
            do_remove "$keep_config" "$yes"
            exit_code=$?
            ;;
        *)
            log_error "Unknown action: $action"
            show_help
            exit 1
            ;;
    esac

    exit $exit_code
}

# Run main if executed directly (not sourced)
# Handle piped execution where BASH_SOURCE is unset
if [[ -z "${BASH_SOURCE[0]:-}" ]] || [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
