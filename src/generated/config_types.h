/*
 * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
 *
 * Generated from: schemas/config/ (all .schema.yaml files)
 * Generated at: 2026-02-06 13:16:58 UTC
 * Generator: scripts/generate_c_types.py
 *
 * To update this file, modify the source schemas and run:
 *   python scripts/generate_c_types.py
 */

#ifndef WTC_GENERATED_CONFIG_TYPES_H
#define WTC_GENERATED_CONFIG_TYPES_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Configuration limits and constants */

/** Maximum alarm rules */
#define WTC_MAX_ALARM_RULES 512

/** Maximum number of RTU devices */
#define WTC_MAX_RTUS 256

/** Maximum number of PID control loops */
#define WTC_MAX_PID_LOOPS 64

/** Maximum number of interlocks */
#define WTC_MAX_INTERLOCKS 128

/** Maximum number of control sequences */
#define WTC_MAX_SEQUENCES 32

/** Maximum number of alarm rules */
#define WTC_MAX_ALARM_RULES 512

/** Maximum number of historian tags */
#define WTC_MAX_HISTORIAN_TAGS 1024

/** Default slot count per RTU (matches RTU GSDML 247 slots) */
#define WTC_DEFAULT_SLOTS 247

/** Maximum slots per RTU (PROFINET/Modbus parity: slots 0-246) */
#define WTC_MAX_SLOTS 247

/** Maximum number of historian tags */
#define WTC_MAX_HISTORIAN_TAGS 1024

/** Maximum downstream devices */
#define MAX_MODBUS_CLIENTS 16

/** Maximum Application Relationships */
#define PROFINET_MAX_AR 256

/** Maximum IO Communication Relationships per AR */
#define PROFINET_MAX_IOCR 64

/** Maximum Application Process Identifiers */
#define PROFINET_MAX_API 256

/** Minimum PROFINET cycle time */
#define PROFINET_MIN_CYCLE_TIME_US 31250

/* ========== Alarm Manager Configuration ========== */

/**
 * limits configuration
 * Maximum concurrent active alarms...
 */
typedef struct {
    /** Maximum concurrent active alarms */
    uint16_t max_active_alarms;
    /** Maximum alarm history entries to retain */
    uint32_t max_history_entries;
    /** Maximum alarm rules */
    uint16_t max_rules;
} alarms_limits_config_t;

/**
 * isa_18_2 configuration
 * Require operator acknowledgment for alarms...
 */
typedef struct {
    /** Maximum duration an alarm can be shelved */
    uint8_t max_shelve_duration_hours;
    /** Log all out-of-service state changes */
    bool out_of_service_logging;
    /** Require consequence and response for each alarm rule */
    bool rationalization_required;
    /** Require operator acknowledgment for alarms */
    bool require_acknowledgment;
    /** Allow alarm shelving (temporary disable with audit) */
    bool shelving_enabled;
} alarms_isa_18_2_config_t;

/**
 * flood_detection configuration
 * Enable alarm flood detection...
 */
typedef struct {
    /** Enable alarm flood detection */
    bool enabled;
    /** Target sustainable alarm rate (ISA-18.2 benchmark) */
    uint8_t target_rate_per_10min;
    /** Alarm count threshold to declare flood condition */
    uint16_t threshold_per_10min;
} alarms_flood_detection_config_t;

/**
 * severity configuration
 */
typedef struct {
    void* levels;
} alarms_severity_config_t;

/**
 * email configuration
 * Enable email notifications...
 */
typedef struct {
    /** Enable email notifications */
    bool enabled;
    /** Minimum severity to trigger email */
    uint8_t min_severity;
    /** Email recipients for alarm notifications */
    void* recipients;
    /** SMTP server hostname */
    char smtp_host[256];
    /** SMTP server port */
    uint16_t smtp_port;
} alarms_notifications_email_config_t;

/**
 * notifications configuration
 * Enable alarm notifications...
 */
typedef struct {
    /** Enable audible alerts on HMI */
    bool audible_alert;
    /** Email notification settings */
    alarms_notifications_email_config_t email;
    /** Enable alarm notifications */
    bool enabled;
    /** Broadcast alarms to WebSocket clients */
    bool websocket_broadcast;
} alarms_notifications_config_t;

/**
 * suppression configuration
 * Maximum suppression duration...
 */
typedef struct {
    /** Audit log all suppression actions */
    bool audit_all;
    /** Maximum suppression duration */
    uint16_t max_duration_minutes;
    /** Require reason when suppressing alarms */
    bool require_reason;
} alarms_suppression_config_t;

/**
 * conditions configuration
 * Available alarm condition types...
 */
typedef struct {
    /** Available alarm condition types */
    void* types;
} alarms_conditions_config_t;

/**
 * alarms configuration
 * Enable alarm management...
 */
typedef struct {
    /** Available alarm conditions */
    alarms_conditions_config_t conditions;
    /** Alarm database path (uses main database if empty) */
    char database_path[256];
    /** Enable alarm management */
    bool enabled;
    /** Alarm flood detection (per ISA-18.2) */
    alarms_flood_detection_config_t flood_detection;
    /** ISA-18.2 compliance settings */
    alarms_isa_18_2_config_t isa_18_2;
    /** Alarm system limits */
    alarms_limits_config_t limits;
    /** Alarm notification settings */
    alarms_notifications_config_t notifications;
    /** Severity level definitions */
    alarms_severity_config_t severity;
    /** Alarm suppression settings */
    alarms_suppression_config_t suppression;
} alarms_config_t;

/* ========== Water Treatment Controller Configuration ========== */

/**
 * system configuration
 * Human-readable system name...
 */
typedef struct {
    /** Directory for configuration files */
    char config_dir[256];
    /** Directory for persistent data storage */
    char data_dir[256];
    /** Installation directory */
    char install_dir[256];
    /** Human-readable system name */
    char name[64];
    /** Controller version string */
    char version[256];
} controller_system_config_t;

/** level enumeration */
typedef enum {
    CONTROLLER_LOGGING_LEVEL_TRACE = 0,
    CONTROLLER_LOGGING_LEVEL_DEBUG,
    CONTROLLER_LOGGING_LEVEL_INFO,
    CONTROLLER_LOGGING_LEVEL_WARN,
    CONTROLLER_LOGGING_LEVEL_ERROR,
    CONTROLLER_LOGGING_LEVEL_FATAL,
} level_t;

/** type enumeration */
typedef enum {
    CONTROLLER_LOGGING_FORWARD_TYPE_ELASTIC = 0,
    CONTROLLER_LOGGING_FORWARD_TYPE_GRAYLOG,
    CONTROLLER_LOGGING_FORWARD_TYPE_SYSLOG,
    CONTROLLER_LOGGING_FORWARD_TYPE_,
} type_t;

/**
 * forward configuration
 * Enable log forwarding...
 */
typedef struct {
    /** Enable log forwarding */
    bool enabled;
    /** Log forwarder hostname */
    char host[256];
    /** Log forwarder port */
    uint16_t port;
    /** Log forwarder type */
    char type[256];
} controller_logging_forward_config_t;

/**
 * logging configuration
 * Minimum log level to output...
 */
typedef struct {
    /** Log file path (empty for stderr only) */
    char file[256];
    /** Log forwarding to external systems (Elastic, Graylog, Syslog) */
    controller_logging_forward_config_t forward;
    /** Minimum log level to output */
    char level[256];
    /** Directory for log files */
    char log_dir[256];
    /** Enable structured JSON logging for log aggregators */
    bool structured;
} controller_logging_config_t;

/**
 * daemon configuration
 * Run as a background daemon...
 */
typedef struct {
    /** Run as a background daemon */
    bool enabled;
    /** PID file location when running as daemon */
    char pid_file[256];
} controller_daemon_config_t;

/**
 * cycle configuration
 * Main cycle time for data collection and control...
 */
typedef struct {
    /** Control engine scan rate for PID/interlock evaluation */
    uint16_t scan_rate_ms;
    /** Main cycle time for data collection and control */
    uint16_t time_ms;
} controller_cycle_config_t;

/**
 * database configuration
 * Enable database persistence...
 */
typedef struct {
    /** Connection timeout */
    uint16_t connection_timeout_ms;
    /** Enable database persistence */
    bool enabled;
    /** PostgreSQL server hostname */
    char host[256];
    /** Maximum database connection pool size */
    uint8_t max_connections;
    /** Database name */
    char name[256];
    /** Database password */
    char password[256];
    /** PostgreSQL server port */
    uint16_t port;
    /** Use SSL for database connections */
    bool use_ssl;
    /** Database username */
    char user[256];
} controller_database_config_t;

/**
 * sqlite configuration
 * SQLite database file path...
 */
typedef struct {
    /** Automatically initialize database schema */
    bool auto_init;
    /** SQLite database file path */
    char db_path[256];
    /** Echo SQL queries for debugging */
    bool echo;
} controller_sqlite_config_t;

/** mode enumeration */
typedef enum {
    CONTROLLER_FAILOVER_MODE_MANUAL = 0,
    CONTROLLER_FAILOVER_MODE_AUTO,
    CONTROLLER_FAILOVER_MODE_HOT_STANDBY,
} mode_t;

/**
 * failover configuration
 * Enable automatic failover handling...
 */
typedef struct {
    /** Enable automatic failover handling */
    bool enabled;
    /** RTU health check interval */
    uint16_t heartbeat_interval_ms;
    /** Number of reconnection attempts before failover */
    uint8_t max_retries;
    /** Failover mode */
    char mode[256];
    /** Time to wait before declaring RTU failed */
    uint16_t timeout_ms;
} controller_failover_config_t;

/**
 * ipc configuration
 * Shared memory segment name...
 */
typedef struct {
    /** Shared memory segment name */
    char shm_name[256];
    /** Timeout for reading shared memory */
    uint16_t shm_read_timeout_ms;
} controller_ipc_config_t;

/**
 * limits configuration
 * Maximum number of RTU devices...
 */
typedef struct {
    /** Default slot count per RTU (matches RTU GSDML 247 slots) */
    uint8_t default_slots;
    /** Maximum number of alarm rules */
    uint8_t max_alarm_rules;
    /** Maximum number of historian tags */
    uint8_t max_historian_tags;
    /** Maximum number of interlocks */
    uint8_t max_interlocks;
    /** Maximum number of PID control loops */
    uint8_t max_pid_loops;
    /** Maximum number of RTU devices */
    uint8_t max_rtus;
    /** Maximum number of control sequences */
    uint8_t max_sequences;
    /** Maximum slots per RTU (PROFINET/Modbus parity: slots 0-246) */
    uint8_t max_slots;
} controller_limits_config_t;

/** startup_mode enumeration */
typedef enum {
    CONTROLLER_DEBUG_STARTUP_MODE_ = 0,
    CONTROLLER_DEBUG_STARTUP_MODE_DEVELOPMENT,
    CONTROLLER_DEBUG_STARTUP_MODE_TESTING,
    CONTROLLER_DEBUG_STARTUP_MODE_PRODUCTION,
} startup_mode_t;

/**
 * debug configuration
 * Enable debug mode...
 */
typedef struct {
    /** Enable debug mode */
    bool enabled;
    /** Run in simulation mode without real hardware */
    bool simulation_mode;
    /** Startup mode override */
    char startup_mode[256];
} controller_debug_config_t;

/**
 * controller configuration
 * System-wide settings...
 */
typedef struct {
    /** Main control cycle timing */
    controller_cycle_config_t cycle;
    /** Daemon/service mode settings */
    controller_daemon_config_t daemon;
    /** PostgreSQL database configuration for persistent storage */
    controller_database_config_t database;
    /** Debug and development settings */
    controller_debug_config_t debug;
    /** RTU failover and redundancy settings */
    controller_failover_config_t failover;
    /** Inter-process communication settings */
    controller_ipc_config_t ipc;
    /** System limits and maximums */
    controller_limits_config_t limits;
    /** Logging configuration */
    controller_logging_config_t logging;
    /** SQLite configuration for local-only deployments */
    controller_sqlite_config_t sqlite;
    /** System-wide settings */
    controller_system_config_t system;
} controller_config_t;

/* ========== Data Historian Configuration ========== */

/**
 * timescale configuration
 * Use TimescaleDB instead of SQLite...
 */
typedef struct {
    /** TimescaleDB database name */
    char database[256];
    /** Use TimescaleDB instead of SQLite */
    bool enabled;
    /** TimescaleDB server hostname */
    char host[256];
    /** TimescaleDB password */
    char password[256];
    /** TimescaleDB server port */
    uint16_t port;
    /** TimescaleDB username */
    char user[256];
} historian_timescale_config_t;

/**
 * sampling configuration
 * Default sample rate for new historian tags...
 */
typedef struct {
    /** Default deadband percentage (change threshold to record) */
    float default_deadband;
    /** Default sample rate for new historian tags */
    uint32_t default_rate_ms;
} historian_sampling_config_t;

/** default_algorithm enumeration */
typedef enum {
    HISTORIAN_COMPRESSION_DEFAULT_ALGORITHM_NONE = 0,
    HISTORIAN_COMPRESSION_DEFAULT_ALGORITHM_SWINGING_DOOR,
    HISTORIAN_COMPRESSION_DEFAULT_ALGORITHM_BOXCAR,
    HISTORIAN_COMPRESSION_DEFAULT_ALGORITHM_DEADBAND,
} default_algorithm_t;

/**
 * compression configuration
 * Default compression algorithm (SDT is industry standard)...
 */
typedef struct {
    /** Default compression algorithm (SDT is industry standard) */
    char default_algorithm[256];
    /** Swinging door compression deviation percentage */
    float swinging_door_deviation;
} historian_compression_config_t;

/**
 * retention configuration
 * Number of days to retain historical data...
 */
typedef struct {
    /** Automatically purge data older than retention period */
    bool auto_purge;
    /** Number of days to retain historical data */
    uint16_t days;
    /** Interval between purge operations */
    uint8_t purge_interval_hours;
} historian_retention_config_t;

/**
 * limits configuration
 * Maximum number of historian tags...
 */
typedef struct {
    /** In-memory buffer size per tag before flush */
    uint32_t buffer_size;
    /** Maximum samples stored per tag (prevents unbounded growth) */
    uint32_t max_samples_per_tag;
    /** Maximum number of historian tags */
    uint32_t max_tags;
} historian_limits_config_t;

/**
 * performance configuration
 * Use asynchronous database writes...
 */
typedef struct {
    /** Use asynchronous database writes */
    bool async_writes;
    /** Number of samples to batch before writing */
    uint16_t batch_size;
    /** Maximum time between buffer flushes */
    uint16_t flush_interval_ms;
} historian_performance_config_t;

/**
 * historian configuration
 * Enable historian data collection...
 */
typedef struct {
    /** Data compression settings */
    historian_compression_config_t compression;
    /** SQLite historian database path (for local storage) */
    char database_path[256];
    /** Enable historian data collection */
    bool enabled;
    /** Historian limits */
    historian_limits_config_t limits;
    /** Performance tuning */
    historian_performance_config_t performance;
    /** Data retention settings */
    historian_retention_config_t retention;
    /** Default sampling settings for new tags */
    historian_sampling_config_t sampling;
    /** TimescaleDB configuration for scalable time-series storage */
    historian_timescale_config_t timescale;
} historian_config_t;

/* ========== Modbus Gateway Configuration ========== */

/**
 * tcp configuration
 * Enable Modbus TCP server...
 */
typedef struct {
    /** TCP bind address */
    char bind_address[256];
    /** Enable Modbus TCP server */
    bool enabled;
    /** Maximum concurrent TCP connections */
    uint8_t max_connections;
    /** Modbus TCP listen port */
    uint16_t port;
} modbus_server_tcp_config_t;

/** parity enumeration */
typedef enum {
    MODBUS_SERVER_RTU_PARITY_N = 0,
    MODBUS_SERVER_RTU_PARITY_E,
    MODBUS_SERVER_RTU_PARITY_O,
} parity_t;

/**
 * rtu configuration
 * Enable Modbus RTU server...
 */
typedef struct {
    /** Serial baud rate */
    uint8_t baud_rate;
    /** Serial data bits */
    uint8_t data_bits;
    /** Serial device path (e.g., /dev/ttyUSB0) */
    char device[64];
    /** Enable Modbus RTU server */
    bool enabled;
    /** Serial parity (None, Even, Odd) */
    char parity[256];
    /** RTU slave address */
    uint8_t slave_address;
    /** Serial stop bits */
    uint8_t stop_bits;
} modbus_server_rtu_config_t;

/**
 * server configuration
 * Modbus TCP server settings...
 */
typedef struct {
    /** Modbus RTU server settings */
    modbus_server_rtu_config_t rtu;
    /** Modbus TCP server settings */
    modbus_server_tcp_config_t tcp;
} modbus_server_config_t;

/**
 * register_map configuration
 * Automatically generate register map from RTU data...
 */
typedef struct {
    /** Base address for actuator registers */
    uint16_t actuator_base_address;
    /** Automatically generate register map from RTU data */
    bool auto_generate;
    /** Custom register map file (JSON) */
    char map_file[256];
    /** Base address for sensor registers */
    uint16_t sensor_base_address;
    /** Base address for status registers */
    uint16_t status_base_address;
} modbus_register_map_config_t;

/**
 * downstream configuration
 * Maximum downstream devices...
 */
typedef struct {
    /** Default polling interval for downstream devices */
    uint16_t default_poll_interval_ms;
    /** Default timeout for downstream device communication */
    uint16_t default_timeout_ms;
    /** Maximum downstream devices */
    uint8_t max_devices;
    /** Number of retries on communication failure */
    uint8_t retry_count;
} modbus_downstream_config_t;

/**
 * timing configuration
 * Response timeout for requests...
 */
typedef struct {
    /** Delay between frames (for RTU compliance) */
    uint16_t inter_frame_delay_ms;
    /** Response timeout for requests */
    uint16_t response_timeout_ms;
    /** Turnaround delay after response */
    uint16_t turnaround_delay_ms;
} modbus_timing_config_t;

/**
 * modbus configuration
 * Enable Modbus gateway...
 */
typedef struct {
    /** Downstream Modbus client configuration */
    modbus_downstream_config_t downstream;
    /** Enable Modbus gateway */
    bool enabled;
    /** Register mapping configuration */
    modbus_register_map_config_t register_map;
    /** Modbus server configuration (exposes PROFINET data) */
    modbus_server_config_t server;
    /** Modbus timing configuration */
    modbus_timing_config_t timing;
} modbus_config_t;

/* ========== PROFINET IO Controller Configuration ========== */

/**
 * controller configuration
 * PROFINET vendor ID (0x0272, must match GSDML)...
 */
typedef struct {
    /** PROFINET device ID (0x0C05) */
    uint16_t device_id;
    /** Default gateway (optional) */
    char gateway[256];
    /** Controller IP address (auto-detect if empty) */
    char ip_address[256];
    /** Controller MAC address (auto-detect if empty) */
    char mac_address[256];
    /** Controller station name (PROFINET IEC 61158-6: lowercase, digits, hyph */
    char station_name[63];
    /** Network subnet mask */
    char subnet_mask[256];
    /** PROFINET vendor ID (0x0272, must match GSDML) */
    uint16_t vendor_id;
} profinet_controller_config_t;

/**
 * discovery configuration
 * DCP discovery response timeout...
 */
typedef struct {
    /** Automatically discover RTUs on startup */
    bool auto_discover;
    /** Periodically scan for new devices */
    bool periodic_scan;
    /** Interval between periodic discovery scans */
    uint16_t scan_interval_sec;
    /** DCP discovery response timeout */
    uint16_t timeout_ms;
} profinet_discovery_config_t;

/**
 * timing configuration
 * Device watchdog timeout...
 */
typedef struct {
    /** Command execution timeout */
    uint16_t command_timeout_ms;
    /** Delay before reconnection attempt */
    uint16_t reconnect_delay_ms;
    /** Device watchdog timeout */
    uint16_t watchdog_ms;
} profinet_timing_config_t;

/**
 * limits configuration
 * Maximum Application Relationships...
 */
typedef struct {
    /** Maximum Application Process Identifiers */
    uint8_t max_api;
    /** Maximum Application Relationships */
    uint8_t max_ar;
    /** Maximum IO Communication Relationships per AR */
    uint8_t max_iocr;
    /** Minimum PROFINET cycle time */
    uint8_t min_cycle_time_us;
} profinet_limits_config_t;

/**
 * authority configuration
 * Commands older than this are rejected during authority trans...
 */
typedef struct {
    /** Maximum time to wait for authority handoff acknowledgment */
    uint16_t handoff_timeout_ms;
    /** Commands older than this are rejected during authority transfer */
    uint16_t stale_command_threshold_ms;
} profinet_authority_config_t;

/**
 * profinet configuration
 * Network interface for PROFINET communication (auto-detect if...
 */
typedef struct {
    /** Authority handoff protocol settings */
    profinet_authority_config_t authority;
    /** Controller identity settings */
    profinet_controller_config_t controller;
    /** PROFINET cycle time (minimum 31.25us, typically 1ms for RT Class 1) */
    uint32_t cycle_time_us;
    /** DCP discovery settings */
    profinet_discovery_config_t discovery;
    /** Network interface for PROFINET communication (auto-detect if empty) */
    char interface[32];
    /** PROFINET stack limits */
    profinet_limits_config_t limits;
    /** Reduction ratio for actual cycle time */
    uint16_t reduction_ratio;
    /** Send clock factor (32 = 1ms base cycle) */
    uint8_t send_clock_factor;
    /** Socket priority for QoS (0-7, 6 recommended for RT) */
    uint8_t socket_priority;
    /** Timing and watchdog settings */
    profinet_timing_config_t timing;
    /** Use raw sockets for RT frames (requires CAP_NET_RAW) */
    bool use_raw_sockets;
} profinet_config_t;

/* ========== Web API and HMI Configuration ========== */

/**
 * api configuration
 * API server bind address...
 */
typedef struct {
    /** Run API only (no UI serving) */
    bool api_only;
    /** Comma-separated list of allowed CORS origins */
    char cors_origins[256];
    /** Enable API debug mode */
    bool debug;
    /** API server bind address */
    char host[256];
    /** API server port */
    uint16_t port;
    /** Number of API worker processes */
    uint8_t workers;
} web_api_config_t;

/**
 * ui configuration
 * UI server port (when running separately)...
 */
typedef struct {
    /** API URL for UI to connect to */
    char api_url[256];
    /** Static UI distribution directory */
    char dist_dir[256];
    /** UI server port (when running separately) */
    uint16_t port;
} web_ui_config_t;

/**
 * timeouts configuration
 * Command execution timeout...
 */
typedef struct {
    /** Command execution timeout */
    uint16_t command_ms;
    /** Database query timeout */
    uint16_t db_query_ms;
    /** PROFINET DCP discovery timeout */
    uint16_t dcp_discovery_ms;
} web_timeouts_config_t;

/**
 * websocket configuration
 * Base reconnection interval (exponential backoff)...
 */
typedef struct {
    /** WebSocket heartbeat interval */
    uint16_t heartbeat_interval_ms;
    /** Base reconnection interval (exponential backoff) */
    uint16_t reconnect_base_ms;
    /** Maximum reconnection attempts */
    uint8_t reconnect_max_attempts;
} web_websocket_config_t;

/**
 * polling configuration
 * Default polling interval...
 */
typedef struct {
    /** Default polling interval */
    uint16_t default_interval_ms;
    /** Reduced polling interval when many RTUs */
    uint32_t many_rtus_interval_ms;
    /** RTU count to trigger reduced polling */
    uint8_t many_rtus_threshold;
} web_polling_config_t;

/**
 * circuit_breaker configuration
 * Failures before opening circuit...
 */
typedef struct {
    /** Failures before opening circuit */
    uint8_t failure_threshold;
    /** Time before attempting reset */
    uint16_t reset_timeout_seconds;
    /** Successes required to close circuit */
    uint8_t success_threshold;
} web_circuit_breaker_config_t;

/**
 * authentication configuration
 * Enable authentication...
 */
typedef struct {
    /** Active Directory domain */
    char ad_domain[256];
    /** Enable Active Directory authentication */
    bool ad_enabled;
    /** Active Directory server */
    char ad_server[256];
    /** Enable authentication */
    bool enabled;
    /** Maximum concurrent sessions per user */
    uint8_t max_sessions_per_user;
    /** Session timeout */
    uint16_t session_timeout_minutes;
} web_authentication_config_t;

/**
 * security configuration
 * API rate limit per IP...
 */
typedef struct {
    /** Enable CSRF protection */
    bool csrf_enabled;
    /** API rate limit per IP */
    uint16_t rate_limit_requests_per_minute;
    /** Use secure cookies (HTTPS only) */
    bool secure_cookies;
} web_security_config_t;

/**
 * web configuration
 * FastAPI backend configuration...
 */
typedef struct {
    /** FastAPI backend configuration */
    web_api_config_t api;
    /** Authentication configuration */
    web_authentication_config_t authentication;
    /** Circuit breaker for API resilience */
    web_circuit_breaker_config_t circuit_breaker;
    /** Fallback polling configuration (when WebSocket unavailable) */
    web_polling_config_t polling;
    /** Security settings */
    web_security_config_t security;
    /** API timeout configuration */
    web_timeouts_config_t timeouts;
    /** Web UI configuration */
    web_ui_config_t ui;
    /** WebSocket streaming configuration */
    web_websocket_config_t websocket;
} web_config_t;


#ifdef __cplusplus
}
#endif

#endif /* WTC_GENERATED_CONFIG_TYPES_H */
