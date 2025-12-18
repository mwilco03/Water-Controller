/*
 * Water Treatment Controller - Cyclic Data Exchange
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "profinet_controller.h"
#include "profinet_frame.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>

/* Cyclic exchange context */
typedef struct {
    profinet_controller_t *controller;

    /* Timing */
    uint32_t cycle_time_us;
    uint16_t cycle_counter;

    /* Statistics */
    uint64_t frames_sent;
    uint64_t frames_received;
    uint64_t frame_errors;
    uint64_t overruns;
} cyclic_context_t;

/* Build cyclic output frame */
static wtc_result_t build_output_frame(profinet_ar_t *ar,
                                        uint8_t *frame,
                                        size_t *frame_len,
                                        uint16_t cycle_counter) {
    if (!ar || !frame || !frame_len) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Find output IOCR */
    int output_iocr = -1;
    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_OUTPUT) {
            output_iocr = i;
            break;
        }
    }

    if (output_iocr < 0) {
        return WTC_ERROR_NOT_FOUND;
    }

    frame_builder_t builder;
    frame_builder_init(&builder, frame, *frame_len, NULL);

    /* Ethernet header - will be filled by caller */
    builder.position = ETH_HEADER_LEN;

    /* Frame ID */
    uint16_t frame_id = ar->iocr[output_iocr].frame_id;
    frame_build_rt_header(&builder, frame_id);

    /* Data */
    if (ar->iocr[output_iocr].data_buffer &&
        ar->iocr[output_iocr].data_length > 0) {
        frame_append_data(&builder,
                          ar->iocr[output_iocr].data_buffer,
                          ar->iocr[output_iocr].data_length);
    }

    /* IOPS for each subslot (one byte per slot, based on actual data length) */
    int output_slot_count = ar->iocr[output_iocr].data_length / 4;
    for (int slot = 0; slot < output_slot_count; slot++) {
        uint8_t iops = IOPS_GOOD;
        frame_append_data(&builder, &iops, 1);
    }

    /* RT header (cycle counter, data status, transfer status) */
    uint16_t net_cycle = htons(cycle_counter);
    frame_append_data(&builder, &net_cycle, 2);

    uint8_t data_status = PROFINET_DATA_STATUS_STATE |
                          PROFINET_DATA_STATUS_VALID |
                          PROFINET_DATA_STATUS_RUN;
    frame_append_data(&builder, &data_status, 1);

    uint8_t transfer_status = 0x00;
    frame_append_data(&builder, &transfer_status, 1);

    /* Pad to minimum size */
    frame_append_padding(&builder, ETH_MIN_FRAME_LEN);

    *frame_len = frame_builder_length(&builder);
    return WTC_OK;
}

/* Parse cyclic input frame */
wtc_result_t parse_input_frame(profinet_ar_t *ar,
                                const uint8_t *frame,
                                size_t frame_len,
                                uint16_t *cycle_counter,
                                uint8_t *data_status) {
    if (!ar || !frame) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Find input IOCR */
    int input_iocr = -1;
    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_INPUT) {
            input_iocr = i;
            break;
        }
    }

    if (input_iocr < 0) {
        return WTC_ERROR_NOT_FOUND;
    }

    frame_parser_t parser;
    frame_parser_init(&parser, frame, frame_len);

    /* Skip Ethernet header */
    parser.position = ETH_HEADER_LEN;

    /* Parse frame ID */
    uint16_t frame_id;
    frame_read_u16(&parser, &frame_id);

    /* Verify frame ID matches expected */
    if (frame_id != ar->iocr[input_iocr].frame_id) {
        return WTC_ERROR_PROTOCOL;
    }

    /* Read data */
    size_t data_len = ar->iocr[input_iocr].data_length;
    if (ar->iocr[input_iocr].data_buffer && data_len > 0) {
        if (frame_parser_remaining(&parser) >= data_len) {
            frame_read_bytes(&parser, ar->iocr[input_iocr].data_buffer, data_len);
        }
    }

    /* Skip IOCS bytes (one per slot, based on actual data length) */
    int input_slot_count = data_len / 4;
    frame_skip_bytes(&parser, input_slot_count);

    /* Read RT header */
    if (cycle_counter && frame_parser_remaining(&parser) >= 2) {
        frame_read_u16(&parser, cycle_counter);
    }

    if (data_status && frame_parser_remaining(&parser) >= 1) {
        frame_read_u8(&parser, data_status);
    }

    /* Update timing */
    ar->iocr[input_iocr].last_frame_time_us = time_get_monotonic_us();

    return WTC_OK;
}

/* Check for frame timeout */
bool check_frame_timeout(profinet_ar_t *ar, uint32_t timeout_us) {
    if (!ar) return true;

    uint64_t now_us = time_get_monotonic_us();

    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_INPUT) {
            if (ar->iocr[i].last_frame_time_us > 0 &&
                now_us - ar->iocr[i].last_frame_time_us > timeout_us) {
                return true;
            }
        }
    }

    return false;
}

/* Get input slot data (float) - dynamic slot support
 * slot_index: 0-based index into the input data buffer
 * RTU dictates slot configuration; controller adapts dynamically
 */
wtc_result_t get_slot_input_float(profinet_ar_t *ar,
                                   int slot_index,
                                   float *value,
                                   iops_t *status) {
    if (!ar || !value || slot_index < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Find input IOCR */
    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_INPUT) {
            /* Calculate offset - no hardcoded slot limits */
            size_t offset = slot_index * 4; /* 4 bytes per float */
            if (offset + 4 <= ar->iocr[i].data_length &&
                ar->iocr[i].data_buffer) {
                /* Read float value (already in host byte order from device) */
                uint32_t int_val;
                memcpy(&int_val, ar->iocr[i].data_buffer + offset, 4);
                int_val = ntohl(int_val); /* Network to host */
                memcpy(value, &int_val, 4);

                if (status) {
                    *status = IOPS_GOOD;
                }
                return WTC_OK;
            }
        }
    }

    if (status) {
        *status = IOPS_BAD;
    }
    return WTC_ERROR_NOT_FOUND;
}

/* Set output slot data - dynamic slot support
 * slot_index: 0-based index into the output data buffer
 * RTU dictates slot configuration; controller adapts dynamically
 */
wtc_result_t set_slot_output(profinet_ar_t *ar,
                              int slot_index,
                              uint8_t command,
                              uint8_t pwm_duty) {
    if (!ar || slot_index < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Find output IOCR */
    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_OUTPUT) {
            /* Calculate offset - no hardcoded slot limits */
            size_t offset = slot_index * 4; /* 4 bytes per actuator */
            if (offset + 4 <= ar->iocr[i].data_length &&
                ar->iocr[i].data_buffer) {
                actuator_output_t output;
                output.command = command;
                output.pwm_duty = pwm_duty;
                output.reserved[0] = 0;
                output.reserved[1] = 0;

                memcpy(ar->iocr[i].data_buffer + offset, &output, 4);
                return WTC_OK;
            }
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Allocate IOCR data buffers */
wtc_result_t allocate_iocr_buffers(profinet_ar_t *ar,
                                    int input_slots,
                                    int output_slots) {
    if (!ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Create input IOCR */
    if (input_slots > 0 && ar->iocr_count < PROFINET_MAX_IOCR) {
        int idx = ar->iocr_count++;
        ar->iocr[idx].type = IOCR_TYPE_INPUT;
        ar->iocr[idx].frame_id = PROFINET_FRAME_ID_RTC1_MIN + ar->session_key * 2;
        ar->iocr[idx].data_length = input_slots * 4; /* 4 bytes per slot */
        ar->iocr[idx].data_buffer = calloc(1, ar->iocr[idx].data_length);
        if (!ar->iocr[idx].data_buffer) {
            return WTC_ERROR_NO_MEMORY;
        }
    }

    /* Create output IOCR */
    if (output_slots > 0 && ar->iocr_count < PROFINET_MAX_IOCR) {
        int idx = ar->iocr_count++;
        ar->iocr[idx].type = IOCR_TYPE_OUTPUT;
        ar->iocr[idx].frame_id = PROFINET_FRAME_ID_RTC1_MIN + ar->session_key * 2 + 1;
        ar->iocr[idx].data_length = output_slots * 4; /* 4 bytes per slot */
        ar->iocr[idx].data_buffer = calloc(1, ar->iocr[idx].data_length);
        if (!ar->iocr[idx].data_buffer) {
            return WTC_ERROR_NO_MEMORY;
        }
    }

    return WTC_OK;
}

/* Free IOCR data buffers */
void free_iocr_buffers(profinet_ar_t *ar) {
    if (!ar) return;

    for (int i = 0; i < ar->iocr_count; i++) {
        free(ar->iocr[i].data_buffer);
        ar->iocr[i].data_buffer = NULL;
    }
    ar->iocr_count = 0;
}

/* Get cycle counter for AR */
uint16_t get_cycle_counter(profinet_ar_t *ar) {
    if (!ar) return 0;

    /* Find any IOCR and get its data */
    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_INPUT) {
            /* Extract cycle counter from last received frame */
            /* This is simplified - real implementation would track this */
            return 0;
        }
    }
    return 0;
}

/* Validate cyclic data timing */
bool validate_cyclic_timing(profinet_ar_t *ar,
                             uint32_t expected_cycle_us,
                             uint32_t tolerance_percent) {
    if (!ar || expected_cycle_us == 0) return false;

    uint64_t now_us = time_get_monotonic_us();
    uint64_t tolerance_us = (expected_cycle_us * tolerance_percent) / 100;

    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_INPUT &&
            ar->iocr[i].last_frame_time_us > 0) {
            uint64_t elapsed = now_us - ar->iocr[i].last_frame_time_us;

            /* Allow some initial frames to establish timing */
            if (elapsed > expected_cycle_us + tolerance_us) {
                return false;
            }
        }
    }

    return true;
}
