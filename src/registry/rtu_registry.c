/*
 * Water Treatment Controller - RTU Registry Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "rtu_registry.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>

/* RTU registry structure */
struct rtu_registry {
    registry_config_t config;
    rtu_device_t *devices[WTC_MAX_RTUS];
    int device_count;
    pthread_mutex_t lock;
};

/* Public functions */

wtc_result_t rtu_registry_init(rtu_registry_t **registry,
                                const registry_config_t *config) {
    if (!registry) {
        return WTC_ERROR_INVALID_PARAM;
    }

    rtu_registry_t *reg = calloc(1, sizeof(rtu_registry_t));
    if (!reg) {
        return WTC_ERROR_NO_MEMORY;
    }

    if (config) {
        memcpy(&reg->config, config, sizeof(registry_config_t));
    }

    pthread_mutex_init(&reg->lock, NULL);

    /* Load existing topology from database if configured */
    if (reg->config.database_path) {
        rtu_registry_load_topology(reg);
    }

    *registry = reg;
    LOG_INFO("RTU registry initialized");
    return WTC_OK;
}

/* Helper to free device and its dynamic arrays */
static void free_device(rtu_device_t *device) {
    if (!device) return;
    free(device->slots);
    free(device->sensors);
    free(device->actuators);
    free(device);
}

void rtu_registry_cleanup(rtu_registry_t *registry) {
    if (!registry) return;

    pthread_mutex_lock(&registry->lock);

    /* Free all devices and their dynamic arrays */
    for (int i = 0; i < registry->device_count; i++) {
        free_device(registry->devices[i]);
    }

    pthread_mutex_unlock(&registry->lock);
    pthread_mutex_destroy(&registry->lock);
    free(registry);

    LOG_INFO("RTU registry cleaned up");
}

wtc_result_t rtu_registry_discover_devices(rtu_registry_t *registry,
                                            const char *interface_name,
                                            uint32_t timeout_ms) {
    if (!registry || !interface_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Discovery is handled by PROFINET controller and DCP */
    /* This function would trigger a DCP identify broadcast */
    LOG_INFO("Starting device discovery on %s (timeout=%u ms)",
             interface_name, timeout_ms);

    /* In practice, discovered devices are added via callbacks */
    (void)timeout_ms;

    return WTC_OK;
}

wtc_result_t rtu_registry_add_device(rtu_registry_t *registry,
                                      const char *station_name,
                                      const char *ip_address,
                                      const slot_config_t *slots,
                                      int slot_count) {
    if (!registry || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&registry->lock);

    /* Check if device already exists */
    for (int i = 0; i < registry->device_count; i++) {
        if (strcmp(registry->devices[i]->station_name, station_name) == 0) {
            pthread_mutex_unlock(&registry->lock);
            return WTC_ERROR_ALREADY_EXISTS;
        }
    }

    /* Check capacity */
    if (registry->device_count >= WTC_MAX_RTUS) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_FULL;
    }

    /* Allocate new device */
    rtu_device_t *device = calloc(1, sizeof(rtu_device_t));
    if (!device) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    device->id = registry->device_count;
    strncpy(device->station_name, station_name, sizeof(device->station_name) - 1);
    if (ip_address) {
        strncpy(device->ip_address, ip_address, sizeof(device->ip_address) - 1);
    }
    device->connection_state = PROFINET_STATE_OFFLINE;
    device->last_seen_ms = time_get_ms();

    /* Allocate dynamic arrays with capacity based on slot_count or defaults */
    device->slot_capacity = slot_count > 0 ? slot_count : WTC_DEFAULT_SLOTS;
    device->slots = calloc(device->slot_capacity, sizeof(slot_config_t));
    if (!device->slots) {
        free(device);
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    device->sensor_capacity = WTC_DEFAULT_SENSORS;
    device->sensors = calloc(device->sensor_capacity, sizeof(sensor_data_t));
    if (!device->sensors) {
        free(device->slots);
        free(device);
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    device->actuator_capacity = WTC_DEFAULT_ACTUATORS;
    device->actuators = calloc(device->actuator_capacity, sizeof(actuator_state_t));
    if (!device->actuators) {
        free(device->sensors);
        free(device->slots);
        free(device);
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    /* Copy slot configuration */
    if (slots && slot_count > 0) {
        memcpy(device->slots, slots, slot_count * sizeof(slot_config_t));
        device->slot_count = slot_count;

        /* Count sensors and actuators from slot config */
        for (int i = 0; i < slot_count; i++) {
            if (slots[i].type == SLOT_TYPE_SENSOR) {
                device->sensor_count++;
            } else if (slots[i].type == SLOT_TYPE_ACTUATOR) {
                device->actuator_count++;
            }
        }
    }

    registry->devices[registry->device_count++] = device;

    pthread_mutex_unlock(&registry->lock);

    /* Invoke callback */
    if (registry->config.on_device_added) {
        registry->config.on_device_added(device, registry->config.callback_ctx);
    }

    LOG_INFO("Added device: %s (%s)", station_name, ip_address ? ip_address : "no IP");
    return WTC_OK;
}

wtc_result_t rtu_registry_remove_device(rtu_registry_t *registry,
                                         const char *station_name) {
    if (!registry || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&registry->lock);

    for (int i = 0; i < registry->device_count; i++) {
        if (strcmp(registry->devices[i]->station_name, station_name) == 0) {
            free_device(registry->devices[i]);

            /* Shift remaining devices */
            for (int j = i; j < registry->device_count - 1; j++) {
                registry->devices[j] = registry->devices[j + 1];
                registry->devices[j]->id = j;
            }
            registry->devices[--registry->device_count] = NULL;

            pthread_mutex_unlock(&registry->lock);

            /* Invoke callback */
            if (registry->config.on_device_removed) {
                registry->config.on_device_removed(station_name,
                                                   registry->config.callback_ctx);
            }

            LOG_INFO("Removed device: %s", station_name);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&registry->lock);
    return WTC_ERROR_NOT_FOUND;
}

rtu_device_t *rtu_registry_get_device(rtu_registry_t *registry,
                                       const char *station_name) {
    if (!registry || !station_name) return NULL;

    pthread_mutex_lock(&registry->lock);

    for (int i = 0; i < registry->device_count; i++) {
        if (strcmp(registry->devices[i]->station_name, station_name) == 0) {
            pthread_mutex_unlock(&registry->lock);
            return registry->devices[i];
        }
    }

    pthread_mutex_unlock(&registry->lock);
    return NULL;
}

rtu_device_t *rtu_registry_get_device_by_index(rtu_registry_t *registry, int index) {
    if (!registry || index < 0 || index >= registry->device_count) {
        return NULL;
    }
    return registry->devices[index];
}

wtc_result_t rtu_registry_list_devices(rtu_registry_t *registry,
                                        rtu_device_t **devices,
                                        int *count,
                                        int max_count) {
    if (!registry || !devices || !count) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&registry->lock);

    int copy_count = registry->device_count;
    if (copy_count > max_count) {
        copy_count = max_count;
    }

    if (copy_count == 0) {
        *devices = NULL;
        *count = 0;
        pthread_mutex_unlock(&registry->lock);
        return WTC_OK;
    }

    /* Allocate array of device structs (caller must free) */
    *devices = calloc(copy_count, sizeof(rtu_device_t));
    if (!*devices) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    /* Copy device data (shallow copy - pointers inside are shared) */
    for (int i = 0; i < copy_count; i++) {
        memcpy(&(*devices)[i], registry->devices[i], sizeof(rtu_device_t));
    }
    *count = copy_count;

    pthread_mutex_unlock(&registry->lock);
    return WTC_OK;
}

int rtu_registry_get_device_count(rtu_registry_t *registry) {
    return registry ? registry->device_count : 0;
}

wtc_result_t rtu_registry_set_device_config(rtu_registry_t *registry,
                                             const char *station_name,
                                             const slot_config_t *slots,
                                             int slot_count) {
    if (!registry || !station_name || !slots || slot_count < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    rtu_device_t *device = rtu_registry_get_device(registry, station_name);
    if (!device) {
        return WTC_ERROR_NOT_FOUND;
    }

    pthread_mutex_lock(&registry->lock);

    /* Reallocate slots array if needed */
    if (slot_count > device->slot_capacity) {
        slot_config_t *new_slots = realloc(device->slots, slot_count * sizeof(slot_config_t));
        if (!new_slots) {
            pthread_mutex_unlock(&registry->lock);
            return WTC_ERROR_NO_MEMORY;
        }
        device->slots = new_slots;
        device->slot_capacity = slot_count;
    }

    memcpy(device->slots, slots, slot_count * sizeof(slot_config_t));
    device->slot_count = slot_count;
    device->config_dirty = true;

    /* Recount sensors and actuators */
    device->sensor_count = 0;
    device->actuator_count = 0;
    for (int i = 0; i < slot_count; i++) {
        if (slots[i].type == SLOT_TYPE_SENSOR) {
            device->sensor_count++;
        } else if (slots[i].type == SLOT_TYPE_ACTUATOR) {
            device->actuator_count++;
        }
    }

    pthread_mutex_unlock(&registry->lock);

    LOG_DEBUG("Updated config for %s (%d slots)", station_name, slot_count);
    return WTC_OK;
}

wtc_result_t rtu_registry_set_device_state(rtu_registry_t *registry,
                                            const char *station_name,
                                            profinet_state_t state) {
    if (!registry || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    rtu_device_t *device = rtu_registry_get_device(registry, station_name);
    if (!device) {
        return WTC_ERROR_NOT_FOUND;
    }

    profinet_state_t old_state = device->connection_state;
    if (old_state == state) {
        return WTC_OK;
    }

    device->connection_state = state;
    device->last_seen_ms = time_get_ms();

    /* Invoke callback */
    if (registry->config.on_device_state_changed) {
        registry->config.on_device_state_changed(station_name, old_state, state,
                                                  registry->config.callback_ctx);
    }

    LOG_INFO("Device %s state changed: %d -> %d", station_name, old_state, state);
    return WTC_OK;
}

wtc_result_t rtu_registry_update_sensor(rtu_registry_t *registry,
                                         const char *station_name,
                                         int slot,
                                         float value,
                                         iops_t status) {
    if (!registry || !station_name || slot < 1) {
        return WTC_ERROR_INVALID_PARAM;
    }

    rtu_device_t *device = rtu_registry_get_device(registry, station_name);
    if (!device) {
        return WTC_ERROR_NOT_FOUND;
    }

    int sensor_idx = slot - 1;
    if (sensor_idx >= device->sensor_capacity) {
        return WTC_ERROR_INVALID_PARAM;
    }

    device->sensors[sensor_idx].value = value;
    device->sensors[sensor_idx].status = status;
    device->sensors[sensor_idx].timestamp_ms = time_get_ms();
    device->sensors[sensor_idx].stale = false;

    return WTC_OK;
}

wtc_result_t rtu_registry_update_actuator(rtu_registry_t *registry,
                                           const char *station_name,
                                           int slot,
                                           const actuator_output_t *output) {
    if (!registry || !station_name || !output || slot < 1) {
        return WTC_ERROR_INVALID_PARAM;
    }

    rtu_device_t *device = rtu_registry_get_device(registry, station_name);
    if (!device) {
        return WTC_ERROR_NOT_FOUND;
    }

    /* Actuator index - slots are 1-based, actuators can start at any configured slot */
    int actuator_idx = slot - 1;
    if (actuator_idx >= device->actuator_capacity) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memcpy(&device->actuators[actuator_idx].output, output, sizeof(actuator_output_t));
    device->actuators[actuator_idx].last_change_ms = time_get_ms();

    return WTC_OK;
}

wtc_result_t rtu_registry_get_sensor(rtu_registry_t *registry,
                                      const char *station_name,
                                      int slot,
                                      sensor_data_t *data) {
    if (!registry || !station_name || !data || slot < 1) {
        return WTC_ERROR_INVALID_PARAM;
    }

    rtu_device_t *device = rtu_registry_get_device(registry, station_name);
    if (!device) {
        return WTC_ERROR_NOT_FOUND;
    }

    int sensor_idx = slot - 1;
    if (sensor_idx >= device->sensor_capacity) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memcpy(data, &device->sensors[sensor_idx], sizeof(sensor_data_t));

    /* Check staleness */
    uint64_t now = time_get_ms();
    if (now - data->timestamp_ms > 5000) { /* 5 second stale threshold */
        data->stale = true;
    }

    return WTC_OK;
}

wtc_result_t rtu_registry_get_actuator(rtu_registry_t *registry,
                                        const char *station_name,
                                        int slot,
                                        actuator_state_t *state) {
    if (!registry || !station_name || !state || slot < 1) {
        return WTC_ERROR_INVALID_PARAM;
    }

    rtu_device_t *device = rtu_registry_get_device(registry, station_name);
    if (!device) {
        return WTC_ERROR_NOT_FOUND;
    }

    int actuator_idx = slot - 1;
    if (actuator_idx >= device->actuator_capacity) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memcpy(state, &device->actuators[actuator_idx], sizeof(actuator_state_t));

    return WTC_OK;
}

wtc_result_t rtu_registry_save_topology(rtu_registry_t *registry) {
    if (!registry) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* In a full implementation, this would serialize to database */
    LOG_INFO("Saving topology (%d devices)", registry->device_count);

    return WTC_OK;
}

wtc_result_t rtu_registry_load_topology(rtu_registry_t *registry) {
    if (!registry) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* In a full implementation, this would load from database */
    LOG_INFO("Loading topology from database");

    return WTC_OK;
}

wtc_result_t rtu_registry_export_json(rtu_registry_t *registry,
                                       char *buffer,
                                       size_t buffer_size) {
    if (!registry || !buffer || buffer_size < 64) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&registry->lock);

    int pos = 0;
    pos += snprintf(buffer + pos, buffer_size - pos, "{\"devices\":[");

    for (int i = 0; i < registry->device_count; i++) {
        rtu_device_t *dev = registry->devices[i];
        if (i > 0) {
            pos += snprintf(buffer + pos, buffer_size - pos, ",");
        }
        pos += snprintf(buffer + pos, buffer_size - pos,
                       "{\"station_name\":\"%s\","
                       "\"ip_address\":\"%s\","
                       "\"vendor_id\":%u,"
                       "\"device_id\":%u,"
                       "\"state\":%d,"
                       "\"slot_count\":%d}",
                       dev->station_name,
                       dev->ip_address,
                       dev->vendor_id,
                       dev->device_id,
                       dev->connection_state,
                       dev->slot_count);
    }

    pos += snprintf(buffer + pos, buffer_size - pos, "]}");

    pthread_mutex_unlock(&registry->lock);
    return WTC_OK;
}

wtc_result_t rtu_registry_import_json(rtu_registry_t *registry,
                                       const char *json_string) {
    if (!registry || !json_string) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* JSON parsing would go here - using a proper JSON library */
    LOG_INFO("Importing topology from JSON");

    return WTC_OK;
}

wtc_result_t rtu_registry_get_stats(rtu_registry_t *registry,
                                     registry_stats_t *stats) {
    if (!registry || !stats) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memset(stats, 0, sizeof(registry_stats_t));

    pthread_mutex_lock(&registry->lock);

    stats->total_devices = registry->device_count;

    for (int i = 0; i < registry->device_count; i++) {
        switch (registry->devices[i]->connection_state) {
        case PROFINET_STATE_RUNNING:
            stats->connected_devices++;
            break;
        case PROFINET_STATE_ERROR:
        case PROFINET_STATE_DISCONNECT:
            stats->error_devices++;
            break;
        default:
            stats->disconnected_devices++;
            break;
        }
    }

    pthread_mutex_unlock(&registry->lock);
    return WTC_OK;
}
