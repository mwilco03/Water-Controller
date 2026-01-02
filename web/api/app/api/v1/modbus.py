"""
Water Treatment Controller - Modbus API Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

REST API for Modbus gateway configuration and register operations.
Provides endpoints for:
- Server configuration (TCP/RTU settings)
- Downstream device management (CRUD)
- Register mapping management (CRUD)
- Register read/write operations
- Gateway status and statistics
"""

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ...core.errors import build_success_response
from ...core.exceptions import CommunicationError, NotFoundError, ValidationError
from ...services.modbus_service import get_modbus_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ============== Pydantic Models ==============


class ModbusServerConfigUpdate(BaseModel):
    """Modbus server configuration update request."""
    tcp_enabled: bool = Field(default=True, description="Enable Modbus TCP server")
    tcp_port: int = Field(default=502, ge=1, le=65535, description="TCP port")
    tcp_bind_address: str = Field(default="0.0.0.0", description="TCP bind address")
    rtu_enabled: bool = Field(default=False, description="Enable Modbus RTU server")
    rtu_device: str = Field(default="/dev/ttyUSB0", description="RTU serial device")
    rtu_baud_rate: int = Field(default=9600, description="RTU baud rate")
    rtu_parity: str = Field(default="N", pattern="^[NEO]$", description="Parity (N/E/O)")
    rtu_data_bits: int = Field(default=8, ge=7, le=8, description="Data bits")
    rtu_stop_bits: int = Field(default=1, ge=1, le=2, description="Stop bits")
    rtu_slave_addr: int = Field(default=1, ge=1, le=247, description="RTU slave address")


class DownstreamDeviceCreate(BaseModel):
    """Create downstream Modbus device request."""
    name: str = Field(..., min_length=1, max_length=64, description="Device name")
    transport: str = Field(..., pattern="^(tcp|rtu)$", description="Transport type")
    tcp_host: str | None = Field(None, description="TCP host (required for TCP)")
    tcp_port: int = Field(default=502, ge=1, le=65535, description="TCP port")
    rtu_device: str | None = Field(None, description="RTU serial device")
    rtu_baud_rate: int = Field(default=9600, description="RTU baud rate")
    slave_addr: int = Field(..., ge=1, le=247, description="Modbus slave address")
    poll_interval_ms: int = Field(default=1000, ge=100, le=60000, description="Poll interval")
    timeout_ms: int = Field(default=1000, ge=100, le=30000, description="Request timeout")
    enabled: bool = Field(default=True, description="Enable device polling")
    description: str | None = Field(None, max_length=256, description="Device description")


class DownstreamDeviceUpdate(DownstreamDeviceCreate):
    """Update downstream Modbus device request."""
    pass


class RegisterMappingCreate(BaseModel):
    """Create register mapping request."""
    modbus_addr: int = Field(..., ge=0, le=65535, description="Modbus register address")
    register_type: str = Field(
        ..., pattern="^(holding|input|coil|discrete)$",
        description="Register type"
    )
    data_type: str = Field(
        default="uint16",
        pattern="^(uint16|int16|uint32|int32|float32)$",
        description="Data type"
    )
    source_type: str = Field(
        ..., pattern="^(sensor|control)$",
        description="Source type (sensor or control)"
    )
    rtu_station: str = Field(..., min_length=1, description="RTU station name")
    slot: int = Field(..., ge=1, le=64, description="Slot number")
    description: str | None = Field(None, max_length=256, description="Mapping description")
    scaling_enabled: bool = Field(default=False, description="Enable value scaling")
    scale_raw_min: float = Field(default=0, description="Raw value minimum")
    scale_raw_max: float = Field(default=65535, description="Raw value maximum")
    scale_eng_min: float = Field(default=0, description="Engineering value minimum")
    scale_eng_max: float = Field(default=100, description="Engineering value maximum")


class RegisterMappingUpdate(RegisterMappingCreate):
    """Update register mapping request."""
    pass


class RegisterWrite(BaseModel):
    """Write register request."""
    value: int = Field(..., ge=0, le=65535, description="Value to write")


# ============== Server Configuration ==============


@router.get("/server/config")
async def get_server_config() -> dict[str, Any]:
    """
    Get Modbus server configuration.

    Returns current TCP and RTU server settings.
    """
    service = get_modbus_service()
    config = service.get_server_config()
    return build_success_response(config)


@router.put("/server/config")
async def update_server_config(
    config: ModbusServerConfigUpdate = Body(...)
) -> dict[str, Any]:
    """
    Update Modbus server configuration.

    Changes take effect on next server restart.
    """
    service = get_modbus_service()
    service.update_server_config(config.model_dump())
    updated = service.get_server_config()
    return build_success_response(updated)


# ============== Gateway Status ==============


@router.get("/status")
async def get_gateway_status() -> dict[str, Any]:
    """
    Get Modbus gateway status.

    Returns status of server, all downstream devices, and mapping count.
    """
    service = get_modbus_service()
    status = service.get_gateway_status()
    return build_success_response(status)


# ============== Downstream Devices ==============


@router.get("/devices")
async def list_devices() -> dict[str, Any]:
    """
    List all downstream Modbus devices.
    """
    service = get_modbus_service()
    devices = service.get_devices()
    return build_success_response(devices)


@router.get("/devices/{device_id}")
async def get_device(
    device_id: int = Path(..., ge=1, description="Device ID")
) -> dict[str, Any]:
    """
    Get a specific downstream device.
    """
    try:
        service = get_modbus_service()
        device = service.get_device(device_id)
        return build_success_response(device)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/devices", status_code=201)
async def create_device(
    device: DownstreamDeviceCreate = Body(...)
) -> dict[str, Any]:
    """
    Create a new downstream Modbus device.
    """
    try:
        service = get_modbus_service()
        device_id = service.create_device(device.model_dump())
        created = service.get_device(device_id)
        return build_success_response(created)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/devices/{device_id}")
async def update_device(
    device_id: int = Path(..., ge=1, description="Device ID"),
    device: DownstreamDeviceUpdate = Body(...)
) -> dict[str, Any]:
    """
    Update a downstream Modbus device.
    """
    try:
        service = get_modbus_service()
        service.update_device(device_id, device.model_dump())
        updated = service.get_device(device_id)
        return build_success_response(updated)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(
    device_id: int = Path(..., ge=1, description="Device ID")
) -> None:
    """
    Delete a downstream Modbus device.
    """
    try:
        service = get_modbus_service()
        service.delete_device(device_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============== Register Mappings ==============


@router.get("/mappings")
async def list_mappings() -> dict[str, Any]:
    """
    List all register mappings.
    """
    service = get_modbus_service()
    mappings = service.get_mappings()
    return build_success_response(mappings)


@router.get("/mappings/{mapping_id}")
async def get_mapping(
    mapping_id: int = Path(..., ge=1, description="Mapping ID")
) -> dict[str, Any]:
    """
    Get a specific register mapping.
    """
    try:
        service = get_modbus_service()
        mapping = service.get_mapping(mapping_id)
        return build_success_response(mapping)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/mappings", status_code=201)
async def create_mapping(
    mapping: RegisterMappingCreate = Body(...)
) -> dict[str, Any]:
    """
    Create a new register mapping.

    Maps a Modbus register address to an RTU slot.
    """
    try:
        service = get_modbus_service()
        mapping_id = service.create_mapping(mapping.model_dump())
        created = service.get_mapping(mapping_id)
        return build_success_response(created)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/mappings/{mapping_id}")
async def update_mapping(
    mapping_id: int = Path(..., ge=1, description="Mapping ID"),
    mapping: RegisterMappingUpdate = Body(...)
) -> dict[str, Any]:
    """
    Update a register mapping.
    """
    try:
        service = get_modbus_service()
        service.update_mapping(mapping_id, mapping.model_dump())
        updated = service.get_mapping(mapping_id)
        return build_success_response(updated)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/mappings/{mapping_id}", status_code=204)
async def delete_mapping(
    mapping_id: int = Path(..., ge=1, description="Mapping ID")
) -> None:
    """
    Delete a register mapping.
    """
    try:
        service = get_modbus_service()
        service.delete_mapping(mapping_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============== Register Operations ==============


@router.get("/devices/{device_name}/registers")
async def read_registers(
    device_name: str = Path(..., min_length=1, description="Device name"),
    register_type: str = Query(
        "holding",
        pattern="^(holding|input|coil|discrete)$",
        description="Register type"
    ),
    start_addr: int = Query(..., ge=0, le=65535, description="Starting address"),
    count: int = Query(1, ge=1, le=125, description="Number of registers")
) -> dict[str, Any]:
    """
    Read registers from a downstream Modbus device.

    Returns list of {address, value} pairs.
    """
    try:
        service = get_modbus_service()
        values = service.read_registers(device_name, register_type, start_addr, count)
        return build_success_response({
            "device": device_name,
            "register_type": register_type,
            "registers": values
        })
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CommunicationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/devices/{device_name}/registers/{addr}")
async def write_register(
    device_name: str = Path(..., min_length=1, description="Device name"),
    addr: int = Path(..., ge=0, le=65535, description="Register address"),
    register_type: str = Query(
        "holding",
        pattern="^(holding|coil)$",
        description="Register type (holding or coil)"
    ),
    body: RegisterWrite = Body(...)
) -> dict[str, Any]:
    """
    Write a single register to a downstream Modbus device.

    Only holding registers and coils can be written.
    """
    try:
        service = get_modbus_service()
        service.write_register(device_name, register_type, addr, body.value)
        return build_success_response({
            "device": device_name,
            "register_type": register_type,
            "address": addr,
            "value": body.value,
            "success": True
        })
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CommunicationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
