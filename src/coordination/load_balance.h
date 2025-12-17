/*
 * Water Treatment Controller - Load Balancing
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_LOAD_BALANCE_H
#define WTC_LOAD_BALANCE_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Load balancer handle */
typedef struct load_balancer load_balancer_t;

/* Load balance configuration */
typedef struct {
    int max_groups;
    uint32_t rebalance_interval_ms;
} load_balance_config_t;

/* Load balance group (e.g., pump group) */
typedef struct {
    int group_id;
    char name[WTC_MAX_NAME];
    bool enabled;

    /* Member RTUs/actuators */
    struct {
        char rtu_station[WTC_MAX_STATION_NAME];
        int slot;
        float capacity;         /* Max output capacity */
        float current_load;     /* Current load */
        uint64_t runtime_ms;    /* Total runtime for wear leveling */
        bool available;         /* Is this member available */
    } members[16];
    int member_count;

    /* Load balance settings */
    float total_demand;         /* Total demand to distribute */
    bool wear_leveling;         /* Enable runtime-based rotation */
    uint32_t rotation_interval_ms;  /* Time between rotations */

    /* Runtime state */
    uint64_t last_rotation_ms;
    int lead_member;            /* Currently leading member */
} load_balance_group_t;

/* Initialize load balancer */
wtc_result_t load_balance_init(load_balancer_t **lb, const load_balance_config_t *config);

/* Cleanup load balancer */
void load_balance_cleanup(load_balancer_t *lb);

/* Start load balancer */
wtc_result_t load_balance_start(load_balancer_t *lb);

/* Stop load balancer */
wtc_result_t load_balance_stop(load_balancer_t *lb);

/* Set RTU registry */
struct rtu_registry;
wtc_result_t load_balance_set_registry(load_balancer_t *lb, struct rtu_registry *registry);

/* Add load balance group */
wtc_result_t load_balance_add_group(load_balancer_t *lb, const load_balance_group_t *group);

/* Remove load balance group */
wtc_result_t load_balance_remove_group(load_balancer_t *lb, int group_id);

/* Set demand for a group */
wtc_result_t load_balance_set_demand(load_balancer_t *lb, int group_id, float demand);

/* Get group status */
wtc_result_t load_balance_get_group(load_balancer_t *lb, int group_id,
                                     load_balance_group_t *group);

/* Process load balancing */
wtc_result_t load_balance_process(load_balancer_t *lb);

/* Force rotation of lead equipment */
wtc_result_t load_balance_rotate(load_balancer_t *lb, int group_id);

#ifdef __cplusplus
}
#endif

#endif /* WTC_LOAD_BALANCE_H */
