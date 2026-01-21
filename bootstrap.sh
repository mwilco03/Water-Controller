#!/bin/bash
# =============================================================================
# Water-Controller Bootstrap Script
# =============================================================================
# One-liner entry point for installation, upgrade, and removal.
# This script dynamically loads modular components via curl - no disk writes.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | bash
#   curl -fsSL .../bootstrap.sh | bash -s -- install
#   curl -fsSL .../bootstrap.sh | bash -s -- upgrade
#   curl -fsSL .../bootstrap.sh | bash -s -- remove
#   curl -fsSL .../bootstrap.sh | bash -s -- install --branch develop
#   curl -fsSL .../bootstrap.sh | bash -s -- upgrade --dry-run
#   curl -fsSL .../bootstrap.sh | bash -s -- remove --keep-config
#   curl -fsSL .../bootstrap.sh | bash -s -- fresh --verbose
#
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
# =============================================================================

set -euo pipefail

# =============================================================================
# Module Loading Configuration
# =============================================================================

# Early parse --branch argument before module loading
# This allows: curl ... | bash -s -- fresh --branch feature-branch
_bootstrap_branch="${WTC_BOOTSTRAP_BRANCH:-main}"
_prev_arg=""
for _arg in "$@"; do
    if [[ "$_prev_arg" == "--branch" ]]; then
        _bootstrap_branch="$_arg"
        break
    fi
    _prev_arg="$_arg"
done
unset _arg _prev_arg

readonly BOOTSTRAP_REPO_RAW="https://raw.githubusercontent.com/mwilco03/Water-Controller"
readonly BOOTSTRAP_BRANCH="$_bootstrap_branch"
readonly BOOTSTRAP_LIB_PATH="bootstrap/lib"
unset _bootstrap_branch

# Modules to load in order (order matters due to dependencies)
readonly BOOTSTRAP_MODULES=(
    "constants"
    "logging"
    "helpers"
    "validation"
    "staging"
    "docker"
    "operations"
)

# =============================================================================
# Module Loader
# =============================================================================

# Load a module from remote URL directly into memory (no disk write)
# Uses bash process substitution: source <(curl ...)
load_module() {
    local module_name="$1"
    local module_url="${BOOTSTRAP_REPO_RAW}/${BOOTSTRAP_BRANCH}/${BOOTSTRAP_LIB_PATH}/${module_name}.sh"

    # Check if running locally (for development)
    local script_dir=""
    if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "${BASH_SOURCE[0]}" ]]; then
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        local local_module="${script_dir}/bootstrap/lib/${module_name}.sh"
        if [[ -f "$local_module" ]]; then
            source "$local_module"
            return 0
        fi
    fi

    # Load from remote
    local module_content
    if ! module_content=$(curl -fsSL --connect-timeout 10 --max-time 30 "$module_url" 2>/dev/null); then
        echo "[ERROR] Failed to load module: $module_name from $module_url" >&2
        return 1
    fi

    # Source the content (eval is needed since we have it in a variable)
    eval "$module_content"
}

# Load all modules in order
load_all_modules() {
    local module
    for module in "${BOOTSTRAP_MODULES[@]}"; do
        if ! load_module "$module"; then
            echo "[ERROR] Failed to load required module: $module" >&2
            echo "[ERROR] Check network connectivity and try again" >&2
            exit 1
        fi
    done
}

# =============================================================================
# Help and Version
# =============================================================================

show_help() {
    cat <<EOF
Water-Controller Bootstrap Script v2.0.0 (Modular)

USAGE:
    bootstrap.sh [ACTION] [OPTIONS]

ACTIONS:
    install     Install Water-Controller (default for fresh systems)
    upgrade     Upgrade existing installation (default for installed systems)
    remove      Remove Water-Controller from this system
    wipe        Complete removal: containers, images, volumes, configs, logs
    fresh       Wipe everything and install from scratch (automated)
    reinstall   Wipe and reinstall, preserving configs where possible

DEPLOYMENT MODE:
    --mode baremetal    Install directly on host (systemd services)
    --mode docker       Install using Docker containers

    All actions respect --mode. Default: baremetal for install, docker for fresh/reinstall.

OPTIONS:
    --branch <name>     Use specific git branch (default: main)
    --force             Force action even if checks fail
    --dry-run           Show what would be done without making changes
    --keep-config       Keep configuration files when removing
    --yes, -y           Answer yes to all prompts
    --quiet, -q         Suppress non-essential output (errors still shown)
    --verbose, -v       Show detailed output for debugging
    --help, -h          Show this help message
    --version           Show version information

LOGGING:
    Bootstrap operations are logged to: /var/log/water-controller-bootstrap.log
    Backups are stored in: /var/backups/water-controller

QUICK START:
    # Fresh install (wipe + install from scratch)
    curl -fsSL ${BOOTSTRAP_REPO_RAW}/main/bootstrap.sh | sudo bash -s -- fresh

    # Uninstall (complete removal)
    curl -fsSL ${BOOTSTRAP_REPO_RAW}/main/bootstrap.sh | sudo bash -s -- wipe

    # Reinstall/Upgrade (wipe + install, preserve configs)
    curl -fsSL ${BOOTSTRAP_REPO_RAW}/main/bootstrap.sh | sudo bash -s -- reinstall

EXAMPLES:
    # Install with Docker
    curl -fsSL .../bootstrap.sh | sudo bash -s -- install --mode docker

    # Install from develop branch
    curl -fsSL .../bootstrap.sh | sudo bash -s -- install --branch develop

    # Upgrade with dry-run
    curl -fsSL .../bootstrap.sh | sudo bash -s -- upgrade --dry-run

    # Remove but keep config files
    curl -fsSL .../bootstrap.sh | sudo bash -s -- remove --keep-config

ARCHITECTURE:
    This bootstrap script loads modular components dynamically:
    - constants.sh   : Version, paths, and global state
    - logging.sh     : Log functions (info, warn, error, debug)
    - helpers.sh     : Discovery, privilege helpers, cleanup
    - validation.sh  : System validation and Docker installation
    - staging.sh     : Version checking, staging, backups
    - docker.sh      : Docker deployment functions
    - operations.sh  : Main action handlers
EOF
}

show_version() {
    echo "Water-Controller Bootstrap v2.0.0 (Modular)"
    echo "Repository: https://github.com/mwilco03/Water-Controller"
    echo "Branch: ${BOOTSTRAP_BRANCH}"
    echo ""
    echo "Modules: ${BOOTSTRAP_MODULES[*]}"
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
            install|upgrade|remove|wipe|fresh|reinstall)
                action="$1"
                shift
                ;;
            --mode)
                if [[ "$2" == "baremetal" || "$2" == "docker" ]]; then
                    DEPLOYMENT_MODE="$2"
                    shift 2
                else
                    echo "[ERROR] Invalid mode: $2. Use 'baremetal' or 'docker'" >&2
                    exit 1
                fi
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
            --quiet|-q)
                QUIET_MODE="true"
                shift
                ;;
            --verbose|-v)
                VERBOSE_MODE="true"
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
                echo "[ERROR] Unknown option: $1" >&2
                show_help
                exit 1
                ;;
        esac
    done

    # Initialize global state for module loading
    QUIET_MODE="${QUIET_MODE:-false}"
    VERBOSE_MODE="${VERBOSE_MODE:-false}"
    DEPLOYMENT_MODE="${DEPLOYMENT_MODE:-}"

    # Show loading message
    if [[ "$QUIET_MODE" != "true" ]]; then
        echo "[INFO] Loading bootstrap modules..." >&2
    fi

    # Load all modules
    load_all_modules

    # Initialize logging
    init_logging
    log_debug "Bootstrap started with args: action=$action branch=$branch force=$force dry_run=$dry_run verbose=$VERBOSE_MODE"

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

    # Validate environment (except for remove/wipe actions which have their own checks)
    if [[ "$action" != "remove" ]] && [[ "$action" != "wipe" ]]; then
        validate_environment || exit 1
    else
        check_root || exit 1
    fi

    # Handle wipe/fresh/reinstall actions immediately
    if [[ "$action" == "wipe" ]]; then
        do_wipe
        exit $?
    fi

    if [[ "$action" == "fresh" ]]; then
        do_fresh "$branch"
        exit $?
    fi

    if [[ "$action" == "reinstall" ]]; then
        do_reinstall "$branch"
        exit $?
    fi

    # Handle deployment mode for install action
    if [[ "$action" == "install" && "$DEPLOYMENT_MODE" == "docker" ]]; then
        log_info "Deployment mode: Docker"
        validate_docker_requirements || exit 1
        do_docker_install
        exit $?
    fi

    # Default to baremetal for install if no mode specified
    if [[ "$action" == "install" && -z "$DEPLOYMENT_MODE" ]]; then
        DEPLOYMENT_MODE="baremetal"
        log_info "Deployment mode: Bare-metal (default)"
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
# Handle piped execution where BASH_SOURCE is unset
if [[ -z "${BASH_SOURCE[0]:-}" ]] || [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
