/*
 * Water Treatment Controller - Data Compression
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_COMPRESSION_H
#define WTC_COMPRESSION_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Compression state for a single tag */
typedef struct {
    compression_t algorithm;
    float deadband;

    /* Swinging door state */
    float last_stored_value;
    uint64_t last_stored_time;
    float slope_max;
    float slope_min;
    bool first_sample;

    /* Statistics */
    uint64_t samples_in;
    uint64_t samples_out;
} compression_state_t;

/* Initialize compression state */
void compression_init(compression_state_t *state, compression_t algorithm, float deadband);

/* Reset compression state */
void compression_reset(compression_state_t *state);

/* Check if a sample should be stored based on compression algorithm
 * Returns true if the sample should be stored, false if it can be discarded */
bool compression_should_store(compression_state_t *state, float value, uint64_t timestamp_ms);

/* Force store a sample (bypass compression) */
void compression_force_store(compression_state_t *state, float value, uint64_t timestamp_ms);

/* Get compression ratio */
float compression_get_ratio(compression_state_t *state);

/* ============== Bulk Compression ============== */

/* Compress an array of samples using specified algorithm */
wtc_result_t compression_compress_samples(const historian_sample_t *input,
                                           int input_count,
                                           compression_t algorithm,
                                           float deadband,
                                           historian_sample_t **output,
                                           int *output_count);

/* Decompress/interpolate samples to regular intervals */
wtc_result_t compression_interpolate_samples(const historian_sample_t *input,
                                              int input_count,
                                              uint64_t start_time,
                                              uint64_t end_time,
                                              uint32_t interval_ms,
                                              historian_sample_t **output,
                                              int *output_count);

#ifdef __cplusplus
}
#endif

#endif /* WTC_COMPRESSION_H */
