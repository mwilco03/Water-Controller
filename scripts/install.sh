#!/bin/bash
#
# Water Treatment Controller - Installation Script
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"

# Source common utilities
source "$SCRIPT_DIR/lib/common.sh"

# =============================================================================
# Parse Arguments
# =============================================================================

SKIP_BUILD=false
SKIP_SERVICES=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build) SKIP_BUILD=true; shift ;;
        --skip-services) SKIP_SERVICES=true; shift ;;
        --help)
            echo "Usage: $0 [--skip-build] [--skip-services]"
            exit 0
            ;;
        *) shift ;;
    esac
done

# =============================================================================
# Main Installation
# =============================================================================

log_header "Water Treatment Controller Installation"

# Check root privileges
require_root

# Create service user
create_service_user

# Create directories
create_directories

# Set ownership
set_permissions

# Build if not skipped
if [ "$SKIP_BUILD" = false ]; then
    log_info "Building controller..."
    cd "$SOURCE_DIR"
    mkdir -p build && cd build
    cmake -DCMAKE_BUILD_TYPE=Release ..
    make -j$(nproc)

    # Install binaries
    log_info "Installing binaries..."
    cp water_treat_controller "$INSTALL_DIR/bin/"
    cp lib*.so "$INSTALL_DIR/lib/" 2>/dev/null || true
fi

# Install web components
log_info "Installing web components..."
cp -r "$SOURCE_DIR/web" "$INSTALL_DIR/"

# Setup Python virtual environment
setup_python_venv "$INSTALL_DIR/web/api/requirements.txt"

# Build Node.js UI
build_nodejs_ui

# Create default configuration files
create_default_config

# Install systemd services
if [ "$SKIP_SERVICES" = false ]; then
    install_systemd_services "$SOURCE_DIR"
    enable_services
    log_info "Services installed. Start with: systemctl start water-controller"
fi

# Create management script
create_management_script

# Print completion message
print_completion_message
