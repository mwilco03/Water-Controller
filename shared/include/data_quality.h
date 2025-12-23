/**
 * @file data_quality.h
 * @brief Shared data quality definitions for Water-Controller and Water-Treat
 *
 * This header provides canonical definitions for OPC UA-compatible data quality
 * indicators used in the 5-byte PROFINET sensor data format.
 *
 * Per PROFINET_DATA_FORMAT_SPECIFICATION.md:
 *   Bytes 0-3: Float32 value (big-endian)
 *   Byte 4:    Quality indicator (this header)
 *
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef SHARED_DATA_QUALITY_H
#define SHARED_DATA_QUALITY_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Data quality indicators (OPC UA compatible)
 *
 * These values follow the OPC UA quality encoding where:
 * - Bits 6-7 indicate the quality category
 * - 0x00 = Good, 0x40 = Uncertain, 0x80 = Bad, 0xC0 = Special
 *
 * Used in byte 4 of the 5-byte PROFINET sensor input format.
 */
typedef enum {
    QUALITY_GOOD          = 0x00,  /**< Fresh, valid reading */
    QUALITY_UNCERTAIN     = 0x40,  /**< May be stale, sensor degraded, or at limit */
    QUALITY_BAD           = 0x80,  /**< Sensor failure, invalid reading */
    QUALITY_NOT_CONNECTED = 0xC0,  /**< No communication with sensor/device */
} data_quality_t;

/**
 * @brief Check if quality indicates valid data
 * @param quality Quality value to check
 * @return true if GOOD or UNCERTAIN, false if BAD or NOT_CONNECTED
 */
static inline int quality_is_usable(data_quality_t quality) {
    return (quality == QUALITY_GOOD || quality == QUALITY_UNCERTAIN);
}

/**
 * @brief Check if quality indicates good data
 * @param quality Quality value to check
 * @return true if GOOD, false otherwise
 */
static inline int quality_is_good(data_quality_t quality) {
    return (quality == QUALITY_GOOD);
}

/**
 * @brief Get string representation of quality
 * @param quality Quality value
 * @return Human-readable string
 */
static inline const char* quality_to_string(data_quality_t quality) {
    switch (quality) {
        case QUALITY_GOOD:          return "Good";
        case QUALITY_UNCERTAIN:     return "Uncertain";
        case QUALITY_BAD:           return "Bad";
        case QUALITY_NOT_CONNECTED: return "Not Connected";
        default:                    return "Unknown";
    }
}

/**
 * @brief Get worst quality between two values
 * @param q1 First quality value
 * @param q2 Second quality value
 * @return The worse of the two quality values
 */
static inline data_quality_t quality_worst(data_quality_t q1, data_quality_t q2) {
    return (q1 > q2) ? q1 : q2;
}

/**
 * @brief Get best quality between two values
 * @param q1 First quality value
 * @param q2 Second quality value
 * @return The better of the two quality values
 */
static inline data_quality_t quality_best(data_quality_t q1, data_quality_t q2) {
    return (q1 < q2) ? q1 : q2;
}

#ifdef __cplusplus
}
#endif

#endif /* SHARED_DATA_QUALITY_H */
