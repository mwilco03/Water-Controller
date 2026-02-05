/*
 * Water Treatment Controller - Failover Management Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "failover.h"
#include "rtu_registry.h"
#include "logger.h"
#include "time_utils.h"
#include <stdlib.h>
#include <string.h>

#define LOG_TAG "FAILOVER"
#define MAX_MONITORED_RTUS 256

/* Backup mapping */
typedef struct {
    char primary[WTC_MAX_STATION_NAME];
    char backup[WTC_MAX_STATION_NAME];
    bool active;  /* Is failover currently active */
} backup_mapping_t;

/* Failover manager structure */
struct failover_manager {
    failover_config_t config;
    bool running;

    struct rtu_registry *registry;

    rtu_health_t *health;
    int health_count;

    backup_mapping_t *backups;
    int backup_count;

    failover_status_t status;
    failover_callback_t callback;
    void *callback_ctx;

    uint64_t last_process_ms;
};

/* Initialize failover manager */
wtc_result_t failover_init(failover_manager_t **mgr, const failover_config_t *config) {
    if (!mgr || !config) return WTC_ERROR_INVALID_PARAM;

    failover_manager_t *fm = calloc(1, sizeof(failover_manager_t));
    if (!fm) {
        return WTC_ERROR_NO_MEMORY;
    }

    memcpy(&fm->config, config, sizeof(failover_config_t));

    fm->health = calloc(MAX_MONITORED_RTUS, sizeof(rtu_health_t));
    fm->backups = calloc(MAX_MONITORED_RTUS, sizeof(backup_mapping_t));

    if (!fm->health || !fm->backups) {
        free(fm->health);
        free(fm->backups);
        free(fm);
        return WTC_ERROR_NO_MEMORY;
    }

    fm->running = false;

    LOG_INFO(LOG_TAG, "Failover manager initialized (mode: %d, timeout: %ums)",
             config->mode, config->timeout_ms);
    *mgr = fm;
    return WTC_OK;
}

/* Cleanup failover manager */
void failover_cleanup(failover_manager_t *mgr) {
    if (!mgr) return;
    free(mgr->health);
    free(mgr->backups);
    free(mgr);
    LOG_INFO(LOG_TAG, "Failover manager cleaned up");
}

/* Start failover manager */
wtc_result_t failover_start(failover_manager_t *mgr) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;
    mgr->running = true;
    mgr->last_process_ms = time_get_ms();
    LOG_INFO(LOG_TAG, "Failover manager started");
    return WTC_OK;
}

/* Stop failover manager */
wtc_result_t failover_stop(failover_manager_t *mgr) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;
    mgr->running = false;
    LOG_INFO(LOG_TAG, "Failover manager stopped");
    return WTC_OK;
}

/* Set RTU registry */
wtc_result_t failover_set_registry(failover_manager_t *mgr, struct rtu_registry *registry) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;
    mgr->registry = registry;
    return WTC_OK;
}

/* Find or create health entry */
static rtu_health_t *get_health_entry(failover_manager_t *mgr, const char *station_name) {
    /* Find existing */
    for (int i = 0; i < mgr->health_count; i++) {
        if (strcmp(mgr->health[i].station_name, station_name) == 0) {
            return &mgr->health[i];
        }
    }

    /* Create new */
    if (mgr->health_count >= MAX_MONITORED_RTUS) {
        return NULL;
    }

    rtu_health_t *h = &mgr->health[mgr->health_count++];
    memset(h, 0, sizeof(rtu_health_t));
    snprintf(h->station_name, sizeof(h->station_name), "%s", station_name);
    h->healthy = true;
    h->last_heartbeat_ms = time_get_ms();

    return h;
}

/* Configure backup for an RTU */
wtc_result_t failover_set_backup(failover_manager_t *mgr,
                                  const char *primary_station,
                                  const char *backup_station) {
    if (!mgr || !primary_station || !backup_station) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Check for existing */
    for (int i = 0; i < mgr->backup_count; i++) {
        if (strcmp(mgr->backups[i].primary, primary_station) == 0) {
            snprintf(mgr->backups[i].backup, sizeof(mgr->backups[i].backup), "%s", backup_station);
            LOG_INFO(LOG_TAG, "Updated backup for %s -> %s",
                     primary_station, backup_station);
            return WTC_OK;
        }
    }

    if (mgr->backup_count >= MAX_MONITORED_RTUS) {
        return WTC_ERROR_FULL;
    }

    backup_mapping_t *b = &mgr->backups[mgr->backup_count++];
    snprintf(b->primary, sizeof(b->primary), "%s", primary_station);
    snprintf(b->backup, sizeof(b->backup), "%s", backup_station);
    b->active = false;

    LOG_INFO(LOG_TAG, "Configured backup for %s -> %s", primary_station, backup_station);
    return WTC_OK;
}

/* Remove backup configuration */
wtc_result_t failover_remove_backup(failover_manager_t *mgr,
                                     const char *primary_station) {
    if (!mgr || !primary_station) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->backup_count; i++) {
        if (strcmp(mgr->backups[i].primary, primary_station) == 0) {
            memmove(&mgr->backups[i], &mgr->backups[i + 1],
                    (mgr->backup_count - i - 1) * sizeof(backup_mapping_t));
            mgr->backup_count--;
            LOG_INFO(LOG_TAG, "Removed backup for %s", primary_station);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Get RTU health status */
wtc_result_t failover_get_health(failover_manager_t *mgr,
                                  const char *station_name,
                                  rtu_health_t *health) {
    if (!mgr || !station_name || !health) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->health_count; i++) {
        if (strcmp(mgr->health[i].station_name, station_name) == 0) {
            memcpy(health, &mgr->health[i], sizeof(rtu_health_t));
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Get overall failover status */
wtc_result_t failover_get_status(failover_manager_t *mgr, failover_status_t *status) {
    if (!mgr || !status) return WTC_ERROR_INVALID_PARAM;
    memcpy(status, &mgr->status, sizeof(failover_status_t));
    return WTC_OK;
}

/* Execute failover */
static void execute_failover(failover_manager_t *mgr, backup_mapping_t *mapping) {
    if (mapping->active) return;

    LOG_WARN(LOG_TAG, "Executing failover: %s -> %s",
             mapping->primary, mapping->backup);

    mapping->active = true;
    mgr->status.last_failover_ms = time_get_ms();
    snprintf(mgr->status.last_failed_station, WTC_MAX_STATION_NAME, "%s", mapping->primary);

    /* Update health entry */
    rtu_health_t *h = get_health_entry(mgr, mapping->primary);
    if (h) {
        h->in_failover = true;
        snprintf(h->backup_station, sizeof(h->backup_station), "%s", mapping->backup);
    }

    /* Notify callback */
    if (mgr->callback) {
        mgr->callback(mapping->primary, mapping->backup, true, mgr->callback_ctx);
    }
}

/* Restore from failover */
wtc_result_t failover_restore(failover_manager_t *mgr, const char *station_name) {
    if (!mgr || !station_name) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->backup_count; i++) {
        if (strcmp(mgr->backups[i].primary, station_name) == 0 &&
            mgr->backups[i].active) {

            LOG_INFO(LOG_TAG, "Restoring from failover: %s", station_name);

            mgr->backups[i].active = false;

            rtu_health_t *h = get_health_entry(mgr, station_name);
            if (h) {
                h->in_failover = false;
                h->backup_station[0] = '\0';
            }

            if (mgr->callback) {
                mgr->callback(mgr->backups[i].primary, mgr->backups[i].backup,
                              false, mgr->callback_ctx);
            }

            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Force failover for an RTU */
wtc_result_t failover_force(failover_manager_t *mgr, const char *station_name) {
    if (!mgr || !station_name) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->backup_count; i++) {
        if (strcmp(mgr->backups[i].primary, station_name) == 0) {
            execute_failover(mgr, &mgr->backups[i]);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Process failover logic */
wtc_result_t failover_process(failover_manager_t *mgr) {
    if (!mgr || !mgr->running) return WTC_ERROR_NOT_INITIALIZED;

    uint64_t now = time_get_ms();

    /* Update health from registry */
    if (mgr->registry) {
        rtu_device_t *devices = NULL;
        int count = 0;

        if (rtu_registry_list_devices(mgr->registry, &devices, &count,
                                       MAX_MONITORED_RTUS) == WTC_OK && devices) {
            mgr->status.healthy_count = 0;
            mgr->status.failed_count = 0;
            mgr->status.in_failover_count = 0;

            for (int i = 0; i < count; i++) {
                rtu_health_t *h = get_health_entry(mgr, devices[i].station_name);
                if (!h) continue;

                bool was_healthy = h->healthy;

                /* Check connection state */
                if (devices[i].connection_state == PROFINET_STATE_RUNNING) {
                    h->healthy = true;
                    h->last_heartbeat_ms = now;
                    h->consecutive_failures = 0;
                    mgr->status.healthy_count++;

                    /* Auto-restore if in failover and primary is back */
                    if (h->in_failover &&
                        mgr->config.mode == FAILOVER_MODE_AUTO) {
                        failover_restore(mgr, h->station_name);
                    }
                } else {
                    /* Check timeout */
                    if ((now - h->last_heartbeat_ms) >= mgr->config.timeout_ms) {
                        h->healthy = false;
                        h->consecutive_failures++;
                        mgr->status.failed_count++;

                        if (was_healthy) {
                            LOG_WARN(LOG_TAG, "RTU %s health check failed",
                                     h->station_name);
                        }
                    }
                }

                h->packet_loss = devices[i].packet_loss_percent;

                if (h->in_failover) {
                    mgr->status.in_failover_count++;
                }
            }

            free(devices);
        }
    }

    /* Check for failover conditions */
    if (mgr->config.mode != FAILOVER_MODE_MANUAL) {
        for (int i = 0; i < mgr->backup_count; i++) {
            rtu_health_t *primary = get_health_entry(mgr, mgr->backups[i].primary);

            if (primary && !primary->healthy && !mgr->backups[i].active) {
                /* Check if backup is healthy */
                rtu_health_t *backup = get_health_entry(mgr, mgr->backups[i].backup);

                if (backup && backup->healthy) {
                    execute_failover(mgr, &mgr->backups[i]);
                } else {
                    LOG_ERROR(LOG_TAG, "Cannot failover %s: backup %s not healthy",
                              mgr->backups[i].primary, mgr->backups[i].backup);
                }
            }
        }
    }

    mgr->last_process_ms = now;
    return WTC_OK;
}

/* Set callback */
wtc_result_t failover_set_callback(failover_manager_t *mgr,
                                    failover_callback_t callback, void *ctx) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;
    mgr->callback = callback;
    mgr->callback_ctx = ctx;
    return WTC_OK;
}
