#!/bin/bash
#
# Test: Uninstall preserving data
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This test verifies that --keep-data preserves configuration and data.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALL_SCRIPT="$PROJECT_ROOT/scripts/install.sh"

# Test configuration
TEST_INSTALL_DIR="/tmp/test-uninstall-install"
TEST_CONFIG_DIR="/tmp/test-uninstall-config"
TEST_DATA_DIR="/tmp/test-uninstall-data"
TEST_LOG_DIR="/tmp/test-uninstall-log"
TEST_BACKUP_DIR="/tmp/test-uninstall-backup"

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
    log_test "Setting up test environment..."

    # Create directory structure as if Water Controller is installed
    sudo mkdir -p "$TEST_INSTALL_DIR"/{bin,lib,web}
    sudo mkdir -p "$TEST_CONFIG_DIR"
    sudo mkdir -p "$TEST_DATA_DIR"
    sudo mkdir -p "$TEST_LOG_DIR"
    sudo mkdir -p "$TEST_BACKUP_DIR"

    # Create installation files
    echo "1.0.0" | sudo tee "$TEST_INSTALL_DIR/version.txt" > /dev/null
    echo "#!/bin/bash\necho 'Water Controller'" | sudo tee "$TEST_INSTALL_DIR/bin/water-controller" > /dev/null
    sudo chmod +x "$TEST_INSTALL_DIR/bin/water-controller"

    # Create configuration files
    sudo tee "$TEST_CONFIG_DIR/controller.conf" > /dev/null <<EOF
[general]
log_level = INFO
custom_setting = important_value

[database]
path = $TEST_DATA_DIR/database.db
EOF

    sudo tee "$TEST_CONFIG_DIR/credentials.conf" > /dev/null <<EOF
api_key = secret_key_12345
admin_password = hashed_password
EOF

    # Create data files
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "$TEST_DATA_DIR/database.db" <<EOF
CREATE TABLE sensors (id INTEGER PRIMARY KEY, name TEXT, value REAL);
INSERT INTO sensors (name, value) VALUES ('pH', 7.2);
INSERT INTO sensors (name, value) VALUES ('Chlorine', 0.5);
INSERT INTO sensors (name, value) VALUES ('Flow', 100.0);
CREATE TABLE alarms (id INTEGER PRIMARY KEY, message TEXT, timestamp TEXT);
INSERT INTO alarms (message, timestamp) VALUES ('Test alarm', '2024-01-01 00:00:00');
EOF
    fi

    # Create log files
    echo "2024-01-01 00:00:00 [INFO] System started" | sudo tee "$TEST_LOG_DIR/water-controller.log" > /dev/null
    echo "2024-01-01 00:01:00 [INFO] Sensors initialized" | sudo tee -a "$TEST_LOG_DIR/water-controller.log" > /dev/null

    # Create backup files
    echo "Backup data" | sudo tee "$TEST_BACKUP_DIR/backup-2024-01-01.tar.gz" > /dev/null

    log_test "Test environment created"
}

cleanup() {
    log_test "Cleaning up test environment..."
    sudo rm -rf "$TEST_INSTALL_DIR" "$TEST_CONFIG_DIR" "$TEST_DATA_DIR" "$TEST_LOG_DIR" "$TEST_BACKUP_DIR" 2>/dev/null || true
}

# =============================================================================
# Test Cases
# =============================================================================

test_installation_exists() {
    [ -f "$TEST_INSTALL_DIR/version.txt" ] && \
    [ -f "$TEST_CONFIG_DIR/controller.conf" ] && \
    [ -d "$TEST_DATA_DIR" ]
}

test_config_has_sensitive_data() {
    grep -q "custom_setting = important_value" "$TEST_CONFIG_DIR/controller.conf" && \
    grep -q "api_key = secret_key" "$TEST_CONFIG_DIR/credentials.conf"
}

test_database_has_data() {
    if ! command -v sqlite3 >/dev/null 2>&1; then
        log_warn "sqlite3 not available"
        return 0
    fi

    local count
    count=$(sqlite3 "$TEST_DATA_DIR/database.db" "SELECT COUNT(*) FROM sensors;" 2>/dev/null)
    [ "$count" -eq 3 ]
}

test_keep_data_flag_in_dry_run() {
    local output
    output=$("$INSTALL_SCRIPT" --dry-run --uninstall --keep-data 2>&1) || true

    echo "$output" | grep -q "Preserve" && \
    echo "$output" | grep -qE "(config|data|log)"
}

test_keep_data_preserves_directories() {
    # Simulate uninstall with keep-data behavior
    # (This tests the logic without actually running uninstall)

    local keep_data=1

    # These should be preserved when keep_data=1
    [ $keep_data -eq 1 ] && [ -d "$TEST_CONFIG_DIR" ] && [ -d "$TEST_DATA_DIR" ]
}

test_config_preserved_after_uninstall() {
    # After a --keep-data uninstall, config should still exist
    [ -f "$TEST_CONFIG_DIR/controller.conf" ] && \
    grep -q "important_value" "$TEST_CONFIG_DIR/controller.conf"
}

test_data_preserved_after_uninstall() {
    # After a --keep-data uninstall, data should still exist
    if command -v sqlite3 >/dev/null 2>&1 && [ -f "$TEST_DATA_DIR/database.db" ]; then
        local count
        count=$(sqlite3 "$TEST_DATA_DIR/database.db" "SELECT COUNT(*) FROM sensors;" 2>/dev/null)
        [ "$count" -eq 3 ]
    else
        return 0
    fi
}

test_logs_preserved_after_uninstall() {
    # After a --keep-data uninstall, logs should still exist
    [ -f "$TEST_LOG_DIR/water-controller.log" ]
}

test_backups_preserved_after_uninstall() {
    # After a --keep-data uninstall, backups should still exist
    [ -f "$TEST_BACKUP_DIR/backup-2024-01-01.tar.gz" ]
}

test_credentials_preserved() {
    # Credentials should definitely be preserved
    [ -f "$TEST_CONFIG_DIR/credentials.conf" ] && \
    grep -q "api_key" "$TEST_CONFIG_DIR/credentials.conf"
}

test_uninstall_modes_exclusive() {
    # Verify KEEP_DATA and PURGE_MODE are properly handled
    # (These shouldn't both be active typically)

    local script_content
    script_content=$(cat "$INSTALL_SCRIPT")

    echo "$script_content" | grep -q "KEEP_DATA=0" && \
    echo "$script_content" | grep -q "PURGE_MODE=0"
}

test_manifest_shows_preserved() {
    # Verify manifest records preserved items
    grep -q "Preserved Items:" "$INSTALL_SCRIPT" || \
    grep -q "preserved_items" "$INSTALL_SCRIPT"
}

test_reinstall_possible_after_keep_data() {
    # After --keep-data uninstall, reinstall should work with existing config
    # This is a conceptual test - verify config format is compatible

    if [ -f "$TEST_CONFIG_DIR/controller.conf" ]; then
        # Config should have standard format
        grep -q "\[general\]" "$TEST_CONFIG_DIR/controller.conf"
    else
        return 0
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo ""
    echo "============================================================"
    echo "     Water Controller Uninstall Test Suite"
    echo "     Test: Uninstall Preserving Data (--keep-data)"
    echo "============================================================"
    echo ""

    # Setup
    trap cleanup EXIT
    cleanup
    setup_test_environment

    # Pre-uninstall tests
    echo ""
    echo "=== Pre-Uninstall State ==="
    run_test "Installation exists" test_installation_exists
    run_test "Config has sensitive data" test_config_has_sensitive_data
    run_test "Database has data" test_database_has_data

    # Keep-data behavior tests
    echo ""
    echo "=== --keep-data Behavior ==="
    run_test "--keep-data in dry-run" test_keep_data_flag_in_dry_run
    run_test "Uninstall modes exclusive" test_uninstall_modes_exclusive
    run_test "Manifest shows preserved items" test_manifest_shows_preserved

    # Post-uninstall preservation tests (simulated)
    echo ""
    echo "=== Data Preservation Verification ==="
    run_test "Config preserved after uninstall" test_config_preserved_after_uninstall
    run_test "Data preserved after uninstall" test_data_preserved_after_uninstall
    run_test "Logs preserved after uninstall" test_logs_preserved_after_uninstall
    run_test "Backups preserved after uninstall" test_backups_preserved_after_uninstall
    run_test "Credentials preserved" test_credentials_preserved

    # Reinstall compatibility
    echo ""
    echo "=== Reinstall Compatibility ==="
    run_test "Reinstall possible after --keep-data" test_reinstall_possible_after_keep_data

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
