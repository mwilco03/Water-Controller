#!/bin/bash
# =============================================================================
# Water-Controller Remove Script
# =============================================================================
# Safely removes Water-Controller from the system.
#
# Features:
# - Stops and disables all services
# - Optionally preserves configuration
# - Creates backup before removal
# - Removes systemd unit files
# - Cleans up all installation artifacts
#
# Usage:
#   ./remove.sh [options]
#   ./remove.sh --keep-config
#   ./remove.sh --yes
#
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
# =============================================================================

set -euo pipefail

# =============================================================================
# Constants
# =============================================================================

readonly REMOVE_VERSION="1.0.0"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Paths
readonly INSTALL_BASE="/opt/water-controller"
readonly CONFIG_DIR="/etc/water-controller"
readonly DATA_DIR="/var/lib/water-controller"
readonly LOG_DIR="/var/log/water-controller"
readonly BACKUP_DIR="/var/backups"

# Services to remove
readonly SERVICES=(
    "water-controller"
    "water-controller-api"
    "water-controller-ui"
    "water-controller-frontend"
    "water-controller-hmi"
)

# Colors
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# =============================================================================
# Logging
# =============================================================================

log_info() { echo -e "${GREEN}[INFO]${NC} $1" >&2; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1" >&2; }

# =============================================================================
# Global Variables
# =============================================================================

KEEP_CONFIG="false"
CONFIRM_YES="false"
DRY_RUN="false"
FORCE="false"

# =============================================================================
# Detection Functions
# =============================================================================

# Check if Water-Controller is installed
is_installed() {
    [[ -d "$INSTALL_BASE" ]] || \
    [[ -d "$CONFIG_DIR" ]] || \
    [[ -d "$DATA_DIR" ]] || \
    systemctl list-unit-files "water-controller*.service" &>/dev/null
}

# Get installed version
get_installed_version() {
    local version_file="$INSTALL_BASE/.version"

    if [[ -f "$version_file" ]]; then
        if command -v jq &>/dev/null; then
            jq -r '.version // "unknown"' "$version_file" 2>/dev/null
        else
            grep -oP '"version"\s*:\s*"\K[^"]+' "$version_file" 2>/dev/null || echo "unknown"
        fi
    else
        echo "unknown"
    fi
}

# List what will be removed
list_removal_targets() {
    echo ""
    echo "The following will be removed:"
    echo "------------------------------"

    # Installation directory
    if [[ -d "$INSTALL_BASE" ]]; then
        local size
        size=$(du -sh "$INSTALL_BASE" 2>/dev/null | awk '{print $1}')
        echo "  [DIR]  $INSTALL_BASE ($size)"
    fi

    # Config directory
    if [[ -d "$CONFIG_DIR" ]]; then
        if [[ "$KEEP_CONFIG" == "true" ]]; then
            echo "  [DIR]  $CONFIG_DIR (WILL BE PRESERVED)"
        else
            local size
            size=$(du -sh "$CONFIG_DIR" 2>/dev/null | awk '{print $1}')
            echo "  [DIR]  $CONFIG_DIR ($size)"
        fi
    fi

    # Data directory
    if [[ -d "$DATA_DIR" ]]; then
        if [[ "$KEEP_CONFIG" == "true" ]]; then
            echo "  [DIR]  $DATA_DIR (WILL BE PRESERVED)"
        else
            local size
            size=$(du -sh "$DATA_DIR" 2>/dev/null | awk '{print $1}')
            echo "  [DIR]  $DATA_DIR ($size)"
        fi
    fi

    # Log directory
    if [[ -d "$LOG_DIR" ]]; then
        local size
        size=$(du -sh "$LOG_DIR" 2>/dev/null | awk '{print $1}')
        echo "  [DIR]  $LOG_DIR ($size)"
    fi

    # Systemd services
    for svc in "${SERVICES[@]}"; do
        if [[ -f "/etc/systemd/system/${svc}.service" ]]; then
            echo "  [SVC]  ${svc}.service"
        fi
    done

    echo ""
}

# =============================================================================
# Removal Phases
# =============================================================================

# PHASE 1: Stop Services
phase_stop_services() {
    log_step "PHASE 1: Stopping services..."

    for svc in "${SERVICES[@]}"; do
        if systemctl is-active "${svc}.service" &>/dev/null; then
            log_info "Stopping ${svc}..."
            if [[ "$DRY_RUN" != "true" ]]; then
                sudo systemctl stop "${svc}.service" 2>/dev/null || true
            fi
        fi
    done

    # Wait for services to stop
    if [[ "$DRY_RUN" != "true" ]]; then
        sleep 2
    fi

    log_info "Services stopped"
}

# PHASE 2: Disable Services
phase_disable_services() {
    log_step "PHASE 2: Disabling services..."

    for svc in "${SERVICES[@]}"; do
        if systemctl is-enabled "${svc}.service" &>/dev/null; then
            log_info "Disabling ${svc}..."
            if [[ "$DRY_RUN" != "true" ]]; then
                sudo systemctl disable "${svc}.service" 2>/dev/null || true
            fi
        fi
    done

    log_info "Services disabled"
}

# PHASE 3: Backup Config (if requested)
phase_backup_config() {
    if [[ "$KEEP_CONFIG" != "true" ]]; then
        return 0
    fi

    log_step "PHASE 3: Backing up configuration..."

    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_path="$BACKUP_DIR/water-controller-$timestamp"

    log_info "Creating backup at: $backup_path"

    if [[ "$DRY_RUN" != "true" ]]; then
        sudo mkdir -p "$backup_path"

        # Backup config directory
        if [[ -d "$CONFIG_DIR" ]]; then
            sudo cp -r "$CONFIG_DIR" "$backup_path/"
            log_info "Backed up: $CONFIG_DIR"
        fi

        # Backup data directory
        if [[ -d "$DATA_DIR" ]]; then
            sudo cp -r "$DATA_DIR" "$backup_path/"
            log_info "Backed up: $DATA_DIR"
        fi

        # Record what was backed up (using sudo tee for permission)
        sudo tee "$backup_path/backup_info.txt" > /dev/null <<EOF
Water-Controller Backup
=======================
Created: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Version: $(get_installed_version)
Reason: Uninstallation with --keep-config

Contents:
$(ls -la "$backup_path" 2>/dev/null)

To restore:
  sudo cp -r $backup_path/water-controller/* /etc/water-controller/
  sudo cp -r $backup_path/water-controller/* /var/lib/water-controller/
EOF

        log_info "Backup created: $backup_path"
    else
        log_info "[DRY RUN] Would create backup at: $backup_path"
    fi
}

# PHASE 4: Remove Systemd Unit Files
phase_remove_systemd() {
    log_step "PHASE 4: Removing systemd unit files..."

    for svc in "${SERVICES[@]}"; do
        local unit_file="/etc/systemd/system/${svc}.service"
        if [[ -f "$unit_file" ]]; then
            log_info "Removing: $unit_file"
            if [[ "$DRY_RUN" != "true" ]]; then
                sudo rm -f "$unit_file"
            fi
        fi
    done

    # Reload systemd
    if [[ "$DRY_RUN" != "true" ]]; then
        sudo systemctl daemon-reload
    fi

    log_info "Systemd unit files removed"
}

# PHASE 5: Remove Installation Directory
phase_remove_install_dir() {
    log_step "PHASE 5: Removing installation directory..."

    if [[ -d "$INSTALL_BASE" ]]; then
        log_info "Removing: $INSTALL_BASE"
        if [[ "$DRY_RUN" != "true" ]]; then
            sudo rm -rf "$INSTALL_BASE"
        fi
    fi

    log_info "Installation directory removed"
}

# PHASE 6: Remove Config and Data (unless --keep-config)
phase_remove_config_data() {
    if [[ "$KEEP_CONFIG" == "true" ]]; then
        log_step "PHASE 6: Preserving configuration and data..."
        log_info "Config preserved: $CONFIG_DIR"
        log_info "Data preserved: $DATA_DIR"
        return 0
    fi

    log_step "PHASE 6: Removing configuration and data..."

    if [[ -d "$CONFIG_DIR" ]]; then
        log_info "Removing: $CONFIG_DIR"
        if [[ "$DRY_RUN" != "true" ]]; then
            sudo rm -rf "$CONFIG_DIR"
        fi
    fi

    if [[ -d "$DATA_DIR" ]]; then
        log_info "Removing: $DATA_DIR"
        if [[ "$DRY_RUN" != "true" ]]; then
            sudo rm -rf "$DATA_DIR"
        fi
    fi

    log_info "Configuration and data removed"
}

# PHASE 7: Remove Log Directory
phase_remove_logs() {
    log_step "PHASE 7: Removing log files..."

    if [[ -d "$LOG_DIR" ]]; then
        log_info "Removing: $LOG_DIR"
        if [[ "$DRY_RUN" != "true" ]]; then
            sudo rm -rf "$LOG_DIR"
        fi
    fi

    # Also remove install log
    local install_log="/var/log/water-controller-install.log"
    if [[ -f "$install_log" ]]; then
        log_info "Removing: $install_log"
        if [[ "$DRY_RUN" != "true" ]]; then
            sudo rm -f "$install_log"
        fi
    fi

    log_info "Log files removed"
}

# PHASE 8: Final Verification
phase_verify() {
    log_step "PHASE 8: Verification..."

    local remaining=()

    # Check for remaining directories
    [[ -d "$INSTALL_BASE" ]] && remaining+=("$INSTALL_BASE")

    if [[ "$KEEP_CONFIG" != "true" ]]; then
        [[ -d "$CONFIG_DIR" ]] && remaining+=("$CONFIG_DIR")
        [[ -d "$DATA_DIR" ]] && remaining+=("$DATA_DIR")
    fi

    [[ -d "$LOG_DIR" ]] && remaining+=("$LOG_DIR")

    # Check for remaining services
    for svc in "${SERVICES[@]}"; do
        if [[ -f "/etc/systemd/system/${svc}.service" ]]; then
            remaining+=("/etc/systemd/system/${svc}.service")
        fi
    done

    if [[ ${#remaining[@]} -gt 0 ]]; then
        log_warn "Some items could not be removed:"
        for item in "${remaining[@]}"; do
            log_warn "  - $item"
        done
        return 1
    fi

    log_info "Verification passed: all items removed"
    return 0
}

# =============================================================================
# Main Removal Function
# =============================================================================

do_remove() {
    log_info "Water-Controller Remove Script v$REMOVE_VERSION"
    echo ""

    # Check if installed
    if ! is_installed; then
        if [[ "$FORCE" == "true" ]]; then
            log_warn "No installation detected, but --force specified. Continuing."
        else
            log_info "Water-Controller is not installed"
            return 0
        fi
    fi

    local installed_version
    installed_version=$(get_installed_version)
    log_info "Installed version: $installed_version"

    # Show what will be removed
    list_removal_targets

    # Confirm unless --yes was specified
    if [[ "$CONFIRM_YES" != "true" ]] && [[ "$DRY_RUN" != "true" ]]; then
        echo ""
        if [[ "$KEEP_CONFIG" == "true" ]]; then
            echo "Configuration and data will be PRESERVED."
        else
            echo -e "${RED}WARNING: All data and configuration will be DELETED!${NC}"
        fi
        echo ""
        read -r -p "Are you sure you want to continue? [y/N] " response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            log_info "Removal cancelled"
            return 0
        fi
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info ""
        log_info "=== DRY RUN MODE ==="
        log_info "The following actions would be performed:"
        log_info ""
    fi

    # Execute removal phases
    phase_stop_services
    phase_disable_services
    phase_backup_config
    phase_remove_systemd
    phase_remove_install_dir
    phase_remove_config_data
    phase_remove_logs

    if [[ "$DRY_RUN" != "true" ]]; then
        if ! phase_verify; then
            if [[ "$FORCE" == "true" ]]; then
                log_warn "Verification failed but --force specified. Continuing."
            else
                log_error "Verification failed. Use --force to ignore."
                return 1
            fi
        fi
    fi

    # Final message
    echo ""
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN complete. No changes were made."
    else
        log_info "======================================"
        log_info "Water-Controller has been removed"
        log_info ""

        if [[ "$KEEP_CONFIG" == "true" ]]; then
            log_info "Configuration preserved at: $BACKUP_DIR/water-controller-*"
        fi

        log_info ""
        log_info "To reinstall:"
        log_info "  curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | bash"
        log_info "======================================"
    fi

    return 0
}

# =============================================================================
# Help and Usage
# =============================================================================

show_help() {
    cat <<EOF
Water-Controller Remove Script v$REMOVE_VERSION

USAGE:
    remove.sh [OPTIONS]

OPTIONS:
    --keep-config       Preserve configuration and data files
    --yes, -y           Skip confirmation prompt
    --dry-run           Show what would be removed without making changes
    --force             Force removal even if errors occur
    --help, -h          Show this help message
    --version           Show version information

DESCRIPTION:
    Safely removes Water-Controller from the system. This includes:

    - Stopping all Water-Controller services
    - Disabling services from starting at boot
    - Removing systemd unit files
    - Removing the installation directory (/opt/water-controller)
    - Removing configuration files (/etc/water-controller)
    - Removing data files (/var/lib/water-controller)
    - Removing log files (/var/log/water-controller)

EXAMPLES:
    # Standard removal (with confirmation)
    ./remove.sh

    # Remove but keep configuration
    ./remove.sh --keep-config

    # Remove without confirmation
    ./remove.sh --yes

    # See what would be removed
    ./remove.sh --dry-run

NOTES:
    When using --keep-config, configuration and data are backed up to:
    /var/backups/water-controller-YYYYMMDD_HHMMSS/
EOF
}

# =============================================================================
# Main Entry Point
# =============================================================================

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --keep-config)
                KEEP_CONFIG="true"
                shift
                ;;
            --yes|-y)
                CONFIRM_YES="true"
                shift
                ;;
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            --force)
                FORCE="true"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            --version)
                echo "Water-Controller Remove v$REMOVE_VERSION"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Check root (unless dry-run)
    if [[ "$DRY_RUN" != "true" ]] && [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi

    do_remove
}

main "$@"
