<!--
  DOCUMENT CLASS: Development (Developer Reference)

  This document explains BUILD SYSTEM INTERNALS.
  Update when installation/upgrade scripts are modified.

  For user-facing installation guide, see: guides/INSTALL.md
-->

# Water-Controller Installation System Internals

This document provides technical details about the installation, upgrade, and version management infrastructure for Water-Controller. It is intended for developers maintaining or extending the installation system.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           bootstrap.sh                                    │
│                       (curl|bash entry point)                             │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                       │
│  │  install.sh │  │  upgrade.sh │  │  remove.sh  │                       │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                       │
│         │                │                │                               │
│         └────────────────┼────────────────┘                               │
│                          │                                                │
│                          ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                       scripts/lib/                                   │ │
│  ├─────────────────────────────────────────────────────────────────────┤ │
│  │  common.sh     │ Shared utilities, error handling                   │ │
│  │  detection.sh  │ System detection, prerequisites                    │ │
│  │  validation.sh │ Post-install verification                          │ │
│  │  build.sh      │ Source acquisition, Python/npm builds              │ │
│  │  service.sh    │ systemd service management                         │ │
│  │  version.sh    │ Pre-flight checks, manifest, rollback              │ │
│  │  install-files.sh │ File installation, permissions                  │ │
│  │  upgrade.sh    │ Upgrade-specific utilities                         │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

## Key Design Principles

### 1. SD Card Write Endurance

Embedded systems often use SD cards with limited write cycles. The installation system minimizes writes:

- **Pre-flight version check**: Uses `git ls-remote` (network-only) before any clone
- **Staging in /tmp**: Clone to tmpfs when possible, then atomic copy
- **Rollback pruning**: Only keep last N versions to limit disk usage

### 2. Idempotent Operations

Every step should be safe to run multiple times:

```bash
step_NNNN_description() {
    local STEP_ID="INST-NNNN"

    # GUARD: Skip if already done
    if [[ -f "/opt/water-controller/some-marker" ]]; then
        log_step_skip "$STEP_ID" "Already complete"
        return 0
    fi

    # VALIDATE: Check preconditions
    require_command "some-tool" || return 1
    require_file "/some/dependency" || return 1

    # EXECUTE: Do the work
    local TEMP_TARGET=$(mktemp -d)
    trap "rm -rf '$TEMP_TARGET'" RETURN
    do_work "$TEMP_TARGET" || return 1

    # Atomic move into place
    mv "$TEMP_TARGET/result" "/opt/water-controller/target"

    # VERIFY: Confirm postconditions
    verify_checksum "/opt/water-controller/target" "$EXPECTED" || return 1

    # RECORD: Update manifest
    manifest_add "/opt/water-controller/target" "$CHECKSUM"

    log_step_done "$STEP_ID"
    return 0
}
```

### 3. Fail-Safe with Rollback

The upgrade system maintains rollback snapshots:

```
/opt/water-controller/.rollback/
├── 20250115_100000/    # Oldest (will be pruned)
├── 20250115_120000/    # Previous
│   ├── venv/
│   ├── app/
│   ├── web/
│   ├── .version
│   └── .rollback_info
└── 20250116_080000/    # Most recent
```

## File Formats

### .version (JSON)

```json
{
  "schema_version": 1,
  "package": "water-controller",
  "version": "1.2.3",
  "commit_sha": "a1b2c3d4e5f6789...",
  "commit_short": "a1b2c3d",
  "branch": "main",
  "tag": "v1.2.3",
  "installed_at": "2025-01-15T10:30:00Z",
  "installed_by": "bootstrap.sh",
  "previous_version": "1.2.2",
  "previous_sha": "f6e5d4c3b2a1..."
}
```

**Fields:**
- `schema_version`: Format version for future compatibility
- `commit_sha`: Full Git commit hash for exact version identification
- `previous_*`: Enables rollback tracking and version history

### .manifest

```
# Water-Controller Installation Manifest
# Generated: 2025-01-15T10:30:00Z
# Format: <checksum> <size> <path>
#
a1b2c3d4... 12345 venv/bin/uvicorn
b2c3d4e5... 6789 app/main.py
c3d4e5f6... 4321 web/.next/build-manifest.json
```

**Purpose:**
- Track all installed files with SHA256 checksums
- Enable fast upgrade analysis (what changed?)
- Verify installation integrity

### .rollback_info

```
timestamp=20250115_100000
created_at=2025-01-15T10:00:00Z
version=1.2.2
commit_sha=f6e5d4c3b2a1...
reason=upgrade
```

## Module Reference

### detection.sh

System detection and prerequisite checking.

**Key Functions:**
```bash
detect_system        # OS, arch, RAM, storage info
classify_hardware    # Platform identification (Pi 4, x86_64, etc.)
check_prerequisites  # Validate system requirements
check_dependencies   # List missing packages
check_port_available # Port conflict detection
detect_existing_installation  # Find current install state
```

**Exit Codes:**
- 0: Prerequisites satisfied
- 2: Prerequisites failed

### version.sh

Version management and pre-flight checks.

**Key Functions:**
```bash
# Pre-flight (zero disk writes)
get_remote_ref <repo_url> <ref>  # git ls-remote wrapper
preflight_check [branch]          # Compare local vs remote

# Version file operations
read_version_field <field>
write_version_file <sha> <branch> [version] [tag]

# Manifest operations
generate_manifest [base_dir]
verify_manifest [manifest_file]
diff_manifests <old> <new>

# Rollback operations
create_rollback_snapshot
list_rollbacks
restore_rollback [snapshot]
prune_rollbacks
```

**Return Codes (preflight_check):**
- 0: Update available
- 1: Already at latest (no update needed)
- 2: Could not determine (network error)
- 3: No local installation

### build.sh

Source acquisition and build operations.

**Key Functions:**
```bash
acquire_source [--source path] [--branch name]
create_python_venv
build_python_backend
build_react_frontend
verify_build
apply_build_optimizations <platform>
```

### service.sh

systemd service management.

**Key Functions:**
```bash
generate_service_unit [platform] [workers]
generate_frontend_service_unit
install_service [platform] [workers]
enable_service
start_service
stop_service
check_service_health
```

### validation.sh

Post-installation verification.

**Key Functions:**
```bash
verify_install_complete    # Check all required files exist
verify_python_imports      # Test Python module imports
verify_service_running     # Confirm systemd service active
verify_health_endpoint     # HTTP health check
```

## Bootstrap Flow

```
bootstrap.sh
    │
    ├── detect_system_state()
    │   └── Returns: fresh | installed | corrupted
    │
    ├── validate_environment()
    │   ├── check_root()
    │   ├── check_required_tools()
    │   ├── check_network()
    │   └── check_disk_space()
    │
    ├── [For upgrade] preflight_version_check()
    │   └── git ls-remote (no disk writes)
    │   └── If same version: exit 0 immediately
    │
    ├── create_staging_dir()
    │   └── /tmp/water-controller-{action}-{timestamp}-{pid}/
    │
    ├── clone_to_staging()
    │   └── git clone --depth 1 --branch {branch}
    │
    └── Execute action script from staging
        ├── install: scripts/install.sh
        ├── upgrade: scripts/upgrade.sh
        └── remove:  scripts/remove.sh
```

## Upgrade Flow Detail

```
upgrade.sh
    │
    ├── PHASE 0: PRE-FLIGHT (zero disk writes)
    │   ├── Read /opt/water-controller/.version
    │   ├── git ls-remote (network only)
    │   └── Compare SHAs → exit if same
    │
    ├── PHASE 1: STAGE
    │   ├── Select temp dir (/tmp or /var/tmp based on space)
    │   ├── git clone --depth 1 to staging
    │   └── Store commit info
    │
    ├── PHASE 2: ANALYZE
    │   ├── Generate manifest for staged files
    │   ├── Compare with current manifest
    │   └── Count: new, modified, deleted, config
    │
    ├── PHASE 3: BACKUP
    │   ├── Create .rollback/{timestamp}/
    │   ├── Copy venv/, app/, web/
    │   ├── Copy .version, .manifest
    │   └── Prune old rollbacks (keep 2)
    │
    ├── PHASE 4: STOP
    │   ├── Stop water-controller services
    │   └── Wait for graceful shutdown
    │
    ├── PHASE 5: APPLY
    │   ├── Update Python dependencies
    │   ├── Copy updated source files
    │   ├── Rebuild frontend if needed
    │   ├── Update systemd services
    │   └── Write new .version file
    │
    └── PHASE 6: VALIDATE
        ├── Start services
        ├── Health check (HTTP /health)
        └── On failure: trigger rollback
```

## Configuration Handling

### Config File Classification

| Path Pattern | Classification | Upgrade Behavior |
|--------------|----------------|------------------|
| `etc/*.yaml` | User config | Preserve if modified |
| `etc/*.yaml.example` | Template | Always update |
| `etc/*.d/*` | Drop-in | Preserve |
| `app/**` | Application | Always update |
| `web/**` | Frontend | Always update |
| `venv/**` | Dependencies | Update via pip |

### Modified File Detection

```bash
# During manifest generation, compute config file hashes
original_hash=$(sha256sum /opt/water-controller/etc/config.yaml.example)
current_hash=$(sha256sum /opt/water-controller/etc/config.yaml)

if [[ "$original_hash" == "$current_hash" ]]; then
    # User hasn't modified - safe to replace
    CONFLICT_POLICY="replace"
else
    # User modified - preserve their version
    CONFLICT_POLICY="preserve"
fi
```

## Exit Codes

| Code | Meaning | Recovery |
|------|---------|----------|
| 0 | Success | - |
| 1 | General error | Check logs |
| 2 | Prerequisites failed | Install dependencies |
| 3 | Build failed | Check build logs |
| 4 | Service failed | Check systemd journal |
| 5 | Validation failed | Check health endpoint |

## Adding New Installation Steps

1. Create step function following the idempotent pattern:

```bash
# scripts/lib/my-module.sh

step_0150_configure_something() {
    local STEP_ID="INST-0150"
    local STEP_NAME="Configure something"

    log_step_start "$STEP_ID" "$STEP_NAME"

    # Guard clause
    if something_already_configured; then
        log_step_skip "$STEP_ID" "Already configured"
        return 0
    fi

    # Preconditions
    require_file "/some/dependency" || return 1

    # Action
    do_configuration || {
        log_step_fail "$STEP_ID" "Configuration failed"
        return 1
    }

    # Verification
    verify_configuration || return 1

    log_step_done "$STEP_ID"
    return 0
}
```

2. Register in install.sh:

```bash
# In main installation sequence
step_0150_configure_something || exit 1
```

3. Add to manifest tracking if files are created:

```bash
manifest_add "/path/to/created/file" "$(sha256sum ...)"
```

## Testing

### Unit Testing Steps

```bash
# Test individual step idempotency
./scripts/lib/my-module.sh --test-step 0150

# Run step twice, verify same result
step_0150_configure_something
step_0150_configure_something
# Should report "Already configured" second time
```

### Integration Testing

```bash
# Full install/upgrade/remove cycle
./test/integration/test-lifecycle.sh

# Test pre-flight check
./scripts/lib/version.sh --check main
echo $?  # 0=update, 1=current, 2=error
```

### Rollback Testing

```bash
# Create known-good state
sudo ./scripts/install.sh

# Create rollback snapshot
sudo ./scripts/lib/version.sh --create-rollback

# Break something
sudo rm -rf /opt/water-controller/venv

# Restore
sudo ./scripts/lib/version.sh --restore-rollback

# Verify
curl http://localhost:8000/health
```

## Debugging

### Enable Debug Output

```bash
DEBUG=1 sudo ./scripts/install.sh
```

### Log Locations

- Installation log: `/var/log/water-controller-install.log`
- Service logs: `journalctl -u water-controller`
- Application logs: `/var/log/water-controller/app.log`

### Common Debug Commands

```bash
# Check version module
./scripts/lib/version.sh --status

# Check detection
./scripts/lib/detection.sh --full

# Verify manifest
./scripts/lib/version.sh --verify-manifest

# Check service health
./scripts/lib/service.sh --health
```

## Future Improvements

### Planned Enhancements

1. **Differential Updates**: Use manifest to only transfer changed files
2. **Signature Verification**: GPG sign releases, verify before install
3. **Atomic Symlink Switch**: Install to versioned dirs, switch via symlink
4. **Containerized Builds**: Build in Docker for reproducibility
5. **OTA Updates**: Over-the-air updates for deployed systems

### Extension Points

- Add hooks in `scripts/hooks/` for custom pre/post actions
- Environment-specific configs in `scripts/env/`
- Platform-specific optimizations in `scripts/platform/`
