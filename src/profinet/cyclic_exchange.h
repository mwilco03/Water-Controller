/*
 * Water Treatment Controller - Cyclic Data Exchange
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_CYCLIC_EXCHANGE_H
#define WTC_CYCLIC_EXCHANGE_H

#include "profinet_controller.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Allocate IOCR data buffers for an AR
 *
 * @param ar          Application Relationship to allocate buffers for
 * @param input_slots Number of input slots (sensors) - 4 bytes per slot
 * @param output_slots Number of output slots (actuators) - 4 bytes per slot
 * @return WTC_OK on success, error code otherwise
 */
wtc_result_t allocate_iocr_buffers(profinet_ar_t *ar,
                                    int input_slots,
                                    int output_slots);

/**
 * Free IOCR data buffers for an AR
 *
 * @param ar Application Relationship to free buffers for
 */
void free_iocr_buffers(profinet_ar_t *ar);

/**
 * Parse cyclic input frame from RTU
 *
 * @param ar            Application Relationship
 * @param frame         Frame data
 * @param frame_len     Frame length
 * @param cycle_counter Output: cycle counter from frame (can be NULL)
 * @param data_status   Output: data status from frame (can be NULL)
 * @return WTC_OK on success, error code otherwise
 */
wtc_result_t parse_input_frame(profinet_ar_t *ar,
                                const uint8_t *frame,
                                size_t frame_len,
                                uint16_t *cycle_counter,
                                uint8_t *data_status);

/**
 * Get input slot data as float with quality
 *
 * RTU dictates slot configuration; controller adapts dynamically.
 * Uses 5-byte sensor format: Float32 (big-endian) + Quality byte
 *
 * @param ar          Application Relationship
 * @param slot_index  0-based index into input data buffer
 * @param value       Output: float value from slot
 * @param status      Output: I/O provider status (can be NULL)
 * @param quality     Output: Data quality from 5th byte (can be NULL)
 * @return WTC_OK on success, error code otherwise
 */
wtc_result_t get_slot_input_float(profinet_ar_t *ar,
                                   int slot_index,
                                   float *value,
                                   iops_t *status,
                                   data_quality_t *quality);

/**
 * Unpack sensor data from 5-byte PROFINET format
 *
 * Format per IEC-61158-6 Section 4.10.3.3:
 * Bytes 0-3: Float32 value (big-endian, IEEE 754)
 * Byte 4:    Quality indicator (OPC UA compatible)
 *
 * @param data        Pointer to 5-byte sensor data
 * @param len         Length of data buffer (must be >= 5)
 * @param reading     Output: sensor_reading_t with value, quality, timestamp
 * @return WTC_OK on success, error code otherwise
 */
wtc_result_t unpack_sensor_from_profinet(const uint8_t *data,
                                          size_t len,
                                          sensor_reading_t *reading);

/**
 * Set output slot data
 *
 * RTU dictates slot configuration; controller adapts dynamically.
 *
 * @param ar          Application Relationship
 * @param slot_index  0-based index into output data buffer
 * @param command     Actuator command byte
 * @param pwm_duty    PWM duty cycle (0-255)
 * @return WTC_OK on success, error code otherwise
 */
wtc_result_t set_slot_output(profinet_ar_t *ar,
                              int slot_index,
                              uint8_t command,
                              uint8_t pwm_duty);

#ifdef __cplusplus
}
#endif

#endif /* WTC_CYCLIC_EXCHANGE_H */
