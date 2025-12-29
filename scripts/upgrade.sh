#!/bin/bash
# =============================================================================
# Water-Controller Upgrade Script
# =============================================================================
# Implements git-based upgrade with pre-flight version checking.
#
# KEY FEATURE: Pre-flight version check using git ls-remote
# - Checks remote version BEFORE any disk writes
# - If already at latest version, exits immediately with zero writes
# - Critical for SD card endurance on embedded systems
#
# Upgrade Flow:
#   PHASE 0: PRE-FLIGHT (zero disk writes)
#   PHASE 1: STAGE (clone to /tmp)
#   PHASE 2: ANALYZE (diff manifests)
#   PHASE 3: BACKUP (create rollback snapshot)
#   PHASE 4: STOP (stop services)
#   PHASE 5: APPLY (copy files)
#   PHASE 6: VALIDATE (health check)
#
# Usage:
#   ./upgrade.sh [options]
#   ./upgrade.sh --dry-run
#   ./upgrade.sh --force
#   ./upgrade.sh --branch develop
#
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
# =============================================================================

set -euo pipefail

# =============================================================================
# Constants
# =============================================================================

readonly UPGRADE_VERSION="1.0.0"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Repository
readonly REPO_URL="https://github.com/mwilco03/Water-Controller.git"
readonly DEFAULT_BRANCH="main"

# Paths
readonly INSTALL_BASE="/opt/water-controller"
readonly VERSION_FILE="$INSTALL_BASE/.version"
readonly MANIFEST_FILE="$INSTALL_BASE/.manifest"
readonly ROLLBACK_DIR="$INSTALL_BASE/.rollback"
readonly CONFIG_DIR="/etc/water-controller"
readonly DATA_DIR="/var/lib/water-controller"
readonly LOG_DIR="/var/log/water-controller"
readonly INSTALL_LOG_FILE="/var/log/water-controller-install.log"

# Service
readonly SERVICE_NAME="water-controller"

# Timeouts
readonly SERVICE_STOP_TIMEOUT=30
readonly SERVICE_START_TIMEOUT=30
readonly HEALTH_CHECK_TIMEOUT=30

# Rollback retention
readonly ROLLBACK_KEEP_COUNT=2

# =============================================================================
# Source Library Modules
# =============================================================================

# Source detection module
if [[ -f "$SCRIPT_DIR/lib/detection.sh" ]]; then
    source "$SCRIPT_DIR/lib/detection.sh"
else
    # Minimal logging fallback
    log_info() { echo "[INFO] $1" >&2; }
    log_warn() { echo "[WARN] $1" >&2; }
    log_error() { echo "[ERROR] $1" >&2; }
    log_debug() { [[ "${DEBUG:-0}" == "1" ]] && echo "[DEBUG] $1" >&2; }
    _log_write() { :; }
fi

# Note: version.sh provides functions like preflight_check, create_rollback_snapshot, etc.
# These are available but upgrade.sh implements its own versions for better control.
# The module can be sourced if needed for future enhancements.

# =============================================================================
# Global Variables
# =============================================================================

STAGING_DIR=""
DRY_RUN="false"
FORCE="false"
TARGET_BRANCH="$DEFAULT_BRANCH"
SOURCE_DIR=""

# =============================================================================
# Cleanup Trap
# =============================================================================

cleanup() {
    local exit_code=$?

    if [[ -n "$STAGING_DIR" ]] && [[ -d "$STAGING_DIR" ]]; then
        log_info "Cleaning up staging directory..."
        rm -rf "$STAGING_DIR"
    fi

    exit $exit_code
}

trap cleanup EXIT

# =============================================================================
# PHASE 0: PRE-FLIGHT (Zero Disk Writes)
# =============================================================================

# Check if upgrade is needed by comparing local vs remote versions
# Uses git ls-remote which performs NO disk writes
phase_preflight() {
    log_info "=== PHASE 0: PRE-FLIGHT VERSION CHECK ==="
    log_info "Checking if upgrade is needed (zero disk writes)..."

    # Check for existing installation
    if [[ ! -d "$INSTALL_BASE" ]]; then
        log_error "No installation found at $INSTALL_BASE"
        log_info "Use install.sh for fresh installation"
        return 1
    fi

    # Read local version
    local local_sha=""
    local local_version=""

    if [[ -f "$VERSION_FILE" ]]; then
        if command -v jq &>/dev/null; then
            local_sha=$(jq -r '.commit_sha // ""' "$VERSION_FILE" 2>/dev/null)
            local_version=$(jq -r '.version // "unknown"' "$VERSION_FILE" 2>/dev/null)
        else
            local_sha=$(grep -oP '"commit_sha"\s*:\s*"\K[^"]+' "$VERSION_FILE" 2>/dev/null || echo "")
            local_version=$(grep -oP '"version"\s*:\s*"\K[^"]+' "$VERSION_FILE" 2>/dev/null || echo "unknown")
        fi
    fi

    if [[ -z "$local_sha" ]]; then
        log_warn "Could not determine installed version"
        log_info "Proceeding with upgrade (no version tracking)"
        return 0
    fi

    log_info "Installed version: $local_version (${local_sha:0:12})"

    # Get remote version using git ls-remote (no disk writes!)
    log_info "Fetching remote version from $TARGET_BRANCH..."

    local remote_sha
    remote_sha=$(git ls-remote "$REPO_URL" "refs/heads/$TARGET_BRANCH" 2>/dev/null | awk '{print $1}')

    if [[ -z "$remote_sha" ]]; then
        log_warn "Could not fetch remote version (network issue?)"
        if [[ "$FORCE" != "true" ]]; then
            log_error "Use --force to proceed anyway"
            return 1
        fi
        log_info "Proceeding due to --force flag"
        return 0
    fi

    log_info "Remote version:    ${remote_sha:0:12} (${TARGET_BRANCH})"

    # Compare versions
    if [[ "$local_sha" == "$remote_sha" ]]; then
        log_info ""
        log_info "======================================"
        log_info "Already at latest version!"
        log_info "Commit: ${remote_sha:0:12}"
        log_info "No upgrade needed. Exiting."
        log_info "======================================"
        log_info ""

        # Exit with success - no disk writes occurred
        if [[ "$FORCE" != "true" ]]; then
            return 2  # Special exit code for "already current"
        fi
        log_info "Proceeding due to --force flag"
    fi

    log_info "Update available: ${local_sha:0:12} -> ${remote_sha:0:12}"
    _log_write "INFO" "Upgrade available: $local_version (${local_sha:0:12}) -> ${remote_sha:0:12}"

    return 0
}

# =============================================================================
# PHASE 1: STAGE (Clone to /tmp)
# =============================================================================

phase_stage() {
    log_info "=== PHASE 1: STAGING ==="

    # Select temp directory with enough space
    local tmp_base="/tmp"
    local tmp_space
    tmp_space=$(df -m /tmp 2>/dev/null | awk 'NR==2 {print $4}')

    if [[ -n "$tmp_space" ]] && [[ "$tmp_space" -lt 1024 ]]; then
        tmp_base="/var/tmp"
        log_info "Using /var/tmp (insufficient space in /tmp)"
    fi

    # Create staging directory
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    STAGING_DIR="${tmp_base}/water-controller-upgrade-${timestamp}-$$"

    log_info "Creating staging directory: $STAGING_DIR"
    mkdir -p "$STAGING_DIR"

    # Clone repository
    log_info "Cloning $TARGET_BRANCH branch..."

    if ! git clone --depth 1 --branch "$TARGET_BRANCH" "$REPO_URL" "$STAGING_DIR/repo" 2>&1; then
        log_error "Failed to clone repository"
        return 1
    fi

    # Verify clone
    if [[ ! -d "$STAGING_DIR/repo/.git" ]]; then
        log_error "Clone verification failed"
        return 1
    fi

    # Get commit info
    local commit_sha
    commit_sha=$(cd "$STAGING_DIR/repo" && git rev-parse HEAD)
    local commit_short="${commit_sha:0:7}"

    log_info "Cloned successfully: $commit_short"

    # Store commit info
    echo "$commit_sha" > "$STAGING_DIR/.commit_sha"
    echo "$TARGET_BRANCH" > "$STAGING_DIR/.branch"

    SOURCE_DIR="$STAGING_DIR/repo"

    _log_write "INFO" "Staged repository at: $STAGING_DIR"

    return 0
}

# =============================================================================
# PHASE 2: ANALYZE (Diff Manifests)
# =============================================================================

phase_analyze() {
    log_info "=== PHASE 2: ANALYZE ==="

    local new_files=0
    local modified_files=0
    local deleted_files=0
    local config_files=0

    # Generate manifest for staged files
    log_info "Generating manifest for staged files..."

    local staged_manifest="$STAGING_DIR/staged.manifest"

    {
        echo "# Staged installation manifest"
        find "$SOURCE_DIR" -type f \
            ! -path "*/.git/*" \
            ! -name "*.md" \
            ! -name "*.txt" \
            ! -name ".gitignore" \
            -print0 2>/dev/null | \
        while IFS= read -r -d '' file; do
            local checksum size relpath
            checksum=$(sha256sum "$file" 2>/dev/null | awk '{print $1}')
            size=$(stat -c %s "$file" 2>/dev/null || echo "0")
            relpath="${file#$SOURCE_DIR/}"
            echo "$checksum $size $relpath"
        done | sort -k3
    } > "$staged_manifest"

    # Compare with current manifest if exists
    if [[ -f "$MANIFEST_FILE" ]]; then
        log_info "Comparing with current installation..."

        # Read current manifest
        declare -A current_files
        while IFS=' ' read -r checksum size path; do
            [[ "$checksum" =~ ^# ]] && continue
            [[ -z "$checksum" ]] && continue
            current_files["$path"]="$checksum"
        done < "$MANIFEST_FILE"

        # Read staged manifest
        declare -A staged_files
        while IFS=' ' read -r checksum size path; do
            [[ "$checksum" =~ ^# ]] && continue
            [[ -z "$checksum" ]] && continue
            staged_files["$path"]="$checksum"
        done < "$staged_manifest"

        # Count differences
        for path in "${!staged_files[@]}"; do
            if [[ -z "${current_files[$path]:-}" ]]; then
                ((new_files++))
            elif [[ "${current_files[$path]}" != "${staged_files[$path]}" ]]; then
                ((modified_files++))
                # Check if it's a config file
                if [[ "$path" == etc/* ]] || [[ "$path" == *.conf ]] || [[ "$path" == *.yaml ]]; then
                    ((config_files++))
                fi
            fi
        done

        for path in "${!current_files[@]}"; do
            if [[ -z "${staged_files[$path]:-}" ]]; then
                ((deleted_files++))
            fi
        done
    else
        log_info "No current manifest found, treating as full upgrade"
        new_files=$(wc -l < "$staged_manifest")
    fi

    log_info ""
    log_info "Change summary:"
    log_info "  New files:      $new_files"
    log_info "  Modified files: $modified_files"
    log_info "  Deleted files:  $deleted_files"
    log_info "  Config files:   $config_files"
    log_info ""

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN: Would apply the above changes"
        return 2  # Signal dry run complete
    fi

    _log_write "INFO" "Upgrade analysis: $new_files new, $modified_files modified, $deleted_files deleted"

    return 0
}

# =============================================================================
# PHASE 3: BACKUP (Create Rollback Snapshot)
# =============================================================================

phase_backup() {
    log_info "=== PHASE 3: BACKUP ==="

    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local rollback_path="$ROLLBACK_DIR/$timestamp"

    log_info "Creating rollback snapshot: $rollback_path"
    mkdir -p "$rollback_path"

    # Backup critical directories
    local dirs=(
        "venv"
        "app"
        "web"
    )

    for dir in "${dirs[@]}"; do
        local src="$INSTALL_BASE/$dir"
        if [[ -d "$src" ]]; then
            log_debug "Backing up: $dir"
            cp -a "$src" "$rollback_path/" 2>/dev/null || true
        fi
    done

    # Backup version and manifest
    [[ -f "$VERSION_FILE" ]] && cp "$VERSION_FILE" "$rollback_path/.version"
    [[ -f "$MANIFEST_FILE" ]] && cp "$MANIFEST_FILE" "$rollback_path/.manifest"

    # Record rollback metadata
    local current_version
    current_version=$(jq -r '.version // "unknown"' "$VERSION_FILE" 2>/dev/null || echo "unknown")
    local current_sha
    current_sha=$(jq -r '.commit_sha // ""' "$VERSION_FILE" 2>/dev/null || echo "")

    cat > "$rollback_path/.rollback_info" <<EOF
timestamp=$timestamp
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
version=$current_version
commit_sha=$current_sha
reason=upgrade
EOF

    log_info "Rollback snapshot created"

    # Prune old rollbacks
    log_debug "Pruning old rollback snapshots..."
    local rollbacks=()
    while IFS= read -r dir; do
        rollbacks+=("$dir")
    done < <(find "$ROLLBACK_DIR" -maxdepth 1 -mindepth 1 -type d | sort)

    local count=${#rollbacks[@]}
    local to_remove=$((count - ROLLBACK_KEEP_COUNT))

    if [[ $to_remove -gt 0 ]]; then
        log_info "Removing $to_remove old rollback snapshot(s)..."
        for ((i=0; i<to_remove; i++)); do
            rm -rf "${rollbacks[$i]}"
        done
    fi

    _log_write "INFO" "Rollback snapshot created: $timestamp"

    return 0
}

# =============================================================================
# PHASE 4: STOP (Stop Services)
# =============================================================================

phase_stop() {
    log_info "=== PHASE 4: STOP SERVICES ==="

    local services=(
        "$SERVICE_NAME"
        "${SERVICE_NAME}-frontend"
        "${SERVICE_NAME}-api"
        "${SERVICE_NAME}-ui"
    )

    for svc in "${services[@]}"; do
        if systemctl is-active "${svc}.service" &>/dev/null; then
            log_info "Stopping ${svc}..."

            if ! sudo systemctl stop "${svc}.service"; then
                log_warn "Could not stop ${svc} gracefully"
            fi

            # Wait for service to stop
            local waited=0
            while systemctl is-active "${svc}.service" &>/dev/null && [[ $waited -lt $SERVICE_STOP_TIMEOUT ]]; do
                sleep 1
                ((waited++))
            done

            if systemctl is-active "${svc}.service" &>/dev/null; then
                log_warn "Force killing ${svc}..."
                sudo systemctl kill "${svc}.service" 2>/dev/null || true
            fi
        fi
    done

    log_info "Services stopped"
    _log_write "INFO" "Services stopped for upgrade"

    return 0
}

# =============================================================================
# PHASE 5: APPLY (Copy Files)
# =============================================================================

phase_apply() {
    log_info "=== PHASE 5: APPLY ==="

    # Update Python virtual environment and dependencies
    if [[ -d "$SOURCE_DIR/web/api" ]]; then
        log_info "Updating Python dependencies..."

        local venv_path="$INSTALL_BASE/venv"

        if [[ -d "$venv_path" ]] && [[ -f "$SOURCE_DIR/web/api/requirements.txt" ]]; then
            if ! "$venv_path/bin/pip" install -r "$SOURCE_DIR/web/api/requirements.txt" 2>&1 | \
                tee -a "$INSTALL_LOG_FILE"; then
                log_error "Python dependency installation failed"
                return 1
            fi
        fi

        # Copy updated Python source
        log_info "Copying Python source..."
        if [[ -d "$INSTALL_BASE/app" ]]; then
            rm -rf "$INSTALL_BASE/app"
        fi
        mkdir -p "$INSTALL_BASE/app"

        if [[ -d "$SOURCE_DIR/web/api/app" ]]; then
            cp -r "$SOURCE_DIR/web/api/app"/* "$INSTALL_BASE/app/"
        elif [[ -d "$SOURCE_DIR/web/api" ]]; then
            cp -r "$SOURCE_DIR/web/api"/* "$INSTALL_BASE/app/"
        fi
    fi

    # Update frontend
    if [[ -d "$SOURCE_DIR/web/ui" ]]; then
        log_info "Updating frontend..."

        local web_path="$INSTALL_BASE/web"
        mkdir -p "$web_path"

        # Copy package files
        cp "$SOURCE_DIR/web/ui/package.json" "$web_path/" 2>/dev/null || true
        cp "$SOURCE_DIR/web/ui/package-lock.json" "$web_path/" 2>/dev/null || true

        # Install npm dependencies if package.json changed
        if [[ -f "$web_path/package.json" ]]; then
            log_info "Installing npm dependencies..."
            if ! (cd "$web_path" && npm ci 2>&1) | tee -a "$INSTALL_LOG_FILE"; then
                log_warn "npm ci failed, trying npm install..."
                if ! (cd "$web_path" && npm install 2>&1) | tee -a "$INSTALL_LOG_FILE"; then
                    log_error "npm dependency installation failed"
                    return 1
                fi
            fi
        fi

        # Copy source files
        if [[ -d "$SOURCE_DIR/web/ui/src" ]]; then
            rm -rf "$web_path/src"
            cp -r "$SOURCE_DIR/web/ui/src" "$web_path/"
        fi

        # Copy other frontend files
        for file in next.config.js tsconfig.json tailwind.config.js; do
            [[ -f "$SOURCE_DIR/web/ui/$file" ]] && cp "$SOURCE_DIR/web/ui/$file" "$web_path/"
        done

        # Build frontend
        log_info "Building frontend..."
        if ! (cd "$web_path" && npm run build 2>&1) | tee -a "$INSTALL_LOG_FILE"; then
            log_error "Frontend build failed"
            return 1
        fi
        log_info "Frontend build successful"
    fi

    # Copy scripts
    if [[ -d "$SOURCE_DIR/scripts" ]]; then
        log_info "Updating scripts..."
        cp -r "$SOURCE_DIR/scripts"/* "$INSTALL_BASE/scripts/" 2>/dev/null || true
        chmod +x "$INSTALL_BASE/scripts"/*.sh 2>/dev/null || true
        chmod +x "$INSTALL_BASE/scripts/lib"/*.sh 2>/dev/null || true
    fi

    # Update systemd services if changed
    if [[ -d "$SOURCE_DIR/systemd" ]]; then
        log_info "Updating systemd services..."
        for service_file in "$SOURCE_DIR/systemd"/*.service; do
            if [[ -f "$service_file" ]]; then
                local service_name
                service_name=$(basename "$service_file")
                sudo cp "$service_file" "/etc/systemd/system/$service_name"
            fi
        done
        sudo systemctl daemon-reload
    fi

    # Write new version file
    log_info "Writing version metadata..."
    local commit_sha
    commit_sha=$(cat "$STAGING_DIR/.commit_sha")
    local branch
    branch=$(cat "$STAGING_DIR/.branch")

    local version="0.0.0"
    if [[ -f "$SOURCE_DIR/package.json" ]]; then
        version=$(jq -r '.version // "0.0.0"' "$SOURCE_DIR/package.json" 2>/dev/null || echo "0.0.0")
    fi

    # Get previous version
    local previous_version=""
    local previous_sha=""
    if [[ -f "$VERSION_FILE" ]]; then
        previous_version=$(jq -r '.version // ""' "$VERSION_FILE" 2>/dev/null || echo "")
        previous_sha=$(jq -r '.commit_sha // ""' "$VERSION_FILE" 2>/dev/null || echo "")
    fi

    cat > "$VERSION_FILE" <<EOF
{
  "schema_version": 1,
  "package": "water-controller",
  "version": "$version",
  "commit_sha": "$commit_sha",
  "commit_short": "${commit_sha:0:7}",
  "branch": "$branch",
  "tag": "",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "installed_by": "upgrade.sh",
  "previous_version": "$previous_version",
  "previous_sha": "$previous_sha"
}
EOF

    log_info "Upgrade applied"
    _log_write "INFO" "Upgrade applied: $previous_version -> $version"

    return 0
}

# =============================================================================
# PHASE 6: VALIDATE (Health Check)
# =============================================================================

phase_validate() {
    log_info "=== PHASE 6: VALIDATE ==="

    # Start services
    log_info "Starting services..."

    local services=(
        "$SERVICE_NAME"
    )

    for svc in "${services[@]}"; do
        if [[ -f "/etc/systemd/system/${svc}.service" ]]; then
            log_info "Starting ${svc}..."
            sudo systemctl start "${svc}.service" || {
                log_error "Failed to start ${svc}"
                return 1
            }
        fi
    done

    # Wait for service to become active
    log_info "Waiting for services to become active..."
    local waited=0
    while [[ $waited -lt $SERVICE_START_TIMEOUT ]]; do
        if systemctl is-active "${SERVICE_NAME}.service" &>/dev/null; then
            break
        fi
        sleep 1
        ((waited++))
    done

    if ! systemctl is-active "${SERVICE_NAME}.service" &>/dev/null; then
        log_error "Service failed to start within $SERVICE_START_TIMEOUT seconds"
        return 1
    fi

    # Health check
    log_info "Running health check..."
    local health_url="http://localhost:8000/health"
    local health_ok=false

    for ((i=0; i<$HEALTH_CHECK_TIMEOUT; i++)); do
        if curl -fsSL --connect-timeout 2 "$health_url" &>/dev/null; then
            health_ok=true
            break
        fi
        sleep 1
    done

    if [[ "$health_ok" != "true" ]]; then
        log_warn "Health endpoint not responding (service may still be starting)"
    else
        log_info "Health check passed"
    fi

    # Verify critical files
    log_info "Verifying installation..."

    local critical_files=(
        "$INSTALL_BASE/venv/bin/uvicorn"
        "$INSTALL_BASE/venv/bin/python3"
    )

    for file in "${critical_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            log_error "Missing critical file: $file"
            return 1
        fi
    done

    log_info ""
    log_info "======================================"
    log_info "UPGRADE COMPLETED SUCCESSFULLY!"
    log_info ""
    log_info "New version:  $(jq -r '.version' "$VERSION_FILE" 2>/dev/null)"
    log_info "Commit:       $(jq -r '.commit_short' "$VERSION_FILE" 2>/dev/null)"
    log_info "======================================"
    log_info ""

    _log_write "INFO" "Upgrade completed and validated"

    return 0
}

# =============================================================================
# Rollback
# =============================================================================

do_rollback() {
    log_error "Upgrade failed, initiating rollback..."

    # Find most recent rollback
    local latest_rollback
    latest_rollback=$(find "$ROLLBACK_DIR" -maxdepth 1 -mindepth 1 -type d | sort -r | head -n1)

    if [[ -z "$latest_rollback" ]] || [[ ! -d "$latest_rollback" ]]; then
        log_error "No rollback snapshot available!"
        return 1
    fi

    local rollback_name
    rollback_name=$(basename "$latest_rollback")
    log_info "Rolling back to: $rollback_name"

    # Stop services
    phase_stop || true

    # Restore directories
    local dirs=(
        "venv"
        "app"
        "web"
    )

    for dir in "${dirs[@]}"; do
        local src="$latest_rollback/$dir"
        local dst="$INSTALL_BASE/$dir"

        if [[ -d "$src" ]]; then
            log_info "Restoring: $dir"
            rm -rf "$dst"
            cp -a "$src" "$dst"
        fi
    done

    # Restore version and manifest
    [[ -f "$latest_rollback/.version" ]] && cp "$latest_rollback/.version" "$VERSION_FILE"
    [[ -f "$latest_rollback/.manifest" ]] && cp "$latest_rollback/.manifest" "$MANIFEST_FILE"

    # Restart services
    sudo systemctl daemon-reload
    sudo systemctl start "${SERVICE_NAME}.service" || true

    log_info "Rollback completed"
    _log_write "WARN" "Rolled back to: $rollback_name"

    return 0
}

# =============================================================================
# Main
# =============================================================================

show_help() {
    cat <<EOF
Water-Controller Upgrade Script v$UPGRADE_VERSION

USAGE:
    upgrade.sh [OPTIONS]

OPTIONS:
    --branch <name>     Target branch (default: $DEFAULT_BRANCH)
    --force             Force upgrade even if already current
    --dry-run           Show what would be done without making changes
    --help, -h          Show this help message
    --version           Show version information

DESCRIPTION:
    This script performs a git-based upgrade of Water-Controller with
    pre-flight version checking. The pre-flight check uses git ls-remote
    to compare local vs remote versions WITHOUT any disk writes.

    If the installation is already at the latest version, the script
    exits immediately with zero disk writes (important for SD card
    endurance on embedded systems).

PHASES:
    0. PRE-FLIGHT   Check if upgrade needed (zero disk writes)
    1. STAGE        Clone new version to /tmp
    2. ANALYZE      Diff manifests, count changes
    3. BACKUP       Create rollback snapshot
    4. STOP         Stop services gracefully
    5. APPLY        Copy files, update dependencies
    6. VALIDATE     Start services, health check

EXAMPLES:
    ./upgrade.sh                    # Standard upgrade
    ./upgrade.sh --dry-run          # Show what would change
    ./upgrade.sh --force            # Force even if current
    ./upgrade.sh --branch develop   # Upgrade to develop branch
EOF
}

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --branch)
                TARGET_BRANCH="$2"
                shift 2
                ;;
            --force)
                FORCE="true"
                shift
                ;;
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            --version)
                echo "Water-Controller Upgrade v$UPGRADE_VERSION"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Check root
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi

    # Initialize logging
    init_logging 2>/dev/null || true

    log_info "Water-Controller Upgrade v$UPGRADE_VERSION"
    log_info "Target branch: $TARGET_BRANCH"
    log_info ""

    _log_write "INFO" "=== Starting upgrade to $TARGET_BRANCH ==="

    # PHASE 0: Pre-flight (zero disk writes)
    phase_preflight
    local preflight_result=$?

    if [[ $preflight_result -eq 2 ]]; then
        # Already at latest version
        exit 0
    elif [[ $preflight_result -ne 0 ]]; then
        exit 1
    fi

    # PHASE 1: Stage
    phase_stage || {
        log_error "Staging failed"
        exit 1
    }

    # PHASE 2: Analyze
    phase_analyze
    local analyze_result=$?

    if [[ $analyze_result -eq 2 ]]; then
        # Dry run complete
        exit 0
    elif [[ $analyze_result -ne 0 ]]; then
        log_error "Analysis failed"
        exit 1
    fi

    # PHASE 3: Backup
    phase_backup || {
        log_error "Backup failed"
        exit 1
    }

    # PHASE 4: Stop
    phase_stop || {
        log_error "Failed to stop services"
        exit 1
    }

    # PHASE 5: Apply
    if ! phase_apply; then
        log_error "Apply failed, initiating rollback"
        do_rollback
        exit 1
    fi

    # PHASE 6: Validate
    if ! phase_validate; then
        log_error "Validation failed, initiating rollback"
        do_rollback
        exit 1
    fi

    exit 0
}

main "$@"
