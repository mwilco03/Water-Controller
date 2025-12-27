#!/bin/bash
#
# Test: Rollback during mid-upgrade failure
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This test simulates a failure during upgrade and verifies rollback works.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Test configuration
TEST_INSTALL_DIR="/tmp/test-wtc-rollback-install"
TEST_CONFIG_DIR="/tmp/test-wtc-rollback-config"
TEST_DATA_DIR="/tmp/test-wtc-rollback-data"
TEST_BACKUP_DIR="/tmp/test-wtc-rollback-backup"

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

    ((TESTS_RUN++)) || true
    log_test "Running: $test_name"

    if $test_func; then
        log_pass "$test_name"
        ((TESTS_PASSED++)) || true
    else
        log_fail "$test_name"
        ((TESTS_FAILED++)) || true
    fi
    return 0  # Always return success to prevent set -e from exiting
}

setup_test_environment() {
    log_test "Setting up test environment for rollback testing..."

    # Create directory structure
    sudo mkdir -p "$TEST_INSTALL_DIR"/{bin,lib}
    sudo mkdir -p "$TEST_CONFIG_DIR"
    sudo mkdir -p "$TEST_DATA_DIR"
    sudo mkdir -p "$TEST_BACKUP_DIR/rollback"

    # Create original version files
    echo "1.0.0" | sudo tee "$TEST_INSTALL_DIR/version.txt" > /dev/null
    echo "original_content" | sudo tee "$TEST_INSTALL_DIR/app.py" > /dev/null

    # Create original config
    sudo tee "$TEST_CONFIG_DIR/controller.conf" > /dev/null <<EOF
[general]
log_level = INFO
setting = original_value
EOF

    # Create original database
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "$TEST_DATA_DIR/test.db" <<EOF
CREATE TABLE IF NOT EXISTS test_data (id INTEGER PRIMARY KEY, value TEXT);
INSERT INTO test_data (value) VALUES ('original_data');
EOF
    fi

    log_test "Original state created (version 1.0.0)"
}

create_rollback_point() {
    local rollback_name="$1"
    local rollback_path="$TEST_BACKUP_DIR/rollback/$rollback_name"

    mkdir -p "$rollback_path"

    # Archive application
    tar -czf "$rollback_path/app.tar.gz" -C "$TEST_INSTALL_DIR" . 2>/dev/null

    # Archive config
    tar -czf "$rollback_path/config.tar.gz" -C "$TEST_CONFIG_DIR" . 2>/dev/null

    # Copy database
    if [ -f "$TEST_DATA_DIR/test.db" ]; then
        cp "$TEST_DATA_DIR/test.db" "$rollback_path/database.db"
    fi

    # Create metadata
    cat > "$rollback_path/metadata.json" <<EOF
{
    "name": "$rollback_name",
    "timestamp": "$(date -Iseconds)",
    "version": "1.0.0",
    "description": "Pre-upgrade rollback point"
}
EOF

    log_test "Rollback point created: $rollback_name"
}

simulate_partial_upgrade() {
    log_test "Simulating partial upgrade..."

    # Modify version (upgrade started)
    echo "2.0.0" | sudo tee "$TEST_INSTALL_DIR/version.txt" > /dev/null

    # Modify some files (partially upgraded)
    echo "partially_upgraded_content" | sudo tee "$TEST_INSTALL_DIR/app.py" > /dev/null

    # Modify config
    sudo tee "$TEST_CONFIG_DIR/controller.conf" > /dev/null <<EOF
[general]
log_level = DEBUG
setting = upgraded_value
new_setting = added
EOF

    # Modify database
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "$TEST_DATA_DIR/test.db" "INSERT INTO test_data (value) VALUES ('upgraded_data');"
    fi

    log_test "Simulated partial upgrade to version 2.0.0"
}

perform_rollback() {
    local rollback_name="$1"
    local rollback_path="$TEST_BACKUP_DIR/rollback/$rollback_name"

    log_test "Performing rollback from: $rollback_name"

    # Restore application
    if [ -f "$rollback_path/app.tar.gz" ]; then
        sudo rm -rf "$TEST_INSTALL_DIR"/*
        sudo tar -xzf "$rollback_path/app.tar.gz" -C "$TEST_INSTALL_DIR"
    fi

    # Restore config
    if [ -f "$rollback_path/config.tar.gz" ]; then
        sudo rm -rf "$TEST_CONFIG_DIR"/*
        sudo tar -xzf "$rollback_path/config.tar.gz" -C "$TEST_CONFIG_DIR"
    fi

    # Restore database
    if [ -f "$rollback_path/database.db" ]; then
        cp "$rollback_path/database.db" "$TEST_DATA_DIR/test.db"
    fi

    log_test "Rollback completed"
}

cleanup() {
    log_test "Cleaning up test environment..."
    sudo rm -rf "$TEST_INSTALL_DIR" "$TEST_CONFIG_DIR" "$TEST_DATA_DIR" "$TEST_BACKUP_DIR" 2>/dev/null || true
}

# =============================================================================
# Test Cases
# =============================================================================

test_original_state_exists() {
    [ -f "$TEST_INSTALL_DIR/version.txt" ] && \
    grep -q "1.0.0" "$TEST_INSTALL_DIR/version.txt"
}

test_rollback_point_created() {
    [ -d "$TEST_BACKUP_DIR/rollback/pre-upgrade-test" ] && \
    [ -f "$TEST_BACKUP_DIR/rollback/pre-upgrade-test/app.tar.gz" ] && \
    [ -f "$TEST_BACKUP_DIR/rollback/pre-upgrade-test/metadata.json" ]
}

test_partial_upgrade_applied() {
    [ -f "$TEST_INSTALL_DIR/version.txt" ] && \
    grep -q "2.0.0" "$TEST_INSTALL_DIR/version.txt" && \
    grep -q "upgraded_value" "$TEST_CONFIG_DIR/controller.conf"
}

test_rollback_restores_version() {
    grep -q "1.0.0" "$TEST_INSTALL_DIR/version.txt"
}

test_rollback_restores_app() {
    grep -q "original_content" "$TEST_INSTALL_DIR/app.py"
}

test_rollback_restores_config() {
    grep -q "original_value" "$TEST_CONFIG_DIR/controller.conf" && \
    ! grep -q "new_setting" "$TEST_CONFIG_DIR/controller.conf"
}

test_rollback_restores_database() {
    if ! command -v sqlite3 >/dev/null 2>&1; then
        log_warn "sqlite3 not available, skipping database rollback test"
        return 0
    fi

    local count
    count=$(sqlite3 "$TEST_DATA_DIR/test.db" "SELECT COUNT(*) FROM test_data;" 2>/dev/null)

    # Should only have original data (1 row)
    [ "$count" -eq 1 ]
}

test_verify_rollback_point() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    export ROLLBACK_DIR="$TEST_BACKUP_DIR/rollback"

    verify_rollback_point "pre-upgrade-test" >/dev/null 2>&1
}

test_test_rollback_restore() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    export ROLLBACK_DIR="$TEST_BACKUP_DIR/rollback"

    test_rollback_restore "pre-upgrade-test" >/dev/null 2>&1
}

test_emergency_rollback_function() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    export INSTALL_DIR="$TEST_INSTALL_DIR"
    export CONFIG_DIR="$TEST_CONFIG_DIR"
    export DATA_DIR="$TEST_DATA_DIR"
    export ROLLBACK_DIR="$TEST_BACKUP_DIR/rollback"

    # Simulate another partial upgrade
    echo "3.0.0" | sudo tee "$TEST_INSTALL_DIR/version.txt" > /dev/null

    # Emergency rollback should restore to 1.0.0
    emergency_rollback "pre-upgrade-test" >/dev/null 2>&1 || true

    grep -q "1.0.0" "$TEST_INSTALL_DIR/version.txt"
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo ""
    echo "============================================================"
    echo "     Water Controller Upgrade Test Suite"
    echo "     Test: Rollback During Mid-Upgrade"
    echo "============================================================"
    echo ""

    # Setup
    trap cleanup EXIT
    cleanup
    setup_test_environment

    # Phase 1: Verify original state
    run_test "Original state exists" test_original_state_exists

    # Phase 2: Create rollback point
    create_rollback_point "pre-upgrade-test"
    run_test "Rollback point created" test_rollback_point_created
    run_test "Verify rollback point" test_verify_rollback_point
    run_test "Test rollback restore (dry-run)" test_test_rollback_restore

    # Phase 3: Simulate partial upgrade
    simulate_partial_upgrade
    run_test "Partial upgrade applied" test_partial_upgrade_applied

    # Phase 4: Perform rollback
    perform_rollback "pre-upgrade-test"
    run_test "Rollback restores version" test_rollback_restores_version
    run_test "Rollback restores app" test_rollback_restores_app
    run_test "Rollback restores config" test_rollback_restores_config
    run_test "Rollback restores database" test_rollback_restores_database

    # Phase 5: Test emergency rollback function
    run_test "Emergency rollback function" test_emergency_rollback_function

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
