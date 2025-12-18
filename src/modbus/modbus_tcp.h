/*
 * Water Treatment Controller - Modbus TCP Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_MODBUS_TCP_H
#define WTC_MODBUS_TCP_H

#include "modbus_common.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Maximum concurrent TCP connections */
#define MODBUS_TCP_MAX_CONNECTIONS  32

/* Modbus TCP context */
typedef struct modbus_tcp modbus_tcp_t;

/* TCP connection callback */
typedef void (*modbus_tcp_connect_cb)(modbus_tcp_t *ctx, int client_fd,
                                       const char *client_ip, void *user_data);
typedef void (*modbus_tcp_disconnect_cb)(modbus_tcp_t *ctx, int client_fd,
                                          void *user_data);

/* Request handler callback (for server mode) */
typedef modbus_exception_t (*modbus_tcp_request_handler)(
    modbus_tcp_t *ctx,
    uint8_t unit_id,
    const modbus_pdu_t *request,
    modbus_pdu_t *response,
    void *user_data
);

/* TCP configuration */
typedef struct {
    modbus_role_t role;
    char bind_address[64];
    uint16_t port;
    uint32_t timeout_ms;
    uint32_t max_connections;

    /* Server callbacks */
    modbus_tcp_request_handler request_handler;
    modbus_tcp_connect_cb on_connect;
    modbus_tcp_disconnect_cb on_disconnect;
    void *user_data;
} modbus_tcp_config_t;

/* Initialize Modbus TCP context */
wtc_result_t modbus_tcp_init(modbus_tcp_t **ctx, const modbus_tcp_config_t *config);

/* Cleanup Modbus TCP context */
void modbus_tcp_cleanup(modbus_tcp_t *ctx);

/* Start TCP server (non-blocking, spawns thread) */
wtc_result_t modbus_tcp_server_start(modbus_tcp_t *ctx);

/* Stop TCP server */
wtc_result_t modbus_tcp_server_stop(modbus_tcp_t *ctx);

/* Connect to TCP server (client mode) */
wtc_result_t modbus_tcp_connect(modbus_tcp_t *ctx, const char *host, uint16_t port);

/* Disconnect from TCP server */
void modbus_tcp_disconnect(modbus_tcp_t *ctx);

/* Check if connected */
bool modbus_tcp_is_connected(modbus_tcp_t *ctx);

/* Send request and wait for response (client mode) */
wtc_result_t modbus_tcp_transact(modbus_tcp_t *ctx,
                                  uint8_t unit_id,
                                  const modbus_pdu_t *request,
                                  modbus_pdu_t *response);

/* Convenience functions for client operations */
wtc_result_t modbus_tcp_read_coils(modbus_tcp_t *ctx, uint8_t unit_id,
                                    uint16_t start_addr, uint16_t quantity,
                                    uint8_t *values);

wtc_result_t modbus_tcp_read_discrete_inputs(modbus_tcp_t *ctx, uint8_t unit_id,
                                              uint16_t start_addr, uint16_t quantity,
                                              uint8_t *values);

wtc_result_t modbus_tcp_read_holding_registers(modbus_tcp_t *ctx, uint8_t unit_id,
                                                uint16_t start_addr, uint16_t quantity,
                                                uint16_t *values);

wtc_result_t modbus_tcp_read_input_registers(modbus_tcp_t *ctx, uint8_t unit_id,
                                              uint16_t start_addr, uint16_t quantity,
                                              uint16_t *values);

wtc_result_t modbus_tcp_write_single_coil(modbus_tcp_t *ctx, uint8_t unit_id,
                                           uint16_t addr, bool value);

wtc_result_t modbus_tcp_write_single_register(modbus_tcp_t *ctx, uint8_t unit_id,
                                               uint16_t addr, uint16_t value);

wtc_result_t modbus_tcp_write_multiple_coils(modbus_tcp_t *ctx, uint8_t unit_id,
                                              uint16_t start_addr, uint16_t quantity,
                                              const uint8_t *values);

wtc_result_t modbus_tcp_write_multiple_registers(modbus_tcp_t *ctx, uint8_t unit_id,
                                                  uint16_t start_addr, uint16_t quantity,
                                                  const uint16_t *values);

/* Get statistics */
wtc_result_t modbus_tcp_get_stats(modbus_tcp_t *ctx, modbus_stats_t *stats);

/* Get active connection count */
int modbus_tcp_get_connection_count(modbus_tcp_t *ctx);

#ifdef __cplusplus
}
#endif

#endif /* WTC_MODBUS_TCP_H */
