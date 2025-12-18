/*
 * Water Treatment Controller - IPC Server Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "ipc_server.h"
#include "rtu_registry.h"
#include "alarm_manager.h"
#include "control_engine.h"
#include "logger.h"
#include "time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <pthread.h>

#define LOG_TAG "IPC"
#define SHM_NAME "/wtc_shared_memory"

/* IPC server structure */
struct ipc_server {
    int shm_fd;
    wtc_shared_memory_t *shm;
    bool running;

    struct rtu_registry *registry;
    struct alarm_manager *alarms;
    struct control_engine *control;

    uint32_t last_command_seq;
};

/* Initialize IPC server */
wtc_result_t ipc_server_init(ipc_server_t **server) {
    if (!server) return WTC_ERROR_INVALID_PARAM;

    ipc_server_t *srv = calloc(1, sizeof(ipc_server_t));
    if (!srv) {
        return WTC_ERROR_NO_MEMORY;
    }

    /* Create shared memory */
    srv->shm_fd = shm_open(SHM_NAME, O_CREAT | O_RDWR, 0666);
    if (srv->shm_fd < 0) {
        LOG_ERROR(LOG_TAG, "Failed to create shared memory");
        free(srv);
        return WTC_ERROR_IO;
    }

    /* Set size */
    if (ftruncate(srv->shm_fd, sizeof(wtc_shared_memory_t)) < 0) {
        LOG_ERROR(LOG_TAG, "Failed to set shared memory size");
        close(srv->shm_fd);
        shm_unlink(SHM_NAME);
        free(srv);
        return WTC_ERROR_IO;
    }

    /* Map memory */
    srv->shm = mmap(NULL, sizeof(wtc_shared_memory_t),
                    PROT_READ | PROT_WRITE, MAP_SHARED, srv->shm_fd, 0);
    if (srv->shm == MAP_FAILED) {
        LOG_ERROR(LOG_TAG, "Failed to map shared memory");
        close(srv->shm_fd);
        shm_unlink(SHM_NAME);
        free(srv);
        return WTC_ERROR_IO;
    }

    /* Initialize shared memory */
    memset(srv->shm, 0, sizeof(wtc_shared_memory_t));
    srv->shm->magic = WTC_SHM_KEY;
    srv->shm->version = WTC_SHM_VERSION;

    /* Initialize mutex with process-shared attribute */
    pthread_mutexattr_t attr;
    pthread_mutexattr_init(&attr);
    pthread_mutexattr_setpshared(&attr, PTHREAD_PROCESS_SHARED);
    pthread_mutex_init(&srv->shm->lock, &attr);
    pthread_mutexattr_destroy(&attr);

    srv->running = false;

    LOG_INFO(LOG_TAG, "IPC server initialized (shm: %s)", SHM_NAME);
    *server = srv;
    return WTC_OK;
}

/* Cleanup IPC server */
void ipc_server_cleanup(ipc_server_t *server) {
    if (!server) return;

    if (server->shm) {
        pthread_mutex_destroy(&server->shm->lock);
        munmap(server->shm, sizeof(wtc_shared_memory_t));
    }

    if (server->shm_fd >= 0) {
        close(server->shm_fd);
        shm_unlink(SHM_NAME);
    }

    free(server);
    LOG_INFO(LOG_TAG, "IPC server cleaned up");
}

/* Start IPC server */
wtc_result_t ipc_server_start(ipc_server_t *server) {
    if (!server) return WTC_ERROR_INVALID_PARAM;
    server->running = true;
    server->shm->controller_running = true;
    LOG_INFO(LOG_TAG, "IPC server started");
    return WTC_OK;
}

/* Stop IPC server */
wtc_result_t ipc_server_stop(ipc_server_t *server) {
    if (!server) return WTC_ERROR_INVALID_PARAM;
    server->running = false;
    server->shm->controller_running = false;
    LOG_INFO(LOG_TAG, "IPC server stopped");
    return WTC_OK;
}

/* Set registry */
wtc_result_t ipc_server_set_registry(ipc_server_t *server,
                                      struct rtu_registry *registry) {
    if (!server) return WTC_ERROR_INVALID_PARAM;
    server->registry = registry;
    return WTC_OK;
}

/* Set alarm manager */
wtc_result_t ipc_server_set_alarm_manager(ipc_server_t *server,
                                           struct alarm_manager *alarms) {
    if (!server) return WTC_ERROR_INVALID_PARAM;
    server->alarms = alarms;
    return WTC_OK;
}

/* Set control engine */
wtc_result_t ipc_server_set_control_engine(ipc_server_t *server,
                                            struct control_engine *control) {
    if (!server) return WTC_ERROR_INVALID_PARAM;
    server->control = control;
    return WTC_OK;
}

/* Update RTU data in shared memory */
static void update_rtu_data(ipc_server_t *server) {
    if (!server->registry) return;

    rtu_device_t *devices = NULL;
    int count = 0;

    if (rtu_registry_list_devices(server->registry, &devices, &count,
                                   WTC_MAX_SHM_RTUS) != WTC_OK) {
        return;
    }

    server->shm->rtu_count = count;
    server->shm->total_rtus = count;
    server->shm->connected_rtus = 0;

    for (int i = 0; i < count && i < WTC_MAX_SHM_RTUS; i++) {
        shm_rtu_t *shm_rtu = &server->shm->rtus[i];
        rtu_device_t *rtu = &devices[i];

        strncpy(shm_rtu->station_name, rtu->station_name, 63);
        strncpy(shm_rtu->ip_address, rtu->ip_address, 15);
        shm_rtu->vendor_id = rtu->vendor_id;
        shm_rtu->device_id = rtu->device_id;
        shm_rtu->connection_state = rtu->connection_state;
        shm_rtu->slot_count = rtu->slot_count;
        shm_rtu->packet_loss_percent = rtu->packet_loss_percent;
        shm_rtu->total_cycles = rtu->total_cycles;

        if (rtu->connection_state == PROFINET_STATE_RUNNING) {
            server->shm->connected_rtus++;
        }

        /* Copy sensor data */
        shm_rtu->sensor_count = rtu->sensor_count;
        for (int j = 0; j < rtu->sensor_count && j < WTC_MAX_SHM_SENSORS; j++) {
            shm_rtu->sensors[j].slot = j;
            shm_rtu->sensors[j].value = rtu->sensors[j].value;
            shm_rtu->sensors[j].status = rtu->sensors[j].status;
            shm_rtu->sensors[j].timestamp_ms = rtu->sensors[j].timestamp_ms;
        }

        /* Copy actuator data */
        shm_rtu->actuator_count = rtu->actuator_count;
        for (int j = 0; j < rtu->actuator_count && j < WTC_MAX_SHM_ACTUATORS; j++) {
            shm_rtu->actuators[j].slot = j;
            shm_rtu->actuators[j].command = rtu->actuators[j].output.command;
            shm_rtu->actuators[j].pwm_duty = rtu->actuators[j].output.pwm_duty;
            shm_rtu->actuators[j].forced = rtu->actuators[j].forced;
        }
    }

    free(devices);
}

/* Update alarm data in shared memory */
static void update_alarm_data(ipc_server_t *server) {
    if (!server->alarms) return;

    alarm_t *alarms = NULL;
    int count = 0;

    if (alarm_manager_get_active(server->alarms, &alarms, &count,
                                  WTC_MAX_SHM_ALARMS) != WTC_OK) {
        return;
    }

    server->shm->alarm_count = count;
    server->shm->active_alarms = count;
    server->shm->unack_alarms = 0;

    for (int i = 0; i < count && i < WTC_MAX_SHM_ALARMS; i++) {
        shm_alarm_t *shm_alarm = &server->shm->alarms[i];
        alarm_t *alarm = &alarms[i];

        shm_alarm->alarm_id = alarm->alarm_id;
        shm_alarm->rule_id = alarm->rule_id;
        strncpy(shm_alarm->rtu_station, alarm->rtu_station, 63);
        shm_alarm->slot = alarm->slot;
        shm_alarm->severity = alarm->severity;
        shm_alarm->state = alarm->state;
        strncpy(shm_alarm->message, alarm->message, 255);
        shm_alarm->value = alarm->value;
        shm_alarm->threshold = alarm->threshold;
        shm_alarm->raise_time_ms = alarm->raise_time_ms;
        shm_alarm->ack_time_ms = alarm->ack_time_ms;
        strncpy(shm_alarm->ack_user, alarm->ack_user, 63);

        if (alarm->state == ALARM_STATE_ACTIVE_UNACK ||
            alarm->state == ALARM_STATE_CLEARED_UNACK) {
            server->shm->unack_alarms++;
        }
    }

    free(alarms);
}

/* Update PID loop data in shared memory */
static void update_pid_data(ipc_server_t *server) {
    if (!server->control) return;

    pid_loop_t *loops = NULL;
    int count = 0;

    if (control_engine_list_pid_loops(server->control, &loops, &count, 64) != WTC_OK) {
        return;
    }

    server->shm->pid_loop_count = count;

    for (int i = 0; i < count && i < 64; i++) {
        shm_pid_loop_t *shm_loop = &server->shm->pid_loops[i];
        pid_loop_t *loop = &loops[i];

        shm_loop->loop_id = loop->loop_id;
        strncpy(shm_loop->name, loop->name, 63);
        shm_loop->enabled = loop->enabled;
        strncpy(shm_loop->input_rtu, loop->input_rtu, 63);
        shm_loop->input_slot = loop->input_slot;
        strncpy(shm_loop->output_rtu, loop->output_rtu, 63);
        shm_loop->output_slot = loop->output_slot;
        shm_loop->kp = loop->kp;
        shm_loop->ki = loop->ki;
        shm_loop->kd = loop->kd;
        shm_loop->setpoint = loop->setpoint;
        shm_loop->pv = loop->pv;
        shm_loop->cv = loop->cv;
        shm_loop->mode = loop->mode;
    }

    free(loops);
}

/* Update shared memory */
wtc_result_t ipc_server_update(ipc_server_t *server) {
    if (!server || !server->running) return WTC_ERROR_NOT_INITIALIZED;

    pthread_mutex_lock(&server->shm->lock);

    server->shm->last_update_ms = time_get_ms();

    update_rtu_data(server);
    update_alarm_data(server);
    update_pid_data(server);

    pthread_mutex_unlock(&server->shm->lock);

    return WTC_OK;
}

/* Process incoming commands */
wtc_result_t ipc_server_process_commands(ipc_server_t *server) {
    if (!server || !server->running) return WTC_ERROR_NOT_INITIALIZED;

    pthread_mutex_lock(&server->shm->lock);

    /* Check for new command */
    if (server->shm->command_sequence != server->last_command_seq &&
        server->shm->command.command_type != SHM_CMD_NONE) {

        shm_command_t *cmd = &server->shm->command;

        switch (cmd->command_type) {
            case SHM_CMD_ACTUATOR:
                if (server->registry) {
                    actuator_output_t output = {
                        .command = cmd->actuator_cmd.command,
                        .pwm_duty = cmd->actuator_cmd.pwm_duty,
                        .reserved = {0, 0}
                    };
                    rtu_registry_update_actuator(server->registry,
                                                  cmd->actuator_cmd.rtu_station,
                                                  cmd->actuator_cmd.slot,
                                                  &output);
                    LOG_DEBUG(LOG_TAG, "Actuator command: %s.%d = %d",
                              cmd->actuator_cmd.rtu_station,
                              cmd->actuator_cmd.slot,
                              cmd->actuator_cmd.command);
                }
                break;

            case SHM_CMD_SETPOINT:
                if (server->control) {
                    control_engine_set_setpoint(server->control,
                                                 cmd->setpoint_cmd.loop_id,
                                                 cmd->setpoint_cmd.setpoint);
                    LOG_DEBUG(LOG_TAG, "Setpoint command: loop %d = %.2f",
                              cmd->setpoint_cmd.loop_id,
                              cmd->setpoint_cmd.setpoint);
                }
                break;

            case SHM_CMD_PID_MODE:
                if (server->control) {
                    control_engine_set_pid_mode(server->control,
                                                 cmd->mode_cmd.loop_id,
                                                 cmd->mode_cmd.mode);
                    LOG_DEBUG(LOG_TAG, "PID mode command: loop %d = %d",
                              cmd->mode_cmd.loop_id,
                              cmd->mode_cmd.mode);
                }
                break;

            case SHM_CMD_ACK_ALARM:
                if (server->alarms) {
                    alarm_manager_acknowledge(server->alarms,
                                               cmd->ack_cmd.alarm_id,
                                               cmd->ack_cmd.user);
                    LOG_DEBUG(LOG_TAG, "Alarm ack command: alarm %d by %s",
                              cmd->ack_cmd.alarm_id,
                              cmd->ack_cmd.user);
                }
                break;

            case SHM_CMD_RESET_INTERLOCK:
                if (server->control) {
                    control_engine_reset_interlock(server->control,
                                                    cmd->reset_cmd.interlock_id);
                    LOG_DEBUG(LOG_TAG, "Interlock reset: %d",
                              cmd->reset_cmd.interlock_id);
                }
                break;
        }

        /* Acknowledge command */
        server->last_command_seq = server->shm->command_sequence;
        server->shm->command_ack = server->shm->command_sequence;
        server->shm->command.command_type = SHM_CMD_NONE;
    }

    pthread_mutex_unlock(&server->shm->lock);

    return WTC_OK;
}

/* Get shared memory pointer */
wtc_shared_memory_t *ipc_server_get_shm(ipc_server_t *server) {
    return server ? server->shm : NULL;
}
