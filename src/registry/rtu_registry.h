/*
 * Water Treatment Controller - RTU Registry
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_RTU_REGISTRY_H
#define WTC_RTU_REGISTRY_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* RTU registry handle */
typedef struct rtu_registry rtu_registry_t;

/* Registry configuration */
typedef struct {
    const char *database_path;
    int max_devices;

    /* Callbacks */
    void (*on_device_added)(const rtu_device_t *device, void *ctx);
    void (*on_device_removed)(const char *station_name, void *ctx);
    void (*on_device_state_changed)(const char *station_name,
                                    profinet_state_t old_state,
                                    profinet_state_t new_state,
                                    void *ctx);
    void *callback_ctx;
} registry_config_t;

/* Initialize RTU registry */
wtc_result_t rtu_registry_init(rtu_registry_t **registry,
                                const registry_config_t *config);

/* Cleanup RTU registry */
void rtu_registry_cleanup(rtu_registry_t *registry);

/* Discover devices on network */
wtc_result_t rtu_registry_discover_devices(rtu_registry_t *registry,
                                            const char *interface_name,
                                            uint32_t timeout_ms);

/* Add device to registry */
wtc_result_t rtu_registry_add_device(rtu_registry_t *registry,
                                      const char *station_name,
                                      const char *ip_address,
                                      const slot_config_t *slots,
                                      int slot_count);

/* Remove device from registry */
wtc_result_t rtu_registry_remove_device(rtu_registry_t *registry,
                                         const char *station_name);

/* Get device by station name */
rtu_device_t *rtu_registry_get_device(rtu_registry_t *registry,
                                       const char *station_name);

/* Get device by index */
rtu_device_t *rtu_registry_get_device_by_index(rtu_registry_t *registry,
                                                int index);

/* List all devices */
wtc_result_t rtu_registry_list_devices(rtu_registry_t *registry,
                                        rtu_device_t **devices,
                                        int *count,
                                        int max_count);

/* Get device count */
int rtu_registry_get_device_count(rtu_registry_t *registry);

/* Set device slot configuration */
wtc_result_t rtu_registry_set_device_config(rtu_registry_t *registry,
                                             const char *station_name,
                                             const slot_config_t *slots,
                                             int slot_count);

/* Update device state */
wtc_result_t rtu_registry_set_device_state(rtu_registry_t *registry,
                                            const char *station_name,
                                            profinet_state_t state);

/* Update sensor data with quality
 * Uses 5-byte sensor format: Float32 + Quality byte
 */
wtc_result_t rtu_registry_update_sensor(rtu_registry_t *registry,
                                         const char *station_name,
                                         int slot,
                                         float value,
                                         iops_t status,
                                         data_quality_t quality);

/* Update actuator state */
wtc_result_t rtu_registry_update_actuator(rtu_registry_t *registry,
                                           const char *station_name,
                                           int slot,
                                           const actuator_output_t *output);

/* Get sensor data */
wtc_result_t rtu_registry_get_sensor(rtu_registry_t *registry,
                                      const char *station_name,
                                      int slot,
                                      sensor_data_t *data);

/* Get actuator state */
wtc_result_t rtu_registry_get_actuator(rtu_registry_t *registry,
                                        const char *station_name,
                                        int slot,
                                        actuator_state_t *state);

/* Save registry to database */
wtc_result_t rtu_registry_save_topology(rtu_registry_t *registry);

/* Load registry from database */
wtc_result_t rtu_registry_load_topology(rtu_registry_t *registry);

/* Export registry to JSON */
wtc_result_t rtu_registry_export_json(rtu_registry_t *registry,
                                       char *buffer,
                                       size_t buffer_size);

/* Import registry from JSON */
wtc_result_t rtu_registry_import_json(rtu_registry_t *registry,
                                       const char *json_string);

/* Get registry statistics */
typedef struct {
    int total_devices;
    int connected_devices;
    int disconnected_devices;
    int error_devices;
    uint64_t total_packets_rx;
    uint64_t total_packets_tx;
    float avg_latency_ms;
} registry_stats_t;

wtc_result_t rtu_registry_get_stats(rtu_registry_t *registry,
                                     registry_stats_t *stats);

#ifdef __cplusplus
}
#endif

#endif /* WTC_RTU_REGISTRY_H */
