#!/bin/bash
#
# Water Treatment Controller HMI Installation Script
#
# This script installs the Water Treatment Controller HMI as a systemd service.
# Run with sudo: sudo ./install-hmi.sh
#
# After installation:
#   sudo systemctl start water-controller-hmi
#   Access HMI at http://localhost:8080
#

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Source common utilities
source "$SCRIPT_DIR/lib/common.sh"

# =============================================================================
# Main Installation
# =============================================================================

log_header "Water Treatment Controller HMI Installation"

# Check root privileges
require_root

# Create service user
log_step "Step 1: Creating service user and group..."
create_service_user

# Create directories
log_step "Step 2: Creating directories..."
create_directories
echo "  Created: $INSTALL_DIR"
echo "  Created: $DATA_DIR"
echo "  Created: $CONFIG_DIR"
echo "  Created: $LOG_DIR"

# Copy application files
log_step "Step 3: Copying application files..."
cp -r "$PROJECT_DIR/web" "$INSTALL_DIR/"
echo "  Copied: web application"

cp -r "$PROJECT_DIR/scripts" "$INSTALL_DIR/"
echo "  Copied: scripts"

# Copy startup script to /usr/local/bin if it exists
if [ -f "$SCRIPT_DIR/water-controller" ]; then
    cp "$SCRIPT_DIR/water-controller" "$BIN_DIR/water-controller"
    chmod +x "$BIN_DIR/water-controller"
    echo "  Installed: $BIN_DIR/water-controller"
fi

# Setup Python virtual environment
log_step "Step 4: Setting up Python virtual environment..."
setup_python_venv "$INSTALL_DIR/web/api/requirements.txt"

# Build UI
log_step "Step 5: Building UI..."
if ! build_nodejs_ui; then
    log_error "HMI build failed. Installation cannot continue."
    log_error "Fix the errors above and run the installer again."
    exit 1
fi

# Create default configuration
log_step "Step 6: Creating default configuration..."
if [ ! -f "$CONFIG_DIR/environment" ]; then
    cat > "$CONFIG_DIR/environment" << EOF
# Water Treatment Controller HMI Configuration
DATA_DIR=$DATA_DIR
API_PORT=8000
UI_PORT=8080
LOG_LEVEL=INFO
WT_LOG_LEVEL=INFO
WT_CONFIG_DIR=$CONFIG_DIR
WT_DATA_DIR=$DATA_DIR
NODE_ENV=production
PYTHONUNBUFFERED=1
EOF
    echo "  Created: $CONFIG_DIR/environment"
else
    echo "  Configuration already exists"
fi

# Set permissions
log_step "Step 7: Setting permissions..."
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
set_permissions
echo "  Set ownership and permissions"

# Install systemd service
log_step "Step 8: Installing systemd service..."
cp "$PROJECT_DIR/systemd/water-controller-hmi.service" "$SYSTEMD_DIR/"
systemctl daemon-reload
echo "  Installed: $SYSTEMD_DIR/water-controller-hmi.service"

# Enable service
log_step "Step 9: Enabling service..."
systemctl enable water-controller-hmi
echo "  Enabled: water-controller-hmi.service"

# Start service
log_step "Step 10: Starting service..."
systemctl start water-controller-hmi
sleep 3

# Verify service is running
if systemctl is-active --quiet water-controller-hmi; then
    echo "  Service started successfully"
    echo "  Status: $(systemctl is-active water-controller-hmi)"
else
    log_warn "Service may have failed to start. Check logs:"
    echo "    journalctl -u water-controller-hmi -n 50"
fi

# Print completion message
print_hmi_completion_message
