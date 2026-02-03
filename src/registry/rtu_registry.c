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

/*
 * Internal: find device by station_name while lock is ALREADY HELD.
 * Returns raw pointer for internal use only — caller must hold registry->lock.
 */
static rtu_device_t *find_device_locked(rtu_registry_t *registry,
                                         const char *station_name) {
    for (int i = 0; i < registry->device_count; i++) {
        if (strcmp(registry->devices[i]->station_name, station_name) == 0) {
            return registry->devices[i];
        }
    }
    return NULL;
}

/*
 * Deep-copy a single device (caller frees with rtu_registry_free_device_copy).
 * Must be called while registry lock is held.
 */
static rtu_device_t *deep_copy_device(const rtu_device_t *src) {
    rtu_device_t *dst = calloc(1, sizeof(rtu_device_t));
    if (!dst) return NULL;

    memcpy(dst, src, sizeof(rtu_device_t));

    /* Deep copy dynamic arrays */
    if (src->slots && src->slot_capacity > 0) {
        dst->slots = calloc(src->slot_capacity, sizeof(slot_config_t));
        if (dst->slots) {
            memcpy(dst->slots, src->slots, src->slot_count * sizeof(slot_config_t));
        } else {
            dst->slot_capacity = 0;
            dst->slot_count = 0;
        }
    } else {
        dst->slots = NULL;
    }

    if (src->sensors && src->sensor_capacity > 0) {
        dst->sensors = calloc(src->sensor_capacity, sizeof(sensor_data_t));
        if (dst->sensors) {
            memcpy(dst->sensors, src->sensors,
                   src->sensor_capacity * sizeof(sensor_data_t));
        } else {
            dst->sensor_capacity = 0;
        }
    } else {
        dst->sensors = NULL;
    }

    if (src->actuators && src->actuator_capacity > 0) {
        dst->actuators = calloc(src->actuator_capacity, sizeof(actuator_state_t));
        if (dst->actuators) {
            memcpy(dst->actuators, src->actuators,
                   src->actuator_capacity * sizeof(actuator_state_t));
        } else {
            dst->actuator_capacity = 0;
        }
    } else {
        dst->actuators = NULL;
    }

    return dst;
}

rtu_device_t *rtu_registry_get_device(rtu_registry_t *registry,
                                       const char *station_name) {
    if (!registry || !station_name) return NULL;

    pthread_mutex_lock(&registry->lock);

    rtu_device_t *src = find_device_locked(registry, station_name);
    rtu_device_t *copy = src ? deep_copy_device(src) : NULL;

    pthread_mutex_unlock(&registry->lock);
    return copy;
}

rtu_device_t *rtu_registry_get_device_by_index(rtu_registry_t *registry, int index) {
    if (!registry) {
        return NULL;
    }

    pthread_mutex_lock(&registry->lock);

    if (index < 0 || index >= registry->device_count) {
        pthread_mutex_unlock(&registry->lock);
        return NULL;
    }

    rtu_device_t *copy = deep_copy_device(registry->devices[index]);
    pthread_mutex_unlock(&registry->lock);

    return copy;
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

    /* Allocate array of device structs (caller must free with rtu_registry_free_device_list) */
    *devices = calloc(copy_count, sizeof(rtu_device_t));
    if (!*devices) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    /* REG-C4 fix: Deep copy device data including dynamic arrays */
    for (int i = 0; i < copy_count; i++) {
        rtu_device_t *src = registry->devices[i];
        rtu_device_t *dst = &(*devices)[i];

        /* Copy base struct */
        memcpy(dst, src, sizeof(rtu_device_t));

        /* Deep copy slots array */
        if (src->slots && src->slot_capacity > 0) {
            dst->slots = calloc(src->slot_capacity, sizeof(slot_config_t));
            if (dst->slots) {
                memcpy(dst->slots, src->slots, src->slot_count * sizeof(slot_config_t));
            } else {
                dst->slot_capacity = 0;
                dst->slot_count = 0;
            }
        } else {
            dst->slots = NULL;
        }

        /* Deep copy sensors array */
        if (src->sensors && src->sensor_capacity > 0) {
            dst->sensors = calloc(src->sensor_capacity, sizeof(sensor_data_t));
            if (dst->sensors) {
                memcpy(dst->sensors, src->sensors, src->sensor_capacity * sizeof(sensor_data_t));
            } else {
                dst->sensor_capacity = 0;
            }
        } else {
            dst->sensors = NULL;
        }

        /* Deep copy actuators array */
        if (src->actuators && src->actuator_capacity > 0) {
            dst->actuators = calloc(src->actuator_capacity, sizeof(actuator_state_t));
            if (dst->actuators) {
                memcpy(dst->actuators, src->actuators, src->actuator_capacity * sizeof(actuator_state_t));
            } else {
                dst->actuator_capacity = 0;
            }
        } else {
            dst->actuators = NULL;
        }
    }
    *count = copy_count;

    pthread_mutex_unlock(&registry->lock);
    return WTC_OK;
}

/* Free device list returned by rtu_registry_list_devices (REG-C4 fix) */
void rtu_registry_free_device_list(rtu_device_t *devices, int count) {
    if (!devices) return;

    for (int i = 0; i < count; i++) {
        free(devices[i].slots);
        free(devices[i].sensors);
        free(devices[i].actuators);
    }
    free(devices);
}

/* Free single device copy returned by get_device / get_device_by_index */
void rtu_registry_free_device_copy(rtu_device_t *device) {
    if (!device) return;
    free(device->slots);
    free(device->sensors);
    free(device->actuators);
    free(device);
}

int rtu_registry_get_device_count(rtu_registry_t *registry) {
    if (!registry) {
        return 0;
    }

    /* REG-C1 fix: protect device_count read with lock */
    pthread_mutex_lock(&registry->lock);
    int count = registry->device_count;
    pthread_mutex_unlock(&registry->lock);

    return count;
}

wtc_result_t rtu_registry_set_device_config(rtu_registry_t *registry,
                                             const char *station_name,
                                             const slot_config_t *slots,
                                             int slot_count) {
    if (!registry || !station_name || !slots || slot_count < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* REG-C3 fix: Keep lock held for entire operation */
    pthread_mutex_lock(&registry->lock);

    /* Find device while holding lock */
    rtu_device_t *device = NULL;
    for (int i = 0; i < registry->device_count; i++) {
        if (strcmp(registry->devices[i]->station_name, station_name) == 0) {
            device = registry->devices[i];
            break;
        }
    }

    if (!device) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NOT_FOUND;
    }

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

    pthread_mutex_lock(&registry->lock);

    rtu_device_t *device = find_device_locked(registry, station_name);
    if (!device) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    profinet_state_t old_state = device->connection_state;
    if (old_state == state) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_OK;
    }

    device->connection_state = state;
    device->last_seen_ms = time_get_ms();

    pthread_mutex_unlock(&registry->lock);

    /* Invoke callback outside lock to avoid deadlocks */
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
                                         iops_t status,
                                         data_quality_t quality) {
    if (!registry || !station_name || slot < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&registry->lock);

    rtu_device_t *device = find_device_locked(registry, station_name);
    if (!device) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    if (slot >= device->sensor_capacity) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_INVALID_PARAM;
    }

    device->sensors[slot].value = value;
    device->sensors[slot].status = status;
    device->sensors[slot].quality = quality;
    device->sensors[slot].timestamp_ms = time_get_ms();
    device->sensors[slot].stale = false;

    pthread_mutex_unlock(&registry->lock);

    return WTC_OK;
}

wtc_result_t rtu_registry_update_actuator(rtu_registry_t *registry,
                                           const char *station_name,
                                           int slot,
                                           const actuator_output_t *output) {
    if (!registry || !station_name || !output || slot < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&registry->lock);

    rtu_device_t *device = find_device_locked(registry, station_name);
    if (!device) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    if (slot >= device->actuator_capacity) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_INVALID_PARAM;
    }

    memcpy(&device->actuators[slot].output, output, sizeof(actuator_output_t));
    device->actuators[slot].last_change_ms = time_get_ms();

    pthread_mutex_unlock(&registry->lock);

    return WTC_OK;
}

wtc_result_t rtu_registry_get_sensor(rtu_registry_t *registry,
                                      const char *station_name,
                                      int slot,
                                      sensor_data_t *data) {
    if (!registry || !station_name || !data || slot < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&registry->lock);

    rtu_device_t *device = find_device_locked(registry, station_name);
    if (!device) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    if (slot >= device->sensor_capacity) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_INVALID_PARAM;
    }

    memcpy(data, &device->sensors[slot], sizeof(sensor_data_t));

    pthread_mutex_unlock(&registry->lock);

    /* Check staleness (safe on the copy) */
    uint64_t now = time_get_ms();
    if (now - data->timestamp_ms > 5000) {
        data->stale = true;
    }

    return WTC_OK;
}

wtc_result_t rtu_registry_get_actuator(rtu_registry_t *registry,
                                        const char *station_name,
                                        int slot,
                                        actuator_state_t *state) {
    if (!registry || !station_name || !state || slot < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&registry->lock);

    rtu_device_t *device = find_device_locked(registry, station_name);
    if (!device) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    if (slot >= device->actuator_capacity) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_INVALID_PARAM;
    }

    memcpy(state, &device->actuators[slot], sizeof(actuator_state_t));

    pthread_mutex_unlock(&registry->lock);

    return WTC_OK;
}

/* REG-H1 fix: Implement actual persistence using JSON file */
wtc_result_t rtu_registry_save_topology(rtu_registry_t *registry) {
    if (!registry) {
        return WTC_ERROR_INVALID_PARAM;
    }

    const char *path = registry->config.database_path;
    if (!path) {
        path = "/var/lib/water-controller/topology.json";
    }

    pthread_mutex_lock(&registry->lock);

    /* Build JSON content */
    char *buffer = malloc(65536);
    if (!buffer) {
        pthread_mutex_unlock(&registry->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    int pos = 0;
    pos += snprintf(buffer + pos, 65536 - pos, "{\"version\":1,\"devices\":[");

    for (int i = 0; i < registry->device_count; i++) {
        rtu_device_t *dev = registry->devices[i];
        if (i > 0) {
            pos += snprintf(buffer + pos, 65536 - pos, ",");
        }

        pos += snprintf(buffer + pos, 65536 - pos,
            "{\"station_name\":\"%s\",\"ip_address\":\"%s\","
            "\"vendor_id\":%u,\"device_id\":%u,"
            "\"slot_count\":%d,\"slots\":[",
            dev->station_name, dev->ip_address,
            dev->vendor_id, dev->device_id, dev->slot_count);

        for (int j = 0; j < dev->slot_count; j++) {
            if (j > 0) {
                pos += snprintf(buffer + pos, 65536 - pos, ",");
            }
            pos += snprintf(buffer + pos, 65536 - pos,
                "{\"number\":%d,\"type\":%d,\"subslot\":%d,\"name\":\"%s\"}",
                dev->slots[j].slot, dev->slots[j].type,
                dev->slots[j].subslot, dev->slots[j].name);
        }

        pos += snprintf(buffer + pos, 65536 - pos, "]}");
    }

    pos += snprintf(buffer + pos, 65536 - pos, "]}");

    pthread_mutex_unlock(&registry->lock);

    FILE *fp = fopen(path, "w");
    if (!fp) {
        LOG_ERROR("Failed to open topology file for writing: %s", path);
        free(buffer);
        return WTC_ERROR_IO;
    }

    size_t written = fwrite(buffer, 1, pos, fp);
    fclose(fp);
    free(buffer);

    if (written != (size_t)pos) {
        LOG_ERROR("Failed to write complete topology file");
        return WTC_ERROR_IO;
    }

    LOG_INFO("Saved topology to %s (%d devices)", path, registry->device_count);
    return WTC_OK;
}

wtc_result_t rtu_registry_load_topology(rtu_registry_t *registry) {
    if (!registry) {
        return WTC_ERROR_INVALID_PARAM;
    }

    const char *path = registry->config.database_path;
    if (!path) {
        path = "/var/lib/water-controller/topology.json";
    }

    FILE *fp = fopen(path, "r");
    if (!fp) {
        LOG_INFO("No existing topology file at %s", path);
        return WTC_OK;
    }

    fseek(fp, 0, SEEK_END);
    long size = ftell(fp);
    fseek(fp, 0, SEEK_SET);

    if (size <= 0 || size > 1024 * 1024) {
        fclose(fp);
        LOG_WARN("Topology file invalid size: %ld", size);
        return WTC_ERROR_INVALID_PARAM;
    }

    char *buffer = malloc(size + 1);
    if (!buffer) {
        fclose(fp);
        return WTC_ERROR_NO_MEMORY;
    }

    size_t read_bytes = fread(buffer, 1, size, fp);
    fclose(fp);

    if (read_bytes != (size_t)size) {
        free(buffer);
        return WTC_ERROR_IO;
    }
    buffer[size] = '\0';

    const char *p = buffer;
    int loaded = 0;

    while ((p = strstr(p, "\"station_name\":\"")) != NULL) {
        p += 16;
        const char *end = strchr(p, '"');
        if (!end) break;

        char station_name[64] = {0};
        size_t len = end - p;
        if (len >= sizeof(station_name)) len = sizeof(station_name) - 1;
        strncpy(station_name, p, len);

        const char *ip_start = strstr(end, "\"ip_address\":\"");
        char ip_address[16] = {0};
        if (ip_start) {
            ip_start += 14;
            const char *ip_end = strchr(ip_start, '"');
            if (ip_end) {
                len = ip_end - ip_start;
                if (len >= sizeof(ip_address)) len = sizeof(ip_address) - 1;
                strncpy(ip_address, ip_start, len);
            }
        }

        wtc_result_t res = rtu_registry_add_device(registry, station_name,
                                                    ip_address[0] ? ip_address : NULL,
                                                    NULL, 0);
        if (res == WTC_OK) {
            loaded++;
        }

        p = end;
    }

    free(buffer);
    LOG_INFO("Loaded %d devices from %s", loaded, path);
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
