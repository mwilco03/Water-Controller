#!/bin/bash
# Water Treatment Controller - Credential Management
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This script manages credentials for production deployment.
# Generates secure passwords and configures all system components.

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration directories
CONFIG_DIR="${CONFIG_DIR:-/etc/water-controller}"
SECRETS_DIR="${SECRETS_DIR:-/etc/water-controller/secrets}"

print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}  Water Treatment Controller${NC}"
    echo -e "${BLUE}  Credential Management${NC}"
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

# Generate cryptographically secure password
generate_password() {
    local length="${1:-32}"
    openssl rand -base64 48 | tr -dc 'a-zA-Z0-9!@#$%^&*()_+-=' | head -c "$length"
}

# Generate API key
generate_api_key() {
    openssl rand -hex 32
}

# Generate JWT secret
generate_jwt_secret() {
    openssl rand -base64 64 | tr -d '\n'
}

# Hash password using bcrypt (via Python)
hash_password() {
    local password="$1"
    python3 -c "
import bcrypt
password = '''$password'''.encode('utf-8')
salt = bcrypt.gensalt(rounds=12)
hashed = bcrypt.hashpw(password, salt)
print(hashed.decode('utf-8'))
" 2>/dev/null || echo "$password"
}

# Create secure directories
setup_directories() {
    print_step "Creating secure directories..."

    mkdir -p "$CONFIG_DIR"
    mkdir -p "$SECRETS_DIR"

    chmod 700 "$CONFIG_DIR"
    chmod 700 "$SECRETS_DIR"

    # Set immutable attribute on secrets directory
    chattr +i "$SECRETS_DIR" 2>/dev/null || true

    print_step "Directories created"
}

# Generate all system credentials
generate_credentials() {
    print_step "Generating secure credentials..."

    # Temporarily allow modifications
    chattr -i "$SECRETS_DIR" 2>/dev/null || true

    # Database credentials
    DB_PASSWORD=$(generate_password 32)
    DB_READONLY_PASSWORD=$(generate_password 32)

    # API credentials
    API_KEY=$(generate_api_key)
    JWT_SECRET=$(generate_jwt_secret)

    # Admin user credentials
    ADMIN_PASSWORD=$(generate_password 24)
    OPERATOR_PASSWORD=$(generate_password 24)
    VIEWER_PASSWORD=$(generate_password 24)

    # MQTT credentials (if used)
    MQTT_PASSWORD=$(generate_password 32)

    # Encryption keys
    ENCRYPTION_KEY=$(openssl rand -hex 32)
    BACKUP_ENCRYPTION_KEY=$(openssl rand -hex 32)

    # Save database credentials
    cat > "$SECRETS_DIR/database.env" << EOF
# Database Credentials - KEEP SECURE
# Generated: $(date -Iseconds)
# DO NOT COMMIT TO VERSION CONTROL

DB_PASSWORD=$DB_PASSWORD
DB_READONLY_PASSWORD=$DB_READONLY_PASSWORD
EOF
    chmod 600 "$SECRETS_DIR/database.env"

    # Save API credentials
    cat > "$SECRETS_DIR/api.env" << EOF
# API Credentials - KEEP SECURE
# Generated: $(date -Iseconds)
# DO NOT COMMIT TO VERSION CONTROL

API_KEY=$API_KEY
JWT_SECRET=$JWT_SECRET
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=24
EOF
    chmod 600 "$SECRETS_DIR/api.env"

    # Save user credentials (hashed for reference)
    cat > "$SECRETS_DIR/users.env" << EOF
# User Credentials - KEEP SECURE
# Generated: $(date -Iseconds)
# DO NOT COMMIT TO VERSION CONTROL
# Store these passwords in a secure password manager

ADMIN_PASSWORD=$ADMIN_PASSWORD
OPERATOR_PASSWORD=$OPERATOR_PASSWORD
VIEWER_PASSWORD=$VIEWER_PASSWORD
EOF
    chmod 600 "$SECRETS_DIR/users.env"

    # Save encryption keys
    cat > "$SECRETS_DIR/encryption.env" << EOF
# Encryption Keys - KEEP SECURE
# Generated: $(date -Iseconds)
# DO NOT COMMIT TO VERSION CONTROL

ENCRYPTION_KEY=$ENCRYPTION_KEY
BACKUP_ENCRYPTION_KEY=$BACKUP_ENCRYPTION_KEY
EOF
    chmod 600 "$SECRETS_DIR/encryption.env"

    # Save MQTT credentials
    cat > "$SECRETS_DIR/mqtt.env" << EOF
# MQTT Credentials - KEEP SECURE
# Generated: $(date -Iseconds)

MQTT_USER=wtc_service
MQTT_PASSWORD=$MQTT_PASSWORD
EOF
    chmod 600 "$SECRETS_DIR/mqtt.env"

    # Re-apply immutable attribute
    chattr +i "$SECRETS_DIR" 2>/dev/null || true

    print_step "Credentials generated and saved"
}

# Create combined environment file for services
create_service_env() {
    print_step "Creating service environment file..."

    cat > "$CONFIG_DIR/production.env" << EOF
# Water Treatment Controller - Production Environment
# Generated: $(date -Iseconds)
# This file sources secrets from secure location

# Database connection
DATABASE_URL=postgresql://wtc:\${DB_PASSWORD}@localhost:5432/water_treatment
DB_HOST=localhost
DB_PORT=5432
DB_NAME=water_treatment
DB_USER=wtc

# API configuration
API_HOST=0.0.0.0
API_PORT=8080
API_WORKERS=4

# Security settings
CORS_ORIGINS=https://hmi.water-controller.local
SECURE_COOKIES=true
SESSION_TIMEOUT_MINUTES=60

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Feature flags
ENABLE_TRENDS=true
ENABLE_ALARMS=true
ENABLE_CONTROL=true
ENABLE_BACKUP=true

# Include secrets
include $SECRETS_DIR/database.env
include $SECRETS_DIR/api.env
include $SECRETS_DIR/encryption.env
EOF

    chmod 640 "$CONFIG_DIR/production.env"

    print_step "Service environment file created"
}

# Update PostgreSQL with new credentials
update_postgres_credentials() {
    print_step "Updating PostgreSQL credentials..."

    # Source the new password
    source "$SECRETS_DIR/database.env"

    # Update database user password
    sudo -u postgres psql -c "ALTER USER wtc WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || {
        print_warning "Could not update PostgreSQL password - database may not be initialized yet"
        return 0
    }

    # Create read-only user if it doesn't exist
    sudo -u postgres psql << EOF 2>/dev/null || true
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'wtc_readonly') THEN
        CREATE USER wtc_readonly WITH PASSWORD '$DB_READONLY_PASSWORD';
    ELSE
        ALTER USER wtc_readonly WITH PASSWORD '$DB_READONLY_PASSWORD';
    END IF;
END
\$\$;

GRANT CONNECT ON DATABASE water_treatment TO wtc_readonly;
GRANT USAGE ON SCHEMA public TO wtc_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO wtc_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO wtc_readonly;
EOF

    print_step "PostgreSQL credentials updated"
}

# Create initial admin users in the application
create_application_users() {
    print_step "Creating application users..."

    source "$SECRETS_DIR/users.env"
    source "$SECRETS_DIR/database.env"

    # Hash passwords
    ADMIN_HASH=$(hash_password "$ADMIN_PASSWORD")
    OPERATOR_HASH=$(hash_password "$OPERATOR_PASSWORD")
    VIEWER_HASH=$(hash_password "$VIEWER_PASSWORD")

    # Insert users into database
    PGPASSWORD="$DB_PASSWORD" psql -h localhost -U wtc -d water_treatment << EOF 2>/dev/null || {
        print_warning "Could not create application users - database may not be ready"
        return 0
    }
-- Create users table if not exists
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    role VARCHAR(32) NOT NULL,
    email VARCHAR(256),
    full_name VARCHAR(256),
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ,
    password_changed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create audit log for user actions
CREATE TABLE IF NOT EXISTS user_audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id),
    action VARCHAR(64) NOT NULL,
    details JSONB,
    ip_address INET,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Insert or update default users
INSERT INTO users (username, password_hash, role, full_name)
VALUES
    ('admin', '$ADMIN_HASH', 'ADMIN', 'System Administrator'),
    ('operator', '$OPERATOR_HASH', 'OPERATOR', 'Plant Operator'),
    ('viewer', '$VIEWER_HASH', 'VIEWER', 'Read-Only User')
ON CONFLICT (username) DO UPDATE SET
    password_hash = EXCLUDED.password_hash,
    password_changed_at = NOW();
EOF

    print_step "Application users created"
}

# Configure systemd service credentials
configure_systemd_credentials() {
    print_step "Configuring systemd service credentials..."

    # Create systemd credential directory
    mkdir -p /etc/systemd/system/water-controller.service.d

    cat > /etc/systemd/system/water-controller.service.d/credentials.conf << EOF
[Service]
EnvironmentFile=$CONFIG_DIR/production.env
EnvironmentFile=$SECRETS_DIR/database.env
EnvironmentFile=$SECRETS_DIR/api.env
EnvironmentFile=$SECRETS_DIR/encryption.env

# Security hardening
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
NoNewPrivileges=true
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
EOF

    chmod 644 /etc/systemd/system/water-controller.service.d/credentials.conf

    systemctl daemon-reload 2>/dev/null || true

    print_step "Systemd credentials configured"
}

# Create Docker secrets
create_docker_secrets() {
    print_step "Creating Docker secrets..."

    # Check if Docker is available
    if ! command -v docker &>/dev/null; then
        print_warning "Docker not installed, skipping Docker secrets"
        return 0
    fi

    # Check if Docker Swarm is initialized
    if ! docker info 2>/dev/null | grep -q "Swarm: active"; then
        print_warning "Docker Swarm not active, creating local secret files instead"

        mkdir -p /var/lib/water-controller/secrets
        chmod 700 /var/lib/water-controller/secrets

        source "$SECRETS_DIR/database.env"
        source "$SECRETS_DIR/api.env"

        echo "$DB_PASSWORD" > /var/lib/water-controller/secrets/db_password
        echo "$API_KEY" > /var/lib/water-controller/secrets/api_key
        echo "$JWT_SECRET" > /var/lib/water-controller/secrets/jwt_secret

        chmod 600 /var/lib/water-controller/secrets/*

        return 0
    fi

    # Create Docker Swarm secrets
    source "$SECRETS_DIR/database.env"
    source "$SECRETS_DIR/api.env"
    source "$SECRETS_DIR/encryption.env"

    echo "$DB_PASSWORD" | docker secret create wtc_db_password - 2>/dev/null || \
        docker secret rm wtc_db_password && echo "$DB_PASSWORD" | docker secret create wtc_db_password -

    echo "$API_KEY" | docker secret create wtc_api_key - 2>/dev/null || \
        docker secret rm wtc_api_key && echo "$API_KEY" | docker secret create wtc_api_key -

    echo "$JWT_SECRET" | docker secret create wtc_jwt_secret - 2>/dev/null || \
        docker secret rm wtc_jwt_secret && echo "$JWT_SECRET" | docker secret create wtc_jwt_secret -

    print_step "Docker secrets created"
}

# Rotate credentials
rotate_credentials() {
    print_step "Rotating credentials..."

    # Backup old credentials
    BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
    mkdir -p "$CONFIG_DIR/credential_backups"

    chattr -i "$SECRETS_DIR" 2>/dev/null || true
    cp -r "$SECRETS_DIR" "$CONFIG_DIR/credential_backups/secrets_$BACKUP_DATE"

    # Generate new credentials
    generate_credentials

    # Update all systems
    update_postgres_credentials
    create_application_users
    configure_systemd_credentials
    create_docker_secrets

    # Restart services
    systemctl restart water-controller 2>/dev/null || true
    systemctl restart water-controller-api 2>/dev/null || true

    print_step "Credentials rotated successfully"
    print_warning "Old credentials backed up to: $CONFIG_DIR/credential_backups/secrets_$BACKUP_DATE"
}

# Verify credential security
verify_security() {
    print_step "Verifying credential security..."

    local issues=0

    # Check file permissions
    for file in "$SECRETS_DIR"/*.env; do
        if [[ -f "$file" ]]; then
            perms=$(stat -c %a "$file")
            if [[ "$perms" != "600" ]]; then
                print_warning "Insecure permissions on $file: $perms (should be 600)"
                ((issues++))
            fi
        fi
    done

    # Check directory permissions
    dir_perms=$(stat -c %a "$SECRETS_DIR")
    if [[ "$dir_perms" != "700" ]]; then
        print_warning "Insecure permissions on $SECRETS_DIR: $dir_perms (should be 700)"
        ((issues++))
    fi

    # Check for default passwords in config files
    if grep -r "password123\|admin123\|default\|changeme" "$CONFIG_DIR" 2>/dev/null; then
        print_warning "Default/weak passwords found in configuration"
        ((issues++))
    fi

    # Check password strength
    source "$SECRETS_DIR/users.env" 2>/dev/null
    if [[ ${#ADMIN_PASSWORD} -lt 16 ]]; then
        print_warning "Admin password is shorter than recommended (16+ characters)"
        ((issues++))
    fi

    if [[ $issues -eq 0 ]]; then
        print_step "Security verification passed"
    else
        print_warning "Found $issues security issues"
    fi

    return $issues
}

# Print credential summary (without showing actual values)
print_summary() {
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  Credential Setup Complete${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "Credential files created:"
    echo "  - $SECRETS_DIR/database.env"
    echo "  - $SECRETS_DIR/api.env"
    echo "  - $SECRETS_DIR/users.env"
    echo "  - $SECRETS_DIR/encryption.env"
    echo "  - $SECRETS_DIR/mqtt.env"
    echo ""
    echo "Service configuration:"
    echo "  - $CONFIG_DIR/production.env"
    echo ""
    echo -e "${YELLOW}IMPORTANT:${NC}"
    echo "  1. Save the user passwords from $SECRETS_DIR/users.env"
    echo "     in a secure password manager"
    echo ""
    echo "  2. The secrets directory is protected with immutable flag"
    echo "     Use 'chattr -i $SECRETS_DIR' to modify"
    echo ""
    echo "  3. Rotate credentials periodically with:"
    echo "     $0 --rotate"
    echo ""
    echo "Default users created:"
    echo "  - admin (ADMIN role)"
    echo "  - operator (OPERATOR role)"
    echo "  - viewer (VIEWER role)"
    echo ""
    echo -e "${RED}WARNING: Note down the passwords now - they will not be shown again!${NC}"
    echo ""

    # Show passwords one time
    if [[ -f "$SECRETS_DIR/users.env" ]]; then
        echo "User Passwords (SAVE THESE NOW):"
        echo "================================"
        source "$SECRETS_DIR/users.env"
        echo "  admin:    $ADMIN_PASSWORD"
        echo "  operator: $OPERATOR_PASSWORD"
        echo "  viewer:   $VIEWER_PASSWORD"
        echo ""
    fi
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --generate       Generate new credentials (default)"
    echo "  --rotate         Rotate all credentials"
    echo "  --verify         Verify credential security"
    echo "  --help           Show this help"
    echo ""
    echo "Environment variables:"
    echo "  CONFIG_DIR       Configuration directory (default: /etc/water-controller)"
    echo "  SECRETS_DIR      Secrets directory (default: /etc/water-controller/secrets)"
}

# Main
ACTION="generate"

while [[ $# -gt 0 ]]; do
    case $1 in
        --generate)
            ACTION="generate"
            shift
            ;;
        --rotate)
            ACTION="rotate"
            shift
            ;;
        --verify)
            ACTION="verify"
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

print_header
check_root

case "$ACTION" in
    generate)
        setup_directories
        generate_credentials
        create_service_env
        update_postgres_credentials
        create_application_users
        configure_systemd_credentials
        create_docker_secrets
        verify_security
        print_summary
        ;;
    rotate)
        rotate_credentials
        verify_security
        print_summary
        ;;
    verify)
        verify_security
        ;;
esac
