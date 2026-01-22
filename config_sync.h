/*
 * Water Treatment Controller - Configuration Sync
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Handles PROFINET acyclic synchronization of configuration
 * from Controller to RTUs. Triggered on AR_STATE_RUN.
 *
 * Wire protocol definitions are in shared/include/config_sync_protocol.h
 */

#ifndef WTC_CONFIG_SYNC_H
#define WTC_CONFIG_SYNC_H

#include "types.h"
#include "config_sync_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ============== Result Codes ============== */

typedef enum {
    CONFIG_SYNC_OK                      = 0,
    CONFIG_SYNC_ERROR_INVALID_PARAM     = -1,
    CONFIG_SYNC_ERROR_NO_MEMORY         = -2,
    CONFIG_SYNC_ERROR_SERIALIZE         = -3,
    CONFIG_SYNC_ERROR_SEND              = -4,
    CONFIG_SYNC_ERROR_TIMEOUT           = -5,
    CONFIG_SYNC_ERROR_RTU_NOT_CONNECTED = -6,
    CONFIG_SYNC_ERROR_RTU_NOT_APPROVED  = -7,
} config_sync_result_t;

/* ============== Configuration ============== */

typedef struct {
    bool sync_on_connect;           /* Sync when RTU connects (AR_STATE_RUN) */
    bool sync_enrollment;           /* Send enrollment packet */
    bool sync_device_config;        /* Send device config (0xF841) */
    bool sync_sensor_config;        /* Send sensor config (0xF842) */
    bool sync_actuator_config;      /* Send actuator config (0xF843) */
    uint32_t sync_timeout_ms;       /* Timeout for each write operation */
    uint32_t retry_count;           /* Number of retries on failure */
} config_sync_config_t;

/* Default configuration */
#define CONFIG_SYNC_DEFAULT_CONFIG { \
    .sync_on_connect = true, \
    .sync_enrollment = true, \
    .sync_device_config = true, \
    .sync_sensor_config = true, \
    .sync_actuator_config = true, \
    .sync_timeout_ms = 5000, \
    .retry_count = 2, \
}

/* ============== Sync Manager ============== */

typedef struct config_sync_manager config_sync_manager_t;

/* Callback for sync completion */
typedef void (*config_sync_callback_t)(const char *station_name,
                                        config_sync_result_t result,
                                        void *ctx);

/* Statistics */
typedef struct {
    uint32_t total_syncs;
    uint32_t successful_syncs;
    uint32_t failed_syncs;
    uint64_t last_sync_time_ms;
    char last_sync_rtu[WTC_MAX_STATION_NAME];
} config_sync_stats_t;

/* ============== Manager Lifecycle ============== */

/**
 * Initialize config sync manager.
 *
 * @param manager   Output: manager handle
 * @param config    Configuration (NULL for defaults)
 * @return WTC_OK on success
 */
wtc_result_t config_sync_manager_init(config_sync_manager_t **manager,
                                       const config_sync_config_t *config);

/**
 * Cleanup config sync manager.
 */
void config_sync_manager_cleanup(config_sync_manager_t *manager);

/**
 * Set PROFINET controller for sync operations.
 */
struct profinet_controller;
wtc_result_t config_sync_set_profinet(config_sync_manager_t *manager,
                                       struct profinet_controller *profinet);

/**
 * Set RTU registry for device/sensor/actuator info.
 */
struct rtu_registry;
wtc_result_t config_sync_set_registry(config_sync_manager_t *manager,
                                       struct rtu_registry *registry);

/**
 * Set callback for sync results.
 */
void config_sync_set_callback(config_sync_manager_t *manager,
                               config_sync_callback_t callback,
                               void *ctx);

/* ============== Sync Operations ============== */

/**
 * Sync all configuration to a specific RTU.
 * Called on AR_STATE_RUN transition.
 *
 * Sends packets in order:
 *   1. Enrollment (0xF845) - if sync_enrollment enabled
 *   2. Device config (0xF841) - if sync_device_config enabled
 *   3. Sensor config (0xF842) - if sync_sensor_config enabled
 *   4. Actuator config (0xF843) - if sync_actuator_config enabled
 *
 * @param manager       Sync manager
 * @param station_name  RTU station name
 * @return CONFIG_SYNC_OK on success
 */
config_sync_result_t config_sync_to_rtu(config_sync_manager_t *manager,
                                         const char *station_name);

/**
 * Send enrollment packet to RTU.
 *
 * @param manager       Sync manager
 * @param station_name  RTU station name
 * @param token         Enrollment token (wtc-enroll-...)
 * @param operation     ENROLLMENT_OP_BIND, UNBIND, REBIND, or STATUS
 * @return CONFIG_SYNC_OK on success
 */
config_sync_result_t config_sync_send_enrollment(config_sync_manager_t *manager,
                                                  const char *station_name,
                                                  const char *token,
                                                  uint8_t operation);

/**
 * Send device configuration to RTU.
 *
 * @param manager       Sync manager
 * @param station_name  RTU station name
 * @param device        Device record (from registry)
 * @return CONFIG_SYNC_OK on success
 */
config_sync_result_t config_sync_send_device_config(config_sync_manager_t *manager,
                                                     const char *station_name,
                                                     const rtu_device_t *device);

/**
 * Send sensor configuration to RTU.
 *
 * @param manager       Sync manager
 * @param station_name  RTU station name
 * @param slots         Array of slot configs
 * @param slot_count    Number of slots
 * @return CONFIG_SYNC_OK on success
 */
config_sync_result_t config_sync_send_sensor_config(config_sync_manager_t *manager,
                                                     const char *station_name,
                                                     const slot_config_t *slots,
                                                     int slot_count);

/**
 * Send actuator configuration to RTU.
 *
 * @param manager       Sync manager
 * @param station_name  RTU station name
 * @param slots         Array of slot configs
 * @param slot_count    Number of slots
 * @return CONFIG_SYNC_OK on success
 */
config_sync_result_t config_sync_send_actuator_config(config_sync_manager_t *manager,
                                                       const char *station_name,
                                                       const slot_config_t *slots,
                                                       int slot_count);

/* ============== Event Handlers ============== */

/**
 * Handle RTU connection event (AR_STATE_RUN).
 * Triggers full config sync if sync_on_connect enabled.
 *
 * @param manager       Sync manager
 * @param station_name  RTU that connected
 */
void config_sync_on_rtu_connect(config_sync_manager_t *manager,
                                 const char *station_name);

/**
 * Get sync statistics.
 */
wtc_result_t config_sync_get_stats(config_sync_manager_t *manager,
                                    config_sync_stats_t *stats);

#ifdef __cplusplus
}
#endif

#endif /* WTC_CONFIG_SYNC_H */
