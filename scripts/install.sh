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

set -o pipefail

# =============================================================================
# Script Constants
# =============================================================================

readonly INSTALLER_VERSION="1.0.0"
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
readonly DEFAULT_SOURCE_REPO="https://github.com/water-controller/water-controller.git"
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
        "detection.sh"
        "dependencies.sh"
        "pnet.sh"
        "build.sh"
        "install-files.sh"
        "service.sh"
        "network-storage.sh"
        "validation.sh"
        "documentation.sh"
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
    --upgrade           Upgrade existing installation
    --uninstall         Remove installation completely

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
        log_error "This script must be run as root"
        ((errors++))
    fi

    # Check for required commands
    local required_commands=("bash" "grep" "sed" "awk" "tar" "gzip")
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            log_error "Required command not found: $cmd"
            ((errors++))
        fi
    done

    # Check disk space (need at least 1GB free)
    local free_space
    free_space=$(df -m / 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -n "$free_space" ] && [ "$free_space" -lt 1024 ]; then
        log_error "Insufficient disk space: ${free_space}MB available, 1024MB required"
        ((errors++))
    fi

    # Check if systemd is available
    if ! command -v systemctl >/dev/null 2>&1; then
        log_error "systemd is required but not found"
        ((errors++))
    fi

    # Check source availability
    if [ -n "$SOURCE_PATH" ]; then
        if [ ! -d "$SOURCE_PATH" ]; then
            log_error "Source path not found: $SOURCE_PATH"
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
            log_error "No existing installation found at $INSTALL_DIR for upgrade"
            ((errors++))
        fi
    fi

    # Check no existing installation in fresh install mode
    if [ $UPGRADE_MODE -eq 0 ] && [ $UNINSTALL_MODE -eq 0 ]; then
        if [ -d "$INSTALL_DIR" ] && [ $FORCE -eq 0 ]; then
            log_error "Installation already exists at $INSTALL_DIR"
            log_error "Use --upgrade to upgrade or --force to overwrite"
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

    if [ $INTERACTIVE -eq 0 ] || [ $FORCE -eq 1 ]; then
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
# Installation Steps
# =============================================================================

# Step 1: System Detection
step_detect_system() {
    log_info "=== Step 1: System Detection ==="

    if [ $DRY_RUN -eq 1 ]; then
        log_info "[DRY RUN] Would detect system configuration"
        return 0
    fi

    # Run system detection
    if ! detect_system; then
        log_error "System detection failed"
        return 1
    fi

    # Classify hardware
    if ! classify_hardware; then
        log_warn "Hardware classification failed, continuing with generic settings"
    fi

    # Check prerequisites
    if ! check_prerequisites; then
        log_error "Prerequisites check failed"
        return 1
    fi

    log_info "System detection complete"
    return 0
}

# Step 2: Install Dependencies
step_install_dependencies() {
    log_info "=== Step 2: Dependency Installation ==="

    if [ $SKIP_DEPS -eq 1 ]; then
        log_info "Skipping dependency installation (--skip-deps)"
        return 0
    fi

    if [ $DRY_RUN -eq 1 ]; then
        log_info "[DRY RUN] Would install dependencies:"
        log_info "  - Python 3.9+"
        log_info "  - Node.js 18+"
        log_info "  - Build tools"
        return 0
    fi

    # Install Python
    if ! install_python; then
        log_error "Python installation failed"
        return 1
    fi

    # Install Node.js
    if ! install_nodejs; then
        log_error "Node.js installation failed"
        return 1
    fi

    # Install build dependencies
    if ! install_build_deps; then
        log_error "Build dependencies installation failed"
        return 1
    fi

    # Check for PROFINET dependencies (optional)
    install_profinet_deps || log_warn "PROFINET dependencies not available"

    # Verify all dependencies
    if ! verify_all_dependencies; then
        log_error "Dependency verification failed"
        return 1
    fi

    log_info "Dependencies installed successfully"
    return 0
}

# Step 3: P-Net PROFINET Installation (Cornerstone of the project)
step_install_pnet() {
    log_info "=== Step 3: P-Net PROFINET Installation ==="
    log_info "P-Net is the cornerstone of industrial communication"

    if [ $DRY_RUN -eq 1 ]; then
        log_info "[DRY RUN] Would install p-net PROFINET stack:"
        log_info "  - Clone from: https://github.com/rtlabs-com/p-net.git"
        log_info "  - Build with cmake"
        log_info "  - Install to /usr/local"
        return 0
    fi

    # Check if p-net is already installed
    if verify_pnet_installation 2>/dev/null; then
        log_info "P-Net already installed, verifying..."
        if diagnose_pnet >/dev/null 2>&1; then
            log_info "Existing p-net installation verified"
            return 0
        fi
        log_warn "Existing installation has issues, reinstalling..."
    fi

    # Full p-net installation from source
    log_info "Installing p-net from source (not available in repositories)..."

    if ! install_pnet_full; then
        log_error "P-Net installation failed"
        log_error "This is critical - PROFINET communication will not work"
        return 1
    fi

    # Configure p-net
    local pnet_interface="${NETWORK_INTERFACE:-}"
    if [ -z "$pnet_interface" ]; then
        # Auto-detect first ethernet interface
        pnet_interface=$(ip -brief link show 2>/dev/null | grep -E '^(eth|en)' | awk '{print $1}' | head -1)
    fi

    if [ -n "$pnet_interface" ]; then
        log_info "Configuring p-net for interface: $pnet_interface"
        create_pnet_config "$pnet_interface" "water-controller" "${STATIC_IP:-}" || {
            log_warn "P-Net configuration creation failed"
        }
        configure_pnet_interface "$pnet_interface" || {
            log_warn "P-Net interface configuration failed"
        }
    else
        log_warn "No ethernet interface detected for p-net configuration"
    fi

    # Load kernel modules
    load_pnet_modules || log_warn "Some kernel modules could not be loaded"

    # Install sample application for testing
    install_pnet_sample || log_warn "Sample application installation failed"

    # Final verification
    if ! verify_pnet_installation; then
        log_error "P-Net installation verification failed"
        return 1
    fi

    log_info "P-Net PROFINET installation complete"
    return 0
}

# Step 4: Acquire and Build Source
step_build() {
    log_info "=== Step 4: Source Acquisition and Build ==="

    if [ $SKIP_BUILD -eq 1 ]; then
        log_info "Skipping build (--skip-build)"
        return 0
    fi

    local build_dir="/tmp/water-controller-build-$$"

    if [ $DRY_RUN -eq 1 ]; then
        log_info "[DRY RUN] Would acquire and build source"
        if [ -n "$SOURCE_PATH" ]; then
            log_info "  Source: $SOURCE_PATH"
        else
            log_info "  Repository: $SOURCE_REPO"
            log_info "  Branch: $SOURCE_BRANCH"
        fi
        return 0
    fi

    # Acquire source
    if [ -n "$SOURCE_PATH" ]; then
        if ! acquire_source "$SOURCE_PATH" "$build_dir"; then
            log_error "Failed to copy source from $SOURCE_PATH"
            return 1
        fi
    else
        if ! acquire_source "$SOURCE_REPO" "$build_dir" "$SOURCE_BRANCH"; then
            log_error "Failed to clone repository"
            return 1
        fi
    fi

    # Create Python virtual environment
    if ! create_python_venv "${INSTALL_DIR}/venv"; then
        log_error "Failed to create Python virtual environment"
        rm -rf "$build_dir"
        return 1
    fi

    # Build Python backend
    if ! build_python_backend "$build_dir" "${INSTALL_DIR}/venv"; then
        log_error "Failed to build Python backend"
        rm -rf "$build_dir"
        return 1
    fi

    # Build React frontend
    if ! build_react_frontend "$build_dir"; then
        log_error "Failed to build React frontend"
        rm -rf "$build_dir"
        return 1
    fi

    # Verify build
    if ! verify_build "$build_dir"; then
        log_error "Build verification failed"
        rm -rf "$build_dir"
        return 1
    fi

    # Apply platform optimizations
    apply_build_optimizations "$build_dir" || log_warn "Optimizations could not be applied"

    # Store build directory for installation step
    BUILD_DIR="$build_dir"
    export BUILD_DIR

    log_info "Build completed successfully"
    return 0
}

# Step 5: Install Files
step_install_files() {
    log_info "=== Step 5: File Installation ==="

    if [ $DRY_RUN -eq 1 ]; then
        log_info "[DRY RUN] Would install files to:"
        log_info "  - $INSTALL_DIR"
        log_info "  - $CONFIG_DIR"
        log_info "  - $DATA_DIR"
        return 0
    fi

    # Create service user
    if ! create_service_user; then
        log_error "Failed to create service user"
        return 1
    fi

    # Create directory structure
    if ! create_directory_structure; then
        log_error "Failed to create directory structure"
        return 1
    fi

    # Install Python application
    local build_dir="${BUILD_DIR:-/tmp/water-controller-build-$$}"
    if [ -d "$build_dir" ]; then
        if ! install_python_app "$build_dir"; then
            log_error "Failed to install Python application"
            return 1
        fi

        # Install frontend
        if ! install_frontend "$build_dir"; then
            log_error "Failed to install frontend"
            return 1
        fi
    elif [ $SKIP_BUILD -eq 0 ]; then
        log_error "Build directory not found"
        return 1
    fi

    # Install configuration template
    if ! install_config_template; then
        log_error "Failed to install configuration"
        return 1
    fi

    log_info "Files installed successfully"
    return 0
}

# Step 6: Configure Service
step_configure_service() {
    log_info "=== Step 6: Service Configuration ==="

    if [ $DRY_RUN -eq 1 ]; then
        log_info "[DRY RUN] Would configure systemd service"
        return 0
    fi

    # Generate service unit
    local service_content
    service_content=$(generate_service_unit)
    if [ -z "$service_content" ]; then
        log_error "Failed to generate service unit"
        return 1
    fi

    # Install service
    if ! install_service "$service_content"; then
        log_error "Failed to install service"
        return 1
    fi

    # Enable service
    if ! enable_service; then
        log_error "Failed to enable service"
        return 1
    fi

    log_info "Service configured successfully"
    return 0
}

# Step 7: Network and Storage Configuration
step_configure_network_storage() {
    log_info "=== Step 7: Network and Storage Configuration ==="

    if [ $SKIP_NETWORK -eq 1 ] && [ $CONFIGURE_NETWORK -eq 0 ]; then
        log_info "Skipping network configuration"
    fi

    if [ $DRY_RUN -eq 1 ]; then
        log_info "[DRY RUN] Would configure network and storage"
        return 0
    fi

    # Configure tmpfs for write endurance
    if ! configure_tmpfs; then
        log_warn "tmpfs configuration failed, continuing"
    fi

    # Configure SQLite for WAL mode
    if ! configure_sqlite; then
        log_warn "SQLite configuration failed, continuing"
    fi

    # Configure log rotation
    if ! configure_log_rotation; then
        log_warn "Log rotation configuration failed, continuing"
    fi

    # Network configuration if requested
    if [ $CONFIGURE_NETWORK -eq 1 ]; then
        # Select network interface
        local iface="$NETWORK_INTERFACE"
        if [ -z "$iface" ]; then
            iface=$(select_network_interface)
        fi

        if [ -n "$iface" ]; then
            # Configure static IP if provided
            if [ -n "$STATIC_IP" ]; then
                if ! configure_static_ip "$iface" "$STATIC_IP"; then
                    log_warn "Static IP configuration failed"
                fi
            fi

            # Tune network interface for PROFINET
            if ! tune_network_interface "$iface"; then
                log_warn "Network tuning failed"
            fi
        fi

        # Configure firewall
        if ! configure_firewall; then
            log_warn "Firewall configuration failed"
        fi
    fi

    log_info "Network and storage configuration complete"
    return 0
}

# Step 8: Start Service
step_start_service() {
    log_info "=== Step 8: Starting Service ==="

    if [ $DRY_RUN -eq 1 ]; then
        log_info "[DRY RUN] Would start water-controller service"
        return 0
    fi

    # Start the service
    if ! start_service; then
        log_error "Failed to start service"
        return 1
    fi

    # Wait for service to be healthy
    sleep 3

    # Check service health
    if ! check_service_health; then
        log_error "Service health check failed"
        return 1
    fi

    log_info "Service started successfully"
    return 0
}

# Step 9: Validation
step_validate() {
    log_info "=== Step 9: Post-Installation Validation ==="

    if [ $SKIP_VALIDATION -eq 1 ]; then
        log_info "Skipping validation (--skip-validation)"
        return 0
    fi

    if [ $DRY_RUN -eq 1 ]; then
        log_info "[DRY RUN] Would run validation tests"
        return 0
    fi

    # Run validation suite
    if ! run_validation_suite; then
        log_warn "Some validation tests failed"
        # Don't fail installation for validation issues
        return 0
    fi

    log_info "Validation complete"
    return 0
}

# Step 10: Documentation
step_generate_docs() {
    log_info "=== Step 10: Generating Documentation ==="

    if [ $DRY_RUN -eq 1 ]; then
        log_info "[DRY RUN] Would generate documentation"
        return 0
    fi

    # Generate installation report
    if ! generate_installation_report; then
        log_warn "Failed to generate installation report"
    fi

    # Generate configuration documentation
    if ! generate_config_docs; then
        log_warn "Failed to generate configuration docs"
    fi

    log_info "Documentation generated"
    return 0
}

# =============================================================================
# Upgrade Process
# =============================================================================

do_upgrade() {
    log_info "Starting upgrade process..."

    # Create rollback point before upgrade
    log_info "Creating rollback point..."
    ROLLBACK_POINT=$(create_rollback_point "Pre-upgrade backup")
    if [ -z "$ROLLBACK_POINT" ]; then
        log_error "Failed to create rollback point"
        if ! confirm "Continue without rollback capability?"; then
            return 1
        fi
    else
        log_info "Rollback point created: $ROLLBACK_POINT"
    fi

    # Stop existing service
    log_info "Stopping existing service..."
    stop_service || log_warn "Service stop failed or not running"

    # Run installation steps
    step_detect_system || { rollback_on_failure; return 1; }
    step_install_dependencies || { rollback_on_failure; return 1; }
    step_install_pnet || { rollback_on_failure; return 1; }
    step_build || { rollback_on_failure; return 1; }
    step_install_files || { rollback_on_failure; return 1; }
    step_configure_service || { rollback_on_failure; return 1; }
    step_configure_network_storage || { rollback_on_failure; return 1; }
    step_start_service || { rollback_on_failure; return 1; }
    step_validate || log_warn "Validation had issues"
    step_generate_docs

    # Clean up build directory
    cleanup_build

    log_info "Upgrade completed successfully"
    return 0
}

# Rollback on failure during upgrade
rollback_on_failure() {
    if [ -n "$ROLLBACK_POINT" ]; then
        log_error "Installation failed, initiating rollback..."
        if perform_rollback "$ROLLBACK_POINT"; then
            log_info "Rollback successful"
        else
            log_error "Rollback failed - manual intervention required"
        fi
    fi
}

# =============================================================================
# Uninstall Process
# =============================================================================

do_uninstall() {
    log_info "Starting uninstallation process..."

    if [ $DRY_RUN -eq 1 ]; then
        log_info "[DRY RUN] Would uninstall Water Controller"
        log_info "  - Stop and disable service"
        log_info "  - Remove $INSTALL_DIR"
        log_info "  - Remove $CONFIG_DIR (optional)"
        log_info "  - Remove $DATA_DIR (optional)"
        log_info "  - Remove service user (optional)"
        return 0
    fi

    # Confirm uninstallation
    if ! confirm "This will remove the Water Controller installation. Continue?" "n"; then
        log_info "Uninstallation cancelled"
        return 0
    fi

    local errors=0

    # Stop service
    log_info "Stopping service..."
    if command -v systemctl >/dev/null 2>&1; then
        systemctl stop water-controller.service 2>/dev/null || true
        systemctl disable water-controller.service 2>/dev/null || true
    fi

    # Remove service file
    log_info "Removing service file..."
    rm -f /etc/systemd/system/water-controller.service
    systemctl daemon-reload 2>/dev/null || true

    # Remove installation directory
    log_info "Removing installation directory..."
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR" || ((errors++))
    fi

    # Ask about configuration
    if [ -d "$CONFIG_DIR" ]; then
        if confirm "Remove configuration directory ($CONFIG_DIR)?" "n"; then
            rm -rf "$CONFIG_DIR" || ((errors++))
        else
            log_info "Configuration preserved at $CONFIG_DIR"
        fi
    fi

    # Ask about data
    if [ -d "$DATA_DIR" ]; then
        if confirm "Remove data directory ($DATA_DIR)? This includes the database!" "n"; then
            rm -rf "$DATA_DIR" || ((errors++))
        else
            log_info "Data preserved at $DATA_DIR"
        fi
    fi

    # Ask about logs
    if [ -d "$LOG_DIR" ]; then
        if confirm "Remove log directory ($LOG_DIR)?" "n"; then
            rm -rf "$LOG_DIR" || ((errors++))
        else
            log_info "Logs preserved at $LOG_DIR"
        fi
    fi

    # Ask about backups
    if [ -d "$BACKUP_DIR" ]; then
        if confirm "Remove backup directory ($BACKUP_DIR)?" "n"; then
            rm -rf "$BACKUP_DIR" || ((errors++))
        else
            log_info "Backups preserved at $BACKUP_DIR"
        fi
    fi

    # Ask about service user
    if id water-controller >/dev/null 2>&1; then
        if confirm "Remove service user (water-controller)?" "n"; then
            userdel water-controller 2>/dev/null || ((errors++))
        else
            log_info "Service user preserved"
        fi
    fi

    # Remove logrotate config
    rm -f /etc/logrotate.d/water-controller 2>/dev/null || true

    # Remove tmpfs mount
    if grep -q "water-controller" /etc/fstab 2>/dev/null; then
        log_info "Removing tmpfs mount from fstab..."
        sed -i '/water-controller/d' /etc/fstab 2>/dev/null || true
    fi

    if [ $errors -eq 0 ]; then
        log_info "Uninstallation completed successfully"
    else
        log_warn "Uninstallation completed with $errors errors"
    fi

    return 0
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

    local api_port=8000
    local hmi_port=8080

    echo ""
    echo "============================================================"
    echo "            WATER TREATMENT CONTROLLER INSTALLED"
    echo "============================================================"
    echo ""
    echo "Installation completed successfully!"
    echo ""
    echo "Service Status:"
    echo "  systemctl status water-controller"
    echo ""
    echo "Access Points:"
    echo "  API:  http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):${api_port}"
    echo "  HMI:  http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):${hmi_port}"
    echo ""
    echo "Useful Commands:"
    echo "  Start:    systemctl start water-controller"
    echo "  Stop:     systemctl stop water-controller"
    echo "  Restart:  systemctl restart water-controller"
    echo "  Logs:     journalctl -u water-controller -f"
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
        _early_log_error "Failed to load installation modules"
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
        log_error "Pre-flight checks failed"
        exit 1
    fi

    # Execute appropriate mode
    local result=0
    if [ $UNINSTALL_MODE -eq 1 ]; then
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
        log_error "Installation failed. Check log file: $LOG_FILE"
        exit 1
    fi

    exit 0
}

# Run main function
main "$@"
