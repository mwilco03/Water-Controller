/**
 * @file version_negotiation.h
 * @brief Protocol version negotiation between Controller and RTU
 *
 * This module ensures runtime compatibility checking between Controller
 * and RTU, preventing silent failures due to version mismatches.
 *
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef SHARED_VERSION_NEGOTIATION_H
#define SHARED_VERSION_NEGOTIATION_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================
 * Version Constants
 * ============================================================================
 * These must match between Controller and RTU for compatibility.
 * Increment appropriately on breaking changes.
 */

/* Protocol version - major.minor format in single uint16_t */
#define WTC_PROTOCOL_VERSION_MAJOR   1
#define WTC_PROTOCOL_VERSION_MINOR   0
#define WTC_PROTOCOL_VERSION         ((WTC_PROTOCOL_VERSION_MAJOR << 8) | WTC_PROTOCOL_VERSION_MINOR)

/* Shared memory interface version */
#define WTC_SHM_INTERFACE_VERSION    1

/* Cyclic data format version */
#define WTC_CYCLIC_DATA_VERSION      1

/* State reconciliation format version */
#define WTC_STATE_FORMAT_VERSION     1

/* Alarm format version */
#define WTC_ALARM_FORMAT_VERSION     1

/* ============================================================================
 * Capability Flags
 * ============================================================================
 * Features supported by this version.
 */

#define WTC_CAP_AUTHORITY_HANDOFF    (1 << 0)  /* Authority handoff protocol */
#define WTC_CAP_STATE_RECONCILE      (1 << 1)  /* State reconciliation */
#define WTC_CAP_5BYTE_SENSOR         (1 << 2)  /* 5-byte sensor format with quality */
#define WTC_CAP_ALARM_ISA18          (1 << 3)  /* ISA-18.2 alarm model */
#define WTC_CAP_FAILOVER             (1 << 4)  /* Failover support */
#define WTC_CAP_CASCADE_PID          (1 << 5)  /* Cascade PID control */
#define WTC_CAP_ACYCLIC_RECORDS      (1 << 6)  /* PROFINET acyclic records */
#define WTC_CAP_USER_SYNC            (1 << 7)  /* User synchronization */

/* All capabilities supported by this version */
#define WTC_CAPABILITIES_CURRENT     (WTC_CAP_AUTHORITY_HANDOFF | \
                                      WTC_CAP_STATE_RECONCILE | \
                                      WTC_CAP_5BYTE_SENSOR | \
                                      WTC_CAP_ALARM_ISA18 | \
                                      WTC_CAP_FAILOVER | \
                                      WTC_CAP_CASCADE_PID | \
                                      WTC_CAP_ACYCLIC_RECORDS | \
                                      WTC_CAP_USER_SYNC)

/* Minimum required capabilities for connection */
#define WTC_CAPABILITIES_REQUIRED    (WTC_CAP_5BYTE_SENSOR)

/* ============================================================================
 * Version Info Structure
 * ============================================================================
 */

/**
 * @brief Version information exchanged during connection
 */
typedef struct {
    uint16_t protocol_version;    /* Major.minor as (major << 8 | minor) */
    uint16_t shm_version;         /* Shared memory interface version */
    uint16_t cyclic_version;      /* Cyclic data format version */
    uint16_t state_version;       /* State reconciliation format version */
    uint16_t alarm_version;       /* Alarm format version */
    uint32_t capabilities;        /* Capability flags */
    char     build_version[32];   /* Build version string (e.g., "1.0.0-abc123") */
    uint32_t build_timestamp;     /* Unix timestamp of build */
} wtc_version_info_t;

/**
 * @brief Compatibility result
 */
typedef enum {
    VERSION_COMPATIBLE = 0,       /* Versions are compatible */
    VERSION_MINOR_MISMATCH = 1,   /* Minor version differs, backwards compatible */
    VERSION_MAJOR_MISMATCH = 2,   /* Major version differs, not compatible */
    VERSION_CAPABILITY_MISSING = 3, /* Required capability missing */
    VERSION_FORMAT_MISMATCH = 4,  /* Data format version mismatch */
} version_compat_t;

/**
 * @brief Compatibility check result with details
 */
typedef struct {
    version_compat_t result;      /* Overall compatibility result */
    bool protocol_ok;             /* Protocol version compatible */
    bool shm_ok;                  /* Shared memory version compatible */
    bool cyclic_ok;               /* Cyclic data format compatible */
    bool state_ok;                /* State format compatible */
    bool alarm_ok;                /* Alarm format compatible */
    uint32_t missing_caps;        /* Missing required capabilities */
    char message[128];            /* Human-readable compatibility message */
} version_check_result_t;

/* ============================================================================
 * Functions
 * ============================================================================
 */

/**
 * @brief Get current version info for this component
 *
 * @param[out] info  Version info to populate
 */
void wtc_get_version_info(wtc_version_info_t *info);

/**
 * @brief Check compatibility with remote version
 *
 * @param[in]  local   Local version info
 * @param[in]  remote  Remote version info
 * @param[out] result  Detailed compatibility result
 * @return true if compatible, false otherwise
 */
bool wtc_check_compatibility(const wtc_version_info_t *local,
                              const wtc_version_info_t *remote,
                              version_check_result_t *result);

/**
 * @brief Check if a specific capability is available
 *
 * @param[in] info  Version info to check
 * @param[in] cap   Capability flag to check
 * @return true if capability is available
 */
static inline bool wtc_has_capability(const wtc_version_info_t *info, uint32_t cap) {
    return info && (info->capabilities & cap) == cap;
}

/**
 * @brief Get protocol major version from combined version
 */
static inline uint8_t wtc_protocol_major(uint16_t version) {
    return (uint8_t)(version >> 8);
}

/**
 * @brief Get protocol minor version from combined version
 */
static inline uint8_t wtc_protocol_minor(uint16_t version) {
    return (uint8_t)(version & 0xFF);
}

/**
 * @brief Format version info as string
 *
 * @param[in]  info    Version info
 * @param[out] buffer  Output buffer
 * @param[in]  size    Buffer size
 * @return Number of characters written
 */
int wtc_version_to_string(const wtc_version_info_t *info,
                           char *buffer, size_t size);

/**
 * @brief Get capability name string
 */
const char *wtc_capability_name(uint32_t cap);

#ifdef __cplusplus
}
#endif

#endif /* SHARED_VERSION_NEGOTIATION_H */
