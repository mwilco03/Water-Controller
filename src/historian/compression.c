/*
 * Water Treatment Controller - Data Compression Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "compression.h"
#include "logger.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define LOG_TAG "COMPRESSION"

/* Initialize compression state */
void compression_init(compression_state_t *state, compression_t algorithm, float deadband) {
    if (!state) return;

    memset(state, 0, sizeof(compression_state_t));
    state->algorithm = algorithm;
    state->deadband = deadband;
    state->first_sample = true;
}

/* Reset compression state */
void compression_reset(compression_state_t *state) {
    if (!state) return;

    compression_t alg = state->algorithm;
    float db = state->deadband;
    compression_init(state, alg, db);
}

/* Swinging door compression algorithm */
static bool swinging_door_check(compression_state_t *state, float value, uint64_t timestamp_ms) {
    if (state->first_sample) {
        state->last_stored_value = value;
        state->last_stored_time = timestamp_ms;
        state->first_sample = false;
        state->samples_in++;
        state->samples_out++;
        return true;
    }

    float dt = (float)(timestamp_ms - state->last_stored_time);
    if (dt <= 0) {
        state->samples_in++;
        return false;
    }

    /* Calculate slope to current point (used for debugging/analysis) */
    float slope = (value - state->last_stored_value) / dt;
    (void)slope;  /* Retained for future slope logging */

    /* Calculate slopes to deadband boundaries */
    float slope_upper = (value + state->deadband - state->last_stored_value) / dt;
    float slope_lower = (value - state->deadband - state->last_stored_value) / dt;

    /* First point after stored point */
    if (state->slope_max == 0 && state->slope_min == 0) {
        state->slope_max = slope_upper;
        state->slope_min = slope_lower;
        state->samples_in++;
        return false;
    }

    /* Narrow the door */
    if (slope_upper < state->slope_max) state->slope_max = slope_upper;
    if (slope_lower > state->slope_min) state->slope_min = slope_lower;

    /* Check if door is still open */
    if (state->slope_max >= state->slope_min) {
        /* Door still open, don't store */
        state->samples_in++;
        return false;
    }

    /* Door closed, store previous point and reset */
    state->last_stored_value = value;
    state->last_stored_time = timestamp_ms;
    state->slope_max = 0;
    state->slope_min = 0;
    state->samples_in++;
    state->samples_out++;
    return true;
}

/* Deadband compression algorithm */
static bool deadband_check(compression_state_t *state, float value, uint64_t timestamp_ms) {
    if (state->first_sample) {
        state->last_stored_value = value;
        state->last_stored_time = timestamp_ms;
        state->first_sample = false;
        state->samples_in++;
        state->samples_out++;
        return true;
    }

    state->samples_in++;

    /* Check if value exceeds deadband */
    if (fabsf(value - state->last_stored_value) > state->deadband) {
        state->last_stored_value = value;
        state->last_stored_time = timestamp_ms;
        state->samples_out++;
        return true;
    }

    return false;
}

/* Boxcar (periodic) compression algorithm */
static bool boxcar_check(compression_state_t *state, float value, uint64_t timestamp_ms) {
    if (state->first_sample) {
        state->last_stored_value = value;
        state->last_stored_time = timestamp_ms;
        state->first_sample = false;
        state->samples_in++;
        state->samples_out++;
        return true;
    }

    state->samples_in++;

    /* Store if value changed significantly OR time exceeded */
    bool value_changed = fabsf(value - state->last_stored_value) > state->deadband;
    bool time_exceeded = (timestamp_ms - state->last_stored_time) >= 60000;  /* 1 minute max */

    if (value_changed || time_exceeded) {
        state->last_stored_value = value;
        state->last_stored_time = timestamp_ms;
        state->samples_out++;
        return true;
    }

    return false;
}

/* Check if a sample should be stored */
bool compression_should_store(compression_state_t *state, float value, uint64_t timestamp_ms) {
    if (!state) return true;

    switch (state->algorithm) {
        case COMPRESSION_NONE:
            state->samples_in++;
            state->samples_out++;
            return true;

        case COMPRESSION_SWINGING_DOOR:
            return swinging_door_check(state, value, timestamp_ms);

        case COMPRESSION_DEADBAND:
            return deadband_check(state, value, timestamp_ms);

        case COMPRESSION_BOXCAR:
            return boxcar_check(state, value, timestamp_ms);

        default:
            state->samples_in++;
            state->samples_out++;
            return true;
    }
}

/* Force store a sample */
void compression_force_store(compression_state_t *state, float value, uint64_t timestamp_ms) {
    if (!state) return;

    state->last_stored_value = value;
    state->last_stored_time = timestamp_ms;
    state->slope_max = 0;
    state->slope_min = 0;
    state->samples_in++;
    state->samples_out++;

    if (state->first_sample) {
        state->first_sample = false;
    }
}

/* Get compression ratio */
float compression_get_ratio(compression_state_t *state) {
    if (!state || state->samples_in == 0) return 1.0f;
    return (float)state->samples_out / (float)state->samples_in;
}

/* Compress an array of samples */
wtc_result_t compression_compress_samples(const historian_sample_t *input,
                                           int input_count,
                                           compression_t algorithm,
                                           float deadband,
                                           historian_sample_t **output,
                                           int *output_count) {
    if (!input || input_count <= 0 || !output || !output_count) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Allocate output buffer (worst case: same size as input) */
    *output = calloc(input_count, sizeof(historian_sample_t));
    if (!*output) {
        return WTC_ERROR_NO_MEMORY;
    }

    compression_state_t state;
    compression_init(&state, algorithm, deadband);

    *output_count = 0;

    for (int i = 0; i < input_count; i++) {
        if (compression_should_store(&state, input[i].value, input[i].timestamp_ms)) {
            (*output)[*output_count] = input[i];
            (*output_count)++;
        }
    }

    /* Shrink buffer to actual size */
    if (*output_count < input_count) {
        historian_sample_t *shrunk = realloc(*output,
                                              (*output_count) * sizeof(historian_sample_t));
        if (shrunk) {
            *output = shrunk;
        }
    }

    LOG_DEBUG(LOG_TAG, "Compressed %d samples to %d (ratio: %.2f%%)",
              input_count, *output_count,
              100.0f * (float)*output_count / (float)input_count);

    return WTC_OK;
}

/* Interpolate samples to regular intervals */
wtc_result_t compression_interpolate_samples(const historian_sample_t *input,
                                              int input_count,
                                              uint64_t start_time,
                                              uint64_t end_time,
                                              uint32_t interval_ms,
                                              historian_sample_t **output,
                                              int *output_count) {
    if (!input || input_count <= 0 || !output || !output_count || interval_ms == 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Calculate output sample count */
    int count = (int)((end_time - start_time) / interval_ms) + 1;
    *output = calloc(count, sizeof(historian_sample_t));
    if (!*output) {
        return WTC_ERROR_NO_MEMORY;
    }

    *output_count = 0;
    int input_idx = 0;

    for (uint64_t t = start_time; t <= end_time && *output_count < count; t += interval_ms) {
        /* Find surrounding input samples */
        while (input_idx < input_count - 1 && input[input_idx + 1].timestamp_ms <= t) {
            input_idx++;
        }

        historian_sample_t *out = &(*output)[*output_count];
        out->timestamp_ms = t;
        out->tag_id = input[0].tag_id;

        if (input_idx >= input_count - 1) {
            /* Past end of data, use last value */
            out->value = input[input_count - 1].value;
            out->quality = input[input_count - 1].quality;
        } else if (input[input_idx].timestamp_ms == t) {
            /* Exact match */
            out->value = input[input_idx].value;
            out->quality = input[input_idx].quality;
        } else {
            /* Linear interpolation */
            historian_sample_t *s1 = (historian_sample_t *)&input[input_idx];
            historian_sample_t *s2 = (historian_sample_t *)&input[input_idx + 1];

            float dt = (float)(s2->timestamp_ms - s1->timestamp_ms);
            float t_offset = (float)(t - s1->timestamp_ms);

            if (dt > 0) {
                float ratio = t_offset / dt;
                out->value = s1->value + ratio * (s2->value - s1->value);
            } else {
                out->value = s1->value;
            }
            out->quality = (s1->quality < s2->quality) ? s1->quality : s2->quality;
        }

        (*output_count)++;
    }

    return WTC_OK;
}
