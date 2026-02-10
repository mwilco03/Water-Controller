/*
 * Water Treatment Controller - IPC Server
 * Provides shared memory interface for Python API
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_IPC_SERVER_H
#define WTC_IPC_SERVER_H

#include "types.h"
#include <pthread.h>

#ifdef __cplusplus
extern "C" {
#endif

/* IPC shared memory key */
#define WTC_SHM_KEY         0x57544301  /* "WTC\1" */
#define WTC_SHM_VERSION     3           /* Increment on breaking changes - v3 adds correlation_id */
#define WTC_MAX_SHM_RTUS    64
#define WTC_MAX_SHM_ALARMS  256
#define WTC_MAX_SHM_SENSORS 32
#define WTC_MAX_SHM_ACTUATORS 32

/* Protocol version for compatibility checking */
#define WTC_PROTOCOL_VERSION_MAJOR 1
#define WTC_PROTOCOL_VERSION_MINOR 0
#define WTC_PROTOCOL_VERSION ((WTC_PROTOCOL_VERSION_MAJOR << 8) | WTC_PROTOCOL_VERSION_MINOR)

/* Capability flags */
#define WTC_CAP_AUTHORITY_HANDOFF   (1 << 0)
#define WTC_CAP_STATE_RECONCILE     (1 << 1)
#define WTC_CAP_5BYTE_SENSOR        (1 << 2)
#define WTC_CAP_ALARM_ISA18         (1 << 3)

/* Shared memory RTU data (simplified for IPC) */
typedef struct {
    char station_name[64];
    char ip_address[16];
    uint16_t vendor_id;
    uint16_t device_id;
    int connection_state;
    int slot_count;

    /* Sensor data - 5-byte format with quality */
    struct {
        int slot;
        float value;
        int status;           /* IOPS status */
        uint8_t quality;      /* Data quality (OPC UA compatible: 0x00=GOOD, 0x40=UNCERTAIN, 0x80=BAD, 0xC0=NOT_CONNECTED) */
        uint64_t timestamp_ms;
    } sensors[WTC_MAX_SHM_SENSORS];
    int sensor_count;

    /* Actuator data */
    struct {
        int slot;
        uint8_t command;
        uint8_t pwm_duty;
        bool forced;
    } actuators[WTC_MAX_SHM_ACTUATORS];
    int actuator_count;

    /* Statistics */
    float packet_loss_percent;
    uint64_t total_cycles;
} shm_rtu_t;

/* Shared memory alarm data */
typedef struct {
    int alarm_id;
    int rule_id;
    char rtu_station[64];
    int slot;
    int severity;
    int state;
    char message[256];
    float value;
    float threshold;
    uint64_t raise_time_ms;
    uint64_t ack_time_ms;
    char ack_user[64];
} shm_alarm_t;

/* Shared memory PID loop data */
typedef struct {
    int loop_id;
    char name[64];
    bool enabled;
    char input_rtu[64];
    int input_slot;
    char output_rtu[64];
    int output_slot;
    float kp, ki, kd;
    float setpoint;
    float pv;
    float cv;
    int mode;
} shm_pid_loop_t;

/* Discovery result structures */
typedef struct {
    char station_name[64];
    char ip_address[16];
    char mac_address[18];
    uint16_t vendor_id;
    uint16_t device_id;
    bool reachable;
} shm_discovered_device_t;

typedef struct {
    uint8_t address;
    uint16_t device_type;
    char description[64];
} shm_i2c_device_t;

typedef struct {
    uint8_t rom_code[8];
    uint8_t family_code;
    char description[64];
} shm_onewire_device_t;

/* User sync constants - must be defined before use in structs */
/* IPC buffer can hold more users than RTU (32 vs 16) - controller truncates when sending */
#define IPC_USER_SYNC_MAX_USERS     32

/* Correlation ID for distributed tracing */
#define WTC_CORRELATION_ID_LEN 37  /* UUID format + null terminator */

/* Command structure for write operations */
typedef struct {
    uint32_t sequence;
    int command_type;
    char correlation_id[WTC_CORRELATION_ID_LEN];  /* For distributed tracing */
    union {
        struct {
            char rtu_station[64];
            int slot;
            uint8_t command;
            uint8_t pwm_duty;
        } actuator_cmd;
        struct {
            int loop_id;
            float setpoint;
        } setpoint_cmd;
        struct {
            int loop_id;
            int mode;
        } mode_cmd;
        struct {
            int alarm_id;
            char user[64];
        } ack_cmd;
        struct {
            int interlock_id;
        } reset_cmd;
        struct {
            char station_name[64];
            char ip_address[16];
            uint16_t vendor_id;
            uint16_t device_id;
        } add_rtu_cmd;
        struct {
            char station_name[64];
        } remove_rtu_cmd;
        struct {
            char station_name[64];
        } connect_rtu_cmd;
        struct {
            char station_name[64];
        } disconnect_rtu_cmd;
        struct {
            char network_interface[32];
            uint32_t timeout_ms;
        } dcp_discover_cmd;
        struct {
            char rtu_station[64];
            int bus_number;
        } i2c_discover_cmd;
        struct {
            char rtu_station[64];
            int bus_number;
        } onewire_discover_cmd;
        struct {
            char rtu_station[64];
            int slot;
            int slot_type;
            char name[64];
            char unit[16];
            int measurement_type;
            int actuator_type;
        } configure_slot_cmd;
        struct {
            char station_name[64];   /* Target RTU (empty = all RTUs) */
            uint32_t user_count;
            struct {
                char username[32];
                char password_hash[64];
                uint8_t role;        /* 0=viewer, 1=operator, 2=engineer, 3=admin */
                uint8_t flags;       /* Bit 0: active, Bit 1: synced_from_controller */
            } users[IPC_USER_SYNC_MAX_USERS];
        } user_sync_cmd;
    };
} shm_command_t;

/* Command types */
#define SHM_CMD_NONE            0
#define SHM_CMD_ACTUATOR        1
#define SHM_CMD_SETPOINT        2
#define SHM_CMD_PID_MODE        3
#define SHM_CMD_ACK_ALARM       4
#define SHM_CMD_RESET_INTERLOCK 5
#define SHM_CMD_ADD_RTU         6
#define SHM_CMD_REMOVE_RTU      7
#define SHM_CMD_CONNECT_RTU     8
#define SHM_CMD_DISCONNECT_RTU  9
#define SHM_CMD_DCP_DISCOVER    10
#define SHM_CMD_I2C_DISCOVER    11
#define SHM_CMD_ONEWIRE_DISCOVER 12
#define SHM_CMD_CONFIGURE_SLOT  13
#define SHM_CMD_USER_SYNC       14
#define SHM_CMD_USER_SYNC_ALL   15

/* Discovery result limits */
#define WTC_MAX_DISCOVERY_DEVICES 32
#define WTC_MAX_I2C_DEVICES       16
#define WTC_MAX_ONEWIRE_DEVICES   16

/* Main shared memory structure */
typedef struct {
    /* Header */
    uint32_t magic;
    uint32_t version;
    uint64_t last_update_ms;
    bool controller_running;

    /* System status */
    int total_rtus;
    int connected_rtus;
    int active_alarms;
    int unack_alarms;

    /* RTU data */
    shm_rtu_t rtus[WTC_MAX_SHM_RTUS];
    int rtu_count;

    /* Alarm data */
    shm_alarm_t alarms[WTC_MAX_SHM_ALARMS];
    int alarm_count;

    /* PID loops */
    shm_pid_loop_t pid_loops[64];
    int pid_loop_count;

    /* Command queue (API -> Controller) */
    shm_command_t command;
    uint32_t command_sequence;
    uint32_t command_ack;

    /* Command result (Controller -> API) */
    int command_result;          /* 0 = success, negative = error */
    char command_error_msg[256]; /* Error message if any */

    /* Discovery results (populated by controller after discovery commands) */
    shm_discovered_device_t discovered_devices[WTC_MAX_DISCOVERY_DEVICES];
    int discovered_device_count;
    bool discovery_in_progress;
    bool discovery_complete;

    /* I2C discovery results */
    shm_i2c_device_t i2c_devices[WTC_MAX_I2C_DEVICES];
    int i2c_device_count;
    bool i2c_discovery_complete;

    /* 1-Wire discovery results */
    shm_onewire_device_t onewire_devices[WTC_MAX_ONEWIRE_DEVICES];
    int onewire_device_count;
    bool onewire_discovery_complete;

    /* Event notification queue (Controller -> API for WebSocket broadcast) */
    #define WTC_MAX_NOTIFICATIONS 32
    struct {
        int event_type;      /* 0=none, 1=RTU offline, 2=RTU online, 3=alarm, 4=config change */
        char station_name[64];
        char message[256];
        uint64_t timestamp_ms;
    } notifications[WTC_MAX_NOTIFICATIONS];
    int notification_write_idx;  /* Next write position (circular buffer) */
    int notification_read_idx;   /* Next read position for API */

    /* Mutex for synchronization */
    pthread_mutex_t lock;
} wtc_shared_memory_t;

/* Event types for notifications */
#define WTC_EVENT_NONE          0
#define WTC_EVENT_RTU_OFFLINE   1
#define WTC_EVENT_RTU_ONLINE    2
#define WTC_EVENT_ALARM         3
#define WTC_EVENT_CONFIG_CHANGE 4

/* IPC server handle */
typedef struct ipc_server ipc_server_t;

/* Initialize IPC server */
wtc_result_t ipc_server_init(ipc_server_t **server);

/* Cleanup IPC server */
void ipc_server_cleanup(ipc_server_t *server);

/* Start IPC server */
wtc_result_t ipc_server_start(ipc_server_t *server);

/* Stop IPC server */
wtc_result_t ipc_server_stop(ipc_server_t *server);

/* Set registry for data access */
struct rtu_registry;
wtc_result_t ipc_server_set_registry(ipc_server_t *server,
                                      struct rtu_registry *registry);

/* Set alarm manager */
struct alarm_manager;
wtc_result_t ipc_server_set_alarm_manager(ipc_server_t *server,
                                           struct alarm_manager *alarms);

/* Set control engine */
struct control_engine;
wtc_result_t ipc_server_set_control_engine(ipc_server_t *server,
                                            struct control_engine *control);

/* Set PROFINET controller */
struct profinet_controller;
wtc_result_t ipc_server_set_profinet(ipc_server_t *server,
                                      struct profinet_controller *profinet);

/* Set DCP discovery */
struct dcp_discovery;
wtc_result_t ipc_server_set_dcp(ipc_server_t *server,
                                 struct dcp_discovery *dcp);

/* Set user sync manager (for caching users on auto-sync) */
struct user_sync_manager;
wtc_result_t ipc_server_set_user_sync(ipc_server_t *server,
                                       struct user_sync_manager *user_sync);

/* Update shared memory (call periodically) */
wtc_result_t ipc_server_update(ipc_server_t *server);

/* Process incoming commands */
wtc_result_t ipc_server_process_commands(ipc_server_t *server);

/* Get shared memory pointer (for direct access) */
wtc_shared_memory_t *ipc_server_get_shm(ipc_server_t *server);

/* Post event notification (for WebSocket broadcast by API) */
wtc_result_t ipc_server_post_notification(ipc_server_t *server,
                                           int event_type,
                                           const char *station_name,
                                           const char *message);

#ifdef __cplusplus
}
#endif

#endif /* WTC_IPC_SERVER_H */
