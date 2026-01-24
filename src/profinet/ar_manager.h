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

/* Initialize AR manager */
wtc_result_t ar_manager_init(ar_manager_t **manager,
                              int socket_fd,
                              const uint8_t *controller_mac);

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

/* Set callback for AR state changes */
void ar_manager_set_state_callback(ar_manager_t *manager,
                                    ar_state_change_callback_t callback,
                                    void *ctx);

/* ============== Resilient Connection API ============== */

/**
 * @brief Connection strategy for resilient connect.
 *
 * Defines different approaches to try when connecting to a device.
 */
typedef enum {
    CONNECT_STRATEGY_STANDARD,       /* Standard connect with given name */
    CONNECT_STRATEGY_LOWERCASE,      /* Force lowercase station name */
    CONNECT_STRATEGY_UPPERCASE,      /* Force uppercase station name */
    CONNECT_STRATEGY_NO_DASH,        /* Remove dashes from station name */
    CONNECT_STRATEGY_MINIMAL_CONFIG, /* Minimal expected configuration */
    CONNECT_STRATEGY_REDISCOVER,     /* Re-run DCP discovery first */
    CONNECT_STRATEGY_COUNT
} connect_strategy_t;

/**
 * @brief Resilient connection options.
 */
typedef struct {
    int max_attempts;           /* Max total attempts (default: 5) */
    int base_delay_ms;          /* Base delay between attempts (default: 1000) */
    int max_delay_ms;           /* Max delay with backoff (default: 10000) */
    bool try_name_variations;   /* Try station name variations (default: true) */
    bool try_rediscovery;       /* Try DCP rediscovery on failure (default: true) */
    bool try_minimal_config;    /* Try minimal expected config (default: true) */
} resilient_connect_opts_t;

/**
 * @brief Default resilient connection options.
 */
#define RESILIENT_CONNECT_OPTS_DEFAULT { \
    .max_attempts = 5,                   \
    .base_delay_ms = 1000,               \
    .max_delay_ms = 10000,               \
    .try_name_variations = true,         \
    .try_rediscovery = true,             \
    .try_minimal_config = true           \
}

/**
 * @brief Attempt resilient connection with multiple strategies.
 *
 * Tries multiple connection strategies including:
 * - Station name variations (case, dashes)
 * - Different expected configurations
 * - DCP rediscovery
 * - Exponential backoff between attempts
 *
 * @param[in] manager    AR manager instance
 * @param[in] ar         AR to connect
 * @param[in] opts       Connection options (NULL for defaults)
 * @return WTC_OK on success, error code on failure after all attempts
 *
 * @note Thread safety: Acquires manager lock
 * @note Memory: NO_ALLOC
 */
wtc_result_t ar_connect_resilient(ar_manager_t *manager,
                                   profinet_ar_t *ar,
                                   const resilient_connect_opts_t *opts);

/**
 * @brief Generate station name variation.
 *
 * Generates different variations of a station name for connection attempts.
 * Format expected: rtu-XXXX where XXXX is last 4 hex digits of MAC.
 *
 * @param[in]  original   Original station name
 * @param[in]  strategy   Which variation to generate
 * @param[out] output     Buffer for output name
 * @param[in]  output_len Size of output buffer
 * @return true if variation was generated, false if not applicable
 *
 * @note Thread safety: SAFE
 * @note Memory: NO_ALLOC
 */
bool ar_generate_name_variation(const char *original,
                                 connect_strategy_t strategy,
                                 char *output,
                                 size_t output_len);

#ifdef __cplusplus
}
#endif

#endif /* WTC_AR_MANAGER_H */
