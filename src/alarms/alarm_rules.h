/*
 * Water Treatment Controller - Alarm Rules Engine
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_ALARM_RULES_H
#define WTC_ALARM_RULES_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Alarm rules engine handle */
typedef struct alarm_rules_engine alarm_rules_engine_t;

/* Initialize alarm rules engine */
wtc_result_t alarm_rules_init(alarm_rules_engine_t **engine, int max_rules);

/* Cleanup alarm rules engine */
void alarm_rules_cleanup(alarm_rules_engine_t *engine);

/* Add alarm rule */
wtc_result_t alarm_rules_add(alarm_rules_engine_t *engine, const alarm_rule_t *rule);

/* Remove alarm rule */
wtc_result_t alarm_rules_remove(alarm_rules_engine_t *engine, int rule_id);

/* Get alarm rule */
wtc_result_t alarm_rules_get(alarm_rules_engine_t *engine, int rule_id, alarm_rule_t *rule);

/* Enable/disable alarm rule */
wtc_result_t alarm_rules_enable(alarm_rules_engine_t *engine, int rule_id, bool enabled);

/* Evaluate alarm rule against a value */
wtc_result_t alarm_rules_evaluate(alarm_rules_engine_t *engine, int rule_id,
                                   float value, uint64_t timestamp_ms, bool *triggered);

/* Evaluate all rules for a station/slot */
wtc_result_t alarm_rules_evaluate_point(alarm_rules_engine_t *engine,
                                         const char *rtu_station, int slot,
                                         float value, uint64_t timestamp_ms,
                                         int *triggered_rule_ids, int *triggered_count,
                                         int max_triggered);

/* List all rules */
wtc_result_t alarm_rules_list(alarm_rules_engine_t *engine, alarm_rule_t **rules,
                               int *count, int max_count);

/* Get rule count */
int alarm_rules_count(alarm_rules_engine_t *engine);

/* Check if condition is met */
bool alarm_rules_check_condition(alarm_condition_t condition, float value,
                                  float threshold, float last_value);

#ifdef __cplusplus
}
#endif

#endif /* WTC_ALARM_RULES_H */
