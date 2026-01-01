"""
Water Treatment Controller - Network Discovery Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

import time
from typing import Any

import ipaddress

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...models.base import get_db
from ...models.rtu import RTU
from ...services.profinet_client import get_profinet_client

router = APIRouter()


class DiscoveryRequest(BaseModel):
    """Request for network discovery."""

    subnet: str | None = Field(None, description="Subnet to scan (e.g., '192.168.1.0/24')")
    timeout_seconds: int = Field(10, ge=1, le=60, description="Discovery timeout")

    @field_validator("subnet")
    @classmethod
    def validate_subnet_cidr(cls, v: str | None) -> str | None:
        """Validate subnet is valid CIDR notation."""
        if v is None:
            return None
        try:
            ipaddress.ip_network(v, strict=False)
            return v
        except ValueError as e:
            raise ValueError(f"Invalid CIDR notation: {v}. {e}")


class DiscoveredDevice(BaseModel):
    """Device discovered on the network."""

    ip_address: str
    mac_address: str
    name_of_station: str
    vendor: str
    vendor_id: str
    device_type: str
    device_id: str
    already_configured: bool
    rtu_name: str | None = None


class DiscoveryResponse(BaseModel):
    """Response for network discovery."""

    devices: list[DiscoveredDevice]
    scan_duration_seconds: float


@router.post("/rtu")
async def discover_rtus(
    request: DiscoveryRequest | None = None,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Scan network for PROFINET devices.

    Uses PROFINET DCP (Discovery and Configuration Protocol).
    When the C controller is running, performs real network discovery.
    Otherwise, returns configured RTUs for testing.
    """
    start_time = time.time()
    timeout_ms = (request.timeout_seconds * 1000) if request else 10000

    # Get list of already configured RTUs for matching
    existing_rtus = db.query(RTU).all()
    configured_stations = {rtu.station_name.lower(): rtu for rtu in existing_rtus}
    configured_macs = {getattr(rtu, 'mac_address', '').lower() for rtu in existing_rtus if hasattr(rtu, 'mac_address')}

    devices = []

    # Try real DCP discovery via controller
    profinet = get_profinet_client()
    if profinet.is_controller_running():
        discovered = profinet.dcp_discover(timeout_ms)

        for dev in discovered:
            device_name = dev.get("device_name", "").lower()
            mac = dev.get("mac_address", "").lower()

            # Check if already configured
            already_configured = device_name in configured_stations or mac in configured_macs
            rtu_name = None
            if device_name in configured_stations:
                rtu_name = configured_stations[device_name].station_name

            devices.append(DiscoveredDevice(
                ip_address=dev.get("ip_address") or "0.0.0.0",
                mac_address=dev.get("mac_address", "00:00:00:00:00:00"),
                name_of_station=dev.get("device_name", "unknown"),
                vendor=dev.get("vendor_name", "Unknown"),
                vendor_id=hex(dev.get("profinet_vendor_id", 0)),
                device_type=dev.get("device_type", "PROFINET Device"),
                device_id=hex(dev.get("profinet_device_id", 0)),
                already_configured=already_configured,
                rtu_name=rtu_name,
            ))
    else:
        # Controller not running - return configured RTUs for HMI testing
        for rtu in existing_rtus:
            devices.append(DiscoveredDevice(
                ip_address=rtu.ip_address,
                mac_address="00:00:00:00:00:00",
                name_of_station=rtu.station_name,
                vendor="Unknown (simulation mode)",
                vendor_id=rtu.vendor_id,
                device_type="Water Treatment RTU",
                device_id=rtu.device_id,
                already_configured=True,
                rtu_name=rtu.station_name,
            ))

    duration = time.time() - start_time

    response = DiscoveryResponse(
        devices=devices,
        scan_duration_seconds=round(duration, 2),
    )

    return build_success_response(response.model_dump())
