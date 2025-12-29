# Water-Controller Upgrade Guide

This guide covers upgrading Water-Controller to newer versions. The upgrade system is designed with SD card endurance in mind, using pre-flight version checking to avoid unnecessary disk writes.

## Quick Upgrade

```bash
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | bash
```

The bootstrap script automatically detects that Water-Controller is already installed and runs an upgrade instead of a fresh installation.

## How Upgrades Work

### Pre-Flight Version Check (Zero Disk Writes)

Before any disk writes occur, the upgrade script:

1. Reads the installed version from `/opt/water-controller/.version`
2. Uses `git ls-remote` to fetch the remote commit SHA (network-only, no local writes)
3. Compares the two SHAs

If the versions match, the upgrade exits immediately **without writing anything to disk**. This is critical for SD card longevity on embedded systems like Raspberry Pi.

```
┌─────────────────────────────────────────────────────────────────┐
│              PRE-FLIGHT VERSION CHECK                            │
│         (Zero disk writes if already current)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Read local commit SHA from .version file                    │
│  2. Run: git ls-remote https://github.com/.../Water-Controller  │
│  3. Compare SHAs:                                               │
│     - MATCH: "Already current", exit 0 (no writes)              │
│     - DIFFER: Proceed to upgrade                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Upgrade Phases

When an upgrade is needed, the following phases execute:

| Phase | Name | Description |
|-------|------|-------------|
| 0 | Pre-Flight | Check if upgrade needed (zero writes) |
| 1 | Stage | Clone new version to /tmp |
| 2 | Analyze | Diff manifests, count changes |
| 3 | Backup | Create rollback snapshot |
| 4 | Stop | Stop services gracefully |
| 5 | Apply | Copy files, update dependencies |
| 6 | Validate | Start services, health check |

### Automatic Rollback

If the upgrade fails during validation (Phase 6), the system automatically rolls back to the previous version using the snapshot created in Phase 3.

## Upgrade Methods

### Method 1: Bootstrap (Recommended)

```bash
# Standard upgrade
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | bash

# With explicit upgrade action
curl -fsSL .../bootstrap.sh | bash -s -- upgrade

# Dry run (see what would change)
curl -fsSL .../bootstrap.sh | bash -s -- upgrade --dry-run

# Force upgrade even if already current
curl -fsSL .../bootstrap.sh | bash -s -- upgrade --force

# Upgrade from a specific branch
curl -fsSL .../bootstrap.sh | bash -s -- upgrade --branch develop
```

### Method 2: Direct Script

If you have the repository checked out:

```bash
cd /opt/water-controller
sudo ./scripts/upgrade.sh

# Or with options
sudo ./scripts/upgrade.sh --dry-run
sudo ./scripts/upgrade.sh --force
sudo ./scripts/upgrade.sh --branch develop
```

### Method 3: Manual Upgrade

For complete control over the upgrade process:

```bash
# 1. Clone new version to staging
git clone --depth 1 https://github.com/mwilco03/Water-Controller.git /tmp/water-controller-upgrade

# 2. Stop services
sudo systemctl stop water-controller

# 3. Backup current installation
sudo cp -a /opt/water-controller /opt/water-controller.backup

# 4. Copy new files
sudo cp -r /tmp/water-controller-upgrade/* /opt/water-controller/

# 5. Update dependencies
/opt/water-controller/venv/bin/pip install -r /opt/water-controller/app/requirements.txt

# 6. Rebuild frontend
cd /opt/water-controller/web && npm ci && npm run build

# 7. Start services
sudo systemctl start water-controller

# 8. Verify
curl http://localhost:8000/health

# 9. Cleanup
rm -rf /tmp/water-controller-upgrade
```

## Version Information

### Check Current Version

```bash
# View version file
cat /opt/water-controller/.version

# Or use the version module
/opt/water-controller/scripts/lib/version.sh --status
```

Example output:

```json
{
  "schema_version": 1,
  "package": "water-controller",
  "version": "1.2.3",
  "commit_sha": "a1b2c3d4e5f6...",
  "commit_short": "a1b2c3d",
  "branch": "main",
  "installed_at": "2025-01-15T10:30:00Z",
  "previous_version": "1.2.2",
  "previous_sha": "f6e5d4c3b2a1..."
}
```

### Check for Updates

```bash
# Pre-flight check only (no upgrade, just check)
/opt/water-controller/scripts/lib/version.sh --check

# Or via upgrade script
sudo ./scripts/upgrade.sh --dry-run
```

## Rollback

### Automatic Rollback

If an upgrade fails during validation, the system automatically rolls back. You'll see:

```
[ERROR] Validation failed, initiating rollback
[INFO] Rolling back to: 20250115_103000
[INFO] Rollback completed
```

### Manual Rollback

To manually rollback to a previous version:

```bash
# List available rollback snapshots
/opt/water-controller/scripts/lib/version.sh --list-rollbacks

# Restore from most recent rollback
sudo /opt/water-controller/scripts/lib/version.sh --restore-rollback

# Restore from specific snapshot
sudo /opt/water-controller/scripts/lib/version.sh --restore-rollback 20250115_103000
```

### Rollback Retention

By default, the last 2 successful upgrades are kept. Older rollbacks are automatically pruned to save disk space.

## Configuration Handling

### Preserved Files

User-modified configuration files are preserved during upgrades:

- `/etc/water-controller/config.yaml` (if modified)
- `/etc/water-controller/environment` (if modified)
- `/var/lib/water-controller/*` (all data)

### Updated Files

Template and example files are updated:

- `/etc/water-controller/config.yaml.example`
- Systemd unit files (if changed in new version)
- Application code

### Conflict Resolution

If you've modified a file that the upgrade also changes:

1. Your modified version is preserved
2. The new template is installed as `.example`
3. A message shows what changed

Example:

```
[WARN] Config conflict: config.yaml
[INFO] Your version preserved, new template at config.yaml.example
[INFO] Review changes: diff /etc/water-controller/config.yaml{,.example}
```

## Upgrade Best Practices

### Before Upgrading

1. **Check current status**:
   ```bash
   sudo systemctl status water-controller
   ```

2. **Review what will change**:
   ```bash
   curl -fsSL .../bootstrap.sh | bash -s -- upgrade --dry-run
   ```

3. **Backup critical data** (optional, upgrade creates automatic backup):
   ```bash
   sudo cp -a /var/lib/water-controller /var/backups/water-controller-$(date +%Y%m%d)
   ```

### After Upgrading

1. **Verify services are running**:
   ```bash
   sudo systemctl status water-controller
   ```

2. **Check health endpoint**:
   ```bash
   curl http://localhost:8000/health
   ```

3. **Test HMI access**:
   ```bash
   curl -s http://localhost:8080 | head
   ```

4. **Review logs for errors**:
   ```bash
   journalctl -u water-controller --since "5 minutes ago"
   ```

## Troubleshooting

### Upgrade Gets Stuck

```bash
# Check for running processes
ps aux | grep water-controller

# Force kill if needed
sudo systemctl kill water-controller

# Try upgrade again
sudo ./scripts/upgrade.sh --force
```

### Rollback Failed

```bash
# Manual recovery from backup
sudo systemctl stop water-controller
sudo rm -rf /opt/water-controller
sudo cp -a /opt/water-controller/.rollback/LATEST/* /opt/water-controller/
sudo systemctl start water-controller
```

### Version File Missing

If the `.version` file is missing or corrupted:

```bash
# Force upgrade (bypasses version check)
sudo ./scripts/upgrade.sh --force
```

### Pre-Flight Check Always Fails

```bash
# Check network connectivity
git ls-remote https://github.com/mwilco03/Water-Controller.git HEAD

# If network issue, use --force
sudo ./scripts/upgrade.sh --force
```

## Scheduled Updates

For automated updates (use with caution in production):

```bash
# Create update script
cat > /usr/local/bin/update-water-controller <<'EOF'
#!/bin/bash
/opt/water-controller/scripts/upgrade.sh 2>&1 | logger -t water-controller-update
EOF
chmod +x /usr/local/bin/update-water-controller

# Add to cron (weekly Sunday 3am)
echo "0 3 * * 0 root /usr/local/bin/update-water-controller" | sudo tee /etc/cron.d/water-controller-update
```

## Related Documentation

- [Installation Guide](INSTALL.md) - Fresh installation
- [Internals](INTERNALS.md) - Technical details of the installation system
- [ADR-001](ADR-001-SYSTEM-READINESS-GATES.md) - System readiness design decisions
