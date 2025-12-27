/*
 * Water Treatment Controller - Authority Manager
 * Implements formal authority handoff protocol between Controller and RTU
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * This module prevents split-brain scenarios by ensuring only one entity
 * (either Controller or RTU) has control authority at any given time.
 */

#ifndef WTC_AUTHORITY_MANAGER_H
#define WTC_AUTHORITY_MANAGER_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Authority manager handle */
typedef struct authority_manager authority_manager_t;

/* Authority manager configuration */
typedef struct {
    uint32_t handoff_timeout_ms;     /* Max time to wait for RTU acknowledgment */
    uint32_t stale_command_ms;       /* Commands older than this are rejected */
    uint32_t heartbeat_interval_ms;  /* How often to send authority heartbeats */
    bool auto_release_on_disconnect; /* Release authority when RTU disconnects */
} authority_manager_config_t;

/* Callback for authority state changes */
typedef void (*authority_callback_t)(const char *station_name,
                                      authority_state_t old_state,
                                      authority_state_t new_state,
                                      void *ctx);

/* Initialize authority manager */
wtc_result_t authority_manager_init(authority_manager_t **manager,
                                     const authority_manager_config_t *config);

/* Cleanup authority manager */
void authority_manager_cleanup(authority_manager_t *manager);

/* Set callback for authority changes */
void authority_manager_set_callback(authority_manager_t *manager,
                                     authority_callback_t callback,
                                     void *ctx);

/* Request authority over an RTU (Controller -> RTU)
 * Initiates the handoff protocol:
 * 1. Controller sends AUTHORITY_REQUEST
 * 2. RTU transitions to HANDOFF_PENDING
 * 3. RTU sends AUTHORITY_GRANT
 * 4. Controller transitions to SUPERVISED
 */
wtc_result_t authority_request(authority_manager_t *manager,
                                const char *station_name,
                                authority_context_t *ctx);

/* Release authority back to RTU (Controller -> RTU)
 * Initiates graceful release:
 * 1. Controller sends AUTHORITY_RELEASE
 * 2. RTU transitions to RELEASING
 * 3. RTU sends AUTHORITY_RELEASED
 * 4. RTU transitions to AUTONOMOUS
 */
wtc_result_t authority_release(authority_manager_t *manager,
                                const char *station_name,
                                authority_context_t *ctx);

/* Handle authority grant from RTU (RTU -> Controller) */
wtc_result_t authority_handle_grant(authority_manager_t *manager,
                                     const char *station_name,
                                     uint32_t epoch,
                                     authority_context_t *ctx);

/* Handle authority released from RTU (RTU -> Controller) */
wtc_result_t authority_handle_released(authority_manager_t *manager,
                                        const char *station_name,
                                        uint32_t epoch,
                                        authority_context_t *ctx);

/* Check if a command should be accepted based on authority epoch
 * Returns WTC_OK if command is valid, WTC_ERROR_PERMISSION if stale
 */
wtc_result_t authority_validate_command(authority_manager_t *manager,
                                         const char *station_name,
                                         uint32_t command_epoch,
                                         const authority_context_t *ctx);

/* Get current authority state for an RTU */
authority_state_t authority_get_state(authority_manager_t *manager,
                                       const char *station_name);

/* Get current authority epoch for an RTU */
uint32_t authority_get_epoch(authority_manager_t *manager,
                              const char *station_name);

/* Process authority timeouts and heartbeats (call from main loop) */
wtc_result_t authority_manager_process(authority_manager_t *manager,
                                        uint64_t now_ms);

/* Force release authority on RTU disconnect */
wtc_result_t authority_force_release(authority_manager_t *manager,
                                      const char *station_name);

/* Initialize authority context with defaults */
void authority_context_init(authority_context_t *ctx);

/* Get string representation of authority state */
const char *authority_state_to_string(authority_state_t state);

#ifdef __cplusplus
}
#endif

#endif /* WTC_AUTHORITY_MANAGER_H */
