/*
 * Water Treatment Controller - Configuration Manager Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "config_manager.h"
#include "logger.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <ctype.h>

#define LOG_TAG "CONFIG"
#define MAX_CONFIG_ENTRIES 256
#define MAX_KEY_LEN 64
#define MAX_VALUE_LEN 256

/* Configuration entry */
typedef struct {
    char key[MAX_KEY_LEN];
    char value[MAX_VALUE_LEN];
} config_entry_t;

/* Configuration manager structure */
struct config_manager {
    char config_path[256];
    config_entry_t entries[MAX_CONFIG_ENTRIES];
    int entry_count;
    system_config_t config;
    config_change_callback_t callback;
    void *callback_ctx;
};

/* Helper to trim whitespace */
static char *trim(char *str) {
    while (isspace((unsigned char)*str)) str++;
    if (*str == 0) return str;

    char *end = str + strlen(str) - 1;
    while (end > str && isspace((unsigned char)*end)) end--;
    end[1] = '\0';

    return str;
}

/* Initialize configuration manager */
wtc_result_t config_manager_init(config_manager_t **mgr, const char *config_path) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;

    config_manager_t *new_mgr = calloc(1, sizeof(config_manager_t));
    if (!new_mgr) {
        return WTC_ERROR_NO_MEMORY;
    }

    if (config_path) {
        strncpy(new_mgr->config_path, config_path, sizeof(new_mgr->config_path) - 1);
    }

    /* Set defaults */
    config_manager_get_defaults(&new_mgr->config);

    LOG_INFO(LOG_TAG, "Configuration manager initialized");
    *mgr = new_mgr;
    return WTC_OK;
}

/* Cleanup configuration manager */
void config_manager_cleanup(config_manager_t *mgr) {
    if (!mgr) return;
    free(mgr);
    LOG_INFO(LOG_TAG, "Configuration manager cleaned up");
}

/* Load configuration from file */
wtc_result_t config_manager_load(config_manager_t *mgr, const char *filename) {
    if (!mgr || !filename) return WTC_ERROR_INVALID_PARAM;

    FILE *fp = fopen(filename, "r");
    if (!fp) {
        LOG_WARN(LOG_TAG, "Config file not found: %s, using defaults", filename);
        return WTC_ERROR_NOT_FOUND;
    }

    char line[512];
    mgr->entry_count = 0;

    while (fgets(line, sizeof(line), fp) && mgr->entry_count < MAX_CONFIG_ENTRIES) {
        char *trimmed = trim(line);

        /* Skip comments and empty lines */
        if (*trimmed == '#' || *trimmed == ';' || *trimmed == '\0') {
            continue;
        }

        /* Parse key=value */
        char *eq = strchr(trimmed, '=');
        if (!eq) continue;

        *eq = '\0';
        char *key = trim(trimmed);
        char *value = trim(eq + 1);

        /* Remove quotes */
        size_t vlen = strlen(value);
        if (vlen >= 2 && (value[0] == '"' || value[0] == '\'')) {
            value++;
            value[strlen(value) - 1] = '\0';
        }

        strncpy(mgr->entries[mgr->entry_count].key, key, MAX_KEY_LEN - 1);
        strncpy(mgr->entries[mgr->entry_count].value, value, MAX_VALUE_LEN - 1);
        mgr->entry_count++;
    }

    fclose(fp);

    /* Apply loaded values to config struct */
    config_manager_get_string(mgr, "system.name", mgr->config.system_name,
                               sizeof(mgr->config.system_name));
    config_manager_get_string(mgr, "profinet.interface", mgr->config.interface_name,
                               sizeof(mgr->config.interface_name));
    config_manager_get_int(mgr, "profinet.cycle_time_ms", (int *)&mgr->config.cycle_time_ms);
    config_manager_get_string(mgr, "database.host", mgr->config.db_host,
                               sizeof(mgr->config.db_host));
    config_manager_get_int(mgr, "database.port", &mgr->config.db_port);
    config_manager_get_string(mgr, "database.name", mgr->config.db_name,
                               sizeof(mgr->config.db_name));
    config_manager_get_string(mgr, "database.user", mgr->config.db_user,
                               sizeof(mgr->config.db_user));
    config_manager_get_string(mgr, "database.password", mgr->config.db_password,
                               sizeof(mgr->config.db_password));
    config_manager_get_int(mgr, "control.scan_rate_ms", (int *)&mgr->config.scan_rate_ms);
    config_manager_get_int(mgr, "historian.sample_rate_ms",
                           (int *)&mgr->config.default_sample_rate_ms);
    config_manager_get_int(mgr, "historian.retention_days", &mgr->config.retention_days);
    config_manager_get_string(mgr, "api.host", mgr->config.api_host,
                               sizeof(mgr->config.api_host));
    config_manager_get_int(mgr, "api.port", &mgr->config.api_port);

    LOG_INFO(LOG_TAG, "Loaded %d configuration entries from %s", mgr->entry_count, filename);
    return WTC_OK;
}

/* Save configuration to file */
wtc_result_t config_manager_save(config_manager_t *mgr, const char *filename) {
    if (!mgr || !filename) return WTC_ERROR_INVALID_PARAM;

    FILE *fp = fopen(filename, "w");
    if (!fp) {
        LOG_ERROR(LOG_TAG, "Cannot write config file: %s", filename);
        return WTC_ERROR_IO;
    }

    fprintf(fp, "# Water Treatment Controller Configuration\n");
    fprintf(fp, "# Generated automatically\n\n");

    fprintf(fp, "[system]\n");
    fprintf(fp, "name = \"%s\"\n", mgr->config.system_name);
    fprintf(fp, "log_level = %d\n", mgr->config.log_level);
    fprintf(fp, "\n");

    fprintf(fp, "[profinet]\n");
    fprintf(fp, "interface = \"%s\"\n", mgr->config.interface_name);
    fprintf(fp, "cycle_time_ms = %u\n", mgr->config.cycle_time_ms);
    fprintf(fp, "vendor_id = %u\n", mgr->config.vendor_id);
    fprintf(fp, "device_id = %u\n", mgr->config.device_id);
    fprintf(fp, "\n");

    fprintf(fp, "[database]\n");
    fprintf(fp, "host = \"%s\"\n", mgr->config.db_host);
    fprintf(fp, "port = %d\n", mgr->config.db_port);
    fprintf(fp, "name = \"%s\"\n", mgr->config.db_name);
    fprintf(fp, "user = \"%s\"\n", mgr->config.db_user);
    fprintf(fp, "# password = \"***\"\n");
    fprintf(fp, "\n");

    fprintf(fp, "[control]\n");
    fprintf(fp, "scan_rate_ms = %u\n", mgr->config.scan_rate_ms);
    fprintf(fp, "max_pid_loops = %d\n", mgr->config.max_pid_loops);
    fprintf(fp, "max_interlocks = %d\n", mgr->config.max_interlocks);
    fprintf(fp, "\n");

    fprintf(fp, "[historian]\n");
    fprintf(fp, "sample_rate_ms = %u\n", mgr->config.default_sample_rate_ms);
    fprintf(fp, "retention_days = %d\n", mgr->config.retention_days);
    fprintf(fp, "\n");

    fprintf(fp, "[api]\n");
    fprintf(fp, "host = \"%s\"\n", mgr->config.api_host);
    fprintf(fp, "port = %d\n", mgr->config.api_port);

    fclose(fp);
    LOG_INFO(LOG_TAG, "Configuration saved to %s", filename);
    return WTC_OK;
}

/* Get system configuration */
wtc_result_t config_manager_get_config(config_manager_t *mgr, system_config_t *config) {
    if (!mgr || !config) return WTC_ERROR_INVALID_PARAM;
    memcpy(config, &mgr->config, sizeof(system_config_t));
    return WTC_OK;
}

/* Set system configuration */
wtc_result_t config_manager_set_config(config_manager_t *mgr, const system_config_t *config) {
    if (!mgr || !config) return WTC_ERROR_INVALID_PARAM;
    memcpy(&mgr->config, config, sizeof(system_config_t));
    return WTC_OK;
}

/* Get string configuration value */
wtc_result_t config_manager_get_string(config_manager_t *mgr, const char *key,
                                        char *value, size_t max_len) {
    if (!mgr || !key || !value) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->entry_count; i++) {
        if (strcmp(mgr->entries[i].key, key) == 0) {
            strncpy(value, mgr->entries[i].value, max_len - 1);
            value[max_len - 1] = '\0';
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Get integer configuration value */
wtc_result_t config_manager_get_int(config_manager_t *mgr, const char *key, int *value) {
    if (!mgr || !key || !value) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->entry_count; i++) {
        if (strcmp(mgr->entries[i].key, key) == 0) {
            *value = atoi(mgr->entries[i].value);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Get float configuration value */
wtc_result_t config_manager_get_float(config_manager_t *mgr, const char *key, float *value) {
    if (!mgr || !key || !value) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->entry_count; i++) {
        if (strcmp(mgr->entries[i].key, key) == 0) {
            *value = (float)atof(mgr->entries[i].value);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Get boolean configuration value */
wtc_result_t config_manager_get_bool(config_manager_t *mgr, const char *key, bool *value) {
    if (!mgr || !key || !value) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->entry_count; i++) {
        if (strcmp(mgr->entries[i].key, key) == 0) {
            const char *v = mgr->entries[i].value;
            *value = (strcmp(v, "true") == 0 || strcmp(v, "1") == 0 ||
                      strcmp(v, "yes") == 0 || strcmp(v, "on") == 0);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Set string configuration value */
wtc_result_t config_manager_set_string(config_manager_t *mgr, const char *key,
                                        const char *value) {
    if (!mgr || !key || !value) return WTC_ERROR_INVALID_PARAM;

    /* Find existing or add new */
    for (int i = 0; i < mgr->entry_count; i++) {
        if (strcmp(mgr->entries[i].key, key) == 0) {
            strncpy(mgr->entries[i].value, value, MAX_VALUE_LEN - 1);
            if (mgr->callback) {
                mgr->callback(key, mgr->callback_ctx);
            }
            return WTC_OK;
        }
    }

    if (mgr->entry_count >= MAX_CONFIG_ENTRIES) {
        return WTC_ERROR_FULL;
    }

    strncpy(mgr->entries[mgr->entry_count].key, key, MAX_KEY_LEN - 1);
    strncpy(mgr->entries[mgr->entry_count].value, value, MAX_VALUE_LEN - 1);
    mgr->entry_count++;

    if (mgr->callback) {
        mgr->callback(key, mgr->callback_ctx);
    }

    return WTC_OK;
}

/* Set integer configuration value */
wtc_result_t config_manager_set_int(config_manager_t *mgr, const char *key, int value) {
    char str[32];
    snprintf(str, sizeof(str), "%d", value);
    return config_manager_set_string(mgr, key, str);
}

/* Set float configuration value */
wtc_result_t config_manager_set_float(config_manager_t *mgr, const char *key, float value) {
    char str[32];
    snprintf(str, sizeof(str), "%f", value);
    return config_manager_set_string(mgr, key, str);
}

/* Set boolean configuration value */
wtc_result_t config_manager_set_bool(config_manager_t *mgr, const char *key, bool value) {
    return config_manager_set_string(mgr, key, value ? "true" : "false");
}

/* Watch for configuration changes */
wtc_result_t config_manager_watch(config_manager_t *mgr, config_change_callback_t cb, void *ctx) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;
    mgr->callback = cb;
    mgr->callback_ctx = ctx;
    return WTC_OK;
}

/* Get default configuration */
void config_manager_get_defaults(system_config_t *config) {
    if (!config) return;

    memset(config, 0, sizeof(system_config_t));

    /* General */
    strncpy(config->system_name, "Water Treatment Controller", sizeof(config->system_name) - 1);
    config->log_level = LOG_LEVEL_INFO;
    strncpy(config->log_file, "/var/log/water-controller.log", sizeof(config->log_file) - 1);

    /* PROFINET - empty interface means auto-detect */
    config->interface_name[0] = '\0';
    config->cycle_time_ms = 1000;
    config->vendor_id = 0x1234;
    config->device_id = 0x0001;

    /* Database */
    strncpy(config->db_host, "localhost", sizeof(config->db_host) - 1);
    config->db_port = 5432;
    strncpy(config->db_name, "water_treatment", sizeof(config->db_name) - 1);
    strncpy(config->db_user, "wtc", sizeof(config->db_user) - 1);

    /* Control */
    config->scan_rate_ms = 100;
    config->max_pid_loops = 64;
    config->max_interlocks = 128;

    /* Historian */
    config->default_sample_rate_ms = 1000;
    config->retention_days = 365;

    /* Web API */
    strncpy(config->api_host, "0.0.0.0", sizeof(config->api_host) - 1);
    config->api_port = 8080;
}
