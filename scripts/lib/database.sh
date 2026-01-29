#!/bin/bash
#
# Water Treatment Controller - Database Installation Module
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module provides PostgreSQL/TimescaleDB installation, configuration,
# user creation, and database initialization for bare-metal deployments.
#
# Target: ARM/x86 SBCs running Debian-based Linux
#

# Prevent multiple sourcing
if [ -n "${_WTC_DATABASE_LOADED:-}" ]; then
    return 0
fi
_WTC_DATABASE_LOADED=1

# Source detection module for logging functions
: "${SCRIPT_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
if [ -f "$SCRIPT_DIR/detection.sh" ]; then
    # shellcheck source=detection.sh
    source "$SCRIPT_DIR/detection.sh"
fi

# =============================================================================
# Constants
# =============================================================================

readonly DATABASE_MODULE_VERSION="1.0.0"

# Database credentials - hardcoded by design (see CLAUDE.md)
readonly DB_NAME="water_treatment"
readonly DB_USER="wtc"
readonly DB_PASSWORD="wtc_password"
readonly DB_HOST="localhost"
readonly DB_PORT="${WTC_DB_PORT:-5432}"

# PostgreSQL version preference
readonly PG_VERSION_PREFERRED=15
readonly PG_VERSION_MINIMUM=14

# =============================================================================
# Detection Functions
# =============================================================================

# Check if PostgreSQL is installed
is_postgres_installed() {
    command -v psql >/dev/null 2>&1
}

# Check if PostgreSQL service is running
is_postgres_running() {
    if command -v systemctl >/dev/null 2>&1; then
        systemctl is-active --quiet postgresql 2>/dev/null || \
        systemctl is-active --quiet postgresql@* 2>/dev/null
    elif command -v service >/dev/null 2>&1; then
        service postgresql status >/dev/null 2>&1
    else
        pgrep -x postgres >/dev/null 2>&1
    fi
}

# Get installed PostgreSQL version
get_postgres_version() {
    if is_postgres_installed; then
        psql --version 2>/dev/null | grep -oP '\d+' | head -1
    fi
}

# Check if TimescaleDB extension is available
is_timescaledb_available() {
    if is_postgres_running; then
        sudo -u postgres psql -tAc "SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb';" 2>/dev/null | grep -q "1"
    else
        return 1
    fi
}

# Check if database exists
database_exists() {
    local db_name="${1:-$DB_NAME}"
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$db_name';" 2>/dev/null | grep -q "1"
}

# Check if user exists
db_user_exists() {
    local user="${1:-$DB_USER}"
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$user';" 2>/dev/null | grep -q "1"
}

# =============================================================================
# Installation Functions
# =============================================================================

# Install PostgreSQL
install_postgresql() {
    log_info "Installing PostgreSQL..."

    if is_postgres_installed; then
        local pg_version
        pg_version=$(get_postgres_version)
        log_info "PostgreSQL $pg_version is already installed"

        if [ "$pg_version" -lt "$PG_VERSION_MINIMUM" ]; then
            log_warn "PostgreSQL version $pg_version is below minimum ($PG_VERSION_MINIMUM)"
            log_warn "Consider upgrading for best compatibility"
        fi
        return 0
    fi

    # Detect package manager
    if command -v apt-get >/dev/null 2>&1; then
        _install_postgresql_apt
    elif command -v dnf >/dev/null 2>&1; then
        _install_postgresql_dnf
    elif command -v yum >/dev/null 2>&1; then
        _install_postgresql_yum
    else
        log_error "Unsupported package manager. Install PostgreSQL manually."
        return 1
    fi
}

# Install PostgreSQL on Debian/Ubuntu
_install_postgresql_apt() {
    log_info "Installing PostgreSQL via apt..."

    # Update package list
    apt-get update -qq || {
        log_error "apt-get update failed"
        return 1
    }

    # Try to install preferred version first
    local pg_pkg="postgresql-${PG_VERSION_PREFERRED}"
    if apt-cache show "$pg_pkg" >/dev/null 2>&1; then
        log_info "Installing PostgreSQL $PG_VERSION_PREFERRED..."
        DEBIAN_FRONTEND=noninteractive apt-get install -y \
            "$pg_pkg" \
            "postgresql-contrib-${PG_VERSION_PREFERRED}" \
            libpq-dev || {
            log_warn "Failed to install PostgreSQL $PG_VERSION_PREFERRED, trying default..."
        }
    fi

    # Fall back to default PostgreSQL package
    if ! is_postgres_installed; then
        log_info "Installing default PostgreSQL version..."
        DEBIAN_FRONTEND=noninteractive apt-get install -y \
            postgresql \
            postgresql-contrib \
            libpq-dev || {
            log_error "Failed to install PostgreSQL"
            return 1
        }
    fi

    # Start PostgreSQL service
    systemctl start postgresql || {
        log_error "Failed to start PostgreSQL service"
        return 1
    }

    systemctl enable postgresql || {
        log_warn "Failed to enable PostgreSQL service at boot"
    }

    log_info "PostgreSQL installed successfully"
    return 0
}

# Install PostgreSQL on RHEL/CentOS/Fedora
_install_postgresql_dnf() {
    log_info "Installing PostgreSQL via dnf..."

    dnf install -y postgresql-server postgresql-contrib || {
        log_error "Failed to install PostgreSQL"
        return 1
    }

    # Initialize database cluster
    postgresql-setup --initdb 2>/dev/null || {
        log_warn "Database cluster may already be initialized"
    }

    # Start and enable service
    systemctl start postgresql || {
        log_error "Failed to start PostgreSQL"
        return 1
    }
    systemctl enable postgresql

    log_info "PostgreSQL installed successfully"
    return 0
}

# Install PostgreSQL on older RHEL/CentOS
_install_postgresql_yum() {
    log_info "Installing PostgreSQL via yum..."

    yum install -y postgresql-server postgresql-contrib || {
        log_error "Failed to install PostgreSQL"
        return 1
    }

    # Initialize database cluster
    postgresql-setup initdb 2>/dev/null || {
        log_warn "Database cluster may already be initialized"
    }

    # Start and enable service
    systemctl start postgresql || {
        log_error "Failed to start PostgreSQL"
        return 1
    }
    systemctl enable postgresql

    log_info "PostgreSQL installed successfully"
    return 0
}

# Install TimescaleDB extension
install_timescaledb() {
    log_info "Installing TimescaleDB extension..."

    if is_timescaledb_available; then
        log_info "TimescaleDB is already available"
        return 0
    fi

    local pg_version
    pg_version=$(get_postgres_version)

    if [ -z "$pg_version" ]; then
        log_error "Cannot determine PostgreSQL version"
        return 1
    fi

    if command -v apt-get >/dev/null 2>&1; then
        _install_timescaledb_apt "$pg_version"
    elif command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then
        _install_timescaledb_rpm "$pg_version"
    else
        log_error "Unsupported package manager for TimescaleDB"
        return 1
    fi
}

# Install TimescaleDB on Debian/Ubuntu
_install_timescaledb_apt() {
    local pg_version="$1"
    log_info "Adding TimescaleDB repository..."

    # Install prerequisites
    apt-get install -y gnupg apt-transport-https lsb-release wget || {
        log_error "Failed to install prerequisites"
        return 1
    }

    # Add TimescaleDB repository
    local distro
    distro=$(lsb_release -cs 2>/dev/null || echo "bookworm")

    # Add GPG key
    wget -qO - https://packagecloud.io/timescale/timescaledb/gpgkey 2>/dev/null | \
        gpg --dearmor -o /usr/share/keyrings/timescaledb-archive-keyring.gpg 2>/dev/null || {
        # Fallback to apt-key for older systems
        wget -qO - https://packagecloud.io/timescale/timescaledb/gpgkey 2>/dev/null | apt-key add - 2>/dev/null
    }

    # Add repository
    echo "deb [signed-by=/usr/share/keyrings/timescaledb-archive-keyring.gpg] https://packagecloud.io/timescale/timescaledb/debian/ $distro main" | \
        tee /etc/apt/sources.list.d/timescaledb.list >/dev/null 2>&1 || \
    echo "deb https://packagecloud.io/timescale/timescaledb/debian/ $distro main" | \
        tee /etc/apt/sources.list.d/timescaledb.list >/dev/null

    # Update and install
    apt-get update -qq || {
        log_warn "apt update had issues, continuing..."
    }

    # Try to install TimescaleDB for the installed PostgreSQL version
    local ts_pkg="timescaledb-2-postgresql-${pg_version}"
    if apt-cache show "$ts_pkg" >/dev/null 2>&1; then
        DEBIAN_FRONTEND=noninteractive apt-get install -y "$ts_pkg" || {
            log_warn "Failed to install $ts_pkg"
        }
    fi

    # Fallback: try other versions
    if ! is_timescaledb_available; then
        for ver in 15 14 16; do
            ts_pkg="timescaledb-2-postgresql-${ver}"
            if apt-cache show "$ts_pkg" >/dev/null 2>&1; then
                log_info "Trying $ts_pkg..."
                DEBIAN_FRONTEND=noninteractive apt-get install -y "$ts_pkg" 2>/dev/null && break
            fi
        done
    fi

    # Configure PostgreSQL to load TimescaleDB
    _configure_timescaledb_preload

    # Restart PostgreSQL to load extension
    systemctl restart postgresql || {
        log_warn "Failed to restart PostgreSQL"
    }

    if is_timescaledb_available; then
        log_info "TimescaleDB installed successfully"
        return 0
    else
        log_warn "TimescaleDB installation may have issues - continuing anyway"
        return 0
    fi
}

# Install TimescaleDB on RHEL/CentOS/Fedora
_install_timescaledb_rpm() {
    local pg_version="$1"
    log_info "Adding TimescaleDB repository for RPM..."

    # Add TimescaleDB repository
    cat > /etc/yum.repos.d/timescaledb.repo << 'EOF'
[timescaledb]
name=TimescaleDB Repository
baseurl=https://packagecloud.io/timescale/timescaledb/el/8/$basearch
gpgcheck=0
enabled=1
EOF

    # Install TimescaleDB
    if command -v dnf >/dev/null 2>&1; then
        dnf install -y "timescaledb-2-postgresql-${pg_version}" 2>/dev/null || \
            dnf install -y timescaledb-2-postgresql-14 2>/dev/null
    else
        yum install -y "timescaledb-2-postgresql-${pg_version}" 2>/dev/null || \
            yum install -y timescaledb-2-postgresql-14 2>/dev/null
    fi

    _configure_timescaledb_preload
    systemctl restart postgresql

    return 0
}

# Configure postgresql.conf to preload TimescaleDB
_configure_timescaledb_preload() {
    log_debug "Configuring TimescaleDB preload..."

    # Find postgresql.conf
    local pg_conf
    pg_conf=$(find /etc/postgresql -name "postgresql.conf" 2>/dev/null | head -1)

    if [ -z "$pg_conf" ]; then
        pg_conf=$(find /var/lib/pgsql -name "postgresql.conf" 2>/dev/null | head -1)
    fi

    if [ -z "$pg_conf" ]; then
        log_warn "Could not find postgresql.conf"
        return 1
    fi

    # Check if already configured
    if grep -q "shared_preload_libraries.*timescaledb" "$pg_conf" 2>/dev/null; then
        log_debug "TimescaleDB already in shared_preload_libraries"
        return 0
    fi

    # Backup config
    cp "$pg_conf" "${pg_conf}.backup.$(date +%Y%m%d)" 2>/dev/null

    # Add TimescaleDB to shared_preload_libraries
    if grep -q "^shared_preload_libraries" "$pg_conf" 2>/dev/null; then
        # Append to existing
        sed -i "s/^shared_preload_libraries = '\(.*\)'/shared_preload_libraries = '\1,timescaledb'/" "$pg_conf"
    else
        # Add new line
        echo "shared_preload_libraries = 'timescaledb'" >> "$pg_conf"
    fi

    log_debug "TimescaleDB added to shared_preload_libraries"
    return 0
}

# =============================================================================
# Database Setup Functions
# =============================================================================

# Create database user
create_db_user() {
    local user="${1:-$DB_USER}"
    local password="${2:-$DB_PASSWORD}"

    log_info "Creating database user: $user"

    if db_user_exists "$user"; then
        log_info "User $user already exists"
        # Update password just in case
        sudo -u postgres psql -c "ALTER USER $user WITH PASSWORD '$password';" 2>/dev/null || {
            log_warn "Could not update user password"
        }
        return 0
    fi

    sudo -u postgres psql -c "CREATE USER $user WITH PASSWORD '$password';" || {
        log_error "Failed to create database user"
        return 1
    }

    log_info "Database user $user created"
    return 0
}

# Create database
create_database() {
    local db_name="${1:-$DB_NAME}"
    local owner="${2:-$DB_USER}"

    log_info "Creating database: $db_name"

    if database_exists "$db_name"; then
        log_info "Database $db_name already exists"
        return 0
    fi

    sudo -u postgres psql -c "CREATE DATABASE $db_name OWNER $owner;" || {
        log_error "Failed to create database"
        return 1
    }

    log_info "Database $db_name created"
    return 0
}

# Initialize database schema from init.sql
initialize_database_schema() {
    log_info "Initializing database schema..."

    # Find init.sql
    local init_sql=""
    local search_paths=(
        "${SOURCE_DIR:-}/docker/init.sql"
        "${INSTALL_DIR:-/opt/water-controller}/docker/init.sql"
        "/opt/water-controller/docker/init.sql"
        "${SCRIPT_DIR}/../../docker/init.sql"
    )

    for path in "${search_paths[@]}"; do
        if [ -f "$path" ]; then
            init_sql="$path"
            break
        fi
    done

    if [ -z "$init_sql" ]; then
        log_error "init.sql not found. Searched: ${search_paths[*]}"
        return 1
    fi

    log_info "Using schema from: $init_sql"

    # Run init.sql as the database owner
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$init_sql" 2>&1 | \
        while read -r line; do
            # Filter out noise, keep important messages
            if echo "$line" | grep -qiE "(error|fail|warning)"; then
                log_warn "$line"
            else
                log_debug "$line"
            fi
        done

    # Verify schema was created
    local table_count
    table_count=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null)

    if [ -z "$table_count" ] || [ "$table_count" -lt 5 ]; then
        log_warn "Schema initialization may have issues (only $table_count tables found)"
    else
        log_info "Database schema initialized ($table_count tables)"
    fi

    return 0
}

# Configure pg_hba.conf for local authentication
configure_pg_hba() {
    log_info "Configuring PostgreSQL authentication..."

    # Find pg_hba.conf
    local pg_hba
    pg_hba=$(find /etc/postgresql -name "pg_hba.conf" 2>/dev/null | head -1)

    if [ -z "$pg_hba" ]; then
        pg_hba=$(find /var/lib/pgsql -name "pg_hba.conf" 2>/dev/null | head -1)
    fi

    if [ -z "$pg_hba" ]; then
        log_warn "Could not find pg_hba.conf"
        return 1
    fi

    # Check if wtc user entry already exists
    if grep -q "^local.*${DB_NAME}.*${DB_USER}" "$pg_hba" 2>/dev/null; then
        log_debug "pg_hba.conf already configured for $DB_USER"
        return 0
    fi

    # Backup
    cp "$pg_hba" "${pg_hba}.backup.$(date +%Y%m%d)" 2>/dev/null

    # Add entries for wtc user (insert before the first existing rule)
    local temp_file
    temp_file=$(mktemp)

    {
        echo "# Water Treatment Controller access rules"
        echo "local   $DB_NAME    $DB_USER                                md5"
        echo "host    $DB_NAME    $DB_USER    127.0.0.1/32            md5"
        echo "host    $DB_NAME    $DB_USER    ::1/128                 md5"
        echo ""
        cat "$pg_hba"
    } > "$temp_file"

    mv "$temp_file" "$pg_hba"
    chown postgres:postgres "$pg_hba"
    chmod 640 "$pg_hba"

    # Reload PostgreSQL to apply changes
    systemctl reload postgresql 2>/dev/null || \
        sudo -u postgres pg_ctl reload -D "$(dirname "$pg_hba")" 2>/dev/null || true

    log_info "PostgreSQL authentication configured"
    return 0
}

# =============================================================================
# Main Setup Function
# =============================================================================

# Complete database setup
setup_database() {
    log_info "Starting database setup..."

    # Step 1: Install PostgreSQL if needed
    if ! is_postgres_installed; then
        install_postgresql || {
            log_error "PostgreSQL installation failed"
            return 1
        }
    fi

    # Step 2: Ensure PostgreSQL is running
    if ! is_postgres_running; then
        log_info "Starting PostgreSQL service..."
        systemctl start postgresql || {
            log_error "Failed to start PostgreSQL"
            return 1
        }
    fi

    # Step 3: Install TimescaleDB
    install_timescaledb || {
        log_warn "TimescaleDB installation had issues, continuing..."
    }

    # Step 4: Create database user
    create_db_user "$DB_USER" "$DB_PASSWORD" || {
        log_error "Failed to create database user"
        return 1
    }

    # Step 5: Create database
    create_database "$DB_NAME" "$DB_USER" || {
        log_error "Failed to create database"
        return 1
    }

    # Step 6: Configure authentication
    configure_pg_hba || {
        log_warn "pg_hba configuration had issues"
    }

    # Step 7: Initialize schema
    initialize_database_schema || {
        log_error "Schema initialization failed"
        return 1
    }

    log_info "Database setup completed successfully"
    return 0
}

# Verify database setup
verify_database() {
    log_info "Verifying database setup..."

    local errors=0

    # Check PostgreSQL is running
    if ! is_postgres_running; then
        log_error "PostgreSQL is not running"
        ((errors++))
    else
        log_info "[OK] PostgreSQL is running"
    fi

    # Check database exists
    if ! database_exists "$DB_NAME"; then
        log_error "Database $DB_NAME does not exist"
        ((errors++))
    else
        log_info "[OK] Database $DB_NAME exists"
    fi

    # Check user exists
    if ! db_user_exists "$DB_USER"; then
        log_error "User $DB_USER does not exist"
        ((errors++))
    else
        log_info "[OK] User $DB_USER exists"
    fi

    # Check we can connect
    if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" >/dev/null 2>&1; then
        log_info "[OK] Can connect to database as $DB_USER"
    else
        log_error "Cannot connect to database"
        ((errors++))
    fi

    # Check TimescaleDB extension
    if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -tAc "SELECT 1 FROM pg_extension WHERE extname = 'timescaledb';" 2>/dev/null | grep -q "1"; then
        log_info "[OK] TimescaleDB extension is enabled"
    else
        log_warn "[WARN] TimescaleDB extension may not be enabled"
    fi

    # Check tables exist
    local table_count
    table_count=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null)

    if [ -n "$table_count" ] && [ "$table_count" -ge 5 ]; then
        log_info "[OK] Database has $table_count tables"
    else
        log_warn "[WARN] Database has only $table_count tables (expected 5+)"
    fi

    if [ $errors -gt 0 ]; then
        log_error "Database verification failed with $errors error(s)"
        return 1
    fi

    log_info "Database verification passed"
    return 0
}

# =============================================================================
# CLI Interface
# =============================================================================

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    case "${1:-}" in
        --install-postgres)
            install_postgresql
            exit $?
            ;;
        --install-timescale)
            install_timescaledb
            exit $?
            ;;
        --create-user)
            create_db_user
            exit $?
            ;;
        --create-db)
            create_database
            exit $?
            ;;
        --init-schema)
            initialize_database_schema
            exit $?
            ;;
        --setup)
            setup_database
            exit $?
            ;;
        --verify)
            verify_database
            exit $?
            ;;
        --help|-h)
            echo "Water-Controller Database Module v$DATABASE_MODULE_VERSION"
            echo ""
            echo "Usage: $0 [OPTION]"
            echo ""
            echo "Options:"
            echo "  --install-postgres   Install PostgreSQL"
            echo "  --install-timescale  Install TimescaleDB extension"
            echo "  --create-user        Create database user (wtc)"
            echo "  --create-db          Create database (water_treatment)"
            echo "  --init-schema        Initialize database schema from init.sql"
            echo "  --setup              Complete database setup (all of the above)"
            echo "  --verify             Verify database setup"
            echo "  --help, -h           Show this help message"
            ;;
        *)
            echo "Usage: $0 [--setup|--verify|--help]" >&2
            exit 1
            ;;
    esac
fi
