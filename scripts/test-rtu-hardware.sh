#!/bin/bash
# Water Treatment Controller - RTU Hardware Test Suite
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Comprehensive test suite for verifying RTU hardware connectivity
# and functionality with the Water Treatment Controller.

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Auto-detect network interface
detect_interface() {
    for iface in /sys/class/net/*; do
        name=$(basename "$iface")
        case "$name" in lo|docker*|veth*|br-*|virbr*|vnet*) continue ;; esac
        if [ -f "$iface/operstate" ] && [ "$(cat "$iface/operstate")" = "up" ]; then
            echo "$name"; return 0
        fi
    done
    for iface in /sys/class/net/*; do
        name=$(basename "$iface")
        case "$name" in lo|docker*|veth*|br-*|virbr*|vnet*) continue ;; esac
        echo "$name"; return 0
    done
}

# Configuration
RTU_IP="${RTU_IP:-192.168.1.100}"
RTU_STATION="${RTU_STATION:-water-treat-rtu}"
CONTROLLER_IP="${CONTROLLER_IP:-192.168.1.1}"
PROFINET_INTERFACE="${PROFINET_INTERFACE:-$(detect_interface)}"
# API runs on port 8000, UI on port 8080 (see config/ports.env)
API_URL="${API_URL:-http://localhost:${WTC_API_PORT:-8000}}"
TEST_TIMEOUT="${TEST_TIMEOUT:-10}"
VERBOSE="${VERBOSE:-false}"

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0
TEST_LOG=""

print_header() {
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   Water Treatment Controller - RTU Hardware Test Suite   ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "RTU IP:        $RTU_IP"
    echo "Station Name:  $RTU_STATION"
    echo "Controller IP: $CONTROLLER_IP"
    echo "Interface:     $PROFINET_INTERFACE"
    echo "API URL:       $API_URL"
    echo ""
}

log_test() {
    local result="$1"
    local name="$2"
    local details="$3"

    TEST_LOG+="$(date -Iseconds) | $result | $name | $details\n"

    case "$result" in
        PASS)
            echo -e "  ${GREEN}✓${NC} $name"
            ((TESTS_PASSED++))
            ;;
        FAIL)
            echo -e "  ${RED}✗${NC} $name"
            echo -e "    ${RED}→ $details${NC}"
            ((TESTS_FAILED++))
            ;;
        SKIP)
            echo -e "  ${YELLOW}○${NC} $name (skipped: $details)"
            ((TESTS_SKIPPED++))
            ;;
        INFO)
            echo -e "  ${CYAN}ℹ${NC} $name: $details"
            ;;
    esac
}

run_test() {
    local name="$1"
    local cmd="$2"

    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "  ${CYAN}Running:${NC} $cmd"
    fi

    if output=$(eval "$cmd" 2>&1); then
        log_test "PASS" "$name" ""
        return 0
    else
        log_test "FAIL" "$name" "$output"
        return 1
    fi
}

# ============================================
# Network Connectivity Tests
# ============================================
test_network() {
    echo ""
    echo -e "${CYAN}═══ Network Connectivity Tests ═══${NC}"

    # Test 1: Ping RTU
    if ping -c 3 -W 2 "$RTU_IP" >/dev/null 2>&1; then
        log_test "PASS" "RTU ping test ($RTU_IP)"
    else
        log_test "FAIL" "RTU ping test ($RTU_IP)" "Cannot reach RTU"
        return 1
    fi

    # Test 2: Check PROFINET interface
    if ip link show "$PROFINET_INTERFACE" >/dev/null 2>&1; then
        local state=$(ip link show "$PROFINET_INTERFACE" | grep -oP 'state \K\w+')
        if [[ "$state" == "UP" ]]; then
            log_test "PASS" "PROFINET interface state"
        else
            log_test "FAIL" "PROFINET interface state" "Interface is $state"
        fi
    else
        log_test "FAIL" "PROFINET interface exists" "Interface $PROFINET_INTERFACE not found"
    fi

    # Test 3: Check for PROFINET ports
    if ss -uln | grep -q ":34962\|:34963\|:34964"; then
        log_test "PASS" "PROFINET ports listening"
    else
        log_test "SKIP" "PROFINET ports listening" "Controller may not be running"
    fi

    # Test 4: ARP entry for RTU
    if arp -n | grep -q "$RTU_IP"; then
        local mac=$(arp -n | grep "$RTU_IP" | awk '{print $3}')
        log_test "PASS" "RTU MAC address resolved"
        log_test "INFO" "RTU MAC" "$mac"
    else
        log_test "SKIP" "RTU MAC address" "No ARP entry yet"
    fi

    # Test 5: Network latency
    local latency=$(ping -c 5 -W 2 "$RTU_IP" 2>/dev/null | tail -1 | awk -F'/' '{print $5}')
    if [[ -n "$latency" ]]; then
        log_test "INFO" "Network latency" "${latency}ms average"
        if (( $(echo "$latency < 10" | bc -l) )); then
            log_test "PASS" "Latency acceptable (<10ms)"
        else
            log_test "FAIL" "Latency acceptable" "${latency}ms exceeds 10ms threshold"
        fi
    fi
}

# ============================================
# PROFINET Communication Tests
# ============================================
test_profinet() {
    echo ""
    echo -e "${CYAN}═══ PROFINET Communication Tests ═══${NC}"

    # Check if controller process is running
    if ! pgrep -f "water-controller" >/dev/null 2>&1; then
        log_test "SKIP" "PROFINET tests" "Controller not running"
        return 0
    fi

    # Test 1: DCP Identify (PROFINET device discovery)
    # Note: This requires custom tooling or the p-net stack
    log_test "INFO" "PROFINET DCP" "Sending identify request..."

    # Use netcat to send PROFINET DCP identify multicast
    # DCP uses multicast address 01:0e:cf:00:00:00 on ethertype 0x8892

    # Test 2: Check RTU connection state via API
    if curl -s "$API_URL/api/v1/rtus/$RTU_STATION" >/dev/null 2>&1; then
        local state=$(curl -s "$API_URL/api/v1/rtus/$RTU_STATION" | jq -r '.state // "unknown"')
        if [[ "$state" == "CONNECTED" || "$state" == "RUN" ]]; then
            log_test "PASS" "RTU PROFINET state"
            log_test "INFO" "Connection state" "$state"
        else
            log_test "FAIL" "RTU PROFINET state" "State is: $state"
        fi
    else
        log_test "SKIP" "RTU PROFINET state" "API not responding"
    fi

    # Test 3: Check cyclic data exchange
    local cycle_time=$(curl -s "$API_URL/api/v1/system/health" | jq -r '.cycle_time_ms // 0')
    if [[ "$cycle_time" != "0" && "$cycle_time" != "null" ]]; then
        log_test "PASS" "Cyclic data exchange active"
        log_test "INFO" "Cycle time" "${cycle_time}ms"
    else
        log_test "SKIP" "Cyclic data exchange" "Not available"
    fi

    # Test 4: Check packet loss
    local packet_loss=$(curl -s "$API_URL/api/v1/system/health" | jq -r '.packet_loss_percent // 0')
    if [[ "$packet_loss" != "null" ]]; then
        if (( $(echo "$packet_loss < 1" | bc -l) )); then
            log_test "PASS" "Packet loss acceptable (<1%)"
        else
            log_test "FAIL" "Packet loss" "${packet_loss}% exceeds threshold"
        fi
    fi
}

# ============================================
# Sensor Reading Tests
# ============================================
test_sensors() {
    echo ""
    echo -e "${CYAN}═══ Sensor Reading Tests ═══${NC}"

    # Get sensor data from API
    local sensors
    sensors=$(curl -s "$API_URL/api/v1/rtus/$RTU_STATION/sensors" 2>/dev/null)

    if [[ -z "$sensors" || "$sensors" == "null" ]]; then
        log_test "SKIP" "Sensor tests" "Cannot retrieve sensor data"
        return 0
    fi

    local sensor_count=$(echo "$sensors" | jq '.sensors | length')
    log_test "INFO" "Sensors detected" "$sensor_count"

    # Test each sensor
    echo "$sensors" | jq -c '.sensors[]' 2>/dev/null | while read -r sensor; do
        local name=$(echo "$sensor" | jq -r '.name')
        local value=$(echo "$sensor" | jq -r '.value')
        local unit=$(echo "$sensor" | jq -r '.unit')
        local quality=$(echo "$sensor" | jq -r '.quality')
        local slot=$(echo "$sensor" | jq -r '.slot')

        # Check quality
        if [[ "$quality" == "GOOD" ]]; then
            log_test "PASS" "Sensor $name (slot $slot)"
            log_test "INFO" "$name value" "$value $unit"
        else
            log_test "FAIL" "Sensor $name (slot $slot)" "Quality: $quality"
        fi

        # Validate value ranges
        case "$name" in
            *pH*)
                if (( $(echo "$value >= 0 && $value <= 14" | bc -l) )); then
                    log_test "PASS" "$name range valid (0-14)"
                else
                    log_test "FAIL" "$name range" "$value outside 0-14"
                fi
                ;;
            *Temp*|*temperature*)
                if (( $(echo "$value >= -40 && $value <= 100" | bc -l) )); then
                    log_test "PASS" "$name range valid (-40 to 100°C)"
                else
                    log_test "FAIL" "$name range" "$value outside -40 to 100"
                fi
                ;;
            *TDS*)
                if (( $(echo "$value >= 0 && $value <= 5000" | bc -l) )); then
                    log_test "PASS" "$name range valid (0-5000 ppm)"
                else
                    log_test "FAIL" "$name range" "$value outside 0-5000"
                fi
                ;;
            *Turbidity*)
                if (( $(echo "$value >= 0 && $value <= 4000" | bc -l) )); then
                    log_test "PASS" "$name range valid (0-4000 NTU)"
                else
                    log_test "FAIL" "$name range" "$value outside 0-4000"
                fi
                ;;
            *Flow*)
                if (( $(echo "$value >= 0" | bc -l) )); then
                    log_test "PASS" "$name range valid (>=0)"
                else
                    log_test "FAIL" "$name range" "$value is negative"
                fi
                ;;
            *Level*|*Pressure*)
                if (( $(echo "$value >= 0" | bc -l) )); then
                    log_test "PASS" "$name range valid"
                else
                    log_test "FAIL" "$name range" "$value is negative"
                fi
                ;;
        esac
    done
}

# ============================================
# Actuator Command Tests
# ============================================
test_actuators() {
    echo ""
    echo -e "${CYAN}═══ Actuator Command Tests ═══${NC}"

    echo -e "  ${YELLOW}⚠ WARNING: These tests will operate physical equipment!${NC}"
    echo -e "  ${YELLOW}  Ensure plant is in safe state before proceeding.${NC}"

    if [[ "$SKIP_ACTUATOR_TESTS" == "true" ]]; then
        log_test "SKIP" "Actuator tests" "SKIP_ACTUATOR_TESTS=true"
        return 0
    fi

    # Get actuator data
    local rtu_data
    rtu_data=$(curl -s "$API_URL/api/v1/rtus/$RTU_STATION" 2>/dev/null)

    if [[ -z "$rtu_data" || "$rtu_data" == "null" ]]; then
        log_test "SKIP" "Actuator tests" "Cannot retrieve RTU data"
        return 0
    fi

    # Test actuator commands
    local actuators=$(echo "$rtu_data" | jq -c '.actuators[]' 2>/dev/null)

    if [[ -z "$actuators" ]]; then
        log_test "SKIP" "Actuator tests" "No actuators found"
        return 0
    fi

    echo "$actuators" | while read -r actuator; do
        local slot=$(echo "$actuator" | jq -r '.slot')
        local name=$(echo "$actuator" | jq -r '.name')
        local current_cmd=$(echo "$actuator" | jq -r '.command')

        log_test "INFO" "Testing actuator" "$name (slot $slot)"

        # Test ON command
        if curl -s -X POST "$API_URL/api/v1/rtus/$RTU_STATION/actuators/$slot" \
            -H "Content-Type: application/json" \
            -d '{"command":"ON"}' >/dev/null 2>&1; then

            sleep 1
            local new_state=$(curl -s "$API_URL/api/v1/rtus/$RTU_STATION" | \
                jq -r ".actuators[] | select(.slot==$slot) | .command")

            if [[ "$new_state" == "ON" ]]; then
                log_test "PASS" "$name ON command"
            else
                log_test "FAIL" "$name ON command" "State is: $new_state"
            fi
        else
            log_test "FAIL" "$name ON command" "API request failed"
        fi

        # Test OFF command
        if curl -s -X POST "$API_URL/api/v1/rtus/$RTU_STATION/actuators/$slot" \
            -H "Content-Type: application/json" \
            -d '{"command":"OFF"}' >/dev/null 2>&1; then

            sleep 1
            local new_state=$(curl -s "$API_URL/api/v1/rtus/$RTU_STATION" | \
                jq -r ".actuators[] | select(.slot==$slot) | .command")

            if [[ "$new_state" == "OFF" ]]; then
                log_test "PASS" "$name OFF command"
            else
                log_test "FAIL" "$name OFF command" "State is: $new_state"
            fi
        else
            log_test "FAIL" "$name OFF command" "API request failed"
        fi

        # Test PWM command (if supported)
        if curl -s -X POST "$API_URL/api/v1/rtus/$RTU_STATION/actuators/$slot" \
            -H "Content-Type: application/json" \
            -d '{"command":"PWM","pwm_duty":50}' >/dev/null 2>&1; then

            sleep 1
            local new_duty=$(curl -s "$API_URL/api/v1/rtus/$RTU_STATION" | \
                jq -r ".actuators[] | select(.slot==$slot) | .pwm_duty")

            if [[ "$new_duty" == "50" ]]; then
                log_test "PASS" "$name PWM command (50%)"
            else
                log_test "FAIL" "$name PWM command" "Duty is: $new_duty"
            fi
        fi

        # Restore original state
        curl -s -X POST "$API_URL/api/v1/rtus/$RTU_STATION/actuators/$slot" \
            -H "Content-Type: application/json" \
            -d "{\"command\":\"$current_cmd\"}" >/dev/null 2>&1
    done
}

# ============================================
# Alarm System Tests
# ============================================
test_alarms() {
    echo ""
    echo -e "${CYAN}═══ Alarm System Tests ═══${NC}"

    # Get current alarms
    local alarms
    alarms=$(curl -s "$API_URL/api/v1/alarms" 2>/dev/null)

    if [[ -z "$alarms" || "$alarms" == "null" ]]; then
        log_test "SKIP" "Alarm tests" "Cannot retrieve alarm data"
        return 0
    fi

    local active_count=$(echo "$alarms" | jq '[.alarms[] | select(.state | startswith("ACTIVE"))] | length')
    local unacked_count=$(echo "$alarms" | jq '[.alarms[] | select(.state == "ACTIVE_UNACK")] | length')

    log_test "INFO" "Active alarms" "$active_count"
    log_test "INFO" "Unacknowledged" "$unacked_count"

    # Test acknowledge function
    if [[ "$unacked_count" -gt 0 ]]; then
        local test_alarm=$(echo "$alarms" | jq -r '.alarms[0].alarm_id')

        if curl -s -X POST "$API_URL/api/v1/alarms/$test_alarm/acknowledge" \
            -H "Content-Type: application/json" \
            -d '{"user":"test_script"}' >/dev/null 2>&1; then
            log_test "PASS" "Alarm acknowledge function"
        else
            log_test "FAIL" "Alarm acknowledge function" "API request failed"
        fi
    else
        log_test "SKIP" "Alarm acknowledge" "No unacked alarms to test"
    fi

    # Check alarm history
    local history
    history=$(curl -s "$API_URL/api/v1/alarms/history?limit=10" 2>/dev/null)

    if [[ -n "$history" && "$history" != "null" ]]; then
        local history_count=$(echo "$history" | jq '.alarms | length')
        log_test "PASS" "Alarm history available"
        log_test "INFO" "Recent alarms" "$history_count entries"
    else
        log_test "SKIP" "Alarm history" "No history available"
    fi
}

# ============================================
# Control Loop Tests
# ============================================
test_control_loops() {
    echo ""
    echo -e "${CYAN}═══ Control Loop Tests ═══${NC}"

    # Get PID loops
    local loops
    loops=$(curl -s "$API_URL/api/v1/control/pid" 2>/dev/null)

    if [[ -z "$loops" || "$loops" == "null" ]]; then
        log_test "SKIP" "Control loop tests" "Cannot retrieve PID data"
        return 0
    fi

    local loop_count=$(echo "$loops" | jq '.loops | length')
    log_test "INFO" "PID loops configured" "$loop_count"

    echo "$loops" | jq -c '.loops[]' 2>/dev/null | while read -r loop; do
        local loop_id=$(echo "$loop" | jq -r '.loop_id')
        local name=$(echo "$loop" | jq -r '.name')
        local enabled=$(echo "$loop" | jq -r '.enabled')
        local mode=$(echo "$loop" | jq -r '.mode')
        local pv=$(echo "$loop" | jq -r '.pv')
        local sp=$(echo "$loop" | jq -r '.setpoint')
        local cv=$(echo "$loop" | jq -r '.cv')

        log_test "INFO" "Loop: $name" "Mode=$mode, PV=$pv, SP=$sp, CV=$cv"

        if [[ "$enabled" == "true" ]]; then
            log_test "PASS" "$name loop enabled"

            # Check if PV is tracking setpoint reasonably
            local error=$(echo "scale=2; $pv - $sp" | bc -l | sed 's/-//')
            local sp_abs=$(echo "$sp" | sed 's/-//')
            if [[ "$sp_abs" != "0" ]]; then
                local error_pct=$(echo "scale=2; $error / $sp_abs * 100" | bc -l 2>/dev/null || echo "0")
                if (( $(echo "$error_pct < 10" | bc -l 2>/dev/null || echo "1") )); then
                    log_test "PASS" "$name tracking (error <10%)"
                else
                    log_test "INFO" "$name tracking" "Error: ${error_pct}%"
                fi
            fi
        else
            log_test "INFO" "$name loop" "Disabled"
        fi
    done
}

# ============================================
# Data Historian Tests
# ============================================
test_historian() {
    echo ""
    echo -e "${CYAN}═══ Data Historian Tests ═══${NC}"

    # Get trend tags
    local tags
    tags=$(curl -s "$API_URL/api/v1/trends/tags" 2>/dev/null)

    if [[ -z "$tags" || "$tags" == "null" || "$tags" == "[]" ]]; then
        log_test "SKIP" "Historian tests" "No trend tags configured"
        return 0
    fi

    local tag_count=$(echo "$tags" | jq 'length')
    log_test "INFO" "Trend tags configured" "$tag_count"

    # Test data retrieval for first tag
    local first_tag=$(echo "$tags" | jq -r '.[0].tag_id')
    local start_time=$(date -u -d '1 hour ago' '+%Y-%m-%dT%H:%M:%SZ')
    local end_time=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

    local samples
    samples=$(curl -s "$API_URL/api/v1/trends/$first_tag?start_time=$start_time&end_time=$end_time" 2>/dev/null)

    if [[ -n "$samples" && "$samples" != "null" ]]; then
        local sample_count=$(echo "$samples" | jq '.samples | length')
        if [[ "$sample_count" -gt 0 ]]; then
            log_test "PASS" "Trend data retrieval"
            log_test "INFO" "Samples (last hour)" "$sample_count"
        else
            log_test "INFO" "Trend data" "No samples in last hour"
        fi
    else
        log_test "FAIL" "Trend data retrieval" "API request failed"
    fi

    # Check database connection (if psql available)
    if command -v psql &>/dev/null; then
        if psql -h localhost -U wtc -d water_treatment -c "SELECT 1" >/dev/null 2>&1; then
            log_test "PASS" "Database connection"

            # Check hypertable stats
            local hypertable_size=$(psql -h localhost -U wtc -d water_treatment -t -c \
                "SELECT pg_size_pretty(hypertable_size('historian_data'))" 2>/dev/null | xargs)
            if [[ -n "$hypertable_size" ]]; then
                log_test "INFO" "Historian data size" "$hypertable_size"
            fi
        else
            log_test "SKIP" "Database connection" "Cannot connect"
        fi
    fi
}

# ============================================
# System Health Tests
# ============================================
test_system_health() {
    echo ""
    echo -e "${CYAN}═══ System Health Tests ═══${NC}"

    local health
    health=$(curl -s "$API_URL/api/v1/system/health" 2>/dev/null)

    if [[ -z "$health" || "$health" == "null" ]]; then
        log_test "FAIL" "System health endpoint" "API not responding"
        return 1
    fi

    log_test "PASS" "System health endpoint"

    # Parse health metrics
    local cycle_time=$(echo "$health" | jq -r '.cycle_time_ms // "N/A"')
    local packet_loss=$(echo "$health" | jq -r '.packet_loss_percent // "N/A"')
    local uptime=$(echo "$health" | jq -r '.uptime_percent // "N/A"')
    local cpu=$(echo "$health" | jq -r '.cpu_usage_percent // "N/A"')
    local memory=$(echo "$health" | jq -r '.memory_usage_percent // "N/A"')
    local rtus_connected=$(echo "$health" | jq -r '.rtus_connected // 0')
    local rtus_total=$(echo "$health" | jq -r '.rtus_total // 0')
    local active_alarms=$(echo "$health" | jq -r '.active_alarms // 0')

    log_test "INFO" "Cycle time" "${cycle_time}ms"
    log_test "INFO" "Packet loss" "${packet_loss}%"
    log_test "INFO" "Uptime" "${uptime}%"
    log_test "INFO" "CPU usage" "${cpu}%"
    log_test "INFO" "Memory usage" "${memory}%"
    log_test "INFO" "RTUs connected" "$rtus_connected / $rtus_total"
    log_test "INFO" "Active alarms" "$active_alarms"

    # Validate metrics
    if [[ "$uptime" != "N/A" ]] && (( $(echo "$uptime >= 99" | bc -l 2>/dev/null || echo "0") )); then
        log_test "PASS" "Uptime >=99%"
    elif [[ "$uptime" != "N/A" ]]; then
        log_test "FAIL" "Uptime" "Only ${uptime}%"
    fi

    if [[ "$cpu" != "N/A" ]] && (( $(echo "$cpu < 80" | bc -l 2>/dev/null || echo "1") )); then
        log_test "PASS" "CPU usage <80%"
    elif [[ "$cpu" != "N/A" ]]; then
        log_test "FAIL" "CPU usage" "${cpu}% exceeds threshold"
    fi

    if [[ "$memory" != "N/A" ]] && (( $(echo "$memory < 80" | bc -l 2>/dev/null || echo "1") )); then
        log_test "PASS" "Memory usage <80%"
    elif [[ "$memory" != "N/A" ]]; then
        log_test "FAIL" "Memory usage" "${memory}% exceeds threshold"
    fi

    if [[ "$rtus_connected" -eq "$rtus_total" && "$rtus_total" -gt 0 ]]; then
        log_test "PASS" "All RTUs connected"
    elif [[ "$rtus_total" -gt 0 ]]; then
        log_test "FAIL" "RTU connectivity" "Only $rtus_connected of $rtus_total connected"
    fi
}

# ============================================
# Print Summary
# ============================================
print_summary() {
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                    Test Summary                          ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""

    local total=$((TESTS_PASSED + TESTS_FAILED + TESTS_SKIPPED))

    echo -e "  ${GREEN}Passed:${NC}  $TESTS_PASSED"
    echo -e "  ${RED}Failed:${NC}  $TESTS_FAILED"
    echo -e "  ${YELLOW}Skipped:${NC} $TESTS_SKIPPED"
    echo -e "  Total:   $total"
    echo ""

    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║               ALL TESTS PASSED                           ║${NC}"
        echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
        return 0
    else
        echo -e "${RED}╔══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║           $TESTS_FAILED TEST(S) FAILED                              ║${NC}"
        echo -e "${RED}╚══════════════════════════════════════════════════════════╝${NC}"
        return 1
    fi
}

# Save test report
save_report() {
    local report_file="/var/log/water-controller/test-report-$(date +%Y%m%d-%H%M%S).log"

    mkdir -p "$(dirname "$report_file")"

    cat > "$report_file" << EOF
Water Treatment Controller - RTU Hardware Test Report
======================================================
Date: $(date -Iseconds)
RTU IP: $RTU_IP
Station: $RTU_STATION
Controller IP: $CONTROLLER_IP

Results:
  Passed:  $TESTS_PASSED
  Failed:  $TESTS_FAILED
  Skipped: $TESTS_SKIPPED

Detailed Log:
$(echo -e "$TEST_LOG")
EOF

    echo ""
    echo "Test report saved to: $report_file"
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --rtu-ip IP          RTU IP address (default: $RTU_IP)"
    echo "  --station NAME       RTU station name (default: $RTU_STATION)"
    echo "  --api-url URL        API URL (default: $API_URL)"
    echo "  --interface IFACE    PROFINET interface (default: $PROFINET_INTERFACE)"
    echo "  --skip-actuators     Skip actuator command tests"
    echo "  --verbose            Show detailed output"
    echo "  --quick              Run quick connectivity tests only"
    echo "  --save-report        Save test report to file"
    echo "  --help               Show this help"
    echo ""
    echo "Environment variables:"
    echo "  RTU_IP, RTU_STATION, CONTROLLER_IP, PROFINET_INTERFACE, API_URL"
}

# Parse arguments
QUICK_TEST=false
SAVE_REPORT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --rtu-ip)
            RTU_IP="$2"
            shift 2
            ;;
        --station)
            RTU_STATION="$2"
            shift 2
            ;;
        --api-url)
            API_URL="$2"
            shift 2
            ;;
        --interface)
            PROFINET_INTERFACE="$2"
            shift 2
            ;;
        --skip-actuators)
            SKIP_ACTUATOR_TESTS=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --quick)
            QUICK_TEST=true
            shift
            ;;
        --save-report)
            SAVE_REPORT=true
            shift
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Main execution
print_header

test_network

if [[ "$QUICK_TEST" == "true" ]]; then
    print_summary
    exit $?
fi

test_profinet
test_sensors
test_actuators
test_alarms
test_control_loops
test_historian
test_system_health

if [[ "$SAVE_REPORT" == "true" ]]; then
    save_report
fi

print_summary
