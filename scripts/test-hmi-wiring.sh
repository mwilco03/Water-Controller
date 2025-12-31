#!/usr/bin/env bash
#
# HMI Wiring Test Battery
#
# Runs comprehensive end-to-end tests to validate the wiring between
# the Next.js frontend and FastAPI backend.
#
# Usage: ./scripts/test-hmi-wiring.sh [--quick|--full]
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
WEB_API_DIR="$PROJECT_ROOT/web/api"
WEB_UI_DIR="$PROJECT_ROOT/web/ui"

# Test ports (non-standard to avoid conflicts)
API_PORT="${TEST_API_PORT:-18000}"
UI_PORT="${TEST_UI_PORT:-18080}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# PIDs for cleanup
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo -e "\n${BLUE}Cleaning up...${NC}"
    [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
    [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
    wait 2>/dev/null || true
}

trap cleanup EXIT

log_test() {
    local status="$1"
    local name="$2"
    local detail="${3:-}"

    case "$status" in
        PASS)
            echo -e "  ${GREEN}✓${NC} $name"
            ((TESTS_PASSED++))
            ;;
        FAIL)
            echo -e "  ${RED}✗${NC} $name"
            [[ -n "$detail" ]] && echo -e "    ${RED}→ $detail${NC}"
            ((TESTS_FAILED++))
            ;;
        SKIP)
            echo -e "  ${YELLOW}○${NC} $name (skipped: $detail)"
            ((TESTS_SKIPPED++))
            ;;
    esac
}

wait_for_port() {
    local port=$1
    local timeout=${2:-30}
    local start=$(date +%s)

    while ! nc -z localhost "$port" 2>/dev/null; do
        if (( $(date +%s) - start > timeout )); then
            return 1
        fi
        sleep 0.5
    done
    return 0
}

wait_for_http() {
    local url=$1
    local timeout=${2:-30}
    local start=$(date +%s)

    while true; do
        if curl -sf "$url" >/dev/null 2>&1; then
            return 0
        fi
        if (( $(date +%s) - start > timeout )); then
            return 1
        fi
        sleep 0.5
    done
}

# =============================================================================
# Test Categories
# =============================================================================

test_prerequisites() {
    echo -e "\n${BLUE}=== Prerequisites ===${NC}"

    # Check Node.js
    if command -v node &>/dev/null; then
        log_test PASS "Node.js installed ($(node --version))"
    else
        log_test FAIL "Node.js not installed"
        return 1
    fi

    # Check npm
    if command -v npm &>/dev/null; then
        log_test PASS "npm installed ($(npm --version))"
    else
        log_test FAIL "npm not installed"
        return 1
    fi

    # Check Python
    if command -v python3 &>/dev/null; then
        log_test PASS "Python installed ($(python3 --version))"
    else
        log_test FAIL "Python not installed"
        return 1
    fi

    # Check uvicorn
    if python3 -c "import uvicorn" 2>/dev/null; then
        log_test PASS "uvicorn installed"
    else
        log_test FAIL "uvicorn not installed" "pip install uvicorn"
        return 1
    fi

    # Check httpx for tests
    if python3 -c "import httpx" 2>/dev/null; then
        log_test PASS "httpx installed"
    else
        log_test SKIP "httpx not installed" "pip install httpx"
    fi

    # Check frontend dependencies
    if [[ -d "$WEB_UI_DIR/node_modules" ]]; then
        log_test PASS "Frontend node_modules exists"
    else
        log_test FAIL "Frontend node_modules missing" "cd web/ui && npm install"
        return 1
    fi

    # Check for port conflicts
    if ! nc -z localhost "$API_PORT" 2>/dev/null; then
        log_test PASS "Port $API_PORT available for API"
    else
        log_test FAIL "Port $API_PORT in use"
        return 1
    fi

    if ! nc -z localhost "$UI_PORT" 2>/dev/null; then
        log_test PASS "Port $UI_PORT available for UI"
    else
        log_test FAIL "Port $UI_PORT in use"
        return 1
    fi
}

test_frontend_build() {
    echo -e "\n${BLUE}=== Frontend Build Tests ===${NC}"

    cd "$WEB_UI_DIR"

    # TypeScript compilation
    echo -e "  ${YELLOW}Running TypeScript check...${NC}"
    if npx tsc --noEmit 2>/dev/null; then
        log_test PASS "TypeScript compilation"
    else
        log_test FAIL "TypeScript compilation" "npx tsc --noEmit for errors"
    fi

    # ESLint check
    echo -e "  ${YELLOW}Running ESLint...${NC}"
    lint_output=$(npm run lint 2>&1) || true
    if echo "$lint_output" | grep -qi "error"; then
        log_test FAIL "ESLint check" "Errors found"
    else
        log_test PASS "ESLint check (warnings OK)"
    fi

    # Next.js build
    echo -e "  ${YELLOW}Running Next.js build (this may take a moment)...${NC}"
    if npm run build >/dev/null 2>&1; then
        log_test PASS "Next.js production build"
    else
        log_test FAIL "Next.js production build" "npm run build for errors"
    fi

    # Check .next directory
    if [[ -d "$WEB_UI_DIR/.next" ]]; then
        log_test PASS ".next build directory exists"
    else
        log_test FAIL ".next build directory missing"
    fi

    cd "$PROJECT_ROOT"
}

test_backend_startup() {
    echo -e "\n${BLUE}=== Backend Startup Tests ===${NC}"

    cd "$WEB_API_DIR"

    echo -e "  ${YELLOW}Starting backend on port $API_PORT...${NC}"

    WTC_STARTUP_MODE=development \
    DATABASE_URL=sqlite:///:memory: \
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT" &
    BACKEND_PID=$!

    if wait_for_port "$API_PORT" 15; then
        log_test PASS "Backend started on port $API_PORT"
    else
        log_test FAIL "Backend failed to start"
        kill "$BACKEND_PID" 2>/dev/null || true
        BACKEND_PID=""
        return 1
    fi

    # Test health endpoint
    sleep 1
    if curl -sf "http://localhost:$API_PORT/health" >/dev/null; then
        log_test PASS "Health endpoint responds"
    else
        log_test FAIL "Health endpoint not responding"
    fi

    cd "$PROJECT_ROOT"
}

test_backend_endpoints() {
    echo -e "\n${BLUE}=== Backend API Endpoint Tests ===${NC}"

    local base="http://localhost:$API_PORT"

    # /health
    if curl -sf "$base/health" | grep -q "status"; then
        log_test PASS "GET /health returns status"
    else
        log_test FAIL "GET /health"
    fi

    # /api/openapi.json (FastAPI default path)
    local openapi_response
    openapi_response=$(curl -sf "$base/api/openapi.json" 2>/dev/null) || openapi_response=""
    if echo "$openapi_response" | grep -q "openapi"; then
        log_test PASS "GET /api/openapi.json returns OpenAPI spec"
    elif echo "$openapi_response" | grep -q "paths"; then
        log_test PASS "GET /api/openapi.json returns API spec"
    else
        log_test FAIL "GET /api/openapi.json"
    fi

    # /api/v1/rtus
    local rtus_response
    rtus_response=$(curl -sf "$base/api/v1/rtus" 2>/dev/null) || rtus_response=""
    if [[ -n "$rtus_response" ]]; then
        log_test PASS "GET /api/v1/rtus returns data"
    else
        log_test FAIL "GET /api/v1/rtus"
    fi

    # /api/v1/alarms
    local alarms_response
    alarms_response=$(curl -sf "$base/api/v1/alarms" 2>/dev/null) || alarms_response=""
    if [[ -n "$alarms_response" ]]; then
        log_test PASS "GET /api/v1/alarms returns data"
    else
        log_test FAIL "GET /api/v1/alarms"
    fi

    # /api/v1/auth/login (test validation)
    local auth_code
    auth_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$base/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username":"invalid","password":"invalid"}')
    if [[ "$auth_code" == "401" || "$auth_code" == "403" ]]; then
        log_test PASS "POST /api/v1/auth/login rejects invalid credentials"
    else
        log_test FAIL "POST /api/v1/auth/login returned $auth_code"
    fi

    # 404 handling
    local not_found_code
    not_found_code=$(curl -s -o /dev/null -w "%{http_code}" "$base/api/v1/nonexistent")
    if [[ "$not_found_code" == "404" ]]; then
        log_test PASS "404 for unknown endpoints"
    else
        log_test FAIL "Expected 404, got $not_found_code"
    fi
}

test_frontend_startup() {
    echo -e "\n${BLUE}=== Frontend Startup Tests ===${NC}"

    cd "$WEB_UI_DIR"

    echo -e "  ${YELLOW}Starting frontend on port $UI_PORT...${NC}"

    API_URL="http://localhost:$API_PORT" \
    npm run dev -- -p "$UI_PORT" &
    FRONTEND_PID=$!

    if wait_for_port "$UI_PORT" 30; then
        log_test PASS "Frontend started on port $UI_PORT"
    else
        log_test FAIL "Frontend failed to start"
        kill "$FRONTEND_PID" 2>/dev/null || true
        FRONTEND_PID=""
        return 1
    fi

    sleep 3  # Let Next.js compile

    cd "$PROJECT_ROOT"
}

test_frontend_serves() {
    echo -e "\n${BLUE}=== Frontend Serving Tests ===${NC}"

    local base="http://localhost:$UI_PORT"

    # Root page
    local root_response
    root_response=$(curl -sf "$base/" 2>/dev/null) || root_response=""
    if echo "$root_response" | grep -qi "html"; then
        log_test PASS "GET / returns HTML"
    else
        log_test FAIL "GET / does not return HTML"
    fi

    # Contains Next.js markers
    if echo "$root_response" | grep -qi "_next\|__NEXT"; then
        log_test PASS "HTML contains Next.js references"
    else
        log_test FAIL "HTML missing Next.js references"
    fi

    # Content type
    local content_type
    content_type=$(curl -sI "$base/" | grep -i "content-type" | head -1)
    if echo "$content_type" | grep -qi "text/html"; then
        log_test PASS "Content-Type is text/html"
    else
        log_test FAIL "Content-Type: $content_type"
    fi
}

test_frontend_to_backend() {
    echo -e "\n${BLUE}=== Frontend-to-Backend Wiring Tests ===${NC}"

    local ui_base="http://localhost:$UI_PORT"
    local api_base="http://localhost:$API_PORT"

    # Test API proxy through frontend
    # Note: next.config.js should proxy /api/* to API_URL
    local proxy_response
    proxy_response=$(curl -sf "$ui_base/api/v1/rtus" 2>/dev/null) || proxy_response=""
    if [[ -n "$proxy_response" ]]; then
        log_test PASS "Frontend proxies /api/v1/rtus to backend"
    else
        # Try direct backend to verify it's just the proxy
        if curl -sf "$api_base/api/v1/rtus" >/dev/null; then
            log_test FAIL "Backend works but frontend proxy fails"
        else
            log_test FAIL "Both frontend and backend /api/v1/rtus fail"
        fi
    fi

    # Verify response consistency
    local direct_response
    direct_response=$(curl -sf "$api_base/api/v1/rtus" 2>/dev/null) || direct_response=""
    if [[ "$proxy_response" == "$direct_response" ]]; then
        log_test PASS "Proxied response matches direct response"
    elif [[ -n "$proxy_response" && -n "$direct_response" ]]; then
        log_test PASS "Both endpoints return data (format may differ)"
    else
        log_test SKIP "Cannot compare responses" "one or both failed"
    fi
}

test_websocket() {
    echo -e "\n${BLUE}=== WebSocket Tests ===${NC}"

    # Check if websocket endpoint is documented
    local openapi
    openapi=$(curl -sf "http://localhost:$API_PORT/api/openapi.json" 2>/dev/null) || openapi=""
    if echo "$openapi" | grep -qi "ws"; then
        log_test PASS "WebSocket endpoint documented in OpenAPI"
    else
        log_test SKIP "WebSocket not found in OpenAPI" "may be undocumented"
    fi

    # Try to connect with websocat if available
    if command -v websocat &>/dev/null; then
        if timeout 2 websocat "ws://localhost:$API_PORT/api/v1/ws/live" </dev/null >/dev/null 2>&1; then
            log_test PASS "WebSocket connection successful"
        else
            log_test FAIL "WebSocket connection failed"
        fi
    else
        log_test SKIP "WebSocket connection test" "websocat not installed"
    fi
}

print_summary() {
    echo -e "\n${BLUE}=== Test Summary ===${NC}"
    echo -e "  ${GREEN}Passed:${NC}  $TESTS_PASSED"
    echo -e "  ${RED}Failed:${NC}  $TESTS_FAILED"
    echo -e "  ${YELLOW}Skipped:${NC} $TESTS_SKIPPED"
    echo ""

    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}All tests passed!${NC}"
        return 0
    else
        echo -e "${RED}Some tests failed.${NC}"
        return 1
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    local mode="${1:-full}"

    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║         HMI Wiring End-to-End Test Battery                 ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Project: $PROJECT_ROOT"
    echo "API Port: $API_PORT"
    echo "UI Port: $UI_PORT"
    echo "Mode: $mode"

    test_prerequisites || exit 1

    if [[ "$mode" == "--quick" ]]; then
        # Quick mode: just check backend starts and basic endpoints
        test_backend_startup || exit 1
        test_backend_endpoints
        print_summary
        exit $?
    fi

    # Full mode
    test_frontend_build
    test_backend_startup || exit 1
    test_backend_endpoints
    test_frontend_startup || exit 1
    test_frontend_serves
    test_frontend_to_backend
    test_websocket

    print_summary
}

main "$@"
