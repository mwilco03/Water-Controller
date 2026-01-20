/**
 * @file profinet_user_handler.h
 * @brief PROFINET record handler for user sync integration
 *
 * This module provides the glue between the RTU's PROFINET device stack
 * and the user_store module. It registers a handler for record index 0xF840
 * to receive user sync payloads from the Controller.
 *
 * INTEGRATION STEPS:
 * 1. Include this header in your RTU's PROFINET device initialization
 * 2. Call profinet_user_handler_init() after user_store_init()
 * 3. Register profinet_user_handler_write() with your PROFINET stack
 *
 * EXAMPLE (p-net based):
 * @code
 *   // In profinet_device.c init function:
 *   user_store_init(&config);
 *   profinet_user_handler_init();
 *
 *   // In record write callback:
 *   if (index == USER_SYNC_RECORD_INDEX) {
 *       return profinet_user_handler_write(data, length);
 *   }
 * @endcode
 *
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef RTU_PROFINET_USER_HANDLER_H
#define RTU_PROFINET_USER_HANDLER_H

#include "user_sync_protocol.h"
#include "user_store.h"
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============== Handler State ============== */

/**
 * @brief User handler statistics
 */
typedef struct {
    uint32_t write_requests;    /**< Total write requests received */
    uint32_t write_successes;   /**< Successful writes */
    uint32_t write_failures;    /**< Failed writes */
    uint32_t read_requests;     /**< Total read requests */
    int      last_error;        /**< Last error code */
} profinet_user_handler_stats_t;

/* ============== Initialization ============== */

/**
 * @brief Initialize PROFINET user handler
 *
 * Must be called after user_store_init().
 *
 * @return  0 on success, -1 on failure
 */
int profinet_user_handler_init(void);

/**
 * @brief Shutdown PROFINET user handler
 */
void profinet_user_handler_shutdown(void);

/* ============== Record Handlers ============== */

/**
 * @brief Handle PROFINET record write for user sync
 *
 * This is the main entry point for PROFINET acyclic writes.
 * Call this from your PROFINET device's write_record callback
 * when index == USER_SYNC_RECORD_INDEX (0xF840).
 *
 * @param data    Record data from Controller
 * @param length  Data length in bytes
 * @return        0 on success, negative error code on failure
 *
 * Return codes follow PROFINET Application Layer response format:
 * -  0: OK
 * - -1: Invalid data / checksum error
 * - -2: Version mismatch
 * - -3: Resource busy / storage error
 */
int profinet_user_handler_write(const uint8_t *data, size_t length);

/**
 * @brief Handle PROFINET record read for user sync status
 *
 * Allows Controller to read back sync status from RTU.
 * Call this from your PROFINET device's read_record callback
 * when index == USER_SYNC_RECORD_INDEX (0xF840).
 *
 * Returns a status structure (not user credentials).
 *
 * @param data        Output buffer for response
 * @param max_length  Maximum buffer size
 * @param actual_len  Output: actual response length
 * @return            0 on success, negative error code on failure
 */
int profinet_user_handler_read(uint8_t *data, size_t max_length,
                                size_t *actual_len);

/* ============== Statistics ============== */

/**
 * @brief Get handler statistics
 *
 * @param stats  Output statistics structure
 */
void profinet_user_handler_get_stats(profinet_user_handler_stats_t *stats);

/**
 * @brief Reset handler statistics
 */
void profinet_user_handler_reset_stats(void);

#ifdef __cplusplus
}
#endif

#endif /* RTU_PROFINET_USER_HANDLER_H */
