/*
 * Water Treatment Controller - Alarm Rules Engine Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "alarm_rules.h"
#include "logger.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define LOG_TAG "ALARM_RULES"

/* Rule state for timing */
typedef struct {
    alarm_rule_t rule;
    uint64_t condition_start_ms;
    float last_value;
    bool in_alarm;
} rule_state_t;

/* Alarm rules engine structure */
struct alarm_rules_engine {
    rule_state_t *rules;
    int rule_count;
    int max_rules;
};

/* Initialize alarm rules engine */
wtc_result_t alarm_rules_init(alarm_rules_engine_t **engine, int max_rules) {
    if (!engine || max_rules <= 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    alarm_rules_engine_t *eng = calloc(1, sizeof(alarm_rules_engine_t));
    if (!eng) {
        return WTC_ERROR_NO_MEMORY;
    }

    eng->rules = calloc(max_rules, sizeof(rule_state_t));
    if (!eng->rules) {
        free(eng);
        return WTC_ERROR_NO_MEMORY;
    }

    eng->max_rules = max_rules;
    eng->rule_count = 0;

    LOG_INFO(LOG_TAG, "Alarm rules engine initialized (max %d rules)", max_rules);
    *engine = eng;
    return WTC_OK;
}

/* Cleanup alarm rules engine */
void alarm_rules_cleanup(alarm_rules_engine_t *engine) {
    if (!engine) return;
    free(engine->rules);
    free(engine);
    LOG_INFO(LOG_TAG, "Alarm rules engine cleaned up");
}

/* Add alarm rule */
wtc_result_t alarm_rules_add(alarm_rules_engine_t *engine, const alarm_rule_t *rule) {
    if (!engine || !rule) return WTC_ERROR_INVALID_PARAM;

    /* Check if rule already exists */
    for (int i = 0; i < engine->rule_count; i++) {
        if (engine->rules[i].rule.rule_id == rule->rule_id) {
            /* Update existing rule */
            memcpy(&engine->rules[i].rule, rule, sizeof(alarm_rule_t));
            LOG_DEBUG(LOG_TAG, "Updated alarm rule %d: %s", rule->rule_id, rule->name);
            return WTC_OK;
        }
    }

    /* Add new rule */
    if (engine->rule_count >= engine->max_rules) {
        LOG_ERROR(LOG_TAG, "Maximum rules reached (%d)", engine->max_rules);
        return WTC_ERROR_FULL;
    }

    memcpy(&engine->rules[engine->rule_count].rule, rule, sizeof(alarm_rule_t));
    engine->rules[engine->rule_count].condition_start_ms = 0;
    engine->rules[engine->rule_count].last_value = 0;
    engine->rules[engine->rule_count].in_alarm = false;
    engine->rule_count++;

    LOG_INFO(LOG_TAG, "Added alarm rule %d: %s", rule->rule_id, rule->name);
    return WTC_OK;
}

/* Remove alarm rule */
wtc_result_t alarm_rules_remove(alarm_rules_engine_t *engine, int rule_id) {
    if (!engine) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < engine->rule_count; i++) {
        if (engine->rules[i].rule.rule_id == rule_id) {
            /* Shift remaining rules */
            memmove(&engine->rules[i], &engine->rules[i + 1],
                    (engine->rule_count - i - 1) * sizeof(rule_state_t));
            engine->rule_count--;
            LOG_INFO(LOG_TAG, "Removed alarm rule %d", rule_id);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Get alarm rule */
wtc_result_t alarm_rules_get(alarm_rules_engine_t *engine, int rule_id, alarm_rule_t *rule) {
    if (!engine || !rule) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < engine->rule_count; i++) {
        if (engine->rules[i].rule.rule_id == rule_id) {
            memcpy(rule, &engine->rules[i].rule, sizeof(alarm_rule_t));
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Enable/disable alarm rule */
wtc_result_t alarm_rules_enable(alarm_rules_engine_t *engine, int rule_id, bool enabled) {
    if (!engine) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < engine->rule_count; i++) {
        if (engine->rules[i].rule.rule_id == rule_id) {
            engine->rules[i].rule.enabled = enabled;
            LOG_INFO(LOG_TAG, "%s alarm rule %d",
                     enabled ? "Enabled" : "Disabled", rule_id);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Check if condition is met */
bool alarm_rules_check_condition(alarm_condition_t condition, float value,
                                  float threshold, float last_value) {
    switch (condition) {
        case ALARM_CONDITION_HIGH:
            return value > threshold;

        case ALARM_CONDITION_LOW:
            return value < threshold;

        case ALARM_CONDITION_HIGH_HIGH:
            return value > threshold;

        case ALARM_CONDITION_LOW_LOW:
            return value < threshold;

        case ALARM_CONDITION_RATE_OF_CHANGE:
            return fabsf(value - last_value) > threshold;

        case ALARM_CONDITION_DEVIATION:
            return fabsf(value - threshold) > threshold * 0.1f;  /* 10% deviation */

        case ALARM_CONDITION_BAD_QUALITY:
            return false;  /* Handled separately */

        default:
            return false;
    }
}

/* Evaluate alarm rule against a value */
wtc_result_t alarm_rules_evaluate(alarm_rules_engine_t *engine, int rule_id,
                                   float value, uint64_t timestamp_ms, bool *triggered) {
    if (!engine || !triggered) return WTC_ERROR_INVALID_PARAM;

    *triggered = false;

    for (int i = 0; i < engine->rule_count; i++) {
        if (engine->rules[i].rule.rule_id == rule_id) {
            rule_state_t *state = &engine->rules[i];
            alarm_rule_t *rule = &state->rule;

            if (!rule->enabled) {
                state->condition_start_ms = 0;
                state->in_alarm = false;
                return WTC_OK;
            }

            bool condition_met = alarm_rules_check_condition(
                rule->condition, value, rule->threshold, state->last_value);

            state->last_value = value;

            if (condition_met) {
                if (state->condition_start_ms == 0) {
                    state->condition_start_ms = timestamp_ms;
                }

                uint64_t elapsed = timestamp_ms - state->condition_start_ms;
                if (elapsed >= rule->delay_ms && !state->in_alarm) {
                    state->in_alarm = true;
                    *triggered = true;
                    LOG_DEBUG(LOG_TAG, "Rule %d triggered: %s = %.2f (threshold: %.2f)",
                              rule_id, rule->name, value, rule->threshold);
                }
            } else {
                state->condition_start_ms = 0;
                if (state->in_alarm) {
                    state->in_alarm = false;
                    LOG_DEBUG(LOG_TAG, "Rule %d cleared: %s", rule_id, rule->name);
                }
            }

            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Evaluate all rules for a station/slot */
wtc_result_t alarm_rules_evaluate_point(alarm_rules_engine_t *engine,
                                         const char *rtu_station, int slot,
                                         float value, uint64_t timestamp_ms,
                                         int *triggered_rule_ids, int *triggered_count,
                                         int max_triggered) {
    if (!engine || !rtu_station || !triggered_rule_ids || !triggered_count) {
        return WTC_ERROR_INVALID_PARAM;
    }

    *triggered_count = 0;

    for (int i = 0; i < engine->rule_count; i++) {
        alarm_rule_t *rule = &engine->rules[i].rule;

        if (strcmp(rule->rtu_station, rtu_station) != 0 || rule->slot != slot) {
            continue;
        }

        bool triggered = false;
        wtc_result_t result = alarm_rules_evaluate(engine, rule->rule_id,
                                                    value, timestamp_ms, &triggered);

        if (result == WTC_OK && triggered && *triggered_count < max_triggered) {
            triggered_rule_ids[(*triggered_count)++] = rule->rule_id;
        }
    }

    return WTC_OK;
}

/* List all rules */
wtc_result_t alarm_rules_list(alarm_rules_engine_t *engine, alarm_rule_t **rules,
                               int *count, int max_count) {
    if (!engine || !rules || !count) return WTC_ERROR_INVALID_PARAM;

    int copy_count = engine->rule_count;
    if (copy_count > max_count) copy_count = max_count;

    *rules = calloc(copy_count, sizeof(alarm_rule_t));
    if (!*rules) {
        return WTC_ERROR_NO_MEMORY;
    }

    for (int i = 0; i < copy_count; i++) {
        memcpy(&(*rules)[i], &engine->rules[i].rule, sizeof(alarm_rule_t));
    }

    *count = copy_count;
    return WTC_OK;
}

/* Get rule count */
int alarm_rules_count(alarm_rules_engine_t *engine) {
    return engine ? engine->rule_count : 0;
}
