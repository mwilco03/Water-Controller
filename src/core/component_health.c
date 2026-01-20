/*
 * Water Treatment Controller - Component Health Monitoring Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "component_health.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>

/* Default configuration */
#define DEFAULT_FAILURE_THRESHOLD    3
#define DEFAULT_RECOVERY_TIMEOUT_MS  30000
#define HEALTH_CHECK_INTERVAL_MS     5000

/* Component entry with health check function */
typedef struct {
    component_health_t info;
    health_check_fn check_fn;
    void *component_ptr;
} component_entry_t;

/* Health monitor structure */
struct health_monitor {
    component_entry_t components[COMPONENT_COUNT];
    uint64_t start_time_ms;
    uint64_t last_check_ms;
    pthread_mutex_t lock;
};

/* Component names */
static const char *component_names[COMPONENT_COUNT] = {
    [COMPONENT_PROFINET] = "PROFINET",
    [COMPONENT_REGISTRY] = "Registry",
    [COMPONENT_CONTROL_ENGINE] = "ControlEngine",
    [COMPONENT_ALARM_MANAGER] = "AlarmManager",
    [COMPONENT_HISTORIAN] = "Historian",
    [COMPONENT_IPC_SERVER] = "IPCServer",
    [COMPONENT_DATABASE] = "Database",
    [COMPONENT_MODBUS] = "Modbus",
    [COMPONENT_FAILOVER] = "Failover",
};

/* Public API */

wtc_result_t health_monitor_init(health_monitor_t **monitor) {
    if (!monitor) {
        return WTC_ERROR_INVALID_PARAM;
    }

    health_monitor_t *hm = calloc(1, sizeof(health_monitor_t));
    if (!hm) {
        return WTC_ERROR_NO_MEMORY;
    }

    hm->start_time_ms = time_get_ms();
    pthread_mutex_init(&hm->lock, NULL);

    /* Initialize all components with defaults */
    for (int i = 0; i < COMPONENT_COUNT; i++) {
        component_entry_t *entry = &hm->components[i];
        entry->info.id = (component_id_t)i;
        entry->info.name = component_names[i];
        entry->info.health = HEALTH_UNKNOWN;
        entry->info.circuit = CIRCUIT_CLOSED;
        entry->info.failure_threshold = DEFAULT_FAILURE_THRESHOLD;
        entry->info.recovery_timeout_ms = DEFAULT_RECOVERY_TIMEOUT_MS;
        entry->info.critical = false;
        entry->info.initialized = false;
    }

    /* Mark critical components */
    hm->components[COMPONENT_PROFINET].info.critical = true;
    hm->components[COMPONENT_REGISTRY].info.critical = true;
    hm->components[COMPONENT_CONTROL_ENGINE].info.critical = true;
    hm->components[COMPONENT_ALARM_MANAGER].info.critical = true;

    *monitor = hm;
    LOG_INFO("Health monitor initialized");

    return WTC_OK;
}

void health_monitor_cleanup(health_monitor_t *monitor) {
    if (!monitor) return;

    pthread_mutex_destroy(&monitor->lock);
    free(monitor);
    LOG_DEBUG("Health monitor cleaned up");
}

wtc_result_t health_register_component(health_monitor_t *monitor,
                                        component_id_t id,
                                        const char *name,
                                        bool critical,
                                        uint32_t failure_threshold,
                                        uint32_t recovery_timeout_ms) {
    if (!monitor || id >= COMPONENT_COUNT) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&monitor->lock);

    component_entry_t *entry = &monitor->components[id];
    if (name) {
        entry->info.name = name;
    }
    entry->info.critical = critical;
    entry->info.failure_threshold = failure_threshold > 0 ? failure_threshold : DEFAULT_FAILURE_THRESHOLD;
    entry->info.recovery_timeout_ms = recovery_timeout_ms > 0 ? recovery_timeout_ms : DEFAULT_RECOVERY_TIMEOUT_MS;

    LOG_DEBUG("Registered component %s (critical=%s, threshold=%u)",
              entry->info.name, critical ? "true" : "false", entry->info.failure_threshold);

    pthread_mutex_unlock(&monitor->lock);
    return WTC_OK;
}

wtc_result_t health_set_check_fn(health_monitor_t *monitor,
                                  component_id_t id,
                                  health_check_fn fn,
                                  void *component) {
    if (!monitor || id >= COMPONENT_COUNT) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&monitor->lock);

    monitor->components[id].check_fn = fn;
    monitor->components[id].component_ptr = component;

    pthread_mutex_unlock(&monitor->lock);
    return WTC_OK;
}

void health_report_success(health_monitor_t *monitor, component_id_t id) {
    if (!monitor || id >= COMPONENT_COUNT) return;

    pthread_mutex_lock(&monitor->lock);

    component_health_t *info = &monitor->components[id].info;
    info->success_count++;
    info->consecutive_failures = 0;
    info->last_success_ms = time_get_ms();

    /* Update health state */
    if (info->health == HEALTH_UNHEALTHY || info->health == HEALTH_UNKNOWN) {
        info->health = HEALTH_HEALTHY;
        LOG_INFO("Component %s recovered to HEALTHY", info->name);
    }

    /* Handle circuit breaker */
    if (info->circuit == CIRCUIT_HALF_OPEN) {
        info->circuit = CIRCUIT_CLOSED;
        LOG_INFO("Circuit breaker for %s closed (recovered)", info->name);
    }

    pthread_mutex_unlock(&monitor->lock);
}

void health_report_failure(health_monitor_t *monitor,
                            component_id_t id,
                            wtc_result_t result,
                            const char *error_msg) {
    if (!monitor || id >= COMPONENT_COUNT) return;

    pthread_mutex_lock(&monitor->lock);

    component_health_t *info = &monitor->components[id].info;
    info->failure_count++;
    info->consecutive_failures++;
    info->last_failure_ms = time_get_ms();
    info->last_result = result;

    if (error_msg) {
        snprintf(info->last_error, sizeof(info->last_error), "%s", error_msg);
    }

    /* Update health state based on consecutive failures */
    if (info->consecutive_failures >= info->failure_threshold) {
        if (info->health != HEALTH_FAILED) {
            info->health = HEALTH_UNHEALTHY;
            LOG_WARN("Component %s is UNHEALTHY (%u consecutive failures)",
                     info->name, info->consecutive_failures);

            /* Open circuit breaker */
            if (info->circuit == CIRCUIT_CLOSED) {
                info->circuit = CIRCUIT_OPEN;
                LOG_WARN("Circuit breaker for %s opened", info->name);
            }
        }
    } else {
        if (info->health == HEALTH_HEALTHY) {
            info->health = HEALTH_DEGRADED;
            LOG_DEBUG("Component %s degraded after failure", info->name);
        }
    }

    pthread_mutex_unlock(&monitor->lock);
}

void health_set_state(health_monitor_t *monitor,
                       component_id_t id,
                       health_state_t state) {
    if (!monitor || id >= COMPONENT_COUNT) return;

    pthread_mutex_lock(&monitor->lock);

    component_health_t *info = &monitor->components[id].info;
    health_state_t old_state = info->health;
    info->health = state;

    if (old_state != state) {
        LOG_INFO("Component %s health changed: %s -> %s",
                 info->name, health_state_name(old_state), health_state_name(state));
    }

    pthread_mutex_unlock(&monitor->lock);
}

void health_mark_initialized(health_monitor_t *monitor, component_id_t id) {
    if (!monitor || id >= COMPONENT_COUNT) return;

    pthread_mutex_lock(&monitor->lock);

    component_health_t *info = &monitor->components[id].info;
    info->initialized = true;
    if (info->health == HEALTH_UNKNOWN) {
        info->health = HEALTH_HEALTHY;
    }

    LOG_DEBUG("Component %s marked as initialized", info->name);

    pthread_mutex_unlock(&monitor->lock);
}

bool health_circuit_allow(health_monitor_t *monitor, component_id_t id) {
    if (!monitor || id >= COMPONENT_COUNT) return false;

    pthread_mutex_lock(&monitor->lock);

    component_health_t *info = &monitor->components[id].info;
    uint64_t now_ms = time_get_ms();
    bool allow = false;

    switch (info->circuit) {
        case CIRCUIT_CLOSED:
            allow = true;
            break;

        case CIRCUIT_OPEN:
            /* Check if recovery timeout has passed */
            if (now_ms - info->last_failure_ms >= info->recovery_timeout_ms) {
                info->circuit = CIRCUIT_HALF_OPEN;
                allow = true;  /* Allow one test call */
                LOG_DEBUG("Circuit breaker for %s half-open, testing recovery", info->name);
            }
            break;

        case CIRCUIT_HALF_OPEN:
            /* Only allow one call while half-open */
            allow = false;
            break;
    }

    pthread_mutex_unlock(&monitor->lock);
    return allow;
}

circuit_state_t health_get_circuit(health_monitor_t *monitor, component_id_t id) {
    if (!monitor || id >= COMPONENT_COUNT) return CIRCUIT_OPEN;

    pthread_mutex_lock(&monitor->lock);
    circuit_state_t state = monitor->components[id].info.circuit;
    pthread_mutex_unlock(&monitor->lock);

    return state;
}

void health_circuit_reset(health_monitor_t *monitor, component_id_t id) {
    if (!monitor || id >= COMPONENT_COUNT) return;

    pthread_mutex_lock(&monitor->lock);

    component_health_t *info = &monitor->components[id].info;
    info->circuit = CIRCUIT_CLOSED;
    info->consecutive_failures = 0;
    LOG_INFO("Circuit breaker for %s manually reset", info->name);

    pthread_mutex_unlock(&monitor->lock);
}

wtc_result_t health_get_component(health_monitor_t *monitor,
                                   component_id_t id,
                                   component_health_t *health) {
    if (!monitor || id >= COMPONENT_COUNT || !health) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&monitor->lock);
    memcpy(health, &monitor->components[id].info, sizeof(*health));
    pthread_mutex_unlock(&monitor->lock);

    return WTC_OK;
}

wtc_result_t health_get_system(health_monitor_t *monitor,
                                system_health_t *health) {
    if (!monitor || !health) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memset(health, 0, sizeof(*health));

    pthread_mutex_lock(&monitor->lock);

    uint64_t now_ms = time_get_ms();
    health->uptime_seconds = (uint32_t)((now_ms - monitor->start_time_ms) / 1000);
    health->overall = HEALTH_HEALTHY;
    health->can_control = true;
    health->can_observe = true;

    for (int i = 0; i < COMPONENT_COUNT; i++) {
        component_health_t *info = &monitor->components[i].info;

        if (!info->initialized) continue;

        switch (info->health) {
            case HEALTH_HEALTHY:
                health->healthy_count++;
                break;
            case HEALTH_DEGRADED:
                health->degraded_count++;
                if (health->overall == HEALTH_HEALTHY) {
                    health->overall = HEALTH_DEGRADED;
                }
                break;
            case HEALTH_UNHEALTHY:
                health->unhealthy_count++;
                if (info->critical) {
                    health->can_control = false;
                }
                if (health->overall < HEALTH_UNHEALTHY) {
                    health->overall = HEALTH_UNHEALTHY;
                }
                break;
            case HEALTH_FAILED:
                health->failed_count++;
                if (info->critical) {
                    health->can_control = false;
                    health->can_observe = false;
                }
                health->overall = HEALTH_FAILED;
                break;
            default:
                break;
        }
    }

    /* Build summary message */
    snprintf(health->message, sizeof(health->message),
             "Health: %s | Healthy: %d, Degraded: %d, Unhealthy: %d, Failed: %d | "
             "Control: %s, Observe: %s",
             health_state_name(health->overall),
             health->healthy_count, health->degraded_count,
             health->unhealthy_count, health->failed_count,
             health->can_control ? "OK" : "BLOCKED",
             health->can_observe ? "OK" : "BLOCKED");

    pthread_mutex_unlock(&monitor->lock);
    return WTC_OK;
}

bool health_can_control(health_monitor_t *monitor) {
    if (!monitor) return false;

    system_health_t health;
    health_get_system(monitor, &health);
    return health.can_control;
}

bool health_can_observe(health_monitor_t *monitor) {
    if (!monitor) return false;

    system_health_t health;
    health_get_system(monitor, &health);
    return health.can_observe;
}

wtc_result_t health_monitor_process(health_monitor_t *monitor, uint64_t now_ms) {
    if (!monitor) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Only check at intervals */
    if (now_ms - monitor->last_check_ms < HEALTH_CHECK_INTERVAL_MS) {
        return WTC_OK;
    }

    pthread_mutex_lock(&monitor->lock);
    monitor->last_check_ms = now_ms;

    for (int i = 0; i < COMPONENT_COUNT; i++) {
        component_entry_t *entry = &monitor->components[i];

        if (!entry->info.initialized || !entry->check_fn) continue;

        /* Run health check */
        char error_msg[128] = {0};
        health_state_t new_state = entry->check_fn(entry->component_ptr,
                                                     error_msg, sizeof(error_msg));

        entry->info.last_check_ms = now_ms;

        /* Update state if changed */
        if (new_state != entry->info.health) {
            LOG_INFO("Component %s health changed: %s -> %s%s%s",
                     entry->info.name,
                     health_state_name(entry->info.health),
                     health_state_name(new_state),
                     error_msg[0] ? " (" : "",
                     error_msg[0] ? error_msg : "");

            entry->info.health = new_state;

            if (error_msg[0]) {
                snprintf(entry->info.last_error, sizeof(entry->info.last_error),
                         "%s", error_msg);
            }
        }
    }

    pthread_mutex_unlock(&monitor->lock);
    return WTC_OK;
}

const char *health_component_name(component_id_t id) {
    if (id >= COMPONENT_COUNT) return "Unknown";
    return component_names[id];
}

const char *health_state_name(health_state_t state) {
    switch (state) {
        case HEALTH_UNKNOWN:   return "UNKNOWN";
        case HEALTH_HEALTHY:   return "HEALTHY";
        case HEALTH_DEGRADED:  return "DEGRADED";
        case HEALTH_UNHEALTHY: return "UNHEALTHY";
        case HEALTH_FAILED:    return "FAILED";
        default:               return "INVALID";
    }
}

const char *health_circuit_name(circuit_state_t state) {
    switch (state) {
        case CIRCUIT_CLOSED:    return "CLOSED";
        case CIRCUIT_OPEN:      return "OPEN";
        case CIRCUIT_HALF_OPEN: return "HALF_OPEN";
        default:                return "INVALID";
    }
}
