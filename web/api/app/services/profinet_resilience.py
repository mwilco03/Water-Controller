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
from typing import Optional, List, Dict, Callable, Any, Tuple
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
    # TODO: Implement GSDML parsing
    # For now, return None to use defaults
    logger.debug(f"GSDML parsing not yet implemented for: {gsdml_path}")
    return None
