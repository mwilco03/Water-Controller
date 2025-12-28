#!/bin/bash
#
# Fault Injection Test Script
# Tests system resilience under network failures
#
# CAUTION: This script modifies network settings. Run only in test environments.
#
# Prerequisites:
#   - Root/sudo access
#   - tc (traffic control) and iptables installed
#   - System services running
#
# Usage:
#   sudo ./fault_injection.sh [test_name]
#
# Available tests:
#   network_partition  - Complete network isolation
#   packet_loss        - Random packet drops
#   high_latency       - Simulated high latency
#   all                - Run all tests

set -e

# Configuration
API_URL="${API_URL:-http://localhost:8080}"
PROFINET_INTERFACE="${PROFINET_INTERFACE:-eth0}"
TEST_DURATION="${TEST_DURATION:-10}"
RECOVERY_WAIT="${RECOVERY_WAIT:-30}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi

    if ! command -v tc &> /dev/null; then
        log_error "tc (traffic control) not found. Install iproute2."
        exit 1
    fi

    if ! command -v iptables &> /dev/null; then
        log_error "iptables not found."
        exit 1
    fi

    if ! command -v curl &> /dev/null; then
        log_error "curl not found."
        exit 1
    fi

    log_info "Prerequisites satisfied."
}

# Check system health
check_health() {
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/api/v1/system/health" 2>/dev/null || echo "000")

    if [[ "$status" == "200" ]]; then
        return 0
    else
        return 1
    fi
}

# Wait for recovery
wait_for_recovery() {
    local max_attempts=$((RECOVERY_WAIT))
    local attempt=0

    log_info "Waiting for system recovery (max ${RECOVERY_WAIT}s)..."

    while [[ $attempt -lt $max_attempts ]]; do
        if check_health; then
            log_info "System recovered after ${attempt}s"
            return 0
        fi
        sleep 1
        ((attempt++))
    done

    log_error "System did not recover within ${RECOVERY_WAIT}s"
    return 1
}

# Cleanup function
cleanup() {
    log_info "Cleaning up network modifications..."

    # Remove tc qdisc
    tc qdisc del dev $PROFINET_INTERFACE root 2>/dev/null || true

    # Remove iptables rules
    iptables -D INPUT -p tcp --dport 8080 -j DROP 2>/dev/null || true
    iptables -D OUTPUT -p tcp --sport 8080 -j DROP 2>/dev/null || true
    iptables -D INPUT -i $PROFINET_INTERFACE -j DROP 2>/dev/null || true
    iptables -D OUTPUT -o $PROFINET_INTERFACE -j DROP 2>/dev/null || true

    log_info "Cleanup complete."
}

# Trap for cleanup on exit
trap cleanup EXIT

# Test: Network Partition
test_network_partition() {
    log_info "=== TEST: Network Partition ==="
    log_info "Simulating complete network isolation for ${TEST_DURATION}s..."

    # Record initial state
    local initial_health
    if check_health; then
        initial_health="healthy"
    else
        initial_health="unhealthy"
        log_warn "System already unhealthy before test"
    fi

    # Apply network partition (block PROFINET interface)
    iptables -A INPUT -i $PROFINET_INTERFACE -j DROP
    iptables -A OUTPUT -o $PROFINET_INTERFACE -j DROP

    log_info "Network partition active. Sleeping ${TEST_DURATION}s..."
    sleep $TEST_DURATION

    # Remove partition
    iptables -D INPUT -i $PROFINET_INTERFACE -j DROP
    iptables -D OUTPUT -o $PROFINET_INTERFACE -j DROP

    log_info "Network partition removed."

    # Wait for recovery
    if wait_for_recovery; then
        log_info "${GREEN}PASS${NC}: System recovered from network partition"
        return 0
    else
        log_error "${RED}FAIL${NC}: System did not recover from network partition"
        return 1
    fi
}

# Test: Packet Loss
test_packet_loss() {
    log_info "=== TEST: Packet Loss (30%) ==="
    log_info "Simulating 30% packet loss for ${TEST_DURATION}s..."

    # Record initial state
    if ! check_health; then
        log_warn "System unhealthy before test"
    fi

    # Apply packet loss
    tc qdisc add dev $PROFINET_INTERFACE root netem loss 30%

    log_info "Packet loss active. Sleeping ${TEST_DURATION}s..."
    sleep $TEST_DURATION

    # Check if system remains functional (degraded OK)
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/api/v1/system/health" 2>/dev/null || echo "000")

    # Remove packet loss
    tc qdisc del dev $PROFINET_INTERFACE root 2>/dev/null || true

    log_info "Packet loss removed."

    if [[ "$status" == "200" ]]; then
        log_info "${GREEN}PASS${NC}: System remained functional during packet loss"
        return 0
    else
        log_warn "${YELLOW}DEGRADED${NC}: System health check returned $status during packet loss"
        # Still pass if it recovers
        if wait_for_recovery; then
            return 0
        fi
        return 1
    fi
}

# Test: High Latency
test_high_latency() {
    log_info "=== TEST: High Latency (500ms) ==="
    log_info "Simulating 500ms latency for ${TEST_DURATION}s..."

    # Apply latency
    tc qdisc add dev $PROFINET_INTERFACE root netem delay 500ms 50ms

    log_info "High latency active. Sleeping ${TEST_DURATION}s..."
    sleep $TEST_DURATION

    # Check if system remains functional
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${API_URL}/api/v1/system/health" 2>/dev/null || echo "000")

    # Remove latency
    tc qdisc del dev $PROFINET_INTERFACE root 2>/dev/null || true

    log_info "High latency removed."

    if [[ "$status" == "200" ]]; then
        log_info "${GREEN}PASS${NC}: System remained functional during high latency"
        return 0
    else
        log_warn "${YELLOW}DEGRADED${NC}: System health check returned $status during high latency"
        if wait_for_recovery; then
            return 0
        fi
        return 1
    fi
}

# Test: API Server Disconnect
test_api_disconnect() {
    log_info "=== TEST: API Server Disconnect ==="
    log_info "Blocking API port 8080 for ${TEST_DURATION}s..."

    # Block API port
    iptables -A INPUT -p tcp --dport 8080 -j DROP
    iptables -A OUTPUT -p tcp --sport 8080 -j DROP

    log_info "API port blocked. Sleeping ${TEST_DURATION}s..."
    sleep $TEST_DURATION

    # Remove block
    iptables -D INPUT -p tcp --dport 8080 -j DROP
    iptables -D OUTPUT -p tcp --sport 8080 -j DROP

    log_info "API port unblocked."

    # Wait for recovery
    if wait_for_recovery; then
        log_info "${GREEN}PASS${NC}: System recovered from API disconnect"
        return 0
    else
        log_error "${RED}FAIL${NC}: System did not recover from API disconnect"
        return 1
    fi
}

# Run all tests
run_all_tests() {
    local passed=0
    local failed=0
    local total=4

    log_info "Running all fault injection tests..."
    echo ""

    # Ensure clean state
    cleanup

    # Initial health check
    if ! check_health; then
        log_error "System not healthy. Cannot run tests."
        exit 1
    fi

    # Run tests
    if test_network_partition; then ((passed++)); else ((failed++)); fi
    sleep 5  # Cool-down

    if test_packet_loss; then ((passed++)); else ((failed++)); fi
    sleep 5

    if test_high_latency; then ((passed++)); else ((failed++)); fi
    sleep 5

    if test_api_disconnect; then ((passed++)); else ((failed++)); fi

    # Summary
    echo ""
    log_info "=== TEST SUMMARY ==="
    log_info "Passed: ${passed}/${total}"
    log_info "Failed: ${failed}/${total}"

    if [[ $failed -eq 0 ]]; then
        log_info "${GREEN}All tests passed!${NC}"
        return 0
    else
        log_error "${RED}Some tests failed.${NC}"
        return 1
    fi
}

# Main
main() {
    check_prerequisites

    local test_name="${1:-all}"

    case "$test_name" in
        network_partition)
            test_network_partition
            ;;
        packet_loss)
            test_packet_loss
            ;;
        high_latency)
            test_high_latency
            ;;
        api_disconnect)
            test_api_disconnect
            ;;
        all)
            run_all_tests
            ;;
        *)
            echo "Usage: $0 [network_partition|packet_loss|high_latency|api_disconnect|all]"
            exit 1
            ;;
    esac
}

main "$@"
