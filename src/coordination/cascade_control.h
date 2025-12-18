/*
 * Water Treatment Controller - Cascade Control
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_CASCADE_CONTROL_H
#define WTC_CASCADE_CONTROL_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Cascade controller handle */
typedef struct cascade_controller cascade_controller_t;

/* Cascade configuration */
typedef struct {
    int max_cascades;
    uint32_t update_interval_ms;
} cascade_config_t;

/* Cascade loop definition */
typedef struct {
    int cascade_id;
    char name[WTC_MAX_NAME];
    bool enabled;

    /* Primary (outer) loop */
    int primary_loop_id;

    /* Secondary (inner) loop */
    int secondary_loop_id;

    /* Cascade parameters */
    float output_scale;      /* Scale factor for primary output to secondary setpoint */
    float output_offset;     /* Offset for secondary setpoint */
    float min_setpoint;      /* Minimum secondary setpoint */
    float max_setpoint;      /* Maximum secondary setpoint */

    /* Runtime */
    float current_cascade_sp;
    bool cascade_active;
} cascade_loop_t;

/* Initialize cascade controller */
wtc_result_t cascade_init(cascade_controller_t **ctrl, const cascade_config_t *config);

/* Cleanup cascade controller */
void cascade_cleanup(cascade_controller_t *ctrl);

/* Start cascade controller */
wtc_result_t cascade_start(cascade_controller_t *ctrl);

/* Stop cascade controller */
wtc_result_t cascade_stop(cascade_controller_t *ctrl);

/* Set control engine reference */
struct control_engine;
wtc_result_t cascade_set_control_engine(cascade_controller_t *ctrl,
                                         struct control_engine *engine);

/* Add cascade loop */
wtc_result_t cascade_add_loop(cascade_controller_t *ctrl, const cascade_loop_t *loop);

/* Remove cascade loop */
wtc_result_t cascade_remove_loop(cascade_controller_t *ctrl, int cascade_id);

/* Enable/disable cascade */
wtc_result_t cascade_enable(cascade_controller_t *ctrl, int cascade_id, bool enabled);

/* Get cascade loop status */
wtc_result_t cascade_get_loop(cascade_controller_t *ctrl, int cascade_id,
                               cascade_loop_t *loop);

/* Process cascade control */
wtc_result_t cascade_process(cascade_controller_t *ctrl);

#ifdef __cplusplus
}
#endif

#endif /* WTC_CASCADE_CONTROL_H */
