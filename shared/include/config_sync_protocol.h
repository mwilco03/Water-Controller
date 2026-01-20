/*
 * Water Treatment Controller - Configuration Sync Protocol
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Shared definitions for Controller ↔ RTU configuration synchronization.
 * Used by both Controller (sender) and RTU (receiver) implementations.
 *
 * PROFINET Record Index Allocation:
 *   0xF840 - User sync (see user_sync_protocol.h)
 *   0xF841 - Device configuration
 *   0xF842 - Sensor configuration
 *   0xF843 - Actuator configuration
 *   0xF844 - RTU status (RTU → Controller, read-only)
 *   0xF845 - Enrollment/binding
 *
 * Wire Format: All multi-byte values are big-endian (network byte order)
 * Checksum: CRC16-CCITT (polynomial 0x1021, init 0xFFFF)
 */

#ifndef CONFIG_SYNC_PROTOCOL_H
#define CONFIG_SYNC_PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============== Protocol Constants ============== */

#define CONFIG_SYNC_PROTOCOL_VERSION    1

/* PROFINET record indices */
#define CONFIG_SYNC_DEVICE_INDEX        0xF841
#define CONFIG_SYNC_SENSOR_INDEX        0xF842
#define CONFIG_SYNC_ACTUATOR_INDEX      0xF843
#define CONFIG_SYNC_STATUS_INDEX        0xF844
#define CONFIG_SYNC_ENROLLMENT_INDEX    0xF845

/* Maximum counts */
#define CONFIG_SYNC_MAX_SENSORS         16
#define CONFIG_SYNC_MAX_ACTUATORS       8
#define CONFIG_SYNC_MAX_NAME_LEN        16
#define CONFIG_SYNC_MAX_UNIT_LEN        8
#define CONFIG_SYNC_MAX_STATION_NAME    32
#define CONFIG_SYNC_TOKEN_LEN           64

/* Enrollment operations */
#define ENROLLMENT_OP_BIND              0x01
#define ENROLLMENT_OP_UNBIND            0x02
#define ENROLLMENT_OP_REBIND            0x03
#define ENROLLMENT_OP_STATUS            0x04

/* Enrollment magic number */
#define ENROLLMENT_MAGIC                0x454E524C  /* "ENRL" */

/* Authority modes */
#define AUTHORITY_MODE_AUTONOMOUS       0x00
#define AUTHORITY_MODE_SUPERVISED       0x01

/* ============== CRC16-CCITT (shared with user_sync_protocol.h) ============== */

#ifndef CRC16_CCITT_DEFINED
#define CRC16_CCITT_DEFINED

static inline uint16_t crc16_ccitt_update(uint16_t crc, uint8_t byte) {
    crc ^= (uint16_t)byte << 8;
    for (int i = 0; i < 8; i++) {
        if (crc & 0x8000) {
            crc = (crc << 1) ^ 0x1021;
        } else {
            crc <<= 1;
        }
    }
    return crc;
}

static inline uint16_t crc16_ccitt(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc = crc16_ccitt_update(crc, data[i]);
    }
    return crc;
}

#endif /* CRC16_CCITT_DEFINED */

/* ============== Device Configuration (0xF841) ============== */

/*
 * Device configuration packet sent from Controller to RTU.
 * Contains global RTU settings and metadata.
 *
 * Wire format (52 bytes):
 *   version:u8 flags:u8 crc16:u16 timestamp:u32
 *   station_name:char[32]
 *   sensor_count:u16 actuator_count:u16
 *   authority_mode:u8 reserved:u8 watchdog_ms:u32
 */
typedef struct __attribute__((packed)) {
    uint8_t version;                              /* Protocol version (1) */
    uint8_t flags;                                /* Bit 0: config_changed, Bit 1: force_apply */
    uint16_t crc16;                               /* CRC16 of payload (after this field) */
    uint32_t config_timestamp;                    /* Unix timestamp of config version */
    char station_name[CONFIG_SYNC_MAX_STATION_NAME];  /* RTU station name */
    uint16_t sensor_count;                        /* Expected sensor count */
    uint16_t actuator_count;                      /* Expected actuator count */
    uint8_t authority_mode;                       /* AUTHORITY_MODE_* */
    uint8_t reserved;                             /* Padding */
    uint32_t watchdog_ms;                         /* Watchdog timeout in ms */
} device_config_payload_t;

/* ============== Sensor Configuration (0xF842) ============== */

/*
 * Single sensor configuration entry.
 *
 * Wire format (42 bytes per entry):
 *   slot:u8 type:u8 name:char[16] unit:char[8]
 *   scale_min:f32 scale_max:f32 alarm_low:f32 alarm_high:f32
 */
typedef struct __attribute__((packed)) {
    uint8_t slot;                                 /* Slot number (1-8) */
    uint8_t sensor_type;                          /* Sensor type enum */
    char name[CONFIG_SYNC_MAX_NAME_LEN];          /* Sensor name/tag */
    char unit[CONFIG_SYNC_MAX_UNIT_LEN];          /* Engineering unit */
    float scale_min;                              /* Raw value minimum */
    float scale_max;                              /* Raw value maximum */
    float alarm_low;                              /* Low alarm threshold */
    float alarm_high;                             /* High alarm threshold */
} sensor_config_entry_t;

/*
 * Sensor configuration packet header.
 * Followed by sensor_config_entry_t[count]
 *
 * Wire format: header (4 bytes) + entries (42 bytes each)
 */
typedef struct __attribute__((packed)) {
    uint8_t version;                              /* Protocol version (1) */
    uint8_t count;                                /* Number of sensor entries */
    uint16_t crc16;                               /* CRC16 of payload (after this field) */
    /* Followed by sensor_config_entry_t[count] */
} sensor_config_header_t;

/* ============== Actuator Configuration (0xF843) ============== */

/*
 * Single actuator configuration entry.
 *
 * Wire format (22 bytes per entry):
 *   slot:u8 type:u8 name:char[16] default_state:u8 reserved:u8 interlock_mask:u16
 */
typedef struct __attribute__((packed)) {
    uint8_t slot;                                 /* Slot number (9-15) */
    uint8_t actuator_type;                        /* Actuator type enum */
    char name[CONFIG_SYNC_MAX_NAME_LEN];          /* Actuator name/tag */
    uint8_t default_state;                        /* Default state on startup/failsafe */
    uint8_t reserved;                             /* Padding */
    uint16_t interlock_mask;                      /* Bit mask of interlock associations */
} actuator_config_entry_t;

/*
 * Actuator configuration packet header.
 * Followed by actuator_config_entry_t[count]
 *
 * Wire format: header (4 bytes) + entries (22 bytes each)
 */
typedef struct __attribute__((packed)) {
    uint8_t version;                              /* Protocol version (1) */
    uint8_t count;                                /* Number of actuator entries */
    uint16_t crc16;                               /* CRC16 of payload (after this field) */
    /* Followed by actuator_config_entry_t[count] */
} actuator_config_header_t;

/* ============== RTU Status (0xF844) - Read by Controller ============== */

/*
 * RTU status packet (RTU → Controller via record read).
 * Provides RTU health and diagnostic information.
 *
 * Wire format (32 bytes):
 *   version:u8 flags:u8 crc16:u16
 *   uptime_seconds:u32
 *   config_version:u32
 *   sensor_count:u8 actuator_count:u8 active_alarms:u8 authority_state:u8
 *   free_memory_kb:u16 cpu_percent:u8 temperature_c:i8
 *   reserved:u8[12]
 */
typedef struct __attribute__((packed)) {
    uint8_t version;                              /* Protocol version (1) */
    uint8_t flags;                                /* Status flags */
    uint16_t crc16;                               /* CRC16 of payload */
    uint32_t uptime_seconds;                      /* RTU uptime */
    uint32_t config_version;                      /* Applied config timestamp */
    uint8_t sensor_count;                         /* Active sensor count */
    uint8_t actuator_count;                       /* Active actuator count */
    uint8_t active_alarms;                        /* Number of active alarms */
    uint8_t authority_state;                      /* Current authority state */
    uint16_t free_memory_kb;                      /* Free memory in KB */
    uint8_t cpu_percent;                          /* CPU usage 0-100 */
    int8_t temperature_c;                         /* Board temperature in Celsius */
    uint8_t reserved[12];                         /* Reserved for future use */
} rtu_status_payload_t;

/* ============== Enrollment (0xF845) ============== */

/*
 * Enrollment packet for device binding.
 * Controller sends BIND with token, RTU stores and validates.
 *
 * Wire format (80 bytes):
 *   magic:u32 version:u8 operation:u8 crc16:u16
 *   enrollment_token:char[64]
 *   controller_id:u32 reserved:u32
 */
typedef struct __attribute__((packed)) {
    uint32_t magic;                               /* ENROLLMENT_MAGIC (0x454E524C) */
    uint8_t version;                              /* Protocol version (1) */
    uint8_t operation;                            /* ENROLLMENT_OP_* */
    uint16_t crc16;                               /* CRC16 of payload (after this field) */
    char enrollment_token[CONFIG_SYNC_TOKEN_LEN]; /* Enrollment token */
    uint32_t controller_id;                       /* Controller identifier */
    uint32_t reserved;                            /* Reserved */
} enrollment_payload_t;

/*
 * Enrollment response (RTU → Controller via record read after write).
 */
typedef struct __attribute__((packed)) {
    uint32_t magic;                               /* ENROLLMENT_MAGIC */
    uint8_t version;                              /* Protocol version (1) */
    uint8_t status;                               /* 0=success, non-zero=error code */
    uint16_t crc16;                               /* CRC16 of payload */
    uint32_t bound_controller_id;                 /* Currently bound controller ID (0 if unbound) */
    uint32_t bound_timestamp;                     /* When binding occurred (Unix timestamp) */
} enrollment_response_t;

/* ============== Helper Functions ============== */

/*
 * Validate device config payload.
 * Returns true if valid (correct version, CRC matches).
 */
static inline bool device_config_validate(const device_config_payload_t *payload) {
    if (payload->version != CONFIG_SYNC_PROTOCOL_VERSION) {
        return false;
    }
    uint16_t expected_crc = crc16_ccitt(
        (const uint8_t *)payload + 4,  /* Skip version, flags, crc16 */
        sizeof(device_config_payload_t) - 4
    );
    return payload->crc16 == expected_crc;
}

/*
 * Calculate and set CRC for device config payload.
 */
static inline void device_config_set_crc(device_config_payload_t *payload) {
    payload->crc16 = crc16_ccitt(
        (const uint8_t *)payload + 4,
        sizeof(device_config_payload_t) - 4
    );
}

/*
 * Validate enrollment payload.
 */
static inline bool enrollment_validate(const enrollment_payload_t *payload) {
    if (payload->magic != ENROLLMENT_MAGIC) {
        return false;
    }
    if (payload->version != CONFIG_SYNC_PROTOCOL_VERSION) {
        return false;
    }
    uint16_t expected_crc = crc16_ccitt(
        (const uint8_t *)payload + 8,  /* Skip magic, version, operation, crc16 */
        sizeof(enrollment_payload_t) - 8
    );
    return payload->crc16 == expected_crc;
}

/*
 * Calculate and set CRC for enrollment payload.
 */
static inline void enrollment_set_crc(enrollment_payload_t *payload) {
    payload->crc16 = crc16_ccitt(
        (const uint8_t *)payload + 8,
        sizeof(enrollment_payload_t) - 8
    );
}

#ifdef __cplusplus
}
#endif

#endif /* CONFIG_SYNC_PROTOCOL_H */
