"""
PROFINET Resilience and Adaptive Connection Module

Implements error tolerance, automatic parameter adjustment, and
format fallback strategies for robust PROFINET connections.

Design principles:
1. Parse errors and extract actionable feedback
2. Maintain multiple connection strategies
3. Automatically adjust parameters based on device responses
4. Learn from failures to improve success rate
"""

import struct
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List, Dict, Callable, Any, Tuple, TYPE_CHECKING
from copy import deepcopy

logger = logging.getLogger(__name__)


# ============================================================================
# PNIO Error Codes (IEC 61158-6-10)
# ============================================================================

class PNIOErrorDecode(Enum):
    """Error decode byte values."""
    PNIORW = 0x80        # Read/Write error
    PNIOCM = 0x81        # Connection Manager error
    PNIO = 0x82          # General PNIO error


class PNIOCMErrorCode1(Enum):
    """Connection Manager error code 1 (block identification)."""
    CONNECT = 0x00       # General connect error
    AR_BLOCK = 0x01      # ARBlockReq error
    IOCR_BLOCK = 0x02    # IOCRBlockReq error
    ALARM_CR_BLOCK = 0x03  # AlarmCRBlockReq error
    EXPECTED_SUBMOD = 0x04  # ExpectedSubmoduleBlockReq error
    PRM_SERVER = 0x05    # PRMServerBlockReq error
    MCR_BLOCK = 0x06     # MCRBlockReq error
    AR_RPC_BLOCK = 0x07  # ARRPCBlockReq error
    IR_INFO_BLOCK = 0x08 # IRInfoBlock error


class IOCRErrorCode2(Enum):
    """IOCR block specific error codes."""
    IOCR_TYPE = 0x00
    LT_FIELD = 0x01
    RT_CLASS = 0x02
    RESERVED = 0x03
    CSDU_LENGTH = 0x04
    FRAME_ID = 0x05
    SEND_CLOCK = 0x06
    REDUCTION = 0x07
    PHASE = 0x08
    SEQUENCE = 0x09
    DATA_LENGTH = 0x0A
    FRAME_OFFSET = 0x0B
    WATCHDOG = 0x0C
    DATA_HOLD = 0x0D
    TAG_HEADER = 0x0E
    MULTICAST_MAC = 0x0F
    API_COUNT = 0x10


class AlarmCRErrorCode2(Enum):
    """AlarmCR block specific error codes."""
    ALARM_TYPE = 0x00
    BLOCK_LENGTH = 0x01
    LT_FIELD = 0x02
    PROPERTIES = 0x03
    RTA_TIMEOUT = 0x04
    RTA_RETRIES = 0x05
    LOCAL_ALARM_REF = 0x06
    MAX_ALARM_DATA_LEN = 0x07
    TAG_HEADER_HIGH = 0x08
    TAG_HEADER_LOW = 0x09


class ExpectedSubmodErrorCode2(Enum):
    """ExpectedSubmodule block specific error codes."""
    BLOCK_LENGTH = 0x00
    API_COUNT = 0x01
    SLOT_NUMBER = 0x02
    MODULE_IDENT = 0x03
    SUBMODULE_IDENT = 0x04
    DATA_DESCRIPTION = 0x05


# ============================================================================
# Connection Strategy Configuration
# ============================================================================

class FormatVariant(Enum):
    """Wire format variants to try."""
    SCAPY_SPEC = auto()       # Scapy's spec-compliant format
    C_COMPATIBLE = auto()      # Match C implementation exactly
    MINIMAL = auto()           # Minimal configuration


@dataclass
class IOCRParams:
    """IOCR block parameters that can be adjusted."""
    frame_send_offset: int = 0          # 0 or 0xFFFFFFFF
    data_hold_factor: int = 3           # 3 (C) or 10 (spec default)
    watchdog_factor: int = 10
    tag_header: int = 0                 # 0 (C) or priority-encoded
    multicast_mac: str = "00:00:00:00:00:00"
    send_clock_factor: int = 32
    reduction_ratio: int = 32
    phase: int = 1


@dataclass
class AlarmCRParams:
    """AlarmCR block parameters that can be adjusted."""
    rta_timeout_factor: int = 100
    rta_retries: int = 3
    max_alarm_data_length: int = 200
    tag_header_high: int = 0xC000
    tag_header_low: int = 0xA000
    include_tag_headers: bool = True    # Some devices may not expect these


@dataclass
class ExpectedSubmodParams:
    """ExpectedSubmodule block parameters."""
    format: FormatVariant = FormatVariant.SCAPY_SPEC
    include_data_description_type: bool = True  # Spec has type, C doesn't


@dataclass
class ConnectionStrategy:
    """
    Complete connection strategy with all adjustable parameters.

    Each strategy variant represents a different approach to connecting
    to a device. If one fails, we try the next.
    """
    name: str
    description: str
    iocr: IOCRParams = field(default_factory=IOCRParams)
    alarm_cr: AlarmCRParams = field(default_factory=AlarmCRParams)
    expected_submod: ExpectedSubmodParams = field(default_factory=ExpectedSubmodParams)

    # Connection-level settings
    activity_timeout_factor: int = 1000
    session_key_start: int = 1

    # Retry behavior
    max_retries: int = 3
    retry_delay_ms: int = 1000

    def clone(self, name: str = None) -> 'ConnectionStrategy':
        """Create a modified copy of this strategy."""
        new_strategy = deepcopy(self)
        if name:
            new_strategy.name = name
        return new_strategy


# Pre-defined strategies
STRATEGY_SPEC_COMPLIANT = ConnectionStrategy(
    name="spec_compliant",
    description="Standard PROFINET spec-compliant format",
    iocr=IOCRParams(
        frame_send_offset=0xFFFFFFFF,  # Spec: device calculates
        data_hold_factor=3,
        tag_header=0,
        multicast_mac="00:00:00:00:00:00"
    ),
    alarm_cr=AlarmCRParams(include_tag_headers=True),
    expected_submod=ExpectedSubmodParams(
        format=FormatVariant.SCAPY_SPEC,
        include_data_description_type=True
    )
)

STRATEGY_C_COMPATIBLE = ConnectionStrategy(
    name="c_compatible",
    description="Match C implementation wire format",
    iocr=IOCRParams(
        frame_send_offset=0,           # C uses 0
        data_hold_factor=3,
        tag_header=0,
        multicast_mac="00:00:00:00:00:00"
    ),
    alarm_cr=AlarmCRParams(include_tag_headers=True),
    expected_submod=ExpectedSubmodParams(
        format=FormatVariant.C_COMPATIBLE,
        include_data_description_type=False  # C doesn't include type field
    )
)

STRATEGY_MINIMAL = ConnectionStrategy(
    name="minimal",
    description="Minimal configuration for compatibility",
    iocr=IOCRParams(
        frame_send_offset=0,
        data_hold_factor=3,
        watchdog_factor=3,
        tag_header=0,
        multicast_mac="00:00:00:00:00:00"
    ),
    alarm_cr=AlarmCRParams(
        include_tag_headers=False,  # Try without
        max_alarm_data_length=128
    ),
    expected_submod=ExpectedSubmodParams(
        format=FormatVariant.SCAPY_SPEC,
        include_data_description_type=True
    )
)

# Ordered list of strategies to try
DEFAULT_STRATEGY_ORDER = [
    STRATEGY_SPEC_COMPLIANT,
    STRATEGY_C_COMPATIBLE,
    STRATEGY_MINIMAL,
]


# ============================================================================
# Error Analysis and Correction
# ============================================================================

@dataclass
class ErrorAnalysis:
    """Result of analyzing a PNIO error response."""
    error_decode: int
    error_code1: int
    error_code2: int

    block_name: str = "Unknown"
    field_name: str = "Unknown"
    description: str = "Unknown error"

    suggested_fix: Optional[str] = None
    parameter_adjustment: Optional[Dict[str, Any]] = None
    should_retry: bool = True
    try_different_strategy: bool = False


class ErrorAnalyzer:
    """
    Analyzes PNIO error responses and suggests corrections.

    This is the core of the resilience system - it parses device
    error responses and returns actionable feedback.
    """

    # Maps (error_code1, error_code2) to (description, fix, parameter_adjustment)
    ERROR_MAP: Dict[Tuple[int, int], Tuple[str, str, Optional[Dict]]] = {
        # IOCR errors
        (0x02, 0x00): ("Invalid IOCR type", "Check IOCRType value", None),
        (0x02, 0x01): ("Invalid LT field", "Set LT to 0x8892", {"iocr.lt": 0x8892}),
        (0x02, 0x02): ("Invalid RT class", "Use RT_CLASS_1", {"iocr.rt_class": 1}),
        (0x02, 0x04): ("C_SDU length error", "Adjust DataLength", None),
        (0x02, 0x05): ("Invalid frame ID", "Check FrameID range", None),
        (0x02, 0x06): ("Invalid send clock factor", "Try 32", {"iocr.send_clock_factor": 32}),
        (0x02, 0x07): ("Invalid reduction ratio", "Try 32", {"iocr.reduction_ratio": 32}),
        (0x02, 0x08): ("Invalid phase", "Phase must be >= 1", {"iocr.phase": 1}),
        (0x02, 0x0B): ("Invalid frame send offset", "Try 0 instead of 0xFFFFFFFF", {"iocr.frame_send_offset": 0}),
        (0x02, 0x0C): ("Invalid watchdog factor", "Try 10", {"iocr.watchdog_factor": 10}),
        (0x02, 0x0D): ("Invalid data hold factor", "Try 3", {"iocr.data_hold_factor": 3}),
        (0x02, 0x0E): ("Invalid tag header", "Set to 0", {"iocr.tag_header": 0}),
        (0x02, 0x0F): ("Invalid multicast MAC", "Use zeros", {"iocr.multicast_mac": "00:00:00:00:00:00"}),

        # AlarmCR errors
        (0x03, 0x00): ("Invalid AlarmCR type", "Use type 1", None),
        (0x03, 0x01): ("Invalid block length", "Check TagHeader inclusion", {"alarm_cr.include_tag_headers": True}),
        (0x03, 0x07): ("Invalid max alarm data length", "Try 200", {"alarm_cr.max_alarm_data_length": 200}),
        (0x03, 0x08): ("Invalid tag header high", "Use 0xC000", {"alarm_cr.tag_header_high": 0xC000}),
        (0x03, 0x09): ("Invalid tag header low", "Use 0xA000", {"alarm_cr.tag_header_low": 0xA000}),

        # ExpectedSubmodule errors
        (0x04, 0x00): ("Invalid block length", "Try different format", None),
        (0x04, 0x02): ("Invalid slot number", "Check slot configuration", None),
        (0x04, 0x03): ("Module ident mismatch", "Check GSDML module IDs", None),
        (0x04, 0x04): ("Submodule ident mismatch", "Check GSDML submodule IDs", None),
        (0x04, 0x05): ("Invalid data description", "Try without type field", {"expected_submod.include_data_description_type": False}),

        # AR errors
        (0x01, 0x00): ("AR type error", "Use IOCAR type 1", None),
        (0x01, 0x05): ("Station name not found", "Check station name matches device", None),
    }

    BLOCK_NAMES = {
        0x00: "Connect",
        0x01: "ARBlockReq",
        0x02: "IOCRBlockReq",
        0x03: "AlarmCRBlockReq",
        0x04: "ExpectedSubmoduleBlockReq",
        0x05: "PRMServerBlockReq",
    }

    @classmethod
    def analyze(cls, error_decode: int, error_code1: int, error_code2: int) -> ErrorAnalysis:
        """
        Analyze error codes and return actionable feedback.

        Args:
            error_decode: PNIO error decode byte (0x80=RW, 0x81=CM, 0x82=PNIO)
            error_code1: Block identification or general error type
            error_code2: Specific error within the block

        Returns:
            ErrorAnalysis with description and suggested fixes
        """
        analysis = ErrorAnalysis(
            error_decode=error_decode,
            error_code1=error_code1,
            error_code2=error_code2,
            block_name=cls.BLOCK_NAMES.get(error_code1, f"Block 0x{error_code1:02X}"),
        )

        # Look up specific error
        key = (error_code1, error_code2)
        if key in cls.ERROR_MAP:
            desc, fix, params = cls.ERROR_MAP[key]
            analysis.description = desc
            analysis.suggested_fix = fix
            analysis.parameter_adjustment = params
            analysis.should_retry = params is not None
        else:
            analysis.description = f"Unknown error in {analysis.block_name}"
            analysis.suggested_fix = "Try different connection strategy"
            analysis.try_different_strategy = True

        logger.info(
            f"Error analysis: {analysis.block_name} - {analysis.description} "
            f"(decode=0x{error_decode:02X}, code1=0x{error_code1:02X}, code2=0x{error_code2:02X})"
        )
        if analysis.suggested_fix:
            logger.info(f"Suggested fix: {analysis.suggested_fix}")

        return analysis

    @classmethod
    def analyze_from_response(cls, response_bytes: bytes) -> Optional[ErrorAnalysis]:
        """
        Parse error from raw PNIO response bytes.

        The PNIO status is the first 4 bytes after the NDR header:
        - ErrorCode (1 byte)
        - ErrorDecode (1 byte)
        - ErrorCode1 (1 byte)
        - ErrorCode2 (1 byte)
        """
        # Skip RPC header (80 bytes) to get to PNIO status
        if len(response_bytes) < 84:
            return None

        # PNIO Status starts at offset 80
        error_code = response_bytes[80]
        error_decode = response_bytes[81]
        error_code1 = response_bytes[82]
        error_code2 = response_bytes[83]

        if error_code == 0 and error_decode == 0:
            return None  # No error

        return cls.analyze(error_decode, error_code1, error_code2)


# ============================================================================
# Adaptive Connector
# ============================================================================

@dataclass
class ConnectionAttempt:
    """Record of a connection attempt."""
    strategy_name: str
    success: bool
    error_analysis: Optional[ErrorAnalysis] = None
    response_time_ms: float = 0
    packet_size: int = 0


class AdaptiveConnector:
    """
    Manages adaptive connection attempts with automatic parameter adjustment.

    Usage:
        connector = AdaptiveConnector()

        for strategy in connector.iterate_strategies():
            result = attempt_connection(strategy)
            if connector.process_result(result):
                break  # Success!
    """

    def __init__(self, strategies: List[ConnectionStrategy] = None):
        self.strategies = strategies or DEFAULT_STRATEGY_ORDER.copy()
        self.current_index = 0
        self.attempts: List[ConnectionAttempt] = []
        self.successful_strategy: Optional[ConnectionStrategy] = None

        # Learning: track what works
        self._working_params: Dict[str, Any] = {}
        self._failed_params: Dict[str, Any] = {}

    def reset(self):
        """Reset for a new connection sequence."""
        self.current_index = 0
        self.attempts = []
        self.successful_strategy = None

    def get_current_strategy(self) -> Optional[ConnectionStrategy]:
        """Get the current strategy to try."""
        if self.current_index < len(self.strategies):
            return self.strategies[self.current_index]
        return None

    def iterate_strategies(self):
        """Iterate through strategies, yielding each one to try."""
        while self.current_index < len(self.strategies):
            yield self.strategies[self.current_index]
            self.current_index += 1

    def process_result(
        self,
        success: bool,
        error_analysis: Optional[ErrorAnalysis] = None,
        response_time_ms: float = 0
    ) -> bool:
        """
        Process the result of a connection attempt.

        Returns True if we should stop trying (success or exhausted options).
        """
        current = self.get_current_strategy()
        if current is None:
            return True

        attempt = ConnectionAttempt(
            strategy_name=current.name,
            success=success,
            error_analysis=error_analysis,
            response_time_ms=response_time_ms
        )
        self.attempts.append(attempt)

        if success:
            self.successful_strategy = current
            self._record_success(current)
            logger.info(f"Connection successful with strategy: {current.name}")
            return True

        # Learn from failure
        if error_analysis and error_analysis.parameter_adjustment:
            self._apply_adjustment(error_analysis.parameter_adjustment)

        if error_analysis and error_analysis.try_different_strategy:
            self.current_index += 1

        return False

    def _record_success(self, strategy: ConnectionStrategy):
        """Record successful parameters for future use."""
        self._working_params.update({
            'frame_send_offset': strategy.iocr.frame_send_offset,
            'data_hold_factor': strategy.iocr.data_hold_factor,
            'tag_header': strategy.iocr.tag_header,
            'include_alarm_tag_headers': strategy.alarm_cr.include_tag_headers,
            'expected_submod_format': strategy.expected_submod.format.name,
        })
        logger.info(f"Recorded working parameters: {self._working_params}")

    def _apply_adjustment(self, adjustments: Dict[str, Any]):
        """Apply parameter adjustments to remaining strategies."""
        for strategy in self.strategies[self.current_index:]:
            for key, value in adjustments.items():
                parts = key.split('.')
                if len(parts) == 2:
                    obj_name, attr_name = parts
                    obj = getattr(strategy, obj_name, None)
                    if obj and hasattr(obj, attr_name):
                        setattr(obj, attr_name, value)
                        logger.debug(f"Adjusted {strategy.name}.{key} = {value}")

    def get_diagnostic_report(self) -> str:
        """Generate a diagnostic report of all attempts."""
        lines = ["=== Connection Diagnostic Report ===", ""]

        for i, attempt in enumerate(self.attempts, 1):
            lines.append(f"Attempt {i}: {attempt.strategy_name}")
            lines.append(f"  Success: {attempt.success}")
            if attempt.error_analysis:
                ea = attempt.error_analysis
                lines.append(f"  Error: {ea.block_name} - {ea.description}")
                if ea.suggested_fix:
                    lines.append(f"  Fix: {ea.suggested_fix}")
            lines.append("")

        if self.successful_strategy:
            lines.append(f"Final: Connected with '{self.successful_strategy.name}'")
        else:
            lines.append("Final: All strategies exhausted, connection failed")

        if self._working_params:
            lines.append("")
            lines.append("Working parameters:")
            for k, v in self._working_params.items():
                lines.append(f"  {k}: {v}")

        return "\n".join(lines)


# ============================================================================
# Response Parser
# ============================================================================

class PNIOResponseParser:
    """
    Parse PNIO RPC responses and extract status/error information.
    """

    RPC_HEADER_SIZE = 80

    @classmethod
    def parse_connect_response(cls, data: bytes) -> Dict[str, Any]:
        """
        Parse a Connect Response and return structured result.

        Returns dict with:
            - success: bool
            - error_code, error_decode, error_code1, error_code2 (if error)
            - ar_uuid, session_key, device_mac, device_port (if success)
            - frame_ids: list of (iocr_ref, frame_id) tuples
        """
        result = {
            'success': False,
            'raw_length': len(data),
        }

        if len(data) < cls.RPC_HEADER_SIZE + 4:
            result['error'] = "Response too short"
            return result

        # Check RPC packet type (offset 1)
        ptype = data[1]
        if ptype == 0x03:  # Fault
            result['error'] = "RPC Fault response"
            return result

        if ptype != 0x02:  # Not Response
            result['error'] = f"Unexpected RPC packet type: {ptype}"
            return result

        # Parse PNIO status (first 4 bytes after RPC header)
        pos = cls.RPC_HEADER_SIZE
        result['error_code'] = data[pos]
        result['error_decode'] = data[pos + 1]
        result['error_code1'] = data[pos + 2]
        result['error_code2'] = data[pos + 3]

        # Check for PNIO-CM error
        if result['error_decode'] == 0x81:  # PNIOCM
            result['error'] = "PNIO-CM error"
            return result

        if result['error_code'] != 0:
            result['error'] = f"PNIO error code: {result['error_code']}"
            return result

        # Success - parse NDR header and blocks
        result['success'] = True
        result['frame_ids'] = []

        # Skip PNIO status and parse NDR header
        pos += 4  # Skip PNIO status
        if pos + 20 > len(data):
            return result

        # NDR: ArgsMax(4) + ArgsLen(4) + MaxCount(4) + Offset(4) + ActualCount(4)
        args_len = struct.unpack_from("<I", data, pos + 4)[0]
        pos += 20

        # Parse blocks
        end_pos = pos + args_len
        while pos + 6 <= end_pos and pos + 6 <= len(data):
            block_type = struct.unpack_from(">H", data, pos)[0]
            block_len = struct.unpack_from(">H", data, pos + 2)[0]

            if block_type == 0x8101:  # ARBlockRes
                # Skip to AR UUID (after type, length, version)
                ar_pos = pos + 6 + 2  # +2 for AR type
                if ar_pos + 16 <= len(data):
                    result['ar_uuid'] = data[ar_pos:ar_pos+16]
                    ar_pos += 16
                    if ar_pos + 2 <= len(data):
                        result['session_key'] = struct.unpack_from(">H", data, ar_pos)[0]
                    ar_pos += 2
                    if ar_pos + 6 <= len(data):
                        result['device_mac'] = ':'.join(f'{b:02x}' for b in data[ar_pos:ar_pos+6])
                    ar_pos += 6
                    if ar_pos + 2 <= len(data):
                        result['device_port'] = struct.unpack_from(">H", data, ar_pos)[0]

            elif block_type == 0x8102:  # IOCRBlockRes
                iocr_pos = pos + 6 + 2  # Skip header + IOCR type
                if iocr_pos + 4 <= len(data):
                    iocr_ref = struct.unpack_from(">H", data, iocr_pos)[0]
                    frame_id = struct.unpack_from(">H", data, iocr_pos + 2)[0]
                    result['frame_ids'].append((iocr_ref, frame_id))

            # Move to next block (aligned to 4 bytes)
            pos += 4 + block_len
            while pos % 4 != 0:
                pos += 1

        return result


# ============================================================================
# High-Level Resilient Connect Function
# ============================================================================

def create_resilient_connector(
    custom_strategies: List[ConnectionStrategy] = None,
    max_total_attempts: int = 10
) -> AdaptiveConnector:
    """
    Create an AdaptiveConnector with default or custom strategies.

    Args:
        custom_strategies: Optional list of strategies to try
        max_total_attempts: Maximum total connection attempts

    Returns:
        Configured AdaptiveConnector
    """
    strategies = custom_strategies or DEFAULT_STRATEGY_ORDER.copy()
    connector = AdaptiveConnector(strategies)
    return connector


# ============================================================================
# GSDML Parsing
# ============================================================================

@dataclass
class GsdmlModule:
    """Parsed module information from GSDML."""
    module_id: str
    module_ident_number: int
    name: str
    submodules: List['GsdmlSubmodule'] = field(default_factory=list)
    is_input: bool = False
    is_output: bool = False
    input_length: int = 0
    output_length: int = 0


@dataclass
class GsdmlSubmodule:
    """Parsed submodule information from GSDML."""
    submodule_id: str
    submodule_ident_number: int
    name: str
    input_length: int = 0
    output_length: int = 0


@dataclass
class GsdmlDeviceInfo:
    """Complete parsed GSDML device information."""
    vendor_id: int
    device_id: int
    vendor_name: str
    device_name: str
    min_device_interval: int
    max_input_length: int
    max_output_length: int
    modules: List[GsdmlModule] = field(default_factory=list)
    dap_module_ident: int = 0x00000001
    dap_submodule_ident: int = 0x00000001


def _parse_hex_int(value: str) -> int:
    """Parse hex string (0x...) or decimal string to int."""
    if value is None:
        return 0
    value = value.strip()
    if value.startswith('0x') or value.startswith('0X'):
        return int(value, 16)
    return int(value)


def _calculate_io_length(io_data_element) -> Tuple[int, int]:
    """
    Calculate input and output lengths from IOData element.

    Returns (input_length, output_length) in bytes.
    """
    input_len = 0
    output_len = 0

    if io_data_element is None:
        return input_len, output_len

    # Find Input and Output elements
    for child in io_data_element:
        tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag

        if tag_name == 'Input':
            # Sum up all DataItem lengths
            for data_item in child:
                item_tag = data_item.tag.split('}')[-1] if '}' in data_item.tag else data_item.tag
                if item_tag == 'DataItem':
                    data_type = data_item.get('DataType', '')
                    input_len += _get_data_type_size(data_type)

        elif tag_name == 'Output':
            for data_item in child:
                item_tag = data_item.tag.split('}')[-1] if '}' in data_item.tag else data_item.tag
                if item_tag == 'DataItem':
                    data_type = data_item.get('DataType', '')
                    output_len += _get_data_type_size(data_type)

    return input_len, output_len


def _get_data_type_size(data_type: str) -> int:
    """Get size in bytes for a GSDML data type."""
    type_sizes = {
        'Boolean': 1,
        'Integer8': 1,
        'Integer16': 2,
        'Integer32': 4,
        'Integer64': 8,
        'Unsigned8': 1,
        'Unsigned16': 2,
        'Unsigned32': 4,
        'Unsigned64': 8,
        'Float32': 4,
        'Float64': 8,
        'OctetString': 1,  # Per-character
        'VisibleString': 1,  # Per-character
    }
    return type_sizes.get(data_type, 1)


def parse_gsdml_file(gsdml_path: str) -> Optional[GsdmlDeviceInfo]:
    """
    Parse a GSDML XML file and extract device/module information.

    GSDML (General Station Description Markup Language) files describe
    PROFINET devices according to IEC 61158/61784.

    Args:
        gsdml_path: Path to the GSDML XML file

    Returns:
        GsdmlDeviceInfo with parsed module identifiers, or None on failure
    """
    import xml.etree.ElementTree as ET
    from pathlib import Path

    path = Path(gsdml_path)
    if not path.exists():
        logger.warning(f"GSDML file not found: {gsdml_path}")
        return None

    try:
        tree = ET.parse(gsdml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        logger.error(f"Failed to parse GSDML XML: {e}")
        return None

    # Handle namespace - GSDML uses ISO15745Profile namespace
    ns = {'gsdml': 'http://www.profibus.com/GSDML/2003/11/DeviceProfile'}

    # Try to find elements with or without namespace
    def find_element(parent, path_variants):
        """Find element trying multiple path variants."""
        for path in path_variants:
            elem = parent.find(path, ns)
            if elem is not None:
                return elem
            # Try without namespace
            elem = parent.find(path.replace('gsdml:', ''))
            if elem is not None:
                return elem
        return None

    def find_all_elements(parent, path_variants):
        """Find all elements trying multiple path variants."""
        for path in path_variants:
            elems = parent.findall(path, ns)
            if elems:
                return elems
            # Try without namespace
            elems = parent.findall(path.replace('gsdml:', ''))
            if elems:
                return elems
        return []

    # Parse DeviceIdentity
    device_identity = find_element(root, ['.//gsdml:DeviceIdentity', './/DeviceIdentity'])
    if device_identity is None:
        # Try direct children of ProfileBody
        for child in root.iter():
            if child.tag.endswith('DeviceIdentity'):
                device_identity = child
                break

    vendor_id = 0
    device_id = 0
    vendor_name = "Unknown"

    if device_identity is not None:
        vendor_id = _parse_hex_int(device_identity.get('VendorID', '0'))
        device_id = _parse_hex_int(device_identity.get('DeviceID', '0'))

        # Find VendorName
        for child in device_identity:
            tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if tag_name == 'VendorName':
                vendor_name = child.get('Value', 'Unknown')

    # Parse DeviceAccessPointItem for timing and IO config
    dap_item = None
    for elem in root.iter():
        tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag_name == 'DeviceAccessPointItem':
            dap_item = elem
            break

    min_device_interval = 32
    max_input_length = 256
    max_output_length = 256
    device_name = "PROFINET Device"
    dap_module_ident = 0x00000001
    dap_submodule_ident = 0x00000001

    if dap_item is not None:
        min_device_interval = int(dap_item.get('MinDeviceInterval', '32'))
        device_name = dap_item.get('DNS_CompatibleName', 'profinet-device')

        # Find IOConfigData
        for child in dap_item.iter():
            tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if tag_name == 'IOConfigData':
                max_input_length = int(child.get('MaxInputLength', '256'))
                max_output_length = int(child.get('MaxOutputLength', '256'))

        # Find DAP submodule ident from VirtualSubmoduleList
        for child in dap_item.iter():
            tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if tag_name == 'VirtualSubmoduleItem':
                submod_id = child.get('ID', '')
                if 'DAP' in submod_id.upper():
                    dap_submodule_ident = _parse_hex_int(
                        child.get('SubmoduleIdentNumber', '0x00000001')
                    )
                    break

    # Parse ModuleList for all modules
    modules = []
    for elem in root.iter():
        tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag_name == 'ModuleItem':
            module_id = elem.get('ID', '')
            module_ident = _parse_hex_int(elem.get('ModuleIdentNumber', '0'))

            # Get module name from ModuleInfo/Name
            module_name = module_id
            for info in elem.iter():
                info_tag = info.tag.split('}')[-1] if '}' in info.tag else info.tag
                if info_tag == 'ModuleInfo':
                    for name_elem in info:
                        name_tag = name_elem.tag.split('}')[-1] if '}' in name_elem.tag else name_elem.tag
                        if name_tag == 'Name':
                            module_name = name_elem.get('TextId', module_id)
                            break

            gsdml_module = GsdmlModule(
                module_id=module_id,
                module_ident_number=module_ident,
                name=module_name,
            )

            # Parse submodules
            for submod in elem.iter():
                submod_tag = submod.tag.split('}')[-1] if '}' in submod.tag else submod.tag
                if submod_tag == 'VirtualSubmoduleItem':
                    submod_id = submod.get('ID', '')
                    submod_ident = _parse_hex_int(
                        submod.get('SubmoduleIdentNumber', '0')
                    )

                    # Get submodule name
                    submod_name = submod_id
                    for info in submod.iter():
                        info_tag = info.tag.split('}')[-1] if '}' in info.tag else info.tag
                        if info_tag == 'ModuleInfo':
                            for name_elem in info:
                                name_tag = name_elem.tag.split('}')[-1] if '}' in name_elem.tag else name_elem.tag
                                if name_tag == 'Name':
                                    submod_name = name_elem.get('TextId', submod_id)
                                    break

                    # Find IOData for this submodule
                    io_data = None
                    for io_elem in submod:
                        io_tag = io_elem.tag.split('}')[-1] if '}' in io_elem.tag else io_elem.tag
                        if io_tag == 'IOData':
                            io_data = io_elem
                            break

                    input_len, output_len = _calculate_io_length(io_data)

                    gsdml_submodule = GsdmlSubmodule(
                        submodule_id=submod_id,
                        submodule_ident_number=submod_ident,
                        name=submod_name,
                        input_length=input_len,
                        output_length=output_len,
                    )
                    gsdml_module.submodules.append(gsdml_submodule)

                    # Track module I/O direction
                    if input_len > 0:
                        gsdml_module.is_input = True
                        gsdml_module.input_length += input_len
                    if output_len > 0:
                        gsdml_module.is_output = True
                        gsdml_module.output_length += output_len

            modules.append(gsdml_module)

    logger.info(
        f"Parsed GSDML: {vendor_name} ({device_name}) - "
        f"vendor=0x{vendor_id:04X}, device=0x{device_id:04X}, "
        f"{len(modules)} modules"
    )

    return GsdmlDeviceInfo(
        vendor_id=vendor_id,
        device_id=device_id,
        vendor_name=vendor_name,
        device_name=device_name,
        min_device_interval=min_device_interval,
        max_input_length=max_input_length,
        max_output_length=max_output_length,
        modules=modules,
        dap_module_ident=dap_module_ident,
        dap_submodule_ident=dap_submodule_ident,
    )


def get_module_by_type(gsdml_info: GsdmlDeviceInfo, module_type: str) -> Optional[GsdmlModule]:
    """
    Find a module by type name (e.g., 'pH', 'Pump', 'Valve').

    Args:
        gsdml_info: Parsed GSDML device info
        module_type: Type name to search for (case-insensitive)

    Returns:
        Matching GsdmlModule or None
    """
    type_lower = module_type.lower()
    for module in gsdml_info.modules:
        if type_lower in module.module_id.lower() or type_lower in module.name.lower():
            return module
    return None


def get_module_idents_by_measurement(
    gsdml_info: GsdmlDeviceInfo,
    measurement_type: str
) -> Tuple[int, int]:
    """
    Get module and submodule identifiers for a measurement type.

    Maps measurement type names to GSDML module identifiers.

    Args:
        gsdml_info: Parsed GSDML device info
        measurement_type: Measurement type (pH, TDS, Temperature, etc.)

    Returns:
        (module_ident, submodule_ident) tuple, or (0, 0) if not found
    """
    # Map measurement types to GSDML module name patterns
    type_to_pattern = {
        'ph': ['ph'],
        'tds': ['tds'],
        'turbidity': ['turb'],
        'temperature': ['temp'],
        'flow': ['flow'],
        'flow_rate': ['flow'],
        'level': ['level'],
        'dissolved_oxygen': ['generic', 'ai'],
        'pressure': ['generic', 'ai'],
        'conductivity': ['generic', 'ai'],
        'orp': ['generic', 'ai'],
        'chlorine': ['generic', 'ai'],
    }

    patterns = type_to_pattern.get(measurement_type.lower(), ['generic'])

    for pattern in patterns:
        for module in gsdml_info.modules:
            if pattern in module.module_id.lower():
                if module.submodules:
                    return (module.module_ident_number,
                            module.submodules[0].submodule_ident_number)
                return (module.module_ident_number, module.module_ident_number + 1)

    return (0, 0)


def get_module_idents_by_actuator(
    gsdml_info: GsdmlDeviceInfo,
    actuator_type: str
) -> Tuple[int, int]:
    """
    Get module and submodule identifiers for an actuator type.

    Maps actuator type names to GSDML module identifiers.

    Args:
        gsdml_info: Parsed GSDML device info
        actuator_type: Actuator type (Pump, Valve, etc.)

    Returns:
        (module_ident, submodule_ident) tuple, or (0, 0) if not found
    """
    # Map actuator types to GSDML module name patterns
    type_to_pattern = {
        'pump': ['pump'],
        'valve': ['valve'],
        'relay': ['generic', 'do'],
        'pwm': ['generic', 'do'],
        'latching': ['generic', 'do'],
        'momentary': ['generic', 'do'],
    }

    patterns = type_to_pattern.get(actuator_type.lower(), ['generic'])

    for pattern in patterns:
        for module in gsdml_info.modules:
            if pattern in module.module_id.lower():
                if module.submodules:
                    return (module.module_ident_number,
                            module.submodules[0].submodule_ident_number)
                return (module.module_ident_number, module.module_ident_number + 1)

    return (0, 0)


# ============================================================================
# Utility: Generate strategy from GSDML
# ============================================================================

def strategy_from_gsdml(gsdml_path: str) -> Optional[ConnectionStrategy]:
    """
    Parse GSDML file and generate optimized connection strategy.

    This extracts device-specific parameters like:
    - Supported timing values
    - Module/submodule identifiers
    - Alarm capabilities

    Returns None if GSDML parsing fails.
    """
    try:
        gsdml_info = parse_gsdml_file(gsdml_path)
        if gsdml_info is None:
            return None

        # Create strategy with GSDML-derived timing parameters
        strategy = STRATEGY_SPEC_COMPLIANT.clone(name=f"gsdml_{gsdml_info.device_id}")
        strategy.description = f"Strategy from {gsdml_info.vendor_name} GSDML"

        # Apply timing constraints from GSDML
        if gsdml_info.min_device_interval > 0:
            # MinDeviceInterval is in 31.25μs units, SendClockFactor is in same units
            strategy.iocr.send_clock_factor = gsdml_info.min_device_interval

        logger.info(
            f"Generated strategy from GSDML: {gsdml_info.vendor_name} "
            f"(vendor_id=0x{gsdml_info.vendor_id:04X}, device_id=0x{gsdml_info.device_id:04X}, "
            f"{len(gsdml_info.modules)} modules)"
        )
        return strategy

    except Exception as e:
        logger.warning(f"Failed to parse GSDML {gsdml_path}: {e}")
        return None
