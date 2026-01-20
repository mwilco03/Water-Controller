"""
Water Treatment Controller - Logging Configuration Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

REST API for log forwarding configuration.
Supports forwarding logs to syslog, Elasticsearch, Loki, and other destinations.
"""

import logging
import socket
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from ...core.errors import build_success_response

logger = logging.getLogger(__name__)

router = APIRouter()


# In-memory config storage (in production, persist to database or config file)
_log_config: dict[str, Any] = {
    "enabled": False,
    "forward_type": "syslog",
    "host": "localhost",
    "port": 514,
    "protocol": "udp",
    "index": None,
    "api_key": None,
    "tls_enabled": False,
    "tls_verify": True,
    "include_alarms": True,
    "include_events": True,
    "include_audit": True,
    "log_level": "INFO",
}


# Available log destinations with their configuration
LOG_DESTINATIONS = [
    {
        "type": "syslog",
        "name": "Syslog",
        "description": "Standard syslog server (rsyslog, syslog-ng)",
        "default_port": 514,
        "protocols": ["udp", "tcp"],
        "requires_index": False,
    },
    {
        "type": "elastic",
        "name": "Elasticsearch",
        "description": "Elasticsearch/OpenSearch cluster",
        "default_port": 9200,
        "protocols": ["http", "https"],
        "requires_index": True,
    },
    {
        "type": "loki",
        "name": "Grafana Loki",
        "description": "Loki log aggregation system",
        "default_port": 3100,
        "protocols": ["http", "https"],
        "requires_index": False,
    },
    {
        "type": "splunk",
        "name": "Splunk HEC",
        "description": "Splunk HTTP Event Collector",
        "default_port": 8088,
        "protocols": ["http", "https"],
        "requires_index": True,
    },
    {
        "type": "fluentd",
        "name": "Fluentd/Fluent Bit",
        "description": "Fluentd forward protocol",
        "default_port": 24224,
        "protocols": ["tcp"],
        "requires_index": False,
    },
]


class LogForwardingConfig(BaseModel):
    """Log forwarding configuration."""

    enabled: bool = Field(False, description="Enable log forwarding")
    forward_type: str = Field("syslog", description="Destination type")
    host: str = Field("localhost", description="Destination host")
    port: int = Field(514, ge=1, le=65535, description="Destination port")
    protocol: str = Field("udp", description="Transport protocol")
    index: str | None = Field(None, description="Index/stream name (Elasticsearch/Splunk)")
    api_key: str | None = Field(None, description="API key for authentication")
    tls_enabled: bool = Field(False, description="Enable TLS encryption")
    tls_verify: bool = Field(True, description="Verify TLS certificates")
    include_alarms: bool = Field(True, description="Forward alarm events")
    include_events: bool = Field(True, description="Forward system events")
    include_audit: bool = Field(True, description="Forward audit logs")
    log_level: str = Field("INFO", description="Minimum log level to forward")


@router.get("/config")
async def get_logging_config() -> dict[str, Any]:
    """
    Get current log forwarding configuration.
    """
    # Return config without sensitive fields
    safe_config = {**_log_config}
    if safe_config.get("api_key"):
        safe_config["api_key"] = "********"  # Mask API key

    return build_success_response(safe_config)


@router.put("/config")
async def update_logging_config(
    config: LogForwardingConfig = Body(...)
) -> dict[str, Any]:
    """
    Update log forwarding configuration.
    """
    global _log_config

    # Validate forward_type
    valid_types = [d["type"] for d in LOG_DESTINATIONS]
    if config.forward_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid forward_type. Must be one of: {valid_types}"
        )

    # Validate log level
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if config.log_level.upper() not in valid_levels:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid log_level. Must be one of: {valid_levels}"
        )

    # Update config
    _log_config = config.model_dump()
    logger.info(f"Log forwarding config updated: type={config.forward_type}, host={config.host}")

    # Return updated config (masked)
    safe_config = {**_log_config}
    if safe_config.get("api_key"):
        safe_config["api_key"] = "********"

    return build_success_response(safe_config)


@router.get("/destinations")
async def get_log_destinations() -> dict[str, Any]:
    """
    Get available log forwarding destinations.

    Returns list of supported destination types with their configuration options.
    """
    return build_success_response({
        "destinations": LOG_DESTINATIONS
    })


@router.post("/test")
async def test_log_forwarding() -> dict[str, Any]:
    """
    Test log forwarding connection.

    Sends a test message to the configured destination.
    """
    if not _log_config.get("enabled"):
        raise HTTPException(
            status_code=400,
            detail="Log forwarding is not enabled. Enable it first in configuration."
        )

    host = _log_config.get("host", "localhost")
    port = _log_config.get("port", 514)
    protocol = _log_config.get("protocol", "udp")
    forward_type = _log_config.get("forward_type", "syslog")

    try:
        if forward_type == "syslog":
            # Test syslog connection
            test_msg = "<14>1 - WTC - - - - Test message from Water Treatment Controller"

            if protocol == "udp":
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(5)
                sock.sendto(test_msg.encode(), (host, port))
                sock.close()
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((host, port))
                sock.send(test_msg.encode())
                sock.close()

            return build_success_response({
                "success": True,
                "message": f"Test message sent to syslog at {host}:{port} via {protocol.upper()}"
            })

        elif forward_type == "elastic":
            # Test Elasticsearch connection via HTTP
            import urllib.request
            import ssl

            url = f"{'https' if _log_config.get('tls_enabled') else 'http'}://{host}:{port}/_cluster/health"

            ctx = None
            if _log_config.get("tls_enabled") and not _log_config.get("tls_verify"):
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(url)
            if _log_config.get("api_key"):
                req.add_header("Authorization", f"ApiKey {_log_config['api_key']}")

            try:
                with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                    if resp.status == 200:
                        return build_success_response({
                            "success": True,
                            "message": f"Successfully connected to Elasticsearch at {host}:{port}"
                        })
            except Exception as e:
                raise HTTPException(
                    status_code=502,
                    detail=f"Elasticsearch connection failed: {e}"
                )

        elif forward_type == "loki":
            # Test Loki connection
            import urllib.request
            import ssl

            url = f"{'https' if _log_config.get('tls_enabled') else 'http'}://{host}:{port}/ready"

            ctx = None
            if _log_config.get("tls_enabled") and not _log_config.get("tls_verify"):
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            try:
                with urllib.request.urlopen(url, timeout=5, context=ctx) as resp:
                    if resp.status == 200:
                        return build_success_response({
                            "success": True,
                            "message": f"Successfully connected to Loki at {host}:{port}"
                        })
            except Exception as e:
                raise HTTPException(
                    status_code=502,
                    detail=f"Loki connection failed: {e}"
                )

        else:
            # Generic TCP test for other destinations
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.close()

            return build_success_response({
                "success": True,
                "message": f"Successfully connected to {forward_type} at {host}:{port}"
            })

    except socket.timeout:
        raise HTTPException(
            status_code=504,
            detail=f"Connection to {host}:{port} timed out"
        )
    except socket.error as e:
        raise HTTPException(
            status_code=502,
            detail=f"Connection failed: {e}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Test failed: {e}"
        )

    return build_success_response({
        "success": True,
        "message": "Test completed"
    })
