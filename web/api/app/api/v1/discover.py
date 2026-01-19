"""
Water Treatment Controller - Network Discovery Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

import asyncio
import subprocess
import time
from datetime import datetime, timezone
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

# Simple in-memory cache for discovered devices
_discovery_cache: list[dict] = []
_cache_timestamp: str | None = None


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

    id: int  # Derived from MAC address hash
    mac_address: str
    ip_address: str | None
    device_name: str | None  # PROFINET station name
    vendor_name: str | None
    device_type: str | None
    vendor_id: int | None  # PROFINET vendor ID as integer
    device_id: int | None  # PROFINET device ID as integer
    discovered_at: str  # ISO timestamp
    added_to_registry: bool  # True if already configured in DB
    rtu_name: str | None = None  # Name in registry if configured


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
    now = datetime.now(timezone.utc).isoformat()

    def mac_to_id(mac: str) -> int:
        """Convert MAC address to a stable integer ID."""
        clean = mac.replace(":", "").replace("-", "").lower()
        # Use last 6 hex digits as ID (fits in 32-bit int)
        return int(clean[-6:], 16) if clean else 0

    # Try real DCP discovery via controller
    profinet = get_profinet_client()
    if profinet.is_controller_running():
        discovered = profinet.dcp_discover(timeout_ms)

        for dev in discovered:
            device_name = dev.get("device_name", "").lower()
            mac = dev.get("mac_address", "00:00:00:00:00:00")

            # Check if already configured
            added_to_registry = device_name in configured_stations or mac.lower() in configured_macs
            rtu_name = None
            if device_name in configured_stations:
                rtu_name = configured_stations[device_name].station_name

            devices.append(DiscoveredDevice(
                id=mac_to_id(mac),
                mac_address=mac,
                ip_address=dev.get("ip_address") or None,
                device_name=dev.get("device_name") or None,
                vendor_name=dev.get("vendor_name") or None,
                device_type=dev.get("device_type") or "PROFINET Device",
                vendor_id=dev.get("profinet_vendor_id"),
                device_id=dev.get("profinet_device_id"),
                discovered_at=now,
                added_to_registry=added_to_registry,
                rtu_name=rtu_name,
            ))
    else:
        # Controller not running - return configured RTUs for HMI testing
        for idx, rtu in enumerate(existing_rtus):
            # Parse hex vendor/device IDs if stored as strings
            vendor_id = rtu.vendor_id
            device_id = rtu.device_id
            if isinstance(vendor_id, str):
                vendor_id = int(vendor_id, 16) if vendor_id.startswith("0x") else int(vendor_id)
            if isinstance(device_id, str):
                device_id = int(device_id, 16) if device_id.startswith("0x") else int(device_id)

            devices.append(DiscoveredDevice(
                id=idx + 1,
                mac_address="00:00:00:00:00:00",
                ip_address=rtu.ip_address,
                device_name=rtu.station_name,
                vendor_name="Simulation Mode",
                device_type="Water Treatment RTU",
                vendor_id=vendor_id,
                device_id=device_id,
                discovered_at=now,
                added_to_registry=True,
                rtu_name=rtu.station_name,
            ))

    duration = time.time() - start_time

    response = DiscoveryResponse(
        devices=devices,
        scan_duration_seconds=round(duration, 2),
    )

    # Cache the results
    global _discovery_cache, _cache_timestamp
    _discovery_cache = [d.model_dump() for d in devices]
    _cache_timestamp = now

    return build_success_response(response.model_dump())


@router.get("/cached")
async def get_cached_discovery() -> dict[str, Any]:
    """
    Get previously discovered devices from cache.

    Returns the last scan results without performing a new network scan.
    """
    return build_success_response({
        "devices": _discovery_cache,
        "cached_at": _cache_timestamp,
    })


@router.delete("/cache")
async def clear_discovery_cache() -> dict[str, Any]:
    """
    Clear the discovery cache.
    """
    global _discovery_cache, _cache_timestamp
    _discovery_cache = []
    _cache_timestamp = None
    return build_success_response({"message": "Discovery cache cleared"})


class PingScanRequest(BaseModel):
    """Request for ping scan."""

    subnet: str = Field(..., description="Subnet to scan (e.g., '192.168.1.0/24')")
    timeout_ms: int = Field(500, ge=100, le=5000, description="Ping timeout per host in milliseconds")
    max_concurrent: int = Field(50, ge=1, le=255, description="Max concurrent pings")

    @field_validator("subnet")
    @classmethod
    def validate_subnet_cidr(cls, v: str) -> str:
        """Validate subnet is valid CIDR notation and /24 or smaller."""
        try:
            network = ipaddress.ip_network(v, strict=False)
            if network.prefixlen < 24:
                raise ValueError("Subnet must be /24 or smaller for safety")
            return str(network)
        except ValueError as e:
            raise ValueError(f"Invalid CIDR notation: {v}. {e}")


class PingResult(BaseModel):
    """Result of pinging a single host."""

    ip_address: str
    reachable: bool
    response_time_ms: float | None = None
    hostname: str | None = None


class PingScanResponse(BaseModel):
    """Response for ping scan."""

    subnet: str
    total_hosts: int
    reachable_count: int
    unreachable_count: int
    scan_duration_seconds: float
    results: list[PingResult]


async def ping_host(ip: str, timeout_ms: int) -> PingResult:
    """Ping a single host and return result."""
    timeout_sec = timeout_ms / 1000.0

    try:
        # Use system ping command (works on Linux)
        # -c 1: send 1 packet
        # -W: timeout in seconds
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", str(max(1, int(timeout_sec))), ip,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        start = time.time()
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec + 1)
        elapsed = (time.time() - start) * 1000  # Convert to ms

        if proc.returncode == 0:
            # Try to extract actual RTT from ping output
            output = stdout.decode()
            rtt = None
            for line in output.split("\n"):
                if "time=" in line:
                    try:
                        time_part = line.split("time=")[1].split()[0]
                        rtt = float(time_part.replace("ms", ""))
                    except (IndexError, ValueError):
                        rtt = elapsed
                    break

            return PingResult(
                ip_address=ip,
                reachable=True,
                response_time_ms=round(rtt or elapsed, 2),
            )
        else:
            return PingResult(ip_address=ip, reachable=False)

    except asyncio.TimeoutError:
        return PingResult(ip_address=ip, reachable=False)
    except Exception:
        return PingResult(ip_address=ip, reachable=False)


@router.post("/ping-scan")
async def ping_scan_subnet(request: PingScanRequest) -> dict[str, Any]:
    """
    Perform a ping scan of a subnet.

    Pings all hosts in the specified /24 (or smaller) subnet and returns
    which IPs respond. Useful for debugging when PROFINET discovery fails.
    """
    start_time = time.time()
    network = ipaddress.ip_network(request.subnet, strict=False)

    # Get all host IPs (excluding network and broadcast for /24+)
    hosts = list(network.hosts())
    total_hosts = len(hosts)

    # Ping all hosts concurrently with semaphore to limit parallelism
    semaphore = asyncio.Semaphore(request.max_concurrent)

    async def ping_with_semaphore(ip: str) -> PingResult:
        async with semaphore:
            return await ping_host(ip, request.timeout_ms)

    # Run all pings
    tasks = [ping_with_semaphore(str(ip)) for ip in hosts]
    results = await asyncio.gather(*tasks)

    # Sort results: reachable first, then by IP
    results.sort(key=lambda r: (not r.reachable, ipaddress.ip_address(r.ip_address)))

    reachable = [r for r in results if r.reachable]
    duration = time.time() - start_time

    response = PingScanResponse(
        subnet=request.subnet,
        total_hosts=total_hosts,
        reachable_count=len(reachable),
        unreachable_count=total_hosts - len(reachable),
        scan_duration_seconds=round(duration, 2),
        results=results,
    )

    return build_success_response(response.model_dump())
