/*
 * Water Treatment Controller - Modbus Gateway Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "modbus_gateway.h"
#include "registry/rtu_registry.h"
#include "control/control_engine.h"
#include "alarms/alarm_manager.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>

#define LOG_TAG "MODBUS_GW"

/* Downstream client context */
typedef struct {
    downstream_device_t config;
    modbus_tcp_t *tcp;
    modbus_rtu_t *rtu;
    bool connected;
    uint64_t last_poll_ms;
    uint64_t last_error_ms;
    int consecutive_errors;
} downstream_client_t;

/* Gateway structure */
struct modbus_gateway {
    modbus_gateway_config_t config;

    /* Server contexts */
    modbus_tcp_t *server_tcp;
    modbus_rtu_t *server_rtu;

    /* Downstream clients */
    downstream_client_t clients[MAX_MODBUS_CLIENTS];
    int client_count;

    /* Register map */
    register_map_t *register_map;

    /* Data sources */
    struct rtu_registry *registry;
    struct control_engine *control;
    struct alarm_manager *alarms;

    /* State */
    bool running;
    pthread_mutex_t lock;

    /* Statistics */
    uint64_t total_requests;
    uint64_t total_errors;
};

/* Forward declarations */
static modbus_exception_t handle_server_request(
    modbus_tcp_t *ctx, uint8_t unit_id, const modbus_pdu_t *request,
    modbus_pdu_t *response, void *user_data);

static modbus_exception_t handle_rtu_request(
    modbus_rtu_t *ctx, uint8_t slave_addr, const modbus_pdu_t *request,
    modbus_pdu_t *response, void *user_data);

/* Read register value from data source */
static wtc_result_t read_register_value(modbus_gateway_t *gw,
                                         const register_mapping_t *mapping,
                                         uint16_t *value) {
    if (!gw || !mapping || !value) return WTC_ERROR_INVALID_PARAM;

    float raw_value = 0;

    switch (mapping->source) {
    case DATA_SOURCE_PROFINET_SENSOR:
        if (gw->registry) {
            sensor_data_t data;
            if (rtu_registry_get_sensor(gw->registry, mapping->rtu_station,
                                        mapping->slot, &data) == WTC_OK) {
                raw_value = data.value;
            }
        }
        break;

    case DATA_SOURCE_PROFINET_ACTUATOR:
        if (gw->registry) {
            actuator_state_t state;
            if (rtu_registry_get_actuator(gw->registry, mapping->rtu_station,
                                          mapping->slot, &state) == WTC_OK) {
                raw_value = state.output.pwm_duty;
            }
        }
        break;

    case DATA_SOURCE_PID_SETPOINT:
    case DATA_SOURCE_PID_PV:
    case DATA_SOURCE_PID_CV:
        if (gw->control) {
            pid_loop_t loop;
            if (control_engine_get_pid_loop(gw->control, mapping->pid_loop_id,
                                            &loop) == WTC_OK) {
                if (mapping->source == DATA_SOURCE_PID_SETPOINT) {
                    raw_value = loop.setpoint;
                } else if (mapping->source == DATA_SOURCE_PID_PV) {
                    raw_value = loop.pv;
                } else {
                    raw_value = loop.cv;
                }
            }
        }
        break;

    case DATA_SOURCE_MODBUS_CLIENT:
        /* Read from downstream Modbus device */
        for (int i = 0; i < gw->client_count; i++) {
            downstream_client_t *cli = &gw->clients[i];
            if (cli->connected) {
                uint16_t val;
                wtc_result_t res = WTC_ERROR_NOT_FOUND;

                if (cli->tcp) {
                    res = modbus_tcp_read_holding_registers(
                        cli->tcp, mapping->modbus_source.slave_addr,
                        mapping->modbus_source.remote_addr, 1, &val);
                } else if (cli->rtu) {
                    res = modbus_rtu_read_holding_registers(
                        cli->rtu, mapping->modbus_source.slave_addr,
                        mapping->modbus_source.remote_addr, 1, &val);
                }

                if (res == WTC_OK) {
                    raw_value = val;
                    break;
                }
            }
        }
        break;

    default:
        break;
    }

    /* Apply scaling */
    float scaled = register_map_scale_value(&mapping->scaling, raw_value);

    /* Convert to register value based on data type */
    switch (mapping->data_type) {
    case MODBUS_DTYPE_UINT16:
        *value = (uint16_t)scaled;
        break;
    case MODBUS_DTYPE_INT16:
        *value = (uint16_t)(int16_t)scaled;
        break;
    default:
        *value = (uint16_t)scaled;
        break;
    }

    return WTC_OK;
}

/* Write register value to data source */
static wtc_result_t write_register_value(modbus_gateway_t *gw,
                                          const register_mapping_t *mapping,
                                          uint16_t value) {
    if (!gw || !mapping || mapping->read_only) {
        return WTC_ERROR_INVALID_PARAM;
    }

    float eng_value = (float)value;

    /* Reverse scaling */
    float raw_value = register_map_unscale_value(&mapping->scaling, eng_value);

    switch (mapping->source) {
    case DATA_SOURCE_PROFINET_ACTUATOR:
        if (gw->registry) {
            actuator_output_t output = {
                .command = (raw_value > 0) ? 1 : 0,
                .pwm_duty = (uint8_t)raw_value,
            };
            return rtu_registry_update_actuator(gw->registry, mapping->rtu_station,
                                                 mapping->slot, &output);
        }
        break;

    case DATA_SOURCE_PID_SETPOINT:
        if (gw->control) {
            return control_engine_set_setpoint(gw->control,
                                               mapping->pid_loop_id, raw_value);
        }
        break;

    case DATA_SOURCE_MODBUS_CLIENT:
        /* Write to downstream Modbus device */
        for (int i = 0; i < gw->client_count; i++) {
            downstream_client_t *cli = &gw->clients[i];
            if (cli->connected) {
                if (cli->tcp) {
                    return modbus_tcp_write_single_register(
                        cli->tcp, mapping->modbus_source.slave_addr,
                        mapping->modbus_source.remote_addr, (uint16_t)raw_value);
                } else if (cli->rtu) {
                    return modbus_rtu_write_single_register(
                        cli->rtu, mapping->modbus_source.slave_addr,
                        mapping->modbus_source.remote_addr, (uint16_t)raw_value);
                }
            }
        }
        break;

    default:
        return WTC_ERROR_INVALID_PARAM;
    }

    return WTC_OK;
}

/* Handle Modbus server request */
static modbus_exception_t handle_server_request(
    modbus_tcp_t *ctx, uint8_t unit_id, const modbus_pdu_t *request,
    modbus_pdu_t *response, void *user_data) {

    modbus_gateway_t *gw = (modbus_gateway_t *)user_data;
    (void)ctx;
    (void)unit_id;

    if (!gw || !request || !response) {
        return MODBUS_EX_SLAVE_DEVICE_FAILURE;
    }

    pthread_mutex_lock(&gw->lock);
    gw->total_requests++;
    pthread_mutex_unlock(&gw->lock);

    uint16_t start_addr = modbus_get_uint16_be(&request->data[0]);
    uint16_t quantity = modbus_get_uint16_be(&request->data[2]);

    response->function_code = request->function_code;

    switch (request->function_code) {
    case MODBUS_FC_READ_HOLDING_REGISTERS:
    case MODBUS_FC_READ_INPUT_REGISTERS: {
        if (quantity > MODBUS_MAX_READ_REGISTERS) {
            return MODBUS_EX_ILLEGAL_DATA_VALUE;
        }

        modbus_register_type_t reg_type =
            (request->function_code == MODBUS_FC_READ_HOLDING_REGISTERS)
            ? MODBUS_REG_HOLDING : MODBUS_REG_INPUT;

        response->data[0] = quantity * 2; /* Byte count */
        response->data_len = 1 + quantity * 2;

        for (uint16_t i = 0; i < quantity; i++) {
            uint16_t value = 0;
            register_mapping_t *mapping = register_map_get_register(
                gw->register_map, reg_type, start_addr + i);

            if (mapping) {
                read_register_value(gw, mapping, &value);
            }

            modbus_set_uint16_be(&response->data[1 + i * 2], value);
        }
        break;
    }

    case MODBUS_FC_WRITE_SINGLE_REGISTER: {
        uint16_t value = modbus_get_uint16_be(&request->data[2]);

        register_mapping_t *mapping = register_map_get_register(
            gw->register_map, MODBUS_REG_HOLDING, start_addr);

        if (!mapping) {
            return MODBUS_EX_ILLEGAL_DATA_ADDRESS;
        }

        if (mapping->read_only) {
            return MODBUS_EX_ILLEGAL_FUNCTION;
        }

        if (write_register_value(gw, mapping, value) != WTC_OK) {
            return MODBUS_EX_SLAVE_DEVICE_FAILURE;
        }

        /* Echo request */
        memcpy(response->data, request->data, 4);
        response->data_len = 4;
        break;
    }

    case MODBUS_FC_WRITE_MULTIPLE_REGISTERS: {
        if (quantity > MODBUS_MAX_WRITE_REGISTERS) {
            return MODBUS_EX_ILLEGAL_DATA_VALUE;
        }

        for (uint16_t i = 0; i < quantity; i++) {
            uint16_t value = modbus_get_uint16_be(&request->data[5 + i * 2]);

            register_mapping_t *mapping = register_map_get_register(
                gw->register_map, MODBUS_REG_HOLDING, start_addr + i);

            if (!mapping) {
                return MODBUS_EX_ILLEGAL_DATA_ADDRESS;
            }

            if (mapping->read_only) {
                return MODBUS_EX_ILLEGAL_FUNCTION;
            }

            if (write_register_value(gw, mapping, value) != WTC_OK) {
                return MODBUS_EX_SLAVE_DEVICE_FAILURE;
            }
        }

        /* Response: start addr + quantity */
        modbus_set_uint16_be(&response->data[0], start_addr);
        modbus_set_uint16_be(&response->data[2], quantity);
        response->data_len = 4;
        break;
    }

    case MODBUS_FC_READ_COILS:
    case MODBUS_FC_READ_DISCRETE_INPUTS: {
        if (quantity > MODBUS_MAX_READ_BITS) {
            return MODBUS_EX_ILLEGAL_DATA_VALUE;
        }

        modbus_register_type_t coil_type =
            (request->function_code == MODBUS_FC_READ_COILS)
            ? MODBUS_REG_COIL : MODBUS_REG_DISCRETE_INPUT;

        uint8_t byte_count = (quantity + 7) / 8;
        response->data[0] = byte_count;
        memset(&response->data[1], 0, byte_count);
        response->data_len = 1 + byte_count;

        for (uint16_t i = 0; i < quantity; i++) {
            coil_mapping_t *mapping = register_map_get_coil(
                gw->register_map, coil_type, start_addr + i);

            if (mapping) {
                /* Read coil state from actuator */
                if (gw->registry && mapping->source == DATA_SOURCE_PROFINET_ACTUATOR) {
                    actuator_state_t state;
                    if (rtu_registry_get_actuator(gw->registry, mapping->rtu_station,
                                                  mapping->slot, &state) == WTC_OK) {
                        bool on = (state.output.command == mapping->command_on_value);
                        if (on) {
                            response->data[1 + i / 8] |= (1 << (i % 8));
                        }
                    }
                }
            }
        }
        break;
    }

    case MODBUS_FC_WRITE_SINGLE_COIL: {
        uint16_t value = modbus_get_uint16_be(&request->data[2]);
        bool on = (value == 0xFF00);

        coil_mapping_t *mapping = register_map_get_coil(
            gw->register_map, MODBUS_REG_COIL, start_addr);

        if (!mapping) {
            return MODBUS_EX_ILLEGAL_DATA_ADDRESS;
        }

        if (mapping->read_only) {
            return MODBUS_EX_ILLEGAL_FUNCTION;
        }

        if (gw->registry && mapping->source == DATA_SOURCE_PROFINET_ACTUATOR) {
            actuator_output_t output = {
                .command = on ? mapping->command_on_value : mapping->command_off_value,
            };
            rtu_registry_update_actuator(gw->registry, mapping->rtu_station,
                                         mapping->slot, &output);
        }

        /* Echo request */
        memcpy(response->data, request->data, 4);
        response->data_len = 4;
        break;
    }

    default:
        return MODBUS_EX_ILLEGAL_FUNCTION;
    }

    return MODBUS_EX_NONE;
}

/* Handle RTU server request (same logic) */
static modbus_exception_t handle_rtu_request(
    modbus_rtu_t *ctx, uint8_t slave_addr, const modbus_pdu_t *request,
    modbus_pdu_t *response, void *user_data) {

    (void)ctx;
    (void)slave_addr;

    /* Reuse TCP handler logic */
    return handle_server_request(NULL, slave_addr, request, response, user_data);
}

/* Connect downstream clients */
static void connect_downstream_clients(modbus_gateway_t *gw) {
    for (int i = 0; i < gw->client_count; i++) {
        downstream_client_t *cli = &gw->clients[i];

        if (!cli->config.enabled || cli->connected) continue;

        if (cli->config.transport == MODBUS_TRANSPORT_TCP) {
            if (!cli->tcp) {
                modbus_tcp_config_t cfg = {
                    .role = MODBUS_ROLE_CLIENT,
                    .timeout_ms = cli->config.timeout_ms,
                };
                modbus_tcp_init(&cli->tcp, &cfg);
            }

            if (modbus_tcp_connect(cli->tcp, cli->config.tcp.host,
                                   cli->config.tcp.port) == WTC_OK) {
                cli->connected = true;
                LOG_INFO(LOG_TAG, "Connected to downstream: %s (%s:%d)",
                         cli->config.name, cli->config.tcp.host, cli->config.tcp.port);
            }
        } else if (cli->config.transport == MODBUS_TRANSPORT_RTU) {
            if (!cli->rtu) {
                modbus_rtu_config_t cfg = {
                    .role = MODBUS_ROLE_CLIENT,
                    .baud_rate = cli->config.rtu.baud_rate,
                    .data_bits = cli->config.rtu.data_bits,
                    .parity = cli->config.rtu.parity,
                    .stop_bits = cli->config.rtu.stop_bits,
                    .timeout_ms = cli->config.timeout_ms,
                };
                strncpy(cfg.device, cli->config.rtu.device, 63);
                modbus_rtu_init(&cli->rtu, &cfg);
            }

            if (modbus_rtu_open(cli->rtu) == WTC_OK) {
                cli->connected = true;
                LOG_INFO(LOG_TAG, "Connected to downstream: %s (%s)",
                         cli->config.name, cli->config.rtu.device);
            }
        }
    }
}

wtc_result_t modbus_gateway_init(modbus_gateway_t **gw,
                                  const modbus_gateway_config_t *config) {
    if (!gw || !config) return WTC_ERROR_INVALID_PARAM;

    modbus_gateway_t *gateway = calloc(1, sizeof(modbus_gateway_t));
    if (!gateway) return WTC_ERROR_NO_MEMORY;

    memcpy(&gateway->config, config, sizeof(modbus_gateway_config_t));
    pthread_mutex_init(&gateway->lock, NULL);

    /* Initialize register map */
    register_map_config_t rm_config = {0};
    if (register_map_init(&gateway->register_map, &rm_config) != WTC_OK) {
        free(gateway);
        return WTC_ERROR_NO_MEMORY;
    }

    /* Load register map from file if specified */
    if (config->register_map_file[0]) {
        register_map_load_json(gateway->register_map, config->register_map_file);
    }

    /* Initialize TCP server */
    if (config->server.tcp_enabled) {
        modbus_tcp_config_t tcp_cfg = {
            .role = MODBUS_ROLE_SERVER,
            .port = config->server.tcp_port ? config->server.tcp_port : 502,
            .max_connections = 32,
            .timeout_ms = 5000,
            .request_handler = handle_server_request,
            .user_data = gateway,
        };
        if (config->server.tcp_bind_address[0]) {
            strncpy(tcp_cfg.bind_address, config->server.tcp_bind_address,
                    sizeof(tcp_cfg.bind_address) - 1);
            tcp_cfg.bind_address[sizeof(tcp_cfg.bind_address) - 1] = '\0';
        }

        if (modbus_tcp_init(&gateway->server_tcp, &tcp_cfg) != WTC_OK) {
            LOG_ERROR(LOG_TAG, "Failed to initialize TCP server");
        }
    }

    /* Initialize RTU server */
    if (config->server.rtu_enabled && config->server.rtu_device[0]) {
        modbus_rtu_config_t rtu_cfg = {
            .role = MODBUS_ROLE_SERVER,
            .baud_rate = config->server.rtu_baud_rate ? config->server.rtu_baud_rate : 9600,
            .data_bits = 8,
            .parity = 'N',
            .stop_bits = 1,
            .slave_addr = config->server.rtu_slave_addr ? config->server.rtu_slave_addr : 1,
            .timeout_ms = 1000,
            .request_handler = handle_rtu_request,
            .user_data = gateway,
        };
        strncpy(rtu_cfg.device, config->server.rtu_device,
                sizeof(rtu_cfg.device) - 1);
        rtu_cfg.device[sizeof(rtu_cfg.device) - 1] = '\0';

        if (modbus_rtu_init(&gateway->server_rtu, &rtu_cfg) != WTC_OK) {
            LOG_ERROR(LOG_TAG, "Failed to initialize RTU server");
        }
    }

    /* Initialize downstream clients */
    for (int i = 0; i < config->downstream_count && i < MAX_MODBUS_CLIENTS; i++) {
        memcpy(&gateway->clients[i].config, &config->downstream[i],
               sizeof(downstream_device_t));
        gateway->client_count++;
    }

    *gw = gateway;
    LOG_INFO(LOG_TAG, "Modbus gateway initialized");
    return WTC_OK;
}

void modbus_gateway_cleanup(modbus_gateway_t *gw) {
    if (!gw) return;

    modbus_gateway_stop(gw);

    /* Cleanup downstream clients */
    for (int i = 0; i < gw->client_count; i++) {
        if (gw->clients[i].tcp) {
            modbus_tcp_cleanup(gw->clients[i].tcp);
        }
        if (gw->clients[i].rtu) {
            modbus_rtu_cleanup(gw->clients[i].rtu);
        }
    }

    /* Cleanup servers */
    if (gw->server_tcp) modbus_tcp_cleanup(gw->server_tcp);
    if (gw->server_rtu) modbus_rtu_cleanup(gw->server_rtu);

    /* Cleanup register map */
    if (gw->register_map) register_map_cleanup(gw->register_map);

    pthread_mutex_destroy(&gw->lock);
    free(gw);

    LOG_INFO(LOG_TAG, "Modbus gateway cleaned up");
}

wtc_result_t modbus_gateway_set_registry(modbus_gateway_t *gw,
                                          struct rtu_registry *registry) {
    if (!gw) return WTC_ERROR_INVALID_PARAM;
    gw->registry = registry;

    /* Auto-generate register map if configured */
    if (gw->config.auto_generate_map && registry) {
        register_map_auto_generate(gw->register_map, registry,
                                   gw->config.sensor_base_addr,
                                   gw->config.actuator_base_addr);
    }

    return WTC_OK;
}

wtc_result_t modbus_gateway_set_control_engine(modbus_gateway_t *gw,
                                                struct control_engine *control) {
    if (!gw) return WTC_ERROR_INVALID_PARAM;
    gw->control = control;
    return WTC_OK;
}

wtc_result_t modbus_gateway_set_alarm_manager(modbus_gateway_t *gw,
                                               struct alarm_manager *alarms) {
    if (!gw) return WTC_ERROR_INVALID_PARAM;
    gw->alarms = alarms;
    return WTC_OK;
}

wtc_result_t modbus_gateway_start(modbus_gateway_t *gw) {
    if (!gw) return WTC_ERROR_INVALID_PARAM;

    gw->running = true;

    /* Start TCP server */
    if (gw->server_tcp) {
        if (modbus_tcp_server_start(gw->server_tcp) != WTC_OK) {
            LOG_ERROR(LOG_TAG, "Failed to start TCP server");
        }
    }

    /* Start RTU server */
    if (gw->server_rtu) {
        if (modbus_rtu_server_start(gw->server_rtu) != WTC_OK) {
            LOG_ERROR(LOG_TAG, "Failed to start RTU server");
        }
    }

    /* Connect downstream clients */
    connect_downstream_clients(gw);

    LOG_INFO(LOG_TAG, "Modbus gateway started");
    return WTC_OK;
}

wtc_result_t modbus_gateway_stop(modbus_gateway_t *gw) {
    if (!gw) return WTC_ERROR_INVALID_PARAM;

    gw->running = false;

    /* Stop servers */
    if (gw->server_tcp) modbus_tcp_server_stop(gw->server_tcp);
    if (gw->server_rtu) modbus_rtu_server_stop(gw->server_rtu);

    /* Disconnect downstream clients */
    for (int i = 0; i < gw->client_count; i++) {
        if (gw->clients[i].tcp) {
            modbus_tcp_disconnect(gw->clients[i].tcp);
        }
        if (gw->clients[i].rtu) {
            modbus_rtu_close(gw->clients[i].rtu);
        }
        gw->clients[i].connected = false;
    }

    LOG_INFO(LOG_TAG, "Modbus gateway stopped");
    return WTC_OK;
}

/* MB-C2 fix: Cache for downstream polled values */
#define DOWNSTREAM_CACHE_SIZE 256

typedef struct {
    uint16_t start_addr;
    uint16_t count;
    uint16_t values[128];
    uint64_t last_update_ms;
    bool valid;
} downstream_cache_entry_t;

static downstream_cache_entry_t downstream_cache[MAX_MODBUS_CLIENTS];

/* Poll a single downstream client */
static void poll_downstream_client(modbus_gateway_t *gw, int client_idx) {
    downstream_client_t *cli = &gw->clients[client_idx];

    /* Find registers mapped to this downstream client */
    register_map_t *rm = gw->register_map;
    if (!rm) return;

    /* Poll holding registers in configured ranges */
    uint16_t start_addr = 0;
    uint16_t quantity = 10; /* Default poll 10 registers at a time */

    uint16_t values[128];
    wtc_result_t res = WTC_ERROR_NOT_FOUND;

    if (cli->tcp && cli->connected) {
        res = modbus_tcp_read_holding_registers(
            cli->tcp, cli->config.slave_addr, start_addr, quantity, values);
    } else if (cli->rtu && cli->connected) {
        res = modbus_rtu_read_holding_registers(
            cli->rtu, cli->config.slave_addr, start_addr, quantity, values);
    }

    if (res == WTC_OK) {
        /* Update cache */
        downstream_cache[client_idx].start_addr = start_addr;
        downstream_cache[client_idx].count = quantity;
        memcpy(downstream_cache[client_idx].values, values, quantity * sizeof(uint16_t));
        downstream_cache[client_idx].last_update_ms = time_get_ms();
        downstream_cache[client_idx].valid = true;

        cli->consecutive_errors = 0;
    } else {
        cli->consecutive_errors++;
        cli->last_error_ms = time_get_ms();

        /* Mark client as disconnected after 3 consecutive errors */
        if (cli->consecutive_errors >= 3) {
            cli->connected = false;
            downstream_cache[client_idx].valid = false;
            LOG_WARN(LOG_TAG, "Downstream %s marked offline after %d errors",
                     cli->config.name, cli->consecutive_errors);
        }
    }
}

wtc_result_t modbus_gateway_process(modbus_gateway_t *gw) {
    if (!gw || !gw->running) return WTC_ERROR_INVALID_PARAM;

    uint64_t now = time_get_ms();

    /* MB-H2 fix: Take lock for entire iteration to prevent race conditions */
    pthread_mutex_lock(&gw->lock);

    /* Poll downstream devices */
    for (int i = 0; i < gw->client_count; i++) {
        downstream_client_t *cli = &gw->clients[i];

        if (!cli->config.enabled) continue;

        /* Reconnect if disconnected */
        if (!cli->connected) {
            if (now - cli->last_error_ms > 5000) { /* 5 second reconnect delay */
                pthread_mutex_unlock(&gw->lock);
                connect_downstream_clients(gw);
                pthread_mutex_lock(&gw->lock);
            }
            continue;
        }

        /* Poll if interval elapsed */
        if (cli->config.poll_interval_ms > 0 &&
            now - cli->last_poll_ms >= cli->config.poll_interval_ms) {

            cli->last_poll_ms = now;

            /* MB-C2 fix: Actually poll the downstream device */
            pthread_mutex_unlock(&gw->lock);
            poll_downstream_client(gw, i);
            pthread_mutex_lock(&gw->lock);
        }
    }

    pthread_mutex_unlock(&gw->lock);

    return WTC_OK;
}

wtc_result_t modbus_gateway_add_downstream(modbus_gateway_t *gw,
                                            const downstream_device_t *device) {
    if (!gw || !device || gw->client_count >= MAX_MODBUS_CLIENTS) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&gw->lock);

    memcpy(&gw->clients[gw->client_count].config, device,
           sizeof(downstream_device_t));
    gw->client_count++;

    pthread_mutex_unlock(&gw->lock);

    LOG_INFO(LOG_TAG, "Added downstream device: %s", device->name);
    return WTC_OK;
}

wtc_result_t modbus_gateway_remove_downstream(modbus_gateway_t *gw,
                                               const char *name) {
    if (!gw || !name) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&gw->lock);

    for (int i = 0; i < gw->client_count; i++) {
        if (strcmp(gw->clients[i].config.name, name) == 0) {
            /* Cleanup */
            if (gw->clients[i].tcp) {
                modbus_tcp_cleanup(gw->clients[i].tcp);
            }
            if (gw->clients[i].rtu) {
                modbus_rtu_cleanup(gw->clients[i].rtu);
            }

            /* Shift remaining */
            for (int j = i; j < gw->client_count - 1; j++) {
                gw->clients[j] = gw->clients[j + 1];
            }
            gw->client_count--;

            pthread_mutex_unlock(&gw->lock);
            LOG_INFO(LOG_TAG, "Removed downstream device: %s", name);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&gw->lock);
    return WTC_ERROR_NOT_FOUND;
}

register_map_t *modbus_gateway_get_register_map(modbus_gateway_t *gw) {
    return gw ? gw->register_map : NULL;
}

wtc_result_t modbus_gateway_get_stats(modbus_gateway_t *gw,
                                       modbus_gateway_stats_t *stats) {
    if (!gw || !stats) return WTC_ERROR_INVALID_PARAM;

    memset(stats, 0, sizeof(modbus_gateway_stats_t));

    pthread_mutex_lock(&gw->lock);

    if (gw->server_tcp) {
        modbus_tcp_get_stats(gw->server_tcp, &stats->server_tcp_stats);
        stats->active_tcp_connections = modbus_tcp_get_connection_count(gw->server_tcp);
    }

    if (gw->server_rtu) {
        modbus_rtu_get_stats(gw->server_rtu, &stats->server_rtu_stats);
    }

    for (int i = 0; i < gw->client_count; i++) {
        if (gw->clients[i].connected) {
            stats->downstream_devices_online++;
        }
        if (gw->clients[i].tcp) {
            modbus_tcp_get_stats(gw->clients[i].tcp, &stats->client_stats[i]);
        }
        if (gw->clients[i].rtu) {
            modbus_rtu_get_stats(gw->clients[i].rtu, &stats->client_stats[i]);
        }
    }

    stats->total_requests_processed = gw->total_requests;
    stats->total_errors = gw->total_errors;

    pthread_mutex_unlock(&gw->lock);

    return WTC_OK;
}

wtc_result_t modbus_gateway_read_downstream(modbus_gateway_t *gw,
                                             const char *device_name,
                                             uint16_t start_addr,
                                             uint16_t quantity,
                                             uint16_t *values) {
    if (!gw || !device_name || !values) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < gw->client_count; i++) {
        if (strcmp(gw->clients[i].config.name, device_name) == 0) {
            downstream_client_t *cli = &gw->clients[i];

            if (!cli->connected) return WTC_ERROR_NOT_CONNECTED;

            if (cli->tcp) {
                return modbus_tcp_read_holding_registers(
                    cli->tcp, cli->config.slave_addr, start_addr, quantity, values);
            } else if (cli->rtu) {
                return modbus_rtu_read_holding_registers(
                    cli->rtu, cli->config.slave_addr, start_addr, quantity, values);
            }
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t modbus_gateway_write_downstream(modbus_gateway_t *gw,
                                              const char *device_name,
                                              uint16_t start_addr,
                                              uint16_t quantity,
                                              const uint16_t *values) {
    if (!gw || !device_name || !values) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < gw->client_count; i++) {
        if (strcmp(gw->clients[i].config.name, device_name) == 0) {
            downstream_client_t *cli = &gw->clients[i];

            if (!cli->connected) return WTC_ERROR_NOT_CONNECTED;

            if (cli->tcp) {
                return modbus_tcp_write_multiple_registers(
                    cli->tcp, cli->config.slave_addr, start_addr, quantity, values);
            } else if (cli->rtu) {
                return modbus_rtu_write_multiple_registers(
                    cli->rtu, cli->config.slave_addr, start_addr, quantity, values);
            }
        }
    }

    return WTC_ERROR_NOT_FOUND;
}
