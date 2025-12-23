/**
 * @file alarm_definitions.h
 * @brief Shared alarm definitions for Water-Controller and Water-Treat
 *
 * This header provides canonical definitions for alarm-related enumerations
 * that must be consistent between the controller and RTU systems.
 *
 * CRITICAL: Both Water-Controller and Water-Treat MUST use these definitions
 * to ensure alarm data is interpreted correctly across the PROFINET interface.
 *
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef SHARED_ALARM_DEFINITIONS_H
#define SHARED_ALARM_DEFINITIONS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Alarm severity levels (ISA-18.2 compatible)
 *
 * Values are zero-based for consistency with standard C enum conventions.
 * Both systems must use these exact values for correct alarm prioritization.
 *
 * @note CRITICAL is used instead of EMERGENCY for ISA-18.2 alignment
 */
typedef enum {
    ALARM_SEVERITY_LOW = 0,       /**< Low priority - informational */
    ALARM_SEVERITY_MEDIUM = 1,    /**< Medium priority - requires attention */
    ALARM_SEVERITY_HIGH = 2,      /**< High priority - requires prompt action */
    ALARM_SEVERITY_CRITICAL = 3,  /**< Critical - requires immediate action */
} alarm_severity_t;

/**
 * @brief Alarm condition types for threshold-based alarms
 *
 * Defines how sensor values are evaluated against alarm setpoints.
 */
typedef enum {
    ALARM_CONDITION_ABOVE = 0,        /**< Value > high threshold */
    ALARM_CONDITION_BELOW = 1,        /**< Value < low threshold */
    ALARM_CONDITION_OUT_OF_RANGE = 2, /**< Value outside (low, high) range */
    ALARM_CONDITION_RATE_OF_CHANGE = 3, /**< Rate of change exceeds limit */
    ALARM_CONDITION_DEVIATION = 4,    /**< Deviation from setpoint exceeds limit */
    ALARM_CONDITION_BAD_QUALITY = 5,  /**< Data quality is BAD or NOT_CONNECTED */
} alarm_condition_t;

/**
 * @brief Alarm-triggered interlock actions
 *
 * Defines what action to take on associated actuators when an alarm activates.
 */
typedef enum {
    INTERLOCK_ACTION_NONE = 0,    /**< Alarm only, no actuator action */
    INTERLOCK_ACTION_OFF = 1,     /**< Force actuator OFF */
    INTERLOCK_ACTION_ON = 2,      /**< Force actuator ON */
    INTERLOCK_ACTION_PWM = 3,     /**< Set actuator to specific PWM duty */
} interlock_action_t;

/**
 * @brief Alarm states (ISA-18.2 state machine)
 */
typedef enum {
    ALARM_STATE_CLEARED = 0,       /**< Condition resolved */
    ALARM_STATE_ACTIVE = 1,        /**< Condition active, unacknowledged */
    ALARM_STATE_ACKNOWLEDGED = 2,  /**< Condition active, acknowledged */
    ALARM_STATE_CLEARED_UNACK = 3, /**< Condition cleared but not acknowledged */
} alarm_state_t;

/* ============================================================================
 * Legacy Compatibility Macros
 * ============================================================================
 * These macros provide backward compatibility for code using old enum values.
 * They should be removed once all code is migrated to the new definitions.
 */

/* Water-Controller legacy severity values (1-4 based) */
#define LEGACY_ALARM_SEVERITY_LOW       1
#define LEGACY_ALARM_SEVERITY_MEDIUM    2
#define LEGACY_ALARM_SEVERITY_HIGH      3
#define LEGACY_ALARM_SEVERITY_EMERGENCY 4

/* Water-Controller legacy condition names */
#define ALARM_CONDITION_HIGH      ALARM_CONDITION_ABOVE
#define ALARM_CONDITION_LOW       ALARM_CONDITION_BELOW
#define ALARM_CONDITION_HIGH_HIGH ALARM_CONDITION_ABOVE  /* Use ABOVE with HH threshold */
#define ALARM_CONDITION_LOW_LOW   ALARM_CONDITION_BELOW  /* Use BELOW with LL threshold */

/* Water-Controller legacy interlock names */
#define INTERLOCK_ACTION_ALARM_ONLY INTERLOCK_ACTION_NONE
#define INTERLOCK_ACTION_FORCE_OFF  INTERLOCK_ACTION_OFF
#define INTERLOCK_ACTION_FORCE_ON   INTERLOCK_ACTION_ON
#define INTERLOCK_ACTION_SET_VALUE  INTERLOCK_ACTION_PWM

/**
 * @brief Convert legacy (1-4) severity to canonical (0-3) severity
 *
 * @param legacy Legacy severity value (1=LOW, 2=MEDIUM, 3=HIGH, 4=EMERGENCY)
 * @return Canonical severity value (0=LOW, 1=MEDIUM, 2=HIGH, 3=CRITICAL)
 */
static inline alarm_severity_t alarm_severity_from_legacy(int legacy) {
    if (legacy <= 0) return ALARM_SEVERITY_LOW;
    if (legacy >= 4) return ALARM_SEVERITY_CRITICAL;
    return (alarm_severity_t)(legacy - 1);
}

/**
 * @brief Convert canonical (0-3) severity to legacy (1-4) severity
 *
 * @param severity Canonical severity value
 * @return Legacy severity value for backward compatibility
 */
static inline int alarm_severity_to_legacy(alarm_severity_t severity) {
    return (int)severity + 1;
}

/**
 * @brief Get string representation of alarm severity
 */
static inline const char* alarm_severity_to_string(alarm_severity_t severity) {
    switch (severity) {
        case ALARM_SEVERITY_LOW:      return "Low";
        case ALARM_SEVERITY_MEDIUM:   return "Medium";
        case ALARM_SEVERITY_HIGH:     return "High";
        case ALARM_SEVERITY_CRITICAL: return "Critical";
        default:                      return "Unknown";
    }
}

/**
 * @brief Get string representation of alarm condition
 */
static inline const char* alarm_condition_to_string(alarm_condition_t condition) {
    switch (condition) {
        case ALARM_CONDITION_ABOVE:          return "Above Threshold";
        case ALARM_CONDITION_BELOW:          return "Below Threshold";
        case ALARM_CONDITION_OUT_OF_RANGE:   return "Out of Range";
        case ALARM_CONDITION_RATE_OF_CHANGE: return "Rate of Change";
        case ALARM_CONDITION_DEVIATION:      return "Deviation";
        case ALARM_CONDITION_BAD_QUALITY:    return "Bad Quality";
        default:                             return "Unknown";
    }
}

/**
 * @brief Get string representation of interlock action
 */
static inline const char* interlock_action_to_string(interlock_action_t action) {
    switch (action) {
        case INTERLOCK_ACTION_NONE: return "Alarm Only";
        case INTERLOCK_ACTION_OFF:  return "Force Off";
        case INTERLOCK_ACTION_ON:   return "Force On";
        case INTERLOCK_ACTION_PWM:  return "Set PWM";
        default:                    return "Unknown";
    }
}

#ifdef __cplusplus
}
#endif

#endif /* SHARED_ALARM_DEFINITIONS_H */
