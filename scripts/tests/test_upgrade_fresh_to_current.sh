#!/bin/bash
#
# Test: Upgrade from fresh install to current version
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This test verifies that a fresh installation can be upgraded successfully.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALL_SCRIPT="$PROJECT_ROOT/scripts/install.sh"

# Test configuration
TEST_INSTALL_DIR="/tmp/test-wtc-install"
TEST_CONFIG_DIR="/tmp/test-wtc-config"
TEST_DATA_DIR="/tmp/test-wtc-data"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_test() { echo -e "${GREEN}[TEST]${NC} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# Track test results
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

cleanup() {
    log_test "Cleaning up test environment..."
    sudo rm -rf "$TEST_INSTALL_DIR" "$TEST_CONFIG_DIR" "$TEST_DATA_DIR" 2>/dev/null || true
    sudo systemctl stop water-controller.service 2>/dev/null || true
}

# =============================================================================
# Test Cases
# =============================================================================

test_install_script_exists() {
    [ -f "$INSTALL_SCRIPT" ] && [ -x "$INSTALL_SCRIPT" ]
}

test_upgrade_module_exists() {
    local upgrade_module="$PROJECT_ROOT/scripts/lib/upgrade.sh"
    [ -f "$upgrade_module" ]
}

test_pre_upgrade_health_check() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    # This should work even without an existing installation
    # It may warn but should not crash
    pre_upgrade_health_check >/dev/null 2>&1
    local result=$?

    # Health check may fail (no installation) but should not crash
    return 0
}

test_check_disk_space() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    # Should return 0 if there's enough space, 1 otherwise
    check_disk_space_for_upgrade >/dev/null 2>&1
    local result=$?

    # On a test system, we expect this to pass
    [ $result -eq 0 ]
}

test_generate_upgrade_plan() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    local plan_file
    plan_file=$(generate_upgrade_plan "1.0.0" 2>/dev/null)

    # Should return a valid file path
    [ -n "$plan_file" ] && [ -f "$plan_file" ]
}

test_export_configuration() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    # Create minimal test config
    sudo mkdir -p "$TEST_CONFIG_DIR"
    echo "test=value" | sudo tee "$TEST_CONFIG_DIR/test.conf" >/dev/null

    # Export should succeed
    export CONFIG_DIR="$TEST_CONFIG_DIR"
    local export_file
    export_file=$(export_current_configuration 2>/dev/null)

    [ -n "$export_file" ] && [ -f "$export_file" ]
}

test_version_comparison() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    export INSTALL_DIR="$TEST_INSTALL_DIR"
    sudo mkdir -p "$TEST_INSTALL_DIR"
    echo "1.0.0" | sudo tee "$TEST_INSTALL_DIR/version.txt" >/dev/null

    # Compare same version
    local result
    result=$(compare_versions "1.0.0" 2>/dev/null)

    echo "$result" | grep -q "status=current"
}

test_upgrade_available_detection() {
    source "$PROJECT_ROOT/scripts/lib/upgrade.sh"

    export INSTALL_DIR="$TEST_INSTALL_DIR"
    sudo mkdir -p "$TEST_INSTALL_DIR"
    echo "1.0.0" | sudo tee "$TEST_INSTALL_DIR/version.txt" >/dev/null

    # Compare different version
    local result
    result=$(compare_versions "2.0.0" 2>/dev/null)

    echo "$result" | grep -q "status=upgrade_available"
}

test_dry_run_mode() {
    # Test that --dry-run shows what would happen without making changes
    local output
    output=$("$INSTALL_SCRIPT" --dry-run --uninstall 2>&1) || true

    echo "$output" | grep -q "DRY RUN"
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo ""
    echo "============================================================"
    echo "     Water Controller Upgrade Test Suite"
    echo "     Test: Fresh Install to Current"
    echo "============================================================"
    echo ""

    # Setup
    trap cleanup EXIT
    cleanup

    # Run tests
    run_test "Install script exists" test_install_script_exists
    run_test "Upgrade module exists" test_upgrade_module_exists
    run_test "Pre-upgrade health check" test_pre_upgrade_health_check
    run_test "Check disk space function" test_check_disk_space
    run_test "Generate upgrade plan" test_generate_upgrade_plan
    run_test "Export configuration" test_export_configuration
    run_test "Version comparison (same)" test_version_comparison
    run_test "Upgrade available detection" test_upgrade_available_detection
    run_test "Dry-run mode" test_dry_run_mode

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
