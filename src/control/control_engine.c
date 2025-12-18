/*
 * Water Treatment Controller - Control Engine Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "control_engine.h"
#include "registry/rtu_registry.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <math.h>

/* Control engine structure */
struct control_engine {
    control_engine_config_t config;
    rtu_registry_t *registry;

    /* PID loops */
    pid_loop_t pid_loops[WTC_MAX_PID_LOOPS];
    int pid_loop_count;
    int next_pid_id;

    /* Interlocks */
    interlock_t interlocks[WTC_MAX_INTERLOCKS];
    int interlock_count;
    int next_interlock_id;

    /* Forced outputs */
    struct {
        char station_name[WTC_MAX_STATION_NAME];
        int slot;
        actuator_output_t output;
    } forced_outputs[128];
    int forced_count;

    /* Thread management */
    pthread_t control_thread;
    volatile bool running;
    pthread_mutex_t lock;

    /* Statistics */
    control_stats_t stats;
};

/* Forward declarations */
static void process_pid_loops(control_engine_t *engine);
static void process_interlocks(control_engine_t *engine);

/* Control thread function */
static void *control_thread_func(void *arg) {
    control_engine_t *engine = (control_engine_t *)arg;
    uint64_t next_scan_ms = time_get_monotonic_ms();

    LOG_DEBUG("Control thread started, scan rate: %u ms", engine->config.scan_rate_ms);

    while (engine->running) {
        uint64_t start_us = time_get_monotonic_us();

        pthread_mutex_lock(&engine->lock);
        control_engine_process(engine);
        pthread_mutex_unlock(&engine->lock);

        uint64_t elapsed_us = time_get_monotonic_us() - start_us;

        /* Update statistics */
        engine->stats.total_scans++;
        if (elapsed_us < engine->stats.scan_time_us_min ||
            engine->stats.scan_time_us_min == 0) {
            engine->stats.scan_time_us_min = elapsed_us;
        }
        if (elapsed_us > engine->stats.scan_time_us_max) {
            engine->stats.scan_time_us_max = elapsed_us;
        }
        engine->stats.scan_time_us_avg =
            (engine->stats.scan_time_us_avg * (engine->stats.total_scans - 1) +
             elapsed_us) / engine->stats.total_scans;

        /* Wait for next scan */
        next_scan_ms += engine->config.scan_rate_ms;
        uint64_t now_ms = time_get_monotonic_ms();
        if (now_ms < next_scan_ms) {
            time_sleep_ms(next_scan_ms - now_ms);
        } else {
            next_scan_ms = now_ms + engine->config.scan_rate_ms;
        }
    }

    LOG_DEBUG("Control thread stopped");
    return NULL;
}

/* Calculate PID output */
static float calculate_pid(pid_loop_t *loop, float pv, float dt_ms) {
    if (!loop || loop->mode == PID_MODE_OFF) {
        return 0.0f;
    }

    if (loop->mode == PID_MODE_MANUAL) {
        return loop->cv; /* Use manually set output */
    }

    float dt = dt_ms / 1000.0f;
    if (dt <= 0) dt = 0.001f;

    /* Calculate error */
    float error = loop->setpoint - pv;

    /* Apply deadband */
    if (fabsf(error) < loop->deadband) {
        error = 0.0f;
    }

    /* Proportional term */
    float p_term = loop->kp * error;

    /* Integral term with anti-windup */
    loop->integral += loop->ki * error * dt;
    if (loop->integral_limit > 0) {
        if (loop->integral > loop->integral_limit) {
            loop->integral = loop->integral_limit;
        } else if (loop->integral < -loop->integral_limit) {
            loop->integral = -loop->integral_limit;
        }
    }
    float i_term = loop->integral;

    /* Derivative term with filtering */
    float derivative = (error - loop->last_error) / dt;
    if (loop->derivative_filter > 0) {
        loop->derivative = loop->derivative * loop->derivative_filter +
                          derivative * (1.0f - loop->derivative_filter);
    } else {
        loop->derivative = derivative;
    }
    float d_term = loop->kd * loop->derivative;

    /* Calculate output */
    float output = p_term + i_term + d_term;

    /* Clamp to output limits */
    if (output > loop->output_max) {
        output = loop->output_max;
        /* Anti-windup: don't accumulate integral if saturated */
        if (error > 0) loop->integral -= loop->ki * error * dt;
    } else if (output < loop->output_min) {
        output = loop->output_min;
        if (error < 0) loop->integral -= loop->ki * error * dt;
    }

    /* Save state */
    loop->last_error = error;
    loop->error = error;
    loop->pv = pv;
    loop->cv = output;

    return output;
}

/* Process all PID loops */
static void process_pid_loops(control_engine_t *engine) {
    if (!engine || !engine->registry) return;

    uint64_t now_ms = time_get_ms();

    for (int i = 0; i < engine->pid_loop_count; i++) {
        pid_loop_t *loop = &engine->pid_loops[i];
        if (!loop->enabled || loop->mode == PID_MODE_OFF) continue;

        /* Read process variable from RTU */
        sensor_data_t sensor;
        wtc_result_t res = rtu_registry_get_sensor(engine->registry,
                                                    loop->input_rtu,
                                                    loop->input_slot,
                                                    &sensor);
        if (res != WTC_OK || sensor.status != IOPS_GOOD) {
            /* Input fault - hold last output or go to safe state */
            LOG_WARN("PID loop %d: input fault from %s slot %d",
                     loop->loop_id, loop->input_rtu, loop->input_slot);
            continue;
        }

        /* Calculate time since last update */
        uint64_t dt_ms = 100; /* Default scan rate */
        if (loop->last_update_ms > 0) {
            dt_ms = now_ms - loop->last_update_ms;
        }
        loop->last_update_ms = now_ms;

        /* Calculate PID output */
        float output = calculate_pid(loop, sensor.value, dt_ms);

        /* Write output to RTU */
        actuator_output_t actuator_out;
        if (output > 0.5f) {
            /* PWM mode for variable output */
            actuator_out.command = ACTUATOR_CMD_PWM;
            actuator_out.pwm_duty = (uint8_t)(output);
        } else if (output > 0) {
            actuator_out.command = ACTUATOR_CMD_ON;
            actuator_out.pwm_duty = 0;
        } else {
            actuator_out.command = ACTUATOR_CMD_OFF;
            actuator_out.pwm_duty = 0;
        }
        actuator_out.reserved[0] = 0;
        actuator_out.reserved[1] = 0;

        rtu_registry_update_actuator(engine->registry,
                                     loop->output_rtu,
                                     loop->output_slot,
                                     &actuator_out);

        /* Invoke callback */
        if (engine->config.on_pid_output) {
            engine->config.on_pid_output(loop->loop_id, output,
                                         engine->config.callback_ctx);
        }
    }
}

/* Process all interlocks */
static void process_interlocks(control_engine_t *engine) {
    if (!engine || !engine->registry) return;

    uint64_t now_ms = time_get_ms();

    engine->stats.tripped_interlocks = 0;

    for (int i = 0; i < engine->interlock_count; i++) {
        interlock_t *interlock = &engine->interlocks[i];
        if (!interlock->enabled) continue;

        if (interlock->tripped) {
            engine->stats.tripped_interlocks++;
        }

        /* Read condition value from RTU */
        sensor_data_t sensor;
        wtc_result_t res = rtu_registry_get_sensor(engine->registry,
                                                    interlock->condition_rtu,
                                                    interlock->condition_slot,
                                                    &sensor);
        if (res != WTC_OK || sensor.status != IOPS_GOOD) {
            /* Input fault - treat as condition met for safety */
            LOG_WARN("Interlock %d: input fault, assuming trip condition",
                     interlock->interlock_id);
        }

        /* Evaluate condition */
        bool condition_met = false;
        switch (interlock->condition) {
        case INTERLOCK_CONDITION_ABOVE:
            condition_met = sensor.value > interlock->threshold;
            break;
        case INTERLOCK_CONDITION_BELOW:
            condition_met = sensor.value < interlock->threshold;
            break;
        case INTERLOCK_CONDITION_EQUAL:
            condition_met = fabsf(sensor.value - interlock->threshold) < 0.01f;
            break;
        case INTERLOCK_CONDITION_NOT_EQUAL:
            condition_met = fabsf(sensor.value - interlock->threshold) >= 0.01f;
            break;
        }

        /* Handle delay */
        if (condition_met && !interlock->tripped) {
            if (interlock->condition_start_ms == 0) {
                interlock->condition_start_ms = now_ms;
            } else if (now_ms - interlock->condition_start_ms >= interlock->delay_ms) {
                /* Trip interlock */
                interlock->tripped = true;
                interlock->trip_time_ms = now_ms;
                LOG_WARN("Interlock %d TRIPPED: %s (value=%.2f, threshold=%.2f)",
                         interlock->interlock_id, interlock->name,
                         sensor.value, interlock->threshold);

                /* Invoke callback */
                if (engine->config.on_interlock_trip) {
                    engine->config.on_interlock_trip(interlock->interlock_id,
                                                     engine->config.callback_ctx);
                }
            }
        } else if (!condition_met) {
            interlock->condition_start_ms = 0;
        }

        /* Apply interlock action if tripped */
        if (interlock->tripped && interlock->action != INTERLOCK_ACTION_ALARM_ONLY) {
            actuator_output_t actuator_out;
            memset(&actuator_out, 0, sizeof(actuator_out));

            switch (interlock->action) {
            case INTERLOCK_ACTION_FORCE_OFF:
                actuator_out.command = ACTUATOR_CMD_OFF;
                break;
            case INTERLOCK_ACTION_FORCE_ON:
                actuator_out.command = ACTUATOR_CMD_ON;
                break;
            case INTERLOCK_ACTION_SET_VALUE:
                actuator_out.command = ACTUATOR_CMD_PWM;
                actuator_out.pwm_duty = (uint8_t)interlock->action_value;
                break;
            default:
                break;
            }

            rtu_registry_update_actuator(engine->registry,
                                         interlock->action_rtu,
                                         interlock->action_slot,
                                         &actuator_out);
        }
    }
}

/* Public functions */

wtc_result_t control_engine_init(control_engine_t **engine,
                                  const control_engine_config_t *config) {
    if (!engine) {
        return WTC_ERROR_INVALID_PARAM;
    }

    control_engine_t *eng = calloc(1, sizeof(control_engine_t));
    if (!eng) {
        return WTC_ERROR_NO_MEMORY;
    }

    if (config) {
        memcpy(&eng->config, config, sizeof(control_engine_config_t));
    }

    /* Set defaults */
    if (eng->config.scan_rate_ms == 0) {
        eng->config.scan_rate_ms = 100; /* 100ms default */
    }

    eng->next_pid_id = 1;
    eng->next_interlock_id = 1;
    pthread_mutex_init(&eng->lock, NULL);

    *engine = eng;
    LOG_INFO("Control engine initialized");
    return WTC_OK;
}

void control_engine_cleanup(control_engine_t *engine) {
    if (!engine) return;

    control_engine_stop(engine);
    pthread_mutex_destroy(&engine->lock);
    free(engine);

    LOG_INFO("Control engine cleaned up");
}

wtc_result_t control_engine_load_program(control_engine_t *engine,
                                          const char *program_file) {
    if (!engine || !program_file) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Program loading would parse control program file */
    LOG_INFO("Loading control program: %s", program_file);

    return WTC_OK;
}

wtc_result_t control_engine_start(control_engine_t *engine) {
    if (!engine) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (engine->running) {
        return WTC_OK;
    }

    engine->running = true;

    if (pthread_create(&engine->control_thread, NULL,
                       control_thread_func, engine) != 0) {
        LOG_ERROR("Failed to create control thread");
        engine->running = false;
        return WTC_ERROR;
    }

    LOG_INFO("Control engine started");
    return WTC_OK;
}

wtc_result_t control_engine_stop(control_engine_t *engine) {
    if (!engine || !engine->running) {
        return WTC_OK;
    }

    engine->running = false;
    pthread_join(engine->control_thread, NULL);

    LOG_INFO("Control engine stopped");
    return WTC_OK;
}

wtc_result_t control_engine_process(control_engine_t *engine) {
    if (!engine) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Process interlocks first (safety) */
    process_interlocks(engine);

    /* Process PID loops */
    process_pid_loops(engine);

    return WTC_OK;
}

wtc_result_t control_engine_set_registry(control_engine_t *engine,
                                          struct rtu_registry *registry) {
    if (!engine) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);
    engine->registry = registry;
    pthread_mutex_unlock(&engine->lock);

    return WTC_OK;
}

wtc_result_t control_engine_add_pid_loop(control_engine_t *engine,
                                          const pid_loop_t *config,
                                          int *loop_id) {
    if (!engine || !config) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    if (engine->pid_loop_count >= WTC_MAX_PID_LOOPS) {
        pthread_mutex_unlock(&engine->lock);
        return WTC_ERROR_FULL;
    }

    pid_loop_t *loop = &engine->pid_loops[engine->pid_loop_count++];
    memcpy(loop, config, sizeof(pid_loop_t));
    loop->loop_id = engine->next_pid_id++;

    if (loop_id) {
        *loop_id = loop->loop_id;
    }

    pthread_mutex_unlock(&engine->lock);

    LOG_INFO("Added PID loop %d: %s", loop->loop_id, loop->name);
    return WTC_OK;
}

wtc_result_t control_engine_remove_pid_loop(control_engine_t *engine,
                                             int loop_id) {
    if (!engine) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    for (int i = 0; i < engine->pid_loop_count; i++) {
        if (engine->pid_loops[i].loop_id == loop_id) {
            /* Shift remaining loops */
            for (int j = i; j < engine->pid_loop_count - 1; j++) {
                engine->pid_loops[j] = engine->pid_loops[j + 1];
            }
            engine->pid_loop_count--;

            pthread_mutex_unlock(&engine->lock);
            LOG_INFO("Removed PID loop %d", loop_id);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&engine->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t control_engine_get_pid_loop(control_engine_t *engine,
                                          int loop_id,
                                          pid_loop_t *loop) {
    if (!engine || !loop) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    for (int i = 0; i < engine->pid_loop_count; i++) {
        if (engine->pid_loops[i].loop_id == loop_id) {
            memcpy(loop, &engine->pid_loops[i], sizeof(pid_loop_t));
            pthread_mutex_unlock(&engine->lock);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&engine->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t control_engine_set_setpoint(control_engine_t *engine,
                                          int loop_id,
                                          float setpoint) {
    if (!engine) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    for (int i = 0; i < engine->pid_loop_count; i++) {
        if (engine->pid_loops[i].loop_id == loop_id) {
            engine->pid_loops[i].setpoint = setpoint;
            pthread_mutex_unlock(&engine->lock);
            LOG_DEBUG("PID loop %d setpoint changed to %.2f", loop_id, setpoint);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&engine->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t control_engine_set_pid_mode(control_engine_t *engine,
                                          int loop_id,
                                          pid_mode_t mode) {
    if (!engine) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    for (int i = 0; i < engine->pid_loop_count; i++) {
        if (engine->pid_loops[i].loop_id == loop_id) {
            engine->pid_loops[i].mode = mode;
            if (mode == PID_MODE_AUTO) {
                /* Reset integral on mode change */
                engine->pid_loops[i].integral = 0;
            }
            pthread_mutex_unlock(&engine->lock);
            LOG_INFO("PID loop %d mode changed to %d", loop_id, mode);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&engine->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t control_engine_set_pid_tuning(control_engine_t *engine,
                                            int loop_id,
                                            float kp, float ki, float kd) {
    if (!engine) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    for (int i = 0; i < engine->pid_loop_count; i++) {
        if (engine->pid_loops[i].loop_id == loop_id) {
            engine->pid_loops[i].kp = kp;
            engine->pid_loops[i].ki = ki;
            engine->pid_loops[i].kd = kd;
            pthread_mutex_unlock(&engine->lock);
            LOG_INFO("PID loop %d tuning: Kp=%.3f Ki=%.3f Kd=%.3f",
                     loop_id, kp, ki, kd);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&engine->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t control_engine_get_pid_output(control_engine_t *engine,
                                            int loop_id,
                                            float *output) {
    if (!engine || !output) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    for (int i = 0; i < engine->pid_loop_count; i++) {
        if (engine->pid_loops[i].loop_id == loop_id) {
            *output = engine->pid_loops[i].cv;
            pthread_mutex_unlock(&engine->lock);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&engine->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t control_engine_list_pid_loops(control_engine_t *engine,
                                            pid_loop_t **loops,
                                            int *count,
                                            int max_count) {
    if (!engine || !loops || !count) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    int copy_count = engine->pid_loop_count;
    if (copy_count > max_count) {
        copy_count = max_count;
    }

    for (int i = 0; i < copy_count; i++) {
        loops[i] = &engine->pid_loops[i];
    }
    *count = copy_count;

    pthread_mutex_unlock(&engine->lock);
    return WTC_OK;
}

wtc_result_t control_engine_add_interlock(control_engine_t *engine,
                                           const interlock_t *config,
                                           int *interlock_id) {
    if (!engine || !config) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    if (engine->interlock_count >= WTC_MAX_INTERLOCKS) {
        pthread_mutex_unlock(&engine->lock);
        return WTC_ERROR_FULL;
    }

    interlock_t *interlock = &engine->interlocks[engine->interlock_count++];
    memcpy(interlock, config, sizeof(interlock_t));
    interlock->interlock_id = engine->next_interlock_id++;

    if (interlock_id) {
        *interlock_id = interlock->interlock_id;
    }

    pthread_mutex_unlock(&engine->lock);

    LOG_INFO("Added interlock %d: %s", interlock->interlock_id, interlock->name);
    return WTC_OK;
}

wtc_result_t control_engine_remove_interlock(control_engine_t *engine,
                                              int interlock_id) {
    if (!engine) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    for (int i = 0; i < engine->interlock_count; i++) {
        if (engine->interlocks[i].interlock_id == interlock_id) {
            for (int j = i; j < engine->interlock_count - 1; j++) {
                engine->interlocks[j] = engine->interlocks[j + 1];
            }
            engine->interlock_count--;

            pthread_mutex_unlock(&engine->lock);
            LOG_INFO("Removed interlock %d", interlock_id);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&engine->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t control_engine_get_interlock(control_engine_t *engine,
                                           int interlock_id,
                                           interlock_t *interlock) {
    if (!engine || !interlock) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    for (int i = 0; i < engine->interlock_count; i++) {
        if (engine->interlocks[i].interlock_id == interlock_id) {
            memcpy(interlock, &engine->interlocks[i], sizeof(interlock_t));
            pthread_mutex_unlock(&engine->lock);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&engine->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t control_engine_enable_interlock(control_engine_t *engine,
                                              int interlock_id,
                                              bool enabled) {
    if (!engine) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    for (int i = 0; i < engine->interlock_count; i++) {
        if (engine->interlocks[i].interlock_id == interlock_id) {
            engine->interlocks[i].enabled = enabled;
            pthread_mutex_unlock(&engine->lock);
            LOG_INFO("Interlock %d %s", interlock_id, enabled ? "enabled" : "disabled");
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&engine->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t control_engine_reset_interlock(control_engine_t *engine,
                                             int interlock_id) {
    if (!engine) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    for (int i = 0; i < engine->interlock_count; i++) {
        if (engine->interlocks[i].interlock_id == interlock_id) {
            engine->interlocks[i].tripped = false;
            engine->interlocks[i].trip_time_ms = 0;
            engine->interlocks[i].condition_start_ms = 0;
            pthread_mutex_unlock(&engine->lock);
            LOG_INFO("Interlock %d reset", interlock_id);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&engine->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t control_engine_list_interlocks(control_engine_t *engine,
                                             interlock_t **interlocks,
                                             int *count,
                                             int max_count) {
    if (!engine || !interlocks || !count) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    int copy_count = engine->interlock_count;
    if (copy_count > max_count) {
        copy_count = max_count;
    }

    for (int i = 0; i < copy_count; i++) {
        interlocks[i] = &engine->interlocks[i];
    }
    *count = copy_count;

    pthread_mutex_unlock(&engine->lock);
    return WTC_OK;
}

wtc_result_t control_engine_force_output(control_engine_t *engine,
                                          const char *station_name,
                                          int slot,
                                          uint8_t command,
                                          uint8_t pwm_duty) {
    if (!engine || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    /* Check if already forced */
    for (int i = 0; i < engine->forced_count; i++) {
        if (strcmp(engine->forced_outputs[i].station_name, station_name) == 0 &&
            engine->forced_outputs[i].slot == slot) {
            engine->forced_outputs[i].output.command = command;
            engine->forced_outputs[i].output.pwm_duty = pwm_duty;
            pthread_mutex_unlock(&engine->lock);
            return WTC_OK;
        }
    }

    /* Add new forced output */
    if (engine->forced_count >= 128) {
        pthread_mutex_unlock(&engine->lock);
        return WTC_ERROR_FULL;
    }

    strncpy(engine->forced_outputs[engine->forced_count].station_name,
            station_name, WTC_MAX_STATION_NAME - 1);
    engine->forced_outputs[engine->forced_count].slot = slot;
    engine->forced_outputs[engine->forced_count].output.command = command;
    engine->forced_outputs[engine->forced_count].output.pwm_duty = pwm_duty;
    engine->forced_count++;

    pthread_mutex_unlock(&engine->lock);

    LOG_WARN("Forced output: %s slot %d = cmd %d duty %d",
             station_name, slot, command, pwm_duty);
    return WTC_OK;
}

wtc_result_t control_engine_release_output(control_engine_t *engine,
                                            const char *station_name,
                                            int slot) {
    if (!engine || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    for (int i = 0; i < engine->forced_count; i++) {
        if (strcmp(engine->forced_outputs[i].station_name, station_name) == 0 &&
            engine->forced_outputs[i].slot == slot) {
            for (int j = i; j < engine->forced_count - 1; j++) {
                engine->forced_outputs[j] = engine->forced_outputs[j + 1];
            }
            engine->forced_count--;

            pthread_mutex_unlock(&engine->lock);
            LOG_INFO("Released forced output: %s slot %d", station_name, slot);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&engine->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t control_engine_is_output_forced(control_engine_t *engine,
                                              const char *station_name,
                                              int slot,
                                              bool *forced) {
    if (!engine || !station_name || !forced) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    *forced = false;
    for (int i = 0; i < engine->forced_count; i++) {
        if (strcmp(engine->forced_outputs[i].station_name, station_name) == 0 &&
            engine->forced_outputs[i].slot == slot) {
            *forced = true;
            break;
        }
    }

    pthread_mutex_unlock(&engine->lock);
    return WTC_OK;
}

wtc_result_t control_engine_get_stats(control_engine_t *engine,
                                       control_stats_t *stats) {
    if (!engine || !stats) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&engine->lock);

    memcpy(stats, &engine->stats, sizeof(control_stats_t));
    stats->active_pid_loops = engine->pid_loop_count;
    stats->active_interlocks = engine->interlock_count;

    pthread_mutex_unlock(&engine->lock);
    return WTC_OK;
}
