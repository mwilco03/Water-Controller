/*
 * Water Treatment Controller - Alarm Manager
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_ALARM_MANAGER_H
#define WTC_ALARM_MANAGER_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Alarm manager handle */
typedef struct alarm_manager alarm_manager_t;

/* Alarm manager configuration */
typedef struct {
    const char *database_path;
    int max_active_alarms;
    int max_history_entries;
    bool store_to_database;

    /* ISA-18.2 settings */
    int max_alarms_per_10min;  /* Alarm flood detection */
    bool require_ack;           /* Require acknowledgment */
    bool shelving_enabled;      /* Allow alarm shelving */

    /* Callbacks */
    alarm_callback_t on_alarm_raised;
    alarm_callback_t on_alarm_cleared;
    alarm_callback_t on_alarm_acknowledged;
    void *callback_ctx;
} alarm_manager_config_t;

/* Initialize alarm manager */
wtc_result_t alarm_manager_init(alarm_manager_t **manager,
                                 const alarm_manager_config_t *config);

/* Cleanup alarm manager */
void alarm_manager_cleanup(alarm_manager_t *manager);

/* Start alarm manager */
wtc_result_t alarm_manager_start(alarm_manager_t *manager);

/* Stop alarm manager */
wtc_result_t alarm_manager_stop(alarm_manager_t *manager);

/* Set RTU registry for data access */
struct rtu_registry;
wtc_result_t alarm_manager_set_registry(alarm_manager_t *manager,
                                         struct rtu_registry *registry);

/* ============== Alarm Rules ============== */

/* Create alarm rule */
wtc_result_t alarm_manager_create_rule(alarm_manager_t *manager,
                                        const char *rtu_station,
                                        int slot,
                                        alarm_condition_t condition,
                                        float threshold,
                                        alarm_severity_t severity,
                                        uint32_t delay_ms,
                                        const char *message,
                                        int *rule_id);

/* Delete alarm rule */
wtc_result_t alarm_manager_delete_rule(alarm_manager_t *manager,
                                        int rule_id);

/* Enable/disable alarm rule */
wtc_result_t alarm_manager_enable_rule(alarm_manager_t *manager,
                                        int rule_id,
                                        bool enabled);

/* Get alarm rule */
wtc_result_t alarm_manager_get_rule(alarm_manager_t *manager,
                                     int rule_id,
                                     alarm_rule_t *rule);

/* List all alarm rules */
wtc_result_t alarm_manager_list_rules(alarm_manager_t *manager,
                                       alarm_rule_t **rules,
                                       int *count,
                                       int max_count);

/* ============== Active Alarms ============== */

/* Acknowledge alarm */
wtc_result_t alarm_manager_acknowledge(alarm_manager_t *manager,
                                        int alarm_id,
                                        const char *user);

/* Acknowledge all active alarms */
wtc_result_t alarm_manager_acknowledge_all(alarm_manager_t *manager,
                                            const char *user);

/* Get active alarms */
wtc_result_t alarm_manager_get_active(alarm_manager_t *manager,
                                       alarm_t **alarms,
                                       int *count,
                                       int max_count);

/* Get active alarm count */
int alarm_manager_get_active_count(alarm_manager_t *manager);

/* Get unacknowledged alarm count */
int alarm_manager_get_unack_count(alarm_manager_t *manager);

/* ============== Alarm History ============== */

/* Get alarm history */
wtc_result_t alarm_manager_get_history(alarm_manager_t *manager,
                                        uint64_t start_time_ms,
                                        uint64_t end_time_ms,
                                        alarm_t **alarms,
                                        int *count,
                                        int max_count);

/* Clear alarm history older than specified time */
wtc_result_t alarm_manager_clear_history(alarm_manager_t *manager,
                                          uint64_t before_time_ms);

/* ============== Alarm Suppression ============== */

/* Suppress alarms for a slot temporarily */
wtc_result_t alarm_manager_suppress(alarm_manager_t *manager,
                                     const char *rtu_station,
                                     int slot,
                                     uint32_t duration_ms,
                                     const char *reason,
                                     const char *user);

/* Remove suppression */
wtc_result_t alarm_manager_unsuppress(alarm_manager_t *manager,
                                       const char *rtu_station,
                                       int slot);

/* Check if alarms are suppressed */
bool alarm_manager_is_suppressed(alarm_manager_t *manager,
                                  const char *rtu_station,
                                  int slot);

/* ============== Alarm Shelving (ISA-18.2) ============== */

/* Shelve alarm (temporary disable with audit trail) */
wtc_result_t alarm_manager_shelve(alarm_manager_t *manager,
                                   int rule_id,
                                   uint32_t duration_ms,
                                   const char *reason,
                                   const char *user);

/* Unshelve alarm */
wtc_result_t alarm_manager_unshelve(alarm_manager_t *manager,
                                     int rule_id,
                                     const char *user);

/* ============== ISA-18.2 Compliance (ALM-H1 fix) ============== */

/* Set alarm point out-of-service */
wtc_result_t alarm_manager_set_out_of_service(alarm_manager_t *manager,
                                               int rule_id,
                                               bool oos,
                                               const char *reason,
                                               const char *user);

/* Set rationalization data for alarm rule */
wtc_result_t alarm_manager_set_rationalization(alarm_manager_t *manager,
                                                int rule_id,
                                                const char *consequence,
                                                const char *response,
                                                uint32_t response_time_sec);

/* Get rationalization data for alarm rule */
wtc_result_t alarm_manager_get_rationalization(alarm_manager_t *manager,
                                                int rule_id,
                                                char *consequence,
                                                size_t consequence_len,
                                                char *response,
                                                size_t response_len,
                                                uint32_t *response_time_sec);

/* Export alarm configuration to JSON */
wtc_result_t alarm_manager_export_config(alarm_manager_t *manager,
                                          char *buffer,
                                          size_t buffer_size);

/* ============== Statistics ============== */

/* Get alarm statistics */
wtc_result_t alarm_manager_get_statistics(alarm_manager_t *manager,
                                           alarm_stats_t *stats);

/* Get alarm rate (alarms per hour) */
float alarm_manager_get_alarm_rate(alarm_manager_t *manager);

/* Check for alarm flood condition */
bool alarm_manager_is_alarm_flood(alarm_manager_t *manager);

/* ============== Processing ============== */

/* Process alarm rules (called periodically) */
wtc_result_t alarm_manager_process(alarm_manager_t *manager);

/* Manually raise alarm (for external sources) */
wtc_result_t alarm_manager_raise_alarm(alarm_manager_t *manager,
                                        const char *rtu_station,
                                        int slot,
                                        alarm_severity_t severity,
                                        const char *message,
                                        float value);

/* Manually clear alarm */
wtc_result_t alarm_manager_clear_alarm(alarm_manager_t *manager,
                                        int alarm_id);

#ifdef __cplusplus
}
#endif

#endif /* WTC_ALARM_MANAGER_H */
