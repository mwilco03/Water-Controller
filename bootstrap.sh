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
#   curl -fsSL .../bootstrap.sh | bash -s -- fresh --verbose
#
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
# =============================================================================

set -euo pipefail

# =============================================================================
# Constants
# =============================================================================

readonly BOOTSTRAP_VERSION="1.3.0"
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

# Service names (DRY - single source of truth)
readonly DOCKER_SERVICE="docker"
readonly WTC_DOCKER_SERVICE="water-controller-docker"

# Global state
QUIET_MODE="false"
VERBOSE_MODE="false"  # Show detailed output for debugging
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
    local mkdir_error

    if [[ -w "$log_dir" ]] || [[ $EUID -eq 0 ]]; then
        if [[ $EUID -ne 0 ]]; then
            if ! mkdir_error=$(sudo mkdir -p "$log_dir" 2>&1); then
                echo "[WARN] Could not create log directory $log_dir: $mkdir_error" >&2
            fi
            if ! sudo touch "$BOOTSTRAP_LOG" 2>&1; then
                echo "[WARN] Could not create log file $BOOTSTRAP_LOG" >&2
            fi
            sudo chmod 644 "$BOOTSTRAP_LOG" 2>/dev/null || true
        else
            if ! mkdir_error=$(mkdir -p "$log_dir" 2>&1); then
                echo "[WARN] Could not create log directory $log_dir: $mkdir_error" >&2
            fi
            if ! touch "$BOOTSTRAP_LOG" 2>&1; then
                echo "[WARN] Could not create log file $BOOTSTRAP_LOG" >&2
            fi
        fi
    else
        echo "[INFO] Log directory $log_dir not writable and not root, logs may not be saved" >&2
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

log_verbose() {
    write_log "VERBOSE" "$1"
    # Verbose output only shown with --verbose flag
    if [[ "$VERBOSE_MODE" == "true" ]] && [[ "$QUIET_MODE" != "true" ]]; then
        echo -e "  $1" >&2
    fi
}

# =============================================================================
# Helper Functions
# =============================================================================

# -----------------------------------------------------------------------------
# Discovery-First Helper Functions
# -----------------------------------------------------------------------------
# These functions implement the "discovery-first" pattern:
# - Discover state BEFORE assuming failure reasons
# - Capture actual errors instead of swallowing them
# - Report what was DISCOVERED, not what was ASSUMED

# Store last discovery result for detailed error reporting
_LAST_DISCOVERY_ERROR=""
_LAST_DISCOVERY_METHOD=""

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

    # Step 3: Can we access the socket? Check permissions properly
    local socket_accessible=false
    if [[ -r "$socket" ]] && [[ -w "$socket" ]]; then
        socket_accessible=true
    elif [[ $EUID -eq 0 ]]; then
        # Root should always have access
        socket_accessible=true
    elif id -nG 2>/dev/null | grep -qw docker; then
        # User is in docker group - socket should be accessible
        socket_accessible=true
    fi

    if [[ "$socket_accessible" != "true" ]]; then
        _LAST_DISCOVERY_ERROR="Permission denied: user '$(whoami)' is not root and not in docker group"
        _LAST_DISCOVERY_METHOD="group membership check (id -nG | grep docker)"
        return 1
    fi

    # Step 4: Can we actually talk to the daemon?
    local docker_error
    if ! docker_error=$(docker info 2>&1); then
        # Parse the actual error to provide accurate diagnosis
        if [[ "$docker_error" == *"permission denied"* ]]; then
            _LAST_DISCOVERY_ERROR="Permission denied accessing Docker daemon"
            _LAST_DISCOVERY_METHOD="docker info (permission error)"
        elif [[ "$docker_error" == *"Cannot connect"* ]] || [[ "$docker_error" == *"connection refused"* ]]; then
            _LAST_DISCOVERY_ERROR="Docker daemon not responding (socket exists but daemon stopped)"
            _LAST_DISCOVERY_METHOD="docker info (connection refused)"
        elif [[ "$docker_error" == *"Is the docker daemon running"* ]]; then
            _LAST_DISCOVERY_ERROR="Docker daemon is not running"
            _LAST_DISCOVERY_METHOD="docker info (daemon not running)"
        else
            _LAST_DISCOVERY_ERROR="Docker command failed: $docker_error"
            _LAST_DISCOVERY_METHOD="docker info (unknown error)"
        fi
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
        # Preserve the Docker discovery error
        _LAST_DISCOVERY_ERROR="Docker Compose requires working Docker: $_LAST_DISCOVERY_ERROR"
        return 1
    fi

    # Check for docker compose (plugin) or docker-compose (standalone)
    local compose_error
    if compose_error=$(docker compose version 2>&1); then
        _LAST_DISCOVERY_METHOD="docker compose plugin"
        return 0
    fi

    # Plugin failed, check why
    if [[ "$compose_error" == *"is not a docker command"* ]]; then
        # Plugin not installed, try standalone
        if command -v docker-compose &>/dev/null; then
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
    else
        _LAST_DISCOVERY_ERROR="docker compose failed: $compose_error"
        _LAST_DISCOVERY_METHOD="docker compose version"
        return 1
    fi
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

    # If we're running from a piped curl from github, network is already proven
    if [[ ! -t 0 ]] && [[ "$target" == *"github.com"* ]]; then
        _LAST_DISCOVERY_METHOD="script was piped from remote source - network connectivity already verified by successful download"
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
                _LAST_DISCOVERY_ERROR="SSL/TLS error connecting to $target"
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
        _LAST_DISCOVERY_ERROR="wget failed to reach $target"
        _LAST_DISCOVERY_METHOD="wget to $target"
        return 1
    fi

    _LAST_DISCOVERY_ERROR="No curl or wget available to test connectivity"
    _LAST_DISCOVERY_METHOD="tool availability check"
    return 1
}

# Log a discovered error with full context
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

# -----------------------------------------------------------------------------

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

# Check required tools are present, install if missing
check_required_tools() {
    local missing=()
    local tool

    for tool in "${REQUIRED_TOOLS[@]}"; do
        if ! command -v "$tool" &>/dev/null; then
            missing+=("$tool")
        fi
    done

    if [[ ${#missing[@]} -eq 0 ]]; then
        log_debug "All required tools present: ${REQUIRED_TOOLS[*]}"
        return 0
    fi

    log_warn "Missing required tools: ${missing[*]}"
    log_info "Attempting to install missing tools..."

    # Detect package manager and install
    if command -v apt-get &>/dev/null; then
        run_privileged apt-get update -qq
        run_privileged apt-get install -y "${missing[@]}"
    elif command -v dnf &>/dev/null; then
        run_privileged dnf install -y "${missing[@]}"
    elif command -v yum &>/dev/null; then
        run_privileged yum install -y "${missing[@]}"
    elif command -v pacman &>/dev/null; then
        run_privileged pacman -Sy --noconfirm "${missing[@]}"
    else
        log_error "No supported package manager found (apt-get, dnf, yum, pacman)"
        log_info "Please install manually: ${missing[*]}"
        return 1
    fi

    # Verify installation succeeded
    local still_missing=()
    for tool in "${missing[@]}"; do
        if ! command -v "$tool" &>/dev/null; then
            still_missing+=("$tool")
        fi
    done

    if [[ ${#still_missing[@]} -gt 0 ]]; then
        log_error "Failed to install: ${still_missing[*]}"
        return 1
    fi

    log_info "Successfully installed: ${missing[*]}"
    return 0
}

# Check network connectivity to GitHub using discovery-first approach
check_network() {
    log_info "Checking network connectivity..."

    # Use discovery function - it handles piped execution detection
    if discover_network "https://github.com" 10; then
        log_debug "Network connectivity confirmed ($_LAST_DISCOVERY_METHOD)"
        return 0
    fi

    # First attempt failed - provide detailed diagnosis before retry
    log_warn "Network check issue: $_LAST_DISCOVERY_ERROR"

    # Retry with exponential backoff only if it makes sense
    case "$_LAST_DISCOVERY_ERROR" in
        *"DNS resolution failed"*)
            log_error "DNS resolution failed for github.com"
            log_info "Check: /etc/resolv.conf, try 'nslookup github.com'"
            log_info "Fix:   Add 'nameserver 8.8.8.8' to /etc/resolv.conf"
            return 1
            ;;
        *"SSL"*|*"certificate"*)
            log_error "SSL/TLS error - certificate issue"
            log_info "Check: System time (date), CA certificates"
            log_info "Fix:   sudo apt-get install --reinstall ca-certificates"
            return 1
            ;;
        *"Connection refused"*)
            log_error "Connection refused by github.com - unusual, may be blocked"
            log_info "Check: Firewall rules, proxy settings"
            return 1
            ;;
        *)
            # Transient error - worth retrying
            local max_retries=3
            local retry_delay=2
            local attempt

            for ((attempt=2; attempt<=max_retries; attempt++)); do
                log_info "Retrying network check (attempt $attempt/$max_retries) in ${retry_delay}s..."
                sleep "$retry_delay"

                if discover_network "https://github.com" 10; then
                    log_info "Network connectivity confirmed on attempt $attempt"
                    return 0
                fi

                log_warn "Attempt $attempt failed: $_LAST_DISCOVERY_ERROR"
                retry_delay=$((retry_delay * 2))
            done

            log_discovered_error "Cannot reach GitHub after $max_retries attempts"
            return 1
            ;;
    esac
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
    run_privileged systemctl start "$DOCKER_SERVICE"
    run_privileged systemctl enable "$DOCKER_SERVICE"

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

    # Step 1: Discovery - what is the current Docker state?
    if ! discover_docker; then
        # Docker not working - discover WHY and take appropriate action
        case "$_LAST_DISCOVERY_ERROR" in
            *"not found in PATH"*)
                # Docker binary not installed
                log_warn "Docker is not installed"
                if [[ -t 0 ]] || [[ -e /dev/tty ]]; then
                    local response
                    response=$(prompt_user "Would you like to install Docker now? [Y/n] ")
                    if [[ "$response" =~ ^[Nn]$ ]]; then
                        log_error "Docker is required for docker deployment mode"
                        log_info "Install Docker manually: https://docs.docker.com/engine/install/"
                        return 1
                    fi
                else
                    log_info "Non-interactive mode detected, installing Docker automatically..."
                fi
                if ! install_docker; then
                    log_error "Docker installation failed"
                    return 1
                fi
                ;;

            *"not root and not in docker group"*)
                # Permission issue - need elevated privileges
                log_warn "Docker access requires privileges"
                log_info "  Discovered: $_LAST_DISCOVERY_ERROR"
                log_info "Attempting with elevated privileges..."

                # Try with sudo
                if run_privileged docker info &>/dev/null; then
                    log_info "Docker accessible with elevated privileges"
                    # Continue - subsequent docker commands will use run_privileged
                else
                    log_error "Docker not accessible even with sudo"
                    log_info "Fix: Add user to docker group: sudo usermod -aG docker $(whoami)"
                    log_info "     Then log out and back in, or run: newgrp docker"
                    return 1
                fi
                ;;

            *"daemon not responding"*|*"daemon is not running"*|*"daemon stopped"*)
                # Daemon not running - try to start it
                log_info "Docker daemon not running, attempting to start..."
                log_info "  Discovered via: $_LAST_DISCOVERY_METHOD"

                if command -v systemctl &>/dev/null; then
                    local start_error
                    if ! start_error=$(run_privileged systemctl start "$DOCKER_SERVICE" 2>&1); then
                        log_error "Failed to start Docker daemon"
                        log_error "  Cause: $start_error"
                        log_info "Check: sudo systemctl status $DOCKER_SERVICE"
                        log_info "Logs:  sudo journalctl -xeu $DOCKER_SERVICE"
                        return 1
                    fi
                    run_privileged systemctl enable "$DOCKER_SERVICE" 2>/dev/null || true
                fi

                # Wait for daemon with progress
                local wait_count=0
                log_info "Waiting for Docker daemon to respond..."
                while ! discover_docker && [[ $wait_count -lt 15 ]]; do
                    sleep 1
                    wait_count=$((wait_count + 1))
                done

                if ! discover_docker; then
                    log_discovered_error "Docker daemon failed to start after ${wait_count}s"
                    log_info "Check: sudo systemctl status $DOCKER_SERVICE"
                    log_info "Logs:  sudo journalctl -xeu $DOCKER_SERVICE"
                    return 1
                fi
                log_info "Docker daemon started successfully"
                ;;

            *"socket does not exist"*)
                # Socket missing - daemon never installed or completely broken
                log_error "Docker socket missing - Docker may not be properly installed"
                log_info "  Discovered: $_LAST_DISCOVERY_ERROR"
                log_info "Try reinstalling Docker: https://docs.docker.com/engine/install/"
                return 1
                ;;

            *)
                # Unknown error - report what we discovered
                log_discovered_error "Docker validation failed"
                return 1
                ;;
        esac
    fi

    # Step 2: Verify Docker Compose
    if ! discover_docker_compose; then
        log_discovered_error "Docker Compose not available"

        # Provide specific remediation based on discovery
        if [[ "$_LAST_DISCOVERY_ERROR" == *"plugin"*"standalone"* ]]; then
            log_info "Install Docker Compose plugin:"
            log_info "  sudo apt-get install docker-compose-plugin"
            log_info "Or standalone: https://docs.docker.com/compose/install/"
        fi
        return 1
    fi
    log_info "Docker Compose available ($_LAST_DISCOVERY_METHOD)"

    # Step 3: Ensure docker is enabled for boot
    if command -v systemctl &>/dev/null; then
        if ! systemctl is-enabled "$DOCKER_SERVICE" &>/dev/null 2>&1; then
            log_info "Enabling Docker to start on boot..."
            run_privileged systemctl enable "$DOCKER_SERVICE" 2>/dev/null || true
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
    local service_file="/etc/systemd/system/${WTC_DOCKER_SERVICE}.service"
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
        echo ""
        echo "# Network interface (empty = auto-detect)"
        echo "WTC_INTERFACE=${WTC_INTERFACE:-}"
    } | run_privileged tee "$env_file" > /dev/null
    run_privileged chmod 600 "$env_file"

    # Discovery: Find docker binary path at install time
    local docker_bin
    docker_bin=$(command -v docker)
    if [[ -z "$docker_bin" ]]; then
        log_error "Cannot find docker binary for systemd unit"
        return 1
    fi
    log_debug "Docker binary discovered at: $docker_bin"

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
# Docker path discovered at install time: $docker_bin
ExecStart=$docker_bin compose up -d
ExecStop=$docker_bin compose down
TimeoutStartSec=300
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
EOF
)

    echo "$service_content" | run_privileged tee "$service_file" > /dev/null

    # Enable service
    run_privileged systemctl daemon-reload
    run_privileged systemctl enable "${WTC_DOCKER_SERVICE}.service"

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

# Cleanup partial Docker install on failure
cleanup_docker_partial() {
    log_warn "Cleaning up partial Docker installation..."
    if command -v docker &>/dev/null && docker info &>/dev/null; then
        # Stop and remove containers from this project
        local containers
        containers=$(docker ps -aq --filter "name=wtc-" 2>/dev/null || true)
        if [[ -n "$containers" ]]; then
            docker stop $containers 2>/dev/null || true
            docker rm -f $containers 2>/dev/null || true
        fi
    fi
}

# Run Docker deployment
do_docker_install() {
    log_step "Starting Docker deployment..."

    # Set up cleanup trap for partial failure
    local docker_install_failed="false"
    trap 'docker_install_failed="true"' ERR

    # Pre-deployment checks (non-blocking, warnings only)
    check_docker_resources || log_warn "Resource checks failed, proceeding anyway..."
    check_port_conflicts || log_warn "Port conflicts detected, proceeding anyway..."

    # Validate package-lock.json if repo is already cloned
    if [[ -d "/opt/water-controller/web/ui" ]]; then
        validate_package_lock "/opt/water-controller/web/ui" || log_warn "Package lock validation failed"
    fi

    # Find docker directory
    local docker_dir=""
    local repo_dir=""
    if [[ -d "./docker" ]]; then
        # Running from within repo directory - pull latest
        docker_dir="./docker"
        repo_dir="."
        log_info "Running from repo directory, pulling latest changes..."
        git pull origin main 2>/dev/null || log_warn "Could not pull latest (may be offline)"
    else
        # Always clone fresh to ensure we have latest code
        # This fixes issues where /opt/water-controller has stale Dockerfiles
        local staging_dir
        staging_dir=$(create_staging_dir "docker-install")
        register_cleanup "$staging_dir"

        clone_to_staging "$staging_dir" "main" || return 1
        docker_dir="$staging_dir/repo/docker"
        repo_dir="$staging_dir/repo"

        # Copy to persistent location (including hidden files)
        log_info "Installing to /opt/water-controller..."
        local mkdir_result
        if ! mkdir_result=$(run_privileged mkdir -p /opt/water-controller 2>&1); then
            log_error "Failed to create /opt/water-controller: $mkdir_result"
            return 1
        fi
        # Remove old files first to ensure clean install
        if [[ -d "/opt/water-controller/docker" ]]; then
            log_info "Removing old installation files..."
            run_privileged rm -rf /opt/water-controller/docker /opt/water-controller/web /opt/water-controller/src 2>/dev/null || true
        fi
        if ! run_privileged cp -a "$staging_dir/repo/." /opt/water-controller/; then
            log_error "Failed to copy repository to /opt/water-controller"
            return 1
        fi
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
        export GRAFANA_PASSWORD=$(generate_password 24)
    fi

    if [[ -z "${DB_PASSWORD:-}" ]]; then
        export DB_PASSWORD=$(generate_password 32)
    fi

    # Save passwords to PERSISTENT location
    local creds_file="/opt/water-controller/config/.docker-credentials"
    log_info "Configuring service credentials..."
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

    # Discovery: Verify docker directory exists and is accessible
    if [[ ! -d "$docker_dir" ]]; then
        log_error "Docker directory not found: $docker_dir"
        log_info "  Expected docker-compose.yml at: $docker_dir/docker-compose.yml"
        return 1
    fi
    if [[ ! -f "$docker_dir/docker-compose.yml" ]]; then
        log_error "docker-compose.yml not found in: $docker_dir"
        log_info "  Directory contents: $(ls -la "$docker_dir" 2>&1 | head -5)"
        return 1
    fi
    log_debug "Docker directory verified: $docker_dir"

    (
        cd "$docker_dir" || exit 1
        export GRAFANA_PASSWORD="$GRAFANA_PASSWORD"
        export DB_PASSWORD="$DB_PASSWORD"

        docker compose build --no-cache --progress=plain 2>&1 | while IFS= read -r line; do
            # Show build step numbers only (e.g., "#7" from "#7 [api 1/8] FROM docker...")
            if echo "$line" | grep -qE "^#[0-9]+ \["; then
                step=$(echo "$line" | grep -oE "^#[0-9]+")
                echo "[BUILD] $step" >&2
            # Show image building status
            elif echo "$line" | grep -qE "Image docker-[a-z]+ Building"; then
                echo "[BUILD] $line" >&2
            # Show completion/finish messages
            elif echo "$line" | grep -qE "writing image|FINISHED|exporting"; then
                echo "[BUILD] $line" >&2
            # Always show errors
            elif echo "$line" | grep -qiE "error|ERROR|failed|FAILED|fatal"; then
                echo "[BUILD ERROR] $line" >&2
            fi
        done
    ) || {
        log_error "Docker image build failed"
        log_info "Check logs above for build errors"
        log_info "Common issues:"
        log_info "  - Missing build dependencies (should be auto-installed)"
        log_info "  - Network connectivity (required for package downloads)"
        log_info "  - Insufficient disk space"
        cleanup_docker_partial
        return 1
    }

    # Start containers (docker_dir already verified above during build step)
    # Note: POSIX shared memory for controller-API IPC is created automatically
    # by the controller process. Both containers use ipc: host to share the
    # host's IPC namespace where /dev/shm/wtc_shared_memory is created.
    log_step "Starting containers..."
    (
        cd "$docker_dir" || { echo "ERROR: Cannot access $docker_dir" >&2; exit 1; }
        export GRAFANA_PASSWORD="$GRAFANA_PASSWORD"
        export DB_PASSWORD="$DB_PASSWORD"

        docker compose up -d --force-recreate
    )

    local result=$?
    if [[ $result -ne 0 ]]; then
        log_error "Docker deployment failed"
        cleanup_docker_partial
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
    log_info "  Restart: sudo systemctl restart $WTC_DOCKER_SERVICE"
    log_info "  Stop:    sudo systemctl stop $WTC_DOCKER_SERVICE"
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

    # Check disk space (minimum 5GB for Docker images + data)
    local available_gb
    available_gb=$(df -BG / 2>/dev/null | awk 'NR==2 {print $4}' | tr -d 'G')

    if [[ -n "$available_gb" ]] && [[ "$available_gb" -lt 5 ]]; then
        log_error "Insufficient disk space: ${available_gb}GB available, 5GB minimum required for Docker deployment"
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
# Pre-Flight Validation
# =============================================================================

# Show disk space usage
# Default: concise one-liner summary
# With --verbose: full breakdown
show_disk_space() {
    local label="${1:-Current}"

    # Get root filesystem stats
    local df_line
    df_line=$(df -h / 2>/dev/null | tail -1)
    local size avail used_pct
    size=$(echo "$df_line" | awk '{print $2}')
    avail=$(echo "$df_line" | awk '{print $4}')
    used_pct=$(echo "$df_line" | awk '{print $5}')

    # Get Docker reclaimable space if available
    local docker_reclaimable=""
    local docker_total=""
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        local docker_df
        docker_df=$(docker system df --format "{{.Type}}\t{{.Size}}\t{{.Reclaimable}}" 2>/dev/null)
        if [[ -n "$docker_df" ]]; then
            # Sum up reclaimable space (extract numeric values)
            docker_total=$(docker system df --format "{{.Size}}" 2>/dev/null | paste -sd+ | bc 2>/dev/null || echo "")
            docker_reclaimable=$(docker system df --format "{{.Reclaimable}}" 2>/dev/null | grep -oP '[\d.]+[KMGT]?B' | head -1 || echo "")
        fi
    fi

    if [[ "$VERBOSE_MODE" == "true" ]]; then
        # Verbose: full breakdown
        log_info "═══ $label Disk Space ═══"
        df -h / /var /tmp 2>/dev/null | head -5 || df -h / 2>/dev/null
        if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
            log_info "Docker disk usage:"
            docker system df 2>/dev/null || true
        fi
    else
        # Concise: one-liner summary
        local summary="Disk: ${avail} available of ${size} (${used_pct} used)"
        if [[ -n "$docker_reclaimable" ]]; then
            summary="$summary, Docker reclaimable: ~${docker_reclaimable}"
        fi
        log_info "$summary"
    fi
}

# Validate package-lock.json is in sync with package.json
validate_package_lock() {
    local ui_dir="${1:-/opt/water-controller/web/ui}"

    if [[ ! -d "$ui_dir" ]]; then
        log_debug "UI directory not found, skipping package-lock validation"
        return 0
    fi

    if [[ ! -f "$ui_dir/package.json" ]] || [[ ! -f "$ui_dir/package-lock.json" ]]; then
        log_warn "Missing package.json or package-lock.json in $ui_dir"
        return 1
    fi

    log_step "Validating package-lock.json sync..."

    # Run npm ci --dry-run to check if lock file is in sync
    if command -v npm &>/dev/null; then
        if (cd "$ui_dir" && npm ci --dry-run 2>&1) | grep -qiE "npm error|npm ERR"; then
            log_error "package-lock.json is out of sync with package.json"
            log_info "Run 'cd $ui_dir && npm install' to regenerate lock file"
            return 1
        fi
        log_info "✓ package-lock.json is in sync"
    else
        log_warn "npm not available, skipping package-lock validation"
    fi

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

    # Discovery: Verify repo directory and checksum file exist
    if [[ ! -d "$verify_dir" ]]; then
        log_warn "Verification directory not found: $verify_dir"
        return 0  # Non-fatal, continue without verification
    fi
    if [[ ! -f "$verify_dir/$CHECKSUM_FILE" ]]; then
        log_debug "No checksum file at: $verify_dir/$CHECKSUM_FILE"
        return 0  # Non-fatal, continue without verification
    fi

    # Change to repo directory and verify
    (
        cd "$verify_dir" || { echo "ERROR: Cannot access $verify_dir" >&2; exit 1; }
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

# Wipe action - complete removal including Docker resources
do_wipe() {
    log_step "Starting complete system wipe..."
    show_disk_space "Before Wipe"

    # Stop all containers first
    if command -v docker &>/dev/null && docker info &>/dev/null; then
        # Stop containers by name pattern
        local containers
        containers=$(docker ps -aq --filter "name=wtc-" 2>/dev/null || true)
        local container_count=0
        if [[ -n "$containers" ]]; then
            container_count=$(echo "$containers" | wc -w)
            log_info "Stopping $container_count container(s)..."
            if [[ "$VERBOSE_MODE" == "true" ]]; then
                docker stop $containers 2>&1 || true
                docker rm -f $containers 2>&1 || true
            else
                docker stop $containers >/dev/null 2>&1 || true
                docker rm -f $containers >/dev/null 2>&1 || true
            fi
        fi

        # Stop docker compose stack if compose file exists
        if [[ -f "/opt/water-controller/docker/docker-compose.yml" ]]; then
            log_verbose "Stopping docker compose stack..."
            (cd /opt/water-controller/docker && docker compose down -v --remove-orphans 2>/dev/null) || true
        fi
    fi

    # Stop and disable systemd services
    local services=(
        "water-controller"
        "water-controller-api"
        "water-controller-ui"
        "water-controller-frontend"
        "water-controller-hmi"
        "water-controller-docker"
    )
    local stopped_services=0
    for svc in "${services[@]}"; do
        if systemctl is-active --quiet "${svc}.service" 2>/dev/null; then
            ((stopped_services++))
            log_verbose "Stopping ${svc}.service"
        fi
        run_privileged systemctl stop "${svc}.service" 2>/dev/null || true
        run_privileged systemctl disable "${svc}.service" 2>/dev/null || true
        run_privileged rm -f "/etc/systemd/system/${svc}.service" 2>/dev/null || true
    done
    if [[ $stopped_services -gt 0 ]]; then
        log_info "Stopped $stopped_services systemd service(s)"
    fi
    run_privileged systemctl daemon-reload 2>/dev/null || true

    # Remove Docker resources for this project
    if command -v docker &>/dev/null && docker info &>/dev/null; then
        # Count resources before removal
        local image_count=0 volume_count=0 network_count=0

        # Remove project images
        local images
        images=$(docker images --filter "reference=*water*" -q 2>/dev/null || true)
        images="$images $(docker images --filter "reference=*wtc*" -q 2>/dev/null || true)"
        images=$(echo "$images" | xargs -n1 2>/dev/null | sort -u | xargs 2>/dev/null || true)
        if [[ -n "$images" ]]; then
            image_count=$(echo "$images" | wc -w)
            if [[ "$VERBOSE_MODE" == "true" ]]; then
                docker rmi -f $images 2>&1 || true
            else
                docker rmi -f $images >/dev/null 2>&1 || true
            fi
        fi

        # Remove project volumes
        local volumes
        volumes=$(docker volume ls -q --filter "name=wtc" 2>/dev/null || true)
        volumes="$volumes $(docker volume ls -q --filter "name=water" 2>/dev/null || true)"
        volumes=$(echo "$volumes" | xargs -n1 2>/dev/null | sort -u | xargs 2>/dev/null || true)
        if [[ -n "$volumes" ]]; then
            volume_count=$(echo "$volumes" | wc -w)
            if [[ "$VERBOSE_MODE" == "true" ]]; then
                docker volume rm -f $volumes 2>&1 || true
            else
                docker volume rm -f $volumes >/dev/null 2>&1 || true
            fi
        fi

        # Remove project networks
        local networks
        networks=$(docker network ls -q --filter "name=wtc" 2>/dev/null || true)
        networks="$networks $(docker network ls -q --filter "name=water" 2>/dev/null || true)"
        networks=$(echo "$networks" | xargs -n1 2>/dev/null | sort -u | xargs 2>/dev/null || true)
        if [[ -n "$networks" ]]; then
            network_count=$(echo "$networks" | wc -w)
            if [[ "$VERBOSE_MODE" == "true" ]]; then
                docker network rm $networks 2>&1 || true
            else
                docker network rm $networks >/dev/null 2>&1 || true
            fi
        fi

        # Summary of Docker cleanup
        if [[ $image_count -gt 0 ]] || [[ $volume_count -gt 0 ]] || [[ $network_count -gt 0 ]]; then
            log_info "Removed Docker resources: ${image_count} image(s), ${volume_count} volume(s), ${network_count} network(s)"
        fi

        # Prune build cache (silent unless verbose)
        log_verbose "Pruning Docker build cache..."
        if [[ "$VERBOSE_MODE" == "true" ]]; then
            docker builder prune -af 2>&1 || true
            docker system prune -f 2>&1 || true
        else
            docker builder prune -af >/dev/null 2>&1 || true
            docker system prune -f >/dev/null 2>&1 || true
        fi
    fi

    # Remove all directories (consolidated log message)
    log_info "Removing installation directories..."
    log_verbose "/opt/water-controller"
    run_privileged rm -rf /opt/water-controller 2>/dev/null || true
    log_verbose "/etc/water-controller"
    run_privileged rm -rf /etc/water-controller 2>/dev/null || true
    log_verbose "/var/lib/water-controller"
    run_privileged rm -rf /var/lib/water-controller 2>/dev/null || true
    log_verbose "/var/log/water-controller"
    run_privileged rm -rf /var/log/water-controller 2>/dev/null || true
    log_verbose "/var/backups/water-controller"
    run_privileged rm -rf /var/backups/water-controller 2>/dev/null || true

    # Remove credentials files
    run_privileged rm -f /root/.water-controller-credentials 2>/dev/null || true

    # Clean up temp files
    run_privileged rm -rf /tmp/water-controller-* 2>/dev/null || true
    run_privileged rm -rf /var/tmp/water-controller-* 2>/dev/null || true

    show_disk_space "After Wipe"
    log_info "✓ System wipe completed"
    return 0
}

# Fresh install - wipe everything and reinstall from scratch
do_fresh() {
    local branch="${1:-main}"

    log_step "Starting fresh install (wipe + install)..."
    show_disk_space "Before Fresh Install"

    # Wipe everything first
    do_wipe || {
        log_error "Wipe failed, aborting fresh install"
        return 1
    }

    # Now do a clean install
    log_step "Cloning and installing from scratch..."

    # Validate environment
    validate_environment || return 1

    # Default to docker if mode not specified
    if [[ -z "$DEPLOYMENT_MODE" ]]; then
        DEPLOYMENT_MODE="docker"
        log_info "Deployment mode: Docker (default)"
    else
        log_info "Deployment mode: $DEPLOYMENT_MODE"
    fi

    local result=0
    if [[ "$DEPLOYMENT_MODE" == "docker" ]]; then
        validate_docker_requirements || return 1
        do_docker_install
        result=$?
    else
        do_install "$branch" "true"
        result=$?
    fi

    show_disk_space "After Fresh Install"

    if [[ $result -eq 0 ]]; then
        log_info "✓ Fresh install completed successfully!"
    else
        log_error "Fresh install failed"
    fi

    return $result
}

# Reinstall/Upgrade - wipe and reinstall while attempting to preserve configs
do_reinstall() {
    local branch="${1:-main}"

    log_step "Starting reinstall (upgrade with clean slate)..."
    show_disk_space "Before Reinstall"

    # Backup config if exists
    local config_backup=""
    if [[ -d "/opt/water-controller/config" ]]; then
        config_backup="/tmp/water-controller-config-backup-$$"
        log_info "Backing up configuration..."
        cp -r /opt/water-controller/config "$config_backup" 2>/dev/null || true
    fi

    # Backup credentials
    local creds_backup=""
    if [[ -f "/opt/water-controller/config/.docker-credentials" ]]; then
        creds_backup="/tmp/water-controller-creds-backup-$$"
        cp /opt/water-controller/config/.docker-credentials "$creds_backup" 2>/dev/null || true
    fi

    # Wipe everything
    do_wipe || {
        log_error "Wipe failed, aborting reinstall"
        return 1
    }

    # Validate environment
    validate_environment || return 1

    # Default to docker if mode not specified
    if [[ -z "$DEPLOYMENT_MODE" ]]; then
        DEPLOYMENT_MODE="docker"
        log_info "Deployment mode: Docker (default)"
    else
        log_info "Deployment mode: $DEPLOYMENT_MODE"
    fi

    local result=0
    if [[ "$DEPLOYMENT_MODE" == "docker" ]]; then
        validate_docker_requirements || return 1
        do_docker_install
        result=$?
    else
        do_install "$branch" "true"
        result=$?
    fi

    # Restore config if backup exists
    if [[ -n "$config_backup" ]] && [[ -d "$config_backup" ]] && [[ $result -eq 0 ]]; then
        log_info "Restoring configuration backup..."
        cp -r "$config_backup"/* /opt/water-controller/config/ 2>/dev/null || true
        rm -rf "$config_backup"
    fi

    # Restore credentials if backup exists
    if [[ -n "$creds_backup" ]] && [[ -f "$creds_backup" ]] && [[ $result -eq 0 ]]; then
        cp "$creds_backup" /opt/water-controller/config/.docker-credentials 2>/dev/null || true
        rm -f "$creds_backup"
    fi

    show_disk_space "After Reinstall"

    if [[ $result -eq 0 ]]; then
        log_info "✓ Reinstall completed successfully!"
    else
        log_error "Reinstall failed"
    fi

    return $result
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
    wipe        Complete removal: containers, images, volumes, configs, logs
    fresh       Wipe everything and install from scratch (automated)
    reinstall   Wipe and reinstall, preserving configs where possible

DEPLOYMENT MODE:
    --mode baremetal    Install directly on host (systemd services)
    --mode docker       Install using Docker containers

    All actions respect --mode. Default: baremetal for install, docker for fresh/reinstall.

OPTIONS:
    --branch <name>     Use specific git branch (default: main)
    --force             Force action even if checks fail
    --dry-run           Show what would be done without making changes
    --keep-config       Keep configuration files when removing
    --yes, -y           Answer yes to all prompts
    --quiet, -q         Suppress non-essential output (errors still shown)
    --verbose, -v       Show detailed output for debugging
    --help, -h          Show this help message
    --version           Show version information

LOGGING:
    Bootstrap operations are logged to: $BOOTSTRAP_LOG
    Backups are stored in: $BACKUP_DIR

QUICK START:
    # Fresh install (wipe + install from scratch)
    curl -fsSL $REPO_RAW_URL/main/bootstrap.sh | sudo bash -s -- fresh

    # Uninstall (complete removal)
    curl -fsSL $REPO_RAW_URL/main/bootstrap.sh | sudo bash -s -- wipe

    # Reinstall/Upgrade (wipe + install, preserve configs)
    curl -fsSL $REPO_RAW_URL/main/bootstrap.sh | sudo bash -s -- reinstall

EXAMPLES:
    # Install with Docker
    curl -fsSL .../bootstrap.sh | sudo bash -s -- install --mode docker

    # Install from develop branch
    curl -fsSL .../bootstrap.sh | sudo bash -s -- install --branch develop

    # Upgrade with dry-run
    curl -fsSL .../bootstrap.sh | sudo bash -s -- upgrade --dry-run

    # Remove but keep config
    curl -fsSL .../bootstrap.sh | sudo bash -s -- remove --keep-config

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
            install|upgrade|remove|wipe|fresh|reinstall)
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
            --verbose|-v)
                VERBOSE_MODE="true"
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
    log_debug "Bootstrap started with args: action=$action branch=$branch force=$force dry_run=$dry_run verbose=$VERBOSE_MODE"

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

    # Validate environment (except for remove/wipe actions which have their own checks)
    if [[ "$action" != "remove" ]] && [[ "$action" != "wipe" ]]; then
        validate_environment || exit 1
    else
        check_root || exit 1
    fi

    # Handle wipe/fresh/reinstall actions immediately
    if [[ "$action" == "wipe" ]]; then
        do_wipe
        exit $?
    fi

    if [[ "$action" == "fresh" ]]; then
        do_fresh "$branch"
        exit $?
    fi

    if [[ "$action" == "reinstall" ]]; then
        do_reinstall "$branch"
        exit $?
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
