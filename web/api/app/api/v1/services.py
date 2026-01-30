"""
Water Treatment Controller - Service Management Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

REST API for system service management.
Provides endpoints for listing services and controlling them (start/stop/restart).

Note: In containerized deployments, these endpoints control internal services.
For Docker deployments, use docker-compose commands for container-level control.
"""

import asyncio
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Path

from ...core.errors import build_success_response

logger = logging.getLogger(__name__)

router = APIRouter()


# Service registry - maps service names to their status check commands
# In a real deployment, these would be systemd services or similar
MANAGED_SERVICES = {
    "profinet_controller": {
        "description": "PROFINET Controller (C process)",
        "check_cmd": "pgrep -f water_treat_controller",
        "start_cmd": None,  # Managed by Docker
        "stop_cmd": None,
        "restart_cmd": None,
    },
    "modbus_gateway": {
        "description": "Modbus TCP/RTU Gateway",
        "check_cmd": None,  # Internal Python service
        "start_cmd": None,
        "stop_cmd": None,
        "restart_cmd": None,
    },
    "historian": {
        "description": "Data Historian (TimescaleDB writer)",
        "check_cmd": None,  # Internal Python service
        "start_cmd": None,
        "stop_cmd": None,
        "restart_cmd": None,
    },
    "alarm_processor": {
        "description": "Alarm Processing Engine",
        "check_cmd": None,  # Internal Python service
        "start_cmd": None,
        "stop_cmd": None,
        "restart_cmd": None,
    },
}


async def check_service_status(service_name: str) -> str:
    """Check if a service is running."""
    service_config = MANAGED_SERVICES.get(service_name)
    if not service_config:
        return "unknown"

    check_cmd = service_config.get("check_cmd")
    if not check_cmd:
        # Internal Python services - check if their components are active
        # For now, assume active if API is running
        return "active"

    try:
        proc = await asyncio.create_subprocess_shell(
            check_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return "active" if proc.returncode == 0 else "inactive"
    except Exception as e:
        logger.warning(f"Failed to check service {service_name}: {e}")
        return "unknown"


@router.get("")
async def list_services() -> dict[str, Any]:
    """
    List all managed services and their current status.

    Returns a dictionary of service_name -> status.
    Status values: active, inactive, failed, unknown
    """
    services = {}

    for service_name, config in MANAGED_SERVICES.items():
        status = await check_service_status(service_name)
        services[service_name] = status

    return build_success_response(services)


@router.get("/{service_name}")
async def get_service(
    service_name: str = Path(..., description="Service name")
) -> dict[str, Any]:
    """
    Get detailed information about a specific service.
    """
    if service_name not in MANAGED_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown service: {service_name}"
        )

    config = MANAGED_SERVICES[service_name]
    status = await check_service_status(service_name)

    return build_success_response({
        "name": service_name,
        "status": status,
        "description": config["description"],
        "controllable": config.get("restart_cmd") is not None,
    })


@router.post("/{service_name}/start")
async def start_service(
    service_name: str = Path(..., description="Service name")
) -> dict[str, Any]:
    """
    Start a service.

    Note: In containerized deployments, container-level services
    are managed by Docker/orchestrator. This endpoint controls
    internal application services only.
    """
    if service_name not in MANAGED_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown service: {service_name}"
        )

    config = MANAGED_SERVICES[service_name]
    start_cmd = config.get("start_cmd")

    if not start_cmd:
        raise HTTPException(
            status_code=503,
            detail=f"Service {service_name} is managed by Docker and cannot be started via API. "
                   "Use 'docker compose restart <service>' from the host."
        )

    try:
        proc = await asyncio.create_subprocess_shell(
            start_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to start {service_name}: {stderr.decode()}"
            )

        logger.info(f"Started service: {service_name}")
        return build_success_response({
            "service": service_name,
            "action": "start",
            "success": True,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start {service_name}: {e}"
        )


@router.post("/{service_name}/stop")
async def stop_service(
    service_name: str = Path(..., description="Service name")
) -> dict[str, Any]:
    """
    Stop a service.

    Note: In containerized deployments, container-level services
    are managed by Docker/orchestrator. This endpoint controls
    internal application services only.
    """
    if service_name not in MANAGED_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown service: {service_name}"
        )

    config = MANAGED_SERVICES[service_name]
    stop_cmd = config.get("stop_cmd")

    if not stop_cmd:
        raise HTTPException(
            status_code=503,
            detail=f"Service {service_name} is managed by Docker and cannot be stopped via API. "
                   "Use 'docker compose stop <service>' from the host."
        )

    try:
        proc = await asyncio.create_subprocess_shell(
            stop_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to stop {service_name}: {stderr.decode()}"
            )

        logger.info(f"Stopped service: {service_name}")
        return build_success_response({
            "service": service_name,
            "action": "stop",
            "success": True,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop {service_name}: {e}"
        )


@router.post("/{service_name}/restart")
async def restart_service(
    service_name: str = Path(..., description="Service name")
) -> dict[str, Any]:
    """
    Restart a service.

    Note: In containerized deployments, container-level services
    are managed by Docker/orchestrator. This endpoint controls
    internal application services only.
    """
    if service_name not in MANAGED_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown service: {service_name}"
        )

    config = MANAGED_SERVICES[service_name]
    restart_cmd = config.get("restart_cmd")

    if not restart_cmd:
        raise HTTPException(
            status_code=503,
            detail=f"Service {service_name} is managed by Docker and cannot be restarted via API. "
                   "Use 'docker compose restart <service>' from the host."
        )

    try:
        proc = await asyncio.create_subprocess_shell(
            restart_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to restart {service_name}: {stderr.decode()}"
            )

        logger.info(f"Restarted service: {service_name}")
        return build_success_response({
            "service": service_name,
            "action": "restart",
            "success": True,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restart {service_name}: {e}"
        )
