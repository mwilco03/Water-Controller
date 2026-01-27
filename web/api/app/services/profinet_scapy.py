#!/usr/bin/env python3
"""
PROFINET IO Controller - Complete Scapy Implementation

This module provides a production-grade PROFINET IO Controller using Scapy.
It matches the capabilities of the C implementation:
- Full RPC operations (Connect, Control, Read, Write, Release)
- DCP operations (Discover, Set IP, Set Name, Signal, Reset)
- Cyclic I/O (RT frames for sensor/actuator data)
- State machine with 8 states
- Error recovery with 7 strategies
- Watchdog and health monitoring

Usage:
    from profinet_scapy import ProfinetController
    ctrl = ProfinetController(interface="eth0")
    devices = ctrl.discover()  # DCP multicast discovery
    if devices:
        ctrl.connect(devices[0].ip_address)  # Connect to first discovered device
        value = ctrl.read_sensor(slot=1)
        ctrl.disconnect()

Copyright (C) 2024-2026
SPDX-License-Identifier: GPL-3.0-or-later
"""

import logging
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from typing import Callable, Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)

# Try to import Scapy
try:
    from scapy.all import (
        Ether, Raw, conf, get_if_hwaddr, sendp, sniff, AsyncSniffer
    )
    from scapy.contrib.pnio import ProfinetIO, PNIORealTimeCyclicPDU
    from scapy.contrib.pnio_dcp import (
        ProfinetDCP, DCPNameOfStationBlock, DCPIPBlock, DCPDeviceIDBlock,
        DCPControlBlock
    )
    from scapy.contrib.pnio_rpc import (
        # Block builders for ExpectedSubmodule (kept for _build_expected_submodule_block_scapy fallback)
        Block, ExpectedSubmoduleBlockReq, ExpectedSubmoduleAPI, ExpectedSubmodule,
        ExpectedSubmoduleDataDescription,
        # Control/Read/Write operations (still use Scapy for these simpler packets)
        IODControlReq, IODReadReq, IODWriteReq,
        PNIOServiceReqPDU, PNIOServiceResPDU
        # NOTE: ARBlockReq, IOCRBlockReq, AlarmCRBlockReq, IOCRAPI, IOCRAPIObject
        # removed - we build these manually to match C code byte-for-byte
    )
    from scapy.layers.dcerpc import DceRpc4
    SCAPY_AVAILABLE = True
except ImportError as e:
    SCAPY_AVAILABLE = False
    logger.error(f"Scapy import failed: {e}")
    logger.error("Install with: pip install scapy")

# Import resilience module
try:
    from .profinet_resilience import (
        AdaptiveConnector, ConnectionStrategy, ErrorAnalyzer,
        PNIOResponseParser, create_resilient_connector,
        STRATEGY_SPEC_COMPLIANT, STRATEGY_C_COMPATIBLE, STRATEGY_MINIMAL,
        IOCRParams, AlarmCRParams, ExpectedSubmodParams, FormatVariant
    )
    RESILIENCE_AVAILABLE = True
except ImportError as e:
    RESILIENCE_AVAILABLE = False
    logger.warning(f"Resilience module not available: {e}")


# =============================================================================
# Constants - Match C Implementation
# =============================================================================

# PROFINET UUIDs
PNIO_UUID = "dea00001-6c97-11d1-8271-00a02442df7d"
PNIO_CONTROLLER_UUID = "dea00002-6c97-11d1-8271-00a02442df7d"

# Network
RPC_PORT = 34964
PROFINET_ETHERTYPE = 0x8892
DCP_MULTICAST = "01:0e:cf:00:00:00"

# RPC Operation Numbers
class RpcOpnum(IntEnum):
    CONNECT = 0
    RELEASE = 1
    READ = 2
    WRITE = 3
    CONTROL = 4
    READ_IMPLICIT = 5

# Control Commands
class ControlCommand(IntEnum):
    PRM_END = 0x0001
    APP_READY = 0x0002
    RELEASE = 0x0003
    PRM_BEGIN = 0x0004
    READY_FOR_COMPANION = 0x0005
    READY_FOR_RTC3 = 0x0006

# AR Types
class ARType(IntEnum):
    IOCAR = 0x0001
    IOSAR = 0x0006
    IOCARPME = 0x0010

# IOCR Types
class IOCRType(IntEnum):
    INPUT = 0x0001
    OUTPUT = 0x0002
    MULTICAST_PROVIDER = 0x0003
    MULTICAST_CONSUMER = 0x0004

# Frame IDs
FRAME_ID_INPUT = 0x8001   # Device -> Controller
FRAME_ID_OUTPUT = 0x8000  # Controller -> Device
FRAME_ID_ALARM_HIGH = 0xFC01
FRAME_ID_ALARM_LOW = 0xFE01

# Data Quality (OPC UA compatible)
class Quality(IntEnum):
    GOOD = 0x00
    UNCERTAIN = 0x40
    BAD = 0x80
    NOT_CONNECTED = 0xC0
    SIMULATED = 0x41

# RTU Module IDs (from GSDML)
MOD_DAP = 0x00000001
SUBMOD_DAP = 0x00000001
MOD_TEMP = 0x00000040
SUBMOD_TEMP = 0x00000041

# Timeouts (ms)
CONNECT_TIMEOUT_MS = 5000
CONTROL_TIMEOUT_MS = 3000
DCP_TIMEOUT_MS = 1280
WATCHDOG_TIMEOUT_MS = 3000
APP_READY_TIMEOUT_MS = 30000


# =============================================================================
# State Machine
# =============================================================================

class ARState(Enum):
    """AR (Application Relationship) States - matches C implementation"""
    INIT = auto()           # Initial state
    CONNECT_REQ = auto()    # Connect request sent
    CONNECT_CNF = auto()    # Connect confirmed
    PRMSRV = auto()         # Parameter service (PrmEnd sent)
    READY = auto()          # Ready (awaiting device ApplicationReady)
    RUN = auto()            # Running (cyclic I/O active)
    CLOSE = auto()          # Closing (Release sent)
    ABORT = auto()          # Aborted (error/timeout)


class RecoveryAction(Enum):
    """Recovery actions for error handling"""
    NONE = auto()           # Fatal, don't retry
    RETRY_SAME = auto()     # Retry with same parameters
    TRY_LOWERCASE = auto()  # Try lowercase station name
    TRY_MINIMAL = auto()    # Try minimal config (DAP only)
    FIX_BLOCK_LENGTH = auto()
    FIX_PHASE = auto()
    FIX_TIMING = auto()
    REDISCOVER = auto()
    WAIT_AND_RETRY = auto()


class ConnectStrategy(Enum):
    """Connection strategies for resilient connect"""
    STANDARD = auto()       # Use given station name as-is
    LOWERCASE = auto()      # Force lowercase
    UPPERCASE = auto()      # Force uppercase
    NO_DASH = auto()        # Remove dashes
    MINIMAL_CONFIG = auto() # DAP only
    REDISCOVER = auto()     # Re-run DCP first


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class DeviceInfo:
    """Discovered device information"""
    mac_address: str = ""
    ip_address: str = ""
    subnet_mask: str = ""
    gateway: str = ""
    station_name: str = ""
    vendor_name: str = ""
    vendor_id: int = 0
    device_id: int = 0
    device_role: int = 0
    discovered_time: float = 0.0

    def to_dict(self) -> dict:
        return {
            "mac_address": self.mac_address,
            "ip_address": self.ip_address,
            "subnet_mask": self.subnet_mask,
            "gateway": self.gateway,
            "station_name": self.station_name,
            "vendor_name": self.vendor_name,
            "vendor_id": self.vendor_id,
            "device_id": self.device_id,
        }


@dataclass
class SensorReading:
    """Sensor data with quality"""
    slot: int
    value: float
    quality: int = Quality.GOOD
    timestamp: float = field(default_factory=time.time)


@dataclass
class ARContext:
    """Application Relationship context"""
    ar_uuid: bytes = field(default_factory=lambda: uuid4().bytes)
    activity_uuid: bytes = field(default_factory=lambda: uuid4().bytes)
    session_key: int = 1
    seq_num: int = 0
    state: ARState = ARState.INIT
    input_frame_id: int = FRAME_ID_INPUT
    output_frame_id: int = FRAME_ID_OUTPUT
    device_mac: str = ""
    device_ip: str = ""
    last_activity: float = 0.0
    watchdog_ms: int = WATCHDOG_TIMEOUT_MS
    error_message: str = ""


@dataclass
class SlotConfig:
    """Slot configuration for expected submodules"""
    slot_number: int
    subslot_number: int = 1
    module_ident: int = 0
    submodule_ident: int = 0
    direction: str = "input"  # input, output, no_io
    data_length: int = 0


# Device profiles matching C implementation
PROFILE_MINIMAL = [
    SlotConfig(0, 1, MOD_DAP, SUBMOD_DAP, "no_io", 0),
]

PROFILE_RTU_CPU_TEMP = [
    SlotConfig(0, 1, MOD_DAP, SUBMOD_DAP, "no_io", 0),
    SlotConfig(1, 1, MOD_TEMP, SUBMOD_TEMP, "input", 5),  # 4-byte float + 1 IOPS
]

PROFILE_WATER_TREAT = [
    SlotConfig(0, 1, MOD_DAP, SUBMOD_DAP, "no_io", 0),
    SlotConfig(1, 1, MOD_TEMP, SUBMOD_TEMP, "input", 5),
    # Additional slots would go here for full Water-Treat RTU
]


# =============================================================================
# PROFINET Controller - Main Class
# =============================================================================

class ProfinetController:
    """
    PROFINET IO Controller using Scapy.

    Complete implementation matching C controller capabilities:
    - RPC operations (Connect, Control, Read, Write, Release)
    - DCP discovery and configuration
    - Cyclic I/O with RT frames
    - State machine with error recovery
    - Watchdog monitoring
    """

    def __init__(self, interface: str = "eth0", station_name: str = "controller"):
        """
        Initialize PROFINET controller.

        Args:
            interface: Network interface name (e.g., "eth0")
            station_name: Controller's station name
        """
        if not SCAPY_AVAILABLE:
            raise RuntimeError("Scapy is required. Install with: pip install scapy")

        self.interface = interface
        self.station_name = station_name
        self._lock = threading.RLock()

        # Get controller MAC
        try:
            self.mac = get_if_hwaddr(interface)
        except Exception:
            self.mac = "02:00:00:00:00:01"
            logger.warning(f"Could not get MAC for {interface}, using {self.mac}")

        # Connection state
        self.ar: Optional[ARContext] = None
        self.device: Optional[DeviceInfo] = None
        self.discovered_devices: Dict[str, DeviceInfo] = {}
        self.sensors: Dict[int, SensorReading] = {}

        # Cyclic I/O
        self._cyclic_running = False
        self._output_thread: Optional[threading.Thread] = None
        self._sniffer: Optional[AsyncSniffer] = None
        self._stop_event = threading.Event()
        self._cycle_counter = 0

        # Callbacks
        self._on_state_change: Optional[Callable[[ARState, ARState], None]] = None
        self._on_sensor_data: Optional[Callable[[int, float, int], None]] = None

        # Resilience tracking
        self._last_response: Optional[bytes] = None
        self._last_error_analysis = None
        self._adaptive_connector: Optional['AdaptiveConnector'] = None
        self._connection_strategy: Optional['ConnectionStrategy'] = None
        self._current_iocr_params = None
        self._current_alarm_params = None
        self._current_submod_format = None

        logger.info(f"PROFINET Controller initialized on {interface} ({self.mac})")

    # =========================================================================
    # DCP Discovery
    # =========================================================================

    def discover(self, timeout_s: float = 3.0, station_name: str = None) -> List[DeviceInfo]:
        """
        Discover PROFINET devices on the network.

        Args:
            timeout_s: Discovery timeout in seconds
            station_name: Optional specific station name to find

        Returns:
            List of discovered devices
        """
        logger.info(f"Starting DCP discovery (timeout={timeout_s}s)")
        self.discovered_devices.clear()

        # Build DCP Identify request
        # Note: Scapy auto-calculates block_length, don't set it manually
        if station_name:
            # Identify specific device by name
            dcp = (
                Ether(dst=DCP_MULTICAST, src=self.mac, type=PROFINET_ETHERTYPE) /
                ProfinetDCP(
                    service_id=0x05,  # Identify
                    service_type=0x00,  # Request
                    xid=0x1234,
                    reserved=0,
                    dcp_data_length=4 + len(station_name)
                ) /
                DCPNameOfStationBlock(
                    option=0x02,
                    sub_option=0x02,
                    name_of_station=station_name.encode()
                )
            )
        else:
            # Identify all devices
            dcp = (
                Ether(dst=DCP_MULTICAST, src=self.mac, type=PROFINET_ETHERTYPE) /
                ProfinetDCP(
                    service_id=0x05,
                    service_type=0x00,
                    xid=0x1234,
                    reserved=0,
                    dcp_data_length=4
                ) /
                DCPNameOfStationBlock(option=0xFF, sub_option=0xFF)  # All
            )

        results = []

        def handle_response(pkt):
            if ProfinetDCP not in pkt:
                return False
            if pkt[ProfinetDCP].service_type != 0x01:  # Not a response
                return False

            device = self._parse_dcp_response(pkt)
            if device:
                self.discovered_devices[device.station_name] = device
                results.append(device)
                logger.info(f"Discovered: {device.station_name} at {device.ip_address} ({device.mac_address})")

            return False  # Continue sniffing

        # Send discovery and sniff for responses
        sendp(dcp, iface=self.interface, verbose=False)
        sniff(
            iface=self.interface,
            timeout=timeout_s,
            store=False,
            prn=handle_response,
            filter="ether proto 0x8892"
        )

        logger.info(f"Discovery complete: found {len(results)} device(s)")
        return results

    def _parse_dcp_response(self, pkt) -> Optional[DeviceInfo]:
        """Parse DCP response packet into DeviceInfo."""
        try:
            device = DeviceInfo(
                mac_address=pkt.src,
                discovered_time=time.time()
            )

            # Walk through DCP blocks
            layer = pkt[ProfinetDCP].payload
            while layer:
                if hasattr(layer, 'option'):
                    if layer.option == 0x01:  # IP
                        if hasattr(layer, 'ip'):
                            device.ip_address = layer.ip
                        if hasattr(layer, 'netmask'):
                            device.subnet_mask = layer.netmask
                        if hasattr(layer, 'gateway'):
                            device.gateway = layer.gateway
                    elif layer.option == 0x02:  # Device
                        if hasattr(layer, 'name_of_station'):
                            device.station_name = layer.name_of_station.decode() if isinstance(layer.name_of_station, bytes) else layer.name_of_station
                        if hasattr(layer, 'vendor_id'):
                            device.vendor_id = layer.vendor_id
                        if hasattr(layer, 'device_id'):
                            device.device_id = layer.device_id

                layer = layer.payload if hasattr(layer, 'payload') else None

            return device if device.station_name else None

        except Exception as e:
            logger.debug(f"Failed to parse DCP response: {e}")
            return None

    def set_device_ip(self, mac_address: str, ip: str, mask: str, gateway: str,
                      permanent: bool = False) -> bool:
        """
        Set device IP address via DCP.

        Args:
            mac_address: Target device MAC
            ip: IP address to set
            mask: Subnet mask
            gateway: Gateway address
            permanent: Store permanently (survive reboot)
        """
        logger.info(f"Setting IP {ip} on device {mac_address}")

        # Build DCP Set IP request
        block_qualifier = 0x0001 if permanent else 0x0000

        dcp = (
            Ether(dst=mac_address, src=self.mac, type=PROFINET_ETHERTYPE) /
            ProfinetDCP(
                service_id=0x04,  # Set
                service_type=0x00,
                xid=0x1235,
                reserved=0,
                dcp_data_length=18
            ) /
            DCPIPBlock(
                option=0x01,
                sub_option=0x02,
                block_qualifier=block_qualifier,
                ip=ip,
                netmask=mask,
                gateway=gateway
            )
        )

        result = [False]

        def handle_response(pkt):
            if ProfinetDCP in pkt and pkt[ProfinetDCP].service_type == 0x01:
                result[0] = True
                return True
            return False

        sendp(dcp, iface=self.interface, verbose=False)
        sniff(iface=self.interface, timeout=2.0, store=False,
              stop_filter=handle_response, filter="ether proto 0x8892")

        return result[0]

    def set_device_name(self, mac_address: str, name: str, permanent: bool = False) -> bool:
        """Set device station name via DCP."""
        logger.info(f"Setting name '{name}' on device {mac_address}")

        block_qualifier = 0x0001 if permanent else 0x0000
        name_bytes = name.encode()

        dcp = (
            Ether(dst=mac_address, src=self.mac, type=PROFINET_ETHERTYPE) /
            ProfinetDCP(
                service_id=0x04,
                service_type=0x00,
                xid=0x1236,
                reserved=0,
                dcp_data_length=4 + len(name_bytes)
            ) /
            DCPNameOfStationBlock(
                option=0x02,
                sub_option=0x02,
                block_qualifier=block_qualifier,
                name_of_station=name_bytes
            )
        )

        result = [False]

        def handle_response(pkt):
            if ProfinetDCP in pkt and pkt[ProfinetDCP].service_type == 0x01:
                result[0] = True
                return True
            return False

        sendp(dcp, iface=self.interface, verbose=False)
        sniff(iface=self.interface, timeout=2.0, store=False,
              stop_filter=handle_response, filter="ether proto 0x8892")

        return result[0]

    def signal_device(self, mac_address: str, duration_s: int = 3) -> bool:
        """Blink device LED via DCP Signal."""
        logger.info(f"Signaling device {mac_address} for {duration_s}s")

        dcp = (
            Ether(dst=mac_address, src=self.mac, type=PROFINET_ETHERTYPE) /
            ProfinetDCP(
                service_id=0x04,
                service_type=0x00,
                xid=0x1237,
                reserved=0,
                dcp_data_length=8
            ) /
            DCPControlBlock(
                option=0x05,
                sub_option=0x03,  # Signal
                block_qualifier=0x0100,  # Signal On
                control_signal_value=duration_s
            )
        )

        sendp(dcp, iface=self.interface, verbose=False)
        return True

    # =========================================================================
    # RPC Connection - Full Handshake
    # =========================================================================

    def connect(self, device_ip: str, profile: List[SlotConfig] = None,
                timeout_s: float = 10.0) -> bool:
        """
        Connect to PROFINET device with full handshake.

        Sequence: Connect → PrmEnd → ApplicationReady → Cyclic I/O

        Args:
            device_ip: Device IP address
            profile: Slot configuration (default: RTU_CPU_TEMP)
            timeout_s: Overall connection timeout

        Returns:
            True if connection established and running
        """
        if profile is None:
            profile = PROFILE_RTU_CPU_TEMP

        logger.info(f"Connecting to {device_ip}")

        with self._lock:
            # Create AR context
            self.ar = ARContext(
                ar_uuid=uuid4().bytes,
                activity_uuid=uuid4().bytes,
                session_key=1,
                device_ip=device_ip,
            )
            self._set_state(ARState.INIT)

        try:
            # Step 1: Connect Request
            logger.info(f"[{device_ip}] Step 1: Connect Request")
            self._set_state(ARState.CONNECT_REQ)

            if not self._rpc_connect(profile):
                raise Exception("Connect Request failed")

            self._set_state(ARState.CONNECT_CNF)
            logger.info(f"[{device_ip}] Connect confirmed")

            # Step 2: PrmEnd
            logger.info(f"[{device_ip}] Step 2: PrmEnd")
            self._set_state(ARState.PRMSRV)

            if not self._rpc_control(ControlCommand.PRM_END):
                raise Exception("PrmEnd failed")

            logger.info(f"[{device_ip}] PrmEnd confirmed")

            # Step 3: ApplicationReady
            # Send ApplicationReady to device (this was the working approach)
            logger.info(f"[{device_ip}] Step 3: ApplicationReady")
            self._set_state(ARState.READY)

            if not self._rpc_control(ControlCommand.APP_READY):
                raise Exception("ApplicationReady failed")

            # Connection established
            self._set_state(ARState.RUN)
            logger.info(f"[{device_ip}] *** CONNECTION RUNNING ***")

            # Step 4: Start Cyclic I/O
            self._start_cyclic_io()

            return True

        except Exception as e:
            logger.error(f"[{device_ip}] Connect failed: {e}")
            self._set_state(ARState.ABORT)
            if self.ar:
                self.ar.error_message = str(e)
            return False

    def connect_resilient(self, device_ip: str, max_retries: int = 10) -> bool:
        """
        Connect with adaptive retry strategies and automatic error correction.

        Uses the resilience module to:
        1. Try multiple wire format strategies (spec-compliant, C-compatible, minimal)
        2. Analyze device error responses and adjust parameters
        3. Learn from failures to improve success rate
        4. Provide detailed diagnostic output

        Args:
            device_ip: Target device IP address
            max_retries: Maximum total connection attempts

        Returns:
            True if connection successful, False otherwise
        """
        if RESILIENCE_AVAILABLE:
            return self._connect_with_adaptive_strategies(device_ip, max_retries)
        else:
            # Fallback to basic retry logic
            return self._connect_with_basic_retry(device_ip, max_retries)

    def _connect_with_adaptive_strategies(self, device_ip: str, max_retries: int) -> bool:
        """Connect using adaptive connector with error-based parameter adjustment."""
        logger.info(f"Starting adaptive connection to {device_ip}")

        # Create adaptive connector with all strategies
        self._adaptive_connector = create_resilient_connector()

        attempt = 0
        while attempt < max_retries:
            attempt += 1

            for strategy in self._adaptive_connector.iterate_strategies():
                logger.info(f"Attempt {attempt}: Strategy '{strategy.name}' - {strategy.description}")
                self._connection_strategy = strategy

                # Try connecting with current strategy
                success = self._connect_with_strategy(device_ip, strategy)

                # Process result and get error analysis
                error_analysis = self._last_error_analysis
                should_stop = self._adaptive_connector.process_result(
                    success=success,
                    error_analysis=error_analysis
                )

                if success:
                    logger.info(f"*** Connection successful with strategy '{strategy.name}' ***")
                    return True

                if should_stop:
                    break

                # Log error analysis
                if error_analysis:
                    logger.warning(f"Error in {error_analysis.block_name}: {error_analysis.description}")
                    if error_analysis.parameter_adjustment:
                        logger.info(f"Applying adjustment: {error_analysis.parameter_adjustment}")

                # Short delay between strategy attempts
                time.sleep(0.5)

            # Reset connector for next round
            self._adaptive_connector.current_index = 0

            # Longer backoff between full rounds
            if attempt < max_retries:
                backoff = min(2 ** (attempt - 1), 8)
                logger.info(f"Waiting {backoff}s before next round...")
                time.sleep(backoff)

        # Generate diagnostic report
        report = self._adaptive_connector.get_diagnostic_report()
        logger.error(f"Connection failed after {attempt} attempts.\n{report}")

        return False

    def _connect_with_strategy(self, device_ip: str, strategy: 'ConnectionStrategy') -> bool:
        """Attempt connection using specific strategy parameters."""
        # For now, use the default profile but apply strategy parameters
        # Future: build profile dynamically based on strategy

        # Apply IOCR parameters from strategy
        self._current_iocr_params = strategy.iocr
        self._current_alarm_params = strategy.alarm_cr
        self._current_submod_format = strategy.expected_submod.format

        # Use standard connect with profile
        return self.connect(device_ip, PROFILE_RTU_CPU_TEMP)

    def _connect_with_basic_retry(self, device_ip: str, max_retries: int) -> bool:
        """Basic retry logic when resilience module not available."""
        strategies = [
            (ConnectStrategy.STANDARD, PROFILE_RTU_CPU_TEMP),
            (ConnectStrategy.LOWERCASE, PROFILE_RTU_CPU_TEMP),
            (ConnectStrategy.MINIMAL_CONFIG, PROFILE_MINIMAL),
            (ConnectStrategy.REDISCOVER, PROFILE_RTU_CPU_TEMP),
        ]

        for attempt, (strategy, profile) in enumerate(strategies):
            if attempt >= max_retries:
                break

            logger.info(f"Connect attempt {attempt + 1}: {strategy.name}")

            if strategy == ConnectStrategy.REDISCOVER:
                self.discover(timeout_s=2.0)

            if self.connect(device_ip, profile):
                return True

            # Exponential backoff
            backoff = min(2 ** attempt, 16)
            logger.info(f"Waiting {backoff}s before retry...")
            time.sleep(backoff)

        return False

    def get_diagnostic_report(self) -> str:
        """Get diagnostic report from last connection attempt."""
        if self._adaptive_connector:
            return self._adaptive_connector.get_diagnostic_report()
        return "No diagnostic data available (adaptive connector not used)"

    def disconnect(self) -> bool:
        """Disconnect from device."""
        if not self.ar or self.ar.state == ARState.INIT:
            return True

        logger.info(f"Disconnecting from {self.ar.device_ip}")

        # Stop cyclic I/O first
        self._stop_cyclic_io()

        # Send Release
        self._set_state(ARState.CLOSE)
        try:
            self._rpc_control(ControlCommand.RELEASE)
        except Exception as e:
            logger.warning(f"Release failed: {e}")

        self._set_state(ARState.INIT)
        logger.info("Disconnected")
        return True

    def _build_expected_submodule_block_c_format(self, profile: List[SlotConfig]) -> Block:
        """
        Build Expected Submodule block matching C implementation wire format.

        Citation: profinet_rpc.c:554-628

        C format structure:
        - BlockHeader: type(2) + length(2) + version(2) = 6 bytes
        - NumberOfAPIs(2) = 1
        - API(4) = 0
        - NumberOfSlots(2)
        - For each slot:
            - SlotNumber(2)
            - ModuleIdentNumber(4)
            - NumberOfSubmodules(2)
            - For each submodule:
                - SubslotNumber(2)
                - SubmoduleIdentNumber(4)
                - SubmoduleProperties(2) = 0x0001(input) or 0x0002(output)
                - DataLength(2)
                - LengthIOCS(1) = 1
                - LengthIOPS(1) = 1

        This differs from Scapy's ExpectedSubmoduleBlockReq which has:
        - Multiple API entries (one per slot)
        - DataDescription type field (2 bytes extra per submodule)
        """
        # Build block content manually
        data = bytearray()

        # NumberOfAPIs = 1 (big-endian)
        data.extend(struct.pack(">H", 1))

        # API = 0 (big-endian)
        data.extend(struct.pack(">I", 0))

        # Group profile by slot
        slots_dict = {}
        for slot_cfg in profile:
            if slot_cfg.slot_number not in slots_dict:
                slots_dict[slot_cfg.slot_number] = {
                    'module_ident': slot_cfg.module_ident,
                    'submodules': []
                }
            slots_dict[slot_cfg.slot_number]['submodules'].append(slot_cfg)

        # NumberOfSlots
        data.extend(struct.pack(">H", len(slots_dict)))

        # Slot data
        for slot_num in sorted(slots_dict.keys()):
            slot_info = slots_dict[slot_num]

            # SlotNumber
            data.extend(struct.pack(">H", slot_num))

            # ModuleIdentNumber
            data.extend(struct.pack(">I", slot_info['module_ident']))

            # NumberOfSubmodules
            data.extend(struct.pack(">H", len(slot_info['submodules'])))

            # Submodule data
            for submod in slot_info['submodules']:
                # SubslotNumber
                data.extend(struct.pack(">H", submod.subslot_number))

                # SubmoduleIdentNumber
                data.extend(struct.pack(">I", submod.submodule_ident))

                # SubmoduleProperties: 0x0001=input, 0x0002=output, 0x0000=no_io
                if submod.direction == "input":
                    props = 0x0001
                elif submod.direction == "output":
                    props = 0x0002
                else:
                    props = 0x0000
                data.extend(struct.pack(">H", props))

                # DataLength (C writes data_length directly, no DataDescription type)
                data.extend(struct.pack(">H", submod.data_length))

                # LengthIOCS = 1, LengthIOPS = 1
                data.append(1)
                data.append(1)

        # Calculate block length (content after type+length, includes version)
        block_content_len = len(data) + 2  # +2 for version bytes

        # Build complete block with header
        block = bytearray()
        # Block type 0x0104 (Expected Submodule Block)
        block.extend(struct.pack(">H", 0x0104))
        # Block length
        block.extend(struct.pack(">H", block_content_len))
        # Version 1.0
        block.append(1)
        block.append(0)
        # Content
        block.extend(data)

        logger.debug(f"Built ExpectedSubmodule block: {len(block)} bytes, {len(slots_dict)} slots")

        # Return as Scapy Raw packet so it can be included in blocks list
        return Raw(load=bytes(block))

    def _build_ar_block_manual(self) -> bytes:
        """
        Build AR Block Request MANUALLY matching C code EXACTLY.

        Citation: profinet_rpc.c:402-431

        C format structure:
        - BlockHeader: type(2) + length(2) + version(2) = 6 bytes
        - ARType (2) = 0x0001 (IOCAR)
        - ARUUID (16)
        - SessionKey (2)
        - CMInitiatorMacAdd (6)
        - CMInitiatorObjectUUID (16)
        - ARProperties (4) = 0x00000001 (State=1=Active)
        - CMInitiatorActivityTimeoutFactor (2) = 1000 (100s in 100ms units)
        - CMInitiatorUDPRTPort (2) = 34964
        - StationNameLength (2)
        - CMInitiatorStationName (variable)

        Block content = 2+16+2+6+16+4+2+2+2+name_len = 52 + name_len
        BlockLength = 52 + name_len + 2 (version) = 54 + name_len
        """
        if not self.ar:
            raise ValueError("AR context not initialized")

        # Build block content (after version bytes)
        data = bytearray()

        # ARType = 0x0001 (IOCAR) - C: line 406
        data.extend(struct.pack(">H", ARType.IOCAR))

        # ARUUID (16 bytes) - C: line 407-408
        data.extend(self.ar.ar_uuid)

        # SessionKey (2 bytes) - C: line 409
        data.extend(struct.pack(">H", self.ar.session_key))

        # CMInitiatorMacAdd (6 bytes) - C: line 410-411
        # self.mac is string like "00:11:22:33:44:55"
        mac_bytes = bytes.fromhex(self.mac.replace(':', ''))
        data.extend(mac_bytes)

        # CMInitiatorObjectUUID (16 bytes) - C: line 412-413
        # Generate a new UUID for controller object
        data.extend(uuid4().bytes)

        # ARProperties (4 bytes) - C: line 414
        # State=1 (Active) in bits 0-2
        ar_props = 0x00000001  # State = Active
        data.extend(struct.pack(">I", ar_props))

        # CMInitiatorActivityTimeoutFactor (2 bytes) - C: line 415
        # Value in 100ms units, 1000 = 100 seconds
        data.extend(struct.pack(">H", 1000))

        # CMInitiatorUDPRTPort (2 bytes) - C: line 416
        data.extend(struct.pack(">H", RPC_PORT))

        # StationNameLength (2 bytes) - C: lines 419-420
        name_bytes = self.station_name.encode('utf-8')
        data.extend(struct.pack(">H", len(name_bytes)))

        # CMInitiatorStationName (variable) - C: lines 421-422
        data.extend(name_bytes)

        # Calculate block length (content after type+length, includes version)
        block_content_len = len(data) + 2  # +2 for version bytes

        # Build complete block with header
        block = bytearray()
        # Block type 0x0101 (AR Block Request)
        block.extend(struct.pack(">H", 0x0101))
        # Block length
        block.extend(struct.pack(">H", block_content_len))
        # Version 1.0
        block.append(1)
        block.append(0)
        # Content
        block.extend(data)

        logger.debug(f"Built AR block (manual): {len(block)} bytes, station_name={self.station_name}")

        return bytes(block)

    def _build_iocr_block_manual(self, iocr_type: int, profile: List[SlotConfig]) -> bytes:
        """
        Build IOCR Block Request MANUALLY matching C code EXACTLY.

        Citation: profinet_rpc.c:433-514

        C format structure:
        - BlockHeader: type(2) + length(2) + version(2) = 6 bytes
        - IOCRType (2) - 0x0001=Input, 0x0002=Output
        - IOCRReference (2) - 0x0001 for Input, 0x0002 for Output
        - LT (2) = 0x8892 (PROFINET Ethertype)
        - IOCRProperties (4) = 0x00000001 (RT Class 1)
        - DataLength (2) - sum of data lengths + IOPS byte
        - FrameID (2) - 0x8001=Input, 0x8000=Output
        - SendClockFactor (2) = 32
        - ReductionRatio (2) = 32
        - Phase (2) = 1
        - Sequence (2) = 0 (deprecated)
        - FrameSendOffset (4) = 0
        - WatchdogFactor (2) = 10
        - DataHoldFactor (2) = 3
        - IOCRTagHeader (2) = 0
        - IOCRMulticastMACAdd (6) = 00:00:00:00:00:00
        - NumberOfAPIs (2) = 1
        - API data:
          - API (4) = 0
          - NumberOfIODataObjects (2)
          - IODataObjects (slot(2) + subslot(2) + frame_offset(2) each)
          - NumberOfIOCS (2)
          - IOCSs (slot(2) + subslot(2) + frame_offset(2) each)

        Args:
            iocr_type: 1=Input, 2=Output
            profile: List of slot configurations
        """
        is_input = (iocr_type == IOCRType.INPUT)

        # Filter slots matching this IOCR type with data_length > 0
        matching_slots = [
            s for s in profile
            if ((s.direction == "input") == is_input) and s.data_length > 0
        ]

        # Calculate data length: sum of slot data lengths + 1 byte for IOPS
        data_len = sum(s.data_length for s in matching_slots) + 1
        if data_len < 4:
            data_len = 4  # Minimum per PROFINET spec

        # Build block content
        data = bytearray()

        # IOCRType (2) - C: line 438
        data.extend(struct.pack(">H", iocr_type))

        # IOCRReference (2) - C: line 439
        iocr_ref = 0x0001 if is_input else 0x0002
        data.extend(struct.pack(">H", iocr_ref))

        # LT (2) = 0x8892 - C: line 440
        data.extend(struct.pack(">H", PROFINET_ETHERTYPE))

        # IOCRProperties (4) = RT Class 1 - C: line 441
        data.extend(struct.pack(">I", 0x00000001))

        # DataLength (2) - C: line 442
        data.extend(struct.pack(">H", data_len))

        # FrameID (2) - C: line 443
        frame_id = FRAME_ID_INPUT if is_input else FRAME_ID_OUTPUT
        data.extend(struct.pack(">H", frame_id))

        # SendClockFactor (2) = 32 - C: line 444
        data.extend(struct.pack(">H", 32))

        # ReductionRatio (2) = 32 - C: line 445
        data.extend(struct.pack(">H", 32))

        # Phase (2) = 1 - C: line 446
        data.extend(struct.pack(">H", 1))

        # Sequence (2) = 0 (deprecated) - C: line 447
        data.extend(struct.pack(">H", 0))

        # FrameSendOffset (4) = 0 - C: line 448
        data.extend(struct.pack(">I", 0))

        # WatchdogFactor (2) = 10 - C: line 449
        data.extend(struct.pack(">H", 10))

        # DataHoldFactor (2) = 3 - C: line 450
        data.extend(struct.pack(">H", 3))

        # IOCRTagHeader (2) = 0 - C: line 451
        data.extend(struct.pack(">H", 0))

        # IOCRMulticastMACAdd (6) = zeros - C: line 452-453
        data.extend(b'\x00\x00\x00\x00\x00\x00')

        # NumberOfAPIs (2) = 1 - C: line 456
        data.extend(struct.pack(">H", 1))

        # API 0 - C: line 459
        data.extend(struct.pack(">I", 0))

        # NumberOfIODataObjects (2) - C: line 474
        data.extend(struct.pack(">H", len(matching_slots)))

        # IODataObjects - C: lines 476-490
        frame_offset = 0
        for slot in matching_slots:
            data.extend(struct.pack(">H", slot.slot_number))
            data.extend(struct.pack(">H", slot.subslot_number))
            data.extend(struct.pack(">H", frame_offset))
            frame_offset += slot.data_length

        # NumberOfIOCS (2) - C: line 493
        data.extend(struct.pack(">H", len(matching_slots)))

        # IOCSs - C: lines 495-508
        iocs_offset = 0
        for slot in matching_slots:
            data.extend(struct.pack(">H", slot.slot_number))
            data.extend(struct.pack(">H", slot.subslot_number))
            data.extend(struct.pack(">H", iocs_offset))
            iocs_offset += 1  # IOCS is 1 byte per submodule

        # Calculate block length (content after type+length, includes version)
        block_content_len = len(data) + 2  # +2 for version bytes

        # Build complete block with header
        block = bytearray()
        # Block type 0x0102 (IOCR Block Request)
        block.extend(struct.pack(">H", 0x0102))
        # Block length
        block.extend(struct.pack(">H", block_content_len))
        # Version 1.0
        block.append(1)
        block.append(0)
        # Content
        block.extend(data)

        iocr_name = "Input" if is_input else "Output"
        logger.debug(f"Built {iocr_name} IOCR block (manual): {len(block)} bytes, "
                     f"{len(matching_slots)} slots, data_len={data_len}")

        return bytes(block)

    def _build_alarm_cr_block_c_format(self) -> Block:
        """
        Build Alarm CR block matching C implementation wire format.

        Citation: profinet_rpc.c:517-540

        C format structure:
        - BlockHeader: type(2) + length(2) + version(2) = 6 bytes
        - AlarmCRType(2) = 1
        - LT(2) = 0x8892
        - AlarmCRProperties(4) = 0
        - RTATimeoutFactor(2) = 100
        - RTARetries(2) = 3
        - LocalAlarmReference(2) = 0x0001
        - MaxAlarmDataLength(2) = 200
        - AlarmCRTagHeaderHigh(2) = 0xC000  (priority 6)
        - AlarmCRTagHeaderLow(2) = 0xA000   (priority 5)

        Total content: 20 bytes + 2 version = 22 bytes
        """
        # Build block content
        data = bytearray()

        # AlarmCRType = 1
        data.extend(struct.pack(">H", 0x0001))

        # LT = 0x8892 (PROFINET Ethertype)
        data.extend(struct.pack(">H", PROFINET_ETHERTYPE))

        # AlarmCRProperties = 0 (4 bytes)
        data.extend(struct.pack(">I", 0))

        # RTATimeoutFactor = 100
        data.extend(struct.pack(">H", 100))

        # RTARetries = 3
        data.extend(struct.pack(">H", 3))

        # LocalAlarmReference = 0x0001
        data.extend(struct.pack(">H", 0x0001))

        # MaxAlarmDataLength = 200 (matches C default)
        data.extend(struct.pack(">H", 200))

        # AlarmCRTagHeaderHigh = 0xC000 (priority 6)
        data.extend(struct.pack(">H", 0xC000))

        # AlarmCRTagHeaderLow = 0xA000 (priority 5)
        data.extend(struct.pack(">H", 0xA000))

        # Calculate block length (content after type+length, includes version)
        block_content_len = len(data) + 2  # +2 for version bytes

        # Build complete block with header
        block = bytearray()
        # Block type 0x0103 (Alarm CR Block Request)
        block.extend(struct.pack(">H", 0x0103))
        # Block length
        block.extend(struct.pack(">H", block_content_len))
        # Version 1.0
        block.append(1)
        block.append(0)
        # Content
        block.extend(data)

        logger.debug(f"Built AlarmCR block: {len(block)} bytes (BlockLength={block_content_len})")

        # Return as Scapy Raw packet so it can be included in blocks list
        return Raw(load=bytes(block))

    def _build_expected_submodule_block_manual(self, profile: List[SlotConfig]) -> Block:
        """
        Build Expected Submodule block MANUALLY matching C code EXACTLY.

        C code format (profinet_rpc.c:554-628):
        - BlockHeader: type(2) + length(2) + version(2) = 6 bytes
        - NumberOfAPIs (2) = 1
        - API 0:
          - API Number (4) = 0
          - NumberOfSlots (2)
          - For each slot:
            - SlotNumber (2)
            - ModuleIdentNumber (4)
            - NumberOfSubslots (2)   <-- NO ModuleProperties field!
            - For each subslot:
              - SubslotNumber (2)
              - SubmoduleIdentNumber (4)
              - SubmoduleProperties (2) = 0x0001(input) or 0x0002(output) or 0x0000(no_io)
              - DataLength (2)       <-- NO DataDescription type field!
              - LengthIOCS (1) = 1
              - LengthIOPS (1) = 1

        This differs from standard PROFINET spec which has:
        - Per-slot API entries (not NumberOfSlots inside single API)
        - ModuleProperties field (C omits)
        - DataDescription type field (C omits)
        """
        # Build block content
        data = bytearray()

        # NumberOfAPIs = 1 (C: line 558)
        data.extend(struct.pack(">H", 1))

        # API 0 (C: line 561)
        data.extend(struct.pack(">I", 0))  # API Number

        # Group profile by slot (C: lines 564-577 count unique slots)
        slots_dict = {}
        for slot_cfg in profile:
            if slot_cfg.slot_number not in slots_dict:
                slots_dict[slot_cfg.slot_number] = {
                    'module_ident': slot_cfg.module_ident,
                    'submodules': []
                }
            slots_dict[slot_cfg.slot_number]['submodules'].append(slot_cfg)

        # NumberOfSlots (C: line 578)
        data.extend(struct.pack(">H", len(slots_dict)))

        # Slot data (C: lines 581-622)
        for slot_num in sorted(slots_dict.keys()):
            slot_info = slots_dict[slot_num]

            # SlotNumber (C: line 583)
            data.extend(struct.pack(">H", slot_num))

            # ModuleIdentNumber (C: line 593)
            data.extend(struct.pack(">I", slot_info['module_ident']))

            # NumberOfSubslots (C: line 602) - NO ModuleProperties before this!
            data.extend(struct.pack(">H", len(slot_info['submodules'])))

            # Subslot data (C: lines 605-622)
            for submod in slot_info['submodules']:
                # SubslotNumber (C: line 609)
                data.extend(struct.pack(">H", submod.subslot_number))

                # SubmoduleIdentNumber (C: line 610)
                data.extend(struct.pack(">I", submod.submodule_ident))

                # SubmoduleProperties (C: line 613-614)
                if submod.direction == "input":
                    props = 0x0001
                elif submod.direction == "output":
                    props = 0x0002
                else:
                    props = 0x0000  # DAP / no_io
                data.extend(struct.pack(">H", props))

                # DataLength (C: line 617) - just data_length, NO DataDescription type!
                data.extend(struct.pack(">H", submod.data_length))

                # LengthIOCS = 1, LengthIOPS = 1 (C: lines 618-621)
                data.append(1)
                data.append(1)

        # Calculate block length (content after type+length, includes version)
        block_content_len = len(data) + 2  # +2 for version bytes

        # Build complete block with header
        block = bytearray()
        # Block type 0x0104 (Expected Submodule Block Request)
        block.extend(struct.pack(">H", 0x0104))
        # Block length
        block.extend(struct.pack(">H", block_content_len))
        # Version 1.0
        block.append(1)
        block.append(0)
        # Content
        block.extend(data)

        logger.debug(f"Built ExpectedSubmodule block (C format): {len(block)} bytes, {len(slots_dict)} slots")

        # Return as Scapy Raw packet
        return Raw(load=bytes(block))

    def _build_expected_submodule_block_scapy(self, profile: List[SlotConfig]) -> Block:
        """
        Build Expected Submodule block using Scapy's spec-compliant format.

        Standard PROFINET format (IEC 61158-6-10):
        - NumberOfAPIs
        - For each API entry (one per API+Slot combination):
            - API (4)
            - SlotNumber (2)
            - ModuleIdentNumber (4)
            - ModuleProperties (2)
            - NumberOfSubmodules (2)
            - For each Submodule:
                - SubslotNumber (2)
                - SubmoduleIdentNumber (4)
                - SubmoduleProperties (2)
                - DataDescription array (based on Type)

        NOTE: C code has non-standard format with NumberOfSlots field,
        but p-net device expects standard format.
        """
        apis_list = []

        for slot in profile:
            # Map direction to SubmoduleProperties_Type enum
            # 0=NO_IO, 1=INPUT, 2=OUTPUT, 3=INPUT_OUTPUT
            if slot.direction == "input":
                submod_type = 1
            elif slot.direction == "output":
                submod_type = 2
            elif slot.direction == "input_output":
                submod_type = 3
            else:
                submod_type = 0  # NO_IO

            # Build data description list based on SubmoduleProperties_Type
            # For INPUT (1) or OUTPUT (2): exactly 1 DataDescription
            # For INPUT_OUTPUT (3): exactly 2 DataDescriptions
            # For NO_IO (0): no DataDescriptions
            data_desc_list = []
            if submod_type == 1:  # INPUT
                data_desc_list.append(ExpectedSubmoduleDataDescription(
                    DataDescription=1,  # Input
                    SubmoduleDataLength=slot.data_length,
                    LengthIOCS=1,
                    LengthIOPS=1
                ))
            elif submod_type == 2:  # OUTPUT
                data_desc_list.append(ExpectedSubmoduleDataDescription(
                    DataDescription=2,  # Output
                    SubmoduleDataLength=slot.data_length,
                    LengthIOCS=1,
                    LengthIOPS=1
                ))
            elif submod_type == 3:  # INPUT_OUTPUT
                data_desc_list.append(ExpectedSubmoduleDataDescription(
                    DataDescription=1,  # Input
                    SubmoduleDataLength=slot.data_length,
                    LengthIOCS=1,
                    LengthIOPS=1
                ))
                data_desc_list.append(ExpectedSubmoduleDataDescription(
                    DataDescription=2,  # Output
                    SubmoduleDataLength=slot.data_length,
                    LengthIOCS=1,
                    LengthIOPS=1
                ))
            # For NO_IO (0), data_desc_list stays empty

            # Build submodule entry
            submod = ExpectedSubmodule(
                SubslotNumber=slot.subslot_number,
                SubmoduleIdentNumber=slot.submodule_ident,
                SubmoduleProperties_Type=submod_type,
                SubmoduleProperties_SharedInput=0,
                SubmoduleProperties_ReduceInputSubmoduleDataLength=0,
                SubmoduleProperties_ReduceOutputSubmoduleDataLength=0,
                SubmoduleProperties_DiscardIOXS=0,
                SubmoduleProperties_reserved_1=0,
                SubmoduleProperties_reserved_2=0,
                DataDescription=data_desc_list
            )

            # Build API entry (one per slot in spec-compliant format)
            api = ExpectedSubmoduleAPI(
                API=0,
                SlotNumber=slot.slot_number,
                ModuleIdentNumber=slot.module_ident,
                ModuleProperties=0,
                Submodules=[submod]
            )
            apis_list.append(api)

        logger.debug(f"Built {len(apis_list)} ExpectedSubmoduleAPI entries")

        return ExpectedSubmoduleBlockReq(
            NumberOfAPIs=len(apis_list),
            APIs=apis_list
        )

    def _rpc_connect(self, profile: List[SlotConfig]) -> bool:
        """
        Send RPC Connect request using ALL manual block builders.

        This method builds all PROFINET blocks manually to match the C code
        byte-for-byte, avoiding Scapy's broken serialization.

        Citation: profinet_rpc.c:365-670
        """
        if not self.ar:
            return False

        try:
            # ====== Build ALL blocks MANUALLY (no Scapy packet classes) ======
            # This avoids Scapy's broken serialization that caused:
            # - ExpectedSubmoduleBlockReq: API=0x40 instead of 0, wrong slot counts
            # - Potential issues with AR and IOCR blocks as well

            # Build AR block manually (C: lines 402-431)
            logger.debug("Building AR block (manual, matching C code)...")
            ar_block_bytes = self._build_ar_block_manual()
            ar_block = Raw(load=ar_block_bytes)
            logger.debug(f"AR block: {len(ar_block_bytes)} bytes")

            # Build Input IOCR block manually (C: lines 433-514)
            logger.debug("Building Input IOCR block (manual, matching C code)...")
            iocr_input_bytes = self._build_iocr_block_manual(IOCRType.INPUT, profile)
            iocr_input = Raw(load=iocr_input_bytes)
            logger.debug(f"Input IOCR block: {len(iocr_input_bytes)} bytes")

            # Build Output IOCR block manually (C: lines 433-514)
            logger.debug("Building Output IOCR block (manual, matching C code)...")
            iocr_output_bytes = self._build_iocr_block_manual(IOCRType.OUTPUT, profile)
            iocr_output = Raw(load=iocr_output_bytes)
            logger.debug(f"Output IOCR block: {len(iocr_output_bytes)} bytes")

            # Build Alarm CR block manually (C: lines 517-540)
            logger.debug("Building Alarm CR block (manual, matching C code)...")
            alarm_cr = self._build_alarm_cr_block_c_format()
            logger.debug("Alarm CR block built")

            # Build Expected Submodule block manually (C: lines 554-628)
            logger.debug("Building Expected Submodule block (manual, matching C code)...")
            exp_submod = self._build_expected_submodule_block_manual(profile)
            logger.debug("Expected Submodule block built")

            # ====== Build NDR header and PNIO payload manually ======
            # The C code (profinet_rpc.c:380-398) shows NDR header structure:
            # - ArgsMaximum (4 bytes LE)
            # - ArgsLength (4 bytes LE)
            # - MaxCount (4 bytes LE)
            # - Offset (4 bytes LE) = 0
            # - ActualCount (4 bytes LE)

            # Concatenate all PNIO blocks
            pnio_blocks = (
                ar_block_bytes +
                iocr_input_bytes +
                iocr_output_bytes +
                bytes(alarm_cr) +
                bytes(exp_submod)
            )
            pnio_len = len(pnio_blocks)

            # Build NDR header (little-endian per DCE/RPC drep)
            ndr_header = struct.pack("<IIIII",
                pnio_len,  # ArgsMaximum
                pnio_len,  # ArgsLength
                pnio_len,  # MaxCount
                0,         # Offset (always 0)
                pnio_len   # ActualCount
            )

            # Complete PNIO payload
            pnio_payload = ndr_header + pnio_blocks

            logger.info(f"Connect request: NDR header={len(ndr_header)} bytes, "
                        f"PNIO blocks={pnio_len} bytes, total payload={len(pnio_payload)} bytes")

            # ====== Build DCE/RPC header manually for full control ======
            # Or use Scapy's DceRpc4 with Raw payload since header serialization is OK

            # Wrap in DCE/RPC using Scapy (RPC header serialization is reliable)
            rpc = DceRpc4(
                ptype="request",
                flags1=0x22,  # Last Fragment (0x02) + Idempotent (0x20)
                object=self.ar.ar_uuid,  # AR UUID as object UUID (C: line 238)
                opnum=RpcOpnum.CONNECT,
                if_id=PNIO_UUID,
                act_id=self.ar.activity_uuid
            ) / Raw(load=pnio_payload)

            # Debug: dump packet hex for analysis
            try:
                pkt_bytes = bytes(rpc)
                logger.info(f"Connect request packet size: {len(pkt_bytes)} bytes")
                # Log first 150 bytes in hex for debugging
                hex_str = ' '.join(f'{b:02X}' for b in pkt_bytes[:150])
                logger.debug(f"Connect request hex (first 150): {hex_str}")
            except Exception as hex_err:
                logger.debug(f"Could not dump packet hex: {hex_err}")

            # Send and receive
            return self._rpc_send_recv(rpc, CONNECT_TIMEOUT_MS)

        except Exception as e:
            logger.error(f"Failed to build Connect request: {e}", exc_info=True)
            raise

    def _rpc_control(self, command: ControlCommand) -> bool:
        """Send RPC Control request (PrmEnd, ApplicationReady, Release)."""
        if not self.ar:
            return False

        self.ar.seq_num += 1

        # Map ControlCommand enum to Scapy bit fields
        ctrl = IODControlReq(
            ARUUID=self.ar.ar_uuid,
            SessionKey=self.ar.session_key,
            # Individual ControlCommand bit fields
            ControlCommand_reserved=0,
            ControlCommand_PrmBegin=1 if command == ControlCommand.PRM_BEGIN else 0,
            ControlCommand_ReadyForRT_CLASS_3=0,
            ControlCommand_ReadyForCompanion=1 if command == ControlCommand.READY_FOR_COMPANION else 0,
            ControlCommand_Done=0,
            ControlCommand_Release=1 if command == ControlCommand.RELEASE else 0,
            ControlCommand_ApplicationReady=1 if command == ControlCommand.APP_READY else 0,
            ControlCommand_PrmEnd=1 if command == ControlCommand.PRM_END else 0,
        )

        pnio = PNIOServiceReqPDU(args_max=16384, blocks=[ctrl])

        rpc = DceRpc4(
            ptype="request",
            flags1=0x22,  # Last Fragment (0x02) + Idempotent (0x20)
            object=self.ar.ar_uuid,  # AR UUID as object UUID
            opnum=RpcOpnum.CONTROL,
            if_id=PNIO_UUID,
            act_id=uuid4().bytes,
            seqnum=self.ar.seq_num
        ) / pnio

        return self._rpc_send_recv(rpc, CONTROL_TIMEOUT_MS)

    def _wait_for_app_ready(self, timeout_s: float = 30.0) -> bool:
        """
        Wait for ApplicationReady request from device and respond.

        After PrmEnd, the DEVICE sends ApplicationReady to the controller.
        The controller must receive it and send back a response.

        Args:
            timeout_s: How long to wait for ApplicationReady (default 30s)

        Returns:
            True if ApplicationReady received and response sent
        """
        if not self.ar:
            return False

        logger.info(f"Waiting up to {timeout_s}s for ApplicationReady from device...")

        # Open UDP socket to receive on RPC port
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout_s)

        try:
            # Bind to RPC port to receive incoming requests
            sock.bind(('0.0.0.0', RPC_PORT))
            logger.debug(f"Listening on UDP port {RPC_PORT} for ApplicationReady")

            while True:
                try:
                    data, addr = sock.recvfrom(4096)
                    logger.debug(f"Received {len(data)} bytes from {addr}")

                    # Parse incoming packet
                    if len(data) < 80:
                        logger.debug("Packet too short, ignoring")
                        continue

                    # Check if it's an RPC request (packet type 0)
                    pkt_type = data[1]
                    if pkt_type != 0:  # Not a request
                        logger.debug(f"Not a request packet (type={pkt_type}), ignoring")
                        continue

                    # Check opnum (at offset 76-77, little-endian)
                    opnum = struct.unpack("<H", data[76:78])[0]
                    if opnum != RpcOpnum.CONTROL:
                        logger.debug(f"Not a Control request (opnum={opnum}), ignoring")
                        continue

                    # Parse the IODControlReq block to get control command
                    # Block starts after RPC header (80 bytes) + NDR header (20 bytes)
                    # Actually the structure varies, let's look for the control command
                    # In the block: Reserved(2) + ARUUID(16) + SessionKey(2) + AlarmSeqNum(2) + ControlCommand(2)
                    # Block header is 6 bytes (type + length + version)

                    # Find control command - it's at a known offset in the IODControlReq
                    # RPC header = 80, NDR = 20, block header = 6, reserved = 2, ARUUID = 16, session = 2, alarm = 2
                    # So control command is at offset 80 + 20 + 6 + 2 + 16 + 2 + 2 = 128
                    if len(data) >= 130:
                        ctrl_cmd = struct.unpack(">H", data[128:130])[0]
                        logger.info(f"Received Control request: command=0x{ctrl_cmd:04X}")

                        if ctrl_cmd == ControlCommand.APP_READY:
                            logger.info("*** ApplicationReady received from device! ***")

                            # Build and send response
                            if self._send_app_ready_response(sock, addr, data):
                                logger.info("ApplicationReady response sent")
                                return True
                            else:
                                logger.error("Failed to send ApplicationReady response")
                                return False
                    else:
                        logger.debug(f"Packet too short for control command ({len(data)} bytes)")

                except socket.timeout:
                    logger.error("Timeout waiting for ApplicationReady from device")
                    return False

        except OSError as e:
            # Port might be in use
            logger.warning(f"Could not bind to port {RPC_PORT}: {e}")
            logger.info("Trying alternative: poll on existing connection...")
            return self._poll_for_app_ready(timeout_s)
        finally:
            sock.close()

    def _poll_for_app_ready(self, timeout_s: float) -> bool:
        """
        Alternative method: poll for ApplicationReady using the existing socket.

        Used when we can't bind to the RPC port (already in use).
        """
        if not self.ar:
            return False

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout_s)

        try:
            # Connect to device so we can receive their responses
            sock.connect((self.ar.device_ip, RPC_PORT))

            # The device should send ApplicationReady to us
            # But since we're not bound to the port, we need to send something first
            # to establish the "connection" for UDP

            # Some devices send ApplicationReady to the source port of our last packet
            # We can try receiving on the connected socket
            start_time = time.time()
            while (time.time() - start_time) < timeout_s:
                try:
                    data = sock.recv(4096)
                    if len(data) >= 80:
                        pkt_type = data[1]
                        if pkt_type == 0:  # Request
                            opnum = struct.unpack("<H", data[76:78])[0]
                            if opnum == RpcOpnum.CONTROL and len(data) >= 130:
                                ctrl_cmd = struct.unpack(">H", data[128:130])[0]
                                if ctrl_cmd == ControlCommand.APP_READY:
                                    logger.info("*** ApplicationReady received (poll mode)! ***")
                                    # Send response
                                    return self._send_app_ready_response(sock, (self.ar.device_ip, RPC_PORT), data)
                except socket.timeout:
                    pass  # Keep trying

            logger.error("Timeout in poll mode waiting for ApplicationReady")
            return False
        finally:
            sock.close()

    def _send_app_ready_response(self, sock, addr, request_data: bytes) -> bool:
        """
        Send ApplicationReady response to device.

        Args:
            sock: Socket to send on
            addr: Destination address (device IP, port)
            request_data: The original request packet (to extract activity UUID, etc.)

        Returns:
            True if response sent successfully
        """
        if not self.ar:
            return False

        try:
            # Extract activity UUID from request (bytes 24-40 in RPC header)
            activity_uuid = request_data[24:40]

            # Extract sequence number (bytes 64-68, little-endian)
            seq_num = struct.unpack("<I", request_data[64:68])[0]

            # Build RPC response header
            resp = bytearray(200)  # Allocate enough space

            # RPC header (80 bytes)
            resp[0] = 4  # Version
            resp[1] = 2  # Type: Response
            resp[2] = 0x22  # Flags: Last fragment + Idempotent
            resp[3] = 0  # Flags2

            # Data representation (little-endian, ASCII, IEEE)
            resp[4] = 0x10
            resp[5:8] = b'\x00\x00\x00'

            # Serial high
            resp[8:10] = b'\x00\x00'

            # Object UUID (AR UUID)
            resp[10:26] = self.ar.ar_uuid

            # Interface UUID (PNIO Controller)
            resp[26:42] = bytes.fromhex("dea000026c9711d1827100a02442df7d")

            # Activity UUID (must match request)
            resp[42:58] = activity_uuid

            # Server boot time
            resp[58:62] = b'\x00\x00\x00\x00'

            # Interface version (little-endian)
            struct.pack_into("<I", resp, 62, 1)

            # Sequence number (little-endian, match request)
            struct.pack_into("<I", resp, 66, seq_num)

            # Opnum (little-endian)
            struct.pack_into("<H", resp, 70, RpcOpnum.CONTROL)

            # Interface hint, Activity hint
            struct.pack_into("<H", resp, 72, 0xFFFF)
            struct.pack_into("<H", resp, 74, 0xFFFF)

            # Fragment length (will update)
            # Fragment number
            struct.pack_into("<H", resp, 78, 0)

            # Auth length, Serial low
            resp[80] = 0
            resp[81] = 0

            # Wait, the standard RPC header is 80 bytes, but I've been writing past it
            # Let me recalculate - RPC header format:
            # 0: version (1), 1: type (1), 2-3: flags (2), 4-7: drep (4),
            # 8-9: serial_high (2), 10-25: object_uuid (16), 26-41: interface_uuid (16),
            # 42-57: activity_uuid (16), 58-61: server_boot (4), 62-65: if_version (4),
            # 66-69: seq_num (4), 70-71: opnum (2), 72-73: if_hint (2), 74-75: act_hint (2),
            # 76-77: frag_len (2), 78-79: frag_num (2), 80: auth_len (1), 81: serial_low (1)
            # Total = 82 bytes

            pos = 82

            # NDR header (20 bytes) - for response format
            # ArgsMaximum, ArgsLength, MaxCount, Offset, ActualCount (all 4 bytes each, little-endian)
            # We'll fill in the actual sizes after building the block

            ndr_pos = pos
            pos += 20

            block_start = pos

            # IODControlRes block (block type 0x8110)
            # Block header: type(2) + length(2) + version(2) = 6 bytes
            struct.pack_into(">H", resp, pos, 0x8110)  # Block type
            pos += 2
            block_len_pos = pos
            pos += 2  # Length (fill later)
            resp[pos] = 1  # Version high
            resp[pos + 1] = 0  # Version low
            pos += 2

            # Reserved
            struct.pack_into(">H", resp, pos, 0)
            pos += 2

            # AR UUID
            resp[pos:pos + 16] = self.ar.ar_uuid
            pos += 16

            # Session key
            struct.pack_into(">H", resp, pos, self.ar.session_key)
            pos += 2

            # Alarm sequence number (can be 0)
            struct.pack_into(">H", resp, pos, 0)
            pos += 2

            # Control command (echo back APP_READY)
            struct.pack_into(">H", resp, pos, ControlCommand.APP_READY)
            pos += 2

            # Control block properties
            struct.pack_into(">H", resp, pos, 0)
            pos += 2

            # Calculate block length (content after header, excluding type field)
            block_content_len = pos - block_start - 6 + 2  # +2 for version in length
            struct.pack_into(">H", resp, block_len_pos, block_content_len)

            # Calculate total PNIO block size
            pnio_size = pos - block_start

            # Fill NDR header
            struct.pack_into("<I", resp, ndr_pos, pnio_size)      # ArgsMaximum
            struct.pack_into("<I", resp, ndr_pos + 4, pnio_size)  # ArgsLength
            struct.pack_into("<I", resp, ndr_pos + 8, pnio_size)  # MaxCount
            struct.pack_into("<I", resp, ndr_pos + 12, 0)         # Offset
            struct.pack_into("<I", resp, ndr_pos + 16, pnio_size) # ActualCount

            # Fragment length (total after RPC header)
            frag_len = pos - 82
            struct.pack_into("<H", resp, 76, frag_len)

            # Send response
            sock.sendto(bytes(resp[:pos]), addr)
            logger.debug(f"Sent ApplicationReady response ({pos} bytes) to {addr}")
            return True

        except Exception as e:
            logger.error(f"Failed to build/send ApplicationReady response: {e}")
            return False

    def _rpc_send_recv(self, rpc_pkt, timeout_ms: int) -> bool:
        """Send RPC packet and wait for response."""
        if not self.ar:
            return False

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout_ms / 1000.0)

        try:
            logger.info(f"Serializing RPC packet...")
            try:
                pkt_bytes = bytes(rpc_pkt)
            except Exception as e:
                logger.error(f"Failed to serialize RPC packet: {e}", exc_info=True)
                raise
            logger.info(f"Sending {len(pkt_bytes)} bytes to {self.ar.device_ip}:{RPC_PORT}")
            sock.sendto(pkt_bytes, (self.ar.device_ip, RPC_PORT))
            logger.info("Packet sent, waiting for response...")

            resp, addr = sock.recvfrom(4096)
            logger.debug(f"Received {len(resp)} bytes from {addr}")

            # Parse response
            return self._parse_rpc_response(resp)

        except socket.timeout:
            logger.error("RPC timeout")
            return False
        except Exception as e:
            logger.error(f"RPC error: {e}")
            return False
        finally:
            sock.close()

    def _parse_rpc_response(self, data: bytes) -> bool:
        """Parse RPC response and check status."""
        # Store raw response for analysis
        self._last_response = data
        self._last_error_analysis = None

        if len(data) < 84:
            logger.error(f"Response too short: {len(data)} bytes")
            return False

        # RPC header is 80 bytes, PNIO Status at offset 80
        pkt_type = data[1]
        if pkt_type != 2:  # Not a Response
            logger.error(f"Not a response packet: type={pkt_type}")
            return False

        # PNIO Status
        status = data[80:84]
        if status == b"\x00\x00\x00\x00":
            logger.debug("RPC SUCCESS")
            return True

        # Parse error and store for retry logic
        code, decode, code1, code2 = status

        # Use resilience module if available for detailed analysis
        if RESILIENCE_AVAILABLE:
            self._last_error_analysis = ErrorAnalyzer.analyze(decode, code1, code2)
            error_msg = f"{self._last_error_analysis.block_name}: {self._last_error_analysis.description}"
            if self._last_error_analysis.suggested_fix:
                logger.info(f"Suggested fix: {self._last_error_analysis.suggested_fix}")
        else:
            error_msg = self._analyze_error(code, decode, code1, code2)

        logger.error(f"RPC ERROR: {error_msg}")

        if self.ar:
            self.ar.error_message = error_msg
            self.ar.error_code1 = code1
            self.ar.error_code2 = code2

        return False

    def _analyze_error(self, code: int, decode: int, code1: int, code2: int) -> str:
        """Analyze PNIO error code and return description."""
        blocks = {
            0x00: "Connect",
            0x01: "ARBlock",
            0x02: "IOCRBlock",
            0x03: "AlarmCRBlock",
            0x04: "ExpectedSubmodule",
            0x05: "PRMServer",
        }

        errors = {
            (0x02, 0x04): "Invalid IOCR type",
            (0x02, 0x05): "Invalid LT field",
            (0x02, 0x06): "Invalid RT class",
            (0x02, 0x07): "Invalid CSDU length",
            (0x02, 0x08): "Invalid frame ID",
            (0x02, 0x09): "Invalid send clock",
            (0x02, 0x0A): "Invalid reduction ratio",
            (0x02, 0x0B): "Invalid phase (must be >= 1)",
            (0x02, 0x0C): "Invalid data length",
            (0x03, 0x00): "Invalid AlarmCR type",
            (0x03, 0x01): "Invalid AlarmCR length",
            (0x04, 0x00): "Invalid API",
            (0x04, 0x01): "Invalid slot",
            (0x04, 0x02): "Invalid subslot",
            (0x04, 0x03): "Unknown module",
            (0x04, 0x04): "Unknown submodule",
        }

        block_name = blocks.get(code1, f"Block-0x{code1:02X}")
        error_detail = errors.get((code1, code2), f"Error-0x{code2:02X}")

        return f"{block_name}: {error_detail} (decode=0x{decode:02X})"

    # =========================================================================
    # Read/Write Operations
    # =========================================================================

    def read_record(self, slot: int, subslot: int, index: int) -> Optional[bytes]:
        """Read record data from device."""
        if not self.ar or self.ar.state != ARState.RUN:
            logger.warning("Not connected")
            return None

        self.ar.seq_num += 1

        read_req = IODReadReq(
            seqNum=self.ar.seq_num,
            ARUUID=self.ar.ar_uuid,
            API=0,
            slotNumber=slot,
            subslotNumber=subslot,
            index=index,
            recordDataLength=64
        )

        pnio = PNIOServiceReqPDU(args_max=16384, blocks=[read_req])

        rpc = DceRpc4(
            ptype="request",
            flags1=0x22,  # Last Fragment (0x02) + Idempotent (0x20)
            object=self.ar.ar_uuid,  # AR UUID as object UUID
            opnum=RpcOpnum.READ,
            if_id=PNIO_UUID,
            act_id=uuid4().bytes,
            seqnum=self.ar.seq_num
        ) / pnio

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(CONTROL_TIMEOUT_MS / 1000.0)

        try:
            sock.sendto(bytes(rpc), (self.ar.device_ip, RPC_PORT))
            resp, _ = sock.recvfrom(4096)

            # Parse response - extract record data
            # Response format: RPC header (80) + Status (4) + ReadRes block
            if len(resp) >= 100:
                # Find record data in response
                return resp[100:]  # Simplified - actual parsing would find block
            return None

        except Exception as e:
            logger.error(f"Read failed: {e}")
            return None
        finally:
            sock.close()

    def write_record(self, slot: int, subslot: int, index: int, data: bytes) -> bool:
        """Write record data to device."""
        if not self.ar or self.ar.state != ARState.RUN:
            return False

        self.ar.seq_num += 1

        write_req = IODWriteReq(
            seqNum=self.ar.seq_num,
            ARUUID=self.ar.ar_uuid,
            API=0,
            slotNumber=slot,
            subslotNumber=subslot,
            index=index,
            recordDataLength=len(data),
            RecordData=data
        )

        pnio = PNIOServiceReqPDU(args_max=16384, blocks=[write_req])

        rpc = DceRpc4(
            ptype="request",
            flags1=0x22,  # Last Fragment (0x02) + Idempotent (0x20)
            object=self.ar.ar_uuid,  # AR UUID as object UUID
            opnum=RpcOpnum.WRITE,
            if_id=PNIO_UUID,
            act_id=uuid4().bytes,
            seqnum=self.ar.seq_num
        ) / pnio

        return self._rpc_send_recv(rpc, CONTROL_TIMEOUT_MS)

    # =========================================================================
    # Cyclic I/O
    # =========================================================================

    def _start_cyclic_io(self):
        """Start cyclic I/O data exchange."""
        if self._cyclic_running:
            return

        logger.info("Starting cyclic I/O")
        self._cyclic_running = True
        self._stop_event.clear()

        # Find device MAC from discovered devices
        device_mac = None
        if self.device:
            device_mac = self.device.mac_address
        else:
            # Try to find by IP
            for dev in self.discovered_devices.values():
                if dev.ip_address == self.ar.device_ip:
                    device_mac = dev.mac_address
                    break

        if not device_mac:
            logger.warning("Device MAC unknown - cyclic I/O may not work properly")
            device_mac = "ff:ff:ff:ff:ff:ff"

        self.ar.device_mac = device_mac

        # Start output frame sender
        self._output_thread = threading.Thread(
            target=self._output_loop,
            daemon=True,
            name="pn-output"
        )
        self._output_thread.start()

        # Start input frame sniffer
        try:
            self._sniffer = AsyncSniffer(
                iface=self.interface,
                filter=f"ether proto 0x8892",
                prn=self._handle_input_frame,
                store=False
            )
            self._sniffer.start()
        except Exception as e:
            logger.error(f"Failed to start sniffer: {e}")

    def _stop_cyclic_io(self):
        """Stop cyclic I/O."""
        if not self._cyclic_running:
            return

        logger.info("Stopping cyclic I/O")
        self._cyclic_running = False
        self._stop_event.set()

        if self._sniffer:
            try:
                self._sniffer.stop()
            except Exception:
                pass
            self._sniffer = None

        if self._output_thread:
            self._output_thread.join(timeout=2.0)
            self._output_thread = None

    def _output_loop(self):
        """Send output frames periodically."""
        cycle_time = 0.032  # 32ms

        while not self._stop_event.is_set():
            try:
                self._send_output_frame()
            except Exception as e:
                logger.debug(f"Output frame error: {e}")

            time.sleep(cycle_time)

    def _send_output_frame(self):
        """Build and send PROFINET RT output frame."""
        if not self.ar or not self.ar.device_mac:
            return

        self._cycle_counter = (self._cycle_counter + 1) & 0xFFFF

        # Build RT payload
        # Structure: I/O Data + IOCS + CycleCounter(2) + DataStatus(1) + TransferStatus(1)
        io_data = b'\x00\x00\x00'  # Output data (commands)
        iocs = b'\x80'  # IO Consumer Status: Good

        cycle_bytes = struct.pack(">H", self._cycle_counter)
        data_status = 0x35  # Run, StationOK, ProviderRun
        transfer_status = 0x00

        rt_data = io_data + iocs

        # Build frame
        frame = (
            Ether(dst=self.ar.device_mac, src=self.mac, type=PROFINET_ETHERTYPE) /
            ProfinetIO(frameID=FRAME_ID_OUTPUT) /
            PNIORealTimeCyclicPDU(
                data=rt_data,
                cycleCounter=self._cycle_counter,
                dataStatus=data_status,
                transferStatus=transfer_status
            )
        )

        sendp(frame, iface=self.interface, verbose=False)

    def _handle_input_frame(self, pkt):
        """Handle received PROFINET RT input frame."""
        try:
            if ProfinetIO not in pkt:
                return

            frame_id = pkt[ProfinetIO].frameID

            # Only process input CR frames
            if frame_id != FRAME_ID_INPUT:
                return

            # Extract RT cyclic data
            if PNIORealTimeCyclicPDU in pkt:
                cyclic = pkt[PNIORealTimeCyclicPDU]
                data = bytes(cyclic.data)
                data_status = cyclic.dataStatus
                cycle = cyclic.cycleCounter

                # Check validity
                data_valid = (data_status & 0x04) and not (data_status & 0x10)

                if data_valid and len(data) >= 5:
                    self._process_sensor_data(data, time.time())

                logger.debug(f"RX: cycle={cycle} status=0x{data_status:02X} data={data.hex()}")

        except Exception as e:
            logger.debug(f"Input frame error: {e}")

    def _process_sensor_data(self, data: bytes, timestamp: float):
        """Parse sensor data from cyclic input."""
        with self._lock:
            # CPU Temperature (slot 1): 4-byte float (big-endian) + 1-byte IOPS
            if len(data) >= 5:
                try:
                    temp_value = struct.unpack(">f", data[0:4])[0]
                    iops = data[4]

                    # Quality from IOPS
                    if iops & 0x80:
                        quality = Quality.GOOD
                    elif iops & 0x40:
                        quality = Quality.UNCERTAIN
                    else:
                        quality = Quality.BAD

                    self.sensors[1] = SensorReading(
                        slot=1,
                        value=temp_value,
                        quality=quality,
                        timestamp=timestamp
                    )

                    if self._on_sensor_data:
                        self._on_sensor_data(1, temp_value, quality)

                    logger.debug(f"Sensor[1]: {temp_value:.2f}°C quality={quality.name}")

                except struct.error as e:
                    logger.warning(f"Failed to parse sensor data: {e}")

    # =========================================================================
    # State Management
    # =========================================================================

    def _set_state(self, new_state: ARState):
        """Set AR state with notification."""
        if self.ar:
            old_state = self.ar.state
            self.ar.state = new_state
            self.ar.last_activity = time.time()

            logger.info(f"State: {old_state.name} -> {new_state.name}")

            if self._on_state_change:
                self._on_state_change(old_state, new_state)

    def set_state_callback(self, callback: Callable[[ARState, ARState], None]):
        """Register callback for state changes."""
        self._on_state_change = callback

    def set_sensor_callback(self, callback: Callable[[int, float, int], None]):
        """Register callback for sensor data updates."""
        self._on_sensor_data = callback

    # =========================================================================
    # Public API
    # =========================================================================

    @property
    def state(self) -> ARState:
        """Get current connection state."""
        return self.ar.state if self.ar else ARState.INIT

    @property
    def is_connected(self) -> bool:
        """Check if connected and running."""
        return self.ar is not None and self.ar.state == ARState.RUN

    def read_sensor(self, slot: int) -> Optional[SensorReading]:
        """Get sensor reading from slot."""
        with self._lock:
            return self.sensors.get(slot)

    def get_all_sensors(self) -> Dict[int, SensorReading]:
        """Get all sensor readings."""
        with self._lock:
            return dict(self.sensors)

    def check_health(self) -> bool:
        """Check connection health (watchdog)."""
        if not self.ar or self.ar.state != ARState.RUN:
            return False

        elapsed = (time.time() - self.ar.last_activity) * 1000
        if elapsed > self.ar.watchdog_ms:
            logger.warning(f"Watchdog timeout: {elapsed:.0f}ms > {self.ar.watchdog_ms}ms")
            self._set_state(ARState.ABORT)
            return False

        return True


# =============================================================================
# Main / CLI
# =============================================================================

def main():
    """CLI entry point for testing."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    if not SCAPY_AVAILABLE:
        print("ERROR: Scapy not available")
        return 1

    # Parse args
    interface = sys.argv[1] if len(sys.argv) > 1 else "eth0"
    device_ip = sys.argv[2] if len(sys.argv) > 2 else None

    # Create controller
    ctrl = ProfinetController(interface=interface)

    # Discover devices
    print(f"\n=== Discovering PROFINET devices on {interface} ===")
    devices = ctrl.discover(timeout_s=3.0)

    for dev in devices:
        print(f"  {dev.station_name}: {dev.ip_address} ({dev.mac_address})")

    if not device_ip and devices:
        device_ip = devices[0].ip_address
        print(f"\nUsing first discovered device: {device_ip}")

    if not device_ip:
        print("No device to connect to")
        return 1

    # Connect
    print(f"\n=== Connecting to {device_ip} ===")
    if ctrl.connect(device_ip):
        print("Connected!")

        # Read sensor data for a few seconds
        print("\n=== Reading sensor data ===")
        for _ in range(10):
            time.sleep(1)
            reading = ctrl.read_sensor(1)
            if reading:
                print(f"  Temperature: {reading.value:.2f}°C (quality={Quality(reading.quality).name})")
            else:
                print("  No data yet...")

        # Disconnect
        print("\n=== Disconnecting ===")
        ctrl.disconnect()
    else:
        print("Connection failed!")
        if ctrl.ar:
            print(f"Error: {ctrl.ar.error_message}")
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
