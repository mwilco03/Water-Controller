"""
Water Treatment Controller - Network Discovery Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Real network discovery using PROFINET DCP and ICMP ping.

ICMP ping uses icmplib with unprivileged mode (SOCK_DGRAM) by default,
falling back to privileged mode (SOCK_RAW + CAP_NET_RAW) if needed.

DCP discovery still requires CAP_NET_RAW for raw Ethernet frames.
"""

import asyncio
import logging
import socket
import time
from datetime import datetime, timezone
from typing import Any

import ipaddress

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

# icmplib for ICMP ping - supports unprivileged mode without CAP_NET_RAW
from icmplib import async_ping, async_multiping, SocketPermissionError

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

    # Get network interface - use auto-detection if not specified
    from ...core.network import get_profinet_interface
    try:
        interface = get_profinet_interface()
    except RuntimeError as e:
        logger.error(f"No network interface available: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"No network interface available for DCP discovery: {e}"
        )

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
    error: str | None = None


class PingScanResponse(BaseModel):
    """Response for ping scan."""

    subnet: str
    total_hosts: int
    reachable_count: int
    unreachable_count: int
    scan_duration_seconds: float
    results: list[PingResult]


# Cache for privileged mode detection - check once at startup
_icmp_privileged_mode: bool | None = None


def _detect_icmp_privileged_mode() -> bool:
    """
    Detect whether we need privileged mode for ICMP.

    Returns True if privileged mode (CAP_NET_RAW) is required,
    False if unprivileged mode (SOCK_DGRAM) works.

    This is cached after first call for performance.
    """
    global _icmp_privileged_mode
    if _icmp_privileged_mode is not None:
        return _icmp_privileged_mode

    # Try unprivileged mode first (preferred - no CAP_NET_RAW needed)
    try:
        # Test with a count=0 ping to localhost - just checks socket creation
        from icmplib import ping as sync_ping
        sync_ping("127.0.0.1", count=0, timeout=0, privileged=False)
        _icmp_privileged_mode = False
        logger.info("ICMP: Using unprivileged mode (SOCK_DGRAM) - no CAP_NET_RAW needed")
        return False
    except SocketPermissionError:
        pass

    # Try privileged mode (requires CAP_NET_RAW)
    try:
        from icmplib import ping as sync_ping
        sync_ping("127.0.0.1", count=0, timeout=0, privileged=True)
        _icmp_privileged_mode = True
        logger.info("ICMP: Using privileged mode (SOCK_RAW) - CAP_NET_RAW available")
        return True
    except SocketPermissionError:
        pass

    # Neither mode works - will fail at runtime with clear error
    logger.error(
        "ICMP: Neither privileged nor unprivileged mode available. "
        "Set net.ipv4.ping_group_range or add CAP_NET_RAW capability."
    )
    _icmp_privileged_mode = True  # Default to privileged, will fail with clear error
    return True


async def icmp_ping_scan(hosts: list[str], timeout_sec: float = 2.0) -> dict[str, PingResult]:
    """
    Perform ICMP ping scan using icmplib.

    Uses unprivileged mode (SOCK_DGRAM) if available, falling back to
    privileged mode (SOCK_RAW + CAP_NET_RAW) if needed.

    Much faster than spawning ping processes - can scan 254 hosts in ~2 seconds.
    """
    results: dict[str, PingResult] = {}
    privileged = _detect_icmp_privileged_mode()

    try:
        # Use icmplib's async_multiping for efficient batch scanning
        ping_results = await async_multiping(
            hosts,
            count=1,
            timeout=timeout_sec,
            privileged=privileged,
            concurrent_tasks=50,
        )

        for host_result in ping_results:
            ip = host_result.address
            if host_result.is_alive:
                results[ip] = PingResult(
                    ip_address=ip,
                    reachable=True,
                    response_time_ms=round(host_result.avg_rtt, 2) if host_result.avg_rtt else None,
                )
            else:
                results[ip] = PingResult(
                    ip_address=ip,
                    reachable=False,
                )

    except SocketPermissionError as e:
        logger.error(f"ICMP ping failed - insufficient permissions: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ICMP_PERMISSION_DENIED",
                "message": "Cannot create ICMP socket - insufficient permissions",
                "suggested_action": (
                    "Either set 'net.ipv4.ping_group_range=0 65535' in container, "
                    "or add CAP_NET_RAW capability"
                ),
            }
        )
    except Exception as e:
        logger.error(f"ICMP ping scan failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ICMP_SCAN_ERROR",
                "message": f"Ping scan failed: {e}",
                "suggested_action": "Check network configuration",
            }
        )

    # Ensure all requested hosts have results
    for ip in hosts:
        if ip not in results:
            results[ip] = PingResult(ip_address=ip, reachable=False)

    return results


class PortScanRequest(BaseModel):
    """Request for TCP port scan to find RTUs."""

    subnet: str = Field(..., description="Subnet to scan (e.g., '192.168.1.0/24')")
    port: int = Field(9081, ge=1, le=65535, description="TCP port to scan")
    timeout_ms: int = Field(1000, ge=100, le=10000, description="Connection timeout per host in ms")
    max_concurrent: int = Field(50, ge=1, le=255, description="Max concurrent connections")
    fetch_info: bool = Field(True, description="Fetch RTU info from responding hosts")

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


class PortScanResult(BaseModel):
    """Result of scanning a single host."""

    ip_address: str
    port: int
    open: bool
    response_time_ms: float | None = None
    rtu_info: dict | None = None  # Info fetched from RTU API


class PortScanResponse(BaseModel):
    """Response for port scan."""

    subnet: str
    port: int
    total_hosts: int
    open_count: int
    scan_duration_seconds: float
    results: list[PortScanResult]


async def check_port(ip: str, port: int, timeout_ms: int, fetch_info: bool) -> PortScanResult:
    """Check if TCP port is open and optionally fetch RTU info."""
    timeout_sec = timeout_ms / 1000.0

    try:
        start = time.time()

        # Try TCP connection
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=timeout_sec
        )
        elapsed = (time.time() - start) * 1000

        writer.close()
        await writer.wait_closed()

        result = PortScanResult(
            ip_address=ip,
            port=port,
            open=True,
            response_time_ms=round(elapsed, 2),
        )

        # Optionally fetch RTU info via HTTP
        if fetch_info:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    # Try common RTU info endpoints
                    for endpoint in ["/api/info", "/api/status", "/info", "/status", "/"]:
                        try:
                            resp = await client.get(f"http://{ip}:{port}{endpoint}")
                            if resp.status_code == 200:
                                try:
                                    data = resp.json()
                                except Exception:
                                    data = {"raw": resp.text[:500]}
                                result.rtu_info = {
                                    "endpoint": endpoint,
                                    "data": data
                                }
                                break
                        except Exception:
                            continue
            except Exception as e:
                logger.debug(f"Failed to fetch RTU info from {ip}:{port}: {e}")

        return result

    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return PortScanResult(ip_address=ip, port=port, open=False)
    except Exception:
        return PortScanResult(ip_address=ip, port=port, open=False)


@router.post("/port-scan")
async def port_scan_subnet(request: PortScanRequest) -> dict[str, Any]:
    """
    Scan subnet for RTUs by TCP port (default: 9081).

    Performs a TCP connect scan to find Water-Treat RTUs exposing their
    HTTP API. This is an alternative to PROFINET DCP for RTUs that
    expose a REST interface.

    If fetch_info is True (default), attempts to GET RTU info from
    responding hosts at common API endpoints.

    Returns list of hosts with open port and optional RTU info.
    """
    start_time = time.time()
    network = ipaddress.ip_network(request.subnet, strict=False)

    hosts = list(network.hosts())
    total_hosts = len(hosts)

    logger.info(f"Starting port scan of {request.subnet}:{request.port} ({total_hosts} hosts)")

    semaphore = asyncio.Semaphore(request.max_concurrent)

    async def scan_with_semaphore(ip: str) -> PortScanResult:
        async with semaphore:
            return await check_port(ip, request.port, request.timeout_ms, request.fetch_info)

    tasks = [scan_with_semaphore(str(ip)) for ip in hosts]
    results = await asyncio.gather(*tasks)

    # Filter to only open ports and sort by IP
    open_results = [r for r in results if r.open]
    open_results.sort(key=lambda r: ipaddress.ip_address(r.ip_address))

    duration = time.time() - start_time

    logger.info(f"Port scan complete: {len(open_results)}/{total_hosts} hosts have port {request.port} open")

    response = PortScanResponse(
        subnet=request.subnet,
        port=request.port,
        total_hosts=total_hosts,
        open_count=len(open_results),
        scan_duration_seconds=round(duration, 2),
        results=open_results,  # Only return open ports
    )

    return build_success_response(response.model_dump())


@router.post("/ping-scan")
async def ping_scan_subnet(request: PingScanRequest) -> dict[str, Any]:
    """
    Perform a ping scan of a subnet using raw ICMP packets.

    Uses raw sockets for high-performance scanning - can scan 254 hosts in ~2 seconds.
    Requires CAP_NET_RAW capability and host network mode.

    Returns reachable hosts with response times. Useful for:
    - Verifying network connectivity before DCP discovery
    - Finding devices that don't respond to PROFINET DCP
    - Debugging network issues
    """
    start_time = time.time()
    network = ipaddress.ip_network(request.subnet, strict=False)

    # Get all host IPs (excluding network and broadcast for /24+)
    hosts = [str(ip) for ip in network.hosts()]
    total_hosts = len(hosts)

    logger.info(f"Starting ICMP ping scan of {request.subnet} ({total_hosts} hosts)")

    # Use raw ICMP for fast batch scanning
    timeout_sec = request.timeout_ms / 1000.0
    results_dict = await icmp_ping_scan(hosts, timeout_sec)

    # Convert to sorted list
    results = list(results_dict.values())
    results.sort(key=lambda r: (not r.reachable, ipaddress.ip_address(r.ip_address)))

    reachable = [r for r in results if r.reachable]
    duration = time.time() - start_time

    logger.info(f"ICMP scan complete: {len(reachable)}/{total_hosts} hosts reachable in {duration:.2f}s")

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


# ==================== Single Host Ping ====================


class SinglePingRequest(BaseModel):
    """Request for single host ping."""

    ip_address: str = Field(..., description="IP address to ping")
    timeout_ms: int = Field(1000, ge=100, le=10000, description="Ping timeout in milliseconds")
    count: int = Field(3, ge=1, le=10, description="Number of ping attempts")

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        """Validate IP address."""
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid IP address: {v}")


class SinglePingResponse(BaseModel):
    """Response for single host ping."""

    ip_address: str
    reachable: bool
    packets_sent: int
    packets_received: int
    packet_loss_percent: float
    min_rtt_ms: float | None = None
    avg_rtt_ms: float | None = None
    max_rtt_ms: float | None = None
    error: str | None = None


@router.post("/ping")
async def ping_single_host(request: SinglePingRequest) -> dict[str, Any]:
    """
    Ping a single IP address using ICMP echo requests.

    Performs multiple ping attempts (default 3) and returns statistics
    including packet loss and round-trip times.

    Uses unprivileged ICMP (SOCK_DGRAM) if available, falling back to
    privileged mode (SOCK_RAW + CAP_NET_RAW) if needed.

    Use this endpoint to:
    - Verify connectivity to a specific RTU before configuration
    - Diagnose network issues with a particular device
    - Check if a host is reachable before DCP discovery
    """
    logger.info(f"Pinging {request.ip_address} ({request.count} attempts, timeout {request.timeout_ms}ms)")

    timeout_sec = request.timeout_ms / 1000.0
    privileged = _detect_icmp_privileged_mode()

    try:
        # Use icmplib's async_ping for single host
        result = await async_ping(
            request.ip_address,
            count=request.count,
            timeout=timeout_sec,
            privileged=privileged,
        )

        response = SinglePingResponse(
            ip_address=request.ip_address,
            reachable=result.is_alive,
            packets_sent=result.packets_sent,
            packets_received=result.packets_received,
            packet_loss_percent=round(result.packet_loss * 100, 1),
            min_rtt_ms=round(result.min_rtt, 2) if result.min_rtt else None,
            avg_rtt_ms=round(result.avg_rtt, 2) if result.avg_rtt else None,
            max_rtt_ms=round(result.max_rtt, 2) if result.max_rtt else None,
        )

        logger.info(
            f"Ping {request.ip_address}: {result.packets_received}/{result.packets_sent} received, "
            f"{result.packet_loss * 100:.1f}% loss"
            + (f", avg RTT {result.avg_rtt:.2f}ms" if result.avg_rtt else "")
        )

        return build_success_response(response.model_dump())

    except SocketPermissionError as e:
        logger.error(f"ICMP ping failed - insufficient permissions: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ICMP_PERMISSION_DENIED",
                "message": "Cannot create ICMP socket - insufficient permissions",
                "suggested_action": (
                    "Either set 'net.ipv4.ping_group_range=0 65535' in container, "
                    "or add CAP_NET_RAW capability"
                ),
            }
        )
    except Exception as e:
        logger.error(f"ICMP ping failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ICMP_PING_ERROR",
                "message": f"Ping failed: {e}",
                "suggested_action": "Check network configuration",
            }
        )


@router.get("/ping/{ip_address}")
async def ping_single_host_get(
    ip_address: str,
    timeout_ms: int = 1000,
    count: int = 3,
) -> dict[str, Any]:
    """
    Ping a single IP address (GET variant for convenience).

    Simpler alternative to POST /ping for quick connectivity checks.
    Same functionality as POST /ping but with query parameters.

    Uses unprivileged ICMP if available, privileged mode otherwise.
    """
    # Validate IP address
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid IP address: {ip_address}")

    # Validate parameters
    if not (100 <= timeout_ms <= 10000):
        raise HTTPException(status_code=400, detail="timeout_ms must be between 100 and 10000")
    if not (1 <= count <= 10):
        raise HTTPException(status_code=400, detail="count must be between 1 and 10")

    request = SinglePingRequest(ip_address=ip_address, timeout_ms=timeout_ms, count=count)
    return await ping_single_host(request)


# ==================== HTTP Probe ====================


class HttpProbeRequest(BaseModel):
    """Request for HTTP probe."""

    ip_address: str = Field(..., description="IP address to probe")
    port: int = Field(8000, ge=1, le=65535, description="Port to connect to")
    path: str = Field("/health", description="URL path to request")
    timeout_ms: int = Field(3000, ge=100, le=30000, description="Request timeout in milliseconds")

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        """Validate IP address."""
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid IP address: {v}")


class HttpProbeResult(BaseModel):
    """Result of HTTP probe."""

    ip_address: str
    port: int
    path: str
    reachable: bool
    status_code: int | None = None
    response_time_ms: float | None = None
    response_body: str | None = None
    error: str | None = None
    is_water_treat_rtu: bool = False


@router.post("/http-probe")
async def http_probe_rtu(request: HttpProbeRequest) -> dict[str, Any]:
    """
    Probe an RTU via HTTP to check its health API.

    Makes an HTTP GET request to the specified IP:port/path and returns
    the response. Useful for verifying RTU connectivity and checking
    if a device is a Water-Treat RTU.

    Returns:
        - status_code: HTTP response code (if reachable)
        - response_body: Response text (truncated to 4KB)
        - is_water_treat_rtu: True if response looks like Water-Treat RTU
        - error: Error message if request failed
    """
    import httpx

    url = f"http://{request.ip_address}:{request.port}{request.path}"
    timeout_sec = request.timeout_ms / 1000.0

    logger.info(f"HTTP probe: {url} (timeout: {timeout_sec}s)")

    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            response = await client.get(url)
        elapsed = (time.time() - start) * 1000

        # Truncate response body to 4KB
        body = response.text[:4096] if response.text else None

        # Check if this looks like a Water-Treat RTU
        is_wt_rtu = False
        if body:
            # Look for Water-Treat RTU signatures in response
            lower_body = body.lower()
            if any(sig in lower_body for sig in ["water-treat", "watertreatrtu", "wtc-rtu", "rtu_status"]):
                is_wt_rtu = True

        result = HttpProbeResult(
            ip_address=request.ip_address,
            port=request.port,
            path=request.path,
            reachable=True,
            status_code=response.status_code,
            response_time_ms=round(elapsed, 2),
            response_body=body,
            is_water_treat_rtu=is_wt_rtu,
        )

        logger.info(f"HTTP probe {url}: {response.status_code} in {elapsed:.1f}ms")
        return build_success_response(result.model_dump())

    except httpx.ConnectTimeout:
        logger.warning(f"HTTP probe {url}: connection timeout")
        return build_success_response(HttpProbeResult(
            ip_address=request.ip_address,
            port=request.port,
            path=request.path,
            reachable=False,
            error=f"Connection timeout after {request.timeout_ms}ms",
        ).model_dump())

    except httpx.ConnectError as e:
        logger.warning(f"HTTP probe {url}: connection refused - {e}")
        return build_success_response(HttpProbeResult(
            ip_address=request.ip_address,
            port=request.port,
            path=request.path,
            reachable=False,
            error=f"Connection refused: {e}",
        ).model_dump())

    except httpx.ReadTimeout:
        logger.warning(f"HTTP probe {url}: read timeout")
        return build_success_response(HttpProbeResult(
            ip_address=request.ip_address,
            port=request.port,
            path=request.path,
            reachable=False,
            error=f"Read timeout after {request.timeout_ms}ms",
        ).model_dump())

    except Exception as e:
        logger.error(f"HTTP probe {url} failed: {type(e).__name__}: {e}")
        return build_success_response(HttpProbeResult(
            ip_address=request.ip_address,
            port=request.port,
            path=request.path,
            reachable=False,
            error=f"{type(e).__name__}: {e}",
        ).model_dump())


class HttpProbeBatchRequest(BaseModel):
    """Request for batch HTTP probe."""

    ip_addresses: list[str] = Field(..., description="List of IP addresses to probe")
    port: int = Field(8000, ge=1, le=65535, description="Port to connect to")
    path: str = Field("/health", description="URL path to request")
    timeout_ms: int = Field(2000, ge=100, le=10000, description="Request timeout per host")
    max_concurrent: int = Field(10, ge=1, le=50, description="Max concurrent requests")


@router.post("/http-probe-batch")
async def http_probe_batch(request: HttpProbeBatchRequest) -> dict[str, Any]:
    """
    Probe multiple RTUs via HTTP in parallel.

    Makes HTTP GET requests to all specified IPs and returns results.
    Useful for scanning a subnet after ping-scan to identify Water-Treat RTUs.
    """
    import httpx

    results: list[HttpProbeResult] = []
    semaphore = asyncio.Semaphore(request.max_concurrent)
    timeout_sec = request.timeout_ms / 1000.0

    async def probe_one(ip: str) -> HttpProbeResult:
        url = f"http://{ip}:{request.port}{request.path}"
        async with semaphore:
            try:
                start = time.time()
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    response = await client.get(url)
                elapsed = (time.time() - start) * 1000

                body = response.text[:4096] if response.text else None
                is_wt_rtu = False
                if body:
                    lower_body = body.lower()
                    if any(sig in lower_body for sig in ["water-treat", "watertreatrtu", "wtc-rtu", "rtu_status"]):
                        is_wt_rtu = True

                return HttpProbeResult(
                    ip_address=ip,
                    port=request.port,
                    path=request.path,
                    reachable=True,
                    status_code=response.status_code,
                    response_time_ms=round(elapsed, 2),
                    response_body=body,
                    is_water_treat_rtu=is_wt_rtu,
                )
            except Exception as e:
                return HttpProbeResult(
                    ip_address=ip,
                    port=request.port,
                    path=request.path,
                    reachable=False,
                    error=f"{type(e).__name__}: {e}",
                )

    start_time = time.time()
    tasks = [probe_one(ip) for ip in request.ip_addresses]
    results = await asyncio.gather(*tasks)
    duration = time.time() - start_time

    # Sort: reachable first, then Water-Treat RTUs first
    results.sort(key=lambda r: (not r.reachable, not r.is_water_treat_rtu, r.ip_address))

    reachable = [r for r in results if r.reachable]
    water_treat_rtus = [r for r in results if r.is_water_treat_rtu]

    logger.info(
        f"HTTP batch probe complete: {len(reachable)}/{len(request.ip_addresses)} reachable, "
        f"{len(water_treat_rtus)} Water-Treat RTUs in {duration:.2f}s"
    )

    return build_success_response({
        "total_probed": len(request.ip_addresses),
        "reachable_count": len(reachable),
        "water_treat_rtu_count": len(water_treat_rtus),
        "scan_duration_seconds": round(duration, 2),
        "results": [r.model_dump() for r in results],
    })
