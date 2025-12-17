/*
 * Water Treatment Controller - Multi-RTU Coordination
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_COORDINATION_H
#define WTC_COORDINATION_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Coordination manager handle */
typedef struct coordination_manager coordination_manager_t;

/* Coordination configuration */
typedef struct {
    failover_mode_t failover_mode;
    uint32_t heartbeat_interval_ms;
    uint32_t failover_timeout_ms;
    bool enable_load_balancing;
    bool enable_cascade_control;
} coordination_config_t;

/* Initialize coordination manager */
wtc_result_t coordination_init(coordination_manager_t **mgr,
                                const coordination_config_t *config);

/* Cleanup coordination manager */
void coordination_cleanup(coordination_manager_t *mgr);

/* Start coordination */
wtc_result_t coordination_start(coordination_manager_t *mgr);

/* Stop coordination */
wtc_result_t coordination_stop(coordination_manager_t *mgr);

/* Set RTU registry */
struct rtu_registry;
wtc_result_t coordination_set_registry(coordination_manager_t *mgr,
                                        struct rtu_registry *registry);

/* Set control engine */
struct control_engine;
wtc_result_t coordination_set_control_engine(coordination_manager_t *mgr,
                                              struct control_engine *engine);

/* Process coordination logic */
wtc_result_t coordination_process(coordination_manager_t *mgr);

/* Get coordination status */
typedef struct {
    bool active;
    int managed_rtus;
    int healthy_rtus;
    int failed_rtus;
    bool load_balancing_active;
    bool cascade_active;
    uint64_t last_failover_ms;
} coordination_status_t;

wtc_result_t coordination_get_status(coordination_manager_t *mgr,
                                      coordination_status_t *status);

#ifdef __cplusplus
}
#endif

#endif /* WTC_COORDINATION_H */
