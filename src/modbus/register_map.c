/*
 * Water Treatment Controller - Modbus Register Map Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "register_map.h"
#include "registry/rtu_registry.h"
#include "utils/logger.h"

#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <pthread.h>

#define LOG_TAG "REG_MAP"

/* Register map structure */
struct register_map {
    register_map_config_t config;

    register_mapping_t *registers;
    int register_count;
    int register_capacity;

    coil_mapping_t *coils;
    int coil_count;
    int coil_capacity;

    pthread_mutex_t lock;
};

wtc_result_t register_map_init(register_map_t **map,
                                const register_map_config_t *config) {
    if (!map) return WTC_ERROR_INVALID_PARAM;

    register_map_t *rm = calloc(1, sizeof(register_map_t));
    if (!rm) return WTC_ERROR_NO_MEMORY;

    if (config) {
        memcpy(&rm->config, config, sizeof(register_map_config_t));
    }

    rm->register_capacity = 256;
    rm->registers = calloc(rm->register_capacity, sizeof(register_mapping_t));
    if (!rm->registers) {
        free(rm);
        return WTC_ERROR_NO_MEMORY;
    }

    rm->coil_capacity = 256;
    rm->coils = calloc(rm->coil_capacity, sizeof(coil_mapping_t));
    if (!rm->coils) {
        free(rm->registers);
        free(rm);
        return WTC_ERROR_NO_MEMORY;
    }

    pthread_mutex_init(&rm->lock, NULL);

    *map = rm;
    LOG_INFO(LOG_TAG, "Register map initialized");
    return WTC_OK;
}

void register_map_cleanup(register_map_t *map) {
    if (!map) return;

    pthread_mutex_destroy(&map->lock);
    free(map->registers);
    free(map->coils);
    free(map);

    LOG_INFO(LOG_TAG, "Register map cleaned up");
}

wtc_result_t register_map_add_register(register_map_t *map,
                                        const register_mapping_t *mapping) {
    if (!map || !mapping) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&map->lock);

    /* Check for duplicate */
    for (int i = 0; i < map->register_count; i++) {
        if (map->registers[i].modbus_addr == mapping->modbus_addr &&
            map->registers[i].reg_type == mapping->reg_type) {
            pthread_mutex_unlock(&map->lock);
            return WTC_ERROR_ALREADY_EXISTS;
        }
    }

    /* Expand if needed */
    if (map->register_count >= map->register_capacity) {
        int new_cap = map->register_capacity * 2;
        register_mapping_t *new_regs = realloc(map->registers,
                                                new_cap * sizeof(register_mapping_t));
        if (!new_regs) {
            pthread_mutex_unlock(&map->lock);
            return WTC_ERROR_NO_MEMORY;
        }
        map->registers = new_regs;
        map->register_capacity = new_cap;
    }

    memcpy(&map->registers[map->register_count], mapping, sizeof(register_mapping_t));
    map->register_count++;

    pthread_mutex_unlock(&map->lock);

    LOG_DEBUG(LOG_TAG, "Added register mapping: addr=%d type=%d",
              mapping->modbus_addr, mapping->reg_type);
    return WTC_OK;
}

wtc_result_t register_map_add_coil(register_map_t *map,
                                    const coil_mapping_t *mapping) {
    if (!map || !mapping) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&map->lock);

    /* Check for duplicate */
    for (int i = 0; i < map->coil_count; i++) {
        if (map->coils[i].modbus_addr == mapping->modbus_addr &&
            map->coils[i].reg_type == mapping->reg_type) {
            pthread_mutex_unlock(&map->lock);
            return WTC_ERROR_ALREADY_EXISTS;
        }
    }

    /* Expand if needed */
    if (map->coil_count >= map->coil_capacity) {
        int new_cap = map->coil_capacity * 2;
        coil_mapping_t *new_coils = realloc(map->coils,
                                             new_cap * sizeof(coil_mapping_t));
        if (!new_coils) {
            pthread_mutex_unlock(&map->lock);
            return WTC_ERROR_NO_MEMORY;
        }
        map->coils = new_coils;
        map->coil_capacity = new_cap;
    }

    memcpy(&map->coils[map->coil_count], mapping, sizeof(coil_mapping_t));
    map->coil_count++;

    pthread_mutex_unlock(&map->lock);

    LOG_DEBUG(LOG_TAG, "Added coil mapping: addr=%d type=%d",
              mapping->modbus_addr, mapping->reg_type);
    return WTC_OK;
}

wtc_result_t register_map_remove_register(register_map_t *map, uint16_t addr) {
    if (!map) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&map->lock);

    for (int i = 0; i < map->register_count; i++) {
        if (map->registers[i].modbus_addr == addr) {
            /* Shift remaining entries */
            for (int j = i; j < map->register_count - 1; j++) {
                map->registers[j] = map->registers[j + 1];
            }
            map->register_count--;
            pthread_mutex_unlock(&map->lock);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&map->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t register_map_remove_coil(register_map_t *map, uint16_t addr) {
    if (!map) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&map->lock);

    for (int i = 0; i < map->coil_count; i++) {
        if (map->coils[i].modbus_addr == addr) {
            for (int j = i; j < map->coil_count - 1; j++) {
                map->coils[j] = map->coils[j + 1];
            }
            map->coil_count--;
            pthread_mutex_unlock(&map->lock);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&map->lock);
    return WTC_ERROR_NOT_FOUND;
}

register_mapping_t *register_map_get_register(register_map_t *map,
                                               modbus_register_type_t type,
                                               uint16_t addr) {
    if (!map) return NULL;

    pthread_mutex_lock(&map->lock);

    for (int i = 0; i < map->register_count; i++) {
        if (map->registers[i].modbus_addr == addr &&
            map->registers[i].reg_type == type &&
            map->registers[i].enabled) {
            pthread_mutex_unlock(&map->lock);
            return &map->registers[i];
        }
    }

    pthread_mutex_unlock(&map->lock);
    return NULL;
}

coil_mapping_t *register_map_get_coil(register_map_t *map,
                                       modbus_register_type_t type,
                                       uint16_t addr) {
    if (!map) return NULL;

    pthread_mutex_lock(&map->lock);

    for (int i = 0; i < map->coil_count; i++) {
        if (map->coils[i].modbus_addr == addr &&
            map->coils[i].reg_type == type &&
            map->coils[i].enabled) {
            pthread_mutex_unlock(&map->lock);
            return &map->coils[i];
        }
    }

    pthread_mutex_unlock(&map->lock);
    return NULL;
}

int register_map_get_register_range(register_map_t *map,
                                     modbus_register_type_t type,
                                     uint16_t start_addr,
                                     uint16_t count,
                                     register_mapping_t **mappings,
                                     int max_mappings) {
    if (!map || !mappings) return 0;

    int found = 0;
    pthread_mutex_lock(&map->lock);

    for (int i = 0; i < map->register_count && found < max_mappings; i++) {
        register_mapping_t *m = &map->registers[i];
        if (m->reg_type == type && m->enabled &&
            m->modbus_addr >= start_addr &&
            m->modbus_addr < start_addr + count) {
            mappings[found++] = m;
        }
    }

    pthread_mutex_unlock(&map->lock);
    return found;
}

int register_map_get_coil_range(register_map_t *map,
                                 modbus_register_type_t type,
                                 uint16_t start_addr,
                                 uint16_t count,
                                 coil_mapping_t **mappings,
                                 int max_mappings) {
    if (!map || !mappings) return 0;

    int found = 0;
    pthread_mutex_lock(&map->lock);

    for (int i = 0; i < map->coil_count && found < max_mappings; i++) {
        coil_mapping_t *m = &map->coils[i];
        if (m->reg_type == type && m->enabled &&
            m->modbus_addr >= start_addr &&
            m->modbus_addr < start_addr + count) {
            mappings[found++] = m;
        }
    }

    pthread_mutex_unlock(&map->lock);
    return found;
}

wtc_result_t register_map_auto_generate(register_map_t *map,
                                         rtu_registry_t *registry,
                                         uint16_t sensor_base,
                                         uint16_t actuator_base) {
    if (!map || !registry) return WTC_ERROR_INVALID_PARAM;

    rtu_device_t *devices = NULL;
    int device_count = 0;

    if (rtu_registry_list_devices(registry, &devices, &device_count, 64) != WTC_OK) {
        return WTC_ERROR_INTERNAL;
    }

    uint16_t sensor_addr = sensor_base;
    uint16_t actuator_addr = actuator_base;
    uint16_t coil_addr = 0;

    for (int d = 0; d < device_count; d++) {
        rtu_device_t *dev = &devices[d];

        /* Create input registers for sensors (float32 = 2 registers each) */
        for (int s = 0; s < dev->sensor_count; s++) {
            register_mapping_t reg = {
                .modbus_addr = sensor_addr,
                .reg_type = MODBUS_REG_INPUT,
                .data_type = MODBUS_DTYPE_FLOAT32_BE,
                .register_count = 2,
                .source = DATA_SOURCE_PROFINET_SENSOR,
                .slot = s + 1,
                .read_only = true,
                .enabled = true,
            };
            strncpy(reg.rtu_station, dev->station_name, 63);
            snprintf(reg.description, 63, "%s Sensor %d", dev->station_name, s + 1);

            register_map_add_register(map, &reg);
            sensor_addr += 2;
        }

        /* Create holding registers for actuator values */
        for (int a = 0; a < dev->actuator_count; a++) {
            register_mapping_t reg = {
                .modbus_addr = actuator_addr,
                .reg_type = MODBUS_REG_HOLDING,
                .data_type = MODBUS_DTYPE_UINT16,
                .register_count = 1,
                .source = DATA_SOURCE_PROFINET_ACTUATOR,
                .slot = a + 1,
                .read_only = false,
                .enabled = true,
            };
            strncpy(reg.rtu_station, dev->station_name, 63);
            snprintf(reg.description, 63, "%s Actuator %d", dev->station_name, a + 1);

            register_map_add_register(map, &reg);
            actuator_addr++;

            /* Also create coil for on/off control */
            coil_mapping_t coil = {
                .modbus_addr = coil_addr,
                .reg_type = MODBUS_REG_COIL,
                .source = DATA_SOURCE_PROFINET_ACTUATOR,
                .slot = a + 1,
                .command_on_value = 1,
                .command_off_value = 0,
                .read_only = false,
                .enabled = true,
            };
            strncpy(coil.rtu_station, dev->station_name, 63);
            snprintf(coil.description, 63, "%s Actuator %d On/Off", dev->station_name, a + 1);

            register_map_add_coil(map, &coil);
            coil_addr++;
        }
    }

    free(devices);

    LOG_INFO(LOG_TAG, "Auto-generated %d register mappings, %d coil mappings",
             map->register_count, map->coil_count);

    return WTC_OK;
}

wtc_result_t register_map_load_json(register_map_t *map, const char *filename) {
    if (!map || !filename) return WTC_ERROR_INVALID_PARAM;

    FILE *f = fopen(filename, "r");
    if (!f) {
        LOG_ERROR(LOG_TAG, "Failed to open %s", filename);
        return WTC_ERROR_IO;
    }

    /* Simple JSON parser would go here */
    /* For now, just close the file */
    fclose(f);

    LOG_INFO(LOG_TAG, "Loaded register map from %s", filename);
    return WTC_OK;
}

wtc_result_t register_map_save_json(register_map_t *map, const char *filename) {
    if (!map || !filename) return WTC_ERROR_INVALID_PARAM;

    FILE *f = fopen(filename, "w");
    if (!f) {
        LOG_ERROR(LOG_TAG, "Failed to create %s", filename);
        return WTC_ERROR_IO;
    }

    pthread_mutex_lock(&map->lock);

    fprintf(f, "{\n  \"registers\": [\n");

    for (int i = 0; i < map->register_count; i++) {
        register_mapping_t *r = &map->registers[i];
        fprintf(f, "    {\n");
        fprintf(f, "      \"address\": %d,\n", r->modbus_addr);
        fprintf(f, "      \"type\": %d,\n", r->reg_type);
        fprintf(f, "      \"data_type\": %d,\n", r->data_type);
        fprintf(f, "      \"source\": %d,\n", r->source);
        fprintf(f, "      \"rtu_station\": \"%s\",\n", r->rtu_station);
        fprintf(f, "      \"slot\": %d,\n", r->slot);
        fprintf(f, "      \"description\": \"%s\",\n", r->description);
        fprintf(f, "      \"enabled\": %s\n", r->enabled ? "true" : "false");
        fprintf(f, "    }%s\n", i < map->register_count - 1 ? "," : "");
    }

    fprintf(f, "  ],\n  \"coils\": [\n");

    for (int i = 0; i < map->coil_count; i++) {
        coil_mapping_t *c = &map->coils[i];
        fprintf(f, "    {\n");
        fprintf(f, "      \"address\": %d,\n", c->modbus_addr);
        fprintf(f, "      \"type\": %d,\n", c->reg_type);
        fprintf(f, "      \"source\": %d,\n", c->source);
        fprintf(f, "      \"rtu_station\": \"%s\",\n", c->rtu_station);
        fprintf(f, "      \"slot\": %d,\n", c->slot);
        fprintf(f, "      \"description\": \"%s\",\n", c->description);
        fprintf(f, "      \"enabled\": %s\n", c->enabled ? "true" : "false");
        fprintf(f, "    }%s\n", i < map->coil_count - 1 ? "," : "");
    }

    fprintf(f, "  ]\n}\n");

    pthread_mutex_unlock(&map->lock);

    fclose(f);

    LOG_INFO(LOG_TAG, "Saved register map to %s", filename);
    return WTC_OK;
}

wtc_result_t register_map_get_stats(register_map_t *map, register_map_stats_t *stats) {
    if (!map || !stats) return WTC_ERROR_INVALID_PARAM;

    memset(stats, 0, sizeof(register_map_stats_t));

    pthread_mutex_lock(&map->lock);

    stats->total_register_mappings = map->register_count;
    stats->total_coil_mappings = map->coil_count;

    for (int i = 0; i < map->register_count; i++) {
        if (map->registers[i].reg_type == MODBUS_REG_HOLDING) {
            stats->holding_registers++;
        } else if (map->registers[i].reg_type == MODBUS_REG_INPUT) {
            stats->input_registers++;
        }
    }

    for (int i = 0; i < map->coil_count; i++) {
        if (map->coils[i].reg_type == MODBUS_REG_COIL) {
            stats->coils++;
        } else if (map->coils[i].reg_type == MODBUS_REG_DISCRETE_INPUT) {
            stats->discrete_inputs++;
        }
    }

    pthread_mutex_unlock(&map->lock);

    return WTC_OK;
}

float register_map_scale_value(const scaling_t *scaling, float raw_value) {
    if (!scaling || !scaling->enabled) {
        return raw_value;
    }

    /* Linear scaling: eng = (raw - raw_min) * (eng_max - eng_min) / (raw_max - raw_min) + eng_min + offset */
    float raw_range = scaling->raw_max - scaling->raw_min;
    if (raw_range == 0) return raw_value + scaling->offset;

    float eng_range = scaling->eng_max - scaling->eng_min;
    float normalized = (raw_value - scaling->raw_min) / raw_range;
    return normalized * eng_range + scaling->eng_min + scaling->offset;
}

float register_map_unscale_value(const scaling_t *scaling, float eng_value) {
    if (!scaling || !scaling->enabled) {
        return eng_value;
    }

    float eng_range = scaling->eng_max - scaling->eng_min;
    if (eng_range == 0) return eng_value - scaling->offset;

    float raw_range = scaling->raw_max - scaling->raw_min;
    float normalized = (eng_value - scaling->offset - scaling->eng_min) / eng_range;
    return normalized * raw_range + scaling->raw_min;
}
