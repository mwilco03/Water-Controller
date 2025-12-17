/*
 * Water Treatment Controller - CRC Utilities
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_CRC_H
#define WTC_CRC_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* CRC-16 (PROFINET uses CRC-16-CCITT) */
uint16_t crc16_ccitt(const uint8_t *data, size_t len);
uint16_t crc16_ccitt_update(uint16_t crc, const uint8_t *data, size_t len);

/* CRC-32 (IEEE 802.3) */
uint32_t crc32(const uint8_t *data, size_t len);
uint32_t crc32_update(uint32_t crc, const uint8_t *data, size_t len);

/* Verify CRC-32 FCS (Frame Check Sequence) */
bool crc32_verify_fcs(const uint8_t *frame, size_t len);

#ifdef __cplusplus
}
#endif

#endif /* WTC_CRC_H */
