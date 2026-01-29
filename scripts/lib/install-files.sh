#!/bin/bash
#
# Water Treatment Controller - Installation and File Placement System
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module provides file installation, user/group creation,
# directory structure setup, and atomic file operations.
#
# Tech Stack: Python/FastAPI backend, React frontend
# Target: ARM/x86 SBCs running Debian-based Linux
#

# Prevent multiple sourcing
if [ -n "${_WTC_INSTALL_FILES_LOADED:-}" ]; then
    return 0
fi
_WTC_INSTALL_FILES_LOADED=1

# Source detection module for logging functions
: "${SCRIPT_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
if [ -f "$SCRIPT_DIR/detection.sh" ]; then
    # shellcheck source=detection.sh
    source "$SCRIPT_DIR/detection.sh"
fi

# =============================================================================
# Constants
# =============================================================================

readonly INSTALL_FILES_VERSION="1.0.0"

# Service user configuration
: "${SERVICE_USER:=water-controller}"
: "${SERVICE_GROUP:=water-controller}"

# Installation paths
: "${INSTALL_BASE:=/opt/water-controller}"
: "${VENV_PATH:=$INSTALL_BASE/venv}"
: "${APP_PATH:=$INSTALL_BASE/app}"
: "${WEB_PATH:=$INSTALL_BASE/web}"
readonly DOCS_PATH="$INSTALL_BASE/docs"
: "${CONFIG_DIR:=/etc/water-controller}"
: "${DATA_DIR:=/var/lib/water-controller}"
: "${LOG_DIR:=/var/log/water-controller}"
: "${RUN_DIR:=/run/water-controller}"

# Backup directory
readonly BACKUP_BASE="/var/backup/water-controller"

# =============================================================================
# Atomic File Operations
# =============================================================================

# Write file atomically (write to temp, then rename)
# Input: source_file, destination_file
# Returns: 0 on success, 4 on failure
atomic_write() {
    local source_file="$1"
    local dest_file="$2"

    if [ -z "$source_file" ] || [ -z "$dest_file" ]; then
        log_error "atomic_write: source and destination required"
        return 4
    fi

    if [ ! -f "$source_file" ]; then
        log_error "atomic_write: source file does not exist: $source_file"
        return 4
    fi

    local dest_dir
    dest_dir="$(dirname "$dest_file")"

    # Ensure destination directory exists
    if [ ! -d "$dest_dir" ]; then
        mkdir -p "$dest_dir" || {
            log_error "atomic_write: failed to create directory: $dest_dir"
            return 4
        }
    fi

    # Create temp file in same directory (for atomic rename)
    local temp_file
    temp_file="$(mktemp "${dest_file}.tmp.XXXXXX")" || {
        log_error "atomic_write: failed to create temp file"
        return 4
    }

    # Copy source to temp
    if ! cp "$source_file" "$temp_file"; then
        log_error "atomic_write: failed to copy to temp file"
        rm -f "$temp_file"
        return 4
    fi

    # Verify copy with checksum
    local source_sum dest_sum
    source_sum="$(sha256sum "$source_file" 2>/dev/null | awk '{print $1}')"
    dest_sum="$(sha256sum "$temp_file" 2>/dev/null | awk '{print $1}')"

    if [ "$source_sum" != "$dest_sum" ]; then
        log_error "atomic_write: checksum mismatch after copy"
        rm -f "$temp_file"
        return 4
    fi

    # Atomic rename
    if ! mv "$temp_file" "$dest_file"; then
        log_error "atomic_write: failed to rename temp file to destination"
        rm -f "$temp_file"
        return 4
    fi

    log_debug "atomic_write: $source_file -> $dest_file (checksum: ${source_sum:0:8}...)"
    return 0
}

# Write content atomically to a file
# Input: content (stdin or $1), destination_file
# Returns: 0 on success, 4 on failure
atomic_write_content() {
    local dest_file="$1"
    local content="$2"

    if [ -z "$dest_file" ]; then
        log_error "atomic_write_content: destination required"
        return 4
    fi

    local dest_dir
    dest_dir="$(dirname "$dest_file")"

    # Ensure destination directory exists
    if [ ! -d "$dest_dir" ]; then
        mkdir -p "$dest_dir" || {
            log_error "atomic_write_content: failed to create directory: $dest_dir"
            return 4
        }
    fi

    # Create temp file
    local temp_file
    temp_file="$(mktemp "${dest_file}.tmp.XXXXXX")" || {
        log_error "atomic_write_content: failed to create temp file"
        return 4
    }

    # Write content
    if [ -n "$content" ]; then
        echo "$content" > "$temp_file" || {
            log_error "atomic_write_content: failed to write content"
            rm -f "$temp_file"
            return 4
        }
    else
        # Read from stdin
        cat > "$temp_file" || {
            log_error "atomic_write_content: failed to write from stdin"
            rm -f "$temp_file"
            return 4
        }
    fi

    # Atomic rename
    if ! mv "$temp_file" "$dest_file"; then
        log_error "atomic_write_content: failed to rename temp file"
        rm -f "$temp_file"
        return 4
    fi

    log_debug "atomic_write_content: wrote to $dest_file"
    return 0
}

# Backup a file before modifying
# Input: filepath
# Returns: 0 on success, prints backup path
backup_file() {
    local filepath="$1"

    if [ -z "$filepath" ]; then
        log_error "backup_file: filepath required"
        return 1
    fi

    if [ ! -f "$filepath" ]; then
        log_debug "backup_file: file does not exist, nothing to backup: $filepath"
        return 0
    fi

    local timestamp
    timestamp="$(date +%Y%m%d_%H%M%S)"

    local backup_path="${filepath}.backup.${timestamp}"

    if ! cp -p "$filepath" "$backup_path"; then
        log_error "backup_file: failed to create backup: $backup_path"
        return 1
    fi

    # Verify backup
    if [ ! -f "$backup_path" ]; then
        log_error "backup_file: backup verification failed"
        return 1
    fi

    log_info "Created backup: $backup_path"
    echo "$backup_path"
    return 0
}

# =============================================================================
# User and Group Creation
# =============================================================================

# Create service user and group
# Returns: 0 on success
create_service_user() {
    log_info "Setting up service user and group..."

    # Check if group exists
    if getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
        log_debug "Group already exists: $SERVICE_GROUP"
    else
        log_info "Creating group: $SERVICE_GROUP"
        sudo groupadd --system "$SERVICE_GROUP" || {
            log_error "Failed to create group: $SERVICE_GROUP"
            return 1
        }
    fi

    # Check if user exists
    if id "$SERVICE_USER" >/dev/null 2>&1; then
        log_debug "User already exists: $SERVICE_USER"

        # Ensure user is in the correct group
        if ! id -nG "$SERVICE_USER" | grep -qw "$SERVICE_GROUP"; then
            log_info "Adding user to group: $SERVICE_GROUP"
            sudo usermod -a -G "$SERVICE_GROUP" "$SERVICE_USER" || {
                log_warn "Failed to add user to group"
            }
        fi
    else
        log_info "Creating user: $SERVICE_USER"
        sudo useradd --system \
            --gid "$SERVICE_GROUP" \
            --no-create-home \
            --home-dir "$INSTALL_BASE" \
            --shell /usr/sbin/nologin \
            --comment "Water Controller Service" \
            "$SERVICE_USER" || {
            log_error "Failed to create user: $SERVICE_USER"
            return 1
        }
    fi

    # Add to dialout group for serial port access (PROFINET/Modbus RTU)
    if getent group dialout >/dev/null 2>&1; then
        if ! id -nG "$SERVICE_USER" | grep -qw "dialout"; then
            log_debug "Adding user to dialout group for serial access"
            sudo usermod -a -G dialout "$SERVICE_USER" || {
                log_warn "Failed to add user to dialout group"
            }
        fi
    fi

    # Add to gpio group if it exists (for Raspberry Pi GPIO access)
    if getent group gpio >/dev/null 2>&1; then
        if ! id -nG "$SERVICE_USER" | grep -qw "gpio"; then
            log_debug "Adding user to gpio group"
            sudo usermod -a -G gpio "$SERVICE_USER" || {
                log_warn "Failed to add user to gpio group"
            }
        fi
    fi

    log_info "Service user setup complete: $SERVICE_USER"
    _log_write "INFO" "Service user created/verified: $SERVICE_USER:$SERVICE_GROUP"

    return 0
}

# =============================================================================
# Directory Structure
# =============================================================================

# Create complete directory structure with proper permissions
# Returns: 0 on success
create_directory_structure() {
    log_info "Creating directory structure..."

    local failed=0

    # Application directories (owned by root, readable by service)
    local app_dirs=(
        "$INSTALL_BASE"
        "$INSTALL_BASE/app"
        "$INSTALL_BASE/web"
        "$INSTALL_BASE/docs"
    )

    for dir in "${app_dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            log_debug "Creating directory: $dir"
            sudo mkdir -p "$dir" || {
                log_error "Failed to create directory: $dir"
                failed=1
                continue
            }
        fi
        # Set ownership: root:service-group
        sudo chown root:"$SERVICE_GROUP" "$dir" || {
            log_warn "Failed to set ownership on: $dir"
        }
        # Set permissions: rwxr-x--- (750)
        sudo chmod 750 "$dir" || {
            log_warn "Failed to set permissions on: $dir"
        }
    done

    # Venv directory (may already exist from build)
    if [ -d "$VENV_PATH" ]; then
        sudo chown -R root:"$SERVICE_GROUP" "$VENV_PATH" || {
            log_warn "Failed to set ownership on venv"
        }
        sudo chmod 750 "$VENV_PATH" || {
            log_warn "Failed to set permissions on venv"
        }
    fi

    # Configuration directory (sensitive, restricted access)
    if [ ! -d "$CONFIG_DIR" ]; then
        log_debug "Creating config directory: $CONFIG_DIR"
        sudo mkdir -p "$CONFIG_DIR" || {
            log_error "Failed to create config directory: $CONFIG_DIR"
            failed=1
        }
    fi
    sudo chown root:"$SERVICE_GROUP" "$CONFIG_DIR"
    sudo chmod 750 "$CONFIG_DIR"  # rwxr-x--- (group can read)

    # Data directory (service needs write access)
    local data_dirs=(
        "$DATA_DIR"
        "$DATA_DIR/historian"
        "$DATA_DIR/backups"
        "$DATA_DIR/uploads"
    )

    for dir in "${data_dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            log_debug "Creating data directory: $dir"
            sudo mkdir -p "$dir" || {
                log_error "Failed to create directory: $dir"
                failed=1
                continue
            }
        fi
        # Set ownership: service user
        sudo chown "$SERVICE_USER:$SERVICE_GROUP" "$dir" || {
            log_warn "Failed to set ownership on: $dir"
        }
        # Set permissions: rwxr-x--- (750)
        sudo chmod 750 "$dir" || {
            log_warn "Failed to set permissions on: $dir"
        }
    done

    # Log directory (service needs write access)
    if [ ! -d "$LOG_DIR" ]; then
        log_debug "Creating log directory: $LOG_DIR"
        sudo mkdir -p "$LOG_DIR" || {
            log_error "Failed to create log directory: $LOG_DIR"
            failed=1
        }
    fi
    sudo chown "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
    sudo chmod 750 "$LOG_DIR"

    # Runtime directory (for PID files, sockets - tmpfs typically)
    # This is usually created by systemd, but we prepare it
    if [ ! -d "$RUN_DIR" ]; then
        log_debug "Creating runtime directory: $RUN_DIR"
        sudo mkdir -p "$RUN_DIR" || {
            log_warn "Failed to create runtime directory (may be created by systemd)"
        }
    fi
    if [ -d "$RUN_DIR" ]; then
        sudo chown "$SERVICE_USER:$SERVICE_GROUP" "$RUN_DIR"
        sudo chmod 755 "$RUN_DIR"
    fi

    # Backup directory
    if [ ! -d "$BACKUP_BASE" ]; then
        log_debug "Creating backup directory: $BACKUP_BASE"
        sudo mkdir -p "$BACKUP_BASE" || {
            log_warn "Failed to create backup directory"
        }
    fi
    if [ -d "$BACKUP_BASE" ]; then
        sudo chown root:root "$BACKUP_BASE"
        sudo chmod 700 "$BACKUP_BASE"
    fi

    if [ $failed -ne 0 ]; then
        log_error "Directory structure creation had errors"
        return 1
    fi

    log_info "Directory structure created successfully"
    _log_write "INFO" "Directory structure created"

    return 0
}

# =============================================================================
# Python Application Installation
# =============================================================================

# Install Python application files
# Returns: 0 on success
install_python_app() {
    log_info "Installing Python application..."

    if [ -z "$SOURCE_DIR" ]; then
        log_error "SOURCE_DIR not set. Run acquire_source first."
        return 4
    fi

    # Find backend source directory
    local backend_src=""
    if [ -d "$SOURCE_DIR/web/api" ]; then
        backend_src="$SOURCE_DIR/web/api"
    elif [ -d "$SOURCE_DIR/backend" ]; then
        backend_src="$SOURCE_DIR/backend"
    elif [ -d "$SOURCE_DIR/api" ]; then
        backend_src="$SOURCE_DIR/api"
    elif [ -f "$SOURCE_DIR/main.py" ] || [ -d "$SOURCE_DIR/app" ]; then
        backend_src="$SOURCE_DIR"
    else
        log_error "Could not find Python application source"
        return 4
    fi

    log_info "Installing from: $backend_src"
    log_info "Installing to: $APP_PATH"

    # Ensure destination directory exists
    sudo mkdir -p "$APP_PATH" || {
        log_error "Failed to create app directory: $APP_PATH"
        return 4
    }

    # Copy Python files (excluding __pycache__, .pyc, etc.)
    log_debug "Copying Python application files..."

    # Use rsync if available for better control
    if command -v rsync >/dev/null 2>&1; then
        sudo rsync -av --delete \
            --exclude='__pycache__' \
            --exclude='*.pyc' \
            --exclude='*.pyo' \
            --exclude='.pytest_cache' \
            --exclude='.mypy_cache' \
            --exclude='.git' \
            --exclude='venv' \
            --exclude='env' \
            --exclude='.env' \
            --exclude='node_modules' \
            "$backend_src/" "$APP_PATH/" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
            log_error "rsync failed"
            return 4
        }
    else
        # Fallback to cp
        # First, clean destination
        sudo find "$APP_PATH" -mindepth 1 -delete 2>/dev/null || true

        # Copy files
        sudo cp -r "$backend_src"/* "$APP_PATH/" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
            log_error "cp failed"
            return 4
        }

        # Remove unwanted files
        sudo find "$APP_PATH" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
        sudo find "$APP_PATH" -type f -name '*.pyc' -delete 2>/dev/null || true
        sudo find "$APP_PATH" -type f -name '*.pyo' -delete 2>/dev/null || true
        sudo find "$APP_PATH" -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true
        sudo find "$APP_PATH" -type d -name 'venv' -exec rm -rf {} + 2>/dev/null || true
        sudo find "$APP_PATH" -type d -name 'node_modules' -exec rm -rf {} + 2>/dev/null || true
    fi

    # Set ownership and permissions
    log_debug "Setting file ownership and permissions..."
    sudo chown -R root:"$SERVICE_GROUP" "$APP_PATH"

    # Directories: 750, Files: 640
    sudo find "$APP_PATH" -type d -exec chmod 750 {} \;
    sudo find "$APP_PATH" -type f -exec chmod 640 {} \;

    # Make any scripts executable
    sudo find "$APP_PATH" -type f -name '*.sh' -exec chmod 750 {} \;

    # Verify main application file exists
    local main_file=""
    if [ -f "$APP_PATH/app/main.py" ]; then
        main_file="$APP_PATH/app/main.py"
    elif [ -f "$APP_PATH/main.py" ]; then
        main_file="$APP_PATH/main.py"
    fi

    if [ -z "$main_file" ]; then
        log_warn "No main.py found in installed application"
    else
        log_debug "Main application file: $main_file"
    fi

    # Count installed files
    local file_count
    file_count="$(find "$APP_PATH" -type f -name '*.py' | wc -l)"
    log_info "Installed $file_count Python files"

    _log_write "INFO" "Python application installed: $file_count files to $APP_PATH"

    return 0
}

# =============================================================================
# Frontend Installation
# =============================================================================

# Install React frontend build
# Returns: 0 on success
install_frontend() {
    log_info "Installing frontend..."

    if [ -z "$SOURCE_DIR" ]; then
        log_error "SOURCE_DIR not set. Run acquire_source first."
        return 4
    fi

    # Find frontend build directory
    local frontend_build=""
    local frontend_src=""
    local is_nextjs=0

    # Check for build output in various locations
    if [ -d "$SOURCE_DIR/web/ui/dist" ]; then
        frontend_build="$SOURCE_DIR/web/ui/dist"
        frontend_src="$SOURCE_DIR/web/ui"
    elif [ -d "$SOURCE_DIR/web/ui/build" ]; then
        frontend_build="$SOURCE_DIR/web/ui/build"
        frontend_src="$SOURCE_DIR/web/ui"
    elif [ -d "$SOURCE_DIR/web/ui/.next" ]; then
        # Next.js build - need entire frontend directory for 'next start'
        frontend_build="$SOURCE_DIR/web/ui/.next"
        frontend_src="$SOURCE_DIR/web/ui"
        is_nextjs=1
    elif [ -d "$SOURCE_DIR/frontend/dist" ]; then
        frontend_build="$SOURCE_DIR/frontend/dist"
        frontend_src="$SOURCE_DIR/frontend"
    elif [ -d "$SOURCE_DIR/frontend/build" ]; then
        frontend_build="$SOURCE_DIR/frontend/build"
        frontend_src="$SOURCE_DIR/frontend"
    fi

    # Check if FRONTEND_BUILD_DIR was set by build.sh
    if [ -z "$frontend_build" ] && [ -n "$FRONTEND_BUILD_DIR" ] && [ -d "$FRONTEND_BUILD_DIR" ]; then
        frontend_build="$FRONTEND_BUILD_DIR"
    fi

    if [ -z "$frontend_build" ] || [ ! -d "$frontend_build" ]; then
        log_warn "No frontend build found, skipping frontend installation"
        log_warn "Run build_react_frontend first or ensure build output exists"
        return 0
    fi

    log_info "Installing frontend from: $frontend_build"
    log_info "Installing to: $WEB_PATH"

    # Ensure destination directory exists
    sudo mkdir -p "$WEB_PATH" || {
        log_error "Failed to create web directory: $WEB_PATH"
        return 4
    }

    # For Next.js, we need to copy the entire frontend directory structure
    # including node_modules, package.json, and next.config.js for 'next start'
    if [ "$is_nextjs" -eq 1 ] && [ -n "$frontend_src" ]; then
        log_info "Next.js build detected - installing complete frontend for production server"

        if command -v rsync >/dev/null 2>&1; then
            # Copy .next build output
            sudo rsync -av --delete \
                "$frontend_build/" "$WEB_PATH/.next/" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
                log_error "rsync failed for .next"
                return 4
            }

            # Copy node_modules (required for next start)
            if [ -d "$frontend_src/node_modules" ]; then
                log_debug "Copying node_modules for Next.js runtime..."
                sudo rsync -av \
                    "$frontend_src/node_modules/" "$WEB_PATH/node_modules/" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
                    log_error "rsync failed for node_modules"
                    return 4
                }
            fi

            # Copy essential config files
            for config_file in package.json next.config.js; do
                if [ -f "$frontend_src/$config_file" ]; then
                    sudo cp "$frontend_src/$config_file" "$WEB_PATH/" 2>&1 | tee -a "$INSTALL_LOG_FILE"
                fi
            done
        else
            # Without rsync, use cp
            sudo find "$WEB_PATH" -mindepth 1 -delete 2>/dev/null || true

            # Copy .next
            sudo mkdir -p "$WEB_PATH/.next"
            sudo cp -r "$frontend_build"/* "$WEB_PATH/.next/" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
                log_error "cp failed for .next"
                return 4
            }

            # Copy node_modules
            if [ -d "$frontend_src/node_modules" ]; then
                log_debug "Copying node_modules for Next.js runtime..."
                sudo cp -r "$frontend_src/node_modules" "$WEB_PATH/" 2>&1 | tee -a "$INSTALL_LOG_FILE"
            fi

            # Copy config files
            for config_file in package.json next.config.js; do
                if [ -f "$frontend_src/$config_file" ]; then
                    sudo cp "$frontend_src/$config_file" "$WEB_PATH/" 2>&1 | tee -a "$INSTALL_LOG_FILE"
                fi
            done
        fi
    else
        # Standard static build - just copy build output
        log_debug "Copying frontend build files..."

        if command -v rsync >/dev/null 2>&1; then
            sudo rsync -av --delete \
                "$frontend_build/" "$WEB_PATH/" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
                log_error "rsync failed"
                return 4
            }
        else
            # Clean destination first
            sudo find "$WEB_PATH" -mindepth 1 -delete 2>/dev/null || true

            # Copy files
            sudo cp -r "$frontend_build"/* "$WEB_PATH/" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
                log_error "cp failed"
                return 4
            }
        fi
    fi

    # Set ownership and permissions
    log_debug "Setting file ownership and permissions..."
    sudo chown -R root:"$SERVICE_GROUP" "$WEB_PATH"

    # Directories: 755 (world readable for static files)
    # Files: 644
    sudo find "$WEB_PATH" -type d -exec chmod 755 {} \;
    sudo find "$WEB_PATH" -type f -exec chmod 644 {} \;

    # Verify index.html exists (for static builds)
    if [ -f "$WEB_PATH/index.html" ]; then
        log_debug "Found index.html in frontend build"
    elif [ -d "$WEB_PATH/server" ]; then
        log_debug "Found Next.js server build"
    else
        log_warn "No index.html found (may be OK for SSR builds)"
    fi

    # Count installed files
    local file_count
    file_count="$(find "$WEB_PATH" -type f | wc -l)"
    log_info "Installed $file_count frontend files"

    _log_write "INFO" "Frontend installed: $file_count files to $WEB_PATH"

    return 0
}

# =============================================================================
# Configuration Installation
# =============================================================================

# Generate default configuration file content
_generate_default_config() {
    cat << 'YAML'
# Water-Controller Configuration
# Generated by installation script

# General settings
general:
  log_level: INFO
  data_dir: /var/lib/water-controller
  log_dir: /var/log/water-controller

# API server settings
api:
  host: 0.0.0.0
  port: 8000
  workers: 2
  reload: false

# Database settings
database:
  type: sqlite
  path: /var/lib/water-controller/historian.db
  # For PostgreSQL:
  # type: postgresql
  # host: localhost
  # port: 5432
  # name: water_controller
  # user: wtc
  # password: changeme

# PROFINET settings (empty interface = auto-detect)
profinet:
  interface: ""
  station_name: water-controller
  cycle_time_ms: 1000

# Alarm settings
alarms:
  enabled: true
  max_active: 1000
  history_days: 90

# Historian settings
historian:
  enabled: true
  compression: swinging_door
  retention_days: 365
  checkpoint_interval: 300

# Security settings
security:
  # Generate a secure secret key for production!
  secret_key: CHANGE_ME_IN_PRODUCTION
  token_expire_minutes: 60
  password_min_length: 8
YAML
}

# Install configuration template
# Returns: 0 on success
install_config_template() {
    log_info "Installing configuration files..."

    local config_file="$CONFIG_DIR/config.yaml"
    local config_backup=""

    # Ensure config directory exists
    mkdir -p "$CONFIG_DIR" || {
        log_error "Failed to create config directory: $CONFIG_DIR"
        return 4
    }

    # Check for existing configuration
    if [ -f "$config_file" ]; then
        log_info "Existing configuration found, creating backup..."
        config_backup="$(backup_file "$config_file")" || {
            log_error "Failed to backup existing configuration"
            return 4
        }

        # For now, preserve existing config (don't overwrite)
        log_info "Preserving existing configuration"
        log_info "New template saved to: ${config_file}.new"

        # Save new template alongside for reference
        _generate_default_config > "${config_file}.new"
        chown root:"$SERVICE_GROUP" "${config_file}.new"
        chmod 640 "${config_file}.new"
    else
        log_info "Creating default configuration..."

        # Generate default config
        _generate_default_config > "$config_file" || {
            log_error "Failed to write configuration file"
            return 4
        }
    fi

    # Set ownership and permissions
    chown root:"$SERVICE_GROUP" "$config_file"
    chmod 640 "$config_file"  # rw-r----- (sensitive data)

    # Create environment file for systemd
    local env_file="$CONFIG_DIR/environment"
    if [ ! -f "$env_file" ]; then
        log_debug "Creating environment file..."
        cat > "$env_file" << EOF
# Environment variables for Water-Controller service
# Loaded by systemd via EnvironmentFile directive

# Configuration path
CONFIG_PATH=$config_file

# Data paths
DATA_DIR=$DATA_DIR
LOG_DIR=$LOG_DIR

# Python settings
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1

# API settings (can override config.yaml)
# API_HOST=0.0.0.0
# API_PORT=8000
# API_WORKERS=2

# Database (can override config.yaml)
# DATABASE_URL=sqlite:///var/lib/water-controller/historian.db
EOF
        chown root:"$SERVICE_GROUP" "$env_file"
        chmod 640 "$env_file"
    fi

    # Create logging configuration if using YAML-based logging
    local logging_file="$CONFIG_DIR/logging.yaml"
    if [ ! -f "$logging_file" ]; then
        log_debug "Creating logging configuration..."
        cat > "$logging_file" << 'YAML'
# Logging configuration for Water-Controller
version: 1
disable_existing_loggers: false

formatters:
  standard:
    format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  detailed:
    format: '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'

handlers:
  console:
    class: logging.StreamHandler
    level: INFO
    formatter: standard
    stream: ext://sys.stdout

  file:
    class: logging.handlers.RotatingFileHandler
    level: DEBUG
    formatter: detailed
    filename: /var/log/water-controller/app.log
    maxBytes: 10485760  # 10MB
    backupCount: 5

root:
  level: INFO
  handlers: [console, file]

loggers:
  uvicorn:
    level: INFO
  uvicorn.error:
    level: INFO
  uvicorn.access:
    level: WARNING
  sqlalchemy:
    level: WARNING
YAML
        chown root:"$SERVICE_GROUP" "$logging_file"
        chmod 640 "$logging_file"
    fi

    # Copy ports.env if it exists in source
    local ports_env_src=""
    if [ -n "$SOURCE_DIR" ]; then
        if [ -f "$SOURCE_DIR/config/ports.env" ]; then
            ports_env_src="$SOURCE_DIR/config/ports.env"
        fi
    fi

    local ports_env_file="$CONFIG_DIR/ports.env"
    if [ -n "$ports_env_src" ] && [ -f "$ports_env_src" ]; then
        log_debug "Installing ports.env configuration..."
        cp "$ports_env_src" "$ports_env_file" || {
            log_warn "Failed to copy ports.env"
        }
        chown root:"$SERVICE_GROUP" "$ports_env_file"
        chmod 640 "$ports_env_file"
    elif [ ! -f "$ports_env_file" ]; then
        # Create minimal ports.env if not from source
        log_debug "Creating default ports.env..."
        cat > "$ports_env_file" << 'ENV'
# Water Treatment Controller - Port Configuration
# Centralized port definitions

# API Server (FastAPI)
WTC_API_PORT=8000

# HMI / Web UI (Next.js)
WTC_UI_PORT=8080

# PROFINET ports
WTC_PROFINET_UDP_PORT=34964
WTC_PROFINET_TCP_PORT_START=34962
WTC_PROFINET_TCP_PORT_END=34963

# Modbus TCP port (non-root)
WTC_MODBUS_TCP_PORT=1502

# Database port
WTC_DB_PORT=5432
ENV
        chown root:"$SERVICE_GROUP" "$ports_env_file"
        chmod 640 "$ports_env_file"
    fi

    log_info "Configuration files installed"
    _log_write "INFO" "Configuration installed to $CONFIG_DIR"

    return 0
}

# =============================================================================
# Combined Installation Function
# =============================================================================

# Run complete file installation
# Returns: 0 on success, 4 on failure
install_all_files() {
    log_info "Running complete file installation..."

    # Create service user
    create_service_user || {
        log_error "Failed to create service user"
        return 4
    }

    # Create directory structure
    create_directory_structure || {
        log_error "Failed to create directory structure"
        return 4
    }

    # Install Python application
    install_python_app || {
        log_error "Failed to install Python application"
        return 4
    }

    # Install frontend
    install_frontend || {
        log_warn "Frontend installation skipped or failed"
        # Don't fail completely if frontend is missing
    }

    # Install configuration
    install_config_template || {
        log_error "Failed to install configuration"
        return 4
    }

    log_info "File installation completed successfully"
    return 0
}

# =============================================================================
# Verification Function
# =============================================================================

# Verify installation
# Returns: 0 if OK, 4 if problems found
verify_file_installation() {
    log_info "Verifying file installation..."

    local failed=0
    local results=()

    # Check service user
    if id "$SERVICE_USER" >/dev/null 2>&1; then
        results+=("[OK] Service user: $SERVICE_USER")
    else
        results+=("[FAIL] Service user not found: $SERVICE_USER")
        failed=1
    fi

    # Check directories
    local dirs_to_check=(
        "$INSTALL_BASE"
        "$APP_PATH"
        "$CONFIG_DIR"
        "$DATA_DIR"
        "$LOG_DIR"
    )

    for dir in "${dirs_to_check[@]}"; do
        if [ -d "$dir" ]; then
            results+=("[OK] Directory: $dir")
        else
            results+=("[FAIL] Directory missing: $dir")
            failed=1
        fi
    done

    # Check config file
    if [ -f "$CONFIG_DIR/config.yaml" ]; then
        results+=("[OK] Config: $CONFIG_DIR/config.yaml")
    else
        results+=("[FAIL] Config missing: $CONFIG_DIR/config.yaml")
        failed=1
    fi

    # Check app files
    if [ -f "$APP_PATH/app/main.py" ] || [ -f "$APP_PATH/main.py" ]; then
        local py_count
        py_count="$(find "$APP_PATH" -name '*.py' | wc -l)"
        results+=("[OK] Python app: $py_count files")
    else
        results+=("[WARN] No main.py found in app directory")
    fi

    # Check venv
    if [ -x "$VENV_PATH/bin/python3" ]; then
        results+=("[OK] Python venv: $VENV_PATH")
    else
        results+=("[WARN] Python venv not found")
    fi

    # Check frontend
    if [ -d "$WEB_PATH" ] && [ "$(ls -A "$WEB_PATH" 2>/dev/null)" ]; then
        local web_count
        web_count="$(find "$WEB_PATH" -type f | wc -l)"
        results+=("[OK] Frontend: $web_count files")
    else
        results+=("[INFO] Frontend not installed")
    fi

    # Print results
    echo ""
    echo "FILE INSTALLATION VERIFICATION:"
    echo "================================"
    for check_result in "${results[@]}"; do
        echo "  $check_result"
    done
    echo "================================"
    echo ""

    if [ $failed -ne 0 ]; then
        log_error "File installation verification failed"
        return 4
    fi

    log_info "File installation verification passed"
    return 0
}

# =============================================================================
# Main Entry Point (when run directly)
# =============================================================================

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    # Initialize logging
    init_logging || {
        echo "[WARN] Logging initialization failed" >&2
    }

    case "${1:-}" in
        --create-user)
            create_service_user
            exit $?
            ;;
        --create-dirs)
            create_directory_structure
            exit $?
            ;;
        --install-app)
            if [ -z "$SOURCE_DIR" ]; then
                log_error "SOURCE_DIR not set"
                exit 1
            fi
            install_python_app
            exit $?
            ;;
        --install-frontend)
            if [ -z "$SOURCE_DIR" ]; then
                log_error "SOURCE_DIR not set"
                exit 1
            fi
            install_frontend
            exit $?
            ;;
        --install-config)
            install_config_template
            exit $?
            ;;
        --install-all)
            install_all_files
            exit $?
            ;;
        --verify)
            verify_file_installation
            exit $?
            ;;
        --help|-h)
            echo "Water-Controller File Installation Module v$INSTALL_FILES_VERSION"
            echo ""
            echo "Usage: $0 [OPTION]"
            echo ""
            echo "Options:"
            echo "  --create-user       Create service user and group"
            echo "  --create-dirs       Create directory structure"
            echo "  --install-app       Install Python application (requires SOURCE_DIR)"
            echo "  --install-frontend  Install frontend build (requires SOURCE_DIR)"
            echo "  --install-config    Install configuration templates"
            echo "  --install-all       Run complete installation"
            echo "  --verify            Verify file installation"
            echo "  --help, -h          Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  SOURCE_DIR          Source code directory"
            echo ""
            echo "Paths:"
            echo "  Install:  $INSTALL_BASE"
            echo "  Config:   $CONFIG_DIR"
            echo "  Data:     $DATA_DIR"
            echo "  Logs:     $LOG_DIR"
            ;;
        *)
            echo "Usage: $0 [--create-user|--create-dirs|--install-app|--install-frontend|--install-config|--install-all|--verify|--help]" >&2
            exit 1
            ;;
    esac
fi
