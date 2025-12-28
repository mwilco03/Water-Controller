#!/bin/bash
#
# Water Treatment Controller - Path Configuration
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Single source of truth for all installation and build paths.
# This file is sourced by build scripts, validation scripts, and systemd units.
#
# IMPORTANT: If you change paths here, update:
#   - systemd/*.service files
#   - web/api/app/core/config.py
#   - Dockerfile configurations
#

# Prevent multiple sourcing
if [ -n "$_WTC_PATHS_LOADED" ]; then
    return 0
fi
_WTC_PATHS_LOADED=1

# =============================================================================
# Base Installation Paths
# =============================================================================

# Root installation directory
readonly WTC_INSTALL_BASE="${WTC_INSTALL_BASE:-/opt/water-controller}"

# Configuration directory
readonly WTC_CONFIG_DIR="${WTC_CONFIG_DIR:-/etc/water-controller}"

# Runtime state directory
readonly WTC_STATE_DIR="${WTC_STATE_DIR:-/var/lib/water-controller}"

# Log directory
readonly WTC_LOG_DIR="${WTC_LOG_DIR:-/var/log/water-controller}"

# =============================================================================
# Python Backend Paths
# =============================================================================

# Python virtual environment
readonly WTC_VENV_PATH="${WTC_VENV_PATH:-${WTC_INSTALL_BASE}/venv}"

# Backend source directory
readonly WTC_API_PATH="${WTC_API_PATH:-${WTC_INSTALL_BASE}/web/api}"

# Backend entry point
readonly WTC_API_MAIN="${WTC_API_MAIN:-${WTC_API_PATH}/main.py}"

# SQLite database location (if not using PostgreSQL)
readonly WTC_DB_PATH="${WTC_DB_PATH:-${WTC_STATE_DIR}/water_controller.db}"

# =============================================================================
# Frontend (Next.js) Paths - Critical for UI Build Validation
# =============================================================================

# UI source/installation directory
readonly WTC_UI_PATH="${WTC_UI_PATH:-${WTC_INSTALL_BASE}/web/ui}"

# Next.js build output root
readonly WTC_UI_NEXT_DIR="${WTC_UI_NEXT_DIR:-${WTC_UI_PATH}/.next}"

# Next.js standalone server (production mode)
readonly WTC_UI_STANDALONE_DIR="${WTC_UI_STANDALONE_DIR:-${WTC_UI_NEXT_DIR}/standalone}"

# Next.js static assets (JS bundles, CSS, etc.)
readonly WTC_UI_STATIC_DIR="${WTC_UI_STATIC_DIR:-${WTC_UI_NEXT_DIR}/static}"

# Next.js server entry point (copied from standalone or custom)
readonly WTC_UI_SERVER_JS="${WTC_UI_SERVER_JS:-${WTC_UI_PATH}/server.js}"

# Public assets directory
readonly WTC_UI_PUBLIC_DIR="${WTC_UI_PUBLIC_DIR:-${WTC_UI_PATH}/public}"

# =============================================================================
# Binary Paths (PROFINET Controller)
# =============================================================================

# Compiled binary directory
readonly WTC_BIN_DIR="${WTC_BIN_DIR:-${WTC_INSTALL_BASE}/bin}"

# Main controller binary
readonly WTC_CONTROLLER_BIN="${WTC_CONTROLLER_BIN:-${WTC_BIN_DIR}/water_treat_controller}"

# =============================================================================
# Script Paths
# =============================================================================

# Scripts library directory
readonly WTC_SCRIPTS_LIB="${WTC_SCRIPTS_LIB:-${WTC_INSTALL_BASE}/scripts/lib}"

# UI build validation script
readonly WTC_UI_BUILD_CHECK="${WTC_UI_BUILD_CHECK:-${WTC_SCRIPTS_LIB}/ui_build_check.sh}"

# =============================================================================
# Service Ports
# =============================================================================

# FastAPI backend port
readonly WTC_API_PORT="${WTC_API_PORT:-8080}"

# Next.js UI port
readonly WTC_UI_PORT="${WTC_UI_PORT:-3000}"

# Modbus gateway port
readonly WTC_MODBUS_PORT="${WTC_MODBUS_PORT:-502}"

# =============================================================================
# Validation Functions
# =============================================================================

# Check if UI build artifacts exist
# Returns: 0 if valid, 1 if missing/invalid
wtc_check_ui_build() {
    [ -d "$WTC_UI_STATIC_DIR" ] && \
    [ -f "$WTC_UI_SERVER_JS" ] && \
    [ "$(find "$WTC_UI_STATIC_DIR" -name "*.js" -type f 2>/dev/null | wc -l)" -ge 5 ]
}

# Check if API is ready
# Returns: 0 if ready, 1 if not
wtc_check_api_ready() {
    [ -f "$WTC_API_MAIN" ] && \
    [ -x "$WTC_VENV_PATH/bin/uvicorn" ]
}

# Check if controller binary exists
# Returns: 0 if exists, 1 if not
wtc_check_controller_bin() {
    [ -x "$WTC_CONTROLLER_BIN" ]
}

# =============================================================================
# Export for Subprocesses
# =============================================================================

export WTC_INSTALL_BASE
export WTC_CONFIG_DIR
export WTC_STATE_DIR
export WTC_LOG_DIR
export WTC_VENV_PATH
export WTC_API_PATH
export WTC_API_MAIN
export WTC_DB_PATH
export WTC_UI_PATH
export WTC_UI_NEXT_DIR
export WTC_UI_STANDALONE_DIR
export WTC_UI_STATIC_DIR
export WTC_UI_SERVER_JS
export WTC_UI_PUBLIC_DIR
export WTC_BIN_DIR
export WTC_CONTROLLER_BIN
export WTC_SCRIPTS_LIB
export WTC_UI_BUILD_CHECK
export WTC_API_PORT
export WTC_UI_PORT
export WTC_MODBUS_PORT

# =============================================================================
# Print Configuration (when run directly)
# =============================================================================

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    echo "Water Controller Path Configuration"
    echo "===================================="
    echo ""
    echo "Base Paths:"
    echo "  Install Base:    $WTC_INSTALL_BASE"
    echo "  Config Dir:      $WTC_CONFIG_DIR"
    echo "  State Dir:       $WTC_STATE_DIR"
    echo "  Log Dir:         $WTC_LOG_DIR"
    echo ""
    echo "Backend (Python/FastAPI):"
    echo "  Venv Path:       $WTC_VENV_PATH"
    echo "  API Path:        $WTC_API_PATH"
    echo "  API Main:        $WTC_API_MAIN"
    echo "  Database:        $WTC_DB_PATH"
    echo ""
    echo "Frontend (Next.js):"
    echo "  UI Path:         $WTC_UI_PATH"
    echo "  Next.js Dir:     $WTC_UI_NEXT_DIR"
    echo "  Standalone Dir:  $WTC_UI_STANDALONE_DIR"
    echo "  Static Dir:      $WTC_UI_STATIC_DIR"
    echo "  Server JS:       $WTC_UI_SERVER_JS"
    echo "  Public Dir:      $WTC_UI_PUBLIC_DIR"
    echo ""
    echo "Binaries:"
    echo "  Bin Dir:         $WTC_BIN_DIR"
    echo "  Controller:      $WTC_CONTROLLER_BIN"
    echo ""
    echo "Ports:"
    echo "  API:             $WTC_API_PORT"
    echo "  UI:              $WTC_UI_PORT"
    echo "  Modbus:          $WTC_MODBUS_PORT"
    echo ""
    echo "Validation Status:"
    if wtc_check_ui_build; then
        echo "  UI Build:        OK"
    else
        echo "  UI Build:        MISSING"
    fi
    if wtc_check_api_ready; then
        echo "  API Ready:       OK"
    else
        echo "  API Ready:       NOT READY"
    fi
    if wtc_check_controller_bin; then
        echo "  Controller:      OK"
    else
        echo "  Controller:      MISSING"
    fi
fi
