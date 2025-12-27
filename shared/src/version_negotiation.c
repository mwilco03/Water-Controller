/**
 * @file version_negotiation.c
 * @brief Protocol version negotiation implementation
 *
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "version_negotiation.h"
#include <string.h>
#include <stdio.h>
#include <time.h>

/* Build-time version info - should be set by build system */
#ifndef WTC_BUILD_VERSION
#define WTC_BUILD_VERSION "1.0.0-dev"
#endif

#ifndef WTC_BUILD_TIMESTAMP
#define WTC_BUILD_TIMESTAMP 0
#endif

void wtc_get_version_info(wtc_version_info_t *info) {
    if (!info) return;

    memset(info, 0, sizeof(*info));

    info->protocol_version = WTC_PROTOCOL_VERSION;
    info->shm_version = WTC_SHM_INTERFACE_VERSION;
    info->cyclic_version = WTC_CYCLIC_DATA_VERSION;
    info->state_version = WTC_STATE_FORMAT_VERSION;
    info->alarm_version = WTC_ALARM_FORMAT_VERSION;
    info->capabilities = WTC_CAPABILITIES_CURRENT;

    strncpy(info->build_version, WTC_BUILD_VERSION,
            sizeof(info->build_version) - 1);
    info->build_timestamp = WTC_BUILD_TIMESTAMP;
}

bool wtc_check_compatibility(const wtc_version_info_t *local,
                              const wtc_version_info_t *remote,
                              version_check_result_t *result) {
    if (!local || !remote || !result) {
        return false;
    }

    memset(result, 0, sizeof(*result));
    result->result = VERSION_COMPATIBLE;

    /* Check protocol version */
    uint8_t local_major = wtc_protocol_major(local->protocol_version);
    uint8_t remote_major = wtc_protocol_major(remote->protocol_version);
    uint8_t local_minor = wtc_protocol_minor(local->protocol_version);
    uint8_t remote_minor = wtc_protocol_minor(remote->protocol_version);

    if (local_major != remote_major) {
        result->protocol_ok = false;
        result->result = VERSION_MAJOR_MISMATCH;
        snprintf(result->message, sizeof(result->message),
                 "Protocol major version mismatch: local=%d remote=%d",
                 local_major, remote_major);
        return false;
    }

    if (local_minor != remote_minor) {
        result->protocol_ok = true;  /* Still compatible */
        if (result->result == VERSION_COMPATIBLE) {
            result->result = VERSION_MINOR_MISMATCH;
        }
    } else {
        result->protocol_ok = true;
    }

    /* Check shared memory version */
    result->shm_ok = (local->shm_version == remote->shm_version);
    if (!result->shm_ok) {
        result->result = VERSION_FORMAT_MISMATCH;
        snprintf(result->message, sizeof(result->message),
                 "Shared memory version mismatch: local=%d remote=%d",
                 local->shm_version, remote->shm_version);
        return false;
    }

    /* Check cyclic data version */
    result->cyclic_ok = (local->cyclic_version == remote->cyclic_version);
    if (!result->cyclic_ok) {
        result->result = VERSION_FORMAT_MISMATCH;
        snprintf(result->message, sizeof(result->message),
                 "Cyclic data version mismatch: local=%d remote=%d",
                 local->cyclic_version, remote->cyclic_version);
        return false;
    }

    /* Check state format version */
    result->state_ok = (local->state_version == remote->state_version);
    if (!result->state_ok) {
        result->result = VERSION_FORMAT_MISMATCH;
        snprintf(result->message, sizeof(result->message),
                 "State format version mismatch: local=%d remote=%d",
                 local->state_version, remote->state_version);
        return false;
    }

    /* Check alarm format version */
    result->alarm_ok = (local->alarm_version == remote->alarm_version);
    if (!result->alarm_ok) {
        result->result = VERSION_FORMAT_MISMATCH;
        snprintf(result->message, sizeof(result->message),
                 "Alarm format version mismatch: local=%d remote=%d",
                 local->alarm_version, remote->alarm_version);
        return false;
    }

    /* Check required capabilities */
    uint32_t required = WTC_CAPABILITIES_REQUIRED;
    uint32_t remote_caps = remote->capabilities;
    result->missing_caps = required & ~remote_caps;

    if (result->missing_caps != 0) {
        result->result = VERSION_CAPABILITY_MISSING;
        snprintf(result->message, sizeof(result->message),
                 "Missing required capabilities: 0x%08X",
                 result->missing_caps);
        return false;
    }

    /* All checks passed */
    if (result->result == VERSION_COMPATIBLE) {
        snprintf(result->message, sizeof(result->message),
                 "Compatible: protocol %d.%d, all formats match",
                 local_major, local_minor);
    } else if (result->result == VERSION_MINOR_MISMATCH) {
        snprintf(result->message, sizeof(result->message),
                 "Compatible with minor version difference: %d.%d vs %d.%d",
                 local_major, local_minor, remote_major, remote_minor);
    }

    return true;
}

int wtc_version_to_string(const wtc_version_info_t *info,
                           char *buffer, size_t size) {
    if (!info || !buffer || size == 0) {
        return 0;
    }

    return snprintf(buffer, size,
                    "Protocol: %d.%d, SHM: %d, Cyclic: %d, State: %d, Alarm: %d, "
                    "Caps: 0x%08X, Build: %s",
                    wtc_protocol_major(info->protocol_version),
                    wtc_protocol_minor(info->protocol_version),
                    info->shm_version,
                    info->cyclic_version,
                    info->state_version,
                    info->alarm_version,
                    info->capabilities,
                    info->build_version);
}

const char *wtc_capability_name(uint32_t cap) {
    switch (cap) {
        case WTC_CAP_AUTHORITY_HANDOFF: return "AUTHORITY_HANDOFF";
        case WTC_CAP_STATE_RECONCILE:   return "STATE_RECONCILE";
        case WTC_CAP_5BYTE_SENSOR:      return "5BYTE_SENSOR";
        case WTC_CAP_ALARM_ISA18:       return "ALARM_ISA18";
        case WTC_CAP_FAILOVER:          return "FAILOVER";
        case WTC_CAP_CASCADE_PID:       return "CASCADE_PID";
        case WTC_CAP_ACYCLIC_RECORDS:   return "ACYCLIC_RECORDS";
        case WTC_CAP_USER_SYNC:         return "USER_SYNC";
        default:                        return "UNKNOWN";
    }
}
