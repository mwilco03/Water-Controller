#!/bin/bash
# Water Treatment Controller - Backup Automation Script
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This script automates backups of the Water Treatment Controller system.
# Install as a cron job or systemd timer for automated backups.

set -e

# Configuration
BACKUP_BASE_DIR="${BACKUP_BASE_DIR:-/var/backups/water-controller}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
REMOTE_BACKUP_ENABLED="${REMOTE_BACKUP_ENABLED:-false}"
REMOTE_BACKUP_PATH="${REMOTE_BACKUP_PATH:-}"
ENCRYPT_BACKUPS="${ENCRYPT_BACKUPS:-false}"
ENCRYPTION_KEY="${ENCRYPTION_KEY:-}"

# Database settings (from environment or config file)
if [[ -f /etc/water-controller/database.env ]]; then
    source /etc/water-controller/database.env
fi

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-water_treatment}"
DB_USER="${DB_USER:-wtc}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging
LOG_FILE="/var/log/water-controller/backup.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

log_info() {
    log "INFO" "$@"
}

log_error() {
    log "ERROR" "$@"
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_success() {
    log "SUCCESS" "$@"
    echo -e "${GREEN}[OK]${NC} $*"
}

# Create backup directories
setup_directories() {
    mkdir -p "$BACKUP_BASE_DIR"/{database,config,historian,daily,weekly,monthly}
    chmod 700 "$BACKUP_BASE_DIR"
}

# Generate backup filename
get_backup_filename() {
    local type=$1
    local date=$(date '+%Y%m%d_%H%M%S')
    echo "wtc_${type}_${date}"
}

# Backup PostgreSQL database
backup_database() {
    log_info "Starting database backup..."

    local backup_file="$BACKUP_BASE_DIR/database/$(get_backup_filename 'db').sql.gz"

    if [[ -n "$DB_PASSWORD" ]]; then
        export PGPASSWORD="$DB_PASSWORD"
    fi

    # Full database dump with compression
    pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --format=custom \
        --compress=9 \
        --file="${backup_file%.gz}" \
        --verbose 2>&1 | tee -a "$LOG_FILE"

    # Compress if using plain format
    if [[ -f "${backup_file%.gz}" ]]; then
        gzip "${backup_file%.gz}"
    fi

    unset PGPASSWORD

    if [[ -f "$backup_file" ]]; then
        local size=$(du -h "$backup_file" | cut -f1)
        log_success "Database backup complete: $backup_file ($size)"
        echo "$backup_file"
    else
        log_error "Database backup failed"
        return 1
    fi
}

# Backup TimescaleDB continuous aggregates
backup_timescaledb_aggregates() {
    log_info "Backing up TimescaleDB aggregates..."

    local backup_file="$BACKUP_BASE_DIR/historian/$(get_backup_filename 'aggregates').sql.gz"

    if [[ -n "$DB_PASSWORD" ]]; then
        export PGPASSWORD="$DB_PASSWORD"
    fi

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
        SELECT timescaledb_pre_restore();
    " 2>/dev/null || true

    # Dump continuous aggregates
    pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --table='historian_hourly' \
        --table='historian_daily' \
        --format=plain \
        | gzip > "$backup_file"

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
        SELECT timescaledb_post_restore();
    " 2>/dev/null || true

    unset PGPASSWORD

    log_success "Aggregates backup complete: $backup_file"
}

# Backup configuration files
backup_config() {
    log_info "Starting configuration backup..."

    local backup_file="$BACKUP_BASE_DIR/config/$(get_backup_filename 'config').tar.gz"

    # Create tarball of configuration
    tar -czf "$backup_file" \
        -C / \
        --exclude='*.key' \
        --exclude='*.pem' \
        etc/water-controller 2>/dev/null || true

    # Add docker config if exists
    if [[ -d /opt/water-controller/docker/config ]]; then
        tar -rf "${backup_file%.gz}" \
            -C /opt/water-controller \
            docker/config 2>/dev/null || true
        gzip -f "${backup_file%.gz}"
    fi

    if [[ -f "$backup_file" ]]; then
        local size=$(du -h "$backup_file" | cut -f1)
        log_success "Configuration backup complete: $backup_file ($size)"
        echo "$backup_file"
    else
        log_error "Configuration backup failed"
        return 1
    fi
}

# Backup historian data (incremental)
backup_historian_incremental() {
    local days="${1:-1}"
    log_info "Starting incremental historian backup (last $days days)..."

    local backup_file="$BACKUP_BASE_DIR/historian/$(get_backup_filename 'historian_incr').csv.gz"

    if [[ -n "$DB_PASSWORD" ]]; then
        export PGPASSWORD="$DB_PASSWORD"
    fi

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
        COPY (
            SELECT h.time, t.tag_name, h.value, h.quality
            FROM historian_data h
            JOIN historian_tags t ON h.tag_id = t.id
            WHERE h.time > NOW() - INTERVAL '$days days'
            ORDER BY h.time
        ) TO STDOUT WITH CSV HEADER
    " | gzip > "$backup_file"

    unset PGPASSWORD

    local size=$(du -h "$backup_file" | cut -f1)
    log_success "Historian incremental backup complete: $backup_file ($size)"
    echo "$backup_file"
}

# Encrypt backup file
encrypt_backup() {
    local file=$1

    if [[ "$ENCRYPT_BACKUPS" != "true" ]]; then
        echo "$file"
        return
    fi

    if [[ -z "$ENCRYPTION_KEY" ]]; then
        log_error "Encryption enabled but no key provided"
        return 1
    fi

    local encrypted_file="${file}.enc"

    openssl enc -aes-256-cbc \
        -salt \
        -in "$file" \
        -out "$encrypted_file" \
        -pass pass:"$ENCRYPTION_KEY"

    rm -f "$file"
    log_info "Backup encrypted: $encrypted_file"
    echo "$encrypted_file"
}

# Upload to remote storage
upload_remote() {
    local file=$1

    if [[ "$REMOTE_BACKUP_ENABLED" != "true" ]]; then
        return
    fi

    if [[ -z "$REMOTE_BACKUP_PATH" ]]; then
        log_error "Remote backup enabled but no path configured"
        return 1
    fi

    log_info "Uploading to remote storage: $REMOTE_BACKUP_PATH"

    # Detect remote type and upload
    if [[ "$REMOTE_BACKUP_PATH" == s3://* ]]; then
        # AWS S3
        aws s3 cp "$file" "$REMOTE_BACKUP_PATH/$(basename "$file")"
    elif [[ "$REMOTE_BACKUP_PATH" == gs://* ]]; then
        # Google Cloud Storage
        gsutil cp "$file" "$REMOTE_BACKUP_PATH/$(basename "$file")"
    elif [[ "$REMOTE_BACKUP_PATH" == *:* ]]; then
        # SCP/rsync
        rsync -avz "$file" "$REMOTE_BACKUP_PATH/"
    else
        # Local path
        cp "$file" "$REMOTE_BACKUP_PATH/"
    fi

    log_success "Remote upload complete"
}

# Clean old backups
cleanup_old_backups() {
    log_info "Cleaning up old backups (retention: $BACKUP_RETENTION_DAYS days)..."

    find "$BACKUP_BASE_DIR/database" -name "*.sql*" -mtime +$BACKUP_RETENTION_DAYS -delete
    find "$BACKUP_BASE_DIR/config" -name "*.tar*" -mtime +$BACKUP_RETENTION_DAYS -delete
    find "$BACKUP_BASE_DIR/historian" -name "*_incr*" -mtime +7 -delete

    log_success "Cleanup complete"
}

# Rotate backups (daily -> weekly -> monthly)
rotate_backups() {
    log_info "Rotating backups..."

    local today=$(date +%u)  # Day of week (1-7, Monday is 1)
    local day_of_month=$(date +%d)

    # Copy to weekly on Sunday
    if [[ "$today" == "7" ]]; then
        local latest_daily=$(ls -t "$BACKUP_BASE_DIR/database/"*.sql* 2>/dev/null | head -1)
        if [[ -n "$latest_daily" ]]; then
            cp "$latest_daily" "$BACKUP_BASE_DIR/weekly/"
            log_info "Weekly backup created"
        fi
    fi

    # Copy to monthly on 1st of month
    if [[ "$day_of_month" == "01" ]]; then
        local latest_daily=$(ls -t "$BACKUP_BASE_DIR/database/"*.sql* 2>/dev/null | head -1)
        if [[ -n "$latest_daily" ]]; then
            cp "$latest_daily" "$BACKUP_BASE_DIR/monthly/"
            log_info "Monthly backup created"
        fi
    fi

    # Keep only last 4 weekly backups
    find "$BACKUP_BASE_DIR/weekly" -name "*.sql*" -mtime +28 -delete

    # Keep only last 12 monthly backups
    find "$BACKUP_BASE_DIR/monthly" -name "*.sql*" -mtime +365 -delete
}

# Full backup routine
full_backup() {
    log_info "Starting full backup..."
    local start_time=$(date +%s)

    setup_directories

    # Backup all components
    local db_file=$(backup_database)
    local config_file=$(backup_config)
    backup_timescaledb_aggregates

    # Encrypt if enabled
    if [[ "$ENCRYPT_BACKUPS" == "true" ]]; then
        db_file=$(encrypt_backup "$db_file")
        config_file=$(encrypt_backup "$config_file")
    fi

    # Upload to remote
    upload_remote "$db_file"
    upload_remote "$config_file"

    # Rotate backups
    rotate_backups

    # Cleanup
    cleanup_old_backups

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log_success "Full backup complete in ${duration}s"
}

# Incremental backup routine
incremental_backup() {
    log_info "Starting incremental backup..."

    setup_directories

    local hist_file=$(backup_historian_incremental 1)

    if [[ "$ENCRYPT_BACKUPS" == "true" ]]; then
        hist_file=$(encrypt_backup "$hist_file")
    fi

    upload_remote "$hist_file"

    log_success "Incremental backup complete"
}

# Restore from backup
restore_backup() {
    local backup_file=$1

    if [[ ! -f "$backup_file" ]]; then
        log_error "Backup file not found: $backup_file"
        exit 1
    fi

    log_info "Restoring from backup: $backup_file"

    # Decrypt if needed
    if [[ "$backup_file" == *.enc ]]; then
        if [[ -z "$ENCRYPTION_KEY" ]]; then
            log_error "Encrypted backup requires ENCRYPTION_KEY"
            exit 1
        fi

        local decrypted_file="${backup_file%.enc}"
        openssl enc -aes-256-cbc -d \
            -in "$backup_file" \
            -out "$decrypted_file" \
            -pass pass:"$ENCRYPTION_KEY"
        backup_file="$decrypted_file"
    fi

    if [[ -n "$DB_PASSWORD" ]]; then
        export PGPASSWORD="$DB_PASSWORD"
    fi

    # Restore database
    if [[ "$backup_file" == *.sql* ]]; then
        log_info "Restoring database..."

        # Terminate existing connections
        psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c "
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();
        " 2>/dev/null || true

        # Drop and recreate database
        psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c "DROP DATABASE IF EXISTS ${DB_NAME}_restore;"
        psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c "CREATE DATABASE ${DB_NAME}_restore OWNER $DB_USER;"

        # Restore
        if [[ "$backup_file" == *.gz ]]; then
            gunzip -c "$backup_file" | pg_restore \
                -h "$DB_HOST" \
                -p "$DB_PORT" \
                -U "$DB_USER" \
                -d "${DB_NAME}_restore" \
                --no-owner \
                --no-privileges \
                --verbose
        else
            pg_restore \
                -h "$DB_HOST" \
                -p "$DB_PORT" \
                -U "$DB_USER" \
                -d "${DB_NAME}_restore" \
                --no-owner \
                --no-privileges \
                --verbose \
                "$backup_file"
        fi

        log_success "Database restored to ${DB_NAME}_restore"
        log_info "To switch to restored database, run:"
        log_info "  psql -U postgres -c 'ALTER DATABASE $DB_NAME RENAME TO ${DB_NAME}_old;'"
        log_info "  psql -U postgres -c 'ALTER DATABASE ${DB_NAME}_restore RENAME TO $DB_NAME;'"
    fi

    unset PGPASSWORD
}

# List available backups
list_backups() {
    echo -e "${BLUE}Available Backups:${NC}"
    echo ""

    echo "Database backups:"
    ls -lh "$BACKUP_BASE_DIR/database/"*.sql* 2>/dev/null || echo "  (none)"
    echo ""

    echo "Configuration backups:"
    ls -lh "$BACKUP_BASE_DIR/config/"*.tar* 2>/dev/null || echo "  (none)"
    echo ""

    echo "Weekly backups:"
    ls -lh "$BACKUP_BASE_DIR/weekly/"*.sql* 2>/dev/null || echo "  (none)"
    echo ""

    echo "Monthly backups:"
    ls -lh "$BACKUP_BASE_DIR/monthly/"*.sql* 2>/dev/null || echo "  (none)"
}

# Verify backup integrity
verify_backup() {
    local backup_file=$1

    if [[ ! -f "$backup_file" ]]; then
        log_error "Backup file not found: $backup_file"
        return 1
    fi

    log_info "Verifying backup: $backup_file"

    if [[ "$backup_file" == *.gz ]]; then
        if gzip -t "$backup_file" 2>/dev/null; then
            log_success "Backup integrity verified (gzip OK)"
        else
            log_error "Backup corrupted (gzip check failed)"
            return 1
        fi
    fi

    if [[ "$backup_file" == *.sql* ]]; then
        # Check if it's a valid PostgreSQL dump
        if zcat "$backup_file" 2>/dev/null | head -1 | grep -q "PostgreSQL"; then
            log_success "Backup format verified (PostgreSQL dump)"
        fi
    fi
}

# Install cron job
install_cron() {
    log_info "Installing backup cron jobs..."

    local script_path=$(readlink -f "$0")

    cat > /etc/cron.d/water-controller-backup << EOF
# Water Treatment Controller - Automated Backups
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Daily full backup at 2:00 AM
0 2 * * * root $script_path full >> /var/log/water-controller/backup-cron.log 2>&1

# Incremental historian backup every 4 hours
0 */4 * * * root $script_path incremental >> /var/log/water-controller/backup-cron.log 2>&1
EOF

    chmod 644 /etc/cron.d/water-controller-backup
    log_success "Cron jobs installed at /etc/cron.d/water-controller-backup"
}

# Show usage
usage() {
    echo "Usage: $0 COMMAND [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  full            Run full backup (database + config)"
    echo "  incremental     Run incremental historian backup"
    echo "  restore FILE    Restore from backup file"
    echo "  list            List available backups"
    echo "  verify FILE     Verify backup integrity"
    echo "  install-cron    Install automated backup cron jobs"
    echo "  cleanup         Clean old backups"
    echo ""
    echo "Environment variables:"
    echo "  BACKUP_BASE_DIR         Base directory for backups"
    echo "  BACKUP_RETENTION_DAYS   Days to keep backups (default: 30)"
    echo "  REMOTE_BACKUP_ENABLED   Enable remote upload (true/false)"
    echo "  REMOTE_BACKUP_PATH      Remote path (s3://, gs://, or rsync path)"
    echo "  ENCRYPT_BACKUPS         Encrypt backups (true/false)"
    echo "  ENCRYPTION_KEY          Encryption password"
}

# Main
case "${1:-}" in
    full)
        full_backup
        ;;
    incremental)
        incremental_backup
        ;;
    restore)
        restore_backup "$2"
        ;;
    list)
        list_backups
        ;;
    verify)
        verify_backup "$2"
        ;;
    install-cron)
        install_cron
        ;;
    cleanup)
        cleanup_old_backups
        ;;
    *)
        usage
        exit 1
        ;;
esac
