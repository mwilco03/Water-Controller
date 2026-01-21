#!/bin/bash
# =============================================================================
# Water-Controller Bootstrap - Helper Functions
# =============================================================================
# Discovery patterns, privilege helpers, cleanup handlers, and user prompts.
# Depends on: constants.sh, logging.sh

# Prevent double-sourcing
[[ -n "${_WTC_HELPERS_LOADED:-}" ]] && return 0
_WTC_HELPERS_LOADED=1

# =============================================================================
# Discovery-First Helper Functions
# =============================================================================
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

# =============================================================================
# Privilege Helpers
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

# =============================================================================
# Cleanup Handlers
# =============================================================================

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

# =============================================================================
# User Interaction
# =============================================================================

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
