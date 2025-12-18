/*
 * Water Treatment Controller - Modbus Common Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "modbus_common.h"
#include <string.h>

/* CRC-16 lookup table for Modbus RTU */
static const uint16_t crc16_table[256] = {
    0x0000, 0xC0C1, 0xC181, 0x0140, 0xC301, 0x03C0, 0x0280, 0xC241,
    0xC601, 0x06C0, 0x0780, 0xC741, 0x0500, 0xC5C1, 0xC481, 0x0440,
    0xCC01, 0x0CC0, 0x0D80, 0xCD41, 0x0F00, 0xCFC1, 0xCE81, 0x0E40,
    0x0A00, 0xCAC1, 0xCB81, 0x0B40, 0xC901, 0x09C0, 0x0880, 0xC841,
    0xD801, 0x18C0, 0x1980, 0xD941, 0x1B00, 0xDBC1, 0xDA81, 0x1A40,
    0x1E00, 0xDEC1, 0xDF81, 0x1F40, 0xDD01, 0x1DC0, 0x1C80, 0xDC41,
    0x1400, 0xD4C1, 0xD581, 0x1540, 0xD701, 0x17C0, 0x1680, 0xD641,
    0xD201, 0x12C0, 0x1380, 0xD341, 0x1100, 0xD1C1, 0xD081, 0x1040,
    0xF001, 0x30C0, 0x3180, 0xF141, 0x3300, 0xF3C1, 0xF281, 0x3240,
    0x3600, 0xF6C1, 0xF781, 0x3740, 0xF501, 0x35C0, 0x3480, 0xF441,
    0x3C00, 0xFCC1, 0xFD81, 0x3D40, 0xFF01, 0x3FC0, 0x3E80, 0xFE41,
    0xFA01, 0x3AC0, 0x3B80, 0xFB41, 0x3900, 0xF9C1, 0xF881, 0x3840,
    0x2800, 0xE8C1, 0xE981, 0x2940, 0xEB01, 0x2BC0, 0x2A80, 0xEA41,
    0xEE01, 0x2EC0, 0x2F80, 0xEF41, 0x2D00, 0xEDC1, 0xEC81, 0x2C40,
    0xE401, 0x24C0, 0x2580, 0xE541, 0x2700, 0xE7C1, 0xE681, 0x2640,
    0x2200, 0xE2C1, 0xE381, 0x2340, 0xE101, 0x21C0, 0x2080, 0xE041,
    0xA001, 0x60C0, 0x6180, 0xA141, 0x6300, 0xA3C1, 0xA281, 0x6240,
    0x6600, 0xA6C1, 0xA781, 0x6740, 0xA501, 0x65C0, 0x6480, 0xA441,
    0x6C00, 0xACC1, 0xAD81, 0x6D40, 0xAF01, 0x6FC0, 0x6E80, 0xAE41,
    0xAA01, 0x6AC0, 0x6B80, 0xAB41, 0x6900, 0xA9C1, 0xA881, 0x6840,
    0x7800, 0xB8C1, 0xB981, 0x7940, 0xBB01, 0x7BC0, 0x7A80, 0xBA41,
    0xBE01, 0x7EC0, 0x7F80, 0xBF41, 0x7D00, 0xBDC1, 0xBC81, 0x7C40,
    0xB401, 0x74C0, 0x7580, 0xB541, 0x7700, 0xB7C1, 0xB681, 0x7640,
    0x7200, 0xB2C1, 0xB381, 0x7340, 0xB101, 0x71C0, 0x7080, 0xB041,
    0x5000, 0x90C1, 0x9181, 0x5140, 0x9301, 0x53C0, 0x5280, 0x9241,
    0x9601, 0x56C0, 0x5780, 0x9741, 0x5500, 0x95C1, 0x9481, 0x5440,
    0x9C01, 0x5CC0, 0x5D80, 0x9D41, 0x5F00, 0x9FC1, 0x9E81, 0x5E40,
    0x5A00, 0x9AC1, 0x9B81, 0x5B40, 0x9901, 0x59C0, 0x5880, 0x9841,
    0x8801, 0x48C0, 0x4980, 0x8941, 0x4B00, 0x8BC1, 0x8A81, 0x4A40,
    0x4E00, 0x8EC1, 0x8F81, 0x4F40, 0x8D01, 0x4DC0, 0x4C80, 0x8C41,
    0x4400, 0x84C1, 0x8581, 0x4540, 0x8701, 0x47C0, 0x4680, 0x8641,
    0x8201, 0x42C0, 0x4380, 0x8341, 0x4100, 0x81C1, 0x8081, 0x4040
};

uint16_t modbus_crc16(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        uint8_t idx = (crc ^ data[i]) & 0xFF;
        crc = (crc >> 8) ^ crc16_table[idx];
    }
    return crc;
}

uint16_t modbus_get_uint16_be(const uint8_t *data) {
    return (uint16_t)((data[0] << 8) | data[1]);
}

void modbus_set_uint16_be(uint8_t *data, uint16_t value) {
    data[0] = (value >> 8) & 0xFF;
    data[1] = value & 0xFF;
}

uint32_t modbus_get_uint32_be(const uint8_t *data) {
    return ((uint32_t)data[0] << 24) |
           ((uint32_t)data[1] << 16) |
           ((uint32_t)data[2] << 8) |
           (uint32_t)data[3];
}

void modbus_set_uint32_be(uint8_t *data, uint32_t value) {
    data[0] = (value >> 24) & 0xFF;
    data[1] = (value >> 16) & 0xFF;
    data[2] = (value >> 8) & 0xFF;
    data[3] = value & 0xFF;
}

float modbus_get_float32_be(const uint8_t *data) {
    union {
        uint32_t u;
        float f;
    } val;
    val.u = modbus_get_uint32_be(data);
    return val.f;
}

void modbus_set_float32_be(uint8_t *data, float value) {
    union {
        uint32_t u;
        float f;
    } val;
    val.f = value;
    modbus_set_uint32_be(data, val.u);
}

int modbus_build_read_request(modbus_pdu_t *pdu, uint8_t fc,
                               uint16_t start_addr, uint16_t quantity) {
    if (!pdu) return -1;

    pdu->function_code = fc;
    modbus_set_uint16_be(&pdu->data[0], start_addr);
    modbus_set_uint16_be(&pdu->data[2], quantity);
    pdu->data_len = 4;

    return 0;
}

int modbus_build_write_single_register(modbus_pdu_t *pdu,
                                        uint16_t addr, uint16_t value) {
    if (!pdu) return -1;

    pdu->function_code = MODBUS_FC_WRITE_SINGLE_REGISTER;
    modbus_set_uint16_be(&pdu->data[0], addr);
    modbus_set_uint16_be(&pdu->data[2], value);
    pdu->data_len = 4;

    return 0;
}

int modbus_build_write_multiple_registers(modbus_pdu_t *pdu,
                                           uint16_t start_addr,
                                           uint16_t quantity,
                                           const uint16_t *values) {
    if (!pdu || !values || quantity > MODBUS_MAX_WRITE_REGISTERS) return -1;

    pdu->function_code = MODBUS_FC_WRITE_MULTIPLE_REGISTERS;
    modbus_set_uint16_be(&pdu->data[0], start_addr);
    modbus_set_uint16_be(&pdu->data[2], quantity);
    pdu->data[4] = quantity * 2;

    for (uint16_t i = 0; i < quantity; i++) {
        modbus_set_uint16_be(&pdu->data[5 + i * 2], values[i]);
    }
    pdu->data_len = 5 + quantity * 2;

    return 0;
}

int modbus_build_write_single_coil(modbus_pdu_t *pdu,
                                    uint16_t addr, bool value) {
    if (!pdu) return -1;

    pdu->function_code = MODBUS_FC_WRITE_SINGLE_COIL;
    modbus_set_uint16_be(&pdu->data[0], addr);
    modbus_set_uint16_be(&pdu->data[2], value ? 0xFF00 : 0x0000);
    pdu->data_len = 4;

    return 0;
}

int modbus_build_write_multiple_coils(modbus_pdu_t *pdu,
                                       uint16_t start_addr,
                                       uint16_t quantity,
                                       const uint8_t *values) {
    if (!pdu || !values || quantity > MODBUS_MAX_WRITE_BITS) return -1;

    uint8_t byte_count = (quantity + 7) / 8;

    pdu->function_code = MODBUS_FC_WRITE_MULTIPLE_COILS;
    modbus_set_uint16_be(&pdu->data[0], start_addr);
    modbus_set_uint16_be(&pdu->data[2], quantity);
    pdu->data[4] = byte_count;
    memcpy(&pdu->data[5], values, byte_count);
    pdu->data_len = 5 + byte_count;

    return 0;
}

int modbus_parse_read_response(const modbus_pdu_t *pdu,
                                uint8_t *data, uint16_t *data_len) {
    if (!pdu || !data || !data_len) return -1;

    if (modbus_is_exception(pdu)) {
        return -1;
    }

    uint8_t byte_count = pdu->data[0];
    if (byte_count > pdu->data_len - 1) return -1;

    memcpy(data, &pdu->data[1], byte_count);
    *data_len = byte_count;

    return 0;
}

int modbus_parse_write_response(const modbus_pdu_t *pdu,
                                 uint16_t *addr, uint16_t *value) {
    if (!pdu || !addr || !value) return -1;

    if (modbus_is_exception(pdu)) {
        return -1;
    }

    *addr = modbus_get_uint16_be(&pdu->data[0]);
    *value = modbus_get_uint16_be(&pdu->data[2]);

    return 0;
}

bool modbus_is_exception(const modbus_pdu_t *pdu) {
    return pdu && (pdu->function_code & 0x80);
}

modbus_exception_t modbus_get_exception(const modbus_pdu_t *pdu) {
    if (!pdu || !(pdu->function_code & 0x80)) {
        return MODBUS_EX_NONE;
    }
    return (modbus_exception_t)pdu->data[0];
}

const char *modbus_exception_string(modbus_exception_t ex) {
    switch (ex) {
    case MODBUS_EX_NONE:                     return "No exception";
    case MODBUS_EX_ILLEGAL_FUNCTION:         return "Illegal function";
    case MODBUS_EX_ILLEGAL_DATA_ADDRESS:     return "Illegal data address";
    case MODBUS_EX_ILLEGAL_DATA_VALUE:       return "Illegal data value";
    case MODBUS_EX_SLAVE_DEVICE_FAILURE:     return "Slave device failure";
    case MODBUS_EX_ACKNOWLEDGE:              return "Acknowledge";
    case MODBUS_EX_SLAVE_BUSY:               return "Slave busy";
    case MODBUS_EX_MEMORY_PARITY_ERROR:      return "Memory parity error";
    case MODBUS_EX_GATEWAY_PATH_UNAVAILABLE: return "Gateway path unavailable";
    case MODBUS_EX_GATEWAY_TARGET_FAILED:    return "Gateway target failed";
    default:                                 return "Unknown exception";
    }
}

const char *modbus_function_string(uint8_t fc) {
    switch (fc & 0x7F) {
    case MODBUS_FC_READ_COILS:               return "Read Coils";
    case MODBUS_FC_READ_DISCRETE_INPUTS:     return "Read Discrete Inputs";
    case MODBUS_FC_READ_HOLDING_REGISTERS:   return "Read Holding Registers";
    case MODBUS_FC_READ_INPUT_REGISTERS:     return "Read Input Registers";
    case MODBUS_FC_WRITE_SINGLE_COIL:        return "Write Single Coil";
    case MODBUS_FC_WRITE_SINGLE_REGISTER:    return "Write Single Register";
    case MODBUS_FC_WRITE_MULTIPLE_COILS:     return "Write Multiple Coils";
    case MODBUS_FC_WRITE_MULTIPLE_REGISTERS: return "Write Multiple Registers";
    case MODBUS_FC_READ_WRITE_REGISTERS:     return "Read/Write Registers";
    default:                                 return "Unknown function";
    }
}
