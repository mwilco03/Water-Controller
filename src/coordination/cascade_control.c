/*
 * Water Treatment Controller - Cascade Control Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "cascade_control.h"
#include "control_engine.h"
#include "logger.h"
#include "time_utils.h"
#include <stdlib.h>
#include <string.h>

#define LOG_TAG "CASCADE"

/* Cascade controller structure */
struct cascade_controller {
    cascade_config_t config;
    cascade_loop_t *loops;
    int loop_count;
    bool running;
    uint64_t last_process_ms;
    struct control_engine *control;
};

/* Initialize cascade controller */
wtc_result_t cascade_init(cascade_controller_t **ctrl, const cascade_config_t *config) {
    if (!ctrl || !config) return WTC_ERROR_INVALID_PARAM;

    cascade_controller_t *cc = calloc(1, sizeof(cascade_controller_t));
    if (!cc) {
        return WTC_ERROR_NO_MEMORY;
    }

    memcpy(&cc->config, config, sizeof(cascade_config_t));

    cc->loops = calloc(config->max_cascades, sizeof(cascade_loop_t));
    if (!cc->loops) {
        free(cc);
        return WTC_ERROR_NO_MEMORY;
    }

    cc->loop_count = 0;
    cc->running = false;

    LOG_INFO(LOG_TAG, "Cascade controller initialized (max %d cascades)",
             config->max_cascades);
    *ctrl = cc;
    return WTC_OK;
}

/* Cleanup cascade controller */
void cascade_cleanup(cascade_controller_t *ctrl) {
    if (!ctrl) return;
    free(ctrl->loops);
    free(ctrl);
    LOG_INFO(LOG_TAG, "Cascade controller cleaned up");
}

/* Start cascade controller */
wtc_result_t cascade_start(cascade_controller_t *ctrl) {
    if (!ctrl) return WTC_ERROR_INVALID_PARAM;
    ctrl->running = true;
    ctrl->last_process_ms = time_get_ms();
    LOG_INFO(LOG_TAG, "Cascade controller started");
    return WTC_OK;
}

/* Stop cascade controller */
wtc_result_t cascade_stop(cascade_controller_t *ctrl) {
    if (!ctrl) return WTC_ERROR_INVALID_PARAM;
    ctrl->running = false;
    LOG_INFO(LOG_TAG, "Cascade controller stopped");
    return WTC_OK;
}

/* Set control engine reference */
wtc_result_t cascade_set_control_engine(cascade_controller_t *ctrl,
                                         struct control_engine *engine) {
    if (!ctrl) return WTC_ERROR_INVALID_PARAM;
    ctrl->control = engine;
    return WTC_OK;
}

/* Add cascade loop */
wtc_result_t cascade_add_loop(cascade_controller_t *ctrl, const cascade_loop_t *loop) {
    if (!ctrl || !loop) return WTC_ERROR_INVALID_PARAM;

    /* Check for existing */
    for (int i = 0; i < ctrl->loop_count; i++) {
        if (ctrl->loops[i].cascade_id == loop->cascade_id) {
            memcpy(&ctrl->loops[i], loop, sizeof(cascade_loop_t));
            LOG_DEBUG(LOG_TAG, "Updated cascade %d: %s", loop->cascade_id, loop->name);
            return WTC_OK;
        }
    }

    if (ctrl->loop_count >= ctrl->config.max_cascades) {
        return WTC_ERROR_FULL;
    }

    memcpy(&ctrl->loops[ctrl->loop_count], loop, sizeof(cascade_loop_t));
    ctrl->loop_count++;

    LOG_INFO(LOG_TAG, "Added cascade %d: %s (primary: %d -> secondary: %d)",
             loop->cascade_id, loop->name, loop->primary_loop_id, loop->secondary_loop_id);
    return WTC_OK;
}

/* Remove cascade loop */
wtc_result_t cascade_remove_loop(cascade_controller_t *ctrl, int cascade_id) {
    if (!ctrl) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < ctrl->loop_count; i++) {
        if (ctrl->loops[i].cascade_id == cascade_id) {
            memmove(&ctrl->loops[i], &ctrl->loops[i + 1],
                    (ctrl->loop_count - i - 1) * sizeof(cascade_loop_t));
            ctrl->loop_count--;
            LOG_INFO(LOG_TAG, "Removed cascade %d", cascade_id);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Enable/disable cascade */
wtc_result_t cascade_enable(cascade_controller_t *ctrl, int cascade_id, bool enabled) {
    if (!ctrl) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < ctrl->loop_count; i++) {
        if (ctrl->loops[i].cascade_id == cascade_id) {
            ctrl->loops[i].enabled = enabled;
            ctrl->loops[i].cascade_active = false;

            /* When disabling, switch secondary loop to manual */
            if (!enabled && ctrl->control) {
                control_engine_set_pid_mode(ctrl->control,
                                            ctrl->loops[i].secondary_loop_id,
                                            PID_MODE_MANUAL);
            }

            LOG_INFO(LOG_TAG, "%s cascade %d",
                     enabled ? "Enabled" : "Disabled", cascade_id);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Get cascade loop status */
wtc_result_t cascade_get_loop(cascade_controller_t *ctrl, int cascade_id,
                               cascade_loop_t *loop) {
    if (!ctrl || !loop) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < ctrl->loop_count; i++) {
        if (ctrl->loops[i].cascade_id == cascade_id) {
            memcpy(loop, &ctrl->loops[i], sizeof(cascade_loop_t));
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Process cascade control */
wtc_result_t cascade_process(cascade_controller_t *ctrl) {
    if (!ctrl || !ctrl->running) return WTC_ERROR_NOT_INITIALIZED;

    uint64_t now = time_get_ms();
    if (now - ctrl->last_process_ms < ctrl->config.update_interval_ms) {
        return WTC_OK;  /* Not time yet */
    }
    ctrl->last_process_ms = now;

    if (!ctrl->control) return WTC_ERROR_NOT_INITIALIZED;

    for (int i = 0; i < ctrl->loop_count; i++) {
        cascade_loop_t *loop = &ctrl->loops[i];

        if (!loop->enabled) continue;

        /* Get primary loop output */
        pid_loop_t primary;
        if (control_engine_get_pid_loop(ctrl->control, loop->primary_loop_id,
                                         &primary) != WTC_OK) {
            continue;
        }

        /* Only cascade when primary is in AUTO */
        if (primary.mode != PID_MODE_AUTO && primary.mode != PID_MODE_CASCADE) {
            if (loop->cascade_active) {
                loop->cascade_active = false;
                control_engine_set_pid_mode(ctrl->control, loop->secondary_loop_id,
                                            PID_MODE_MANUAL);
                LOG_DEBUG(LOG_TAG, "Cascade %d deactivated (primary not in AUTO)",
                          loop->cascade_id);
            }
            continue;
        }

        /* Calculate secondary setpoint from primary output */
        float cascade_sp = primary.cv * loop->output_scale + loop->output_offset;

        /* Clamp to limits */
        if (cascade_sp < loop->min_setpoint) cascade_sp = loop->min_setpoint;
        if (cascade_sp > loop->max_setpoint) cascade_sp = loop->max_setpoint;

        loop->current_cascade_sp = cascade_sp;

        /* Set secondary loop setpoint and ensure it's in CASCADE mode */
        control_engine_set_setpoint(ctrl->control, loop->secondary_loop_id, cascade_sp);

        if (!loop->cascade_active) {
            control_engine_set_pid_mode(ctrl->control, loop->secondary_loop_id,
                                        PID_MODE_CASCADE);
            loop->cascade_active = true;
            LOG_DEBUG(LOG_TAG, "Cascade %d activated (SP: %.2f)",
                      loop->cascade_id, cascade_sp);
        }
    }

    return WTC_OK;
}
