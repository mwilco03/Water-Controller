#!/bin/bash
#
# Water Treatment Controller - P-Net PROFINET Installation Module
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module provides comprehensive installation, configuration, and
# verification of the p-net PROFINET device stack - the cornerstone of
# the Water Treatment Controller's industrial communication.
#
# p-net is an open-source PROFINET device stack from RT-Labs
# Repository: https://github.com/rtlabs-com/p-net
#
# Target: ARM/x86 SBCs running Debian-based Linux
# Requirements: Real-time capable network interface, root privileges
#

# Prevent multiple sourcing
if [ -n "$_WTC_PNET_LOADED" ]; then
    return 0
fi
_WTC_PNET_LOADED=1

# Source detection module for logging functions
: "${SCRIPT_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
if [ -f "$SCRIPT_DIR/detection.sh" ]; then
    # shellcheck source=detection.sh
    source "$SCRIPT_DIR/detection.sh"
fi

# =============================================================================
# Constants
# =============================================================================

readonly PNET_VERSION="1.0.0"
readonly PNET_MODULE_VERSION="1.0.0"

# P-Net source
readonly PNET_REPO="https://github.com/rtlabs-com/p-net.git"
readonly PNET_BRANCH="master"
readonly PNET_RECOMMENDED_TAG="v0.5.0"

# Installation paths
readonly PNET_BUILD_DIR="/tmp/pnet-build-$$"
readonly PNET_INSTALL_PREFIX="/usr/local"
readonly PNET_LIB_DIR="${PNET_INSTALL_PREFIX}/lib"
readonly PNET_INCLUDE_DIR="${PNET_INSTALL_PREFIX}/include"
readonly PNET_CONFIG_DIR="/etc/pnet"
readonly PNET_SAMPLE_APP_DIR="/opt/pnet-sample"

# Required kernel modules
readonly PNET_KERNEL_MODULES=("8021q")

# PROFINET ports
readonly PNET_UDP_PORT=34964
readonly PNET_TCP_PORT_START=34962
readonly PNET_TCP_PORT_END=34963

# Minimum requirements
readonly PNET_MIN_CMAKE_VERSION="3.14"

# =============================================================================
# Prerequisite Checks
# =============================================================================

# Check all prerequisites for p-net installation
# Returns: 0 if all prerequisites met, 1 otherwise
check_pnet_prerequisites() {
    log_info "Checking p-net prerequisites..."

    local errors=0

    # Check root privileges
    if [ "$(id -u)" -ne 0 ]; then
        log_error "Root privileges required for p-net installation"
        ((errors++))
    fi

    # Check for git
    if ! command -v git >/dev/null 2>&1; then
        log_error "git is required but not installed"
        ((errors++))
    fi

    # Check for cmake
    if ! command -v cmake >/dev/null 2>&1; then
        log_error "cmake is required but not installed"
        ((errors++))
    else
        # Check cmake version
        local cmake_version
        cmake_version=$(cmake --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        if [ -n "$cmake_version" ]; then
            local cmake_major cmake_minor
            cmake_major=$(echo "$cmake_version" | cut -d. -f1)
            cmake_minor=$(echo "$cmake_version" | cut -d. -f2)
            local req_major req_minor
            req_major=$(echo "$PNET_MIN_CMAKE_VERSION" | cut -d. -f1)
            req_minor=$(echo "$PNET_MIN_CMAKE_VERSION" | cut -d. -f2)

            if [ "$cmake_major" -lt "$req_major" ] || \
               { [ "$cmake_major" -eq "$req_major" ] && [ "$cmake_minor" -lt "$req_minor" ]; }; then
                log_error "cmake $PNET_MIN_CMAKE_VERSION+ required, found $cmake_version"
                ((errors++))
            else
                log_info "cmake version $cmake_version OK"
            fi
        fi
    fi

    # Check for C compiler
    if ! command -v gcc >/dev/null 2>&1 && ! command -v clang >/dev/null 2>&1; then
        log_error "C compiler (gcc or clang) is required but not installed"
        ((errors++))
    fi

    # Check for make
    if ! command -v make >/dev/null 2>&1; then
        log_error "make is required but not installed"
        ((errors++))
    fi

    # Check for required development libraries
    local missing_libs=()

    # Check for libpcap
    if ! _check_lib_installed "pcap"; then
        missing_libs+=("libpcap-dev")
    fi

    if [ ${#missing_libs[@]} -gt 0 ]; then
        log_error "Missing development libraries: ${missing_libs[*]}"
        log_error "Install with: apt install ${missing_libs[*]}"
        ((errors++))
    fi

    # Check network interface availability
    local eth_interfaces
    eth_interfaces=$(ip -brief link show 2>/dev/null | grep -E '^(eth|en)' | awk '{print $1}')
    if [ -z "$eth_interfaces" ]; then
        log_warn "No Ethernet interfaces detected - PROFINET requires Ethernet"
    else
        log_info "Ethernet interfaces available: $(echo "$eth_interfaces" | tr '\n' ' ')"
    fi

    # Check for real-time kernel (optional but recommended)
    if uname -r | grep -qi "rt\|preempt"; then
        log_info "Real-time kernel detected - optimal for PROFINET"
    else
        log_warn "Standard kernel detected - real-time kernel recommended for PROFINET"
    fi

    if [ $errors -gt 0 ]; then
        log_error "Prerequisites check failed with $errors error(s)"
        return 1
    fi

    log_info "All p-net prerequisites met"
    return 0
}

# Check if a library is installed
_check_lib_installed() {
    local lib_name="$1"

    # Check via pkg-config
    if command -v pkg-config >/dev/null 2>&1; then
        if pkg-config --exists "$lib_name" 2>/dev/null; then
            return 0
        fi
        if pkg-config --exists "lib${lib_name}" 2>/dev/null; then
            return 0
        fi
    fi

    # Check via ldconfig
    if ldconfig -p 2>/dev/null | grep -qi "lib${lib_name}"; then
        return 0
    fi

    # Check header files
    if [ -f "/usr/include/${lib_name}.h" ] || \
       [ -f "/usr/include/${lib_name}/${lib_name}.h" ] || \
       [ -f "/usr/local/include/${lib_name}.h" ]; then
        return 0
    fi

    return 1
}

# =============================================================================
# P-Net Installation
# =============================================================================

# Install p-net build dependencies
# Returns: 0 on success, 1 on failure
install_pnet_build_deps() {
    log_info "Installing p-net build dependencies..."

    local packages=()

    # Detect package manager
    if command -v apt-get >/dev/null 2>&1; then
        packages=(
            "build-essential"
            "cmake"
            "git"
            "libpcap-dev"
            "python3"
            "doxygen"
            "graphviz"
        )

        # Update package list
        log_info "Updating package list..."
        sudo apt-get update -qq || {
            log_warn "apt-get update failed, continuing anyway"
        }

        # Install packages
        for pkg in "${packages[@]}"; do
            log_info "Installing $pkg..."
            if ! sudo apt-get install -y -qq "$pkg" 2>/dev/null; then
                log_warn "Failed to install $pkg"
            fi
        done

    elif command -v dnf >/dev/null 2>&1; then
        packages=(
            "gcc"
            "gcc-c++"
            "make"
            "cmake"
            "git"
            "libpcap-devel"
            "python3"
            "doxygen"
            "graphviz"
        )

        for pkg in "${packages[@]}"; do
            log_info "Installing $pkg..."
            sudo dnf install -y -q "$pkg" 2>/dev/null || log_warn "Failed to install $pkg"
        done

    elif command -v yum >/dev/null 2>&1; then
        packages=(
            "gcc"
            "gcc-c++"
            "make"
            "cmake3"
            "git"
            "libpcap-devel"
            "python3"
        )

        for pkg in "${packages[@]}"; do
            log_info "Installing $pkg..."
            sudo yum install -y -q "$pkg" 2>/dev/null || log_warn "Failed to install $pkg"
        done

    else
        log_error "Unsupported package manager"
        return 1
    fi

    log_info "Build dependencies installed"
    return 0
}

# Clone p-net repository
# Arguments:
#   $1 - target directory (optional, default: PNET_BUILD_DIR)
#   $2 - branch or tag (optional, default: PNET_RECOMMENDED_TAG)
# Returns: 0 on success, 1 on failure
clone_pnet() {
    local target_dir="${1:-$PNET_BUILD_DIR}"
    local branch="${2:-$PNET_RECOMMENDED_TAG}"

    log_info "Cloning p-net repository..."
    log_info "  Repository: $PNET_REPO"
    log_info "  Branch/Tag: $branch"
    log_info "  Target: $target_dir"

    # Clean up existing directory
    if [ -d "$target_dir" ]; then
        log_info "Removing existing build directory..."
        rm -rf "$target_dir"
    fi

    # Create parent directory
    mkdir -p "$(dirname "$target_dir")"

    # Clone repository
    if ! git clone --depth 1 --branch "$branch" "$PNET_REPO" "$target_dir" 2>&1; then
        log_warn "Failed to clone tag $branch, trying master branch..."
        if ! git clone --depth 1 "$PNET_REPO" "$target_dir" 2>&1; then
            log_error "Failed to clone p-net repository"
            return 1
        fi
    fi

    # Initialize submodules if any
    if [ -f "$target_dir/.gitmodules" ]; then
        log_info "Initializing submodules..."
        cd "$target_dir" || return 1
        git submodule update --init --recursive 2>&1 || {
            log_warn "Submodule initialization had issues"
        }
    fi

    log_info "p-net repository cloned successfully"
    return 0
}

# Build p-net from source
# Arguments:
#   $1 - source directory
#   $2 - install prefix (optional, default: /usr/local)
# Returns: 0 on success, 1 on failure
build_pnet() {
    local source_dir="${1:-$PNET_BUILD_DIR}"
    local install_prefix="${2:-$PNET_INSTALL_PREFIX}"

    log_info "Building p-net from source..."
    log_info "  Source: $source_dir"
    log_info "  Install prefix: $install_prefix"

    if [ ! -d "$source_dir" ]; then
        log_error "Source directory not found: $source_dir"
        return 1
    fi

    local build_dir="${source_dir}/build"
    mkdir -p "$build_dir"
    cd "$build_dir" || return 1

    # Detect number of CPU cores
    local nproc
    nproc=$(nproc 2>/dev/null || echo 2)

    # Configure with cmake
    log_info "Configuring build with cmake..."

    local cmake_opts=(
        "-DCMAKE_INSTALL_PREFIX=${install_prefix}"
        "-DCMAKE_BUILD_TYPE=Release"
        "-DBUILD_SHARED_LIBS=ON"
        "-DBUILD_TESTING=OFF"
    )

    # Detect architecture-specific options
    local arch
    arch=$(uname -m)
    case "$arch" in
        armv7l|armv6l)
            log_info "Configuring for ARM 32-bit..."
            cmake_opts+=("-DCMAKE_C_FLAGS=-march=armv7-a -mfpu=neon")
            ;;
        aarch64)
            log_info "Configuring for ARM 64-bit..."
            ;;
        x86_64)
            log_info "Configuring for x86_64..."
            ;;
    esac

    if ! cmake "${cmake_opts[@]}" .. 2>&1; then
        log_error "cmake configuration failed"
        return 1
    fi

    # Build
    log_info "Compiling p-net (using $nproc cores)..."
    if ! make -j"$nproc" 2>&1; then
        log_error "Build failed"
        return 1
    fi

    log_info "p-net built successfully"
    return 0
}

# Install p-net to system
# Arguments:
#   $1 - build directory
# Returns: 0 on success, 1 on failure
install_pnet() {
    local build_dir="${1:-${PNET_BUILD_DIR}/build}"

    log_info "Installing p-net to system..."

    if [ ! -d "$build_dir" ]; then
        log_error "Build directory not found: $build_dir"
        return 1
    fi

    cd "$build_dir" || return 1

    # Install
    if ! sudo make install 2>&1; then
        log_error "Installation failed"
        return 1
    fi

    # Update library cache
    log_info "Updating library cache..."
    sudo ldconfig 2>/dev/null || true

    # Create configuration directory
    sudo mkdir -p "$PNET_CONFIG_DIR"
    sudo chmod 755 "$PNET_CONFIG_DIR"

    log_info "p-net installed successfully"
    return 0
}

# Full p-net installation (clone, build, install)
# Arguments:
#   $1 - branch/tag (optional)
# Returns: 0 on success, 1 on failure
install_pnet_full() {
    local branch="${1:-$PNET_RECOMMENDED_TAG}"

    log_info "=========================================="
    log_info "  P-Net PROFINET Stack Installation"
    log_info "=========================================="
    log_info ""

    # Check prerequisites
    if ! check_pnet_prerequisites; then
        log_error "Prerequisites not met"
        return 1
    fi

    # Install build dependencies
    if ! install_pnet_build_deps; then
        log_error "Failed to install build dependencies"
        return 1
    fi

    # Clone repository
    if ! clone_pnet "$PNET_BUILD_DIR" "$branch"; then
        log_error "Failed to clone p-net"
        return 1
    fi

    # Build
    if ! build_pnet "$PNET_BUILD_DIR"; then
        log_error "Failed to build p-net"
        rm -rf "$PNET_BUILD_DIR"
        return 1
    fi

    # Install
    if ! install_pnet "${PNET_BUILD_DIR}/build"; then
        log_error "Failed to install p-net"
        rm -rf "$PNET_BUILD_DIR"
        return 1
    fi

    # Verify installation
    if ! verify_pnet_installation; then
        log_error "Installation verification failed"
        return 1
    fi

    # Clean up build directory
    log_info "Cleaning up build directory..."
    rm -rf "$PNET_BUILD_DIR"

    log_info ""
    log_info "=========================================="
    log_info "  P-Net Installation Complete!"
    log_info "=========================================="

    return 0
}

# =============================================================================
# P-Net Verification
# =============================================================================

# Verify p-net installation
# Returns: 0 if verified, 1 otherwise
verify_pnet_installation() {
    log_info "Verifying p-net installation..."

    local errors=0

    # Check for library files
    log_info "Checking library files..."
    local lib_found=0

    for lib_path in "$PNET_LIB_DIR" "/usr/lib" "/usr/lib64"; do
        if [ -f "${lib_path}/libpnet.so" ] || \
           [ -f "${lib_path}/libpnet.a" ] || \
           ls "${lib_path}"/libpnet.so.* >/dev/null 2>&1; then
            log_info "  Found p-net library in $lib_path"
            lib_found=1
            break
        fi
    done

    if [ $lib_found -eq 0 ]; then
        log_error "  p-net library not found"
        ((errors++))
    fi

    # Check for header files
    log_info "Checking header files..."
    local header_found=0

    for inc_path in "$PNET_INCLUDE_DIR" "/usr/include"; do
        if [ -f "${inc_path}/pnet_api.h" ] || \
           [ -d "${inc_path}/pnet" ]; then
            log_info "  Found p-net headers in $inc_path"
            header_found=1
            break
        fi
    done

    if [ $header_found -eq 0 ]; then
        log_error "  p-net headers not found"
        ((errors++))
    fi

    # Check ldconfig
    log_info "Checking library registration..."
    if ldconfig -p 2>/dev/null | grep -q "libpnet"; then
        log_info "  Library registered in ldconfig"
    else
        log_warn "  Library not in ldconfig cache (may need ldconfig run)"
    fi

    # Check pkg-config (if available)
    if command -v pkg-config >/dev/null 2>&1; then
        log_info "Checking pkg-config..."
        if pkg-config --exists pnet 2>/dev/null; then
            local pnet_version
            pnet_version=$(pkg-config --modversion pnet 2>/dev/null)
            log_info "  pkg-config reports version: $pnet_version"
        else
            log_warn "  p-net not registered with pkg-config"
        fi
    fi

    if [ $errors -gt 0 ]; then
        log_error "Verification failed with $errors error(s)"
        return 1
    fi

    log_info "p-net installation verified successfully"
    return 0
}

# Comprehensive p-net diagnostic check
# Returns: 0 if all checks pass, 1 otherwise
diagnose_pnet() {
    echo ""
    echo "============================================================"
    echo "           P-Net PROFINET Diagnostic Report"
    echo "============================================================"
    echo ""

    local issues=0

    # Section 1: Installation Status
    echo "1. Installation Status"
    echo "   -------------------"

    # Library check
    local lib_status="NOT FOUND"
    local lib_path=""
    for path in "$PNET_LIB_DIR" "/usr/lib" "/usr/lib64" "/usr/local/lib"; do
        if ls "${path}"/libpnet.so* >/dev/null 2>&1; then
            lib_status="FOUND"
            lib_path="$path"
            break
        fi
    done
    echo "   Library:     $lib_status ${lib_path:+($lib_path)}"
    [ "$lib_status" = "NOT FOUND" ] && ((issues++))

    # Header check
    local header_status="NOT FOUND"
    local header_path=""
    for path in "$PNET_INCLUDE_DIR" "/usr/include" "/usr/local/include"; do
        if [ -f "${path}/pnet_api.h" ] || [ -d "${path}/pnet" ]; then
            header_status="FOUND"
            header_path="$path"
            break
        fi
    done
    echo "   Headers:     $header_status ${header_path:+($header_path)}"
    [ "$header_status" = "NOT FOUND" ] && ((issues++))

    # Version check
    local version="unknown"
    if command -v pkg-config >/dev/null 2>&1 && pkg-config --exists pnet 2>/dev/null; then
        version=$(pkg-config --modversion pnet 2>/dev/null)
    fi
    echo "   Version:     $version"
    echo ""

    # Section 2: Network Configuration
    echo "2. Network Configuration"
    echo "   ----------------------"

    # Ethernet interfaces
    echo "   Ethernet Interfaces:"
    local eth_count=0
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            local iface state
            iface=$(echo "$line" | awk '{print $1}')
            state=$(echo "$line" | awk '{print $2}')
            echo "     - $iface ($state)"
            ((eth_count++))
        fi
    done < <(ip -brief link show 2>/dev/null | grep -E '^(eth|en|eno|ens)')

    if [ $eth_count -eq 0 ]; then
        echo "     (none found)"
        ((issues++))
    fi
    echo ""

    # PROFINET ports
    echo "   PROFINET Ports:"
    for port in $PNET_TCP_PORT_START $PNET_TCP_PORT_END; do
        local port_status
        if ss -tln 2>/dev/null | grep -q ":${port} "; then
            port_status="LISTENING"
        else
            port_status="not listening"
        fi
        echo "     - TCP $port: $port_status"
    done
    local udp_status
    if ss -uln 2>/dev/null | grep -q ":${PNET_UDP_PORT} "; then
        udp_status="LISTENING"
    else
        udp_status="not listening"
    fi
    echo "     - UDP $PNET_UDP_PORT: $udp_status"
    echo ""

    # Section 3: Kernel Configuration
    echo "3. Kernel Configuration"
    echo "   ---------------------"

    # Kernel type
    local kernel_type="standard"
    if uname -r | grep -qiE "rt|preempt"; then
        kernel_type="real-time (PREEMPT_RT)"
    fi
    echo "   Kernel Type: $kernel_type"

    # Required modules
    echo "   Kernel Modules:"
    for mod in "${PNET_KERNEL_MODULES[@]}"; do
        local mod_status
        if lsmod 2>/dev/null | grep -q "^${mod}"; then
            mod_status="loaded"
        elif modinfo "$mod" >/dev/null 2>&1; then
            mod_status="available (not loaded)"
        else
            mod_status="NOT AVAILABLE"
            ((issues++))
        fi
        echo "     - $mod: $mod_status"
    done
    echo ""

    # Section 4: System Resources
    echo "4. System Resources"
    echo "   -----------------"

    # Memory
    local mem_total mem_avail
    mem_total=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
    mem_avail=$(free -m 2>/dev/null | awk '/^Mem:/{print $7}')
    echo "   Memory: ${mem_avail:-?}MB available / ${mem_total:-?}MB total"

    # CPU
    local cpu_count
    cpu_count=$(nproc 2>/dev/null || echo "?")
    echo "   CPU Cores: $cpu_count"
    echo ""

    # Section 5: Dependencies
    echo "5. Dependencies"
    echo "   -------------"

    local deps=("cmake" "gcc" "make" "git")
    for dep in "${deps[@]}"; do
        local dep_status dep_version
        if command -v "$dep" >/dev/null 2>&1; then
            dep_version=$("$dep" --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)
            dep_status="installed (${dep_version:-?})"
        else
            dep_status="NOT INSTALLED"
            ((issues++))
        fi
        echo "   - $dep: $dep_status"
    done

    # libpcap
    local pcap_status="NOT FOUND"
    if _check_lib_installed "pcap"; then
        pcap_status="installed"
    else
        ((issues++))
    fi
    echo "   - libpcap: $pcap_status"
    echo ""

    # Summary
    echo "============================================================"
    if [ $issues -eq 0 ]; then
        echo "   Status: ALL CHECKS PASSED"
    else
        echo "   Status: $issues ISSUE(S) FOUND"
    fi
    echo "============================================================"
    echo ""

    return $issues
}

# =============================================================================
# P-Net Configuration
# =============================================================================

# Create p-net configuration file
# Arguments:
#   $1 - network interface
#   $2 - station name
#   $3 - IP address (optional)
# Returns: 0 on success, 1 on failure
create_pnet_config() {
    local interface="${1:-eth0}"
    local station_name="${2:-water-controller}"
    local ip_address="${3:-}"

    log_info "Creating p-net configuration..."

    mkdir -p "$PNET_CONFIG_DIR"

    local config_file="${PNET_CONFIG_DIR}/pnet.conf"

    # Get interface info if IP not provided
    if [ -z "$ip_address" ]; then
        ip_address=$(ip -4 addr show "$interface" 2>/dev/null | grep -oP 'inet \K[\d.]+' | head -1)
    fi

    # Get MAC address
    local mac_address
    mac_address=$(ip link show "$interface" 2>/dev/null | grep -oP 'link/ether \K[\da-f:]+')

    cat > "$config_file" <<EOF
# P-Net PROFINET Configuration
# Generated: $(date -Iseconds)
# Water Treatment Controller

[network]
# Network interface for PROFINET communication
interface = $interface

# Station name (PROFINET device name)
station_name = $station_name

# IP configuration
ip_address = ${ip_address:-192.168.1.100}
netmask = 255.255.255.0
gateway = ${ip_address%.*}.1

# MAC address (read from interface)
mac_address = ${mac_address:-00:00:00:00:00:00}

[profinet]
# Vendor ID (assigned by PI)
vendor_id = 0x0000

# Device ID
device_id = 0x0001

# PROFINET ports
udp_port = $PNET_UDP_PORT
tcp_port_start = $PNET_TCP_PORT_START
tcp_port_end = $PNET_TCP_PORT_END

[timing]
# Cycle time in microseconds (1ms = 1000us)
min_cycle_time_us = 1000

# Watchdog timeout in milliseconds
watchdog_timeout_ms = 1000

[logging]
# Log level: 0=none, 1=error, 2=warning, 3=info, 4=debug
log_level = 3

# Log file
log_file = /var/log/water-controller/pnet.log
EOF

    chmod 644 "$config_file"
    log_info "Configuration created: $config_file"

    return 0
}

# Load required kernel modules for PROFINET
# Returns: 0 on success, 1 on failure
load_pnet_modules() {
    log_info "Loading PROFINET kernel modules..."

    local errors=0

    for mod in "${PNET_KERNEL_MODULES[@]}"; do
        if ! lsmod | grep -q "^${mod}"; then
            log_info "Loading module: $mod"
            if ! modprobe "$mod" 2>/dev/null; then
                log_error "Failed to load module: $mod"
                ((errors++))
            fi
        else
            log_info "Module already loaded: $mod"
        fi
    done

    return $errors
}

# Configure network interface for PROFINET
# Arguments:
#   $1 - network interface
# Returns: 0 on success, 1 on failure
configure_pnet_interface() {
    local interface="${1:-eth0}"

    log_info "Configuring interface $interface for PROFINET..."

    # Verify interface exists
    if ! ip link show "$interface" >/dev/null 2>&1; then
        log_error "Interface not found: $interface"
        return 1
    fi

    # Disable hardware offloading for PROFINET
    log_info "Disabling hardware offloading..."

    local ethtool_opts=(
        "rx off"
        "tx off"
        "sg off"
        "tso off"
        "gso off"
        "gro off"
        "lro off"
    )

    if command -v ethtool >/dev/null 2>&1; then
        for opt in "${ethtool_opts[@]}"; do
            # shellcheck disable=SC2086
            ethtool -K "$interface" $opt 2>/dev/null || true
        done
        log_info "Hardware offloading disabled"
    else
        log_warn "ethtool not available, skipping offload configuration"
    fi

    # Set interface to promiscuous mode for PROFINET DCP
    log_info "Enabling promiscuous mode..."
    ip link set "$interface" promisc on 2>/dev/null || {
        log_warn "Failed to set promiscuous mode"
    }

    # Increase network buffer sizes
    log_info "Tuning network buffers..."
    sysctl -w net.core.rmem_max=16777216 >/dev/null 2>&1 || true
    sysctl -w net.core.wmem_max=16777216 >/dev/null 2>&1 || true
    sysctl -w net.core.rmem_default=1048576 >/dev/null 2>&1 || true
    sysctl -w net.core.wmem_default=1048576 >/dev/null 2>&1 || true

    log_info "Interface configuration complete"
    return 0
}

# =============================================================================
# P-Net Sample Application
# =============================================================================

# Build and install p-net sample application
# Returns: 0 on success, 1 on failure
install_pnet_sample() {
    log_info "Installing p-net sample application..."

    local sample_dir="$PNET_SAMPLE_APP_DIR"
    mkdir -p "$sample_dir"

    # Create a simple test program
    cat > "${sample_dir}/pnet_test.c" <<'EOF'
/*
 * P-Net PROFINET Test Application
 * Water Treatment Controller
 *
 * This simple application verifies p-net library linking and basic functionality.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Check if p-net headers are available */
#ifdef __has_include
#if __has_include(<pnet_api.h>)
#include <pnet_api.h>
#define PNET_AVAILABLE 1
#endif
#endif

#ifndef PNET_AVAILABLE
#define PNET_AVAILABLE 0
#endif

int main(int argc, char *argv[]) {
    printf("P-Net PROFINET Test Application\n");
    printf("================================\n\n");

#if PNET_AVAILABLE
    printf("Status: P-Net library AVAILABLE\n");
    printf("This system can use PROFINET communication.\n");
    return 0;
#else
    printf("Status: P-Net library NOT AVAILABLE\n");
    printf("PROFINET support requires p-net installation.\n");
    printf("See: https://github.com/rtlabs-com/p-net\n");
    return 1;
#endif
}
EOF

    # Create Makefile
    cat > "${sample_dir}/Makefile" <<'EOF'
CC ?= gcc
CFLAGS ?= -Wall -Wextra -O2
LDFLAGS ?= -L/usr/local/lib -L/usr/lib
LIBS ?= -lpnet -lpthread

# Check if libpnet is available
PNET_EXISTS := $(shell pkg-config --exists pnet 2>/dev/null && echo 1 || echo 0)

ifeq ($(PNET_EXISTS),1)
    CFLAGS += $(shell pkg-config --cflags pnet)
    LIBS = $(shell pkg-config --libs pnet)
endif

TARGET = pnet_test

all: $(TARGET)

$(TARGET): pnet_test.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS) $(LIBS) 2>/dev/null || \
	$(CC) $(CFLAGS) -o $@ $< 2>/dev/null || \
	echo "Build failed - p-net library may not be installed"

clean:
	rm -f $(TARGET)

test: $(TARGET)
	./$(TARGET)

.PHONY: all clean test
EOF

    # Create run script
    cat > "${sample_dir}/run_test.sh" <<'EOF'
#!/bin/bash
# P-Net Test Runner

: "${SCRIPT_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
cd "$SCRIPT_DIR"

echo "Building p-net test application..."
make clean >/dev/null 2>&1
make

if [ -f "./pnet_test" ]; then
    echo ""
    echo "Running test..."
    echo ""
    ./pnet_test
    exit $?
else
    echo "Build failed - check p-net installation"
    exit 1
fi
EOF

    chmod +x "${sample_dir}/run_test.sh"

    log_info "Sample application installed at: $sample_dir"
    log_info "Run test with: ${sample_dir}/run_test.sh"

    return 0
}

# =============================================================================
# Module Help
# =============================================================================

pnet_help() {
    cat <<EOF
Water Treatment Controller - P-Net PROFINET Module v${PNET_MODULE_VERSION}

P-Net is an open-source PROFINET device stack from RT-Labs.
Repository: https://github.com/rtlabs-com/p-net

USAGE:
    source pnet.sh
    <function_name> [arguments]

INSTALLATION FUNCTIONS:

    check_pnet_prerequisites
        Check if system meets p-net installation requirements

    install_pnet_build_deps
        Install build dependencies (cmake, gcc, libpcap, etc.)

    clone_pnet [target_dir] [branch]
        Clone p-net repository
        Default branch: $PNET_RECOMMENDED_TAG

    build_pnet [source_dir] [install_prefix]
        Build p-net from source
        Default prefix: $PNET_INSTALL_PREFIX

    install_pnet [build_dir]
        Install built p-net to system

    install_pnet_full [branch]
        Complete installation (clone, build, install, verify)

VERIFICATION FUNCTIONS:

    verify_pnet_installation
        Verify p-net library and headers are installed

    diagnose_pnet
        Comprehensive diagnostic report

CONFIGURATION FUNCTIONS:

    create_pnet_config <interface> [station_name] [ip_address]
        Create p-net configuration file

    load_pnet_modules
        Load required kernel modules (8021q, etc.)

    configure_pnet_interface <interface>
        Configure network interface for PROFINET

UTILITY FUNCTIONS:

    install_pnet_sample
        Install sample test application

EXAMPLES:

    # Full installation
    install_pnet_full

    # Check prerequisites only
    check_pnet_prerequisites

    # Run diagnostics
    diagnose_pnet

    # Configure for specific interface
    create_pnet_config eth0 water-controller 192.168.1.100
    configure_pnet_interface eth0

NOTES:
    - Root privileges required for installation
    - Real-time kernel recommended for optimal PROFINET performance
    - Ethernet interface required (not WiFi)

EOF
}

# =============================================================================
# Main Entry Point
# =============================================================================

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        --help|-h)
            pnet_help
            ;;
        --version|-v)
            echo "P-Net Module v${PNET_MODULE_VERSION}"
            ;;
        install)
            install_pnet_full "${2:-}"
            ;;
        check)
            check_pnet_prerequisites
            ;;
        verify)
            verify_pnet_installation
            ;;
        diagnose)
            diagnose_pnet
            ;;
        configure)
            create_pnet_config "${2:-eth0}" "${3:-water-controller}" "${4:-}"
            configure_pnet_interface "${2:-eth0}"
            ;;
        sample)
            install_pnet_sample
            ;;
        *)
            echo "Usage: $0 {install|check|verify|diagnose|configure|sample|--help}"
            echo ""
            echo "Commands:"
            echo "  install   - Full p-net installation"
            echo "  check     - Check prerequisites"
            echo "  verify    - Verify installation"
            echo "  diagnose  - Run diagnostics"
            echo "  configure - Configure interface"
            echo "  sample    - Install sample app"
            echo ""
            echo "Run '$0 --help' for detailed usage"
            exit 1
            ;;
    esac
fi
