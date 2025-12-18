/*
 * Water Treatment Controller - Modbus RTU Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_MODBUS_RTU_H
#define WTC_MODBUS_RTU_H

#include "modbus_common.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Modbus RTU context */
typedef struct modbus_rtu modbus_rtu_t;

/* Request handler callback (for server mode) */
typedef modbus_exception_t (*modbus_rtu_request_handler)(
    modbus_rtu_t *ctx,
    uint8_t slave_addr,
    const modbus_pdu_t *request,
    modbus_pdu_t *response,
    void *user_data
);

/* RTU configuration */
typedef struct {
    modbus_role_t role;
    char device[64];           /* Serial device path (e.g., /dev/ttyUSB0) */
    uint32_t baud_rate;        /* 9600, 19200, 38400, 57600, 115200 */
    uint8_t data_bits;         /* 7 or 8 */
    char parity;               /* 'N', 'E', 'O' */
    uint8_t stop_bits;         /* 1 or 2 */
    uint8_t slave_addr;        /* Slave address (1-247) for server mode */
    uint32_t timeout_ms;
    uint32_t inter_frame_delay_us; /* 3.5 character times */

    /* Server callback */
    modbus_rtu_request_handler request_handler;
    void *user_data;
} modbus_rtu_config_t;

/* Initialize Modbus RTU context */
wtc_result_t modbus_rtu_init(modbus_rtu_t **ctx, const modbus_rtu_config_t *config);

/* Cleanup Modbus RTU context */
void modbus_rtu_cleanup(modbus_rtu_t *ctx);

/* Open serial port */
wtc_result_t modbus_rtu_open(modbus_rtu_t *ctx);

/* Close serial port */
void modbus_rtu_close(modbus_rtu_t *ctx);

/* Check if serial port is open */
bool modbus_rtu_is_open(modbus_rtu_t *ctx);

/* Start server (non-blocking, spawns thread) */
wtc_result_t modbus_rtu_server_start(modbus_rtu_t *ctx);

/* Stop server */
wtc_result_t modbus_rtu_server_stop(modbus_rtu_t *ctx);

/* Send request and wait for response (client mode) */
wtc_result_t modbus_rtu_transact(modbus_rtu_t *ctx,
                                  uint8_t slave_addr,
                                  const modbus_pdu_t *request,
                                  modbus_pdu_t *response);

/* Convenience functions for client operations */
wtc_result_t modbus_rtu_read_coils(modbus_rtu_t *ctx, uint8_t slave_addr,
                                    uint16_t start_addr, uint16_t quantity,
                                    uint8_t *values);

wtc_result_t modbus_rtu_read_discrete_inputs(modbus_rtu_t *ctx, uint8_t slave_addr,
                                              uint16_t start_addr, uint16_t quantity,
                                              uint8_t *values);

wtc_result_t modbus_rtu_read_holding_registers(modbus_rtu_t *ctx, uint8_t slave_addr,
                                                uint16_t start_addr, uint16_t quantity,
                                                uint16_t *values);

wtc_result_t modbus_rtu_read_input_registers(modbus_rtu_t *ctx, uint8_t slave_addr,
                                              uint16_t start_addr, uint16_t quantity,
                                              uint16_t *values);

wtc_result_t modbus_rtu_write_single_coil(modbus_rtu_t *ctx, uint8_t slave_addr,
                                           uint16_t addr, bool value);

wtc_result_t modbus_rtu_write_single_register(modbus_rtu_t *ctx, uint8_t slave_addr,
                                               uint16_t addr, uint16_t value);

wtc_result_t modbus_rtu_write_multiple_coils(modbus_rtu_t *ctx, uint8_t slave_addr,
                                              uint16_t start_addr, uint16_t quantity,
                                              const uint8_t *values);

wtc_result_t modbus_rtu_write_multiple_registers(modbus_rtu_t *ctx, uint8_t slave_addr,
                                                  uint16_t start_addr, uint16_t quantity,
                                                  const uint16_t *values);

/* Get statistics */
wtc_result_t modbus_rtu_get_stats(modbus_rtu_t *ctx, modbus_stats_t *stats);

/* Flush serial buffers */
void modbus_rtu_flush(modbus_rtu_t *ctx);

#ifdef __cplusplus
}
#endif

#endif /* WTC_MODBUS_RTU_H */
