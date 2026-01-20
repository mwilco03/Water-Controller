/**
 * @file profinet_user_handler.c
 * @brief PROFINET record handler for user sync implementation
 *
 * Bridges the PROFINET device stack with the user_store module.
 *
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "profinet_user_handler.h"
#include <string.h>

/* ============== Internal State ============== */

static struct {
    bool initialized;
    profinet_user_handler_stats_t stats;
} g_handler = {0};

/* ============== Status Response Structure ============== */

/**
 * Response payload for record read requests.
 * Allows Controller to query RTU sync status.
 */
typedef struct __attribute__((packed)) {
    uint8_t  protocol_version;  /**< USER_SYNC_PROTOCOL_VERSION */
    uint8_t  user_count;        /**< Number of users stored */
    uint8_t  active_count;      /**< Number of active users */
    uint8_t  reserved;          /**< Padding */
    uint32_t last_sync_time;    /**< Timestamp of last sync */
    uint32_t last_sync_nonce;   /**< Nonce of last sync */
    uint32_t sync_count;        /**< Total syncs received */
    uint32_t auth_attempts;     /**< Auth attempts since boot */
    uint32_t auth_successes;    /**< Successful auths */
    uint32_t auth_failures;     /**< Failed auths */
} user_sync_status_t;

/* ============== Public API ============== */

int profinet_user_handler_init(void) {
    if (!user_store_is_initialized()) {
        return -1;
    }

    memset(&g_handler, 0, sizeof(g_handler));
    g_handler.initialized = true;

    return 0;
}

void profinet_user_handler_shutdown(void) {
    g_handler.initialized = false;
}

int profinet_user_handler_write(const uint8_t *data, size_t length) {
    if (!g_handler.initialized) {
        return -3;  /* Resource busy / not ready */
    }

    if (!data || length == 0) {
        g_handler.stats.write_requests++;
        g_handler.stats.write_failures++;
        g_handler.stats.last_error = USER_SYNC_ERR_INVALID_PARAM;
        return -1;
    }

    g_handler.stats.write_requests++;

    /* Forward to user store */
    user_sync_result_t result = user_store_receive_sync(data, length);

    if (result == USER_SYNC_OK) {
        g_handler.stats.write_successes++;
        return 0;
    }

    /* Map error codes to PROFINET response */
    g_handler.stats.write_failures++;
    g_handler.stats.last_error = result;

    switch (result) {
        case USER_SYNC_ERR_INVALID_PARAM:
        case USER_SYNC_ERR_CHECKSUM:
            return -1;  /* Invalid data */

        case USER_SYNC_ERR_VERSION_MISMATCH:
            return -2;  /* Version mismatch */

        case USER_SYNC_ERR_REPLAY:
        case USER_SYNC_ERR_STORAGE_FULL:
        case USER_SYNC_ERR_STORAGE_WRITE:
            return -3;  /* Resource busy / storage error */

        default:
            return -1;
    }
}

int profinet_user_handler_read(uint8_t *data, size_t max_length,
                                size_t *actual_len) {
    if (!g_handler.initialized) {
        return -3;
    }

    if (!data || !actual_len || max_length < sizeof(user_sync_status_t)) {
        g_handler.stats.read_requests++;
        return -1;
    }

    g_handler.stats.read_requests++;

    /* Get current stats from user store */
    user_store_stats_t store_stats;
    user_store_get_stats(&store_stats);

    /* Build response */
    user_sync_status_t status = {
        .protocol_version = USER_SYNC_PROTOCOL_VERSION,
        .user_count = store_stats.user_count,
        .active_count = store_stats.active_count,
        .reserved = 0,
        .last_sync_time = store_stats.last_sync_time,
        .last_sync_nonce = store_stats.last_sync_nonce,
        .sync_count = store_stats.sync_count,
        .auth_attempts = store_stats.auth_attempts,
        .auth_successes = store_stats.auth_successes,
        .auth_failures = store_stats.auth_failures,
    };

    memcpy(data, &status, sizeof(status));
    *actual_len = sizeof(status);

    return 0;
}

void profinet_user_handler_get_stats(profinet_user_handler_stats_t *stats) {
    if (stats) {
        *stats = g_handler.stats;
    }
}

void profinet_user_handler_reset_stats(void) {
    memset(&g_handler.stats, 0, sizeof(g_handler.stats));
}
