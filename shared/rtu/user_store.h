/**
 * @file user_store.h
 * @brief RTU-side user credential storage and authentication
 *
 * This module handles:
 * - Receiving user sync payloads from the Controller via PROFINET
 * - Storing user credentials in non-volatile memory (EEPROM/flash)
 * - Authenticating local TUI/HMI login attempts
 * - Role-based access control for local operations
 *
 * USAGE:
 * 1. Call user_store_init() at RTU startup
 * 2. Register user_store_receive_sync() as PROFINET record handler for 0xF840
 * 3. Call user_store_authenticate() when user attempts local login
 * 4. Call user_store_check_access() before privileged operations
 *
 * STORAGE CONSTRAINTS:
 * - Maximum 16 users (USER_SYNC_MAX_USERS)
 * - Each record: 100 bytes (username + hash + metadata)
 * - Total NV requirement: ~1.6KB + header
 *
 * THREAD SAFETY:
 * - All functions are NOT thread-safe by default
 * - RTU should serialize access or provide external locking
 *
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef RTU_USER_STORE_H
#define RTU_USER_STORE_H

#include "user_sync_protocol.h"
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============== Configuration ============== */

/**
 * @brief NV storage backend interface
 *
 * RTU must implement these functions for their specific hardware.
 * Typically wraps EEPROM, SPI flash, or filesystem operations.
 */
typedef struct {
    /**
     * Read data from non-volatile storage
     * @param offset  Byte offset from start of user store region
     * @param data    Output buffer
     * @param len     Number of bytes to read
     * @return        0 on success, -1 on error
     */
    int (*read)(uint32_t offset, void *data, size_t len);

    /**
     * Write data to non-volatile storage
     * @param offset  Byte offset from start of user store region
     * @param data    Data to write
     * @param len     Number of bytes to write
     * @return        0 on success, -1 on error
     */
    int (*write)(uint32_t offset, const void *data, size_t len);

    /**
     * Flush/sync pending writes (optional, can be NULL)
     * @return        0 on success, -1 on error
     */
    int (*flush)(void);
} user_store_nv_ops_t;

/**
 * @brief User store configuration
 */
typedef struct {
    /** Non-volatile storage operations (required) */
    const user_store_nv_ops_t *nv_ops;

    /** Enable replay protection (track nonce) */
    bool enable_replay_protection;

    /** Maximum age of sync payload in seconds (0 = no limit) */
    uint32_t max_sync_age_sec;
} user_store_config_t;

/* ============== Initialization ============== */

/**
 * @brief Initialize user store
 *
 * Loads existing users from NV storage if present.
 * Must be called before any other user_store functions.
 *
 * @param config  Configuration (NULL for defaults with no NV persistence)
 * @return        USER_SYNC_OK on success, error code on failure
 */
user_sync_result_t user_store_init(const user_store_config_t *config);

/**
 * @brief Shutdown user store
 *
 * Flushes any pending writes and releases resources.
 */
void user_store_shutdown(void);

/**
 * @brief Check if user store is initialized
 *
 * @return  true if initialized, false otherwise
 */
bool user_store_is_initialized(void);

/* ============== Sync Reception ============== */

/**
 * @brief Receive and process user sync payload from Controller
 *
 * This is the main entry point for PROFINET record handler.
 * Validates payload, updates user storage, persists to NV memory.
 *
 * @param payload   Raw payload data from PROFINET
 * @param len       Payload length in bytes
 * @return          USER_SYNC_OK on success, error code on failure
 *
 * Error conditions:
 * - USER_SYNC_ERR_INVALID_PARAM: NULL pointer or zero length
 * - USER_SYNC_ERR_VERSION_MISMATCH: Unsupported protocol version
 * - USER_SYNC_ERR_CHECKSUM: CRC validation failed
 * - USER_SYNC_ERR_REPLAY: Nonce less than or equal to last seen
 * - USER_SYNC_ERR_STORAGE_WRITE: Failed to persist to NV memory
 */
user_sync_result_t user_store_receive_sync(const void *payload, size_t len);

/* ============== Authentication ============== */

/**
 * @brief Authenticate user with password
 *
 * Validates username exists, account is active, and password hash matches.
 * On success, returns the user's role for access control.
 *
 * SECURITY: This function uses constant-time comparison for password hashes
 * to prevent timing attacks.
 *
 * @param username  Username to authenticate
 * @param password  Plain text password (will be hashed internally)
 * @param role_out  Output: user's role if authentication succeeds (can be NULL)
 * @return          USER_SYNC_OK on success, error code on failure
 *
 * Error conditions:
 * - USER_SYNC_ERR_INVALID_PARAM: NULL username or password
 * - USER_SYNC_ERR_USER_NOT_FOUND: Username not in storage
 * - USER_SYNC_ERR_INACTIVE: User account is disabled
 * - USER_SYNC_ERR_AUTH_FAILED: Password hash mismatch
 */
user_sync_result_t user_store_authenticate(const char *username,
                                            const char *password,
                                            user_sync_role_t *role_out);

/**
 * @brief Check if user has sufficient role for operation
 *
 * @param username       Username to check
 * @param required_role  Minimum required role
 * @return               true if user exists and role >= required_role
 */
bool user_store_check_access(const char *username,
                              user_sync_role_t required_role);

/* ============== User Query ============== */

/**
 * @brief Get number of users in storage
 *
 * @return  Number of stored users (0 to USER_SYNC_MAX_USERS)
 */
int user_store_count(void);

/**
 * @brief Check if username exists in storage
 *
 * @param username  Username to check
 * @return          true if user exists (regardless of active status)
 */
bool user_store_exists(const char *username);

/**
 * @brief Get user's role
 *
 * @param username  Username to query
 * @param role_out  Output: user's role
 * @return          USER_SYNC_OK on success, USER_SYNC_ERR_USER_NOT_FOUND if not found
 */
user_sync_result_t user_store_get_role(const char *username,
                                        user_sync_role_t *role_out);

/**
 * @brief Check if user account is active
 *
 * @param username  Username to check
 * @return          true if user exists and is active
 */
bool user_store_is_active(const char *username);

/* ============== Statistics ============== */

/**
 * @brief User store statistics
 */
typedef struct {
    /** Number of users in storage */
    uint8_t user_count;

    /** Number of active users */
    uint8_t active_count;

    /** Total sync packets received */
    uint32_t sync_count;

    /** Last successful sync timestamp */
    uint32_t last_sync_time;

    /** Last sync nonce (for replay detection) */
    uint32_t last_sync_nonce;

    /** Authentication attempts since startup */
    uint32_t auth_attempts;

    /** Successful authentications since startup */
    uint32_t auth_successes;

    /** Failed authentications since startup */
    uint32_t auth_failures;
} user_store_stats_t;

/**
 * @brief Get user store statistics
 *
 * @param stats  Output statistics structure
 * @return       USER_SYNC_OK on success
 */
user_sync_result_t user_store_get_stats(user_store_stats_t *stats);

/**
 * @brief Reset authentication counters
 *
 * Resets auth_attempts, auth_successes, auth_failures to zero.
 * Does NOT reset sync_count or last_sync_time.
 */
void user_store_reset_auth_stats(void);

/* ============== Debug/Test ============== */

/**
 * @brief Clear all users from storage
 *
 * WARNING: Destructive operation. Removes all synced users.
 * Primarily for testing or factory reset scenarios.
 *
 * @return  USER_SYNC_OK on success
 */
user_sync_result_t user_store_clear(void);

/**
 * @brief Dump user store contents for debugging
 *
 * Prints user list to provided output function.
 * Does NOT print password hashes for security.
 *
 * @param print_fn  Output function (printf-compatible signature)
 */
void user_store_dump(int (*print_fn)(const char *fmt, ...));

#ifdef __cplusplus
}
#endif

#endif /* RTU_USER_STORE_H */
