/*
 * Water Treatment Controller - Sequence Engine
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "control_engine.h"
#include "registry/rtu_registry.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>

/* Maximum steps in a sequence */
#define MAX_SEQUENCE_STEPS 64

/* Sequence step types */
typedef enum {
    STEP_TYPE_SET_OUTPUT = 0,
    STEP_TYPE_WAIT_TIME,
    STEP_TYPE_WAIT_CONDITION,
    STEP_TYPE_WAIT_LEVEL,
    STEP_TYPE_PARALLEL_START,
    STEP_TYPE_PARALLEL_END,
    STEP_TYPE_GOTO,
    STEP_TYPE_END,
} sequence_step_type_t;

/* Sequence step */
typedef struct {
    sequence_step_type_t type;
    char station_name[WTC_MAX_STATION_NAME];
    int slot;
    union {
        struct {
            uint8_t command;
            uint8_t pwm_duty;
        } output;
        struct {
            uint32_t duration_ms;
        } wait_time;
        struct {
            interlock_condition_t condition;
            float threshold;
            uint32_t timeout_ms;
        } wait_condition;
        struct {
            float target_level;
            float tolerance;
            uint32_t timeout_ms;
        } wait_level;
        struct {
            int target_step;
        } goto_step;
    } params;
} sequence_step_t;

/* Sequence definition */
typedef struct {
    int sequence_id;
    char name[WTC_MAX_NAME];
    bool enabled;
    sequence_state_t state;

    sequence_step_t steps[MAX_SEQUENCE_STEPS];
    int step_count;
    int current_step;

    uint64_t step_start_time_ms;
    uint64_t sequence_start_time_ms;

    /* CE-H4 fix: Configurable timeouts per-sequence */
    uint32_t sequence_timeout_ms;      /* Overall sequence timeout (0 = no limit) */
    uint32_t default_step_timeout_ms;  /* Default timeout for steps (0 = no limit) */

    /* Callbacks */
    void (*on_step_change)(int sequence_id, int step, void *ctx);
    void (*on_complete)(int sequence_id, bool success, void *ctx);
    void *callback_ctx;
} sequence_t;

/* Sequence engine state */
static sequence_t sequences[WTC_MAX_SEQUENCES];
static int sequence_count = 0;
static int next_sequence_id = 1;
static rtu_registry_t *seq_registry = NULL;

/* Set registry for sequence engine */
void sequence_engine_set_registry(rtu_registry_t *registry) {
    seq_registry = registry;
}

/* Create new sequence */
wtc_result_t sequence_create(const char *name, int *sequence_id) {
    if (!name || !sequence_id || sequence_count >= WTC_MAX_SEQUENCES) {
        return WTC_ERROR_INVALID_PARAM;
    }

    sequence_t *seq = &sequences[sequence_count++];
    memset(seq, 0, sizeof(sequence_t));

    seq->sequence_id = next_sequence_id++;
    strncpy(seq->name, name, sizeof(seq->name) - 1);
    seq->enabled = true;
    seq->state = SEQUENCE_STATE_IDLE;

    *sequence_id = seq->sequence_id;

    LOG_INFO("Created sequence %d: %s", seq->sequence_id, name);
    return WTC_OK;
}

/* Add step to sequence */
wtc_result_t sequence_add_step(int sequence_id, const sequence_step_t *step) {
    if (!step) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < sequence_count; i++) {
        if (sequences[i].sequence_id == sequence_id) {
            if (sequences[i].step_count >= MAX_SEQUENCE_STEPS) {
                return WTC_ERROR_FULL;
            }

            memcpy(&sequences[i].steps[sequences[i].step_count++],
                   step, sizeof(sequence_step_t));
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Helper to add output step */
wtc_result_t sequence_add_output_step(int sequence_id,
                                       const char *station, int slot,
                                       uint8_t command, uint8_t pwm_duty) {
    sequence_step_t step;
    memset(&step, 0, sizeof(step));
    step.type = STEP_TYPE_SET_OUTPUT;
    strncpy(step.station_name, station, WTC_MAX_STATION_NAME - 1);
    step.slot = slot;
    step.params.output.command = command;
    step.params.output.pwm_duty = pwm_duty;

    return sequence_add_step(sequence_id, &step);
}

/* Helper to add wait time step */
wtc_result_t sequence_add_wait_step(int sequence_id, uint32_t duration_ms) {
    sequence_step_t step;
    memset(&step, 0, sizeof(step));
    step.type = STEP_TYPE_WAIT_TIME;
    step.params.wait_time.duration_ms = duration_ms;

    return sequence_add_step(sequence_id, &step);
}

/* Helper to add wait condition step */
wtc_result_t sequence_add_wait_condition_step(int sequence_id,
                                               const char *station, int slot,
                                               interlock_condition_t condition,
                                               float threshold,
                                               uint32_t timeout_ms) {
    sequence_step_t step;
    memset(&step, 0, sizeof(step));
    step.type = STEP_TYPE_WAIT_CONDITION;
    strncpy(step.station_name, station, WTC_MAX_STATION_NAME - 1);
    step.slot = slot;
    step.params.wait_condition.condition = condition;
    step.params.wait_condition.threshold = threshold;
    step.params.wait_condition.timeout_ms = timeout_ms;

    return sequence_add_step(sequence_id, &step);
}

/* Helper to add end step */
wtc_result_t sequence_add_end_step(int sequence_id) {
    sequence_step_t step;
    memset(&step, 0, sizeof(step));
    step.type = STEP_TYPE_END;

    return sequence_add_step(sequence_id, &step);
}

/* Start sequence */
wtc_result_t sequence_start(int sequence_id) {
    for (int i = 0; i < sequence_count; i++) {
        if (sequences[i].sequence_id == sequence_id) {
            if (!sequences[i].enabled) {
                return WTC_ERROR_PERMISSION;
            }
            if (sequences[i].state == SEQUENCE_STATE_RUNNING) {
                return WTC_ERROR_BUSY;
            }

            sequences[i].state = SEQUENCE_STATE_RUNNING;
            sequences[i].current_step = 0;
            sequences[i].sequence_start_time_ms = time_get_ms();
            sequences[i].step_start_time_ms = time_get_ms();

            LOG_INFO("Started sequence %d: %s",
                     sequence_id, sequences[i].name);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Stop sequence */
wtc_result_t sequence_stop(int sequence_id) {
    for (int i = 0; i < sequence_count; i++) {
        if (sequences[i].sequence_id == sequence_id) {
            sequences[i].state = SEQUENCE_STATE_ABORTED;

            LOG_INFO("Stopped sequence %d: %s",
                     sequence_id, sequences[i].name);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Pause sequence */
wtc_result_t sequence_pause(int sequence_id) {
    for (int i = 0; i < sequence_count; i++) {
        if (sequences[i].sequence_id == sequence_id) {
            if (sequences[i].state == SEQUENCE_STATE_RUNNING) {
                sequences[i].state = SEQUENCE_STATE_PAUSED;
                LOG_INFO("Paused sequence %d at step %d",
                         sequence_id, sequences[i].current_step);
                return WTC_OK;
            }
            return WTC_ERROR_NOT_INITIALIZED;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Resume sequence */
wtc_result_t sequence_resume(int sequence_id) {
    for (int i = 0; i < sequence_count; i++) {
        if (sequences[i].sequence_id == sequence_id) {
            if (sequences[i].state == SEQUENCE_STATE_PAUSED) {
                sequences[i].state = SEQUENCE_STATE_RUNNING;
                sequences[i].step_start_time_ms = time_get_ms();
                LOG_INFO("Resumed sequence %d at step %d",
                         sequence_id, sequences[i].current_step);
                return WTC_OK;
            }
            return WTC_ERROR_NOT_INITIALIZED;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* CE-H4 fix: Set sequence timeouts */
wtc_result_t sequence_set_timeouts(int sequence_id,
                                    uint32_t sequence_timeout_ms,
                                    uint32_t default_step_timeout_ms) {
    for (int i = 0; i < sequence_count; i++) {
        if (sequences[i].sequence_id == sequence_id) {
            sequences[i].sequence_timeout_ms = sequence_timeout_ms;
            sequences[i].default_step_timeout_ms = default_step_timeout_ms;
            LOG_INFO("Sequence %d timeouts set: sequence=%ums, step=%ums",
                     sequence_id, sequence_timeout_ms, default_step_timeout_ms);
            return WTC_OK;
        }
    }
    return WTC_ERROR_NOT_FOUND;
}

/* Process all running sequences */
wtc_result_t sequence_process(void) {
    if (!seq_registry) return WTC_ERROR_NOT_INITIALIZED;

    uint64_t now_ms = time_get_ms();

    for (int i = 0; i < sequence_count; i++) {
        sequence_t *seq = &sequences[i];

        if (seq->state != SEQUENCE_STATE_RUNNING) continue;

        /* CE-H4 fix: Check sequence-level timeout */
        if (seq->sequence_timeout_ms > 0 &&
            now_ms - seq->sequence_start_time_ms >= seq->sequence_timeout_ms) {
            LOG_ERROR("Sequence %d (%s) timed out after %ums",
                      seq->sequence_id, seq->name, seq->sequence_timeout_ms);
            seq->state = SEQUENCE_STATE_FAULTED;
            if (seq->on_complete) {
                seq->on_complete(seq->sequence_id, false, seq->callback_ctx);
            }
            continue;
        }

        if (seq->current_step >= seq->step_count) {
            seq->state = SEQUENCE_STATE_COMPLETE;
            continue;
        }

        sequence_step_t *step = &seq->steps[seq->current_step];
        bool step_complete = false;

        switch (step->type) {
        case STEP_TYPE_SET_OUTPUT: {
            /* Set output immediately */
            actuator_output_t output;
            output.command = step->params.output.command;
            output.pwm_duty = step->params.output.pwm_duty;
            output.reserved[0] = 0;
            output.reserved[1] = 0;

            rtu_registry_update_actuator(seq_registry,
                                         step->station_name,
                                         step->slot,
                                         &output);
            step_complete = true;
            break;
        }

        case STEP_TYPE_WAIT_TIME:
            if (now_ms - seq->step_start_time_ms >= step->params.wait_time.duration_ms) {
                step_complete = true;
            }
            break;

        case STEP_TYPE_WAIT_CONDITION: {
            sensor_data_t sensor;
            if (rtu_registry_get_sensor(seq_registry,
                                        step->station_name,
                                        step->slot,
                                        &sensor) == WTC_OK) {
                bool condition_met = false;
                switch (step->params.wait_condition.condition) {
                case INTERLOCK_CONDITION_ABOVE:
                    condition_met = sensor.value > step->params.wait_condition.threshold;
                    break;
                case INTERLOCK_CONDITION_BELOW:
                    condition_met = sensor.value < step->params.wait_condition.threshold;
                    break;
                default:
                    break;
                }

                if (condition_met) {
                    step_complete = true;
                }
            }

            /* Check timeout */
            if (step->params.wait_condition.timeout_ms > 0 &&
                now_ms - seq->step_start_time_ms >= step->params.wait_condition.timeout_ms) {
                LOG_WARN("Sequence %d step %d timed out", seq->sequence_id, seq->current_step);
                seq->state = SEQUENCE_STATE_FAULTED;
            }
            break;
        }

        case STEP_TYPE_GOTO:
            seq->current_step = step->params.goto_step.target_step - 1; /* -1 because we increment below */
            step_complete = true;
            break;

        case STEP_TYPE_END:
            seq->state = SEQUENCE_STATE_COMPLETE;
            LOG_INFO("Sequence %d complete", seq->sequence_id);

            if (seq->on_complete) {
                seq->on_complete(seq->sequence_id, true, seq->callback_ctx);
            }
            break;

        default:
            step_complete = true;
            break;
        }

        /* Move to next step */
        if (step_complete && seq->state == SEQUENCE_STATE_RUNNING) {
            seq->current_step++;
            seq->step_start_time_ms = now_ms;

            if (seq->on_step_change) {
                seq->on_step_change(seq->sequence_id, seq->current_step, seq->callback_ctx);
            }
        }
    }

    return WTC_OK;
}

/* Get sequence state */
wtc_result_t sequence_get_state(int sequence_id, sequence_state_t *state, int *current_step) {
    for (int i = 0; i < sequence_count; i++) {
        if (sequences[i].sequence_id == sequence_id) {
            if (state) *state = sequences[i].state;
            if (current_step) *current_step = sequences[i].current_step;
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Create backwash sequence */
wtc_result_t create_backwash_sequence(int *sequence_id, const char *rtu_name) {
    if (!sequence_id || !rtu_name) return WTC_ERROR_INVALID_PARAM;

    sequence_create("Filter Backwash", sequence_id);

    /* Step 1: Close outlet valve */
    sequence_add_output_step(*sequence_id, rtu_name, 11, ACTUATOR_CMD_OFF, 0);
    sequence_add_wait_step(*sequence_id, 5000);

    /* Step 2: Open backwash inlet */
    sequence_add_output_step(*sequence_id, rtu_name, 10, ACTUATOR_CMD_ON, 0);
    sequence_add_wait_step(*sequence_id, 2000);

    /* Step 3: Start backwash pump */
    sequence_add_output_step(*sequence_id, rtu_name, 9, ACTUATOR_CMD_ON, 0);

    /* Step 4: Wait for turbidity to clear */
    sequence_add_wait_condition_step(*sequence_id, rtu_name, 3,
                                      INTERLOCK_CONDITION_BELOW, 10.0f, 300000);

    /* Step 5: Stop backwash pump */
    sequence_add_output_step(*sequence_id, rtu_name, 9, ACTUATOR_CMD_OFF, 0);
    sequence_add_wait_step(*sequence_id, 5000);

    /* Step 6: Close backwash inlet */
    sequence_add_output_step(*sequence_id, rtu_name, 10, ACTUATOR_CMD_OFF, 0);
    sequence_add_wait_step(*sequence_id, 2000);

    /* Step 7: Open outlet valve */
    sequence_add_output_step(*sequence_id, rtu_name, 11, ACTUATOR_CMD_ON, 0);

    /* End */
    sequence_add_end_step(*sequence_id);

    LOG_INFO("Created backwash sequence for %s", rtu_name);
    return WTC_OK;
}

/* Create tank fill sequence */
wtc_result_t create_tank_fill_sequence(int *sequence_id, const char *rtu_name,
                                        float target_level) {
    if (!sequence_id || !rtu_name) return WTC_ERROR_INVALID_PARAM;

    sequence_create("Tank Fill", sequence_id);

    /* Step 1: Open inlet valve */
    sequence_add_output_step(*sequence_id, rtu_name, 10, ACTUATOR_CMD_ON, 0);
    sequence_add_wait_step(*sequence_id, 2000);

    /* Step 2: Start fill pump */
    sequence_add_output_step(*sequence_id, rtu_name, 9, ACTUATOR_CMD_ON, 0);

    /* Step 3: Wait for target level */
    sequence_add_wait_condition_step(*sequence_id, rtu_name, 7,
                                      INTERLOCK_CONDITION_ABOVE, target_level, 3600000);

    /* Step 4: Stop fill pump */
    sequence_add_output_step(*sequence_id, rtu_name, 9, ACTUATOR_CMD_OFF, 0);
    sequence_add_wait_step(*sequence_id, 2000);

    /* Step 5: Close inlet valve */
    sequence_add_output_step(*sequence_id, rtu_name, 10, ACTUATOR_CMD_OFF, 0);

    /* End */
    sequence_add_end_step(*sequence_id);

    LOG_INFO("Created tank fill sequence for %s (target=%.1f%%)", rtu_name, target_level);
    return WTC_OK;
}
