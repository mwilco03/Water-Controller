# Water Controller Field Upgrade Guide

This guide provides procedures for field technicians performing upgrades on Water Controller installations.

## Table of Contents

1. [Pre-Upgrade Checklist](#pre-upgrade-checklist)
2. [Upgrade Modes](#upgrade-modes)
3. [Standard Upgrade Procedure](#standard-upgrade-procedure)
4. [Unattended Upgrade](#unattended-upgrade)
5. [Canary Upgrade](#canary-upgrade)
6. [Staged Upgrade](#staged-upgrade)
7. [Rollback Procedures](#rollback-procedures)
8. [Uninstallation](#uninstallation)
9. [Troubleshooting](#troubleshooting)

---

## Pre-Upgrade Checklist

Before performing any upgrade, verify:

- [ ] SSH access to the device is working
- [ ] Current version is documented
- [ ] Backup of configuration exists
- [ ] At least 512MB free disk space
- [ ] No critical operations in progress
- [ ] Maintenance window scheduled (expect 3-5 minutes downtime)

### Check Current Version

```bash
cat /opt/water-controller/version.txt
```

### Check System Health

```bash
cd /path/to/Water-Controller/scripts
./lib/upgrade.sh health-check
```

### Check Disk Space

```bash
./lib/upgrade.sh disk-check
```

---

## Upgrade Modes

| Mode | Flag | Use Case |
|------|------|----------|
| Interactive | `--upgrade` | Standard upgrade with confirmations |
| Unattended | `--upgrade --unattended` | Automated deployments, CI/CD |
| Canary | `--upgrade --canary` | Production with extended testing |
| Staged | `--upgrade --staged` | Careful step-by-step upgrade |

---

## Standard Upgrade Procedure

The standard interactive upgrade prompts for confirmation at key points.

### Step 1: Navigate to Installation Scripts

```bash
cd /path/to/Water-Controller/scripts
```

### Step 2: Run Upgrade

```bash
sudo ./install.sh --upgrade
```

### Step 3: Monitor Progress

The upgrade will:
1. Run pre-upgrade health check
2. Verify disk space
3. Create rollback point
4. Stop the service
5. Install updates (dependencies, P-Net, build, files)
6. Start the service
7. Run post-upgrade validation

### Step 4: Verify Success

```bash
# Check service status
sudo systemctl status water-controller

# Check API health
curl http://localhost:8000/api/health

# Check logs for errors
sudo journalctl -u water-controller -n 50
```

---

## Unattended Upgrade

For automated deployments with no user interaction.

```bash
sudo ./install.sh --upgrade --unattended
```

### Behavior

- No prompts - fails immediately on any issue
- Requires successful health check
- Requires rollback point creation
- Auto-rollback on any failure
- Auto-rollback if post-upgrade validation fails

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Failure (rollback attempted) |

### Example: CI/CD Integration

```bash
#!/bin/bash
set -e

cd /opt/water-controller-source/scripts

if sudo ./install.sh --upgrade --unattended; then
    echo "Upgrade successful"
    exit 0
else
    echo "Upgrade failed - system rolled back"
    exit 1
fi
```

---

## Canary Upgrade

Extended testing after upgrade with automatic rollback if tests fail.

```bash
sudo ./install.sh --upgrade --canary
```

### Behavior

After standard upgrade completes:
1. Tests API endpoints
2. Tests PROFINET connectivity
3. Monitors service stability for 60 seconds
4. Auto-rollback if any test fails

### Use Cases

- Production upgrades where reliability is critical
- First deployment of a new version
- Systems with strict uptime requirements

---

## Staged Upgrade

Step-by-step upgrade with confirmation at each stage.

```bash
sudo ./install.sh --upgrade --staged
```

### Behavior

Pauses and prompts before:
- Stopping the service
- System detection
- Dependency installation
- P-Net installation
- Source build
- File installation
- Service configuration
- Network/storage configuration
- Service startup
- Validation

### Use Cases

- Debugging upgrade issues
- Training new technicians
- First-time upgrades on new hardware

---

## Rollback Procedures

### Automatic Rollback

Rollback happens automatically when:
- Unattended mode encounters any failure
- Canary mode tests fail
- Any upgrade step fails

### Manual Rollback

#### List Available Rollback Points

```bash
ls -la /var/backups/water-controller/rollback/
```

#### Perform Rollback

```bash
# Using the install script
sudo ./install.sh --rollback <rollback-point-name>

# Or using upgrade.sh directly
sudo ./lib/upgrade.sh emergency-rollback <rollback-point-name>
```

#### Verify Rollback Point Before Using

```bash
./lib/upgrade.sh verify-rollback <rollback-point-name>
```

### Selective Rollback

Rollback only specific components:

```bash
# Rollback application only
./lib/upgrade.sh selective-rollback <point-name> app

# Rollback configuration only
./lib/upgrade.sh selective-rollback <point-name> config

# Rollback database only
./lib/upgrade.sh selective-rollback <point-name> db
```

---

## Uninstallation

### Standard Uninstall

Removes application, prompts about data:

```bash
sudo ./install.sh --uninstall
```

### Uninstall Preserving Data

Keeps configuration and database:

```bash
sudo ./install.sh --uninstall --keep-data
```

### Complete Purge

Removes everything including P-Net, firewall rules, udev rules:

```bash
sudo ./install.sh --uninstall --purge
```

### Dry Run

See what would be removed without making changes:

```bash
sudo ./install.sh --uninstall --dry-run
```

### Uninstall Manifest

After uninstall, a manifest is saved to:
```
/tmp/water-controller-uninstall-manifest-YYYYMMDD_HHMMSS.txt
```

---

## Troubleshooting

### Upgrade Fails at Health Check

```bash
# Run health check manually
./lib/upgrade.sh health-check

# Check for specific issues
./lib/upgrade.sh disk-check
```

Common causes:
- Insufficient disk space
- Database corruption
- Service not running

### Upgrade Fails at Dependency Installation

```bash
# Check package manager
sudo apt update

# Check for held packages
sudo apt-mark showhold
```

### Service Won't Start After Upgrade

```bash
# Check service status
sudo systemctl status water-controller

# Check logs
sudo journalctl -u water-controller -n 100

# Try manual start
sudo /opt/water-controller/venv/bin/python -m water_controller
```

### Rollback Fails

```bash
# Verify rollback point integrity
./lib/upgrade.sh verify-rollback <point-name>

# Try emergency rollback
sudo ./lib/upgrade.sh emergency-rollback

# Manual restoration
sudo tar -xzf /var/backups/water-controller/rollback/<point>/app.tar.gz -C /opt/water-controller
sudo tar -xzf /var/backups/water-controller/rollback/<point>/config.tar.gz -C /etc/water-controller
sudo systemctl restart water-controller
```

### Check Upgrade Reports

Upgrade reports are saved to `/tmp/`:
```bash
ls -la /tmp/upgrade-report-*.txt
ls -la /tmp/pre-upgrade-health-*.txt
ls -la /tmp/post-upgrade-validation-*.txt
```

---

## Quick Reference

### Upgrade Commands

```bash
# Interactive upgrade
sudo ./install.sh --upgrade

# Automated (no prompts)
sudo ./install.sh --upgrade --unattended

# With extended testing
sudo ./install.sh --upgrade --canary

# Step-by-step
sudo ./install.sh --upgrade --staged

# Dry run (see what would happen)
sudo ./install.sh --upgrade --dry-run
```

### Uninstall Commands

```bash
# Standard uninstall
sudo ./install.sh --uninstall

# Keep data
sudo ./install.sh --uninstall --keep-data

# Complete removal
sudo ./install.sh --uninstall --purge
```

### Health Check Commands

```bash
./lib/upgrade.sh health-check
./lib/upgrade.sh disk-check
./lib/upgrade.sh validate
```

### Rollback Commands

```bash
./lib/upgrade.sh verify-rollback <name>
./lib/upgrade.sh emergency-rollback
```

---

## Contact

For issues not covered in this guide, check:
- Installation logs: `/tmp/water-controller-install-*.log`
- Service logs: `journalctl -u water-controller`
- GitHub Issues: https://github.com/water-controller/water-controller/issues
