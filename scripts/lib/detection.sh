#!/bin/bash
#
# Water Treatment Controller - Detection and Prerequisites System
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module provides comprehensive system detection, hardware classification,
# and prerequisite verification for Water-Controller SCADA installation.
#
# Target: ARM/x86 SBCs running Debian-based Linux
# Constraints: SD card write endurance, real-time requirements, 1GB RAM
#

# Prevent multiple sourcing
if [ -n "${_WTC_DETECTION_LOADED:-}" ]; then
    return 0
fi
_WTC_DETECTION_LOADED=1

# =============================================================================
# Constants and Defaults
# =============================================================================

readonly DETECTION_VERSION="1.0.0"
readonly INSTALL_LOG_FILE="${INSTALL_LOG_FILE:-/var/log/water-controller-install.log}"
readonly MIN_DISK_SPACE_MB=2048
readonly MIN_RAM_MB=512
readonly WARN_RAM_MB=1024
readonly DEFAULT_PORT=8000

# Minimum version requirements
readonly MIN_PYTHON_MAJOR=3
readonly MIN_PYTHON_MINOR=9
readonly MIN_NODE_MAJOR=18
readonly MIN_SYSTEMD_VERSION=232

# Supported distributions
readonly SUPPORTED_DISTROS="debian ubuntu raspbian armbian"

# =============================================================================
# Enhanced Logging Functions
# =============================================================================

# Initialize logging - create log file with proper permissions
init_logging() {
    local log_dir
    log_dir="$(dirname "$INSTALL_LOG_FILE")"

    # Create log directory if it doesn't exist
    if [ ! -d "$log_dir" ]; then
        mkdir -p "$log_dir" 2>/dev/null || {
            echo "[ERROR] Cannot create log directory: $log_dir" >&2
            return 1
        }
    fi

    # Create or touch log file
    if [ ! -f "$INSTALL_LOG_FILE" ]; then
        touch "$INSTALL_LOG_FILE" 2>/dev/null || {
            echo "[ERROR] Cannot create log file: $INSTALL_LOG_FILE" >&2
            return 1
        }
        chmod 644 "$INSTALL_LOG_FILE"
    fi

    # Verify write access
    if [ ! -w "$INSTALL_LOG_FILE" ]; then
        echo "[ERROR] Cannot write to log file: $INSTALL_LOG_FILE" >&2
        return 1
    fi

    _log_write "INFO" "=== Water-Controller Installation Log Started ==="
    _log_write "INFO" "Detection module version: $DETECTION_VERSION"
    return 0
}

# Internal function to write to log file
_log_write() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"

    # Write to log file if it exists and is writable
    if [ -w "$INSTALL_LOG_FILE" ]; then
        echo "[$timestamp] [$level] $message" >> "$INSTALL_LOG_FILE"
    fi
}

# Log info message - logs to file and optionally to stderr
log_info() {
    local message="$1"
    local silent="${2:-false}"

    _log_write "INFO" "$message"

    if [ "$silent" != "true" ]; then
        echo -e "\033[0;32m[INFO]\033[0m $message" >&2
    fi
}

# Log warning message - logs to file and stderr
log_warn() {
    local message="$1"
    local silent="${2:-false}"

    _log_write "WARN" "$message"

    if [ "$silent" != "true" ]; then
        echo -e "\033[1;33m[WARN]\033[0m $message" >&2
    fi
}

# Log error message - logs to file and stderr
log_error() {
    local message="$1"
    local silent="${2:-false}"

    _log_write "ERROR" "$message"

    if [ "$silent" != "true" ]; then
        echo -e "\033[0;31m[ERROR]\033[0m $message" >&2
    fi
}

# Log debug message - only logs to file unless DEBUG is set
log_debug() {
    local message="$1"

    _log_write "DEBUG" "$message"

    if [ "${DEBUG:-0}" = "1" ]; then
        echo -e "\033[0;36m[DEBUG]\033[0m $message" >&2
    fi
}

# =============================================================================
# System Detection
# =============================================================================

# Detect comprehensive system information
# Returns: prints key=value pairs for system information
detect_system() {
    log_info "Detecting system configuration..." true

    local os_id=""
    local os_version=""
    local os_codename=""
    local arch=""
    local cpu_cores=""
    local cpu_model=""
    local total_ram_mb=""
    local storage_type=""
    local storage_device=""
    local storage_total_mb=""
    local storage_avail_mb=""
    local network_interfaces=""

    # Detect OS distribution and version from /etc/os-release
    if [ -f /etc/os-release ]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        os_id="${ID:-unknown}"
        os_version="${VERSION_ID:-unknown}"
        os_codename="${VERSION_CODENAME:-unknown}"
        log_debug "Detected OS from /etc/os-release: $os_id $os_version"
    elif [ -f /etc/lsb-release ]; then
        # shellcheck source=/dev/null
        . /etc/lsb-release
        os_id="${DISTRIB_ID:-unknown}"
        os_version="${DISTRIB_RELEASE:-unknown}"
        os_codename="${DISTRIB_CODENAME:-unknown}"
        os_id="$(echo "$os_id" | tr '[:upper:]' '[:lower:]')"
        log_debug "Detected OS from /etc/lsb-release: $os_id $os_version"
    else
        os_id="unknown"
        os_version="unknown"
        os_codename="unknown"
        log_warn "Could not detect OS distribution" true
    fi

    # Detect architecture
    arch="$(dpkg --print-architecture 2>/dev/null || uname -m)"
    case "$arch" in
        x86_64|amd64) arch="amd64" ;;
        aarch64|arm64) arch="arm64" ;;
        armv7l|armhf) arch="armhf" ;;
        armv6l) arch="armel" ;;
        *) log_debug "Uncommon architecture detected: $arch" ;;
    esac
    log_debug "Detected architecture: $arch"

    # Detect CPU information
    cpu_cores="$(nproc 2>/dev/null || grep -c '^processor' /proc/cpuinfo 2>/dev/null || echo "1")"
    cpu_model="$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | sed 's/^[ \t]*//' || echo "unknown")"
    if [ "$cpu_model" = "unknown" ] || [ -z "$cpu_model" ]; then
        # ARM processors often don't have 'model name', try Hardware field
        cpu_model="$(grep -m1 'Hardware' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | sed 's/^[ \t]*//' || echo "unknown")"
    fi
    log_debug "Detected CPU: $cpu_model ($cpu_cores cores)"

    # Detect total RAM in MB
    total_ram_mb="$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo "0")"
    log_debug "Detected RAM: ${total_ram_mb}MB"

    # Detect storage type and root device
    _detect_storage_info
    storage_type="$_STORAGE_TYPE"
    storage_device="$_STORAGE_DEVICE"
    storage_total_mb="$_STORAGE_TOTAL_MB"
    storage_avail_mb="$_STORAGE_AVAIL_MB"
    log_debug "Detected storage: $storage_device ($storage_type) - ${storage_avail_mb}MB available"

    # Detect network interfaces (excluding lo)
    network_interfaces="$(ip -o link show 2>/dev/null | awk -F': ' '{print $2}' | grep -v '^lo$' | tr '\n' ',' | sed 's/,$//')"
    if [ -z "$network_interfaces" ]; then
        network_interfaces="$(ls /sys/class/net 2>/dev/null | grep -v '^lo$' | tr '\n' ',' | sed 's/,$//')"
    fi
    log_debug "Detected network interfaces: $network_interfaces"

    # Output as key=value pairs
    echo "OS_ID=$os_id"
    echo "OS_VERSION=$os_version"
    echo "OS_CODENAME=$os_codename"
    echo "ARCH=$arch"
    echo "CPU_CORES=$cpu_cores"
    echo "CPU_MODEL=$cpu_model"
    echo "TOTAL_RAM_MB=$total_ram_mb"
    echo "STORAGE_TYPE=$storage_type"
    echo "STORAGE_DEVICE=$storage_device"
    echo "STORAGE_TOTAL_MB=$storage_total_mb"
    echo "STORAGE_AVAIL_MB=$storage_avail_mb"
    echo "NETWORK_INTERFACES=$network_interfaces"

    _log_write "INFO" "System detection complete: $os_id $os_version ($arch), ${total_ram_mb}MB RAM, ${storage_avail_mb}MB available on $storage_type"

    return 0
}

# Internal function to detect storage information
# Sets: _STORAGE_TYPE, _STORAGE_DEVICE, _STORAGE_TOTAL_MB, _STORAGE_AVAIL_MB
_detect_storage_info() {
    _STORAGE_TYPE="unknown"
    _STORAGE_DEVICE="unknown"
    _STORAGE_TOTAL_MB="0"
    _STORAGE_AVAIL_MB="0"

    local root_device
    local block_device
    local rotation

    # Find the device for root filesystem
    root_device="$(df / 2>/dev/null | awk 'NR==2 {print $1}')"
    if [ -z "$root_device" ]; then
        log_warn "Could not determine root device" true
        return 1
    fi

    # Get the base block device name (strip partition number)
    if [[ "$root_device" == /dev/mmcblk* ]] || [[ "$root_device" == /dev/nvme* ]]; then
        # mmcblk0p1 -> mmcblk0, nvme0n1p1 -> nvme0n1
        block_device="$(echo "$root_device" | sed 's/p[0-9]*$//')"
    else
        # sda1 -> sda
        block_device="$(echo "$root_device" | sed 's/[0-9]*$//')"
    fi
    block_device="$(basename "$block_device")"
    _STORAGE_DEVICE="$block_device"

    # Determine storage type from /sys/block
    if [ -f "/sys/block/$block_device/queue/rotational" ]; then
        rotation="$(cat "/sys/block/$block_device/queue/rotational" 2>/dev/null)"
        if [ "$rotation" = "0" ]; then
            # Non-rotational - could be SSD, eMMC, or SD
            if [[ "$block_device" == mmcblk* ]]; then
                # Check if it's eMMC or SD card
                if [ -f "/sys/block/$block_device/device/type" ]; then
                    local device_type
                    device_type="$(cat "/sys/block/$block_device/device/type" 2>/dev/null)"
                    case "$device_type" in
                        SD) _STORAGE_TYPE="sdcard" ;;
                        MMC) _STORAGE_TYPE="emmc" ;;
                        *) _STORAGE_TYPE="mmc" ;;
                    esac
                elif [ -d "/sys/block/$block_device/device/mmcblk" ] || \
                     grep -q "mmc" "/sys/block/$block_device/device/uevent" 2>/dev/null; then
                    # Additional check: SD cards typically have removable flag
                    if [ -f "/sys/block/$block_device/removable" ]; then
                        if [ "$(cat "/sys/block/$block_device/removable" 2>/dev/null)" = "1" ]; then
                            _STORAGE_TYPE="sdcard"
                        else
                            _STORAGE_TYPE="emmc"
                        fi
                    else
                        _STORAGE_TYPE="mmc"
                    fi
                else
                    _STORAGE_TYPE="mmc"
                fi
            elif [[ "$block_device" == nvme* ]]; then
                _STORAGE_TYPE="nvme"
            elif [[ "$block_device" == sd* ]]; then
                # Could be SSD or USB
                if [ -f "/sys/block/$block_device/removable" ] && \
                   [ "$(cat "/sys/block/$block_device/removable" 2>/dev/null)" = "1" ]; then
                    _STORAGE_TYPE="usb"
                else
                    _STORAGE_TYPE="ssd"
                fi
            else
                _STORAGE_TYPE="ssd"
            fi
        else
            _STORAGE_TYPE="hdd"
        fi
    else
        # Fallback based on device name
        case "$block_device" in
            mmcblk*) _STORAGE_TYPE="mmc" ;;
            nvme*) _STORAGE_TYPE="nvme" ;;
            sd*) _STORAGE_TYPE="disk" ;;
            *) _STORAGE_TYPE="unknown" ;;
        esac
    fi

    # Get storage capacity from df
    local df_output
    df_output="$(df -m / 2>/dev/null | awk 'NR==2 {print $2, $4}')"
    _STORAGE_TOTAL_MB="$(echo "$df_output" | awk '{print $1}')"
    _STORAGE_AVAIL_MB="$(echo "$df_output" | awk '{print $2}')"

    return 0
}

# =============================================================================
# Hardware Classification
# =============================================================================

# Classify the hardware platform for optimization decisions
# Returns: platform identifier string
classify_hardware() {
    log_info "Classifying hardware platform..." true

    local platform="generic"
    local model=""
    local revision=""

    # Check for Raspberry Pi
    if [ -f /proc/device-tree/model ]; then
        model="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)"
        if [[ "$model" == *"Raspberry Pi"* ]]; then
            platform="raspberry_pi"
            # Extract Pi model
            if [[ "$model" == *"Pi 5"* ]]; then
                platform="raspberry_pi_5"
            elif [[ "$model" == *"Pi 4"* ]]; then
                platform="raspberry_pi_4"
            elif [[ "$model" == *"Pi 3"* ]]; then
                platform="raspberry_pi_3"
            elif [[ "$model" == *"Pi 2"* ]]; then
                platform="raspberry_pi_2"
            elif [[ "$model" == *"Pi Zero 2"* ]]; then
                platform="raspberry_pi_zero2"
            elif [[ "$model" == *"Pi Zero"* ]]; then
                platform="raspberry_pi_zero"
            fi
            log_debug "Raspberry Pi detected: $model -> $platform"
            echo "PLATFORM=$platform"
            echo "PLATFORM_MODEL=$model"
            _log_write "INFO" "Hardware classified as: $platform ($model)"
            return 0
        fi
    fi

    # Check for Raspberry Pi via /proc/cpuinfo (older method)
    if grep -q "^Hardware.*BCM" /proc/cpuinfo 2>/dev/null; then
        revision="$(grep '^Revision' /proc/cpuinfo 2>/dev/null | awk '{print $3}')"
        platform="raspberry_pi"
        # Decode revision for model (simplified)
        case "${revision:(-4)}" in
            0007|0008|0009|000d|000e|000f) platform="raspberry_pi_1" ;;
            a01040|a01041|a21041|a22042) platform="raspberry_pi_2" ;;
            a02082|a22082|a32082|a52082|a22083) platform="raspberry_pi_3" ;;
            a03111|b03111|b03112|b03114|b03115|c03111|c03112|c03114|c03115|d03114|d03115) platform="raspberry_pi_4" ;;
            *) platform="raspberry_pi" ;;
        esac
        model="Raspberry Pi (revision: $revision)"
        log_debug "Raspberry Pi detected via cpuinfo: $revision -> $platform"
        echo "PLATFORM=$platform"
        echo "PLATFORM_MODEL=$model"
        _log_write "INFO" "Hardware classified as: $platform ($model)"
        return 0
    fi

    # Check for Orange Pi
    if [ -f /proc/device-tree/model ]; then
        model="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)"
        if [[ "$model" == *"Orange Pi"* ]]; then
            platform="orange_pi"
            if [[ "$model" == *"5"* ]]; then
                platform="orange_pi_5"
            elif [[ "$model" == *"4"* ]]; then
                platform="orange_pi_4"
            elif [[ "$model" == *"3"* ]]; then
                platform="orange_pi_3"
            elif [[ "$model" == *"Zero"* ]]; then
                platform="orange_pi_zero"
            fi
            log_debug "Orange Pi detected: $model -> $platform"
            echo "PLATFORM=$platform"
            echo "PLATFORM_MODEL=$model"
            _log_write "INFO" "Hardware classified as: $platform ($model)"
            return 0
        fi
    fi

    # Check for other common SBCs via device-tree
    if [ -f /proc/device-tree/model ]; then
        model="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)"

        if [[ "$model" == *"ODROID"* ]]; then
            platform="odroid"
        elif [[ "$model" == *"Banana Pi"* ]]; then
            platform="banana_pi"
        elif [[ "$model" == *"NanoPi"* ]]; then
            platform="nanopi"
        elif [[ "$model" == *"Rock"* ]] || [[ "$model" == *"ROCK"* ]]; then
            platform="rock"
        elif [[ "$model" == *"BeagleBone"* ]] || [[ "$model" == *"BeagleBoard"* ]]; then
            platform="beaglebone"
        elif [[ "$model" == *"Pine"* ]]; then
            platform="pine64"
        fi

        if [ "$platform" != "generic" ]; then
            log_debug "SBC detected via device-tree: $model -> $platform"
            echo "PLATFORM=$platform"
            echo "PLATFORM_MODEL=$model"
            _log_write "INFO" "Hardware classified as: $platform ($model)"
            return 0
        fi
    fi

    # Fallback: Detect based on architecture
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64|amd64)
            # Check if running in VM
            if grep -qE "(hypervisor|VMware|VirtualBox|KVM|Xen|QEMU)" /proc/cpuinfo 2>/dev/null || \
               [ -f /sys/class/dmi/id/product_name ] && grep -qiE "(virtual|vmware|virtualbox|kvm|xen|qemu)" /sys/class/dmi/id/product_name 2>/dev/null; then
                platform="x86_64_vm"
                model="x86_64 Virtual Machine"
            else
                platform="x86_64"
                model="x86_64 System"
            fi
            ;;
        aarch64|arm64)
            platform="arm64_generic"
            model="Generic ARM64 System"
            ;;
        armv7l)
            platform="arm32_generic"
            model="Generic ARM32 System"
            ;;
        armv6l)
            platform="arm32_v6"
            model="ARMv6 System"
            ;;
        *)
            platform="unknown_arch"
            model="Unknown Architecture: $arch"
            ;;
    esac

    log_debug "Generic platform classification: $arch -> $platform"
    echo "PLATFORM=$platform"
    echo "PLATFORM_MODEL=$model"
    _log_write "INFO" "Hardware classified as: $platform ($model)"

    return 0
}

# =============================================================================
# Prerequisite Checks
# =============================================================================

# Check all prerequisites for installation
# Returns: 0 if all pass, 2 with error message if fail
check_prerequisites() {
    log_info "Checking installation prerequisites..."

    local errors=()
    local warnings=()

    # 1. Root/sudo verification
    log_debug "Checking root privileges..."
    if [ "$EUID" -ne 0 ]; then
        errors+=("Root privileges required. Please run with sudo or as root.")
    else
        log_debug "Running as root: OK"
    fi

    # 2. Supported OS check
    log_debug "Checking OS compatibility..."
    local os_id="unknown"
    if [ -f /etc/os-release ]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        os_id="${ID:-unknown}"
    fi
    os_id="$(echo "$os_id" | tr '[:upper:]' '[:lower:]')"

    local os_supported=false
    for distro in $SUPPORTED_DISTROS; do
        if [ "$os_id" = "$distro" ]; then
            os_supported=true
            break
        fi
    done

    if [ "$os_supported" = false ]; then
        errors+=("Unsupported OS: $os_id. Supported: $SUPPORTED_DISTROS")
    else
        log_debug "OS compatibility: $os_id - OK"
    fi

    # 3. Minimum disk space: 2GB free
    log_debug "Checking available disk space..."
    local avail_space_mb
    avail_space_mb="$(df -m / 2>/dev/null | awk 'NR==2 {print $4}')"
    if [ -z "$avail_space_mb" ] || [ "$avail_space_mb" -lt "$MIN_DISK_SPACE_MB" ]; then
        errors+=("Insufficient disk space: ${avail_space_mb:-0}MB available, ${MIN_DISK_SPACE_MB}MB required")
    else
        log_debug "Disk space: ${avail_space_mb}MB available - OK"
    fi

    # 4. Minimum RAM: 512MB (warn if <1GB)
    log_debug "Checking available RAM..."
    local total_ram_mb
    total_ram_mb="$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null)"
    if [ -z "$total_ram_mb" ] || [ "$total_ram_mb" -lt "$MIN_RAM_MB" ]; then
        errors+=("Insufficient RAM: ${total_ram_mb:-0}MB available, ${MIN_RAM_MB}MB minimum required")
    elif [ "$total_ram_mb" -lt "$WARN_RAM_MB" ]; then
        warnings+=("Low RAM: ${total_ram_mb}MB available. ${WARN_RAM_MB}MB+ recommended for optimal performance")
        log_debug "RAM: ${total_ram_mb}MB available - WARNING (low)"
    else
        log_debug "RAM: ${total_ram_mb}MB available - OK"
    fi

    # 5. Internet connectivity
    log_debug "Checking internet connectivity..."
    local internet_ok=false

    # Try ping first (faster)
    if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
        internet_ok=true
    # Fallback to curl
    elif command -v curl >/dev/null 2>&1 && curl -s --connect-timeout 5 https://www.google.com >/dev/null 2>&1; then
        internet_ok=true
    # Fallback to wget
    elif command -v wget >/dev/null 2>&1 && wget -q --timeout=5 --spider https://www.google.com 2>/dev/null; then
        internet_ok=true
    fi

    if [ "$internet_ok" = false ]; then
        errors+=("No internet connectivity detected. Installation requires network access.")
    else
        log_debug "Internet connectivity: OK"
    fi

    # 6. systemd availability and version
    log_debug "Checking systemd..."
    if ! command -v systemctl >/dev/null 2>&1; then
        errors+=("systemd not found. This installation requires systemd.")
    else
        local systemd_version
        systemd_version="$(systemctl --version 2>/dev/null | head -n1 | awk '{print $2}')"
        if [ -n "$systemd_version" ] && [ "$systemd_version" -lt "$MIN_SYSTEMD_VERSION" ] 2>/dev/null; then
            errors+=("systemd version $systemd_version is too old. Minimum required: $MIN_SYSTEMD_VERSION")
        else
            log_debug "systemd version: $systemd_version - OK"
        fi
    fi

    # 7. Write access to required directories
    log_debug "Checking write access to directories..."
    for dir in /opt /etc /var; do
        if [ ! -w "$dir" ]; then
            errors+=("No write access to $dir")
        else
            log_debug "Write access to $dir: OK"
        fi
    done

    # Report warnings
    for warning in "${warnings[@]}"; do
        log_warn "$warning"
    done

    # Report errors and exit if any
    if [ ${#errors[@]} -gt 0 ]; then
        log_error "Prerequisite checks failed with ${#errors[@]} error(s):"
        for error in "${errors[@]}"; do
            log_error "  - $error"
        done
        _log_write "ERROR" "Prerequisites check FAILED: ${errors[*]}"
        return 2
    fi

    log_info "All prerequisite checks passed"
    _log_write "INFO" "All prerequisite checks passed"
    return 0
}

# =============================================================================
# Dependency Detection
# =============================================================================

# Check for required dependencies and return list of missing ones
# Returns: prints list of missing dependencies (one per line)
check_dependencies() {
    log_info "Checking dependencies..." true

    local missing=()

    # Build tools
    log_debug "Checking build tools..."

    if ! command -v gcc >/dev/null 2>&1; then
        missing+=("gcc")
        log_debug "gcc: MISSING"
    else
        log_debug "gcc: $(gcc --version | head -n1)"
    fi

    if ! command -v make >/dev/null 2>&1; then
        missing+=("make")
        log_debug "make: MISSING"
    else
        log_debug "make: $(make --version | head -n1)"
    fi

    if ! command -v pkg-config >/dev/null 2>&1; then
        missing+=("pkg-config")
        log_debug "pkg-config: MISSING"
    else
        log_debug "pkg-config: $(pkg-config --version)"
    fi

    if ! command -v git >/dev/null 2>&1; then
        missing+=("git")
        log_debug "git: MISSING"
    else
        log_debug "git: $(git --version)"
    fi

    if ! command -v curl >/dev/null 2>&1; then
        missing+=("curl")
        log_debug "curl: MISSING"
    else
        log_debug "curl: $(curl --version | head -n1)"
    fi

    if ! command -v cmake >/dev/null 2>&1; then
        missing+=("cmake")
        log_debug "cmake: MISSING"
    else
        log_debug "cmake: $(cmake --version | head -n1)"
    fi

    # Python 3.9+
    log_debug "Checking Python..."
    if ! command -v python3 >/dev/null 2>&1; then
        missing+=("python3")
        log_debug "python3: MISSING"
    else
        local python_version
        python_version="$(python3 --version 2>/dev/null | awk '{print $2}')"
        local python_major python_minor
        python_major="$(echo "$python_version" | cut -d. -f1)"
        python_minor="$(echo "$python_version" | cut -d. -f2)"

        if [ "$python_major" -lt "$MIN_PYTHON_MAJOR" ] || \
           { [ "$python_major" -eq "$MIN_PYTHON_MAJOR" ] && [ "$python_minor" -lt "$MIN_PYTHON_MINOR" ]; }; then
            missing+=("python3>=${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}")
            log_debug "python3: $python_version (REQUIRES ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+)"
        else
            log_debug "python3: $python_version"
        fi
    fi

    # Check for python3-venv
    if command -v python3 >/dev/null 2>&1; then
        if ! python3 -c "import venv" 2>/dev/null; then
            missing+=("python3-venv")
            log_debug "python3-venv: MISSING"
        else
            log_debug "python3-venv: OK"
        fi
    fi

    # Check for pip3
    log_debug "Checking pip3..."
    if ! command -v pip3 >/dev/null 2>&1; then
        missing+=("pip3")
        log_debug "pip3: MISSING"
    else
        log_debug "pip3: $(pip3 --version 2>/dev/null | awk '{print $2}')"
    fi

    # Node.js 18+
    log_debug "Checking Node.js..."
    if ! command -v node >/dev/null 2>&1; then
        missing+=("nodejs")
        log_debug "nodejs: MISSING"
    else
        local node_version
        node_version="$(node --version 2>/dev/null | sed 's/^v//')"
        local node_major
        node_major="$(echo "$node_version" | cut -d. -f1)"

        if [ "$node_major" -lt "$MIN_NODE_MAJOR" ] 2>/dev/null; then
            missing+=("nodejs>=${MIN_NODE_MAJOR}")
            log_debug "nodejs: $node_version (REQUIRES ${MIN_NODE_MAJOR}+)"
        else
            log_debug "nodejs: $node_version"
        fi
    fi

    # npm
    log_debug "Checking npm..."
    if ! command -v npm >/dev/null 2>&1; then
        missing+=("npm")
        log_debug "npm: MISSING"
    else
        log_debug "npm: $(npm --version 2>/dev/null)"
    fi

    # SQLite3
    log_debug "Checking SQLite3..."
    if ! command -v sqlite3 >/dev/null 2>&1; then
        missing+=("sqlite3")
        log_debug "sqlite3: MISSING"
    else
        log_debug "sqlite3: $(sqlite3 --version 2>/dev/null | awk '{print $1}')"
    fi

    # Output missing dependencies
    if [ ${#missing[@]} -gt 0 ]; then
        log_debug "Missing dependencies: ${missing[*]}"
        _log_write "INFO" "Missing dependencies detected: ${missing[*]}"
        printf '%s\n' "${missing[@]}"
    else
        log_debug "All dependencies satisfied"
        _log_write "INFO" "All dependencies satisfied"
    fi

    return 0
}

# =============================================================================
# Port Conflict Detection
# =============================================================================

# Check if a port is available
# Input: port number (default 8000)
# Returns: 0 if available, 1 if in use (prints process name)
check_port_available() {
    local port="${1:-$DEFAULT_PORT}"
    local process_info=""

    log_debug "Checking if port $port is available..."

    # Validate port number
    if ! [[ "$port" =~ ^[0-9]+$ ]] || [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
        log_error "Invalid port number: $port"
        return 2
    fi

    # Try ss first (most modern and reliable)
    if command -v ss >/dev/null 2>&1; then
        process_info="$(ss -tlnp 2>/dev/null | grep ":$port " | head -n1)"
        if [ -n "$process_info" ]; then
            local process_name
            process_name="$(echo "$process_info" | grep -oP 'users:\(\("\K[^"]+' 2>/dev/null || echo "unknown")"
            log_debug "Port $port in use by: $process_name (detected via ss)"
            echo "PORT_IN_USE=$port"
            echo "PROCESS=$process_name"
            _log_write "WARN" "Port $port is in use by: $process_name"
            return 1
        fi
    # Fallback to netstat
    elif command -v netstat >/dev/null 2>&1; then
        process_info="$(netstat -tlnp 2>/dev/null | grep ":$port " | head -n1)"
        if [ -n "$process_info" ]; then
            local process_name
            process_name="$(echo "$process_info" | awk '{print $NF}' | cut -d/ -f2)"
            log_debug "Port $port in use by: $process_name (detected via netstat)"
            echo "PORT_IN_USE=$port"
            echo "PROCESS=$process_name"
            _log_write "WARN" "Port $port is in use by: $process_name"
            return 1
        fi
    # Fallback to lsof
    elif command -v lsof >/dev/null 2>&1; then
        process_info="$(lsof -i ":$port" -P -n 2>/dev/null | grep LISTEN | head -n1)"
        if [ -n "$process_info" ]; then
            local process_name
            process_name="$(echo "$process_info" | awk '{print $1}')"
            log_debug "Port $port in use by: $process_name (detected via lsof)"
            echo "PORT_IN_USE=$port"
            echo "PROCESS=$process_name"
            _log_write "WARN" "Port $port is in use by: $process_name"
            return 1
        fi
    else
        log_warn "Cannot check port availability: ss, netstat, and lsof not found" true
        _log_write "WARN" "Cannot check port $port: no suitable tool found"
        return 2
    fi

    log_debug "Port $port is available"
    echo "PORT_AVAILABLE=$port"
    _log_write "INFO" "Port $port is available"
    return 0
}

# =============================================================================
# Existing Installation Detection
# =============================================================================

# Detect existing Water-Controller installation
# Returns: not_installed | version_string | corrupted
detect_existing_installation() {
    log_info "Detecting existing installation..." true

    local install_status="not_installed"
    local installed_version=""
    local service_status=""
    local service_name="water-controller.service"

    # Check for Python virtual environment with uvicorn/gunicorn
    local venv_path="/opt/water-controller/venv"
    local uvicorn_path="$venv_path/bin/uvicorn"
    local gunicorn_path="$venv_path/bin/gunicorn"
    local app_path="/opt/water-controller/web/api"

    local server_found=""
    if [ -x "$uvicorn_path" ]; then
        server_found="uvicorn"
        log_debug "Uvicorn found at: $uvicorn_path"
    elif [ -x "$gunicorn_path" ]; then
        server_found="gunicorn"
        log_debug "Gunicorn found at: $gunicorn_path"
    fi

    if [ -n "$server_found" ]; then
        # Try to get version from Python app
        if [ -f "$app_path/main.py" ]; then
            # Try to extract __version__ from Python code
            installed_version="$(grep -E "^__version__\s*=" "$app_path/main.py" 2>/dev/null | sed "s/.*['\"]\\([^'\"]*\\)['\"].*/\\1/" || echo "")"

            # Try version.py if main.py doesn't have version
            if [ -z "$installed_version" ] && [ -f "$app_path/version.py" ]; then
                installed_version="$(grep -E "^__version__\s*=" "$app_path/version.py" 2>/dev/null | sed "s/.*['\"]\\([^'\"]*\\)['\"].*/\\1/" || echo "")"
            fi

            # Try __init__.py
            if [ -z "$installed_version" ] && [ -f "$app_path/__init__.py" ]; then
                installed_version="$(grep -E "^__version__\s*=" "$app_path/__init__.py" 2>/dev/null | sed "s/.*['\"]\\([^'\"]*\\)['\"].*/\\1/" || echo "")"
            fi

            if [ -n "$installed_version" ]; then
                install_status="installed"
                log_debug "Installed version: $installed_version (from Python code)"
            else
                # App files exist but no version found
                install_status="installed"
                installed_version="unknown"
                log_debug "App found but version unknown"
            fi
        else
            # Server binary exists but no app files - corrupted
            install_status="corrupted"
            log_debug "Server ($server_found) exists but app files missing - corrupted"
        fi
    else
        log_debug "No uvicorn or gunicorn found in venv"
    fi

    # Check for systemd service
    if systemctl list-unit-files "$service_name" >/dev/null 2>&1; then
        if systemctl is-enabled "$service_name" >/dev/null 2>&1; then
            service_status="enabled"
        else
            service_status="disabled"
        fi

        if systemctl is-active "$service_name" >/dev/null 2>&1; then
            service_status="${service_status}:running"
        else
            service_status="${service_status}:stopped"
        fi

        log_debug "Service status: $service_status"

        # If service exists but no server binary, installation is corrupted
        if [ "$install_status" = "not_installed" ]; then
            install_status="corrupted"
            log_debug "Service exists but server missing - corrupted installation"
        fi
    else
        log_debug "No systemd service found: $service_name"
        service_status="not_found"
    fi

    # Check for installation directory structure
    local install_dir_status="not_found"
    if [ -d "/opt/water-controller" ]; then
        install_dir_status="exists"
        # Check for Python-based installation structure
        if [ -d "/opt/water-controller/web" ] && [ -d "/opt/water-controller/venv" ]; then
            install_dir_status="complete"
        elif [ -d "/opt/water-controller/web/api" ] || [ -d "/opt/water-controller/venv" ]; then
            install_dir_status="partial"
            if [ "$install_status" = "not_installed" ]; then
                install_status="corrupted"
                log_debug "Partial installation directory - corrupted"
            fi
        else
            install_dir_status="partial"
        fi
    fi

    # Check for config directory
    local config_status="not_found"
    if [ -d "/etc/water-controller" ]; then
        config_status="exists"
        if [ -f "/etc/water-controller/controller.conf" ]; then
            config_status="configured"
        fi
    fi

    # Output results
    echo "INSTALL_STATUS=$install_status"
    if [ -n "$installed_version" ]; then
        echo "INSTALLED_VERSION=$installed_version"
    fi
    echo "SERVICE_STATUS=$service_status"
    echo "INSTALL_DIR_STATUS=$install_dir_status"
    echo "CONFIG_STATUS=$config_status"

    # Log summary
    case "$install_status" in
        "not_installed")
            _log_write "INFO" "No existing installation detected"
            log_info "No existing installation detected" true
            ;;
        "installed")
            _log_write "INFO" "Existing installation detected: version=$installed_version, service=$service_status"
            log_info "Existing installation detected: $installed_version" true
            ;;
        "corrupted")
            _log_write "WARN" "Corrupted installation detected: service=$service_status, dir=$install_dir_status"
            log_warn "Corrupted installation detected" true
            ;;
    esac

    return 0
}

# =============================================================================
# Combined Detection Function
# =============================================================================

# Run all detection functions and output comprehensive system info
run_full_detection() {
    log_info "Running full system detection..."

    echo "=== SYSTEM DETECTION ==="
    detect_system
    echo ""

    echo "=== HARDWARE CLASSIFICATION ==="
    classify_hardware
    echo ""

    echo "=== EXISTING INSTALLATION ==="
    detect_existing_installation
    echo ""

    echo "=== DEPENDENCIES ==="
    echo "MISSING_DEPENDENCIES=$(check_dependencies | tr '\n' ',' | sed 's/,$//')"
    echo ""

    echo "=== PORT CHECKS ==="
    check_port_available 8000
    check_port_available 8080
    check_port_available 3000
    check_port_available 502
    echo ""

    log_info "Full detection complete"
    return 0
}

# =============================================================================
# Main Entry Point (when run directly)
# =============================================================================

# Only run main if this script is executed directly, not sourced
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    # Initialize logging
    init_logging || {
        echo "[WARN] Logging initialization failed, continuing without file logging" >&2
    }

    # Parse arguments
    case "${1:-}" in
        --detect-system)
            detect_system
            ;;
        --classify-hardware)
            classify_hardware
            ;;
        --check-prerequisites)
            check_prerequisites
            exit $?
            ;;
        --check-dependencies)
            check_dependencies
            ;;
        --check-port)
            check_port_available "${2:-$DEFAULT_PORT}"
            exit $?
            ;;
        --detect-installation)
            detect_existing_installation
            ;;
        --full)
            run_full_detection
            ;;
        --help|-h)
            echo "Water-Controller Detection Module v$DETECTION_VERSION"
            echo ""
            echo "Usage: $0 [OPTION]"
            echo ""
            echo "Options:"
            echo "  --detect-system       Detect system configuration"
            echo "  --classify-hardware   Classify hardware platform"
            echo "  --check-prerequisites Check installation prerequisites"
            echo "  --check-dependencies  List missing dependencies"
            echo "  --check-port [PORT]   Check if port is available (default: $DEFAULT_PORT)"
            echo "  --detect-installation Detect existing installation"
            echo "  --full                Run all detection functions"
            echo "  --help, -h            Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  INSTALL_LOG_FILE      Log file path (default: $INSTALL_LOG_FILE)"
            echo "  DEBUG                 Set to 1 for debug output"
            ;;
        *)
            echo "Usage: $0 [--detect-system|--classify-hardware|--check-prerequisites|--check-dependencies|--check-port PORT|--detect-installation|--full|--help]" >&2
            exit 1
            ;;
    esac
fi
