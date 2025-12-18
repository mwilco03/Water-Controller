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
#define WTC_SHM_VERSION     1
#define WTC_MAX_SHM_RTUS    64
#define WTC_MAX_SHM_ALARMS  256
#define WTC_MAX_SHM_SENSORS 32
#define WTC_MAX_SHM_ACTUATORS 32

/* Shared memory RTU data (simplified for IPC) */
typedef struct {
    char station_name[64];
    char ip_address[16];
    uint16_t vendor_id;
    uint16_t device_id;
    int connection_state;
    int slot_count;

    /* Sensor data */
    struct {
        int slot;
        float value;
        int status;
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

/* Command structure for write operations */
typedef struct {
    uint32_t sequence;
    int command_type;
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
    };
} shm_command_t;

/* Command types */
#define SHM_CMD_NONE            0
#define SHM_CMD_ACTUATOR        1
#define SHM_CMD_SETPOINT        2
#define SHM_CMD_PID_MODE        3
#define SHM_CMD_ACK_ALARM       4
#define SHM_CMD_RESET_INTERLOCK 5

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

    /* Mutex for synchronization */
    pthread_mutex_t lock;
} wtc_shared_memory_t;

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

/* Update shared memory (call periodically) */
wtc_result_t ipc_server_update(ipc_server_t *server);

/* Process incoming commands */
wtc_result_t ipc_server_process_commands(ipc_server_t *server);

/* Get shared memory pointer (for direct access) */
wtc_shared_memory_t *ipc_server_get_shm(ipc_server_t *server);

#ifdef __cplusplus
}
#endif

#endif /* WTC_IPC_SERVER_H */
