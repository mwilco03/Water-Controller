#!/bin/bash
# =============================================================================
# Water-Controller Deployment Validator
# =============================================================================
# Validates all components are running and properly connected.
#
# Usage:
#   ./scripts/validate-deployment.sh
#
# Copyright (C) 2024-2026
# SPDX-License-Identifier: GPL-3.0-or-later
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Component status tracking
FAILED_CHECKS=()
PASSED_CHECKS=()
WARNING_CHECKS=()

log_section() {
    echo -e "\n${BLUE}═══ $1 ═══${NC}"
}

log_pass() {
    echo -e "${GREEN}✓${NC} $1"
    PASSED_CHECKS+=("$1")
}

log_fail() {
    echo -e "${RED}✗${NC} $1"
    FAILED_CHECKS+=("$1")
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    WARNING_CHECKS+=("$1")
}

log_info() {
    echo -e "  $1"
}

# =============================================================================
# Docker Compose Validation
# =============================================================================

validate_docker() {
    log_section "Docker Environment"

    if ! command -v docker &> /dev/null; then
        log_fail "Docker not installed"
        return 1
    fi
    log_pass "Docker installed"

    if ! docker info &> /dev/null; then
        log_fail "Docker daemon not running"
        return 1
    fi
    log_pass "Docker daemon running"

    if ! command -v docker compose &> /dev/null; then
        log_fail "Docker Compose not installed"
        return 1
    fi
    log_pass "Docker Compose installed"
}

# =============================================================================
# Container Status Validation
# =============================================================================

validate_containers() {
    log_section "Container Status"

    local containers=("wtc-database" "wtc-api" "wtc-ui" "wtc-grafana")

    for container in "${containers[@]}"; do
        if docker ps --filter "name=$container" --filter "status=running" | grep -q "$container"; then
            log_pass "Container $container running"

            # Check health status if available
            health=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "none")
            if [[ "$health" == "healthy" ]]; then
                log_info "Health: healthy"
            elif [[ "$health" == "unhealthy" ]]; then
                log_warn "Health: unhealthy"
            fi
        else
            log_fail "Container $container not running"
        fi
    done
}

# =============================================================================
# Database Validation
# =============================================================================

validate_database() {
    log_section "Database Connectivity"

    # Discovery: Check Docker access first
    local docker_error
    if ! docker_error=$(docker ps --filter "name=wtc-database" 2>&1); then
        log_fail "Cannot access Docker to check database container"
        if [[ "$docker_error" == *"permission denied"* ]]; then
            log_info "  Cause: Permission denied - run with sudo or add user to docker group"
        elif [[ "$docker_error" == *"Cannot connect"* ]]; then
            log_info "  Cause: Docker daemon not running"
        else
            log_info "  Cause: $docker_error"
        fi
        return 1
    fi

    # Check if database container is running
    if ! docker ps --filter "name=wtc-database" --filter "status=running" | grep -q wtc-database; then
        log_fail "Database container not running"

        # Discovery: WHY is it not running?
        local container_status
        container_status=$(docker ps -a --filter "name=wtc-database" --format "{{.Status}}" 2>/dev/null)
        if [[ -z "$container_status" ]]; then
            log_info "  Cause: Container does not exist"
            log_info "  Fix: docker compose up -d database"
        elif [[ "$container_status" == *"Exited"* ]]; then
            log_info "  Cause: Container exited - $container_status"
            log_info "  Check: docker logs wtc-database"
        else
            log_info "  Status: $container_status"
        fi
        return 1
    fi

    # Test PostgreSQL connection with error capture
    local pg_error
    if ! pg_error=$(docker exec wtc-database pg_isready -U wtc -d water_treatment 2>&1); then
        log_fail "PostgreSQL not accepting connections"
        if [[ "$pg_error" == *"rejecting"* ]]; then
            log_info "  Cause: PostgreSQL is rejecting connections (starting up?)"
        elif [[ "$pg_error" == *"no response"* ]]; then
            log_info "  Cause: PostgreSQL not responding"
        else
            log_info "  Cause: $pg_error"
        fi
        log_info "  Check: docker logs wtc-database"
        return 1
    fi
    log_pass "PostgreSQL accepting connections"

    # Check if wtc user can connect with error capture
    local psql_error
    if ! psql_error=$(docker exec wtc-database psql -U wtc -d water_treatment -c "SELECT 1" 2>&1); then
        log_fail "User 'wtc' cannot connect to database"
        if [[ "$psql_error" == *"does not exist"* ]]; then
            log_info "  Cause: User 'wtc' does not exist"
        elif [[ "$psql_error" == *"authentication failed"* ]]; then
            log_info "  Cause: Authentication failed for user 'wtc'"
        elif [[ "$psql_error" == *"database"*"does not exist"* ]]; then
            log_info "  Cause: Database 'water_treatment' does not exist"
        else
            log_info "  Cause: $psql_error"
        fi
        log_info "  Fix: docker exec wtc-database psql -U postgres -c \"CREATE USER wtc WITH PASSWORD 'wtc_password' SUPERUSER;\""
        return 1
    fi
    log_pass "User 'wtc' can connect to database"

    # Check TimescaleDB extension with error capture
    local tsdb_output
    tsdb_output=$(docker exec wtc-database psql -U wtc -d water_treatment -c "SELECT extname FROM pg_extension WHERE extname='timescaledb';" 2>&1)
    if echo "$tsdb_output" | grep -q timescaledb; then
        log_pass "TimescaleDB extension enabled"
    else
        log_warn "TimescaleDB extension not enabled"
        if [[ "$tsdb_output" == *"ERROR"* ]]; then
            log_info "  Query error: $tsdb_output"
        fi
    fi

    # Check critical tables exist with error capture
    local tables=("users" "rtus" "sensors" "controls" "alarm_rules" "historian_samples")
    local tables_ok=true

    for table in "${tables[@]}"; do
        local table_check
        table_check=$(docker exec wtc-database psql -U wtc -d water_treatment -c "\dt $table" 2>&1)
        if echo "$table_check" | grep -q "$table"; then
            log_pass "Table '$table' exists"
        else
            log_fail "Table '$table' missing"
            tables_ok=false
        fi
    done

    if [[ "$tables_ok" == false ]]; then
        log_info "Database schema incomplete. Re-run initialization:"
        log_info "docker exec -i wtc-database psql -U wtc -d water_treatment < docker/init.sql"
    fi

    # Check default admin user exists with error capture
    local admin_check
    admin_check=$(docker exec wtc-database psql -U wtc -d water_treatment -c "SELECT username FROM users WHERE username='admin';" 2>&1)
    if echo "$admin_check" | grep -q admin; then
        log_pass "Default admin user exists"
    else
        log_warn "Default admin user missing"
        if [[ "$admin_check" == *"ERROR"* ]]; then
            log_info "  Query error: $admin_check"
        fi
    fi
}

# =============================================================================
# API Validation
# =============================================================================

validate_api() {
    log_section "API Connectivity"

    local api_port="${WTC_API_PORT:-8000}"
    local api_url="http://localhost:$api_port"

    # Check if API container is running
    if ! docker ps --filter "name=wtc-api" --filter "status=running" | grep -q wtc-api; then
        log_fail "API container not running"
        return 1
    fi

    # Test health endpoint
    if curl -sf "$api_url/health" > /dev/null 2>&1; then
        log_pass "API health endpoint responding"

        # Check health details
        local health_json=$(curl -s "$api_url/health")
        local db_status=$(echo "$health_json" | grep -o '"database"[^}]*"status":"[^"]*"' | grep -o 'status":"[^"]*"' | cut -d'"' -f3)

        if [[ "$db_status" == "ok" ]]; then
            log_pass "API database connection OK"
        else
            log_fail "API database connection failed"
            log_info "Check API logs: docker logs wtc-api"
        fi
    else
        log_fail "API health endpoint not responding"
        log_info "Check API logs: docker logs wtc-api"
        return 1
    fi

    # Test API docs endpoint
    if curl -sf "$api_url/docs" > /dev/null 2>&1; then
        log_pass "API documentation available at $api_url/docs"
    else
        log_warn "API documentation not available"
    fi

    # Test API endpoints
    if curl -sf "$api_url/api/v1/rtus" > /dev/null 2>&1; then
        log_pass "API RTU endpoint responding"
    else
        log_warn "API RTU endpoint not responding (may require auth)"
    fi
}

# =============================================================================
# Web UI Validation
# =============================================================================

validate_ui() {
    log_section "Web UI Connectivity"

    local ui_port="${WTC_UI_PORT:-8080}"
    local ui_url="http://localhost:$ui_port"

    # Check if UI container is running
    if ! docker ps --filter "name=wtc-ui" --filter "status=running" | grep -q wtc-ui; then
        log_fail "UI container not running"
        return 1
    fi

    # Test UI endpoint
    if curl -sf "$ui_url" > /dev/null 2>&1; then
        log_pass "Web UI responding at $ui_url"
    else
        log_fail "Web UI not responding"
        log_info "Check UI logs: docker logs wtc-ui"
        return 1
    fi
}

# =============================================================================
# Grafana Validation
# =============================================================================

validate_grafana() {
    log_section "Grafana Connectivity"

    local grafana_port="${WTC_GRAFANA_PORT:-3000}"
    local grafana_url="http://localhost:$grafana_port"

    # Check if Grafana container is running
    if ! docker ps --filter "name=wtc-grafana" --filter "status=running" | grep -q wtc-grafana; then
        log_warn "Grafana container not running (optional)"
        return 0
    fi

    # Test Grafana endpoint
    if curl -sf "$grafana_url/api/health" > /dev/null 2>&1; then
        log_pass "Grafana responding at $grafana_url"
    else
        log_warn "Grafana not responding"
    fi
}

# =============================================================================
# Network Validation
# =============================================================================

validate_network() {
    log_section "Network Configuration"

    # Check if wtc-internal network exists
    if docker network ls | grep -q "wtc"; then
        log_pass "Docker network 'wtc-internal' exists"
    else
        log_warn "Docker network 'wtc-internal' not found"
    fi

    # Check port bindings
    local api_port="${WTC_API_PORT:-8000}"
    local ui_port="${WTC_UI_PORT:-8080}"
    local grafana_port="${WTC_GRAFANA_PORT:-3000}"

    if netstat -tuln 2>/dev/null | grep -q ":$api_port" || ss -tuln 2>/dev/null | grep -q ":$api_port"; then
        log_pass "API port $api_port bound"
    else
        log_warn "API port $api_port not bound"
    fi

    if netstat -tuln 2>/dev/null | grep -q ":$ui_port" || ss -tuln 2>/dev/null | grep -q ":$ui_port"; then
        log_pass "UI port $ui_port bound"
    else
        log_warn "UI port $ui_port not bound"
    fi

    if netstat -tuln 2>/dev/null | grep -q ":$grafana_port" || ss -tuln 2>/dev/null | grep -q ":$grafana_port"; then
        log_pass "Grafana port $grafana_port bound"
    else
        log_warn "Grafana port $grafana_port not bound (optional)"
    fi
}

# =============================================================================
# Volume Validation
# =============================================================================

validate_volumes() {
    log_section "Volume Configuration"

    local volumes=("db_data" "grafana_data")

    for volume in "${volumes[@]}"; do
        # Check if volume name contains project prefix
        if docker volume ls | grep -q "water-controller.*$volume\|wtc.*$volume\|$volume"; then
            log_pass "Volume '$volume' exists"
        else
            log_warn "Volume '$volume' not found"
        fi
    done
}

# =============================================================================
# Authentication Test
# =============================================================================

validate_auth() {
    log_section "Authentication Test"

    local api_port="${WTC_API_PORT:-8000}"
    local api_url="http://localhost:$api_port"

    # Try to login with default admin credentials
    local response=$(curl -s -X POST "$api_url/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username":"admin","password":"admin"}' 2>/dev/null)

    if echo "$response" | grep -q "token"; then
        log_pass "Authentication working (admin/admin)"
        log_warn "⚠️  DEFAULT PASSWORD IN USE - CHANGE IMMEDIATELY"
    else
        log_fail "Authentication not working"
        log_info "Response: $response"
    fi
}

# =============================================================================
# Main Validation Flow
# =============================================================================

main() {
    echo -e "${BLUE}"
    echo "═══════════════════════════════════════════════════"
    echo "  Water-Controller Deployment Validator"
    echo "═══════════════════════════════════════════════════"
    echo -e "${NC}"

    # Load environment variables if available
    if [[ -f "docker/.env" ]]; then
        export $(grep -v '^#' docker/.env | xargs)
        log_info "Loaded environment from docker/.env"
    fi

    # Run validations (continue on failure to show all issues)
    validate_docker || true
    validate_containers || true
    validate_database || true
    validate_api || true
    validate_ui || true
    validate_grafana || true
    validate_network || true
    validate_volumes || true
    validate_auth || true

    # Summary
    echo -e "\n${BLUE}═══ Validation Summary ═══${NC}"
    echo -e "${GREEN}Passed:${NC} ${#PASSED_CHECKS[@]}"
    echo -e "${YELLOW}Warnings:${NC} ${#WARNING_CHECKS[@]}"
    echo -e "${RED}Failed:${NC} ${#FAILED_CHECKS[@]}"

    if [[ ${#FAILED_CHECKS[@]} -gt 0 ]]; then
        echo -e "\n${RED}Failed checks:${NC}"
        for check in "${FAILED_CHECKS[@]}"; do
            echo -e "  ${RED}✗${NC} $check"
        done
        exit 1
    fi

    if [[ ${#WARNING_CHECKS[@]} -gt 0 ]]; then
        echo -e "\n${YELLOW}Warnings:${NC}"
        for check in "${WARNING_CHECKS[@]}"; do
            echo -e "  ${YELLOW}⚠${NC} $check"
        done
    fi

    echo -e "\n${GREEN}✓ Deployment validation complete${NC}"
    exit 0
}

main "$@"
