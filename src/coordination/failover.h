/*
 * Water Treatment Controller - Failover Management
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_FAILOVER_H
#define WTC_FAILOVER_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Failover manager handle */
typedef struct failover_manager failover_manager_t;

/* Failover configuration */
typedef struct {
    failover_mode_t mode;
    uint32_t heartbeat_interval_ms;
    uint32_t timeout_ms;
    int max_retries;
} failover_config_t;

/* RTU health status */
typedef struct {
    char station_name[WTC_MAX_STATION_NAME];
    bool healthy;
    uint64_t last_heartbeat_ms;
    int consecutive_failures;
    float packet_loss;
    bool in_failover;
    char backup_station[WTC_MAX_STATION_NAME];  /* If failed over to backup */
} rtu_health_t;

/* Failover status */
typedef struct {
    int healthy_count;
    int failed_count;
    int in_failover_count;
    uint64_t last_failover_ms;
    char last_failed_station[WTC_MAX_STATION_NAME];
} failover_status_t;

/* Initialize failover manager */
wtc_result_t failover_init(failover_manager_t **mgr, const failover_config_t *config);

/* Cleanup failover manager */
void failover_cleanup(failover_manager_t *mgr);

/* Start failover manager */
wtc_result_t failover_start(failover_manager_t *mgr);

/* Stop failover manager */
wtc_result_t failover_stop(failover_manager_t *mgr);

/* Set RTU registry */
struct rtu_registry;
wtc_result_t failover_set_registry(failover_manager_t *mgr, struct rtu_registry *registry);

/* Configure backup for an RTU */
wtc_result_t failover_set_backup(failover_manager_t *mgr,
                                  const char *primary_station,
                                  const char *backup_station);

/* Remove backup configuration */
wtc_result_t failover_remove_backup(failover_manager_t *mgr,
                                     const char *primary_station);

/* Get RTU health status */
wtc_result_t failover_get_health(failover_manager_t *mgr,
                                  const char *station_name,
                                  rtu_health_t *health);

/* Get overall failover status */
wtc_result_t failover_get_status(failover_manager_t *mgr, failover_status_t *status);

/* Process failover logic */
wtc_result_t failover_process(failover_manager_t *mgr);

/* Force failover for an RTU */
wtc_result_t failover_force(failover_manager_t *mgr, const char *station_name);

/* Restore from failover */
wtc_result_t failover_restore(failover_manager_t *mgr, const char *station_name);

/* Callbacks */
typedef void (*failover_callback_t)(const char *primary, const char *backup,
                                     bool failed_over, void *ctx);
wtc_result_t failover_set_callback(failover_manager_t *mgr,
                                    failover_callback_t callback, void *ctx);

#ifdef __cplusplus
}
#endif

#endif /* WTC_FAILOVER_H */
