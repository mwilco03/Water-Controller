#!/bin/bash
#
# Water Treatment Controller - Dependency Installation System
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module provides distribution-agnostic package installation,
# Python/Node.js setup, and dependency verification.
#
# Tech Stack: Python/FastAPI backend, React frontend
# Target: ARM/x86 SBCs running Debian-based Linux
#

# Prevent multiple sourcing
if [ -n "$_WTC_DEPENDENCIES_LOADED" ]; then
    return 0
fi
_WTC_DEPENDENCIES_LOADED=1

# Source detection module for logging and detection functions
: "${SCRIPT_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
if [ -f "$SCRIPT_DIR/detection.sh" ]; then
    # shellcheck source=detection.sh
    source "$SCRIPT_DIR/detection.sh"
fi

# =============================================================================
# Constants
# =============================================================================

readonly DEPENDENCIES_VERSION="1.0.0"

# Version requirements
readonly REQUIRED_PYTHON_MAJOR=3
readonly REQUIRED_PYTHON_MINOR=9
readonly REQUIRED_NODE_MAJOR=18

# Package manager lock timeout (seconds)
readonly APT_LOCK_TIMEOUT=300
readonly APT_LOCK_RETRY_INTERVAL=5

# NodeSource repository for Node.js
readonly NODESOURCE_URL="https://deb.nodesource.com/setup_20.x"

# =============================================================================
# Package Manager Detection and Abstraction
# =============================================================================

# Detect the system's package manager
# Sets: _PKG_MANAGER (apt|dnf|yum|pacman|apk|zypper)
_detect_package_manager() {
    if command -v apt-get >/dev/null 2>&1; then
        _PKG_MANAGER="apt"
    elif command -v dnf >/dev/null 2>&1; then
        _PKG_MANAGER="dnf"
    elif command -v yum >/dev/null 2>&1; then
        _PKG_MANAGER="yum"
    elif command -v pacman >/dev/null 2>&1; then
        _PKG_MANAGER="pacman"
    elif command -v apk >/dev/null 2>&1; then
        _PKG_MANAGER="apk"
    elif command -v zypper >/dev/null 2>&1; then
        _PKG_MANAGER="zypper"
    else
        _PKG_MANAGER="unknown"
        return 1
    fi
    return 0
}

# Wait for apt lock to be released
# Returns: 0 when lock is free, 1 on timeout
_wait_for_apt_lock() {
    local waited=0
    local lock_files=(
        "/var/lib/dpkg/lock"
        "/var/lib/dpkg/lock-frontend"
        "/var/lib/apt/lists/lock"
        "/var/cache/apt/archives/lock"
    )

    while [ $waited -lt $APT_LOCK_TIMEOUT ]; do
        local locked=false

        for lock_file in "${lock_files[@]}"; do
            if fuser "$lock_file" >/dev/null 2>&1; then
                locked=true
                break
            fi
        done

        if [ "$locked" = false ]; then
            return 0
        fi

        log_debug "Waiting for apt lock... ($waited/$APT_LOCK_TIMEOUT seconds)"
        sleep $APT_LOCK_RETRY_INTERVAL
        waited=$((waited + APT_LOCK_RETRY_INTERVAL))
    done

    log_error "Timeout waiting for apt lock after $APT_LOCK_TIMEOUT seconds"
    return 1
}

# Map generic package names to distribution-specific names
# Input: generic package name
# Output: distribution-specific package name
_map_package_name() {
    local generic_name="$1"
    local mapped_name="$generic_name"

    _detect_package_manager

    case "$_PKG_MANAGER" in
        apt)
            case "$generic_name" in
                python3-dev) mapped_name="python3-dev" ;;
                python3-pip) mapped_name="python3-pip" ;;
                python3-venv) mapped_name="python3-venv" ;;
                nodejs) mapped_name="nodejs" ;;
                build-essential) mapped_name="build-essential" ;;
                libsqlite3-dev) mapped_name="libsqlite3-dev" ;;
                libffi-dev) mapped_name="libffi-dev" ;;
                libssl-dev) mapped_name="libssl-dev" ;;
                *) mapped_name="$generic_name" ;;
            esac
            ;;
        dnf|yum)
            case "$generic_name" in
                python3-dev) mapped_name="python3-devel" ;;
                python3-pip) mapped_name="python3-pip" ;;
                python3-venv) mapped_name="python3-venv" ;;
                nodejs) mapped_name="nodejs" ;;
                build-essential) mapped_name="@development-tools" ;;
                libsqlite3-dev) mapped_name="sqlite-devel" ;;
                libffi-dev) mapped_name="libffi-devel" ;;
                libssl-dev) mapped_name="openssl-devel" ;;
                *) mapped_name="$generic_name" ;;
            esac
            ;;
        pacman)
            case "$generic_name" in
                python3-dev) mapped_name="python" ;;
                python3-pip) mapped_name="python-pip" ;;
                python3-venv) mapped_name="python" ;;
                nodejs) mapped_name="nodejs" ;;
                build-essential) mapped_name="base-devel" ;;
                libsqlite3-dev) mapped_name="sqlite" ;;
                libffi-dev) mapped_name="libffi" ;;
                libssl-dev) mapped_name="openssl" ;;
                *) mapped_name="$generic_name" ;;
            esac
            ;;
        apk)
            case "$generic_name" in
                python3-dev) mapped_name="python3-dev" ;;
                python3-pip) mapped_name="py3-pip" ;;
                python3-venv) mapped_name="python3" ;;
                nodejs) mapped_name="nodejs" ;;
                build-essential) mapped_name="build-base" ;;
                libsqlite3-dev) mapped_name="sqlite-dev" ;;
                libffi-dev) mapped_name="libffi-dev" ;;
                libssl-dev) mapped_name="openssl-dev" ;;
                *) mapped_name="$generic_name" ;;
            esac
            ;;
        zypper)
            case "$generic_name" in
                python3-dev) mapped_name="python3-devel" ;;
                python3-pip) mapped_name="python3-pip" ;;
                python3-venv) mapped_name="python3-venv" ;;
                nodejs) mapped_name="nodejs" ;;
                build-essential) mapped_name="-t pattern devel_basis" ;;
                libsqlite3-dev) mapped_name="sqlite3-devel" ;;
                libffi-dev) mapped_name="libffi-devel" ;;
                libssl-dev) mapped_name="openssl-devel" ;;
                *) mapped_name="$generic_name" ;;
            esac
            ;;
    esac

    echo "$mapped_name"
}

# Check if a package is already installed
# Input: package name
# Returns: 0 if installed, 1 if not
_is_package_installed() {
    local package="$1"

    _detect_package_manager

    case "$_PKG_MANAGER" in
        apt)
            dpkg -l "$package" 2>/dev/null | grep -q "^ii" && return 0
            ;;
        dnf|yum)
            rpm -q "$package" >/dev/null 2>&1 && return 0
            ;;
        pacman)
            pacman -Qi "$package" >/dev/null 2>&1 && return 0
            ;;
        apk)
            apk info -e "$package" >/dev/null 2>&1 && return 0
            ;;
        zypper)
            rpm -q "$package" >/dev/null 2>&1 && return 0
            ;;
    esac

    return 1
}

# Install a system package
# Input: package name (generic)
# Returns: 0 on success, 1 on failure
install_system_package() {
    local generic_package="$1"

    if [ -z "$generic_package" ]; then
        log_error "install_system_package: No package name provided"
        return 1
    fi

    _detect_package_manager
    if [ "$_PKG_MANAGER" = "unknown" ]; then
        log_error "No supported package manager found"
        return 1
    fi

    local package
    package="$(_map_package_name "$generic_package")"

    # Check if already installed (for non-group packages)
    if [[ "$package" != @* ]] && [[ "$package" != "-t pattern"* ]]; then
        if _is_package_installed "$package"; then
            log_debug "Package already installed: $package"
            return 0
        fi
    fi

    log_info "Installing package: $package (via $_PKG_MANAGER)"

    local install_cmd
    local result=0

    case "$_PKG_MANAGER" in
        apt)
            _wait_for_apt_lock || return 1

            # Update package lists if not done recently
            if [ ! -f /var/lib/apt/periodic/update-success-stamp ] || \
               [ "$(find /var/lib/apt/periodic/update-success-stamp -mmin +60 2>/dev/null)" ]; then
                log_debug "Updating apt package lists..."
                sudo apt-get update -qq 2>&1 | tee -a "$INSTALL_LOG_FILE" || true
            fi

            sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$package" 2>&1 | tee -a "$INSTALL_LOG_FILE"
            result=${PIPESTATUS[0]}
            ;;
        dnf)
            if [[ "$package" == @* ]]; then
                sudo dnf group install -y "$package" 2>&1 | tee -a "$INSTALL_LOG_FILE"
            else
                sudo dnf install -y "$package" 2>&1 | tee -a "$INSTALL_LOG_FILE"
            fi
            result=${PIPESTATUS[0]}
            ;;
        yum)
            if [[ "$package" == @* ]]; then
                sudo yum groupinstall -y "${package#@}" 2>&1 | tee -a "$INSTALL_LOG_FILE"
            else
                sudo yum install -y "$package" 2>&1 | tee -a "$INSTALL_LOG_FILE"
            fi
            result=${PIPESTATUS[0]}
            ;;
        pacman)
            if [[ "$package" == "base-devel" ]]; then
                sudo pacman -S --noconfirm --needed base-devel 2>&1 | tee -a "$INSTALL_LOG_FILE"
            else
                sudo pacman -S --noconfirm --needed "$package" 2>&1 | tee -a "$INSTALL_LOG_FILE"
            fi
            result=${PIPESTATUS[0]}
            ;;
        apk)
            sudo apk add --no-cache "$package" 2>&1 | tee -a "$INSTALL_LOG_FILE"
            result=${PIPESTATUS[0]}
            ;;
        zypper)
            if [[ "$package" == "-t pattern"* ]]; then
                # shellcheck disable=SC2086
                sudo zypper install -y $package 2>&1 | tee -a "$INSTALL_LOG_FILE"
            else
                sudo zypper install -y "$package" 2>&1 | tee -a "$INSTALL_LOG_FILE"
            fi
            result=${PIPESTATUS[0]}
            ;;
    esac

    if [ $result -ne 0 ]; then
        log_error "Failed to install package: $package (exit code: $result)"
        return 1
    fi

    # Verify installation
    if [[ "$package" != @* ]] && [[ "$package" != "-t pattern"* ]] && [[ "$package" != "base-devel" ]]; then
        if ! _is_package_installed "$package"; then
            log_error "Package installation verification failed: $package"
            return 1
        fi
    fi

    log_info "Successfully installed: $package"
    return 0
}

# =============================================================================
# Python Installation
# =============================================================================

# Check Python version meets requirements
# Returns: 0 if version OK, 1 if not
_check_python_version() {
    if ! command -v python3 >/dev/null 2>&1; then
        return 1
    fi

    local version
    version="$(python3 --version 2>/dev/null | awk '{print $2}')"
    local major minor
    major="$(echo "$version" | cut -d. -f1)"
    minor="$(echo "$version" | cut -d. -f2)"

    if [ "$major" -lt "$REQUIRED_PYTHON_MAJOR" ]; then
        return 1
    fi

    if [ "$major" -eq "$REQUIRED_PYTHON_MAJOR" ] && [ "$minor" -lt "$REQUIRED_PYTHON_MINOR" ]; then
        return 1
    fi

    log_debug "Python version $version meets requirements (>= $REQUIRED_PYTHON_MAJOR.$REQUIRED_PYTHON_MINOR)"
    return 0
}

# Install Python 3.9+ with pip and venv
# Returns: 0 on success, 1 on failure
install_python() {
    log_info "Setting up Python environment..."

    # Check if Python already meets requirements
    if _check_python_version; then
        local version
        version="$(python3 --version 2>/dev/null | awk '{print $2}')"
        log_info "Python $version already installed and meets requirements"
    else
        log_info "Installing Python 3..."

        _detect_package_manager

        case "$_PKG_MANAGER" in
            apt)
                # On older Debian/Ubuntu, we might need to add deadsnakes PPA
                # For now, try system packages first
                install_system_package "python3" || return 1
                ;;
            dnf|yum)
                install_system_package "python3" || return 1
                ;;
            pacman)
                install_system_package "python" || return 1
                ;;
            apk)
                install_system_package "python3" || return 1
                ;;
            zypper)
                install_system_package "python3" || return 1
                ;;
            *)
                log_error "Unsupported package manager for Python installation"
                return 1
                ;;
        esac

        # Verify Python was installed
        if ! _check_python_version; then
            log_error "Python installation failed or version too old"
            log_error "Required: Python >= $REQUIRED_PYTHON_MAJOR.$REQUIRED_PYTHON_MINOR"
            return 1
        fi
    fi

    # Install pip
    log_info "Installing pip3..."
    if ! command -v pip3 >/dev/null 2>&1; then
        install_system_package "python3-pip" || {
            # Try alternative installation via ensurepip
            log_info "Trying ensurepip..."
            python3 -m ensurepip --upgrade 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
                log_error "Failed to install pip"
                return 1
            }
        }
    fi

    # Verify pip
    if ! command -v pip3 >/dev/null 2>&1; then
        log_error "pip3 not available after installation"
        return 1
    fi
    log_debug "pip3 version: $(pip3 --version 2>/dev/null | awk '{print $2}')"

    # Install venv module
    log_info "Installing python3-venv..."
    if ! python3 -c "import venv" 2>/dev/null; then
        install_system_package "python3-venv" || {
            log_error "Failed to install python3-venv"
            return 1
        }
    fi

    # Verify venv
    if ! python3 -c "import venv" 2>/dev/null; then
        log_error "python3-venv not available after installation"
        return 1
    fi
    log_debug "python3-venv: OK"

    # Install python3-dev for native extensions
    log_info "Installing python3-dev..."
    install_system_package "python3-dev" || {
        log_warn "Failed to install python3-dev (may affect native extensions)"
    }

    log_info "Python environment setup complete"
    log_info "  Python: $(python3 --version 2>/dev/null)"
    log_info "  pip: $(pip3 --version 2>/dev/null | awk '{print $1, $2}')"

    return 0
}

# =============================================================================
# Node.js Installation
# =============================================================================

# Check Node.js version meets requirements
# Returns: 0 if version OK, 1 if not
_check_node_version() {
    if ! command -v node >/dev/null 2>&1; then
        return 1
    fi

    local version
    version="$(node --version 2>/dev/null | sed 's/^v//')"
    local major
    major="$(echo "$version" | cut -d. -f1)"

    if [ "$major" -lt "$REQUIRED_NODE_MAJOR" ]; then
        return 1
    fi

    log_debug "Node.js version $version meets requirements (>= $REQUIRED_NODE_MAJOR)"
    return 0
}

# Install Node.js 18+ and npm
# Returns: 0 on success, 1 on failure
install_nodejs() {
    log_info "Setting up Node.js environment..."

    # Check if Node.js already meets requirements
    if _check_node_version; then
        local version
        version="$(node --version 2>/dev/null)"
        log_info "Node.js $version already installed and meets requirements"
    else
        log_info "Installing Node.js..."

        _detect_package_manager

        case "$_PKG_MANAGER" in
            apt)
                # Use NodeSource repository for newer Node.js
                log_info "Adding NodeSource repository..."

                # Install prerequisites
                install_system_package "ca-certificates" || true
                install_system_package "curl" || true
                install_system_package "gnupg" || true

                # Download and run NodeSource setup script
                if curl -fsSL "$NODESOURCE_URL" -o /tmp/nodesource_setup.sh 2>&1 | tee -a "$INSTALL_LOG_FILE"; then
                    sudo bash /tmp/nodesource_setup.sh 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
                        log_error "NodeSource setup script failed"
                        rm -f /tmp/nodesource_setup.sh
                        return 1
                    }
                    rm -f /tmp/nodesource_setup.sh

                    # Install Node.js from NodeSource
                    _wait_for_apt_lock || return 1
                    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
                        log_error "Failed to install Node.js from NodeSource"
                        return 1
                    }
                else
                    log_warn "Failed to download NodeSource setup, trying system packages"
                    install_system_package "nodejs" || return 1
                fi
                ;;
            dnf)
                # Use NodeSource or module stream
                if dnf module list nodejs 2>/dev/null | grep -q "18"; then
                    sudo dnf module enable -y nodejs:18 2>&1 | tee -a "$INSTALL_LOG_FILE" || true
                fi
                install_system_package "nodejs" || return 1
                ;;
            yum)
                # Try NodeSource for older RHEL/CentOS
                if curl -fsSL "$NODESOURCE_URL" -o /tmp/nodesource_setup.sh 2>&1; then
                    sudo bash /tmp/nodesource_setup.sh 2>&1 | tee -a "$INSTALL_LOG_FILE" || true
                    rm -f /tmp/nodesource_setup.sh
                fi
                install_system_package "nodejs" || return 1
                ;;
            pacman)
                install_system_package "nodejs" || return 1
                install_system_package "npm" || return 1
                ;;
            apk)
                install_system_package "nodejs" || return 1
                install_system_package "npm" || return 1
                ;;
            zypper)
                install_system_package "nodejs" || return 1
                install_system_package "npm" || return 1
                ;;
            *)
                log_error "Unsupported package manager for Node.js installation"
                return 1
                ;;
        esac

        # Verify Node.js was installed
        if ! _check_node_version; then
            log_error "Node.js installation failed or version too old"
            log_error "Required: Node.js >= $REQUIRED_NODE_MAJOR"
            return 1
        fi
    fi

    # Check npm
    if ! command -v npm >/dev/null 2>&1; then
        log_info "Installing npm..."
        install_system_package "npm" || {
            log_error "Failed to install npm"
            return 1
        }
    fi

    # Verify npm
    if ! command -v npm >/dev/null 2>&1; then
        log_error "npm not available after installation"
        return 1
    fi

    local npm_version
    npm_version="$(npm --version 2>/dev/null)"
    log_debug "npm version: $npm_version"

    # Check npm version (should be >= 8 for Node 18+)
    local npm_major
    npm_major="$(echo "$npm_version" | cut -d. -f1)"
    if [ "$npm_major" -lt 8 ] 2>/dev/null; then
        log_warn "npm version $npm_version is old, upgrading..."
        npm install -g npm@latest 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
            log_warn "Failed to upgrade npm (continuing with current version)"
        }
    fi

    log_info "Node.js environment setup complete"
    log_info "  Node.js: $(node --version 2>/dev/null)"
    log_info "  npm: $(npm --version 2>/dev/null)"

    return 0
}

# =============================================================================
# Build Dependencies
# =============================================================================

# Install build tools and development libraries
# Returns: 0 on success, 1 on failure
install_build_deps() {
    log_info "Installing build dependencies..."

    local failed=0
    local packages=(
        "build-essential"
        "pkg-config"
        "libsqlite3-dev"
        "python3-dev"
        "libffi-dev"
        "libssl-dev"
        "git"
        "curl"
        "wget"
    )

    for package in "${packages[@]}"; do
        if ! install_system_package "$package"; then
            log_warn "Failed to install: $package"
            # Some packages are optional, don't fail immediately
            case "$package" in
                "build-essential"|"git"|"curl")
                    # Critical packages
                    failed=1
                    ;;
                *)
                    # Non-critical, continue
                    ;;
            esac
        fi
    done

    # Install network tools
    log_info "Installing network tools..."
    local net_packages=(
        "ethtool"
        "iproute2"
        "net-tools"
    )

    for package in "${net_packages[@]}"; do
        install_system_package "$package" || {
            log_warn "Failed to install network tool: $package (may be optional)"
        }
    done

    # Verify critical tools
    log_info "Verifying build tools..."

    if ! command -v gcc >/dev/null 2>&1; then
        log_error "gcc not available after build-essential installation"
        failed=1
    else
        log_debug "gcc: $(gcc --version | head -n1)"
    fi

    if ! command -v make >/dev/null 2>&1; then
        log_error "make not available after build-essential installation"
        failed=1
    else
        log_debug "make: $(make --version | head -n1)"
    fi

    if ! command -v git >/dev/null 2>&1; then
        log_error "git not available"
        failed=1
    else
        log_debug "git: $(git --version)"
    fi

    if ! command -v curl >/dev/null 2>&1; then
        log_error "curl not available"
        failed=1
    else
        log_debug "curl: $(curl --version | head -n1)"
    fi

    if [ $failed -ne 0 ]; then
        log_error "Build dependencies installation failed"
        return 1
    fi

    log_info "Build dependencies installation complete"
    return 0
}

# =============================================================================
# PROFINET Libraries
# =============================================================================

# Install PROFINET-related dependencies (best effort)
# Returns: 0 on success, 1 on failure (warning only for PROFINET)
install_profinet_deps() {
    log_info "Installing PROFINET-related dependencies..."

    local profinet_available=false

    # Check for p-net or similar PROFINET libraries
    _detect_package_manager

    case "$_PKG_MANAGER" in
        apt)
            # p-net is typically not in standard repos
            # Check if available
            if apt-cache show libpnet 2>/dev/null | grep -q "Package:"; then
                install_system_package "libpnet" && profinet_available=true
            fi
            ;;
        dnf|yum)
            if dnf info libpnet 2>/dev/null | grep -q "Name"; then
                install_system_package "libpnet" && profinet_available=true
            fi
            ;;
    esac

    if [ "$profinet_available" = false ]; then
        log_warn "PROFINET library (p-net) not available in system repositories"
        log_warn "PROFINET support may require manual compilation"
        log_warn "See: https://github.com/rtlabs-com/p-net"
    fi

    # Install related network libraries that may be useful
    local net_libs=(
        "libpcap-dev"
        "libnet1-dev"
    )

    _detect_package_manager
    case "$_PKG_MANAGER" in
        apt)
            for lib in "${net_libs[@]}"; do
                install_system_package "$lib" || {
                    log_debug "Optional network library not available: $lib"
                }
            done
            ;;
        dnf|yum)
            install_system_package "libpcap-devel" || true
            install_system_package "libnet-devel" || true
            ;;
    esac

    # Always return success - PROFINET is optional
    log_info "PROFINET dependencies check complete"
    return 0
}

# =============================================================================
# Dependency Verification
# =============================================================================

# Verify all dependencies are installed
# Returns: 0 if all present, 1 if any missing
verify_all_dependencies() {
    log_info "Verifying all dependencies..."

    local failed=0
    local results=()

    # Python check
    if _check_python_version; then
        results+=("[OK] Python $(python3 --version 2>/dev/null | awk '{print $2}')")
    else
        results+=("[FAIL] Python >= $REQUIRED_PYTHON_MAJOR.$REQUIRED_PYTHON_MINOR")
        failed=1
    fi

    # pip check
    if command -v pip3 >/dev/null 2>&1; then
        results+=("[OK] pip3 $(pip3 --version 2>/dev/null | awk '{print $2}')")
    else
        results+=("[FAIL] pip3")
        failed=1
    fi

    # venv check
    if python3 -c "import venv" 2>/dev/null; then
        results+=("[OK] python3-venv")
    else
        results+=("[FAIL] python3-venv")
        failed=1
    fi

    # Node.js check
    if _check_node_version; then
        results+=("[OK] Node.js $(node --version 2>/dev/null)")
    else
        results+=("[FAIL] Node.js >= $REQUIRED_NODE_MAJOR")
        failed=1
    fi

    # npm check
    if command -v npm >/dev/null 2>&1; then
        results+=("[OK] npm $(npm --version 2>/dev/null)")
    else
        results+=("[FAIL] npm")
        failed=1
    fi

    # Build tools
    if command -v gcc >/dev/null 2>&1; then
        results+=("[OK] gcc")
    else
        results+=("[FAIL] gcc")
        failed=1
    fi

    if command -v make >/dev/null 2>&1; then
        results+=("[OK] make")
    else
        results+=("[FAIL] make")
        failed=1
    fi

    if command -v git >/dev/null 2>&1; then
        results+=("[OK] git")
    else
        results+=("[FAIL] git")
        failed=1
    fi

    if command -v curl >/dev/null 2>&1; then
        results+=("[OK] curl")
    else
        results+=("[FAIL] curl")
        failed=1
    fi

    if command -v pkg-config >/dev/null 2>&1; then
        results+=("[OK] pkg-config")
    else
        results+=("[WARN] pkg-config (optional)")
    fi

    if command -v cmake >/dev/null 2>&1; then
        results+=("[OK] cmake")
    else
        results+=("[WARN] cmake (optional)")
    fi

    if command -v sqlite3 >/dev/null 2>&1; then
        results+=("[OK] sqlite3 $(sqlite3 --version 2>/dev/null | awk '{print $1}')")
    else
        results+=("[WARN] sqlite3 (optional for CLI access)")
    fi

    # Print results
    echo ""
    echo "DEPENDENCY VERIFICATION RESULTS:"
    echo "================================="
    for result in "${results[@]}"; do
        echo "  $result"
    done
    echo "================================="
    echo ""

    # Log all versions to install log
    _log_write "INFO" "Dependency verification results:"
    for result in "${results[@]}"; do
        _log_write "INFO" "  $result"
    done

    if [ $failed -ne 0 ]; then
        log_error "Some required dependencies are missing"
        return 1
    fi

    log_info "All required dependencies verified"
    return 0
}

# =============================================================================
# Combined Installation Function
# =============================================================================

# Install all dependencies in correct order
# Returns: 0 on success, 1 on failure
install_all_dependencies() {
    log_info "Installing all dependencies..."

    # Install build dependencies first
    install_build_deps || {
        log_error "Failed to install build dependencies"
        return 1
    }

    # Install Python
    install_python || {
        log_error "Failed to install Python"
        return 1
    }

    # Install Node.js
    install_nodejs || {
        log_error "Failed to install Node.js"
        return 1
    }

    # Install PROFINET dependencies (optional)
    install_profinet_deps || {
        log_warn "PROFINET dependencies installation had issues (non-fatal)"
    }

    # Verify all dependencies
    verify_all_dependencies || {
        log_error "Dependency verification failed"
        return 1
    }

    log_info "All dependencies installed successfully"
    return 0
}

# =============================================================================
# Main Entry Point (when run directly)
# =============================================================================

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    # Initialize logging
    init_logging || {
        echo "[WARN] Logging initialization failed, continuing without file logging" >&2
    }

    # Parse arguments
    case "${1:-}" in
        --install-package)
            if [ -z "${2:-}" ]; then
                log_error "Usage: $0 --install-package <package_name>"
                exit 1
            fi
            install_system_package "$2"
            exit $?
            ;;
        --install-python)
            install_python
            exit $?
            ;;
        --install-nodejs)
            install_nodejs
            exit $?
            ;;
        --install-build-deps)
            install_build_deps
            exit $?
            ;;
        --install-profinet)
            install_profinet_deps
            exit $?
            ;;
        --verify)
            verify_all_dependencies
            exit $?
            ;;
        --install-all)
            install_all_dependencies
            exit $?
            ;;
        --help|-h)
            echo "Water-Controller Dependencies Module v$DEPENDENCIES_VERSION"
            echo ""
            echo "Usage: $0 [OPTION]"
            echo ""
            echo "Options:"
            echo "  --install-package <name>  Install a system package"
            echo "  --install-python          Install Python 3.9+ with pip and venv"
            echo "  --install-nodejs          Install Node.js 18+ with npm"
            echo "  --install-build-deps      Install build tools and dev libraries"
            echo "  --install-profinet        Install PROFINET-related dependencies"
            echo "  --verify                  Verify all dependencies are installed"
            echo "  --install-all             Install all dependencies"
            echo "  --help, -h                Show this help message"
            echo ""
            echo "This script requires root privileges for package installation."
            ;;
        *)
            echo "Usage: $0 [--install-package <name>|--install-python|--install-nodejs|--install-build-deps|--install-profinet|--verify|--install-all|--help]" >&2
            exit 1
            ;;
    esac
fi
