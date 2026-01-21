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
import socket
import struct
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


def _icmp_checksum(data: bytes) -> int:
    """Calculate ICMP checksum."""
    if len(data) % 2:
        data += b'\x00'
    s = sum(struct.unpack('!%dH' % (len(data) // 2), data))
    s = (s >> 16) + (s & 0xffff)
    s += s >> 16
    return ~s & 0xffff


def _build_icmp_packet(seq: int, identifier: int) -> bytes:
    """Build ICMP echo request packet."""
    icmp_type = 8  # Echo request
    icmp_code = 0
    checksum = 0
    payload = b'WTC-PING' + struct.pack('!d', time.time())  # 8 bytes tag + 8 bytes timestamp

    # Build header without checksum
    header = struct.pack('!BBHHH', icmp_type, icmp_code, checksum, identifier, seq)
    packet = header + payload

    # Calculate and insert checksum
    checksum = _icmp_checksum(packet)
    header = struct.pack('!BBHHH', icmp_type, icmp_code, checksum, identifier, seq)
    return header + payload


def _parse_icmp_reply(data: bytes, expected_id: int) -> tuple[str, int, float] | None:
    """Parse ICMP reply, return (ip, seq, rtt_ms) or None."""
    if len(data) < 28:  # IP header (20) + ICMP header (8)
        return None

    # IP header - extract source address
    ip_header = data[:20]
    src_ip = '.'.join(str(b) for b in ip_header[12:16])

    # ICMP header starts after IP header
    icmp_header = data[20:28]
    icmp_type, icmp_code, checksum, identifier, seq = struct.unpack('!BBHHH', icmp_header)

    # Type 0 = Echo reply
    if icmp_type != 0:
        return None

    # Check identifier matches our requests
    if identifier != expected_id:
        return None

    # Extract timestamp from payload if present
    rtt_ms = 0.0
    if len(data) >= 36:  # Has our payload
        payload = data[28:]
        if payload[:8] == b'WTC-PING' and len(payload) >= 16:
            send_time = struct.unpack('!d', payload[8:16])[0]
            rtt_ms = (time.time() - send_time) * 1000

    return (src_ip, seq, rtt_ms)


async def icmp_ping_scan(hosts: list[str], timeout_sec: float = 2.0) -> dict[str, PingResult]:
    """
    Perform ICMP ping scan using raw sockets.

    Much faster than spawning ping processes - can scan 254 hosts in ~2 seconds.
    Requires CAP_NET_RAW capability.
    """
    results: dict[str, PingResult] = {}
    identifier = os.getpid() & 0xFFFF
    send_times: dict[str, float] = {}
    send_failures = 0

    try:
        # Create raw ICMP socket - use blocking mode with short timeout for recv polling
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        sock.settimeout(0.01)  # 10ms timeout for non-blocking recv
    except PermissionError as e:
        logger.error(f"ICMP socket creation failed: PermissionError - {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ICMP_PERMISSION_DENIED",
                "message": "Raw socket creation requires CAP_NET_RAW capability",
                "suggested_action": "Recreate container: docker compose up -d --force-recreate api"
            }
        )
    except OSError as e:
        logger.error(f"ICMP socket creation failed: OSError - {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ICMP_SOCKET_ERROR",
                "message": f"Failed to create ICMP socket: {e}",
                "suggested_action": "Check network configuration and capabilities"
            }
        )

    try:
        # Send ICMP echo requests to all hosts
        for seq, ip in enumerate(hosts):
            packet = _build_icmp_packet(seq, identifier)
            try:
                sock.sendto(packet, (ip, 0))
                send_times[ip] = time.time()
            except OSError as e:
                send_failures += 1
                logger.warning(f"Failed to send ICMP to {ip}: {e}")
                results[ip] = PingResult(ip_address=ip, reachable=False, error=str(e))

        # If ALL sends failed, something is fundamentally wrong
        if send_failures == len(hosts):
            logger.error(
                f"All {send_failures} ICMP sends failed - check CAP_NET_RAW capability and network config"
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "ICMP_SEND_FAILED",
                    "message": f"Failed to send ICMP packets to any host ({send_failures} failures)",
                    "suggested_action": "Recreate container: docker compose up -d --force-recreate api"
                }
            )
        elif send_failures > 0:
            logger.warning(f"ICMP send failed for {send_failures}/{len(hosts)} hosts")

        # Collect replies until timeout
        end_time = time.time() + timeout_sec
        received = set()

        while time.time() < end_time and len(received) < len(send_times):
            try:
                data, addr = sock.recvfrom(1024)
                parsed = _parse_icmp_reply(data, identifier)
                if parsed:
                    src_ip, seq, rtt_ms = parsed
                    if src_ip in send_times and src_ip not in received:
                        received.add(src_ip)
                        # Use calculated RTT from packet, or calculate from send time
                        if rtt_ms == 0:
                            rtt_ms = (time.time() - send_times[src_ip]) * 1000
                        results[src_ip] = PingResult(
                            ip_address=src_ip,
                            reachable=True,
                            response_time_ms=round(rtt_ms, 2)
                        )
            except socket.timeout:
                await asyncio.sleep(0.001)  # Brief yield to event loop
            except BlockingIOError:
                await asyncio.sleep(0.001)
            except OSError as e:
                logger.debug(f"ICMP recv error: {e}")
                await asyncio.sleep(0.001)

        # Mark unreached hosts (only those we successfully sent to)
        for ip in hosts:
            if ip not in results:
                results[ip] = PingResult(ip_address=ip, reachable=False)

    finally:
        sock.close()

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


async def _icmp_ping_single(ip: str, timeout_sec: float) -> tuple[bool, float | None, str | None]:
    """
    Send a single ICMP echo request and wait for reply.

    Returns (reachable, rtt_ms, error) tuple.
    Requires CAP_NET_RAW capability.
    """
    identifier = os.getpid() & 0xFFFF
    seq = int(time.time() * 1000) & 0xFFFF

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        sock.settimeout(timeout_sec)
    except PermissionError as e:
        logger.error(f"ICMP socket creation failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ICMP_PERMISSION_DENIED",
                "message": "Raw socket creation requires CAP_NET_RAW capability",
                "suggested_action": "Recreate container: docker compose up -d --force-recreate api"
            }
        )
    except OSError as e:
        logger.error(f"ICMP socket creation failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ICMP_SOCKET_ERROR",
                "message": f"Failed to create ICMP socket: {e}",
                "suggested_action": "Check network configuration"
            }
        )

    try:
        # Build and send ICMP packet
        packet = _build_icmp_packet(seq, identifier)
        send_time = time.time()
        try:
            sock.sendto(packet, (ip, 0))
        except OSError as e:
            logger.warning(f"Failed to send ICMP to {ip}: {e}")
            return (False, None, f"Send failed: {e}")

        # Wait for reply
        end_time = time.time() + timeout_sec
        while time.time() < end_time:
            try:
                remaining = end_time - time.time()
                if remaining <= 0:
                    break
                sock.settimeout(remaining)
                data, addr = sock.recvfrom(1024)
                parsed = _parse_icmp_reply(data, identifier)
                if parsed:
                    src_ip, reply_seq, rtt_ms = parsed
                    if src_ip == ip:
                        # Use calculated RTT or compute from send time
                        if rtt_ms == 0:
                            rtt_ms = (time.time() - send_time) * 1000
                        return (True, rtt_ms, None)
            except socket.timeout:
                break
            except BlockingIOError:
                await asyncio.sleep(0.001)
            except OSError as e:
                logger.debug(f"ICMP recv error for {ip}: {e}")
                break

        return (False, None, None)  # Timeout - no reply received

    finally:
        sock.close()


@router.post("/ping")
async def ping_single_host(request: SinglePingRequest) -> dict[str, Any]:
    """
    Ping a single IP address using ICMP echo requests.

    Performs multiple ping attempts (default 3) and returns statistics
    including packet loss and round-trip times.

    Requires CAP_NET_RAW capability and host network mode.

    Use this endpoint to:
    - Verify connectivity to a specific RTU before configuration
    - Diagnose network issues with a particular device
    - Check if a host is reachable before DCP discovery
    """
    logger.info(f"Pinging {request.ip_address} ({request.count} attempts, timeout {request.timeout_ms}ms)")

    timeout_sec = request.timeout_ms / 1000.0
    rtts: list[float] = []
    packets_received = 0
    last_error: str | None = None

    for i in range(request.count):
        try:
            reachable, rtt_ms, error = await _icmp_ping_single(request.ip_address, timeout_sec)
            if error:
                last_error = error
                logger.warning(f"Ping attempt {i+1} to {request.ip_address}: {error}")
            if reachable and rtt_ms is not None:
                packets_received += 1
                rtts.append(rtt_ms)
        except HTTPException:
            # Re-raise permission errors
            raise
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Ping attempt {i+1} failed: {e}")

        # Brief delay between attempts
        if i < request.count - 1:
            await asyncio.sleep(0.1)

    packet_loss = ((request.count - packets_received) / request.count) * 100

    response = SinglePingResponse(
        ip_address=request.ip_address,
        reachable=packets_received > 0,
        packets_sent=request.count,
        packets_received=packets_received,
        packet_loss_percent=round(packet_loss, 1),
        min_rtt_ms=round(min(rtts), 2) if rtts else None,
        avg_rtt_ms=round(sum(rtts) / len(rtts), 2) if rtts else None,
        max_rtt_ms=round(max(rtts), 2) if rtts else None,
        error=last_error if packets_received == 0 else None,
    )

    logger.info(
        f"Ping {request.ip_address}: {packets_received}/{request.count} received, "
        f"{packet_loss:.1f}% loss" + (f", avg RTT {response.avg_rtt_ms}ms" if rtts else "")
    )

    return build_success_response(response.model_dump())


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

    Requires CAP_NET_RAW capability and host network mode.
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
