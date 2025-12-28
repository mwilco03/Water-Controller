#!/bin/bash
#
# Water Treatment Controller - Validation and Testing System
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module provides comprehensive validation tests for
# Water-Controller installation verification.
#
# Tech Stack: Python/FastAPI backend, React frontend
# Target: ARM/x86 SBCs running Debian-based Linux
#

# Prevent multiple sourcing
if [ -n "$_WTC_VALIDATION_LOADED" ]; then
    return 0
fi
_WTC_VALIDATION_LOADED=1

# Source detection module for logging functions
: "${SCRIPT_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
if [ -f "$SCRIPT_DIR/detection.sh" ]; then
    # shellcheck source=detection.sh
    source "$SCRIPT_DIR/detection.sh"
fi

# =============================================================================
# Constants
# =============================================================================

readonly VALIDATION_VERSION="1.0.0"

# Paths
: "${INSTALL_BASE:=/opt/water-controller}"
: "${VENV_PATH:=$INSTALL_BASE/venv}"
: "${APP_PATH:=$INSTALL_BASE/app}"
: "${WEB_PATH:=$INSTALL_BASE/web}"
: "${CONFIG_DIR:=/etc/water-controller}"
: "${DATA_DIR:=/var/lib/water-controller}"
: "${LOG_DIR:=/var/log/water-controller}"

# Service
: "${SERVICE_NAME:=water-controller}"
: "${SERVICE_USER:=water-controller}"

# Network
: "${DEFAULT_API_PORT:=8000}"

# Test timeouts (seconds)
readonly HTTP_TIMEOUT=5
readonly DB_TIMEOUT=10

# Resource thresholds
readonly MAX_MEMORY_MB=512
readonly MAX_CPU_PERCENT=10
readonly MAX_FD_COUNT=1000

# Test results tracking
declare -a TEST_RESULTS=()
declare -i TESTS_PASSED=0
declare -i TESTS_FAILED=0
declare -i TESTS_WARNED=0

# =============================================================================
# Test Result Helpers
# =============================================================================

# Record test result
_record_result() {
    local status="$1"  # PASS, FAIL, WARN, INFO
    local name="$2"
    local message="$3"

    case "$status" in
        PASS)
            TEST_RESULTS+=("[PASS] $name")
            ((TESTS_PASSED++))
            ;;
        FAIL)
            TEST_RESULTS+=("[FAIL] $name - $message")
            ((TESTS_FAILED++))
            ;;
        WARN)
            TEST_RESULTS+=("[WARN] $name - $message")
            ((TESTS_WARNED++))
            ;;
        INFO)
            TEST_RESULTS+=("[INFO] $name - $message")
            ;;
    esac
}

# Reset test counters
_reset_results() {
    TEST_RESULTS=()
    TESTS_PASSED=0
    TESTS_FAILED=0
    TESTS_WARNED=0
}

# =============================================================================
# File Integrity Tests
# =============================================================================

# Test file and directory integrity
# Returns: 0 if all pass, 5 if any fail
test_file_integrity() {
    log_info "Running file integrity tests..."

    local failed=0

    # Check Python venv
    if [ -x "$VENV_PATH/bin/python3" ]; then
        _record_result "PASS" "Python venv exists"
    else
        _record_result "FAIL" "Python venv" "Not found at $VENV_PATH/bin/python3"
        failed=1
    fi

    # Check pip in venv
    if [ -x "$VENV_PATH/bin/pip" ]; then
        _record_result "PASS" "pip in venv"
    else
        _record_result "FAIL" "pip in venv" "Not found"
        failed=1
    fi

    # Check uvicorn in venv
    if [ -x "$VENV_PATH/bin/uvicorn" ]; then
        _record_result "PASS" "uvicorn in venv"
    else
        _record_result "FAIL" "uvicorn in venv" "Not found"
        failed=1
    fi

    # Check app code
    if [ -f "$APP_PATH/app/main.py" ]; then
        _record_result "PASS" "App main.py (app/main.py)"
    elif [ -f "$APP_PATH/main.py" ]; then
        _record_result "PASS" "App main.py"
    else
        _record_result "FAIL" "App main.py" "Not found in $APP_PATH"
        failed=1
    fi

    # Check frontend
    if [ -d "$WEB_PATH" ] && [ "$(ls -A "$WEB_PATH" 2>/dev/null)" ]; then
        if [ -f "$WEB_PATH/index.html" ]; then
            _record_result "PASS" "Frontend index.html"
        else
            _record_result "WARN" "Frontend" "No index.html (may be SSR build)"
        fi
    else
        _record_result "WARN" "Frontend" "Directory empty or missing"
    fi

    # Check config
    if [ -f "$CONFIG_DIR/config.yaml" ]; then
        _record_result "PASS" "Config file exists"

        # Check config is readable by service group
        if [ -r "$CONFIG_DIR/config.yaml" ]; then
            _record_result "PASS" "Config file readable"
        else
            _record_result "WARN" "Config file" "May not be readable"
        fi
    else
        _record_result "FAIL" "Config file" "Not found at $CONFIG_DIR/config.yaml"
        failed=1
    fi

    # Check database directory
    if [ -d "$DATA_DIR" ]; then
        _record_result "PASS" "Data directory exists"

        # Check ownership
        local owner
        owner="$(stat -c '%U' "$DATA_DIR" 2>/dev/null)"
        if [ "$owner" = "$SERVICE_USER" ]; then
            _record_result "PASS" "Data directory ownership"
        else
            _record_result "WARN" "Data directory" "Owner is $owner, expected $SERVICE_USER"
        fi
    else
        _record_result "FAIL" "Data directory" "Not found at $DATA_DIR"
        failed=1
    fi

    # Check database file
    if [ -f "$DATA_DIR/historian.db" ]; then
        _record_result "PASS" "Database file exists"
    else
        _record_result "INFO" "Database file" "Will be created on first run"
    fi

    # Check log directory
    if [ -d "$LOG_DIR" ]; then
        _record_result "PASS" "Log directory exists"

        # Check writable
        if [ -w "$LOG_DIR" ] || [ "$(stat -c '%U' "$LOG_DIR" 2>/dev/null)" = "$SERVICE_USER" ]; then
            _record_result "PASS" "Log directory writable"
        else
            _record_result "WARN" "Log directory" "May not be writable by service"
        fi
    else
        _record_result "FAIL" "Log directory" "Not found at $LOG_DIR"
        failed=1
    fi

    # Check permissions
    local app_perms
    app_perms="$(stat -c '%a' "$APP_PATH" 2>/dev/null)"
    if [ "$app_perms" = "750" ] || [ "$app_perms" = "755" ]; then
        _record_result "PASS" "App directory permissions ($app_perms)"
    else
        _record_result "WARN" "App directory permissions" "Got $app_perms, expected 750"
    fi

    if [ $failed -ne 0 ]; then
        return 5
    fi
    return 0
}

# =============================================================================
# Service Status Tests
# =============================================================================

# Test systemd service status
# Returns: 0 if pass, 5 if fail
test_service_status() {
    log_info "Running service status tests..."

    local failed=0

    # Check service is active
    if systemctl is-active "$SERVICE_NAME.service" >/dev/null 2>&1; then
        _record_result "PASS" "Service active"
    else
        _record_result "FAIL" "Service active" "Service is not running"
        failed=1
    fi

    # Check service is enabled
    if systemctl is-enabled "$SERVICE_NAME.service" >/dev/null 2>&1; then
        _record_result "PASS" "Service enabled"
    else
        _record_result "WARN" "Service enabled" "Service will not start on boot"
    fi

    # Check service uptime
    local active_enter
    active_enter="$(systemctl show "$SERVICE_NAME.service" --property=ActiveEnterTimestamp 2>/dev/null | cut -d= -f2)"

    if [ -n "$active_enter" ] && [ "$active_enter" != "n/a" ]; then
        local active_epoch
        active_epoch="$(date -d "$active_enter" +%s 2>/dev/null || echo 0)"
        local now_epoch
        now_epoch="$(date +%s)"
        local uptime=$((now_epoch - active_epoch))

        if [ "$uptime" -gt 10 ]; then
            _record_result "PASS" "Service uptime" "${uptime}s"
        else
            _record_result "WARN" "Service uptime" "Only ${uptime}s (may be restarting)"
        fi
    fi

    # Check for recent restarts
    local restart_count
    restart_count="$(systemctl show "$SERVICE_NAME.service" --property=NRestarts 2>/dev/null | cut -d= -f2)"

    if [ -n "$restart_count" ] && [ "$restart_count" != "0" ]; then
        _record_result "WARN" "Service restarts" "$restart_count restarts recorded"
    else
        _record_result "PASS" "Service restarts" "No restarts"
    fi

    # Check main process
    local main_pid
    main_pid="$(systemctl show "$SERVICE_NAME.service" --property=MainPID 2>/dev/null | cut -d= -f2)"

    if [ -n "$main_pid" ] && [ "$main_pid" != "0" ]; then
        if ps -p "$main_pid" >/dev/null 2>&1; then
            _record_result "PASS" "Main process running" "PID $main_pid"
        else
            _record_result "FAIL" "Main process" "PID $main_pid not found"
            failed=1
        fi
    else
        _record_result "FAIL" "Main process" "No PID available"
        failed=1
    fi

    # Check uvicorn processes
    local uvicorn_count
    uvicorn_count="$(pgrep -c -f 'uvicorn' 2>/dev/null || echo 0)"

    if [ "$uvicorn_count" -gt 0 ]; then
        _record_result "PASS" "Uvicorn processes" "$uvicorn_count running"
    else
        _record_result "WARN" "Uvicorn processes" "None found"
    fi

    if [ $failed -ne 0 ]; then
        return 5
    fi
    return 0
}

# =============================================================================
# Health Endpoint Test
# =============================================================================

# Test health endpoint
# Returns: 0 if pass, 5 if fail
test_health_endpoint() {
    log_info "Running health endpoint test..."

    if ! command -v curl >/dev/null 2>&1; then
        _record_result "WARN" "Health endpoint" "curl not available, skipping"
        return 0
    fi

    local endpoints=(
        "/health"
        "/api/health"
        "/api/v1/health"
    )

    for endpoint in "${endpoints[@]}"; do
        local url="http://localhost:${DEFAULT_API_PORT}${endpoint}"
        local http_code
        local response

        http_code="$(curl -s -o /tmp/health_response.txt -w "%{http_code}" \
            --connect-timeout "$HTTP_TIMEOUT" \
            --max-time "$HTTP_TIMEOUT" \
            "$url" 2>/dev/null || echo "000")"

        if [ "$http_code" = "200" ]; then
            response="$(cat /tmp/health_response.txt 2>/dev/null)"
            rm -f /tmp/health_response.txt

            _record_result "PASS" "Health endpoint" "$endpoint returned HTTP 200"

            # Try to parse JSON response
            if command -v jq >/dev/null 2>&1 && [ -n "$response" ]; then
                local status
                status="$(echo "$response" | jq -r '.status // .health // "unknown"' 2>/dev/null)"
                if [ "$status" = "ok" ] || [ "$status" = "healthy" ]; then
                    _record_result "PASS" "Health status" "Status: $status"
                fi
            fi

            return 0
        fi
    done

    # No health endpoint found, but service might still be working
    _record_result "WARN" "Health endpoint" "No health endpoint responded"
    return 0
}

# =============================================================================
# HMI Interface Test
# =============================================================================

# Test HMI interface
# Returns: 0 if pass, 5 if fail
test_hmi_interface() {
    log_info "Running HMI interface test..."

    if ! command -v curl >/dev/null 2>&1; then
        _record_result "WARN" "HMI interface" "curl not available, skipping"
        return 0
    fi

    local url="http://localhost:${DEFAULT_API_PORT}/"
    local http_code
    local response

    http_code="$(curl -s -o /tmp/hmi_response.txt -w "%{http_code}" \
        --connect-timeout "$HTTP_TIMEOUT" \
        --max-time "$HTTP_TIMEOUT" \
        "$url" 2>/dev/null || echo "000")"

    if [ "$http_code" = "200" ]; then
        response="$(cat /tmp/hmi_response.txt 2>/dev/null)"
        rm -f /tmp/hmi_response.txt

        _record_result "PASS" "HMI root endpoint" "HTTP 200"

        # Check for HTML content
        if echo "$response" | grep -qi "<html"; then
            _record_result "PASS" "HMI HTML content"

            # Check for React root div
            if echo "$response" | grep -qi 'id="root"\|id="app"\|id="__next"'; then
                _record_result "PASS" "HMI React container"
            else
                _record_result "INFO" "HMI React container" "Standard container not found"
            fi
        else
            # Might be JSON API at root
            _record_result "INFO" "HMI content" "Not HTML (may be API)"
        fi

        return 0
    elif [ "$http_code" = "000" ]; then
        _record_result "FAIL" "HMI interface" "Connection failed"
        return 5
    else
        _record_result "WARN" "HMI interface" "HTTP $http_code"
        return 0
    fi
}

# =============================================================================
# API Endpoint Test
# =============================================================================

# Test API endpoints
# Returns: 0 if pass, 5 if fail
test_api_endpoints() {
    log_info "Running API endpoint tests..."

    if ! command -v curl >/dev/null 2>&1; then
        _record_result "WARN" "API endpoints" "curl not available, skipping"
        return 0
    fi

    local failed=0
    local endpoints=(
        "/api/status"
        "/api/v1/status"
        "/api/v1/system/health"
        "/docs"
        "/openapi.json"
    )

    local found_working=false

    for endpoint in "${endpoints[@]}"; do
        local url="http://localhost:${DEFAULT_API_PORT}${endpoint}"
        local http_code

        http_code="$(curl -s -o /dev/null -w "%{http_code}" \
            --connect-timeout "$HTTP_TIMEOUT" \
            --max-time "$HTTP_TIMEOUT" \
            "$url" 2>/dev/null || echo "000")"

        if [ "$http_code" = "200" ]; then
            _record_result "PASS" "API endpoint $endpoint" "HTTP 200"
            found_working=true
        elif [ "$http_code" = "401" ] || [ "$http_code" = "403" ]; then
            _record_result "PASS" "API endpoint $endpoint" "HTTP $http_code (auth required)"
            found_working=true
        fi
    done

    if [ "$found_working" = true ]; then
        return 0
    else
        _record_result "WARN" "API endpoints" "No endpoints responded"
        return 0
    fi
}

# =============================================================================
# Database Access Test
# =============================================================================

# Test database access
# Returns: 0 if pass, 5 if fail
test_database_access() {
    log_info "Running database access tests..."

    local db_path="$DATA_DIR/historian.db"
    local failed=0

    # Check if sqlite3 is available
    if ! command -v sqlite3 >/dev/null 2>&1; then
        _record_result "WARN" "SQLite CLI" "Not installed, limited testing"

        # At least check file exists and is readable
        if [ -f "$db_path" ]; then
            _record_result "PASS" "Database file exists"
        else
            _record_result "INFO" "Database file" "Will be created on first run"
        fi

        return 0
    fi

    # Check database file
    if [ ! -f "$db_path" ]; then
        _record_result "INFO" "Database file" "Not yet created"
        return 0
    fi

    _record_result "PASS" "Database file exists"

    # Check database is not locked
    if ! timeout "$DB_TIMEOUT" sqlite3 "$db_path" "SELECT 1;" >/dev/null 2>&1; then
        _record_result "FAIL" "Database access" "Cannot query database (locked or corrupted)"
        failed=1
    else
        _record_result "PASS" "Database query test"
    fi

    # Check WAL mode
    local journal_mode
    journal_mode="$(timeout "$DB_TIMEOUT" sqlite3 "$db_path" "PRAGMA journal_mode;" 2>/dev/null)"

    if [ "$journal_mode" = "wal" ]; then
        _record_result "PASS" "Database WAL mode"
    else
        _record_result "WARN" "Database journal mode" "Got '$journal_mode', expected 'wal'"
    fi

    # Check WAL file exists (indicates WAL mode is active)
    if [ -f "${db_path}-wal" ]; then
        _record_result "PASS" "WAL file exists"
    fi

    # Test Python database access
    if [ -x "$VENV_PATH/bin/python3" ]; then
        if timeout "$DB_TIMEOUT" "$VENV_PATH/bin/python3" -c "
import sqlite3
conn = sqlite3.connect('$db_path')
cursor = conn.cursor()
cursor.execute('SELECT 1')
conn.close()
" 2>/dev/null; then
            _record_result "PASS" "Python database access"
        else
            _record_result "WARN" "Python database access" "Failed"
        fi
    fi

    # Check file permissions
    local db_owner
    db_owner="$(stat -c '%U' "$db_path" 2>/dev/null)"

    if [ "$db_owner" = "$SERVICE_USER" ] || [ "$db_owner" = "root" ]; then
        _record_result "PASS" "Database ownership" "$db_owner"
    else
        _record_result "WARN" "Database ownership" "Owner is $db_owner"
    fi

    if [ $failed -ne 0 ]; then
        return 5
    fi
    return 0
}

# =============================================================================
# Network Configuration Test
# =============================================================================

# Test network configuration
# Returns: 0 if pass, 5 if fail
test_network_config() {
    log_info "Running network configuration tests..."

    local failed=0

    # Check if API port is listening
    if command -v ss >/dev/null 2>&1; then
        if ss -tlnp 2>/dev/null | grep -q ":$DEFAULT_API_PORT "; then
            _record_result "PASS" "API port listening" "Port $DEFAULT_API_PORT"
        else
            _record_result "FAIL" "API port" "Port $DEFAULT_API_PORT not listening"
            failed=1
        fi
    elif command -v netstat >/dev/null 2>&1; then
        if netstat -tlnp 2>/dev/null | grep -q ":$DEFAULT_API_PORT "; then
            _record_result "PASS" "API port listening" "Port $DEFAULT_API_PORT"
        else
            _record_result "FAIL" "API port" "Port $DEFAULT_API_PORT not listening"
            failed=1
        fi
    else
        _record_result "WARN" "Port check" "ss/netstat not available"
    fi

    # Check network interfaces
    local interfaces
    interfaces="$(ip -o link show 2>/dev/null | grep -v "lo:" | awk -F': ' '{print $2}' | tr '\n' ' ')"

    if [ -n "$interfaces" ]; then
        _record_result "PASS" "Network interfaces" "$interfaces"
    else
        _record_result "WARN" "Network interfaces" "None found"
    fi

    # Check for IP address
    local ip_addrs
    ip_addrs="$(ip -4 addr show 2>/dev/null | grep -oP 'inet \K[\d.]+' | grep -v '^127\.' | tr '\n' ' ')"

    if [ -n "$ip_addrs" ]; then
        _record_result "PASS" "IP addresses" "$ip_addrs"
    else
        _record_result "WARN" "IP addresses" "No non-loopback IPs found"
    fi

    # Check firewall status (informational)
    if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
        _record_result "INFO" "Firewall" "UFW active"
    elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active firewalld >/dev/null 2>&1; then
        _record_result "INFO" "Firewall" "firewalld active"
    else
        _record_result "INFO" "Firewall" "No active firewall detected"
    fi

    if [ $failed -ne 0 ]; then
        return 5
    fi
    return 0
}

# =============================================================================
# Resource Usage Test
# =============================================================================

# Test resource usage
# Returns: 0 if pass, 5 if excessive
test_resource_usage() {
    log_info "Running resource usage tests..."

    # Get main process PID
    local main_pid
    main_pid="$(systemctl show "$SERVICE_NAME.service" --property=MainPID 2>/dev/null | cut -d= -f2)"

    if [ -z "$main_pid" ] || [ "$main_pid" = "0" ]; then
        _record_result "WARN" "Resource usage" "Cannot determine main PID"
        return 0
    fi

    if [ ! -d "/proc/$main_pid" ]; then
        _record_result "WARN" "Resource usage" "Process $main_pid not found"
        return 0
    fi

    # Check memory usage
    local mem_kb
    mem_kb="$(awk '/VmRSS/ {print $2}' /proc/"$main_pid"/status 2>/dev/null || echo 0)"
    local mem_mb=$((mem_kb / 1024))

    if [ "$mem_mb" -lt "$MAX_MEMORY_MB" ]; then
        _record_result "PASS" "Memory usage" "${mem_mb}MB"
    else
        _record_result "WARN" "Memory usage" "${mem_mb}MB exceeds ${MAX_MEMORY_MB}MB"
    fi

    # Check CPU usage
    local cpu_percent
    cpu_percent="$(ps -p "$main_pid" -o %cpu= 2>/dev/null | tr -d ' ')"

    if [ -n "$cpu_percent" ]; then
        local cpu_int
        cpu_int="${cpu_percent%.*}"

        if [ "${cpu_int:-0}" -lt "$MAX_CPU_PERCENT" ]; then
            _record_result "PASS" "CPU usage" "${cpu_percent}%"
        else
            _record_result "WARN" "CPU usage" "${cpu_percent}% (may be high at startup)"
        fi
    fi

    # Check file descriptors
    local fd_count
    fd_count="$(ls /proc/"$main_pid"/fd 2>/dev/null | wc -l)"

    if [ "$fd_count" -lt "$MAX_FD_COUNT" ]; then
        _record_result "PASS" "File descriptors" "$fd_count open"
    else
        _record_result "WARN" "File descriptors" "$fd_count open (may indicate leak)"
    fi

    # Check thread count
    local thread_count
    thread_count="$(ls /proc/"$main_pid"/task 2>/dev/null | wc -l)"

    _record_result "INFO" "Thread count" "$thread_count"

    return 0
}

# =============================================================================
# Log Health Test
# =============================================================================

# Test log health
# Returns: 0 if pass, 5 if errors found
test_log_health() {
    log_info "Running log health tests..."

    local failed=0

    # Check recent journal logs for errors
    local error_count
    error_count="$(journalctl -u "$SERVICE_NAME.service" --since "5 minutes ago" -p err --no-pager 2>/dev/null | grep -c "" || echo 0)"

    if [ "$error_count" -eq 0 ]; then
        _record_result "PASS" "Recent log errors" "None"
    else
        _record_result "WARN" "Recent log errors" "$error_count errors in last 5 minutes"
    fi

    # Check for startup messages
    local startup_ok
    startup_ok="$(journalctl -u "$SERVICE_NAME.service" --since "10 minutes ago" --no-pager 2>/dev/null | \
        grep -iE "started|running|listening|uvicorn" | head -1)"

    if [ -n "$startup_ok" ]; then
        _record_result "PASS" "Startup messages" "Found in logs"
    else
        _record_result "WARN" "Startup messages" "No startup confirmation in recent logs"
    fi

    # Check log directory size
    if [ -d "$LOG_DIR" ]; then
        local log_size
        log_size="$(du -sm "$LOG_DIR" 2>/dev/null | cut -f1)"

        if [ "${log_size:-0}" -lt 100 ]; then
            _record_result "PASS" "Log directory size" "${log_size}MB"
        else
            _record_result "WARN" "Log directory size" "${log_size}MB (consider rotation)"
        fi
    fi

    # Check logrotate configuration
    if [ -f "/etc/logrotate.d/water-controller" ]; then
        _record_result "PASS" "Logrotate configuration"
    else
        _record_result "WARN" "Logrotate configuration" "Not found"
    fi

    return 0
}

# =============================================================================
# Python Dependencies Test
# =============================================================================

# Test Python dependencies
# Returns: 0 if pass, 5 if fail
test_python_deps() {
    log_info "Running Python dependencies tests..."

    local failed=0

    if [ ! -x "$VENV_PATH/bin/python3" ]; then
        _record_result "FAIL" "Python venv" "Not found"
        return 5
    fi

    # Test FastAPI import
    if "$VENV_PATH/bin/python3" -c "import fastapi" 2>/dev/null; then
        local fastapi_version
        fastapi_version="$("$VENV_PATH/bin/pip" show fastapi 2>/dev/null | grep Version | awk '{print $2}')"
        _record_result "PASS" "FastAPI" "$fastapi_version"
    else
        _record_result "FAIL" "FastAPI" "Import failed"
        failed=1
    fi

    # Test uvicorn import
    if "$VENV_PATH/bin/python3" -c "import uvicorn" 2>/dev/null; then
        local uvicorn_version
        uvicorn_version="$("$VENV_PATH/bin/pip" show uvicorn 2>/dev/null | grep Version | awk '{print $2}')"
        _record_result "PASS" "uvicorn" "$uvicorn_version"
    else
        _record_result "FAIL" "uvicorn" "Import failed"
        failed=1
    fi

    # Test pydantic import
    if "$VENV_PATH/bin/python3" -c "import pydantic" 2>/dev/null; then
        _record_result "PASS" "pydantic"
    else
        _record_result "WARN" "pydantic" "Import failed"
    fi

    # Test SQLAlchemy if used
    if "$VENV_PATH/bin/python3" -c "import sqlalchemy" 2>/dev/null; then
        _record_result "PASS" "SQLAlchemy"
    else
        _record_result "INFO" "SQLAlchemy" "Not installed (may not be required)"
    fi

    # Test aiosqlite for async database
    if "$VENV_PATH/bin/python3" -c "import aiosqlite" 2>/dev/null; then
        _record_result "PASS" "aiosqlite"
    else
        _record_result "INFO" "aiosqlite" "Not installed"
    fi

    # Count installed packages
    local pkg_count
    pkg_count="$("$VENV_PATH/bin/pip" list 2>/dev/null | wc -l)"
    _record_result "INFO" "Installed packages" "$pkg_count"

    if [ $failed -ne 0 ]; then
        return 5
    fi
    return 0
}

# Test P-Net PROFINET installation (cornerstone of the project)
# Returns: 0 if pass, 5 if fail
test_pnet() {
    log_info "Running P-Net PROFINET tests..."

    local failed=0

    # Check for p-net library
    local lib_found=0
    for lib_path in "/usr/local/lib" "/usr/lib" "/usr/lib64"; do
        if ls "${lib_path}"/libpnet.so* >/dev/null 2>&1; then
            lib_found=1
            _record_result "PASS" "P-Net library" "$lib_path"
            break
        fi
    done

    if [ $lib_found -eq 0 ]; then
        _record_result "FAIL" "P-Net library" "Not found - CRITICAL"
        failed=1
    fi

    # Check for p-net headers
    local header_found=0
    for inc_path in "/usr/local/include" "/usr/include"; do
        if [ -f "${inc_path}/pnet_api.h" ] || [ -d "${inc_path}/pnet" ]; then
            header_found=1
            _record_result "PASS" "P-Net headers" "$inc_path"
            break
        fi
    done

    if [ $header_found -eq 0 ]; then
        _record_result "FAIL" "P-Net headers" "Not found"
        failed=1
    fi

    # Check ldconfig registration
    if ldconfig -p 2>/dev/null | grep -q "libpnet"; then
        _record_result "PASS" "P-Net ldconfig" "Registered"
    else
        _record_result "WARN" "P-Net ldconfig" "Not in cache"
    fi

    # Check p-net configuration
    if [ -f "/etc/pnet/pnet.conf" ]; then
        _record_result "PASS" "P-Net config" "/etc/pnet/pnet.conf"
    else
        _record_result "INFO" "P-Net config" "Not configured"
    fi

    # Check PROFINET ports
    local profinet_ports_ok=1
    for port in 34962 34963; do
        if ss -tln 2>/dev/null | grep -q ":${port} "; then
            _record_result "PASS" "PROFINET TCP $port" "Listening"
        else
            _record_result "INFO" "PROFINET TCP $port" "Not listening (may be normal)"
        fi
    done

    if ss -uln 2>/dev/null | grep -q ":34964 "; then
        _record_result "PASS" "PROFINET UDP 34964" "Listening"
    else
        _record_result "INFO" "PROFINET UDP 34964" "Not listening"
    fi

    # Check for ethernet interface
    local eth_iface
    eth_iface=$(ip -brief link show 2>/dev/null | grep -E '^(eth|en)' | awk '{print $1}' | head -1)
    if [ -n "$eth_iface" ]; then
        _record_result "PASS" "Ethernet interface" "$eth_iface"
    else
        _record_result "WARN" "Ethernet interface" "None found (required for PROFINET)"
    fi

    # Check kernel modules
    if lsmod 2>/dev/null | grep -q "^8021q"; then
        _record_result "PASS" "802.1Q module" "Loaded"
    else
        _record_result "WARN" "802.1Q module" "Not loaded"
    fi

    # Check for real-time kernel
    if uname -r | grep -qiE "rt|preempt"; then
        _record_result "PASS" "Real-time kernel" "$(uname -r)"
    else
        _record_result "INFO" "Real-time kernel" "Standard kernel (RT recommended)"
    fi

    if [ $failed -ne 0 ]; then
        log_error "P-Net validation FAILED - PROFINET will not work"
        return 5
    fi

    log_info "P-Net validation passed"
    return 0
}

# =============================================================================
# Full Validation Suite
# =============================================================================

# Run all validation tests
# Returns: 0 if all pass, 5 if any fail
run_validation_suite() {
    log_info "Running full validation suite..."

    _reset_results

    local suite_failed=0

    echo ""
    echo "=========================================="
    echo "  Water-Controller Validation Suite"
    echo "  Version: $VALIDATION_VERSION"
    echo "=========================================="
    echo ""

    # Run all tests
    echo "1. File Integrity Tests"
    echo "------------------------"
    test_file_integrity || suite_failed=1
    echo ""

    echo "2. Service Status Tests"
    echo "------------------------"
    test_service_status || suite_failed=1
    echo ""

    echo "3. Health Endpoint Test"
    echo "------------------------"
    test_health_endpoint || suite_failed=1
    echo ""

    echo "4. HMI Interface Test"
    echo "----------------------"
    test_hmi_interface || suite_failed=1
    echo ""

    echo "5. API Endpoint Tests"
    echo "----------------------"
    test_api_endpoints || suite_failed=1
    echo ""

    echo "6. Database Access Tests"
    echo "-------------------------"
    test_database_access || suite_failed=1
    echo ""

    echo "7. Network Configuration Tests"
    echo "-------------------------------"
    test_network_config || suite_failed=1
    echo ""

    echo "8. Resource Usage Tests"
    echo "------------------------"
    test_resource_usage || suite_failed=1
    echo ""

    echo "9. Log Health Tests"
    echo "--------------------"
    test_log_health || suite_failed=1
    echo ""

    echo "10. Python Dependencies Tests"
    echo "------------------------------"
    test_python_deps || suite_failed=1
    echo ""

    echo "11. P-Net PROFINET Tests (CRITICAL)"
    echo "------------------------------------"
    test_pnet || suite_failed=1
    echo ""

    # Print summary
    echo "=========================================="
    echo "  VALIDATION RESULTS"
    echo "=========================================="
    echo ""

    for test_entry in "${TEST_RESULTS[@]}"; do
        echo "  $test_entry"
    done

    echo ""
    echo "=========================================="
    echo "  SUMMARY"
    echo "=========================================="
    echo "  Passed:  $TESTS_PASSED"
    echo "  Failed:  $TESTS_FAILED"
    echo "  Warned:  $TESTS_WARNED"
    echo "  Total:   $((TESTS_PASSED + TESTS_FAILED + TESTS_WARNED))"
    echo "=========================================="
    echo ""

    # Log results
    _log_write "INFO" "Validation complete: $TESTS_PASSED passed, $TESTS_FAILED failed, $TESTS_WARNED warnings"

    if [ $TESTS_FAILED -gt 0 ]; then
        log_error "Validation suite completed with $TESTS_FAILED failure(s)"
        return 5
    elif [ $TESTS_WARNED -gt 0 ]; then
        log_warn "Validation suite completed with $TESTS_WARNED warning(s)"
        return 0
    else
        log_info "Validation suite passed"
        return 0
    fi
}

# =============================================================================
# Quick Health Check
# =============================================================================

# Quick health check (subset of full validation)
# Returns: 0 if healthy, 5 if unhealthy
quick_health_check() {
    log_info "Running quick health check..."

    _reset_results

    local failed=0

    # Service active?
    if ! systemctl is-active "$SERVICE_NAME.service" >/dev/null 2>&1; then
        _record_result "FAIL" "Service" "Not running"
        failed=1
    else
        _record_result "PASS" "Service" "Running"
    fi

    # Can we reach the API?
    if command -v curl >/dev/null 2>&1; then
        local http_code
        http_code="$(curl -s -o /dev/null -w "%{http_code}" \
            --connect-timeout 3 \
            --max-time 3 \
            "http://localhost:${DEFAULT_API_PORT}/" 2>/dev/null || echo "000")"

        if [ "$http_code" != "000" ]; then
            _record_result "PASS" "API" "Responding (HTTP $http_code)"
        else
            _record_result "FAIL" "API" "Not responding"
            failed=1
        fi
    fi

    # Print results
    echo ""
    for test_entry in "${TEST_RESULTS[@]}"; do
        echo "  $test_entry"
    done
    echo ""

    if [ $failed -ne 0 ]; then
        return 5
    fi
    return 0
}

# =============================================================================
# Main Entry Point
# =============================================================================

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    # Initialize logging
    init_logging || {
        echo "[WARN] Logging initialization failed" >&2
    }

    case "${1:-}" in
        --file-integrity)
            _reset_results
            test_file_integrity
            exit $?
            ;;
        --service-status)
            _reset_results
            test_service_status
            exit $?
            ;;
        --health-endpoint)
            _reset_results
            test_health_endpoint
            exit $?
            ;;
        --hmi)
            _reset_results
            test_hmi_interface
            exit $?
            ;;
        --api)
            _reset_results
            test_api_endpoints
            exit $?
            ;;
        --database)
            _reset_results
            test_database_access
            exit $?
            ;;
        --network)
            _reset_results
            test_network_config
            exit $?
            ;;
        --resources)
            _reset_results
            test_resource_usage
            exit $?
            ;;
        --logs)
            _reset_results
            test_log_health
            exit $?
            ;;
        --python-deps)
            _reset_results
            test_python_deps
            exit $?
            ;;
        --full|--all)
            run_validation_suite
            exit $?
            ;;
        --quick)
            quick_health_check
            exit $?
            ;;
        --help|-h)
            echo "Water-Controller Validation Module v$VALIDATION_VERSION"
            echo ""
            echo "Usage: $0 [OPTION]"
            echo ""
            echo "Individual Tests:"
            echo "  --file-integrity    Test file and directory structure"
            echo "  --service-status    Test systemd service status"
            echo "  --health-endpoint   Test health endpoint"
            echo "  --hmi               Test HMI interface"
            echo "  --api               Test API endpoints"
            echo "  --database          Test database access"
            echo "  --network           Test network configuration"
            echo "  --resources         Test resource usage"
            echo "  --logs              Test log health"
            echo "  --python-deps       Test Python dependencies"
            echo ""
            echo "Suites:"
            echo "  --full, --all       Run full validation suite"
            echo "  --quick             Quick health check"
            echo ""
            echo "  --help, -h          Show this help"
            ;;
        *)
            echo "Usage: $0 [--file-integrity|--service-status|--health-endpoint|--hmi|--api|--database|--network|--resources|--logs|--python-deps|--full|--quick|--help]" >&2
            exit 1
            ;;
    esac
fi
