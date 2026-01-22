/*
 * Water Treatment Controller - Configuration Sync Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "config_sync.h"
#include "../profinet/profinet_controller.h"
#include "../registry/rtu_registry.h"
#include "../utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <stdio.h>

/* ============== Manager Structure ============== */

struct config_sync_manager {
    config_sync_config_t config;
    profinet_controller_t *profinet;
    rtu_registry_t *registry;
    config_sync_callback_t callback;
    void *callback_ctx;
    config_sync_stats_t stats;
    uint32_t controller_id;  /* Unique controller identifier */
};

/* ============== Helper Functions ============== */

static uint64_t get_current_time_ms(void) {
    return time_utils_get_monotonic_ms();
}

static uint32_t get_unix_timestamp(void) {
    return (uint32_t)time_utils_get_unix_seconds();
}

/* ============== Manager Lifecycle ============== */

wtc_result_t config_sync_manager_init(config_sync_manager_t **manager,
                                       const config_sync_config_t *config) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    config_sync_manager_t *mgr = calloc(1, sizeof(config_sync_manager_t));
    if (!mgr) {
        return WTC_ERROR_NO_MEMORY;
    }

    /* Apply configuration */
    if (config) {
        mgr->config = *config;
    } else {
        config_sync_config_t default_config = CONFIG_SYNC_DEFAULT_CONFIG;
        mgr->config = default_config;
    }

    /* Generate controller ID from timestamp + random */
    mgr->controller_id = get_unix_timestamp() ^ 0xC0DE;

    *manager = mgr;
    return WTC_OK;
}

void config_sync_manager_cleanup(config_sync_manager_t *manager) {
    if (manager) {
        free(manager);
    }
}

wtc_result_t config_sync_set_profinet(config_sync_manager_t *manager,
                                       profinet_controller_t *profinet) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }
    manager->profinet = profinet;
    return WTC_OK;
}

wtc_result_t config_sync_set_registry(config_sync_manager_t *manager,
                                       rtu_registry_t *registry) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }
    manager->registry = registry;
    return WTC_OK;
}

void config_sync_set_callback(config_sync_manager_t *manager,
                               config_sync_callback_t callback,
                               void *ctx) {
    if (manager) {
        manager->callback = callback;
        manager->callback_ctx = ctx;
    }
}

/* ============== Packet Building ============== */

static config_sync_result_t build_enrollment_packet(
    enrollment_payload_t *payload,
    const char *token,
    uint8_t operation,
    uint32_t controller_id
) {
    if (!payload || !token) {
        return CONFIG_SYNC_ERROR_INVALID_PARAM;
    }

    memset(payload, 0, sizeof(enrollment_payload_t));

    payload->magic = ENROLLMENT_MAGIC;
    payload->version = CONFIG_SYNC_PROTOCOL_VERSION;
    payload->operation = operation;
    payload->controller_id = controller_id;
    payload->reserved = 0;

    /* Copy token (max 64 chars) */
    strncpy(payload->enrollment_token, token, CONFIG_SYNC_TOKEN_LEN - 1);
    payload->enrollment_token[CONFIG_SYNC_TOKEN_LEN - 1] = '\0';

    /* Calculate CRC */
    enrollment_set_crc(payload);

    return CONFIG_SYNC_OK;
}

static config_sync_result_t build_device_config_packet(
    device_config_payload_t *payload,
    const rtu_device_t *device
) {
    if (!payload || !device) {
        return CONFIG_SYNC_ERROR_INVALID_PARAM;
    }

    memset(payload, 0, sizeof(device_config_payload_t));

    payload->version = CONFIG_SYNC_PROTOCOL_VERSION;
    payload->flags = 0x01;  /* config_changed */
    payload->config_timestamp = get_unix_timestamp();

    /* Copy station name */
    strncpy(payload->station_name, device->station_name, CONFIG_SYNC_MAX_STATION_NAME - 1);
    payload->station_name[CONFIG_SYNC_MAX_STATION_NAME - 1] = '\0';

    /* Count sensors and actuators from slots */
    uint16_t sensor_count = 0;
    uint16_t actuator_count = 0;
    for (int i = 0; i < device->slot_count && i < WTC_MAX_SLOTS; i++) {
        if (device->slots && device->slots[i].enabled) {
            if (device->slots[i].type == SLOT_TYPE_SENSOR) {
                sensor_count++;
            } else if (device->slots[i].type == SLOT_TYPE_ACTUATOR) {
                actuator_count++;
            }
        }
    }
    payload->sensor_count = sensor_count;
    payload->actuator_count = actuator_count;

    payload->authority_mode = AUTHORITY_MODE_SUPERVISED;
    payload->reserved = 0;
    payload->watchdog_ms = 3000;  /* 3 second watchdog */

    /* Calculate CRC */
    device_config_set_crc(payload);

    return CONFIG_SYNC_OK;
}

static config_sync_result_t build_sensor_config_packet(
    uint8_t *buffer,
    size_t buffer_size,
    size_t *packet_size,
    const slot_config_t *slots,
    int slot_count
) {
    if (!buffer || !packet_size || !slots) {
        return CONFIG_SYNC_ERROR_INVALID_PARAM;
    }

    /* Count sensor slots */
    int sensor_count = 0;
    for (int i = 0; i < slot_count && i < CONFIG_SYNC_MAX_SENSORS; i++) {
        if (slots[i].type == SLOT_TYPE_SENSOR && slots[i].enabled) {
            sensor_count++;
        }
    }

    /* Calculate required size */
    size_t required = sizeof(sensor_config_header_t) +
                      (sensor_count * sizeof(sensor_config_entry_t));
    if (required > buffer_size) {
        return CONFIG_SYNC_ERROR_NO_MEMORY;
    }

    /* Build header */
    sensor_config_header_t *header = (sensor_config_header_t *)buffer;
    header->version = CONFIG_SYNC_PROTOCOL_VERSION;
    header->count = (uint8_t)sensor_count;

    /* Build entries */
    sensor_config_entry_t *entries = (sensor_config_entry_t *)(buffer + sizeof(sensor_config_header_t));
    int entry_idx = 0;
    for (int i = 0; i < slot_count && entry_idx < sensor_count; i++) {
        if (slots[i].type == SLOT_TYPE_SENSOR && slots[i].enabled) {
            sensor_config_entry_t *entry = &entries[entry_idx++];

            entry->slot = (uint8_t)slots[i].slot;
            entry->sensor_type = (uint8_t)slots[i].measurement_type;

            strncpy(entry->name, slots[i].name, CONFIG_SYNC_MAX_NAME_LEN - 1);
            entry->name[CONFIG_SYNC_MAX_NAME_LEN - 1] = '\0';

            strncpy(entry->unit, slots[i].unit, CONFIG_SYNC_MAX_UNIT_LEN - 1);
            entry->unit[CONFIG_SYNC_MAX_UNIT_LEN - 1] = '\0';

            entry->scale_min = slots[i].scale_min;
            entry->scale_max = slots[i].scale_max;
            entry->alarm_low = slots[i].alarm_low;
            entry->alarm_high = slots[i].alarm_high;
        }
    }

    /* Calculate CRC (over entries only, after header) */
    header->crc16 = crc16_ccitt(
        (const uint8_t *)entries,
        sensor_count * sizeof(sensor_config_entry_t)
    );

    *packet_size = required;
    return CONFIG_SYNC_OK;
}

static config_sync_result_t build_actuator_config_packet(
    uint8_t *buffer,
    size_t buffer_size,
    size_t *packet_size,
    const slot_config_t *slots,
    int slot_count
) {
    if (!buffer || !packet_size || !slots) {
        return CONFIG_SYNC_ERROR_INVALID_PARAM;
    }

    /* Count actuator slots */
    int actuator_count = 0;
    for (int i = 0; i < slot_count && i < CONFIG_SYNC_MAX_ACTUATORS; i++) {
        if (slots[i].type == SLOT_TYPE_ACTUATOR && slots[i].enabled) {
            actuator_count++;
        }
    }

    /* Calculate required size */
    size_t required = sizeof(actuator_config_header_t) +
                      (actuator_count * sizeof(actuator_config_entry_t));
    if (required > buffer_size) {
        return CONFIG_SYNC_ERROR_NO_MEMORY;
    }

    /* Build header */
    actuator_config_header_t *header = (actuator_config_header_t *)buffer;
    header->version = CONFIG_SYNC_PROTOCOL_VERSION;
    header->count = (uint8_t)actuator_count;

    /* Build entries */
    actuator_config_entry_t *entries = (actuator_config_entry_t *)(buffer + sizeof(actuator_config_header_t));
    int entry_idx = 0;
    for (int i = 0; i < slot_count && entry_idx < actuator_count; i++) {
        if (slots[i].type == SLOT_TYPE_ACTUATOR && slots[i].enabled) {
            actuator_config_entry_t *entry = &entries[entry_idx++];

            entry->slot = (uint8_t)slots[i].slot;
            entry->actuator_type = (uint8_t)slots[i].actuator_type;

            strncpy(entry->name, slots[i].name, CONFIG_SYNC_MAX_NAME_LEN - 1);
            entry->name[CONFIG_SYNC_MAX_NAME_LEN - 1] = '\0';

            entry->default_state = ACTUATOR_CMD_OFF;
            entry->reserved = 0;
            entry->interlock_mask = 0;  /* No interlocks by default */
        }
    }

    /* Calculate CRC (over entries only) */
    header->crc16 = crc16_ccitt(
        (const uint8_t *)entries,
        actuator_count * sizeof(actuator_config_entry_t)
    );

    *packet_size = required;
    return CONFIG_SYNC_OK;
}

/* ============== Send Functions ============== */

static config_sync_result_t send_packet(
    config_sync_manager_t *manager,
    const char *station_name,
    uint16_t index,
    const void *data,
    size_t len
) {
    if (!manager || !manager->profinet || !station_name || !data) {
        return CONFIG_SYNC_ERROR_INVALID_PARAM;
    }

    wtc_result_t result = profinet_controller_write_record(
        manager->profinet,
        station_name,
        0,          /* API 0 */
        0,          /* Slot 0 (DAP) */
        1,          /* Subslot 1 */
        index,
        data,
        len
    );

    if (result != WTC_OK) {
        return CONFIG_SYNC_ERROR_SEND;
    }

    return CONFIG_SYNC_OK;
}

/* ============== Public API ============== */

config_sync_result_t config_sync_send_enrollment(
    config_sync_manager_t *manager,
    const char *station_name,
    const char *token,
    uint8_t operation
) {
    if (!manager || !station_name || !token) {
        return CONFIG_SYNC_ERROR_INVALID_PARAM;
    }

    enrollment_payload_t payload;
    config_sync_result_t result = build_enrollment_packet(
        &payload, token, operation, manager->controller_id
    );
    if (result != CONFIG_SYNC_OK) {
        return result;
    }

    return send_packet(manager, station_name,
                       CONFIG_SYNC_ENROLLMENT_INDEX,
                       &payload, sizeof(payload));
}

config_sync_result_t config_sync_send_device_config(
    config_sync_manager_t *manager,
    const char *station_name,
    const rtu_device_t *device
) {
    if (!manager || !station_name || !device) {
        return CONFIG_SYNC_ERROR_INVALID_PARAM;
    }

    device_config_payload_t payload;
    config_sync_result_t result = build_device_config_packet(&payload, device);
    if (result != CONFIG_SYNC_OK) {
        return result;
    }

    return send_packet(manager, station_name,
                       CONFIG_SYNC_DEVICE_INDEX,
                       &payload, sizeof(payload));
}

config_sync_result_t config_sync_send_sensor_config(
    config_sync_manager_t *manager,
    const char *station_name,
    const slot_config_t *slots,
    int slot_count
) {
    if (!manager || !station_name || !slots || slot_count <= 0) {
        return CONFIG_SYNC_ERROR_INVALID_PARAM;
    }

    /* Buffer for packet (header + max 16 sensor entries) */
    uint8_t buffer[sizeof(sensor_config_header_t) +
                   (CONFIG_SYNC_MAX_SENSORS * sizeof(sensor_config_entry_t))];
    size_t packet_size = 0;

    config_sync_result_t result = build_sensor_config_packet(
        buffer, sizeof(buffer), &packet_size, slots, slot_count
    );
    if (result != CONFIG_SYNC_OK) {
        return result;
    }

    return send_packet(manager, station_name,
                       CONFIG_SYNC_SENSOR_INDEX,
                       buffer, packet_size);
}

config_sync_result_t config_sync_send_actuator_config(
    config_sync_manager_t *manager,
    const char *station_name,
    const slot_config_t *slots,
    int slot_count
) {
    if (!manager || !station_name || !slots || slot_count <= 0) {
        return CONFIG_SYNC_ERROR_INVALID_PARAM;
    }

    /* Buffer for packet (header + max 8 actuator entries) */
    uint8_t buffer[sizeof(actuator_config_header_t) +
                   (CONFIG_SYNC_MAX_ACTUATORS * sizeof(actuator_config_entry_t))];
    size_t packet_size = 0;

    config_sync_result_t result = build_actuator_config_packet(
        buffer, sizeof(buffer), &packet_size, slots, slot_count
    );
    if (result != CONFIG_SYNC_OK) {
        return result;
    }

    return send_packet(manager, station_name,
                       CONFIG_SYNC_ACTUATOR_INDEX,
                       buffer, packet_size);
}

config_sync_result_t config_sync_to_rtu(
    config_sync_manager_t *manager,
    const char *station_name
) {
    if (!manager || !station_name) {
        return CONFIG_SYNC_ERROR_INVALID_PARAM;
    }

    if (!manager->profinet) {
        return CONFIG_SYNC_ERROR_RTU_NOT_CONNECTED;
    }

    if (!manager->registry) {
        return CONFIG_SYNC_ERROR_INVALID_PARAM;
    }

    /* Get RTU device from registry */
    rtu_device_t *device = rtu_registry_find_device(manager->registry, station_name);
    if (!device) {
        return CONFIG_SYNC_ERROR_INVALID_PARAM;
    }

    /* Check RTU is connected */
    if (device->connection_state != PROFINET_STATE_RUNNING) {
        return CONFIG_SYNC_ERROR_RTU_NOT_CONNECTED;
    }

    config_sync_result_t result = CONFIG_SYNC_OK;
    manager->stats.total_syncs++;

    /* 1. Send enrollment (if enabled and we have a token) */
    /* Note: In a full implementation, we'd fetch the token from a database or config */
    /* For now, we skip enrollment if no token source is available */

    /* 2. Send device config (if enabled) */
    if (manager->config.sync_device_config) {
        result = config_sync_send_device_config(manager, station_name, device);
        if (result != CONFIG_SYNC_OK) {
            manager->stats.failed_syncs++;
            if (manager->callback) {
                manager->callback(station_name, result, manager->callback_ctx);
            }
            return result;
        }
    }

    /* 3. Send sensor config (if enabled and slots exist) */
    if (manager->config.sync_sensor_config && device->slots && device->slot_count > 0) {
        result = config_sync_send_sensor_config(manager, station_name,
                                                 device->slots, device->slot_count);
        if (result != CONFIG_SYNC_OK) {
            manager->stats.failed_syncs++;
            if (manager->callback) {
                manager->callback(station_name, result, manager->callback_ctx);
            }
            return result;
        }
    }

    /* 4. Send actuator config (if enabled and slots exist) */
    if (manager->config.sync_actuator_config && device->slots && device->slot_count > 0) {
        result = config_sync_send_actuator_config(manager, station_name,
                                                   device->slots, device->slot_count);
        if (result != CONFIG_SYNC_OK) {
            manager->stats.failed_syncs++;
            if (manager->callback) {
                manager->callback(station_name, result, manager->callback_ctx);
            }
            return result;
        }
    }

    /* Success */
    manager->stats.successful_syncs++;
    manager->stats.last_sync_time_ms = get_current_time_ms();
    strncpy(manager->stats.last_sync_rtu, station_name, WTC_MAX_STATION_NAME - 1);
    manager->stats.last_sync_rtu[WTC_MAX_STATION_NAME - 1] = '\0';

    if (manager->callback) {
        manager->callback(station_name, CONFIG_SYNC_OK, manager->callback_ctx);
    }

    return CONFIG_SYNC_OK;
}

void config_sync_on_rtu_connect(config_sync_manager_t *manager,
                                 const char *station_name) {
    if (!manager || !station_name) {
        return;
    }

    if (manager->config.sync_on_connect) {
        config_sync_to_rtu(manager, station_name);
    }
}

wtc_result_t config_sync_get_stats(config_sync_manager_t *manager,
                                    config_sync_stats_t *stats) {
    if (!manager || !stats) {
        return WTC_ERROR_INVALID_PARAM;
    }

    *stats = manager->stats;
    return WTC_OK;
}
