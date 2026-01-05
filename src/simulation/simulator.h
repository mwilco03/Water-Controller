/*
 * Water Treatment Controller - Simulation Mode
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Virtual RTU simulator for testing and training without real hardware.
 * Generates realistic water treatment plant sensor data and responds
 * to actuator commands.
 *
 * Usage:
 *   Start controller with --simulation flag:
 *     ./wtc_controller --simulation
 *
 *   Or set environment variable:
 *     WTC_SIMULATION_MODE=1 ./wtc_controller
 */

#ifndef WTC_SIMULATOR_H
#define WTC_SIMULATOR_H

#include "../types.h"
#include "../registry/rtu_registry.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Simulation scenarios - matches Python DemoScenario enum */
typedef enum {
    SIM_SCENARIO_NORMAL = 0,           /* Stable operation, minor variations */
    SIM_SCENARIO_STARTUP,              /* RTUs connecting, systems initializing */
    SIM_SCENARIO_ALARMS,               /* Various alarm conditions triggered */
    SIM_SCENARIO_HIGH_LOAD,            /* System under stress, near limits */
    SIM_SCENARIO_MAINTENANCE,          /* Some RTUs offline for maintenance */
    SIM_SCENARIO_WATER_TREATMENT,      /* Full water treatment plant demo */
    SIM_SCENARIO_COUNT
} sim_scenario_t;

/* Simulated sensor configuration */
typedef struct {
    int slot;
    char tag[32];
    float base_value;
    char unit[16];
    float noise_amplitude;      /* Random noise range */
    float trend_amplitude;      /* Sinusoidal trend amplitude */
    float trend_period_sec;     /* Trend period in seconds */
    float min_value;
    float max_value;
    float alarm_low;            /* Low alarm threshold (0 = disabled) */
    float alarm_high;           /* High alarm threshold (0 = disabled) */
} sim_sensor_config_t;

/* Simulated actuator state */
typedef struct {
    int slot;
    char tag[32];
    actuator_command_t command;
    uint8_t pwm_duty;
    bool forced;
} sim_actuator_state_t;

/* Simulated RTU configuration */
typedef struct {
    char station_name[64];
    char ip_address[16];
    uint16_t vendor_id;
    uint16_t device_id;
    profinet_state_t state;
    int slot_count;
    sim_sensor_config_t *sensors;
    int sensor_count;
    sim_actuator_state_t *actuators;
    int actuator_count;
    float packet_loss_percent;
    uint32_t total_cycles;
} sim_rtu_config_t;

/* Simulator configuration */
typedef struct {
    sim_scenario_t scenario;
    float update_rate_hz;       /* How often to update values (default: 1.0) */
    bool enable_alarms;         /* Generate alarm conditions */
    bool enable_pid_response;   /* Simulate process response to PID output */
    float time_scale;           /* Speed up/slow down simulation (1.0 = real-time) */
    void *user_data;
} simulator_config_t;

/* Simulator handle */
typedef struct simulator simulator_t;

/* Simulator statistics */
typedef struct {
    uint32_t rtu_count;
    uint32_t sensor_count;
    uint32_t actuator_count;
    uint32_t update_count;
    uint64_t start_time_ms;
    uint64_t elapsed_time_ms;
    sim_scenario_t scenario;
    bool running;
} simulator_stats_t;

/*
 * Initialize simulator with configuration.
 *
 * @param simulator Output pointer to simulator handle
 * @param config    Simulator configuration
 * @return WTC_OK on success, error code on failure
 */
wtc_result_t simulator_init(simulator_t **simulator, const simulator_config_t *config);

/*
 * Cleanup and free simulator resources.
 *
 * @param simulator Simulator handle
 */
void simulator_cleanup(simulator_t *simulator);

/*
 * Start simulation - begins generating data.
 *
 * @param simulator Simulator handle
 * @return WTC_OK on success
 */
wtc_result_t simulator_start(simulator_t *simulator);

/*
 * Stop simulation.
 *
 * @param simulator Simulator handle
 * @return WTC_OK on success
 */
wtc_result_t simulator_stop(simulator_t *simulator);

/*
 * Process simulation update - call from main loop.
 * Updates all sensor values, checks alarm conditions,
 * and responds to actuator commands.
 *
 * @param simulator Simulator handle
 * @return WTC_OK on success
 */
wtc_result_t simulator_process(simulator_t *simulator);

/*
 * Connect simulator to RTU registry.
 * Simulator will populate registry with virtual RTUs.
 *
 * @param simulator Simulator handle
 * @param registry  RTU registry to populate
 * @return WTC_OK on success
 */
wtc_result_t simulator_set_registry(simulator_t *simulator, rtu_registry_t *registry);

/*
 * Get current sensor value for a simulated RTU.
 *
 * @param simulator     Simulator handle
 * @param station_name  RTU station name
 * @param slot          Sensor slot number
 * @param value         Output sensor value
 * @param quality       Output data quality
 * @return WTC_OK on success, WTC_ERR_NOT_FOUND if RTU/slot not found
 */
wtc_result_t simulator_get_sensor(simulator_t *simulator,
                                   const char *station_name,
                                   int slot,
                                   float *value,
                                   data_quality_t *quality);

/*
 * Command an actuator on a simulated RTU.
 *
 * @param simulator     Simulator handle
 * @param station_name  RTU station name
 * @param slot          Actuator slot number
 * @param command       Actuator command (OFF, ON, PWM)
 * @param pwm_duty      PWM duty cycle (0-255)
 * @return WTC_OK on success
 */
wtc_result_t simulator_command_actuator(simulator_t *simulator,
                                         const char *station_name,
                                         int slot,
                                         actuator_command_t command,
                                         uint8_t pwm_duty);

/*
 * Get simulator statistics.
 *
 * @param simulator Simulator handle
 * @param stats     Output statistics structure
 * @return WTC_OK on success
 */
wtc_result_t simulator_get_stats(simulator_t *simulator, simulator_stats_t *stats);

/*
 * Get list of simulated RTUs.
 *
 * @param simulator     Simulator handle
 * @param rtus          Output array of RTU configurations
 * @param count         Output number of RTUs
 * @param max_count     Maximum number of RTUs to return
 * @return WTC_OK on success
 */
wtc_result_t simulator_list_rtus(simulator_t *simulator,
                                  sim_rtu_config_t **rtus,
                                  int *count,
                                  int max_count);

/*
 * Change simulation scenario at runtime.
 *
 * @param simulator Simulator handle
 * @param scenario  New scenario to load
 * @return WTC_OK on success
 */
wtc_result_t simulator_set_scenario(simulator_t *simulator, sim_scenario_t scenario);

/*
 * Inject a fault condition for training.
 *
 * @param simulator     Simulator handle
 * @param station_name  RTU station name
 * @param fault_type    Type of fault (COMM_LOSS, SENSOR_FAIL, etc.)
 * @return WTC_OK on success
 */
wtc_result_t simulator_inject_fault(simulator_t *simulator,
                                     const char *station_name,
                                     int fault_type);

/*
 * Clear injected fault condition.
 *
 * @param simulator     Simulator handle
 * @param station_name  RTU station name
 * @return WTC_OK on success
 */
wtc_result_t simulator_clear_fault(simulator_t *simulator,
                                    const char *station_name);

/* Scenario name lookup */
const char *simulator_scenario_name(sim_scenario_t scenario);

/* Parse scenario from string */
sim_scenario_t simulator_parse_scenario(const char *name);

#ifdef __cplusplus
}
#endif

#endif /* WTC_SIMULATOR_H */
