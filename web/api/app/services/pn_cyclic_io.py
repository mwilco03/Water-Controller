"""
PROFINET Cyclic I/O using Scapy - Layer 2 Real-Time Data Exchange

This module handles the cyclic I/O data exchange after PROFINET connection
is established. Uses Scapy for proper PROFINET RT frame generation.

CRITICAL: This is the missing piece - after RPC handshake (Connect, PrmEnd,
ApplicationReady), the actual sensor data flows via Layer 2 Ethernet frames,
NOT UDP.

Frame Structure:
- Ethertype: 0x8892 (PROFINET)
- FrameID: 0x8000 (Output CR - controller to device)
- FrameID: 0x8001 (Input CR - device to controller)
"""

import logging
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Try to import Scapy
try:
    from scapy.all import (
        Ether, Raw, conf, get_if_hwaddr, sendp, sniff, AsyncSniffer
    )
    from scapy.contrib.pnio import ProfinetIO
    SCAPY_AVAILABLE = True
    logger.info("Scapy PROFINET modules loaded successfully")
except ImportError as e:
    SCAPY_AVAILABLE = False
    logger.warning(f"Scapy not available: {e}. Cyclic I/O will not function.")

# PROFINET RT constants
PROFINET_ETHERTYPE = 0x8892
FRAME_ID_OUTPUT = 0x8000  # Controller -> Device (Output CR)
FRAME_ID_INPUT = 0x8001   # Device -> Controller (Input CR)

# Data quality
QUALITY_GOOD = 0x80       # IOPS/IOCS good
QUALITY_BAD = 0x00        # IOPS/IOCS bad


@dataclass
class CyclicIOConfig:
    """Configuration for cyclic I/O exchange."""
    interface: str = "eth0"
    cycle_time_ms: int = 32  # 32ms cycle time
    watchdog_factor: int = 10  # 320ms watchdog
    input_data_length: int = 5  # Bytes of input data (e.g., 4-byte float + 1 IOPS)
    output_data_length: int = 4  # Bytes of output data


@dataclass
class CyclicIOState:
    """Runtime state for cyclic I/O."""
    running: bool = False
    cycle_counter: int = 0
    last_input_time: float = 0.0
    last_output_time: float = 0.0
    input_data: bytes = b''
    output_data: bytes = b'\x00\x00\x00\x80'  # Default: 0 command + good status
    data_valid: bool = False
    error_count: int = 0


class ProfinetCyclicIO:
    """
    PROFINET Cyclic I/O Manager using Scapy.

    Handles Layer 2 real-time data exchange after connection is established.
    """

    def __init__(self, config: CyclicIOConfig | None = None):
        self.config = config or CyclicIOConfig()
        self._state = CyclicIOState()
        self._lock = threading.RLock()

        # Connection info (set when starting)
        self._controller_mac: str = ""
        self._device_mac: str = ""
        self._device_ip: str = ""
        self._station_name: str = ""

        # Threading
        self._output_thread: Optional[threading.Thread] = None
        self._sniffer: Optional[AsyncSniffer] = None
        self._stop_event = threading.Event()

        # Callback for sensor data updates
        self._on_input_data: Optional[Callable[[bytes, float], None]] = None

    def is_available(self) -> bool:
        """Check if Scapy is available for cyclic I/O."""
        return SCAPY_AVAILABLE

    def start(
        self,
        device_mac: str,
        device_ip: str,
        station_name: str,
        on_input_data: Optional[Callable[[bytes, float], None]] = None
    ) -> bool:
        """
        Start cyclic I/O exchange.

        Args:
            device_mac: RTU MAC address (e.g., "B8:27:EB:5F:4B:64")
            device_ip: RTU IP address (for logging)
            station_name: RTU station name
            on_input_data: Callback(data_bytes, timestamp) when input received

        Returns:
            True if started successfully.
        """
        if not SCAPY_AVAILABLE:
            logger.error("Cannot start cyclic I/O: Scapy not available")
            return False

        with self._lock:
            if self._state.running:
                logger.warning(f"Cyclic I/O already running for {station_name}")
                return True

            # Get controller MAC
            try:
                self._controller_mac = get_if_hwaddr(self.config.interface)
            except Exception as e:
                logger.error(f"Cannot get MAC for {self.config.interface}: {e}")
                return False

            self._device_mac = device_mac.lower()
            self._device_ip = device_ip
            self._station_name = station_name
            self._on_input_data = on_input_data

            self._stop_event.clear()
            self._state = CyclicIOState(running=True)

            # Start output frame sender thread
            self._output_thread = threading.Thread(
                target=self._output_loop,
                name=f"pn-output-{station_name}",
                daemon=True
            )
            self._output_thread.start()

            # Start input frame sniffer
            try:
                self._sniffer = AsyncSniffer(
                    iface=self.config.interface,
                    filter=f"ether proto 0x8892 and ether src {self._device_mac}",
                    prn=self._handle_input_frame,
                    store=False
                )
                self._sniffer.start()
            except Exception as e:
                logger.error(f"Cannot start sniffer: {e}")
                self._stop_event.set()
                self._state.running = False
                return False

            logger.info(f"[{station_name}] Cyclic I/O STARTED - "
                       f"Output: FrameID 0x{FRAME_ID_OUTPUT:04X}, "
                       f"Input: FrameID 0x{FRAME_ID_INPUT:04X}")
            return True

    def stop(self):
        """Stop cyclic I/O exchange."""
        with self._lock:
            if not self._state.running:
                return

            logger.info(f"[{self._station_name}] Stopping cyclic I/O...")
            self._stop_event.set()
            self._state.running = False

            # Stop sniffer
            if self._sniffer:
                try:
                    self._sniffer.stop()
                except Exception:
                    pass
                self._sniffer = None

            # Wait for output thread
            if self._output_thread:
                self._output_thread.join(timeout=2.0)
                self._output_thread = None

            logger.info(f"[{self._station_name}] Cyclic I/O stopped")

    def set_output_data(self, data: bytes):
        """Set output data to send to device."""
        with self._lock:
            self._state.output_data = data

    def get_input_data(self) -> tuple[bytes, float, bool]:
        """
        Get latest input data from device.

        Returns:
            (data_bytes, timestamp, is_valid)
        """
        with self._lock:
            return (
                self._state.input_data,
                self._state.last_input_time,
                self._state.data_valid
            )

    def get_stats(self) -> dict:
        """Get cyclic I/O statistics."""
        with self._lock:
            return {
                "running": self._state.running,
                "cycle_counter": self._state.cycle_counter,
                "last_input_time": self._state.last_input_time,
                "last_output_time": self._state.last_output_time,
                "data_valid": self._state.data_valid,
                "error_count": self._state.error_count,
            }

    def _output_loop(self):
        """Send output frames at configured cycle time."""
        logger.info(f"[{self._station_name}] Output loop started "
                   f"(cycle={self.config.cycle_time_ms}ms)")

        cycle_time_sec = self.config.cycle_time_ms / 1000.0

        while not self._stop_event.is_set():
            try:
                self._send_output_frame()
                time.sleep(cycle_time_sec)
            except Exception as e:
                logger.error(f"[{self._station_name}] Output frame error: {e}")
                with self._lock:
                    self._state.error_count += 1
                time.sleep(0.1)  # Back off on error

        logger.info(f"[{self._station_name}] Output loop stopped")

    def _send_output_frame(self):
        """Build and send a PROFINET RT output frame."""
        with self._lock:
            cycle_counter = self._state.cycle_counter
            output_data = self._state.output_data
            self._state.cycle_counter = (cycle_counter + 1) & 0xFFFF

        # Build PROFINET RT frame
        # Structure: Ether / ProfinetIO / CycleCounter(2) / DataStatus(1) / TransferStatus(1) / Data

        # PROFINET RT frame payload
        # CycleCounter: 2 bytes (big-endian)
        # DataStatus: 1 byte (0x35 = valid, run, station ok, provider ok)
        # TransferStatus: 1 byte (0x00)
        # Then I/O data + IOPS

        data_status = 0x35  # State=Run, StationProblem=0, ProviderState=Run
        transfer_status = 0x00

        rt_payload = struct.pack(">H", cycle_counter)  # CycleCounter
        rt_payload += struct.pack("B", data_status)     # DataStatus
        rt_payload += struct.pack("B", transfer_status) # TransferStatus
        rt_payload += output_data                        # I/O Data + IOCS

        # Build frame using Scapy
        frame = (
            Ether(dst=self._device_mac, src=self._controller_mac, type=PROFINET_ETHERTYPE) /
            ProfinetIO(frameID=FRAME_ID_OUTPUT) /
            Raw(load=rt_payload)
        )

        # Send frame
        sendp(frame, iface=self.config.interface, verbose=False)

        with self._lock:
            self._state.last_output_time = time.time()

        logger.debug(f"[{self._station_name}] TX Output frame cycle={cycle_counter}")

    def _handle_input_frame(self, pkt):
        """Process received PROFINET RT input frame."""
        try:
            # Check for ProfinetIO layer
            if ProfinetIO not in pkt:
                return

            frame_id = pkt[ProfinetIO].frameID

            # Only process Input CR frames
            if frame_id != FRAME_ID_INPUT:
                return

            # Get raw payload after ProfinetIO header
            if Raw not in pkt:
                return

            raw_data = bytes(pkt[Raw].load)

            if len(raw_data) < 4:
                return

            # Parse RT frame
            # CycleCounter(2) + DataStatus(1) + TransferStatus(1) + I/O Data
            cycle_counter = struct.unpack(">H", raw_data[0:2])[0]
            data_status = raw_data[2]
            transfer_status = raw_data[3]
            io_data = raw_data[4:]  # Remaining is I/O data + IOPS

            # Check data validity
            # DataStatus bit 2 (0x04) = ProviderState (1=Run)
            # DataStatus bit 4 (0x10) = StationProblemIndicator (0=OK)
            data_valid = (data_status & 0x04) and not (data_status & 0x10)

            timestamp = time.time()

            with self._lock:
                self._state.input_data = io_data
                self._state.last_input_time = timestamp
                self._state.data_valid = data_valid

            logger.debug(f"[{self._station_name}] RX Input frame "
                        f"cycle={cycle_counter} status=0x{data_status:02X} "
                        f"data={io_data.hex()}")

            # Invoke callback
            if self._on_input_data:
                self._on_input_data(io_data, timestamp)

        except Exception as e:
            logger.error(f"[{self._station_name}] Input frame parse error: {e}")
            with self._lock:
                self._state.error_count += 1


# Singleton manager for multiple RTU connections
class CyclicIOManager:
    """Manages cyclic I/O for multiple RTU connections."""

    _instance: Optional['CyclicIOManager'] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._ios: Dict[str, ProfinetCyclicIO] = {}
                cls._instance._config = CyclicIOConfig()
            return cls._instance

    def configure(self, interface: str = "eth0", cycle_time_ms: int = 32):
        """Configure default settings for new connections."""
        self._config = CyclicIOConfig(
            interface=interface,
            cycle_time_ms=cycle_time_ms
        )

    def start_cyclic_io(
        self,
        station_name: str,
        device_mac: str,
        device_ip: str,
        on_input_data: Optional[Callable[[bytes, float], None]] = None
    ) -> bool:
        """Start cyclic I/O for an RTU."""
        with self._lock:
            if station_name in self._ios:
                # Already exists, check if running
                io = self._ios[station_name]
                if io._state.running:
                    return True

            # Create new cyclic I/O handler
            io = ProfinetCyclicIO(self._config)
            success = io.start(device_mac, device_ip, station_name, on_input_data)

            if success:
                self._ios[station_name] = io

            return success

    def stop_cyclic_io(self, station_name: str):
        """Stop cyclic I/O for an RTU."""
        with self._lock:
            io = self._ios.pop(station_name, None)
            if io:
                io.stop()

    def stop_all(self):
        """Stop all cyclic I/O."""
        with self._lock:
            for station_name in list(self._ios.keys()):
                self._ios[station_name].stop()
            self._ios.clear()

    def get_input_data(self, station_name: str) -> tuple[bytes, float, bool]:
        """Get input data for an RTU."""
        with self._lock:
            io = self._ios.get(station_name)
            if io:
                return io.get_input_data()
            return b'', 0.0, False

    def set_output_data(self, station_name: str, data: bytes):
        """Set output data for an RTU."""
        with self._lock:
            io = self._ios.get(station_name)
            if io:
                io.set_output_data(data)

    def get_stats(self, station_name: str) -> dict:
        """Get stats for an RTU's cyclic I/O."""
        with self._lock:
            io = self._ios.get(station_name)
            if io:
                return io.get_stats()
            return {"running": False}

    def is_available(self) -> bool:
        """Check if Scapy is available."""
        return SCAPY_AVAILABLE


def get_cyclic_io_manager() -> CyclicIOManager:
    """Get the singleton cyclic I/O manager."""
    return CyclicIOManager()
