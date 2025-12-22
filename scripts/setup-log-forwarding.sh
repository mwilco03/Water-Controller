#!/bin/bash
# Water Treatment Controller - Log Forwarding Setup
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This script configures log forwarding to centralized log management systems.
# Supports: Syslog, Elasticsearch, Graylog, Splunk

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
LOG_DESTINATION="${LOG_DESTINATION:-syslog}"
SYSLOG_SERVER="${SYSLOG_SERVER:-}"
SYSLOG_PORT="${SYSLOG_PORT:-514}"
SYSLOG_PROTOCOL="${SYSLOG_PROTOCOL:-udp}"
ELASTIC_URL="${ELASTIC_URL:-}"
ELASTIC_INDEX="${ELASTIC_INDEX:-water-controller}"
GRAYLOG_URL="${GRAYLOG_URL:-}"
SPLUNK_URL="${SPLUNK_URL:-}"
SPLUNK_TOKEN="${SPLUNK_TOKEN:-}"

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

# Configure rsyslog for remote forwarding
configure_rsyslog() {
    print_step "Configuring rsyslog for remote forwarding..."

    # Install rsyslog if not present
    if ! command -v rsyslogd &>/dev/null; then
        apt-get update && apt-get install -y rsyslog || yum install -y rsyslog
    fi

    # Create rsyslog configuration
    cat > /etc/rsyslog.d/50-water-controller.conf << EOF
# Water Treatment Controller - Log Forwarding Configuration

# Define custom template for structured logs
template(name="WTCLogFormat" type="list") {
    constant(value="{")
    constant(value="\"@timestamp\":\"")         property(name="timereported" dateFormat="rfc3339")
    constant(value="\",\"host\":\"")            property(name="hostname")
    constant(value="\",\"program\":\"")         property(name="programname")
    constant(value="\",\"facility\":\"")        property(name="syslogfacility-text")
    constant(value="\",\"severity\":\"")        property(name="syslogseverity-text")
    constant(value="\",\"message\":\"")         property(name="msg" format="json")
    constant(value="\",\"source\":\"water-controller\"}")
    constant(value="\n")
}

# Filter Water Controller logs
if \$programname startswith 'water' or \$programname startswith 'wtc' then {
EOF

    case "$LOG_DESTINATION" in
        syslog)
            if [[ -n "$SYSLOG_SERVER" ]]; then
                if [[ "$SYSLOG_PROTOCOL" == "tcp" ]]; then
                    echo "    action(type=\"omfwd\" target=\"$SYSLOG_SERVER\" port=\"$SYSLOG_PORT\" protocol=\"tcp\" template=\"WTCLogFormat\")" >> /etc/rsyslog.d/50-water-controller.conf
                else
                    echo "    action(type=\"omfwd\" target=\"$SYSLOG_SERVER\" port=\"$SYSLOG_PORT\" protocol=\"udp\" template=\"WTCLogFormat\")" >> /etc/rsyslog.d/50-water-controller.conf
                fi
            fi
            ;;
    esac

    cat >> /etc/rsyslog.d/50-water-controller.conf << 'EOF'
    # Also log locally
    action(type="omfile" file="/var/log/water-controller/combined.log" template="WTCLogFormat")
}

# Local file logging with rotation
\$outchannel wtc_log,/var/log/water-controller/wtc.log,104857600,/usr/bin/rotate-wtc-logs
EOF

    # Create log rotation script
    cat > /usr/bin/rotate-wtc-logs << 'EOF'
#!/bin/bash
mv /var/log/water-controller/wtc.log /var/log/water-controller/wtc.log.1
kill -HUP $(cat /var/run/rsyslogd.pid)
EOF
    chmod +x /usr/bin/rotate-wtc-logs

    # Create log directory
    mkdir -p /var/log/water-controller
    chmod 755 /var/log/water-controller

    # Restart rsyslog
    systemctl restart rsyslog

    print_step "rsyslog configured"
}

# Configure Filebeat for Elasticsearch
configure_filebeat() {
    print_step "Configuring Filebeat for Elasticsearch..."

    # Install Filebeat if not present
    if ! command -v filebeat &>/dev/null; then
        # Add Elastic repo
        wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | apt-key add -
        echo "deb https://artifacts.elastic.co/packages/8.x/apt stable main" | tee /etc/apt/sources.list.d/elastic-8.x.list
        apt-get update && apt-get install -y filebeat
    fi

    # Configure Filebeat
    cat > /etc/filebeat/filebeat.yml << EOF
# Water Treatment Controller - Filebeat Configuration

filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /var/log/water-controller/*.log
      - /var/log/water-controller/**/*.log
    fields:
      application: water-controller
      environment: production
    fields_under_root: true
    json.keys_under_root: true
    json.add_error_key: true

  - type: container
    paths:
      - /var/lib/docker/containers/*/*.log
    processors:
      - add_docker_metadata:
          host: "unix:///var/run/docker.sock"
      - add_kubernetes_metadata: ~

processors:
  - add_host_metadata:
      when.not.contains.tags: forwarded
  - add_cloud_metadata: ~
  - add_process_metadata:
      match_pids: [process.pid]

output.elasticsearch:
  hosts: ["$ELASTIC_URL"]
  index: "$ELASTIC_INDEX-%{+yyyy.MM.dd}"
  pipeline: water-controller

setup.template:
  name: "$ELASTIC_INDEX"
  pattern: "$ELASTIC_INDEX-*"

setup.ilm:
  enabled: true
  rollover_alias: "$ELASTIC_INDEX"
  pattern: "{now/d}-000001"
  policy_name: "water-controller-policy"

logging.level: info
logging.to_files: true
logging.files:
  path: /var/log/filebeat
  name: filebeat
  keepfiles: 7
  permissions: 0640
EOF

    # Create Elasticsearch ingest pipeline
    if [[ -n "$ELASTIC_URL" ]]; then
        curl -X PUT "$ELASTIC_URL/_ingest/pipeline/water-controller" \
            -H "Content-Type: application/json" \
            -d '{
                "description": "Water Controller log processing pipeline",
                "processors": [
                    {
                        "grok": {
                            "field": "message",
                            "patterns": [
                                "\\[%{TIMESTAMP_ISO8601:timestamp}\\] \\[%{WORD:level}\\] %{GREEDYDATA:msg}"
                            ],
                            "ignore_failure": true
                        }
                    },
                    {
                        "date": {
                            "field": "timestamp",
                            "formats": ["ISO8601", "yyyy-MM-dd HH:mm:ss"],
                            "ignore_failure": true
                        }
                    },
                    {
                        "geoip": {
                            "field": "source.ip",
                            "ignore_missing": true
                        }
                    }
                ]
            }' 2>/dev/null || print_warning "Could not create Elasticsearch pipeline"

        # Create ILM policy
        curl -X PUT "$ELASTIC_URL/_ilm/policy/water-controller-policy" \
            -H "Content-Type: application/json" \
            -d '{
                "policy": {
                    "phases": {
                        "hot": {
                            "min_age": "0ms",
                            "actions": {
                                "rollover": {
                                    "max_size": "50GB",
                                    "max_age": "1d"
                                }
                            }
                        },
                        "warm": {
                            "min_age": "7d",
                            "actions": {
                                "shrink": {"number_of_shards": 1},
                                "forcemerge": {"max_num_segments": 1}
                            }
                        },
                        "cold": {
                            "min_age": "30d",
                            "actions": {
                                "freeze": {}
                            }
                        },
                        "delete": {
                            "min_age": "365d",
                            "actions": {
                                "delete": {}
                            }
                        }
                    }
                }
            }' 2>/dev/null || print_warning "Could not create ILM policy"
    fi

    # Enable and start Filebeat
    systemctl enable filebeat
    systemctl restart filebeat

    print_step "Filebeat configured"
}

# Configure Fluent Bit for Graylog
configure_fluentbit_graylog() {
    print_step "Configuring Fluent Bit for Graylog..."

    # Install Fluent Bit
    if ! command -v fluent-bit &>/dev/null; then
        curl https://raw.githubusercontent.com/fluent/fluent-bit/master/install.sh | sh
    fi

    # Parse Graylog URL
    GRAYLOG_HOST=$(echo "$GRAYLOG_URL" | sed -E 's|https?://([^:]+).*|\1|')
    GRAYLOG_PORT=$(echo "$GRAYLOG_URL" | sed -E 's|.*:([0-9]+).*|\1|')
    [[ -z "$GRAYLOG_PORT" ]] && GRAYLOG_PORT=12201

    # Configure Fluent Bit
    cat > /etc/fluent-bit/fluent-bit.conf << EOF
[SERVICE]
    Flush         1
    Log_Level     info
    Daemon        off
    Parsers_File  parsers.conf
    HTTP_Server   On
    HTTP_Listen   0.0.0.0
    HTTP_Port     2020

[INPUT]
    Name              tail
    Path              /var/log/water-controller/*.log
    Parser            json
    Tag               wtc.*
    Refresh_Interval  5
    Mem_Buf_Limit     5MB
    Skip_Long_Lines   On

[INPUT]
    Name              systemd
    Tag               systemd.*
    Systemd_Filter    _SYSTEMD_UNIT=water-controller.service
    Systemd_Filter    _SYSTEMD_UNIT=water-controller-api.service
    Read_From_Tail    On

[FILTER]
    Name              modify
    Match             *
    Add               _application water-controller
    Add               _environment production

[OUTPUT]
    Name              gelf
    Match             *
    Host              $GRAYLOG_HOST
    Port              $GRAYLOG_PORT
    Mode              udp
    Gelf_Short_Message_Key message
    Gelf_Full_Message_Key  full_message
EOF

    # Enable and start Fluent Bit
    systemctl enable fluent-bit
    systemctl restart fluent-bit

    print_step "Fluent Bit configured for Graylog"
}

# Configure HTTP Event Collector for Splunk
configure_splunk_hec() {
    print_step "Configuring Splunk HEC..."

    if [[ -z "$SPLUNK_URL" || -z "$SPLUNK_TOKEN" ]]; then
        print_error "SPLUNK_URL and SPLUNK_TOKEN are required"
        return 1
    fi

    # Install Fluent Bit if not present
    if ! command -v fluent-bit &>/dev/null; then
        curl https://raw.githubusercontent.com/fluent/fluent-bit/master/install.sh | sh
    fi

    # Configure Fluent Bit for Splunk
    cat > /etc/fluent-bit/fluent-bit.conf << EOF
[SERVICE]
    Flush         1
    Log_Level     info
    Daemon        off
    Parsers_File  parsers.conf

[INPUT]
    Name              tail
    Path              /var/log/water-controller/*.log
    Parser            json
    Tag               wtc.*
    Refresh_Interval  5

[INPUT]
    Name              systemd
    Tag               systemd.*
    Systemd_Filter    _SYSTEMD_UNIT=water-controller.service

[FILTER]
    Name              modify
    Match             *
    Add               source water-controller
    Add               sourcetype _json
    Add               index main

[OUTPUT]
    Name              splunk
    Match             *
    Host              $(echo "$SPLUNK_URL" | sed -E 's|https?://([^:]+).*|\1|')
    Port              $(echo "$SPLUNK_URL" | sed -E 's|.*:([0-9]+).*|\1|')
    Splunk_Token      $SPLUNK_TOKEN
    tls               On
    tls.verify        Off
EOF

    systemctl enable fluent-bit
    systemctl restart fluent-bit

    print_step "Splunk HEC configured"
}

# Create logrotate configuration
configure_logrotate() {
    print_step "Configuring log rotation..."

    cat > /etc/logrotate.d/water-controller << 'EOF'
/var/log/water-controller/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 root adm
    sharedscripts
    postrotate
        systemctl reload rsyslog >/dev/null 2>&1 || true
        systemctl reload water-controller-api >/dev/null 2>&1 || true
    endscript
}

/var/log/water-controller/**/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 root adm
}
EOF

    print_step "Log rotation configured"
}

# Create environment file for log forwarding
create_env_file() {
    print_step "Creating log forwarding environment file..."

    mkdir -p /etc/water-controller

    cat > /etc/water-controller/logging.env << EOF
# Log Forwarding Configuration
# Generated on $(date)

LOG_DESTINATION=$LOG_DESTINATION
SYSLOG_SERVER=$SYSLOG_SERVER
SYSLOG_PORT=$SYSLOG_PORT
SYSLOG_PROTOCOL=$SYSLOG_PROTOCOL
ELASTIC_URL=$ELASTIC_URL
ELASTIC_INDEX=$ELASTIC_INDEX
GRAYLOG_URL=$GRAYLOG_URL
SPLUNK_URL=$SPLUNK_URL
EOF

    chmod 600 /etc/water-controller/logging.env
    print_step "Environment file created"
}

# Test log forwarding
test_forwarding() {
    print_step "Testing log forwarding..."

    # Send test message
    logger -t water-controller -p local0.info "Test log message from Water Treatment Controller setup"

    # Check if log was written
    sleep 2
    if grep -q "Test log message" /var/log/water-controller/*.log 2>/dev/null; then
        print_step "Local logging: OK"
    else
        print_warning "Local logging may not be configured correctly"
    fi

    case "$LOG_DESTINATION" in
        elasticsearch)
            if [[ -n "$ELASTIC_URL" ]]; then
                curl -s "$ELASTIC_URL/$ELASTIC_INDEX-*/_search?q=Test" | grep -q "hits" && \
                    print_step "Elasticsearch forwarding: OK" || \
                    print_warning "Could not verify Elasticsearch forwarding"
            fi
            ;;
    esac
}

# Print summary
print_summary() {
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  Log Forwarding Setup Complete${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "Destination: $LOG_DESTINATION"
    echo ""
    echo "Configuration files:"
    echo "  - /etc/rsyslog.d/50-water-controller.conf"
    echo "  - /etc/logrotate.d/water-controller"
    echo "  - /etc/water-controller/logging.env"

    case "$LOG_DESTINATION" in
        elasticsearch)
            echo "  - /etc/filebeat/filebeat.yml"
            ;;
        graylog)
            echo "  - /etc/fluent-bit/fluent-bit.conf"
            ;;
        splunk)
            echo "  - /etc/fluent-bit/fluent-bit.conf"
            ;;
    esac

    echo ""
    echo "Log directory: /var/log/water-controller/"
    echo ""
    echo "To test: logger -t water-controller 'Test message'"
}

usage() {
    echo "Usage: $0 [DESTINATION] [OPTIONS]"
    echo ""
    echo "Destinations:"
    echo "  syslog        Forward to remote syslog server"
    echo "  elasticsearch Forward to Elasticsearch/ELK stack"
    echo "  graylog       Forward to Graylog"
    echo "  splunk        Forward to Splunk HEC"
    echo "  local         Local logging only"
    echo ""
    echo "Environment variables:"
    echo "  SYSLOG_SERVER, SYSLOG_PORT, SYSLOG_PROTOCOL"
    echo "  ELASTIC_URL, ELASTIC_INDEX"
    echo "  GRAYLOG_URL"
    echo "  SPLUNK_URL, SPLUNK_TOKEN"
}

# Main
check_root

LOG_DESTINATION="${1:-$LOG_DESTINATION}"

case "$LOG_DESTINATION" in
    syslog)
        configure_rsyslog
        ;;
    elasticsearch)
        configure_rsyslog
        configure_filebeat
        ;;
    graylog)
        configure_rsyslog
        configure_fluentbit_graylog
        ;;
    splunk)
        configure_rsyslog
        configure_splunk_hec
        ;;
    local|"")
        configure_rsyslog
        ;;
    --help|-h)
        usage
        exit 0
        ;;
    *)
        print_error "Unknown destination: $LOG_DESTINATION"
        usage
        exit 1
        ;;
esac

configure_logrotate
create_env_file
test_forwarding
print_summary
