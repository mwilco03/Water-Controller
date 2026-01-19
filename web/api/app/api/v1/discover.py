"""
Water Treatment Controller - Network Discovery Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Real network discovery using PROFINET DCP and ICMP ping.
Requires host network mode and CAP_NET_RAW for full functionality.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import ipaddress

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...models.base import get_db
from ...models.rtu import RTU
from ...services.dcp_discovery import discover_profinet_devices

logger = logging.getLogger(__name__)

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
    Scan network for PROFINET devices using DCP multicast.

    Performs real PROFINET DCP (Discovery and Configuration Protocol)
    discovery on the physical network. Requires:
    - Host network mode (network_mode: host in docker-compose)
    - CAP_NET_RAW capability

    Returns discovered devices with their IP addresses, station names,
    and vendor information. Also indicates if devices are already
    registered in the system.
    """
    start_time = time.time()
    timeout_sec = request.timeout_seconds if request else 10

    # Get list of already configured RTUs for matching
    existing_rtus = db.query(RTU).all()
    configured_stations = {rtu.station_name.lower(): rtu for rtu in existing_rtus}
    configured_ips = {rtu.ip_address: rtu for rtu in existing_rtus}

    devices = []
    now = datetime.now(timezone.utc).isoformat()

    def mac_to_id(mac: str) -> int:
        """Convert MAC address to a stable integer ID."""
        clean = mac.replace(":", "").replace("-", "").lower()
        return int(clean[-6:], 16) if clean else 0

    # Get network interface from environment
    interface = os.environ.get("WTC_INTERFACE", "eth0")

    # Perform real DCP discovery
    logger.info(f"Starting DCP discovery on {interface} (timeout: {timeout_sec}s)")

    try:
        discovered = await discover_profinet_devices(
            interface=interface,
            timeout_sec=float(timeout_sec)
        )
        logger.info(f"DCP discovery found {len(discovered)} devices")

        for dev in discovered:
            device_name = (dev.get("device_name") or "").lower()
            mac = dev.get("mac_address", "00:00:00:00:00:00")
            ip = dev.get("ip_address")

            # Check if already configured (by station name or IP)
            added_to_registry = False
            rtu_name = None

            if device_name and device_name in configured_stations:
                added_to_registry = True
                rtu_name = configured_stations[device_name].station_name
            elif ip and ip in configured_ips:
                added_to_registry = True
                rtu_name = configured_ips[ip].station_name

            devices.append(DiscoveredDevice(
                id=mac_to_id(mac),
                mac_address=mac,
                ip_address=ip,
                device_name=dev.get("device_name"),
                vendor_name=dev.get("vendor_name"),
                device_type=dev.get("device_type") or "PROFINET Device",
                vendor_id=dev.get("profinet_vendor_id"),
                device_id=dev.get("profinet_device_id"),
                discovered_at=now,
                added_to_registry=added_to_registry,
                rtu_name=rtu_name,
            ))

    except PermissionError:
        logger.error("DCP discovery failed: CAP_NET_RAW capability required")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "DISCOVERY_PERMISSION_DENIED",
                "message": "DCP discovery requires CAP_NET_RAW capability",
                "suggested_action": "Ensure container has cap_add: [NET_RAW] in docker-compose.yml"
            }
        )
    except OSError as e:
        logger.error(f"DCP discovery failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "DISCOVERY_NETWORK_ERROR",
                "message": f"Network error during DCP discovery: {e}",
                "suggested_action": f"Verify interface {interface} exists and container has network_mode: host"
            }
        )

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
    which IPs respond. Requires host network mode to reach physical network.

    Returns reachable hosts with response times. Useful for:
    - Verifying network connectivity before DCP discovery
    - Finding devices that don't respond to PROFINET DCP
    - Debugging network issues
    """
    start_time = time.time()
    network = ipaddress.ip_network(request.subnet, strict=False)

    # Get all host IPs (excluding network and broadcast for /24+)
    hosts = list(network.hosts())
    total_hosts = len(hosts)

    logger.info(f"Starting ping scan of {request.subnet} ({total_hosts} hosts)")

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

    logger.info(f"Ping scan complete: {len(reachable)}/{total_hosts} hosts reachable in {duration:.2f}s")

    # Warn if no hosts reachable - likely network isolation issue
    if len(reachable) == 0:
        logger.warning(
            f"No hosts reachable in {request.subnet}. "
            "Check that container has network_mode: host in docker-compose.yml"
        )

    response = PingScanResponse(
        subnet=request.subnet,
        total_hosts=total_hosts,
        reachable_count=len(reachable),
        unreachable_count=total_hosts - len(reachable),
        scan_duration_seconds=round(duration, 2),
        results=results,
    )

    return build_success_response(response.model_dump())
