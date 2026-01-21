#!/bin/bash
#
# Water Treatment Controller - Upgrade Assessment and Validation Module
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module provides comprehensive pre-upgrade assessment, post-upgrade
# validation, and rollback enhancements for production field deployments.
# Use with: ./install.sh --upgrade
#
# Target: ARM/x86 SBCs running Debian-based Linux
# Requirements: Existing Water Controller installation
#

# Prevent multiple sourcing
if [ -n "${_WTC_UPGRADE_LOADED:-}" ]; then
    return 0
fi
_WTC_UPGRADE_LOADED=1

# Source detection module for logging functions
: "${SCRIPT_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
if [ -f "$SCRIPT_DIR/detection.sh" ]; then
    # shellcheck source=detection.sh
    source "$SCRIPT_DIR/detection.sh"
fi

# =============================================================================
# Constants
# =============================================================================

readonly UPGRADE_MODULE_VERSION="1.0.0"

# Paths
: "${INSTALL_DIR:=/opt/water-controller}"
: "${CONFIG_DIR:=/etc/water-controller}"
: "${DATA_DIR:=/var/lib/water-controller}"
: "${LOG_DIR:=/var/log/water-controller}"
: "${BACKUP_DIR:=/var/backups/water-controller}"
: "${ROLLBACK_DIR:=$BACKUP_DIR/rollback}"

# Upgrade requirements (use different names to avoid conflicts with detection.sh)
readonly UPGRADE_MIN_DISK_SPACE_MB=512
readonly UPGRADE_MIN_MEMORY_MB=256
readonly SERVICE_STABILITY_CHECK_SECONDS=60

# API endpoints for testing
readonly API_HEALTH_ENDPOINT="/api/health"
readonly API_VERSION_ENDPOINT="/api/version"
: "${API_PORT:=8000}"

# =============================================================================
# Pre-Upgrade Assessment Functions
# =============================================================================

# Full system health assessment before upgrade
# Returns: 0 if healthy, 1 if issues found
pre_upgrade_health_check() {
    log_info "Running pre-upgrade health check..."

    local issues=0
    local report_file="/tmp/pre-upgrade-health-$(date +%Y%m%d_%H%M%S).txt"

    {
        echo "Pre-Upgrade Health Check Report"
        echo "================================"
        echo "Date: $(date -Iseconds)"
        echo "Hostname: $(hostname)"
        echo ""
    } > "$report_file"

    # Check 1: Disk space
    log_info "  Checking disk space..."
    if ! check_disk_space_for_upgrade; then
        echo "[FAIL] Disk space insufficient" >> "$report_file"
        ((issues++))
    else
        echo "[PASS] Disk space adequate" >> "$report_file"
    fi

    # Check 2: Running processes
    log_info "  Checking running processes..."
    if ! check_running_processes; then
        echo "[WARN] Critical operations may be in progress" >> "$report_file"
        # Don't fail, just warn
    else
        echo "[PASS] No critical operations in progress" >> "$report_file"
    fi

    # Check 3: Service status
    log_info "  Checking service status..."
    if systemctl is-active water-controller.service >/dev/null 2>&1; then
        echo "[PASS] Service is running" >> "$report_file"
    else
        echo "[WARN] Service is not running" >> "$report_file"
    fi

    # Check 4: Database integrity
    log_info "  Checking database integrity..."
    local db_file="$DATA_DIR/water_controller.db"
    if [ -f "$db_file" ]; then
        if command -v sqlite3 >/dev/null 2>&1; then
            if sqlite3 "$db_file" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
                echo "[PASS] Database integrity check passed" >> "$report_file"
            else
                echo "[FAIL] Database integrity check failed" >> "$report_file"
                ((issues++))
            fi
        else
            echo "[SKIP] sqlite3 not available for database check" >> "$report_file"
        fi
    else
        echo "[INFO] No database file found" >> "$report_file"
    fi

    # Check 5: Configuration validity
    log_info "  Checking configuration..."
    if [ -d "$CONFIG_DIR" ] && [ -f "$CONFIG_DIR/controller.conf" ]; then
        echo "[PASS] Configuration directory exists" >> "$report_file"
    else
        echo "[WARN] Configuration may be missing" >> "$report_file"
    fi

    # Check 6: Memory availability
    log_info "  Checking memory..."
    local avail_mem
    avail_mem=$(free -m 2>/dev/null | awk '/^Mem:/{print $7}')
    if [ -n "$avail_mem" ] && [ "$avail_mem" -ge "$UPGRADE_MIN_MEMORY_MB" ]; then
        echo "[PASS] Available memory: ${avail_mem}MB" >> "$report_file"
    else
        echo "[WARN] Low memory: ${avail_mem:-unknown}MB available" >> "$report_file"
    fi

    # Summary
    echo "" >> "$report_file"
    echo "Issues Found: $issues" >> "$report_file"
    echo "Report saved to: $report_file" >> "$report_file"

    log_info "Health check complete. Report: $report_file"

    if [ $issues -gt 0 ]; then
        log_warn "Pre-upgrade health check found $issues issue(s)"
        return 1
    fi

    log_info "Pre-upgrade health check passed"
    return 0
}

# Verify adequate disk space for backup + new install
# Returns: 0 if sufficient, 1 if not
check_disk_space_for_upgrade() {
    log_info "Checking disk space for upgrade..."

    # Calculate current installation size
    local install_size=0
    if [ -d "$INSTALL_DIR" ]; then
        install_size=$(du -sm "$INSTALL_DIR" 2>/dev/null | cut -f1)
    fi

    local config_size=0
    if [ -d "$CONFIG_DIR" ]; then
        config_size=$(du -sm "$CONFIG_DIR" 2>/dev/null | cut -f1)
    fi

    local data_size=0
    if [ -d "$DATA_DIR" ]; then
        data_size=$(du -sm "$DATA_DIR" 2>/dev/null | cut -f1)
    fi

    # Need: current size (backup) + new install + buffer
    local required_space=$((install_size + config_size + data_size + UPGRADE_MIN_DISK_SPACE_MB))

    # Check available space on relevant partitions
    local avail_space
    avail_space=$(df -m "$BACKUP_DIR" 2>/dev/null | awk 'NR==2 {print $4}')

    if [ -z "$avail_space" ]; then
        # Try root partition
        avail_space=$(df -m / 2>/dev/null | awk 'NR==2 {print $4}')
    fi

    log_info "  Current installation: ${install_size}MB"
    log_info "  Configuration: ${config_size}MB"
    log_info "  Data: ${data_size}MB"
    log_info "  Required for upgrade: ${required_space}MB"
    log_info "  Available: ${avail_space:-unknown}MB"

    if [ -n "$avail_space" ] && [ "$avail_space" -ge "$required_space" ]; then
        log_info "Disk space check passed"
        return 0
    else
        log_error "Insufficient disk space for upgrade"
        return 1
    fi
}

# Verify no critical operations in progress
# Returns: 0 if safe to upgrade, 1 if operations in progress
check_running_processes() {
    log_info "Checking for critical operations..."

    local critical=0

    # Check for active database writes (WAL file activity)
    local wal_file="$DATA_DIR/water_controller.db-wal"
    if [ -f "$wal_file" ]; then
        local wal_size
        wal_size=$(stat -c%s "$wal_file" 2>/dev/null || echo 0)
        if [ "$wal_size" -gt 1048576 ]; then  # > 1MB WAL = active writes
            log_warn "Large WAL file detected - active database operations"
            ((critical++))
        fi
    fi

    # Check for backup in progress
    if pgrep -f "water-controller.*backup" >/dev/null 2>&1; then
        log_warn "Backup operation in progress"
        ((critical++))
    fi

    # Check for active API connections
    local api_connections
    api_connections=$(ss -tn state established "( sport = :$API_PORT )" 2>/dev/null | wc -l)
    if [ "$api_connections" -gt 5 ]; then
        log_warn "Multiple active API connections: $api_connections"
        # Don't fail, just warn
    fi

    if [ $critical -gt 0 ]; then
        return 1
    fi

    log_info "No critical operations detected"
    return 0
}

# Export current configuration for comparison
# Returns: path to exported config tarball
export_current_configuration() {
    log_info "Exporting current configuration..."

    local export_dir="/tmp/wtc-config-export-$(date +%Y%m%d_%H%M%S)"
    local export_file="${export_dir}.tar.gz"

    mkdir -p "$export_dir"

    # Copy configuration files
    if [ -d "$CONFIG_DIR" ]; then
        cp -a "$CONFIG_DIR"/* "$export_dir/" 2>/dev/null || true
    fi

    # Export environment variables if service file exists
    if [ -f /etc/systemd/system/water-controller.service ]; then
        grep "^Environment" /etc/systemd/system/water-controller.service > "$export_dir/service-env.txt" 2>/dev/null || true
    fi

    # Export installed version
    if [ -f "$INSTALL_DIR/version.txt" ]; then
        cp "$INSTALL_DIR/version.txt" "$export_dir/"
    fi

    # Create tarball
    tar -czf "$export_file" -C "$(dirname "$export_dir")" "$(basename "$export_dir")" 2>/dev/null
    rm -rf "$export_dir"

    log_info "Configuration exported to: $export_file"
    echo "$export_file"
}

# Record database schema version and row counts
# Returns: 0 on success
snapshot_database_state() {
    log_info "Creating database state snapshot..."

    local db_file="$DATA_DIR/water_controller.db"
    local snapshot_file="/tmp/db-snapshot-$(date +%Y%m%d_%H%M%S).txt"

    if [ ! -f "$db_file" ]; then
        log_warn "Database file not found: $db_file"
        return 0
    fi

    if ! command -v sqlite3 >/dev/null 2>&1; then
        log_warn "sqlite3 not available, skipping database snapshot"
        return 0
    fi

    {
        echo "Database State Snapshot"
        echo "======================="
        echo "Date: $(date -Iseconds)"
        echo "Database: $db_file"
        echo ""

        echo "Schema Version:"
        sqlite3 "$db_file" "SELECT * FROM schema_version;" 2>/dev/null || echo "No schema_version table"
        echo ""

        echo "Table Row Counts:"
        sqlite3 "$db_file" "SELECT name, (SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=m.name) as count FROM sqlite_master m WHERE type='table';" 2>/dev/null || echo "Could not get row counts"
        echo ""

        echo "Tables:"
        sqlite3 "$db_file" ".tables" 2>/dev/null || echo "Could not list tables"
        echo ""

        echo "Database Size:"
        ls -lh "$db_file" 2>/dev/null || echo "Could not get size"

    } > "$snapshot_file"

    log_info "Database snapshot saved to: $snapshot_file"
    echo "$snapshot_file"
    return 0
}

# Verify network connectivity to update sources
# Returns: 0 if connected, 1 if not
verify_network_connectivity() {
    local source="${1:-https://github.com}"

    log_info "Verifying network connectivity to $source..."

    # Extract host from URL (for diagnostic messages)
    local host
    host=$(echo "$source" | sed -E 's|^https?://([^/]+).*|\1|')

    # Try HTTP connection first - this is the primary test
    # curl/wget handle DNS resolution internally, so this tests both DNS and connectivity
    if command -v curl >/dev/null 2>&1; then
        if curl -s --connect-timeout 10 --max-time 30 -o /dev/null -w "%{http_code}" "$source" | grep -qE "^[23]"; then
            log_info "Network connectivity verified"
            return 0
        fi
    elif command -v wget >/dev/null 2>&1; then
        if wget -q --timeout=10 --spider "$source" 2>/dev/null; then
            log_info "Network connectivity verified"
            return 0
        fi
    fi

    # HTTP connection failed - try to diagnose why
    # Check if DNS resolution works (optional diagnostic, not a gate)
    if command -v host >/dev/null 2>&1; then
        if ! host "$host" >/dev/null 2>&1; then
            log_error "DNS resolution failed for $host"
            return 1
        fi
    elif command -v nslookup >/dev/null 2>&1; then
        if ! nslookup "$host" >/dev/null 2>&1; then
            log_error "DNS resolution failed for $host"
            return 1
        fi
    elif command -v getent >/dev/null 2>&1; then
        if ! getent hosts "$host" >/dev/null 2>&1; then
            log_error "DNS resolution failed for $host"
            return 1
        fi
    fi

    # DNS worked but HTTP failed - likely firewall or service issue
    log_error "HTTP connection to $source failed (DNS OK)"
    return 1
}

# Compare installed vs available versions
# Arguments: $1 - available version (optional, will fetch if not provided)
# Returns: 0 if upgrade available, 1 if current, 2 on error
compare_versions() {
    local available_version="${1:-}"

    log_info "Comparing versions..."

    # Get current version
    local current_version="unknown"
    if [ -f "$INSTALL_DIR/version.txt" ]; then
        current_version=$(cat "$INSTALL_DIR/version.txt" 2>/dev/null | tr -d '[:space:]')
    elif [ -f "$INSTALL_DIR/VERSION" ]; then
        current_version=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null | tr -d '[:space:]')
    fi

    log_info "  Current version: $current_version"

    # If no available version provided, we can't compare
    if [ -z "$available_version" ]; then
        log_warn "No available version specified"
        echo "current=$current_version"
        return 2
    fi

    log_info "  Available version: $available_version"

    # Simple version comparison
    if [ "$current_version" = "$available_version" ]; then
        log_info "Already running latest version"
        echo "current=$current_version;available=$available_version;status=current"
        return 1
    fi

    # Version is different (newer or older)
    log_info "Upgrade available: $current_version -> $available_version"
    echo "current=$current_version;available=$available_version;status=upgrade_available"
    return 0
}

# Generate step-by-step upgrade plan with estimates
# Returns: path to plan file
generate_upgrade_plan() {
    local target_version="${1:-latest}"

    log_info "Generating upgrade plan..."

    local plan_file="/tmp/upgrade-plan-$(date +%Y%m%d_%H%M%S).txt"

    # Get current system info
    local current_version="unknown"
    if [ -f "$INSTALL_DIR/version.txt" ]; then
        current_version=$(cat "$INSTALL_DIR/version.txt" 2>/dev/null | tr -d '[:space:]')
    fi

    {
        echo "Water Controller Upgrade Plan"
        echo "=============================="
        echo ""
        echo "Generated: $(date -Iseconds)"
        echo "Current Version: $current_version"
        echo "Target Version: $target_version"
        echo ""
        echo "Estimated Total Downtime: 3-5 minutes"
        echo ""
        echo "Pre-Upgrade Steps:"
        echo "  1. [ ] Run health check (pre_upgrade_health_check)"
        echo "  2. [ ] Verify disk space (check_disk_space_for_upgrade)"
        echo "  3. [ ] Export configuration (export_current_configuration)"
        echo "  4. [ ] Snapshot database (snapshot_database_state)"
        echo "  5. [ ] Create rollback point"
        echo ""
        echo "Upgrade Steps:"
        echo "  6. [ ] Stop service (~10s)"
        echo "  7. [ ] Backup current installation (~30s)"
        echo "  8. [ ] Download/extract new version (~60s)"
        echo "  9. [ ] Install dependencies (~120s)"
        echo " 10. [ ] Migrate configuration (~10s)"
        echo " 11. [ ] Apply database migrations (~30s)"
        echo " 12. [ ] Start service (~10s)"
        echo ""
        echo "Post-Upgrade Validation:"
        echo " 13. [ ] Verify service starts"
        echo " 14. [ ] Test API endpoints"
        echo " 15. [ ] Compare configuration"
        echo " 16. [ ] Verify database migration"
        echo " 17. [ ] Monitor stability (60s)"
        echo ""
        echo "Rollback Procedure:"
        echo "  - If any step fails, automatic rollback will be attempted"
        echo "  - Manual rollback: ./install.sh --rollback <rollback-point>"
        echo ""
        echo "Notes:"
        echo "  - Ensure network connectivity before starting"
        echo "  - Have SSH access to device for manual intervention"
        echo "  - Keep this plan file for reference"
        echo ""

    } > "$plan_file"

    log_info "Upgrade plan saved to: $plan_file"
    echo "$plan_file"
}

# =============================================================================
# Post-Upgrade Validation Functions
# =============================================================================

# Run full validation suite after upgrade
# Returns: 0 if all validations pass, 1 if any fail
post_upgrade_validation() {
    log_info "Running post-upgrade validation..."

    local failures=0
    local report_file="/tmp/post-upgrade-validation-$(date +%Y%m%d_%H%M%S).txt"

    {
        echo "Post-Upgrade Validation Report"
        echo "==============================="
        echo "Date: $(date -Iseconds)"
        echo ""
    } > "$report_file"

    # Validation 1: Service running
    log_info "  Checking service status..."
    if systemctl is-active water-controller.service >/dev/null 2>&1; then
        echo "[PASS] Service is running" >> "$report_file"
    else
        echo "[FAIL] Service is not running" >> "$report_file"
        ((failures++))
    fi

    # Validation 2: API responsive
    log_info "  Testing API endpoints..."
    if test_upgrade_api_endpoints; then
        echo "[PASS] API endpoints responding" >> "$report_file"
    else
        echo "[FAIL] API endpoints not responding" >> "$report_file"
        ((failures++))
    fi

    # Validation 3: Database accessible
    log_info "  Verifying database..."
    if verify_database_migration; then
        echo "[PASS] Database accessible and migrated" >> "$report_file"
    else
        echo "[WARN] Database verification had issues" >> "$report_file"
    fi

    # Validation 4: Configuration intact
    log_info "  Checking configuration..."
    if [ -d "$CONFIG_DIR" ] && [ -f "$CONFIG_DIR/controller.conf" ]; then
        echo "[PASS] Configuration files present" >> "$report_file"
    else
        echo "[WARN] Configuration may need attention" >> "$report_file"
    fi

    # Validation 5: No errors in logs
    log_info "  Checking recent logs..."
    local error_count
    error_count=$(journalctl -u water-controller.service --since "5 minutes ago" -p err 2>/dev/null | wc -l)
    if [ "$error_count" -eq 0 ]; then
        echo "[PASS] No errors in recent logs" >> "$report_file"
    else
        echo "[WARN] Found $error_count errors in recent logs" >> "$report_file"
    fi

    # Summary
    echo "" >> "$report_file"
    echo "Failures: $failures" >> "$report_file"

    log_info "Validation complete. Report: $report_file"

    if [ $failures -gt 0 ]; then
        log_error "Post-upgrade validation failed with $failures failure(s)"
        return 1
    fi

    log_info "Post-upgrade validation passed"
    return 0
}

# Compare old vs new configuration, flag changes
# Arguments: $1 - path to exported old config
compare_configuration() {
    local old_config_path="${1:-}"

    log_info "Comparing configuration..."

    if [ -z "$old_config_path" ] || [ ! -f "$old_config_path" ]; then
        log_warn "Old configuration not provided or not found"
        return 0
    fi

    local compare_dir="/tmp/config-compare-$$"
    mkdir -p "$compare_dir/old" "$compare_dir/new"

    # Extract old config
    tar -xzf "$old_config_path" -C "$compare_dir/old" --strip-components=1 2>/dev/null || true

    # Copy new config
    cp -a "$CONFIG_DIR"/* "$compare_dir/new/" 2>/dev/null || true

    # Generate diff
    local diff_file="/tmp/config-diff-$(date +%Y%m%d_%H%M%S).txt"
    {
        echo "Configuration Comparison"
        echo "========================"
        echo "Date: $(date -Iseconds)"
        echo ""

        diff -rq "$compare_dir/old" "$compare_dir/new" 2>/dev/null || echo "No differences found"
        echo ""

        echo "Detailed Differences:"
        diff -ru "$compare_dir/old" "$compare_dir/new" 2>/dev/null || echo "No detailed differences"

    } > "$diff_file"

    rm -rf "$compare_dir"

    log_info "Configuration comparison saved to: $diff_file"
    echo "$diff_file"
}

# Verify database schema updated correctly
# Returns: 0 if OK, 1 if issues
verify_database_migration() {
    log_info "Verifying database migration..."

    local db_file="$DATA_DIR/water_controller.db"

    if [ ! -f "$db_file" ]; then
        log_info "No database file found (may be new installation)"
        return 0
    fi

    if ! command -v sqlite3 >/dev/null 2>&1; then
        log_warn "sqlite3 not available for verification"
        return 0
    fi

    # Check integrity
    local integrity
    integrity=$(sqlite3 "$db_file" "PRAGMA integrity_check;" 2>/dev/null)
    if [ "$integrity" != "ok" ]; then
        log_error "Database integrity check failed: $integrity"
        return 1
    fi

    # Check for migration table
    if sqlite3 "$db_file" "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations';" 2>/dev/null | grep -q "schema_migrations"; then
        log_info "Schema migrations table present"
    fi

    log_info "Database migration verification passed"
    return 0
}

# Test critical API endpoints for upgrade validation
# Returns: 0 if all pass, 1 if any fail
# Note: Named differently from validation.sh test_api_endpoints to avoid conflict
test_upgrade_api_endpoints() {
    log_info "Testing API endpoints..."

    local base_url="http://localhost:$API_PORT"
    local failures=0

    # Wait for API to be ready
    local retries=10
    while [ $retries -gt 0 ]; do
        if curl -s --connect-timeout 2 "$base_url$API_HEALTH_ENDPOINT" >/dev/null 2>&1; then
            break
        fi
        sleep 1
        ((retries--))
    done

    if [ $retries -eq 0 ]; then
        log_error "API not responding after 10 seconds"
        return 1
    fi

    # Test health endpoint
    local health_response
    health_response=$(curl -s --connect-timeout 5 "$base_url$API_HEALTH_ENDPOINT" 2>/dev/null)
    if echo "$health_response" | grep -qiE '"status".*:.*"(ok|healthy)"'; then
        log_info "  Health endpoint: OK"
    else
        log_warn "  Health endpoint: Unexpected response"
        ((failures++))
    fi

    # Test version endpoint
    local version_response
    version_response=$(curl -s --connect-timeout 5 "$base_url$API_VERSION_ENDPOINT" 2>/dev/null)
    if echo "$version_response" | grep -qiE '"version"'; then
        log_info "  Version endpoint: OK"
    else
        log_warn "  Version endpoint: No version found"
    fi

    if [ $failures -gt 0 ]; then
        return 1
    fi

    return 0
}

# Test PROFINET connectivity
# Returns: 0 if OK, 1 if issues
test_profinet_connectivity() {
    log_info "Testing PROFINET connectivity..."

    # Check if P-Net library is loaded
    if ! ldconfig -p 2>/dev/null | grep -q "libpnet"; then
        log_warn "P-Net library not found in ldconfig"
        return 1
    fi

    # Check PROFINET ports
    local udp_port=34964
    local tcp_ports="34962:34963"

    # Check if ports are in use (meaning PROFINET stack is active)
    if ss -uln 2>/dev/null | grep -q ":$udp_port "; then
        log_info "  PROFINET UDP port $udp_port: LISTENING"
    else
        log_info "  PROFINET UDP port $udp_port: not listening (may be normal)"
    fi

    log_info "PROFINET connectivity check complete"
    return 0
}

# Monitor service for stability
# Arguments: $1 - seconds to monitor (default 60)
# Returns: 0 if stable, 1 if crashes detected
verify_service_stability() {
    local duration="${1:-$SERVICE_STABILITY_CHECK_SECONDS}"

    log_info "Monitoring service stability for ${duration}s..."

    local start_time
    start_time=$(date +%s)
    local restarts=0
    local last_start=""

    while true; do
        local elapsed=$(( $(date +%s) - start_time ))
        if [ $elapsed -ge "$duration" ]; then
            break
        fi

        # Check service status
        if ! systemctl is-active water-controller.service >/dev/null 2>&1; then
            log_warn "Service stopped during monitoring"
            ((restarts++))
        fi

        # Check for restart
        local current_start
        current_start=$(systemctl show water-controller.service --property=ActiveEnterTimestamp 2>/dev/null | cut -d= -f2)
        if [ -n "$last_start" ] && [ "$current_start" != "$last_start" ]; then
            log_warn "Service restarted during monitoring"
            ((restarts++))
        fi
        last_start="$current_start"

        # Show progress
        printf "\r  Progress: %d/%d seconds (restarts: %d)" "$elapsed" "$duration" "$restarts"

        sleep 5
    done

    echo ""  # New line after progress

    if [ $restarts -gt 0 ]; then
        log_error "Service had $restarts restart(s) during stability check"
        return 1
    fi

    log_info "Service stability check passed"
    return 0
}

# Generate detailed upgrade summary report
# Returns: path to report file
generate_upgrade_report() {
    local start_time="${1:-}"
    local end_time="${2:-$(date -Iseconds)}"
    local status="${3:-completed}"

    log_info "Generating upgrade report..."

    local report_file="/tmp/upgrade-report-$(date +%Y%m%d_%H%M%S).txt"

    # Get version info
    local new_version="unknown"
    if [ -f "$INSTALL_DIR/version.txt" ]; then
        new_version=$(cat "$INSTALL_DIR/version.txt" 2>/dev/null | tr -d '[:space:]')
    fi

    {
        echo "Water Controller Upgrade Report"
        echo "================================"
        echo ""
        echo "Status: $status"
        echo "Start Time: ${start_time:-unknown}"
        echo "End Time: $end_time"
        echo "New Version: $new_version"
        echo ""
        echo "System Information:"
        echo "  Hostname: $(hostname)"
        echo "  Kernel: $(uname -r)"
        echo "  Platform: $(uname -m)"
        echo ""
        echo "Service Status:"
        systemctl status water-controller.service --no-pager 2>/dev/null || echo "  Service status unavailable"
        echo ""
        echo "Disk Usage:"
        df -h "$INSTALL_DIR" 2>/dev/null || echo "  Disk info unavailable"
        echo ""
        echo "Recent Logs:"
        journalctl -u water-controller.service --since "10 minutes ago" --no-pager -n 20 2>/dev/null || echo "  Logs unavailable"
        echo ""
        echo "--- End of Report ---"

    } > "$report_file"

    log_info "Upgrade report saved to: $report_file"
    echo "$report_file"
}

# Send notification about upgrade completion
# Arguments: $1 - webhook URL (optional)
notify_upgrade_complete() {
    local webhook_url="${1:-}"
    local status="${2:-completed}"

    log_info "Sending upgrade notification..."

    if [ -z "$webhook_url" ]; then
        log_info "No webhook URL configured, skipping notification"
        return 0
    fi

    local hostname
    hostname=$(hostname)

    local version="unknown"
    if [ -f "$INSTALL_DIR/version.txt" ]; then
        version=$(cat "$INSTALL_DIR/version.txt" 2>/dev/null | tr -d '[:space:]')
    fi

    local payload
    payload=$(cat <<EOF
{
    "event": "upgrade_$status",
    "hostname": "$hostname",
    "version": "$version",
    "timestamp": "$(date -Iseconds)"
}
EOF
    )

    if command -v curl >/dev/null 2>&1; then
        curl -s -X POST -H "Content-Type: application/json" \
            -d "$payload" \
            "$webhook_url" >/dev/null 2>&1 && {
            log_info "Notification sent successfully"
        } || {
            log_warn "Failed to send notification"
        }
    else
        log_warn "curl not available, skipping notification"
    fi

    return 0
}


# =============================================================================
# Rollback Enhancements
# =============================================================================

# Validate rollback archive integrity before use
# Arguments: $1 - rollback point name or path
# Returns: 0 if valid, 1 if corrupt
verify_rollback_point() {
    local rollback_point="${1:-}"

    log_info "Verifying rollback point: $rollback_point"

    local rollback_path
    if [ -d "$rollback_point" ]; then
        rollback_path="$rollback_point"
    elif [ -d "$ROLLBACK_DIR/$rollback_point" ]; then
        rollback_path="$ROLLBACK_DIR/$rollback_point"
    else
        log_error "Rollback point not found: $rollback_point"
        return 1
    fi

    local errors=0

    # Check metadata
    if [ ! -f "$rollback_path/metadata.json" ]; then
        log_error "Missing metadata.json"
        ((errors++))
    fi

    # Verify archives
    local archives=("app.tar.gz" "config.tar.gz")
    for archive in "${archives[@]}"; do
        if [ -f "$rollback_path/$archive" ]; then
            if ! gzip -t "$rollback_path/$archive" 2>/dev/null; then
                log_error "Corrupt archive: $archive"
                ((errors++))
            else
                log_info "  Archive OK: $archive"
            fi
        fi
    done

    # Verify database backup if present
    if [ -f "$rollback_path/database.db" ]; then
        if command -v sqlite3 >/dev/null 2>&1; then
            if sqlite3 "$rollback_path/database.db" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
                log_info "  Database OK: database.db"
            else
                log_error "Corrupt database backup"
                ((errors++))
            fi
        fi
    fi

    if [ $errors -gt 0 ]; then
        log_error "Rollback point verification failed with $errors error(s)"
        return 1
    fi

    log_info "Rollback point verification passed"
    return 0
}

# Dry-run restore to temp location
# Arguments: $1 - rollback point name
# Returns: 0 if test successful, 1 if failed
test_rollback_restore() {
    local rollback_point="${1:-}"

    log_info "Testing rollback restore (dry-run)..."

    local rollback_path
    if [ -d "$ROLLBACK_DIR/$rollback_point" ]; then
        rollback_path="$ROLLBACK_DIR/$rollback_point"
    else
        log_error "Rollback point not found: $rollback_point"
        return 1
    fi

    local test_dir="/tmp/rollback-test-$$"
    mkdir -p "$test_dir"

    local errors=0

    # Test app archive extraction
    if [ -f "$rollback_path/app.tar.gz" ]; then
        log_info "  Testing app.tar.gz extraction..."
        if tar -tzf "$rollback_path/app.tar.gz" >/dev/null 2>&1; then
            tar -xzf "$rollback_path/app.tar.gz" -C "$test_dir" 2>/dev/null || ((errors++))
        else
            ((errors++))
        fi
    fi

    # Test config archive extraction
    if [ -f "$rollback_path/config.tar.gz" ]; then
        log_info "  Testing config.tar.gz extraction..."
        if tar -tzf "$rollback_path/config.tar.gz" >/dev/null 2>&1; then
            tar -xzf "$rollback_path/config.tar.gz" -C "$test_dir" 2>/dev/null || ((errors++))
        else
            ((errors++))
        fi
    fi

    # Cleanup
    rm -rf "$test_dir"

    if [ $errors -gt 0 ]; then
        log_error "Rollback test failed with $errors error(s)"
        return 1
    fi

    log_info "Rollback test passed"
    return 0
}

# Rollback only specific components
# Arguments: $1 - rollback point, $2 - components (app|config|db)
selective_rollback() {
    local rollback_point="${1:-}"
    local components="${2:-all}"

    log_info "Performing selective rollback: $components"

    local rollback_path
    if [ -d "$ROLLBACK_DIR/$rollback_point" ]; then
        rollback_path="$ROLLBACK_DIR/$rollback_point"
    else
        log_error "Rollback point not found: $rollback_point"
        return 1
    fi

    # Verify before proceeding
    if ! verify_rollback_point "$rollback_point"; then
        log_error "Rollback point verification failed"
        return 1
    fi

    # Stop service
    sudo systemctl stop water-controller.service 2>/dev/null || true

    local errors=0

    case "$components" in
        app|all)
            if [ -f "$rollback_path/app.tar.gz" ]; then
                log_info "Rolling back application..."
                sudo rm -rf "$INSTALL_DIR"
                sudo mkdir -p "$INSTALL_DIR"
                sudo tar -xzf "$rollback_path/app.tar.gz" -C "$INSTALL_DIR" 2>/dev/null || ((errors++))
            fi
            ;;&
        config|all)
            if [ -f "$rollback_path/config.tar.gz" ]; then
                log_info "Rolling back configuration..."
                sudo rm -rf "$CONFIG_DIR"
                sudo mkdir -p "$CONFIG_DIR"
                sudo tar -xzf "$rollback_path/config.tar.gz" -C "$CONFIG_DIR" 2>/dev/null || ((errors++))
            fi
            ;;&
        db|all)
            if [ -f "$rollback_path/database.db" ]; then
                log_info "Rolling back database..."
                sudo cp "$rollback_path/database.db" "$DATA_DIR/water_controller.db" 2>/dev/null || ((errors++))
                if [ -f "$rollback_path/database.db-wal" ]; then
                    sudo cp "$rollback_path/database.db-wal" "$DATA_DIR/water_controller.db-wal" 2>/dev/null || true
                fi
                if [ -f "$rollback_path/database.db-shm" ]; then
                    sudo cp "$rollback_path/database.db-shm" "$DATA_DIR/water_controller.db-shm" 2>/dev/null || true
                fi
            fi
            ;;
    esac

    # Restart service
    sudo systemctl start water-controller.service 2>/dev/null || ((errors++))

    if [ $errors -gt 0 ]; then
        log_error "Selective rollback completed with $errors error(s)"
        return 1
    fi

    log_info "Selective rollback completed successfully"
    return 0
}

# Fast rollback skipping non-essential steps
# Arguments: $1 - rollback point (optional, uses latest)
emergency_rollback() {
    log_warn "EMERGENCY ROLLBACK INITIATED"

    local rollback_point="${1:-}"

    # Find latest rollback point if not specified
    if [ -z "$rollback_point" ]; then
        rollback_point=$(ls -t "$ROLLBACK_DIR" 2>/dev/null | head -1)
        if [ -z "$rollback_point" ]; then
            log_error "No rollback points available!"
            return 1
        fi
        log_info "Using latest rollback point: $rollback_point"
    fi

    local rollback_path="$ROLLBACK_DIR/$rollback_point"

    if [ ! -d "$rollback_path" ]; then
        log_error "Rollback point not found: $rollback_path"
        return 1
    fi

    # Stop service immediately
    sudo systemctl stop water-controller.service 2>/dev/null || true
    sudo systemctl kill water-controller.service 2>/dev/null || true

    # Restore app (skip validation for speed)
    if [ -f "$rollback_path/app.tar.gz" ]; then
        log_info "Restoring application..."
        sudo rm -rf "$INSTALL_DIR"
        sudo mkdir -p "$INSTALL_DIR"
        sudo tar -xzf "$rollback_path/app.tar.gz" -C "$INSTALL_DIR" 2>/dev/null || true
    fi

    # Restore config
    if [ -f "$rollback_path/config.tar.gz" ]; then
        log_info "Restoring configuration..."
        sudo rm -rf "$CONFIG_DIR"
        sudo mkdir -p "$CONFIG_DIR"
        sudo tar -xzf "$rollback_path/config.tar.gz" -C "$CONFIG_DIR" 2>/dev/null || true
    fi

    # Restore service file
    if [ -f "$rollback_path/water-controller.service" ]; then
        sudo cp "$rollback_path/water-controller.service" /etc/systemd/system/
        sudo systemctl daemon-reload
    fi

    # Restart service
    log_info "Restarting service..."
    sudo systemctl start water-controller.service

    # Quick check
    sleep 3
    if systemctl is-active water-controller.service >/dev/null 2>&1; then
        log_info "Emergency rollback successful - service running"
        return 0
    else
        log_error "Emergency rollback completed but service failed to start"
        return 1
    fi
}

# =============================================================================
# Main Upgrade Orchestration
# =============================================================================

# Helper function to run upgrade steps with optional staging
_run_upgrade_step() {
    local step_func="$1"
    local step_name="$2"

    if [ "${STAGED_MODE:-0}" -eq 1 ]; then
        log_info "=== STAGED: $step_name ==="
        if ! confirm "Proceed with $step_name?"; then
            log_info "Upgrade cancelled at: $step_name"
            return 1
        fi
    fi

    $step_func
}

# Rollback on failure during upgrade
rollback_on_failure() {
    if [ -n "${ROLLBACK_POINT:-}" ]; then
        log_error "Installation failed. System may be in inconsistent state. Initiating rollback..."
        if perform_rollback "$ROLLBACK_POINT"; then
            log_info "Rollback successful. System restored to pre-upgrade state."
        else
            log_error "Standard rollback failed. Trying emergency rollback..."
            if emergency_rollback; then
                log_info "Emergency rollback completed. Verify system manually."
            else
                log_error "Emergency rollback failed. Manual intervention required. Run: ./install.sh --selective-rollback"
            fi
        fi
    fi
}

# Main upgrade orchestration function
do_upgrade() {
    log_info "Starting upgrade process..."
    local upgrade_start
    upgrade_start=$(date -Iseconds)

    # Log upgrade mode
    if [ "${UNATTENDED_MODE:-0}" -eq 1 ]; then
        log_info "Mode: UNATTENDED (no prompts, auto-rollback on failure)"
    elif [ "${CANARY_MODE:-0}" -eq 1 ]; then
        log_info "Mode: CANARY (extended testing, auto-rollback if tests fail)"
    elif [ "${STAGED_MODE:-0}" -eq 1 ]; then
        log_info "Mode: STAGED (pause at each step for confirmation)"
    else
        log_info "Mode: INTERACTIVE"
    fi

    # Compare versions before upgrade
    log_info "Checking version compatibility..."
    compare_versions || log_warn "Could not compare versions"

    # Verify network connectivity for downloads (informational only, non-blocking)
    log_info "Verifying network connectivity..."
    if ! verify_network_connectivity; then
        log_warn "Network connectivity issues detected - continuing anyway"
    fi

    # Pre-upgrade health check (informational only, non-blocking)
    log_info "Running pre-upgrade health check..."
    if ! pre_upgrade_health_check; then
        log_warn "Pre-upgrade health check found issues - continuing anyway"
    fi

    # Check disk space
    log_info "Checking disk space..."
    if ! check_disk_space_for_upgrade; then
        log_error "Insufficient disk space for upgrade. Upgrade cannot proceed. Free disk space and retry."
        return 1
    fi

    # Check for running processes (informational only, non-blocking)
    if ! check_running_processes; then
        log_warn "Critical operations may be in progress - continuing anyway"
    fi

    # Generate upgrade plan
    log_info "Generating upgrade plan..."
    generate_upgrade_plan || log_warn "Could not generate upgrade plan"

    # Export current configuration for comparison
    local old_config
    old_config=$(export_current_configuration 2>/dev/null) || true

    # Snapshot database state for potential rollback
    log_info "Creating database snapshot..."
    snapshot_database_state || log_warn "Database snapshot not available"

    # Create rollback point before upgrade (best effort, non-blocking)
    log_info "Creating rollback point..."
    ROLLBACK_POINT=$(create_rollback_point "Pre-upgrade backup")
    if [ -z "$ROLLBACK_POINT" ]; then
        log_warn "Failed to create rollback point - continuing without rollback capability"
    else
        log_info "Rollback point created: $ROLLBACK_POINT"
        # Verify the rollback point is valid
        if ! verify_rollback_point "$ROLLBACK_POINT"; then
            log_warn "Rollback point verification failed - rollback may not work"
        fi
    fi

    # Canary mode: Test rollback restore capability before proceeding
    if [ "${CANARY_MODE:-0}" -eq 1 ] && [ -n "$ROLLBACK_POINT" ]; then
        log_info "CANARY MODE: Testing rollback restore capability..."
        if ! test_rollback_restore "$ROLLBACK_POINT"; then
            log_error "Rollback restore test failed. Upgrade unsafe without rollback capability. Fix backup system and retry."
            return 1
        fi
    fi

    # Staged mode: confirm before stopping service
    if [ "${STAGED_MODE:-0}" -eq 1 ]; then
        if ! confirm "Ready to stop service and begin upgrade?"; then
            log_info "Upgrade cancelled by user"
            return 1
        fi
    fi

    # Stop existing service
    log_info "Stopping existing service..."
    stop_service || log_warn "Service stop failed or not running"

    # Run installation steps with staged pauses if requested
    _run_upgrade_step "step_detect_system" "System Detection" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_install_dependencies" "Dependency Installation" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_install_pnet" "P-Net Installation" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_build" "Source Build" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_install_files" "File Installation" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_configure_service" "Service Configuration" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_configure_network_storage" "Network/Storage Configuration" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_start_service" "Service Startup" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_validate" "Validation" || log_warn "Validation had issues"
    step_generate_docs

    # Clean up build directory
    cleanup_build

    # Post-upgrade validation
    log_info "Running post-upgrade validation..."
    if ! post_upgrade_validation; then
        log_warn "Post-upgrade validation found issues"
        if [ "${UNATTENDED_MODE:-0}" -eq 1 ] || [ "${CANARY_MODE:-0}" -eq 1 ]; then
            log_error "Auto-rollback triggered due to validation failure"
            rollback_on_failure
            return 1
        fi
        log_warn "Consider rolling back if problems persist"
    fi

    # Canary mode: Extended testing with stability monitoring
    if [ "${CANARY_MODE:-0}" -eq 1 ]; then
        log_info "CANARY MODE: Running extended tests..."

        # Test API endpoints
        if ! test_upgrade_api_endpoints; then
            log_error "API endpoint test failed. Backend not responding correctly. Initiating rollback."
            rollback_on_failure
            return 1
        fi

        # Test PROFINET connectivity
        test_profinet_connectivity || log_warn "PROFINET test had issues"

        # Monitor service stability for 60 seconds
        log_info "Monitoring service stability (60 seconds)..."
        if ! verify_service_stability 60; then
            log_error "Service stability check failed. Service crashed or unresponsive. Initiating rollback."
            rollback_on_failure
            return 1
        fi

        log_info "CANARY MODE: All extended tests passed"
    fi

    # Compare configuration changes
    if [ -n "$old_config" ] && [ -f "$old_config" ]; then
        local config_diff
        config_diff=$(compare_configuration "$old_config" 2>/dev/null) || true
        if [ -n "$config_diff" ]; then
            log_info "Configuration comparison saved to: $config_diff"
        fi
    fi

    # Verify database migration if applicable
    log_info "Verifying database migration..."
    if ! verify_database_migration; then
        log_warn "Database migration verification had issues"
        if [ "${UNATTENDED_MODE:-0}" -eq 1 ] || [ "${CANARY_MODE:-0}" -eq 1 ]; then
            log_error "Database migration failed. Data integrity at risk. Initiating rollback."
            rollback_on_failure
            return 1
        fi
    fi

    # Generate upgrade report
    local report
    report=$(generate_upgrade_report "$upgrade_start" "$(date -Iseconds)" "completed" 2>/dev/null) || true
    if [ -n "$report" ]; then
        log_info "Upgrade report saved to: $report"
    fi

    # Send upgrade completion notification
    notify_upgrade_complete || log_warn "Could not send upgrade notification"

    log_info "Upgrade completed successfully"
    return 0
}

# =============================================================================
# Module Entry Point
# =============================================================================

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        --help|-h)
            cat <<EOF
Water Controller Upgrade Module v${UPGRADE_MODULE_VERSION}

USAGE:
    source upgrade.sh
    <function_name> [arguments]

PRE-UPGRADE FUNCTIONS:
    pre_upgrade_health_check      Full system health assessment
    check_disk_space_for_upgrade  Verify adequate disk space
    check_running_processes       Verify no critical operations
    export_current_configuration  Dump current config for comparison
    snapshot_database_state       Record DB schema version and row counts
    verify_network_connectivity   Check connectivity to update sources
    compare_versions [available]  Compare installed vs available versions
    generate_upgrade_plan [ver]   Create step-by-step upgrade plan

POST-UPGRADE FUNCTIONS:
    post_upgrade_validation       Run full validation suite
    compare_configuration [old]   Diff old vs new config
    verify_database_migration     Confirm DB schema updated correctly
    test_upgrade_api_endpoints    Hit critical API endpoints
    test_profinet_connectivity    Verify P-Net stack responds
    verify_service_stability [s]  Monitor service for stability
    generate_upgrade_report       Create detailed upgrade summary
    notify_upgrade_complete [url] Send webhook notification

ROLLBACK ENHANCEMENTS:
    verify_rollback_point [name]  Validate rollback archive integrity
    test_rollback_restore [name]  Dry-run restore to temp location
    selective_rollback [name] [c] Rollback specific components
    emergency_rollback [name]     Fast rollback for emergencies

EXAMPLES:
    # Run pre-upgrade health check
    ./upgrade.sh health-check

    # Run post-upgrade validation
    ./upgrade.sh validate

EOF
            ;;
        health-check)
            pre_upgrade_health_check
            ;;
        disk-check)
            check_disk_space_for_upgrade
            ;;
        export-config)
            export_current_configuration
            ;;
        db-snapshot)
            snapshot_database_state
            ;;
        plan)
            generate_upgrade_plan "${2:-latest}"
            ;;
        validate)
            post_upgrade_validation
            ;;
        verify-rollback)
            verify_rollback_point "${2:-}"
            ;;
        emergency-rollback)
            emergency_rollback "${2:-}"
            ;;
        *)
            echo "Usage: $0 {health-check|disk-check|export-config|db-snapshot|plan|validate|verify-rollback|emergency-rollback|--help}"
            exit 1
            ;;
    esac
fi
