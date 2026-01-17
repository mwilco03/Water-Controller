#!/bin/bash
# =============================================================================
# Water-Controller Database Authentication Fix
# =============================================================================
# Fixes PostgreSQL authentication issues for wtc-api.
#
# This script ensures:
# 1. The 'wtc' database user exists with correct password
# 2. The user has necessary permissions
# 3. The database schema is properly initialized
#
# Usage:
#   ./scripts/fix-database-auth.sh
#
# Copyright (C) 2024-2026
# SPDX-License-Identifier: GPL-3.0-or-later
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Database connection parameters
DB_CONTAINER="wtc-database"
DB_NAME="water_treatment"
DB_USER="wtc"
DB_PASSWORD="wtc_password"
POSTGRES_USER="postgres"

# =============================================================================
# Pre-flight checks
# =============================================================================

log_info "Checking database container..."

if ! docker ps --filter "name=$DB_CONTAINER" --filter "status=running" | grep -q "$DB_CONTAINER"; then
    log_error "Database container '$DB_CONTAINER' is not running"
    log_info "Start it with: docker compose up -d database"
    exit 1
fi

log_success "Database container is running"

# =============================================================================
# Check current authentication status
# =============================================================================

log_info "Testing current authentication..."

if docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" &>/dev/null; then
    log_success "Authentication already working for user '$DB_USER'"
    log_info "No fixes needed. Run validation: ./scripts/validate-deployment.sh"
    exit 0
fi

log_warn "User '$DB_USER' cannot authenticate. Applying fixes..."

# =============================================================================
# Fix 1: Ensure user exists with correct password
# =============================================================================

log_info "Ensuring user '$DB_USER' exists..."

# Check if user exists
if docker exec "$DB_CONTAINER" psql -U "$POSTGRES_USER" -d "$DB_NAME" \
    -c "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER';" 2>/dev/null | grep -q "1 row"; then

    log_warn "User '$DB_USER' exists, resetting password..."
    docker exec "$DB_CONTAINER" psql -U "$POSTGRES_USER" -d "$DB_NAME" \
        -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
    log_success "Password reset for user '$DB_USER'"
else
    log_info "Creating user '$DB_USER'..."
    docker exec "$DB_CONTAINER" psql -U "$POSTGRES_USER" -d "$DB_NAME" \
        -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD' CREATEDB;"
    log_success "User '$DB_USER' created"
fi

# =============================================================================
# Fix 2: Grant necessary permissions
# =============================================================================

log_info "Granting permissions to user '$DB_USER'..."

docker exec "$DB_CONTAINER" psql -U "$POSTGRES_USER" -d "$DB_NAME" <<EOF
    -- Grant database privileges
    GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

    -- Grant schema privileges
    GRANT ALL PRIVILEGES ON SCHEMA public TO $DB_USER;

    -- Grant table privileges
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $DB_USER;
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;

    -- Grant future privileges
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DB_USER;

    -- Make wtc owner of public schema
    ALTER SCHEMA public OWNER TO $DB_USER;
EOF

log_success "Permissions granted"

# =============================================================================
# Fix 3: Verify authentication
# =============================================================================

log_info "Verifying authentication..."

if docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" &>/dev/null; then
    log_success "✓ User '$DB_USER' can now authenticate"
else
    log_error "Authentication still failing after fixes"
    log_info "Check pg_hba.conf: docker exec $DB_CONTAINER cat /var/lib/postgresql/data/pg_hba.conf"
    exit 1
fi

# =============================================================================
# Fix 4: Check if schema needs initialization
# =============================================================================

log_info "Checking database schema..."

table_count=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
    -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';" 2>/dev/null | tr -d ' ')

if [[ "$table_count" -lt 5 ]]; then
    log_warn "Database schema incomplete (found $table_count tables, expected 15+)"
    log_info "Initializing schema from docker/init.sql..."

    if [[ -f "docker/init.sql" ]]; then
        docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" < docker/init.sql
        log_success "Schema initialized"
    else
        log_error "init.sql not found at docker/init.sql"
        exit 1
    fi
else
    log_success "Schema is initialized ($table_count tables found)"
fi

# =============================================================================
# Fix 5: Restart API container to pick up changes
# =============================================================================

log_info "Restarting API container to apply changes..."

if docker ps --filter "name=wtc-api" --format "{{.Names}}" | grep -q "wtc-api"; then
    docker restart wtc-api
    log_success "API container restarted"

    # Wait for health check
    log_info "Waiting for API to become healthy..."
    sleep 5

    local api_port="${WTC_API_PORT:-8000}"
    if curl -sf "http://localhost:$api_port/health" >/dev/null 2>&1; then
        log_success "✓ API is healthy"
    else
        log_warn "API may still be starting up. Check logs: docker logs wtc-api"
    fi
else
    log_warn "API container not running. Start it with: docker compose up -d api"
fi

# =============================================================================
# Summary
# =============================================================================

echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Database Authentication Fixed${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo "Next steps:"
echo "  1. Verify deployment: ./scripts/validate-deployment.sh"
echo "  2. Access API docs: http://localhost:${WTC_API_PORT:-8000}/docs"
echo "  3. Login with: admin / admin (CHANGE THIS PASSWORD)"
echo ""
