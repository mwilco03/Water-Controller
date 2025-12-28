#!/bin/bash
#
# Water Treatment Controller - UI Build Artifacts Validation
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This script validates that Next.js UI build artifacts exist and are valid
# before allowing the UI service to start.
#
# Exit codes:
#   0 - All required artifacts present and valid
#   1 - Missing or invalid artifacts (service should not start)
#   2 - Warning conditions (service can start but may be degraded)
#

set -euo pipefail

# =============================================================================
# Constants - Single Source of Truth for UI Build Paths
# =============================================================================

# Installation paths (must match systemd service and build.sh)
readonly UI_INSTALL_PATH="${WTC_UI_PATH:-/opt/water-controller/web/ui}"
readonly UI_STANDALONE_DIR="${UI_INSTALL_PATH}/.next/standalone"
readonly UI_STATIC_DIR="${UI_INSTALL_PATH}/.next/static"
readonly UI_PUBLIC_DIR="${UI_INSTALL_PATH}/public"
readonly UI_SERVER_JS="${UI_INSTALL_PATH}/server.js"

# Required directories for Next.js standalone server
readonly REQUIRED_DIRS=(
    "${UI_INSTALL_PATH}"
    "${UI_STANDALONE_DIR}"
    "${UI_STATIC_DIR}"
)

# Required files for Next.js to function
readonly REQUIRED_FILES=(
    "${UI_SERVER_JS}"
)

# Optional but expected files
readonly EXPECTED_FILES=(
    "${UI_INSTALL_PATH}/package.json"
    "${UI_INSTALL_PATH}/next.config.js"
)

# Minimum expected file counts (sanity check)
readonly MIN_STATIC_FILES=10      # Minimum JS/CSS files expected
readonly MIN_STANDALONE_FILES=5   # Minimum server files expected

# =============================================================================
# Logging Functions
# =============================================================================

log_info() {
    echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') - $*" >&2
}

log_warn() {
    echo "[WARN] $(date '+%Y-%m-%d %H:%M:%S') - $*" >&2
}

log_error() {
    echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') - $*" >&2
}

log_debug() {
    if [ "${WTC_DEBUG:-0}" = "1" ]; then
        echo "[DEBUG] $(date '+%Y-%m-%d %H:%M:%S') - $*" >&2
    fi
}

# =============================================================================
# Validation Functions
# =============================================================================

# Check if a directory exists and is not empty
check_directory() {
    local dir="$1"
    local description="${2:-directory}"

    if [ ! -d "$dir" ]; then
        log_error "Missing $description: $dir"
        return 1
    fi

    if [ -z "$(ls -A "$dir" 2>/dev/null)" ]; then
        log_error "Empty $description: $dir"
        return 1
    fi

    log_debug "Found $description: $dir"
    return 0
}

# Check if a file exists and is readable
check_file() {
    local file="$1"
    local description="${2:-file}"

    if [ ! -f "$file" ]; then
        log_error "Missing $description: $file"
        return 1
    fi

    if [ ! -r "$file" ]; then
        log_error "Unreadable $description: $file"
        return 1
    fi

    log_debug "Found $description: $file"
    return 0
}

# Count files in directory matching pattern
count_files() {
    local dir="$1"
    local pattern="${2:-*}"

    find "$dir" -type f -name "$pattern" 2>/dev/null | wc -l
}

# Validate Next.js static assets
validate_static_assets() {
    log_info "Validating static assets..."

    if ! check_directory "$UI_STATIC_DIR" "static assets directory"; then
        return 1
    fi

    # Check for JavaScript bundles
    local js_count
    js_count=$(count_files "$UI_STATIC_DIR" "*.js")

    if [ "$js_count" -lt "$MIN_STATIC_FILES" ]; then
        log_error "Insufficient JS bundles: found $js_count, expected at least $MIN_STATIC_FILES"
        return 1
    fi

    log_info "Found $js_count JavaScript bundles"

    # Check for CSS files (optional but expected)
    local css_count
    css_count=$(count_files "$UI_STATIC_DIR" "*.css")
    log_debug "Found $css_count CSS files"

    # Check for chunks directory (Next.js 14+ structure)
    if [ -d "${UI_STATIC_DIR}/chunks" ]; then
        local chunk_count
        chunk_count=$(count_files "${UI_STATIC_DIR}/chunks" "*.js")
        log_info "Found $chunk_count chunk files"
    fi

    return 0
}

# Validate Next.js standalone server
validate_standalone_server() {
    log_info "Validating standalone server..."

    # Check for standalone directory (optional, depends on build config)
    if [ -d "$UI_STANDALONE_DIR" ]; then
        if ! check_directory "$UI_STANDALONE_DIR" "standalone server directory"; then
            return 1
        fi

        local server_files
        server_files=$(count_files "$UI_STANDALONE_DIR" "*.js")

        if [ "$server_files" -lt "$MIN_STANDALONE_FILES" ]; then
            log_warn "Low standalone file count: $server_files files"
        fi

        log_info "Standalone server directory validated: $server_files files"
    else
        log_debug "No standalone directory (may be using development mode)"
    fi

    # Check for server.js entry point
    if ! check_file "$UI_SERVER_JS" "server entry point"; then
        # Fall back to checking for next binary
        if [ -x "${UI_INSTALL_PATH}/node_modules/.bin/next" ]; then
            log_warn "No server.js found, but next binary exists (development mode)"
            return 2
        fi
        return 1
    fi

    return 0
}

# Validate Node.js is available
validate_nodejs() {
    log_info "Validating Node.js runtime..."

    if ! command -v node >/dev/null 2>&1; then
        log_error "Node.js not found in PATH"
        return 1
    fi

    local node_version
    node_version=$(node --version 2>/dev/null)
    log_info "Node.js version: $node_version"

    # Check minimum Node.js version (18+)
    local major_version
    major_version=$(echo "$node_version" | sed 's/^v//' | cut -d. -f1)

    if [ "$major_version" -lt 18 ]; then
        log_error "Node.js version too old: $node_version (requires 18+)"
        return 1
    fi

    return 0
}

# Validate package.json exists and has correct structure
validate_package_json() {
    log_info "Validating package.json..."

    local pkg_file="${UI_INSTALL_PATH}/package.json"

    if ! check_file "$pkg_file" "package.json"; then
        return 1
    fi

    # Check for required fields using basic grep (no jq dependency)
    if ! grep -q '"name"' "$pkg_file" 2>/dev/null; then
        log_error "Invalid package.json: missing 'name' field"
        return 1
    fi

    if ! grep -q '"next"' "$pkg_file" 2>/dev/null; then
        log_error "Invalid package.json: missing 'next' dependency"
        return 1
    fi

    log_debug "package.json validated"
    return 0
}

# Write validation status to a marker file for health checks
write_status_marker() {
    local status="$1"
    local message="${2:-}"
    local marker_file="${UI_INSTALL_PATH}/.build-status"

    # Try to write status marker (may fail if read-only, that's OK)
    {
        echo "status=$status"
        echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "message=$message"
    } > "$marker_file" 2>/dev/null || true
}

# =============================================================================
# Main Validation
# =============================================================================

main() {
    local exit_code=0
    local warnings=0

    log_info "=============================================="
    log_info "Water Controller UI Build Validation"
    log_info "=============================================="
    log_info "UI Path: $UI_INSTALL_PATH"

    # Check Node.js first
    if ! validate_nodejs; then
        log_error "FAILED: Node.js validation"
        write_status_marker "error" "Node.js not available or too old"
        exit 1
    fi

    # Check required directories exist
    log_info "Checking required directories..."
    for dir in "${REQUIRED_DIRS[@]}"; do
        if ! check_directory "$dir" "required directory"; then
            exit_code=1
        fi
    done

    if [ $exit_code -ne 0 ]; then
        log_error "FAILED: Required directories missing"
        log_error ""
        log_error "The Next.js UI has not been built. Run:"
        log_error "  cd $UI_INSTALL_PATH && npm run build"
        log_error ""
        write_status_marker "error" "Required directories missing"
        exit 1
    fi

    # Validate static assets
    if ! validate_static_assets; then
        log_error "FAILED: Static assets validation"
        write_status_marker "error" "Static assets missing or incomplete"
        exit 1
    fi

    # Validate standalone server
    local server_result=0
    validate_standalone_server || server_result=$?

    if [ $server_result -eq 1 ]; then
        log_error "FAILED: Standalone server validation"
        write_status_marker "error" "Server entry point missing"
        exit 1
    elif [ $server_result -eq 2 ]; then
        warnings=$((warnings + 1))
    fi

    # Validate package.json (warning only)
    if ! validate_package_json; then
        log_warn "Package.json validation failed (non-fatal)"
        warnings=$((warnings + 1))
    fi

    # Check expected files (warnings only)
    for file in "${EXPECTED_FILES[@]}"; do
        if [ ! -f "$file" ]; then
            log_warn "Expected file missing: $file"
            warnings=$((warnings + 1))
        fi
    done

    # Summary
    log_info "=============================================="
    if [ $warnings -gt 0 ]; then
        log_warn "Validation completed with $warnings warning(s)"
        write_status_marker "warning" "$warnings warnings"
        exit 2
    else
        log_info "Validation PASSED - UI build artifacts are valid"
        write_status_marker "ok" "All checks passed"
        exit 0
    fi
}

# =============================================================================
# Quick Check Mode (for systemd ConditionPathExists alternative)
# =============================================================================

quick_check() {
    # Minimal check for systemd ExecStartPre
    # Returns 0 only if essential files exist

    [ -d "$UI_INSTALL_PATH" ] || exit 1
    [ -d "$UI_STATIC_DIR" ] || exit 1
    [ -f "$UI_SERVER_JS" ] || exit 1

    # Count JS files quickly
    local js_count
    js_count=$(find "$UI_STATIC_DIR" -name "*.js" -type f 2>/dev/null | head -20 | wc -l)
    [ "$js_count" -ge 5 ] || exit 1

    exit 0
}

# =============================================================================
# Script Entry Point
# =============================================================================

case "${1:-}" in
    --quick)
        quick_check
        ;;
    --help|-h)
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Validate Next.js UI build artifacts before service startup."
        echo ""
        echo "Options:"
        echo "  --quick     Minimal check (for systemd ExecStartPre)"
        echo "  --help, -h  Show this help message"
        echo ""
        echo "Exit codes:"
        echo "  0  All required artifacts present and valid"
        echo "  1  Missing or invalid artifacts (service should not start)"
        echo "  2  Warning conditions (service can start but may be degraded)"
        echo ""
        echo "Environment variables:"
        echo "  WTC_UI_PATH   Override UI installation path"
        echo "  WTC_DEBUG     Set to 1 for debug output"
        ;;
    *)
        main
        ;;
esac
