#!/bin/bash
# Water Treatment Controller - PostgreSQL Production Setup
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This script configures PostgreSQL for production use with TimescaleDB.

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-water_treatment}"
DB_USER="${DB_USER:-wtc}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/water-controller}"
DATA_RETENTION_DAYS="${DATA_RETENTION_DAYS:-365}"
REPLICATION_ENABLED="${REPLICATION_ENABLED:-false}"

print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}  PostgreSQL Production Setup${NC}"
    echo -e "${BLUE}============================================${NC}"
}

print_step() {
    echo -e "${GREEN}[*]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root"
        exit 1
    fi
}

generate_password() {
    openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32
}

install_timescaledb() {
    print_step "Checking TimescaleDB installation..."

    if ! command -v psql &>/dev/null; then
        print_step "Installing PostgreSQL..."

        # Detect OS
        if [[ -f /etc/debian_version ]]; then
            apt-get update
            apt-get install -y postgresql postgresql-contrib
        elif [[ -f /etc/redhat-release ]]; then
            yum install -y postgresql-server postgresql-contrib
            postgresql-setup --initdb
        fi
    fi

    # Add TimescaleDB repository
    if [[ -f /etc/debian_version ]]; then
        print_step "Adding TimescaleDB repository..."
        apt-get install -y gnupg postgresql-common apt-transport-https lsb-release wget

        # Add TimescaleDB APT repository
        echo "deb https://packagecloud.io/timescale/timescaledb/debian/ $(lsb_release -c -s) main" | tee /etc/apt/sources.list.d/timescaledb.list

        wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | apt-key add -

        apt-get update
        apt-get install -y timescaledb-2-postgresql-15 || apt-get install -y timescaledb-2-postgresql-14
    fi

    print_step "TimescaleDB installation complete"
}

configure_postgresql() {
    print_step "Configuring PostgreSQL for production..."

    # Find PostgreSQL configuration directory
    PG_CONF_DIR=$(find /etc/postgresql -name "postgresql.conf" -exec dirname {} \; 2>/dev/null | head -1)
    if [[ -z "$PG_CONF_DIR" ]]; then
        PG_CONF_DIR="/var/lib/pgsql/data"
    fi

    PG_CONF="$PG_CONF_DIR/postgresql.conf"
    PG_HBA="$PG_CONF_DIR/pg_hba.conf"

    if [[ ! -f "$PG_CONF" ]]; then
        print_error "PostgreSQL configuration not found at $PG_CONF"
        exit 1
    fi

    # Backup original configuration
    cp "$PG_CONF" "$PG_CONF.backup.$(date +%Y%m%d)"
    cp "$PG_HBA" "$PG_HBA.backup.$(date +%Y%m%d)"

    # Create production configuration
    cat >> "$PG_CONF" << 'EOF'

# ============================================
# Water Treatment Controller - Production Config
# ============================================

# Connection Settings
listen_addresses = '*'
max_connections = 200
superuser_reserved_connections = 3

# Memory Settings (adjust based on available RAM)
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 16MB
maintenance_work_mem = 128MB

# Checkpoint Settings
checkpoint_completion_target = 0.9
wal_buffers = 16MB
min_wal_size = 1GB
max_wal_size = 4GB

# Query Planner
random_page_cost = 1.1
effective_io_concurrency = 200

# Logging
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_rotation_age = 1d
log_rotation_size = 100MB
log_min_duration_statement = 1000
log_checkpoints = on
log_connections = on
log_disconnections = on
log_lock_waits = on
log_temp_files = 0

# TimescaleDB Settings
shared_preload_libraries = 'timescaledb'
timescaledb.max_background_workers = 8

# Autovacuum (important for TimescaleDB)
autovacuum = on
autovacuum_max_workers = 4
autovacuum_naptime = 30s
autovacuum_vacuum_threshold = 50
autovacuum_analyze_threshold = 50
EOF

    # Configure authentication
    cat >> "$PG_HBA" << EOF

# Water Treatment Controller connections
host    $DB_NAME    $DB_USER    0.0.0.0/0    scram-sha-256
hostssl $DB_NAME    $DB_USER    0.0.0.0/0    scram-sha-256
EOF

    print_step "PostgreSQL configuration updated"
}

create_database() {
    print_step "Creating production database..."

    # Generate secure password
    DB_PASSWORD=$(generate_password)

    # Store password securely
    mkdir -p /etc/water-controller
    chmod 700 /etc/water-controller

    cat > /etc/water-controller/database.env << EOF
# Database credentials - KEEP SECURE
# Generated on $(date)

DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
EOF

    chmod 600 /etc/water-controller/database.env

    # Restart PostgreSQL to apply config
    systemctl restart postgresql

    # Create user and database
    sudo -u postgres psql << EOF
-- Create user with secure password
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD' CREATEDB;

-- Create database
CREATE DATABASE $DB_NAME OWNER $DB_USER;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

-- Enable TimescaleDB
\c $DB_NAME
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
EOF

    print_step "Database created successfully"
    echo ""
    echo -e "${YELLOW}Database credentials saved to: /etc/water-controller/database.env${NC}"
    echo -e "${YELLOW}Password: $DB_PASSWORD${NC}"
    echo ""
    print_warning "Save this password securely - it will not be shown again!"
}

setup_ssl() {
    print_step "Setting up SSL for database connections..."

    SSL_DIR="/etc/postgresql/ssl"
    mkdir -p "$SSL_DIR"

    # Generate self-signed certificate (replace with proper cert in production)
    openssl req -new -x509 -days 365 -nodes \
        -out "$SSL_DIR/server.crt" \
        -keyout "$SSL_DIR/server.key" \
        -subj "/CN=water-controller-db"

    chmod 600 "$SSL_DIR/server.key"
    chown postgres:postgres "$SSL_DIR"/*

    # Update PostgreSQL config
    cat >> "$PG_CONF" << EOF

# SSL Configuration
ssl = on
ssl_cert_file = '$SSL_DIR/server.crt'
ssl_key_file = '$SSL_DIR/server.key'
EOF

    print_step "SSL configured"
}

configure_retention() {
    print_step "Configuring data retention policies..."

    sudo -u postgres psql -d "$DB_NAME" << EOF
-- Update retention policies
SELECT remove_retention_policy('historian_data', if_exists => true);
SELECT remove_retention_policy('alarm_history', if_exists => true);
SELECT remove_retention_policy('audit_log', if_exists => true);

SELECT add_retention_policy('historian_data', INTERVAL '$DATA_RETENTION_DAYS days');
SELECT add_retention_policy('alarm_history', INTERVAL '365 days');
SELECT add_retention_policy('audit_log', INTERVAL '730 days');

-- Create daily aggregation for long-term storage
CREATE MATERIALIZED VIEW IF NOT EXISTS historian_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    tag_id,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    FIRST(value, time) AS first_value,
    LAST(value, time) AS last_value,
    COUNT(*) AS sample_count
FROM historian_data
GROUP BY bucket, tag_id;

SELECT add_continuous_aggregate_policy('historian_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE);

-- Compress old data
SELECT add_compression_policy('historian_data', INTERVAL '7 days', if_not_exists => true);
SELECT add_compression_policy('alarm_history', INTERVAL '30 days', if_not_exists => true);
EOF

    print_step "Retention policies configured"
}

setup_monitoring() {
    print_step "Setting up database monitoring..."

    sudo -u postgres psql -d "$DB_NAME" << 'EOF'
-- Create monitoring views
CREATE OR REPLACE VIEW db_stats AS
SELECT
    pg_database_size(current_database()) as database_size,
    (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) as active_connections,
    (SELECT count(*) FROM historian_data WHERE time > NOW() - INTERVAL '1 hour') as samples_last_hour,
    (SELECT count(*) FROM alarm_history WHERE state = 'ACTIVE_UNACK') as active_alarms;

-- Create function to get hypertable stats
CREATE OR REPLACE FUNCTION get_hypertable_stats()
RETURNS TABLE(
    hypertable_name TEXT,
    total_size TEXT,
    num_chunks BIGINT,
    compression_ratio FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        h.hypertable_name::TEXT,
        pg_size_pretty(hypertable_size(h.hypertable_name))::TEXT,
        (SELECT count(*) FROM timescaledb_information.chunks c WHERE c.hypertable_name = h.hypertable_name),
        COALESCE(
            (SELECT 1.0 - (compressed_bytes::FLOAT / uncompressed_bytes::FLOAT)
             FROM hypertable_compression_stats(h.hypertable_name)
             WHERE uncompressed_bytes > 0
             LIMIT 1),
            0.0
        )
    FROM timescaledb_information.hypertables h;
END;
$$ LANGUAGE plpgsql;
EOF

    print_step "Monitoring views created"
}

print_summary() {
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  PostgreSQL Production Setup Complete${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "Database: $DB_NAME"
    echo "User: $DB_USER"
    echo "Host: $DB_HOST:$DB_PORT"
    echo ""
    echo "Configuration files:"
    echo "  - /etc/water-controller/database.env"
    echo "  - $PG_CONF"
    echo "  - $PG_HBA"
    echo ""
    echo "Data retention: $DATA_RETENTION_DAYS days"
    echo ""
    echo "To connect:"
    echo "  source /etc/water-controller/database.env"
    echo "  psql \$DATABASE_URL"
    echo ""
    echo "To check database status:"
    echo "  sudo -u postgres psql -d $DB_NAME -c 'SELECT * FROM db_stats;'"
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --install-timescaledb    Install TimescaleDB extension"
    echo "  --configure-only         Only update configuration, don't create database"
    echo "  --retention-days N       Set data retention period (default: 365)"
    echo "  --enable-ssl             Enable SSL connections"
    echo "  --help                   Show this help"
    echo ""
    echo "Environment variables:"
    echo "  DB_HOST, DB_PORT, DB_NAME, DB_USER"
}

# Parse arguments
INSTALL_TIMESCALEDB=false
CONFIGURE_ONLY=false
ENABLE_SSL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --install-timescaledb)
            INSTALL_TIMESCALEDB=true
            shift
            ;;
        --configure-only)
            CONFIGURE_ONLY=true
            shift
            ;;
        --retention-days)
            DATA_RETENTION_DAYS="$2"
            shift 2
            ;;
        --enable-ssl)
            ENABLE_SSL=true
            shift
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Main execution
print_header
check_root

if [[ "$INSTALL_TIMESCALEDB" == "true" ]]; then
    install_timescaledb
fi

configure_postgresql

if [[ "$ENABLE_SSL" == "true" ]]; then
    setup_ssl
fi

if [[ "$CONFIGURE_ONLY" != "true" ]]; then
    create_database
fi

configure_retention
setup_monitoring

# Restart PostgreSQL
systemctl restart postgresql

print_summary
