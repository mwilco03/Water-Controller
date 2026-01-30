#!/bin/bash
#
# Water Treatment Controller - Main Installation Script
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This script orchestrates the complete installation of the Water Treatment
# Controller SCADA system on ARM/x86 single-board computers.
#
# Usage: ./install.sh [OPTIONS]
#
# Target: ARM/x86 SBCs running Debian-based Linux
# Tech Stack: Python/FastAPI backend, React frontend
# Constraints: SD card write endurance, real-time requirements, 1GB RAM minimum
#

set -euo pipefail

# =============================================================================
# Script Constants
# =============================================================================

readonly INSTALLER_VERSION="2.0.0"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly LIB_DIR="${SCRIPT_DIR}/lib"
readonly LOG_FILE="/tmp/water-controller-install-$(date +%Y%m%d_%H%M%S).log"

# Installation paths
readonly DEFAULT_INSTALL_DIR="/opt/water-controller"
readonly DEFAULT_CONFIG_DIR="/etc/water-controller"
readonly DEFAULT_DATA_DIR="/var/lib/water-controller"
readonly DEFAULT_LOG_DIR="/var/log/water-controller"
readonly DEFAULT_BACKUP_DIR="/var/backups/water-controller"

# Source repository
readonly DEFAULT_SOURCE_REPO="https://github.com/mwilco03/Water-Controller.git"
readonly DEFAULT_SOURCE_BRANCH="main"

# =============================================================================
# Global Variables
# =============================================================================

# Installation options (can be overridden by CLI args)
INSTALL_DIR="$DEFAULT_INSTALL_DIR"
CONFIG_DIR="$DEFAULT_CONFIG_DIR"
DATA_DIR="$DEFAULT_DATA_DIR"
LOG_DIR="$DEFAULT_LOG_DIR"
BACKUP_DIR="$DEFAULT_BACKUP_DIR"
SOURCE_REPO="$DEFAULT_SOURCE_REPO"
SOURCE_BRANCH="$DEFAULT_SOURCE_BRANCH"
SOURCE_PATH=""

# Modes
DRY_RUN=0
VERBOSE=0
INTERACTIVE=1
FORCE=0
SKIP_DEPS=0
SKIP_BUILD=0
SKIP_NETWORK=0
SKIP_VALIDATION=0
UPGRADE_MODE=0
UNINSTALL_MODE=0
PURGE_MODE=0
KEEP_DATA=0

# Upgrade sub-modes
UNATTENDED_MODE=0
CANARY_MODE=0
STAGED_MODE=0
SELECTIVE_ROLLBACK_MODE=0

# Network configuration
CONFIGURE_NETWORK=0
STATIC_IP=""
NETWORK_INTERFACE=""

# State tracking
INSTALL_START_TIME=""
MODULES_LOADED=0
ROLLBACK_POINT=""

# =============================================================================
# Early Logging (before modules loaded)
# =============================================================================

_early_log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

_early_log_info() { _early_log "INFO" "$@"; }
_early_log_warn() { _early_log "WARN" "$@"; }
_early_log_error() { _early_log "ERROR" "$@"; }

# =============================================================================
# Module Loading
# =============================================================================

# Load all library modules
load_modules() {
    local modules=(
        "common.sh"
        "detection.sh"
        "dependencies.sh"
        "database.sh"
        "pnet.sh"
        "build.sh"
        "install-files.sh"
        "service.sh"
        "network-storage.sh"
        "validation.sh"
        "documentation.sh"
        "upgrade.sh"
        "steps.sh"
        "uninstall.sh"
    )

    _early_log_info "Loading installation modules..."

    for module in "${modules[@]}"; do
        local module_path="${LIB_DIR}/${module}"

        if [ ! -f "$module_path" ]; then
            _early_log_error "Required module not found: $module_path"
            return 1
        fi

        # shellcheck source=/dev/null
        if ! source "$module_path"; then
            _early_log_error "Failed to load module: $module"
            return 1
        fi

        if [ $VERBOSE -eq 1 ]; then
            _early_log_info "Loaded: $module"
        fi
    done

    MODULES_LOADED=1
    log_info "All modules loaded successfully"
    return 0
}

# =============================================================================
# Usage and Help
# =============================================================================

show_usage() {
    cat <<EOF
Water Treatment Controller - Installation Script v${INSTALLER_VERSION}

USAGE:
    $0 [OPTIONS]

INSTALLATION MODES:
    (default)           Fresh installation
    --upgrade           Upgrade existing installation (interactive)
    --uninstall         Remove installation completely
    --uninstall --purge Remove everything including P-Net, firewall rules, udev rules
    --uninstall --keep-data  Remove application but preserve data/config

UPGRADE MODES (use with --upgrade):
    --unattended        Fully automated, no prompts, auto-rollback on failure
    --canary            Run extended tests after upgrade, auto-rollback if fail
    --staged            Pause at each major step for confirmation

OPTIONS:
    -h, --help          Show this help message
    -v, --verbose       Enable verbose output
    -y, --yes           Non-interactive mode (accept defaults)
    -n, --dry-run       Show what would be done without making changes
    -f, --force         Force installation (skip confirmations)

PATHS:
    --install-dir PATH  Installation directory (default: $DEFAULT_INSTALL_DIR)
    --config-dir PATH   Configuration directory (default: $DEFAULT_CONFIG_DIR)
    --data-dir PATH     Data directory (default: $DEFAULT_DATA_DIR)
    --log-dir PATH      Log directory (default: $DEFAULT_LOG_DIR)

SOURCE:
    --source PATH       Use local source directory instead of git clone
    --repo URL          Git repository URL (default: $DEFAULT_SOURCE_REPO)
    --branch NAME       Git branch to use (default: $DEFAULT_SOURCE_BRANCH)

NETWORK:
    --configure-network Enable network configuration
    --static-ip IP      Set static IP address (e.g., 192.168.1.100/24)
    --interface NAME    Network interface to configure (e.g., eth0)

SKIP OPTIONS:
    --skip-deps         Skip dependency installation
    --skip-build        Skip build step (use pre-built artifacts)
    --skip-network      Skip network configuration
    --skip-validation   Skip post-installation validation

EXAMPLES:
    # Interactive installation
    $0

    # Non-interactive installation with defaults
    $0 --yes

    # Install from local source
    $0 --source /path/to/source

    # Upgrade existing installation
    $0 --upgrade

    # Configure with static IP
    $0 --configure-network --static-ip 192.168.1.100/24 --interface eth0

    # Dry run to see what would happen
    $0 --dry-run

    # Uninstall
    $0 --uninstall

EOF
}

# =============================================================================
# Argument Parsing
# =============================================================================

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                show_usage
                exit 0
                ;;
            -v|--verbose)
                VERBOSE=1
                shift
                ;;
            -y|--yes)
                INTERACTIVE=0
                shift
                ;;
            -n|--dry-run)
                DRY_RUN=1
                shift
                ;;
            -f|--force)
                FORCE=1
                shift
                ;;
            --upgrade)
                UPGRADE_MODE=1
                shift
                ;;
            --uninstall)
                UNINSTALL_MODE=1
                shift
                ;;
            --purge)
                PURGE_MODE=1
                shift
                ;;
            --keep-data)
                KEEP_DATA=1
                shift
                ;;
            --unattended)
                UNATTENDED_MODE=1
                INTERACTIVE=0
                shift
                ;;
            --canary)
                CANARY_MODE=1
                shift
                ;;
            --staged)
                STAGED_MODE=1
                shift
                ;;
            --selective-rollback)
                SELECTIVE_ROLLBACK_MODE=1
                shift
                ;;
            --install-dir)
                INSTALL_DIR="$2"
                shift 2
                ;;
            --config-dir)
                CONFIG_DIR="$2"
                shift 2
                ;;
            --data-dir)
                DATA_DIR="$2"
                shift 2
                ;;
            --log-dir)
                LOG_DIR="$2"
                shift 2
                ;;
            --source)
                SOURCE_PATH="$2"
                shift 2
                ;;
            --repo)
                SOURCE_REPO="$2"
                shift 2
                ;;
            --branch)
                SOURCE_BRANCH="$2"
                shift 2
                ;;
            --configure-network)
                CONFIGURE_NETWORK=1
                shift
                ;;
            --static-ip)
                STATIC_IP="$2"
                CONFIGURE_NETWORK=1
                shift 2
                ;;
            --interface)
                NETWORK_INTERFACE="$2"
                shift 2
                ;;
            --skip-deps)
                SKIP_DEPS=1
                shift
                ;;
            --skip-build)
                SKIP_BUILD=1
                shift
                ;;
            --skip-network)
                SKIP_NETWORK=1
                shift
                ;;
            --skip-validation)
                SKIP_VALIDATION=1
                shift
                ;;
            *)
                _early_log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    # Export paths for modules
    export INSTALL_DIR CONFIG_DIR DATA_DIR LOG_DIR BACKUP_DIR
    export DRY_RUN VERBOSE INTERACTIVE FORCE
    export SKIP_DEPS SKIP_BUILD SKIP_NETWORK SKIP_VALIDATION
    export UPGRADE_MODE UNINSTALL_MODE PURGE_MODE KEEP_DATA
    export UNATTENDED_MODE CANARY_MODE STAGED_MODE
    export CONFIGURE_NETWORK STATIC_IP NETWORK_INTERFACE
    export SOURCE_PATH SOURCE_REPO SOURCE_BRANCH
}

# =============================================================================
# Pre-flight Checks
# =============================================================================

# Verify we can run the installation
preflight_checks() {
    log_info "Running pre-flight checks..."

    local errors=0

    # Check root privileges
    if [ "$(id -u)" -ne 0 ]; then
        log_error "Script not running as root. Installation cannot proceed. Run with: sudo $0"
        ((errors++))
    fi

    # Check for required commands
    local required_commands=("bash" "grep" "sed" "awk" "tar" "gzip")
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            log_error "Required command not found: $cmd. Installation cannot continue. Install $cmd package and retry."
            ((errors++))
        fi
    done

    # Check disk space (need at least 1GB free)
    local free_space
    free_space=$(df -m / 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -n "$free_space" ] && [ "$free_space" -lt 1024 ]; then
        log_error "Insufficient disk space: ${free_space}MB available, 1024MB required. Installation will fail. Free disk space and retry."
        ((errors++))
    fi

    # Check if systemd is available
    if ! command -v systemctl >/dev/null 2>&1; then
        log_error "systemd not found. Service management unavailable. Install systemd or use a compatible init system."
        ((errors++))
    fi

    # Check source availability
    if [ -n "$SOURCE_PATH" ]; then
        if [ ! -d "$SOURCE_PATH" ]; then
            log_error "Source path not found: $SOURCE_PATH. Cannot install from specified location. Verify path exists and retry."
            ((errors++))
        fi
    else
        # Check if git is available for cloning
        if ! command -v git >/dev/null 2>&1; then
            log_warn "git not found - will attempt to install"
        fi
    fi

    # Check for existing installation in upgrade mode
    if [ $UPGRADE_MODE -eq 1 ]; then
        if [ ! -d "$INSTALL_DIR" ]; then
            log_error "No existing installation at $INSTALL_DIR. Upgrade cannot proceed. Run fresh install instead."
            ((errors++))
        fi
    fi

    # Check no existing installation in fresh install mode
    if [ $UPGRADE_MODE -eq 0 ] && [ $UNINSTALL_MODE -eq 0 ]; then
        if [ -d "$INSTALL_DIR" ] && [ $FORCE -eq 0 ]; then
            log_error "Installation exists at $INSTALL_DIR. Fresh install blocked. Use --upgrade to upgrade or --force to overwrite."
            ((errors++))
        fi
    fi

    if [ $errors -gt 0 ]; then
        log_error "Pre-flight checks failed with $errors error(s)"
        return 1
    fi

    log_info "Pre-flight checks passed"
    return 0
}

# =============================================================================
# Interactive Prompts
# =============================================================================

# Confirm action with user
confirm() {
    local message="$1"
    local default="${2:-n}"

    # Auto-accept in non-interactive, force, or dry-run mode
    if [ $INTERACTIVE -eq 0 ] || [ $FORCE -eq 1 ] || [ $DRY_RUN -eq 1 ]; then
        return 0
    fi

    local prompt
    if [ "$default" = "y" ]; then
        prompt="[Y/n]"
    else
        prompt="[y/N]"
    fi

    echo ""
    read -r -p "$message $prompt " response
    response="${response:-$default}"

    case "$response" in
        [yY][eE][sS]|[yY])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# Get user input with default
prompt_input() {
    local message="$1"
    local default="$2"
    local var_name="$3"

    if [ $INTERACTIVE -eq 0 ]; then
        eval "$var_name=\"$default\""
        return
    fi

    echo ""
    read -r -p "$message [$default]: " response
    response="${response:-$default}"
    eval "$var_name=\"$response\""
}

# Show installation summary and confirm
show_installation_summary() {
    echo ""
    echo "============================================================"
    echo "        Water Treatment Controller - Installation Summary"
    echo "============================================================"
    echo ""

    if [ $UPGRADE_MODE -eq 1 ]; then
        echo "Mode:               UPGRADE"
    elif [ $UNINSTALL_MODE -eq 1 ]; then
        echo "Mode:               UNINSTALL"
    else
        echo "Mode:               FRESH INSTALL"
    fi

    echo ""
    echo "Paths:"
    echo "  Installation:     $INSTALL_DIR"
    echo "  Configuration:    $CONFIG_DIR"
    echo "  Data:             $DATA_DIR"
    echo "  Logs:             $LOG_DIR"
    echo "  Backups:          $BACKUP_DIR"
    echo ""

    if [ $UNINSTALL_MODE -eq 0 ]; then
        echo "Source:"
        if [ -n "$SOURCE_PATH" ]; then
            echo "  Local Path:       $SOURCE_PATH"
        else
            echo "  Repository:       $SOURCE_REPO"
            echo "  Branch:           $SOURCE_BRANCH"
        fi
        echo ""

        echo "Options:"
        echo "  Skip Dependencies: $([ $SKIP_DEPS -eq 1 ] && echo "Yes" || echo "No")"
        echo "  Skip Build:        $([ $SKIP_BUILD -eq 1 ] && echo "Yes" || echo "No")"
        echo "  Configure Network: $([ $CONFIGURE_NETWORK -eq 1 ] && echo "Yes" || echo "No")"
        if [ $CONFIGURE_NETWORK -eq 1 ] && [ -n "$STATIC_IP" ]; then
            echo "    Static IP:       $STATIC_IP"
            echo "    Interface:       ${NETWORK_INTERFACE:-auto}"
        fi
        echo "  Skip Validation:   $([ $SKIP_VALIDATION -eq 1 ] && echo "Yes" || echo "No")"
        echo ""
    fi

    if [ $DRY_RUN -eq 1 ]; then
        echo "*** DRY RUN MODE - No changes will be made ***"
        echo ""
    fi

    echo "============================================================"
    echo ""

    if ! confirm "Proceed with installation?"; then
        log_info "Installation cancelled by user"
        exit 0
    fi
}

# =============================================================================
# Fresh Installation Process
# =============================================================================

do_install() {
    log_info "Starting fresh installation..."

    INSTALL_START_TIME=$(date +%s)

    # Run all installation steps
    step_detect_system || return 1
    step_install_dependencies || return 1
    step_setup_database || return 1
    step_install_pnet || return 1
    step_build || return 1
    step_install_files || return 1
    step_configure_service || return 1
    step_configure_network_storage || return 1
    step_start_service || return 1
    step_validate || log_warn "Validation had issues"
    step_generate_docs

    # Create initial rollback point
    if [ $DRY_RUN -eq 0 ]; then
        log_info "Creating initial rollback point..."
        create_rollback_point "Fresh installation complete" >/dev/null 2>&1 || true
    fi

    # Clean up build directory
    cleanup_build

    # Calculate duration
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - INSTALL_START_TIME))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))

    log_info "Installation completed successfully in ${minutes}m ${seconds}s"
    return 0
}

# Clean up build directory
cleanup_build() {
    local build_dir="${BUILD_DIR:-/tmp/water-controller-build-$$}"
    if [ -d "$build_dir" ]; then
        log_info "Cleaning up build directory..."
        rm -rf "$build_dir"
    fi
}

# =============================================================================
# Completion Message
# =============================================================================

show_completion_message() {
    if [ $DRY_RUN -eq 1 ]; then
        echo ""
        echo "============================================================"
        echo "                     DRY RUN COMPLETE"
        echo "============================================================"
        echo ""
        echo "No changes were made. Run without --dry-run to install."
        echo ""
        return
    fi

    if [ $UNINSTALL_MODE -eq 1 ]; then
        echo ""
        echo "============================================================"
        echo "                 UNINSTALLATION COMPLETE"
        echo "============================================================"
        echo ""
        return
    fi

    # Source port configuration from installed config file
    local config_file="${INSTALL_DIR}/config/ports.env"
    if [[ -f "$config_file" ]]; then
        # shellcheck source=/dev/null
        source "$config_file"
    fi

    # Use configured ports with fallback defaults
    local api_port="${WTC_API_PORT:-8000}"
    local hmi_port="${WTC_UI_PORT:-8080}"

    # Get primary IP address
    local ip_addr
    ip_addr=$(hostname -I 2>/dev/null | awk '{print $1}')
    [[ -z "$ip_addr" ]] && ip_addr="localhost"

    echo ""
    echo "============================================================"
    echo "            WATER TREATMENT CONTROLLER INSTALLED"
    echo "============================================================"
    echo ""
    echo "Installation completed successfully!"
    echo ""
    echo "Port Configuration (from ${config_file}):"
    echo "  API Port:  ${api_port}"
    echo "  HMI Port:  ${hmi_port}"
    echo ""
    echo "Service Status:"
    echo "  systemctl status water-controller"
    echo ""
    echo "Access Points:"
    echo "  API:       http://${ip_addr}:${api_port}"
    echo "  HMI:       http://${ip_addr}:${hmi_port}"
    echo "  API Docs:  http://${ip_addr}:${api_port}/api/docs"
    echo "  Health:    http://${ip_addr}:${api_port}/health"
    echo ""
    echo "Useful Commands:"
    echo "  Start:    systemctl start water-controller"
    echo "  Stop:     systemctl stop water-controller"
    echo "  Restart:  systemctl restart water-controller"
    echo "  Logs:     journalctl -u water-controller -f"
    echo "  Health:   curl http://localhost:${api_port}/health"
    echo ""
    echo "Configuration Files:"
    echo "  Ports:    ${config_file}"
    echo "  Main:     /etc/water-controller/config.yaml"
    echo ""
    echo "To customize ports, edit ${config_file} and restart services."
    echo ""
    echo "Documentation:"
    echo "  Report:   /usr/share/doc/water-controller/installation-report.txt"
    echo "  Config:   /usr/share/doc/water-controller/configuration.md"
    echo ""
    echo "Log file:   $LOG_FILE"
    echo ""
    echo "============================================================"
    echo ""
}

# =============================================================================
# Signal Handlers
# =============================================================================

cleanup_on_exit() {
    local exit_code=$?

    # Clean up build directory on failure
    if [ $exit_code -ne 0 ]; then
        cleanup_build
    fi

    # Remove any temporary files
    rm -f /tmp/water-controller-*.tmp 2>/dev/null || true

    exit $exit_code
}

handle_interrupt() {
    echo ""
    log_warn "Installation interrupted by user"
    cleanup_build
    exit 130
}

# =============================================================================
# Main Entry Point
# =============================================================================

main() {
    # Set up signal handlers
    trap cleanup_on_exit EXIT
    trap handle_interrupt INT TERM

    # Create log file
    touch "$LOG_FILE" 2>/dev/null || true
    chmod 644 "$LOG_FILE" 2>/dev/null || true

    _early_log_info "Water Treatment Controller Installer v${INSTALLER_VERSION}"
    _early_log_info "Log file: $LOG_FILE"

    # Parse command line arguments
    parse_arguments "$@"

    # Load modules
    if ! load_modules; then
        _early_log_error "Module loading failed. Installation cannot proceed. Verify scripts/lib/ directory exists."
        exit 1
    fi

    # Enable verbose logging if requested
    if [ $VERBOSE -eq 1 ]; then
        export LOG_LEVEL="DEBUG"
    fi

    # Show summary and confirm
    show_installation_summary

    # Run pre-flight checks
    if ! preflight_checks; then
        log_error "Pre-flight checks failed. Review errors above and fix before retrying."
        exit 1
    fi

    # Check if Docker mode was requested via environment
    if [[ "${USE_DOCKER:-0}" == "1" ]]; then
        log_info "Docker mode selected via USE_DOCKER environment variable"
        log_info "Skipping bare-metal installation. Use docker compose directly:"
        log_info "  cd docker && docker compose up -d"
        exit 0
    fi

    # Execute appropriate mode
    local result=0
    if [ $SELECTIVE_ROLLBACK_MODE -eq 1 ]; then
        selective_rollback || result=1
    elif [ $UNINSTALL_MODE -eq 1 ]; then
        do_uninstall || result=1
    elif [ $UPGRADE_MODE -eq 1 ]; then
        do_upgrade || result=1
    else
        do_install || result=1
    fi

    # Show completion message
    if [ $result -eq 0 ]; then
        show_completion_message
    else
        log_error "Installation failed. Review errors in log file: $LOG_FILE"
        exit 1
    fi

    exit 0
}

# Run main function
main "$@"
