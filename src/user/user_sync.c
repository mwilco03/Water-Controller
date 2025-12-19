/*
 * Water Treatment Controller - User Synchronization Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "user_sync.h"
#include "profinet/profinet_controller.h"
#include "registry/rtu_registry.h"
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

/* ============== DJB2 Hash Implementation ============== */

/**
 * DJB2 hash algorithm by Dan Bernstein.
 * This implementation matches the RTU for compatibility.
 */
static uint32_t djb2_hash(const char *str) {
    uint32_t hash = 5381;
    int c;

    while ((c = *str++)) {
        hash = ((hash << 5) + hash) + c; /* hash * 33 + c */
    }

    return hash;
}

int user_sync_hash_password(const char *password,
                            char *hash_out,
                            size_t hash_out_size) {
    if (!password || !hash_out || hash_out_size < USER_SYNC_HASH_LEN) {
        return -1;
    }

    /* Concatenate salt and password */
    char salted[256];
    snprintf(salted, sizeof(salted), "%s%s", USER_SYNC_SALT, password);

    /* Compute DJB2 hash */
    uint32_t hash = djb2_hash(salted);

    /* Format as hex string with salt prefix for verification */
    /* Format: "DJB2:<salt_hash>:<password_hash>" */
    uint32_t salt_hash = djb2_hash(USER_SYNC_SALT);
    snprintf(hash_out, hash_out_size, "DJB2:%08X:%08X", salt_hash, hash);

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

    return strcmp(computed_hash, stored_hash) == 0;
}

/* ============== CRC16-CCITT Implementation ============== */

/* CRC16-CCITT lookup table */
static const uint16_t crc16_table[256] = {
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
    0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
    0x1231, 0x0210, 0x3273, 0x2252, 0x52B5, 0x4294, 0x72F7, 0x62D6,
    0x9339, 0x8318, 0xB37B, 0xA35A, 0xD3BD, 0xC39C, 0xF3FF, 0xE3DE,
    0x2462, 0x3443, 0x0420, 0x1401, 0x64E6, 0x74C7, 0x44A4, 0x5485,
    0xA56A, 0xB54B, 0x8528, 0x9509, 0xE5EE, 0xF5CF, 0xC5AC, 0xD58D,
    0x3653, 0x2672, 0x1611, 0x0630, 0x76D7, 0x66F6, 0x5695, 0x46B4,
    0xB75B, 0xA77A, 0x9719, 0x8738, 0xF7DF, 0xE7FE, 0xD79D, 0xC7BC,
    0x48C4, 0x58E5, 0x6886, 0x78A7, 0x0840, 0x1861, 0x2802, 0x3823,
    0xC9CC, 0xD9ED, 0xE98E, 0xF9AF, 0x8948, 0x9969, 0xA90A, 0xB92B,
    0x5AF5, 0x4AD4, 0x7AB7, 0x6A96, 0x1A71, 0x0A50, 0x3A33, 0x2A12,
    0xDBFD, 0xCBDC, 0xFBBF, 0xEB9E, 0x9B79, 0x8B58, 0xBB3B, 0xAB1A,
    0x6CA6, 0x7C87, 0x4CE4, 0x5CC5, 0x2C22, 0x3C03, 0x0C60, 0x1C41,
    0xEDAE, 0xFD8F, 0xCDEC, 0xDDCD, 0xAD2A, 0xBD0B, 0x8D68, 0x9D49,
    0x7E97, 0x6EB6, 0x5ED5, 0x4EF4, 0x3E13, 0x2E32, 0x1E51, 0x0E70,
    0xFF9F, 0xEFBE, 0xDFDD, 0xCFFC, 0xBF1B, 0xAF3A, 0x9F59, 0x8F78,
    0x9188, 0x81A9, 0xB1CA, 0xA1EB, 0xD10C, 0xC12D, 0xF14E, 0xE16F,
    0x1080, 0x00A1, 0x30C2, 0x20E3, 0x5004, 0x4025, 0x7046, 0x6067,
    0x83B9, 0x9398, 0xA3FB, 0xB3DA, 0xC33D, 0xD31C, 0xE37F, 0xF35E,
    0x02B1, 0x1290, 0x22F3, 0x32D2, 0x4235, 0x5214, 0x6277, 0x7256,
    0xB5EA, 0xA5CB, 0x95A8, 0x8589, 0xF56E, 0xE54F, 0xD52C, 0xC50D,
    0x34E2, 0x24C3, 0x14A0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
    0xA7DB, 0xB7FA, 0x8799, 0x97B8, 0xE75F, 0xF77E, 0xC71D, 0xD73C,
    0x26D3, 0x36F2, 0x0691, 0x16B0, 0x6657, 0x7676, 0x4615, 0x5634,
    0xD94C, 0xC96D, 0xF90E, 0xE92F, 0x99C8, 0x89E9, 0xB98A, 0xA9AB,
    0x5844, 0x4865, 0x7806, 0x6827, 0x18C0, 0x08E1, 0x3882, 0x28A3,
    0xCB7D, 0xDB5C, 0xEB3F, 0xFB1E, 0x8BF9, 0x9BD8, 0xABBB, 0xBB9A,
    0x4A75, 0x5A54, 0x6A37, 0x7A16, 0x0AF1, 0x1AD0, 0x2AB3, 0x3A92,
    0xFD2E, 0xED0F, 0xDD6C, 0xCD4D, 0xBDAA, 0xAD8B, 0x9DE8, 0x8DC9,
    0x7C26, 0x6C07, 0x5C64, 0x4C45, 0x3CA2, 0x2C83, 0x1CE0, 0x0CC1,
    0xEF1F, 0xFF3E, 0xCF5D, 0xDF7C, 0xAF9B, 0xBFBA, 0x8FD9, 0x9FF8,
    0x6E17, 0x7E36, 0x4E55, 0x5E74, 0x2E93, 0x3EB2, 0x0ED1, 0x1EF0
};

uint16_t user_sync_crc16(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;

    while (len--) {
        crc = (crc << 8) ^ crc16_table[((crc >> 8) ^ *data++) & 0xFF];
    }

    return crc;
}

/* ============== Serialization ============== */

user_sync_result_t user_sync_serialize(const user_t *users,
                                        int user_count,
                                        user_sync_payload_t *payload) {
    if (!users || !payload || user_count < 0) {
        return USER_SYNC_ERROR_INVALID_PARAM;
    }

    if (user_count > USER_SYNC_MAX_USERS) {
        LOG_WARN(LOG_TAG, "User count %d exceeds max %d, truncating",
                 user_count, USER_SYNC_MAX_USERS);
        user_count = USER_SYNC_MAX_USERS;
    }

    memset(payload, 0, sizeof(user_sync_payload_t));

    /* Fill header */
    payload->header.version = USER_SYNC_VERSION;
    payload->header.user_count = (uint8_t)user_count;
    payload->header.timestamp = (uint32_t)(time_get_ms() / 1000);
    payload->header.nonce = (uint32_t)time_get_ms(); /* Simple nonce */

    /* Fill user records */
    for (int i = 0; i < user_count; i++) {
        user_sync_record_t *record = &payload->users[i];

        /* Copy username (truncate if needed) */
        strncpy(record->username, users[i].username, sizeof(record->username) - 1);
        record->username[sizeof(record->username) - 1] = '\0';

        /* Copy password hash */
        strncpy(record->password_hash, users[i].password_hash,
                sizeof(record->password_hash) - 1);
        record->password_hash[sizeof(record->password_hash) - 1] = '\0';

        /* Set role */
        record->role = (uint8_t)users[i].role;

        /* Set flags */
        record->flags = 0;
        if (users[i].active) {
            record->flags |= 0x01; /* Bit 0: active */
        }
        record->flags |= 0x02; /* Bit 1: synced_from_controller (always set) */
    }

    /* Calculate checksum over user records */
    payload->header.checksum = user_sync_crc16(
        (const uint8_t *)payload->users,
        user_count * sizeof(user_sync_record_t)
    );

    LOG_DEBUG(LOG_TAG, "Serialized %d users, checksum=0x%04X",
              user_count, payload->header.checksum);

    return USER_SYNC_OK;
}

user_sync_result_t user_sync_deserialize(const user_sync_payload_t *payload,
                                          user_t *users,
                                          int max_users,
                                          int *user_count) {
    if (!payload || !users || !user_count || max_users <= 0) {
        return USER_SYNC_ERROR_INVALID_PARAM;
    }

    /* Check version */
    if (payload->header.version != USER_SYNC_VERSION) {
        LOG_ERROR(LOG_TAG, "Version mismatch: expected %d, got %d",
                  USER_SYNC_VERSION, payload->header.version);
        return USER_SYNC_ERROR_VERSION;
    }

    int count = payload->header.user_count;
    if (count > max_users) {
        count = max_users;
    }

    /* Verify checksum */
    uint16_t computed_crc = user_sync_crc16(
        (const uint8_t *)payload->users,
        payload->header.user_count * sizeof(user_sync_record_t)
    );

    if (computed_crc != payload->header.checksum) {
        LOG_ERROR(LOG_TAG, "Checksum mismatch: expected 0x%04X, got 0x%04X",
                  payload->header.checksum, computed_crc);
        return USER_SYNC_ERROR_CHECKSUM;
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
        users[i].active = (record->flags & 0x01) != 0;
        users[i].created_at_ms = 0;
        users[i].last_login_ms = 0;
    }

    *user_count = count;
    LOG_DEBUG(LOG_TAG, "Deserialized %d users", count);

    return USER_SYNC_OK;
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

void user_sync_set_callback(user_sync_manager_t *manager,
                            user_sync_callback_t callback,
                            void *ctx) {
    if (manager) {
        manager->callback = callback;
        manager->callback_ctx = ctx;
    }
}

user_sync_result_t user_sync_to_rtu(user_sync_manager_t *manager,
                                     const char *station_name,
                                     const user_t *users,
                                     int user_count) {
    if (!manager || !station_name || !users) {
        return USER_SYNC_ERROR_INVALID_PARAM;
    }

    if (!manager->profinet) {
        LOG_ERROR(LOG_TAG, "PROFINET controller not set");
        return USER_SYNC_ERROR_SEND;
    }

    /* Serialize users */
    user_sync_payload_t payload;
    user_sync_result_t result = user_sync_serialize(users, user_count, &payload);
    if (result != USER_SYNC_OK) {
        LOG_ERROR(LOG_TAG, "Failed to serialize users: %d", result);
        return result;
    }

    /* Calculate actual payload size */
    size_t payload_size = sizeof(user_sync_header_t) +
                          (payload.header.user_count * sizeof(user_sync_record_t));

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
        result = USER_SYNC_OK;
    } else if (send_result == WTC_ERROR_NOT_CONNECTED) {
        manager->stats.failed_syncs++;
        LOG_WARN(LOG_TAG, "RTU %s not connected", station_name);
        result = USER_SYNC_ERROR_RTU_NOT_CONNECTED;
    } else {
        manager->stats.failed_syncs++;
        LOG_ERROR(LOG_TAG, "Failed to send user sync to %s: %d",
                  station_name, send_result);
        result = USER_SYNC_ERROR_SEND;
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
            user_sync_result_t result = user_sync_to_rtu(
                manager, devices[i].station_name, users, user_count);
            if (result == USER_SYNC_OK) {
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

/* Set registry for RTU listing */
wtc_result_t user_sync_set_registry(user_sync_manager_t *manager,
                                     struct rtu_registry *registry) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }
    manager->registry = registry;
    return WTC_OK;
}
