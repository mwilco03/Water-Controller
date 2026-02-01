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

/* AR state change callback - called when AR transitions states */
typedef void (*ar_state_change_callback_t)(const char *station_name,
                                            ar_state_t old_state,
                                            ar_state_t new_state,
                                            void *ctx);

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

/* Initialize AR manager.
 * vendor_id/device_id are used to build the CMInitiatorObjectUUID
 * (DEA00000-6C97-11D1-8271-{instance}{device}{vendor}) per IEC 61158-6-10. */
wtc_result_t ar_manager_init(ar_manager_t **manager,
                              int socket_fd,
                              const uint8_t *controller_mac,
                              uint16_t vendor_id,
                              uint16_t device_id);

/* Set controller IP address (required for RPC) */
void ar_manager_set_controller_ip(ar_manager_t *manager, uint32_t ip);

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

/* Set callback for AR state changes */
void ar_manager_set_state_callback(ar_manager_t *manager,
                                    ar_state_change_callback_t callback,
                                    void *ctx);

/* ============== Phase 2-4: Discovery Pipeline ============== */

/* Maximum discovered modules from RealIdentificationData 0xF844 */
#define AR_MAX_DISCOVERED_MODULES  64

/* Module discovered via Record Read 0xF844 */
typedef struct {
    uint16_t slot;
    uint16_t subslot;
    uint32_t module_ident;
    uint32_t submodule_ident;
} ar_discovered_module_t;

/* Module discovery result (Phase 3 output) */
typedef struct {
    ar_discovered_module_t modules[AR_MAX_DISCOVERED_MODULES];
    int module_count;
    bool from_cache;  /* true if loaded from GSDML cache */
} ar_module_discovery_t;

/**
 * @brief Phase 2: DAP-only connect.
 *
 * Establishes a minimal AR with only DAP (slot 0) submodules:
 *   Subslot 0x0001 (DAP identity)
 *   Subslot 0x8000 (Interface)
 *   Subslot 0x8001 (Port)
 *
 * This AR is used for Record Read operations to discover
 * actual plugged modules before the full connect.
 *
 * @param[in]  manager  AR manager
 * @param[in]  ar       AR with device info populated
 * @return WTC_OK on success
 */
wtc_result_t ar_send_dap_connect_request(ar_manager_t *manager,
                                          profinet_ar_t *ar);

/**
 * @brief Phase 3: Read RealIdentificationData from device.
 *
 * Sends Record Read (index 0xF844) to discover actual plugged modules.
 * Must be called after a successful DAP-only connect (Phase 2).
 *
 * @param[in]  manager    AR manager
 * @param[in]  ar         Active AR (from Phase 2)
 * @param[out] discovery  Discovered modules
 * @return WTC_OK on success
 */
wtc_result_t ar_read_real_identification(ar_manager_t *manager,
                                          profinet_ar_t *ar,
                                          ar_module_discovery_t *discovery);

/**
 * @brief Phases 2-4 orchestrator: discover modules and full connect.
 *
 * Executes the complete discovery pipeline:
 * 1. DAP-only connect (Phase 2)
 * 2. Record Read 0xF844 for module discovery (Phase 3)
 * 3. Release DAP-only AR
 * 4. Full connect with discovered modules (Phase 4)
 *
 * If GSDML cache is available (Phase 5), phases 2-3 are skipped.
 *
 * @param[in]  manager  AR manager
 * @param[in]  ar       AR with device info populated (station_name, IP, MAC)
 * @return WTC_OK on success, error if any phase fails
 */
wtc_result_t ar_connect_with_discovery(ar_manager_t *manager,
                                        profinet_ar_t *ar);

/**
 * @brief Build connect params using discovered modules.
 *
 * Converts ar_module_discovery_t into a connect_request_params_t
 * suitable for full connect (Phase 4).
 *
 * @param[in]  manager    AR manager
 * @param[in]  ar         AR handle
 * @param[in]  discovery  Discovered module layout
 * @return WTC_OK on success
 */
wtc_result_t ar_build_full_connect_params(ar_manager_t *manager,
                                           profinet_ar_t *ar,
                                           const ar_module_discovery_t *discovery);

#ifdef __cplusplus
}
#endif

#endif /* WTC_AR_MANAGER_H */
