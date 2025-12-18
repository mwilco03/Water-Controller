/*
 * Water Treatment Controller - Modbus Register Map
 * Configurable mapping between PROFINET/RTU data and Modbus registers
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_REGISTER_MAP_H
#define WTC_REGISTER_MAP_H

#include "modbus_common.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Forward declarations */
struct rtu_registry;
typedef struct rtu_registry rtu_registry_t;

/* Maximum register mappings */
#define MAX_REGISTER_MAPPINGS   1024
#define MAX_COIL_MAPPINGS       1024

/* Data source type */
typedef enum {
    DATA_SOURCE_PROFINET_SENSOR,    /* PROFINET RTU sensor input */
    DATA_SOURCE_PROFINET_ACTUATOR,  /* PROFINET RTU actuator output */
    DATA_SOURCE_PID_SETPOINT,       /* PID loop setpoint */
    DATA_SOURCE_PID_PV,             /* PID process variable */
    DATA_SOURCE_PID_CV,             /* PID control variable */
    DATA_SOURCE_ALARM_STATE,        /* Alarm state */
    DATA_SOURCE_SYSTEM_STATUS,      /* System status flags */
    DATA_SOURCE_INTERNAL,           /* Internal variable */
    DATA_SOURCE_MODBUS_CLIENT,      /* Read from downstream Modbus device */
} data_source_t;

/* Scaling configuration */
typedef struct {
    bool enabled;
    float raw_min;
    float raw_max;
    float eng_min;
    float eng_max;
    float offset;
} scaling_t;

/* Register mapping entry */
typedef struct {
    uint16_t modbus_addr;           /* Modbus register address */
    modbus_register_type_t reg_type; /* Holding, Input, etc. */
    modbus_data_type_t data_type;   /* UINT16, FLOAT32, etc. */
    uint8_t register_count;         /* Number of registers (for 32-bit, 64-bit) */

    data_source_t source;
    char rtu_station[64];           /* Source RTU station name */
    int slot;                       /* Source slot number */
    int pid_loop_id;                /* For PID data sources */
    int alarm_id;                   /* For alarm data sources */

    /* For Modbus client data sources */
    struct {
        uint8_t slave_addr;
        uint16_t remote_addr;
        modbus_transport_t transport;
    } modbus_source;

    scaling_t scaling;

    bool read_only;
    bool enabled;
    char description[64];
} register_mapping_t;

/* Coil mapping entry */
typedef struct {
    uint16_t modbus_addr;           /* Modbus coil address */
    modbus_register_type_t reg_type; /* Coil or Discrete Input */

    data_source_t source;
    char rtu_station[64];
    int slot;
    int bit_offset;                 /* Bit within the value */

    /* For actuator coils */
    int command_on_value;           /* Value when coil is ON */
    int command_off_value;          /* Value when coil is OFF */

    bool read_only;
    bool enabled;
    char description[64];
} coil_mapping_t;

/* Register map handle */
typedef struct register_map register_map_t;

/* Register map configuration */
typedef struct {
    uint16_t holding_base_addr;     /* Base address for holding registers */
    uint16_t input_base_addr;       /* Base address for input registers */
    uint16_t coil_base_addr;        /* Base address for coils */
    uint16_t discrete_base_addr;    /* Base address for discrete inputs */
} register_map_config_t;

/* Initialize register map */
wtc_result_t register_map_init(register_map_t **map,
                                const register_map_config_t *config);

/* Cleanup register map */
void register_map_cleanup(register_map_t *map);

/* Add register mapping */
wtc_result_t register_map_add_register(register_map_t *map,
                                        const register_mapping_t *mapping);

/* Add coil mapping */
wtc_result_t register_map_add_coil(register_map_t *map,
                                    const coil_mapping_t *mapping);

/* Remove register mapping */
wtc_result_t register_map_remove_register(register_map_t *map, uint16_t addr);

/* Remove coil mapping */
wtc_result_t register_map_remove_coil(register_map_t *map, uint16_t addr);

/* Get register mapping by address */
register_mapping_t *register_map_get_register(register_map_t *map,
                                               modbus_register_type_t type,
                                               uint16_t addr);

/* Get coil mapping by address */
coil_mapping_t *register_map_get_coil(register_map_t *map,
                                       modbus_register_type_t type,
                                       uint16_t addr);

/* Get all mappings for a range */
int register_map_get_register_range(register_map_t *map,
                                     modbus_register_type_t type,
                                     uint16_t start_addr,
                                     uint16_t count,
                                     register_mapping_t **mappings,
                                     int max_mappings);

/* Get all coil mappings for a range */
int register_map_get_coil_range(register_map_t *map,
                                 modbus_register_type_t type,
                                 uint16_t start_addr,
                                 uint16_t count,
                                 coil_mapping_t **mappings,
                                 int max_mappings);

/* Load register map from JSON file */
wtc_result_t register_map_load_json(register_map_t *map, const char *filename);

/* Save register map to JSON file */
wtc_result_t register_map_save_json(register_map_t *map, const char *filename);

/* Auto-generate mappings from PROFINET registry */
wtc_result_t register_map_auto_generate(register_map_t *map,
                                         rtu_registry_t *registry,
                                         uint16_t sensor_base,
                                         uint16_t actuator_base);

/* Get mapping statistics */
typedef struct {
    int total_register_mappings;
    int total_coil_mappings;
    int holding_registers;
    int input_registers;
    int coils;
    int discrete_inputs;
} register_map_stats_t;

wtc_result_t register_map_get_stats(register_map_t *map, register_map_stats_t *stats);

/* Apply scaling to value */
float register_map_scale_value(const scaling_t *scaling, float raw_value);

/* Reverse scaling (eng to raw) */
float register_map_unscale_value(const scaling_t *scaling, float eng_value);

#ifdef __cplusplus
}
#endif

#endif /* WTC_REGISTER_MAP_H */
