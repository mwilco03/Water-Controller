/*
 * Water Treatment Controller - User Synchronization
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Handles PROFINET acyclic synchronization of user credentials
 * from Controller to RTUs for local TUI authentication.
 *
 * Wire protocol definitions are in shared/include/user_sync_protocol.h
 * to ensure Controller and RTU use identical formats.
 */

#ifndef WTC_USER_SYNC_H
#define WTC_USER_SYNC_H

#include "types.h"
#include "user_sync_protocol.h"  /* Shared protocol definitions */

#ifdef __cplusplus
extern "C" {
#endif

/* ============== Controller-Specific Definitions ============== */

/*
 * Note: Wire protocol constants (USER_SYNC_PROTOCOL_VERSION, USER_SYNC_RECORD_INDEX,
 * USER_SYNC_MAX_USERS, USER_SYNC_HASH_LEN, USER_SYNC_SALT) are defined in
 * user_sync_protocol.h for cross-system compatibility.
 *
 * Legacy aliases for backward compatibility:
 */
#define USER_SYNC_VERSION       USER_SYNC_PROTOCOL_VERSION

/* Controller-specific status codes (extend shared result codes) */
typedef enum {
    /* Import shared result codes */
    WTC_USER_SYNC_OK                    = USER_SYNC_OK,
    WTC_USER_SYNC_ERROR_INVALID_PARAM   = USER_SYNC_ERR_INVALID_PARAM,
    WTC_USER_SYNC_ERROR_CHECKSUM        = USER_SYNC_ERR_CHECKSUM,
    WTC_USER_SYNC_ERROR_VERSION         = USER_SYNC_ERR_VERSION_MISMATCH,

    /* Controller-specific codes */
    WTC_USER_SYNC_ERROR_NO_MEMORY       = -20,
    WTC_USER_SYNC_ERROR_SERIALIZE       = -21,
    WTC_USER_SYNC_ERROR_SEND            = -22,
    WTC_USER_SYNC_ERROR_TIMEOUT         = -23,
    WTC_USER_SYNC_ERROR_RTU_NOT_CONNECTED = -24,
} wtc_user_sync_result_t;

/* User sync manager handle */
typedef struct user_sync_manager user_sync_manager_t;

/* User sync configuration */
typedef struct {
    bool auto_sync_on_connect;      /* Sync when RTU connects */
    bool auto_sync_on_change;       /* Sync when user changes */
    uint32_t sync_timeout_ms;       /* Timeout for sync operation */
    uint32_t retry_count;           /* Number of retries on failure */
    uint32_t retry_delay_ms;        /* Delay between retries */
} user_sync_config_t;

/* Sync result callback */
typedef void (*user_sync_callback_t)(const char *station_name,
                                      int result,
                                      void *ctx);

/* Sync statistics */
typedef struct {
    uint32_t total_syncs;
    uint32_t successful_syncs;
    uint32_t failed_syncs;
    uint64_t last_sync_time_ms;
    char last_sync_rtu[WTC_MAX_STATION_NAME];
} user_sync_stats_t;

/* ============== Hash Functions ============== */

/**
 * Hash password using DJB2 algorithm with salt.
 * Uses shared user_sync_djb2() and user_sync_hash_with_salt() internally.
 *
 * @param password      Plain text password
 * @param hash_out      Output buffer for hex hash string (min USER_SYNC_HASH_LEN bytes)
 * @param hash_out_size Size of output buffer
 * @return 0 on success, -1 on error
 */
int user_sync_hash_password(const char *password,
                            char *hash_out,
                            size_t hash_out_size);

/**
 * Verify password against stored hash.
 * Uses constant-time comparison to prevent timing attacks.
 *
 * @param password      Plain text password to verify
 * @param stored_hash   Stored hash to compare against
 * @return true if password matches, false otherwise
 */
bool user_sync_verify_password(const char *password,
                               const char *stored_hash);

/* ============== Serialization ============== */

/**
 * Calculate CRC16-CCITT checksum.
 * Wrapper around shared user_sync_crc16_ccitt().
 *
 * @param data  Data buffer
 * @param len   Data length
 * @return CRC16 checksum
 */
uint16_t user_sync_crc16(const uint8_t *data, size_t len);

/**
 * Serialize users into sync payload.
 *
 * @param users         Array of user records (from types.h user_t)
 * @param user_count    Number of users (capped at USER_SYNC_MAX_USERS)
 * @param payload       Output payload buffer
 * @return 0 on success, negative error code otherwise
 */
int user_sync_serialize(const user_t *users,
                        int user_count,
                        user_sync_payload_t *payload);

/**
 * Deserialize sync payload into user records.
 * (Used for testing, RTU handles actual deserialization)
 *
 * @param payload       Input payload
 * @param users         Output user array
 * @param max_users     Maximum users to deserialize
 * @param user_count    Output: actual number of users
 * @return 0 on success, negative error code otherwise
 */
int user_sync_deserialize(const user_sync_payload_t *payload,
                          user_t *users,
                          int max_users,
                          int *user_count);

/* ============== Sync Manager ============== */

/**
 * Initialize user sync manager.
 *
 * @param manager   Output: manager handle
 * @param config    Configuration (NULL for defaults)
 * @return WTC_OK on success
 */
wtc_result_t user_sync_manager_init(user_sync_manager_t **manager,
                                     const user_sync_config_t *config);

/**
 * Cleanup user sync manager.
 */
void user_sync_manager_cleanup(user_sync_manager_t *manager);

/**
 * Set PROFINET controller for sync operations.
 */
struct profinet_controller;
wtc_result_t user_sync_set_profinet(user_sync_manager_t *manager,
                                     struct profinet_controller *profinet);

/**
 * Set RTU registry for listing devices.
 */
struct rtu_registry;
wtc_result_t user_sync_set_registry(user_sync_manager_t *manager,
                                     struct rtu_registry *registry);

/**
 * Set callback for sync results.
 */
void user_sync_set_callback(user_sync_manager_t *manager,
                            user_sync_callback_t callback,
                            void *ctx);

/**
 * Sync users to a specific RTU.
 *
 * @param manager       Sync manager
 * @param station_name  RTU station name
 * @param users         Array of users to sync
 * @param user_count    Number of users
 * @return 0 on success, negative error code otherwise
 */
int user_sync_to_rtu(user_sync_manager_t *manager,
                     const char *station_name,
                     const user_t *users,
                     int user_count);

/**
 * Sync users to all connected RTUs.
 *
 * @param manager       Sync manager
 * @param users         Array of users to sync
 * @param user_count    Number of users
 * @return Number of RTUs successfully synced
 */
int user_sync_to_all_rtus(user_sync_manager_t *manager,
                          const user_t *users,
                          int user_count);

/**
 * Handle RTU connection event (triggers sync if auto_sync_on_connect).
 *
 * @param manager       Sync manager
 * @param station_name  RTU that connected
 * @param users         Current user list
 * @param user_count    Number of users
 */
void user_sync_on_rtu_connect(user_sync_manager_t *manager,
                              const char *station_name,
                              const user_t *users,
                              int user_count);

/**
 * Handle user change event (triggers sync if auto_sync_on_change).
 *
 * @param manager       Sync manager
 * @param users         Updated user list
 * @param user_count    Number of users
 */
void user_sync_on_user_change(user_sync_manager_t *manager,
                              const user_t *users,
                              int user_count);

/**
 * Get sync statistics.
 */
wtc_result_t user_sync_get_stats(user_sync_manager_t *manager,
                                  user_sync_stats_t *stats);

#ifdef __cplusplus
}
#endif

#endif /* WTC_USER_SYNC_H */
