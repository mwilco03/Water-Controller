#!/bin/bash
# ============================================================================
# Water Treatment Controller - Port Configuration (Shell)
# ============================================================================
#
# Source this file in shell scripts to get consistent port values:
#   source "${WTC_ROOT:-/opt/water-controller}/config/ports.sh"
#
# All values use WTC_ prefix and can be overridden by environment variables.
# ============================================================================

# Determine config directory
_WTC_CONFIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load the .env file if it exists
if [[ -f "${_WTC_CONFIG_DIR}/ports.env" ]]; then
    # Export all variables from ports.env (skip comments and empty lines)
    set -a
    # shellcheck source=ports.env
    source "${_WTC_CONFIG_DIR}/ports.env"
    set +a
fi

# -----------------------------------------------------------------------------
# Port Variables (with defaults if not set by ports.env)
# -----------------------------------------------------------------------------

# API Server
export WTC_API_PORT="${WTC_API_PORT:-8000}"
export WTC_API_URL="${WTC_API_URL:-http://localhost:${WTC_API_PORT}}"

# Web UI
export WTC_UI_PORT="${WTC_UI_PORT:-8080}"
export WTC_UI_URL="${WTC_UI_URL:-http://localhost:${WTC_UI_PORT}}"
export WTC_UI_HTTPS_PORT="${WTC_UI_HTTPS_PORT:-8443}"

# Docker
export WTC_DOCKER_UI_INTERNAL_PORT="${WTC_DOCKER_UI_INTERNAL_PORT:-3000}"

# Database
export WTC_DB_PORT="${WTC_DB_PORT:-5432}"
export WTC_DB_HOST="${WTC_DB_HOST:-localhost}"

# PROFINET
export WTC_PROFINET_UDP_PORT="${WTC_PROFINET_UDP_PORT:-34964}"
export WTC_PROFINET_TCP_PORT_START="${WTC_PROFINET_TCP_PORT_START:-34962}"
export WTC_PROFINET_TCP_PORT_END="${WTC_PROFINET_TCP_PORT_END:-34963}"

# Modbus
export WTC_MODBUS_TCP_PORT="${WTC_MODBUS_TCP_PORT:-1502}"

# Monitoring
export WTC_GRAYLOG_PORT="${WTC_GRAYLOG_PORT:-12201}"
export WTC_GRAFANA_PORT="${WTC_GRAFANA_PORT:-3000}"

# Derived URLs
export WTC_API_DOCS_URL="${WTC_API_DOCS_URL:-${WTC_API_URL}/api/docs}"
export WTC_API_HEALTH_URL="${WTC_API_HEALTH_URL:-${WTC_API_URL}/health}"
export WTC_WS_URL="${WTC_WS_URL:-ws://localhost:${WTC_API_PORT}/api/v1/ws/live}"

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

# Print all port configuration (useful for debugging)
wtc_print_ports() {
    echo "=== Water Treatment Controller Port Configuration ==="
    echo "API Port:        ${WTC_API_PORT}"
    echo "API URL:         ${WTC_API_URL}"
    echo "UI Port:         ${WTC_UI_PORT}"
    echo "UI URL:          ${WTC_UI_URL}"
    echo "UI HTTPS Port:   ${WTC_UI_HTTPS_PORT}"
    echo "DB Port:         ${WTC_DB_PORT}"
    echo "PROFINET UDP:    ${WTC_PROFINET_UDP_PORT}"
    echo "Modbus TCP:      ${WTC_MODBUS_TCP_PORT}"
    echo "==================================================="
}

# Check if a port is available
wtc_check_port() {
    local port=$1
    if command -v ss &>/dev/null; then
        ! ss -tuln | grep -q ":${port} "
    elif command -v netstat &>/dev/null; then
        ! netstat -tuln | grep -q ":${port} "
    else
        # Fallback: try to bind to the port
        (echo >/dev/tcp/localhost/"${port}") 2>/dev/null && return 1 || return 0
    fi
}

# Wait for a service to be ready on a port
wtc_wait_for_port() {
    local host="${1:-localhost}"
    local port="${2:-${WTC_API_PORT}}"
    local timeout="${3:-30}"
    local elapsed=0

    echo "Waiting for ${host}:${port}..."
    while ! (echo >/dev/tcp/"${host}"/"${port}") 2>/dev/null; do
        sleep 1
        elapsed=$((elapsed + 1))
        if [[ ${elapsed} -ge ${timeout} ]]; then
            echo "Timeout waiting for ${host}:${port}"
            return 1
        fi
    done
    echo "${host}:${port} is ready"
    return 0
}
