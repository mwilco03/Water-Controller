/*
 * Water Treatment Controller - PROFINET Device Configuration
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Defines device profiles for RTU slot/module configurations.
 * The controller uses these profiles to build ExpectedSubmoduleBlockReq
 * that matches what the RTU has plugged.
 *
 * IMPORTANT: This configuration must match the RTU's pnet_plug_module()
 * and pnet_plug_submodule() calls in Water-Treat/profinet_manager.c
 */

#ifndef WTC_DEVICE_CONFIG_H
#define WTC_DEVICE_CONFIG_H

#include "types.h"
#include "gsdml_modules.h"
#include "utils/logger.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Maximum slots in a device profile */
#define DEVICE_CONFIG_MAX_SLOTS 32

/* Device profile - describes what modules an RTU has plugged */
typedef struct {
    const char *name;           /* Profile name (e.g., "water-treat-rtu") */
    const char *description;    /* Human-readable description */

    struct {
        uint16_t slot;
        uint16_t subslot;
        uint32_t module_ident;
        uint32_t submodule_ident;
        uint8_t direction;      /* 0=NO_IO, 1=INPUT, 2=OUTPUT, 3=INPUT_OUTPUT */
        uint16_t input_len;     /* Input data length (bytes) */
        uint16_t output_len;    /* Output data length (bytes) */
    } slots[DEVICE_CONFIG_MAX_SLOTS];

    int slot_count;
} device_profile_t;

/* ============== Pre-defined Device Profiles ============== */

/*
 * MINIMAL_PROFILE - Just DAP, for testing connectivity
 * Use this when you don't know the RTU's module configuration.
 */
static const device_profile_t DEVICE_PROFILE_MINIMAL = {
    .name = "minimal",
    .description = "Minimal profile - DAP only for connectivity testing",
    .slots = {
        { .slot = 0, .subslot = 1,
          .module_ident = GSDML_MOD_DAP,
          .submodule_ident = GSDML_SUBMOD_DAP,
          .direction = 0, .input_len = 0, .output_len = 0 },
    },
    .slot_count = 1,
};

/*
 * RTU_CPU_TEMP_PROFILE - RTU with just CPU temperature sensor
 *
 * This matches the RTU's guaranteed default configuration:
 * - Slot 0: DAP (always present)
 * - Slot 1: CPU Temperature sensor (auto-detected thermal zone)
 *
 * Use this for initial connectivity testing.
 */
static const device_profile_t DEVICE_PROFILE_RTU_CPU_TEMP = {
    .name = "rtu-cpu-temp",
    .description = "RTU with CPU temperature sensor only",
    .slots = {
        /* DAP at slot 0 */
        { .slot = 0, .subslot = 1,
          .module_ident = GSDML_MOD_DAP,
          .submodule_ident = GSDML_SUBMOD_DAP,
          .direction = 0, .input_len = 0, .output_len = 0 },
        /* CPU Temperature at slot 1 */
        { .slot = 1, .subslot = 1,
          .module_ident = GSDML_MOD_TEMPERATURE,
          .submodule_ident = GSDML_SUBMOD_TEMPERATURE,
          .direction = 1, .input_len = GSDML_INPUT_DATA_SIZE, .output_len = 0 },
    },
    .slot_count = 2,
};

/*
 * WATER_TREAT_RTU_PROFILE - Full Water-Treat RTU configuration
 *
 * This MUST match what Water-Treat/profinet_manager.c plugs:
 * - Slot 0: DAP (Device Access Point)
 * - Slots 1-8: Input modules (sensors) - 5 bytes each (4 float + 1 quality)
 * - Slots 9-15: Output modules (actuators) - 4 bytes each
 */
static const device_profile_t DEVICE_PROFILE_WATER_TREAT = {
    .name = "water-treat-rtu",
    .description = "Water Treatment RTU - 8 inputs, 7 outputs",
    .slots = {
        /* DAP at slot 0 */
        { .slot = 0, .subslot = 1,
          .module_ident = GSDML_MOD_DAP,
          .submodule_ident = GSDML_SUBMOD_DAP,
          .direction = 0, .input_len = 0, .output_len = 0 },

        /* Input slots 1-8: Generic AI (0x70/0x71) */
        { .slot = 1, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_AI,
          .submodule_ident = GSDML_SUBMOD_GENERIC_AI,
          .direction = 1, .input_len = GSDML_INPUT_DATA_SIZE, .output_len = 0 },
        { .slot = 2, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_AI,
          .submodule_ident = GSDML_SUBMOD_GENERIC_AI,
          .direction = 1, .input_len = GSDML_INPUT_DATA_SIZE, .output_len = 0 },
        { .slot = 3, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_AI,
          .submodule_ident = GSDML_SUBMOD_GENERIC_AI,
          .direction = 1, .input_len = GSDML_INPUT_DATA_SIZE, .output_len = 0 },
        { .slot = 4, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_AI,
          .submodule_ident = GSDML_SUBMOD_GENERIC_AI,
          .direction = 1, .input_len = GSDML_INPUT_DATA_SIZE, .output_len = 0 },
        { .slot = 5, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_AI,
          .submodule_ident = GSDML_SUBMOD_GENERIC_AI,
          .direction = 1, .input_len = GSDML_INPUT_DATA_SIZE, .output_len = 0 },
        { .slot = 6, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_AI,
          .submodule_ident = GSDML_SUBMOD_GENERIC_AI,
          .direction = 1, .input_len = GSDML_INPUT_DATA_SIZE, .output_len = 0 },
        { .slot = 7, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_AI,
          .submodule_ident = GSDML_SUBMOD_GENERIC_AI,
          .direction = 1, .input_len = GSDML_INPUT_DATA_SIZE, .output_len = 0 },
        { .slot = 8, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_AI,
          .submodule_ident = GSDML_SUBMOD_GENERIC_AI,
          .direction = 1, .input_len = GSDML_INPUT_DATA_SIZE, .output_len = 0 },

        /* Output slots 9-15: Generic DO (0x120/0x121) */
        { .slot = 9, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_DO,
          .submodule_ident = GSDML_SUBMOD_GENERIC_DO,
          .direction = 2, .input_len = 0, .output_len = GSDML_OUTPUT_DATA_SIZE },
        { .slot = 10, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_DO,
          .submodule_ident = GSDML_SUBMOD_GENERIC_DO,
          .direction = 2, .input_len = 0, .output_len = GSDML_OUTPUT_DATA_SIZE },
        { .slot = 11, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_DO,
          .submodule_ident = GSDML_SUBMOD_GENERIC_DO,
          .direction = 2, .input_len = 0, .output_len = GSDML_OUTPUT_DATA_SIZE },
        { .slot = 12, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_DO,
          .submodule_ident = GSDML_SUBMOD_GENERIC_DO,
          .direction = 2, .input_len = 0, .output_len = GSDML_OUTPUT_DATA_SIZE },
        { .slot = 13, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_DO,
          .submodule_ident = GSDML_SUBMOD_GENERIC_DO,
          .direction = 2, .input_len = 0, .output_len = GSDML_OUTPUT_DATA_SIZE },
        { .slot = 14, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_DO,
          .submodule_ident = GSDML_SUBMOD_GENERIC_DO,
          .direction = 2, .input_len = 0, .output_len = GSDML_OUTPUT_DATA_SIZE },
        { .slot = 15, .subslot = 1, .module_ident = GSDML_MOD_GENERIC_DO,
          .submodule_ident = GSDML_SUBMOD_GENERIC_DO,
          .direction = 2, .input_len = 0, .output_len = GSDML_OUTPUT_DATA_SIZE },
    },
    .slot_count = 16,
};

/* ============== Profile Selection ============== */

typedef enum {
    DEVICE_PROFILE_TYPE_MINIMAL,
    DEVICE_PROFILE_TYPE_RTU_CPU_TEMP,
    DEVICE_PROFILE_TYPE_WATER_TREAT,
    DEVICE_PROFILE_TYPE_CUSTOM,
} device_profile_type_t;

/**
 * @brief Get a predefined device profile by type.
 *
 * @param[in] type Profile type to retrieve
 * @return Pointer to device profile (static, do not free)
 */
static inline const device_profile_t *device_config_get_profile(
    device_profile_type_t type)
{
    switch (type) {
    case DEVICE_PROFILE_TYPE_MINIMAL:
        return &DEVICE_PROFILE_MINIMAL;
    case DEVICE_PROFILE_TYPE_RTU_CPU_TEMP:
        return &DEVICE_PROFILE_RTU_CPU_TEMP;
    case DEVICE_PROFILE_TYPE_WATER_TREAT:
        return &DEVICE_PROFILE_WATER_TREAT;
    default:
        return &DEVICE_PROFILE_MINIMAL;
    }
}

/**
 * @brief Log device profile configuration for debugging.
 *
 * @param[in] profile Profile to log
 */
static inline void device_config_log_profile(const device_profile_t *profile)
{
    if (!profile) return;

    LOG_INFO("Device profile: %s - %s", profile->name, profile->description);
    LOG_INFO("  Slot count: %d", profile->slot_count);

    for (int i = 0; i < profile->slot_count; i++) {
        const char *dir = "NO_IO";
        if (profile->slots[i].direction == 1) dir = "INPUT";
        else if (profile->slots[i].direction == 2) dir = "OUTPUT";
        else if (profile->slots[i].direction == 3) dir = "IO";

        LOG_DEBUG("  Slot %d/%d: module=0x%08X submodule=0x%08X %s in=%d out=%d",
                  profile->slots[i].slot, profile->slots[i].subslot,
                  profile->slots[i].module_ident, profile->slots[i].submodule_ident,
                  dir, profile->slots[i].input_len, profile->slots[i].output_len);
    }
}

#ifdef __cplusplus
}
#endif

#endif /* WTC_DEVICE_CONFIG_H */
