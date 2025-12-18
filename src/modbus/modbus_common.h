/*
 * Water Treatment Controller - Modbus Common Definitions
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_MODBUS_COMMON_H
#define WTC_MODBUS_COMMON_H

#include "types.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Modbus protocol constants */
#define MODBUS_TCP_PORT             502
#define MODBUS_TCP_HEADER_LEN       7
#define MODBUS_RTU_MAX_ADU_LEN      256
#define MODBUS_TCP_MAX_ADU_LEN      260
#define MODBUS_MAX_PDU_LEN          253
#define MODBUS_MAX_READ_REGISTERS   125
#define MODBUS_MAX_WRITE_REGISTERS  123
#define MODBUS_MAX_READ_BITS        2000
#define MODBUS_MAX_WRITE_BITS       1968

/* Modbus function codes */
typedef enum {
    MODBUS_FC_READ_COILS                = 0x01,
    MODBUS_FC_READ_DISCRETE_INPUTS      = 0x02,
    MODBUS_FC_READ_HOLDING_REGISTERS    = 0x03,
    MODBUS_FC_READ_INPUT_REGISTERS      = 0x04,
    MODBUS_FC_WRITE_SINGLE_COIL         = 0x05,
    MODBUS_FC_WRITE_SINGLE_REGISTER     = 0x06,
    MODBUS_FC_READ_EXCEPTION_STATUS     = 0x07,
    MODBUS_FC_DIAGNOSTICS               = 0x08,
    MODBUS_FC_WRITE_MULTIPLE_COILS      = 0x0F,
    MODBUS_FC_WRITE_MULTIPLE_REGISTERS  = 0x10,
    MODBUS_FC_REPORT_SLAVE_ID           = 0x11,
    MODBUS_FC_READ_FILE_RECORD          = 0x14,
    MODBUS_FC_WRITE_FILE_RECORD         = 0x15,
    MODBUS_FC_MASK_WRITE_REGISTER       = 0x16,
    MODBUS_FC_READ_WRITE_REGISTERS      = 0x17,
    MODBUS_FC_READ_FIFO_QUEUE           = 0x18,
    MODBUS_FC_ENCAPSULATED_INTERFACE    = 0x2B,
} modbus_function_code_t;

/* Modbus exception codes */
typedef enum {
    MODBUS_EX_NONE                      = 0x00,
    MODBUS_EX_ILLEGAL_FUNCTION          = 0x01,
    MODBUS_EX_ILLEGAL_DATA_ADDRESS      = 0x02,
    MODBUS_EX_ILLEGAL_DATA_VALUE        = 0x03,
    MODBUS_EX_SLAVE_DEVICE_FAILURE      = 0x04,
    MODBUS_EX_ACKNOWLEDGE               = 0x05,
    MODBUS_EX_SLAVE_BUSY                = 0x06,
    MODBUS_EX_MEMORY_PARITY_ERROR       = 0x08,
    MODBUS_EX_GATEWAY_PATH_UNAVAILABLE  = 0x0A,
    MODBUS_EX_GATEWAY_TARGET_FAILED     = 0x0B,
} modbus_exception_t;

/* Modbus transport type */
typedef enum {
    MODBUS_TRANSPORT_TCP,
    MODBUS_TRANSPORT_RTU,
    MODBUS_TRANSPORT_ASCII,
} modbus_transport_t;

/* Modbus role */
typedef enum {
    MODBUS_ROLE_CLIENT,  /* Master */
    MODBUS_ROLE_SERVER,  /* Slave */
} modbus_role_t;

/* Modbus data types for register interpretation */
typedef enum {
    MODBUS_DTYPE_UINT16,
    MODBUS_DTYPE_INT16,
    MODBUS_DTYPE_UINT32_BE,     /* Big-endian */
    MODBUS_DTYPE_UINT32_LE,     /* Little-endian */
    MODBUS_DTYPE_INT32_BE,
    MODBUS_DTYPE_INT32_LE,
    MODBUS_DTYPE_FLOAT32_BE,    /* IEEE 754 big-endian */
    MODBUS_DTYPE_FLOAT32_LE,
    MODBUS_DTYPE_FLOAT64_BE,
    MODBUS_DTYPE_FLOAT64_LE,
    MODBUS_DTYPE_STRING,
    MODBUS_DTYPE_BIT,
} modbus_data_type_t;

/* Modbus register types */
typedef enum {
    MODBUS_REG_COIL,            /* Read/Write bit (FC 1, 5, 15) */
    MODBUS_REG_DISCRETE_INPUT,  /* Read-only bit (FC 2) */
    MODBUS_REG_HOLDING,         /* Read/Write register (FC 3, 6, 16) */
    MODBUS_REG_INPUT,           /* Read-only register (FC 4) */
} modbus_register_type_t;

/* Modbus TCP MBAP header */
typedef struct __attribute__((packed)) {
    uint16_t transaction_id;
    uint16_t protocol_id;       /* Always 0 for Modbus */
    uint16_t length;
    uint8_t unit_id;
} modbus_tcp_header_t;

/* Modbus PDU (Protocol Data Unit) */
typedef struct {
    uint8_t function_code;
    uint8_t data[MODBUS_MAX_PDU_LEN - 1];
    uint16_t data_len;
} modbus_pdu_t;

/* Modbus ADU (Application Data Unit) */
typedef struct {
    modbus_transport_t transport;
    union {
        struct {
            modbus_tcp_header_t header;
        } tcp;
        struct {
            uint8_t slave_addr;
            uint16_t crc;
        } rtu;
    };
    modbus_pdu_t pdu;
} modbus_adu_t;

/* Modbus request/response */
typedef struct {
    uint8_t slave_id;
    uint8_t function_code;
    uint16_t start_address;
    uint16_t quantity;
    uint8_t *data;
    uint16_t data_len;
    modbus_exception_t exception;
    uint16_t transaction_id;
} modbus_message_t;

/* Modbus connection info */
typedef struct {
    modbus_transport_t transport;
    modbus_role_t role;
    union {
        struct {
            char host[64];
            uint16_t port;
            int socket_fd;
        } tcp;
        struct {
            char device[64];
            uint32_t baud_rate;
            uint8_t data_bits;
            char parity;        /* 'N', 'E', 'O' */
            uint8_t stop_bits;
            int serial_fd;
        } rtu;
    };
    uint8_t slave_id;
    uint32_t timeout_ms;
    uint32_t retry_count;
    bool connected;
} modbus_connection_t;

/* Statistics */
typedef struct {
    uint64_t requests_sent;
    uint64_t requests_received;
    uint64_t responses_sent;
    uint64_t responses_received;
    uint64_t exceptions;
    uint64_t timeouts;
    uint64_t crc_errors;
    uint64_t bytes_sent;
    uint64_t bytes_received;
} modbus_stats_t;

/* CRC-16 calculation for Modbus RTU */
uint16_t modbus_crc16(const uint8_t *data, size_t len);

/* Byte order conversion */
uint16_t modbus_get_uint16_be(const uint8_t *data);
void modbus_set_uint16_be(uint8_t *data, uint16_t value);
uint32_t modbus_get_uint32_be(const uint8_t *data);
void modbus_set_uint32_be(uint8_t *data, uint32_t value);
float modbus_get_float32_be(const uint8_t *data);
void modbus_set_float32_be(uint8_t *data, float value);

/* PDU builders */
int modbus_build_read_request(modbus_pdu_t *pdu, uint8_t fc,
                               uint16_t start_addr, uint16_t quantity);
int modbus_build_write_single_register(modbus_pdu_t *pdu,
                                        uint16_t addr, uint16_t value);
int modbus_build_write_multiple_registers(modbus_pdu_t *pdu,
                                           uint16_t start_addr,
                                           uint16_t quantity,
                                           const uint16_t *values);
int modbus_build_write_single_coil(modbus_pdu_t *pdu,
                                    uint16_t addr, bool value);
int modbus_build_write_multiple_coils(modbus_pdu_t *pdu,
                                       uint16_t start_addr,
                                       uint16_t quantity,
                                       const uint8_t *values);

/* PDU parsers */
int modbus_parse_read_response(const modbus_pdu_t *pdu,
                                uint8_t *data, uint16_t *data_len);
int modbus_parse_write_response(const modbus_pdu_t *pdu,
                                 uint16_t *addr, uint16_t *value);

/* Exception handling */
bool modbus_is_exception(const modbus_pdu_t *pdu);
modbus_exception_t modbus_get_exception(const modbus_pdu_t *pdu);
const char *modbus_exception_string(modbus_exception_t ex);
const char *modbus_function_string(uint8_t fc);

#ifdef __cplusplus
}
#endif

#endif /* WTC_MODBUS_COMMON_H */
