#!/bin/bash
# =============================================================================
# Water Treatment Controller - Version Management Module
# =============================================================================
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module provides version detection, comparison, and pre-flight
# version checking to minimize unnecessary disk writes during upgrades.
#
# Key features:
# - Pre-flight version check using git ls-remote (zero disk writes)
# - Version metadata file management (.version JSON)
# - Manifest file management (.manifest with file checksums)
# - Rollback tracking
#
# =============================================================================

# Prevent multiple sourcing
if [[ -n "$_WTC_VERSION_LOADED" ]]; then
    return 0
fi
_WTC_VERSION_LOADED=1

# Source detection module for logging functions
: "${SCRIPT_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
if [[ -f "$SCRIPT_DIR/detection.sh" ]]; then
    # shellcheck source=detection.sh
    source "$SCRIPT_DIR/detection.sh"
fi

# =============================================================================
# Constants
# =============================================================================

readonly VERSION_MODULE_VERSION="1.0.0"

# Paths
: "${INSTALL_BASE:=/opt/water-controller}"
readonly VERSION_FILE="${INSTALL_BASE}/.version"
readonly MANIFEST_FILE="${INSTALL_BASE}/.manifest"
readonly ROLLBACK_DIR="${INSTALL_BASE}/.rollback"
readonly VERSION_SCHEMA=1

# Repository
readonly DEFAULT_REPO_URL="https://github.com/mwilco03/Water-Controller.git"
readonly DEFAULT_BRANCH="main"

# Rollback retention
readonly ROLLBACK_KEEP_COUNT=2

# =============================================================================
# Version File Operations
# =============================================================================

# Read a field from the version file
# Usage: read_version_field <field_name>
# Returns: field value or empty string
read_version_field() {
    local field="$1"

    if [[ ! -f "$VERSION_FILE" ]]; then
        echo ""
        return 1
    fi

    if command -v jq &>/dev/null; then
        jq -r ".$field // \"\"" "$VERSION_FILE" 2>/dev/null
    else
        # Fallback: simple grep for JSON field
        grep -oP "\"$field\"\s*:\s*\"\K[^\"]+" "$VERSION_FILE" 2>/dev/null || echo ""
    fi
}

# Get installed version
get_installed_version() {
    read_version_field "version"
}

# Get installed commit SHA
get_installed_commit_sha() {
    read_version_field "commit_sha"
}

# Get installed branch
get_installed_branch() {
    read_version_field "branch"
}

# Get installation timestamp
get_install_timestamp() {
    read_version_field "installed_at"
}

# Get previous version info
get_previous_version() {
    read_version_field "previous_version"
}

# Get previous commit SHA
get_previous_sha() {
    read_version_field "previous_sha"
}

# Check if version file exists and is valid
is_version_file_valid() {
    if [[ ! -f "$VERSION_FILE" ]]; then
        return 1
    fi

    # Check schema version
    local schema
    schema=$(read_version_field "schema_version")

    if [[ -z "$schema" ]]; then
        return 1
    fi

    # Check required fields
    local commit_sha
    commit_sha=$(read_version_field "commit_sha")

    if [[ -z "$commit_sha" ]]; then
        return 1
    fi

    return 0
}

# =============================================================================
# Pre-Flight Version Check (Zero Disk Writes)
# =============================================================================

# Get remote ref SHA using git ls-remote
# This is a network-only operation with no local disk writes
# Usage: get_remote_ref <repo_url> <ref>
# Returns: SHA of the remote ref
get_remote_ref() {
    local repo_url="${1:-$DEFAULT_REPO_URL}"
    local ref="${2:-HEAD}"

    # Normalize ref
    case "$ref" in
        HEAD|main|master)
            ref="refs/heads/$ref"
            ;;
        v*)
            # Tag reference
            ref="refs/tags/$ref"
            ;;
        refs/*)
            # Already fully qualified
            ;;
        *)
            # Assume branch
            ref="refs/heads/$ref"
            ;;
    esac

    log_debug "Fetching remote ref: $ref from $repo_url"

    local result
    result=$(git ls-remote "$repo_url" "$ref" 2>/dev/null | awk '{print $1}' | head -n1)

    if [[ -z "$result" ]]; then
        log_debug "Could not fetch ref: $ref"
        return 1
    fi

    echo "$result"
    return 0
}

# Pre-flight version check
# Compares local installation against remote WITHOUT any disk writes
# Usage: preflight_check [branch] [repo_url]
# Returns:
#   0 - Update available
#   1 - Already at latest version (no update needed)
#   2 - Could not determine (network error, etc.)
#   3 - No local installation found
preflight_check() {
    local branch="${1:-$DEFAULT_BRANCH}"
    local repo_url="${2:-$DEFAULT_REPO_URL}"

    log_info "Running pre-flight version check..."

    # Check for local version file
    if ! is_version_file_valid; then
        log_debug "No valid version file found"
        return 3
    fi

    local local_sha
    local_sha=$(get_installed_commit_sha)

    if [[ -z "$local_sha" ]]; then
        log_warn "Could not read local commit SHA"
        return 3
    fi

    log_info "Local commit:  ${local_sha:0:12}"

    # Get remote SHA (network only, no disk writes)
    local remote_sha
    remote_sha=$(get_remote_ref "$repo_url" "$branch")

    if [[ -z "$remote_sha" ]]; then
        log_warn "Could not fetch remote version (network issue?)"
        return 2
    fi

    log_info "Remote commit: ${remote_sha:0:12}"

    # Compare
    if [[ "$local_sha" == "$remote_sha" ]]; then
        log_info "Already at latest version, no update needed"
        return 1
    fi

    log_info "Update available: ${local_sha:0:12} -> ${remote_sha:0:12}"
    return 0
}

# =============================================================================
# Version File Writing
# =============================================================================

# Write version metadata file
# Usage: write_version_file <commit_sha> <branch> [version] [tag]
write_version_file() {
    local commit_sha="$1"
    local branch="$2"
    local version="${3:-0.0.0}"
    local tag="${4:-}"

    log_info "Writing version file..."

    # Get previous version info
    local previous_version=""
    local previous_sha=""

    if is_version_file_valid; then
        previous_version=$(get_installed_version)
        previous_sha=$(get_installed_commit_sha)
        log_debug "Previous version: $previous_version ($previous_sha)"
    fi

    # Prepare JSON content
    local timestamp
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    local commit_short="${commit_sha:0:7}"

    # Create version file content
    local content
    content=$(cat <<EOF
{
  "schema_version": $VERSION_SCHEMA,
  "package": "water-controller",
  "version": "$version",
  "commit_sha": "$commit_sha",
  "commit_short": "$commit_short",
  "branch": "$branch",
  "tag": "$tag",
  "installed_at": "$timestamp",
  "installed_by": "install.sh",
  "previous_version": "$previous_version",
  "previous_sha": "$previous_sha"
}
EOF
)

    # Ensure directory exists
    mkdir -p "$(dirname "$VERSION_FILE")"

    # Write file
    echo "$content" > "$VERSION_FILE"

    if [[ $? -ne 0 ]]; then
        log_error "Failed to write version file: $VERSION_FILE"
        return 1
    fi

    # Set permissions
    chmod 644 "$VERSION_FILE"

    log_info "Version file written: $VERSION_FILE"
    _log_write "INFO" "Version file written: $version ($commit_short)"

    return 0
}

# =============================================================================
# Manifest Operations
# =============================================================================

# Generate manifest of installed files with checksums
# Usage: generate_manifest <base_dir> [output_file]
generate_manifest() {
    local base_dir="${1:-$INSTALL_BASE}"
    local output_file="${2:-$MANIFEST_FILE}"

    log_info "Generating file manifest..."

    if [[ ! -d "$base_dir" ]]; then
        log_error "Base directory does not exist: $base_dir"
        return 1
    fi

    # Create manifest header
    local timestamp
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    {
        echo "# Water-Controller Installation Manifest"
        echo "# Generated: $timestamp"
        echo "# Format: <checksum> <size> <path>"
        echo "#"

        # Find all files (excluding .rollback directory and .git)
        find "$base_dir" -type f \
            ! -path "*/.rollback/*" \
            ! -path "*/.git/*" \
            ! -name ".manifest" \
            -print0 2>/dev/null | \
        while IFS= read -r -d '' file; do
            local checksum size relpath

            # Calculate SHA256 checksum
            checksum=$(sha256sum "$file" 2>/dev/null | awk '{print $1}')

            # Get file size
            size=$(stat -c %s "$file" 2>/dev/null || echo "0")

            # Get relative path
            relpath="${file#$base_dir/}"

            echo "$checksum $size $relpath"
        done | sort -k3
    } > "$output_file"

    if [[ $? -ne 0 ]]; then
        log_error "Failed to write manifest file: $output_file"
        return 1
    fi

    local file_count
    file_count=$(grep -c "^[a-f0-9]" "$output_file" 2>/dev/null || echo "0")

    log_info "Manifest generated: $file_count files recorded"
    _log_write "INFO" "Manifest generated: $file_count files"

    return 0
}

# Read manifest into associative array
# Usage: read_manifest <manifest_file>
# Sets: _MANIFEST_CHECKSUMS (associative array)
declare -gA _MANIFEST_CHECKSUMS

read_manifest() {
    local manifest_file="${1:-$MANIFEST_FILE}"

    # Clear existing data
    _MANIFEST_CHECKSUMS=()

    if [[ ! -f "$manifest_file" ]]; then
        log_debug "Manifest file not found: $manifest_file"
        return 1
    fi

    while IFS=' ' read -r checksum size path; do
        # Skip comments and empty lines
        [[ "$checksum" =~ ^# ]] && continue
        [[ -z "$checksum" ]] && continue

        _MANIFEST_CHECKSUMS["$path"]="$checksum"
    done < "$manifest_file"

    local count=${#_MANIFEST_CHECKSUMS[@]}
    log_debug "Loaded $count entries from manifest"

    return 0
}

# Compare current files against manifest
# Usage: verify_manifest [manifest_file]
# Returns: 0 if all files match, 1 if differences found
verify_manifest() {
    local manifest_file="${1:-$MANIFEST_FILE}"

    log_info "Verifying files against manifest..."

    if ! read_manifest "$manifest_file"; then
        log_error "Could not read manifest file"
        return 1
    fi

    local mismatches=0
    local missing=0
    local verified=0

    for path in "${!_MANIFEST_CHECKSUMS[@]}"; do
        local expected_checksum="${_MANIFEST_CHECKSUMS[$path]}"
        local full_path="$INSTALL_BASE/$path"

        if [[ ! -f "$full_path" ]]; then
            log_warn "Missing file: $path"
            ((missing++))
            continue
        fi

        local actual_checksum
        actual_checksum=$(sha256sum "$full_path" 2>/dev/null | awk '{print $1}')

        if [[ "$actual_checksum" != "$expected_checksum" ]]; then
            log_warn "Checksum mismatch: $path"
            log_debug "  Expected: $expected_checksum"
            log_debug "  Actual:   $actual_checksum"
            ((mismatches++))
        else
            ((verified++))
        fi
    done

    log_info "Manifest verification: $verified verified, $missing missing, $mismatches modified"

    if [[ $missing -gt 0 ]] || [[ $mismatches -gt 0 ]]; then
        return 1
    fi

    return 0
}

# Compare two manifests and return differences
# Usage: diff_manifests <old_manifest> <new_manifest>
# Outputs: NEW|MODIFIED|DELETED <path> lines
diff_manifests() {
    local old_manifest="$1"
    local new_manifest="$2"

    declare -A old_files new_files

    # Read old manifest
    if [[ -f "$old_manifest" ]]; then
        while IFS=' ' read -r checksum size path; do
            [[ "$checksum" =~ ^# ]] && continue
            [[ -z "$checksum" ]] && continue
            old_files["$path"]="$checksum"
        done < "$old_manifest"
    fi

    # Read new manifest
    if [[ -f "$new_manifest" ]]; then
        while IFS=' ' read -r checksum size path; do
            [[ "$checksum" =~ ^# ]] && continue
            [[ -z "$checksum" ]] && continue
            new_files["$path"]="$checksum"
        done < "$new_manifest"
    fi

    # Find new and modified files
    for path in "${!new_files[@]}"; do
        if [[ -z "${old_files[$path]:-}" ]]; then
            echo "NEW $path"
        elif [[ "${old_files[$path]}" != "${new_files[$path]}" ]]; then
            echo "MODIFIED $path"
        fi
    done

    # Find deleted files
    for path in "${!old_files[@]}"; do
        if [[ -z "${new_files[$path]:-}" ]]; then
            echo "DELETED $path"
        fi
    done
}

# =============================================================================
# Rollback Management
# =============================================================================

# Create rollback snapshot
# Usage: create_rollback_snapshot
# Returns: path to rollback directory
create_rollback_snapshot() {
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local rollback_path="$ROLLBACK_DIR/$timestamp"

    log_info "Creating rollback snapshot..."

    # Create rollback directory
    mkdir -p "$rollback_path"

    # Copy critical directories
    local dirs_to_backup=(
        "bin"
        "lib"
        "venv"
        "app"
        "web"
    )

    for dir in "${dirs_to_backup[@]}"; do
        local src="$INSTALL_BASE/$dir"
        if [[ -d "$src" ]]; then
            log_debug "Backing up: $dir"
            cp -a "$src" "$rollback_path/" 2>/dev/null || true
        fi
    done

    # Copy version and manifest
    [[ -f "$VERSION_FILE" ]] && cp "$VERSION_FILE" "$rollback_path/.version"
    [[ -f "$MANIFEST_FILE" ]] && cp "$MANIFEST_FILE" "$rollback_path/.manifest"

    # Record rollback metadata
    cat > "$rollback_path/.rollback_info" <<EOF
timestamp=$timestamp
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
version=$(get_installed_version)
commit_sha=$(get_installed_commit_sha)
EOF

    log_info "Rollback snapshot created: $rollback_path"
    _log_write "INFO" "Rollback snapshot created: $timestamp"

    # Prune old rollbacks
    prune_rollbacks

    echo "$rollback_path"
    return 0
}

# Prune old rollback snapshots (keep last N)
prune_rollbacks() {
    log_debug "Pruning old rollback snapshots..."

    if [[ ! -d "$ROLLBACK_DIR" ]]; then
        return 0
    fi

    # Get list of rollback directories sorted by name (oldest first)
    local rollbacks=()
    while IFS= read -r dir; do
        rollbacks+=("$dir")
    done < <(find "$ROLLBACK_DIR" -maxdepth 1 -mindepth 1 -type d | sort)

    local count=${#rollbacks[@]}
    local to_remove=$((count - ROLLBACK_KEEP_COUNT))

    if [[ $to_remove -gt 0 ]]; then
        log_info "Pruning $to_remove old rollback snapshot(s)..."

        for ((i=0; i<to_remove; i++)); do
            local old_rollback="${rollbacks[$i]}"
            log_debug "Removing: $old_rollback"
            rm -rf "$old_rollback"
        done
    fi

    return 0
}

# List available rollbacks
list_rollbacks() {
    if [[ ! -d "$ROLLBACK_DIR" ]]; then
        echo "No rollback snapshots available"
        return 0
    fi

    echo "Available rollback snapshots:"
    echo "-----------------------------"

    find "$ROLLBACK_DIR" -maxdepth 1 -mindepth 1 -type d | sort -r | while read -r dir; do
        local name
        name=$(basename "$dir")

        local info_file="$dir/.rollback_info"
        if [[ -f "$info_file" ]]; then
            local version commit_sha created_at
            version=$(grep "^version=" "$info_file" | cut -d= -f2)
            commit_sha=$(grep "^commit_sha=" "$info_file" | cut -d= -f2)
            created_at=$(grep "^created_at=" "$info_file" | cut -d= -f2)
            echo "  $name: v$version (${commit_sha:0:7}) - $created_at"
        else
            echo "  $name: (no info available)"
        fi
    done

    return 0
}

# Restore from rollback snapshot
# Usage: restore_rollback [snapshot_name]
restore_rollback() {
    local snapshot="${1:-}"

    log_info "Restoring from rollback snapshot..."

    if [[ ! -d "$ROLLBACK_DIR" ]]; then
        log_error "No rollback directory found"
        return 1
    fi

    local rollback_path

    if [[ -z "$snapshot" ]]; then
        # Use most recent snapshot
        rollback_path=$(find "$ROLLBACK_DIR" -maxdepth 1 -mindepth 1 -type d | sort -r | head -n1)
    else
        rollback_path="$ROLLBACK_DIR/$snapshot"
    fi

    if [[ ! -d "$rollback_path" ]]; then
        log_error "Rollback snapshot not found: $rollback_path"
        return 1
    fi

    local snapshot_name
    snapshot_name=$(basename "$rollback_path")
    log_info "Restoring from: $snapshot_name"

    # Restore directories
    local dirs=(
        "bin"
        "lib"
        "venv"
        "app"
        "web"
    )

    for dir in "${dirs[@]}"; do
        local src="$rollback_path/$dir"
        local dst="$INSTALL_BASE/$dir"

        if [[ -d "$src" ]]; then
            log_debug "Restoring: $dir"
            rm -rf "$dst" 2>/dev/null || true
            cp -a "$src" "$dst"
        fi
    done

    # Restore version and manifest
    [[ -f "$rollback_path/.version" ]] && cp "$rollback_path/.version" "$VERSION_FILE"
    [[ -f "$rollback_path/.manifest" ]] && cp "$rollback_path/.manifest" "$MANIFEST_FILE"

    log_info "Rollback restore completed: $snapshot_name"
    _log_write "INFO" "Restored from rollback: $snapshot_name"

    return 0
}

# =============================================================================
# Version Comparison Utilities
# =============================================================================

# Compare semantic versions
# Usage: compare_versions <version1> <version2>
# Returns: -1 if v1 < v2, 0 if equal, 1 if v1 > v2
compare_versions() {
    local v1="$1"
    local v2="$2"

    # Remove 'v' prefix if present
    v1="${v1#v}"
    v2="${v2#v}"

    # Split into components
    IFS='.' read -ra v1_parts <<< "$v1"
    IFS='.' read -ra v2_parts <<< "$v2"

    # Compare each component
    local max_len=${#v1_parts[@]}
    [[ ${#v2_parts[@]} -gt $max_len ]] && max_len=${#v2_parts[@]}

    for ((i=0; i<max_len; i++)); do
        local p1="${v1_parts[$i]:-0}"
        local p2="${v2_parts[$i]:-0}"

        # Remove non-numeric suffixes for comparison
        p1="${p1%%[^0-9]*}"
        p2="${p2%%[^0-9]*}"

        if [[ "$p1" -lt "$p2" ]]; then
            echo "-1"
            return 0
        elif [[ "$p1" -gt "$p2" ]]; then
            echo "1"
            return 0
        fi
    done

    echo "0"
    return 0
}

# Check if update is available (wrapper for preflight_check)
is_update_available() {
    local branch="${1:-$DEFAULT_BRANCH}"

    preflight_check "$branch"
    local result=$?

    [[ $result -eq 0 ]]
}

# =============================================================================
# Main Entry Point (when run directly)
# =============================================================================

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Initialize logging
    init_logging || {
        echo "[WARN] Logging initialization failed" >&2
    }

    case "${1:-}" in
        --check)
            preflight_check "${2:-main}"
            exit $?
            ;;
        --status)
            echo "Version Module v$VERSION_MODULE_VERSION"
            echo ""
            if is_version_file_valid; then
                echo "Installed Version:  $(get_installed_version)"
                echo "Installed Commit:   $(get_installed_commit_sha)"
                echo "Installed Branch:   $(get_installed_branch)"
                echo "Installed At:       $(get_install_timestamp)"
                echo ""
                echo "Previous Version:   $(get_previous_version)"
                echo "Previous Commit:    $(get_previous_sha)"
            else
                echo "No valid installation found"
            fi
            ;;
        --generate-manifest)
            generate_manifest "${2:-$INSTALL_BASE}"
            exit $?
            ;;
        --verify-manifest)
            verify_manifest "${2:-$MANIFEST_FILE}"
            exit $?
            ;;
        --list-rollbacks)
            list_rollbacks
            ;;
        --create-rollback)
            create_rollback_snapshot
            exit $?
            ;;
        --restore-rollback)
            restore_rollback "${2:-}"
            exit $?
            ;;
        --help|-h)
            echo "Water-Controller Version Module v$VERSION_MODULE_VERSION"
            echo ""
            echo "Usage: $0 [OPTION]"
            echo ""
            echo "Options:"
            echo "  --check [branch]      Run pre-flight version check"
            echo "  --status              Show installed version info"
            echo "  --generate-manifest   Generate file manifest"
            echo "  --verify-manifest     Verify files against manifest"
            echo "  --list-rollbacks      List available rollback snapshots"
            echo "  --create-rollback     Create a rollback snapshot"
            echo "  --restore-rollback    Restore from rollback snapshot"
            echo "  --help, -h            Show this help message"
            echo ""
            echo "Paths:"
            echo "  Version file:  $VERSION_FILE"
            echo "  Manifest file: $MANIFEST_FILE"
            echo "  Rollback dir:  $ROLLBACK_DIR"
            ;;
        *)
            echo "Usage: $0 [--check|--status|--generate-manifest|--verify-manifest|--list-rollbacks|--create-rollback|--restore-rollback|--help]" >&2
            exit 1
            ;;
    esac
fi
