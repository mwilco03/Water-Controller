#!/bin/bash
#
# Water Treatment Controller - Source Acquisition and Build System
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module provides source acquisition, Python venv creation,
# backend/frontend build, and verification functions.
#
# Tech Stack: Python/FastAPI backend, React frontend (NO RUST)
# Target: ARM/x86 SBCs running Debian-based Linux
#

# Prevent multiple sourcing
if [ -n "$_WTC_BUILD_LOADED" ]; then
    return 0
fi
_WTC_BUILD_LOADED=1

# Source detection module for logging and detection functions
: "${SCRIPT_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
if [ -f "$SCRIPT_DIR/detection.sh" ]; then
    # shellcheck source=detection.sh
    source "$SCRIPT_DIR/detection.sh"
fi

# =============================================================================
# Constants
# =============================================================================

readonly BUILD_VERSION="1.0.0"

# Repository and paths
readonly DEFAULT_GIT_REPO="https://github.com/mwilco03/Water-Controller.git"
readonly DEFAULT_GIT_BRANCH="main"

# Installation paths
: "${INSTALL_BASE:=/opt/water-controller}"
: "${VENV_PATH:=$INSTALL_BASE/venv}"
: "${APP_PATH:=$INSTALL_BASE/app}"
: "${WEB_PATH:=$INSTALL_BASE/web}"

# Source directory (set by acquire_source)
SOURCE_DIR=""

# Build timeouts (seconds)
readonly PIP_INSTALL_TIMEOUT=600
readonly NPM_INSTALL_TIMEOUT=600
readonly NPM_BUILD_TIMEOUT=900

# =============================================================================
# Source Acquisition
# =============================================================================

# Acquire source code from git or local path
# Input: --source <path> flag or default to git clone
# Sets: SOURCE_DIR variable
# Returns: 0 on success, 1 on failure
acquire_source() {
    local source_path=""
    local git_branch="$DEFAULT_GIT_BRANCH"
    local git_tag=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --source)
                source_path="$2"
                shift 2
                ;;
            --branch)
                git_branch="$2"
                shift 2
                ;;
            --tag)
                git_tag="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    if [ -n "$source_path" ]; then
        # Local source path provided
        log_info "Using local source: $source_path"

        if [ ! -d "$source_path" ]; then
            log_error "Source directory does not exist: $source_path"
            return 1
        fi

        # Verify it looks like a Water-Controller source tree
        if [ ! -f "$source_path/web/api/requirements.txt" ] && \
           [ ! -f "$source_path/requirements.txt" ] && \
           [ ! -f "$source_path/pyproject.toml" ]; then
            log_error "Source directory does not appear to be Water-Controller source"
            log_error "Expected to find web/api/requirements.txt, requirements.txt, or pyproject.toml"
            return 1
        fi

        SOURCE_DIR="$(cd "$source_path" && pwd)"
        log_info "Source directory verified: $SOURCE_DIR"
    else
        # Git clone
        log_info "Cloning Water-Controller from git..."

        # Check git is available
        if ! command -v git >/dev/null 2>&1; then
            log_error "git is not installed"
            return 1
        fi

        # Create temporary clone directory
        local clone_dir
        clone_dir="$(mktemp -d /tmp/water-controller-src.XXXXXX)"

        if [ -z "$clone_dir" ] || [ ! -d "$clone_dir" ]; then
            log_error "Failed to create temporary directory for git clone"
            return 1
        fi

        log_debug "Cloning to temporary directory: $clone_dir"

        # Clone repository
        if ! git clone --depth 1 --branch "$git_branch" "$DEFAULT_GIT_REPO" "$clone_dir" 2>&1 | tee -a "$INSTALL_LOG_FILE"; then
            log_error "Failed to clone repository: $DEFAULT_GIT_REPO"
            rm -rf "$clone_dir"
            return 1
        fi

        # Checkout specific tag if provided
        if [ -n "$git_tag" ]; then
            log_info "Checking out tag: $git_tag"
            if ! (cd "$clone_dir" && git fetch --depth 1 origin "refs/tags/$git_tag" && git checkout "$git_tag") 2>&1 | tee -a "$INSTALL_LOG_FILE"; then
                log_error "Failed to checkout tag: $git_tag"
                rm -rf "$clone_dir"
                return 1
            fi
        fi

        # Verify clone succeeded
        if [ ! -d "$clone_dir/.git" ]; then
            log_error "Git clone verification failed: no .git directory"
            rm -rf "$clone_dir"
            return 1
        fi

        # Get commit info
        local commit_hash
        commit_hash="$(cd "$clone_dir" && git rev-parse --short HEAD)"
        log_info "Cloned successfully at commit: $commit_hash"

        SOURCE_DIR="$clone_dir"
    fi

    # Verify source structure
    log_debug "Verifying source structure..."

    # Check for Python backend
    if [ -d "$SOURCE_DIR/web/api" ]; then
        log_debug "Found Python backend at: $SOURCE_DIR/web/api"
    elif [ -d "$SOURCE_DIR/backend" ]; then
        log_debug "Found Python backend at: $SOURCE_DIR/backend"
    elif [ -f "$SOURCE_DIR/requirements.txt" ]; then
        log_debug "Found requirements.txt in source root"
    else
        log_warn "Python backend structure not detected (may be OK)"
    fi

    # Check for React frontend
    if [ -d "$SOURCE_DIR/web/ui" ] && [ -f "$SOURCE_DIR/web/ui/package.json" ]; then
        log_debug "Found React frontend at: $SOURCE_DIR/web/ui"
    elif [ -d "$SOURCE_DIR/frontend" ] && [ -f "$SOURCE_DIR/frontend/package.json" ]; then
        log_debug "Found React frontend at: $SOURCE_DIR/frontend"
    else
        log_warn "React frontend structure not detected (may be OK)"
    fi

    export SOURCE_DIR
    _log_write "INFO" "Source acquired: $SOURCE_DIR"

    return 0
}

# =============================================================================
# Python Virtual Environment
# =============================================================================

# Create Python virtual environment
# Returns: 0 on success, 3 on failure
create_python_venv() {
    log_info "Creating Python virtual environment..."

    # Check Python is available
    if ! command -v python3 >/dev/null 2>&1; then
        log_error "Python3 is not installed"
        return 3
    fi

    # Check venv module is available
    if ! python3 -c "import venv" 2>/dev/null; then
        log_error "Python venv module not available"
        return 3
    fi

    # Create installation directory if needed
    if [ ! -d "$INSTALL_BASE" ]; then
        log_debug "Creating installation directory: $INSTALL_BASE"
        mkdir -p "$INSTALL_BASE" || {
            log_error "Failed to create installation directory: $INSTALL_BASE"
            return 3
        }
    fi

    # Remove existing venv if corrupted
    if [ -d "$VENV_PATH" ]; then
        if [ ! -x "$VENV_PATH/bin/python3" ]; then
            log_warn "Existing venv appears corrupted, removing..."
            rm -rf "$VENV_PATH"
        else
            log_info "Virtual environment already exists at: $VENV_PATH"
            # Verify it works
            if "$VENV_PATH/bin/python3" --version >/dev/null 2>&1; then
                log_debug "Existing venv is functional"
            else
                log_warn "Existing venv is not functional, recreating..."
                rm -rf "$VENV_PATH"
            fi
        fi
    fi

    # Create venv if it doesn't exist
    if [ ! -d "$VENV_PATH" ]; then
        log_info "Creating virtual environment at: $VENV_PATH"

        if ! python3 -m venv "$VENV_PATH" 2>&1 | tee -a "$INSTALL_LOG_FILE"; then
            log_error "Failed to create virtual environment"
            return 3
        fi
    fi

    # Verify venv was created
    if [ ! -x "$VENV_PATH/bin/python3" ]; then
        log_error "Virtual environment creation failed: python3 not found in venv"
        return 3
    fi

    if [ ! -x "$VENV_PATH/bin/pip" ]; then
        log_error "Virtual environment creation failed: pip not found in venv"
        return 3
    fi

    # Upgrade pip
    log_info "Upgrading pip in virtual environment..."
    if ! "$VENV_PATH/bin/pip" install --upgrade pip 2>&1 | tee -a "$INSTALL_LOG_FILE"; then
        log_warn "Failed to upgrade pip (continuing with existing version)"
    fi

    # Install wheel for faster installs
    log_debug "Installing wheel..."
    "$VENV_PATH/bin/pip" install --upgrade wheel 2>&1 | tee -a "$INSTALL_LOG_FILE" || true

    # Log versions
    local python_version pip_version
    python_version="$("$VENV_PATH/bin/python3" --version 2>&1)"
    pip_version="$("$VENV_PATH/bin/pip" --version 2>&1 | awk '{print $2}')"

    log_info "Virtual environment ready:"
    log_info "  Python: $python_version"
    log_info "  pip: $pip_version"
    log_info "  Path: $VENV_PATH"

    _log_write "INFO" "Virtual environment created: $VENV_PATH"

    return 0
}

# =============================================================================
# Python Backend Build
# =============================================================================

# Find Python backend directory
# Sets: _BACKEND_DIR
# Returns: 0 if found, 1 if not
_find_backend_dir() {
    _BACKEND_DIR=""

    if [ -z "$SOURCE_DIR" ]; then
        log_error "SOURCE_DIR not set. Run acquire_source first."
        return 1
    fi

    # Check common locations
    if [ -d "$SOURCE_DIR/web/api" ] && [ -f "$SOURCE_DIR/web/api/requirements.txt" ]; then
        _BACKEND_DIR="$SOURCE_DIR/web/api"
    elif [ -d "$SOURCE_DIR/backend" ] && [ -f "$SOURCE_DIR/backend/requirements.txt" ]; then
        _BACKEND_DIR="$SOURCE_DIR/backend"
    elif [ -d "$SOURCE_DIR/api" ] && [ -f "$SOURCE_DIR/api/requirements.txt" ]; then
        _BACKEND_DIR="$SOURCE_DIR/api"
    elif [ -f "$SOURCE_DIR/requirements.txt" ]; then
        _BACKEND_DIR="$SOURCE_DIR"
    elif [ -f "$SOURCE_DIR/pyproject.toml" ]; then
        _BACKEND_DIR="$SOURCE_DIR"
    else
        log_error "Could not find Python backend directory"
        return 1
    fi

    log_debug "Found backend directory: $_BACKEND_DIR"
    return 0
}

# Build Python backend
# Returns: 0 on success, 3 on build failure
build_python_backend() {
    log_info "Building Python backend..."

    # Check prerequisites
    if [ -z "$SOURCE_DIR" ]; then
        log_error "SOURCE_DIR not set. Run acquire_source first."
        return 3
    fi

    if [ ! -d "$VENV_PATH" ] || [ ! -x "$VENV_PATH/bin/pip" ]; then
        log_error "Virtual environment not ready. Run create_python_venv first."
        return 3
    fi

    # Find backend directory
    _find_backend_dir || return 3

    log_info "Installing Python dependencies from: $_BACKEND_DIR"

    # Change to backend directory
    local original_dir
    original_dir="$(pwd)"
    cd "$_BACKEND_DIR" || {
        log_error "Failed to change to backend directory: $_BACKEND_DIR"
        return 3
    }

    # Install dependencies
    local install_result=0

    if [ -f "requirements.txt" ]; then
        log_info "Installing from requirements.txt..."

        # Install with timeout
        timeout "$PIP_INSTALL_TIMEOUT" "$VENV_PATH/bin/pip" install -r requirements.txt 2>&1 | tee -a "$INSTALL_LOG_FILE"
        install_result=${PIPESTATUS[0]}

        if [ $install_result -eq 124 ]; then
            log_error "pip install timed out after $PIP_INSTALL_TIMEOUT seconds"
            cd "$original_dir"
            return 3
        elif [ $install_result -ne 0 ]; then
            log_error "pip install failed with exit code: $install_result"
            cd "$original_dir"
            return 3
        fi
    elif [ -f "pyproject.toml" ]; then
        log_info "Installing from pyproject.toml..."

        timeout "$PIP_INSTALL_TIMEOUT" "$VENV_PATH/bin/pip" install -e . 2>&1 | tee -a "$INSTALL_LOG_FILE"
        install_result=${PIPESTATUS[0]}

        if [ $install_result -eq 124 ]; then
            log_error "pip install timed out after $PIP_INSTALL_TIMEOUT seconds"
            cd "$original_dir"
            return 3
        elif [ $install_result -ne 0 ]; then
            log_error "pip install failed with exit code: $install_result"
            cd "$original_dir"
            return 3
        fi
    else
        log_error "No requirements.txt or pyproject.toml found in $_BACKEND_DIR"
        cd "$original_dir"
        return 3
    fi

    cd "$original_dir"

    # Verify FastAPI is installed
    log_info "Verifying FastAPI installation..."
    if ! "$VENV_PATH/bin/pip" show fastapi >/dev/null 2>&1; then
        log_error "FastAPI not installed"
        return 3
    fi
    log_debug "FastAPI: $("$VENV_PATH/bin/pip" show fastapi | grep Version | awk '{print $2}')"

    # Verify uvicorn is installed
    log_info "Verifying uvicorn installation..."
    if ! "$VENV_PATH/bin/pip" show uvicorn >/dev/null 2>&1; then
        log_error "uvicorn not installed"
        return 3
    fi
    log_debug "uvicorn: $("$VENV_PATH/bin/pip" show uvicorn | grep Version | awk '{print $2}')"

    # Run basic import test
    log_info "Running import test..."
    if ! "$VENV_PATH/bin/python3" -c "import fastapi; import uvicorn" 2>&1 | tee -a "$INSTALL_LOG_FILE"; then
        log_error "Python import test failed"
        return 3
    fi

    # Try to import the application module
    local app_module=""
    if [ -f "$_BACKEND_DIR/app/main.py" ]; then
        app_module="app.main"
    elif [ -f "$_BACKEND_DIR/main.py" ]; then
        app_module="main"
    fi

    if [ -n "$app_module" ]; then
        log_info "Testing application import: $app_module"
        # Add the backend directory to PYTHONPATH for import test
        if ! PYTHONPATH="$_BACKEND_DIR:$PYTHONPATH" "$VENV_PATH/bin/python3" -c "import ${app_module%%.*}" 2>&1 | tee -a "$INSTALL_LOG_FILE"; then
            log_warn "Application import test failed (may be OK if dependencies are external)"
        fi
    fi

    # Save installed packages list
    log_info "Saving installed packages list..."
    mkdir -p "$INSTALL_BASE"
    "$VENV_PATH/bin/pip" freeze > "$INSTALL_BASE/installed-packages.txt" 2>&1

    local package_count
    package_count="$(wc -l < "$INSTALL_BASE/installed-packages.txt")"
    log_info "Installed $package_count Python packages"

    _log_write "INFO" "Python backend built successfully: $package_count packages installed"

    return 0
}

# =============================================================================
# React Frontend Build
# =============================================================================

# Find React frontend directory
# Sets: _FRONTEND_DIR
# Returns: 0 if found, 1 if not
_find_frontend_dir() {
    _FRONTEND_DIR=""

    if [ -z "$SOURCE_DIR" ]; then
        log_error "SOURCE_DIR not set. Run acquire_source first."
        return 1
    fi

    # Check common locations
    if [ -d "$SOURCE_DIR/web/ui" ] && [ -f "$SOURCE_DIR/web/ui/package.json" ]; then
        _FRONTEND_DIR="$SOURCE_DIR/web/ui"
    elif [ -d "$SOURCE_DIR/frontend" ] && [ -f "$SOURCE_DIR/frontend/package.json" ]; then
        _FRONTEND_DIR="$SOURCE_DIR/frontend"
    elif [ -d "$SOURCE_DIR/ui" ] && [ -f "$SOURCE_DIR/ui/package.json" ]; then
        _FRONTEND_DIR="$SOURCE_DIR/ui"
    elif [ -d "$SOURCE_DIR/client" ] && [ -f "$SOURCE_DIR/client/package.json" ]; then
        _FRONTEND_DIR="$SOURCE_DIR/client"
    elif [ -f "$SOURCE_DIR/package.json" ]; then
        # Check if it's a frontend package (has react dependency)
        if grep -q '"react"' "$SOURCE_DIR/package.json" 2>/dev/null; then
            _FRONTEND_DIR="$SOURCE_DIR"
        fi
    fi

    if [ -z "$_FRONTEND_DIR" ]; then
        log_warn "Could not find React frontend directory"
        return 1
    fi

    log_debug "Found frontend directory: $_FRONTEND_DIR"
    return 0
}

# Build React frontend
# Returns: 0 on success, 3 on build failure
build_react_frontend() {
    log_info "Building React frontend..."

    # Check prerequisites
    if [ -z "$SOURCE_DIR" ]; then
        log_error "SOURCE_DIR not set. Run acquire_source first."
        return 3
    fi

    # Check Node.js and npm
    if ! command -v node >/dev/null 2>&1; then
        log_error "Node.js is not installed"
        return 3
    fi

    if ! command -v npm >/dev/null 2>&1; then
        log_error "npm is not installed"
        return 3
    fi

    # Find frontend directory
    if ! _find_frontend_dir; then
        log_warn "No React frontend found, skipping frontend build"
        return 0
    fi

    log_info "Building frontend from: $_FRONTEND_DIR"

    # Change to frontend directory
    local original_dir
    original_dir="$(pwd)"
    cd "$_FRONTEND_DIR" || {
        log_error "Failed to change to frontend directory: $_FRONTEND_DIR"
        return 3
    }

    # Clean old node_modules if exists and corrupted
    if [ -d "node_modules" ] && [ ! -f "node_modules/.package-lock.json" ]; then
        log_warn "node_modules appears incomplete, removing..."
        rm -rf node_modules
    fi

    # Install dependencies
    log_info "Installing npm dependencies (this may take several minutes)..."

    local npm_cmd="npm ci"
    # Use npm install if no package-lock.json exists
    if [ ! -f "package-lock.json" ]; then
        npm_cmd="npm install"
        log_debug "No package-lock.json found, using npm install instead of npm ci"
    fi

    timeout "$NPM_INSTALL_TIMEOUT" $npm_cmd 2>&1 | tee -a "$INSTALL_LOG_FILE"
    local npm_result=${PIPESTATUS[0]}

    if [ $npm_result -eq 124 ]; then
        log_error "npm install timed out after $NPM_INSTALL_TIMEOUT seconds"
        cd "$original_dir"
        return 3
    elif [ $npm_result -ne 0 ]; then
        log_error "npm install failed with exit code: $npm_result"
        cd "$original_dir"
        return 3
    fi

    # Build the frontend
    log_info "Building React application..."

    timeout "$NPM_BUILD_TIMEOUT" npm run build 2>&1 | tee -a "$INSTALL_LOG_FILE"
    local build_result=${PIPESTATUS[0]}

    if [ $build_result -eq 124 ]; then
        log_error "npm build timed out after $NPM_BUILD_TIMEOUT seconds"
        cd "$original_dir"
        return 3
    elif [ $build_result -ne 0 ]; then
        log_error "npm build failed with exit code: $build_result"
        cd "$original_dir"
        return 3
    fi

    cd "$original_dir"

    # Find build output directory
    local build_dir=""
    if [ -d "$_FRONTEND_DIR/dist" ]; then
        build_dir="$_FRONTEND_DIR/dist"
    elif [ -d "$_FRONTEND_DIR/build" ]; then
        build_dir="$_FRONTEND_DIR/build"
    elif [ -d "$_FRONTEND_DIR/.next" ]; then
        build_dir="$_FRONTEND_DIR/.next"
    elif [ -d "$_FRONTEND_DIR/out" ]; then
        build_dir="$_FRONTEND_DIR/out"
    fi

    if [ -z "$build_dir" ] || [ ! -d "$build_dir" ]; then
        log_error "Build output directory not found (checked dist/, build/, .next/, out/)"
        return 3
    fi

    log_debug "Build output directory: $build_dir"

    # Verify critical files exist
    if [ -f "$build_dir/index.html" ]; then
        log_debug "Found index.html in build output"
    elif [ -d "$build_dir/server" ]; then
        # Next.js build structure
        log_debug "Found Next.js server build"
    else
        log_warn "index.html not found in build output (may be OK for Next.js)"
    fi

    # Store build directory path for later use
    export FRONTEND_BUILD_DIR="$build_dir"

    local file_count
    file_count="$(find "$build_dir" -type f | wc -l)"
    log_info "Frontend build complete: $file_count files generated"

    _log_write "INFO" "React frontend built successfully: $file_count files in $build_dir"

    return 0
}

# =============================================================================
# Build Verification
# =============================================================================

# Verify all build artifacts exist
# Returns: 0 if complete, 3 if any missing
verify_build() {
    log_info "Verifying build artifacts..."

    local failed=0
    local results=()

    # Check Python venv
    if [ -x "$VENV_PATH/bin/python3" ]; then
        results+=("[OK] Python venv: $VENV_PATH")
    else
        results+=("[FAIL] Python venv not found: $VENV_PATH")
        failed=1
    fi

    # Check pip in venv
    if [ -x "$VENV_PATH/bin/pip" ]; then
        results+=("[OK] pip in venv")
    else
        results+=("[FAIL] pip not found in venv")
        failed=1
    fi

    # Check uvicorn in venv
    if [ -x "$VENV_PATH/bin/uvicorn" ]; then
        results+=("[OK] uvicorn in venv")
    else
        results+=("[FAIL] uvicorn not found in venv")
        failed=1
    fi

    # Check FastAPI is importable
    if "$VENV_PATH/bin/python3" -c "import fastapi" 2>/dev/null; then
        results+=("[OK] FastAPI importable")
    else
        results+=("[FAIL] FastAPI not importable")
        failed=1
    fi

    # Check backend source exists
    if _find_backend_dir 2>/dev/null; then
        if [ -f "$_BACKEND_DIR/app/main.py" ] || [ -f "$_BACKEND_DIR/main.py" ]; then
            results+=("[OK] Backend source found: $_BACKEND_DIR")
        else
            results+=("[WARN] Backend source found but no main.py")
        fi
    else
        results+=("[WARN] Backend directory not identified")
    fi

    # Check frontend build
    if _find_frontend_dir 2>/dev/null; then
        local build_dir=""
        if [ -d "$_FRONTEND_DIR/dist" ]; then
            build_dir="$_FRONTEND_DIR/dist"
        elif [ -d "$_FRONTEND_DIR/build" ]; then
            build_dir="$_FRONTEND_DIR/build"
        elif [ -d "$_FRONTEND_DIR/.next" ]; then
            build_dir="$_FRONTEND_DIR/.next"
        fi

        if [ -n "$build_dir" ] && [ -d "$build_dir" ]; then
            local file_count
            file_count="$(find "$build_dir" -type f | wc -l)"
            results+=("[OK] Frontend build: $build_dir ($file_count files)")
        else
            results+=("[WARN] Frontend build directory not found")
        fi
    else
        results+=("[INFO] No frontend to verify")
    fi

    # Check installed packages file
    if [ -f "$INSTALL_BASE/installed-packages.txt" ]; then
        local pkg_count
        pkg_count="$(wc -l < "$INSTALL_BASE/installed-packages.txt")"
        results+=("[OK] Package manifest: $pkg_count packages")
    else
        results+=("[WARN] Package manifest not found")
    fi

    # Print results
    echo ""
    echo "BUILD VERIFICATION RESULTS:"
    echo "==========================="
    for result in "${results[@]}"; do
        echo "  $result"
    done
    echo "==========================="
    echo ""

    # Log results
    _log_write "INFO" "Build verification results:"
    for result in "${results[@]}"; do
        _log_write "INFO" "  $result"
    done

    if [ $failed -ne 0 ]; then
        log_error "Build verification failed"
        return 3
    fi

    log_info "Build verification passed"
    return 0
}

# =============================================================================
# Platform-Specific Optimization
# =============================================================================

# Apply platform-specific build optimizations
# Input: platform type from detection module
# Returns: 0 on success
apply_build_optimizations() {
    local platform="${1:-generic}"

    log_info "Applying build optimizations for platform: $platform"

    # Get CPU cores for parallel builds
    local cpu_cores
    cpu_cores="$(nproc 2>/dev/null || echo 1)"

    # Set MAKEFLAGS for parallel compilation of native extensions
    export MAKEFLAGS="-j$cpu_cores"
    log_debug "Set MAKEFLAGS=-j$cpu_cores"

    # Platform-specific optimizations
    case "$platform" in
        raspberry_pi_1|raspberry_pi_zero|arm32_v6)
            # Older/slower ARM - conservative settings
            export MAKEFLAGS="-j1"
            export PIP_NO_CACHE_DIR=1  # Save memory
            log_info "Applied low-memory ARM optimizations"
            ;;

        raspberry_pi_2|raspberry_pi_3|raspberry_pi_zero2|arm32_generic)
            # Moderate ARM - balanced settings
            export MAKEFLAGS="-j2"
            log_info "Applied moderate ARM optimizations"
            ;;

        raspberry_pi_4|raspberry_pi_5|arm64_generic|orange_pi*)
            # Modern ARM - allow more parallelism
            if [ "$cpu_cores" -gt 4 ]; then
                export MAKEFLAGS="-j4"
            else
                export MAKEFLAGS="-j$cpu_cores"
            fi
            log_info "Applied modern ARM optimizations"
            ;;

        x86_64|x86_64_vm|amd64)
            # x86_64 - full parallelism
            export MAKEFLAGS="-j$cpu_cores"
            log_info "Applied x86_64 optimizations"
            ;;

        *)
            # Generic fallback
            log_debug "No specific optimizations for platform: $platform"
            ;;
    esac

    # Set npm concurrency to avoid overwhelming low-memory systems
    local total_ram_mb
    total_ram_mb="$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo 2048)"

    if [ "$total_ram_mb" -lt 1024 ]; then
        export npm_config_jobs=1
        log_debug "Set npm_config_jobs=1 (low memory system)"
    elif [ "$total_ram_mb" -lt 2048 ]; then
        export npm_config_jobs=2
        log_debug "Set npm_config_jobs=2"
    fi

    _log_write "INFO" "Build optimizations applied: MAKEFLAGS=$MAKEFLAGS, platform=$platform"

    return 0
}

# =============================================================================
# Combined Build Function
# =============================================================================

# Run complete build process
# Returns: 0 on success, 3 on failure
run_full_build() {
    local source_path=""
    local platform="generic"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --source)
                source_path="$2"
                shift 2
                ;;
            --platform)
                platform="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    log_info "Starting full build process..."

    # Apply optimizations
    apply_build_optimizations "$platform"

    # Acquire source
    if [ -n "$source_path" ]; then
        acquire_source --source "$source_path" || return 3
    else
        acquire_source || return 3
    fi

    # Create venv
    create_python_venv || return 3

    # Build backend
    build_python_backend || return 3

    # Build frontend
    build_react_frontend || return 3

    # Verify build
    verify_build || return 3

    log_info "Full build process completed successfully"
    return 0
}

# =============================================================================
# Cleanup Function
# =============================================================================

# Clean up build artifacts (optional)
# Returns: 0 on success
cleanup_build_source() {
    log_info "Cleaning up build source..."

    # Only clean up if it's a temporary directory we created
    if [ -n "$SOURCE_DIR" ] && [[ "$SOURCE_DIR" == /tmp/water-controller-src.* ]]; then
        log_debug "Removing temporary source directory: $SOURCE_DIR"
        rm -rf "$SOURCE_DIR"
        SOURCE_DIR=""
        log_info "Temporary source directory removed"
    else
        log_debug "Source directory is not temporary, keeping: $SOURCE_DIR"
    fi

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
        --acquire-source)
            shift
            acquire_source "$@"
            exit $?
            ;;
        --create-venv)
            create_python_venv
            exit $?
            ;;
        --build-backend)
            if [ -z "$SOURCE_DIR" ]; then
                log_error "SOURCE_DIR not set. Use --acquire-source first or set SOURCE_DIR environment variable."
                exit 1
            fi
            build_python_backend
            exit $?
            ;;
        --build-frontend)
            if [ -z "$SOURCE_DIR" ]; then
                log_error "SOURCE_DIR not set. Use --acquire-source first or set SOURCE_DIR environment variable."
                exit 1
            fi
            build_react_frontend
            exit $?
            ;;
        --verify)
            verify_build
            exit $?
            ;;
        --full)
            shift
            run_full_build "$@"
            exit $?
            ;;
        --cleanup)
            cleanup_build_source
            exit $?
            ;;
        --help|-h)
            echo "Water-Controller Build Module v$BUILD_VERSION"
            echo ""
            echo "Usage: $0 [OPTION]"
            echo ""
            echo "Options:"
            echo "  --acquire-source [--source PATH] [--branch NAME] [--tag TAG]"
            echo "                          Acquire source from git or local path"
            echo "  --create-venv           Create Python virtual environment"
            echo "  --build-backend         Build Python backend (requires SOURCE_DIR)"
            echo "  --build-frontend        Build React frontend (requires SOURCE_DIR)"
            echo "  --verify                Verify all build artifacts"
            echo "  --full [--source PATH] [--platform NAME]"
            echo "                          Run complete build process"
            echo "  --cleanup               Clean up temporary build files"
            echo "  --help, -h              Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  SOURCE_DIR              Source code directory (set by --acquire-source)"
            echo "  INSTALL_LOG_FILE        Log file path"
            echo ""
            echo "Build paths:"
            echo "  Venv: $VENV_PATH"
            echo "  App:  $APP_PATH"
            echo "  Web:  $WEB_PATH"
            ;;
        *)
            echo "Usage: $0 [--acquire-source|--create-venv|--build-backend|--build-frontend|--verify|--full|--cleanup|--help]" >&2
            exit 1
            ;;
    esac
fi
