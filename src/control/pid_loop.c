/*
 * Water Treatment Controller - PID Loop Utilities
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "control_engine.h"
#include "utils/logger.h"

#include <stdlib.h>
#include <string.h>
#include <math.h>

/* Create standard water treatment PID loop configurations */

/* pH Control PID - controls acid/base dosing */
wtc_result_t create_ph_control_loop(pid_loop_t *loop,
                                     const char *input_rtu, int input_slot,
                                     const char *output_rtu, int output_slot,
                                     float setpoint) {
    if (!loop) return WTC_ERROR_INVALID_PARAM;

    memset(loop, 0, sizeof(pid_loop_t));
    strncpy(loop->name, "pH Control", sizeof(loop->name) - 1);
    loop->enabled = true;
    loop->mode = PID_MODE_AUTO;

    strncpy(loop->input_rtu, input_rtu, WTC_MAX_STATION_NAME - 1);
    loop->input_slot = input_slot;
    strncpy(loop->output_rtu, output_rtu, WTC_MAX_STATION_NAME - 1);
    loop->output_slot = output_slot;

    /* pH control is sensitive - use conservative tuning */
    loop->kp = 2.0f;
    loop->ki = 0.1f;
    loop->kd = 0.5f;
    loop->setpoint = setpoint > 0 ? setpoint : 7.0f;
    loop->output_min = 0.0f;
    loop->output_max = 100.0f;
    loop->deadband = 0.1f;
    loop->integral_limit = 50.0f;
    loop->derivative_filter = 0.8f;

    return WTC_OK;
}

/* Level Control PID - controls pump or valve */
wtc_result_t create_level_control_loop(pid_loop_t *loop,
                                        const char *input_rtu, int input_slot,
                                        const char *output_rtu, int output_slot,
                                        float setpoint) {
    if (!loop) return WTC_ERROR_INVALID_PARAM;

    memset(loop, 0, sizeof(pid_loop_t));
    strncpy(loop->name, "Level Control", sizeof(loop->name) - 1);
    loop->enabled = true;
    loop->mode = PID_MODE_AUTO;

    strncpy(loop->input_rtu, input_rtu, WTC_MAX_STATION_NAME - 1);
    loop->input_slot = input_slot;
    strncpy(loop->output_rtu, output_rtu, WTC_MAX_STATION_NAME - 1);
    loop->output_slot = output_slot;

    /* Level control can be more aggressive */
    loop->kp = 5.0f;
    loop->ki = 0.5f;
    loop->kd = 1.0f;
    loop->setpoint = setpoint > 0 ? setpoint : 50.0f;
    loop->output_min = 0.0f;
    loop->output_max = 100.0f;
    loop->deadband = 2.0f;
    loop->integral_limit = 100.0f;
    loop->derivative_filter = 0.5f;

    return WTC_OK;
}

/* Pressure Control PID - controls pump or valve */
wtc_result_t create_pressure_control_loop(pid_loop_t *loop,
                                           const char *input_rtu, int input_slot,
                                           const char *output_rtu, int output_slot,
                                           float setpoint) {
    if (!loop) return WTC_ERROR_INVALID_PARAM;

    memset(loop, 0, sizeof(pid_loop_t));
    strncpy(loop->name, "Pressure Control", sizeof(loop->name) - 1);
    loop->enabled = true;
    loop->mode = PID_MODE_AUTO;

    strncpy(loop->input_rtu, input_rtu, WTC_MAX_STATION_NAME - 1);
    loop->input_slot = input_slot;
    strncpy(loop->output_rtu, output_rtu, WTC_MAX_STATION_NAME - 1);
    loop->output_slot = output_slot;

    /* Pressure control - medium response */
    loop->kp = 3.0f;
    loop->ki = 0.3f;
    loop->kd = 0.8f;
    loop->setpoint = setpoint > 0 ? setpoint : 5.0f;
    loop->output_min = 0.0f;
    loop->output_max = 100.0f;
    loop->deadband = 0.2f;
    loop->integral_limit = 75.0f;
    loop->derivative_filter = 0.6f;

    return WTC_OK;
}

/* Temperature Control PID */
wtc_result_t create_temperature_control_loop(pid_loop_t *loop,
                                              const char *input_rtu, int input_slot,
                                              const char *output_rtu, int output_slot,
                                              float setpoint) {
    if (!loop) return WTC_ERROR_INVALID_PARAM;

    memset(loop, 0, sizeof(pid_loop_t));
    strncpy(loop->name, "Temperature Control", sizeof(loop->name) - 1);
    loop->enabled = true;
    loop->mode = PID_MODE_AUTO;

    strncpy(loop->input_rtu, input_rtu, WTC_MAX_STATION_NAME - 1);
    loop->input_slot = input_slot;
    strncpy(loop->output_rtu, output_rtu, WTC_MAX_STATION_NAME - 1);
    loop->output_slot = output_slot;

    /* Temperature is slow - use slow tuning */
    loop->kp = 4.0f;
    loop->ki = 0.2f;
    loop->kd = 2.0f;
    loop->setpoint = setpoint > 0 ? setpoint : 25.0f;
    loop->output_min = 0.0f;
    loop->output_max = 100.0f;
    loop->deadband = 0.5f;
    loop->integral_limit = 100.0f;
    loop->derivative_filter = 0.9f;

    return WTC_OK;
}

/* Dissolved Oxygen Control PID - controls aerator */
wtc_result_t create_do_control_loop(pid_loop_t *loop,
                                     const char *input_rtu, int input_slot,
                                     const char *output_rtu, int output_slot,
                                     float setpoint) {
    if (!loop) return WTC_ERROR_INVALID_PARAM;

    memset(loop, 0, sizeof(pid_loop_t));
    strncpy(loop->name, "DO Control", sizeof(loop->name) - 1);
    loop->enabled = true;
    loop->mode = PID_MODE_AUTO;

    strncpy(loop->input_rtu, input_rtu, WTC_MAX_STATION_NAME - 1);
    loop->input_slot = input_slot;
    strncpy(loop->output_rtu, output_rtu, WTC_MAX_STATION_NAME - 1);
    loop->output_slot = output_slot;

    /* DO control - medium-slow response */
    loop->kp = 3.0f;
    loop->ki = 0.15f;
    loop->kd = 1.5f;
    loop->setpoint = setpoint > 0 ? setpoint : 6.0f;
    loop->output_min = 0.0f;
    loop->output_max = 100.0f;
    loop->deadband = 0.2f;
    loop->integral_limit = 80.0f;
    loop->derivative_filter = 0.7f;

    return WTC_OK;
}

/* Chlorine Control PID - controls chlorine dosing */
wtc_result_t create_chlorine_control_loop(pid_loop_t *loop,
                                           const char *input_rtu, int input_slot,
                                           const char *output_rtu, int output_slot,
                                           float setpoint) {
    if (!loop) return WTC_ERROR_INVALID_PARAM;

    memset(loop, 0, sizeof(pid_loop_t));
    strncpy(loop->name, "Chlorine Control", sizeof(loop->name) - 1);
    loop->enabled = true;
    loop->mode = PID_MODE_AUTO;

    strncpy(loop->input_rtu, input_rtu, WTC_MAX_STATION_NAME - 1);
    loop->input_slot = input_slot;
    strncpy(loop->output_rtu, output_rtu, WTC_MAX_STATION_NAME - 1);
    loop->output_slot = output_slot;

    /* Chlorine control - conservative due to health implications */
    loop->kp = 1.5f;
    loop->ki = 0.05f;
    loop->kd = 0.3f;
    loop->setpoint = setpoint > 0 ? setpoint : 1.0f;
    loop->output_min = 0.0f;
    loop->output_max = 100.0f;
    loop->deadband = 0.05f;
    loop->integral_limit = 40.0f;
    loop->derivative_filter = 0.85f;

    return WTC_OK;
}

/* Auto-tuning using relay feedback method (Ziegler-Nichols) */
typedef struct {
    bool active;
    float relay_amplitude;
    float period_start_time;
    float last_crossing_time;
    int crossing_count;
    float period_sum;
    float amplitude_max;
    float amplitude_min;
} autotune_state_t;

static autotune_state_t autotune_states[WTC_MAX_PID_LOOPS];

wtc_result_t pid_start_autotune(int loop_id, float relay_amplitude) {
    if (loop_id < 0 || loop_id >= WTC_MAX_PID_LOOPS) {
        return WTC_ERROR_INVALID_PARAM;
    }

    autotune_state_t *state = &autotune_states[loop_id];
    memset(state, 0, sizeof(autotune_state_t));
    state->active = true;
    state->relay_amplitude = relay_amplitude > 0 ? relay_amplitude : 10.0f;
    state->amplitude_max = -1e30f;
    state->amplitude_min = 1e30f;

    LOG_INFO("Started auto-tuning for loop %d with relay amplitude %.1f",
             loop_id, state->relay_amplitude);
    return WTC_OK;
}

wtc_result_t pid_process_autotune(int loop_id, float pv, float setpoint,
                                   float *output, bool *complete,
                                   float *kp, float *ki, float *kd) {
    if (loop_id < 0 || loop_id >= WTC_MAX_PID_LOOPS ||
        !output || !complete) {
        return WTC_ERROR_INVALID_PARAM;
    }

    autotune_state_t *state = &autotune_states[loop_id];
    *complete = false;

    if (!state->active) {
        return WTC_ERROR_NOT_INITIALIZED;
    }

    float error = setpoint - pv;

    /* Track min/max for amplitude calculation */
    if (pv > state->amplitude_max) state->amplitude_max = pv;
    if (pv < state->amplitude_min) state->amplitude_min = pv;

    /* Relay control */
    if (error > 0) {
        *output = state->relay_amplitude;
    } else {
        *output = -state->relay_amplitude;
    }

    /* Detect zero crossings to measure period */
    static float last_error = 0;
    if ((last_error <= 0 && error > 0) || (last_error >= 0 && error < 0)) {
        state->crossing_count++;

        if (state->crossing_count >= 2) {
            float period = 0; /* Would calculate from timestamps */
            state->period_sum += period;
        }

        /* After sufficient crossings, calculate tuning */
        if (state->crossing_count >= 6) {
            float Tu = state->period_sum / (state->crossing_count - 1);
            float amplitude = (state->amplitude_max - state->amplitude_min) / 2.0f;

            /* Guard against divide-by-zero */
            if (amplitude < 0.001f || Tu < 0.001f) {
                LOG_WARN("Auto-tune failed: insufficient amplitude (%.3f) or period (%.3f)",
                         amplitude, Tu);
                state->active = false;
                *complete = true;
                return WTC_OK;
            }

            float Ku = (4.0f * state->relay_amplitude) / (3.14159f * amplitude);

            /* Ziegler-Nichols PID tuning rules */
            if (kp) *kp = 0.6f * Ku;
            if (ki) *ki = 2.0f * (*kp) / Tu;
            if (kd) *kd = (*kp) * Tu / 8.0f;

            state->active = false;
            *complete = true;

            LOG_INFO("Auto-tune complete: Ku=%.3f Tu=%.3f -> Kp=%.3f Ki=%.3f Kd=%.3f",
                     Ku, Tu, kp ? *kp : 0, ki ? *ki : 0, kd ? *kd : 0);
        }
    }
    last_error = error;

    return WTC_OK;
}

wtc_result_t pid_stop_autotune(int loop_id) {
    if (loop_id < 0 || loop_id >= WTC_MAX_PID_LOOPS) {
        return WTC_ERROR_INVALID_PARAM;
    }

    autotune_states[loop_id].active = false;
    LOG_INFO("Stopped auto-tuning for loop %d", loop_id);
    return WTC_OK;
}

/* Calculate control performance metrics */
typedef struct {
    float iae;          /* Integral of Absolute Error */
    float ise;          /* Integral of Squared Error */
    float overshoot;    /* Maximum overshoot percentage */
    float settling_time; /* Time to reach ±2% of setpoint */
    float rise_time;    /* Time to go from 10% to 90% of step */
} pid_performance_t;

static pid_performance_t performance_metrics[WTC_MAX_PID_LOOPS];

void pid_reset_performance_metrics(int loop_id) {
    if (loop_id >= 0 && loop_id < WTC_MAX_PID_LOOPS) {
        memset(&performance_metrics[loop_id], 0, sizeof(pid_performance_t));
    }
}

void pid_update_performance_metrics(int loop_id, float pv, float setpoint,
                                     float error, float dt) {
    if (loop_id < 0 || loop_id >= WTC_MAX_PID_LOOPS) return;

    pid_performance_t *perf = &performance_metrics[loop_id];

    /* IAE and ISE */
    perf->iae += fabsf(error) * dt;
    perf->ise += error * error * dt;

    /* Overshoot - guard against divide-by-zero */
    if (fabsf(setpoint) > 0.0001f) {
        float overshoot_pct = (pv - setpoint) / setpoint * 100.0f;
        if (overshoot_pct > perf->overshoot) {
            perf->overshoot = overshoot_pct;
        }
    }
}

wtc_result_t pid_get_performance_metrics(int loop_id, pid_performance_t *metrics) {
    if (loop_id < 0 || loop_id >= WTC_MAX_PID_LOOPS || !metrics) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memcpy(metrics, &performance_metrics[loop_id], sizeof(pid_performance_t));
    return WTC_OK;
}
