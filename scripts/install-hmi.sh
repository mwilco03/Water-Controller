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

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "=========================================="
echo "  Water Treatment Controller HMI"
echo "  Installation Script"
echo "=========================================="
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: Please run as root (sudo ./install-hmi.sh)${NC}"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Installation paths
INSTALL_DIR="/opt/water-controller"
DATA_DIR="/var/lib/water-controller"
CONFIG_DIR="/etc/water-controller"
LOG_DIR="/var/log/water-controller"
BIN_DIR="/usr/local/bin"
SYSTEMD_DIR="/etc/systemd/system"

# Service user
SERVICE_USER="water-controller"
SERVICE_GROUP="water-controller"

echo -e "${YELLOW}Step 1: Creating service user and group...${NC}"
if ! getent group "$SERVICE_GROUP" > /dev/null 2>&1; then
    groupadd --system "$SERVICE_GROUP"
    echo "  Created group: $SERVICE_GROUP"
else
    echo "  Group already exists: $SERVICE_GROUP"
fi

if ! getent passwd "$SERVICE_USER" > /dev/null 2>&1; then
    useradd --system --gid "$SERVICE_GROUP" --home-dir "$DATA_DIR" --shell /sbin/nologin "$SERVICE_USER"
    echo "  Created user: $SERVICE_USER"
else
    echo "  User already exists: $SERVICE_USER"
fi

echo -e "${YELLOW}Step 2: Creating directories...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$DATA_DIR/historian"
mkdir -p "$DATA_DIR/backups"
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"
echo "  Created: $INSTALL_DIR"
echo "  Created: $DATA_DIR"
echo "  Created: $CONFIG_DIR"
echo "  Created: $LOG_DIR"

echo -e "${YELLOW}Step 3: Copying application files...${NC}"
# Copy web application
cp -r "$PROJECT_DIR/web" "$INSTALL_DIR/"
echo "  Copied: web application"

# Copy scripts
cp -r "$PROJECT_DIR/scripts" "$INSTALL_DIR/"
echo "  Copied: scripts"

# Copy startup script to /usr/local/bin
cp "$SCRIPT_DIR/water-controller" "$BIN_DIR/water-controller"
chmod +x "$BIN_DIR/water-controller"
echo "  Installed: $BIN_DIR/water-controller"

echo -e "${YELLOW}Step 4: Setting up Python virtual environment...${NC}"
VENV_DIR="$INSTALL_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "  Created virtual environment"
fi

# Install Python dependencies
if [ -f "$INSTALL_DIR/web/api/requirements.txt" ]; then
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/web/api/requirements.txt"
    echo "  Installed Python dependencies"
else
    # Install minimum requirements
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install fastapi uvicorn[standard] pydantic python-jose[cryptography] passlib[bcrypt] psutil
    echo "  Installed minimum Python dependencies"
fi

echo -e "${YELLOW}Step 5: Building UI...${NC}"
if [ -d "$INSTALL_DIR/web/ui" ]; then
    cd "$INSTALL_DIR/web/ui"
    if command -v npm &> /dev/null; then
        npm install --production=false
        npm run build
        echo "  Built UI application"
    else
        echo -e "${YELLOW}  WARNING: npm not found, skipping UI build${NC}"
        echo "  Install Node.js and run 'npm run build' manually"
    fi
    cd - > /dev/null
fi

echo -e "${YELLOW}Step 6: Creating default configuration...${NC}"
if [ ! -f "$CONFIG_DIR/environment" ]; then
    cat > "$CONFIG_DIR/environment" << EOF
# Water Treatment Controller HMI Configuration
DATA_DIR=$DATA_DIR
WEB_PORT=8080
UI_PORT=3000
LOG_LEVEL=INFO
EOF
    echo "  Created: $CONFIG_DIR/environment"
else
    echo "  Configuration already exists"
fi

echo -e "${YELLOW}Step 7: Setting permissions...${NC}"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$CONFIG_DIR"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
chmod 755 "$INSTALL_DIR"
chmod 755 "$DATA_DIR"
chmod 750 "$CONFIG_DIR"
chmod 755 "$LOG_DIR"
echo "  Set ownership and permissions"

echo -e "${YELLOW}Step 8: Installing systemd service...${NC}"
cp "$PROJECT_DIR/systemd/water-controller-hmi.service" "$SYSTEMD_DIR/"
systemctl daemon-reload
echo "  Installed: $SYSTEMD_DIR/water-controller-hmi.service"

echo -e "${YELLOW}Step 9: Enabling service...${NC}"
systemctl enable water-controller-hmi
echo "  Enabled: water-controller-hmi.service"

echo ""
echo -e "${GREEN}=========================================="
echo "  Installation Complete!"
echo "==========================================${NC}"
echo ""
echo "To start the HMI service:"
echo "  sudo systemctl start water-controller-hmi"
echo ""
echo "To check service status:"
echo "  sudo systemctl status water-controller-hmi"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u water-controller-hmi -f"
echo ""
echo "Access the HMI at:"
echo "  http://localhost:8080"
echo ""
echo "Default credentials:"
echo "  Username: admin"
echo "  Password: H2OhYeah!"
echo ""
echo -e "${YELLOW}IMPORTANT: First login will initialize the database.${NC}"
echo ""
