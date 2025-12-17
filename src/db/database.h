/*
 * Water Treatment Controller - Database Layer
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_DATABASE_H
#define WTC_DATABASE_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Database handle */
typedef struct wtc_database wtc_database_t;

/* Database configuration */
typedef struct {
    const char *host;
    int port;
    const char *database;
    const char *username;
    const char *password;
    int max_connections;
    int connection_timeout_ms;
    bool use_ssl;
} database_config_t;

/* Initialize database connection */
wtc_result_t database_init(wtc_database_t **db, const database_config_t *config);

/* Cleanup database connection */
void database_cleanup(wtc_database_t *db);

/* Connect to database */
wtc_result_t database_connect(wtc_database_t *db);

/* Disconnect from database */
wtc_result_t database_disconnect(wtc_database_t *db);

/* Check connection status */
bool database_is_connected(wtc_database_t *db);

/* ============== RTU Operations ============== */

/* Save RTU device to database */
wtc_result_t database_save_rtu(wtc_database_t *db, const rtu_device_t *rtu);

/* Load RTU device from database */
wtc_result_t database_load_rtu(wtc_database_t *db, const char *station_name,
                                rtu_device_t *rtu);

/* Delete RTU device from database */
wtc_result_t database_delete_rtu(wtc_database_t *db, const char *station_name);

/* List all RTU devices */
wtc_result_t database_list_rtus(wtc_database_t *db, rtu_device_t **rtus,
                                 int *count, int max_count);

/* ============== Alarm Operations ============== */

/* Save alarm rule */
wtc_result_t database_save_alarm_rule(wtc_database_t *db, const alarm_rule_t *rule);

/* Load alarm rules */
wtc_result_t database_load_alarm_rules(wtc_database_t *db, alarm_rule_t **rules,
                                        int *count, int max_count);

/* Save alarm instance */
wtc_result_t database_save_alarm(wtc_database_t *db, const alarm_t *alarm);

/* Load alarm history */
wtc_result_t database_load_alarm_history(wtc_database_t *db,
                                          uint64_t start_time_ms,
                                          uint64_t end_time_ms,
                                          alarm_t **alarms,
                                          int *count,
                                          int max_count);

/* ============== Historian Operations ============== */

/* Save historian tag */
wtc_result_t database_save_historian_tag(wtc_database_t *db,
                                          const historian_tag_t *tag);

/* Load historian tags */
wtc_result_t database_load_historian_tags(wtc_database_t *db,
                                           historian_tag_t **tags,
                                           int *count, int max_count);

/* Save historian samples (batch) */
wtc_result_t database_save_historian_samples(wtc_database_t *db,
                                              const historian_sample_t *samples,
                                              int count);

/* Query historian samples */
wtc_result_t database_query_historian_samples(wtc_database_t *db,
                                               int tag_id,
                                               uint64_t start_time_ms,
                                               uint64_t end_time_ms,
                                               historian_sample_t **samples,
                                               int *count,
                                               int max_count);

/* ============== Control Operations ============== */

/* Save PID loop configuration */
wtc_result_t database_save_pid_loop(wtc_database_t *db, const pid_loop_t *loop);

/* Load PID loops */
wtc_result_t database_load_pid_loops(wtc_database_t *db, pid_loop_t **loops,
                                      int *count, int max_count);

/* Save interlock configuration */
wtc_result_t database_save_interlock(wtc_database_t *db, const interlock_t *interlock);

/* Load interlocks */
wtc_result_t database_load_interlocks(wtc_database_t *db, interlock_t **interlocks,
                                       int *count, int max_count);

/* ============== User Operations ============== */

/* Save user */
wtc_result_t database_save_user(wtc_database_t *db, const user_t *user);

/* Load user by username */
wtc_result_t database_load_user(wtc_database_t *db, const char *username,
                                 user_t *user);

/* Delete user */
wtc_result_t database_delete_user(wtc_database_t *db, const char *username);

/* List all users */
wtc_result_t database_list_users(wtc_database_t *db, user_t **users,
                                  int *count, int max_count);

/* ============== Maintenance ============== */

/* Purge old historian data */
wtc_result_t database_purge_historian_data(wtc_database_t *db, int retention_days);

/* Purge old alarm history */
wtc_result_t database_purge_alarm_history(wtc_database_t *db, int retention_days);

/* Get database statistics */
typedef struct {
    uint64_t total_rows;
    uint64_t historian_samples;
    uint64_t alarm_records;
    uint64_t storage_bytes;
} database_stats_t;

wtc_result_t database_get_stats(wtc_database_t *db, database_stats_t *stats);

/* Execute schema migrations */
wtc_result_t database_migrate(wtc_database_t *db);

#ifdef __cplusplus
}
#endif

#endif /* WTC_DATABASE_H */
