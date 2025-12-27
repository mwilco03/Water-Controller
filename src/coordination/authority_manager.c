/*
 * Water Treatment Controller - Authority Manager Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "authority_manager.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>

/* Maximum tracked RTUs */
#define MAX_AUTHORITY_ENTRIES 256

/* Default configuration values */
#define DEFAULT_HANDOFF_TIMEOUT_MS     5000
#define DEFAULT_STALE_COMMAND_MS       10000
#define DEFAULT_HEARTBEAT_INTERVAL_MS  1000

/* Authority entry for a single RTU */
typedef struct {
    char station_name[WTC_MAX_STATION_NAME];
    authority_context_t context;
    uint64_t last_heartbeat_ms;
    bool in_use;
} authority_entry_t;

/* Authority manager structure */
struct authority_manager {
    authority_manager_config_t config;
    authority_entry_t entries[MAX_AUTHORITY_ENTRIES];
    int entry_count;

    authority_callback_t callback;
    void *callback_ctx;

    pthread_mutex_t lock;
};

/* Find or create authority entry for RTU */
static authority_entry_t *find_or_create_entry(authority_manager_t *manager,
                                                 const char *station_name) {
    /* First, look for existing entry */
    for (int i = 0; i < MAX_AUTHORITY_ENTRIES; i++) {
        if (manager->entries[i].in_use &&
            strcmp(manager->entries[i].station_name, station_name) == 0) {
            return &manager->entries[i];
        }
    }

    /* Create new entry */
    for (int i = 0; i < MAX_AUTHORITY_ENTRIES; i++) {
        if (!manager->entries[i].in_use) {
            authority_entry_t *entry = &manager->entries[i];
            memset(entry, 0, sizeof(*entry));
            strncpy(entry->station_name, station_name,
                    sizeof(entry->station_name) - 1);
            authority_context_init(&entry->context);
            entry->in_use = true;
            manager->entry_count++;
            return entry;
        }
    }

    return NULL;
}

/* Find authority entry for RTU */
static authority_entry_t *find_entry(authority_manager_t *manager,
                                      const char *station_name) {
    for (int i = 0; i < MAX_AUTHORITY_ENTRIES; i++) {
        if (manager->entries[i].in_use &&
            strcmp(manager->entries[i].station_name, station_name) == 0) {
            return &manager->entries[i];
        }
    }
    return NULL;
}

/* Notify callback of state change */
static void notify_state_change(authority_manager_t *manager,
                                  const char *station_name,
                                  authority_state_t old_state,
                                  authority_state_t new_state) {
    if (manager->callback && old_state != new_state) {
        manager->callback(station_name, old_state, new_state, manager->callback_ctx);
    }
}

/* Public API */

wtc_result_t authority_manager_init(authority_manager_t **manager,
                                     const authority_manager_config_t *config) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    authority_manager_t *mgr = calloc(1, sizeof(authority_manager_t));
    if (!mgr) {
        return WTC_ERROR_NO_MEMORY;
    }

    if (config) {
        mgr->config = *config;
    } else {
        mgr->config.handoff_timeout_ms = DEFAULT_HANDOFF_TIMEOUT_MS;
        mgr->config.stale_command_ms = DEFAULT_STALE_COMMAND_MS;
        mgr->config.heartbeat_interval_ms = DEFAULT_HEARTBEAT_INTERVAL_MS;
        mgr->config.auto_release_on_disconnect = true;
    }

    pthread_mutex_init(&mgr->lock, NULL);

    *manager = mgr;
    LOG_INFO("Authority manager initialized (handoff_timeout=%ums, stale_command=%ums)",
             mgr->config.handoff_timeout_ms, mgr->config.stale_command_ms);

    return WTC_OK;
}

void authority_manager_cleanup(authority_manager_t *manager) {
    if (!manager) return;

    pthread_mutex_destroy(&manager->lock);
    free(manager);
    LOG_DEBUG("Authority manager cleaned up");
}

void authority_manager_set_callback(authority_manager_t *manager,
                                     authority_callback_t callback,
                                     void *ctx) {
    if (!manager) return;

    pthread_mutex_lock(&manager->lock);
    manager->callback = callback;
    manager->callback_ctx = ctx;
    pthread_mutex_unlock(&manager->lock);
}

wtc_result_t authority_request(authority_manager_t *manager,
                                const char *station_name,
                                authority_context_t *ctx) {
    if (!manager || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    authority_entry_t *entry = find_or_create_entry(manager, station_name);
    if (!entry) {
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_FULL;
    }

    authority_state_t old_state = entry->context.state;

    /* Check current state */
    if (entry->context.state == AUTHORITY_SUPERVISED) {
        /* Already have authority */
        pthread_mutex_unlock(&manager->lock);
        if (ctx) *ctx = entry->context;
        return WTC_OK;
    }

    if (entry->context.state == AUTHORITY_HANDOFF_PENDING) {
        /* Already requesting */
        pthread_mutex_unlock(&manager->lock);
        if (ctx) *ctx = entry->context;
        return WTC_ERROR_BUSY;
    }

    /* Transition to HANDOFF_PENDING */
    entry->context.state = AUTHORITY_HANDOFF_PENDING;
    entry->context.request_time_ms = time_get_ms();
    entry->context.rtu_acknowledged = false;
    entry->context.controller_online = true;
    entry->context.stale_command_threshold_ms = manager->config.stale_command_ms;

    LOG_INFO("Requesting authority over RTU %s (epoch=%u)",
             station_name, entry->context.epoch);

    if (ctx) *ctx = entry->context;

    notify_state_change(manager, station_name, old_state, entry->context.state);

    pthread_mutex_unlock(&manager->lock);
    return WTC_OK;
}

wtc_result_t authority_release(authority_manager_t *manager,
                                const char *station_name,
                                authority_context_t *ctx) {
    if (!manager || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    authority_entry_t *entry = find_entry(manager, station_name);
    if (!entry) {
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    authority_state_t old_state = entry->context.state;

    if (entry->context.state != AUTHORITY_SUPERVISED) {
        /* Don't have authority to release */
        pthread_mutex_unlock(&manager->lock);
        if (ctx) *ctx = entry->context;
        return WTC_ERROR_PERMISSION;
    }

    /* Transition to RELEASING */
    entry->context.state = AUTHORITY_RELEASING;
    entry->context.request_time_ms = time_get_ms();

    LOG_INFO("Releasing authority over RTU %s (epoch=%u)",
             station_name, entry->context.epoch);

    if (ctx) *ctx = entry->context;

    notify_state_change(manager, station_name, old_state, entry->context.state);

    pthread_mutex_unlock(&manager->lock);
    return WTC_OK;
}

wtc_result_t authority_handle_grant(authority_manager_t *manager,
                                     const char *station_name,
                                     uint32_t epoch,
                                     authority_context_t *ctx) {
    if (!manager || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    authority_entry_t *entry = find_entry(manager, station_name);
    if (!entry) {
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    authority_state_t old_state = entry->context.state;

    if (entry->context.state != AUTHORITY_HANDOFF_PENDING) {
        LOG_WARN("Received unexpected authority grant from %s (state=%d)",
                 station_name, entry->context.state);
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_PROTOCOL;
    }

    /* Increment epoch and transition to SUPERVISED */
    entry->context.epoch = epoch;
    entry->context.state = AUTHORITY_SUPERVISED;
    entry->context.grant_time_ms = time_get_ms();
    entry->context.rtu_acknowledged = true;
    strncpy(entry->context.holder, "CONTROLLER",
            sizeof(entry->context.holder) - 1);

    LOG_INFO("Authority granted over RTU %s (epoch=%u, took %lums)",
             station_name, entry->context.epoch,
             (unsigned long)(entry->context.grant_time_ms - entry->context.request_time_ms));

    if (ctx) *ctx = entry->context;

    notify_state_change(manager, station_name, old_state, entry->context.state);

    pthread_mutex_unlock(&manager->lock);
    return WTC_OK;
}

wtc_result_t authority_handle_released(authority_manager_t *manager,
                                        const char *station_name,
                                        uint32_t epoch,
                                        authority_context_t *ctx) {
    if (!manager || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    authority_entry_t *entry = find_entry(manager, station_name);
    if (!entry) {
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    authority_state_t old_state = entry->context.state;

    /* Transition to AUTONOMOUS */
    entry->context.epoch = epoch;
    entry->context.state = AUTHORITY_AUTONOMOUS;
    entry->context.rtu_acknowledged = false;
    strncpy(entry->context.holder, station_name,
            sizeof(entry->context.holder) - 1);

    LOG_INFO("Authority released to RTU %s (epoch=%u)", station_name, epoch);

    if (ctx) *ctx = entry->context;

    notify_state_change(manager, station_name, old_state, entry->context.state);

    pthread_mutex_unlock(&manager->lock);
    return WTC_OK;
}

wtc_result_t authority_validate_command(authority_manager_t *manager,
                                         const char *station_name,
                                         uint32_t command_epoch,
                                         const authority_context_t *ctx) {
    if (!manager || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    authority_entry_t *entry = find_entry(manager, station_name);
    if (!entry) {
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    /* Check if we have authority */
    if (entry->context.state != AUTHORITY_SUPERVISED) {
        LOG_WARN("Command rejected for %s: no authority (state=%d)",
                 station_name, entry->context.state);
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_PERMISSION;
    }

    /* Check epoch - reject commands from old epochs */
    if (command_epoch != 0 && command_epoch < entry->context.epoch) {
        LOG_WARN("Command rejected for %s: stale epoch (%u < %u)",
                 station_name, command_epoch, entry->context.epoch);
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_PERMISSION;
    }

    pthread_mutex_unlock(&manager->lock);
    return WTC_OK;
}

authority_state_t authority_get_state(authority_manager_t *manager,
                                       const char *station_name) {
    if (!manager || !station_name) {
        return AUTHORITY_AUTONOMOUS;
    }

    pthread_mutex_lock(&manager->lock);

    authority_entry_t *entry = find_entry(manager, station_name);
    authority_state_t state = entry ? entry->context.state : AUTHORITY_AUTONOMOUS;

    pthread_mutex_unlock(&manager->lock);
    return state;
}

uint32_t authority_get_epoch(authority_manager_t *manager,
                              const char *station_name) {
    if (!manager || !station_name) {
        return 0;
    }

    pthread_mutex_lock(&manager->lock);

    authority_entry_t *entry = find_entry(manager, station_name);
    uint32_t epoch = entry ? entry->context.epoch : 0;

    pthread_mutex_unlock(&manager->lock);
    return epoch;
}

wtc_result_t authority_manager_process(authority_manager_t *manager,
                                        uint64_t now_ms) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    for (int i = 0; i < MAX_AUTHORITY_ENTRIES; i++) {
        authority_entry_t *entry = &manager->entries[i];
        if (!entry->in_use) continue;

        /* Check for handoff timeout */
        if (entry->context.state == AUTHORITY_HANDOFF_PENDING) {
            uint64_t elapsed = now_ms - entry->context.request_time_ms;
            if (elapsed > manager->config.handoff_timeout_ms) {
                LOG_WARN("Authority handoff timeout for %s after %lums",
                         entry->station_name, (unsigned long)elapsed);

                authority_state_t old_state = entry->context.state;
                entry->context.state = AUTHORITY_AUTONOMOUS;
                entry->context.controller_online = false;

                notify_state_change(manager, entry->station_name,
                                   old_state, entry->context.state);
            }
        }

        /* Check for release timeout */
        if (entry->context.state == AUTHORITY_RELEASING) {
            uint64_t elapsed = now_ms - entry->context.request_time_ms;
            if (elapsed > manager->config.handoff_timeout_ms) {
                LOG_WARN("Authority release timeout for %s, forcing release",
                         entry->station_name);

                authority_state_t old_state = entry->context.state;
                entry->context.state = AUTHORITY_AUTONOMOUS;
                entry->context.epoch++;

                notify_state_change(manager, entry->station_name,
                                   old_state, entry->context.state);
            }
        }
    }

    pthread_mutex_unlock(&manager->lock);
    return WTC_OK;
}

wtc_result_t authority_force_release(authority_manager_t *manager,
                                      const char *station_name) {
    if (!manager || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    authority_entry_t *entry = find_entry(manager, station_name);
    if (!entry) {
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    authority_state_t old_state = entry->context.state;

    /* Force transition to AUTONOMOUS */
    entry->context.state = AUTHORITY_AUTONOMOUS;
    entry->context.epoch++;
    entry->context.controller_online = false;
    strncpy(entry->context.holder, station_name,
            sizeof(entry->context.holder) - 1);

    LOG_WARN("Forced authority release for %s (new epoch=%u)",
             station_name, entry->context.epoch);

    notify_state_change(manager, station_name, old_state, entry->context.state);

    pthread_mutex_unlock(&manager->lock);
    return WTC_OK;
}

void authority_context_init(authority_context_t *ctx) {
    if (!ctx) return;

    memset(ctx, 0, sizeof(*ctx));
    ctx->epoch = 1;  /* Start at epoch 1 */
    ctx->state = AUTHORITY_AUTONOMOUS;
    ctx->stale_command_threshold_ms = DEFAULT_STALE_COMMAND_MS;
}

const char *authority_state_to_string(authority_state_t state) {
    switch (state) {
        case AUTHORITY_AUTONOMOUS:      return "AUTONOMOUS";
        case AUTHORITY_HANDOFF_PENDING: return "HANDOFF_PENDING";
        case AUTHORITY_SUPERVISED:      return "SUPERVISED";
        case AUTHORITY_RELEASING:       return "RELEASING";
        default:                        return "UNKNOWN";
    }
}
