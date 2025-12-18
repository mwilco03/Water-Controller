/*
 * Water Treatment Controller - Multi-RTU Coordination Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "coordination.h"
#include "cascade_control.h"
#include "load_balance.h"
#include "failover.h"
#include "logger.h"
#include <stdlib.h>
#include <string.h>

#define LOG_TAG "COORDINATION"

/* Coordination manager structure */
struct coordination_manager {
    coordination_config_t config;
    bool running;

    struct rtu_registry *registry;
    struct control_engine *control;

    cascade_controller_t *cascade;
    load_balancer_t *load_balancer;
    failover_manager_t *failover;

    coordination_status_t status;
};

/* Initialize coordination manager */
wtc_result_t coordination_init(coordination_manager_t **mgr,
                                const coordination_config_t *config) {
    if (!mgr || !config) return WTC_ERROR_INVALID_PARAM;

    coordination_manager_t *cm = calloc(1, sizeof(coordination_manager_t));
    if (!cm) {
        return WTC_ERROR_NO_MEMORY;
    }

    memcpy(&cm->config, config, sizeof(coordination_config_t));
    cm->running = false;

    /* Initialize sub-components */
    if (config->enable_cascade_control) {
        cascade_config_t cascade_cfg = {
            .max_cascades = 32,
            .update_interval_ms = 100
        };
        if (cascade_init(&cm->cascade, &cascade_cfg) != WTC_OK) {
            LOG_WARN(LOG_TAG, "Failed to initialize cascade controller");
        }
    }

    if (config->enable_load_balancing) {
        load_balance_config_t lb_cfg = {
            .max_groups = 16,
            .rebalance_interval_ms = 5000
        };
        if (load_balance_init(&cm->load_balancer, &lb_cfg) != WTC_OK) {
            LOG_WARN(LOG_TAG, "Failed to initialize load balancer");
        }
    }

    failover_config_t fo_cfg = {
        .mode = config->failover_mode,
        .heartbeat_interval_ms = config->heartbeat_interval_ms,
        .timeout_ms = config->failover_timeout_ms
    };
    if (failover_init(&cm->failover, &fo_cfg) != WTC_OK) {
        LOG_WARN(LOG_TAG, "Failed to initialize failover manager");
    }

    LOG_INFO(LOG_TAG, "Coordination manager initialized");
    *mgr = cm;
    return WTC_OK;
}

/* Cleanup coordination manager */
void coordination_cleanup(coordination_manager_t *mgr) {
    if (!mgr) return;

    coordination_stop(mgr);

    if (mgr->cascade) cascade_cleanup(mgr->cascade);
    if (mgr->load_balancer) load_balance_cleanup(mgr->load_balancer);
    if (mgr->failover) failover_cleanup(mgr->failover);

    free(mgr);
    LOG_INFO(LOG_TAG, "Coordination manager cleaned up");
}

/* Start coordination */
wtc_result_t coordination_start(coordination_manager_t *mgr) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;

    if (mgr->running) return WTC_OK;

    if (mgr->cascade) cascade_start(mgr->cascade);
    if (mgr->load_balancer) load_balance_start(mgr->load_balancer);
    if (mgr->failover) failover_start(mgr->failover);

    mgr->running = true;
    mgr->status.active = true;

    LOG_INFO(LOG_TAG, "Coordination started");
    return WTC_OK;
}

/* Stop coordination */
wtc_result_t coordination_stop(coordination_manager_t *mgr) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;

    if (!mgr->running) return WTC_OK;

    if (mgr->cascade) cascade_stop(mgr->cascade);
    if (mgr->load_balancer) load_balance_stop(mgr->load_balancer);
    if (mgr->failover) failover_stop(mgr->failover);

    mgr->running = false;
    mgr->status.active = false;

    LOG_INFO(LOG_TAG, "Coordination stopped");
    return WTC_OK;
}

/* Set RTU registry */
wtc_result_t coordination_set_registry(coordination_manager_t *mgr,
                                        struct rtu_registry *registry) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;

    mgr->registry = registry;

    if (mgr->failover) failover_set_registry(mgr->failover, registry);
    if (mgr->load_balancer) load_balance_set_registry(mgr->load_balancer, registry);

    return WTC_OK;
}

/* Set control engine */
wtc_result_t coordination_set_control_engine(coordination_manager_t *mgr,
                                              struct control_engine *engine) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;

    mgr->control = engine;

    if (mgr->cascade) cascade_set_control_engine(mgr->cascade, engine);

    return WTC_OK;
}

/* Process coordination logic */
wtc_result_t coordination_process(coordination_manager_t *mgr) {
    if (!mgr || !mgr->running) return WTC_ERROR_NOT_INITIALIZED;

    /* Process failover */
    if (mgr->failover) {
        failover_process(mgr->failover);

        failover_status_t fo_status;
        if (failover_get_status(mgr->failover, &fo_status) == WTC_OK) {
            mgr->status.healthy_rtus = fo_status.healthy_count;
            mgr->status.failed_rtus = fo_status.failed_count;
            mgr->status.last_failover_ms = fo_status.last_failover_ms;
        }
    }

    /* Process load balancing */
    if (mgr->load_balancer) {
        load_balance_process(mgr->load_balancer);
        mgr->status.load_balancing_active = true;
    }

    /* Process cascade control */
    if (mgr->cascade) {
        cascade_process(mgr->cascade);
        mgr->status.cascade_active = true;
    }

    return WTC_OK;
}

/* Get coordination status */
wtc_result_t coordination_get_status(coordination_manager_t *mgr,
                                      coordination_status_t *status) {
    if (!mgr || !status) return WTC_ERROR_INVALID_PARAM;

    memcpy(status, &mgr->status, sizeof(coordination_status_t));
    return WTC_OK;
}
