#!/bin/bash
#
# Water Treatment Controller - Documentation Generation and Rollback System
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module provides installation report generation, configuration
# documentation, backup manifest management, and rollback capabilities.
#
# Target: ARM/x86 SBCs running Debian-based Linux
# Constraints: SD card write endurance, atomic operations for safety
#

# Prevent multiple sourcing
if [ -n "$_WTC_DOCUMENTATION_LOADED" ]; then
    return 0
fi
_WTC_DOCUMENTATION_LOADED=1

# Source detection module for logging functions
: "${SCRIPT_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
if [ -f "$SCRIPT_DIR/detection.sh" ]; then
    # shellcheck source=detection.sh
    source "$SCRIPT_DIR/detection.sh"
fi

# =============================================================================
# Constants
# =============================================================================

readonly DOCUMENTATION_VERSION="1.0.0"

# Paths
readonly INSTALL_DIR="${INSTALL_DIR:-/opt/water-controller}"
: "${CONFIG_DIR:=/etc/water-controller}"
: "${DATA_DIR:=/var/lib/water-controller}"
: "${LOG_DIR:=/var/log/water-controller}"
readonly BACKUP_DIR="${BACKUP_DIR:-/var/backups/water-controller}"
readonly DOC_DIR="${DOC_DIR:-/usr/share/doc/water-controller}"

# Rollback settings
readonly ROLLBACK_DIR="${BACKUP_DIR}/rollback"
readonly MAX_ROLLBACK_POINTS=5
readonly MAX_BACKUP_AGE_DAYS=30

# Report file names
readonly INSTALL_REPORT="installation-report.txt"
readonly CONFIG_DOC="configuration.md"
readonly BACKUP_MANIFEST="backup-manifest.json"

# =============================================================================
# Helper Functions
# =============================================================================

# Get current timestamp in ISO 8601 format
_get_timestamp() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

# Get human-readable timestamp
_get_readable_timestamp() {
    date "+%Y-%m-%d %H:%M:%S %Z"
}

# Get file hash (SHA256)
_get_file_hash() {
    local file="$1"

    if [ ! -f "$file" ]; then
        echo "file_not_found"
        return 1
    fi

    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$file" 2>/dev/null | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$file" 2>/dev/null | awk '{print $1}'
    else
        # Fallback to md5
        if command -v md5sum >/dev/null 2>&1; then
            md5sum "$file" 2>/dev/null | awk '{print $1}'
        else
            echo "no_hash_tool"
            return 1
        fi
    fi
}

# Get directory size in human-readable format
_get_dir_size() {
    local dir="$1"

    if [ -d "$dir" ]; then
        du -sh "$dir" 2>/dev/null | awk '{print $1}'
    else
        echo "0"
    fi
}

# Get file count in directory
_get_file_count() {
    local dir="$1"

    if [ -d "$dir" ]; then
        find "$dir" -type f 2>/dev/null | wc -l
    else
        echo "0"
    fi
}

# Ensure directory exists
_ensure_dir() {
    local dir="$1"

    if [ ! -d "$dir" ]; then
        mkdir -p "$dir" 2>/dev/null || {
            log_error "Failed to create directory: $dir"
            return 1
        }
    fi
    return 0
}

# JSON escape string
_json_escape() {
    local str="$1"
    # Escape backslashes, quotes, and control characters
    printf '%s' "$str" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g; s/\r/\\r/g' | tr '\n' ' '
}

# =============================================================================
# Installation Report Generation
# =============================================================================

# Generate comprehensive installation report
# Returns: 0 on success, 1 on failure
generate_installation_report() {
    local output_file="${1:-${DOC_DIR}/${INSTALL_REPORT}}"
    local report_dir
    report_dir="$(dirname "$output_file")"

    log_info "Generating installation report: $output_file"

    # Ensure output directory exists
    if ! _ensure_dir "$report_dir"; then
        log_error "Cannot create report directory: $report_dir"
        return 1
    fi

    # Create temporary file for atomic write
    local temp_file
    temp_file="$(mktemp)" || {
        log_error "Failed to create temporary file"
        return 1
    }

    # Generate report
    {
        echo "==============================================================================="
        echo "                    WATER TREATMENT CONTROLLER - INSTALLATION REPORT"
        echo "==============================================================================="
        echo ""
        echo "Generated: $(_get_readable_timestamp)"
        echo "Report Version: ${DOCUMENTATION_VERSION}"
        echo ""

        # System Information
        echo "-------------------------------------------------------------------------------"
        echo "                              SYSTEM INFORMATION"
        echo "-------------------------------------------------------------------------------"
        echo ""
        echo "Hostname:        $(hostname 2>/dev/null || echo 'unknown')"
        echo "OS:              $(grep -E '^PRETTY_NAME=' /etc/os-release 2>/dev/null | cut -d'"' -f2 || uname -o)"
        echo "Kernel:          $(uname -r)"
        echo "Architecture:    $(uname -m)"
        echo "CPU:             $(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d':' -f2 | xargs || echo 'unknown')"
        echo "CPU Cores:       $(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null || echo 'unknown')"
        echo "Total RAM:       $(free -h 2>/dev/null | awk '/^Mem:/{print $2}' || echo 'unknown')"
        echo "Available RAM:   $(free -h 2>/dev/null | awk '/^Mem:/{print $7}' || echo 'unknown')"
        echo ""

        # Hardware Detection
        echo "Hardware Type:   $(_detect_hardware_type)"
        echo ""

        # Storage Information
        echo "-------------------------------------------------------------------------------"
        echo "                             STORAGE INFORMATION"
        echo "-------------------------------------------------------------------------------"
        echo ""
        echo "Root Filesystem:"
        df -h / 2>/dev/null | tail -1 | awk '{printf "  Device:      %s\n  Size:        %s\n  Used:        %s (%s)\n  Available:   %s\n  Mount:       %s\n", $1, $2, $3, $5, $4, $6}'
        echo ""

        if [ -d "$DATA_DIR" ]; then
            echo "Data Directory ($DATA_DIR):"
            df -h "$DATA_DIR" 2>/dev/null | tail -1 | awk '{printf "  Size:        %s\n  Used:        %s (%s)\n  Available:   %s\n", $2, $3, $5, $4}'
            echo "  File Count:  $(_get_file_count "$DATA_DIR")"
            echo "  Total Size:  $(_get_dir_size "$DATA_DIR")"
        fi
        echo ""

        # Installation Details
        echo "-------------------------------------------------------------------------------"
        echo "                            INSTALLATION DETAILS"
        echo "-------------------------------------------------------------------------------"
        echo ""
        echo "Installation Directory:  $INSTALL_DIR"
        echo "Configuration Directory: $CONFIG_DIR"
        echo "Data Directory:          $DATA_DIR"
        echo "Log Directory:           $LOG_DIR"
        echo "Backup Directory:        $BACKUP_DIR"
        echo ""

        # Check installed components
        echo "Installed Components:"

        # Python virtual environment
        if [ -d "${INSTALL_DIR}/venv" ]; then
            local python_version
            python_version=$("${INSTALL_DIR}/venv/bin/python" --version 2>&1 || echo "unknown")
            echo "  [x] Python Virtual Environment ($python_version)"
            echo "      Size: $(_get_dir_size "${INSTALL_DIR}/venv")"
        else
            echo "  [ ] Python Virtual Environment (not found)"
        fi

        # Backend application
        if [ -d "${INSTALL_DIR}/app" ]; then
            echo "  [x] Backend Application"
            echo "      Size: $(_get_dir_size "${INSTALL_DIR}/app")"
            echo "      Files: $(_get_file_count "${INSTALL_DIR}/app")"
        else
            echo "  [ ] Backend Application (not found)"
        fi

        # Frontend
        if [ -d "${INSTALL_DIR}/frontend" ]; then
            echo "  [x] Frontend (React)"
            echo "      Size: $(_get_dir_size "${INSTALL_DIR}/frontend")"
        else
            echo "  [ ] Frontend (not found)"
        fi

        # Configuration
        if [ -f "${CONFIG_DIR}/config.yaml" ]; then
            echo "  [x] Configuration File"
            echo "      Hash: $(_get_file_hash "${CONFIG_DIR}/config.yaml")"
        else
            echo "  [ ] Configuration File (not found)"
        fi

        # Database
        if [ -f "${DATA_DIR}/water_controller.db" ]; then
            local db_size
            db_size=$(ls -lh "${DATA_DIR}/water_controller.db" 2>/dev/null | awk '{print $5}')
            echo "  [x] SQLite Database"
            echo "      Size: $db_size"
            echo "      Hash: $(_get_file_hash "${DATA_DIR}/water_controller.db")"
        else
            echo "  [ ] SQLite Database (not found)"
        fi
        echo ""

        # Service Status
        echo "-------------------------------------------------------------------------------"
        echo "                              SERVICE STATUS"
        echo "-------------------------------------------------------------------------------"
        echo ""

        if command -v systemctl >/dev/null 2>&1; then
            if systemctl list-unit-files water-controller.service >/dev/null 2>&1; then
                echo "Service Unit:    water-controller.service"
                echo "Enabled:         $(systemctl is-enabled water-controller.service 2>/dev/null || echo 'unknown')"
                echo "Active:          $(systemctl is-active water-controller.service 2>/dev/null || echo 'unknown')"

                local service_status
                service_status=$(systemctl show water-controller.service --property=ActiveState,SubState,MainPID,MemoryCurrent 2>/dev/null)
                if [ -n "$service_status" ]; then
                    echo ""
                    echo "Detailed Status:"
                    echo "$service_status" | while IFS='=' read -r key value; do
                        printf "  %-15s %s\n" "$key:" "$value"
                    done
                fi
            else
                echo "Service Unit:    water-controller.service (not installed)"
            fi
        else
            echo "systemd not available"
        fi
        echo ""

        # Network Configuration
        echo "-------------------------------------------------------------------------------"
        echo "                           NETWORK CONFIGURATION"
        echo "-------------------------------------------------------------------------------"
        echo ""

        echo "Network Interfaces:"
        ip -brief addr 2>/dev/null | while read -r iface state addrs; do
            printf "  %-15s %-10s %s\n" "$iface" "$state" "$addrs"
        done
        echo ""

        echo "Listening Ports (water-controller related):"
        if command -v ss >/dev/null 2>&1; then
            ss -tlnp 2>/dev/null | grep -E ':(8000|8080|34962|34963|34964)\s' | while read -r line; do
                echo "  $line"
            done
        elif command -v netstat >/dev/null 2>&1; then
            netstat -tlnp 2>/dev/null | grep -E ':(8000|8080|34962|34963|34964)\s' | while read -r line; do
                echo "  $line"
            done
        fi
        echo ""

        # Python Dependencies
        echo "-------------------------------------------------------------------------------"
        echo "                           PYTHON DEPENDENCIES"
        echo "-------------------------------------------------------------------------------"
        echo ""

        if [ -f "${INSTALL_DIR}/venv/bin/pip" ]; then
            echo "Installed Packages:"
            "${INSTALL_DIR}/venv/bin/pip" list --format=columns 2>/dev/null | head -30
            local pkg_count
            pkg_count=$("${INSTALL_DIR}/venv/bin/pip" list 2>/dev/null | wc -l)
            if [ "$pkg_count" -gt 30 ]; then
                echo "  ... and $((pkg_count - 30)) more packages"
            fi
        else
            echo "Python virtual environment not found"
        fi
        echo ""

        # File Permissions
        echo "-------------------------------------------------------------------------------"
        echo "                             FILE PERMISSIONS"
        echo "-------------------------------------------------------------------------------"
        echo ""

        echo "Critical Directories:"
        for dir in "$INSTALL_DIR" "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR"; do
            if [ -d "$dir" ]; then
                local perms owner
                perms=$(stat -c '%a' "$dir" 2>/dev/null || stat -f '%Lp' "$dir" 2>/dev/null)
                owner=$(stat -c '%U:%G' "$dir" 2>/dev/null || stat -f '%Su:%Sg' "$dir" 2>/dev/null)
                printf "  %-35s %s  %s\n" "$dir" "$perms" "$owner"
            fi
        done
        echo ""

        echo "Critical Files:"
        for file in "${CONFIG_DIR}/config.yaml" "${DATA_DIR}/water_controller.db" "/etc/systemd/system/water-controller.service"; do
            if [ -f "$file" ]; then
                local perms owner
                perms=$(stat -c '%a' "$file" 2>/dev/null || stat -f '%Lp' "$file" 2>/dev/null)
                owner=$(stat -c '%U:%G' "$file" 2>/dev/null || stat -f '%Su:%Sg' "$file" 2>/dev/null)
                printf "  %-50s %s  %s\n" "$file" "$perms" "$owner"
            fi
        done
        echo ""

        # Recent Logs
        echo "-------------------------------------------------------------------------------"
        echo "                               RECENT LOGS"
        echo "-------------------------------------------------------------------------------"
        echo ""

        if [ -f "${LOG_DIR}/water-controller.log" ]; then
            echo "Last 20 log entries:"
            tail -20 "${LOG_DIR}/water-controller.log" 2>/dev/null | while read -r line; do
                echo "  $line"
            done
        elif command -v journalctl >/dev/null 2>&1; then
            echo "Last 20 journal entries:"
            journalctl -u water-controller.service -n 20 --no-pager 2>/dev/null | while read -r line; do
                echo "  $line"
            done
        else
            echo "No logs available"
        fi
        echo ""

        # Footer
        echo "==============================================================================="
        echo "                              END OF REPORT"
        echo "==============================================================================="

    } > "$temp_file"

    # Atomic move
    if mv "$temp_file" "$output_file"; then
        chmod 644 "$output_file"
        log_info "Installation report generated: $output_file"
        return 0
    else
        rm -f "$temp_file"
        log_error "Failed to write installation report"
        return 1
    fi
}

# Detect hardware type for report
_detect_hardware_type() {
    # Check for Raspberry Pi
    if [ -f /proc/device-tree/model ]; then
        local model
        model=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)
        if [ -n "$model" ]; then
            echo "$model"
            return
        fi
    fi

    # Check for common SBC identifiers
    if grep -qi "raspberry" /proc/cpuinfo 2>/dev/null; then
        echo "Raspberry Pi"
        return
    fi

    if grep -qi "orange" /proc/cpuinfo 2>/dev/null; then
        echo "Orange Pi"
        return
    fi

    if grep -qi "rockchip" /proc/cpuinfo 2>/dev/null; then
        echo "Rockchip SBC"
        return
    fi

    # Generic detection
    local arch
    arch=$(uname -m)
    case "$arch" in
        armv7l|armv6l)
            echo "ARM 32-bit SBC"
            ;;
        aarch64)
            echo "ARM 64-bit SBC"
            ;;
        x86_64)
            echo "x86_64 System"
            ;;
        i686|i386)
            echo "x86 32-bit System"
            ;;
        *)
            echo "Unknown ($arch)"
            ;;
    esac
}

# =============================================================================
# Configuration Documentation
# =============================================================================

# Generate configuration documentation in Markdown format
# Returns: 0 on success, 1 on failure
generate_config_docs() {
    local output_file="${1:-${DOC_DIR}/${CONFIG_DOC}}"
    local doc_dir
    doc_dir="$(dirname "$output_file")"

    log_info "Generating configuration documentation: $output_file"

    # Ensure output directory exists
    if ! _ensure_dir "$doc_dir"; then
        log_error "Cannot create documentation directory: $doc_dir"
        return 1
    fi

    # Create temporary file for atomic write
    local temp_file
    temp_file="$(mktemp)" || {
        log_error "Failed to create temporary file"
        return 1
    }

    # Generate documentation
    {
        echo "# Water Treatment Controller - Configuration Documentation"
        echo ""
        echo "Generated: $(_get_readable_timestamp)"
        echo ""
        echo "---"
        echo ""

        echo "## Table of Contents"
        echo ""
        echo "1. [Overview](#overview)"
        echo "2. [Directory Structure](#directory-structure)"
        echo "3. [Configuration File](#configuration-file)"
        echo "4. [Service Configuration](#service-configuration)"
        echo "5. [Network Settings](#network-settings)"
        echo "6. [Database Configuration](#database-configuration)"
        echo "7. [Logging Configuration](#logging-configuration)"
        echo "8. [Security Settings](#security-settings)"
        echo ""
        echo "---"
        echo ""

        # Overview
        echo "## Overview"
        echo ""
        echo "The Water Treatment Controller is a SCADA system designed for water treatment"
        echo "facility automation. This document describes the current configuration state."
        echo ""
        echo "- **Installation Path**: \`$INSTALL_DIR\`"
        echo "- **Configuration Path**: \`$CONFIG_DIR\`"
        echo "- **Data Path**: \`$DATA_DIR\`"
        echo "- **Log Path**: \`$LOG_DIR\`"
        echo ""

        # Directory Structure
        echo "## Directory Structure"
        echo ""
        echo "\`\`\`"
        echo "$INSTALL_DIR/"
        if [ -d "$INSTALL_DIR" ]; then
            find "$INSTALL_DIR" -maxdepth 2 -type d 2>/dev/null | sort | while read -r dir; do
                local relative="${dir#$INSTALL_DIR}"
                [ -z "$relative" ] && continue
                local depth
                depth=$(echo "$relative" | tr -cd '/' | wc -c)
                local indent=""
                for ((i=0; i<depth; i++)); do
                    indent="${indent}  "
                done
                echo "${indent}$(basename "$dir")/"
            done
        fi
        echo "\`\`\`"
        echo ""

        # Configuration File
        echo "## Configuration File"
        echo ""
        echo "**Location**: \`${CONFIG_DIR}/config.yaml\`"
        echo ""

        if [ -f "${CONFIG_DIR}/config.yaml" ]; then
            echo "### Current Configuration"
            echo ""
            echo "\`\`\`yaml"
            # Show config but redact sensitive values
            sed -E 's/(password|secret|key|token):\s*.+/\1: [REDACTED]/gi' "${CONFIG_DIR}/config.yaml" 2>/dev/null
            echo "\`\`\`"
        else
            echo "*Configuration file not found*"
        fi
        echo ""

        # Service Configuration
        echo "## Service Configuration"
        echo ""
        echo "**Service Name**: \`water-controller.service\`"
        echo ""

        if [ -f "/etc/systemd/system/water-controller.service" ]; then
            echo "### systemd Unit File"
            echo ""
            echo "\`\`\`ini"
            cat "/etc/systemd/system/water-controller.service" 2>/dev/null
            echo "\`\`\`"
            echo ""

            echo "### Service Status"
            echo ""
            echo "\`\`\`"
            systemctl status water-controller.service --no-pager 2>/dev/null || echo "Service not running"
            echo "\`\`\`"
        else
            echo "*Service unit file not installed*"
        fi
        echo ""

        # Network Settings
        echo "## Network Settings"
        echo ""
        echo "### Configured Interfaces"
        echo ""
        echo "| Interface | State | IP Address |"
        echo "|-----------|-------|------------|"
        ip -brief addr 2>/dev/null | while read -r iface state addrs; do
            echo "| $iface | $state | $addrs |"
        done
        echo ""

        echo "### Firewall Rules"
        echo ""
        if command -v firewall-cmd >/dev/null 2>&1; then
            echo "**Firewall**: firewalld"
            echo ""
            echo "\`\`\`"
            firewall-cmd --list-all 2>/dev/null || echo "Unable to query firewall"
            echo "\`\`\`"
        elif command -v ufw >/dev/null 2>&1; then
            echo "**Firewall**: ufw"
            echo ""
            echo "\`\`\`"
            ufw status verbose 2>/dev/null || echo "Unable to query firewall"
            echo "\`\`\`"
        elif command -v iptables >/dev/null 2>&1; then
            echo "**Firewall**: iptables"
            echo ""
            echo "\`\`\`"
            iptables -L -n 2>/dev/null | head -30 || echo "Unable to query firewall"
            echo "\`\`\`"
        else
            echo "*No firewall detected*"
        fi
        echo ""

        echo "### Required Ports"
        echo ""
        echo "| Port | Protocol | Purpose |"
        echo "|------|----------|---------|"
        echo "| 8000 | TCP | REST API |"
        echo "| 8080 | TCP | HMI Web Interface |"
        echo "| 34962 | TCP | PROFINET |"
        echo "| 34963 | TCP | PROFINET |"
        echo "| 34964 | UDP | PROFINET |"
        echo ""

        # Database Configuration
        echo "## Database Configuration"
        echo ""
        echo "**Type**: SQLite"
        echo "**Location**: \`${DATA_DIR}/water_controller.db\`"
        echo ""

        if [ -f "${DATA_DIR}/water_controller.db" ]; then
            echo "### Database Info"
            echo ""
            echo "| Property | Value |"
            echo "|----------|-------|"
            echo "| Size | $(ls -lh "${DATA_DIR}/water_controller.db" 2>/dev/null | awk '{print $5}') |"
            echo "| Modified | $(stat -c '%y' "${DATA_DIR}/water_controller.db" 2>/dev/null | cut -d'.' -f1 || stat -f '%Sm' "${DATA_DIR}/water_controller.db" 2>/dev/null) |"
            echo "| Permissions | $(stat -c '%a' "${DATA_DIR}/water_controller.db" 2>/dev/null || stat -f '%Lp' "${DATA_DIR}/water_controller.db" 2>/dev/null) |"
            echo ""

            if command -v sqlite3 >/dev/null 2>&1; then
                echo "### SQLite Settings"
                echo ""
                echo "\`\`\`"
                sqlite3 "${DATA_DIR}/water_controller.db" "PRAGMA journal_mode; PRAGMA synchronous; PRAGMA cache_size;" 2>/dev/null
                echo "\`\`\`"
                echo ""

                echo "### Tables"
                echo ""
                echo "\`\`\`"
                sqlite3 "${DATA_DIR}/water_controller.db" ".tables" 2>/dev/null
                echo "\`\`\`"
            fi
        else
            echo "*Database file not found*"
        fi
        echo ""

        # Logging Configuration
        echo "## Logging Configuration"
        echo ""
        echo "**Log Directory**: \`$LOG_DIR\`"
        echo ""

        if [ -d "$LOG_DIR" ]; then
            echo "### Log Files"
            echo ""
            echo "| File | Size | Modified |"
            echo "|------|------|----------|"
            find "$LOG_DIR" -type f -name "*.log*" 2>/dev/null | head -20 | while read -r logfile; do
                local size modified
                size=$(ls -lh "$logfile" 2>/dev/null | awk '{print $5}')
                modified=$(stat -c '%y' "$logfile" 2>/dev/null | cut -d'.' -f1 || stat -f '%Sm' "$logfile" 2>/dev/null)
                echo "| $(basename "$logfile") | $size | $modified |"
            done
        fi
        echo ""

        if [ -f "/etc/logrotate.d/water-controller" ]; then
            echo "### Log Rotation Configuration"
            echo ""
            echo "\`\`\`"
            cat "/etc/logrotate.d/water-controller" 2>/dev/null
            echo "\`\`\`"
        fi
        echo ""

        # Security Settings
        echo "## Security Settings"
        echo ""

        echo "### Service User"
        echo ""
        if id water-controller >/dev/null 2>&1; then
            echo "| Property | Value |"
            echo "|----------|-------|"
            echo "| Username | water-controller |"
            echo "| UID | $(id -u water-controller 2>/dev/null) |"
            echo "| GID | $(id -g water-controller 2>/dev/null) |"
            echo "| Groups | $(id -Gn water-controller 2>/dev/null | tr ' ' ', ') |"
            echo "| Shell | $(getent passwd water-controller 2>/dev/null | cut -d: -f7) |"
            echo "| Home | $(getent passwd water-controller 2>/dev/null | cut -d: -f6) |"
        else
            echo "*Service user not created*"
        fi
        echo ""

        echo "### systemd Security Hardening"
        echo ""
        if [ -f "/etc/systemd/system/water-controller.service" ]; then
            echo "| Setting | Value |"
            echo "|---------|-------|"
            grep -E "^(NoNewPrivileges|ProtectSystem|ProtectHome|PrivateTmp|ReadOnlyPaths|ReadWritePaths)=" \
                "/etc/systemd/system/water-controller.service" 2>/dev/null | while IFS='=' read -r key value; do
                echo "| $key | $value |"
            done
        else
            echo "*Service not installed*"
        fi
        echo ""

        # Footer
        echo "---"
        echo ""
        echo "*This documentation was automatically generated. Manual edits may be overwritten.*"

    } > "$temp_file"

    # Atomic move
    if mv "$temp_file" "$output_file"; then
        chmod 644 "$output_file"
        log_info "Configuration documentation generated: $output_file"
        return 0
    else
        rm -f "$temp_file"
        log_error "Failed to write configuration documentation"
        return 1
    fi
}

# =============================================================================
# Backup Manifest Management
# =============================================================================

# Create or update backup manifest
# Arguments:
#   $1 - backup_type (full, config, database, rollback)
#   $2 - backup_path
#   $3 - description (optional)
# Returns: 0 on success, 1 on failure
create_backup_manifest() {
    local backup_type="${1:-full}"
    local backup_path="$2"
    local description="${3:-Backup created by installation script}"
    local manifest_file="${BACKUP_DIR}/${BACKUP_MANIFEST}"

    if [ -z "$backup_path" ]; then
        log_error "Backup path is required"
        return 1
    fi

    log_info "Creating backup manifest entry for: $backup_path"

    # Ensure backup directory exists
    if ! _ensure_dir "$BACKUP_DIR"; then
        log_error "Cannot create backup directory: $BACKUP_DIR"
        return 1
    fi

    # Calculate backup size and hash
    local backup_size="0"
    local backup_hash="none"
    local file_count=0

    if [ -f "$backup_path" ]; then
        backup_size=$(stat -c '%s' "$backup_path" 2>/dev/null || stat -f '%z' "$backup_path" 2>/dev/null || echo "0")
        backup_hash=$(_get_file_hash "$backup_path")
        file_count=1
    elif [ -d "$backup_path" ]; then
        backup_size=$(du -sb "$backup_path" 2>/dev/null | awk '{print $1}' || echo "0")
        file_count=$(_get_file_count "$backup_path")
    fi

    # Create new entry
    local timestamp
    timestamp=$(_get_timestamp)
    local entry_id
    entry_id=$(echo "${timestamp}-${backup_type}-$$" | sha256sum 2>/dev/null | cut -c1-12 || echo "$$")

    local new_entry
    new_entry=$(cat <<EOF
  {
    "id": "$entry_id",
    "timestamp": "$timestamp",
    "type": "$backup_type",
    "path": "$(_json_escape "$backup_path")",
    "size": $backup_size,
    "file_count": $file_count,
    "hash": "$backup_hash",
    "description": "$(_json_escape "$description")",
    "hostname": "$(hostname 2>/dev/null || echo 'unknown')",
    "created_by": "$(whoami 2>/dev/null || echo 'unknown')"
  }
EOF
)

    # Read existing manifest or create new one
    local temp_file
    temp_file="$(mktemp)" || {
        log_error "Failed to create temporary file"
        return 1
    }

    if [ -f "$manifest_file" ]; then
        # Parse existing manifest and add new entry
        # Simple approach: read the JSON array and append
        local existing_entries
        existing_entries=$(grep -v '^\[' "$manifest_file" | grep -v '^\]' | sed '$ s/,$//')

        if [ -n "$existing_entries" ]; then
            cat > "$temp_file" <<EOF
[
$existing_entries,
$new_entry
]
EOF
        else
            cat > "$temp_file" <<EOF
[
$new_entry
]
EOF
        fi
    else
        cat > "$temp_file" <<EOF
[
$new_entry
]
EOF
    fi

    # Atomic move
    if mv "$temp_file" "$manifest_file"; then
        chmod 644 "$manifest_file"
        log_info "Backup manifest updated: $manifest_file"
        return 0
    else
        rm -f "$temp_file"
        log_error "Failed to update backup manifest"
        return 1
    fi
}

# List backups from manifest
# Arguments:
#   $1 - backup_type filter (optional)
# Returns: 0 on success, 1 on failure
list_backups() {
    local type_filter="$1"
    local manifest_file="${BACKUP_DIR}/${BACKUP_MANIFEST}"

    if [ ! -f "$manifest_file" ]; then
        log_warn "No backup manifest found"
        echo "No backups recorded"
        return 0
    fi

    echo ""
    echo "Backup Manifest: $manifest_file"
    echo ""
    printf "%-14s %-22s %-10s %-12s %s\n" "ID" "TIMESTAMP" "TYPE" "SIZE" "PATH"
    echo "-------------- ---------------------- ---------- ------------ ----------------------------------------"

    # Parse JSON manually (basic parsing for our known format)
    local in_entry=0
    local entry_id="" entry_ts="" entry_type="" entry_size="" entry_path=""

    while IFS= read -r line; do
        # Detect entry start
        if [[ "$line" == *"{"* ]]; then
            in_entry=1
            entry_id="" entry_ts="" entry_type="" entry_size="" entry_path=""
            continue
        fi

        # Detect entry end
        if [[ "$line" == *"}"* ]]; then
            in_entry=0
            # Apply filter
            if [ -z "$type_filter" ] || [ "$entry_type" = "$type_filter" ]; then
                # Format size
                local size_human
                if [ "$entry_size" -gt 1073741824 ] 2>/dev/null; then
                    size_human="$(echo "scale=1; $entry_size / 1073741824" | bc 2>/dev/null || echo "$entry_size")G"
                elif [ "$entry_size" -gt 1048576 ] 2>/dev/null; then
                    size_human="$(echo "scale=1; $entry_size / 1048576" | bc 2>/dev/null || echo "$entry_size")M"
                elif [ "$entry_size" -gt 1024 ] 2>/dev/null; then
                    size_human="$(echo "scale=1; $entry_size / 1024" | bc 2>/dev/null || echo "$entry_size")K"
                else
                    size_human="${entry_size}B"
                fi

                printf "%-14s %-22s %-10s %-12s %s\n" "$entry_id" "$entry_ts" "$entry_type" "$size_human" "$entry_path"
            fi
            continue
        fi

        # Parse fields
        if [ $in_entry -eq 1 ]; then
            case "$line" in
                *'"id"'*)
                    entry_id=$(echo "$line" | sed 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
                    ;;
                *'"timestamp"'*)
                    entry_ts=$(echo "$line" | sed 's/.*"timestamp"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
                    ;;
                *'"type"'*)
                    entry_type=$(echo "$line" | sed 's/.*"type"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
                    ;;
                *'"size"'*)
                    entry_size=$(echo "$line" | sed 's/.*"size"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/')
                    ;;
                *'"path"'*)
                    entry_path=$(echo "$line" | sed 's/.*"path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
                    ;;
            esac
        fi
    done < "$manifest_file"

    echo ""
    return 0
}

# =============================================================================
# Rollback Point Management
# =============================================================================

# Create a rollback point (full system snapshot)
# Arguments:
#   $1 - description (optional)
# Returns: 0 on success, 1 on failure
create_rollback_point() {
    local description="${1:-Manual rollback point}"
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    local rollback_name="rollback_${timestamp}"
    local rollback_path="${ROLLBACK_DIR}/${rollback_name}"

    log_info "Creating rollback point: $rollback_name"

    # Ensure rollback directory exists
    if ! _ensure_dir "$ROLLBACK_DIR"; then
        log_error "Cannot create rollback directory: $ROLLBACK_DIR"
        return 1
    fi

    # Check for maximum rollback points and cleanup if needed
    _cleanup_old_rollback_points

    # Create rollback directory
    if ! sudo mkdir -p "$rollback_path"; then
        log_error "Failed to create rollback directory: $rollback_path"
        return 1
    fi

    local errors=0

    # Stop service if running (for consistent snapshot)
    local service_was_running=0
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl is-active --quiet water-controller.service 2>/dev/null; then
            service_was_running=1
            log_info "Stopping service for consistent snapshot..."
            sudo systemctl stop water-controller.service 2>/dev/null || true
            sleep 2
        fi
    fi

    # Backup application files
    if [ -d "$INSTALL_DIR" ]; then
        log_info "Backing up application directory..."
        if sudo tar -czf "${rollback_path}/app.tar.gz" -C "$(dirname "$INSTALL_DIR")" "$(basename "$INSTALL_DIR")" 2>/dev/null; then
            log_info "Application backup complete"
        else
            log_error "Failed to backup application directory"
            ((errors++))
        fi
    fi

    # Backup configuration
    if [ -d "$CONFIG_DIR" ]; then
        log_info "Backing up configuration directory..."
        if sudo tar -czf "${rollback_path}/config.tar.gz" -C "$(dirname "$CONFIG_DIR")" "$(basename "$CONFIG_DIR")" 2>/dev/null; then
            log_info "Configuration backup complete"
        else
            log_error "Failed to backup configuration directory"
            ((errors++))
        fi
    fi

    # Backup database
    if [ -f "${DATA_DIR}/water_controller.db" ]; then
        log_info "Backing up database..."
        if sudo cp -a "${DATA_DIR}/water_controller.db" "${rollback_path}/water_controller.db" 2>/dev/null; then
            # Also backup WAL and SHM files if they exist
            [ -f "${DATA_DIR}/water_controller.db-wal" ] && sudo cp -a "${DATA_DIR}/water_controller.db-wal" "${rollback_path}/" 2>/dev/null
            [ -f "${DATA_DIR}/water_controller.db-shm" ] && sudo cp -a "${DATA_DIR}/water_controller.db-shm" "${rollback_path}/" 2>/dev/null
            log_info "Database backup complete"
        else
            log_error "Failed to backup database"
            ((errors++))
        fi
    fi

    # Backup service file
    if [ -f "/etc/systemd/system/water-controller.service" ]; then
        log_info "Backing up service file..."
        if sudo cp -a "/etc/systemd/system/water-controller.service" "${rollback_path}/" 2>/dev/null; then
            log_info "Service file backup complete"
        else
            log_error "Failed to backup service file"
            ((errors++))
        fi
    fi

    # Create metadata file
    sudo tee "${rollback_path}/metadata.json" > /dev/null <<EOF
{
  "name": "$rollback_name",
  "timestamp": "$(_get_timestamp)",
  "description": "$(_json_escape "$description")",
  "hostname": "$(hostname 2>/dev/null || echo 'unknown')",
  "created_by": "$(whoami 2>/dev/null || echo 'unknown')",
  "components": {
    "app": $([ -f "${rollback_path}/app.tar.gz" ] && echo "true" || echo "false"),
    "config": $([ -f "${rollback_path}/config.tar.gz" ] && echo "true" || echo "false"),
    "database": $([ -f "${rollback_path}/water_controller.db" ] && echo "true" || echo "false"),
    "service": $([ -f "${rollback_path}/water-controller.service" ] && echo "true" || echo "false")
  },
  "errors": $errors
}
EOF

    # Restart service if it was running
    if [ $service_was_running -eq 1 ]; then
        log_info "Restarting service..."
        sudo systemctl start water-controller.service 2>/dev/null || true
    fi

    # Add to backup manifest
    create_backup_manifest "rollback" "$rollback_path" "$description"

    if [ $errors -eq 0 ]; then
        log_info "Rollback point created successfully: $rollback_path"
        echo "$rollback_path"
        return 0
    else
        log_warn "Rollback point created with $errors errors: $rollback_path"
        echo "$rollback_path"
        return 0  # Still return success as partial backup may be useful
    fi
}

# Cleanup old rollback points (keep only MAX_ROLLBACK_POINTS)
_cleanup_old_rollback_points() {
    if [ ! -d "$ROLLBACK_DIR" ]; then
        return 0
    fi

    local count
    count=$(find "$ROLLBACK_DIR" -maxdepth 1 -type d -name "rollback_*" 2>/dev/null | wc -l)

    if [ "$count" -ge "$MAX_ROLLBACK_POINTS" ]; then
        log_info "Cleaning up old rollback points (keeping $MAX_ROLLBACK_POINTS)..."

        # Get oldest rollback points
        local to_remove=$((count - MAX_ROLLBACK_POINTS + 1))

        find "$ROLLBACK_DIR" -maxdepth 1 -type d -name "rollback_*" 2>/dev/null | \
            sort | head -n "$to_remove" | while read -r old_rollback; do
            log_info "Removing old rollback: $(basename "$old_rollback")"
            sudo rm -rf "$old_rollback"
        done
    fi
}

# List available rollback points
# Returns: 0 on success
list_rollback_points() {
    if [ ! -d "$ROLLBACK_DIR" ]; then
        echo "No rollback points available"
        return 0
    fi

    local count
    count=$(find "$ROLLBACK_DIR" -maxdepth 1 -type d -name "rollback_*" 2>/dev/null | wc -l)

    if [ "$count" -eq 0 ]; then
        echo "No rollback points available"
        return 0
    fi

    echo ""
    echo "Available Rollback Points:"
    echo ""
    printf "%-25s %-22s %-10s %s\n" "NAME" "CREATED" "SIZE" "DESCRIPTION"
    echo "------------------------- ---------------------- ---------- ----------------------------------------"

    find "$ROLLBACK_DIR" -maxdepth 1 -type d -name "rollback_*" 2>/dev/null | sort -r | while read -r rp; do
        local name
        name=$(basename "$rp")

        local created="unknown"
        local description="No description"

        if [ -f "${rp}/metadata.json" ]; then
            created=$(grep '"timestamp"' "${rp}/metadata.json" 2>/dev/null | sed 's/.*"timestamp"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' | cut -c1-19 | tr 'T' ' ')
            description=$(grep '"description"' "${rp}/metadata.json" 2>/dev/null | sed 's/.*"description"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' | cut -c1-40)
        fi

        local size
        size=$(_get_dir_size "$rp")

        printf "%-25s %-22s %-10s %s\n" "$name" "$created" "$size" "$description"
    done

    echo ""
    echo "Total rollback points: $count"
    echo ""

    return 0
}

# Perform rollback to a specific point
# Arguments:
#   $1 - rollback point name or path
#   $2 - components to restore (optional, default: all)
# Returns: 0 on success, 1 on failure
perform_rollback() {
    local rollback_point="$1"
    local components="${2:-all}"

    if [ -z "$rollback_point" ]; then
        log_error "Rollback point name is required"
        return 1
    fi

    # Determine rollback path
    local rollback_path
    if [ -d "$rollback_point" ]; then
        rollback_path="$rollback_point"
    elif [ -d "${ROLLBACK_DIR}/${rollback_point}" ]; then
        rollback_path="${ROLLBACK_DIR}/${rollback_point}"
    else
        log_error "Rollback point not found: $rollback_point"
        return 1
    fi

    log_info "Performing rollback from: $rollback_path"
    log_info "Components to restore: $components"

    # Verify metadata exists
    if [ ! -f "${rollback_path}/metadata.json" ]; then
        log_error "Invalid rollback point: metadata.json not found"
        return 1
    fi

    # Create a pre-rollback snapshot for safety
    log_info "Creating pre-rollback snapshot..."
    create_rollback_point "Pre-rollback snapshot (before restoring $(basename "$rollback_path"))" >/dev/null 2>&1 || true

    # Stop service
    local service_was_running=0
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl is-active --quiet water-controller.service 2>/dev/null; then
            service_was_running=1
            log_info "Stopping service..."
            sudo systemctl stop water-controller.service 2>/dev/null || true
            sleep 2
        fi
    fi

    local errors=0

    # Restore application
    if [ "$components" = "all" ] || [[ "$components" == *"app"* ]]; then
        if [ -f "${rollback_path}/app.tar.gz" ]; then
            log_info "Restoring application..."

            # Backup current app first
            if [ -d "$INSTALL_DIR" ]; then
                sudo mv "$INSTALL_DIR" "${INSTALL_DIR}.rollback-backup.$$" 2>/dev/null || true
            fi

            # Extract
            if sudo tar -xzf "${rollback_path}/app.tar.gz" -C "$(dirname "$INSTALL_DIR")" 2>/dev/null; then
                log_info "Application restored"
                sudo rm -rf "${INSTALL_DIR}.rollback-backup.$$" 2>/dev/null || true
            else
                log_error "Failed to restore application"
                # Attempt to restore backup
                if [ -d "${INSTALL_DIR}.rollback-backup.$$" ]; then
                    sudo mv "${INSTALL_DIR}.rollback-backup.$$" "$INSTALL_DIR" 2>/dev/null || true
                fi
                ((errors++))
            fi
        else
            log_warn "Application backup not found in rollback point"
        fi
    fi

    # Restore configuration
    if [ "$components" = "all" ] || [[ "$components" == *"config"* ]]; then
        if [ -f "${rollback_path}/config.tar.gz" ]; then
            log_info "Restoring configuration..."

            # Backup current config first
            if [ -d "$CONFIG_DIR" ]; then
                sudo mv "$CONFIG_DIR" "${CONFIG_DIR}.rollback-backup.$$" 2>/dev/null || true
            fi

            # Extract
            if sudo tar -xzf "${rollback_path}/config.tar.gz" -C "$(dirname "$CONFIG_DIR")" 2>/dev/null; then
                log_info "Configuration restored"
                sudo rm -rf "${CONFIG_DIR}.rollback-backup.$$" 2>/dev/null || true
            else
                log_error "Failed to restore configuration"
                # Attempt to restore backup
                if [ -d "${CONFIG_DIR}.rollback-backup.$$" ]; then
                    sudo mv "${CONFIG_DIR}.rollback-backup.$$" "$CONFIG_DIR" 2>/dev/null || true
                fi
                ((errors++))
            fi
        else
            log_warn "Configuration backup not found in rollback point"
        fi
    fi

    # Restore database
    if [ "$components" = "all" ] || [[ "$components" == *"database"* ]]; then
        if [ -f "${rollback_path}/water_controller.db" ]; then
            log_info "Restoring database..."

            # Backup current database first
            if [ -f "${DATA_DIR}/water_controller.db" ]; then
                sudo cp -a "${DATA_DIR}/water_controller.db" "${DATA_DIR}/water_controller.db.rollback-backup.$$" 2>/dev/null || true
            fi

            # Copy database
            if sudo cp -a "${rollback_path}/water_controller.db" "${DATA_DIR}/water_controller.db" 2>/dev/null; then
                # Also restore WAL and SHM if present
                [ -f "${rollback_path}/water_controller.db-wal" ] && sudo cp -a "${rollback_path}/water_controller.db-wal" "${DATA_DIR}/" 2>/dev/null
                [ -f "${rollback_path}/water_controller.db-shm" ] && sudo cp -a "${rollback_path}/water_controller.db-shm" "${DATA_DIR}/" 2>/dev/null

                # Set ownership
                sudo chown water-controller:water-controller "${DATA_DIR}/water_controller.db"* 2>/dev/null || true

                log_info "Database restored"
                sudo rm -f "${DATA_DIR}/water_controller.db.rollback-backup.$$" 2>/dev/null || true
            else
                log_error "Failed to restore database"
                # Attempt to restore backup
                if [ -f "${DATA_DIR}/water_controller.db.rollback-backup.$$" ]; then
                    sudo mv "${DATA_DIR}/water_controller.db.rollback-backup.$$" "${DATA_DIR}/water_controller.db" 2>/dev/null || true
                fi
                ((errors++))
            fi
        else
            log_warn "Database backup not found in rollback point"
        fi
    fi

    # Restore service file
    if [ "$components" = "all" ] || [[ "$components" == *"service"* ]]; then
        if [ -f "${rollback_path}/water-controller.service" ]; then
            log_info "Restoring service file..."

            if sudo cp -a "${rollback_path}/water-controller.service" "/etc/systemd/system/water-controller.service" 2>/dev/null; then
                sudo systemctl daemon-reload 2>/dev/null || true
                log_info "Service file restored"
            else
                log_error "Failed to restore service file"
                ((errors++))
            fi
        else
            log_warn "Service file backup not found in rollback point"
        fi
    fi

    # Restart service if it was running
    if [ $service_was_running -eq 1 ]; then
        log_info "Starting service..."
        if sudo systemctl start water-controller.service 2>/dev/null; then
            sleep 3
            if systemctl is-active --quiet water-controller.service 2>/dev/null; then
                log_info "Service started successfully"
            else
                log_error "Service failed to start after rollback"
                ((errors++))
            fi
        else
            log_error "Failed to start service after rollback"
            ((errors++))
        fi
    fi

    if [ $errors -eq 0 ]; then
        log_info "Rollback completed successfully"
        return 0
    else
        log_error "Rollback completed with $errors errors"
        return 1
    fi
}

# =============================================================================
# Backup Cleanup
# =============================================================================

# Clean up old backups based on retention policy
# Arguments:
#   $1 - max_age_days (optional, default: MAX_BACKUP_AGE_DAYS)
# Returns: 0 on success
cleanup_old_backups() {
    local max_age="${1:-$MAX_BACKUP_AGE_DAYS}"

    log_info "Cleaning up backups older than $max_age days..."

    local cleaned=0

    # Clean up old backup files
    if [ -d "$BACKUP_DIR" ]; then
        # Find and remove old backup files
        while IFS= read -r old_backup; do
            [ -z "$old_backup" ] && continue
            log_info "Removing old backup: $old_backup"
            rm -rf "$old_backup"
            ((cleaned++))
        done < <(find "$BACKUP_DIR" -maxdepth 1 \( -name "*.tar.gz" -o -name "*.bak" \) -type f -mtime +"$max_age" 2>/dev/null)

        # Find and remove old rollback directories (beyond MAX_ROLLBACK_POINTS already handled)
        while IFS= read -r old_rollback; do
            [ -z "$old_rollback" ] && continue
            log_info "Removing old rollback point: $(basename "$old_rollback")"
            rm -rf "$old_rollback"
            ((cleaned++))
        done < <(find "$ROLLBACK_DIR" -maxdepth 1 -type d -name "rollback_*" -mtime +"$max_age" 2>/dev/null)
    fi

    # Clean up old config backups
    if [ -d "$CONFIG_DIR" ]; then
        while IFS= read -r old_config; do
            [ -z "$old_config" ] && continue
            log_info "Removing old config backup: $old_config"
            rm -f "$old_config"
            ((cleaned++))
        done < <(find "$CONFIG_DIR" -maxdepth 1 -name "*.bak.*" -type f -mtime +"$max_age" 2>/dev/null)
    fi

    log_info "Cleanup complete: removed $cleaned old backup(s)"
    return 0
}

# Get backup statistics
# Returns: 0 on success
get_backup_stats() {
    echo ""
    echo "Backup Statistics"
    echo "================="
    echo ""

    # Backup directory stats
    if [ -d "$BACKUP_DIR" ]; then
        echo "Backup Directory: $BACKUP_DIR"
        echo "  Total Size:     $(_get_dir_size "$BACKUP_DIR")"
        echo "  File Count:     $(_get_file_count "$BACKUP_DIR")"
        echo ""
    else
        echo "Backup Directory: Not created"
        echo ""
    fi

    # Rollback points
    if [ -d "$ROLLBACK_DIR" ]; then
        local rp_count
        rp_count=$(find "$ROLLBACK_DIR" -maxdepth 1 -type d -name "rollback_*" 2>/dev/null | wc -l)
        echo "Rollback Points:  $rp_count / $MAX_ROLLBACK_POINTS max"
        echo "  Total Size:     $(_get_dir_size "$ROLLBACK_DIR")"

        if [ "$rp_count" -gt 0 ]; then
            local oldest newest
            oldest=$(find "$ROLLBACK_DIR" -maxdepth 1 -type d -name "rollback_*" 2>/dev/null | sort | head -1 | xargs basename 2>/dev/null)
            newest=$(find "$ROLLBACK_DIR" -maxdepth 1 -type d -name "rollback_*" 2>/dev/null | sort | tail -1 | xargs basename 2>/dev/null)
            echo "  Oldest:         $oldest"
            echo "  Newest:         $newest"
        fi
        echo ""
    else
        echo "Rollback Points:  None"
        echo ""
    fi

    # Manifest stats
    local manifest_file="${BACKUP_DIR}/${BACKUP_MANIFEST}"
    if [ -f "$manifest_file" ]; then
        local entry_count
        entry_count=$(grep -c '"id"' "$manifest_file" 2>/dev/null || echo "0")
        echo "Manifest Entries: $entry_count"
        echo "  File:           $manifest_file"
        echo "  Size:           $(ls -lh "$manifest_file" 2>/dev/null | awk '{print $5}')"
    else
        echo "Manifest:         Not created"
    fi
    echo ""

    # Retention policy
    echo "Retention Policy"
    echo "  Max Rollback Points: $MAX_ROLLBACK_POINTS"
    echo "  Max Backup Age:      $MAX_BACKUP_AGE_DAYS days"
    echo ""

    return 0
}

# =============================================================================
# Module Help
# =============================================================================

# Display module help
documentation_help() {
    cat <<EOF
Water Treatment Controller - Documentation and Rollback Module v${DOCUMENTATION_VERSION}

USAGE:
    source documentation.sh
    <function_name> [arguments]

FUNCTIONS:

  Documentation Generation:
    generate_installation_report [output_file]
        Generate comprehensive installation report
        Default: ${DOC_DIR}/${INSTALL_REPORT}

    generate_config_docs [output_file]
        Generate configuration documentation in Markdown
        Default: ${DOC_DIR}/${CONFIG_DOC}

  Backup Manifest:
    create_backup_manifest <type> <path> [description]
        Create/update backup manifest entry
        Types: full, config, database, rollback

    list_backups [type_filter]
        List all backups from manifest
        Optional filter by type

  Rollback Management:
    create_rollback_point [description]
        Create full system rollback point
        Includes: app, config, database, service

    list_rollback_points
        List available rollback points

    perform_rollback <point_name> [components]
        Restore from rollback point
        Components: all, app, config, database, service

  Maintenance:
    cleanup_old_backups [max_age_days]
        Remove backups older than specified days
        Default: ${MAX_BACKUP_AGE_DAYS} days

    get_backup_stats
        Display backup statistics and retention info

EXAMPLES:
    # Generate installation report
    generate_installation_report

    # Create a rollback point before upgrade
    create_rollback_point "Before v2.0 upgrade"

    # List available rollback points
    list_rollback_points

    # Rollback to specific point
    perform_rollback rollback_20240115_120000

    # Rollback only database
    perform_rollback rollback_20240115_120000 "database"

    # Clean up old backups
    cleanup_old_backups 14

EOF
}

# =============================================================================
# Module Initialization
# =============================================================================

# Initialize module (create directories if needed)
_init_documentation_module() {
    # Ensure backup directory exists
    _ensure_dir "$BACKUP_DIR" 2>/dev/null || true
    _ensure_dir "$ROLLBACK_DIR" 2>/dev/null || true
    _ensure_dir "$DOC_DIR" 2>/dev/null || true
}

# Run initialization
_init_documentation_module

# Export functions
export -f generate_installation_report
export -f generate_config_docs
export -f create_backup_manifest
export -f list_backups
export -f create_rollback_point
export -f list_rollback_points
export -f perform_rollback
export -f cleanup_old_backups
export -f get_backup_stats
export -f documentation_help

# =============================================================================
# Main (when run directly)
# =============================================================================

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        --help|-h)
            documentation_help
            ;;
        --version|-v)
            echo "Documentation Module v${DOCUMENTATION_VERSION}"
            ;;
        report)
            generate_installation_report "${2:-}"
            ;;
        config-docs)
            generate_config_docs "${2:-}"
            ;;
        create-rollback)
            create_rollback_point "${2:-}"
            ;;
        list-rollback)
            list_rollback_points
            ;;
        rollback)
            perform_rollback "${2:-}" "${3:-all}"
            ;;
        list-backups)
            list_backups "${2:-}"
            ;;
        cleanup)
            cleanup_old_backups "${2:-}"
            ;;
        stats)
            get_backup_stats
            ;;
        *)
            echo "Usage: $0 {--help|report|config-docs|create-rollback|list-rollback|rollback|list-backups|cleanup|stats}"
            echo "Run '$0 --help' for detailed usage"
            exit 1
            ;;
    esac
fi
