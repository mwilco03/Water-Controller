/*
 * Water Treatment Controller - Interlock Manager
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "control_engine.h"
#include "utils/logger.h"

#include <stdlib.h>
#include <string.h>

/* Create standard water treatment interlocks */

/* Low level pump protection */
wtc_result_t create_low_level_interlock(interlock_t *interlock,
                                         const char *level_rtu, int level_slot,
                                         const char *pump_rtu, int pump_slot,
                                         float low_level_threshold) {
    if (!interlock) return WTC_ERROR_INVALID_PARAM;

    memset(interlock, 0, sizeof(interlock_t));
    strncpy(interlock->name, "Low Level Pump Protect", sizeof(interlock->name) - 1);
    interlock->enabled = true;

    strncpy(interlock->condition_rtu, level_rtu, WTC_MAX_STATION_NAME - 1);
    interlock->condition_slot = level_slot;
    interlock->condition = INTERLOCK_CONDITION_BELOW;
    interlock->threshold = low_level_threshold > 0 ? low_level_threshold : 10.0f;
    interlock->delay_ms = 5000; /* 5 second delay to avoid nuisance trips */

    strncpy(interlock->action_rtu, pump_rtu, WTC_MAX_STATION_NAME - 1);
    interlock->action_slot = pump_slot;
    interlock->action = INTERLOCK_ACTION_FORCE_OFF;

    LOG_DEBUG("Created low level interlock: threshold=%.1f%%", interlock->threshold);
    return WTC_OK;
}

/* High level overflow protection */
wtc_result_t create_high_level_interlock(interlock_t *interlock,
                                          const char *level_rtu, int level_slot,
                                          const char *inlet_rtu, int inlet_slot,
                                          float high_level_threshold) {
    if (!interlock) return WTC_ERROR_INVALID_PARAM;

    memset(interlock, 0, sizeof(interlock_t));
    strncpy(interlock->name, "High Level Overflow Protect", sizeof(interlock->name) - 1);
    interlock->enabled = true;

    strncpy(interlock->condition_rtu, level_rtu, WTC_MAX_STATION_NAME - 1);
    interlock->condition_slot = level_slot;
    interlock->condition = INTERLOCK_CONDITION_ABOVE;
    interlock->threshold = high_level_threshold > 0 ? high_level_threshold : 90.0f;
    interlock->delay_ms = 2000; /* 2 second delay */

    strncpy(interlock->action_rtu, inlet_rtu, WTC_MAX_STATION_NAME - 1);
    interlock->action_slot = inlet_slot;
    interlock->action = INTERLOCK_ACTION_FORCE_OFF;

    LOG_DEBUG("Created high level interlock: threshold=%.1f%%", interlock->threshold);
    return WTC_OK;
}

/* High pressure relief */
wtc_result_t create_high_pressure_interlock(interlock_t *interlock,
                                             const char *pressure_rtu, int pressure_slot,
                                             const char *pump_rtu, int pump_slot,
                                             float high_pressure_threshold) {
    if (!interlock) return WTC_ERROR_INVALID_PARAM;

    memset(interlock, 0, sizeof(interlock_t));
    strncpy(interlock->name, "High Pressure Relief", sizeof(interlock->name) - 1);
    interlock->enabled = true;

    strncpy(interlock->condition_rtu, pressure_rtu, WTC_MAX_STATION_NAME - 1);
    interlock->condition_slot = pressure_slot;
    interlock->condition = INTERLOCK_CONDITION_ABOVE;
    interlock->threshold = high_pressure_threshold > 0 ? high_pressure_threshold : 10.0f;
    interlock->delay_ms = 1000; /* 1 second - fast response for safety */

    strncpy(interlock->action_rtu, pump_rtu, WTC_MAX_STATION_NAME - 1);
    interlock->action_slot = pump_slot;
    interlock->action = INTERLOCK_ACTION_FORCE_OFF;

    LOG_DEBUG("Created high pressure interlock: threshold=%.1f bar", interlock->threshold);
    return WTC_OK;
}

/* Over-temperature shutdown */
wtc_result_t create_overtemp_interlock(interlock_t *interlock,
                                        const char *temp_rtu, int temp_slot,
                                        const char *heater_rtu, int heater_slot,
                                        float max_temperature) {
    if (!interlock) return WTC_ERROR_INVALID_PARAM;

    memset(interlock, 0, sizeof(interlock_t));
    strncpy(interlock->name, "Over-temperature Shutdown", sizeof(interlock->name) - 1);
    interlock->enabled = true;

    strncpy(interlock->condition_rtu, temp_rtu, WTC_MAX_STATION_NAME - 1);
    interlock->condition_slot = temp_slot;
    interlock->condition = INTERLOCK_CONDITION_ABOVE;
    interlock->threshold = max_temperature > 0 ? max_temperature : 50.0f;
    interlock->delay_ms = 3000; /* 3 second delay */

    strncpy(interlock->action_rtu, heater_rtu, WTC_MAX_STATION_NAME - 1);
    interlock->action_slot = heater_slot;
    interlock->action = INTERLOCK_ACTION_FORCE_OFF;

    LOG_DEBUG("Created overtemp interlock: threshold=%.1f C", interlock->threshold);
    return WTC_OK;
}

/* pH out of range (prevents chemical damage) */
wtc_result_t create_ph_interlock(interlock_t *interlock,
                                  const char *ph_rtu, int ph_slot,
                                  const char *dosing_rtu, int dosing_slot,
                                  float low_ph, float high_ph,
                                  bool check_low) {
    if (!interlock) return WTC_ERROR_INVALID_PARAM;

    memset(interlock, 0, sizeof(interlock_t));
    if (check_low) {
        strncpy(interlock->name, "Low pH Interlock", sizeof(interlock->name) - 1);
        interlock->condition = INTERLOCK_CONDITION_BELOW;
        interlock->threshold = low_ph > 0 ? low_ph : 5.5f;
    } else {
        strncpy(interlock->name, "High pH Interlock", sizeof(interlock->name) - 1);
        interlock->condition = INTERLOCK_CONDITION_ABOVE;
        interlock->threshold = high_ph > 0 ? high_ph : 9.0f;
    }
    interlock->enabled = true;

    strncpy(interlock->condition_rtu, ph_rtu, WTC_MAX_STATION_NAME - 1);
    interlock->condition_slot = ph_slot;
    interlock->delay_ms = 10000; /* 10 second delay - pH can fluctuate */

    strncpy(interlock->action_rtu, dosing_rtu, WTC_MAX_STATION_NAME - 1);
    interlock->action_slot = dosing_slot;
    interlock->action = INTERLOCK_ACTION_FORCE_OFF;

    LOG_DEBUG("Created pH interlock: %s threshold=%.1f",
              check_low ? "low" : "high", interlock->threshold);
    return WTC_OK;
}

/* Low flow protection (prevents pump damage) */
wtc_result_t create_low_flow_interlock(interlock_t *interlock,
                                        const char *flow_rtu, int flow_slot,
                                        const char *pump_rtu, int pump_slot,
                                        float min_flow) {
    if (!interlock) return WTC_ERROR_INVALID_PARAM;

    memset(interlock, 0, sizeof(interlock_t));
    strncpy(interlock->name, "Low Flow Pump Protect", sizeof(interlock->name) - 1);
    interlock->enabled = true;

    strncpy(interlock->condition_rtu, flow_rtu, WTC_MAX_STATION_NAME - 1);
    interlock->condition_slot = flow_slot;
    interlock->condition = INTERLOCK_CONDITION_BELOW;
    interlock->threshold = min_flow > 0 ? min_flow : 10.0f;
    interlock->delay_ms = 30000; /* 30 second delay - allow startup */

    strncpy(interlock->action_rtu, pump_rtu, WTC_MAX_STATION_NAME - 1);
    interlock->action_slot = pump_slot;
    interlock->action = INTERLOCK_ACTION_FORCE_OFF;

    LOG_DEBUG("Created low flow interlock: threshold=%.1f L/min", interlock->threshold);
    return WTC_OK;
}

/* Create standard interlock set for water treatment */
wtc_result_t create_water_treatment_interlocks(control_engine_t *engine,
                                                const char *rtu_name) {
    if (!engine || !rtu_name) return WTC_ERROR_INVALID_PARAM;

    interlock_t interlock;
    int id;

    /* Low level pump protection */
    create_low_level_interlock(&interlock, rtu_name, 7, rtu_name, 9, 10.0f);
    control_engine_add_interlock(engine, &interlock, &id);

    /* High level overflow protection */
    create_high_level_interlock(&interlock, rtu_name, 7, rtu_name, 10, 90.0f);
    control_engine_add_interlock(engine, &interlock, &id);

    /* High pressure relief */
    create_high_pressure_interlock(&interlock, rtu_name, 8, rtu_name, 9, 10.0f);
    control_engine_add_interlock(engine, &interlock, &id);

    /* Over-temperature shutdown */
    create_overtemp_interlock(&interlock, rtu_name, 2, rtu_name, 14, 50.0f);
    control_engine_add_interlock(engine, &interlock, &id);

    /* Low pH interlock */
    create_ph_interlock(&interlock, rtu_name, 1, rtu_name, 12, 5.5f, 0, true);
    control_engine_add_interlock(engine, &interlock, &id);

    /* High pH interlock */
    create_ph_interlock(&interlock, rtu_name, 1, rtu_name, 12, 0, 9.0f, false);
    control_engine_add_interlock(engine, &interlock, &id);

    LOG_INFO("Created standard water treatment interlocks for %s", rtu_name);
    return WTC_OK;
}

/* Interlock priority ordering */
typedef enum {
    INTERLOCK_PRIORITY_SAFETY = 0,     /* Highest - personnel safety */
    INTERLOCK_PRIORITY_EQUIPMENT = 1,  /* Equipment protection */
    INTERLOCK_PRIORITY_PROCESS = 2,    /* Process protection */
    INTERLOCK_PRIORITY_QUALITY = 3,    /* Product quality */
} interlock_priority_t;

/* Get interlock priority based on type */
interlock_priority_t get_interlock_priority(const interlock_t *interlock) {
    if (!interlock) return INTERLOCK_PRIORITY_PROCESS;

    /* Classify based on name/type */
    if (strstr(interlock->name, "Pressure") ||
        strstr(interlock->name, "Emergency")) {
        return INTERLOCK_PRIORITY_SAFETY;
    }
    if (strstr(interlock->name, "Pump") ||
        strstr(interlock->name, "Motor") ||
        strstr(interlock->name, "temperature")) {
        return INTERLOCK_PRIORITY_EQUIPMENT;
    }
    if (strstr(interlock->name, "Level") ||
        strstr(interlock->name, "Flow")) {
        return INTERLOCK_PRIORITY_PROCESS;
    }
    if (strstr(interlock->name, "pH") ||
        strstr(interlock->name, "Chlorine") ||
        strstr(interlock->name, "Turbidity")) {
        return INTERLOCK_PRIORITY_QUALITY;
    }

    return INTERLOCK_PRIORITY_PROCESS;
}

/* Check if interlock can be bypassed */
bool interlock_can_bypass(const interlock_t *interlock) {
    if (!interlock) return false;

    interlock_priority_t priority = get_interlock_priority(interlock);

    /* Safety interlocks cannot be bypassed */
    return priority != INTERLOCK_PRIORITY_SAFETY;
}

/* Format interlock status for display */
void format_interlock_status(const interlock_t *interlock, char *buffer, size_t size) {
    if (!interlock || !buffer || size < 64) return;

    const char *status = interlock->tripped ? "TRIPPED" :
                        (interlock->enabled ? "ENABLED" : "DISABLED");

    const char *condition_str = "";
    switch (interlock->condition) {
    case INTERLOCK_CONDITION_ABOVE: condition_str = ">"; break;
    case INTERLOCK_CONDITION_BELOW: condition_str = "<"; break;
    case INTERLOCK_CONDITION_EQUAL: condition_str = "="; break;
    case INTERLOCK_CONDITION_NOT_EQUAL: condition_str = "!="; break;
    }

    snprintf(buffer, size, "%s [%s]: %s slot %d %s %.2f -> %s slot %d",
             interlock->name,
             status,
             interlock->condition_rtu,
             interlock->condition_slot,
             condition_str,
             interlock->threshold,
             interlock->action_rtu,
             interlock->action_slot);
}
