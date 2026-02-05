/*
 * Water Treatment Controller - IPC Server Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "ipc_server.h"
#include "rtu_registry.h"
#include "alarm_manager.h"
#include "control_engine.h"
#include "dcp_discovery.h"
#include "profinet_controller.h"
#include "user/user_sync.h"
#include "logger.h"
#include "time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include <errno.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <pthread.h>
#include <arpa/inet.h>

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
    struct profinet_controller *profinet;
    struct dcp_discovery *dcp;

    uint32_t last_command_seq;

    /* Discovery timing */
    uint64_t discovery_start_ms;
    uint32_t discovery_timeout_ms;
};

/* Forward declarations for static helpers */
static void format_mac_address(const uint8_t *mac, char *str, size_t str_size);
static void format_ip_address(uint32_t ip, char *str, size_t str_size);

/* Initialize IPC server */
wtc_result_t ipc_server_init(ipc_server_t **server) {
    if (!server) return WTC_ERROR_INVALID_PARAM;

    ipc_server_t *srv = calloc(1, sizeof(ipc_server_t));
    if (!srv) {
        return WTC_ERROR_NO_MEMORY;
    }

    /* Create shared memory with permissions allowing API container access */
    /* 0666 allows read/write for all users (API runs as different uid in container) */
    srv->shm_fd = shm_open(SHM_NAME, O_CREAT | O_RDWR, 0666);
    if (srv->shm_fd < 0) {
        LOG_ERROR(LOG_TAG, "Failed to create shared memory");
        free(srv);
        return WTC_ERROR_IO;
    }

    /* Force permissions to 0666 - shm_open mode is affected by umask */
    if (fchmod(srv->shm_fd, 0666) < 0) {
        LOG_WARN(LOG_TAG, "Failed to set shared memory permissions: %s", strerror(errno));
        /* Continue anyway - may work if umask allows */
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
    LOG_INFO(LOG_TAG, "SHM size=%zu, command offset=%zu, command_sequence offset=%zu",
             sizeof(wtc_shared_memory_t),
             offsetof(wtc_shared_memory_t, command),
             offsetof(wtc_shared_memory_t, command_sequence));
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

/* Set PROFINET controller */
wtc_result_t ipc_server_set_profinet(ipc_server_t *server,
                                      struct profinet_controller *profinet) {
    if (!server) return WTC_ERROR_INVALID_PARAM;
    server->profinet = profinet;
    return WTC_OK;
}

/* Set DCP discovery */
wtc_result_t ipc_server_set_dcp(ipc_server_t *server,
                                 struct dcp_discovery *dcp) {
    if (!server) return WTC_ERROR_INVALID_PARAM;
    server->dcp = dcp;
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

        /* Copy sensor data with quality (5-byte format) */
        shm_rtu->sensor_count = rtu->sensor_count;
        for (int j = 0; j < rtu->sensor_count && j < WTC_MAX_SHM_SENSORS; j++) {
            shm_rtu->sensors[j].slot = j;
            shm_rtu->sensors[j].value = rtu->sensors[j].value;
            shm_rtu->sensors[j].status = rtu->sensors[j].status;
            shm_rtu->sensors[j].quality = rtu->sensors[j].quality;  /* OPC UA quality */
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

    /* Harvest DCP discovery results from PROFINET controller cache after timeout */
    if (server->shm->discovery_in_progress && server->profinet &&
        server->discovery_start_ms > 0) {
        uint64_t elapsed_ms = time_get_ms() - server->discovery_start_ms;
        if (elapsed_ms >= server->discovery_timeout_ms) {
            dcp_device_info_t devices[WTC_MAX_DISCOVERY_DEVICES];
            int count = 0;

            if (profinet_controller_get_discovered_devices(
                    server->profinet, devices, &count,
                    WTC_MAX_DISCOVERY_DEVICES) == WTC_OK) {
                server->shm->discovered_device_count = 0;
                for (int i = 0; i < count && i < WTC_MAX_DISCOVERY_DEVICES; i++) {
                    shm_discovered_device_t *shm_dev =
                        &server->shm->discovered_devices[i];

                    strncpy(shm_dev->station_name, devices[i].station_name, 63);
                    shm_dev->station_name[63] = '\0';
                    format_ip_address(devices[i].ip_address,
                                      shm_dev->ip_address,
                                      sizeof(shm_dev->ip_address));
                    format_mac_address(devices[i].mac_address,
                                       shm_dev->mac_address,
                                       sizeof(shm_dev->mac_address));
                    shm_dev->vendor_id = devices[i].vendor_id;
                    shm_dev->device_id = devices[i].device_id;
                    shm_dev->reachable = true;

                    server->shm->discovered_device_count++;
                }
                LOG_INFO(LOG_TAG, "DCP discovery complete: %d devices found", count);
            }

            server->shm->discovery_in_progress = false;
            server->shm->discovery_complete = true;
            server->discovery_start_ms = 0;
        }
    }

    pthread_mutex_unlock(&server->shm->lock);

    return WTC_OK;
}

/* Helper: Format MAC address to string */
static void format_mac_address(const uint8_t *mac, char *str, size_t str_size) {
    snprintf(str, str_size, "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

/* Helper: Format IP address to string */
static void format_ip_address(uint32_t ip, char *str, size_t str_size) {
    struct in_addr addr = { .s_addr = htonl(ip) };
    inet_ntop(AF_INET, &addr, str, str_size);
}

/* DCP discovery callback - populates shared memory discovery results */
static void dcp_discovery_callback(const dcp_device_info_t *device, void *ctx) {
    ipc_server_t *server = (ipc_server_t *)ctx;
    if (!server || !server->shm) return;

    pthread_mutex_lock(&server->shm->lock);

    int idx = server->shm->discovered_device_count;
    if (idx < WTC_MAX_DISCOVERY_DEVICES) {
        shm_discovered_device_t *shm_dev = &server->shm->discovered_devices[idx];

        snprintf(shm_dev->station_name, sizeof(shm_dev->station_name), "%s", device->station_name);

        format_ip_address(device->ip_address, shm_dev->ip_address,
                          sizeof(shm_dev->ip_address));
        format_mac_address(device->mac_address, shm_dev->mac_address,
                           sizeof(shm_dev->mac_address));

        shm_dev->vendor_id = device->vendor_id;
        shm_dev->device_id = device->device_id;
        shm_dev->reachable = true;

        server->shm->discovered_device_count++;
        LOG_DEBUG(LOG_TAG, "DCP discovered: %s at %s",
                  device->station_name, shm_dev->ip_address);
    }

    pthread_mutex_unlock(&server->shm->lock);
}

/* Handle RTU management commands */
static wtc_result_t handle_rtu_command(ipc_server_t *server, shm_command_t *cmd) {
    wtc_result_t result = WTC_OK;
    const char *cmd_name = NULL;

    /* Debug: log every RTU command received */
    LOG_INFO(LOG_TAG, "RTU command received: type=%d, profinet=%p, registry=%p",
             cmd->command_type, (void*)server->profinet, (void*)server->registry);

    switch (cmd->command_type) {
        case SHM_CMD_ADD_RTU:
            cmd_name = "add_rtu";
            if (server->registry) {
                result = rtu_registry_add_device(server->registry,
                                                  cmd->add_rtu_cmd.station_name,
                                                  cmd->add_rtu_cmd.ip_address,
                                                  NULL, 0);
                LOG_INFO(LOG_TAG, "Add RTU command: %s at %s (result=%d)",
                         cmd->add_rtu_cmd.station_name,
                         cmd->add_rtu_cmd.ip_address,
                         result);
            }
            break;

        case SHM_CMD_REMOVE_RTU:
            cmd_name = "remove_rtu";
            if (server->registry) {
                /* Disconnect first if connected */
                if (server->profinet) {
                    profinet_controller_disconnect(server->profinet,
                                                    cmd->remove_rtu_cmd.station_name);
                }
                result = rtu_registry_remove_device(server->registry,
                                                     cmd->remove_rtu_cmd.station_name);
                LOG_INFO(LOG_TAG, "Remove RTU command: %s (result=%d)",
                         cmd->remove_rtu_cmd.station_name, result);
            }
            break;

        case SHM_CMD_CONNECT_RTU:
            cmd_name = "connect_rtu";
            if (!server->profinet) {
                LOG_ERROR(LOG_TAG, "Connect RTU failed: PROFINET controller not set on IPC server!");
                result = WTC_ERROR_NOT_INITIALIZED;
            } else {
                rtu_device_t *device = rtu_registry_get_device(server->registry,
                                                                cmd->connect_rtu_cmd.station_name);
                if (device) {
                    LOG_INFO(LOG_TAG, "Connect RTU: %s at %s (slots=%p, slot_count=%d)",
                             cmd->connect_rtu_cmd.station_name,
                             device->ip_address,
                             (void*)device->slots, device->slot_count);
                    result = profinet_controller_connect(server->profinet,
                                                          cmd->connect_rtu_cmd.station_name,
                                                          device->ip_address,
                                                          device->slots,
                                                          device->slot_count);
                    LOG_INFO(LOG_TAG, "Connect RTU command: %s (result=%d)",
                             cmd->connect_rtu_cmd.station_name, result);
                    rtu_registry_free_device_copy(device);
                } else {
                    result = WTC_ERROR_NOT_FOUND;
                    LOG_WARN(LOG_TAG, "Connect RTU failed: %s not found in registry",
                             cmd->connect_rtu_cmd.station_name);
                }
            }
            break;

        case SHM_CMD_DISCONNECT_RTU:
            cmd_name = "disconnect_rtu";
            if (server->profinet) {
                result = profinet_controller_disconnect(server->profinet,
                                                         cmd->disconnect_rtu_cmd.station_name);
                LOG_INFO(LOG_TAG, "Disconnect RTU command: %s (result=%d)",
                         cmd->disconnect_rtu_cmd.station_name, result);
            }
            break;
    }

    /* Store result in shared memory */
    server->shm->command_result = result;
    if (result != WTC_OK && cmd_name) {
        snprintf(server->shm->command_error_msg, sizeof(server->shm->command_error_msg),
                 "%s failed with error %d", cmd_name, result);
    } else {
        server->shm->command_error_msg[0] = '\0';
    }

    return result;
}

/* Handle discovery commands */
static wtc_result_t handle_discovery_command(ipc_server_t *server, shm_command_t *cmd) {
    wtc_result_t result = WTC_OK;

    switch (cmd->command_type) {
        case SHM_CMD_DCP_DISCOVER:
            if (server->profinet) {
                /* Use PROFINET controller's DCP instance */
                server->shm->discovered_device_count = 0;
                server->shm->discovery_in_progress = true;
                server->shm->discovery_complete = false;

                /* Track timing so update loop knows when to harvest results */
                server->discovery_start_ms = time_get_ms();
                server->discovery_timeout_ms = cmd->dcp_discover_cmd.timeout_ms > 0
                    ? cmd->dcp_discover_cmd.timeout_ms : 5000;

                /* Trigger DCP Identify All broadcast */
                result = profinet_controller_discover_all(server->profinet);

                LOG_INFO(LOG_TAG, "DCP discover via PROFINET controller (timeout=%ums, result=%d)",
                         server->discovery_timeout_ms, result);
            } else if (server->dcp) {
                /* Fallback: standalone DCP handle */
                server->shm->discovered_device_count = 0;
                server->shm->discovery_in_progress = true;
                server->shm->discovery_complete = false;

                result = dcp_discovery_start(server->dcp, dcp_discovery_callback, server);
                if (result == WTC_OK) {
                    result = dcp_discovery_identify_all(server->dcp);
                }

                LOG_INFO(LOG_TAG, "DCP discover via standalone DCP (timeout=%ums, result=%d)",
                         cmd->dcp_discover_cmd.timeout_ms, result);
            } else {
                result = WTC_ERROR_NOT_INITIALIZED;
                LOG_WARN(LOG_TAG, "DCP discovery not available: no PROFINET controller or DCP handle");
            }
            break;

        case SHM_CMD_I2C_DISCOVER:
            /* I2C discovery - requires RTU to perform the scan */
            if (server->profinet) {
                server->shm->i2c_device_count = 0;
                server->shm->i2c_discovery_complete = false;

                /* Send I2C scan request to RTU via acyclic read */
                LOG_INFO(LOG_TAG, "I2C discover command: %s bus %d",
                         cmd->i2c_discover_cmd.rtu_station,
                         cmd->i2c_discover_cmd.bus_number);

                /* Read I2C scan record from RTU (0x8020 = vendor-specific I2C scan) */
                uint8_t scan_buffer[256];
                size_t scan_len = sizeof(scan_buffer);
                result = profinet_controller_read_record(server->profinet,
                                                          cmd->i2c_discover_cmd.rtu_station,
                                                          0, /* API */
                                                          0, /* Slot */
                                                          1, /* Subslot */
                                                          0x8020, /* I2C scan index */
                                                          scan_buffer,
                                                          &scan_len);

                if (result == WTC_OK && scan_len > 0) {
                    /* Parse I2C scan results */
                    int device_count = scan_buffer[0];
                    for (int i = 0; i < device_count && i < WTC_MAX_I2C_DEVICES; i++) {
                        int offset = 1 + i * 3;
                        if (offset + 2 < (int)scan_len) {
                            server->shm->i2c_devices[i].address = scan_buffer[offset];
                            server->shm->i2c_devices[i].device_type =
                                (scan_buffer[offset + 1] << 8) | scan_buffer[offset + 2];
                            server->shm->i2c_device_count++;
                        }
                    }
                }
                server->shm->i2c_discovery_complete = true;
            }
            break;

        case SHM_CMD_ONEWIRE_DISCOVER:
            /* 1-Wire discovery - requires RTU to perform the scan */
            if (server->profinet) {
                server->shm->onewire_device_count = 0;
                server->shm->onewire_discovery_complete = false;

                LOG_INFO(LOG_TAG, "1-Wire discover command: %s bus %d",
                         cmd->onewire_discover_cmd.rtu_station,
                         cmd->onewire_discover_cmd.bus_number);

                /* Read 1-Wire scan record from RTU (0x8021 = vendor-specific 1-Wire scan) */
                uint8_t scan_buffer[256];
                size_t scan_len = sizeof(scan_buffer);
                result = profinet_controller_read_record(server->profinet,
                                                          cmd->onewire_discover_cmd.rtu_station,
                                                          0, /* API */
                                                          0, /* Slot */
                                                          1, /* Subslot */
                                                          0x8021, /* 1-Wire scan index */
                                                          scan_buffer,
                                                          &scan_len);

                if (result == WTC_OK && scan_len > 0) {
                    /* Parse 1-Wire scan results (each device has 8-byte ROM code) */
                    int device_count = scan_buffer[0];
                    for (int i = 0; i < device_count && i < WTC_MAX_ONEWIRE_DEVICES; i++) {
                        int offset = 1 + i * 8;
                        if (offset + 7 < (int)scan_len) {
                            memcpy(server->shm->onewire_devices[i].rom_code,
                                   &scan_buffer[offset], 8);
                            server->shm->onewire_devices[i].family_code = scan_buffer[offset];
                            server->shm->onewire_device_count++;
                        }
                    }
                }
                server->shm->onewire_discovery_complete = true;
            }
            break;
    }

    server->shm->command_result = result;
    return result;
}

/* Handle slot configuration command */
static wtc_result_t handle_configure_slot(ipc_server_t *server, shm_command_t *cmd) {
    if (!server->registry) return WTC_ERROR_NOT_INITIALIZED;

    slot_config_t slot = {
        .slot = cmd->configure_slot_cmd.slot,
        .subslot = 1,
        .type = cmd->configure_slot_cmd.slot_type,
        .enabled = true,
        .measurement_type = cmd->configure_slot_cmd.measurement_type,
        .actuator_type = cmd->configure_slot_cmd.actuator_type,
    };

    strncpy(slot.name, cmd->configure_slot_cmd.name, WTC_MAX_NAME - 1);
    strncpy(slot.unit, cmd->configure_slot_cmd.unit, WTC_MAX_UNIT - 1);

    wtc_result_t result = rtu_registry_set_device_config(server->registry,
                                                          cmd->configure_slot_cmd.rtu_station,
                                                          &slot, 1);

    LOG_INFO(LOG_TAG, "Configure slot command: %s slot %d as %s (result=%d)",
             cmd->configure_slot_cmd.rtu_station,
             cmd->configure_slot_cmd.slot,
             cmd->configure_slot_cmd.name,
             result);

    server->shm->command_result = result;
    return result;
}

/* Handle user sync command */
static wtc_result_t handle_user_sync_command(ipc_server_t *server, shm_command_t *cmd) {
    if (!server->profinet) {
        LOG_ERROR(LOG_TAG, "User sync failed: PROFINET controller not initialized");
        server->shm->command_result = WTC_ERROR_NOT_INITIALIZED;
        return WTC_ERROR_NOT_INITIALIZED;
    }

    uint32_t user_count = cmd->user_sync_cmd.user_count;
    if (user_count > IPC_USER_SYNC_MAX_USERS) {
        user_count = IPC_USER_SYNC_MAX_USERS;
    }

    LOG_INFO(LOG_TAG, "User sync command: %d users to %s",
             user_count,
             cmd->user_sync_cmd.station_name[0] ? cmd->user_sync_cmd.station_name : "all RTUs");

    /* Convert IPC user data to user_t array for sync module */
    user_t users[IPC_USER_SYNC_MAX_USERS];
    for (uint32_t i = 0; i < user_count; i++) {
        memset(&users[i], 0, sizeof(user_t));
        users[i].user_id = i + 1;
        strncpy(users[i].username, cmd->user_sync_cmd.users[i].username,
                WTC_MAX_USERNAME - 1);
        strncpy(users[i].password_hash, cmd->user_sync_cmd.users[i].password_hash,
                255);
        users[i].role = (user_role_t)cmd->user_sync_cmd.users[i].role;
        users[i].active = (cmd->user_sync_cmd.users[i].flags & 0x01) != 0;
    }

    /* Serialize users for PROFINET transfer */
    user_sync_payload_t payload;
    user_sync_result_t sync_result = user_sync_serialize(users, user_count, &payload);
    if (sync_result != USER_SYNC_OK) {
        LOG_ERROR(LOG_TAG, "Failed to serialize users: %d", sync_result);
        server->shm->command_result = WTC_ERROR_INTERNAL;
        return WTC_ERROR_INTERNAL;
    }

    size_t payload_size = sizeof(user_sync_header_t) +
                          (payload.header.user_count * sizeof(user_sync_record_t));

    wtc_result_t result = WTC_OK;

    if (cmd->command_type == SHM_CMD_USER_SYNC && cmd->user_sync_cmd.station_name[0]) {
        /* Sync to specific RTU */
        result = profinet_controller_write_record(
            server->profinet,
            cmd->user_sync_cmd.station_name,
            0,                          /* API */
            0,                          /* Slot (DAP) */
            1,                          /* Subslot */
            USER_SYNC_RECORD_INDEX,     /* Index */
            &payload,
            payload_size
        );

        if (result == WTC_OK) {
            LOG_INFO(LOG_TAG, "User sync to %s successful (%d users)",
                     cmd->user_sync_cmd.station_name, user_count);
        } else {
            LOG_ERROR(LOG_TAG, "User sync to %s failed: %d",
                      cmd->user_sync_cmd.station_name, result);
        }
    } else {
        /* Sync to all RTUs */
        int success_count = 0;
        int total_count = 0;

        if (server->registry) {
            rtu_device_t *devices = NULL;
            int device_count = 0;

            if (rtu_registry_list_devices(server->registry, &devices, &device_count,
                                           WTC_MAX_RTUS) == WTC_OK) {
                for (int i = 0; i < device_count; i++) {
                    if (devices[i].connection_state == PROFINET_STATE_RUNNING) {
                        total_count++;
                        wtc_result_t r = profinet_controller_write_record(
                            server->profinet,
                            devices[i].station_name,
                            0, 0, 1,
                            USER_SYNC_RECORD_INDEX,
                            &payload,
                            payload_size
                        );
                        if (r == WTC_OK) {
                            success_count++;
                        }
                    }
                }
            }
        }

        LOG_INFO(LOG_TAG, "User sync to all RTUs: %d/%d successful (%d users)",
                 success_count, total_count, user_count);
        result = (success_count == total_count) ? WTC_OK : WTC_ERROR;
    }

    server->shm->command_result = result;
    return result;
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
                    server->shm->command_result = WTC_OK;
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
                    server->shm->command_result = WTC_OK;
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
                    server->shm->command_result = WTC_OK;
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
                    server->shm->command_result = WTC_OK;
                }
                break;

            case SHM_CMD_RESET_INTERLOCK:
                if (server->control) {
                    control_engine_reset_interlock(server->control,
                                                    cmd->reset_cmd.interlock_id);
                    LOG_DEBUG(LOG_TAG, "Interlock reset: %d",
                              cmd->reset_cmd.interlock_id);
                    server->shm->command_result = WTC_OK;
                }
                break;

            /* RTU management commands */
            case SHM_CMD_ADD_RTU:
            case SHM_CMD_REMOVE_RTU:
            case SHM_CMD_CONNECT_RTU:
            case SHM_CMD_DISCONNECT_RTU:
                handle_rtu_command(server, cmd);
                break;

            /* Discovery commands */
            case SHM_CMD_DCP_DISCOVER:
            case SHM_CMD_I2C_DISCOVER:
            case SHM_CMD_ONEWIRE_DISCOVER:
                handle_discovery_command(server, cmd);
                break;

            /* Slot configuration */
            case SHM_CMD_CONFIGURE_SLOT:
                handle_configure_slot(server, cmd);
                break;

            /* User sync commands */
            case SHM_CMD_USER_SYNC:
            case SHM_CMD_USER_SYNC_ALL:
                handle_user_sync_command(server, cmd);
                break;

            default:
                LOG_WARN(LOG_TAG, "Unknown command type: %d", cmd->command_type);
                server->shm->command_result = WTC_ERROR_INVALID_PARAM;
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

/* Post event notification for WebSocket broadcast */
wtc_result_t ipc_server_post_notification(ipc_server_t *server,
                                           int event_type,
                                           const char *station_name,
                                           const char *message) {
    if (!server || !server->shm) {
        return WTC_ERROR_NOT_INITIALIZED;
    }

    pthread_mutex_lock(&server->shm->lock);

    /* Get next write index (circular buffer) */
    int idx = server->shm->notification_write_idx;

    /* Store notification */
    server->shm->notifications[idx].event_type = event_type;
    server->shm->notifications[idx].timestamp_ms = time_get_ms();

    if (station_name) {
        strncpy(server->shm->notifications[idx].station_name,
                station_name,
                sizeof(server->shm->notifications[idx].station_name) - 1);
    } else {
        server->shm->notifications[idx].station_name[0] = '\0';
    }

    if (message) {
        strncpy(server->shm->notifications[idx].message,
                message,
                sizeof(server->shm->notifications[idx].message) - 1);
    } else {
        server->shm->notifications[idx].message[0] = '\0';
    }

    /* Advance write index */
    server->shm->notification_write_idx = (idx + 1) % WTC_MAX_NOTIFICATIONS;

    pthread_mutex_unlock(&server->shm->lock);

    LOG_DEBUG(LOG_TAG, "Posted notification: type=%d, station=%s, msg=%s",
              event_type, station_name ? station_name : "(none)",
              message ? message : "(none)");

    return WTC_OK;
}
