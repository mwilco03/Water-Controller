#!/bin/bash
# =============================================================================
# Water-Controller Bootstrap Script
# =============================================================================
# One-liner entry point for installation, upgrade, and removal.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | bash
#   curl -fsSL .../bootstrap.sh | bash -s -- install
#   curl -fsSL .../bootstrap.sh | bash -s -- upgrade
#   curl -fsSL .../bootstrap.sh | bash -s -- remove
#   curl -fsSL .../bootstrap.sh | bash -s -- install --branch develop
#   curl -fsSL .../bootstrap.sh | bash -s -- upgrade --dry-run
#   curl -fsSL .../bootstrap.sh | bash -s -- remove --keep-config
#
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
# =============================================================================

set -euo pipefail

# =============================================================================
# Constants
# =============================================================================

readonly BOOTSTRAP_VERSION="1.0.0"
readonly REPO_URL="https://github.com/mwilco03/Water-Controller.git"
readonly REPO_RAW_URL="https://raw.githubusercontent.com/mwilco03/Water-Controller"
readonly INSTALL_DIR="/opt/water-controller"
readonly VERSION_FILE="$INSTALL_DIR/.version"
readonly MANIFEST_FILE="$INSTALL_DIR/.manifest"
readonly CONFIG_DIR="/etc/water-controller"
readonly DATA_DIR="/var/lib/water-controller"
readonly LOG_DIR="/var/log/water-controller"
readonly MIN_DISK_SPACE_MB=2048
readonly REQUIRED_TOOLS="git curl systemctl"

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# =============================================================================
# Logging Functions
# =============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1" >&2
}

# =============================================================================
# System Detection
# =============================================================================

# Detect current system state
# Returns: fresh | installed | corrupted
detect_system_state() {
    if [[ ! -d "$INSTALL_DIR" ]]; then
        echo "fresh"
        return 0
    fi

    # Check for version file
    if [[ -f "$VERSION_FILE" ]]; then
        # Validate version file is valid JSON
        if command -v jq &>/dev/null && jq -e . "$VERSION_FILE" &>/dev/null; then
            echo "installed"
            return 0
        elif grep -q '"commit_sha"' "$VERSION_FILE" 2>/dev/null; then
            # Fallback for systems without jq
            echo "installed"
            return 0
        fi
    fi

    # Check for partial installation indicators
    if [[ -d "$INSTALL_DIR/venv" ]] || [[ -d "$INSTALL_DIR/web" ]] || \
       [[ -d "$INSTALL_DIR/app" ]] || [[ -f "/etc/systemd/system/water-controller.service" ]]; then
        echo "corrupted"
        return 0
    fi

    # Directory exists but empty or unknown
    if [[ -z "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]]; then
        echo "fresh"
    else
        echo "corrupted"
    fi
}

# Get installed version info
get_installed_version() {
    if [[ ! -f "$VERSION_FILE" ]]; then
        echo ""
        return 1
    fi

    if command -v jq &>/dev/null; then
        jq -r '.version // "unknown"' "$VERSION_FILE" 2>/dev/null || echo "unknown"
    else
        grep -oP '"version"\s*:\s*"\K[^"]+' "$VERSION_FILE" 2>/dev/null || echo "unknown"
    fi
}

# Get installed commit SHA
get_installed_sha() {
    if [[ ! -f "$VERSION_FILE" ]]; then
        echo ""
        return 1
    fi

    if command -v jq &>/dev/null; then
        jq -r '.commit_sha // ""' "$VERSION_FILE" 2>/dev/null
    else
        grep -oP '"commit_sha"\s*:\s*"\K[^"]+' "$VERSION_FILE" 2>/dev/null
    fi
}

# =============================================================================
# Validation Functions
# =============================================================================

# Check if running as root or with sudo capability
check_root() {
    if [[ $EUID -ne 0 ]]; then
        if command -v sudo &>/dev/null && sudo -n true 2>/dev/null; then
            log_info "Will use sudo for privileged operations"
            return 0
        else
            log_error "This script must be run as root or with sudo capability"
            log_info "Run with: sudo bash -c 'curl -fsSL ... | bash'"
            return 1
        fi
    fi
    return 0
}

# Check required tools are present
check_required_tools() {
    local missing=()

    for tool in $REQUIRED_TOOLS; do
        if ! command -v "$tool" &>/dev/null; then
            missing+=("$tool")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing[*]}"
        log_info "Install with: sudo apt-get install ${missing[*]}"
        return 1
    fi

    return 0
}

# Check network connectivity to GitHub
check_network() {
    log_info "Checking network connectivity..."

    if ! curl -fsSL --connect-timeout 10 "https://github.com" &>/dev/null; then
        log_error "Cannot reach GitHub. Check your network connection."
        return 1
    fi

    return 0
}

# Check disk space
check_disk_space() {
    local target_dir="${1:-/opt}"
    local required_mb="${2:-$MIN_DISK_SPACE_MB}"

    # Get parent directory if target doesn't exist
    while [[ ! -d "$target_dir" ]] && [[ "$target_dir" != "/" ]]; do
        target_dir="$(dirname "$target_dir")"
    done

    local available_mb
    available_mb=$(df -m "$target_dir" 2>/dev/null | awk 'NR==2 {print $4}')

    if [[ -z "$available_mb" ]] || [[ "$available_mb" -lt "$required_mb" ]]; then
        log_error "Insufficient disk space: ${available_mb:-0}MB available, ${required_mb}MB required"
        return 1
    fi

    log_info "Disk space check passed: ${available_mb}MB available"
    return 0
}

# Run all validation checks
validate_environment() {
    log_step "Validating environment..."

    check_root || return 1
    check_required_tools || return 1
    check_network || return 1
    check_disk_space "/opt" "$MIN_DISK_SPACE_MB" || return 1

    log_info "Environment validation passed"
    return 0
}

# =============================================================================
# Pre-Flight Version Check (Zero Disk Writes)
# =============================================================================

# Get remote ref SHA using git ls-remote (no disk writes)
# This is the preferred method for version checking
get_remote_sha() {
    local branch="${1:-main}"
    local ref="refs/heads/$branch"

    # Handle tag references
    if [[ "$branch" == v* ]]; then
        ref="refs/tags/$branch"
    fi

    git ls-remote "$REPO_URL" "$ref" 2>/dev/null | awk '{print $1}'
}

# Pre-flight check: determine if upgrade is needed
# Returns: 0 if upgrade needed, 1 if already current, 2 on error
preflight_version_check() {
    local target_branch="${1:-main}"

    log_step "Running pre-flight version check (no disk writes)..."

    local local_sha
    local remote_sha

    # Get installed version
    local_sha=$(get_installed_sha)
    if [[ -z "$local_sha" ]]; then
        log_info "No version file found, treating as fresh install"
        return 0
    fi

    log_info "Installed commit: ${local_sha:0:12}"

    # Get remote version using git ls-remote (no clone needed)
    remote_sha=$(get_remote_sha "$target_branch")
    if [[ -z "$remote_sha" ]]; then
        log_error "Could not fetch remote version - network error or invalid branch"
        return 2
    fi

    log_info "Remote commit:    ${remote_sha:0:12}"

    # Compare
    if [[ "$local_sha" == "$remote_sha" ]]; then
        log_info "Already at latest version (${remote_sha:0:12}), nothing to do"
        return 1
    fi

    log_info "Update available: ${local_sha:0:12} -> ${remote_sha:0:12}"
    return 0
}

# =============================================================================
# Staging Functions
# =============================================================================

# Create staging directory
create_staging_dir() {
    local action="${1:-install}"
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)

    # Use /tmp or /var/tmp depending on space
    local tmp_base="/tmp"
    local tmp_space
    tmp_space=$(df -m /tmp 2>/dev/null | awk 'NR==2 {print $4}')

    if [[ -n "$tmp_space" ]] && [[ "$tmp_space" -lt 1024 ]]; then
        tmp_base="/var/tmp"
    fi

    local staging_dir="${tmp_base}/water-controller-${action}-${timestamp}-$$"
    mkdir -p "$staging_dir"
    echo "$staging_dir"
}

# Clone repository to staging
clone_to_staging() {
    local staging_dir="$1"
    local branch="${2:-main}"

    log_step "Cloning repository to staging..."

    if ! git clone --depth 1 --branch "$branch" "$REPO_URL" "$staging_dir/repo" 2>&1; then
        log_error "Failed to clone repository"
        return 1
    fi

    # Verify clone integrity
    if [[ ! -d "$staging_dir/repo/.git" ]]; then
        log_error "Clone verification failed: .git directory missing"
        return 1
    fi

    # Get commit info
    local commit_sha
    commit_sha=$(cd "$staging_dir/repo" && git rev-parse HEAD)
    local commit_short="${commit_sha:0:7}"

    log_info "Cloned successfully: $commit_short"

    # Store commit info for later
    echo "$commit_sha" > "$staging_dir/.commit_sha"
    echo "$branch" > "$staging_dir/.branch"

    return 0
}

# Cleanup staging directory
cleanup_staging() {
    local staging_dir="$1"

    if [[ -n "$staging_dir" ]] && [[ -d "$staging_dir" ]]; then
        log_info "Cleaning up staging directory..."
        rm -rf "$staging_dir"
    fi
}

# =============================================================================
# Action Handlers
# =============================================================================

# Install action
do_install() {
    local branch="${1:-main}"
    local force="${2:-false}"

    local state
    state=$(detect_system_state)

    case "$state" in
        fresh)
            log_info "Fresh system detected, proceeding with installation"
            ;;
        installed)
            if [[ "$force" == "true" ]]; then
                log_warn "Existing installation found, --force specified, reinstalling"
            else
                log_error "Water-Controller is already installed"
                log_info "Use 'upgrade' to update, or 'install --force' to reinstall"
                log_info "Current version: $(get_installed_version)"
                return 1
            fi
            ;;
        corrupted)
            log_warn "Corrupted installation detected, will attempt to fix"
            ;;
    esac

    # Create staging
    local staging_dir
    staging_dir=$(create_staging_dir "install")
    trap "cleanup_staging '$staging_dir'" EXIT

    # Clone to staging
    clone_to_staging "$staging_dir" "$branch" || return 1

    # Execute install script from staging
    log_step "Running installation script..."

    local install_script="$staging_dir/repo/scripts/install.sh"
    if [[ ! -f "$install_script" ]]; then
        log_error "Install script not found in repository"
        return 1
    fi

    chmod +x "$install_script"

    # Pass source directory to install script
    export SOURCE_DIR="$staging_dir/repo"
    export BOOTSTRAP_MODE="true"

    if [[ $EUID -ne 0 ]]; then
        sudo -E bash "$install_script" --source "$staging_dir/repo"
    else
        bash "$install_script" --source "$staging_dir/repo"
    fi

    local result=$?

    if [[ $result -eq 0 ]]; then
        # Write version file
        write_version_file "$staging_dir"
        log_info "Installation completed successfully!"
        log_info "Run 'systemctl status water-controller' to check service status"
    else
        log_error "Installation failed with exit code: $result"
    fi

    return $result
}

# Upgrade action
do_upgrade() {
    local branch="${1:-main}"
    local force="${2:-false}"
    local dry_run="${3:-false}"

    local state
    state=$(detect_system_state)

    case "$state" in
        fresh)
            log_error "No installation found. Use 'install' instead."
            return 1
            ;;
        installed)
            log_info "Existing installation found: $(get_installed_version)"
            ;;
        corrupted)
            log_warn "Corrupted installation detected. Consider 'install --force' instead."
            if [[ "$force" != "true" ]]; then
                return 1
            fi
            ;;
    esac

    # Pre-flight check (no disk writes yet)
    if [[ "$force" != "true" ]]; then
        local preflight_result
        preflight_version_check "$branch"
        preflight_result=$?

        if [[ $preflight_result -eq 1 ]]; then
            # Already at latest version
            return 0
        elif [[ $preflight_result -eq 2 ]]; then
            # Network error - abort unless forced
            log_error "Pre-flight check failed. Use --force to skip version check."
            return 1
        fi
        # preflight_result=0 means update available, continue
    fi

    if [[ "$dry_run" == "true" ]]; then
        log_info "Dry run: would upgrade from $(get_installed_sha | cut -c1-12) to latest"
        return 0
    fi

    # Create staging
    local staging_dir
    staging_dir=$(create_staging_dir "upgrade")
    trap "cleanup_staging '$staging_dir'" EXIT

    # Clone to staging
    clone_to_staging "$staging_dir" "$branch" || return 1

    # Execute upgrade script from staging
    log_step "Running upgrade script..."

    local upgrade_script="$staging_dir/repo/scripts/upgrade.sh"
    if [[ ! -f "$upgrade_script" ]]; then
        # Fall back to install script with upgrade mode
        upgrade_script="$staging_dir/repo/scripts/install.sh"
        log_info "Using install script in upgrade mode"
    fi

    if [[ ! -f "$upgrade_script" ]]; then
        log_error "Neither upgrade.sh nor install.sh found in repository"
        return 1
    fi

    chmod +x "$upgrade_script"

    # Pass source directory to upgrade script
    export SOURCE_DIR="$staging_dir/repo"
    export BOOTSTRAP_MODE="true"
    export UPGRADE_MODE="true"

    if [[ $EUID -ne 0 ]]; then
        sudo -E bash "$upgrade_script" --source "$staging_dir/repo" --upgrade
    else
        bash "$upgrade_script" --source "$staging_dir/repo" --upgrade
    fi

    local result=$?

    if [[ $result -eq 0 ]]; then
        # Write version file
        write_version_file "$staging_dir"
        log_info "Upgrade completed successfully!"
    else
        log_error "Upgrade failed with exit code: $result"
    fi

    return $result
}

# Remove action
do_remove() {
    local keep_config="${1:-false}"
    local yes="${2:-false}"

    local state
    state=$(detect_system_state)

    if [[ "$state" == "fresh" ]]; then
        log_info "No installation found, nothing to remove"
        return 0
    fi

    if [[ "$yes" != "true" ]]; then
        echo ""
        echo "This will remove Water-Controller from this system."
        if [[ "$keep_config" == "true" ]]; then
            echo "Configuration files will be preserved."
        else
            echo "ALL data and configuration will be DELETED."
        fi
        echo ""
        read -r -p "Are you sure? [y/N] " response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            log_info "Removal cancelled"
            return 0
        fi
    fi

    log_step "Removing Water-Controller..."

    # Stop and disable services
    log_info "Stopping services..."
    local services=(
        "water-controller"
        "water-controller-api"
        "water-controller-ui"
        "water-controller-frontend"
        "water-controller-hmi"
    )

    for svc in "${services[@]}"; do
        if systemctl is-active "${svc}.service" &>/dev/null; then
            if [[ $EUID -ne 0 ]]; then
                sudo systemctl stop "${svc}.service" 2>/dev/null || true
            else
                systemctl stop "${svc}.service" 2>/dev/null || true
            fi
        fi
        if systemctl is-enabled "${svc}.service" &>/dev/null; then
            if [[ $EUID -ne 0 ]]; then
                sudo systemctl disable "${svc}.service" 2>/dev/null || true
            else
                systemctl disable "${svc}.service" 2>/dev/null || true
            fi
        fi
    done

    # Remove systemd unit files
    log_info "Removing systemd unit files..."
    for svc in "${services[@]}"; do
        local unit_file="/etc/systemd/system/${svc}.service"
        if [[ -f "$unit_file" ]]; then
            if [[ $EUID -ne 0 ]]; then
                sudo rm -f "$unit_file"
            else
                rm -f "$unit_file"
            fi
        fi
    done

    # Reload systemd
    if [[ $EUID -ne 0 ]]; then
        sudo systemctl daemon-reload 2>/dev/null || true
    else
        systemctl daemon-reload 2>/dev/null || true
    fi

    # Backup config if requested
    if [[ "$keep_config" == "true" ]] && [[ -d "$CONFIG_DIR" ]]; then
        local backup_dir="/var/backups/water-controller-$(date +%Y%m%d_%H%M%S)"
        log_info "Backing up configuration to: $backup_dir"
        if [[ $EUID -ne 0 ]]; then
            sudo mkdir -p "$backup_dir"
            sudo cp -r "$CONFIG_DIR" "$backup_dir/"
        else
            mkdir -p "$backup_dir"
            cp -r "$CONFIG_DIR" "$backup_dir/"
        fi
    fi

    # Remove installation directory
    log_info "Removing installation directory..."
    if [[ -d "$INSTALL_DIR" ]]; then
        if [[ $EUID -ne 0 ]]; then
            sudo rm -rf "$INSTALL_DIR"
        else
            rm -rf "$INSTALL_DIR"
        fi
    fi

    # Remove config directory (unless keep_config)
    if [[ "$keep_config" != "true" ]] && [[ -d "$CONFIG_DIR" ]]; then
        log_info "Removing configuration directory..."
        if [[ $EUID -ne 0 ]]; then
            sudo rm -rf "$CONFIG_DIR"
        else
            rm -rf "$CONFIG_DIR"
        fi
    fi

    # Remove data directory (unless keep_config)
    if [[ "$keep_config" != "true" ]] && [[ -d "$DATA_DIR" ]]; then
        log_info "Removing data directory..."
        if [[ $EUID -ne 0 ]]; then
            sudo rm -rf "$DATA_DIR"
        else
            rm -rf "$DATA_DIR"
        fi
    fi

    # Remove log directory
    if [[ -d "$LOG_DIR" ]]; then
        log_info "Removing log directory..."
        if [[ $EUID -ne 0 ]]; then
            sudo rm -rf "$LOG_DIR"
        else
            rm -rf "$LOG_DIR"
        fi
    fi

    log_info "Removal completed"

    if [[ "$keep_config" == "true" ]] && [[ -n "${backup_dir:-}" ]]; then
        log_info "Configuration preserved in: $backup_dir"
    fi

    log_info "To reinstall: curl -fsSL $REPO_RAW_URL/main/bootstrap.sh | bash"

    return 0
}

# Write version metadata file
write_version_file() {
    local staging_dir="$1"

    local commit_sha=""
    local branch=""
    local version=""
    local tag=""

    if [[ -f "$staging_dir/.commit_sha" ]]; then
        commit_sha=$(cat "$staging_dir/.commit_sha")
    fi

    if [[ -f "$staging_dir/.branch" ]]; then
        branch=$(cat "$staging_dir/.branch")
    fi

    # Try to get version from package.json or pyproject.toml
    if [[ -f "$staging_dir/repo/package.json" ]]; then
        if command -v jq &>/dev/null; then
            version=$(jq -r '.version // "0.0.0"' "$staging_dir/repo/package.json" 2>/dev/null)
        else
            version=$(grep -oP '"version"\s*:\s*"\K[^"]+' "$staging_dir/repo/package.json" 2>/dev/null || echo "0.0.0")
        fi
    fi

    # Get previous version info if exists
    local previous_version=""
    local previous_sha=""
    if [[ -f "$VERSION_FILE" ]]; then
        if command -v jq &>/dev/null; then
            previous_version=$(jq -r '.version // ""' "$VERSION_FILE" 2>/dev/null)
            previous_sha=$(jq -r '.commit_sha // ""' "$VERSION_FILE" 2>/dev/null)
        else
            previous_version=$(grep -oP '"version"\s*:\s*"\K[^"]+' "$VERSION_FILE" 2>/dev/null || echo "")
            previous_sha=$(grep -oP '"commit_sha"\s*:\s*"\K[^"]+' "$VERSION_FILE" 2>/dev/null || echo "")
        fi
    fi

    # Write version file
    local version_content
    version_content=$(cat <<EOF
{
  "schema_version": 1,
  "package": "water-controller",
  "version": "${version:-0.0.0}",
  "commit_sha": "$commit_sha",
  "commit_short": "${commit_sha:0:7}",
  "branch": "$branch",
  "tag": "$tag",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "installed_by": "bootstrap.sh",
  "bootstrap_version": "$BOOTSTRAP_VERSION",
  "previous_version": "$previous_version",
  "previous_sha": "$previous_sha"
}
EOF
)

    if [[ $EUID -ne 0 ]]; then
        echo "$version_content" | sudo tee "$VERSION_FILE" > /dev/null
    else
        echo "$version_content" > "$VERSION_FILE"
    fi

    log_info "Version file written: $VERSION_FILE"
}

# =============================================================================
# Help and Usage
# =============================================================================

show_help() {
    cat <<EOF
Water-Controller Bootstrap Script v$BOOTSTRAP_VERSION

USAGE:
    bootstrap.sh [ACTION] [OPTIONS]

ACTIONS:
    install     Install Water-Controller (default for fresh systems)
    upgrade     Upgrade existing installation (default for installed systems)
    remove      Remove Water-Controller from this system

OPTIONS:
    --branch <name>     Use specific git branch (default: main)
    --force             Force action even if checks fail
    --dry-run           Show what would be done without making changes
    --keep-config       Keep configuration files when removing
    --yes, -y           Answer yes to all prompts
    --help, -h          Show this help message
    --version           Show version information

EXAMPLES:
    # Install or upgrade (smart detection)
    curl -fsSL $REPO_RAW_URL/main/bootstrap.sh | bash

    # Explicit install
    curl -fsSL .../bootstrap.sh | bash -s -- install

    # Install from develop branch
    curl -fsSL .../bootstrap.sh | bash -s -- install --branch develop

    # Upgrade with dry-run
    curl -fsSL .../bootstrap.sh | bash -s -- upgrade --dry-run

    # Force reinstall
    curl -fsSL .../bootstrap.sh | bash -s -- install --force

    # Remove but keep config
    curl -fsSL .../bootstrap.sh | bash -s -- remove --keep-config

ENVIRONMENT:
    INSTALL_DIR         Installation directory (default: /opt/water-controller)
    CONFIG_DIR          Configuration directory (default: /etc/water-controller)

For more information, see: https://github.com/mwilco03/Water-Controller
EOF
}

show_version() {
    echo "Water-Controller Bootstrap v$BOOTSTRAP_VERSION"

    local state
    state=$(detect_system_state)

    if [[ "$state" == "installed" ]]; then
        echo "Installed version: $(get_installed_version)"
        echo "Installed commit:  $(get_installed_sha | cut -c1-12)"
    else
        echo "Installation status: $state"
    fi
}

# =============================================================================
# Main Entry Point
# =============================================================================

main() {
    local action=""
    local branch="main"
    local force="false"
    local dry_run="false"
    local keep_config="false"
    local yes="false"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            install|upgrade|remove)
                action="$1"
                shift
                ;;
            --branch)
                branch="$2"
                shift 2
                ;;
            --force)
                force="true"
                shift
                ;;
            --dry-run)
                dry_run="true"
                shift
                ;;
            --keep-config)
                keep_config="true"
                shift
                ;;
            --yes|-y)
                yes="true"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            --version)
                show_version
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # If no action specified, auto-detect based on system state
    if [[ -z "$action" ]]; then
        local state
        state=$(detect_system_state)

        case "$state" in
            fresh)
                action="install"
                log_info "Fresh system detected, will install"
                ;;
            installed)
                action="upgrade"
                log_info "Existing installation detected, will upgrade"
                ;;
            corrupted)
                log_warn "Corrupted installation detected"
                action="install"
                force="true"
                ;;
        esac
    fi

    # Validate environment (except for remove action which has its own checks)
    if [[ "$action" != "remove" ]]; then
        validate_environment || exit 1
    else
        check_root || exit 1
    fi

    # Execute action
    local exit_code=0
    case "$action" in
        install)
            do_install "$branch" "$force"
            exit_code=$?
            ;;
        upgrade)
            do_upgrade "$branch" "$force" "$dry_run"
            exit_code=$?
            ;;
        remove)
            do_remove "$keep_config" "$yes"
            exit_code=$?
            ;;
        *)
            log_error "Unknown action: $action"
            show_help
            exit 1
            ;;
    esac

    exit $exit_code
}

# Run main if executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
