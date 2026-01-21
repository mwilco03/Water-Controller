#!/bin/bash
# =============================================================================
# Water-Controller Bootstrap - Constants
# =============================================================================
# All constants and global state variables.
# This module must be sourced first as other modules depend on these values.

# Prevent double-sourcing
[[ -n "${_WTC_CONSTANTS_LOADED:-}" ]] && return 0
_WTC_CONSTANTS_LOADED=1

# =============================================================================
# Version and Repository
# =============================================================================

readonly BOOTSTRAP_VERSION="2.0.0"
readonly REPO_URL="https://github.com/mwilco03/Water-Controller.git"
readonly REPO_RAW_URL="https://raw.githubusercontent.com/mwilco03/Water-Controller"

# =============================================================================
# Installation Paths
# =============================================================================

readonly INSTALL_DIR="/opt/water-controller"
readonly VERSION_FILE="$INSTALL_DIR/.version"
readonly MANIFEST_FILE="$INSTALL_DIR/.manifest"
readonly CONFIG_DIR="/etc/water-controller"
readonly DATA_DIR="/var/lib/water-controller"
readonly LOG_DIR="/var/log/water-controller"
readonly BACKUP_DIR="/var/backups/water-controller"
readonly BOOTSTRAP_LOG="/var/log/water-controller-bootstrap.log"

# =============================================================================
# Requirements
# =============================================================================

readonly MIN_DISK_SPACE_MB=2048
readonly REQUIRED_TOOLS=("git" "curl" "systemctl")
readonly CHECKSUM_FILE="SHA256SUMS"

# =============================================================================
# Service Names (DRY - single source of truth)
# =============================================================================

readonly DOCKER_SERVICE="docker"
readonly WTC_DOCKER_SERVICE="water-controller-docker"

# =============================================================================
# Global State (mutable)
# =============================================================================

QUIET_MODE="${QUIET_MODE:-false}"
VERBOSE_MODE="${VERBOSE_MODE:-false}"
DEPLOYMENT_MODE="${DEPLOYMENT_MODE:-}"
CLEANUP_DIRS=()

# =============================================================================
# Colors for Output
# =============================================================================

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color
