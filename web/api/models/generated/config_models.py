"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY

Generated from: schemas/config/*.schema.yaml
Generated at: 2025-12-30 13:40:20 UTC
Generator: scripts/generate_pydantic.py

To update this file, modify the source schemas and run:
    python scripts/generate_pydantic.py
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator


# ========== Alarm Manager Configuration ==========

class LimitsConfig(BaseModel):
    """Alarm system limits"""

    max_active_alarms: int = Field(default=256, ge=10, le=10000, description="Maximum concurrent active alarms")
    max_history_entries: int = Field(default=10000, ge=100, le=1000000, description="Maximum alarm history entries to retain")
    max_rules: int = Field(default=512, ge=1, le=10000, description="Maximum alarm rules")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class Isa182Config(BaseModel):
    """ISA-18.2 compliance settings"""

    max_shelve_duration_hours: int = Field(default=24, ge=1, le=168, description="Maximum duration an alarm can be shelved")
    out_of_service_logging: bool = Field(default=True, description="Log all out-of-service state changes")
    rationalization_required: bool = Field(default=False, description="Require consequence and response for each alarm rule")
    require_acknowledgment: bool = Field(default=True, description="Require operator acknowledgment for alarms")
    shelving_enabled: bool = Field(default=True, description="Allow alarm shelving (temporary disable with audit)")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class FloodDetectionConfig(BaseModel):
    """Alarm flood detection (per ISA-18.2)"""

    enabled: bool = Field(default=True, description="Enable alarm flood detection")
    target_rate_per_10min: int = Field(default=10, ge=1, le=100, description="Target sustainable alarm rate (ISA-18.2 benchmark)")
    threshold_per_10min: int = Field(default=100, ge=10, le=1000, description="Alarm count threshold to declare flood condition")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class SeverityConfig(BaseModel):
    """Severity level definitions"""

    levels: List[LevelsItemConfig] = Field(default=[{'id': 1, 'name': 'Low', 'color': '#FFFF00', 'response_time_sec': 3600}, {'id': 2, 'name': 'Medium', 'color': '#FFA500', 'response_time_sec': 1800}, {'id': 3, 'name': 'High', 'color': '#FF0000', 'response_time_sec': 300}, {'id': 4, 'name': 'Emergency', 'color': '#8B0000', 'response_time_sec': 60}])

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class EmailConfig(BaseModel):
    """Email notification settings"""

    enabled: bool = Field(default=False, description="Enable email notifications")
    min_severity: int = Field(default=3, ge=1, le=4, description="Minimum severity to trigger email")
    recipients: List[str] = Field(default_factory=list, description="Email recipients for alarm notifications")
    smtp_host: str = Field(default="", description="SMTP server hostname")
    smtp_port: int = Field(default=587, ge=1, le=65535, description="SMTP server port")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class NotificationsConfig(BaseModel):
    """Alarm notification settings"""

    audible_alert: bool = Field(default=True, description="Enable audible alerts on HMI")
    email: Optional[EmailConfig] = Field(default=None, description="Email notification settings")
    enabled: bool = Field(default=True, description="Enable alarm notifications")
    websocket_broadcast: bool = Field(default=True, description="Broadcast alarms to WebSocket clients")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class SuppressionConfig(BaseModel):
    """Alarm suppression settings"""

    audit_all: bool = Field(default=True, description="Audit log all suppression actions")
    max_duration_minutes: int = Field(default=60, ge=1, le=1440, description="Maximum suppression duration")
    require_reason: bool = Field(default=True, description="Require reason when suppressing alarms")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class ConditionsConfig(BaseModel):
    """Available alarm conditions"""

    types: List[str] = Field(default=['HIGH', 'LOW', 'HIGH_HIGH', 'LOW_LOW', 'RATE_OF_CHANGE', 'DEVIATION', 'BAD_QUALITY'], description="Available alarm condition types")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class AlarmsConfig(BaseModel):
    """ISA-18.2 compliant alarm management configuration"""

    conditions: Optional[ConditionsConfig] = Field(default=None, description="Available alarm conditions")
    database_path: str = Field(default="", description="Alarm database path (uses main database if empty)")
    enabled: bool = Field(default=True, description="Enable alarm management")
    flood_detection: Optional[FloodDetectionConfig] = Field(default=None, description="Alarm flood detection (per ISA-18.2)")
    isa_18_2: Optional[Isa182Config] = Field(default=None, description="ISA-18.2 compliance settings")
    limits: Optional[LimitsConfig] = Field(default=None, description="Alarm system limits")
    notifications: Optional[NotificationsConfig] = Field(default=None, description="Alarm notification settings")
    severity: Optional[SeverityConfig] = Field(default=None, description="Severity level definitions")
    suppression: Optional[SuppressionConfig] = Field(default=None, description="Alarm suppression settings")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

# ========== Water Treatment Controller Configuration ==========

class SystemConfig(BaseModel):
    """System-wide settings"""

    config_dir: str = Field(default="/etc/water-controller", description="Directory for configuration files")
    data_dir: str = Field(default="/var/lib/water-controller", description="Directory for persistent data storage")
    install_dir: str = Field(default="/opt/water-controller", description="Installation directory")
    name: str = Field(default="Water Treatment Controller", max_length=64, description="Human-readable system name")
    version: str = Field(default="0.0.1", pattern=r"^\d+\.\d+\.\d+$", description="Controller version string")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class LevelEnum(str, Enum):
    """Enumeration for level."""

    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"

class TypeEnum(str, Enum):
    """Enumeration for type."""

    ELASTIC = "elastic"
    GRAYLOG = "graylog"
    SYSLOG = "syslog"
    EMPTY = ""

class ForwardConfig(BaseModel):
    """Log forwarding to external systems (Elastic, Graylog, Syslog)"""

    enabled: bool = Field(default=False, description="Enable log forwarding")
    host: str = Field(default="", description="Log forwarder hostname")
    port: int = Field(default=0, ge=1, le=65535, description="Log forwarder port")
    type: TypeEnum = Field(default="", description="Log forwarder type")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class LoggingConfig(BaseModel):
    """Logging configuration"""

    file: str = Field(default="", description="Log file path (empty for stderr only)")
    forward: Optional[ForwardConfig] = Field(default=None, description="Log forwarding to external systems (Elastic, Graylog, Syslog)")
    level: LevelEnum = Field(default="INFO", description="Minimum log level to output")
    log_dir: str = Field(default="/var/log/water-controller", description="Directory for log files")
    structured: bool = Field(default=False, description="Enable structured JSON logging for log aggregators")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class DaemonConfig(BaseModel):
    """Daemon/service mode settings"""

    enabled: bool = Field(default=False, description="Run as a background daemon")
    pid_file: str = Field(default="/var/run/water-controller.pid", description="PID file location when running as daemon")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class CycleConfig(BaseModel):
    """Main control cycle timing"""

    scan_rate_ms: int = Field(default=100, ge=10, le=10000, description="Control engine scan rate for PID/interlock evaluation")
    time_ms: int = Field(default=1000, ge=100, le=60000, description="Main cycle time for data collection and control")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class DatabaseConfig(BaseModel):
    """PostgreSQL database configuration for persistent storage"""

    connection_timeout_ms: int = Field(default=5000, ge=1000, le=60000, description="Connection timeout")
    enabled: bool = Field(default=True, description="Enable database persistence")
    host: str = Field(default="localhost", description="PostgreSQL server hostname")
    max_connections: int = Field(default=5, ge=1, le=100, description="Maximum database connection pool size")
    name: str = Field(default="water_controller", description="Database name")
    password: str = Field(default="", description="Database password")
    port: int = Field(default=5432, ge=1, le=65535, description="PostgreSQL server port")
    use_ssl: bool = Field(default=False, description="Use SSL for database connections")
    user: str = Field(default="wtc", description="Database username")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class SqliteConfig(BaseModel):
    """SQLite configuration for local-only deployments"""

    auto_init: bool = Field(default=True, description="Automatically initialize database schema")
    db_path: str = Field(default="/var/lib/water-controller/wtc.db", description="SQLite database file path")
    echo: bool = Field(default=False, description="Echo SQL queries for debugging")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class ModeEnum(str, Enum):
    """Enumeration for mode."""

    MANUAL = "manual"
    AUTO = "auto"
    HOT_STANDBY = "hot_standby"

class FailoverConfig(BaseModel):
    """RTU failover and redundancy settings"""

    enabled: bool = Field(default=True, description="Enable automatic failover handling")
    heartbeat_interval_ms: int = Field(default=1000, ge=100, le=10000, description="RTU health check interval")
    max_retries: int = Field(default=3, ge=0, le=10, description="Number of reconnection attempts before failover")
    mode: ModeEnum = Field(default="auto", description="Failover mode")
    timeout_ms: int = Field(default=5000, ge=1000, le=60000, description="Time to wait before declaring RTU failed")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class IpcConfig(BaseModel):
    """Inter-process communication settings"""

    shm_name: str = Field(default="/wtc_shared_memory", description="Shared memory segment name")
    shm_read_timeout_ms: int = Field(default=100, ge=10, le=5000, description="Timeout for reading shared memory")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class LimitsConfig(BaseModel):
    """System limits and maximums"""

    default_slots: int = Field(default=64, description="Default slot count per RTU")
    max_alarm_rules: int = Field(default=512, description="Maximum number of alarm rules")
    max_historian_tags: int = Field(default=1024, description="Maximum number of historian tags")
    max_interlocks: int = Field(default=128, description="Maximum number of interlocks")
    max_pid_loops: int = Field(default=64, description="Maximum number of PID control loops")
    max_rtus: int = Field(default=256, description="Maximum number of RTU devices")
    max_sequences: int = Field(default=32, description="Maximum number of control sequences")
    max_slots: int = Field(default=256, description="Maximum slots per RTU for fixed arrays")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class StartupModeEnum(str, Enum):
    """Enumeration for startup_mode."""

    EMPTY = ""
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"

class DebugConfig(BaseModel):
    """Debug and development settings"""

    enabled: bool = Field(default=False, description="Enable debug mode")
    simulation_mode: bool = Field(default=False, description="Run in simulation mode without real hardware")
    startup_mode: StartupModeEnum = Field(default="", description="Startup mode override")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class ControllerConfig(BaseModel):
    """Main configuration for the Water Treatment PROFINET IO Controller"""

    cycle: Optional[CycleConfig] = Field(default=None, description="Main control cycle timing")
    daemon: Optional[DaemonConfig] = Field(default=None, description="Daemon/service mode settings")
    database: Optional[DatabaseConfig] = Field(default=None, description="PostgreSQL database configuration for persistent storage")
    debug: Optional[DebugConfig] = Field(default=None, description="Debug and development settings")
    failover: Optional[FailoverConfig] = Field(default=None, description="RTU failover and redundancy settings")
    ipc: Optional[IpcConfig] = Field(default=None, description="Inter-process communication settings")
    limits: Optional[LimitsConfig] = Field(default=None, description="System limits and maximums")
    logging: Optional[LoggingConfig] = Field(default=None, description="Logging configuration")
    sqlite: Optional[SqliteConfig] = Field(default=None, description="SQLite configuration for local-only deployments")
    system: Optional[SystemConfig] = Field(default=None, description="System-wide settings")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

# ========== Data Historian Configuration ==========

class TimescaleConfig(BaseModel):
    """TimescaleDB configuration for scalable time-series storage"""

    database: str = Field(default="wtc_historian", description="TimescaleDB database name")
    enabled: bool = Field(default=False, description="Use TimescaleDB instead of SQLite")
    host: str = Field(default="localhost", description="TimescaleDB server hostname")
    password: str = Field(default="wtc_password", description="TimescaleDB password")
    port: int = Field(default=5432, ge=1, le=65535, description="TimescaleDB server port")
    user: str = Field(default="wtc", description="TimescaleDB username")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class SamplingConfig(BaseModel):
    """Default sampling settings for new tags"""

    default_deadband: float = Field(default=0.1, ge=0.0, le=100.0, description="Default deadband percentage (change threshold to record)")
    default_rate_ms: int = Field(default=1000, ge=100, le=3600000, description="Default sample rate for new historian tags")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class DefaultAlgorithmEnum(str, Enum):
    """Enumeration for default_algorithm."""

    NONE = "none"
    SWINGING_DOOR = "swinging_door"
    BOXCAR = "boxcar"
    DEADBAND = "deadband"

class CompressionConfig(BaseModel):
    """Data compression settings"""

    default_algorithm: DefaultAlgorithmEnum = Field(default="swinging_door", description="Default compression algorithm (SDT is industry standard)")
    swinging_door_deviation: float = Field(default=0.5, ge=0.0, le=10.0, description="Swinging door compression deviation percentage")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class RetentionConfig(BaseModel):
    """Data retention settings"""

    auto_purge: bool = Field(default=True, description="Automatically purge data older than retention period")
    days: int = Field(default=365, ge=1, le=36500, description="Number of days to retain historical data")
    purge_interval_hours: int = Field(default=24, ge=1, le=168, description="Interval between purge operations")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class LimitsConfig(BaseModel):
    """Historian limits"""

    buffer_size: int = Field(default=1000, ge=100, le=100000, description="In-memory buffer size per tag before flush")
    max_samples_per_tag: int = Field(default=1000000, ge=1000, le=100000000, description="Maximum samples stored per tag (prevents unbounded growth)")
    max_tags: int = Field(default=1024, ge=1, le=100000, description="Maximum number of historian tags")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class PerformanceConfig(BaseModel):
    """Performance tuning"""

    async_writes: bool = Field(default=True, description="Use asynchronous database writes")
    batch_size: int = Field(default=100, ge=1, le=10000, description="Number of samples to batch before writing")
    flush_interval_ms: int = Field(default=5000, ge=100, le=60000, description="Maximum time between buffer flushes")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class HistorianConfig(BaseModel):
    """Configuration for time-series data collection, compression, and storage"""

    compression: Optional[CompressionConfig] = Field(default=None, description="Data compression settings")
    database_path: str = Field(default="/var/lib/water-controller/historian.db", description="SQLite historian database path (for local storage)")
    enabled: bool = Field(default=True, description="Enable historian data collection")
    limits: Optional[LimitsConfig] = Field(default=None, description="Historian limits")
    performance: Optional[PerformanceConfig] = Field(default=None, description="Performance tuning")
    retention: Optional[RetentionConfig] = Field(default=None, description="Data retention settings")
    sampling: Optional[SamplingConfig] = Field(default=None, description="Default sampling settings for new tags")
    timescale: Optional[TimescaleConfig] = Field(default=None, description="TimescaleDB configuration for scalable time-series storage")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

# ========== Modbus Gateway Configuration ==========

class TcpConfig(BaseModel):
    """Modbus TCP server settings"""

    bind_address: str = Field(default="0.0.0.0", description="TCP bind address")
    enabled: bool = Field(default=True, description="Enable Modbus TCP server")
    max_connections: int = Field(default=10, ge=1, le=100, description="Maximum concurrent TCP connections")
    port: int = Field(default=502, ge=1, le=65535, description="Modbus TCP listen port")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class ParityEnum(str, Enum):
    """Enumeration for parity."""

    N = "N"
    E = "E"
    O = "O"

class RtuConfig(BaseModel):
    """Modbus RTU server settings"""

    baud_rate: BaudRateEnum = Field(default=9600, description="Serial baud rate")
    data_bits: DataBitsEnum = Field(default=8, description="Serial data bits")
    device: str = Field(default="", max_length=64, description="Serial device path (e.g., /dev/ttyUSB0)")
    enabled: bool = Field(default=False, description="Enable Modbus RTU server")
    parity: ParityEnum = Field(default="N", description="Serial parity (None, Even, Odd)")
    slave_address: int = Field(default=1, ge=1, le=247, description="RTU slave address")
    stop_bits: StopBitsEnum = Field(default=1, description="Serial stop bits")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class ServerConfig(BaseModel):
    """Modbus server configuration (exposes PROFINET data)"""

    rtu: Optional[RtuConfig] = Field(default=None, description="Modbus RTU server settings")
    tcp: Optional[TcpConfig] = Field(default=None, description="Modbus TCP server settings")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class RegisterMapConfig(BaseModel):
    """Register mapping configuration"""

    actuator_base_address: int = Field(default=1000, ge=0, le=65535, description="Base address for actuator registers")
    auto_generate: bool = Field(default=True, description="Automatically generate register map from RTU data")
    map_file: str = Field(default="", max_length=256, description="Custom register map file (JSON)")
    sensor_base_address: int = Field(default=0, ge=0, le=65535, description="Base address for sensor registers")
    status_base_address: int = Field(default=2000, ge=0, le=65535, description="Base address for status registers")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class DownstreamConfig(BaseModel):
    """Downstream Modbus client configuration"""

    default_poll_interval_ms: int = Field(default=1000, ge=100, le=60000, description="Default polling interval for downstream devices")
    default_timeout_ms: int = Field(default=1000, ge=100, le=30000, description="Default timeout for downstream device communication")
    max_devices: int = Field(default=16, ge=0, le=16, description="Maximum downstream devices")
    retry_count: int = Field(default=3, ge=0, le=10, description="Number of retries on communication failure")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class TimingConfig(BaseModel):
    """Modbus timing configuration"""

    inter_frame_delay_ms: int = Field(default=5, ge=0, le=1000, description="Delay between frames (for RTU compliance)")
    response_timeout_ms: int = Field(default=500, ge=50, le=10000, description="Response timeout for requests")
    turnaround_delay_ms: int = Field(default=50, ge=0, le=1000, description="Turnaround delay after response")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class ModbusConfig(BaseModel):
    """PROFINET to Modbus TCP/RTU protocol bridge configuration"""

    downstream: Optional[DownstreamConfig] = Field(default=None, description="Downstream Modbus client configuration")
    enabled: bool = Field(default=True, description="Enable Modbus gateway")
    register_map: Optional[RegisterMapConfig] = Field(default=None, description="Register mapping configuration")
    server: Optional[ServerConfig] = Field(default=None, description="Modbus server configuration (exposes PROFINET data)")
    timing: Optional[TimingConfig] = Field(default=None, description="Modbus timing configuration")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

# ========== PROFINET IO Controller Configuration ==========

class ControllerConfig(BaseModel):
    """Controller identity settings"""

    device_id: int = Field(default=1, ge=0, le=65535, description="PROFINET device ID")
    gateway: str = Field(default="", description="Default gateway (optional)")
    ip_address: str = Field(default="", description="Controller IP address (auto-detect if empty)")
    mac_address: str = Field(default="", pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", description="Controller MAC address (auto-detect if empty)")
    station_name: str = Field(default="wtc-controller", max_length=64, pattern=r"^[a-z0-9][a-z0-9.-]*$", description="Controller station name (DNS compatible)")
    subnet_mask: str = Field(default="255.255.255.0", description="Network subnet mask")
    vendor_id: int = Field(default=4660, ge=0, le=65535, description="PROFINET vendor ID (0x1234)")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class DiscoveryConfig(BaseModel):
    """DCP discovery settings"""

    auto_discover: bool = Field(default=True, description="Automatically discover RTUs on startup")
    periodic_scan: bool = Field(default=False, description="Periodically scan for new devices")
    scan_interval_sec: int = Field(default=300, ge=60, le=3600, description="Interval between periodic discovery scans")
    timeout_ms: int = Field(default=5000, ge=1000, le=30000, description="DCP discovery response timeout")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class TimingConfig(BaseModel):
    """Timing and watchdog settings"""

    command_timeout_ms: int = Field(default=3000, ge=100, le=10000, description="Command execution timeout")
    reconnect_delay_ms: int = Field(default=5000, ge=1000, le=60000, description="Delay before reconnection attempt")
    watchdog_ms: int = Field(default=3000, ge=100, le=60000, description="Device watchdog timeout")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class LimitsConfig(BaseModel):
    """PROFINET stack limits"""

    max_api: int = Field(default=256, description="Maximum Application Process Identifiers")
    max_ar: int = Field(default=256, description="Maximum Application Relationships")
    max_iocr: int = Field(default=64, description="Maximum IO Communication Relationships per AR")
    min_cycle_time_us: int = Field(default=31250, description="Minimum PROFINET cycle time")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class AuthorityConfig(BaseModel):
    """Authority handoff protocol settings"""

    handoff_timeout_ms: int = Field(default=5000, ge=1000, le=30000, description="Maximum time to wait for authority handoff acknowledgment")
    stale_command_threshold_ms: int = Field(default=1000, ge=100, le=10000, description="Commands older than this are rejected during authority transfer")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class ProfinetConfig(BaseModel):
    """Configuration for PROFINET RT Class 1 communication with RTU devices"""

    authority: Optional[AuthorityConfig] = Field(default=None, description="Authority handoff protocol settings")
    controller: Optional[ControllerConfig] = Field(default=None, description="Controller identity settings")
    cycle_time_us: int = Field(default=1000000, ge=31250, le=4000000, description="PROFINET cycle time (minimum 31.25us, typically 1ms for RT Class 1)")
    discovery: Optional[DiscoveryConfig] = Field(default=None, description="DCP discovery settings")
    interface: str = Field(default="eth0", max_length=32, pattern=r"^[a-zA-Z0-9_-]+$", description="Network interface for PROFINET communication")
    limits: Optional[LimitsConfig] = Field(default=None, description="PROFINET stack limits")
    reduction_ratio: int = Field(default=1, ge=1, le=512, description="Reduction ratio for actual cycle time")
    send_clock_factor: int = Field(default=32, ge=1, le=128, description="Send clock factor (32 = 1ms base cycle)")
    socket_priority: int = Field(default=6, ge=0, le=7, description="Socket priority for QoS (0-7, 6 recommended for RT)")
    timing: Optional[TimingConfig] = Field(default=None, description="Timing and watchdog settings")
    use_raw_sockets: bool = Field(default=True, description="Use raw sockets for RT frames (requires CAP_NET_RAW)")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

# ========== Web API and HMI Configuration ==========

class ApiConfig(BaseModel):
    """FastAPI backend configuration"""

    api_only: bool = Field(default=False, description="Run API only (no UI serving)")
    cors_origins: str = Field(default="", description="Comma-separated list of allowed CORS origins")
    debug: bool = Field(default=False, description="Enable API debug mode")
    host: str = Field(default="0.0.0.0", description="API server bind address")
    port: int = Field(default=8080, ge=1, le=65535, description="API server port")
    workers: int = Field(default=4, ge=1, le=32, description="Number of API worker processes")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class UiConfig(BaseModel):
    """Web UI configuration"""

    api_url: str = Field(default="", description="API URL for UI to connect to")
    dist_dir: str = Field(default="", description="Static UI distribution directory")
    port: int = Field(default=3000, ge=1, le=65535, description="UI server port (when running separately)")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class TimeoutsConfig(BaseModel):
    """API timeout configuration"""

    command_ms: int = Field(default=3000, ge=100, le=30000, description="Command execution timeout")
    db_query_ms: int = Field(default=5000, ge=100, le=60000, description="Database query timeout")
    dcp_discovery_ms: int = Field(default=5000, ge=1000, le=30000, description="PROFINET DCP discovery timeout")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class WebsocketConfig(BaseModel):
    """WebSocket streaming configuration"""

    heartbeat_interval_ms: int = Field(default=30000, ge=1000, le=60000, description="WebSocket heartbeat interval")
    reconnect_base_ms: int = Field(default=1000, ge=100, le=30000, description="Base reconnection interval (exponential backoff)")
    reconnect_max_attempts: int = Field(default=10, ge=1, le=100, description="Maximum reconnection attempts")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class PollingConfig(BaseModel):
    """Fallback polling configuration (when WebSocket unavailable)"""

    default_interval_ms: int = Field(default=5000, ge=1000, le=60000, description="Default polling interval")
    many_rtus_interval_ms: int = Field(default=10000, ge=1000, le=120000, description="Reduced polling interval when many RTUs")
    many_rtus_threshold: int = Field(default=10, ge=1, le=100, description="RTU count to trigger reduced polling")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class CircuitBreakerConfig(BaseModel):
    """Circuit breaker for API resilience"""

    failure_threshold: int = Field(default=5, ge=1, le=100, description="Failures before opening circuit")
    reset_timeout_seconds: int = Field(default=30, ge=1, le=600, description="Time before attempting reset")
    success_threshold: int = Field(default=3, ge=1, le=100, description="Successes required to close circuit")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class AuthenticationConfig(BaseModel):
    """Authentication configuration"""

    ad_domain: str = Field(default="", description="Active Directory domain")
    ad_enabled: bool = Field(default=False, description="Enable Active Directory authentication")
    ad_server: str = Field(default="", description="Active Directory server")
    enabled: bool = Field(default=True, description="Enable authentication")
    max_sessions_per_user: int = Field(default=5, ge=1, le=100, description="Maximum concurrent sessions per user")
    session_timeout_minutes: int = Field(default=60, ge=5, le=1440, description="Session timeout")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class SecurityConfig(BaseModel):
    """Security settings"""

    csrf_enabled: bool = Field(default=True, description="Enable CSRF protection")
    rate_limit_requests_per_minute: int = Field(default=100, ge=10, le=10000, description="API rate limit per IP")
    secure_cookies: bool = Field(default=True, description="Use secure cookies (HTTPS only)")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

class WebConfig(BaseModel):
    """Configuration for FastAPI REST API, WebSocket streaming, and React HMI"""

    api: Optional[ApiConfig] = Field(default=None, description="FastAPI backend configuration")
    authentication: Optional[AuthenticationConfig] = Field(default=None, description="Authentication configuration")
    circuit_breaker: Optional[CircuitBreakerConfig] = Field(default=None, description="Circuit breaker for API resilience")
    polling: Optional[PollingConfig] = Field(default=None, description="Fallback polling configuration (when WebSocket unavailable)")
    security: Optional[SecurityConfig] = Field(default=None, description="Security settings")
    timeouts: Optional[TimeoutsConfig] = Field(default=None, description="API timeout configuration")
    ui: Optional[UiConfig] = Field(default=None, description="Web UI configuration")
    websocket: Optional[WebsocketConfig] = Field(default=None, description="WebSocket streaming configuration")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }

# ========== Combined Configuration ==========

class WaterControllerConfig(BaseModel):
    """Complete Water Controller configuration."""

    alarms: Optional[AlarmsConfig] = Field(default=None, description="ISA-18.2 compliant alarm management configuration")
    controller: Optional[ControllerConfig] = Field(default=None, description="Main configuration for the Water Treatment PROFINET IO Controller")
    historian: Optional[HistorianConfig] = Field(default=None, description="Configuration for time-series data collection, compression, and storage")
    modbus: Optional[ModbusConfig] = Field(default=None, description="PROFINET to Modbus TCP/RTU protocol bridge configuration")
    profinet: Optional[ProfinetConfig] = Field(default=None, description="Configuration for PROFINET RT Class 1 communication with RTU devices")
    web: Optional[WebConfig] = Field(default=None, description="Configuration for FastAPI REST API, WebSocket streaming, and React HMI")

    model_config = {
        "extra": "forbid",
        "validate_default": True,
    }
