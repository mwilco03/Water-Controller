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
#include <arpa/inet.h>

/* Track last received cycle counter for replay detection (PN-H1 fix) */
static uint16_t last_cycle_counters[PROFINET_MAX_IOCR];
static bool cycle_counter_initialized[PROFINET_MAX_IOCR];

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

    /* C-SDU fully read into buffer (user_data + IOPS + IOCS).
     * RT trailer (cycle counter + data status + transfer status) follows. */

    /* Read RT header */
    uint16_t received_counter = 0;
    if (frame_parser_remaining(&parser) >= 2) {
        frame_read_u16(&parser, &received_counter);
        if (cycle_counter) {
            *cycle_counter = received_counter;
        }

        /* Validate sequence number for replay detection (PN-H1 fix) */
        if (input_iocr < PROFINET_MAX_IOCR) {
            if (cycle_counter_initialized[input_iocr]) {
                /* Check for replay - counter should be incrementing (with 16-bit wrap) */
                uint16_t expected_min = last_cycle_counters[input_iocr] + 1;
                uint16_t expected_max = last_cycle_counters[input_iocr] + 100; /* Allow some gap */

                /* Handle 16-bit wraparound */
                bool valid = false;
                if (expected_max >= expected_min) {
                    valid = (received_counter >= expected_min && received_counter <= expected_max);
                } else {
                    /* Wrapped around */
                    valid = (received_counter >= expected_min || received_counter <= expected_max);
                }

                if (!valid && received_counter == last_cycle_counters[input_iocr]) {
                    LOG_WARN("Duplicate/replay frame detected: counter=%u", received_counter);
                    return WTC_ERROR_PROTOCOL;
                }
            }
            last_cycle_counters[input_iocr] = received_counter;
            cycle_counter_initialized[input_iocr] = true;
        }
    }

    if (data_status && frame_parser_remaining(&parser) >= 1) {
        frame_read_u8(&parser, data_status);
    }

    /* Update timing */
    ar->iocr[input_iocr].last_frame_time_us = time_get_monotonic_us();

    return WTC_OK;
}

/* Sensor data size: 5 bytes (Float32 + Quality byte) - current format */
#define SENSOR_SLOT_SIZE 5
/* Legacy sensor format: 4 bytes (Float32 only, no quality) */
#define SENSOR_SLOT_SIZE_LEGACY 4

/* Track format mismatch for logging (avoid spam) - rate limited via LOG_WARN_ONCE pattern */

/* Unpack sensor data from PROFINET format with backwards compatibility
 *
 * Current format (5-byte) per IEC-61158-6 Section 4.10.3.3:
 *   Bytes 0-3: Float32 value (big-endian, IEEE 754)
 *   Byte 4:    Quality indicator (OPC UA compatible)
 *
 * Legacy format (4-byte) for backwards compatibility:
 *   Bytes 0-3: Float32 value (big-endian, IEEE 754)
 *   Quality:   Assumed UNCERTAIN (0x40) since no quality byte present
 *
 * Per HARMONIOUS_SYSTEM_DESIGN.md Field Deployment Reality:
 * - MUST accept older format variants
 * - MUST NOT refuse connection based on format mismatch
 * - Log mismatch but continue operation
 */
wtc_result_t unpack_sensor_from_profinet(const uint8_t *data,
                                          size_t len,
                                          sensor_reading_t *reading) {
    if (!data || !reading) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Accept both 4-byte (legacy) and 5-byte (current) formats */
    if (len < SENSOR_SLOT_SIZE_LEGACY) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Convert from big-endian (network byte order) */
    uint32_t be;
    memcpy(&be, data, 4);
    uint32_t raw = ntohl(be);
    memcpy(&reading->value, &raw, sizeof(float));

    /* Extract quality byte if present (5-byte format) */
    if (len >= SENSOR_SLOT_SIZE) {
        reading->quality = (data_quality_t)data[4];
    } else {
        /* Legacy 4-byte format - no quality byte
         * Per HARMONIOUS_SYSTEM_DESIGN.md: treat as UNCERTAIN
         * Log once to avoid spam, but continue operating
         */
        reading->quality = QUALITY_UNCERTAIN;

        static bool legacy_format_logged = false;
        if (!legacy_format_logged) {
            LOG_WARN("Legacy 4-byte sensor format detected (no quality byte). "
                     "Treating as UNCERTAIN. Consider upgrading RTU firmware. "
                     "System continues normal operation.");
            legacy_format_logged = true;
        }
    }

    reading->timestamp_us = time_get_monotonic_us();

    return WTC_OK;
}

/* Get input slot data (float) with quality - dynamic slot support
 * slot_index: 0-based index into the input data buffer
 * RTU dictates slot configuration; controller adapts dynamically
 * Uses 5-byte sensor format: Float32 (big-endian) + Quality byte
 */
wtc_result_t get_slot_input_float(profinet_ar_t *ar,
                                   int slot_index,
                                   float *value,
                                   iops_t *status,
                                   data_quality_t *quality) {
    if (!ar || !value || slot_index < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Find input IOCR */
    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_INPUT) {
            /* Calculate offset - 5 bytes per sensor slot */
            size_t offset = slot_index * SENSOR_SLOT_SIZE;
            if (offset + SENSOR_SLOT_SIZE <= ar->iocr[i].user_data_length &&
                ar->iocr[i].data_buffer) {
                /* Unpack using 5-byte format */
                sensor_reading_t reading;
                wtc_result_t res = unpack_sensor_from_profinet(
                    ar->iocr[i].data_buffer + offset,
                    SENSOR_SLOT_SIZE,
                    &reading);

                if (res == WTC_OK) {
                    *value = reading.value;

                    if (status) {
                        /* Map quality to IOPS for backwards compatibility */
                        *status = (reading.quality == QUALITY_GOOD) ? IOPS_GOOD : IOPS_BAD;
                    }

                    if (quality) {
                        *quality = reading.quality;
                    }

                    return WTC_OK;
                }
            }
        }
    }

    if (status) {
        *status = IOPS_BAD;
    }
    if (quality) {
        *quality = QUALITY_NOT_CONNECTED;
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
            if (offset + 4 <= ar->iocr[i].user_data_length &&
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

/* Actuator slot size: 4 bytes (unchanged) */
#define ACTUATOR_SLOT_SIZE 4

/* Minimum c_sdu_length for RT_CLASS_1 per IEC 61158-6 (pf_cmdev.c:3095) */
#define IOCR_MIN_DATA_LENGTH 40

/* DAP slot 0 always contributes 3 submodules to both IOCRs */
#define DAP_SUBMODULE_COUNT 3

/* Allocate IOCR data buffers.
 * Input slots use 5-byte format (Float32 + Quality).
 * Output slots use 4-byte format (actuator_output_t).
 *
 * Both Input and Output IOCRs are always created — PROFINET requires them
 * even for DAP-only connections (with zero application-module data).
 *
 * Buffer layout (= C-SDU on the wire):
 *   [user_data bytes][IOPS bytes (1 per IODataObject)][IOCS bytes (1 per entry)]
 * Minimum c_sdu_length is 40 per IEC 61158-6.
 */
wtc_result_t allocate_iocr_buffers(profinet_ar_t *ar,
                                    int input_slots,
                                    int output_slots) {
    if (!ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Always create input IOCR (device → controller data).
     * IODataObjects: 3 DAP + input application submodules.
     * IOCS entries:  3 DAP + output application submodules. */
    if (ar->iocr_count < PROFINET_MAX_IOCR) {
        int idx = ar->iocr_count++;
        ar->iocr[idx].type = IOCR_TYPE_INPUT;
        ar->iocr[idx].frame_id = 0xC001;  /* RT_CLASS_1, validated at pf_cmdev.c:3136 */

        uint16_t user_data = (uint16_t)(input_slots * SENSOR_SLOT_SIZE);
        uint16_t iodata = DAP_SUBMODULE_COUNT + (uint16_t)input_slots;
        uint16_t iocs = DAP_SUBMODULE_COUNT + (uint16_t)output_slots;
        uint32_t c_sdu = (uint32_t)(user_data + iodata + iocs);
        if (c_sdu < IOCR_MIN_DATA_LENGTH) {
            c_sdu = IOCR_MIN_DATA_LENGTH;
        }

        ar->iocr[idx].user_data_length = user_data;
        ar->iocr[idx].iodata_count = iodata;
        ar->iocr[idx].iocs_count = iocs;
        ar->iocr[idx].data_length = c_sdu;
        ar->iocr[idx].data_buffer = calloc(1, c_sdu);
        if (!ar->iocr[idx].data_buffer) {
            return WTC_ERROR_NO_MEMORY;
        }
    }

    /* Always create output IOCR (controller → device data).
     * Frame ID 0xFFFF = let device assign from RT_CLASS_1 range
     * (pf_cmdev_fix_frame_id at pf_cmdev.c:4660-4698).
     * IODataObjects: 3 DAP + output application submodules.
     * IOCS entries:  3 DAP + input application submodules. */
    if (ar->iocr_count < PROFINET_MAX_IOCR) {
        int idx = ar->iocr_count++;
        ar->iocr[idx].type = IOCR_TYPE_OUTPUT;
        ar->iocr[idx].frame_id = 0xFFFF;

        uint16_t user_data = (uint16_t)(output_slots * ACTUATOR_SLOT_SIZE);
        uint16_t iodata = DAP_SUBMODULE_COUNT + (uint16_t)output_slots;
        uint16_t iocs = DAP_SUBMODULE_COUNT + (uint16_t)input_slots;
        uint32_t c_sdu = (uint32_t)(user_data + iodata + iocs);
        if (c_sdu < IOCR_MIN_DATA_LENGTH) {
            c_sdu = IOCR_MIN_DATA_LENGTH;
        }

        ar->iocr[idx].user_data_length = user_data;
        ar->iocr[idx].iodata_count = iodata;
        ar->iocr[idx].iocs_count = iocs;
        ar->iocr[idx].data_length = c_sdu;
        ar->iocr[idx].data_buffer = calloc(1, c_sdu);
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

