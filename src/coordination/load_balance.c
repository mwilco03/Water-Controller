/*
 * Water Treatment Controller - Load Balancing Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "load_balance.h"
#include "rtu_registry.h"
#include "logger.h"
#include "time_utils.h"
#include <stdlib.h>
#include <string.h>

#define LOG_TAG "LOAD_BAL"

/* Load balancer structure */
struct load_balancer {
    load_balance_config_t config;
    load_balance_group_t *groups;
    int group_count;
    bool running;
    uint64_t last_process_ms;
    struct rtu_registry *registry;
};

/* Initialize load balancer */
wtc_result_t load_balance_init(load_balancer_t **lb, const load_balance_config_t *config) {
    if (!lb || !config) return WTC_ERROR_INVALID_PARAM;

    load_balancer_t *bal = calloc(1, sizeof(load_balancer_t));
    if (!bal) {
        return WTC_ERROR_NO_MEMORY;
    }

    memcpy(&bal->config, config, sizeof(load_balance_config_t));

    bal->groups = calloc(config->max_groups, sizeof(load_balance_group_t));
    if (!bal->groups) {
        free(bal);
        return WTC_ERROR_NO_MEMORY;
    }

    bal->group_count = 0;
    bal->running = false;

    LOG_INFO(LOG_TAG, "Load balancer initialized (max %d groups)", config->max_groups);
    *lb = bal;
    return WTC_OK;
}

/* Cleanup load balancer */
void load_balance_cleanup(load_balancer_t *lb) {
    if (!lb) return;
    free(lb->groups);
    free(lb);
    LOG_INFO(LOG_TAG, "Load balancer cleaned up");
}

/* Start load balancer */
wtc_result_t load_balance_start(load_balancer_t *lb) {
    if (!lb) return WTC_ERROR_INVALID_PARAM;
    lb->running = true;
    lb->last_process_ms = time_get_ms();
    LOG_INFO(LOG_TAG, "Load balancer started");
    return WTC_OK;
}

/* Stop load balancer */
wtc_result_t load_balance_stop(load_balancer_t *lb) {
    if (!lb) return WTC_ERROR_INVALID_PARAM;
    lb->running = false;
    LOG_INFO(LOG_TAG, "Load balancer stopped");
    return WTC_OK;
}

/* Set RTU registry */
wtc_result_t load_balance_set_registry(load_balancer_t *lb, struct rtu_registry *registry) {
    if (!lb) return WTC_ERROR_INVALID_PARAM;
    lb->registry = registry;
    return WTC_OK;
}

/* Add load balance group */
wtc_result_t load_balance_add_group(load_balancer_t *lb, const load_balance_group_t *group) {
    if (!lb || !group) return WTC_ERROR_INVALID_PARAM;

    /* Check for existing */
    for (int i = 0; i < lb->group_count; i++) {
        if (lb->groups[i].group_id == group->group_id) {
            memcpy(&lb->groups[i], group, sizeof(load_balance_group_t));
            LOG_DEBUG(LOG_TAG, "Updated group %d: %s", group->group_id, group->name);
            return WTC_OK;
        }
    }

    if (lb->group_count >= lb->config.max_groups) {
        return WTC_ERROR_FULL;
    }

    memcpy(&lb->groups[lb->group_count], group, sizeof(load_balance_group_t));
    lb->groups[lb->group_count].last_rotation_ms = time_get_ms();
    lb->group_count++;

    LOG_INFO(LOG_TAG, "Added load balance group %d: %s (%d members)",
             group->group_id, group->name, group->member_count);
    return WTC_OK;
}

/* Remove load balance group */
wtc_result_t load_balance_remove_group(load_balancer_t *lb, int group_id) {
    if (!lb) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < lb->group_count; i++) {
        if (lb->groups[i].group_id == group_id) {
            memmove(&lb->groups[i], &lb->groups[i + 1],
                    (lb->group_count - i - 1) * sizeof(load_balance_group_t));
            lb->group_count--;
            LOG_INFO(LOG_TAG, "Removed group %d", group_id);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Set demand for a group */
wtc_result_t load_balance_set_demand(load_balancer_t *lb, int group_id, float demand) {
    if (!lb) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < lb->group_count; i++) {
        if (lb->groups[i].group_id == group_id) {
            lb->groups[i].total_demand = demand;
            LOG_DEBUG(LOG_TAG, "Set demand for group %d: %.2f", group_id, demand);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Get group status */
wtc_result_t load_balance_get_group(load_balancer_t *lb, int group_id,
                                     load_balance_group_t *group) {
    if (!lb || !group) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < lb->group_count; i++) {
        if (lb->groups[i].group_id == group_id) {
            memcpy(group, &lb->groups[i], sizeof(load_balance_group_t));
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Find member with lowest runtime */
static int find_lowest_runtime_member(load_balance_group_t *group) {
    int lowest_idx = -1;
    uint64_t lowest_runtime = UINT64_MAX;

    for (int i = 0; i < group->member_count; i++) {
        if (group->members[i].available &&
            group->members[i].runtime_ms < lowest_runtime) {
            lowest_runtime = group->members[i].runtime_ms;
            lowest_idx = i;
        }
    }

    return lowest_idx;
}

/* Distribute load across group members */
static void distribute_load(load_balancer_t *lb, load_balance_group_t *group) {
    if (!lb->registry || group->member_count == 0) return;

    /* Calculate total available capacity */
    float total_capacity = 0;
    int available_count = 0;

    for (int i = 0; i < group->member_count; i++) {
        if (group->members[i].available) {
            total_capacity += group->members[i].capacity;
            available_count++;
        }
    }

    if (available_count == 0 || total_capacity <= 0) {
        LOG_WARN(LOG_TAG, "Group %d has no available capacity", group->group_id);
        return;
    }

    /* Distribute demand proportionally */
    float remaining_demand = group->total_demand;

    /* Start with lead member */
    int current = group->lead_member;
    for (int i = 0; i < group->member_count && remaining_demand > 0; i++) {
        if (!group->members[current].available) {
            current = (current + 1) % group->member_count;
            continue;
        }

        /* Calculate this member's share */
        float share = (group->members[current].capacity / total_capacity) *
                      group->total_demand;

        /* Clamp to capacity */
        if (share > group->members[current].capacity) {
            share = group->members[current].capacity;
        }

        group->members[current].current_load = share;
        remaining_demand -= share;

        /* Apply to actuator via registry */
        actuator_output_t output = {
            .command = share > 0 ? ACTUATOR_CMD_PWM : ACTUATOR_CMD_OFF,
            .pwm_duty = (uint8_t)((share / group->members[current].capacity) * 100),
            .reserved = {0, 0}
        };
        rtu_registry_update_actuator(lb->registry,
                                      group->members[current].rtu_station,
                                      group->members[current].slot,
                                      &output);

        current = (current + 1) % group->member_count;
    }
}

/* Force rotation of lead equipment */
wtc_result_t load_balance_rotate(load_balancer_t *lb, int group_id) {
    if (!lb) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < lb->group_count; i++) {
        if (lb->groups[i].group_id == group_id) {
            load_balance_group_t *group = &lb->groups[i];

            if (group->wear_leveling) {
                /* Find member with lowest runtime */
                int new_lead = find_lowest_runtime_member(group);
                if (new_lead >= 0 && new_lead != group->lead_member) {
                    group->lead_member = new_lead;
                    group->last_rotation_ms = time_get_ms();
                    LOG_INFO(LOG_TAG, "Rotated group %d lead to member %d",
                             group_id, new_lead);
                }
            } else {
                /* Simple round-robin */
                int new_lead = (group->lead_member + 1) % group->member_count;
                while (!group->members[new_lead].available &&
                       new_lead != group->lead_member) {
                    new_lead = (new_lead + 1) % group->member_count;
                }
                group->lead_member = new_lead;
                group->last_rotation_ms = time_get_ms();
                LOG_INFO(LOG_TAG, "Rotated group %d lead to member %d",
                         group_id, new_lead);
            }

            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Process load balancing */
wtc_result_t load_balance_process(load_balancer_t *lb) {
    if (!lb || !lb->running) return WTC_ERROR_NOT_INITIALIZED;

    uint64_t now = time_get_ms();

    for (int i = 0; i < lb->group_count; i++) {
        load_balance_group_t *group = &lb->groups[i];

        if (!group->enabled) continue;

        /* Update member availability from registry */
        if (lb->registry) {
            for (int j = 0; j < group->member_count; j++) {
                rtu_device_t *rtu = rtu_registry_get_device(lb->registry,
                                                             group->members[j].rtu_station);
                if (rtu) {
                    group->members[j].available =
                        (rtu->connection_state == PROFINET_STATE_RUNNING);
                }
            }
        }

        /* Check for rotation */
        if (group->rotation_interval_ms > 0 &&
            (now - group->last_rotation_ms) >= group->rotation_interval_ms) {
            load_balance_rotate(lb, group->group_id);
        }

        /* Update runtime for active members */
        uint64_t dt = now - lb->last_process_ms;
        for (int j = 0; j < group->member_count; j++) {
            if (group->members[j].current_load > 0) {
                group->members[j].runtime_ms += dt;
            }
        }

        /* Distribute load */
        distribute_load(lb, group);
    }

    lb->last_process_ms = now;
    return WTC_OK;
}
