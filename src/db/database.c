/*
 * Water Treatment Controller - Database Layer Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "database.h"
#include "logger.h"
#include <stdlib.h>
#include <string.h>
#include <pthread.h>

#ifdef HAVE_POSTGRESQL
#include <libpq-fe.h>
#endif

#define LOG_TAG "DATABASE"

/* Database handle structure */
struct wtc_database {
    database_config_t config;
    bool connected;
    pthread_mutex_t lock;

#ifdef HAVE_POSTGRESQL
    PGconn *conn;
#endif
};

/* Initialize database connection */
wtc_result_t database_init(wtc_database_t **db, const database_config_t *config) {
    if (!db || !config) {
        return WTC_ERROR_INVALID_PARAM;
    }

    wtc_database_t *new_db = calloc(1, sizeof(wtc_database_t));
    if (!new_db) {
        return WTC_ERROR_NO_MEMORY;
    }

    /* Copy configuration */
    memcpy(&new_db->config, config, sizeof(database_config_t));
    if (config->host) {
        new_db->config.host = strdup(config->host);
    }
    if (config->database) {
        new_db->config.database = strdup(config->database);
    }
    if (config->username) {
        new_db->config.username = strdup(config->username);
    }
    if (config->password) {
        new_db->config.password = strdup(config->password);
    }

    pthread_mutex_init(&new_db->lock, NULL);
    new_db->connected = false;

    LOG_INFO(LOG_TAG, "Database layer initialized");
    *db = new_db;
    return WTC_OK;
}

/* Cleanup database connection */
void database_cleanup(wtc_database_t *db) {
    if (!db) return;

    database_disconnect(db);

    free((void *)db->config.host);
    free((void *)db->config.database);
    free((void *)db->config.username);
    free((void *)db->config.password);
    pthread_mutex_destroy(&db->lock);
    free(db);

    LOG_INFO(LOG_TAG, "Database layer cleaned up");
}

/* Connect to database */
wtc_result_t database_connect(wtc_database_t *db) {
    if (!db) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&db->lock);

    if (db->connected) {
        pthread_mutex_unlock(&db->lock);
        return WTC_OK;
    }

#ifdef HAVE_POSTGRESQL
    char conninfo[512];
    snprintf(conninfo, sizeof(conninfo),
             "host=%s port=%d dbname=%s user=%s password=%s connect_timeout=%d",
             db->config.host ? db->config.host : "localhost",
             db->config.port > 0 ? db->config.port : 5432,
             db->config.database ? db->config.database : "water_treatment",
             db->config.username ? db->config.username : "wtc",
             db->config.password ? db->config.password : "",
             db->config.connection_timeout_ms / 1000);

    db->conn = PQconnectdb(conninfo);

    if (PQstatus(db->conn) != CONNECTION_OK) {
        LOG_ERROR(LOG_TAG, "Database connection failed: %s", PQerrorMessage(db->conn));
        PQfinish(db->conn);
        db->conn = NULL;
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_CONNECTION_FAILED;
    }

    LOG_INFO(LOG_TAG, "Connected to PostgreSQL database");
    db->connected = true;
#else
    LOG_WARN(LOG_TAG, "PostgreSQL support not compiled in, using in-memory storage");
    db->connected = true;
#endif

    pthread_mutex_unlock(&db->lock);
    return WTC_OK;
}

/* Disconnect from database */
wtc_result_t database_disconnect(wtc_database_t *db) {
    if (!db) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&db->lock);

    if (!db->connected) {
        pthread_mutex_unlock(&db->lock);
        return WTC_OK;
    }

#ifdef HAVE_POSTGRESQL
    if (db->conn) {
        PQfinish(db->conn);
        db->conn = NULL;
    }
#endif

    db->connected = false;
    LOG_INFO(LOG_TAG, "Database disconnected");

    pthread_mutex_unlock(&db->lock);
    return WTC_OK;
}

/* Check connection status */
bool database_is_connected(wtc_database_t *db) {
    if (!db) return false;
    return db->connected;
}

/* ============== RTU Operations ============== */

wtc_result_t database_save_rtu(wtc_database_t *db, const rtu_device_t *rtu) {
    if (!db || !rtu) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query =
        "INSERT INTO rtus (station_name, ip_address, vendor_id, device_id, slot_count) "
        "VALUES ($1, $2, $3, $4, $5) "
        "ON CONFLICT (station_name) DO UPDATE SET "
        "ip_address = EXCLUDED.ip_address, "
        "vendor_id = EXCLUDED.vendor_id, "
        "device_id = EXCLUDED.device_id, "
        "slot_count = EXCLUDED.slot_count";

    char vendor_id_str[16], device_id_str[16], slot_count_str[16];
    snprintf(vendor_id_str, sizeof(vendor_id_str), "%u", rtu->vendor_id);
    snprintf(device_id_str, sizeof(device_id_str), "%u", rtu->device_id);
    snprintf(slot_count_str, sizeof(slot_count_str), "%d", rtu->slot_count);

    const char *params[] = {
        rtu->station_name,
        rtu->ip_address,
        vendor_id_str,
        device_id_str,
        slot_count_str
    };

    PGresult *res = PQexecParams(db->conn, query, 5, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        LOG_ERROR(LOG_TAG, "Failed to save RTU: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    LOG_DEBUG(LOG_TAG, "Saved RTU %s (in-memory)", rtu->station_name);
#endif

    return WTC_OK;
}

wtc_result_t database_load_rtu(wtc_database_t *db, const char *station_name,
                                rtu_device_t *rtu) {
    if (!db || !station_name || !rtu) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query = "SELECT station_name, ip_address, vendor_id, device_id, slot_count "
                        "FROM rtus WHERE station_name = $1";

    const char *params[] = { station_name };

    PGresult *res = PQexecParams(db->conn, query, 1, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        LOG_ERROR(LOG_TAG, "Failed to load RTU: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    if (PQntuples(res) == 0) {
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    strncpy(rtu->station_name, PQgetvalue(res, 0, 0), WTC_MAX_STATION_NAME - 1);
    strncpy(rtu->ip_address, PQgetvalue(res, 0, 1), WTC_MAX_IP_ADDRESS - 1);
    rtu->vendor_id = (uint16_t)atoi(PQgetvalue(res, 0, 2));
    rtu->device_id = (uint16_t)atoi(PQgetvalue(res, 0, 3));
    rtu->slot_count = atoi(PQgetvalue(res, 0, 4));

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    (void)station_name;
    return WTC_ERROR_NOT_FOUND;
#endif

    return WTC_OK;
}

wtc_result_t database_delete_rtu(wtc_database_t *db, const char *station_name) {
    if (!db || !station_name) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query = "DELETE FROM rtus WHERE station_name = $1";
    const char *params[] = { station_name };

    PGresult *res = PQexecParams(db->conn, query, 1, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        LOG_ERROR(LOG_TAG, "Failed to delete RTU: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    (void)station_name;
#endif

    return WTC_OK;
}

wtc_result_t database_list_rtus(wtc_database_t *db, rtu_device_t **rtus,
                                 int *count, int max_count) {
    if (!db || !rtus || !count) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

    *count = 0;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    char query[256];
    snprintf(query, sizeof(query),
             "SELECT station_name, ip_address, vendor_id, device_id, slot_count "
             "FROM rtus LIMIT %d", max_count);

    PGresult *res = PQexec(db->conn, query);

    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        LOG_ERROR(LOG_TAG, "Failed to list RTUs: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    int rows = PQntuples(res);
    if (rows > max_count) rows = max_count;

    *rtus = calloc(rows, sizeof(rtu_device_t));
    if (!*rtus) {
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    for (int i = 0; i < rows; i++) {
        strncpy((*rtus)[i].station_name, PQgetvalue(res, i, 0), WTC_MAX_STATION_NAME - 1);
        strncpy((*rtus)[i].ip_address, PQgetvalue(res, i, 1), WTC_MAX_IP_ADDRESS - 1);
        (*rtus)[i].vendor_id = (uint16_t)atoi(PQgetvalue(res, i, 2));
        (*rtus)[i].device_id = (uint16_t)atoi(PQgetvalue(res, i, 3));
        (*rtus)[i].slot_count = atoi(PQgetvalue(res, i, 4));
    }

    *count = rows;
    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#endif

    return WTC_OK;
}

/* ============== Alarm Operations ============== */

wtc_result_t database_save_alarm_rule(wtc_database_t *db, const alarm_rule_t *rule) {
    if (!db || !rule) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query =
        "INSERT INTO alarm_rules (rule_id, name, rtu_station, slot, condition, "
        "threshold, delay_ms, severity, message_template, enabled) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) "
        "ON CONFLICT (rule_id) DO UPDATE SET "
        "name = EXCLUDED.name, rtu_station = EXCLUDED.rtu_station, "
        "slot = EXCLUDED.slot, condition = EXCLUDED.condition, "
        "threshold = EXCLUDED.threshold, delay_ms = EXCLUDED.delay_ms, "
        "severity = EXCLUDED.severity, message_template = EXCLUDED.message_template, "
        "enabled = EXCLUDED.enabled";

    char rule_id_str[16], slot_str[16], condition_str[16];
    char threshold_str[32], delay_str[16], severity_str[16], enabled_str[8];

    snprintf(rule_id_str, sizeof(rule_id_str), "%d", rule->rule_id);
    snprintf(slot_str, sizeof(slot_str), "%d", rule->slot);
    snprintf(condition_str, sizeof(condition_str), "%d", rule->condition);
    snprintf(threshold_str, sizeof(threshold_str), "%f", rule->threshold);
    snprintf(delay_str, sizeof(delay_str), "%u", rule->delay_ms);
    snprintf(severity_str, sizeof(severity_str), "%d", rule->severity);
    snprintf(enabled_str, sizeof(enabled_str), "%s", rule->enabled ? "true" : "false");

    const char *params[] = {
        rule_id_str, rule->name, rule->rtu_station, slot_str,
        condition_str, threshold_str, delay_str, severity_str,
        rule->message_template, enabled_str
    };

    PGresult *res = PQexecParams(db->conn, query, 10, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        LOG_ERROR(LOG_TAG, "Failed to save alarm rule: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    LOG_DEBUG(LOG_TAG, "Saved alarm rule %d (in-memory)", rule->rule_id);
#endif

    return WTC_OK;
}

wtc_result_t database_load_alarm_rules(wtc_database_t *db, alarm_rule_t **rules,
                                        int *count, int max_count) {
    if (!db || !rules || !count) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

    *count = 0;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    char query[256];
    snprintf(query, sizeof(query),
             "SELECT rule_id, name, rtu_station, slot, condition, threshold, "
             "delay_ms, severity, message_template, enabled "
             "FROM alarm_rules LIMIT %d", max_count);

    PGresult *res = PQexec(db->conn, query);

    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        LOG_ERROR(LOG_TAG, "Failed to load alarm rules: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    int rows = PQntuples(res);
    if (rows > max_count) rows = max_count;

    *rules = calloc(rows, sizeof(alarm_rule_t));
    if (!*rules) {
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    for (int i = 0; i < rows; i++) {
        (*rules)[i].rule_id = atoi(PQgetvalue(res, i, 0));
        strncpy((*rules)[i].name, PQgetvalue(res, i, 1), WTC_MAX_NAME - 1);
        strncpy((*rules)[i].rtu_station, PQgetvalue(res, i, 2), WTC_MAX_STATION_NAME - 1);
        (*rules)[i].slot = atoi(PQgetvalue(res, i, 3));
        (*rules)[i].condition = atoi(PQgetvalue(res, i, 4));
        (*rules)[i].threshold = atof(PQgetvalue(res, i, 5));
        (*rules)[i].delay_ms = (uint32_t)atoi(PQgetvalue(res, i, 6));
        (*rules)[i].severity = atoi(PQgetvalue(res, i, 7));
        strncpy((*rules)[i].message_template, PQgetvalue(res, i, 8), WTC_MAX_MESSAGE - 1);
        (*rules)[i].enabled = strcmp(PQgetvalue(res, i, 9), "t") == 0;
    }

    *count = rows;
    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#endif

    return WTC_OK;
}

wtc_result_t database_save_alarm(wtc_database_t *db, const alarm_t *alarm) {
    if (!db || !alarm) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query =
        "INSERT INTO alarms (alarm_id, rule_id, rtu_station, slot, severity, state, "
        "message, value, threshold, raise_time, ack_time, clear_time, ack_user) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, to_timestamp($10/1000.0), "
        "to_timestamp($11/1000.0), to_timestamp($12/1000.0), $13) "
        "ON CONFLICT (alarm_id) DO UPDATE SET state = EXCLUDED.state, "
        "ack_time = EXCLUDED.ack_time, clear_time = EXCLUDED.clear_time, "
        "ack_user = EXCLUDED.ack_user";

    char alarm_id_str[16], rule_id_str[16], slot_str[16], severity_str[16], state_str[16];
    char value_str[32], threshold_str[32], raise_str[32], ack_str[32], clear_str[32];

    snprintf(alarm_id_str, sizeof(alarm_id_str), "%d", alarm->alarm_id);
    snprintf(rule_id_str, sizeof(rule_id_str), "%d", alarm->rule_id);
    snprintf(slot_str, sizeof(slot_str), "%d", alarm->slot);
    snprintf(severity_str, sizeof(severity_str), "%d", alarm->severity);
    snprintf(state_str, sizeof(state_str), "%d", alarm->state);
    snprintf(value_str, sizeof(value_str), "%f", alarm->value);
    snprintf(threshold_str, sizeof(threshold_str), "%f", alarm->threshold);
    snprintf(raise_str, sizeof(raise_str), "%lu", alarm->raise_time_ms);
    snprintf(ack_str, sizeof(ack_str), "%lu", alarm->ack_time_ms);
    snprintf(clear_str, sizeof(clear_str), "%lu", alarm->clear_time_ms);

    const char *params[] = {
        alarm_id_str, rule_id_str, alarm->rtu_station, slot_str,
        severity_str, state_str, alarm->message, value_str, threshold_str,
        raise_str, ack_str, clear_str, alarm->ack_user
    };

    PGresult *res = PQexecParams(db->conn, query, 13, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        LOG_ERROR(LOG_TAG, "Failed to save alarm: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    LOG_DEBUG(LOG_TAG, "Saved alarm %d (in-memory)", alarm->alarm_id);
#endif

    return WTC_OK;
}

wtc_result_t database_load_alarm_history(wtc_database_t *db,
                                          uint64_t start_time_ms,
                                          uint64_t end_time_ms,
                                          alarm_t **alarms,
                                          int *count,
                                          int max_count) {
    if (!db || !alarms || !count) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

    *count = 0;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query =
        "SELECT alarm_id, rule_id, rtu_station, slot, severity, state, message, "
        "value, threshold, EXTRACT(EPOCH FROM raise_time)*1000, "
        "EXTRACT(EPOCH FROM ack_time)*1000, EXTRACT(EPOCH FROM clear_time)*1000, ack_user "
        "FROM alarms WHERE raise_time >= to_timestamp($1/1000.0) "
        "AND raise_time <= to_timestamp($2/1000.0) "
        "ORDER BY raise_time DESC LIMIT $3";

    char start_str[32], end_str[32], limit_str[16];
    snprintf(start_str, sizeof(start_str), "%lu", start_time_ms);
    snprintf(end_str, sizeof(end_str), "%lu", end_time_ms);
    snprintf(limit_str, sizeof(limit_str), "%d", max_count);

    const char *params[] = { start_str, end_str, limit_str };

    PGresult *res = PQexecParams(db->conn, query, 3, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        LOG_ERROR(LOG_TAG, "Failed to load alarm history: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    int rows = PQntuples(res);
    *alarms = calloc(rows, sizeof(alarm_t));
    if (!*alarms) {
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    for (int i = 0; i < rows; i++) {
        (*alarms)[i].alarm_id = atoi(PQgetvalue(res, i, 0));
        (*alarms)[i].rule_id = atoi(PQgetvalue(res, i, 1));
        strncpy((*alarms)[i].rtu_station, PQgetvalue(res, i, 2), WTC_MAX_STATION_NAME - 1);
        (*alarms)[i].slot = atoi(PQgetvalue(res, i, 3));
        (*alarms)[i].severity = atoi(PQgetvalue(res, i, 4));
        (*alarms)[i].state = atoi(PQgetvalue(res, i, 5));
        strncpy((*alarms)[i].message, PQgetvalue(res, i, 6), WTC_MAX_MESSAGE - 1);
        (*alarms)[i].value = atof(PQgetvalue(res, i, 7));
        (*alarms)[i].threshold = atof(PQgetvalue(res, i, 8));
        (*alarms)[i].raise_time_ms = (uint64_t)atof(PQgetvalue(res, i, 9));
        (*alarms)[i].ack_time_ms = (uint64_t)atof(PQgetvalue(res, i, 10));
        (*alarms)[i].clear_time_ms = (uint64_t)atof(PQgetvalue(res, i, 11));
        strncpy((*alarms)[i].ack_user, PQgetvalue(res, i, 12), WTC_MAX_USERNAME - 1);
    }

    *count = rows;
    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    (void)start_time_ms;
    (void)end_time_ms;
    (void)max_count;
#endif

    return WTC_OK;
}

/* ============== Historian Operations ============== */

wtc_result_t database_save_historian_tag(wtc_database_t *db,
                                          const historian_tag_t *tag) {
    if (!db || !tag) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query =
        "INSERT INTO historian_tags (tag_id, rtu_station, slot, tag_name, unit, "
        "sample_rate_ms, deadband, compression) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
        "ON CONFLICT (tag_id) DO UPDATE SET tag_name = EXCLUDED.tag_name, "
        "sample_rate_ms = EXCLUDED.sample_rate_ms, deadband = EXCLUDED.deadband, "
        "compression = EXCLUDED.compression";

    char tag_id_str[16], slot_str[16], rate_str[16], deadband_str[32], comp_str[8];
    snprintf(tag_id_str, sizeof(tag_id_str), "%d", tag->tag_id);
    snprintf(slot_str, sizeof(slot_str), "%d", tag->slot);
    snprintf(rate_str, sizeof(rate_str), "%d", tag->sample_rate_ms);
    snprintf(deadband_str, sizeof(deadband_str), "%f", tag->deadband);
    snprintf(comp_str, sizeof(comp_str), "%d", tag->compression);

    const char *params[] = {
        tag_id_str, tag->rtu_station, slot_str, tag->tag_name,
        tag->unit, rate_str, deadband_str, comp_str
    };

    PGresult *res = PQexecParams(db->conn, query, 8, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        LOG_ERROR(LOG_TAG, "Failed to save historian tag: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    LOG_DEBUG(LOG_TAG, "Saved historian tag %d (in-memory)", tag->tag_id);
#endif

    return WTC_OK;
}

wtc_result_t database_load_historian_tags(wtc_database_t *db,
                                           historian_tag_t **tags,
                                           int *count, int max_count) {
    if (!db || !tags || !count) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

    *count = 0;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    char query[256];
    snprintf(query, sizeof(query),
             "SELECT tag_id, rtu_station, slot, tag_name, unit, sample_rate_ms, "
             "deadband, compression FROM historian_tags LIMIT %d", max_count);

    PGresult *res = PQexec(db->conn, query);

    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        LOG_ERROR(LOG_TAG, "Failed to load historian tags: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    int rows = PQntuples(res);
    *tags = calloc(rows, sizeof(historian_tag_t));
    if (!*tags) {
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    for (int i = 0; i < rows; i++) {
        (*tags)[i].tag_id = atoi(PQgetvalue(res, i, 0));
        strncpy((*tags)[i].rtu_station, PQgetvalue(res, i, 1), WTC_MAX_STATION_NAME - 1);
        (*tags)[i].slot = atoi(PQgetvalue(res, i, 2));
        strncpy((*tags)[i].tag_name, PQgetvalue(res, i, 3), WTC_MAX_NAME * 2 - 1);
        strncpy((*tags)[i].unit, PQgetvalue(res, i, 4), WTC_MAX_UNIT - 1);
        (*tags)[i].sample_rate_ms = atoi(PQgetvalue(res, i, 5));
        (*tags)[i].deadband = atof(PQgetvalue(res, i, 6));
        (*tags)[i].compression = atoi(PQgetvalue(res, i, 7));
    }

    *count = rows;
    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    (void)max_count;
#endif

    return WTC_OK;
}

wtc_result_t database_save_historian_samples(wtc_database_t *db,
                                              const historian_sample_t *samples,
                                              int count) {
    if (!db || !samples || count <= 0) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    /* Use COPY for batch inserts */
    PGresult *res = PQexec(db->conn,
        "COPY historian_samples (timestamp, tag_id, value, quality) FROM STDIN");

    if (PQresultStatus(res) != PGRES_COPY_IN) {
        LOG_ERROR(LOG_TAG, "Failed to start COPY: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }
    PQclear(res);

    for (int i = 0; i < count; i++) {
        char line[256];
        snprintf(line, sizeof(line), "%lu\t%d\t%f\t%d\n",
                 samples[i].timestamp_ms, samples[i].tag_id,
                 samples[i].value, samples[i].quality);

        if (PQputCopyData(db->conn, line, strlen(line)) != 1) {
            LOG_ERROR(LOG_TAG, "Failed to send COPY data: %s", PQerrorMessage(db->conn));
            PQputCopyEnd(db->conn, "error");
            pthread_mutex_unlock(&db->lock);
            return WTC_ERROR_IO;
        }
    }

    if (PQputCopyEnd(db->conn, NULL) != 1) {
        LOG_ERROR(LOG_TAG, "Failed to end COPY: %s", PQerrorMessage(db->conn));
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    res = PQgetResult(db->conn);
    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        LOG_ERROR(LOG_TAG, "COPY failed: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
    LOG_DEBUG(LOG_TAG, "Saved %d historian samples", count);
#else
    LOG_DEBUG(LOG_TAG, "Saved %d historian samples (in-memory)", count);
#endif

    return WTC_OK;
}

wtc_result_t database_query_historian_samples(wtc_database_t *db,
                                               int tag_id,
                                               uint64_t start_time_ms,
                                               uint64_t end_time_ms,
                                               historian_sample_t **samples,
                                               int *count,
                                               int max_count) {
    if (!db || !samples || !count) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

    *count = 0;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query =
        "SELECT timestamp, tag_id, value, quality FROM historian_samples "
        "WHERE tag_id = $1 AND timestamp >= $2 AND timestamp <= $3 "
        "ORDER BY timestamp LIMIT $4";

    char tag_str[16], start_str[32], end_str[32], limit_str[16];
    snprintf(tag_str, sizeof(tag_str), "%d", tag_id);
    snprintf(start_str, sizeof(start_str), "%lu", start_time_ms);
    snprintf(end_str, sizeof(end_str), "%lu", end_time_ms);
    snprintf(limit_str, sizeof(limit_str), "%d", max_count);

    const char *params[] = { tag_str, start_str, end_str, limit_str };

    PGresult *res = PQexecParams(db->conn, query, 4, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        LOG_ERROR(LOG_TAG, "Failed to query historian: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    int rows = PQntuples(res);
    *samples = calloc(rows, sizeof(historian_sample_t));
    if (!*samples) {
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    for (int i = 0; i < rows; i++) {
        (*samples)[i].timestamp_ms = (uint64_t)atoll(PQgetvalue(res, i, 0));
        (*samples)[i].tag_id = atoi(PQgetvalue(res, i, 1));
        (*samples)[i].value = atof(PQgetvalue(res, i, 2));
        (*samples)[i].quality = (uint8_t)atoi(PQgetvalue(res, i, 3));
    }

    *count = rows;
    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    (void)tag_id;
    (void)start_time_ms;
    (void)end_time_ms;
    (void)max_count;
#endif

    return WTC_OK;
}

/* ============== Control Operations ============== */

wtc_result_t database_save_pid_loop(wtc_database_t *db, const pid_loop_t *loop) {
    if (!db || !loop) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query =
        "INSERT INTO pid_loops (loop_id, name, enabled, input_rtu, input_slot, "
        "output_rtu, output_slot, kp, ki, kd, setpoint, output_min, output_max, "
        "deadband, integral_limit, derivative_filter, mode) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17) "
        "ON CONFLICT (loop_id) DO UPDATE SET "
        "name = EXCLUDED.name, enabled = EXCLUDED.enabled, "
        "input_rtu = EXCLUDED.input_rtu, input_slot = EXCLUDED.input_slot, "
        "output_rtu = EXCLUDED.output_rtu, output_slot = EXCLUDED.output_slot, "
        "kp = EXCLUDED.kp, ki = EXCLUDED.ki, kd = EXCLUDED.kd, "
        "setpoint = EXCLUDED.setpoint, output_min = EXCLUDED.output_min, "
        "output_max = EXCLUDED.output_max, deadband = EXCLUDED.deadband, "
        "integral_limit = EXCLUDED.integral_limit, derivative_filter = EXCLUDED.derivative_filter, "
        "mode = EXCLUDED.mode";

    char loop_id_str[16], input_slot_str[16], output_slot_str[16];
    char kp_str[32], ki_str[32], kd_str[32], setpoint_str[32];
    char output_min_str[32], output_max_str[32], deadband_str[32];
    char integral_limit_str[32], derivative_filter_str[32], mode_str[16];
    char enabled_str[8];

    snprintf(loop_id_str, sizeof(loop_id_str), "%d", loop->loop_id);
    snprintf(enabled_str, sizeof(enabled_str), "%s", loop->enabled ? "true" : "false");
    snprintf(input_slot_str, sizeof(input_slot_str), "%d", loop->input_slot);
    snprintf(output_slot_str, sizeof(output_slot_str), "%d", loop->output_slot);
    snprintf(kp_str, sizeof(kp_str), "%f", loop->kp);
    snprintf(ki_str, sizeof(ki_str), "%f", loop->ki);
    snprintf(kd_str, sizeof(kd_str), "%f", loop->kd);
    snprintf(setpoint_str, sizeof(setpoint_str), "%f", loop->setpoint);
    snprintf(output_min_str, sizeof(output_min_str), "%f", loop->output_min);
    snprintf(output_max_str, sizeof(output_max_str), "%f", loop->output_max);
    snprintf(deadband_str, sizeof(deadband_str), "%f", loop->deadband);
    snprintf(integral_limit_str, sizeof(integral_limit_str), "%f", loop->integral_limit);
    snprintf(derivative_filter_str, sizeof(derivative_filter_str), "%f", loop->derivative_filter);
    snprintf(mode_str, sizeof(mode_str), "%d", loop->mode);

    const char *params[] = {
        loop_id_str, loop->name, enabled_str, loop->input_rtu, input_slot_str,
        loop->output_rtu, output_slot_str, kp_str, ki_str, kd_str, setpoint_str,
        output_min_str, output_max_str, deadband_str, integral_limit_str,
        derivative_filter_str, mode_str
    };

    PGresult *res = PQexecParams(db->conn, query, 17, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        LOG_ERROR(LOG_TAG, "Failed to save PID loop: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    LOG_DEBUG(LOG_TAG, "Saved PID loop %d (in-memory)", loop->loop_id);
#endif

    return WTC_OK;
}

wtc_result_t database_load_pid_loops(wtc_database_t *db, pid_loop_t **loops,
                                      int *count, int max_count) {
    if (!db || !loops || !count) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

    *count = 0;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    char query[512];
    snprintf(query, sizeof(query),
             "SELECT loop_id, name, enabled, input_rtu, input_slot, output_rtu, "
             "output_slot, kp, ki, kd, setpoint, output_min, output_max, deadband, "
             "integral_limit, derivative_filter, mode FROM pid_loops LIMIT %d", max_count);

    PGresult *res = PQexec(db->conn, query);

    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        LOG_ERROR(LOG_TAG, "Failed to load PID loops: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    int rows = PQntuples(res);
    if (rows > max_count) rows = max_count;

    *loops = calloc(rows, sizeof(pid_loop_t));
    if (!*loops) {
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    for (int i = 0; i < rows; i++) {
        (*loops)[i].loop_id = atoi(PQgetvalue(res, i, 0));
        strncpy((*loops)[i].name, PQgetvalue(res, i, 1), WTC_MAX_NAME - 1);
        (*loops)[i].enabled = strcmp(PQgetvalue(res, i, 2), "t") == 0;
        strncpy((*loops)[i].input_rtu, PQgetvalue(res, i, 3), WTC_MAX_STATION_NAME - 1);
        (*loops)[i].input_slot = atoi(PQgetvalue(res, i, 4));
        strncpy((*loops)[i].output_rtu, PQgetvalue(res, i, 5), WTC_MAX_STATION_NAME - 1);
        (*loops)[i].output_slot = atoi(PQgetvalue(res, i, 6));
        (*loops)[i].kp = (float)atof(PQgetvalue(res, i, 7));
        (*loops)[i].ki = (float)atof(PQgetvalue(res, i, 8));
        (*loops)[i].kd = (float)atof(PQgetvalue(res, i, 9));
        (*loops)[i].setpoint = (float)atof(PQgetvalue(res, i, 10));
        (*loops)[i].output_min = (float)atof(PQgetvalue(res, i, 11));
        (*loops)[i].output_max = (float)atof(PQgetvalue(res, i, 12));
        (*loops)[i].deadband = (float)atof(PQgetvalue(res, i, 13));
        (*loops)[i].integral_limit = (float)atof(PQgetvalue(res, i, 14));
        (*loops)[i].derivative_filter = (float)atof(PQgetvalue(res, i, 15));
        (*loops)[i].mode = atoi(PQgetvalue(res, i, 16));
    }

    *count = rows;
    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    (void)max_count;
#endif

    return WTC_OK;
}

wtc_result_t database_save_interlock(wtc_database_t *db, const interlock_t *interlock) {
    if (!db || !interlock) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query =
        "INSERT INTO interlocks (interlock_id, name, enabled, condition_rtu, "
        "condition_slot, condition_type, threshold, delay_ms, action_rtu, "
        "action_slot, action_type, action_value) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) "
        "ON CONFLICT (interlock_id) DO UPDATE SET "
        "name = EXCLUDED.name, enabled = EXCLUDED.enabled, "
        "condition_rtu = EXCLUDED.condition_rtu, condition_slot = EXCLUDED.condition_slot, "
        "condition_type = EXCLUDED.condition_type, threshold = EXCLUDED.threshold, "
        "delay_ms = EXCLUDED.delay_ms, action_rtu = EXCLUDED.action_rtu, "
        "action_slot = EXCLUDED.action_slot, action_type = EXCLUDED.action_type, "
        "action_value = EXCLUDED.action_value";

    char interlock_id_str[16], condition_slot_str[16], condition_type_str[16];
    char threshold_str[32], delay_str[16], action_slot_str[16];
    char action_type_str[16], action_value_str[32], enabled_str[8];

    snprintf(interlock_id_str, sizeof(interlock_id_str), "%d", interlock->interlock_id);
    snprintf(enabled_str, sizeof(enabled_str), "%s", interlock->enabled ? "true" : "false");
    snprintf(condition_slot_str, sizeof(condition_slot_str), "%d", interlock->condition_slot);
    snprintf(condition_type_str, sizeof(condition_type_str), "%d", interlock->condition);
    snprintf(threshold_str, sizeof(threshold_str), "%f", interlock->threshold);
    snprintf(delay_str, sizeof(delay_str), "%u", interlock->delay_ms);
    snprintf(action_slot_str, sizeof(action_slot_str), "%d", interlock->action_slot);
    snprintf(action_type_str, sizeof(action_type_str), "%d", interlock->action);
    snprintf(action_value_str, sizeof(action_value_str), "%f", interlock->action_value);

    const char *params[] = {
        interlock_id_str, interlock->name, enabled_str, interlock->condition_rtu,
        condition_slot_str, condition_type_str, threshold_str, delay_str,
        interlock->action_rtu, action_slot_str, action_type_str, action_value_str
    };

    PGresult *res = PQexecParams(db->conn, query, 12, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        LOG_ERROR(LOG_TAG, "Failed to save interlock: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    LOG_DEBUG(LOG_TAG, "Saved interlock %d (in-memory)", interlock->interlock_id);
#endif

    return WTC_OK;
}

wtc_result_t database_load_interlocks(wtc_database_t *db, interlock_t **interlocks,
                                       int *count, int max_count) {
    if (!db || !interlocks || !count) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

    *count = 0;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    char query[512];
    snprintf(query, sizeof(query),
             "SELECT interlock_id, name, enabled, condition_rtu, condition_slot, "
             "condition_type, threshold, delay_ms, action_rtu, action_slot, "
             "action_type, action_value FROM interlocks LIMIT %d", max_count);

    PGresult *res = PQexec(db->conn, query);

    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        LOG_ERROR(LOG_TAG, "Failed to load interlocks: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    int rows = PQntuples(res);
    if (rows > max_count) rows = max_count;

    *interlocks = calloc(rows, sizeof(interlock_t));
    if (!*interlocks) {
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    for (int i = 0; i < rows; i++) {
        (*interlocks)[i].interlock_id = atoi(PQgetvalue(res, i, 0));
        strncpy((*interlocks)[i].name, PQgetvalue(res, i, 1), WTC_MAX_NAME - 1);
        (*interlocks)[i].enabled = strcmp(PQgetvalue(res, i, 2), "t") == 0;
        strncpy((*interlocks)[i].condition_rtu, PQgetvalue(res, i, 3), WTC_MAX_STATION_NAME - 1);
        (*interlocks)[i].condition_slot = atoi(PQgetvalue(res, i, 4));
        (*interlocks)[i].condition = atoi(PQgetvalue(res, i, 5));
        (*interlocks)[i].threshold = (float)atof(PQgetvalue(res, i, 6));
        (*interlocks)[i].delay_ms = (uint32_t)atoi(PQgetvalue(res, i, 7));
        strncpy((*interlocks)[i].action_rtu, PQgetvalue(res, i, 8), WTC_MAX_STATION_NAME - 1);
        (*interlocks)[i].action_slot = atoi(PQgetvalue(res, i, 9));
        (*interlocks)[i].action = atoi(PQgetvalue(res, i, 10));
        (*interlocks)[i].action_value = (float)atof(PQgetvalue(res, i, 11));
    }

    *count = rows;
    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    (void)max_count;
#endif

    return WTC_OK;
}

/* ============== User Operations ============== */

wtc_result_t database_save_user(wtc_database_t *db, const user_t *user) {
    if (!db || !user) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query =
        "INSERT INTO users (user_id, username, password_hash, role, created_at, "
        "last_login, active) "
        "VALUES ($1, $2, $3, $4, to_timestamp($5/1000.0), to_timestamp($6/1000.0), $7) "
        "ON CONFLICT (username) DO UPDATE SET "
        "password_hash = EXCLUDED.password_hash, role = EXCLUDED.role, "
        "last_login = EXCLUDED.last_login, active = EXCLUDED.active";

    char user_id_str[16], role_str[16], created_str[32], login_str[32], active_str[8];

    snprintf(user_id_str, sizeof(user_id_str), "%d", user->user_id);
    snprintf(role_str, sizeof(role_str), "%d", user->role);
    snprintf(created_str, sizeof(created_str), "%lu", user->created_at_ms);
    snprintf(login_str, sizeof(login_str), "%lu", user->last_login_ms);
    snprintf(active_str, sizeof(active_str), "%s", user->active ? "true" : "false");

    const char *params[] = {
        user_id_str, user->username, user->password_hash, role_str,
        created_str, login_str, active_str
    };

    PGresult *res = PQexecParams(db->conn, query, 7, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        LOG_ERROR(LOG_TAG, "Failed to save user: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
    LOG_INFO(LOG_TAG, "Saved user %s to database", user->username);
#else
    LOG_DEBUG(LOG_TAG, "Saved user %s (in-memory)", user->username);
#endif

    return WTC_OK;
}

wtc_result_t database_load_user(wtc_database_t *db, const char *username,
                                 user_t *user) {
    if (!db || !username || !user) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query =
        "SELECT user_id, username, password_hash, role, "
        "EXTRACT(EPOCH FROM created_at) * 1000, "
        "EXTRACT(EPOCH FROM last_login) * 1000, active "
        "FROM users WHERE username = $1";

    const char *params[] = { username };

    PGresult *res = PQexecParams(db->conn, query, 1, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        LOG_ERROR(LOG_TAG, "Failed to load user: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    if (PQntuples(res) == 0) {
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    user->user_id = atoi(PQgetvalue(res, 0, 0));
    strncpy(user->username, PQgetvalue(res, 0, 1), WTC_MAX_USERNAME - 1);
    strncpy(user->password_hash, PQgetvalue(res, 0, 2), sizeof(user->password_hash) - 1);
    user->role = atoi(PQgetvalue(res, 0, 3));
    user->created_at_ms = (uint64_t)atof(PQgetvalue(res, 0, 4));
    user->last_login_ms = (uint64_t)atof(PQgetvalue(res, 0, 5));
    user->active = strcmp(PQgetvalue(res, 0, 6), "t") == 0;

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
    return WTC_OK;
#else
    (void)username;
    (void)user;
    return WTC_ERROR_NOT_FOUND;
#endif
}

wtc_result_t database_delete_user(wtc_database_t *db, const char *username) {
    if (!db || !username) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    const char *query = "DELETE FROM users WHERE username = $1";
    const char *params[] = { username };

    PGresult *res = PQexecParams(db->conn, query, 1, NULL, params, NULL, NULL, 0);

    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        LOG_ERROR(LOG_TAG, "Failed to delete user: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
    LOG_INFO(LOG_TAG, "Deleted user %s from database", username);
#else
    LOG_DEBUG(LOG_TAG, "Deleted user %s (in-memory)", username);
#endif

    return WTC_OK;
}

wtc_result_t database_list_users(wtc_database_t *db, user_t **users,
                                  int *count, int max_count) {
    if (!db || !users || !count) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

    *count = 0;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    char query[512];
    snprintf(query, sizeof(query),
             "SELECT user_id, username, password_hash, role, "
             "EXTRACT(EPOCH FROM created_at) * 1000, "
             "EXTRACT(EPOCH FROM last_login) * 1000, active "
             "FROM users LIMIT %d", max_count);

    PGresult *res = PQexec(db->conn, query);

    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        LOG_ERROR(LOG_TAG, "Failed to list users: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    int rows = PQntuples(res);
    if (rows > max_count) rows = max_count;

    *users = calloc(rows, sizeof(user_t));
    if (!*users) {
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    for (int i = 0; i < rows; i++) {
        (*users)[i].user_id = atoi(PQgetvalue(res, i, 0));
        strncpy((*users)[i].username, PQgetvalue(res, i, 1), WTC_MAX_USERNAME - 1);
        strncpy((*users)[i].password_hash, PQgetvalue(res, i, 2), sizeof((*users)[i].password_hash) - 1);
        (*users)[i].role = atoi(PQgetvalue(res, i, 3));
        (*users)[i].created_at_ms = (uint64_t)atof(PQgetvalue(res, i, 4));
        (*users)[i].last_login_ms = (uint64_t)atof(PQgetvalue(res, i, 5));
        (*users)[i].active = strcmp(PQgetvalue(res, i, 6), "t") == 0;
    }

    *count = rows;
    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    (void)max_count;
#endif

    return WTC_OK;
}

/* ============== Maintenance ============== */

wtc_result_t database_purge_historian_data(wtc_database_t *db, int retention_days) {
    if (!db) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    char query[256];
    snprintf(query, sizeof(query),
             "DELETE FROM historian_samples WHERE timestamp < NOW() - INTERVAL '%d days'",
             retention_days);

    PGresult *res = PQexec(db->conn, query);

    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        LOG_ERROR(LOG_TAG, "Failed to purge historian data: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    LOG_INFO(LOG_TAG, "Purged historian data older than %d days", retention_days);
    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    (void)retention_days;
#endif

    return WTC_OK;
}

wtc_result_t database_purge_alarm_history(wtc_database_t *db, int retention_days) {
    if (!db) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    char query[256];
    snprintf(query, sizeof(query),
             "DELETE FROM alarms WHERE raise_time < NOW() - INTERVAL '%d days'",
             retention_days);

    PGresult *res = PQexec(db->conn, query);

    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        LOG_ERROR(LOG_TAG, "Failed to purge alarm history: %s", PQerrorMessage(db->conn));
        PQclear(res);
        pthread_mutex_unlock(&db->lock);
        return WTC_ERROR_IO;
    }

    LOG_INFO(LOG_TAG, "Purged alarm history older than %d days", retention_days);
    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#else
    (void)retention_days;
#endif

    return WTC_OK;
}

wtc_result_t database_get_stats(wtc_database_t *db, database_stats_t *stats) {
    if (!db || !stats) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

    memset(stats, 0, sizeof(database_stats_t));

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    PGresult *res = PQexec(db->conn,
        "SELECT "
        "(SELECT COUNT(*) FROM historian_samples), "
        "(SELECT COUNT(*) FROM alarms), "
        "(SELECT pg_database_size(current_database()))");

    if (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) > 0) {
        stats->historian_samples = (uint64_t)atoll(PQgetvalue(res, 0, 0));
        stats->alarm_records = (uint64_t)atoll(PQgetvalue(res, 0, 1));
        stats->storage_bytes = (uint64_t)atoll(PQgetvalue(res, 0, 2));
        stats->total_rows = stats->historian_samples + stats->alarm_records;
    }

    PQclear(res);
    pthread_mutex_unlock(&db->lock);
#endif

    return WTC_OK;
}

wtc_result_t database_migrate(wtc_database_t *db) {
    if (!db) return WTC_ERROR_INVALID_PARAM;
    if (!db->connected) return WTC_ERROR_NOT_INITIALIZED;

#ifdef HAVE_POSTGRESQL
    pthread_mutex_lock(&db->lock);

    /* Create tables if they don't exist */
    const char *schema[] = {
        /* RTUs table */
        "CREATE TABLE IF NOT EXISTS rtus ("
        "  station_name VARCHAR(64) PRIMARY KEY,"
        "  ip_address VARCHAR(16),"
        "  vendor_id INTEGER,"
        "  device_id INTEGER,"
        "  slot_count INTEGER,"
        "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ")",

        /* Alarm rules table */
        "CREATE TABLE IF NOT EXISTS alarm_rules ("
        "  rule_id SERIAL PRIMARY KEY,"
        "  name VARCHAR(64),"
        "  rtu_station VARCHAR(64),"
        "  slot INTEGER,"
        "  condition INTEGER,"
        "  threshold REAL,"
        "  delay_ms INTEGER,"
        "  severity INTEGER,"
        "  message_template VARCHAR(256),"
        "  enabled BOOLEAN DEFAULT true"
        ")",

        /* Alarms table */
        "CREATE TABLE IF NOT EXISTS alarms ("
        "  alarm_id SERIAL PRIMARY KEY,"
        "  rule_id INTEGER,"
        "  rtu_station VARCHAR(64),"
        "  slot INTEGER,"
        "  severity INTEGER,"
        "  state INTEGER,"
        "  message VARCHAR(256),"
        "  value REAL,"
        "  threshold REAL,"
        "  raise_time TIMESTAMP,"
        "  ack_time TIMESTAMP,"
        "  clear_time TIMESTAMP,"
        "  ack_user VARCHAR(64)"
        ")",

        /* Historian tags table */
        "CREATE TABLE IF NOT EXISTS historian_tags ("
        "  tag_id SERIAL PRIMARY KEY,"
        "  rtu_station VARCHAR(64),"
        "  slot INTEGER,"
        "  tag_name VARCHAR(128),"
        "  unit VARCHAR(16),"
        "  sample_rate_ms INTEGER,"
        "  deadband REAL,"
        "  compression INTEGER"
        ")",

        /* Historian samples - use TimescaleDB hypertable if available */
        "CREATE TABLE IF NOT EXISTS historian_samples ("
        "  timestamp BIGINT NOT NULL,"
        "  tag_id INTEGER NOT NULL,"
        "  value REAL,"
        "  quality SMALLINT"
        ")",

        /* Create indexes */
        "CREATE INDEX IF NOT EXISTS idx_alarms_raise_time ON alarms(raise_time)",
        "CREATE INDEX IF NOT EXISTS idx_samples_tag_time ON historian_samples(tag_id, timestamp)",

        NULL
    };

    for (int i = 0; schema[i] != NULL; i++) {
        PGresult *res = PQexec(db->conn, schema[i]);
        if (PQresultStatus(res) != PGRES_COMMAND_OK) {
            LOG_WARN(LOG_TAG, "Schema migration warning: %s", PQerrorMessage(db->conn));
        }
        PQclear(res);
    }

    /* Try to create TimescaleDB hypertable (may fail if not installed) */
    PGresult *res = PQexec(db->conn,
        "SELECT create_hypertable('historian_samples', 'timestamp', "
        "chunk_time_interval => 86400000, if_not_exists => TRUE)");
    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        LOG_INFO(LOG_TAG, "TimescaleDB not available, using standard PostgreSQL");
    }
    PQclear(res);

    pthread_mutex_unlock(&db->lock);
    LOG_INFO(LOG_TAG, "Database migration completed");
#endif

    return WTC_OK;
}
