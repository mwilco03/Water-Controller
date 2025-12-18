/*
 * Water Treatment Controller - Control Engine
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_CONTROL_ENGINE_H
#define WTC_CONTROL_ENGINE_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Control engine handle */
typedef struct control_engine control_engine_t;

/* Control engine configuration */
typedef struct {
    uint32_t scan_rate_ms;          /* Control loop scan rate */
    const char *program_file;       /* Control program file path */

    /* Callbacks */
    void (*on_pid_output)(int loop_id, float output, void *ctx);
    void (*on_interlock_trip)(int interlock_id, void *ctx);
    void (*on_sequence_step)(int sequence_id, int step, void *ctx);
    void *callback_ctx;
} control_engine_config_t;

/* Initialize control engine */
wtc_result_t control_engine_init(control_engine_t **engine,
                                  const control_engine_config_t *config);

/* Cleanup control engine */
void control_engine_cleanup(control_engine_t *engine);

/* Load control program */
wtc_result_t control_engine_load_program(control_engine_t *engine,
                                          const char *program_file);

/* Start control engine */
wtc_result_t control_engine_start(control_engine_t *engine);

/* Stop control engine */
wtc_result_t control_engine_stop(control_engine_t *engine);

/* Process one scan cycle */
wtc_result_t control_engine_process(control_engine_t *engine);

/* Set RTU registry for data access */
struct rtu_registry;
wtc_result_t control_engine_set_registry(control_engine_t *engine,
                                          struct rtu_registry *registry);

/* ============== PID Loops ============== */

/* Add PID loop */
wtc_result_t control_engine_add_pid_loop(control_engine_t *engine,
                                          const pid_loop_t *config,
                                          int *loop_id);

/* Remove PID loop */
wtc_result_t control_engine_remove_pid_loop(control_engine_t *engine,
                                             int loop_id);

/* Get PID loop */
wtc_result_t control_engine_get_pid_loop(control_engine_t *engine,
                                          int loop_id,
                                          pid_loop_t *loop);

/* Set PID setpoint */
wtc_result_t control_engine_set_setpoint(control_engine_t *engine,
                                          int loop_id,
                                          float setpoint);

/* Set PID mode */
wtc_result_t control_engine_set_pid_mode(control_engine_t *engine,
                                          int loop_id,
                                          pid_mode_t mode);

/* Set PID tuning parameters */
wtc_result_t control_engine_set_pid_tuning(control_engine_t *engine,
                                            int loop_id,
                                            float kp, float ki, float kd);

/* Get PID output */
wtc_result_t control_engine_get_pid_output(control_engine_t *engine,
                                            int loop_id,
                                            float *output);

/* List all PID loops */
wtc_result_t control_engine_list_pid_loops(control_engine_t *engine,
                                            pid_loop_t **loops,
                                            int *count,
                                            int max_count);

/* ============== Interlocks ============== */

/* Add interlock */
wtc_result_t control_engine_add_interlock(control_engine_t *engine,
                                           const interlock_t *config,
                                           int *interlock_id);

/* Remove interlock */
wtc_result_t control_engine_remove_interlock(control_engine_t *engine,
                                              int interlock_id);

/* Get interlock */
wtc_result_t control_engine_get_interlock(control_engine_t *engine,
                                           int interlock_id,
                                           interlock_t *interlock);

/* Enable/disable interlock */
wtc_result_t control_engine_enable_interlock(control_engine_t *engine,
                                              int interlock_id,
                                              bool enabled);

/* Reset tripped interlock */
wtc_result_t control_engine_reset_interlock(control_engine_t *engine,
                                             int interlock_id);

/* List all interlocks */
wtc_result_t control_engine_list_interlocks(control_engine_t *engine,
                                             interlock_t **interlocks,
                                             int *count,
                                             int max_count);

/* ============== Output Forcing ============== */

/* Force output to specific value */
wtc_result_t control_engine_force_output(control_engine_t *engine,
                                          const char *station_name,
                                          int slot,
                                          uint8_t command,
                                          uint8_t pwm_duty);

/* Release forced output */
wtc_result_t control_engine_release_output(control_engine_t *engine,
                                            const char *station_name,
                                            int slot);

/* Check if output is forced */
wtc_result_t control_engine_is_output_forced(control_engine_t *engine,
                                              const char *station_name,
                                              int slot,
                                              bool *forced);

/* ============== Statistics ============== */

typedef struct {
    uint64_t total_scans;
    uint64_t scan_time_us_min;
    uint64_t scan_time_us_max;
    uint64_t scan_time_us_avg;
    int active_pid_loops;
    int active_interlocks;
    int tripped_interlocks;
} control_stats_t;

wtc_result_t control_engine_get_stats(control_engine_t *engine,
                                       control_stats_t *stats);

#ifdef __cplusplus
}
#endif

#endif /* WTC_CONTROL_ENGINE_H */
