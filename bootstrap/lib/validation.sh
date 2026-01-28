#!/bin/bash
# =============================================================================
# Water-Controller Bootstrap - Validation Functions
# =============================================================================
# System validation, requirements checking, and Docker installation.
# Depends on: constants.sh, logging.sh, helpers.sh

# Prevent double-sourcing
[[ -n "${_WTC_VALIDATION_LOADED:-}" ]] && return 0
_WTC_VALIDATION_LOADED=1

# =============================================================================
# Root and Privilege Checks
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

# =============================================================================
# Tool Checks
# =============================================================================

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

# =============================================================================
# Network Checks
# =============================================================================

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

# =============================================================================
# Docker Installation
# =============================================================================

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

# =============================================================================
# Docker Requirements Validation
# =============================================================================

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

# =============================================================================
# Resource Checks
# =============================================================================

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
# Package Validation
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
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        # Get first reclaimable value (Images row) - use awk for portability (no bc/grep -P)
        docker_reclaimable=$(docker system df 2>/dev/null | awk '/Images/ {print $NF}' | head -1) || true
        # Fallback: if awk extraction failed, leave empty
        [[ "$docker_reclaimable" == "RECLAIMABLE" ]] && docker_reclaimable=""
    fi

    if [[ "$VERBOSE_MODE" == "true" ]]; then
        # Verbose: full breakdown
        log_info "=== $label Disk Space ==="
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
        log_info "package-lock.json is in sync"
    else
        log_warn "npm not available, skipping package-lock validation"
    fi

    return 0
}
