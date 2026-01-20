/**
 * @file user_sync_protocol.h
 * @brief Shared user sync protocol definitions for Water-Controller and Water-Treat
 *
 * This header defines the wire protocol for synchronizing user credentials
 * from the SCADA Controller to RTU devices via PROFINET acyclic data.
 *
 * PROTOCOL OVERVIEW:
 * - Controller sends user_sync_payload_t via PROFINET record write to index 0xF840
 * - RTU receives, validates CRC, stores users in non-volatile memory
 * - RTU uses stored credentials for local TUI/HMI authentication
 *
 * HASH FORMAT:
 * - Algorithm: DJB2 (hash = 5381, hash = ((hash << 5) + hash) + c)
 * - Salt: "NaCl4Life" prepended to password before hashing
 * - Wire format: "DJB2:%08X:%08X" (salt_hash:password_hash)
 *
 * IMPORTANT: Both Water-Controller and Water-Treat MUST use these definitions
 * to ensure protocol compatibility. Any changes require version bump.
 *
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef SHARED_USER_SYNC_PROTOCOL_H
#define SHARED_USER_SYNC_PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============== Protocol Constants ============== */

/** Protocol version - increment on breaking changes */
#define USER_SYNC_PROTOCOL_VERSION  1

/** PROFINET record index for user sync (vendor-specific range 0xF000-0xFFFF) */
#define USER_SYNC_RECORD_INDEX      0xF840

/** Maximum users per sync payload (RTU storage constraint) */
#define USER_SYNC_MAX_USERS         16

/** Username field length including null terminator */
#define USER_SYNC_USERNAME_LEN      32

/** Password hash field length including null terminator */
#define USER_SYNC_HASH_LEN          64

/** Salt string for DJB2 hashing - MUST match on both sides */
#define USER_SYNC_SALT              "NaCl4Life"

/** DJB2 initial hash value */
#define DJB2_INIT                   5381

/* ============== User Roles ============== */

/**
 * @brief User role levels for access control
 *
 * Roles are hierarchical: higher values have more permissions.
 * RTU enforces these for local TUI/HMI access.
 *
 * Note: When used with Water-Controller, these values MUST match
 * user_role_t in types.h. The guard prevents redefinition.
 */
#ifndef USER_ROLE_VIEWER
#define USER_ROLE_VIEWER    0   /**< Read-only access to status/alarms */
#define USER_ROLE_OPERATOR  1   /**< Can acknowledge alarms, basic control */
#define USER_ROLE_ENGINEER  2   /**< Can modify setpoints, tuning */
#define USER_ROLE_ADMIN     3   /**< Full access including user management */
#endif

/* Typedef for RTU code that doesn't have types.h */
#ifndef WTC_TYPES_H
typedef uint8_t user_sync_role_t;
#else
typedef user_role_t user_sync_role_t;
#endif

/* ============== User Record Flags ============== */

/** User account is active and can authenticate */
#define USER_FLAG_ACTIVE            0x01

/** User was synced from controller (vs local-only) */
#define USER_FLAG_SYNCED            0x02

/* ============== Wire Format Structures ============== */

/**
 * @brief User record for PROFINET transfer
 *
 * Fixed-size structure for wire serialization.
 * All fields are packed with no padding.
 */
typedef struct __attribute__((packed)) {
    /** Username (null-terminated, max 31 chars + null) */
    char username[USER_SYNC_USERNAME_LEN];

    /** Password hash in format "DJB2:%08X:%08X" */
    char password_hash[USER_SYNC_HASH_LEN];

    /** User role (user_sync_role_t value) */
    uint8_t role;

    /** Flags (USER_FLAG_ACTIVE, USER_FLAG_SYNCED) */
    uint8_t flags;

    /** Reserved for future use (alignment padding) */
    uint8_t reserved[2];
} user_sync_record_t;

/**
 * @brief Sync payload header
 *
 * Sent before user records. Contains metadata for validation.
 */
typedef struct __attribute__((packed)) {
    /** Protocol version (USER_SYNC_PROTOCOL_VERSION) */
    uint8_t version;

    /** Number of user records following (0 to USER_SYNC_MAX_USERS) */
    uint8_t user_count;

    /** CRC16-CCITT of user records (calculated over user data only) */
    uint16_t checksum;

    /** Unix timestamp when sync was initiated (seconds since epoch) */
    uint32_t timestamp;

    /** Random nonce for replay detection (RTU tracks last seen) */
    uint32_t nonce;
} user_sync_header_t;

/**
 * @brief Complete sync payload structure
 *
 * Total size: 12 + (100 * 16) = 1612 bytes max
 * Fits within PROFINET acyclic data limits.
 */
typedef struct __attribute__((packed)) {
    user_sync_header_t header;
    user_sync_record_t users[USER_SYNC_MAX_USERS];
} user_sync_payload_t;

/* ============== Result Codes ============== */

/**
 * @brief User sync operation result codes
 *
 * Negative values indicate errors.
 */
typedef enum {
    USER_SYNC_OK                    =  0,  /**< Operation successful */
    USER_SYNC_ERR_INVALID_PARAM     = -1,  /**< NULL pointer or invalid argument */
    USER_SYNC_ERR_VERSION_MISMATCH  = -2,  /**< Protocol version not supported */
    USER_SYNC_ERR_CHECKSUM          = -3,  /**< CRC validation failed */
    USER_SYNC_ERR_REPLAY            = -4,  /**< Nonce indicates replay attack */
    USER_SYNC_ERR_STORAGE_FULL      = -5,  /**< No room in NV storage */
    USER_SYNC_ERR_STORAGE_WRITE     = -6,  /**< Failed to persist to NV memory */
    USER_SYNC_ERR_USER_NOT_FOUND    = -7,  /**< Username not in storage */
    USER_SYNC_ERR_AUTH_FAILED       = -8,  /**< Password hash mismatch */
    USER_SYNC_ERR_INACTIVE          = -9,  /**< User account is disabled */
    USER_SYNC_ERR_INSUFFICIENT_ROLE = -10, /**< Role below required level */
} user_sync_result_t;

/* ============== Hash Functions ============== */

/**
 * @brief Compute DJB2 hash of a string
 *
 * Standard DJB2 algorithm with 32-bit overflow.
 * hash = 5381
 * for each char c: hash = ((hash << 5) + hash) + c
 *
 * @param str   Null-terminated string to hash
 * @return      32-bit hash value
 */
static inline uint32_t user_sync_djb2(const char *str) {
    uint32_t hash = DJB2_INIT;
    int c;
    while ((c = (unsigned char)*str++)) {
        hash = ((hash << 5) + hash) + (uint32_t)c;
    }
    return hash;
}

/**
 * @brief Compute salted DJB2 hash of password
 *
 * Computes: DJB2(salt) and DJB2(salt + password)
 * Both hashes are needed for the wire format.
 *
 * @param password      Plain text password
 * @param salt_hash_out Output: hash of salt alone
 * @param pass_hash_out Output: hash of salt+password
 */
static inline void user_sync_hash_with_salt(const char *password,
                                             uint32_t *salt_hash_out,
                                             uint32_t *pass_hash_out) {
    /* Hash the salt */
    uint32_t salt_hash = user_sync_djb2(USER_SYNC_SALT);
    if (salt_hash_out) {
        *salt_hash_out = salt_hash;
    }

    /* Continue hashing with password (salt already incorporated) */
    uint32_t hash = salt_hash;
    int c;
    const char *p = password;
    while ((c = (unsigned char)*p++)) {
        hash = ((hash << 5) + hash) + (uint32_t)c;
    }
    if (pass_hash_out) {
        *pass_hash_out = hash;
    }
}

/* ============== CRC16-CCITT ============== */

/**
 * @brief Compute CRC16-CCITT checksum
 *
 * Polynomial: 0x1021 (x^16 + x^12 + x^5 + 1)
 * Initial value: 0xFFFF
 * Used for payload integrity verification.
 *
 * @param data  Data buffer
 * @param len   Data length in bytes
 * @return      16-bit CRC value
 */
static inline uint16_t user_sync_crc16_ccitt(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int j = 0; j < 8; j++) {
            if (crc & 0x8000) {
                crc = (crc << 1) ^ 0x1021;
            } else {
                crc <<= 1;
            }
        }
    }
    return crc;
}

/* ============== Utility Functions ============== */

/**
 * @brief Get string representation of result code
 *
 * @param result  Result code
 * @return        Human-readable string
 */
static inline const char *user_sync_result_str(user_sync_result_t result) {
    switch (result) {
        case USER_SYNC_OK:                    return "OK";
        case USER_SYNC_ERR_INVALID_PARAM:     return "Invalid parameter";
        case USER_SYNC_ERR_VERSION_MISMATCH:  return "Version mismatch";
        case USER_SYNC_ERR_CHECKSUM:          return "Checksum error";
        case USER_SYNC_ERR_REPLAY:            return "Replay detected";
        case USER_SYNC_ERR_STORAGE_FULL:      return "Storage full";
        case USER_SYNC_ERR_STORAGE_WRITE:     return "Storage write failed";
        case USER_SYNC_ERR_USER_NOT_FOUND:    return "User not found";
        case USER_SYNC_ERR_AUTH_FAILED:       return "Authentication failed";
        case USER_SYNC_ERR_INACTIVE:          return "User inactive";
        case USER_SYNC_ERR_INSUFFICIENT_ROLE: return "Insufficient role";
        default:                               return "Unknown error";
    }
}

/**
 * @brief Get string representation of user role
 *
 * @param role  User role value
 * @return      Human-readable string
 */
static inline const char *user_sync_role_str(user_sync_role_t role) {
    switch (role) {
        case USER_ROLE_VIEWER:   return "Viewer";
        case USER_ROLE_OPERATOR: return "Operator";
        case USER_ROLE_ENGINEER: return "Engineer";
        case USER_ROLE_ADMIN:    return "Admin";
        default:                  return "Unknown";
    }
}

/**
 * @brief Check if role meets minimum requirement
 *
 * @param user_role      User's actual role
 * @param required_role  Minimum required role
 * @return               true if user_role >= required_role
 */
static inline bool user_sync_role_sufficient(user_sync_role_t user_role,
                                              user_sync_role_t required_role) {
    return (int)user_role >= (int)required_role;
}

/**
 * @brief Calculate payload size for given user count
 *
 * @param user_count  Number of users (0 to USER_SYNC_MAX_USERS)
 * @return            Total payload size in bytes
 */
static inline size_t user_sync_payload_size(uint8_t user_count) {
    return sizeof(user_sync_header_t) +
           ((size_t)user_count * sizeof(user_sync_record_t));
}

#ifdef __cplusplus
}
#endif

#endif /* SHARED_USER_SYNC_PROTOCOL_H */
