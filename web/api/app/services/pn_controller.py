"""
PROFINET Controller Service - Scapy-based Implementation
Uses Scapy's pnio_rpc module for proper PROFINET packet construction.

This runs in the FastAPI process and provides real-time data to the API.
"""

import asyncio
import logging
import struct
import socket
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)

# Import Scapy PROFINET modules
try:
    from scapy.all import conf, get_if_hwaddr
    from scapy.contrib.pnio_rpc import (
        Block, ARBlockReq, IOCRBlockReq, AlarmCRBlockReq,
        ExpectedSubmoduleBlockReq, IODControlReq,
        PNIOServiceReqPDU, PNIOServiceResPDU
    )
    from scapy.layers.dcerpc import DceRpc4
    SCAPY_RPC_AVAILABLE = True
    logger.info("Scapy PROFINET RPC modules loaded successfully")
except ImportError as e:
    SCAPY_RPC_AVAILABLE = False
    logger.warning(f"Scapy RPC modules not available: {e}")

# Import cyclic I/O manager (Scapy-based Layer 2)
try:
    from .pn_cyclic_io import get_cyclic_io_manager, SCAPY_AVAILABLE
    CYCLIC_IO_AVAILABLE = SCAPY_AVAILABLE
except ImportError:
    CYCLIC_IO_AVAILABLE = False
    logger.warning("Cyclic I/O module not available - sensor data will not flow")

# PROFINET Constants
RPC_PORT = 34964
PNIO_UUID = "dea00001-6c97-11d1-8271-00a02442df7d"
PNIO_INTERFACE_UUID = bytes.fromhex("dea000016c9711d1827100a02442df7d")
PROFINET_ETHERTYPE = 0x8892

# RPC Opnums
OPNUM_CONNECT = 0
OPNUM_RELEASE = 1
OPNUM_READ = 2
OPNUM_WRITE = 3
OPNUM_CONTROL = 4
OPNUM_READ_IMPLICIT = 5

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

# Data Quality Constants (OPC UA compatible)
QUALITY_GOOD = 0x00
QUALITY_UNCERTAIN = 0x40
QUALITY_BAD = 0x80
QUALITY_SIMULATED = 0x41


# =============================================================================
# LEGACY MANUAL PACKET BUILDING (COMMENTED OUT - REPLACED BY SCAPY)
# =============================================================================
# The following functions used manual struct.pack() for packet building.
# They are preserved for reference but replaced by Scapy's proper classes.
# =============================================================================

# def build_block_header(block_type: int, length: int) -> bytes:
#     """Build PNIO block header: type(2) + length(2) + version(2)"""
#     return struct.pack(">HHbb", block_type, length, 1, 0)
#
# def build_ar_block(ar_uuid: bytes, session_key: int, mac: bytes) -> bytes:
#     """Build ARBlockReq - REPLACED BY Scapy ARBlockReq"""
#     pass
#
# def build_iocr_block(iocr_type: int, ref: int, frame_id: int, data_len: int) -> bytes:
#     """Build IOCRBlockReq - REPLACED BY Scapy IOCRBlockReq"""
#     pass
#
# def build_alarm_cr_block() -> bytes:
#     """Build AlarmCRBlockReq - REPLACED BY Scapy AlarmCRBlockReq"""
#     pass
#
# def build_expected_submod_block() -> bytes:
#     """Build ExpectedSubmoduleBlockReq - REPLACED BY Scapy ExpectedSubmoduleBlockReq"""
#     pass
#
# def build_rpc_header(opnum: int, activity_uuid: bytes, frag_len: int, seq_num: int = 0) -> bytes:
#     """Build DCE/RPC header - REPLACED BY Scapy DceRpc4"""
#     pass
#
# def build_connect_request(ar_uuid: bytes, session_key: int, mac: bytes) -> bytes:
#     """Build complete Connect Request - REPLACED BY Scapy PNIOServiceReqPDU"""
#     pass


# =============================================================================
# SCAPY-BASED PACKET BUILDING
# =============================================================================

def build_connect_request_scapy(ar_uuid: bytes, session_key: int, mac_str: str,
                                 activity_uuid: bytes) -> bytes:
    """
    Build Connect Request using Scapy's PROFINET RPC classes.

    This produces packets identical to what the working pn_scapy_controller.py generates.
    """
    if not SCAPY_RPC_AVAILABLE:
        raise RuntimeError("Scapy RPC modules not available")

    # AR Block - Application Relationship
    ar_block = ARBlockReq(
        ARType=0x0001,  # IOCAR
        ARUUID=ar_uuid,
        SessionKey=session_key,
        CMInitiatorMacAdd=mac_str.replace(":", ""),
        CMInitiatorObjectUUID=uuid4().bytes,
        ARProperties_ParameterizationServer=0,
        ARProperties_DeviceAccess=0,
        ARProperties_CompanionAR=0,
        ARProperties_AcknowledgeCompanionAR=0,
        ARProperties_Reserved1=0,
        ARProperties_CMInitiator=1,
        ARProperties_SupervisorTakeoverAllowed=0,
        ARProperties_State=1,
        CMInitiatorActivityTimeoutFactor=1000,
        CMInitiatorUDPRTPort=0x8892,
        StationNameLength=10,
        CMInitiatorStationName=b"controller"
    )

    # Input IOCR - receive data from device
    iocr_input = IOCRBlockReq(
        IOCRType=0x0001,
        IOCRReference=0x0001,
        LT=0x8892,
        IOCRProperties=0x00000000,
        DataLength=6,  # 5 bytes data + 1 IOPS
        FrameID=INPUT_FRAME_ID,
        SendClockFactor=32,
        ReductionRatio=32,
        Phase=1,
        Sequence=0,
        FrameSendOffset=0xFFFFFFFF,
        WatchdogFactor=10,
        DataHoldFactor=10,
        IOCRTagHeader=0xC000,
        IOCRMulticastMACAdd="01:0e:cf:00:00:00"
    )

    # Output IOCR - send data to device
    iocr_output = IOCRBlockReq(
        IOCRType=0x0002,
        IOCRReference=0x0002,
        LT=0x8892,
        IOCRProperties=0x00000000,
        DataLength=4,
        FrameID=OUTPUT_FRAME_ID,
        SendClockFactor=32,
        ReductionRatio=32,
        Phase=1,
        Sequence=0,
        FrameSendOffset=0xFFFFFFFF,
        WatchdogFactor=10,
        DataHoldFactor=10,
        IOCRTagHeader=0xC000,
        IOCRMulticastMACAdd="01:0e:cf:00:00:00"
    )

    # Alarm CR
    alarm_cr = AlarmCRBlockReq(
        AlarmCRType=0x0001,
        LT=0x8892,
        AlarmCRProperties=0x00000000,
        RTATimeoutFactor=100,
        RTARetries=3,
        LocalAlarmReference=0x0001,
        MaxAlarmDataLength=128  # 128, not 200!
    )

    # Expected Submodules - DAP + CPU Temp
    exp_submod = ExpectedSubmoduleBlockReq(
        NumberOfAPIs=1,
        APIs=[{
            'API': 0,
            'SlotNumber': 0,
            'ModuleIdentNumber': MOD_DAP,
            'ModuleProperties': 0,
            'Submodules': [{
                'SubslotNumber': 1,
                'SubmoduleIdentNumber': SUBMOD_DAP,
                'SubmoduleProperties': 0,
                'DataDescription': []
            }]
        }, {
            'API': 0,
            'SlotNumber': 1,
            'ModuleIdentNumber': MOD_TEMP,
            'ModuleProperties': 0,
            'Submodules': [{
                'SubslotNumber': 1,
                'SubmoduleIdentNumber': SUBMOD_TEMP,
                'SubmoduleProperties': 0x0002,  # Input
                'DataDescription': [{
                    'DataDescription': 1,  # Input
                    'SubmoduleDataLength': 5,
                    'LengthIOCS': 1,
                    'LengthIOPS': 1
                }]
            }]
        }]
    )

    # Assemble PNIO service request
    pnio = PNIOServiceReqPDU(
        args_max=16384,
        blocks=[ar_block, iocr_input, iocr_output, alarm_cr, exp_submod]
    )

    # Wrap in DCE/RPC
    rpc = DceRpc4(
        type="request",
        flags1=0x20,
        opnum=OPNUM_CONNECT,
        if_id=PNIO_UUID,
        act_id=activity_uuid
    ) / pnio

    return bytes(rpc)


def build_control_request_scapy(ar_uuid: bytes, session_key: int,
                                 control_cmd: int, activity_uuid: bytes) -> bytes:
    """
    Build Control Request (PrmEnd or ApplicationReady) using Scapy.
    """
    if not SCAPY_RPC_AVAILABLE:
        raise RuntimeError("Scapy RPC modules not available")

    ctrl = IODControlReq(
        ARUUID=ar_uuid,
        SessionKey=session_key,
        ControlCommand=control_cmd
    )

    pnio = PNIOServiceReqPDU(args_max=16384, blocks=[ctrl])

    rpc = DceRpc4(
        type="request",
        flags1=0x20,
        opnum=OPNUM_CONTROL,
        if_id=PNIO_UUID,
        act_id=activity_uuid
    ) / pnio

    return bytes(rpc)


# =============================================================================
# LEGACY MANUAL PACKET BUILDING (COMMENTED OUT - USE SCAPY CLASSES ABOVE)
# =============================================================================
# def build_read_request(...):
#     """Build RPC Read Request - REPLACED BY Scapy IODReadReqPDU (not yet implemented)"""
#     pass
#
# def parse_read_response(...):
#     """Parse RPC Read Response - cyclic I/O now uses Layer 2 frames instead"""
#     pass
# =============================================================================

# =============================================================================
# LEGACY RESPONSE PARSER (COMMENTED OUT - REPLACED BY _parse_pnio_response)
# =============================================================================
# def parse_connect_response(data: bytes) -> Tuple[bool, bytes, str]:
#     """Parse Connect Response - REPLACED BY _parse_pnio_response method"""
#     pass
# =============================================================================


@dataclass
class SensorReading:
    slot: int
    value: float
    quality: int  # 0=good, 0x40=uncertain, 0x80=bad
    timestamp: float = field(default_factory=time.time)


@dataclass
class ARContext:
    """Application Relationship context for a connection"""
    ar_uuid: bytes = field(default_factory=lambda: b"")
    activity_uuid: bytes = field(default_factory=lambda: b"")
    session_key: int = 1
    seq_num: int = 0
    input_frame_id: int = INPUT_FRAME_ID
    output_frame_id: int = OUTPUT_FRAME_ID
    device_mac: bytes = field(default_factory=lambda: b"")


@dataclass
class RTUState:
    station_name: str
    ip_address: str
    mac_address: str = ""
    connected: bool = False
    state: str = "OFFLINE"  # OFFLINE, CONNECTING, CONNECTED, RUNNING, ERROR
    sensors: Dict[int, SensorReading] = field(default_factory=dict)
    last_update: float = 0.0
    error_message: str = ""
    ar_context: ARContext = field(default_factory=ARContext)


class PNController:
    """
    PROFINET IO Controller - runs as background task in FastAPI
    Implements full connection handshake and cyclic I/O
    """

    def __init__(self):
        self.rtus: Dict[str, RTUState] = {}
        self._running = False
        self._lock = threading.RLock()  # RLock for re-entrant calls
        self._task: Optional[asyncio.Task] = None
        self._io_thread: Optional[threading.Thread] = None
        self._local_mac = self._get_local_mac()

    def _get_local_mac(self) -> str:
        """Get local MAC address for controller (string format: 02:00:00:00:00:01)"""
        # Try to get real MAC from network interface using Scapy
        if SCAPY_RPC_AVAILABLE:
            try:
                # Try common interfaces
                for iface in ["eth0", "ens192", "enp0s3", "en0"]:
                    try:
                        mac = get_if_hwaddr(iface)
                        if mac and mac != "00:00:00:00:00:00":
                            logger.info(f"Using MAC {mac} from interface {iface}")
                            return mac
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"Could not get interface MAC: {e}")
        # Default controller MAC
        return "02:00:00:00:00:01"

    def _parse_pnio_response(self, data: bytes, operation: str) -> Tuple[bool, str]:
        """
        Parse PROFINET RPC response, check PNIO status.

        Based on pn_scapy_controller.py reference implementation.
        PNIO Status is at offset 80 (after 80-byte RPC header).

        Returns: (success, error_message)
        """
        if len(data) < 84:
            return False, f"Response too short ({len(data)} bytes)"

        # Check DCE/RPC packet type (offset 1)
        pkt_type = data[1]
        if pkt_type != 2:  # 2 = Response
            return False, f"Not a response packet (type={pkt_type})"

        # PNIO Status at offset 80 (4 bytes)
        status = data[80:84]
        logger.debug(f"[{operation}] PNIO Status: {status.hex()}")

        if status == b"\x00\x00\x00\x00":
            return True, ""
        else:
            # Parse error details
            code, decode, code1, code2 = status
            blocks = {
                1: "ARBlock", 2: "IOCRBlock", 3: "AlarmCRBlock",
                4: "ExpectedSubmod", 5: "IODControlBlock"
            }
            error_msg = f"Error in {blocks.get(code1, f'Block {code1}')}: decode=0x{decode:02x} err=0x{code2:02x}"
            return False, error_msg

    def start(self):
        """Start controller background task"""
        if self._running:
            return
        self._running = True
        logger.info("PROFINET Controller starting")

        # Start cyclic I/O thread
        self._io_thread = threading.Thread(target=self._cyclic_io_loop, daemon=True)
        self._io_thread.start()

    def stop(self):
        """Stop controller"""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("PROFINET Controller stopped")

    def add_rtu(self, station_name: str, ip_address: str, mac_address: str = "") -> bool:
        """Add RTU to manage"""
        with self._lock:
            if station_name in self.rtus:
                # Update IP and MAC if provided
                self.rtus[station_name].ip_address = ip_address
                if mac_address:
                    self.rtus[station_name].mac_address = mac_address
                return True
            self.rtus[station_name] = RTUState(
                station_name=station_name,
                ip_address=ip_address,
                mac_address=mac_address
            )
            logger.info(f"Added RTU: {station_name} at {ip_address} (MAC: {mac_address or 'unknown'})")
        return True

    def get_rtu_state(self, station_name: str) -> Optional[RTUState]:
        """Get RTU state"""
        with self._lock:
            return self.rtus.get(station_name)

    def get_all_rtus(self) -> List[RTUState]:
        """Get all RTU states"""
        with self._lock:
            return list(self.rtus.values())

    def get_sensor_value(self, station_name: str, slot: int) -> Optional[SensorReading]:
        """Get sensor reading from RTU"""
        with self._lock:
            rtu = self.rtus.get(station_name)
            if rtu:
                return rtu.sensors.get(slot)
        return None

    async def connect_rtu(self, station_name: str) -> bool:
        """
        Connect to RTU - Full PROFINET handshake:
        1. Connect Request -> Response
        2. PrmEnd Request -> Response
        3. ApplicationReady Request -> Response
        4. Start cyclic I/O
        """
        with self._lock:
            rtu = self.rtus.get(station_name)
            if not rtu:
                logger.error(f"RTU {station_name} not found")
                return False
            rtu.state = "CONNECTING"
            rtu.error_message = ""

        try:
            # Step 1: Connect Request
            logger.info(f"[{station_name}] Step 1: Sending Connect Request")
            success, ar_uuid, activity_uuid = await self._rpc_connect(rtu)
            if not success:
                raise Exception("Connect Request failed")

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
                raise Exception("PrmEnd failed")

            # Step 3: ApplicationReady
            logger.info(f"[{station_name}] Step 3: Sending ApplicationReady")
            success = await self._rpc_app_ready(rtu)
            if not success:
                raise Exception("ApplicationReady failed")

            with self._lock:
                rtu.state = "RUNNING"
                rtu.connected = True

            logger.info(f"[{station_name}] PROFINET connection established - RUNNING")

            # Step 4: Start Cyclic I/O (Scapy Layer 2)
            if CYCLIC_IO_AVAILABLE and rtu.mac_address:
                logger.info(f"[{station_name}] Step 4: Starting Cyclic I/O")
                cyclic_mgr = get_cyclic_io_manager()

                def on_sensor_data(data: bytes, timestamp: float):
                    """Callback when input data received from RTU"""
                    self._process_cyclic_input(station_name, data, timestamp)

                success = cyclic_mgr.start_cyclic_io(
                    station_name=station_name,
                    device_mac=rtu.mac_address,
                    device_ip=rtu.ip_address,
                    on_input_data=on_sensor_data
                )
                if success:
                    logger.info(f"[{station_name}] Cyclic I/O STARTED - Layer 2 RT frames active")
                else:
                    logger.warning(f"[{station_name}] Cyclic I/O failed to start - sensor data unavailable")
            elif not CYCLIC_IO_AVAILABLE:
                logger.warning(f"[{station_name}] Cyclic I/O not available (Scapy missing)")
            elif not rtu.mac_address:
                logger.warning(f"[{station_name}] No MAC address - cyclic I/O requires device MAC")

            return True

        except Exception as e:
            logger.error(f"[{station_name}] Connect failed: {e}")
            with self._lock:
                rtu.state = "ERROR"
                rtu.error_message = str(e)
                rtu.connected = False
            return False

    def _process_cyclic_input(self, station_name: str, data: bytes, timestamp: float):
        """
        Process input data received via cyclic I/O (Layer 2).

        Called by the cyclic I/O callback when PROFINET RT input frames arrive.

        Data format (from Water-Treat RTU):
        - Slot 1 (CPU Temp): 4-byte float (big-endian) + 1-byte IOPS
        """
        with self._lock:
            rtu = self.rtus.get(station_name)
            if not rtu:
                return

            # Parse input data - expect at least 5 bytes (4-byte float + 1-byte IOPS)
            if len(data) >= 5:
                # CPU Temperature (slot 1)
                try:
                    temp_value = struct.unpack(">f", data[0:4])[0]
                    iops = data[4]  # IO Provider Status

                    # Determine quality from IOPS
                    # Bit 7 (0x80) = Good
                    if iops & 0x80:
                        quality = QUALITY_GOOD
                    elif iops & 0x40:
                        quality = QUALITY_UNCERTAIN
                    else:
                        quality = QUALITY_BAD

                    # Update sensor reading
                    rtu.sensors[1] = SensorReading(
                        slot=1,
                        value=temp_value,
                        quality=quality,
                        timestamp=timestamp
                    )
                    rtu.last_update = timestamp

                    logger.debug(f"[{station_name}] Cyclic input: temp={temp_value:.2f}°C "
                                f"quality=0x{quality:02X}")
                except struct.error as e:
                    logger.warning(f"[{station_name}] Failed to parse sensor data: {e}")
            else:
                logger.debug(f"[{station_name}] Cyclic input too short: {len(data)} bytes")

    def disconnect_rtu(self, station_name: str) -> bool:
        """Disconnect from RTU - stop cyclic I/O and release AR."""
        with self._lock:
            rtu = self.rtus.get(station_name)
            if not rtu:
                return False

            # Stop cyclic I/O first
            if CYCLIC_IO_AVAILABLE:
                cyclic_mgr = get_cyclic_io_manager()
                cyclic_mgr.stop_cyclic_io(station_name)
                logger.info(f"[{station_name}] Cyclic I/O stopped")

            # Update state
            rtu.state = "OFFLINE"
            rtu.connected = False
            rtu.error_message = ""

            logger.info(f"[{station_name}] Disconnected")
            return True

    async def _rpc_connect(self, rtu: RTUState) -> Tuple[bool, bytes, bytes]:
        """Send RPC Connect Request using Scapy, return (success, ar_uuid, activity_uuid)"""
        if not SCAPY_RPC_AVAILABLE:
            logger.error(f"[{rtu.station_name}] Scapy RPC modules not available")
            return False, b"", b""

        ar_uuid = uuid4().bytes
        activity_uuid = uuid4().bytes
        rtu.ar_context.ar_uuid = ar_uuid
        rtu.ar_context.activity_uuid = activity_uuid

        # Build Connect Request using Scapy classes
        pkt = build_connect_request_scapy(
            ar_uuid=ar_uuid,
            session_key=rtu.ar_context.session_key,
            mac_str=self._local_mac,  # Format: "02:00:00:00:00:01"
            activity_uuid=activity_uuid
        )

        logger.info(f"[{rtu.station_name}] Connect Request (Scapy): {len(pkt)} bytes to {rtu.ip_address}:{RPC_PORT}")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: sock.sendto(pkt, (rtu.ip_address, RPC_PORT))
            )

            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: sock.recvfrom(4096)
            )
            data, addr = resp

            logger.info(f"[{rtu.station_name}] Connect Response: {len(data)} bytes")
            logger.debug(f"[{rtu.station_name}] Response hex: {data[:80].hex()}")

            # Parse response - check PNIO status at offset 80
            success, error = self._parse_pnio_response(data, "Connect")
            if success:
                logger.info(f"[{rtu.station_name}] Connect SUCCESS")
                return True, ar_uuid, activity_uuid
            else:
                logger.error(f"[{rtu.station_name}] Connect failed: {error}")
                return False, b"", b""

        except socket.timeout:
            logger.error(f"[{rtu.station_name}] Connect timeout")
            return False, b"", b""
        finally:
            sock.close()

    async def _rpc_prm_end(self, rtu: RTUState) -> bool:
        """Send PrmEnd (ParameterEnd) Control Request using Scapy"""
        if not SCAPY_RPC_AVAILABLE:
            logger.error(f"[{rtu.station_name}] Scapy RPC modules not available")
            return False

        rtu.ar_context.seq_num += 1

        # Build Control Request using Scapy classes
        pkt = build_control_request_scapy(
            ar_uuid=rtu.ar_context.ar_uuid,
            session_key=rtu.ar_context.session_key,
            control_cmd=CONTROL_PRM_END,
            activity_uuid=uuid4().bytes  # New activity UUID for this request
        )

        logger.info(f"[{rtu.station_name}] PrmEnd Request (Scapy): {len(pkt)} bytes")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: sock.sendto(pkt, (rtu.ip_address, RPC_PORT))
            )

            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: sock.recvfrom(4096)
            )
            data, addr = resp

            logger.info(f"[{rtu.station_name}] PrmEnd Response: {len(data)} bytes")

            # Parse response - check PNIO status
            success, error = self._parse_pnio_response(data, "PrmEnd")
            if success:
                logger.info(f"[{rtu.station_name}] PrmEnd SUCCESS")
                return True

            logger.error(f"[{rtu.station_name}] PrmEnd failed: {error}")
            return False

        except socket.timeout:
            logger.error(f"[{rtu.station_name}] PrmEnd timeout - connection failed")
            return False  # Timeout is a failure, don't mask it
        finally:
            sock.close()

    async def _rpc_app_ready(self, rtu: RTUState) -> bool:
        """Send ApplicationReady Control Request using Scapy"""
        if not SCAPY_RPC_AVAILABLE:
            logger.error(f"[{rtu.station_name}] Scapy RPC modules not available")
            return False

        rtu.ar_context.seq_num += 1

        # Build Control Request using Scapy classes
        pkt = build_control_request_scapy(
            ar_uuid=rtu.ar_context.ar_uuid,
            session_key=rtu.ar_context.session_key,
            control_cmd=CONTROL_APP_READY,
            activity_uuid=uuid4().bytes  # New activity UUID for this request
        )

        logger.info(f"[{rtu.station_name}] ApplicationReady Request (Scapy): {len(pkt)} bytes")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: sock.sendto(pkt, (rtu.ip_address, RPC_PORT))
            )

            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: sock.recvfrom(4096)
            )
            data, addr = resp

            logger.info(f"[{rtu.station_name}] ApplicationReady Response: {len(data)} bytes")

            # Parse response - check PNIO status
            success, error = self._parse_pnio_response(data, "ApplicationReady")
            if success:
                logger.info(f"[{rtu.station_name}] ApplicationReady SUCCESS")
                return True

            logger.error(f"[{rtu.station_name}] ApplicationReady failed: {error}")
            return False

        except socket.timeout:
            logger.error(f"[{rtu.station_name}] ApplicationReady timeout - connection failed")
            return False  # Timeout is a failure, don't mask it
        finally:
            sock.close()

    def _cyclic_io_loop(self):
        """
        Background thread for monitoring cyclic I/O status.

        IMPORTANT: Actual cyclic data exchange happens via Layer 2 PROFINET RT frames
        handled by pn_cyclic_io.py (Scapy-based). This thread monitors connection health
        and marks data as BAD if no updates are received within the watchdog period.
        """
        logger.info("Cyclic I/O watchdog thread started")
        watchdog_timeout = 5.0  # Mark data BAD if no update in 5 seconds

        while self._running:
            try:
                current_time = time.time()

                with self._lock:
                    running_rtus = [r for r in self.rtus.values() if r.state == "RUNNING"]

                for rtu in running_rtus:
                    # Check if we've received data recently (from Layer 2 cyclic I/O)
                    data_age = current_time - rtu.last_update if rtu.last_update > 0 else float('inf')

                    if data_age > watchdog_timeout and rtu.sensors:
                        # No data received within watchdog period - mark all as BAD
                        with self._lock:
                            for slot, reading in rtu.sensors.items():
                                if reading.quality != QUALITY_BAD:
                                    reading.quality = QUALITY_BAD
                                    logger.warning(f"[{rtu.station_name}] Slot {slot} quality set to BAD - "
                                                  f"no cyclic data for {data_age:.1f}s")

                time.sleep(1.0)  # Check every second

            except Exception as e:
                logger.error(f"Cyclic I/O watchdog error: {e}")
                time.sleep(1.0)

        logger.info("Cyclic I/O watchdog thread stopped")

    # =============================================================================
    # LEGACY RPC READ (COMMENTED OUT - REPLACED BY LAYER 2 CYCLIC I/O)
    # =============================================================================
    # The actual sensor data now flows via PROFINET RT Layer 2 frames, handled by
    # pn_cyclic_io.py. The callback _process_cyclic_input() receives data from
    # the Scapy-based frame sniffer.
    #
    # def _read_via_rpc(self, rtu: RTUState):
    #     """Read data via RPC Read - REPLACED BY Layer 2 cyclic I/O"""
    #     pass
    # =============================================================================

    # Placeholder for deleted code that referenced undefined functions:
    # - build_read_request (removed - was manual struct.pack)
    # - parse_read_response (removed - was manual parsing)
    # - INDEX_INPUT_DATA (removed - not used with Layer 2)
    # The actual data path is now:
    #   Layer 2 RT Frame -> pn_cyclic_io.py -> _process_cyclic_input() callback


# Singleton instance with thread-safe double-check locking
_controller: Optional[PNController] = None
_controller_lock = threading.Lock()


def get_controller() -> PNController:
    """Get or create controller instance (thread-safe)"""
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:  # Double-check after acquiring lock
                _controller = PNController()
    return _controller


def init_controller():
    """Initialize controller on startup"""
    ctrl = get_controller()
    ctrl.start()
    return ctrl


def shutdown_controller():
    """Shutdown controller"""
    global _controller
    if _controller:
        _controller.stop()
        _controller = None
