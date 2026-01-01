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
        "detection.sh"
        "dependencies.sh"
        "pnet.sh"
        "build.sh"
        "install-files.sh"
        "service.sh"
        "network-storage.sh"
        "validation.sh"
        "documentation.sh"
        "upgrade.sh"
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
        log_error "System detection failed. Cannot determine hardware/OS configuration. Check system compatibility and retry."
        return 1
    fi

    # Classify hardware
    if ! classify_hardware; then
        log_warn "Hardware classification failed, continuing with generic settings"
    fi

    # Check prerequisites
    if ! check_prerequisites; then
        log_error "Prerequisites check failed. Required system components missing. Review requirements and install missing packages."
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
        log_error "Python installation failed. Backend cannot run. Check package manager and network, then retry."
        return 1
    fi

    # Install Node.js
    if ! install_nodejs; then
        log_error "Node.js installation failed. Frontend build unavailable. Check package manager and network, then retry."
        return 1
    fi

    # Install build dependencies
    if ! install_build_deps; then
        log_error "Build dependencies installation failed. Compilation will fail. Check package manager and retry."
        return 1
    fi

    # Check for PROFINET dependencies (optional)
    install_profinet_deps || log_warn "PROFINET dependencies not available"

    # Verify all dependencies
    if ! verify_all_dependencies; then
        log_error "Dependency verification failed. Some packages not properly installed. Check logs and reinstall missing packages."
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
        log_error "P-Net installation failed. PROFINET communication unavailable. Check build tools and network, then retry."
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
        log_error "P-Net verification failed. Installation incomplete or corrupted. Check build logs and reinstall."
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
            log_error "Source copy failed from $SOURCE_PATH. Build cannot proceed. Verify source path and permissions."
            return 1
        fi
    else
        if ! acquire_source "$SOURCE_REPO" "$build_dir" "$SOURCE_BRANCH"; then
            log_error "Repository clone failed. Build cannot proceed. Check network connectivity and repository URL."
            return 1
        fi
    fi

    # Create Python virtual environment
    if ! create_python_venv "${INSTALL_DIR}/venv"; then
        log_error "Python venv creation failed. Backend isolation unavailable. Check Python installation and disk space."
        rm -rf "$build_dir"
        return 1
    fi

    # Build Python backend
    if ! build_python_backend "$build_dir" "${INSTALL_DIR}/venv"; then
        log_error "Python backend build failed. API server unavailable. Check dependencies and build logs."
        rm -rf "$build_dir"
        return 1
    fi

    # Build React frontend
    if ! build_react_frontend "$build_dir"; then
        log_error "React frontend build failed. HMI unavailable. Check Node.js and npm dependencies."
        rm -rf "$build_dir"
        return 1
    fi

    # Verify build
    if ! verify_build "$build_dir"; then
        log_error "Build verification failed. Artifacts may be incomplete. Review build logs and retry."
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
        log_error "Service user creation failed. Service cannot run securely. Check user permissions and retry."
        return 1
    fi

    # Create directory structure
    if ! create_directory_structure; then
        log_error "Directory creation failed. Files cannot be installed. Check disk space and permissions."
        return 1
    fi

    # Install Python application (uses SOURCE_DIR set by acquire_source)
    if [ -n "$SOURCE_DIR" ] && [ -d "$SOURCE_DIR" ]; then
        if ! install_python_app; then
            log_error "Python app installation failed. Backend unavailable. Check file permissions and disk space."
            return 1
        fi

        # Install frontend
        if ! install_frontend; then
            log_error "Frontend installation failed. HMI unavailable. Check file permissions and disk space."
            return 1
        fi
    elif [ $SKIP_BUILD -eq 0 ]; then
        log_error "SOURCE_DIR not set. Installation sequence error. Run build step first or use --source."
        return 1
    fi

    # Install configuration template
    if ! install_config_template; then
        log_error "Configuration installation failed. Default settings unavailable. Check template files and permissions."
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

    # Install service (install_service handles generation internally)
    if ! install_service; then
        log_error "Service installation failed. Automatic startup unavailable. Check systemd and file permissions."
        return 1
    fi

    # Enable service
    if ! enable_service; then
        log_error "Service enable failed. Auto-start on boot unavailable. Run: systemctl enable water-controller"
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
        log_error "Service start failed. Application not running. Check logs: journalctl -u water-controller"
        return 1
    fi

    # Wait for service to be healthy
    sleep 3

    # Check service health
    if ! check_service_health; then
        log_error "Service health check failed. Application may be misconfigured. Check logs: journalctl -u water-controller"
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
    local upgrade_start
    upgrade_start=$(date -Iseconds)

    # Log upgrade mode
    if [ $UNATTENDED_MODE -eq 1 ]; then
        log_info "Mode: UNATTENDED (no prompts, auto-rollback on failure)"
    elif [ $CANARY_MODE -eq 1 ]; then
        log_info "Mode: CANARY (extended testing, auto-rollback if tests fail)"
    elif [ $STAGED_MODE -eq 1 ]; then
        log_info "Mode: STAGED (pause at each step for confirmation)"
    else
        log_info "Mode: INTERACTIVE"
    fi

    # Compare versions before upgrade
    log_info "Checking version compatibility..."
    compare_versions || log_warn "Could not compare versions"

    # Verify network connectivity for downloads (informational only, non-blocking)
    log_info "Verifying network connectivity..."
    if ! verify_network_connectivity; then
        log_warn "Network connectivity issues detected - continuing anyway"
    fi

    # Pre-upgrade health check (informational only, non-blocking)
    log_info "Running pre-upgrade health check..."
    if ! pre_upgrade_health_check; then
        log_warn "Pre-upgrade health check found issues - continuing anyway"
    fi

    # Check disk space
    log_info "Checking disk space..."
    if ! check_disk_space_for_upgrade; then
        log_error "Insufficient disk space for upgrade. Upgrade cannot proceed. Free disk space and retry."
        return 1
    fi

    # Check for running processes (informational only, non-blocking)
    if ! check_running_processes; then
        log_warn "Critical operations may be in progress - continuing anyway"
    fi

    # Generate upgrade plan
    log_info "Generating upgrade plan..."
    generate_upgrade_plan || log_warn "Could not generate upgrade plan"

    # Export current configuration for comparison
    local old_config
    old_config=$(export_current_configuration 2>/dev/null) || true

    # Snapshot database state for potential rollback
    log_info "Creating database snapshot..."
    snapshot_database_state || log_warn "Database snapshot not available"

    # Create rollback point before upgrade (best effort, non-blocking)
    log_info "Creating rollback point..."
    ROLLBACK_POINT=$(create_rollback_point "Pre-upgrade backup")
    if [ -z "$ROLLBACK_POINT" ]; then
        log_warn "Failed to create rollback point - continuing without rollback capability"
    else
        log_info "Rollback point created: $ROLLBACK_POINT"
        # Verify the rollback point is valid
        if ! verify_rollback_point "$ROLLBACK_POINT"; then
            log_warn "Rollback point verification failed - rollback may not work"
        fi
    fi

    # Canary mode: Test rollback restore capability before proceeding
    if [ $CANARY_MODE -eq 1 ] && [ -n "$ROLLBACK_POINT" ]; then
        log_info "CANARY MODE: Testing rollback restore capability..."
        if ! test_rollback_restore "$ROLLBACK_POINT"; then
            log_error "Rollback restore test failed. Upgrade unsafe without rollback capability. Fix backup system and retry."
            return 1
        fi
    fi

    # Staged mode: confirm before stopping service
    if [ $STAGED_MODE -eq 1 ]; then
        if ! confirm "Ready to stop service and begin upgrade?"; then
            log_info "Upgrade cancelled by user"
            return 1
        fi
    fi

    # Stop existing service
    log_info "Stopping existing service..."
    stop_service || log_warn "Service stop failed or not running"

    # Run installation steps with staged pauses if requested
    _run_upgrade_step "step_detect_system" "System Detection" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_install_dependencies" "Dependency Installation" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_install_pnet" "P-Net Installation" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_build" "Source Build" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_install_files" "File Installation" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_configure_service" "Service Configuration" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_configure_network_storage" "Network/Storage Configuration" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_start_service" "Service Startup" || { rollback_on_failure; return 1; }
    _run_upgrade_step "step_validate" "Validation" || log_warn "Validation had issues"
    step_generate_docs

    # Clean up build directory
    cleanup_build

    # Post-upgrade validation
    log_info "Running post-upgrade validation..."
    if ! post_upgrade_validation; then
        log_warn "Post-upgrade validation found issues"
        if [ $UNATTENDED_MODE -eq 1 ] || [ $CANARY_MODE -eq 1 ]; then
            log_error "Auto-rollback triggered due to validation failure"
            rollback_on_failure
            return 1
        fi
        log_warn "Consider rolling back if problems persist"
    fi

    # Canary mode: Extended testing with stability monitoring
    if [ $CANARY_MODE -eq 1 ]; then
        log_info "CANARY MODE: Running extended tests..."

        # Test API endpoints
        if ! test_upgrade_api_endpoints; then
            log_error "API endpoint test failed. Backend not responding correctly. Initiating rollback."
            rollback_on_failure
            return 1
        fi

        # Test PROFINET connectivity
        test_profinet_connectivity || log_warn "PROFINET test had issues"

        # Monitor service stability for 60 seconds
        log_info "Monitoring service stability (60 seconds)..."
        if ! verify_service_stability 60; then
            log_error "Service stability check failed. Service crashed or unresponsive. Initiating rollback."
            rollback_on_failure
            return 1
        fi

        log_info "CANARY MODE: All extended tests passed"
    fi

    # Compare configuration changes
    if [ -n "$old_config" ] && [ -f "$old_config" ]; then
        local config_diff
        config_diff=$(compare_configuration "$old_config" 2>/dev/null) || true
        if [ -n "$config_diff" ]; then
            log_info "Configuration comparison saved to: $config_diff"
        fi
    fi

    # Verify database migration if applicable
    log_info "Verifying database migration..."
    if ! verify_database_migration; then
        log_warn "Database migration verification had issues"
        if [ $UNATTENDED_MODE -eq 1 ] || [ $CANARY_MODE -eq 1 ]; then
            log_error "Database migration failed. Data integrity at risk. Initiating rollback."
            rollback_on_failure
            return 1
        fi
    fi

    # Generate upgrade report
    local report
    report=$(generate_upgrade_report "$upgrade_start" "$(date -Iseconds)" "completed" 2>/dev/null) || true
    if [ -n "$report" ]; then
        log_info "Upgrade report saved to: $report"
    fi

    # Send upgrade completion notification
    notify_upgrade_complete || log_warn "Could not send upgrade notification"

    log_info "Upgrade completed successfully"
    return 0
}

# Helper function to run upgrade steps with optional staging
_run_upgrade_step() {
    local step_func="$1"
    local step_name="$2"

    if [ $STAGED_MODE -eq 1 ]; then
        log_info "=== STAGED: $step_name ==="
        if ! confirm "Proceed with $step_name?"; then
            log_info "Upgrade cancelled at: $step_name"
            return 1
        fi
    fi

    $step_func
}

# Rollback on failure during upgrade
rollback_on_failure() {
    if [ -n "$ROLLBACK_POINT" ]; then
        log_error "Installation failed. System may be in inconsistent state. Initiating rollback..."
        if perform_rollback "$ROLLBACK_POINT"; then
            log_info "Rollback successful. System restored to pre-upgrade state."
        else
            log_error "Standard rollback failed. Trying emergency rollback..."
            if emergency_rollback; then
                log_info "Emergency rollback completed. Verify system manually."
            else
                log_error "Emergency rollback failed. Manual intervention required. Run: ./install.sh --selective-rollback"
            fi
        fi
    fi
}

# =============================================================================
# Uninstall Process
# =============================================================================

do_uninstall() {
    log_info "Starting uninstallation process..."

    local manifest_file="/tmp/water-controller-uninstall-manifest-$(date +%Y%m%d_%H%M%S).txt"
    # Use global arrays so helper functions can append
    UNINSTALL_REMOVED_ITEMS=()
    UNINSTALL_PRESERVED_ITEMS=()
    local errors=0

    if [ $DRY_RUN -eq 1 ]; then
        log_info "[DRY RUN] Would uninstall Water Controller"
        log_info "  - Stop and disable service"
        log_info "  - Remove $INSTALL_DIR"
        log_info "  - Remove service file"
        log_info "  - Remove logrotate config"
        log_info "  - Remove tmpfs mount from fstab"
        if [ $KEEP_DATA -eq 0 ]; then
            log_info "  - Remove $CONFIG_DIR (with confirmation)"
            log_info "  - Remove $DATA_DIR (with confirmation)"
            log_info "  - Remove $LOG_DIR (with confirmation)"
            log_info "  - Remove $BACKUP_DIR (with confirmation)"
        else
            log_info "  - Preserve $CONFIG_DIR (--keep-data)"
            log_info "  - Preserve $DATA_DIR (--keep-data)"
            log_info "  - Preserve $LOG_DIR (--keep-data)"
            log_info "  - Preserve $BACKUP_DIR (--keep-data)"
        fi
        if [ $PURGE_MODE -eq 1 ]; then
            log_info "  - Remove P-Net libraries and headers (--purge)"
            log_info "  - Remove firewall rules (--purge)"
            log_info "  - Remove udev rules (--purge)"
            log_info "  - Remove network configuration (--purge)"
        fi
        return 0
    fi

    # Confirm uninstallation
    local confirm_msg="This will remove the Water Controller installation."
    if [ $PURGE_MODE -eq 1 ]; then
        confirm_msg="$confirm_msg Including P-Net libraries, firewall rules, and udev rules (PURGE mode)."
    fi
    if [ $KEEP_DATA -eq 1 ]; then
        confirm_msg="$confirm_msg Configuration and data will be PRESERVED."
    fi
    confirm_msg="$confirm_msg Continue?"

    if ! confirm "$confirm_msg" "n"; then
        log_info "Uninstallation cancelled"
        return 0
    fi

    # Initialize manifest
    {
        echo "Water Controller Uninstall Manifest"
        echo "===================================="
        echo "Date: $(date -Iseconds)"
        echo "Mode: ${PURGE_MODE:+PURGE }${KEEP_DATA:+KEEP-DATA }STANDARD"
        echo ""
        echo "Removed Items:"
    } > "$manifest_file"

    # Stop service
    log_info "Stopping service..."
    if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl stop water-controller.service 2>/dev/null || true
        sudo systemctl disable water-controller.service 2>/dev/null || true
        UNINSTALL_REMOVED_ITEMS+=("Service: water-controller.service (stopped and disabled)")
    fi

    # Remove service file
    log_info "Removing service file..."
    if [ -f /etc/systemd/system/water-controller.service ]; then
        sudo rm -f /etc/systemd/system/water-controller.service
        UNINSTALL_REMOVED_ITEMS+=("File: /etc/systemd/system/water-controller.service")
    fi
    sudo systemctl daemon-reload 2>/dev/null || true

    # Remove installation directory
    log_info "Removing installation directory..."
    if [ -d "$INSTALL_DIR" ]; then
        sudo rm -rf "$INSTALL_DIR" || ((errors++))
        UNINSTALL_REMOVED_ITEMS+=("Directory: $INSTALL_DIR")
    fi

    # Handle configuration based on --keep-data flag
    if [ -d "$CONFIG_DIR" ]; then
        if [ $KEEP_DATA -eq 1 ]; then
            log_info "Configuration preserved at $CONFIG_DIR (--keep-data)"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: $CONFIG_DIR")
        elif confirm "Remove configuration directory ($CONFIG_DIR)?" "n"; then
            sudo rm -rf "$CONFIG_DIR" || ((errors++))
            UNINSTALL_REMOVED_ITEMS+=("Directory: $CONFIG_DIR")
        else
            log_info "Configuration preserved at $CONFIG_DIR"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: $CONFIG_DIR")
        fi
    fi

    # Handle data directory based on --keep-data flag
    if [ -d "$DATA_DIR" ]; then
        if [ $KEEP_DATA -eq 1 ]; then
            log_info "Data preserved at $DATA_DIR (--keep-data)"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: $DATA_DIR")
        elif confirm "Remove data directory ($DATA_DIR)? This includes the database!" "n"; then
            sudo rm -rf "$DATA_DIR" || ((errors++))
            UNINSTALL_REMOVED_ITEMS+=("Directory: $DATA_DIR")
        else
            log_info "Data preserved at $DATA_DIR"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: $DATA_DIR")
        fi
    fi

    # Handle logs based on --keep-data flag
    if [ -d "$LOG_DIR" ]; then
        if [ $KEEP_DATA -eq 1 ]; then
            log_info "Logs preserved at $LOG_DIR (--keep-data)"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: $LOG_DIR")
        elif confirm "Remove log directory ($LOG_DIR)?" "n"; then
            sudo rm -rf "$LOG_DIR" || ((errors++))
            UNINSTALL_REMOVED_ITEMS+=("Directory: $LOG_DIR")
        else
            log_info "Logs preserved at $LOG_DIR"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: $LOG_DIR")
        fi
    fi

    # Handle backups based on --keep-data flag
    if [ -d "$BACKUP_DIR" ]; then
        if [ $KEEP_DATA -eq 1 ]; then
            log_info "Backups preserved at $BACKUP_DIR (--keep-data)"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: $BACKUP_DIR")
        elif confirm "Remove backup directory ($BACKUP_DIR)?" "n"; then
            sudo rm -rf "$BACKUP_DIR" || ((errors++))
            UNINSTALL_REMOVED_ITEMS+=("Directory: $BACKUP_DIR")
        else
            log_info "Backups preserved at $BACKUP_DIR"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: $BACKUP_DIR")
        fi
    fi

    # Ask about service user (only if not keeping data)
    if [ $KEEP_DATA -eq 0 ]; then
        if id water-controller >/dev/null 2>&1; then
            if confirm "Remove service user (water-controller)?" "n"; then
                sudo userdel water-controller 2>/dev/null || ((errors++))
                UNINSTALL_REMOVED_ITEMS+=("User: water-controller")
            else
                log_info "Service user preserved"
                UNINSTALL_PRESERVED_ITEMS+=("User: water-controller")
            fi
        fi
    fi

    # Remove logrotate config
    if [ -f /etc/logrotate.d/water-controller ]; then
        sudo rm -f /etc/logrotate.d/water-controller 2>/dev/null || true
        UNINSTALL_REMOVED_ITEMS+=("File: /etc/logrotate.d/water-controller")
    fi

    # Remove tmpfs mount from fstab
    if grep -q "water-controller" /etc/fstab 2>/dev/null; then
        log_info "Removing tmpfs mount from fstab..."
        sudo sed -i '/water-controller/d' /etc/fstab 2>/dev/null || true
        UNINSTALL_REMOVED_ITEMS+=("Fstab entry: water-controller tmpfs")
    fi

    # Unmount tmpfs if mounted
    if mountpoint -q /run/water-controller 2>/dev/null; then
        sudo umount /run/water-controller 2>/dev/null || true
        UNINSTALL_REMOVED_ITEMS+=("Mount: /run/water-controller")
    fi

    # =========================================================================
    # PURGE MODE: Remove P-Net, firewall rules, udev rules, network config
    # =========================================================================
    if [ $PURGE_MODE -eq 1 ]; then
        log_info "PURGE MODE: Removing additional components..."

        # Remove P-Net libraries
        _uninstall_pnet_libraries || ((errors++))

        # Remove firewall rules
        _uninstall_firewall_rules || ((errors++))

        # Remove udev rules
        _uninstall_udev_rules || ((errors++))

        # Remove network configuration (optional, with confirmation)
        if confirm "Remove Water Controller network configuration (static IP, etc.)?" "n"; then
            _uninstall_network_config || ((errors++))
        else
            UNINSTALL_PRESERVED_ITEMS+=("Network configuration")
        fi
    fi

    # Write manifest
    for item in "${UNINSTALL_REMOVED_ITEMS[@]}"; do
        echo "  - $item" >> "$manifest_file"
    done

    if [ ${#UNINSTALL_PRESERVED_ITEMS[@]} -gt 0 ]; then
        echo "" >> "$manifest_file"
        echo "Preserved Items:" >> "$manifest_file"
        for item in "${UNINSTALL_PRESERVED_ITEMS[@]}"; do
            echo "  - $item" >> "$manifest_file"
        done
    fi

    echo "" >> "$manifest_file"
    echo "Errors: $errors" >> "$manifest_file"
    echo "Manifest saved to: $manifest_file" >> "$manifest_file"

    log_info "Uninstall manifest saved to: $manifest_file"

    if [ $errors -eq 0 ]; then
        log_info "Uninstallation completed successfully"
    else
        log_warn "Uninstallation completed with $errors errors"
    fi

    return 0
}

# =============================================================================
# Uninstall Helper Functions
# =============================================================================

# Remove P-Net libraries and related files
_uninstall_pnet_libraries() {
    log_info "Removing P-Net libraries..."
    local removed=0

    # P-Net library locations
    local pnet_lib_paths=(
        "/usr/local/lib/libpnet.so"
        "/usr/local/lib/libpnet.so.*"
        "/usr/local/lib/libpnet.a"
        "/usr/lib/libpnet.so"
        "/usr/lib/libpnet.so.*"
        "/usr/lib/libpnet.a"
    )

    # Remove library files
    for pattern in "${pnet_lib_paths[@]}"; do
        # shellcheck disable=SC2086
        for lib_file in $pattern; do
            if [ -f "$lib_file" ]; then
                sudo rm -f "$lib_file" 2>/dev/null && {
                    log_info "  Removed: $lib_file"
                    UNINSTALL_REMOVED_ITEMS+=("P-Net: $lib_file")
                    ((removed++))
                }
            fi
        done
    done

    # Remove P-Net headers
    local pnet_include_paths=(
        "/usr/local/include/pnet"
        "/usr/local/include/pnet_api.h"
        "/usr/include/pnet"
        "/usr/include/pnet_api.h"
    )

    for path in "${pnet_include_paths[@]}"; do
        if [ -e "$path" ]; then
            sudo rm -rf "$path" 2>/dev/null && {
                log_info "  Removed: $path"
                UNINSTALL_REMOVED_ITEMS+=("P-Net: $path")
                ((removed++))
            }
        fi
    done

    # Remove P-Net config directory
    if [ -d "/etc/pnet" ]; then
        sudo rm -rf /etc/pnet 2>/dev/null && {
            log_info "  Removed: /etc/pnet"
            UNINSTALL_REMOVED_ITEMS+=("P-Net: /etc/pnet")
            ((removed++))
        }
    fi

    # Remove P-Net sample application
    if [ -d "/opt/pnet-sample" ]; then
        sudo rm -rf /opt/pnet-sample 2>/dev/null && {
            log_info "  Removed: /opt/pnet-sample"
            UNINSTALL_REMOVED_ITEMS+=("P-Net: /opt/pnet-sample")
            ((removed++))
        }
    fi

    # Remove P-Net pkg-config file
    local pkgconfig_paths=(
        "/usr/local/lib/pkgconfig/pnet.pc"
        "/usr/lib/pkgconfig/pnet.pc"
    )

    for pc_file in "${pkgconfig_paths[@]}"; do
        if [ -f "$pc_file" ]; then
            sudo rm -f "$pc_file" 2>/dev/null && {
                log_info "  Removed: $pc_file"
                UNINSTALL_REMOVED_ITEMS+=("P-Net: $pc_file")
                ((removed++))
            }
        fi
    done

    # Update library cache
    if [ $removed -gt 0 ]; then
        sudo ldconfig 2>/dev/null || true
        log_info "  Updated library cache (ldconfig)"
    fi

    log_info "P-Net cleanup complete ($removed items removed)"
    return 0
}

# Remove firewall rules added by Water Controller
_uninstall_firewall_rules() {
    log_info "Removing firewall rules..."

    # Detect and clean up based on firewall system
    if command -v ufw >/dev/null 2>&1 && sudo ufw status 2>/dev/null | grep -q "Status: active"; then
        log_info "  Cleaning UFW rules..."
        sudo ufw delete allow 8000/tcp 2>/dev/null || true
        sudo ufw delete allow 34964/udp 2>/dev/null || true
        sudo ufw delete allow 34962:34963/tcp 2>/dev/null || true
        UNINSTALL_REMOVED_ITEMS+=("Firewall: UFW rules (ports 8000, 34962-34964)")
        log_info "  UFW rules removed"

    elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active firewalld >/dev/null 2>&1; then
        log_info "  Cleaning firewalld rules..."
        sudo firewall-cmd --permanent --remove-port=8000/tcp 2>/dev/null || true
        sudo firewall-cmd --permanent --remove-port=34964/udp 2>/dev/null || true
        sudo firewall-cmd --permanent --remove-port=34962-34963/tcp 2>/dev/null || true
        sudo firewall-cmd --reload 2>/dev/null || true
        UNINSTALL_REMOVED_ITEMS+=("Firewall: firewalld rules (ports 8000, 34962-34964)")
        log_info "  firewalld rules removed"

    elif command -v nft >/dev/null 2>&1; then
        log_info "  Cleaning nftables rules..."
        sudo nft delete table inet water_controller 2>/dev/null || true
        if [ -f /etc/nftables.d/water-controller.nft ]; then
            sudo rm -f /etc/nftables.d/water-controller.nft 2>/dev/null || true
            UNINSTALL_REMOVED_ITEMS+=("Firewall: /etc/nftables.d/water-controller.nft")
            log_info "  Removed: /etc/nftables.d/water-controller.nft"
        fi
        UNINSTALL_REMOVED_ITEMS+=("Firewall: nftables table water_controller")
        log_info "  nftables rules removed"

    elif command -v iptables >/dev/null 2>&1; then
        log_info "  Cleaning iptables rules..."
        sudo iptables -D INPUT -p tcp --dport 8000 -j ACCEPT 2>/dev/null || true
        sudo iptables -D INPUT -p udp --dport 34964 -j ACCEPT 2>/dev/null || true
        sudo iptables -D INPUT -p tcp --dport 34962:34963 -j ACCEPT 2>/dev/null || true
        if command -v iptables-save >/dev/null 2>&1; then
            if [ -d /etc/iptables ]; then
                sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null 2>/dev/null
            elif command -v netfilter-persistent >/dev/null 2>&1; then
                sudo netfilter-persistent save 2>/dev/null || true
            fi
        fi
        UNINSTALL_REMOVED_ITEMS+=("Firewall: iptables rules (ports 8000, 34962-34964)")
        log_info "  iptables rules removed"
    else
        log_info "  No active firewall detected, skipping"
    fi

    return 0
}

# Remove udev rules added by Water Controller
_uninstall_udev_rules() {
    log_info "Removing udev rules..."

    local udev_rules=(
        "/etc/udev/rules.d/99-water-controller-network.rules"
        "/etc/udev/rules.d/99-water-controller.rules"
        "/etc/udev/rules.d/99-pnet.rules"
    )

    local removed=0
    for rule_file in "${udev_rules[@]}"; do
        if [ -f "$rule_file" ]; then
            sudo rm -f "$rule_file" 2>/dev/null && {
                log_info "  Removed: $rule_file"
                UNINSTALL_REMOVED_ITEMS+=("udev: $rule_file")
                ((removed++))
            }
        fi
    done

    # Reload udev rules if any were removed
    if [ $removed -gt 0 ]; then
        sudo udevadm control --reload-rules 2>/dev/null || true
        sudo udevadm trigger 2>/dev/null || true
        log_info "  Reloaded udev rules"
    fi

    log_info "udev cleanup complete ($removed rules removed)"
    return 0
}

# Remove network configuration added by Water Controller
_uninstall_network_config() {
    log_info "Removing network configuration..."

    # Remove systemd-networkd config
    local networkd_configs=(
        "/etc/systemd/network/10-water-controller-*.network"
    )
    for pattern in "${networkd_configs[@]}"; do
        # shellcheck disable=SC2086
        for config_file in $pattern; do
            if [ -f "$config_file" ]; then
                sudo rm -f "$config_file" 2>/dev/null && {
                    log_info "  Removed: $config_file"
                    UNINSTALL_REMOVED_ITEMS+=("Network: $config_file")
                }
            fi
        done
    done

    # Remove NetworkManager connections
    if command -v nmcli >/dev/null 2>&1; then
        local nm_connections
        nm_connections=$(nmcli -t -f NAME connection show 2>/dev/null | grep "water-controller")
        while IFS= read -r conn; do
            if [ -n "$conn" ]; then
                sudo nmcli connection delete "$conn" 2>/dev/null && {
                    log_info "  Removed NetworkManager connection: $conn"
                    UNINSTALL_REMOVED_ITEMS+=("Network: NetworkManager connection $conn")
                }
            fi
        done <<< "$nm_connections"
    fi

    # Remove dhcpcd configuration entries
    if [ -f /etc/dhcpcd.conf ]; then
        if grep -q "Water-Controller" /etc/dhcpcd.conf 2>/dev/null; then
            log_info "  Cleaning dhcpcd.conf..."
            sudo cp /etc/dhcpcd.conf /etc/dhcpcd.conf.pre-uninstall 2>/dev/null
            sudo sed -i '/# Water-Controller/,/^interface\|^$/d' /etc/dhcpcd.conf 2>/dev/null || true
            UNINSTALL_REMOVED_ITEMS+=("Network: dhcpcd.conf entries (backup saved)")
            log_info "  Cleaned dhcpcd.conf (backup: /etc/dhcpcd.conf.pre-uninstall)"
        fi
    fi

    # Remove interfaces.d config
    local interfaces_d_configs=(
        "/etc/network/interfaces.d/water-controller-*"
    )
    for pattern in "${interfaces_d_configs[@]}"; do
        # shellcheck disable=SC2086
        for config_file in $pattern; do
            if [ -f "$config_file" ]; then
                sudo rm -f "$config_file" 2>/dev/null && {
                    log_info "  Removed: $config_file"
                    UNINSTALL_REMOVED_ITEMS+=("Network: $config_file")
                }
            fi
        done
    done

    log_info "Network configuration cleanup complete"
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
