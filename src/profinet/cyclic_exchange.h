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
 * Check for frame timeout on an AR
 *
 * @param ar          Application Relationship
 * @param timeout_us  Timeout in microseconds
 * @return true if timeout occurred, false otherwise
 */
bool check_frame_timeout(profinet_ar_t *ar, uint32_t timeout_us);

/**
 * Get input slot data as float
 *
 * RTU dictates slot configuration; controller adapts dynamically.
 *
 * @param ar          Application Relationship
 * @param slot_index  0-based index into input data buffer
 * @param value       Output: float value from slot
 * @param status      Output: I/O provider status (can be NULL)
 * @return WTC_OK on success, error code otherwise
 */
wtc_result_t get_slot_input_float(profinet_ar_t *ar,
                                   int slot_index,
                                   float *value,
                                   iops_t *status);

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

/**
 * Get cycle counter for AR
 *
 * @param ar Application Relationship
 * @return Current cycle counter value
 */
uint16_t get_cycle_counter(profinet_ar_t *ar);

/**
 * Validate cyclic data timing
 *
 * @param ar                 Application Relationship
 * @param expected_cycle_us  Expected cycle time in microseconds
 * @param tolerance_percent  Allowed deviation percentage (e.g., 10 = 10%)
 * @return true if timing is valid, false otherwise
 */
bool validate_cyclic_timing(profinet_ar_t *ar,
                             uint32_t expected_cycle_us,
                             uint32_t tolerance_percent);

#ifdef __cplusplus
}
#endif

#endif /* WTC_CYCLIC_EXCHANGE_H */
