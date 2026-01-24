#!/bin/bash
# =============================================================================
# Water Treatment Controller - Installation Steps Module
# =============================================================================
# Individual installation step functions.
# Depends on: detection.sh, dependencies.sh, pnet.sh, build.sh, install-files.sh,
#             service.sh, network-storage.sh, validation.sh, documentation.sh

# Prevent double-sourcing
[[ -n "${_WTC_STEPS_LOADED:-}" ]] && return 0
_WTC_STEPS_LOADED=1

# =============================================================================
# Step 1: System Detection
# =============================================================================

step_detect_system() {
    log_info "=== Step 1: System Detection ==="

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
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

# =============================================================================
# Step 2: Install Dependencies
# =============================================================================

step_install_dependencies() {
    log_info "=== Step 2: Dependency Installation ==="

    if [ "${SKIP_DEPS:-0}" -eq 1 ]; then
        log_info "Skipping dependency installation (--skip-deps)"
        return 0
    fi

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
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

# =============================================================================
# Step 3: Database Setup (PostgreSQL/TimescaleDB)
# =============================================================================

step_setup_database() {
    log_info "=== Step 3: Database Setup ==="

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
        log_info "[DRY RUN] Would setup PostgreSQL/TimescaleDB:"
        log_info "  - Install PostgreSQL if not present"
        log_info "  - Install TimescaleDB extension"
        log_info "  - Create database: water_treatment"
        log_info "  - Create user: wtc"
        log_info "  - Initialize schema from init.sql"
        return 0
    fi

    # Run complete database setup
    if ! setup_database; then
        log_error "Database setup failed. API cannot connect to database. Check PostgreSQL installation and logs."
        return 1
    fi

    # Verify database is ready
    if ! verify_database; then
        log_warn "Database verification had issues, but continuing..."
    fi

    log_info "Database setup complete"
    return 0
}

# =============================================================================
# Step 4: P-Net PROFINET Installation
# =============================================================================

step_install_pnet() {
    log_info "=== Step 4: P-Net PROFINET Installation ==="
    log_info "P-Net is the cornerstone of industrial communication"

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
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

# =============================================================================
# Step 5: Acquire and Build Source
# =============================================================================

step_build() {
    log_info "=== Step 5: Source Acquisition and Build ==="

    if [ "${SKIP_BUILD:-0}" -eq 1 ]; then
        log_info "Skipping build (--skip-build)"
        return 0
    fi

    local build_dir="/tmp/water-controller-build-$$"

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
        log_info "[DRY RUN] Would acquire and build source"
        if [ -n "${SOURCE_PATH:-}" ]; then
            log_info "  Source: $SOURCE_PATH"
        else
            log_info "  Repository: ${SOURCE_REPO:-}"
            log_info "  Branch: ${SOURCE_BRANCH:-main}"
        fi
        return 0
    fi

    # Acquire source
    if [ -n "${SOURCE_PATH:-}" ]; then
        if ! acquire_source --source "$SOURCE_PATH"; then
            log_error "Source copy failed from $SOURCE_PATH. Build cannot proceed. Verify source path and permissions."
            return 1
        fi
    else
        if ! acquire_source --branch "${SOURCE_BRANCH:-main}"; then
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

# =============================================================================
# Step 6: Install Files
# =============================================================================

step_install_files() {
    log_info "=== Step 6: File Installation ==="

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
        log_info "[DRY RUN] Would install files to:"
        log_info "  - ${INSTALL_DIR:-/opt/water-controller}"
        log_info "  - ${CONFIG_DIR:-/etc/water-controller}"
        log_info "  - ${DATA_DIR:-/var/lib/water-controller}"
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
    if [ -n "${SOURCE_DIR:-}" ] && [ -d "${SOURCE_DIR:-}" ]; then
        if ! install_python_app; then
            log_error "Python app installation failed. Backend unavailable. Check file permissions and disk space."
            return 1
        fi

        # Install frontend
        if ! install_frontend; then
            log_error "Frontend installation failed. HMI unavailable. Check file permissions and disk space."
            return 1
        fi
    elif [ "${SKIP_BUILD:-0}" -eq 0 ]; then
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

# =============================================================================
# Step 7: Configure Service
# =============================================================================

step_configure_service() {
    log_info "=== Step 7: Service Configuration ==="

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
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

# =============================================================================
# Step 8: Network and Storage Configuration
# =============================================================================

step_configure_network_storage() {
    log_info "=== Step 8: Network and Storage Configuration ==="

    if [ "${SKIP_NETWORK:-0}" -eq 1 ] && [ "${CONFIGURE_NETWORK:-0}" -eq 0 ]; then
        log_info "Skipping network configuration"
    fi

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
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
    if [ "${CONFIGURE_NETWORK:-0}" -eq 1 ]; then
        # Select network interface
        local iface="${NETWORK_INTERFACE:-}"
        if [ -z "$iface" ]; then
            iface=$(select_network_interface)
        fi

        if [ -n "$iface" ]; then
            # Configure static IP if provided
            if [ -n "${STATIC_IP:-}" ]; then
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

# =============================================================================
# Step 9: Start Service
# =============================================================================

step_start_service() {
    log_info "=== Step 9: Starting Service ==="

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
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

# =============================================================================
# Step 10: Validation
# =============================================================================

step_validate() {
    log_info "=== Step 10: Post-Installation Validation ==="

    if [ "${SKIP_VALIDATION:-0}" -eq 1 ]; then
        log_info "Skipping validation (--skip-validation)"
        return 0
    fi

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
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

# =============================================================================
# Step 11: Documentation
# =============================================================================

step_generate_docs() {
    log_info "=== Step 11: Generating Documentation ==="

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
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
