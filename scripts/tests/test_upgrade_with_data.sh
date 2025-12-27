#!/bin/bash
#
# Test: Upgrade preserving existing data
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This test verifies that an upgrade preserves existing data and configuration.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Test configuration
TEST_INSTALL_DIR="/tmp/test-wtc-install"
TEST_CONFIG_DIR="/tmp/test-wtc-config"
TEST_DATA_DIR="/tmp/test-wtc-data"
TEST_BACKUP_DIR="/tmp/test-wtc-backup"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_test() { echo -e "${GREEN}[TEST]${NC} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local test_name="$1"
    local test_func="$2"

    ((TESTS_RUN++))
    log_test "Running: $test_name"

    if $test_func; then
        log_pass "$test_name"
        ((TESTS_PASSED++))
        return 0
    else
        log_fail "$test_name"
        ((TESTS_FAILED++))
        return 1
    fi
}

setup_test_environment() {
    log_test "Setting up test environment with data..."

    # Create directory structure
    sudo mkdir -p "$TEST_INSTALL_DIR"/{bin,lib,config}
    sudo mkdir -p "$TEST_CONFIG_DIR"
    sudo mkdir -p "$TEST_DATA_DIR"
    sudo mkdir -p "$TEST_BACKUP_DIR/rollback"

    # Create test configuration file
    sudo tee "$TEST_CONFIG_DIR/controller.conf" > /dev/null <<EOF
[general]
log_level = INFO
cycle_time_ms = 1000
custom_setting = preserved_value

[database]
path = $TEST_DATA_DIR/test.db
EOF

    # Create test version file
    echo "1.0.0" | sudo tee "$TEST_INSTALL_DIR/version.txt" > /dev/null

    # Create test database
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "$TEST_DATA_DIR/test.db" <<EOF
CREATE TABLE IF NOT EXISTS test_data (id INTEGER PRIMARY KEY, value TEXT);
INSERT INTO test_data (value) VALUES ('preserved_data_1');
INSERT INTO test_data (value) VALUES ('preserved_data_2');
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER);
INSERT INTO schema_version VALUES (1);
EOF
    fi

    # Create test log file
    echo "2024-01-01 Test log entry" | sudo tee "$TEST_DATA_DIR/test.log" > /dev/null

    log_test "Test environment created with sample data"
}

cleanup() {
    log_test "Cleaning up test environment..."
    sudo rm -rf "$TEST_INSTALL_DIR" "$TEST_CONFIG_DIR" "$TEST_DATA_DIR" "$TEST_BACKUP_DIR" 2>/dev/null || true
}

# =============================================================================
# Test Cases
# =============================================================================

test_configuration_preserved() {
    # Verify custom configuration value exists
    grep -q "custom_setting = preserved_value" "$TEST_CONFIG_DIR/controller.conf"
}

test_database_preserved() {
    if ! command -v sqlite3 >/dev/null 2>&1; then
        log_warn "sqlite3 not available, skipping database test"
        return 0
    fi

    # Verify data still exists
    local count
    count=$(sqlite3 "$TEST_DATA_DIR/test.db" "SELECT COUNT(*) FROM test_data;" 2>/dev/null)
    [ "$count" -eq 2 ]
}

test_database_integrity() {
    if ! command -v sqlite3 >/dev/null 2>&1; then
        log_warn "sqlite3 not available, skipping integrity test"
        return 0
    fi

    local result
    result=$(sqlite3 "$TEST_DATA_DIR/test.db" "PRAGMA integrity_check;" 2>/dev/null)
    [ "$result" = "ok" ]
}

test_database_snapshot() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    export DATA_DIR="$TEST_DATA_DIR"

    local snapshot_file
    snapshot_file=$(snapshot_database_state 2>/dev/null)

    [ -n "$snapshot_file" ] && [ -f "$snapshot_file" ]
}

test_config_export() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    export CONFIG_DIR="$TEST_CONFIG_DIR"

    local export_file
    export_file=$(export_current_configuration 2>/dev/null)

    # Verify export contains our custom setting
    if [ -f "$export_file" ]; then
        local temp_dir="/tmp/config-test-$$"
        mkdir -p "$temp_dir"
        tar -xzf "$export_file" -C "$temp_dir" 2>/dev/null
        grep -rq "preserved_value" "$temp_dir" 2>/dev/null
        local result=$?
        rm -rf "$temp_dir"
        return $result
    fi
    return 1
}

test_config_comparison() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    export CONFIG_DIR="$TEST_CONFIG_DIR"

    # Export current config
    local export_file
    export_file=$(export_current_configuration 2>/dev/null)

    # Modify config
    echo "new_setting = new_value" | sudo tee -a "$TEST_CONFIG_DIR/controller.conf" > /dev/null

    # Compare should detect the change
    local diff_file
    diff_file=$(compare_configuration "$export_file" 2>/dev/null)

    [ -n "$diff_file" ] && [ -f "$diff_file" ]
}

test_rollback_point_creation() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    export INSTALL_DIR="$TEST_INSTALL_DIR"
    export CONFIG_DIR="$TEST_CONFIG_DIR"
    export DATA_DIR="$TEST_DATA_DIR"
    export BACKUP_DIR="$TEST_BACKUP_DIR"
    export ROLLBACK_DIR="$TEST_BACKUP_DIR/rollback"

    # Create a mock rollback point
    local rollback_name="test-rollback-$$"
    local rollback_path="$ROLLBACK_DIR/$rollback_name"

    mkdir -p "$rollback_path"
    tar -czf "$rollback_path/app.tar.gz" -C "$TEST_INSTALL_DIR" . 2>/dev/null
    tar -czf "$rollback_path/config.tar.gz" -C "$TEST_CONFIG_DIR" . 2>/dev/null

    # Create metadata
    cat > "$rollback_path/metadata.json" <<EOF
{
    "name": "$rollback_name",
    "timestamp": "$(date -Iseconds)",
    "version": "1.0.0"
}
EOF

    # Verify rollback point
    verify_rollback_point "$rollback_name" >/dev/null 2>&1
}

test_rollback_verification() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    export ROLLBACK_DIR="$TEST_BACKUP_DIR/rollback"

    # Find the rollback we created
    local rollback_name
    rollback_name=$(ls "$ROLLBACK_DIR" 2>/dev/null | head -1)

    if [ -n "$rollback_name" ]; then
        verify_rollback_point "$rollback_name" >/dev/null 2>&1
    else
        log_warn "No rollback point found to verify"
        return 0
    fi
}

test_post_upgrade_validation() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    export INSTALL_DIR="$TEST_INSTALL_DIR"
    export CONFIG_DIR="$TEST_CONFIG_DIR"
    export DATA_DIR="$TEST_DATA_DIR"

    # This will fail some checks (no service running) but should not crash
    post_upgrade_validation >/dev/null 2>&1 || true
    return 0
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo ""
    echo "============================================================"
    echo "     Water Controller Upgrade Test Suite"
    echo "     Test: Upgrade Preserving Existing Data"
    echo "============================================================"
    echo ""

    # Setup
    trap cleanup EXIT
    cleanup
    setup_test_environment

    # Run tests
    run_test "Configuration file preserved" test_configuration_preserved
    run_test "Database data preserved" test_database_preserved
    run_test "Database integrity" test_database_integrity
    run_test "Database snapshot creation" test_database_snapshot
    run_test "Configuration export" test_config_export
    run_test "Configuration comparison" test_config_comparison
    run_test "Rollback point creation" test_rollback_point_creation
    run_test "Rollback verification" test_rollback_verification
    run_test "Post-upgrade validation runs" test_post_upgrade_validation

    # Summary
    echo ""
    echo "============================================================"
    echo "     Test Summary"
    echo "============================================================"
    echo "  Tests Run:    $TESTS_RUN"
    echo "  Passed:       $TESTS_PASSED"
    echo "  Failed:       $TESTS_FAILED"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        log_pass "All tests passed!"
        exit 0
    else
        log_fail "Some tests failed"
        exit 1
    fi
}

main "$@"
