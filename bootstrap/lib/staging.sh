#!/bin/bash
# =============================================================================
# Water-Controller Bootstrap - Staging and Version Functions
# =============================================================================
# Staging directory management, version checking, checksums, and backups.
# Depends on: constants.sh, logging.sh, helpers.sh

# Prevent double-sourcing
[[ -n "${_WTC_STAGING_LOADED:-}" ]] && return 0
_WTC_STAGING_LOADED=1

# =============================================================================
# Pre-Flight Version Check (Zero Disk Writes)
# =============================================================================

# Get remote ref SHA using git ls-remote (no disk writes)
# This is the preferred method for version checking
get_remote_sha() {
    local branch="${1:-main}"
    local ref="refs/heads/$branch"

    # Handle tag references
    if [[ "$branch" == v* ]]; then
        ref="refs/tags/$branch"
    fi

    git ls-remote "$REPO_URL" "$ref" 2>/dev/null | awk '{print $1}'
}

# Pre-flight check: determine if upgrade is needed
# Returns: 0 if upgrade needed, 1 if already current, 2 on error
preflight_version_check() {
    local target_branch="${1:-main}"

    log_step "Running pre-flight version check (no disk writes)..."

    local local_sha
    local remote_sha

    # Get installed version
    local_sha=$(get_installed_sha)
    if [[ -z "$local_sha" ]]; then
        log_info "No version file found, treating as fresh install"
        return 0
    fi

    log_info "Installed commit: ${local_sha:0:12}"

    # Get remote version using git ls-remote (no clone needed)
    remote_sha=$(get_remote_sha "$target_branch")
    if [[ -z "$remote_sha" ]]; then
        log_error "Could not fetch remote version - network error or invalid branch"
        return 2
    fi

    log_info "Remote commit:    ${remote_sha:0:12}"

    # Compare
    if [[ "$local_sha" == "$remote_sha" ]]; then
        log_info "Already at latest version (${remote_sha:0:12}), nothing to do"
        return 1
    fi

    log_info "Update available: ${local_sha:0:12} -> ${remote_sha:0:12}"
    return 0
}

# =============================================================================
# Staging Directory Functions
# =============================================================================

# Create staging directory
create_staging_dir() {
    local action="${1:-install}"
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)

    # Compare /tmp and /var/tmp space, use the one with more available space
    local tmp_space var_tmp_space tmp_base
    tmp_space=$(df -m /tmp 2>/dev/null | awk 'NR==2 {print $4}') || tmp_space=0
    var_tmp_space=$(df -m /var/tmp 2>/dev/null | awk 'NR==2 {print $4}') || var_tmp_space=0

    # Default to /tmp, but switch to /var/tmp if it has more space or /tmp is low
    if [[ "${var_tmp_space:-0}" -gt "${tmp_space:-0}" ]] || [[ "${tmp_space:-0}" -lt 1024 ]]; then
        if [[ "${var_tmp_space:-0}" -ge 512 ]]; then
            tmp_base="/var/tmp"
            log_debug "Using /var/tmp (${var_tmp_space}MB) instead of /tmp (${tmp_space}MB)"
        else
            tmp_base="/tmp"
            log_warn "Both /tmp (${tmp_space}MB) and /var/tmp (${var_tmp_space}MB) have low space"
        fi
    else
        tmp_base="/tmp"
    fi

    local staging_dir="${tmp_base}/water-controller-${action}-${timestamp}-$$"
    mkdir -p "$staging_dir"
    echo "$staging_dir"
}

# Clone repository to staging
clone_to_staging() {
    local staging_dir="$1"
    local branch="${2:-main}"

    log_step "Cloning repository to staging..."

    local clone_output
    local clone_result

    # Capture both stdout and stderr, preserve exit code
    clone_output=$(git clone --depth 1 --branch "$branch" "$REPO_URL" "$staging_dir/repo" 2>&1) || clone_result=$?

    if [[ ${clone_result:-0} -ne 0 ]]; then
        log_error "Failed to clone repository"
        log_error "Git output: $clone_output"
        return 1
    fi

    log_debug "Clone output: $clone_output"

    # Verify clone integrity
    if [[ ! -d "$staging_dir/repo/.git" ]]; then
        log_error "Clone verification failed: .git directory missing"
        return 1
    fi

    # Get commit info
    local commit_sha
    commit_sha=$(cd "$staging_dir/repo" && git rev-parse HEAD)
    local commit_short="${commit_sha:0:7}"

    log_info "Cloned successfully: $commit_short"

    # Store commit info for later
    echo "$commit_sha" > "$staging_dir/.commit_sha"
    echo "$branch" > "$staging_dir/.branch"

    return 0
}

# Cleanup staging directory (legacy - prefer register_cleanup)
cleanup_staging() {
    local staging_dir="$1"

    if [[ -n "$staging_dir" ]] && [[ -d "$staging_dir" ]]; then
        log_info "Cleaning up staging directory..."
        rm -rf "$staging_dir"
    fi
}

# =============================================================================
# Checksum Verification
# =============================================================================

# Verify repository checksum if SHA256SUMS file exists
verify_checksum() {
    local staging_dir="$1"
    local branch="${2:-main}"

    local checksum_file="$staging_dir/repo/$CHECKSUM_FILE"

    if [[ ! -f "$checksum_file" ]]; then
        log_debug "No checksum file found at $checksum_file, skipping verification"
        return 0
    fi

    log_step "Verifying repository checksum..."

    # Verify the checksum file itself hasn't been tampered with
    # by checking if critical files match their checksums
    local verify_dir="$staging_dir/repo"

    if ! command -v sha256sum &>/dev/null; then
        log_warn "sha256sum not available, skipping checksum verification"
        return 0
    fi

    # Discovery: Verify repo directory and checksum file exist
    if [[ ! -d "$verify_dir" ]]; then
        log_warn "Verification directory not found: $verify_dir"
        return 0  # Non-fatal, continue without verification
    fi
    if [[ ! -f "$verify_dir/$CHECKSUM_FILE" ]]; then
        log_debug "No checksum file at: $verify_dir/$CHECKSUM_FILE"
        return 0  # Non-fatal, continue without verification
    fi

    # Change to repo directory and verify
    (
        cd "$verify_dir" || { echo "ERROR: Cannot access $verify_dir" >&2; exit 1; }
        if sha256sum --check --quiet "$CHECKSUM_FILE" 2>/dev/null; then
            log_info "Checksum verification passed"
            exit 0
        else
            log_warn "Some checksums did not match (files may have changed)"
            exit 1
        fi
    )

    return $?
}

# =============================================================================
# Backup Functions
# =============================================================================

# Create a backup of current installation
create_backup() {
    local backup_reason="${1:-backup}"
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)

    local backup_path="${BACKUP_DIR}/${backup_reason}-${timestamp}"

    log_step "Creating backup..."

    # Ensure backup directory exists
    run_privileged mkdir -p "$BACKUP_DIR" || {
        log_error "Failed to create backup directory"
        return 1
    }

    # Copy installation directory
    if [[ -d "$INSTALL_DIR" ]]; then
        run_privileged cp -a "$INSTALL_DIR" "$backup_path" || {
            log_error "Failed to backup installation directory"
            return 1
        }

        # Also backup version file path
        echo "$INSTALL_DIR" | run_privileged tee "$backup_path/.original_path" >/dev/null

        log_info "Backup created: $backup_path"
        echo "$backup_path"
        return 0
    else
        log_warn "No installation directory to backup"
        return 1
    fi
}

# Clean up old backups, keeping the most recent N
cleanup_old_backups() {
    local keep_count="${1:-3}"

    if [[ ! -d "$BACKUP_DIR" ]]; then
        return 0
    fi

    log_debug "Cleaning up old backups (keeping $keep_count most recent)"

    # Find and remove old backups
    local backup_count
    backup_count=$(find "$BACKUP_DIR" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)

    if [[ "$backup_count" -le "$keep_count" ]]; then
        log_debug "Only $backup_count backups exist, nothing to clean"
        return 0
    fi

    # Remove oldest backups
    find "$BACKUP_DIR" -maxdepth 1 -mindepth 1 -type d -printf '%T@ %p\n' 2>/dev/null | \
        sort -n | \
        head -n -"$keep_count" | \
        cut -d' ' -f2- | \
        while read -r old_backup; do
            log_debug "Removing old backup: $old_backup"
            run_privileged rm -rf "$old_backup"
        done
}

# =============================================================================
# Version File Functions
# =============================================================================

# Extract version from JSON file without jq
# Handles escaped quotes and multiline properly
extract_json_value() {
    local file="$1"
    local key="$2"

    if command -v jq &>/dev/null; then
        jq -r ".$key // \"\"" "$file" 2>/dev/null
        return
    fi

    # Use Python if available (more reliable than grep for JSON)
    if command -v python3 &>/dev/null; then
        python3 -c "import json,sys; d=json.load(open('$file')); print(d.get('$key',''))" 2>/dev/null
        return
    fi

    if command -v python &>/dev/null; then
        python -c "import json,sys; d=json.load(open('$file')); print(d.get('$key',''))" 2>/dev/null
        return
    fi

    # Fallback to grep - handles simple cases
    # Use sed to extract value, handling potential escaped chars
    grep -o "\"$key\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$file" 2>/dev/null | \
        sed 's/.*:[[:space:]]*"\([^"]*\)"/\1/' | \
        head -1
}

# Write version metadata file
write_version_file() {
    local staging_dir="$1"

    local commit_sha=""
    local branch=""
    local version=""
    local tag=""

    if [[ -f "$staging_dir/.commit_sha" ]]; then
        commit_sha=$(cat "$staging_dir/.commit_sha")
    fi

    if [[ -f "$staging_dir/.branch" ]]; then
        branch=$(cat "$staging_dir/.branch")
    fi

    # Try to get version from package.json or pyproject.toml
    if [[ -f "$staging_dir/repo/package.json" ]]; then
        version=$(extract_json_value "$staging_dir/repo/package.json" "version")
        version="${version:-0.0.0}"
    fi

    # Get previous version info if exists
    local previous_version=""
    local previous_sha=""
    if [[ -f "$VERSION_FILE" ]]; then
        previous_version=$(extract_json_value "$VERSION_FILE" "version")
        previous_sha=$(extract_json_value "$VERSION_FILE" "commit_sha")
    fi

    # Write version file
    local version_content
    version_content=$(cat <<EOF
{
  "schema_version": 1,
  "package": "water-controller",
  "version": "${version:-0.0.0}",
  "commit_sha": "$commit_sha",
  "commit_short": "${commit_sha:0:7}",
  "branch": "$branch",
  "tag": "$tag",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "installed_by": "bootstrap.sh",
  "bootstrap_version": "$BOOTSTRAP_VERSION",
  "previous_version": "$previous_version",
  "previous_sha": "$previous_sha"
}
EOF
)

    echo "$version_content" | run_privileged tee "$VERSION_FILE" > /dev/null

    log_info "Version file written: $VERSION_FILE"
}
