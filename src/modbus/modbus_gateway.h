/*
 * Water Treatment Controller - Modbus Gateway
 * PROFINET to Modbus protocol bridge
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_MODBUS_GATEWAY_H
#define WTC_MODBUS_GATEWAY_H

#include "modbus_common.h"
#include "modbus_tcp.h"
#include "modbus_rtu.h"
#include "register_map.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Forward declarations */
struct rtu_registry;
struct control_engine;
struct alarm_manager;

/* Maximum downstream Modbus clients */
#define MAX_MODBUS_CLIENTS  16

/* Gateway handle */
typedef struct modbus_gateway modbus_gateway_t;

/* Downstream Modbus device configuration */
typedef struct {
    char name[64];
    modbus_transport_t transport;
    bool enabled;

    union {
        struct {
            char host[64];
            uint16_t port;
        } tcp;
        struct {
            char device[64];
            uint32_t baud_rate;
            uint8_t data_bits;
            char parity;
            uint8_t stop_bits;
        } rtu;
    };

    uint8_t slave_addr;
    uint32_t poll_interval_ms;
    uint32_t timeout_ms;
} downstream_device_t;

/* Gateway configuration */
typedef struct {
    /* Modbus Server (exposes PROFINET data) */
    struct {
        bool tcp_enabled;
        uint16_t tcp_port;
        char tcp_bind_address[64];

        bool rtu_enabled;
        char rtu_device[64];
        uint32_t rtu_baud_rate;
        uint8_t rtu_slave_addr;
    } server;

    /* Downstream Modbus clients */
    downstream_device_t downstream[MAX_MODBUS_CLIENTS];
    int downstream_count;

    /* Register map file (JSON) */
    char register_map_file[256];

    /* Auto-generate register map */
    bool auto_generate_map;
    uint16_t sensor_base_addr;
    uint16_t actuator_base_addr;
} modbus_gateway_config_t;

/* Initialize gateway */
wtc_result_t modbus_gateway_init(modbus_gateway_t **gw,
                                  const modbus_gateway_config_t *config);

/* Cleanup gateway */
void modbus_gateway_cleanup(modbus_gateway_t *gw);

/* Set RTU registry */
wtc_result_t modbus_gateway_set_registry(modbus_gateway_t *gw,
                                          struct rtu_registry *registry);

/* Set control engine */
wtc_result_t modbus_gateway_set_control_engine(modbus_gateway_t *gw,
                                                struct control_engine *control);

/* Set alarm manager */
wtc_result_t modbus_gateway_set_alarm_manager(modbus_gateway_t *gw,
                                               struct alarm_manager *alarms);

/* Start gateway */
wtc_result_t modbus_gateway_start(modbus_gateway_t *gw);

/* Stop gateway */
wtc_result_t modbus_gateway_stop(modbus_gateway_t *gw);

/* Process gateway (call periodically to poll downstream devices) */
wtc_result_t modbus_gateway_process(modbus_gateway_t *gw);

/* Add downstream device dynamically */
wtc_result_t modbus_gateway_add_downstream(modbus_gateway_t *gw,
                                            const downstream_device_t *device);

/* Remove downstream device */
wtc_result_t modbus_gateway_remove_downstream(modbus_gateway_t *gw,
                                               const char *name);

/* Get register map */
register_map_t *modbus_gateway_get_register_map(modbus_gateway_t *gw);

/* Get statistics */
typedef struct {
    modbus_stats_t server_tcp_stats;
    modbus_stats_t server_rtu_stats;
    modbus_stats_t client_stats[MAX_MODBUS_CLIENTS];
    int active_tcp_connections;
    int downstream_devices_online;
    uint64_t total_requests_processed;
    uint64_t total_errors;
} modbus_gateway_stats_t;

wtc_result_t modbus_gateway_get_stats(modbus_gateway_t *gw,
                                       modbus_gateway_stats_t *stats);

/* Manual read/write to downstream device */
wtc_result_t modbus_gateway_read_downstream(modbus_gateway_t *gw,
                                             const char *device_name,
                                             uint16_t start_addr,
                                             uint16_t quantity,
                                             uint16_t *values);

wtc_result_t modbus_gateway_write_downstream(modbus_gateway_t *gw,
                                              const char *device_name,
                                              uint16_t start_addr,
                                              uint16_t quantity,
                                              const uint16_t *values);

#ifdef __cplusplus
}
#endif

#endif /* WTC_MODBUS_GATEWAY_H */
