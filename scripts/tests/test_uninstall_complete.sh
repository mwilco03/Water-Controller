#!/bin/bash
#
# Test: Complete uninstallation verification
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This test verifies that complete uninstall removes all components.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALL_SCRIPT="$PROJECT_ROOT/scripts/install.sh"

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

# =============================================================================
# Test Cases
# =============================================================================

test_install_script_syntax() {
    # Verify script has no syntax errors
    bash -n "$INSTALL_SCRIPT"
}

test_uninstall_functions_exist() {
    # Verify key uninstall functions are defined
    grep -q "do_uninstall()" "$INSTALL_SCRIPT" && \
    grep -q "_uninstall_pnet_libraries()" "$INSTALL_SCRIPT" && \
    grep -q "_uninstall_firewall_rules()" "$INSTALL_SCRIPT" && \
    grep -q "_uninstall_udev_rules()" "$INSTALL_SCRIPT" && \
    grep -q "_uninstall_network_config()" "$INSTALL_SCRIPT"
}

test_sudo_in_uninstall() {
    # Verify sudo is used for privileged operations
    local uninstall_section
    uninstall_section=$(sed -n '/^do_uninstall()/,/^[a-z_]*().*{/p' "$INSTALL_SCRIPT" | head -200)

    # Check for sudo on systemctl commands
    echo "$uninstall_section" | grep -q "sudo systemctl stop" && \
    echo "$uninstall_section" | grep -q "sudo systemctl disable" && \
    echo "$uninstall_section" | grep -q "sudo rm -f /etc/systemd/system/water-controller.service"
}

test_purge_flag_exists() {
    grep -q "PURGE_MODE" "$INSTALL_SCRIPT" && \
    grep -q "\-\-purge" "$INSTALL_SCRIPT"
}

test_keep_data_flag_exists() {
    grep -q "KEEP_DATA" "$INSTALL_SCRIPT" && \
    grep -q "\-\-keep-data" "$INSTALL_SCRIPT"
}

test_manifest_creation() {
    # Verify manifest is created during uninstall
    grep -q "manifest_file=" "$INSTALL_SCRIPT" && \
    grep -q "Uninstall Manifest" "$INSTALL_SCRIPT"
}

test_pnet_cleanup_paths() {
    # Verify P-Net paths are cleaned up
    grep -q "/usr/local/lib/libpnet" "$INSTALL_SCRIPT" && \
    grep -q "/usr/local/include/pnet" "$INSTALL_SCRIPT" && \
    grep -q "/etc/pnet" "$INSTALL_SCRIPT"
}

test_firewall_cleanup() {
    # Verify firewall cleanup for different systems
    grep -q "ufw delete allow" "$INSTALL_SCRIPT" && \
    grep -q "firewall-cmd --permanent --remove-port" "$INSTALL_SCRIPT" && \
    grep -q "nft delete table" "$INSTALL_SCRIPT" && \
    grep -q "iptables -D INPUT" "$INSTALL_SCRIPT"
}

test_udev_cleanup() {
    # Verify udev rules are cleaned
    grep -q "99-water-controller" "$INSTALL_SCRIPT" && \
    grep -q "udevadm control --reload-rules" "$INSTALL_SCRIPT"
}

test_network_config_cleanup() {
    # Verify network configuration cleanup
    grep -q "systemd/network/10-water-controller" "$INSTALL_SCRIPT" && \
    grep -q "nmcli connection delete" "$INSTALL_SCRIPT" && \
    grep -q "dhcpcd.conf" "$INSTALL_SCRIPT"
}

test_dry_run_uninstall() {
    # Test dry-run mode shows expected output
    local output
    output=$("$INSTALL_SCRIPT" --dry-run --uninstall 2>&1) || true

    echo "$output" | grep -q "DRY RUN" && \
    echo "$output" | grep -q "Stop and disable service"
}

test_dry_run_purge() {
    # Test dry-run with purge shows P-Net cleanup
    local output
    output=$("$INSTALL_SCRIPT" --dry-run --uninstall --purge 2>&1) || true

    echo "$output" | grep -q "P-Net libraries"
}

test_dry_run_keep_data() {
    # Test dry-run with keep-data shows preservation
    local output
    output=$("$INSTALL_SCRIPT" --dry-run --uninstall --keep-data 2>&1) || true

    echo "$output" | grep -q "Preserve"
}

test_tmpfs_cleanup() {
    # Verify tmpfs cleanup
    grep -q "umount /run/water-controller" "$INSTALL_SCRIPT" && \
    grep -q "sed -i '/water-controller/d' /etc/fstab" "$INSTALL_SCRIPT"
}

test_logrotate_cleanup() {
    # Verify logrotate cleanup
    grep -q "rm -f /etc/logrotate.d/water-controller" "$INSTALL_SCRIPT"
}

test_service_user_cleanup() {
    # Verify service user cleanup with sudo
    grep -q "sudo userdel water-controller" "$INSTALL_SCRIPT"
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo ""
    echo "============================================================"
    echo "     Water Controller Uninstall Test Suite"
    echo "     Test: Complete Uninstallation Verification"
    echo "============================================================"
    echo ""

    # Run tests
    run_test "Install script syntax" test_install_script_syntax
    run_test "Uninstall functions exist" test_uninstall_functions_exist
    run_test "sudo used in uninstall" test_sudo_in_uninstall
    run_test "--purge flag exists" test_purge_flag_exists
    run_test "--keep-data flag exists" test_keep_data_flag_exists
    run_test "Manifest creation" test_manifest_creation
    run_test "P-Net cleanup paths" test_pnet_cleanup_paths
    run_test "Firewall cleanup" test_firewall_cleanup
    run_test "udev cleanup" test_udev_cleanup
    run_test "Network config cleanup" test_network_config_cleanup
    run_test "Dry-run uninstall" test_dry_run_uninstall
    run_test "Dry-run with --purge" test_dry_run_purge
    run_test "Dry-run with --keep-data" test_dry_run_keep_data
    run_test "tmpfs cleanup" test_tmpfs_cleanup
    run_test "logrotate cleanup" test_logrotate_cleanup
    run_test "Service user cleanup" test_service_user_cleanup

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
