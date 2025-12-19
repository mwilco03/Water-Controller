/*
 * Water Treatment Controller - User Synchronization
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Handles PROFINET acyclic synchronization of user credentials
 * from Controller to RTUs for local TUI authentication.
 */

#ifndef WTC_USER_SYNC_H
#define WTC_USER_SYNC_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* User sync protocol version */
#define USER_SYNC_VERSION       1

/* PROFINET record index for user sync (vendor-specific range) */
#define USER_SYNC_RECORD_INDEX  0xF840

/* Maximum users in a single sync payload */
#define USER_SYNC_MAX_USERS     32

/* Password hash length (DJB2 produces 32-bit, we store hex + salt info) */
#define USER_SYNC_HASH_LEN      64

/* Salt for password hashing (matches RTU) */
#define USER_SYNC_SALT          "NaCl4Life"

/* User sync status codes */
typedef enum {
    USER_SYNC_OK = 0,
    USER_SYNC_ERROR_INVALID_PARAM = -1,
    USER_SYNC_ERROR_NO_MEMORY = -2,
    USER_SYNC_ERROR_SERIALIZE = -3,
    USER_SYNC_ERROR_CHECKSUM = -4,
    USER_SYNC_ERROR_VERSION = -5,
    USER_SYNC_ERROR_SEND = -6,
    USER_SYNC_ERROR_TIMEOUT = -7,
    USER_SYNC_ERROR_RTU_NOT_CONNECTED = -8,
} user_sync_result_t;

/* User record for sync (fixed-size for serialization) */
typedef struct __attribute__((packed)) {
    char username[32];          /* Username (null-terminated) */
    char password_hash[64];     /* DJB2 hash with salt (hex string) */
    uint8_t role;               /* user_role_t value */
    uint8_t flags;              /* Bit 0: active, Bit 1: synced_from_controller */
    uint8_t reserved[2];        /* Padding for alignment */
} user_sync_record_t;

/* User sync header (sent before user records) */
typedef struct __attribute__((packed)) {
    uint8_t version;            /* Protocol version (USER_SYNC_VERSION) */
    uint8_t user_count;         /* Number of user records following */
    uint16_t checksum;          /* CRC16-CCITT of payload (after header) */
    uint32_t timestamp;         /* Unix timestamp of sync */
    uint32_t nonce;             /* Random nonce for replay protection */
} user_sync_header_t;

/* Complete sync payload structure */
typedef struct __attribute__((packed)) {
    user_sync_header_t header;
    user_sync_record_t users[USER_SYNC_MAX_USERS];
} user_sync_payload_t;

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
                                      user_sync_result_t result,
                                      void *ctx);

/* ============== Hash Functions ============== */

/**
 * Hash password using DJB2 algorithm with salt.
 * Matches the RTU implementation for compatibility.
 *
 * @param password      Plain text password
 * @param hash_out      Output buffer for hex hash string (min 64 bytes)
 * @param hash_out_size Size of output buffer
 * @return 0 on success, -1 on error
 */
int user_sync_hash_password(const char *password,
                            char *hash_out,
                            size_t hash_out_size);

/**
 * Verify password against stored hash.
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
 *
 * @param data  Data buffer
 * @param len   Data length
 * @return CRC16 checksum
 */
uint16_t user_sync_crc16(const uint8_t *data, size_t len);

/**
 * Serialize users into sync payload.
 *
 * @param users         Array of user records
 * @param user_count    Number of users
 * @param payload       Output payload buffer
 * @return USER_SYNC_OK on success, error code otherwise
 */
user_sync_result_t user_sync_serialize(const user_t *users,
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
 * @return USER_SYNC_OK on success, error code otherwise
 */
user_sync_result_t user_sync_deserialize(const user_sync_payload_t *payload,
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
 * @return USER_SYNC_OK on success
 */
user_sync_result_t user_sync_to_rtu(user_sync_manager_t *manager,
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
typedef struct {
    uint32_t total_syncs;
    uint32_t successful_syncs;
    uint32_t failed_syncs;
    uint64_t last_sync_time_ms;
    char last_sync_rtu[WTC_MAX_STATION_NAME];
} user_sync_stats_t;

wtc_result_t user_sync_get_stats(user_sync_manager_t *manager,
                                  user_sync_stats_t *stats);

#ifdef __cplusplus
}
#endif

#endif /* WTC_USER_SYNC_H */
