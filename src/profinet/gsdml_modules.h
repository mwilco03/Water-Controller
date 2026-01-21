/*
 * Water Treatment Controller - GSDML Module Identifiers
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Module and submodule identifiers as defined in the Water-Treat RTU GSDML.
 * Reference: GSDML-V2.4-WaterTreat-RTU-20241222.xml
 *
 * These identifiers must match between controller and RTU for successful
 * PROFINET connection establishment.
 */

#ifndef WTC_GSDML_MODULES_H
#define WTC_GSDML_MODULES_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ============== Device Access Point (DAP) ============== */

#define GSDML_MOD_DAP               0x00000001
#define GSDML_SUBMOD_DAP            0x00000001
#define GSDML_SUBMOD_INTERFACE      0x00000100
#define GSDML_SUBMOD_PORT           0x00000200

/* ============== Input Modules (Sensors) ============== */

#define GSDML_MOD_PH                0x00000010
#define GSDML_MOD_TDS               0x00000020
#define GSDML_MOD_TURBIDITY         0x00000030
#define GSDML_MOD_TEMPERATURE       0x00000040
#define GSDML_MOD_FLOW              0x00000050
#define GSDML_MOD_LEVEL             0x00000060
#define GSDML_MOD_GENERIC_AI        0x00000070

/* Input submodule pattern: module_ident + 1 */
#define GSDML_SUBMOD_PH             0x00000011
#define GSDML_SUBMOD_TDS            0x00000021
#define GSDML_SUBMOD_TURBIDITY      0x00000031
#define GSDML_SUBMOD_TEMPERATURE    0x00000041
#define GSDML_SUBMOD_FLOW           0x00000051
#define GSDML_SUBMOD_LEVEL          0x00000061
#define GSDML_SUBMOD_GENERIC_AI     0x00000071

/* ============== Output Modules (Actuators) ============== */

#define GSDML_MOD_PUMP              0x00000100
#define GSDML_MOD_VALVE             0x00000110
#define GSDML_MOD_GENERIC_DO        0x00000120

/* Output submodule pattern: module_ident + 1 */
#define GSDML_SUBMOD_PUMP           0x00000101
#define GSDML_SUBMOD_VALVE          0x00000111
#define GSDML_SUBMOD_GENERIC_DO     0x00000121

/* ============== I/O Data Sizes ============== */

/* Input data: 4 bytes IEEE754-BE float + 1 byte quality */
#define GSDML_INPUT_DATA_SIZE       5

/* Output data: 1 byte cmd + 1 byte duty + 2 bytes reserved */
#define GSDML_OUTPUT_DATA_SIZE      4

/* ============== Helper Functions ============== */

/**
 * @brief Get GSDML module identifier for a measurement type.
 *
 * @param[in] type Measurement type from sensor configuration
 * @return Module identifier for PROFINET Connect Request
 */
static inline uint32_t gsdml_get_input_module_ident(measurement_type_t type) {
    switch (type) {
    case MEASUREMENT_PH:
        return GSDML_MOD_PH;
    case MEASUREMENT_TDS:
        return GSDML_MOD_TDS;
    case MEASUREMENT_TURBIDITY:
        return GSDML_MOD_TURBIDITY;
    case MEASUREMENT_TEMPERATURE:
        return GSDML_MOD_TEMPERATURE;
    case MEASUREMENT_FLOW_RATE:
        return GSDML_MOD_FLOW;
    case MEASUREMENT_LEVEL:
        return GSDML_MOD_LEVEL;
    case MEASUREMENT_DISSOLVED_OXYGEN:
    case MEASUREMENT_PRESSURE:
    case MEASUREMENT_CONDUCTIVITY:
    case MEASUREMENT_ORP:
    case MEASUREMENT_CHLORINE:
    case MEASUREMENT_CUSTOM:
    default:
        return GSDML_MOD_GENERIC_AI;
    }
}

/**
 * @brief Get GSDML submodule identifier for a measurement type.
 *
 * @param[in] type Measurement type from sensor configuration
 * @return Submodule identifier for PROFINET Connect Request
 */
static inline uint32_t gsdml_get_input_submodule_ident(measurement_type_t type) {
    /* Submodule = Module + 1 per GSDML convention */
    return gsdml_get_input_module_ident(type) + 1;
}

/**
 * @brief Get GSDML module identifier for an actuator type.
 *
 * @param[in] type Actuator type from control configuration
 * @return Module identifier for PROFINET Connect Request
 */
static inline uint32_t gsdml_get_output_module_ident(actuator_type_t type) {
    switch (type) {
    case ACTUATOR_PUMP:
        return GSDML_MOD_PUMP;
    case ACTUATOR_VALVE:
        return GSDML_MOD_VALVE;
    case ACTUATOR_RELAY:
    case ACTUATOR_PWM:
    case ACTUATOR_LATCHING:
    case ACTUATOR_MOMENTARY:
    default:
        return GSDML_MOD_GENERIC_DO;
    }
}

/**
 * @brief Get GSDML submodule identifier for an actuator type.
 *
 * @param[in] type Actuator type from control configuration
 * @return Submodule identifier for PROFINET Connect Request
 */
static inline uint32_t gsdml_get_output_submodule_ident(actuator_type_t type) {
    /* Submodule = Module + 1 per GSDML convention */
    return gsdml_get_output_module_ident(type) + 1;
}

#ifdef __cplusplus
}
#endif

#endif /* WTC_GSDML_MODULES_H */
