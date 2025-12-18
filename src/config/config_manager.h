/*
 * Water Treatment Controller - Configuration Manager
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_CONFIG_MANAGER_H
#define WTC_CONFIG_MANAGER_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Configuration manager handle */
typedef struct config_manager config_manager_t;

/* System configuration */
typedef struct {
    /* General */
    char system_name[64];
    log_level_t log_level;
    char log_file[256];

    /* PROFINET */
    char interface_name[32];
    uint32_t cycle_time_ms;
    uint16_t vendor_id;
    uint16_t device_id;

    /* Database */
    char db_host[64];
    int db_port;
    char db_name[64];
    char db_user[64];
    char db_password[64];

    /* Control */
    uint32_t scan_rate_ms;
    int max_pid_loops;
    int max_interlocks;

    /* Historian */
    uint32_t default_sample_rate_ms;
    int retention_days;

    /* Web API */
    char api_host[64];
    int api_port;
} system_config_t;

/* Initialize configuration manager */
wtc_result_t config_manager_init(config_manager_t **mgr, const char *config_path);

/* Cleanup configuration manager */
void config_manager_cleanup(config_manager_t *mgr);

/* Load configuration from file */
wtc_result_t config_manager_load(config_manager_t *mgr, const char *filename);

/* Save configuration to file */
wtc_result_t config_manager_save(config_manager_t *mgr, const char *filename);

/* Get system configuration */
wtc_result_t config_manager_get_config(config_manager_t *mgr, system_config_t *config);

/* Set system configuration */
wtc_result_t config_manager_set_config(config_manager_t *mgr, const system_config_t *config);

/* Get individual configuration values */
wtc_result_t config_manager_get_string(config_manager_t *mgr, const char *key,
                                        char *value, size_t max_len);
wtc_result_t config_manager_get_int(config_manager_t *mgr, const char *key, int *value);
wtc_result_t config_manager_get_float(config_manager_t *mgr, const char *key, float *value);
wtc_result_t config_manager_get_bool(config_manager_t *mgr, const char *key, bool *value);

/* Set individual configuration values */
wtc_result_t config_manager_set_string(config_manager_t *mgr, const char *key,
                                        const char *value);
wtc_result_t config_manager_set_int(config_manager_t *mgr, const char *key, int value);
wtc_result_t config_manager_set_float(config_manager_t *mgr, const char *key, float value);
wtc_result_t config_manager_set_bool(config_manager_t *mgr, const char *key, bool value);

/* Watch for configuration changes */
typedef void (*config_change_callback_t)(const char *key, void *ctx);
wtc_result_t config_manager_watch(config_manager_t *mgr, config_change_callback_t cb, void *ctx);

/* Get default configuration */
void config_manager_get_defaults(system_config_t *config);

#ifdef __cplusplus
}
#endif

#endif /* WTC_CONFIG_MANAGER_H */
