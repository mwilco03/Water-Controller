# Water-Controller Installation Guide

This guide covers installing Water-Controller on Debian-based Linux systems, including Raspberry Pi and other ARM single-board computers.

## Quick Install

The fastest way to install Water-Controller is with the one-liner bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | bash
```

This command:
1. Detects your system state (fresh install or existing installation)
2. Validates prerequisites (root access, disk space, network)
3. Clones the repository to a staging directory
4. Runs the installation script
5. Writes version metadata for future upgrades

## System Requirements

### Hardware

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 512 MB | 1 GB+ |
| Storage | 2 GB free | 4 GB+ |
| Architecture | ARMv6+ or x86_64 | ARM64 or x86_64 |

### Software

| Requirement | Version |
|-------------|---------|
| OS | Debian 10+, Ubuntu 20.04+, Raspbian 10+ |
| Python | 3.9+ |
| Node.js | 18+ |
| systemd | 232+ |

### Network

- Internet access required for installation
- Ports 3000 (Web UI) and 8080 (API) used by default

## Pre-Installation

### Check System Requirements

```bash
# Check OS version
cat /etc/os-release

# Check Python version
python3 --version

# Check Node.js version
node --version

# Check available disk space
df -h /opt

# Check available RAM
free -h
```

### Install Prerequisites

On Debian/Ubuntu/Raspbian:

```bash
# Update package lists
sudo apt-get update

# Install required packages
sudo apt-get install -y \
    git \
    curl \
    python3 \
    python3-pip \
    python3-venv \
    nodejs \
    npm \
    build-essential

# Verify Node.js version (should be 18+)
node --version

# If Node.js is too old, install via NodeSource:
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
```

## Installation Methods

### Method 1: One-Liner Bootstrap (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/mwilco03/Water-Controller/main/bootstrap.sh | bash
```

#### With Options

```bash
# Install from a specific branch
curl -fsSL .../bootstrap.sh | bash -s -- install --branch develop

# Force reinstall over existing installation
curl -fsSL .../bootstrap.sh | bash -s -- install --force

# Dry run (show what would be done)
curl -fsSL .../bootstrap.sh | bash -s -- install --dry-run
```

### Method 2: Manual Installation

```bash
# Clone the repository
git clone https://github.com/mwilco03/Water-Controller.git
cd Water-Controller

# Run the install script
sudo ./scripts/install.sh --source .
```

### Method 3: Offline Installation

For air-gapped systems:

1. On a connected machine, download the repository:
   ```bash
   git clone --depth 1 https://github.com/mwilco03/Water-Controller.git
   tar -czf water-controller-offline.tar.gz Water-Controller
   ```

2. Transfer the archive to the target system

3. On the target system:
   ```bash
   tar -xzf water-controller-offline.tar.gz
   cd Water-Controller
   sudo ./scripts/install.sh --source .
   ```

## Installation Directory Structure

After installation, files are located at:

```
/opt/water-controller/
├── venv/                  # Python virtual environment
├── app/                   # Python backend application
├── web/                   # Frontend application
├── scripts/               # Installation and management scripts
├── .version               # Version metadata (JSON)
├── .manifest              # Installed files with checksums
└── .rollback/             # Previous version backups

/etc/water-controller/     # Configuration files
/var/lib/water-controller/ # Runtime data, databases
/var/log/water-controller/ # Log files
```

## Post-Installation

### Verify Installation

```bash
# Check service status
sudo systemctl status water-controller

# Run health check
curl http://localhost:8080/health

# View recent logs
journalctl -u water-controller --since "10 minutes ago"
```

### Access the Web Interface

Open a web browser and navigate to:

- **Web UI (HMI)**: http://YOUR_IP:3000
- **API Documentation**: http://YOUR_IP:8080/docs

### Enable Service at Boot

The installation script enables automatic startup, but you can verify:

```bash
sudo systemctl is-enabled water-controller
```

## Configuration

### Main Configuration

Configuration files are stored in `/etc/water-controller/`:

```bash
# List configuration files
ls -la /etc/water-controller/

# Edit main configuration
sudo nano /etc/water-controller/config.yaml
```

### Environment Variables

Create or edit `/etc/water-controller/environment`:

```bash
# API port (default: 8080)
WEB_PORT=8080

# Web UI port (default: 3000)
UI_PORT=3000

# Log level
LOG_LEVEL=INFO

# Data directory
DATA_DIR=/var/lib/water-controller
```

### Service Configuration

Modify the systemd service if needed:

```bash
# Edit service override
sudo systemctl edit water-controller

# Reload after changes
sudo systemctl daemon-reload
sudo systemctl restart water-controller
```

## Troubleshooting

### Installation Fails

**Check prerequisites:**
```bash
# Run prerequisite check
./scripts/lib/detection.sh --check-prerequisites
```

**Check logs:**
```bash
cat /var/log/water-controller-install.log
```

### Service Won't Start

**Check service status:**
```bash
sudo systemctl status water-controller
journalctl -u water-controller -n 50
```

**Check for port conflicts:**
```bash
sudo ss -tlnp | grep -E ':(3000|8080)'
```

**Check file permissions:**
```bash
ls -la /opt/water-controller/
ls -la /var/lib/water-controller/
```

### Python Import Errors

**Verify virtual environment:**
```bash
/opt/water-controller/venv/bin/python3 -c "import fastapi; print('OK')"
```

**Reinstall dependencies:**
```bash
/opt/water-controller/venv/bin/pip install -r /opt/water-controller/app/requirements.txt
```

### Frontend Not Loading

**Check if frontend is built:**
```bash
test -d /opt/water-controller/web/.next && echo "Built" || echo "Not built"
```

**Rebuild frontend:**
```bash
cd /opt/water-controller/web
npm run build
```

## Uninstallation

To remove Water-Controller:

```bash
# Remove completely
sudo ./scripts/remove.sh

# Remove but keep configuration
sudo ./scripts/remove.sh --keep-config

# Or via bootstrap
curl -fsSL .../bootstrap.sh | bash -s -- remove
curl -fsSL .../bootstrap.sh | bash -s -- remove --keep-config
```

## Next Steps

- [Upgrade Guide](UPGRADE.md) - How to upgrade to newer versions
- [Deployment Guide](DEPLOYMENT.md) - Detailed configuration and deployment options
- [Troubleshooting Guide](TROUBLESHOOTING_GUIDE.md) - Common issues and solutions
- [Operator Guide](OPERATOR.md) - Quick reference for operators

## Getting Help

- **GitHub Issues**: https://github.com/mwilco03/Water-Controller/issues
- **Documentation**: https://github.com/mwilco03/Water-Controller/docs
