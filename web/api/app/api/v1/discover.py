"""
Water Treatment Controller - Network Discovery Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...models.base import get_db
from ...models.rtu import RTU

router = APIRouter()


class DiscoveryRequest(BaseModel):
    """Request for network discovery."""

    subnet: Optional[str] = Field(None, description="Subnet to scan (e.g., '192.168.1.0/24')")
    timeout_seconds: int = Field(10, ge=1, le=60, description="Discovery timeout")


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
    rtu_name: Optional[str] = None


class DiscoveryResponse(BaseModel):
    """Response for network discovery."""

    devices: List[DiscoveredDevice]
    scan_duration_seconds: float


@router.post("/rtu")
async def discover_rtus(
    request: Optional[DiscoveryRequest] = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Scan network for PROFINET devices.

    Uses PROFINET DCP (Discovery and Configuration Protocol).
    """
    start_time = time.time()

    # Get list of already configured RTUs
    existing_rtus = db.query(RTU).all()
    configured_ips = {r.ip_address for r in existing_rtus}
    ip_to_rtu = {r.ip_address: r.station_name for r in existing_rtus}

    # In a real implementation, this would:
    # 1. Send DCP Identify All multicast
    # 2. Wait for responses
    # 3. Parse device info from responses

    # For now, return empty list (no controller running)
    devices = []

    # Mock: if there are configured RTUs, show them as "discoverable"
    # This helps test the HMI without real hardware
    for rtu in existing_rtus:
        devices.append(DiscoveredDevice(
            ip_address=rtu.ip_address,
            mac_address="00:00:00:00:00:00",  # Unknown without real scan
            name_of_station=rtu.station_name,
            vendor="Unknown",
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
