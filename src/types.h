/*
 * Water Treatment Controller - Core Type Definitions
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_TYPES_H
#define WTC_TYPES_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Version information */
#define WTC_VERSION_MAJOR 0
#define WTC_VERSION_MINOR 0
#define WTC_VERSION_PATCH 1
#define WTC_VERSION_STRING "0.0.1"

/* Maximum sizes */
#define WTC_MAX_STATION_NAME    64
#define WTC_MAX_IP_ADDRESS      16
#define WTC_MAX_NAME            64
#define WTC_MAX_UNIT            16
#define WTC_MAX_MESSAGE         256
#define WTC_MAX_USERNAME        64
#define WTC_MAX_RTUS            256
#define WTC_MAX_PID_LOOPS       64
#define WTC_MAX_INTERLOCKS      128
#define WTC_MAX_SEQUENCES       32
#define WTC_MAX_ALARM_RULES     512
#define WTC_MAX_HISTORIAN_TAGS  1024

/* Default slot counts (can be overridden per-device) */
#define WTC_DEFAULT_SLOTS       64
#define WTC_DEFAULT_SENSORS     32
#define WTC_DEFAULT_ACTUATORS   32

/* Max slots for fixed-size arrays in configuration structs */
#define WTC_MAX_SLOTS           256

/* Return codes */
typedef enum {
    WTC_OK = 0,
    WTC_ERROR = -1,
    WTC_ERROR_INVALID_PARAM = -2,
    WTC_ERROR_NO_MEMORY = -3,
    WTC_ERROR_NOT_FOUND = -4,
    WTC_ERROR_TIMEOUT = -5,
    WTC_ERROR_BUSY = -6,
    WTC_ERROR_NOT_INITIALIZED = -7,
    WTC_ERROR_ALREADY_EXISTS = -8,
    WTC_ERROR_CONNECTION_FAILED = -9,
    WTC_ERROR_IO = -10,
    WTC_ERROR_PROTOCOL = -11,
    WTC_ERROR_PERMISSION = -12,
    WTC_ERROR_FULL = -13,
    WTC_ERROR_EMPTY = -14,
    WTC_ERROR_INTERNAL = -15,
    WTC_ERROR_NOT_CONNECTED = -16,
} wtc_result_t;

/* PROFINET connection states */
typedef enum {
    PROFINET_STATE_OFFLINE = 0,
    PROFINET_STATE_DISCOVERY,
    PROFINET_STATE_CONNECTING,
    PROFINET_STATE_CONNECTED,
    PROFINET_STATE_RUNNING,
    PROFINET_STATE_ERROR,
    PROFINET_STATE_DISCONNECT,
} profinet_state_t;

/* Slot types */
typedef enum {
    SLOT_TYPE_DAP = 0,
    SLOT_TYPE_SENSOR,
    SLOT_TYPE_ACTUATOR,
} slot_type_t;

/* Measurement types */
typedef enum {
    MEASUREMENT_PH = 0,
    MEASUREMENT_TEMPERATURE,
    MEASUREMENT_TURBIDITY,
    MEASUREMENT_TDS,
    MEASUREMENT_DISSOLVED_OXYGEN,
    MEASUREMENT_FLOW_RATE,
    MEASUREMENT_LEVEL,
    MEASUREMENT_PRESSURE,
    MEASUREMENT_CONDUCTIVITY,
    MEASUREMENT_ORP,
    MEASUREMENT_CHLORINE,
    MEASUREMENT_CUSTOM,
} measurement_type_t;

/* Actuator types */
typedef enum {
    ACTUATOR_RELAY = 0,
    ACTUATOR_PWM,
    ACTUATOR_PUMP,
    ACTUATOR_VALVE,
    ACTUATOR_LATCHING,
    ACTUATOR_MOMENTARY,
} actuator_type_t;

/* Actuator commands */
typedef enum {
    ACTUATOR_CMD_OFF = 0x00,
    ACTUATOR_CMD_ON = 0x01,
    ACTUATOR_CMD_PWM = 0x02,
} actuator_cmd_t;

/* I/O Provider Status (IOPS) */
typedef enum {
    IOPS_BAD = 0x00,
    IOPS_GOOD = 0x80,
} iops_t;

/* Data Quality (OPC UA compatible)
 * Extracted from 5-byte sensor data format:
 * Bytes 0-3: Float32 value (big-endian)
 * Byte 4:    Quality indicator
 */
typedef enum {
    QUALITY_GOOD          = 0x00,
    QUALITY_UNCERTAIN     = 0x40,
    QUALITY_BAD           = 0x80,
    QUALITY_NOT_CONNECTED = 0xC0,
} data_quality_t;

/* Sensor reading with quality (5-byte format) */
typedef struct {
    float value;
    data_quality_t quality;
    uint64_t timestamp_us;
} sensor_reading_t;

/* PID mode */
typedef enum {
    PID_MODE_OFF = 0,
    PID_MODE_MANUAL,
    PID_MODE_AUTO,
    PID_MODE_CASCADE,
} pid_mode_t;

/* Interlock conditions */
typedef enum {
    INTERLOCK_CONDITION_ABOVE = 0,
    INTERLOCK_CONDITION_BELOW,
    INTERLOCK_CONDITION_EQUAL,
    INTERLOCK_CONDITION_NOT_EQUAL,
} interlock_condition_t;

/* Interlock actions */
typedef enum {
    INTERLOCK_ACTION_ALARM_ONLY = 0,
    INTERLOCK_ACTION_FORCE_OFF,
    INTERLOCK_ACTION_FORCE_ON,
    INTERLOCK_ACTION_SET_VALUE,
} interlock_action_t;

/* Alarm severity (ISA-18.2) */
typedef enum {
    ALARM_SEVERITY_LOW = 1,
    ALARM_SEVERITY_MEDIUM = 2,
    ALARM_SEVERITY_HIGH = 3,
    ALARM_SEVERITY_EMERGENCY = 4,
} alarm_severity_t;

/* Alarm states */
typedef enum {
    ALARM_STATE_CLEARED = 0,
    ALARM_STATE_ACTIVE_UNACK,
    ALARM_STATE_ACTIVE_ACK,
    ALARM_STATE_CLEARED_UNACK,
} alarm_state_t;

/* Alarm conditions */
typedef enum {
    ALARM_CONDITION_HIGH = 0,
    ALARM_CONDITION_LOW,
    ALARM_CONDITION_HIGH_HIGH,
    ALARM_CONDITION_LOW_LOW,
    ALARM_CONDITION_RATE_OF_CHANGE,
    ALARM_CONDITION_DEVIATION,
    ALARM_CONDITION_BAD_QUALITY,
} alarm_condition_t;

/* Compression algorithms */
typedef enum {
    COMPRESSION_NONE = 0,
    COMPRESSION_SWINGING_DOOR,
    COMPRESSION_BOXCAR,
    COMPRESSION_DEADBAND,
} compression_t;

/* Sequence states */
typedef enum {
    SEQUENCE_STATE_IDLE = 0,
    SEQUENCE_STATE_RUNNING,
    SEQUENCE_STATE_PAUSED,
    SEQUENCE_STATE_COMPLETE,
    SEQUENCE_STATE_FAULTED,
    SEQUENCE_STATE_ABORTED,
} sequence_state_t;

/* User roles */
typedef enum {
    USER_ROLE_VIEWER = 0,
    USER_ROLE_OPERATOR,
    USER_ROLE_ENGINEER,
    USER_ROLE_ADMIN,
} user_role_t;

/* Failover modes */
typedef enum {
    FAILOVER_MODE_MANUAL = 0,
    FAILOVER_MODE_AUTO,
    FAILOVER_MODE_HOT_STANDBY,
} failover_mode_t;

/* Control authority states - defines who has control of actuators
 * This implements the formal authority handoff protocol to prevent
 * split-brain scenarios between Controller and RTU.
 */
typedef enum {
    AUTHORITY_AUTONOMOUS = 0,    /* RTU is operating independently (no controller) */
    AUTHORITY_HANDOFF_PENDING,   /* Controller requesting authority transfer */
    AUTHORITY_SUPERVISED,        /* Controller has authority, RTU executes commands */
    AUTHORITY_RELEASING,         /* Controller releasing authority back to RTU */
} authority_state_t;

/* Authority handoff context - tracks control ownership between Controller and RTU */
typedef struct {
    uint32_t epoch;              /* Authority epoch - incremented on each handoff */
    authority_state_t state;     /* Current authority state */
    uint64_t request_time_ms;    /* When authority was requested */
    uint64_t grant_time_ms;      /* When authority was granted */
    char holder[WTC_MAX_STATION_NAME];  /* Current authority holder (controller station) */
    bool controller_online;      /* Controller connectivity status */
    bool rtu_acknowledged;       /* RTU acknowledged handoff */
    uint32_t stale_command_threshold_ms; /* Commands older than this are rejected */
} authority_context_t;

/* Log levels */
typedef enum {
    LOG_LEVEL_TRACE = 0,
    LOG_LEVEL_DEBUG,
    LOG_LEVEL_INFO,
    LOG_LEVEL_WARN,
    LOG_LEVEL_ERROR,
    LOG_LEVEL_FATAL,
} log_level_t;

/* ============== Data Structures ============== */

/* Sensor input data (from RTU)
 * Extended to support 5-byte sensor format with quality byte
 */
typedef struct {
    float value;
    iops_t status;
    data_quality_t quality;      /* Application-level quality from 5-byte format */
    uint64_t timestamp_ms;
    bool stale;
} sensor_data_t;

/* Actuator output data (to RTU) */
typedef struct __attribute__((packed)) {
    uint8_t command;
    uint8_t pwm_duty;
    uint8_t reserved[2];
} actuator_output_t;

/* Actuator state (runtime) */
typedef struct {
    actuator_output_t output;
    bool forced;
    uint64_t last_change_ms;
    uint64_t total_on_time_ms;
    uint32_t cycle_count;
} actuator_state_t;

/* Slot configuration */
typedef struct {
    int slot;
    int subslot;
    slot_type_t type;
    char name[WTC_MAX_NAME];
    char unit[WTC_MAX_UNIT];
    measurement_type_t measurement_type;
    actuator_type_t actuator_type;
    float scale_min;
    float scale_max;
    float alarm_low;
    float alarm_high;
    float alarm_low_low;
    float alarm_high_high;
    float warning_low;
    float warning_high;
    float deadband;
    bool enabled;
} slot_config_t;

/* RTU device */
typedef struct {
    int id;
    char station_name[WTC_MAX_STATION_NAME];
    char ip_address[WTC_MAX_IP_ADDRESS];
    uint16_t vendor_id;
    uint16_t device_id;
    profinet_state_t connection_state;
    uint64_t last_seen_ms;

    /* Slot configuration - dynamically allocated */
    slot_config_t *slots;
    int slot_count;
    int slot_capacity;  /* Allocated capacity */

    /* Runtime data - dynamically allocated */
    sensor_data_t *sensors;
    int sensor_count;
    int sensor_capacity;

    actuator_state_t *actuators;
    int actuator_count;
    int actuator_capacity;

    /* Health metrics */
    int failed_cycles;
    float packet_loss_percent;
    uint64_t total_cycles;
    uint64_t good_cycles;
    uint32_t reconnect_count;

    /* Authority tracking - who has control of this RTU */
    authority_context_t authority;

    /* Internal */
    void *profinet_handle;
    bool config_dirty;
} rtu_device_t;

/* PID loop configuration */
typedef struct {
    int loop_id;
    char name[WTC_MAX_NAME];
    bool enabled;

    /* Input (PV) */
    char input_rtu[WTC_MAX_STATION_NAME];
    int input_slot;

    /* Output (CV) */
    char output_rtu[WTC_MAX_STATION_NAME];
    int output_slot;

    /* Tuning parameters */
    float kp;
    float ki;
    float kd;
    float setpoint;
    float output_min;
    float output_max;
    float deadband;
    float integral_limit;
    float derivative_filter;

    /* Runtime */
    float pv;
    float cv;
    float error;
    float integral;
    float derivative;
    float last_error;
    pid_mode_t mode;
    uint64_t last_update_ms;
} pid_loop_t;

/* Interlock configuration */
typedef struct {
    int interlock_id;
    char name[WTC_MAX_NAME];
    bool enabled;

    /* Condition */
    char condition_rtu[WTC_MAX_STATION_NAME];
    int condition_slot;
    interlock_condition_t condition;
    float threshold;
    uint32_t delay_ms;

    /* Action */
    char action_rtu[WTC_MAX_STATION_NAME];
    int action_slot;
    interlock_action_t action;
    float action_value;

    /* Runtime */
    bool tripped;
    uint64_t trip_time_ms;
    uint64_t condition_start_ms;
} interlock_t;

/* Alarm rule */
typedef struct {
    int rule_id;
    char name[WTC_MAX_NAME];
    bool enabled;

    /* Source */
    char rtu_station[WTC_MAX_STATION_NAME];
    int slot;

    /* Condition */
    alarm_condition_t condition;
    float threshold;
    uint32_t delay_ms;

    /* Properties */
    alarm_severity_t severity;
    char message_template[WTC_MAX_MESSAGE];

    /* Runtime */
    bool active;
    uint64_t condition_start_ms;
} alarm_rule_t;

/* Alarm instance */
typedef struct {
    int alarm_id;
    int rule_id;
    char rtu_station[WTC_MAX_STATION_NAME];
    int slot;
    alarm_severity_t severity;
    alarm_state_t state;

    char message[WTC_MAX_MESSAGE];
    float value;
    float threshold;

    uint64_t raise_time_ms;
    uint64_t ack_time_ms;
    uint64_t clear_time_ms;
    char ack_user[WTC_MAX_USERNAME];
} alarm_t;

/* Historian tag */
typedef struct {
    int tag_id;
    char rtu_station[WTC_MAX_STATION_NAME];
    int slot;
    char tag_name[WTC_MAX_NAME * 2];
    char unit[WTC_MAX_UNIT];

    int sample_rate_ms;
    float deadband;
    compression_t compression;

    /* Statistics */
    uint64_t total_samples;
    uint64_t compressed_samples;
    float compression_ratio;
    float last_value;
    uint64_t last_sample_ms;
} historian_tag_t;

/* Historian sample */
typedef struct {
    uint64_t timestamp_ms;
    int tag_id;
    float value;
    uint8_t quality;
} historian_sample_t;

/* Cycle statistics */
typedef struct {
    uint64_t cycle_count;
    uint64_t cycle_time_us_min;
    uint64_t cycle_time_us_max;
    uint64_t cycle_time_us_avg;
    uint64_t overruns;
    float cpu_usage_percent;
} cycle_stats_t;

/* Alarm statistics */
typedef struct {
    uint32_t total_alarms;
    uint32_t active_alarms;
    uint32_t unack_alarms;
    uint32_t alarms_per_hour;
    uint64_t avg_ack_time_ms;
    uint64_t avg_clear_time_ms;
} alarm_stats_t;

/* User */
typedef struct {
    int user_id;
    char username[WTC_MAX_USERNAME];
    char password_hash[256];
    user_role_t role;
    uint64_t created_at_ms;
    uint64_t last_login_ms;
    bool active;
} user_t;

/* Callback types */
typedef void (*alarm_callback_t)(const alarm_t *alarm, void *ctx);
typedef void (*rtu_callback_t)(const rtu_device_t *rtu, void *ctx);
typedef void (*data_callback_t)(const char *station, int slot, float value, void *ctx);

#ifdef __cplusplus
}
#endif

#endif /* WTC_TYPES_H */
