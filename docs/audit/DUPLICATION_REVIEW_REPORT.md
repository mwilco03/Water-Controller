# Documentation and Code Duplication Review Report

**Date:** 2024-12-22
**Repository:** Water-Controller
**Reviewer:** Claude Code Audit

---

## Executive Summary

This report identifies significant duplication across documentation, configuration files, and scripts in the Water-Controller codebase. Addressing these issues will reduce maintenance burden, prevent documentation drift, and ensure consistency.

| Category | Severity | Files Affected | Estimated Effort |
|----------|----------|----------------|------------------|
| **Deployment Documentation** | HIGH | 3 files | Medium |
| **Systemd Services** | MEDIUM | 5 files | Small |
| **Installation Scripts** | MEDIUM | 2+ files | Medium |
| **Configuration Examples** | LOW | Multiple | Small |

---

## Critical Duplication: Deployment Documentation

### Affected Files

| File | Lines | Purpose |
|------|-------|---------|
| `docs/DEPLOYMENT.md` | 681 | Traditional markdown deployment guide |
| `docs/WATER_CONTROLLER_DEPLOYMENT_PROMPT.md` | 681 | System instruction format for AI deployment |
| `docs/WATER_CONTROLLER_DEPLOYMENT_SYSTEM_PROMPT.md` | 104 | Condensed system prompt |

### Overlap Analysis

**DEPLOYMENT.md vs WATER_CONTROLLER_DEPLOYMENT_PROMPT.md**

These two documents cover **~90% identical content** with different formatting:

| Section | DEPLOYMENT.md | WATER_CONTROLLER_DEPLOYMENT_PROMPT.md |
|---------|---------------|--------------------------------------|
| System Requirements | Lines 16-45 | Lines 29-51 (checklist format) |
| Installation Steps | Lines 46-124 | Lines 56-137 (phase-based) |
| Configuration | Lines 125-188 | Lines 138-244 (expanded) |
| Service Management | Lines 189-245 | Lines 350-408 |
| Backup/Restore | Lines 246-313 | Lines 410-468 |
| Troubleshooting | Lines 373-454 | Lines 570-614 |
| Security | Lines 466-473 | Lines 246-304 (expanded) |

**Specific Duplicated Content Examples:**

1. **Hardware Requirements** - Both specify:
   - CPU: ARM Cortex-A53 or x86_64
   - RAM: 512MB minimum, 2GB recommended
   - Network: Dedicated Ethernet for PROFINET

2. **Installation Commands** - Nearly identical:
   ```bash
   # Both files include this exact sequence:
   git clone https://github.com/mwilco03/Water-Controller.git
   cd Water-Controller
   mkdir build && cd build
   cmake -DCMAKE_BUILD_TYPE=Release ..
   make -j$(nproc)
   ```

3. **Configuration File Structure** - Same hierarchy documented in both

4. **Troubleshooting Scenarios** - Same symptoms and solutions

**WATER_CONTROLLER_DEPLOYMENT_SYSTEM_PROMPT.md**

This is a condensed version containing:
- Subset of configuration parameters
- Abbreviated troubleshooting guide
- Core deployment constraints

All content in this file is duplicated from the two larger files.

### Recommendations

| Priority | Action | Benefit |
|----------|--------|---------|
| **HIGH** | Consolidate to single `DEPLOYMENT.md` | Single source of truth |
| **HIGH** | Add "System Prompt Summary" section to DEPLOYMENT.md | Eliminate 2nd file |
| **MEDIUM** | Delete `WATER_CONTROLLER_DEPLOYMENT_SYSTEM_PROMPT.md` | Remove redundancy |
| **LOW** | Auto-generate condensed version from main doc | Maintain AI prompt format if needed |

### Suggested Structure

```markdown
# docs/DEPLOYMENT.md (consolidated)

## Overview
## Quick Start
## Detailed Installation
## Configuration Reference
## Service Management
## Backup & Restore
## Troubleshooting
## Appendix A: System Prompt Summary (condensed for AI use)
## Appendix B: Pre-deployment Checklist
```

---

## Medium Priority: Systemd Service File Duplication

### Pattern Analysis

All 5 service files share common blocks:

```ini
# Security hardening (identical in all 5 files)
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
```

| Service File | Unique Elements | Shared Elements |
|--------------|-----------------|-----------------|
| `water-controller.service` | PROFINET capabilities | Security block, journal output |
| `water-controller-api.service` | Python/uvicorn exec | Security block, journal output |
| `water-controller-ui.service` | Node.js exec | Security block, journal output |
| `water-controller-hmi.service` | --web-only mode | Security block, journal output |
| `water-controller-modbus.service` | Serial port access | Security block, journal output |

### User/Group Inconsistency

| Service | User | Group |
|---------|------|-------|
| water-controller.service | `wtc` | `wtc` |
| water-controller-api.service | `wtc` | `wtc` |
| water-controller-ui.service | `wtc` | `wtc` |
| **water-controller-hmi.service** | **`water-controller`** | **`water-controller`** |
| water-controller-modbus.service | `wtc` | `wtc` |

**Issue:** `water-controller-hmi.service` uses a different user (`water-controller`) than all other services (`wtc`).

### Recommendations

| Priority | Action | Benefit |
|----------|--------|---------|
| **HIGH** | Standardize user/group to `wtc` in all services | Consistency |
| **MEDIUM** | Use systemd drop-in files for shared config | Reduce duplication |
| **LOW** | Create `water-controller@.service` template | Single template for variants |

**Example Drop-in Structure:**
```
/etc/systemd/system/water-controller.service.d/
├── 10-security.conf    # Shared security hardening
├── 20-logging.conf     # Shared journal config
└── 30-environment.conf # Shared environment file
```

---

## Medium Priority: Installation Script Duplication

### Affected Files

| Script | Lines | Purpose |
|--------|-------|---------|
| `scripts/install.sh` | 257 | Full system installation |
| `scripts/install-hmi.sh` | 182 | HMI-specific installation |

### Duplicated Code Blocks

**1. Common Variables (Lines 11-16 in install.sh, Lines 40-49 in install-hmi.sh)**

```bash
# install.sh
INSTALL_DIR="/opt/water-controller"
CONFIG_DIR="/etc/water-controller"
DATA_DIR="/var/lib/water-controller"
LOG_DIR="/var/log/water-controller"
SERVICE_USER="wtc"
SERVICE_GROUP="wtc"

# install-hmi.sh (slightly different user)
INSTALL_DIR="/opt/water-controller"
DATA_DIR="/var/lib/water-controller"
CONFIG_DIR="/etc/water-controller"
LOG_DIR="/var/log/water-controller"
SERVICE_USER="water-controller"
SERVICE_GROUP="water-controller"
```

**2. Color Definitions (Lines 19-22 in both files)**

```bash
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
```

**3. Root Check (Lines 29-32 and 30-33)**

```bash
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: Please run as root${NC}"
    exit 1
fi
```

**4. Directory Creation (Lines 60-64 and 66-76)**

```bash
mkdir -p $INSTALL_DIR/{bin,lib,web,config}
mkdir -p $CONFIG_DIR
mkdir -p $DATA_DIR/{backups,historian,logs}
mkdir -p $LOG_DIR
```

**5. Python Environment Setup (Lines 94-98 and 93-109)**

```bash
python3 -m venv $INSTALL_DIR/venv
$INSTALL_DIR/venv/bin/pip install --upgrade pip
$INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/web/api/requirements.txt
```

### Inconsistency: Service User Names

| Script | Service User |
|--------|--------------|
| `install.sh` | `wtc` |
| `install-hmi.sh` | `water-controller` |

This creates a conflict when both scripts are run on the same system.

### Recommendations

| Priority | Action | Benefit |
|----------|--------|---------|
| **HIGH** | Standardize service user to `wtc` in all scripts | Consistency |
| **HIGH** | Create `common.sh` with shared functions | DRY principle |
| **MEDIUM** | Merge scripts with install mode flag | Single entry point |

**Proposed Structure:**
```bash
scripts/
├── lib/
│   └── common.sh       # Shared variables, colors, functions
├── install.sh          # Calls common.sh, full install
└── install-hmi.sh      # Calls common.sh, HMI-only install
```

**Example common.sh:**
```bash
#!/bin/bash
# Common installation utilities

# Standard paths
export INSTALL_DIR="/opt/water-controller"
export CONFIG_DIR="/etc/water-controller"
export DATA_DIR="/var/lib/water-controller"
export LOG_DIR="/var/log/water-controller"
export SERVICE_USER="wtc"
export SERVICE_GROUP="wtc"

# Colors
export RED='\033[0;31m'
export GREEN='\033[0;32m'
export YELLOW='\033[1;33m'
export NC='\033[0m'

# Common functions
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

require_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root"
        exit 1
    fi
}

create_directories() {
    mkdir -p "$INSTALL_DIR"/{bin,lib,web,config}
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$DATA_DIR"/{backups,historian}
    mkdir -p "$LOG_DIR"
}

setup_python_venv() {
    python3 -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/web/api/requirements.txt"
}
```

---

## Low Priority: Configuration Example Duplication

### Affected Files

Configuration examples appear in multiple locations:

| Location | Content |
|----------|---------|
| `docs/DEPLOYMENT.md` lines 131-153 | controller.conf example |
| `docs/WATER_CONTROLLER_DEPLOYMENT_PROMPT.md` lines 162-197 | controller.conf example (expanded) |
| `scripts/install.sh` lines 112-137 | controller.conf inline creation |
| `docker/config/water-controller.json` | JSON version of same config |

### Recommendations

| Priority | Action | Benefit |
|----------|--------|---------|
| **LOW** | Create `config/controller.conf.example` | Single source |
| **LOW** | Reference example file from documentation | Avoid inline duplication |
| **LOW** | Add JSON schema for validation | Structured validation |

---

## Audit Documentation Quality

The `docs/audit/` directory contains well-structured analysis documents:

| File | Lines | Quality | Notes |
|------|-------|---------|-------|
| `DOCUMENTATION_AUDIT_REPORT.md` | 284 | Good | Comprehensive coverage |
| `DOCUMENTATION_RESTRUCTURING_PLAN.md` | 327 | Good | Actionable migration plan |
| `DOC_COMMENT_RECOMMENDATIONS.md` | N/A | Not reviewed | Code comment guidance |

**Note:** These audit documents do NOT contain significant duplication - they are complementary with distinct purposes.

---

## Action Items Summary

### Immediate Actions (High Priority)

1. **Consolidate deployment documentation**
   - Merge `DEPLOYMENT.md` and `WATER_CONTROLLER_DEPLOYMENT_PROMPT.md`
   - Delete `WATER_CONTROLLER_DEPLOYMENT_SYSTEM_PROMPT.md`
   - Add condensed "System Prompt Summary" appendix

2. **Standardize service user**
   - Update `water-controller-hmi.service` to use `wtc` user
   - Update `install-hmi.sh` to use `wtc` user

### Short-term Actions (Medium Priority)

3. **Refactor installation scripts**
   - Create `scripts/lib/common.sh` with shared code
   - Source common.sh from both install scripts
   - Remove duplicate variable definitions

4. **Standardize systemd services**
   - Consider systemd drop-in files for shared configuration
   - Document the security hardening rationale once

### Long-term Actions (Low Priority)

5. **Configuration management**
   - Create authoritative `config/controller.conf.example`
   - Generate inline examples from this file during docs build

6. **Documentation CI**
   - Add link checking to prevent documentation drift
   - Implement automated duplication detection

---

## Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Documentation files with >50% overlap | 3 | 0 |
| Scripts with shared code blocks | 2 | 0 (refactored to common.sh) |
| Service files with inconsistent config | 5 | 0 (using drop-ins) |
| Configuration examples in multiple places | 4+ | 1 (authoritative example) |

---

*Report generated by duplication analysis*
*Next review recommended: After consolidation actions complete*
