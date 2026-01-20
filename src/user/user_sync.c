/*
 * Water Treatment Controller - User Synchronization Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "user_sync.h"
#include "profinet/profinet_controller.h"
#include "registry/rtu_registry.h"
#include "utils/crc.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#define LOG_TAG "USER_SYNC"

/* Default configuration */
static const user_sync_config_t default_config = {
    .auto_sync_on_connect = true,
    .auto_sync_on_change = true,
    .sync_timeout_ms = 5000,
    .retry_count = 3,
    .retry_delay_ms = 1000,
};

/* User sync manager structure */
struct user_sync_manager {
    user_sync_config_t config;
    struct profinet_controller *profinet;
    struct rtu_registry *registry;

    user_sync_callback_t callback;
    void *callback_ctx;

    user_sync_stats_t stats;
};

/* ============== Constant-Time Comparison ============== */

/**
 * Constant-time string comparison for password hashes.
 * Always compares the full length of both strings.
 */
static bool secure_strcmp(const char *a, const char *b) {
    size_t len_a = strlen(a);
    size_t len_b = strlen(b);
    size_t max_len = (len_a > len_b) ? len_a : len_b;

    /* Length difference already indicates mismatch, but we continue
     * comparing to maintain constant time */
    volatile uint8_t result = (len_a != len_b) ? 1 : 0;

    for (size_t i = 0; i < max_len; i++) {
        uint8_t ca = (i < len_a) ? (uint8_t)a[i] : 0;
        uint8_t cb = (i < len_b) ? (uint8_t)b[i] : 0;
        result |= ca ^ cb;
    }

    return result == 0;
}

/* ============== Hash Functions ============== */

int user_sync_hash_password(const char *password,
                            char *hash_out,
                            size_t hash_out_size) {
    if (!password || !hash_out || hash_out_size < USER_SYNC_HASH_LEN) {
        return -1;
    }

    /* Use shared hash function */
    uint32_t salt_hash, pass_hash;
    user_sync_hash_with_salt(password, &salt_hash, &pass_hash);

    /* Format as hex string: "DJB2:<salt_hash>:<password_hash>" */
    snprintf(hash_out, hash_out_size, "DJB2:%08X:%08X",
             (unsigned int)salt_hash, (unsigned int)pass_hash);

    return 0;
}

bool user_sync_verify_password(const char *password,
                               const char *stored_hash) {
    if (!password || !stored_hash) {
        return false;
    }

    char computed_hash[USER_SYNC_HASH_LEN];
    if (user_sync_hash_password(password, computed_hash, sizeof(computed_hash)) != 0) {
        return false;
    }

    /* Use constant-time comparison to prevent timing attacks */
    return secure_strcmp(computed_hash, stored_hash);
}

/* ============== CRC16-CCITT ============== */

uint16_t user_sync_crc16(const uint8_t *data, size_t len) {
    /* Use shared CRC implementation for consistency */
    return user_sync_crc16_ccitt(data, len);
}

/* ============== Serialization ============== */

int user_sync_serialize(const user_t *users,
                        int user_count,
                        user_sync_payload_t *payload) {
    if (!users || !payload || user_count < 0) {
        return WTC_USER_SYNC_ERROR_INVALID_PARAM;
    }

    if (user_count > USER_SYNC_MAX_USERS) {
        LOG_WARN(LOG_TAG, "User count %d exceeds max %d, truncating",
                 user_count, USER_SYNC_MAX_USERS);
        user_count = USER_SYNC_MAX_USERS;
    }

    memset(payload, 0, sizeof(user_sync_payload_t));

    /* Fill header */
    payload->header.version = USER_SYNC_PROTOCOL_VERSION;
    payload->header.user_count = (uint8_t)user_count;
    payload->header.timestamp = (uint32_t)(time_get_ms() / 1000);
    payload->header.nonce = (uint32_t)time_get_ms(); /* Simple nonce */

    /* Fill user records */
    for (int i = 0; i < user_count; i++) {
        user_sync_record_t *record = &payload->users[i];

        /* Copy username (truncate if needed) */
        strncpy(record->username, users[i].username,
                USER_SYNC_USERNAME_LEN - 1);
        record->username[USER_SYNC_USERNAME_LEN - 1] = '\0';

        /* Copy password hash */
        strncpy(record->password_hash, users[i].password_hash,
                USER_SYNC_HASH_LEN - 1);
        record->password_hash[USER_SYNC_HASH_LEN - 1] = '\0';

        /* Set role */
        record->role = (uint8_t)users[i].role;

        /* Set flags */
        record->flags = 0;
        if (users[i].active) {
            record->flags |= USER_FLAG_ACTIVE;
        }
        record->flags |= USER_FLAG_SYNCED; /* Mark as synced from controller */
    }

    /* Calculate checksum over user records */
    payload->header.checksum = user_sync_crc16(
        (const uint8_t *)payload->users,
        (size_t)user_count * sizeof(user_sync_record_t)
    );

    LOG_DEBUG(LOG_TAG, "Serialized %d users, checksum=0x%04X",
              user_count, payload->header.checksum);

    return 0;
}

int user_sync_deserialize(const user_sync_payload_t *payload,
                          user_t *users,
                          int max_users,
                          int *user_count) {
    if (!payload || !users || !user_count || max_users <= 0) {
        return WTC_USER_SYNC_ERROR_INVALID_PARAM;
    }

    /* Check version */
    if (payload->header.version != USER_SYNC_PROTOCOL_VERSION) {
        LOG_ERROR(LOG_TAG, "Version mismatch: expected %d, got %d",
                  USER_SYNC_PROTOCOL_VERSION, payload->header.version);
        return WTC_USER_SYNC_ERROR_VERSION;
    }

    int count = payload->header.user_count;
    if (count > max_users) {
        count = max_users;
    }
    if (count > USER_SYNC_MAX_USERS) {
        count = USER_SYNC_MAX_USERS;
    }

    /* Verify checksum */
    uint16_t computed_crc = user_sync_crc16(
        (const uint8_t *)payload->users,
        (size_t)payload->header.user_count * sizeof(user_sync_record_t)
    );

    if (computed_crc != payload->header.checksum) {
        LOG_ERROR(LOG_TAG, "Checksum mismatch: expected 0x%04X, got 0x%04X",
                  payload->header.checksum, computed_crc);
        return WTC_USER_SYNC_ERROR_CHECKSUM;
    }

    /* Extract user records */
    for (int i = 0; i < count; i++) {
        const user_sync_record_t *record = &payload->users[i];

        users[i].user_id = i + 1;
        strncpy(users[i].username, record->username, WTC_MAX_USERNAME - 1);
        users[i].username[WTC_MAX_USERNAME - 1] = '\0';
        strncpy(users[i].password_hash, record->password_hash, 255);
        users[i].password_hash[255] = '\0';
        users[i].role = (user_role_t)record->role;
        users[i].active = (record->flags & USER_FLAG_ACTIVE) != 0;
        users[i].created_at_ms = 0;
        users[i].last_login_ms = 0;
    }

    *user_count = count;
    LOG_DEBUG(LOG_TAG, "Deserialized %d users", count);

    return 0;
}

/* ============== Sync Manager ============== */

wtc_result_t user_sync_manager_init(user_sync_manager_t **manager,
                                     const user_sync_config_t *config) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    user_sync_manager_t *mgr = calloc(1, sizeof(user_sync_manager_t));
    if (!mgr) {
        return WTC_ERROR_NO_MEMORY;
    }

    if (config) {
        memcpy(&mgr->config, config, sizeof(user_sync_config_t));
    } else {
        memcpy(&mgr->config, &default_config, sizeof(user_sync_config_t));
    }

    *manager = mgr;
    LOG_INFO(LOG_TAG, "User sync manager initialized");

    return WTC_OK;
}

void user_sync_manager_cleanup(user_sync_manager_t *manager) {
    if (manager) {
        free(manager);
        LOG_INFO(LOG_TAG, "User sync manager cleaned up");
    }
}

wtc_result_t user_sync_set_profinet(user_sync_manager_t *manager,
                                     struct profinet_controller *profinet) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }
    manager->profinet = profinet;
    return WTC_OK;
}

wtc_result_t user_sync_set_registry(user_sync_manager_t *manager,
                                     struct rtu_registry *registry) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }
    manager->registry = registry;
    return WTC_OK;
}

void user_sync_set_callback(user_sync_manager_t *manager,
                            user_sync_callback_t callback,
                            void *ctx) {
    if (manager) {
        manager->callback = callback;
        manager->callback_ctx = ctx;
    }
}

int user_sync_to_rtu(user_sync_manager_t *manager,
                     const char *station_name,
                     const user_t *users,
                     int user_count) {
    if (!manager || !station_name || !users) {
        return WTC_USER_SYNC_ERROR_INVALID_PARAM;
    }

    if (!manager->profinet) {
        LOG_ERROR(LOG_TAG, "PROFINET controller not set");
        return WTC_USER_SYNC_ERROR_SEND;
    }

    /* Serialize users */
    user_sync_payload_t payload;
    int result = user_sync_serialize(users, user_count, &payload);
    if (result != 0) {
        LOG_ERROR(LOG_TAG, "Failed to serialize users: %d", result);
        return result;
    }

    /* Calculate actual payload size */
    size_t payload_size = user_sync_payload_size(payload.header.user_count);

    LOG_INFO(LOG_TAG, "Syncing %d users to RTU %s (%zu bytes)",
             user_count, station_name, payload_size);

    /* Send via PROFINET acyclic write */
    wtc_result_t send_result = profinet_controller_write_record(
        manager->profinet,
        station_name,
        0,                          /* API */
        0,                          /* Slot (DAP) */
        1,                          /* Subslot */
        USER_SYNC_RECORD_INDEX,     /* Index */
        &payload,
        payload_size
    );

    /* Update statistics */
    manager->stats.total_syncs++;

    if (send_result == WTC_OK) {
        manager->stats.successful_syncs++;
        manager->stats.last_sync_time_ms = time_get_ms();
        strncpy(manager->stats.last_sync_rtu, station_name,
                WTC_MAX_STATION_NAME - 1);
        LOG_INFO(LOG_TAG, "User sync to %s successful", station_name);
        result = 0;
    } else if (send_result == WTC_ERROR_NOT_CONNECTED) {
        manager->stats.failed_syncs++;
        LOG_WARN(LOG_TAG, "RTU %s not connected", station_name);
        result = WTC_USER_SYNC_ERROR_RTU_NOT_CONNECTED;
    } else {
        manager->stats.failed_syncs++;
        LOG_ERROR(LOG_TAG, "Failed to send user sync to %s: %d",
                  station_name, send_result);
        result = WTC_USER_SYNC_ERROR_SEND;
    }

    /* Invoke callback */
    if (manager->callback) {
        manager->callback(station_name, result, manager->callback_ctx);
    }

    return result;
}

int user_sync_to_all_rtus(user_sync_manager_t *manager,
                          const user_t *users,
                          int user_count) {
    if (!manager || !users || !manager->registry) {
        return 0;
    }

    int success_count = 0;
    rtu_device_t *devices = NULL;
    int device_count = 0;

    /* Get list of devices */
    if (rtu_registry_list_devices(manager->registry, &devices, &device_count,
                                   WTC_MAX_RTUS) != WTC_OK) {
        return 0;
    }

    LOG_INFO(LOG_TAG, "Syncing %d users to %d RTUs", user_count, device_count);

    for (int i = 0; i < device_count; i++) {
        if (devices[i].connection_state == PROFINET_STATE_RUNNING) {
            int result = user_sync_to_rtu(
                manager, devices[i].station_name, users, user_count);
            if (result == 0) {
                success_count++;
            }
        }
    }

    LOG_INFO(LOG_TAG, "User sync complete: %d/%d RTUs successful",
             success_count, device_count);

    return success_count;
}

void user_sync_on_rtu_connect(user_sync_manager_t *manager,
                              const char *station_name,
                              const user_t *users,
                              int user_count) {
    if (!manager || !station_name || !manager->config.auto_sync_on_connect) {
        return;
    }

    LOG_INFO(LOG_TAG, "RTU %s connected, triggering user sync", station_name);
    user_sync_to_rtu(manager, station_name, users, user_count);
}

void user_sync_on_user_change(user_sync_manager_t *manager,
                              const user_t *users,
                              int user_count) {
    if (!manager || !manager->config.auto_sync_on_change) {
        return;
    }

    LOG_INFO(LOG_TAG, "User change detected, syncing to all RTUs");
    user_sync_to_all_rtus(manager, users, user_count);
}

wtc_result_t user_sync_get_stats(user_sync_manager_t *manager,
                                  user_sync_stats_t *stats) {
    if (!manager || !stats) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memcpy(stats, &manager->stats, sizeof(user_sync_stats_t));
    return WTC_OK;
}
