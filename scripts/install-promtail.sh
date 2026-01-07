#!/bin/bash
#
# Water Treatment Controller - Promtail Installation Script
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Installs Promtail on bare metal to ship logs to a remote Loki server.
# This enables centralized logging for multi-site deployments.
#
# Usage:
#   sudo ./install-promtail.sh --loki-url http://logging-server:3100
#   sudo ./install-promtail.sh --loki-url http://logging-server:3100 --site-name "Plant-A"
#
# Prerequisites:
#   - Water Controller already installed via install.sh
#   - Network access to the Loki server
#

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

readonly SCRIPT_VERSION="1.0.0"
readonly PROMTAIL_VERSION="2.9.4"
readonly INSTALL_DIR="/opt/water-controller"
readonly CONFIG_DIR="/etc/water-controller"
readonly DATA_DIR="/var/lib/water-controller/promtail"
readonly BIN_DIR="${INSTALL_DIR}/bin"

# Defaults
LOKI_URL=""
SITE_NAME=""
DRY_RUN=0
UNINSTALL=0

# =============================================================================
# Logging
# =============================================================================

log_info() { echo "[INFO] $*"; }
log_warn() { echo "[WARN] $*" >&2; }
log_error() { echo "[ERROR] $*" >&2; }

# =============================================================================
# Usage
# =============================================================================

show_usage() {
    cat <<EOF
Water Treatment Controller - Promtail Installer v${SCRIPT_VERSION}

Installs Promtail to ship logs to a remote Loki server.

USAGE:
    $0 --loki-url <URL> [OPTIONS]

REQUIRED:
    --loki-url URL      Loki server URL (e.g., http://logging-server:3100)

OPTIONS:
    --site-name NAME    Site identifier for multi-site deployments
    --dry-run           Show what would be done without making changes
    --uninstall         Remove Promtail installation
    -h, --help          Show this help message

EXAMPLES:
    # Basic installation
    sudo $0 --loki-url http://192.168.1.100:3100

    # Multi-site with site identifier
    sudo $0 --loki-url http://logging.example.com:3100 --site-name "Plant-A"

    # Uninstall
    sudo $0 --uninstall

NOTES:
    - Requires root privileges
    - Water Controller must already be installed
    - Loki server must be accessible from this device

EOF
}

# =============================================================================
# Argument Parsing
# =============================================================================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --loki-url)
                LOKI_URL="$2"
                shift 2
                ;;
            --site-name)
                SITE_NAME="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN=1
                shift
                ;;
            --uninstall)
                UNINSTALL=1
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    # Validate required args (unless uninstalling)
    if [[ $UNINSTALL -eq 0 && -z "$LOKI_URL" ]]; then
        log_error "--loki-url is required"
        show_usage
        exit 1
    fi
}

# =============================================================================
# Preflight Checks
# =============================================================================

preflight_checks() {
    log_info "Running preflight checks..."

    # Check root
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi

    # Check Water Controller is installed
    if [[ ! -d "$INSTALL_DIR" ]]; then
        log_error "Water Controller not found at $INSTALL_DIR"
        log_error "Install Water Controller first: ./install.sh"
        exit 1
    fi

    # Check systemd
    if ! command -v systemctl >/dev/null 2>&1; then
        log_error "systemd not found"
        exit 1
    fi

    # Detect architecture
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)
            PROMTAIL_ARCH="amd64"
            ;;
        aarch64)
            PROMTAIL_ARCH="arm64"
            ;;
        armv7l|armv6l)
            PROMTAIL_ARCH="arm"
            ;;
        *)
            log_error "Unsupported architecture: $ARCH"
            exit 1
            ;;
    esac

    log_info "Architecture: $ARCH -> $PROMTAIL_ARCH"

    # Test Loki connectivity (unless uninstalling)
    if [[ $UNINSTALL -eq 0 ]]; then
        log_info "Testing connectivity to Loki at $LOKI_URL..."
        if command -v curl >/dev/null 2>&1; then
            if ! curl -sf --connect-timeout 5 "${LOKI_URL}/ready" >/dev/null 2>&1; then
                log_warn "Cannot reach Loki at $LOKI_URL - continuing anyway"
                log_warn "Ensure the Loki server is running and accessible"
            else
                log_info "Loki is reachable"
            fi
        fi
    fi

    log_info "Preflight checks passed"
}

# =============================================================================
# Download Promtail
# =============================================================================

download_promtail() {
    local url="https://github.com/grafana/loki/releases/download/v${PROMTAIL_VERSION}/promtail-linux-${PROMTAIL_ARCH}.zip"
    local tmp_dir="/tmp/promtail-install-$$"

    log_info "Downloading Promtail ${PROMTAIL_VERSION} for ${PROMTAIL_ARCH}..."

    if [[ $DRY_RUN -eq 1 ]]; then
        log_info "[DRY RUN] Would download from $url"
        return 0
    fi

    mkdir -p "$tmp_dir"
    mkdir -p "$BIN_DIR"

    # Download
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$url" -o "${tmp_dir}/promtail.zip"
    elif command -v wget >/dev/null 2>&1; then
        wget -q "$url" -O "${tmp_dir}/promtail.zip"
    else
        log_error "Neither curl nor wget found"
        exit 1
    fi

    # Extract
    if command -v unzip >/dev/null 2>&1; then
        unzip -q "${tmp_dir}/promtail.zip" -d "$tmp_dir"
    else
        log_error "unzip not found - install with: apt install unzip"
        rm -rf "$tmp_dir"
        exit 1
    fi

    # Install binary
    mv "${tmp_dir}/promtail-linux-${PROMTAIL_ARCH}" "${BIN_DIR}/promtail"
    chmod +x "${BIN_DIR}/promtail"

    # Cleanup
    rm -rf "$tmp_dir"

    log_info "Promtail installed to ${BIN_DIR}/promtail"
}

# =============================================================================
# Generate Configuration
# =============================================================================

generate_config() {
    log_info "Generating Promtail configuration..."

    if [[ $DRY_RUN -eq 1 ]]; then
        log_info "[DRY RUN] Would generate config at ${CONFIG_DIR}/promtail-config.yml"
        return 0
    fi

    mkdir -p "$CONFIG_DIR"
    mkdir -p "$DATA_DIR"

    # Build site label if provided
    local site_label=""
    if [[ -n "$SITE_NAME" ]]; then
        site_label="site: \"${SITE_NAME}\""
    fi

    cat > "${CONFIG_DIR}/promtail-config.yml" <<EOF
# Water Treatment Controller - Promtail Configuration (Remote Loki)
# Generated by install-promtail.sh on $(date -Iseconds)
# Loki URL: ${LOKI_URL}
${SITE_NAME:+# Site: ${SITE_NAME}}

server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: ${DATA_DIR}/positions.yaml

clients:
  - url: ${LOKI_URL}/loki/api/v1/push
    batchwait: 1s
    batchsize: 1048576
    timeout: 10s

scrape_configs:
  # Scrape systemd journal for water-controller services
  - job_name: journal
    journal:
      max_age: 12h
      labels:
        job: systemd-journal
        app: water-controller
        ${site_label}
      path: /var/log/journal
    relabel_configs:
      # Extract unit name as service
      - source_labels: ['__journal__systemd_unit']
        target_label: unit
      - source_labels: ['__journal__systemd_unit']
        regex: 'water-controller-(.+)\.service'
        target_label: service
        replacement: '\${1}'
      # Add hostname
      - source_labels: ['__journal__hostname']
        target_label: host
      # Add priority as level
      - source_labels: ['__journal_priority_keyword']
        target_label: priority
      # Filter to only water-controller services
      - source_labels: ['__journal__systemd_unit']
        regex: 'water-controller.*\.service'
        action: keep
    pipeline_stages:
      # Try to parse JSON logs from API service
      - json:
          expressions:
            level: level
            logger: logger
            message: message
            correlation_id: correlation_id
            operation_name: operation_name
            rtu: rtu
            duration_ms: duration_ms
            user: user
            timestamp: timestamp
      # If JSON parsing worked, use extracted level
      - labels:
          level:
          logger:
          correlation_id:
          rtu:
      # Extract log level from non-JSON logs
      - regex:
          expression: '(?P<level>DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)'
      - labels:
          level:
      # Normalize log levels to lowercase
      - template:
          source: level
          template: '{{ ToLower .Value }}'
      - labels:
          level:
      # Map systemd priority to level if not already set
      - match:
          selector: '{level=""}'
          stages:
            - template:
                source: priority
                template: '{{ if eq .Value "emerg" }}critical{{ else if eq .Value "alert" }}critical{{ else if eq .Value "crit" }}critical{{ else if eq .Value "err" }}error{{ else if eq .Value "warning" }}warning{{ else if eq .Value "notice" }}info{{ else if eq .Value "info" }}info{{ else if eq .Value "debug" }}debug{{ else }}info{{ end }}'
            - labels:
                level:

  # Scrape application log files (if any service writes to files)
  - job_name: files
    static_configs:
      - targets:
          - localhost
        labels:
          job: water-controller-files
          app: water-controller
          ${site_label}
          __path__: /var/log/water-controller/*.log
    pipeline_stages:
      # Parse filename to extract service
      - regex:
          expression: '/var/log/water-controller/(?P<service>[^/]+)\.log'
      - labels:
          service:
      # Try JSON parsing
      - json:
          expressions:
            level: level
            logger: logger
            message: message
            correlation_id: correlation_id
      - labels:
          level:
          logger:
          correlation_id:
      # Fallback regex for level
      - regex:
          expression: '(?P<level>DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)'
      - labels:
          level:
      - template:
          source: level
          template: '{{ ToLower .Value }}'
      - labels:
          level:
EOF

    # Set ownership
    chown -R wtc:wtc "$DATA_DIR" 2>/dev/null || true

    log_info "Configuration written to ${CONFIG_DIR}/promtail-config.yml"
}

# =============================================================================
# Install Service
# =============================================================================

install_service() {
    log_info "Installing systemd service..."

    if [[ $DRY_RUN -eq 1 ]]; then
        log_info "[DRY RUN] Would install systemd service"
        return 0
    fi

    # Copy service file
    cp "${INSTALL_DIR}/systemd/water-controller-promtail.service" \
       /etc/systemd/system/water-controller-promtail.service

    # Reload systemd
    systemctl daemon-reload

    # Enable and start
    systemctl enable water-controller-promtail.service
    systemctl start water-controller-promtail.service

    # Wait for startup
    sleep 2

    # Check status
    if systemctl is-active --quiet water-controller-promtail.service; then
        log_info "Promtail service started successfully"
    else
        log_warn "Promtail service may not have started correctly"
        log_warn "Check: journalctl -u water-controller-promtail -f"
    fi
}

# =============================================================================
# Uninstall
# =============================================================================

do_uninstall() {
    log_info "Uninstalling Promtail..."

    if [[ $DRY_RUN -eq 1 ]]; then
        log_info "[DRY RUN] Would uninstall Promtail"
        return 0
    fi

    # Stop and disable service
    systemctl stop water-controller-promtail.service 2>/dev/null || true
    systemctl disable water-controller-promtail.service 2>/dev/null || true

    # Remove service file
    rm -f /etc/systemd/system/water-controller-promtail.service
    systemctl daemon-reload

    # Remove binary
    rm -f "${BIN_DIR}/promtail"

    # Optionally remove config and data
    read -r -p "Remove configuration and data? [y/N] " response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        rm -f "${CONFIG_DIR}/promtail-config.yml"
        rm -rf "$DATA_DIR"
        log_info "Configuration and data removed"
    else
        log_info "Configuration preserved at ${CONFIG_DIR}/promtail-config.yml"
    fi

    log_info "Promtail uninstalled"
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "Water Treatment Controller - Promtail Installer v${SCRIPT_VERSION}"
    echo ""

    parse_args "$@"
    preflight_checks

    if [[ $UNINSTALL -eq 1 ]]; then
        do_uninstall
        exit 0
    fi

    download_promtail
    generate_config
    install_service

    echo ""
    echo "============================================================"
    echo "                 PROMTAIL INSTALLATION COMPLETE"
    echo "============================================================"
    echo ""
    echo "Loki URL:     ${LOKI_URL}"
    [[ -n "$SITE_NAME" ]] && echo "Site Name:    ${SITE_NAME}"
    echo ""
    echo "Useful Commands:"
    echo "  Status:   systemctl status water-controller-promtail"
    echo "  Logs:     journalctl -u water-controller-promtail -f"
    echo "  Restart:  systemctl restart water-controller-promtail"
    echo ""
    echo "Verify logs are reaching Loki via Grafana at the central server."
    echo ""
}

main "$@"
