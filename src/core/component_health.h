/*
 * Water Treatment Controller - Component Health Monitoring
 * Provides fault isolation and health tracking for controller components
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * This module implements:
 * - Component health tracking
 * - Circuit breakers for fault isolation
 * - Graceful degradation support
 * - Health status reporting
 */

#ifndef WTC_COMPONENT_HEALTH_H
#define WTC_COMPONENT_HEALTH_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Controller components */
typedef enum {
    COMPONENT_PROFINET = 0,      /* PROFINET IO Controller */
    COMPONENT_REGISTRY,          /* RTU Registry */
    COMPONENT_CONTROL_ENGINE,    /* PID Control Engine */
    COMPONENT_ALARM_MANAGER,     /* Alarm Manager */
    COMPONENT_HISTORIAN,         /* Data Historian */
    COMPONENT_IPC_SERVER,        /* IPC Shared Memory Server */
    COMPONENT_DATABASE,          /* Database Connection */
    COMPONENT_MODBUS,            /* Modbus Gateway */
    COMPONENT_FAILOVER,          /* Failover Manager */
    COMPONENT_COUNT              /* Number of components */
} component_id_t;

/* Component health state */
typedef enum {
    HEALTH_UNKNOWN = 0,          /* Health not yet determined */
    HEALTH_HEALTHY,              /* Component operating normally */
    HEALTH_DEGRADED,             /* Operating with reduced capability */
    HEALTH_UNHEALTHY,            /* Not operating, but recoverable */
    HEALTH_FAILED,               /* Failed, requires intervention */
} health_state_t;

/* Circuit breaker state */
typedef enum {
    CIRCUIT_CLOSED = 0,          /* Normal operation */
    CIRCUIT_OPEN,                /* Blocking calls due to failures */
    CIRCUIT_HALF_OPEN,           /* Testing if component recovered */
} circuit_state_t;

/* Component health info */
typedef struct {
    component_id_t id;           /* Component identifier */
    const char *name;            /* Component name */
    health_state_t health;       /* Current health state */
    circuit_state_t circuit;     /* Circuit breaker state */

    /* Statistics */
    uint32_t success_count;      /* Successful operations */
    uint32_t failure_count;      /* Failed operations */
    uint32_t consecutive_failures; /* Consecutive failures */
    uint64_t last_success_ms;    /* Time of last success */
    uint64_t last_failure_ms;    /* Time of last failure */
    uint64_t last_check_ms;      /* Time of last health check */

    /* Configuration */
    uint32_t failure_threshold;  /* Failures before circuit opens */
    uint32_t recovery_timeout_ms; /* Time before trying again */
    bool critical;               /* Is this component critical? */
    bool initialized;            /* Has component been initialized? */

    /* Error info */
    char last_error[128];        /* Last error message */
    wtc_result_t last_result;    /* Last operation result */
} component_health_t;

/* System health summary */
typedef struct {
    health_state_t overall;      /* Overall system health */
    int healthy_count;           /* Number of healthy components */
    int degraded_count;          /* Number of degraded components */
    int unhealthy_count;         /* Number of unhealthy components */
    int failed_count;            /* Number of failed components */
    uint32_t uptime_seconds;     /* System uptime */
    bool can_control;            /* Can issue control commands */
    bool can_observe;            /* Can observe/monitor */
    char message[256];           /* Summary message */
} system_health_t;

/* Health monitor handle */
typedef struct health_monitor health_monitor_t;

/* Health check callback - called periodically for each component */
typedef health_state_t (*health_check_fn)(void *component, char *error_msg, size_t error_len);

/* Initialize health monitor */
wtc_result_t health_monitor_init(health_monitor_t **monitor);

/* Cleanup health monitor */
void health_monitor_cleanup(health_monitor_t *monitor);

/* ============== Component Registration ============== */

/* Register a component for health monitoring */
wtc_result_t health_register_component(health_monitor_t *monitor,
                                        component_id_t id,
                                        const char *name,
                                        bool critical,
                                        uint32_t failure_threshold,
                                        uint32_t recovery_timeout_ms);

/* Set health check function for a component */
wtc_result_t health_set_check_fn(health_monitor_t *monitor,
                                  component_id_t id,
                                  health_check_fn fn,
                                  void *component);

/* ============== Health Reporting ============== */

/* Report operation success */
void health_report_success(health_monitor_t *monitor, component_id_t id);

/* Report operation failure */
void health_report_failure(health_monitor_t *monitor,
                            component_id_t id,
                            wtc_result_t result,
                            const char *error_msg);

/* Manually set component health state */
void health_set_state(health_monitor_t *monitor,
                       component_id_t id,
                       health_state_t state);

/* Mark component as initialized */
void health_mark_initialized(health_monitor_t *monitor, component_id_t id);

/* ============== Circuit Breaker ============== */

/* Check if operation should proceed (circuit is closed) */
bool health_circuit_allow(health_monitor_t *monitor, component_id_t id);

/* Get current circuit state */
circuit_state_t health_get_circuit(health_monitor_t *monitor, component_id_t id);

/* Manually reset circuit breaker */
void health_circuit_reset(health_monitor_t *monitor, component_id_t id);

/* ============== Health Queries ============== */

/* Get component health info */
wtc_result_t health_get_component(health_monitor_t *monitor,
                                   component_id_t id,
                                   component_health_t *health);

/* Get overall system health */
wtc_result_t health_get_system(health_monitor_t *monitor,
                                system_health_t *health);

/* Check if system can perform control operations */
bool health_can_control(health_monitor_t *monitor);

/* Check if system can perform observation operations */
bool health_can_observe(health_monitor_t *monitor);

/* ============== Processing ============== */

/* Process health checks (call from main loop) */
wtc_result_t health_monitor_process(health_monitor_t *monitor, uint64_t now_ms);

/* ============== Utilities ============== */

/* Get component name */
const char *health_component_name(component_id_t id);

/* Get health state name */
const char *health_state_name(health_state_t state);

/* Get circuit state name */
const char *health_circuit_name(circuit_state_t state);

#ifdef __cplusplus
}
#endif

#endif /* WTC_COMPONENT_HEALTH_H */
