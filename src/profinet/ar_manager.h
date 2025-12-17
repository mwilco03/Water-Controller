/*
 * Water Treatment Controller - Application Relationship Manager
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_AR_MANAGER_H
#define WTC_AR_MANAGER_H

#include "profinet_controller.h"

#ifdef __cplusplus
extern "C" {
#endif

/* AR manager handle */
typedef struct ar_manager ar_manager_t;

/* AR configuration */
typedef struct {
    char station_name[64];
    uint8_t device_mac[6];
    uint32_t device_ip;
    uint16_t vendor_id;
    uint16_t device_id;

    /* IO configuration */
    slot_config_t slots[WTC_MAX_SLOTS];
    int slot_count;

    /* Timing */
    uint32_t cycle_time_us;
    uint16_t reduction_ratio;
    uint32_t watchdog_ms;

    /* Callbacks */
    void (*on_state_changed)(ar_state_t state, void *ctx);
    void (*on_alarm)(uint16_t alarm_type, uint32_t api, uint16_t slot,
                    uint16_t subslot, void *ctx);
    void *callback_ctx;
} ar_config_t;

/* Initialize AR manager */
wtc_result_t ar_manager_init(ar_manager_t **manager,
                              int socket_fd,
                              const uint8_t *controller_mac);

/* Cleanup AR manager */
void ar_manager_cleanup(ar_manager_t *manager);

/* Create new AR */
wtc_result_t ar_manager_create_ar(ar_manager_t *manager,
                                   const ar_config_t *config,
                                   profinet_ar_t **ar);

/* Delete AR */
wtc_result_t ar_manager_delete_ar(ar_manager_t *manager,
                                   const char *station_name);

/* Get AR by station name */
profinet_ar_t *ar_manager_get_ar(ar_manager_t *manager,
                                  const char *station_name);

/* Get AR by frame ID */
profinet_ar_t *ar_manager_get_ar_by_frame_id(ar_manager_t *manager,
                                              uint16_t frame_id);

/* Process AR state machine */
wtc_result_t ar_manager_process(ar_manager_t *manager);

/* Send connect request */
wtc_result_t ar_send_connect_request(ar_manager_t *manager,
                                      profinet_ar_t *ar);

/* Send parameter end */
wtc_result_t ar_send_parameter_end(ar_manager_t *manager,
                                    profinet_ar_t *ar);

/* Send application ready */
wtc_result_t ar_send_application_ready(ar_manager_t *manager,
                                        profinet_ar_t *ar);

/* Send release request */
wtc_result_t ar_send_release_request(ar_manager_t *manager,
                                      profinet_ar_t *ar);

/* Handle received RPC frame */
wtc_result_t ar_handle_rpc(ar_manager_t *manager,
                            const uint8_t *frame,
                            size_t len);

/* Handle received RT frame */
wtc_result_t ar_handle_rt_frame(ar_manager_t *manager,
                                 const uint8_t *frame,
                                 size_t len);

/* Send cyclic output data */
wtc_result_t ar_send_output_data(ar_manager_t *manager,
                                  profinet_ar_t *ar);

/* Get list of all ARs */
wtc_result_t ar_manager_get_all(ar_manager_t *manager,
                                 profinet_ar_t **ars,
                                 int *count,
                                 int max_count);

/* Check AR health (watchdog) */
wtc_result_t ar_manager_check_health(ar_manager_t *manager);

#ifdef __cplusplus
}
#endif

#endif /* WTC_AR_MANAGER_H */
