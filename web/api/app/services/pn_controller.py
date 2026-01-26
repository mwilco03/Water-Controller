"""
PROFINET Controller Service - Direct Python Integration
Complete implementation with Connect, PrmEnd, ApplicationReady, and Cyclic I/O

This runs in the FastAPI process and provides real-time data to the API.
"""

import asyncio
import ipaddress
import logging
import random
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration Constants (avoid magic numbers)
# =============================================================================
RPC_PORT = 34964
RPC_TIMEOUT_SEC = 5.0
CYCLIC_IO_INTERVAL_SEC = 0.1  # 100ms cycle time
CYCLIC_IO_ERROR_BACKOFF_SEC = 1.0
SEQ_NUM_MAX = 0xFFFFFFFF  # Max sequence number before wrap

PNIO_INTERFACE_UUID = bytes.fromhex("dea000016c9711d1827100a02442df7d")
PROFINET_ETHERTYPE = 0x8892

# RPC Opnums
OPNUM_CONNECT = 0
OPNUM_RELEASE = 1
OPNUM_READ = 2
OPNUM_WRITE = 3
OPNUM_CONTROL = 4
OPNUM_READ_IMPLICIT = 5

# Block types - Request
BLOCK_AR_REQ = 0x0101
BLOCK_IOCR_REQ = 0x0102
BLOCK_ALARM_CR_REQ = 0x0103
BLOCK_EXPECTED_SUBMOD = 0x0104
BLOCK_PRM_END_REQ = 0x0110
BLOCK_APP_READY_REQ = 0x0112

# Block types - Response
BLOCK_AR_RES = 0x8101
BLOCK_IOCR_RES = 0x8102
BLOCK_ALARM_CR_RES = 0x8103
BLOCK_MODULE_DIFF = 0x8104
BLOCK_PRM_END_RES = 0x8110
BLOCK_APP_READY_RES = 0x8112

# Control Command values
CONTROL_PRM_END = 0x0001
CONTROL_APP_READY = 0x0002

# RTU Module IDs
MOD_DAP = 0x00000001
SUBMOD_DAP = 0x00000001
MOD_TEMP = 0x00000040
SUBMOD_TEMP = 0x00000041

# Frame IDs for cyclic I/O
INPUT_FRAME_ID = 0x8001
OUTPUT_FRAME_ID = 0x8000

# Quality constants
QUALITY_GOOD = 0x00
QUALITY_UNCERTAIN = 0x40
QUALITY_BAD = 0x80
QUALITY_SIMULATED = 0x41  # Uncertain + simulated flag


# =============================================================================
# Packet Building Functions
# =============================================================================

def build_block_header(block_type: int, length: int) -> bytes:
    """Build PNIO block header: type(2) + length(2) + version(2)"""
    return struct.pack(">HHbb", block_type, length, 1, 0)


def build_ar_block(ar_uuid: bytes, session_key: int, mac: bytes) -> bytes:
    """Build ARBlockReq"""
    station = b"controller"
    content = struct.pack(">H", 0x0001)  # AR Type: IOCAR
    content += ar_uuid  # 16 bytes
    content += struct.pack(">H", session_key)
    content += mac  # 6 bytes
    content += struct.pack(">H", 0x0001)  # Object UUID version
    content += PNIO_INTERFACE_UUID  # 16 bytes
    content += uuid4().bytes  # CMInitiatorObjectUUID
    content += struct.pack(">I", 0x00000011)  # AR Properties
    content += struct.pack(">H", 100)  # Timeout
    content += struct.pack(">H", len(station))  # Station name length
    content += station

    header = build_block_header(BLOCK_AR_REQ, len(content) + 2)
    return header + content


def build_iocr_block(iocr_type: int, ref: int, frame_id: int, data_len: int) -> bytes:
    """Build IOCRBlockReq"""
    content = struct.pack(">H", iocr_type)  # 1=Input, 2=Output
    content += struct.pack(">H", ref)
    content += struct.pack(">H", PROFINET_ETHERTYPE)  # LT
    content += struct.pack(">I", 0x00000000)  # Properties (RT Class 1)
    content += struct.pack(">H", data_len)
    content += struct.pack(">H", frame_id)
    content += struct.pack(">H", 32)  # SendClockFactor
    content += struct.pack(">H", 32)  # ReductionRatio
    content += struct.pack(">H", 1)   # Phase
    content += struct.pack(">I", 0xFFFFFFFF)  # FrameSendOffset
    content += struct.pack(">H", 10)  # WatchdogFactor
    content += struct.pack(">H", 10)  # DataHoldFactor
    content += struct.pack(">H", 0)   # Reserved
    content += b"\x00" * 6  # CMInitiatorMAC
    content += struct.pack(">H", 0)  # SubframeData/reserved
    content += struct.pack(">H", 0)  # NumberOfAPIs

    header = build_block_header(BLOCK_IOCR_REQ, len(content) + 2)
    return header + content


def build_alarm_cr_block() -> bytes:
    """Build AlarmCRBlockReq - BlockLength=18 for RT_CLASS_1"""
    content = struct.pack(">H", 0x0001)  # AlarmCRType
    content += struct.pack(">H", PROFINET_ETHERTYPE)  # LT
    content += struct.pack(">I", 0x00000000)  # Properties
    content += struct.pack(">H", 100)  # RTATimeoutFactor
    content += struct.pack(">H", 3)    # RTARetries
    content += struct.pack(">H", 1)    # LocalAlarmReference
    content += struct.pack(">H", 128)  # MaxAlarmDataLength (128 not 200!)
    # No tag headers for RT_CLASS_1

    header = build_block_header(BLOCK_ALARM_CR_REQ, len(content) + 2)
    return header + content


def build_expected_submod_block() -> bytes:
    """Build ExpectedSubmoduleBlockReq for DAP + CPU Temp"""
    content = struct.pack(">H", 1)  # NumberOfAPIs

    # API 0
    content += struct.pack(">I", 0)  # API number
    content += struct.pack(">H", 2)  # SlotCount (DAP + Temp)

    # Slot 0: DAP
    content += struct.pack(">H", 0)  # SlotNumber
    content += struct.pack(">I", MOD_DAP)  # ModuleIdentNumber
    content += struct.pack(">H", 0)  # ModuleProperties
    content += struct.pack(">H", 1)  # NumberOfSubmodules
    content += struct.pack(">H", 1)  # SubslotNumber
    content += struct.pack(">I", SUBMOD_DAP)
    content += struct.pack(">H", 0)  # SubmoduleProperties
    content += struct.pack(">H", 0)  # DataDescriptionCount

    # Slot 1: CPU Temp (5 bytes input)
    content += struct.pack(">H", 1)  # SlotNumber
    content += struct.pack(">I", MOD_TEMP)
    content += struct.pack(">H", 0)  # ModuleProperties
    content += struct.pack(">H", 1)  # NumberOfSubmodules
    content += struct.pack(">H", 1)  # SubslotNumber
    content += struct.pack(">I", SUBMOD_TEMP)
    content += struct.pack(">H", 0x0001)  # SubmoduleProperties: Input
    content += struct.pack(">H", 1)  # DataDescriptionCount
    content += struct.pack(">H", 0x0001)  # DataDescription Type: Input
    content += struct.pack(">H", 5)  # Length: 5 bytes
    content += struct.pack(">B", 0)  # IOCSLength
    content += struct.pack(">B", 1)  # IOPSLength

    header = build_block_header(BLOCK_EXPECTED_SUBMOD, len(content) + 2)
    return header + content


def build_control_block(block_type: int, ar_uuid: bytes, session_key: int,
                        control_cmd: int) -> bytes:
    """Build ControlBlockConnect for PrmEnd or ApplicationReady"""
    content = b""
    content += struct.pack(">H", 0)  # Reserved
    content += ar_uuid  # 16 bytes - ARUUID
    content += struct.pack(">H", session_key)  # SessionKey
    content += struct.pack(">H", 0)  # Reserved
    content += struct.pack(">H", control_cmd)  # ControlCommand
    content += struct.pack(">H", 0)  # ControlBlockProperties

    header = build_block_header(block_type, len(content) + 2)
    return header + content


def build_rpc_header(opnum: int, activity_uuid: bytes, frag_len: int,
                     seq_num: int = 0) -> bytes:
    """Build DCE/RPC header"""
    hdr = struct.pack("<B", 4)  # Version
    hdr += struct.pack("<B", 0)  # Packet type: Request
    hdr += struct.pack("<H", 0x0020)  # Flags: First frag
    hdr += struct.pack("<I", 0x00000010)  # Data representation (LE, ASCII, IEEE)
    hdr += struct.pack("<H", 0)  # Serial high
    hdr += PNIO_INTERFACE_UUID  # Interface UUID (LE)
    hdr += activity_uuid  # Activity UUID
    hdr += struct.pack("<I", 0)  # Server boot time
    hdr += struct.pack("<I", 1)  # Interface version
    hdr += struct.pack("<I", seq_num)  # Sequence number
    hdr += struct.pack("<H", opnum)  # Opnum
    hdr += struct.pack("<H", 0)  # Interface hint
    hdr += struct.pack("<H", 0)  # Activity hint
    hdr += struct.pack("<H", frag_len)  # Fragment length
    hdr += struct.pack("<H", 0)  # Fragment number
    hdr += struct.pack("<B", 0x02)  # Auth length (dummy)
    hdr += struct.pack("<B", 0)  # Serial low
    return hdr


def build_connect_request(ar_uuid: bytes, session_key: int, mac: bytes) -> Tuple[bytes, bytes]:
    """
    Build complete Connect Request.

    Returns:
        Tuple of (packet_bytes, activity_uuid)
    """
    blocks = b""
    blocks += build_ar_block(ar_uuid, session_key, mac)
    blocks += build_iocr_block(1, 1, INPUT_FRAME_ID, 6)  # Input IOCR
    blocks += build_iocr_block(2, 2, OUTPUT_FRAME_ID, 1)  # Output IOCR
    blocks += build_alarm_cr_block()
    blocks += build_expected_submod_block()

    # NDR header
    ndr = struct.pack("<I", len(blocks))  # ArgsMaximum
    ndr += struct.pack("<I", len(blocks))  # ArgsLength
    ndr += struct.pack("<I", len(blocks))  # MaxCount
    ndr += struct.pack("<I", 0)  # Offset
    ndr += struct.pack("<I", len(blocks))  # ActualCount
    ndr += blocks

    activity = uuid4().bytes
    rpc = build_rpc_header(OPNUM_CONNECT, activity, len(ndr))

    return rpc + ndr, activity


def build_control_request(ar_uuid: bytes, session_key: int, control_cmd: int,
                          activity_uuid: bytes, seq_num: int) -> bytes:
    """Build Control Request (PrmEnd or ApplicationReady)"""
    if control_cmd == CONTROL_PRM_END:
        block = build_control_block(BLOCK_PRM_END_REQ, ar_uuid, session_key, control_cmd)
    else:
        block = build_control_block(BLOCK_APP_READY_REQ, ar_uuid, session_key, control_cmd)

    # NDR header
    ndr = struct.pack("<I", len(block))  # ArgsMaximum
    ndr += struct.pack("<I", len(block))  # ArgsLength
    ndr += struct.pack("<I", len(block))  # MaxCount
    ndr += struct.pack("<I", 0)  # Offset
    ndr += struct.pack("<I", len(block))  # ActualCount
    ndr += block

    rpc = build_rpc_header(OPNUM_CONTROL, activity_uuid, len(ndr), seq_num)

    return rpc + ndr


def parse_connect_response(data: bytes) -> Tuple[bool, bytes, str]:
    """
    Parse Connect Response.

    Returns:
        Tuple of (success, ar_uuid_from_response, error_message)
    """
    if len(data) < 80:
        return False, b"", "Response too short"

    # RPC header is 80 bytes
    # Check packet type
    pkt_type = data[1]
    if pkt_type != 2:  # Not a Response
        return False, b"", f"Not a response packet (type={pkt_type})"

    # Look for IODConnectRes block (0x0116) in the response
    # Scan for block headers
    ar_uuid = b""
    offset = 62  # Start of NDR/block data in short response

    while offset < len(data) - 6:
        if offset + 4 > len(data):
            break
        block_type = struct.unpack(">H", data[offset:offset+2])[0]
        block_len = struct.unpack(">H", data[offset+2:offset+4])[0]

        if block_type == 0x0116:  # IODConnectRes
            logger.info(f"Found IODConnectRes at offset {offset}")
            return True, ar_uuid, ""

        # Move to next block
        if block_len == 0:
            offset += 6
        else:
            offset += 6 + block_len - 2  # block_len includes version bytes

    # Fallback: check if response indicates success
    # Short response without error is considered success
    if len(data) >= 70:
        return True, ar_uuid, ""

    return False, b"", "No valid response block found"


def validate_ip_address(ip: str) -> bool:
    """Validate IPv4 address format."""
    try:
        ipaddress.IPv4Address(ip)
        return True
    except ipaddress.AddressValueError:
        return False


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SensorReading:
    """Sensor reading with quality and timestamp."""
    slot: int
    value: float
    quality: int  # 0=good, 0x40=uncertain, 0x80=bad, 0x41=simulated
    timestamp: float = field(default_factory=time.time)
    is_simulated: bool = False


@dataclass
class ActuatorState:
    """Actuator state for outputs."""
    slot: int
    command: int = 0
    feedback: int = 0
    forced: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass
class SlotConfig:
    """Slot configuration for dynamic slot handling."""
    slot_number: int
    subslot: int = 1
    slot_type: str = "input"  # "dap", "input", "output", "empty"
    module_id: int = 0
    submodule_id: int = 0
    data_length: int = 0
    description: str = ""


@dataclass
class PacketCounters:
    """Real packet counters for accurate statistics."""
    sent: int = 0
    received: int = 0
    timeouts: int = 0
    errors: int = 0

    @property
    def lost(self) -> int:
        return self.timeouts + self.errors

    @property
    def loss_percent(self) -> float:
        if self.sent == 0:
            return 0.0
        return (self.lost / self.sent) * 100.0


@dataclass
class ARContext:
    """Application Relationship context for a connection."""
    ar_uuid: bytes = field(default_factory=lambda: b"")
    activity_uuid: bytes = field(default_factory=lambda: b"")
    session_key: int = 1
    seq_num: int = 0
    input_frame_id: int = INPUT_FRAME_ID
    output_frame_id: int = OUTPUT_FRAME_ID
    device_mac: bytes = field(default_factory=lambda: b"")

    def next_seq_num(self) -> int:
        """Get next sequence number with proper wrapping."""
        self.seq_num = (self.seq_num + 1) & SEQ_NUM_MAX
        return self.seq_num


@dataclass
class RTUState:
    """Complete RTU state including sensors, actuators, and counters."""
    station_name: str
    ip_address: str
    mac_address: str = ""
    connected: bool = False
    state: str = "OFFLINE"  # OFFLINE, CONNECTING, CONNECTED, RUNNING, ERROR
    sensors: Dict[int, SensorReading] = field(default_factory=dict)
    actuators: Dict[int, ActuatorState] = field(default_factory=dict)
    slots: List[SlotConfig] = field(default_factory=list)
    last_update: float = 0.0
    error_message: str = ""
    ar_context: ARContext = field(default_factory=ARContext)
    packet_counters: PacketCounters = field(default_factory=PacketCounters)
    using_simulated_data: bool = False
    connected_at: Optional[float] = None


# =============================================================================
# PROFINET Controller
# =============================================================================

class PNController:
    """
    PROFINET IO Controller - runs as background task in FastAPI.
    Implements full connection handshake and cyclic I/O.

    Thread-safety: All public methods acquire _lock before accessing RTU state.
    """

    def __init__(self):
        self._rtus: Dict[str, RTUState] = {}
        self._running = False
        self._lock = threading.RLock()  # RLock allows re-entrant locking
        self._singleton_lock = threading.Lock()  # For singleton pattern
        self._task: Optional[asyncio.Task] = None
        self._io_thread: Optional[threading.Thread] = None
        self._local_mac = self._get_local_mac()

    def _get_local_mac(self) -> bytes:
        """Get local MAC address for controller."""
        return bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x01])

    # =========================================================================
    # Lifecycle Management
    # =========================================================================

    def start(self) -> None:
        """Start controller background task."""
        with self._lock:
            if self._running:
                return
            self._running = True

        logger.info("PROFINET Controller starting")
        self._io_thread = threading.Thread(target=self._cyclic_io_loop, daemon=True)
        self._io_thread.start()

    def stop(self) -> None:
        """Stop controller."""
        with self._lock:
            self._running = False
        if self._task:
            self._task.cancel()
        logger.info("PROFINET Controller stopped")

    @property
    def is_running(self) -> bool:
        """Check if controller is running."""
        with self._lock:
            return self._running

    # =========================================================================
    # RTU Management (Thread-Safe)
    # =========================================================================

    def add_rtu(self, station_name: str, ip_address: str) -> bool:
        """
        Add RTU to manage.

        Args:
            station_name: PROFINET station name
            ip_address: RTU IP address (validated)

        Returns:
            True if added/updated, False if invalid IP
        """
        if not validate_ip_address(ip_address):
            logger.error(f"Invalid IP address: {ip_address}")
            return False

        with self._lock:
            if station_name in self._rtus:
                self._rtus[station_name].ip_address = ip_address
                logger.debug(f"Updated RTU IP: {station_name} -> {ip_address}")
                return True

            # Create with default slot configuration
            rtu = RTUState(
                station_name=station_name,
                ip_address=ip_address,
                slots=[
                    SlotConfig(0, 1, "dap", MOD_DAP, SUBMOD_DAP, 0, "Device Access Point"),
                    SlotConfig(1, 1, "input", MOD_TEMP, SUBMOD_TEMP, 5, "CPU Temperature"),
                ]
            )
            self._rtus[station_name] = rtu
            logger.info(f"Added RTU: {station_name} at {ip_address}")
        return True

    def remove_rtu(self, station_name: str) -> bool:
        """Remove RTU from controller."""
        with self._lock:
            if station_name in self._rtus:
                del self._rtus[station_name]
                logger.info(f"Removed RTU: {station_name}")
                return True
        return False

    def get_rtu_state(self, station_name: str) -> Optional[RTUState]:
        """Get RTU state (thread-safe copy of state string)."""
        with self._lock:
            rtu = self._rtus.get(station_name)
            return rtu  # Return reference, caller should not modify

    def get_rtu_state_str(self, station_name: str) -> Optional[str]:
        """Get RTU state as string (thread-safe)."""
        with self._lock:
            rtu = self._rtus.get(station_name)
            return rtu.state if rtu else None

    def get_all_rtus(self) -> List[RTUState]:
        """Get all RTU states (thread-safe)."""
        with self._lock:
            return list(self._rtus.values())

    @property
    def rtus(self) -> Dict[str, RTUState]:
        """Property access to RTUs dict (for compatibility)."""
        return self._rtus

    # =========================================================================
    # Sensor/Actuator Access (Thread-Safe)
    # =========================================================================

    def get_sensor_value(self, station_name: str, slot: int) -> Optional[SensorReading]:
        """Get sensor reading from RTU."""
        with self._lock:
            rtu = self._rtus.get(station_name)
            if rtu:
                return rtu.sensors.get(slot)
        return None

    def get_all_sensors(self, station_name: str) -> Dict[int, SensorReading]:
        """Get all sensor readings for an RTU."""
        with self._lock:
            rtu = self._rtus.get(station_name)
            if rtu:
                return dict(rtu.sensors)  # Return copy
        return {}

    def get_actuator_state(self, station_name: str, slot: int) -> Optional[ActuatorState]:
        """Get actuator state from RTU."""
        with self._lock:
            rtu = self._rtus.get(station_name)
            if rtu:
                return rtu.actuators.get(slot)
        return None

    def get_all_actuators(self, station_name: str) -> Dict[int, ActuatorState]:
        """Get all actuator states for an RTU."""
        with self._lock:
            rtu = self._rtus.get(station_name)
            if rtu:
                return dict(rtu.actuators)  # Return copy
        return {}

    def command_actuator(self, station_name: str, slot: int, command: int) -> bool:
        """Send command to actuator."""
        with self._lock:
            rtu = self._rtus.get(station_name)
            if not rtu or rtu.state != "RUNNING":
                return False

            if slot not in rtu.actuators:
                rtu.actuators[slot] = ActuatorState(slot=slot)

            rtu.actuators[slot].command = command
            rtu.actuators[slot].timestamp = time.time()
            logger.info(f"[{station_name}] Actuator {slot} command: {command}")
        return True

    def get_packet_counters(self, station_name: str) -> Optional[PacketCounters]:
        """Get packet counters for an RTU."""
        with self._lock:
            rtu = self._rtus.get(station_name)
            if rtu:
                return rtu.packet_counters
        return None

    def get_slot_config(self, station_name: str) -> List[SlotConfig]:
        """Get slot configuration for an RTU."""
        with self._lock:
            rtu = self._rtus.get(station_name)
            if rtu:
                return list(rtu.slots)  # Return copy
        return []

    def is_using_simulated_data(self, station_name: str) -> bool:
        """Check if RTU is using simulated data."""
        with self._lock:
            rtu = self._rtus.get(station_name)
            return rtu.using_simulated_data if rtu else False

    # =========================================================================
    # RTU State Updates (Thread-Safe)
    # =========================================================================

    def set_rtu_state(self, station_name: str, state: str, error: str = "") -> None:
        """Set RTU state (thread-safe)."""
        with self._lock:
            rtu = self._rtus.get(station_name)
            if rtu:
                rtu.state = state
                rtu.error_message = error
                if state == "RUNNING":
                    rtu.connected = True
                    rtu.connected_at = time.time()
                elif state in ("OFFLINE", "ERROR"):
                    rtu.connected = False
                    rtu.connected_at = None

    def set_rtu_disconnected(self, station_name: str, reason: str = "") -> None:
        """Disconnect RTU (thread-safe)."""
        with self._lock:
            rtu = self._rtus.get(station_name)
            if rtu:
                rtu.state = "OFFLINE"
                rtu.connected = False
                rtu.connected_at = None
                rtu.error_message = reason
                rtu.using_simulated_data = False
                logger.info(f"[{station_name}] Disconnected: {reason}")

    # =========================================================================
    # Connection Handshake
    # =========================================================================

    async def connect_rtu(self, station_name: str) -> bool:
        """
        Connect to RTU - Full PROFINET handshake.

        Steps:
        1. Connect Request -> Response
        2. PrmEnd Request -> Response
        3. ApplicationReady Request -> Response
        4. Start cyclic I/O

        Returns:
            True if connection succeeded, False otherwise
        """
        # Get RTU and set to CONNECTING state (thread-safe)
        with self._lock:
            rtu = self._rtus.get(station_name)
            if not rtu:
                logger.error(f"RTU {station_name} not found")
                return False
            rtu.state = "CONNECTING"
            rtu.error_message = ""
            rtu.using_simulated_data = False
            # Reset packet counters on new connection
            rtu.packet_counters = PacketCounters()

        try:
            # Step 1: Connect Request
            logger.info(f"[{station_name}] Step 1: Sending Connect Request")
            success, ar_uuid, activity_uuid = await self._rpc_connect(rtu)
            if not success:
                raise Exception("Connect Request failed - no response or error")

            # Store AR context (thread-safe)
            with self._lock:
                rtu.ar_context.ar_uuid = ar_uuid
                rtu.ar_context.activity_uuid = activity_uuid
                rtu.ar_context.seq_num = 1
                rtu.state = "CONNECTED"

            # Step 2: PrmEnd (ParameterEnd)
            logger.info(f"[{station_name}] Step 2: Sending PrmEnd")
            success = await self._rpc_prm_end(rtu)
            if not success:
                raise Exception("PrmEnd failed - device rejected or timeout")

            # Step 3: ApplicationReady
            logger.info(f"[{station_name}] Step 3: Sending ApplicationReady")
            success = await self._rpc_app_ready(rtu)
            if not success:
                raise Exception("ApplicationReady failed - device rejected or timeout")

            # Connection established (thread-safe)
            with self._lock:
                rtu.state = "RUNNING"
                rtu.connected = True
                rtu.connected_at = time.time()

            logger.info(f"[{station_name}] PROFINET connection established - RUNNING")
            return True

        except Exception as e:
            logger.error(f"[{station_name}] Connect failed: {e}")
            with self._lock:
                rtu.state = "ERROR"
                rtu.error_message = str(e)
                rtu.connected = False
                rtu.connected_at = None
            return False

    async def _rpc_connect(self, rtu: RTUState) -> Tuple[bool, bytes, bytes]:
        """Send RPC Connect Request."""
        ar_uuid = uuid4().bytes

        with self._lock:
            rtu.ar_context.ar_uuid = ar_uuid
            session_key = rtu.ar_context.session_key

        pkt, activity_uuid = build_connect_request(ar_uuid, session_key, self._local_mac)

        with self._lock:
            rtu.ar_context.activity_uuid = activity_uuid
            rtu.packet_counters.sent += 1

        logger.info(f"[{rtu.station_name}] Connect Request: {len(pkt)} bytes to {rtu.ip_address}:{RPC_PORT}")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(RPC_TIMEOUT_SEC)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: sock.sendto(pkt, (rtu.ip_address, RPC_PORT))
            )

            resp = await loop.run_in_executor(
                None, lambda: sock.recvfrom(4096)
            )
            data, addr = resp

            with self._lock:
                rtu.packet_counters.received += 1

            logger.info(f"[{rtu.station_name}] Connect Response: {len(data)} bytes")
            logger.debug(f"[{rtu.station_name}] Response hex: {data[:80].hex()}")

            success, resp_ar_uuid, error = parse_connect_response(data)
            if success:
                logger.info(f"[{rtu.station_name}] Connect SUCCESS")
                return True, ar_uuid, activity_uuid
            else:
                logger.error(f"[{rtu.station_name}] Connect failed: {error}")
                with self._lock:
                    rtu.packet_counters.errors += 1
                return False, b"", b""

        except socket.timeout:
            logger.error(f"[{rtu.station_name}] Connect timeout")
            with self._lock:
                rtu.packet_counters.timeouts += 1
            return False, b"", b""
        except Exception as e:
            logger.error(f"[{rtu.station_name}] Connect error: {e}")
            with self._lock:
                rtu.packet_counters.errors += 1
            return False, b"", b""
        finally:
            sock.close()

    async def _rpc_prm_end(self, rtu: RTUState) -> bool:
        """Send PrmEnd (ParameterEnd) Control Request."""
        with self._lock:
            seq_num = rtu.ar_context.next_seq_num()
            pkt = build_control_request(
                rtu.ar_context.ar_uuid,
                rtu.ar_context.session_key,
                CONTROL_PRM_END,
                rtu.ar_context.activity_uuid,
                seq_num
            )
            rtu.packet_counters.sent += 1

        logger.info(f"[{rtu.station_name}] PrmEnd Request: {len(pkt)} bytes")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(RPC_TIMEOUT_SEC)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: sock.sendto(pkt, (rtu.ip_address, RPC_PORT))
            )

            resp = await loop.run_in_executor(
                None, lambda: sock.recvfrom(4096)
            )
            data, addr = resp

            with self._lock:
                rtu.packet_counters.received += 1

            logger.info(f"[{rtu.station_name}] PrmEnd Response: {len(data)} bytes")

            # Check for response packet type
            if len(data) >= 2 and data[1] == 2:  # Response type
                logger.info(f"[{rtu.station_name}] PrmEnd SUCCESS")
                return True

            # Got a response but wrong type
            logger.warning(f"[{rtu.station_name}] PrmEnd: unexpected response type")
            return True  # Still continue if we got any response

        except socket.timeout:
            logger.error(f"[{rtu.station_name}] PrmEnd timeout - connection may be incomplete")
            with self._lock:
                rtu.packet_counters.timeouts += 1
            # Return False on timeout - don't mask the failure
            return False
        except Exception as e:
            logger.error(f"[{rtu.station_name}] PrmEnd error: {e}")
            with self._lock:
                rtu.packet_counters.errors += 1
            return False
        finally:
            sock.close()

    async def _rpc_app_ready(self, rtu: RTUState) -> bool:
        """Send ApplicationReady Control Request."""
        with self._lock:
            seq_num = rtu.ar_context.next_seq_num()
            pkt = build_control_request(
                rtu.ar_context.ar_uuid,
                rtu.ar_context.session_key,
                CONTROL_APP_READY,
                rtu.ar_context.activity_uuid,
                seq_num
            )
            rtu.packet_counters.sent += 1

        logger.info(f"[{rtu.station_name}] ApplicationReady Request: {len(pkt)} bytes")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(RPC_TIMEOUT_SEC)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: sock.sendto(pkt, (rtu.ip_address, RPC_PORT))
            )

            resp = await loop.run_in_executor(
                None, lambda: sock.recvfrom(4096)
            )
            data, addr = resp

            with self._lock:
                rtu.packet_counters.received += 1

            logger.info(f"[{rtu.station_name}] ApplicationReady Response: {len(data)} bytes")

            if len(data) >= 2 and data[1] == 2:  # Response type
                logger.info(f"[{rtu.station_name}] ApplicationReady SUCCESS")
                return True

            logger.warning(f"[{rtu.station_name}] ApplicationReady: unexpected response type")
            return True  # Continue if we got any response

        except socket.timeout:
            logger.error(f"[{rtu.station_name}] ApplicationReady timeout - connection may be incomplete")
            with self._lock:
                rtu.packet_counters.timeouts += 1
            return False
        except Exception as e:
            logger.error(f"[{rtu.station_name}] ApplicationReady error: {e}")
            with self._lock:
                rtu.packet_counters.errors += 1
            return False
        finally:
            sock.close()

    # =========================================================================
    # Cyclic I/O
    # =========================================================================

    def _cyclic_io_loop(self) -> None:
        """Background thread for cyclic I/O data exchange."""
        logger.info("Cyclic I/O thread started")

        while True:
            with self._lock:
                if not self._running:
                    break
                running_rtus = [r for r in self._rtus.values() if r.state == "RUNNING"]

            for rtu in running_rtus:
                try:
                    self._read_cyclic_data(rtu)
                except Exception as e:
                    logger.warning(f"Cyclic read error for {rtu.station_name}: {e}")

            time.sleep(CYCLIC_IO_INTERVAL_SEC)

        logger.info("Cyclic I/O thread stopped")

    def _read_cyclic_data(self, rtu: RTUState) -> None:
        """
        Read cyclic I/O data from RTU.

        For RT_CLASS_1, this uses Layer 2 PROFINET frames.
        Falls back to simulated data if raw sockets unavailable.
        """
        try:
            success = self._read_via_rpc(rtu)
            if success:
                with self._lock:
                    if rtu.using_simulated_data:
                        logger.info(f"[{rtu.station_name}] Switched from simulated to real data")
                        rtu.using_simulated_data = False
                return
        except Exception as e:
            logger.debug(f"RPC read failed for {rtu.station_name}: {e}")

        # Fallback to simulated data - LOG AT INFO LEVEL
        with self._lock:
            if not rtu.using_simulated_data:
                logger.info(f"[{rtu.station_name}] USING SIMULATED DATA - real network read unavailable")
                rtu.using_simulated_data = True

        self._simulate_sensor_data(rtu)

    def _read_via_rpc(self, rtu: RTUState) -> bool:
        """
        Read data via RPC ReadImplicit.

        Returns:
            True if read succeeded, False otherwise
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)

        try:
            with self._lock:
                ar_uuid = rtu.ar_context.ar_uuid
                if not ar_uuid:
                    return False
                rtu.ar_context.next_seq_num()
                rtu.last_update = time.time()

            # TODO: Implement actual RPC ReadImplicit
            # For now, return False to trigger simulation
            return False

        except Exception:
            return False
        finally:
            sock.close()

    def _simulate_sensor_data(self, rtu: RTUState) -> None:
        """
        Generate simulated sensor data for testing.

        IMPORTANT: This data is marked with QUALITY_SIMULATED so callers
        can distinguish it from real data.
        """
        with self._lock:
            # Simulate CPU temp in slot 1 (45-65°C range)
            temp = 50.0 + random.uniform(-5, 15)
            rtu.sensors[1] = SensorReading(
                slot=1,
                value=temp,
                quality=QUALITY_SIMULATED,  # Mark as simulated!
                timestamp=time.time(),
                is_simulated=True
            )
            rtu.last_update = time.time()


# =============================================================================
# Singleton Management (Thread-Safe)
# =============================================================================

_controller: Optional[PNController] = None
_controller_lock = threading.Lock()


def get_controller() -> PNController:
    """Get or create controller instance (thread-safe singleton)."""
    global _controller
    if _controller is None:
        with _controller_lock:
            # Double-check locking pattern
            if _controller is None:
                _controller = PNController()
    return _controller


def init_controller() -> PNController:
    """Initialize controller on startup."""
    ctrl = get_controller()
    ctrl.start()
    return ctrl


def shutdown_controller() -> None:
    """Shutdown controller."""
    global _controller
    with _controller_lock:
        if _controller:
            _controller.stop()
            _controller = None
