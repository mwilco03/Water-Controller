/*
 * Water Treatment Controller - Slot Manager
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "rtu_registry.h"
#include "utils/logger.h"

#include <stdlib.h>
#include <string.h>
#include <math.h>

/* Measurement type info */
typedef struct {
    measurement_type_t type;
    const char *name;
    const char *unit;
    float default_min;
    float default_max;
    float default_alarm_low;
    float default_alarm_high;
} measurement_info_t;

static const measurement_info_t measurement_info[] = {
    { MEASUREMENT_PH, "pH", "pH", 0.0f, 14.0f, 6.5f, 8.5f },
    { MEASUREMENT_TEMPERATURE, "Temperature", "C", -20.0f, 100.0f, 0.0f, 50.0f },
    { MEASUREMENT_TURBIDITY, "Turbidity", "NTU", 0.0f, 1000.0f, 0.0f, 4.0f },
    { MEASUREMENT_TDS, "TDS", "ppm", 0.0f, 5000.0f, 0.0f, 500.0f },
    { MEASUREMENT_DISSOLVED_OXYGEN, "Dissolved Oxygen", "mg/L", 0.0f, 20.0f, 2.0f, 20.0f },
    { MEASUREMENT_FLOW_RATE, "Flow Rate", "L/min", 0.0f, 10000.0f, 0.0f, 0.0f },
    { MEASUREMENT_LEVEL, "Level", "%", 0.0f, 100.0f, 10.0f, 90.0f },
    { MEASUREMENT_PRESSURE, "Pressure", "bar", 0.0f, 100.0f, 0.0f, 0.0f },
    { MEASUREMENT_CONDUCTIVITY, "Conductivity", "uS/cm", 0.0f, 100000.0f, 0.0f, 0.0f },
    { MEASUREMENT_ORP, "ORP", "mV", -2000.0f, 2000.0f, 0.0f, 0.0f },
    { MEASUREMENT_CHLORINE, "Chlorine", "ppm", 0.0f, 10.0f, 0.2f, 4.0f },
    { MEASUREMENT_CUSTOM, "Custom", "", 0.0f, 100.0f, 0.0f, 0.0f },
};

/* Get measurement info */
const measurement_info_t *get_measurement_info(measurement_type_t type) {
    for (size_t i = 0; i < sizeof(measurement_info) / sizeof(measurement_info[0]); i++) {
        if (measurement_info[i].type == type) {
            return &measurement_info[i];
        }
    }
    return &measurement_info[sizeof(measurement_info) / sizeof(measurement_info[0]) - 1];
}

/* Create default slot configuration for sensors */
wtc_result_t create_sensor_slot_config(slot_config_t *slot,
                                        int slot_number,
                                        measurement_type_t type,
                                        const char *name) {
    if (!slot || slot_number < 1 || slot_number > 8) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memset(slot, 0, sizeof(slot_config_t));

    slot->slot = slot_number;
    slot->subslot = 1;
    slot->type = SLOT_TYPE_SENSOR;
    slot->measurement_type = type;
    slot->enabled = true;

    const measurement_info_t *info = get_measurement_info(type);

    if (name && name[0] != '\0') {
        strncpy(slot->name, name, sizeof(slot->name) - 1);
    } else {
        snprintf(slot->name, sizeof(slot->name), "%s %d", info->name, slot_number);
    }

    strncpy(slot->unit, info->unit, sizeof(slot->unit) - 1);
    slot->scale_min = info->default_min;
    slot->scale_max = info->default_max;
    slot->alarm_low = info->default_alarm_low;
    slot->alarm_high = info->default_alarm_high;

    /* Set warning thresholds at 80% of alarm thresholds */
    if (info->default_alarm_low > 0) {
        slot->warning_low = info->default_alarm_low * 1.1f;
    }
    if (info->default_alarm_high > 0) {
        slot->warning_high = info->default_alarm_high * 0.9f;
    }

    return WTC_OK;
}

/* Create default slot configuration for actuators */
wtc_result_t create_actuator_slot_config(slot_config_t *slot,
                                          int slot_number,
                                          actuator_type_t type,
                                          const char *name) {
    if (!slot || slot_number < 9 || slot_number > 16) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memset(slot, 0, sizeof(slot_config_t));

    slot->slot = slot_number;
    slot->subslot = 1;
    slot->type = SLOT_TYPE_ACTUATOR;
    slot->actuator_type = type;
    slot->enabled = true;

    static const char *actuator_names[] = {
        "Relay", "PWM", "Pump", "Valve", "Latching", "Momentary"
    };

    if (name && name[0] != '\0') {
        strncpy(slot->name, name, sizeof(slot->name) - 1);
    } else {
        const char *type_name = (type < sizeof(actuator_names) / sizeof(actuator_names[0]))
                                ? actuator_names[type] : "Actuator";
        snprintf(slot->name, sizeof(slot->name), "%s %d", type_name, slot_number - 8);
    }

    return WTC_OK;
}

/* Create standard Water Treatment RTU configuration */
wtc_result_t create_water_treatment_rtu_config(slot_config_t *slots, int *slot_count) {
    if (!slots || !slot_count) {
        return WTC_ERROR_INVALID_PARAM;
    }

    int idx = 0;

    /* Slot 0: DAP (Device Access Point) - implicit */

    /* Sensor slots 1-8 */
    create_sensor_slot_config(&slots[idx++], 1, MEASUREMENT_PH, "pH Sensor");
    create_sensor_slot_config(&slots[idx++], 2, MEASUREMENT_TEMPERATURE, "Temperature");
    create_sensor_slot_config(&slots[idx++], 3, MEASUREMENT_TURBIDITY, "Turbidity");
    create_sensor_slot_config(&slots[idx++], 4, MEASUREMENT_TDS, "TDS");
    create_sensor_slot_config(&slots[idx++], 5, MEASUREMENT_DISSOLVED_OXYGEN, "DO");
    create_sensor_slot_config(&slots[idx++], 6, MEASUREMENT_FLOW_RATE, "Flow Rate");
    create_sensor_slot_config(&slots[idx++], 7, MEASUREMENT_LEVEL, "Tank Level");
    create_sensor_slot_config(&slots[idx++], 8, MEASUREMENT_PRESSURE, "Pressure");

    /* Actuator slots 9-16 */
    create_actuator_slot_config(&slots[idx++], 9, ACTUATOR_PUMP, "Main Pump");
    create_actuator_slot_config(&slots[idx++], 10, ACTUATOR_VALVE, "Inlet Valve");
    create_actuator_slot_config(&slots[idx++], 11, ACTUATOR_VALVE, "Outlet Valve");
    create_actuator_slot_config(&slots[idx++], 12, ACTUATOR_PWM, "Dosing Pump");
    create_actuator_slot_config(&slots[idx++], 13, ACTUATOR_RELAY, "Aerator");
    create_actuator_slot_config(&slots[idx++], 14, ACTUATOR_RELAY, "Heater");
    create_actuator_slot_config(&slots[idx++], 15, ACTUATOR_RELAY, "Mixer");
    create_actuator_slot_config(&slots[idx++], 16, ACTUATOR_RELAY, "Spare");

    *slot_count = idx;
    return WTC_OK;
}

/* Validate sensor value against slot configuration */
wtc_result_t validate_sensor_value(const slot_config_t *slot,
                                    float value,
                                    alarm_severity_t *severity,
                                    const char **message) {
    if (!slot || slot->type != SLOT_TYPE_SENSOR) {
        return WTC_ERROR_INVALID_PARAM;
    }

    *severity = 0;
    *message = NULL;

    /* Check alarm thresholds */
    if (slot->alarm_low_low > 0 && value <= slot->alarm_low_low) {
        *severity = ALARM_SEVERITY_EMERGENCY;
        *message = "Critical low value";
    } else if (slot->alarm_high_high > 0 && value >= slot->alarm_high_high) {
        *severity = ALARM_SEVERITY_EMERGENCY;
        *message = "Critical high value";
    } else if (slot->alarm_low > 0 && value <= slot->alarm_low) {
        *severity = ALARM_SEVERITY_HIGH;
        *message = "Low alarm";
    } else if (slot->alarm_high > 0 && value >= slot->alarm_high) {
        *severity = ALARM_SEVERITY_HIGH;
        *message = "High alarm";
    } else if (slot->warning_low > 0 && value <= slot->warning_low) {
        *severity = ALARM_SEVERITY_MEDIUM;
        *message = "Low warning";
    } else if (slot->warning_high > 0 && value >= slot->warning_high) {
        *severity = ALARM_SEVERITY_MEDIUM;
        *message = "High warning";
    }

    /* Check range */
    if (value < slot->scale_min || value > slot->scale_max) {
        if (*severity < ALARM_SEVERITY_LOW) {
            *severity = ALARM_SEVERITY_LOW;
            *message = "Value out of range";
        }
    }

    return WTC_OK;
}

/* Scale raw sensor value */
float scale_sensor_value(const slot_config_t *slot, float raw_value) {
    if (!slot) return raw_value;

    /* For water treatment sensors, values are typically already scaled by the RTU */
    /* This function can apply additional linear scaling if needed */

    /* Simple linear scaling: (raw - raw_min) / (raw_max - raw_min) * (scale_max - scale_min) + scale_min */
    /* For now, assume raw value is already in engineering units */
    return raw_value;
}

/* Format sensor value for display */
void format_sensor_value(const slot_config_t *slot, float value, char *buffer, size_t buffer_size) {
    if (!slot || !buffer || buffer_size < 16) return;

    const measurement_info_t *info = get_measurement_info(slot->measurement_type);

    /* Format based on measurement type */
    int decimals = 2;
    switch (slot->measurement_type) {
    case MEASUREMENT_PH:
        decimals = 2;
        break;
    case MEASUREMENT_TEMPERATURE:
    case MEASUREMENT_PRESSURE:
    case MEASUREMENT_DISSOLVED_OXYGEN:
    case MEASUREMENT_CHLORINE:
        decimals = 1;
        break;
    case MEASUREMENT_TURBIDITY:
    case MEASUREMENT_TDS:
    case MEASUREMENT_FLOW_RATE:
    case MEASUREMENT_CONDUCTIVITY:
        decimals = 0;
        break;
    case MEASUREMENT_LEVEL:
        decimals = 1;
        break;
    case MEASUREMENT_ORP:
        decimals = 0;
        break;
    default:
        decimals = 2;
        break;
    }

    snprintf(buffer, buffer_size, "%.*f %s", decimals, value, info->unit);
}

/* Get slot by measurement type */
int find_slot_by_measurement_type(const slot_config_t *slots, int slot_count,
                                   measurement_type_t type) {
    if (!slots) return -1;

    for (int i = 0; i < slot_count; i++) {
        if (slots[i].type == SLOT_TYPE_SENSOR &&
            slots[i].measurement_type == type &&
            slots[i].enabled) {
            return slots[i].slot;
        }
    }

    return -1;
}

/* Get slot by name */
int find_slot_by_name(const slot_config_t *slots, int slot_count, const char *name) {
    if (!slots || !name) return -1;

    for (int i = 0; i < slot_count; i++) {
        if (strcmp(slots[i].name, name) == 0 && slots[i].enabled) {
            return slots[i].slot;
        }
    }

    return -1;
}
