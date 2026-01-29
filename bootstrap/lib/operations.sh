#!/bin/bash
# =============================================================================
# Water-Controller Bootstrap - Main Operations
# =============================================================================
# Core action handlers: install, upgrade, remove, wipe, fresh, reinstall.
# Depends on: all other modules

# Prevent double-sourcing
[[ -n "${_WTC_OPERATIONS_LOADED:-}" ]] && return 0
_WTC_OPERATIONS_LOADED=1

# =============================================================================
# Install Action
# =============================================================================

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
    register_cleanup "$staging_dir"

    # Clone to staging
    clone_to_staging "$staging_dir" "$branch" || return 1

    # Verify checksum if available
    verify_checksum "$staging_dir" "$branch" || {
        log_warn "Checksum verification skipped or failed (non-fatal)"
    }

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

    run_privileged_env bash "$install_script" --source "$staging_dir/repo"

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

# =============================================================================
# Upgrade Action
# =============================================================================

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

    # Create backup for rollback
    local backup_dir=""
    if [[ -d "$INSTALL_DIR" ]]; then
        backup_dir=$(create_backup "pre-upgrade")
        if [[ -z "$backup_dir" ]]; then
            log_warn "Could not create backup, upgrade will proceed without rollback capability"
        else
            log_info "Backup created: $backup_dir"
        fi
    fi

    # Create staging
    local staging_dir
    staging_dir=$(create_staging_dir "upgrade")
    register_cleanup "$staging_dir"

    # Clone to staging
    clone_to_staging "$staging_dir" "$branch" || return 1

    # Verify checksum if available
    verify_checksum "$staging_dir" "$branch" || {
        log_warn "Checksum verification skipped or failed (non-fatal)"
    }

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

    run_privileged_env bash "$upgrade_script" --source "$staging_dir/repo" --upgrade

    local result=$?

    if [[ $result -eq 0 ]]; then
        # Write version file
        write_version_file "$staging_dir"
        log_info "Upgrade completed successfully!"
        # Clean up backup on success (keep last 2)
        cleanup_old_backups 2

        # Run validation after upgrade
        log_step "Validating upgraded deployment..."
        if [[ -x "$INSTALL_DIR/scripts/validate-deployment.sh" ]]; then
            if "$INSTALL_DIR/scripts/validate-deployment.sh"; then
                log_info "Post-upgrade validation passed"
            else
                log_warn "Post-upgrade validation had failures"
                log_info "Run: $INSTALL_DIR/scripts/fix-database-auth.sh"
            fi
        fi
    else
        log_error "Upgrade failed with exit code: $result"
        if [[ -n "$backup_dir" ]] && [[ -d "$backup_dir" ]]; then
            log_warn "Backup available for manual rollback: $backup_dir"
            log_info "To rollback: sudo rm -rf $INSTALL_DIR && sudo cp -a $backup_dir $INSTALL_DIR"
        fi
    fi

    return $result
}

# =============================================================================
# Remove Action
# =============================================================================

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
        local response
        response=$(prompt_user "Are you sure? [y/N] ")
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

    local svc
    for svc in "${services[@]}"; do
        if systemctl is-active "${svc}.service" &>/dev/null; then
            run_privileged systemctl stop "${svc}.service" 2>/dev/null || true
        fi
        if systemctl is-enabled "${svc}.service" &>/dev/null; then
            run_privileged systemctl disable "${svc}.service" 2>/dev/null || true
        fi
    done

    # Remove systemd unit files
    log_info "Removing systemd unit files..."
    for svc in "${services[@]}"; do
        local unit_file="/etc/systemd/system/${svc}.service"
        if [[ -f "$unit_file" ]]; then
            run_privileged rm -f "$unit_file"
        fi
    done

    # Reload systemd
    run_privileged systemctl daemon-reload 2>/dev/null || true

    # Backup config if requested
    local config_backup_dir=""
    if [[ "$keep_config" == "true" ]] && [[ -d "$CONFIG_DIR" ]]; then
        config_backup_dir="${BACKUP_DIR}/config-$(date +%Y%m%d_%H%M%S)"
        log_info "Backing up configuration to: $config_backup_dir"
        run_privileged mkdir -p "$config_backup_dir"
        run_privileged cp -r "$CONFIG_DIR" "$config_backup_dir/"
    fi

    # Remove installation directory
    log_info "Removing installation directory..."
    if [[ -d "$INSTALL_DIR" ]]; then
        run_privileged rm -rf "$INSTALL_DIR"
    fi

    # Remove config directory (unless keep_config)
    if [[ "$keep_config" != "true" ]] && [[ -d "$CONFIG_DIR" ]]; then
        log_info "Removing configuration directory..."
        run_privileged rm -rf "$CONFIG_DIR"
    fi

    # Remove data directory (unless keep_config)
    if [[ "$keep_config" != "true" ]] && [[ -d "$DATA_DIR" ]]; then
        log_info "Removing data directory..."
        run_privileged rm -rf "$DATA_DIR"
    fi

    # Remove log directory
    if [[ -d "$LOG_DIR" ]]; then
        log_info "Removing log directory..."
        run_privileged rm -rf "$LOG_DIR"
    fi

    log_info "Removal completed"

    if [[ "$keep_config" == "true" ]] && [[ -n "$config_backup_dir" ]]; then
        log_info "Configuration preserved in: $config_backup_dir"
    fi

    log_info "To reinstall: curl -fsSL $REPO_RAW_URL/main/bootstrap.sh | bash"

    return 0
}

# =============================================================================
# Wipe Action - Complete Removal Including Docker
# =============================================================================

do_wipe() {
    log_step "Starting complete system wipe..."
    show_disk_space "Before Wipe"

    # Stop all containers first
    if command -v docker &>/dev/null && docker info &>/dev/null; then
        # Stop containers by name pattern
        local containers
        containers=$(docker ps -aq --filter "name=wtc-" 2>/dev/null || true)
        local container_count=0
        if [[ -n "$containers" ]]; then
            container_count=$(echo "$containers" | wc -w)
            log_info "Stopping $container_count container(s)..."
            if [[ "$VERBOSE_MODE" == "true" ]]; then
                docker stop $containers 2>&1 || true
                docker rm -f $containers 2>&1 || true
            else
                docker stop $containers >/dev/null 2>&1 || true
                docker rm -f $containers >/dev/null 2>&1 || true
            fi
        fi

        # Stop docker compose stack if compose file exists
        if [[ -f "/opt/water-controller/docker/docker-compose.yml" ]]; then
            log_verbose "Stopping docker compose stack..."
            (cd /opt/water-controller/docker && docker compose down -v --remove-orphans 2>/dev/null) || true
        fi
    fi

    # Stop and disable systemd services
    local services=(
        "water-controller"
        "water-controller-api"
        "water-controller-ui"
        "water-controller-frontend"
        "water-controller-hmi"
        "water-controller-docker"
    )
    local stopped_services=0
    for svc in "${services[@]}"; do
        if systemctl is-active --quiet "${svc}.service" 2>/dev/null; then
            ((stopped_services++))
            log_verbose "Stopping ${svc}.service"
        fi
        run_privileged systemctl stop "${svc}.service" 2>/dev/null || true
        run_privileged systemctl disable "${svc}.service" 2>/dev/null || true
        run_privileged rm -f "/etc/systemd/system/${svc}.service" 2>/dev/null || true
    done
    if [[ $stopped_services -gt 0 ]]; then
        log_info "Stopped $stopped_services systemd service(s)"
    fi
    run_privileged systemctl daemon-reload 2>/dev/null || true

    # Remove Docker resources for this project
    if command -v docker &>/dev/null && docker info &>/dev/null; then
        # Count resources before removal
        local image_count=0 volume_count=0 network_count=0

        # Remove project images
        local images
        images=$(docker images --filter "reference=*water*" -q 2>/dev/null || true)
        images="$images $(docker images --filter "reference=*wtc*" -q 2>/dev/null || true)"
        images=$(echo "$images" | xargs -n1 2>/dev/null | sort -u | xargs 2>/dev/null || true)
        if [[ -n "$images" ]]; then
            image_count=$(echo "$images" | wc -w)
            if [[ "$VERBOSE_MODE" == "true" ]]; then
                docker rmi -f $images 2>&1 || true
            else
                docker rmi -f $images >/dev/null 2>&1 || true
            fi
        fi

        # Remove project volumes
        local volumes
        volumes=$(docker volume ls -q --filter "name=wtc" 2>/dev/null || true)
        volumes="$volumes $(docker volume ls -q --filter "name=water" 2>/dev/null || true)"
        volumes=$(echo "$volumes" | xargs -n1 2>/dev/null | sort -u | xargs 2>/dev/null || true)
        if [[ -n "$volumes" ]]; then
            volume_count=$(echo "$volumes" | wc -w)
            if [[ "$VERBOSE_MODE" == "true" ]]; then
                docker volume rm -f $volumes 2>&1 || true
            else
                docker volume rm -f $volumes >/dev/null 2>&1 || true
            fi
        fi

        # Remove project networks
        local networks
        networks=$(docker network ls -q --filter "name=wtc" 2>/dev/null || true)
        networks="$networks $(docker network ls -q --filter "name=water" 2>/dev/null || true)"
        networks=$(echo "$networks" | xargs -n1 2>/dev/null | sort -u | xargs 2>/dev/null || true)
        if [[ -n "$networks" ]]; then
            network_count=$(echo "$networks" | wc -w)
            if [[ "$VERBOSE_MODE" == "true" ]]; then
                docker network rm $networks 2>&1 || true
            else
                docker network rm $networks >/dev/null 2>&1 || true
            fi
        fi

        # Summary of Docker cleanup
        if [[ $image_count -gt 0 ]] || [[ $volume_count -gt 0 ]] || [[ $network_count -gt 0 ]]; then
            log_info "Removed Docker resources: ${image_count} image(s), ${volume_count} volume(s), ${network_count} network(s)"
        fi

        # Prune build cache (silent unless verbose)
        log_verbose "Pruning Docker build cache..."
        if [[ "$VERBOSE_MODE" == "true" ]]; then
            docker builder prune -af 2>&1 || true
            docker system prune -f 2>&1 || true
        else
            docker builder prune -af >/dev/null 2>&1 || true
            docker system prune -f >/dev/null 2>&1 || true
        fi
    fi

    # Remove all directories (consolidated log message)
    log_info "Removing installation directories..."
    log_verbose "/opt/water-controller"
    run_privileged rm -rf /opt/water-controller 2>/dev/null || true
    log_verbose "/etc/water-controller"
    run_privileged rm -rf /etc/water-controller 2>/dev/null || true
    log_verbose "/var/lib/water-controller"
    run_privileged rm -rf /var/lib/water-controller 2>/dev/null || true
    log_verbose "/var/log/water-controller"
    run_privileged rm -rf /var/log/water-controller 2>/dev/null || true
    log_verbose "/var/backups/water-controller"
    run_privileged rm -rf /var/backups/water-controller 2>/dev/null || true

    # Remove credentials files
    run_privileged rm -f /root/.water-controller-credentials 2>/dev/null || true

    # Clean up temp files
    run_privileged rm -rf /tmp/water-controller-* 2>/dev/null || true
    run_privileged rm -rf /var/tmp/water-controller-* 2>/dev/null || true

    show_disk_space "After Wipe"
    log_info "System wipe completed"
    return 0
}

# =============================================================================
# Fresh Install - Wipe + Install
# =============================================================================

do_fresh() {
    local branch="${1:-main}"

    log_step "Starting fresh install (wipe + install)..."
    show_disk_space "Before Fresh Install"

    # Wipe everything first
    do_wipe || {
        log_error "Wipe failed, aborting fresh install"
        return 1
    }

    # Now do a clean install
    log_step "Cloning and installing from scratch..."

    # Validate environment
    validate_environment || return 1

    # Default to docker if mode not specified
    if [[ -z "$DEPLOYMENT_MODE" ]]; then
        DEPLOYMENT_MODE="docker"
        log_info "Deployment mode: Docker (default)"
    else
        log_info "Deployment mode: $DEPLOYMENT_MODE"
    fi

    local result=0
    if [[ "$DEPLOYMENT_MODE" == "docker" ]]; then
        validate_docker_requirements || return 1
        do_docker_install
        result=$?
    else
        do_install "$branch" "true"
        result=$?
    fi

    show_disk_space "After Fresh Install"

    if [[ $result -eq 0 ]]; then
        log_info "Fresh install completed successfully!"
    else
        log_error "Fresh install failed"
    fi

    return $result
}

# =============================================================================
# Reinstall - Wipe + Install with Config Preservation
# =============================================================================

do_reinstall() {
    local branch="${1:-main}"

    log_step "Starting reinstall (upgrade with clean slate)..."
    show_disk_space "Before Reinstall"

    # Backup config if exists
    local config_backup=""
    if [[ -d "/opt/water-controller/config" ]]; then
        config_backup="/tmp/water-controller-config-backup-$$"
        log_info "Backing up configuration..."
        cp -r /opt/water-controller/config "$config_backup" 2>/dev/null || true
    fi

    # Backup credentials
    local creds_backup=""
    if [[ -f "/opt/water-controller/config/.docker-credentials" ]]; then
        creds_backup="/tmp/water-controller-creds-backup-$$"
        cp /opt/water-controller/config/.docker-credentials "$creds_backup" 2>/dev/null || true
    fi

    # Wipe everything
    do_wipe || {
        log_error "Wipe failed, aborting reinstall"
        return 1
    }

    # Validate environment
    validate_environment || return 1

    # Default to docker if mode not specified
    if [[ -z "$DEPLOYMENT_MODE" ]]; then
        DEPLOYMENT_MODE="docker"
        log_info "Deployment mode: Docker (default)"
    else
        log_info "Deployment mode: $DEPLOYMENT_MODE"
    fi

    local result=0
    if [[ "$DEPLOYMENT_MODE" == "docker" ]]; then
        validate_docker_requirements || return 1
        do_docker_install
        result=$?
    else
        do_install "$branch" "true"
        result=$?
    fi

    # Restore config if backup exists
    if [[ -n "$config_backup" ]] && [[ -d "$config_backup" ]] && [[ $result -eq 0 ]]; then
        log_info "Restoring configuration backup..."
        cp -r "$config_backup"/* /opt/water-controller/config/ 2>/dev/null || true
        rm -rf "$config_backup"
    fi

    # Restore credentials if backup exists
    if [[ -n "$creds_backup" ]] && [[ -f "$creds_backup" ]] && [[ $result -eq 0 ]]; then
        cp "$creds_backup" /opt/water-controller/config/.docker-credentials 2>/dev/null || true
        rm -f "$creds_backup"
    fi

    show_disk_space "After Reinstall"

    if [[ $result -eq 0 ]]; then
        log_info "Reinstall completed successfully!"
    else
        log_error "Reinstall failed"
    fi

    return $result
}
