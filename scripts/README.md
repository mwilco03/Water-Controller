# Water Treatment Controller - Installation Scripts

Modular installation system for the Water Treatment Controller SCADA system.

## Overview

This installation system provides automated deployment of the Water Treatment Controller on ARM and x86 single-board computers running Debian-based Linux distributions.

**Tech Stack:**
- Backend: Python/FastAPI with uvicorn
- Frontend: React
- Database: SQLite with WAL mode
- Industrial: **P-Net PROFINET** (cornerstone of communication)

**Target Hardware:**
- Raspberry Pi (3B+, 4, 5)
- Orange Pi
- x86/x64 SBCs
- Minimum: 1GB RAM, 4GB storage

## Quick Start

```bash
# Run as root
sudo ./install.sh

# Non-interactive installation
sudo ./install.sh --yes

# Dry run (preview changes)
sudo ./install.sh --dry-run
```

## Installation Steps

The installer performs 10 steps:

| Step | Description | Module |
|------|-------------|--------|
| 1 | System Detection | detection.sh |
| 2 | Dependency Installation | dependencies.sh |
| 3 | **P-Net PROFINET Installation** | pnet.sh |
| 4 | Source Acquisition & Build | build.sh |
| 5 | File Installation | install-files.sh |
| 6 | Service Configuration | service.sh |
| 7 | Network & Storage | network-storage.sh |
| 8 | Service Start | service.sh |
| 9 | Validation | validation.sh |
| 10 | Documentation | documentation.sh |

## P-Net PROFINET (Critical)

P-Net is the cornerstone of this project, providing industrial PROFINET communication.

### Automatic Installation

P-Net is automatically built from source during installation because it's not available in standard repositories:

```bash
# Standalone p-net installation
./lib/pnet.sh install

# Check prerequisites
./lib/pnet.sh check

# Run diagnostics
./lib/pnet.sh diagnose

# Verify installation
./lib/pnet.sh verify
```

### P-Net Requirements

- Ethernet interface (not WiFi)
- libpcap-dev
- cmake 3.14+
- gcc/g++
- Real-time kernel recommended (not required)

### P-Net Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 34962 | TCP | PROFINET RTC |
| 34963 | TCP | PROFINET RTC |
| 34964 | UDP | PROFINET DCP |

## Command Line Options

### Installation Modes

```bash
./install.sh                  # Fresh installation
./install.sh --upgrade        # Upgrade existing
./install.sh --uninstall      # Remove installation
```

### Options

```bash
-h, --help          Show help
-v, --verbose       Verbose output
-y, --yes           Non-interactive mode
-n, --dry-run       Preview without changes
-f, --force         Force overwrite
```

### Paths

```bash
--install-dir PATH  Installation directory (/opt/water-controller)
--config-dir PATH   Configuration directory (/etc/water-controller)
--data-dir PATH     Data directory (/var/lib/water-controller)
--log-dir PATH      Log directory (/var/log/water-controller)
```

### Source

```bash
--source PATH       Use local source directory
--repo URL          Git repository URL
--branch NAME       Git branch (default: main)
```

### Network

```bash
--configure-network Enable network configuration
--static-ip IP      Static IP (e.g., 192.168.1.100/24)
--interface NAME    Network interface (e.g., eth0)
```

### Skip Options

```bash
--skip-deps         Skip dependency installation
--skip-build        Skip build step
--skip-network      Skip network configuration
--skip-validation   Skip validation tests
```

## Module Reference

### lib/detection.sh

System detection and prerequisite checks.

```bash
source lib/detection.sh
detect_system           # Detect OS, arch, hardware
classify_hardware       # Identify SBC type
check_prerequisites     # Verify requirements
check_dependencies      # Check installed tools
```

### lib/dependencies.sh

Package installation across distributions.

```bash
source lib/dependencies.sh
install_python          # Python 3.9+
install_nodejs          # Node.js 18+
install_build_deps      # Build tools
verify_all_dependencies # Verify all
```

### lib/pnet.sh

P-Net PROFINET stack installation.

```bash
source lib/pnet.sh
check_pnet_prerequisites  # Check requirements
install_pnet_full         # Full installation
verify_pnet_installation  # Verify install
diagnose_pnet             # Run diagnostics
configure_pnet_interface  # Configure network
```

### lib/build.sh

Source acquisition and compilation.

```bash
source lib/build.sh
acquire_source          # Clone/copy source
create_python_venv      # Create venv
build_python_backend    # Install Python deps
build_react_frontend    # npm build
verify_build            # Verify artifacts
```

### lib/install-files.sh

File installation and permissions.

```bash
source lib/install-files.sh
create_service_user       # Create user
create_directory_structure # Create dirs
install_python_app        # Install backend
install_frontend          # Install React
install_config_template   # Config files
```

### lib/service.sh

systemd service management.

```bash
source lib/service.sh
generate_service_unit   # Create unit file
install_service         # Install to systemd
enable_service          # Enable at boot
start_service           # Start service
check_service_health    # Health check
```

### lib/network-storage.sh

Network and storage optimization.

```bash
source lib/network-storage.sh
select_network_interface  # Select interface
configure_static_ip       # Set static IP
configure_firewall        # Firewall rules
configure_tmpfs           # RAM disk
configure_sqlite          # WAL mode
configure_log_rotation    # Log rotation
```

### lib/validation.sh

Post-installation testing.

```bash
source lib/validation.sh
run_validation_suite    # Run all tests
test_file_integrity     # Check files
test_service_status     # Service health
test_health_endpoint    # API health
test_pnet               # P-Net verification
```

### lib/documentation.sh

Documentation and rollback.

```bash
source lib/documentation.sh
generate_installation_report  # System report
generate_config_docs          # Config docs
create_rollback_point         # Create backup
perform_rollback              # Restore backup
cleanup_old_backups           # Cleanup
```

## Directory Structure

After installation:

```
/opt/water-controller/
├── venv/               # Python virtual environment
├── app/                # Backend application
├── frontend/           # React build
└── web/                # Static assets

/etc/water-controller/
├── config.yaml         # Main configuration
└── *.yaml.bak.*        # Config backups

/etc/pnet/
└── pnet.conf           # PROFINET configuration

/var/lib/water-controller/
├── water_controller.db # SQLite database
└── data/               # Application data

/var/log/water-controller/
└── *.log               # Application logs

/var/backups/water-controller/
└── rollback/           # Rollback points
```

## Validation

Run validation after installation:

```bash
# Full validation suite
./lib/validation.sh

# Individual tests
source lib/validation.sh
test_file_integrity
test_service_status
test_pnet              # Critical - PROFINET
test_health_endpoint
```

## Rollback

Create and manage rollback points:

```bash
source lib/documentation.sh

# Create rollback point
create_rollback_point "Before upgrade"

# List rollback points
list_rollback_points

# Restore from rollback
perform_rollback rollback_20240115_120000
```

## Troubleshooting

### P-Net Installation Failed

```bash
# Check prerequisites
./lib/pnet.sh check

# Run diagnostics
./lib/pnet.sh diagnose

# Manual install
./lib/pnet.sh install
```

### Service Won't Start

```bash
# Check status
systemctl status water-controller

# Check logs
journalctl -u water-controller -f

# Run validation
./lib/validation.sh
```

### Network Issues

```bash
# Check PROFINET ports
ss -tlnp | grep -E '3496[234]'

# Check interface
ip addr show eth0

# Configure interface
source lib/pnet.sh
configure_pnet_interface eth0
```

## Support

- Documentation: `/usr/share/doc/water-controller/`
- Logs: `/var/log/water-controller/`
- P-Net: https://github.com/rtlabs-com/p-net

## License

GPL-3.0-or-later
