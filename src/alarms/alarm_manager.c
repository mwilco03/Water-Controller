/*
 * Water Treatment Controller - Alarm Manager Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "alarm_manager.h"
#include "registry/rtu_registry.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <math.h>

/* Maximum alarms */
#define MAX_ACTIVE_ALARMS 256
#define MAX_HISTORY_ALARMS 10000
#define MAX_SUPPRESSIONS 64

/* Suppression entry */
typedef struct {
    char rtu_station[WTC_MAX_STATION_NAME];
    int slot;
    uint64_t end_time_ms;
    char reason[128];
    char user[WTC_MAX_USERNAME];
} suppression_t;

/* Alarm manager structure */
struct alarm_manager {
    alarm_manager_config_t config;
    rtu_registry_t *registry;

    /* Alarm rules */
    alarm_rule_t rules[WTC_MAX_ALARM_RULES];
    int rule_count;
    int next_rule_id;

    /* Active alarms */
    alarm_t active_alarms[MAX_ACTIVE_ALARMS];
    int active_count;
    int next_alarm_id;

    /* Alarm history */
    alarm_t *history;
    int history_count;
    int history_capacity;
    int history_write_pos;

    /* Suppressions */
    suppression_t suppressions[MAX_SUPPRESSIONS];
    int suppression_count;

    /* Alarm rate tracking */
    uint64_t alarm_timestamps[600]; /* Last 10 minutes */
    int alarm_timestamp_idx;

    /* Thread management */
    pthread_t process_thread;
    volatile bool running;
    pthread_mutex_t lock;

    /* Statistics */
    alarm_stats_t stats;
};

/* Find active alarm by rule ID */
static alarm_t *find_active_alarm_by_rule(alarm_manager_t *manager, int rule_id) {
    for (int i = 0; i < manager->active_count; i++) {
        if (manager->active_alarms[i].rule_id == rule_id) {
            return &manager->active_alarms[i];
        }
    }
    return NULL;
}

/* Add alarm to history */
static void add_to_history(alarm_manager_t *manager, const alarm_t *alarm) {
    if (!manager->history) return;

    memcpy(&manager->history[manager->history_write_pos],
           alarm, sizeof(alarm_t));

    manager->history_write_pos = (manager->history_write_pos + 1) % manager->history_capacity;
    if (manager->history_count < manager->history_capacity) {
        manager->history_count++;
    }
}

/* Track alarm rate */
static void track_alarm(alarm_manager_t *manager) {
    manager->alarm_timestamps[manager->alarm_timestamp_idx] = time_get_ms();
    manager->alarm_timestamp_idx = (manager->alarm_timestamp_idx + 1) % 600;
}

/* Process thread function */
static void *process_thread_func(void *arg) {
    alarm_manager_t *manager = (alarm_manager_t *)arg;

    LOG_DEBUG("Alarm manager thread started");

    while (manager->running) {
        pthread_mutex_lock(&manager->lock);
        alarm_manager_process(manager);
        pthread_mutex_unlock(&manager->lock);

        time_sleep_ms(100); /* 100ms scan rate */
    }

    LOG_DEBUG("Alarm manager thread stopped");
    return NULL;
}

/* Public functions */

wtc_result_t alarm_manager_init(alarm_manager_t **manager,
                                 const alarm_manager_config_t *config) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    alarm_manager_t *mgr = calloc(1, sizeof(alarm_manager_t));
    if (!mgr) {
        return WTC_ERROR_NO_MEMORY;
    }

    if (config) {
        memcpy(&mgr->config, config, sizeof(alarm_manager_config_t));
    }

    /* Set defaults */
    if (mgr->config.max_active_alarms == 0) {
        mgr->config.max_active_alarms = MAX_ACTIVE_ALARMS;
    }
    if (mgr->config.max_history_entries == 0) {
        mgr->config.max_history_entries = MAX_HISTORY_ALARMS;
    }
    if (mgr->config.max_alarms_per_10min == 0) {
        mgr->config.max_alarms_per_10min = 100; /* ISA-18.2 recommendation */
    }

    /* Allocate history buffer */
    mgr->history_capacity = mgr->config.max_history_entries;
    mgr->history = calloc(mgr->history_capacity, sizeof(alarm_t));
    if (!mgr->history) {
        free(mgr);
        return WTC_ERROR_NO_MEMORY;
    }

    mgr->next_rule_id = 1;
    mgr->next_alarm_id = 1;
    pthread_mutex_init(&mgr->lock, NULL);

    *manager = mgr;
    LOG_INFO("Alarm manager initialized");
    return WTC_OK;
}

void alarm_manager_cleanup(alarm_manager_t *manager) {
    if (!manager) return;

    alarm_manager_stop(manager);
    pthread_mutex_destroy(&manager->lock);
    free(manager->history);
    free(manager);

    LOG_INFO("Alarm manager cleaned up");
}

wtc_result_t alarm_manager_start(alarm_manager_t *manager) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (manager->running) {
        return WTC_OK;
    }

    manager->running = true;

    if (pthread_create(&manager->process_thread, NULL,
                       process_thread_func, manager) != 0) {
        LOG_ERROR("Failed to create alarm manager thread");
        manager->running = false;
        return WTC_ERROR;
    }

    LOG_INFO("Alarm manager started");
    return WTC_OK;
}

wtc_result_t alarm_manager_stop(alarm_manager_t *manager) {
    if (!manager || !manager->running) {
        return WTC_OK;
    }

    manager->running = false;
    pthread_join(manager->process_thread, NULL);

    LOG_INFO("Alarm manager stopped");
    return WTC_OK;
}

wtc_result_t alarm_manager_set_registry(alarm_manager_t *manager,
                                         struct rtu_registry *registry) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);
    manager->registry = registry;
    pthread_mutex_unlock(&manager->lock);

    return WTC_OK;
}

wtc_result_t alarm_manager_create_rule(alarm_manager_t *manager,
                                        const char *rtu_station,
                                        int slot,
                                        alarm_condition_t condition,
                                        float threshold,
                                        alarm_severity_t severity,
                                        uint32_t delay_ms,
                                        const char *message,
                                        int *rule_id) {
    if (!manager || !rtu_station) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    if (manager->rule_count >= WTC_MAX_ALARM_RULES) {
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_FULL;
    }

    alarm_rule_t *rule = &manager->rules[manager->rule_count++];
    memset(rule, 0, sizeof(alarm_rule_t));

    rule->rule_id = manager->next_rule_id++;
    strncpy(rule->rtu_station, rtu_station, WTC_MAX_STATION_NAME - 1);
    rule->slot = slot;
    rule->condition = condition;
    rule->threshold = threshold;
    rule->severity = severity;
    rule->delay_ms = delay_ms;
    rule->enabled = true;

    if (message) {
        strncpy(rule->message_template, message, WTC_MAX_MESSAGE - 1);
    } else {
        /* Generate default message */
        const char *cond_str = "";
        switch (condition) {
        case ALARM_CONDITION_HIGH: cond_str = "High"; break;
        case ALARM_CONDITION_LOW: cond_str = "Low"; break;
        case ALARM_CONDITION_HIGH_HIGH: cond_str = "High-High"; break;
        case ALARM_CONDITION_LOW_LOW: cond_str = "Low-Low"; break;
        case ALARM_CONDITION_RATE_OF_CHANGE: cond_str = "Rate of Change"; break;
        case ALARM_CONDITION_DEVIATION: cond_str = "Deviation"; break;
        case ALARM_CONDITION_BAD_QUALITY: cond_str = "Bad Quality"; break;
        }
        snprintf(rule->message_template, WTC_MAX_MESSAGE,
                 "%s alarm on %s slot %d", cond_str, rtu_station, slot);
    }

    snprintf(rule->name, WTC_MAX_NAME, "%s_%d_%d",
             rtu_station, slot, condition);

    if (rule_id) {
        *rule_id = rule->rule_id;
    }

    pthread_mutex_unlock(&manager->lock);

    LOG_INFO("Created alarm rule %d: %s (threshold=%.2f, severity=%d)",
             rule->rule_id, rule->name, threshold, severity);
    return WTC_OK;
}

wtc_result_t alarm_manager_delete_rule(alarm_manager_t *manager, int rule_id) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    for (int i = 0; i < manager->rule_count; i++) {
        if (manager->rules[i].rule_id == rule_id) {
            for (int j = i; j < manager->rule_count - 1; j++) {
                manager->rules[j] = manager->rules[j + 1];
            }
            manager->rule_count--;

            pthread_mutex_unlock(&manager->lock);
            LOG_INFO("Deleted alarm rule %d", rule_id);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&manager->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t alarm_manager_enable_rule(alarm_manager_t *manager,
                                        int rule_id, bool enabled) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    for (int i = 0; i < manager->rule_count; i++) {
        if (manager->rules[i].rule_id == rule_id) {
            manager->rules[i].enabled = enabled;
            pthread_mutex_unlock(&manager->lock);
            LOG_INFO("Alarm rule %d %s", rule_id, enabled ? "enabled" : "disabled");
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&manager->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t alarm_manager_acknowledge(alarm_manager_t *manager,
                                        int alarm_id, const char *user) {
    if (!manager || !user) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    for (int i = 0; i < manager->active_count; i++) {
        if (manager->active_alarms[i].alarm_id == alarm_id) {
            if (manager->active_alarms[i].state == ALARM_STATE_ACTIVE_UNACK) {
                manager->active_alarms[i].state = ALARM_STATE_ACTIVE_ACK;
            } else if (manager->active_alarms[i].state == ALARM_STATE_CLEARED_UNACK) {
                manager->active_alarms[i].state = ALARM_STATE_CLEARED;
            }

            manager->active_alarms[i].ack_time_ms = time_get_ms();
            strncpy(manager->active_alarms[i].ack_user, user, WTC_MAX_USERNAME - 1);

            /* Invoke callback */
            if (manager->config.on_alarm_acknowledged) {
                manager->config.on_alarm_acknowledged(&manager->active_alarms[i],
                                                       manager->config.callback_ctx);
            }

            pthread_mutex_unlock(&manager->lock);
            LOG_INFO("Alarm %d acknowledged by %s", alarm_id, user);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&manager->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t alarm_manager_acknowledge_all(alarm_manager_t *manager,
                                            const char *user) {
    if (!manager || !user) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    int acked = 0;
    for (int i = 0; i < manager->active_count; i++) {
        if (manager->active_alarms[i].state == ALARM_STATE_ACTIVE_UNACK ||
            manager->active_alarms[i].state == ALARM_STATE_CLEARED_UNACK) {
            if (manager->active_alarms[i].state == ALARM_STATE_ACTIVE_UNACK) {
                manager->active_alarms[i].state = ALARM_STATE_ACTIVE_ACK;
            } else {
                manager->active_alarms[i].state = ALARM_STATE_CLEARED;
            }
            manager->active_alarms[i].ack_time_ms = time_get_ms();
            strncpy(manager->active_alarms[i].ack_user, user, WTC_MAX_USERNAME - 1);
            acked++;
        }
    }

    pthread_mutex_unlock(&manager->lock);
    LOG_INFO("Acknowledged %d alarms by %s", acked, user);
    return WTC_OK;
}

wtc_result_t alarm_manager_get_active(alarm_manager_t *manager,
                                       alarm_t **alarms,
                                       int *count,
                                       int max_count) {
    if (!manager || !alarms || !count) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    int copy_count = manager->active_count;
    if (copy_count > max_count) {
        copy_count = max_count;
    }

    for (int i = 0; i < copy_count; i++) {
        alarms[i] = &manager->active_alarms[i];
    }
    *count = copy_count;

    pthread_mutex_unlock(&manager->lock);
    return WTC_OK;
}

int alarm_manager_get_active_count(alarm_manager_t *manager) {
    return manager ? manager->active_count : 0;
}

int alarm_manager_get_unack_count(alarm_manager_t *manager) {
    if (!manager) return 0;

    int count = 0;
    pthread_mutex_lock(&manager->lock);
    for (int i = 0; i < manager->active_count; i++) {
        if (manager->active_alarms[i].state == ALARM_STATE_ACTIVE_UNACK ||
            manager->active_alarms[i].state == ALARM_STATE_CLEARED_UNACK) {
            count++;
        }
    }
    pthread_mutex_unlock(&manager->lock);
    return count;
}

wtc_result_t alarm_manager_suppress(alarm_manager_t *manager,
                                     const char *rtu_station,
                                     int slot,
                                     uint32_t duration_ms,
                                     const char *reason,
                                     const char *user) {
    if (!manager || !rtu_station) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    if (manager->suppression_count >= MAX_SUPPRESSIONS) {
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_FULL;
    }

    suppression_t *sup = &manager->suppressions[manager->suppression_count++];
    strncpy(sup->rtu_station, rtu_station, WTC_MAX_STATION_NAME - 1);
    sup->slot = slot;
    sup->end_time_ms = time_get_ms() + duration_ms;
    if (reason) strncpy(sup->reason, reason, sizeof(sup->reason) - 1);
    if (user) strncpy(sup->user, user, WTC_MAX_USERNAME - 1);

    pthread_mutex_unlock(&manager->lock);

    LOG_WARN("Alarms suppressed for %s slot %d for %u ms by %s: %s",
             rtu_station, slot, duration_ms, user ? user : "unknown",
             reason ? reason : "no reason");
    return WTC_OK;
}

bool alarm_manager_is_suppressed(alarm_manager_t *manager,
                                  const char *rtu_station,
                                  int slot) {
    if (!manager || !rtu_station) return false;

    uint64_t now_ms = time_get_ms();

    pthread_mutex_lock(&manager->lock);

    for (int i = 0; i < manager->suppression_count; i++) {
        if (strcmp(manager->suppressions[i].rtu_station, rtu_station) == 0 &&
            manager->suppressions[i].slot == slot &&
            manager->suppressions[i].end_time_ms > now_ms) {
            pthread_mutex_unlock(&manager->lock);
            return true;
        }
    }

    pthread_mutex_unlock(&manager->lock);
    return false;
}

wtc_result_t alarm_manager_get_statistics(alarm_manager_t *manager,
                                           alarm_stats_t *stats) {
    if (!manager || !stats) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    stats->total_alarms = manager->stats.total_alarms;
    stats->active_alarms = manager->active_count;
    stats->unack_alarms = 0;

    for (int i = 0; i < manager->active_count; i++) {
        if (manager->active_alarms[i].state == ALARM_STATE_ACTIVE_UNACK) {
            stats->unack_alarms++;
        }
    }

    stats->alarms_per_hour = (uint32_t)(alarm_manager_get_alarm_rate(manager));

    pthread_mutex_unlock(&manager->lock);
    return WTC_OK;
}

float alarm_manager_get_alarm_rate(alarm_manager_t *manager) {
    if (!manager) return 0;

    uint64_t now_ms = time_get_ms();
    uint64_t ten_min_ago = now_ms - 600000;
    int count = 0;

    for (int i = 0; i < 600; i++) {
        if (manager->alarm_timestamps[i] > ten_min_ago) {
            count++;
        }
    }

    return count * 6.0f; /* Convert to per hour */
}

bool alarm_manager_is_alarm_flood(alarm_manager_t *manager) {
    if (!manager) return false;

    uint64_t now_ms = time_get_ms();
    uint64_t ten_min_ago = now_ms - 600000;
    int count = 0;

    for (int i = 0; i < 600; i++) {
        if (manager->alarm_timestamps[i] > ten_min_ago) {
            count++;
        }
    }

    return count > manager->config.max_alarms_per_10min;
}

wtc_result_t alarm_manager_process(alarm_manager_t *manager) {
    if (!manager || !manager->registry) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint64_t now_ms = time_get_ms();

    /* Process each rule */
    for (int i = 0; i < manager->rule_count; i++) {
        alarm_rule_t *rule = &manager->rules[i];
        if (!rule->enabled) continue;

        /* Check suppression */
        if (alarm_manager_is_suppressed(manager, rule->rtu_station, rule->slot)) {
            continue;
        }

        /* Read sensor value */
        sensor_data_t sensor;
        wtc_result_t res = rtu_registry_get_sensor(manager->registry,
                                                    rule->rtu_station,
                                                    rule->slot,
                                                    &sensor);

        bool condition_met = false;

        /* Check quality from 5-byte sensor format
         * Don't alarm on BAD/NOT_CONNECTED values except for BAD_QUALITY rules
         */
        bool quality_good = (res == WTC_OK &&
                             sensor.status == IOPS_GOOD &&
                             sensor.quality == QUALITY_GOOD);

        if (!quality_good) {
            /* Bad quality alarm - trigger only for BAD_QUALITY condition */
            if (rule->condition == ALARM_CONDITION_BAD_QUALITY) {
                condition_met = true;
            }
            /* Skip other alarms when quality is bad/uncertain/not_connected */
        } else {
            /* Evaluate condition only when quality is GOOD */
            switch (rule->condition) {
            case ALARM_CONDITION_HIGH:
            case ALARM_CONDITION_HIGH_HIGH:
                condition_met = sensor.value >= rule->threshold;
                break;
            case ALARM_CONDITION_LOW:
            case ALARM_CONDITION_LOW_LOW:
                condition_met = sensor.value <= rule->threshold;
                break;
            default:
                break;
            }
        }

        /* Check if alarm already active */
        alarm_t *existing = find_active_alarm_by_rule(manager, rule->rule_id);

        if (condition_met) {
            /* Handle delay */
            if (rule->condition_start_ms == 0) {
                rule->condition_start_ms = now_ms;
            } else if (!existing && now_ms - rule->condition_start_ms >= rule->delay_ms) {
                /* Raise alarm */
                if (manager->active_count < MAX_ACTIVE_ALARMS) {
                    alarm_t *alarm = &manager->active_alarms[manager->active_count++];
                    memset(alarm, 0, sizeof(alarm_t));

                    alarm->alarm_id = manager->next_alarm_id++;
                    alarm->rule_id = rule->rule_id;
                    strncpy(alarm->rtu_station, rule->rtu_station, WTC_MAX_STATION_NAME - 1);
                    alarm->slot = rule->slot;
                    alarm->severity = rule->severity;
                    alarm->state = ALARM_STATE_ACTIVE_UNACK;
                    alarm->value = sensor.value;
                    alarm->threshold = rule->threshold;
                    alarm->raise_time_ms = now_ms;

                    snprintf(alarm->message, WTC_MAX_MESSAGE, "%s (value=%.2f, threshold=%.2f)",
                             rule->message_template, sensor.value, rule->threshold);

                    rule->active = true;
                    manager->stats.total_alarms++;
                    track_alarm(manager);
                    add_to_history(manager, alarm);

                    LOG_WARN("ALARM RAISED [%d]: %s - %s",
                             alarm->alarm_id, rule->name, alarm->message);

                    if (manager->config.on_alarm_raised) {
                        manager->config.on_alarm_raised(alarm, manager->config.callback_ctx);
                    }
                }
            }
        } else {
            rule->condition_start_ms = 0;

            /* Clear alarm if active */
            if (existing && (existing->state == ALARM_STATE_ACTIVE_UNACK ||
                            existing->state == ALARM_STATE_ACTIVE_ACK)) {
                existing->clear_time_ms = now_ms;
                if (existing->state == ALARM_STATE_ACTIVE_ACK) {
                    existing->state = ALARM_STATE_CLEARED;
                } else {
                    existing->state = ALARM_STATE_CLEARED_UNACK;
                }

                rule->active = false;
                add_to_history(manager, existing);

                LOG_INFO("ALARM CLEARED [%d]: %s", existing->alarm_id, rule->name);

                if (manager->config.on_alarm_cleared) {
                    manager->config.on_alarm_cleared(existing, manager->config.callback_ctx);
                }
            }
        }
    }

    /* Remove fully cleared alarms from active list */
    for (int i = manager->active_count - 1; i >= 0; i--) {
        if (manager->active_alarms[i].state == ALARM_STATE_CLEARED) {
            for (int j = i; j < manager->active_count - 1; j++) {
                manager->active_alarms[j] = manager->active_alarms[j + 1];
            }
            manager->active_count--;
        }
    }

    /* Update statistics */
    manager->stats.active_alarms = manager->active_count;

    return WTC_OK;
}

wtc_result_t alarm_manager_raise_alarm(alarm_manager_t *manager,
                                        const char *rtu_station,
                                        int slot,
                                        alarm_severity_t severity,
                                        const char *message,
                                        float value) {
    if (!manager || !message) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    if (manager->active_count >= MAX_ACTIVE_ALARMS) {
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_FULL;
    }

    alarm_t *alarm = &manager->active_alarms[manager->active_count++];
    memset(alarm, 0, sizeof(alarm_t));

    alarm->alarm_id = manager->next_alarm_id++;
    alarm->rule_id = 0; /* External alarm, no rule */
    if (rtu_station) {
        strncpy(alarm->rtu_station, rtu_station, WTC_MAX_STATION_NAME - 1);
    }
    alarm->slot = slot;
    alarm->severity = severity;
    alarm->state = ALARM_STATE_ACTIVE_UNACK;
    alarm->value = value;
    alarm->raise_time_ms = time_get_ms();
    strncpy(alarm->message, message, WTC_MAX_MESSAGE - 1);

    manager->stats.total_alarms++;
    track_alarm(manager);
    add_to_history(manager, alarm);

    pthread_mutex_unlock(&manager->lock);

    LOG_WARN("ALARM RAISED (external) [%d]: %s", alarm->alarm_id, message);

    if (manager->config.on_alarm_raised) {
        manager->config.on_alarm_raised(alarm, manager->config.callback_ctx);
    }

    return WTC_OK;
}
