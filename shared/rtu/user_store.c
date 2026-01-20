/**
 * @file user_store.c
 * @brief RTU-side user credential storage and authentication implementation
 *
 * This module provides local authentication capabilities for RTU TUI/HMI
 * using credentials synced from the SCADA Controller via PROFINET.
 *
 * MEMORY LAYOUT:
 * - All user storage is statically allocated (no malloc after init)
 * - NV storage format: [header][user0][user1]...[userN]
 *
 * SECURITY NOTES:
 * - Password hash comparison uses constant-time algorithm
 * - Hashes never logged or exposed via debug functions
 * - Failed auth attempts are rate-limited by caller (not this module)
 *
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "user_store.h"
#include <string.h>
#include <stdio.h>

/* ============== Internal Structures ============== */

/** NV storage header - persisted at offset 0 */
typedef struct __attribute__((packed)) {
    uint32_t magic;         /* 0x55535253 = "USRS" */
    uint8_t  version;       /* Storage format version */
    uint8_t  user_count;    /* Number of valid users */
    uint16_t reserved;      /* Alignment padding */
    uint32_t last_nonce;    /* Last sync nonce for replay protection */
    uint32_t last_sync;     /* Last sync timestamp */
} nv_header_t;

#define NV_MAGIC            0x55535253  /* "USRS" in little-endian */
#define NV_VERSION          1
#define NV_HEADER_SIZE      sizeof(nv_header_t)
#define NV_USER_OFFSET      NV_HEADER_SIZE
#define NV_USER_SIZE        sizeof(user_sync_record_t)

/** Runtime user store state */
typedef struct {
    bool initialized;

    /* Configuration */
    user_store_config_t config;

    /* User storage (RAM mirror of NV) */
    user_sync_record_t users[USER_SYNC_MAX_USERS];
    uint8_t user_count;

    /* Replay protection */
    uint32_t last_nonce;
    uint32_t last_sync_time;

    /* Statistics */
    uint32_t sync_count;
    uint32_t auth_attempts;
    uint32_t auth_successes;
    uint32_t auth_failures;
} user_store_state_t;

/* ============== Static State ============== */

static user_store_state_t g_store = {0};

/* ============== Internal Functions ============== */

/**
 * Constant-time memory comparison
 * Compares all bytes regardless of early mismatch to prevent timing attacks.
 */
static bool secure_memcmp(const void *a, const void *b, size_t len) {
    const volatile uint8_t *pa = (const volatile uint8_t *)a;
    const volatile uint8_t *pb = (const volatile uint8_t *)b;
    volatile uint8_t result = 0;

    for (size_t i = 0; i < len; i++) {
        result |= pa[i] ^ pb[i];
    }

    return result == 0;
}

/**
 * Constant-time string comparison for password hashes
 */
static bool secure_strcmp(const char *a, const char *b) {
    size_t len_a = strlen(a);
    size_t len_b = strlen(b);
    size_t max_len = (len_a > len_b) ? len_a : len_b;

    /* Always compare same number of bytes */
    volatile uint8_t result = (len_a != len_b) ? 1 : 0;

    for (size_t i = 0; i < max_len; i++) {
        uint8_t ca = (i < len_a) ? (uint8_t)a[i] : 0;
        uint8_t cb = (i < len_b) ? (uint8_t)b[i] : 0;
        result |= ca ^ cb;
    }

    return result == 0;
}

/**
 * Find user by username
 * Returns index or -1 if not found
 */
static int find_user(const char *username) {
    if (!username) {
        return -1;
    }

    for (int i = 0; i < g_store.user_count; i++) {
        if (strncmp(g_store.users[i].username, username,
                    USER_SYNC_USERNAME_LEN) == 0) {
            return i;
        }
    }
    return -1;
}

/**
 * Format password hash string from password
 * Output format: "DJB2:%08X:%08X"
 */
static void format_password_hash(const char *password, char *hash_out) {
    uint32_t salt_hash, pass_hash;
    user_sync_hash_with_salt(password, &salt_hash, &pass_hash);
    snprintf(hash_out, USER_SYNC_HASH_LEN, "DJB2:%08X:%08X",
             (unsigned int)salt_hash, (unsigned int)pass_hash);
}

/**
 * Load users from NV storage
 */
static user_sync_result_t load_from_nv(void) {
    if (!g_store.config.nv_ops || !g_store.config.nv_ops->read) {
        /* No NV backend - start with empty store */
        return USER_SYNC_OK;
    }

    nv_header_t header;
    if (g_store.config.nv_ops->read(0, &header, sizeof(header)) != 0) {
        /* Read failed - start with empty store */
        return USER_SYNC_OK;
    }

    /* Validate header */
    if (header.magic != NV_MAGIC || header.version != NV_VERSION) {
        /* Invalid or no data - start with empty store */
        return USER_SYNC_OK;
    }

    /* Sanity check user count */
    if (header.user_count > USER_SYNC_MAX_USERS) {
        header.user_count = USER_SYNC_MAX_USERS;
    }

    /* Load users */
    size_t user_data_size = (size_t)header.user_count * NV_USER_SIZE;
    if (user_data_size > 0) {
        if (g_store.config.nv_ops->read(NV_USER_OFFSET, g_store.users,
                                         user_data_size) != 0) {
            return USER_SYNC_ERR_STORAGE_WRITE;
        }
    }

    g_store.user_count = header.user_count;
    g_store.last_nonce = header.last_nonce;
    g_store.last_sync_time = header.last_sync;

    return USER_SYNC_OK;
}

/**
 * Save users to NV storage
 */
static user_sync_result_t save_to_nv(void) {
    if (!g_store.config.nv_ops || !g_store.config.nv_ops->write) {
        /* No NV backend - RAM only */
        return USER_SYNC_OK;
    }

    /* Prepare header */
    nv_header_t header = {
        .magic = NV_MAGIC,
        .version = NV_VERSION,
        .user_count = g_store.user_count,
        .reserved = 0,
        .last_nonce = g_store.last_nonce,
        .last_sync = g_store.last_sync_time,
    };

    /* Write header */
    if (g_store.config.nv_ops->write(0, &header, sizeof(header)) != 0) {
        return USER_SYNC_ERR_STORAGE_WRITE;
    }

    /* Write users */
    size_t user_data_size = (size_t)g_store.user_count * NV_USER_SIZE;
    if (user_data_size > 0) {
        if (g_store.config.nv_ops->write(NV_USER_OFFSET, g_store.users,
                                          user_data_size) != 0) {
            return USER_SYNC_ERR_STORAGE_WRITE;
        }
    }

    /* Flush if supported */
    if (g_store.config.nv_ops->flush) {
        g_store.config.nv_ops->flush();
    }

    return USER_SYNC_OK;
}

/* ============== Public API Implementation ============== */

user_sync_result_t user_store_init(const user_store_config_t *config) {
    /* Clear state */
    memset(&g_store, 0, sizeof(g_store));

    /* Apply configuration */
    if (config) {
        g_store.config = *config;
    }

    /* Load from NV if available */
    user_sync_result_t result = load_from_nv();
    if (result != USER_SYNC_OK) {
        return result;
    }

    g_store.initialized = true;
    return USER_SYNC_OK;
}

void user_store_shutdown(void) {
    if (g_store.initialized) {
        /* Final save to NV */
        save_to_nv();
    }
    memset(&g_store, 0, sizeof(g_store));
}

bool user_store_is_initialized(void) {
    return g_store.initialized;
}

user_sync_result_t user_store_receive_sync(const void *payload, size_t len) {
    if (!g_store.initialized) {
        return USER_SYNC_ERR_INVALID_PARAM;
    }

    if (!payload || len < sizeof(user_sync_header_t)) {
        return USER_SYNC_ERR_INVALID_PARAM;
    }

    const user_sync_payload_t *sync = (const user_sync_payload_t *)payload;

    /* Version check */
    if (sync->header.version != USER_SYNC_PROTOCOL_VERSION) {
        return USER_SYNC_ERR_VERSION_MISMATCH;
    }

    /* User count sanity */
    if (sync->header.user_count > USER_SYNC_MAX_USERS) {
        return USER_SYNC_ERR_INVALID_PARAM;
    }

    /* Verify payload size */
    size_t expected_size = user_sync_payload_size(sync->header.user_count);
    if (len < expected_size) {
        return USER_SYNC_ERR_INVALID_PARAM;
    }

    /* Verify CRC */
    size_t user_data_size = (size_t)sync->header.user_count * sizeof(user_sync_record_t);
    uint16_t computed_crc = user_sync_crc16_ccitt(
        (const uint8_t *)sync->users, user_data_size);
    if (computed_crc != sync->header.checksum) {
        return USER_SYNC_ERR_CHECKSUM;
    }

    /* Replay protection */
    if (g_store.config.enable_replay_protection) {
        if (sync->header.nonce <= g_store.last_nonce) {
            return USER_SYNC_ERR_REPLAY;
        }
    }

    /* Age check */
    if (g_store.config.max_sync_age_sec > 0) {
        /* Note: RTU would need access to current time for this check */
        /* For now, we trust the controller's timestamp */
    }

    /* Copy users to storage */
    memcpy(g_store.users, sync->users,
           (size_t)sync->header.user_count * sizeof(user_sync_record_t));
    g_store.user_count = sync->header.user_count;
    g_store.last_nonce = sync->header.nonce;
    g_store.last_sync_time = sync->header.timestamp;
    g_store.sync_count++;

    /* Persist to NV */
    user_sync_result_t result = save_to_nv();
    if (result != USER_SYNC_OK) {
        return result;
    }

    return USER_SYNC_OK;
}

user_sync_result_t user_store_authenticate(const char *username,
                                            const char *password,
                                            user_sync_role_t *role_out) {
    if (!g_store.initialized) {
        return USER_SYNC_ERR_INVALID_PARAM;
    }

    if (!username || !password) {
        return USER_SYNC_ERR_INVALID_PARAM;
    }

    g_store.auth_attempts++;

    /* Find user */
    int idx = find_user(username);
    if (idx < 0) {
        g_store.auth_failures++;
        return USER_SYNC_ERR_USER_NOT_FOUND;
    }

    /* Check if active */
    if (!(g_store.users[idx].flags & USER_FLAG_ACTIVE)) {
        g_store.auth_failures++;
        return USER_SYNC_ERR_INACTIVE;
    }

    /* Compute hash of provided password */
    char computed_hash[USER_SYNC_HASH_LEN];
    format_password_hash(password, computed_hash);

    /* Constant-time comparison */
    if (!secure_strcmp(computed_hash, g_store.users[idx].password_hash)) {
        g_store.auth_failures++;
        return USER_SYNC_ERR_AUTH_FAILED;
    }

    /* Success */
    g_store.auth_successes++;
    if (role_out) {
        *role_out = (user_sync_role_t)g_store.users[idx].role;
    }

    return USER_SYNC_OK;
}

bool user_store_check_access(const char *username,
                              user_sync_role_t required_role) {
    if (!g_store.initialized || !username) {
        return false;
    }

    int idx = find_user(username);
    if (idx < 0) {
        return false;
    }

    if (!(g_store.users[idx].flags & USER_FLAG_ACTIVE)) {
        return false;
    }

    return user_sync_role_sufficient(
        (user_sync_role_t)g_store.users[idx].role, required_role);
}

int user_store_count(void) {
    return g_store.initialized ? g_store.user_count : 0;
}

bool user_store_exists(const char *username) {
    if (!g_store.initialized) {
        return false;
    }
    return find_user(username) >= 0;
}

user_sync_result_t user_store_get_role(const char *username,
                                        user_sync_role_t *role_out) {
    if (!g_store.initialized || !username || !role_out) {
        return USER_SYNC_ERR_INVALID_PARAM;
    }

    int idx = find_user(username);
    if (idx < 0) {
        return USER_SYNC_ERR_USER_NOT_FOUND;
    }

    *role_out = (user_sync_role_t)g_store.users[idx].role;
    return USER_SYNC_OK;
}

bool user_store_is_active(const char *username) {
    if (!g_store.initialized || !username) {
        return false;
    }

    int idx = find_user(username);
    if (idx < 0) {
        return false;
    }

    return (g_store.users[idx].flags & USER_FLAG_ACTIVE) != 0;
}

user_sync_result_t user_store_get_stats(user_store_stats_t *stats) {
    if (!stats) {
        return USER_SYNC_ERR_INVALID_PARAM;
    }

    memset(stats, 0, sizeof(*stats));

    if (!g_store.initialized) {
        return USER_SYNC_OK;
    }

    stats->user_count = g_store.user_count;

    /* Count active users */
    for (int i = 0; i < g_store.user_count; i++) {
        if (g_store.users[i].flags & USER_FLAG_ACTIVE) {
            stats->active_count++;
        }
    }

    stats->sync_count = g_store.sync_count;
    stats->last_sync_time = g_store.last_sync_time;
    stats->last_sync_nonce = g_store.last_nonce;
    stats->auth_attempts = g_store.auth_attempts;
    stats->auth_successes = g_store.auth_successes;
    stats->auth_failures = g_store.auth_failures;

    return USER_SYNC_OK;
}

void user_store_reset_auth_stats(void) {
    g_store.auth_attempts = 0;
    g_store.auth_successes = 0;
    g_store.auth_failures = 0;
}

user_sync_result_t user_store_clear(void) {
    if (!g_store.initialized) {
        return USER_SYNC_ERR_INVALID_PARAM;
    }

    memset(g_store.users, 0, sizeof(g_store.users));
    g_store.user_count = 0;

    return save_to_nv();
}

void user_store_dump(int (*print_fn)(const char *fmt, ...)) {
    if (!print_fn || !g_store.initialized) {
        return;
    }

    print_fn("User Store: %d users\n", g_store.user_count);
    print_fn("Last sync: nonce=%u time=%u\n",
             (unsigned)g_store.last_nonce, (unsigned)g_store.last_sync_time);
    print_fn("Auth stats: attempts=%u success=%u fail=%u\n",
             (unsigned)g_store.auth_attempts,
             (unsigned)g_store.auth_successes,
             (unsigned)g_store.auth_failures);
    print_fn("---\n");

    for (int i = 0; i < g_store.user_count; i++) {
        const user_sync_record_t *u = &g_store.users[i];
        print_fn("[%d] %s role=%s active=%s\n",
                 i,
                 u->username,
                 user_sync_role_str((user_sync_role_t)u->role),
                 (u->flags & USER_FLAG_ACTIVE) ? "yes" : "no");
    }
}
