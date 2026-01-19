/*
 * Water Treatment Controller - Simulation Mode Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "simulator.h"
#include "../utils/logger.h"
#include "../utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <pthread.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* Maximum simulated RTUs */
#define SIM_MAX_RTUS 16
#define SIM_MAX_SENSORS_PER_RTU 32
#define SIM_MAX_ACTUATORS_PER_RTU 16

/* Internal RTU state */
typedef struct {
    sim_rtu_config_t config;
    sim_sensor_config_t sensors[SIM_MAX_SENSORS_PER_RTU];
    sim_actuator_state_t actuators[SIM_MAX_ACTUATORS_PER_RTU];
    float sensor_values[SIM_MAX_SENSORS_PER_RTU];
    data_quality_t sensor_quality[SIM_MAX_SENSORS_PER_RTU];
    bool fault_injected;
    int fault_type;
} sim_rtu_t;

/* Simulator internal state */
struct simulator {
    simulator_config_t config;
    sim_rtu_t rtus[SIM_MAX_RTUS];
    int rtu_count;
    rtu_registry_t *registry;
    bool running;
    uint64_t start_time_ms;
    uint32_t update_count;
    pthread_mutex_t lock;
};

/* Scenario names for lookup */
static const char *scenario_names[] = {
    [SIM_SCENARIO_NORMAL] = "normal",
    [SIM_SCENARIO_STARTUP] = "startup",
    [SIM_SCENARIO_ALARMS] = "alarms",
    [SIM_SCENARIO_HIGH_LOAD] = "high_load",
    [SIM_SCENARIO_MAINTENANCE] = "maintenance",
    [SIM_SCENARIO_WATER_TREATMENT] = "water_treatment_plant",
};

const char *simulator_scenario_name(sim_scenario_t scenario) {
    if (scenario >= 0 && scenario < SIM_SCENARIO_COUNT) {
        return scenario_names[scenario];
    }
    return "unknown";
}

sim_scenario_t simulator_parse_scenario(const char *name) {
    if (!name) return SIM_SCENARIO_NORMAL;

    for (int i = 0; i < SIM_SCENARIO_COUNT; i++) {
        if (strcmp(name, scenario_names[i]) == 0) {
            return (sim_scenario_t)i;
        }
    }

    /* Handle short aliases */
    if (strcmp(name, "wtp") == 0) return SIM_SCENARIO_WATER_TREATMENT;
    if (strcmp(name, "alarm") == 0) return SIM_SCENARIO_ALARMS;

    return SIM_SCENARIO_NORMAL;
}

/* Generate random noise in range [-amplitude, +amplitude] */
static float random_noise(float amplitude) {
    return ((float)rand() / RAND_MAX * 2.0f - 1.0f) * amplitude;
}

/* Calculate sensor value at time t */
static float calculate_sensor_value(const sim_sensor_config_t *sensor, float t) {
    /* Base value with sinusoidal trend */
    float trend = 0.0f;
    if (sensor->trend_period_sec > 0) {
        trend = sensor->trend_amplitude * sinf(2.0f * M_PI * t / sensor->trend_period_sec);
    }

    /* Add random noise */
    float noise = random_noise(sensor->noise_amplitude);

    /* Combine and clamp */
    float value = sensor->base_value + trend + noise;
    if (value < sensor->min_value) value = sensor->min_value;
    if (value > sensor->max_value) value = sensor->max_value;

    return value;
}

/* Set up water treatment plant scenario */
static void setup_water_treatment_scenario(simulator_t *sim) {
    /* Clear existing */
    sim->rtu_count = 0;

    /* ===== Intake RTU ===== */
    sim_rtu_t *intake = &sim->rtus[sim->rtu_count++];
    memset(intake, 0, sizeof(*intake));
    strncpy(intake->config.station_name, "intake-rtu-01", 63);
    strncpy(intake->config.ip_address, "192.168.1.10", 15);
    intake->config.vendor_id = 0x0493;
    intake->config.device_id = 0x0001;
    intake->config.state = PROFINET_STATE_RUNNING;
    intake->config.slot_count = 16;

    /* Intake sensors */
    intake->config.sensor_count = 4;
    intake->sensors[0] = (sim_sensor_config_t){
        .slot = 1, .tag = "RAW_FLOW", .base_value = 850.0f, .unit = "GPM",
        .noise_amplitude = 15.0f, .trend_amplitude = 50.0f, .trend_period_sec = 600.0f,
        .min_value = 0, .max_value = 1200, .alarm_low = 100, .alarm_high = 1100
    };
    intake->sensors[1] = (sim_sensor_config_t){
        .slot = 2, .tag = "RAW_TURB", .base_value = 12.0f, .unit = "NTU",
        .noise_amplitude = 2.0f, .trend_amplitude = 3.0f, .trend_period_sec = 1800.0f,
        .min_value = 0, .max_value = 100, .alarm_high = 25
    };
    intake->sensors[2] = (sim_sensor_config_t){
        .slot = 3, .tag = "RAW_PH", .base_value = 7.2f, .unit = "pH",
        .noise_amplitude = 0.1f, .trend_amplitude = 0.2f, .trend_period_sec = 900.0f,
        .min_value = 0, .max_value = 14, .alarm_low = 6.5f, .alarm_high = 8.5f
    };
    intake->sensors[3] = (sim_sensor_config_t){
        .slot = 4, .tag = "INTAKE_LEVEL", .base_value = 75.0f, .unit = "%",
        .noise_amplitude = 2.0f, .trend_amplitude = 5.0f, .trend_period_sec = 1200.0f,
        .min_value = 0, .max_value = 100, .alarm_low = 20, .alarm_high = 95
    };

    /* Intake actuators */
    intake->config.actuator_count = 2;
    intake->actuators[0] = (sim_actuator_state_t){.slot = 5, .tag = "INTAKE_VALVE", .command = ACTUATOR_CMD_ON};
    intake->actuators[1] = (sim_actuator_state_t){.slot = 6, .tag = "INTAKE_PUMP", .command = ACTUATOR_CMD_ON};

    /* ===== Clarifier RTU ===== */
    sim_rtu_t *clarifier = &sim->rtus[sim->rtu_count++];
    memset(clarifier, 0, sizeof(*clarifier));
    strncpy(clarifier->config.station_name, "clarifier-rtu-01", 63);
    strncpy(clarifier->config.ip_address, "192.168.1.11", 15);
    clarifier->config.vendor_id = 0x0493;
    clarifier->config.device_id = 0x0001;
    clarifier->config.state = PROFINET_STATE_RUNNING;
    clarifier->config.slot_count = 16;

    clarifier->config.sensor_count = 3;
    clarifier->sensors[0] = (sim_sensor_config_t){
        .slot = 1, .tag = "CLAR_TURB", .base_value = 3.5f, .unit = "NTU",
        .noise_amplitude = 0.5f, .trend_amplitude = 1.0f, .trend_period_sec = 1200.0f,
        .min_value = 0, .max_value = 50, .alarm_high = 8
    };
    clarifier->sensors[1] = (sim_sensor_config_t){
        .slot = 2, .tag = "SLUDGE_LEVEL", .base_value = 35.0f, .unit = "%",
        .noise_amplitude = 2.0f, .trend_amplitude = 8.0f, .trend_period_sec = 3600.0f,
        .min_value = 0, .max_value = 100, .alarm_high = 75
    };
    clarifier->sensors[2] = (sim_sensor_config_t){
        .slot = 3, .tag = "COAG_FLOW", .base_value = 15.0f, .unit = "GPH",
        .noise_amplitude = 1.0f, .trend_amplitude = 2.0f, .trend_period_sec = 600.0f,
        .min_value = 0, .max_value = 50
    };

    clarifier->config.actuator_count = 3;
    clarifier->actuators[0] = (sim_actuator_state_t){.slot = 4, .tag = "COAG_PUMP", .command = ACTUATOR_CMD_ON};
    clarifier->actuators[1] = (sim_actuator_state_t){.slot = 5, .tag = "FLOC_MIXER", .command = ACTUATOR_CMD_ON};
    clarifier->actuators[2] = (sim_actuator_state_t){.slot = 6, .tag = "SLUDGE_VALVE", .command = ACTUATOR_CMD_OFF};

    /* ===== Filter RTU ===== */
    sim_rtu_t *filter = &sim->rtus[sim->rtu_count++];
    memset(filter, 0, sizeof(*filter));
    strncpy(filter->config.station_name, "filter-rtu-01", 63);
    strncpy(filter->config.ip_address, "192.168.1.12", 15);
    filter->config.vendor_id = 0x0493;
    filter->config.device_id = 0x0001;
    filter->config.state = PROFINET_STATE_RUNNING;
    filter->config.slot_count = 16;

    filter->config.sensor_count = 3;
    filter->sensors[0] = (sim_sensor_config_t){
        .slot = 1, .tag = "FILT_TURB", .base_value = 0.3f, .unit = "NTU",
        .noise_amplitude = 0.05f, .trend_amplitude = 0.1f, .trend_period_sec = 1800.0f,
        .min_value = 0, .max_value = 10, .alarm_high = 1.0f
    };
    filter->sensors[1] = (sim_sensor_config_t){
        .slot = 2, .tag = "FILT_DP", .base_value = 8.0f, .unit = "PSI",
        .noise_amplitude = 0.5f, .trend_amplitude = 2.0f, .trend_period_sec = 7200.0f,
        .min_value = 0, .max_value = 25, .alarm_high = 18
    };
    filter->sensors[2] = (sim_sensor_config_t){
        .slot = 3, .tag = "FILT_FLOW", .base_value = 420.0f, .unit = "GPM",
        .noise_amplitude = 10.0f, .trend_amplitude = 30.0f, .trend_period_sec = 900.0f,
        .min_value = 0, .max_value = 600
    };

    filter->config.actuator_count = 2;
    filter->actuators[0] = (sim_actuator_state_t){.slot = 4, .tag = "FILT_INLET", .command = ACTUATOR_CMD_ON};
    filter->actuators[1] = (sim_actuator_state_t){.slot = 5, .tag = "BACKWASH", .command = ACTUATOR_CMD_OFF};

    /* ===== Disinfection RTU ===== */
    sim_rtu_t *disinfect = &sim->rtus[sim->rtu_count++];
    memset(disinfect, 0, sizeof(*disinfect));
    strncpy(disinfect->config.station_name, "disinfect-rtu-01", 63);
    strncpy(disinfect->config.ip_address, "192.168.1.13", 15);
    disinfect->config.vendor_id = 0x0493;
    disinfect->config.device_id = 0x0001;
    disinfect->config.state = PROFINET_STATE_RUNNING;
    disinfect->config.slot_count = 16;

    disinfect->config.sensor_count = 3;
    disinfect->sensors[0] = (sim_sensor_config_t){
        .slot = 1, .tag = "CL2_RESIDUAL", .base_value = 1.8f, .unit = "mg/L",
        .noise_amplitude = 0.1f, .trend_amplitude = 0.3f, .trend_period_sec = 600.0f,
        .min_value = 0, .max_value = 5, .alarm_low = 0.5f, .alarm_high = 4.0f
    };
    disinfect->sensors[1] = (sim_sensor_config_t){
        .slot = 2, .tag = "CL2_FLOW", .base_value = 2.5f, .unit = "GPH",
        .noise_amplitude = 0.2f, .trend_amplitude = 0.5f, .trend_period_sec = 900.0f,
        .min_value = 0, .max_value = 10
    };
    disinfect->sensors[2] = (sim_sensor_config_t){
        .slot = 3, .tag = "CONTACT_TIME", .base_value = 32.0f, .unit = "min",
        .noise_amplitude = 1.0f, .trend_amplitude = 0, .trend_period_sec = 0,
        .min_value = 0, .max_value = 60, .alarm_low = 20
    };

    disinfect->config.actuator_count = 1;
    disinfect->actuators[0] = (sim_actuator_state_t){
        .slot = 4, .tag = "CL2_PUMP", .command = ACTUATOR_CMD_PWM, .pwm_duty = 65
    };

    /* ===== Distribution RTU ===== */
    sim_rtu_t *distrib = &sim->rtus[sim->rtu_count++];
    memset(distrib, 0, sizeof(*distrib));
    strncpy(distrib->config.station_name, "distrib-rtu-01", 63);
    strncpy(distrib->config.ip_address, "192.168.1.14", 15);
    distrib->config.vendor_id = 0x0493;
    distrib->config.device_id = 0x0001;
    distrib->config.state = PROFINET_STATE_RUNNING;
    distrib->config.slot_count = 16;

    distrib->config.sensor_count = 3;
    distrib->sensors[0] = (sim_sensor_config_t){
        .slot = 1, .tag = "CLEARWELL_LVL", .base_value = 82.0f, .unit = "%",
        .noise_amplitude = 1.0f, .trend_amplitude = 8.0f, .trend_period_sec = 3600.0f,
        .min_value = 0, .max_value = 100, .alarm_low = 25, .alarm_high = 95
    };
    distrib->sensors[1] = (sim_sensor_config_t){
        .slot = 2, .tag = "DIST_PRESS", .base_value = 55.0f, .unit = "PSI",
        .noise_amplitude = 2.0f, .trend_amplitude = 5.0f, .trend_period_sec = 1800.0f,
        .min_value = 0, .max_value = 100, .alarm_low = 35, .alarm_high = 80
    };
    distrib->sensors[2] = (sim_sensor_config_t){
        .slot = 3, .tag = "DIST_FLOW", .base_value = 780.0f, .unit = "GPM",
        .noise_amplitude = 20.0f, .trend_amplitude = 100.0f, .trend_period_sec = 7200.0f,
        .min_value = 0, .max_value = 1500
    };

    distrib->config.actuator_count = 3;
    distrib->actuators[0] = (sim_actuator_state_t){.slot = 4, .tag = "HIGH_LIFT_1", .command = ACTUATOR_CMD_ON};
    distrib->actuators[1] = (sim_actuator_state_t){.slot = 5, .tag = "HIGH_LIFT_2", .command = ACTUATOR_CMD_ON};
    distrib->actuators[2] = (sim_actuator_state_t){.slot = 6, .tag = "DIST_VALVE", .command = ACTUATOR_CMD_ON};

    LOG_INFO("[SIM] Loaded water treatment plant scenario with %d RTUs", sim->rtu_count);
}

/* Set up normal scenario with single demo RTU */
static void setup_normal_scenario(simulator_t *sim) {
    sim->rtu_count = 0;

    sim_rtu_t *rtu = &sim->rtus[sim->rtu_count++];
    memset(rtu, 0, sizeof(*rtu));
    strncpy(rtu->config.station_name, "demo-rtu-01", 63);
    strncpy(rtu->config.ip_address, "192.168.1.100", 15);
    rtu->config.vendor_id = 0x0493;
    rtu->config.device_id = 0x0001;
    rtu->config.state = PROFINET_STATE_RUNNING;
    rtu->config.slot_count = 16;

    rtu->config.sensor_count = 4;
    rtu->sensors[0] = (sim_sensor_config_t){
        .slot = 1, .tag = "TEMP_01", .base_value = 25.0f, .unit = "C",
        .noise_amplitude = 0.5f, .trend_amplitude = 2.0f, .trend_period_sec = 300.0f,
        .min_value = 0, .max_value = 100
    };
    rtu->sensors[1] = (sim_sensor_config_t){
        .slot = 2, .tag = "PRESS_01", .base_value = 50.0f, .unit = "PSI",
        .noise_amplitude = 1.0f, .trend_amplitude = 5.0f, .trend_period_sec = 600.0f,
        .min_value = 0, .max_value = 100
    };
    rtu->sensors[2] = (sim_sensor_config_t){
        .slot = 3, .tag = "FLOW_01", .base_value = 100.0f, .unit = "GPM",
        .noise_amplitude = 3.0f, .trend_amplitude = 10.0f, .trend_period_sec = 450.0f,
        .min_value = 0, .max_value = 200
    };
    rtu->sensors[3] = (sim_sensor_config_t){
        .slot = 4, .tag = "LEVEL_01", .base_value = 75.0f, .unit = "%",
        .noise_amplitude = 1.0f, .trend_amplitude = 5.0f, .trend_period_sec = 900.0f,
        .min_value = 0, .max_value = 100
    };

    rtu->config.actuator_count = 2;
    rtu->actuators[0] = (sim_actuator_state_t){.slot = 5, .tag = "VALVE_01", .command = ACTUATOR_CMD_ON};
    rtu->actuators[1] = (sim_actuator_state_t){.slot = 6, .tag = "PUMP_01", .command = ACTUATOR_CMD_ON};

    LOG_INFO("[SIM] Loaded normal scenario with %d RTUs", sim->rtu_count);
}

/* Set up alarm scenario */
static void setup_alarm_scenario(simulator_t *sim) {
    /* Start with normal, then modify */
    setup_normal_scenario(sim);

    /* Modify sensors to trigger alarms */
    if (sim->rtu_count > 0) {
        sim_rtu_t *rtu = &sim->rtus[0];
        /* High temperature alarm */
        rtu->sensors[0].base_value = 38.0f;
        rtu->sensors[0].alarm_high = 35.0f;
        /* Low pressure alarm */
        rtu->sensors[1].base_value = 15.0f;
        rtu->sensors[1].alarm_low = 20.0f;
    }

    LOG_INFO("[SIM] Loaded alarm scenario");
}

/* Set up high load scenario */
static void setup_high_load_scenario(simulator_t *sim) {
    setup_water_treatment_scenario(sim);

    /* Push values near alarm thresholds */
    for (int i = 0; i < sim->rtu_count; i++) {
        sim_rtu_t *rtu = &sim->rtus[i];
        for (int j = 0; j < rtu->config.sensor_count; j++) {
            if (rtu->sensors[j].alarm_high > 0) {
                rtu->sensors[j].base_value = rtu->sensors[j].alarm_high * 0.9f;
            }
        }
    }

    LOG_INFO("[SIM] Loaded high load scenario");
}

/* Set up maintenance scenario */
static void setup_maintenance_scenario(simulator_t *sim) {
    setup_water_treatment_scenario(sim);

    /* Set one RTU offline */
    for (int i = 0; i < sim->rtu_count; i++) {
        if (strcmp(sim->rtus[i].config.station_name, "clarifier-rtu-01") == 0) {
            sim->rtus[i].config.state = PROFINET_STATE_OFFLINE;
            break;
        }
    }

    LOG_INFO("[SIM] Loaded maintenance scenario (clarifier offline)");
}

/* Set up startup scenario */
static void setup_startup_scenario(simulator_t *sim) {
    setup_normal_scenario(sim);

    /* Set RTU to connecting state */
    if (sim->rtu_count > 0) {
        sim->rtus[0].config.state = PROFINET_STATE_CONNECTING;
    }

    LOG_INFO("[SIM] Loaded startup scenario");
}

/* Load scenario configuration */
static void load_scenario(simulator_t *sim, sim_scenario_t scenario) {
    pthread_mutex_lock(&sim->lock);

    switch (scenario) {
    case SIM_SCENARIO_WATER_TREATMENT:
        setup_water_treatment_scenario(sim);
        break;
    case SIM_SCENARIO_ALARMS:
        setup_alarm_scenario(sim);
        break;
    case SIM_SCENARIO_HIGH_LOAD:
        setup_high_load_scenario(sim);
        break;
    case SIM_SCENARIO_MAINTENANCE:
        setup_maintenance_scenario(sim);
        break;
    case SIM_SCENARIO_STARTUP:
        setup_startup_scenario(sim);
        break;
    case SIM_SCENARIO_NORMAL:
    default:
        setup_normal_scenario(sim);
        break;
    }

    sim->config.scenario = scenario;
    pthread_mutex_unlock(&sim->lock);
}

/* Register simulated RTUs with registry */
static void register_rtus_with_registry(simulator_t *sim) {
    if (!sim->registry) return;

    for (int i = 0; i < sim->rtu_count; i++) {
        sim_rtu_t *rtu = &sim->rtus[i];

        /* Build slot configuration */
        slot_config_t slots[SIM_MAX_SENSORS_PER_RTU + SIM_MAX_ACTUATORS_PER_RTU];
        int slot_idx = 0;

        for (int j = 0; j < rtu->config.sensor_count; j++) {
            memset(&slots[slot_idx], 0, sizeof(slot_config_t));
            slots[slot_idx].slot = rtu->sensors[j].slot;
            slots[slot_idx].type = SLOT_TYPE_SENSOR;
            strncpy(slots[slot_idx].name, rtu->sensors[j].tag, WTC_MAX_NAME - 1);
            strncpy(slots[slot_idx].unit, rtu->sensors[j].unit, WTC_MAX_UNIT - 1);
            slots[slot_idx].enabled = true;
            slot_idx++;
        }

        for (int j = 0; j < rtu->config.actuator_count; j++) {
            memset(&slots[slot_idx], 0, sizeof(slot_config_t));
            slots[slot_idx].slot = rtu->actuators[j].slot;
            slots[slot_idx].type = SLOT_TYPE_ACTUATOR;
            strncpy(slots[slot_idx].name, rtu->actuators[j].tag, WTC_MAX_NAME - 1);
            slots[slot_idx].enabled = true;
            slot_idx++;
        }

        /* Add to registry */
        wtc_result_t res = rtu_registry_add_device(
            sim->registry,
            rtu->config.station_name,
            rtu->config.ip_address,
            slots,
            slot_idx
        );

        if (res == WTC_OK) {
            /* Set connection state */
            rtu_registry_set_device_state(sim->registry, rtu->config.station_name, rtu->config.state);
            LOG_INFO("[SIM] Registered RTU: %s (%s)",
                     rtu->config.station_name, rtu->config.ip_address);
        }
    }
}

wtc_result_t simulator_init(simulator_t **simulator, const simulator_config_t *config) {
    if (!simulator) return WTC_ERROR_INVALID_PARAM;

    simulator_t *sim = calloc(1, sizeof(simulator_t));
    if (!sim) return WTC_ERROR_NO_MEMORY;

    /* Copy configuration */
    if (config) {
        sim->config = *config;
    } else {
        /* Defaults */
        sim->config.scenario = SIM_SCENARIO_NORMAL;
        sim->config.update_rate_hz = 1.0f;
        sim->config.enable_alarms = true;
        sim->config.enable_pid_response = true;
        sim->config.time_scale = 1.0f;
    }

    pthread_mutex_init(&sim->lock, NULL);

    /* Load scenario */
    load_scenario(sim, sim->config.scenario);

    *simulator = sim;
    LOG_INFO("[SIM] Simulator initialized with scenario: %s",
             simulator_scenario_name(sim->config.scenario));

    return WTC_OK;
}

void simulator_cleanup(simulator_t *simulator) {
    if (!simulator) return;

    simulator_stop(simulator);
    pthread_mutex_destroy(&simulator->lock);
    free(simulator);

    LOG_INFO("[SIM] Simulator cleaned up");
}

wtc_result_t simulator_start(simulator_t *simulator) {
    if (!simulator) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&simulator->lock);
    simulator->running = true;
    simulator->start_time_ms = time_get_ms();
    simulator->update_count = 0;

    /* Initialize sensor values */
    for (int i = 0; i < simulator->rtu_count; i++) {
        sim_rtu_t *rtu = &simulator->rtus[i];
        for (int j = 0; j < rtu->config.sensor_count; j++) {
            rtu->sensor_values[j] = rtu->sensors[j].base_value;
            rtu->sensor_quality[j] = QUALITY_GOOD;
        }
    }

    /* Register with RTU registry */
    register_rtus_with_registry(simulator);

    pthread_mutex_unlock(&simulator->lock);

    LOG_INFO("[SIM] Simulator started");
    return WTC_OK;
}

wtc_result_t simulator_stop(simulator_t *simulator) {
    if (!simulator) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&simulator->lock);
    simulator->running = false;
    pthread_mutex_unlock(&simulator->lock);

    LOG_INFO("[SIM] Simulator stopped");
    return WTC_OK;
}

wtc_result_t simulator_process(simulator_t *simulator) {
    if (!simulator || !simulator->running) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&simulator->lock);

    uint64_t now_ms = time_get_ms();
    float elapsed_sec = (now_ms - simulator->start_time_ms) / 1000.0f;
    elapsed_sec *= simulator->config.time_scale;

    /* Update all sensor values */
    for (int i = 0; i < simulator->rtu_count; i++) {
        sim_rtu_t *rtu = &simulator->rtus[i];

        /* Skip offline RTUs */
        if (rtu->config.state != PROFINET_STATE_RUNNING) {
            for (int j = 0; j < rtu->config.sensor_count; j++) {
                rtu->sensor_quality[j] = QUALITY_NOT_CONNECTED;
            }
            continue;
        }

        /* Check for injected faults */
        if (rtu->fault_injected) {
            for (int j = 0; j < rtu->config.sensor_count; j++) {
                rtu->sensor_quality[j] = QUALITY_BAD;
            }
            continue;
        }

        /* Update sensor values */
        for (int j = 0; j < rtu->config.sensor_count; j++) {
            rtu->sensor_values[j] = calculate_sensor_value(&rtu->sensors[j], elapsed_sec);
            rtu->sensor_quality[j] = QUALITY_GOOD;
        }

        rtu->config.total_cycles++;

        /* Update registry with new values */
        if (simulator->registry) {
            for (int j = 0; j < rtu->config.sensor_count; j++) {
                rtu_registry_update_sensor(
                    simulator->registry,
                    rtu->config.station_name,
                    rtu->sensors[j].slot,
                    rtu->sensor_values[j],
                    IOPS_GOOD,
                    rtu->sensor_quality[j]
                );
            }
        }
    }

    simulator->update_count++;
    pthread_mutex_unlock(&simulator->lock);

    return WTC_OK;
}

wtc_result_t simulator_set_registry(simulator_t *simulator, rtu_registry_t *registry) {
    if (!simulator) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&simulator->lock);
    simulator->registry = registry;

    /* If already running, register RTUs */
    if (simulator->running) {
        register_rtus_with_registry(simulator);
    }

    pthread_mutex_unlock(&simulator->lock);
    return WTC_OK;
}

wtc_result_t simulator_get_sensor(simulator_t *simulator,
                                   const char *station_name,
                                   int slot,
                                   float *value,
                                   data_quality_t *quality) {
    if (!simulator || !station_name || !value) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&simulator->lock);

    wtc_result_t result = WTC_ERROR_NOT_FOUND;

    for (int i = 0; i < simulator->rtu_count; i++) {
        sim_rtu_t *rtu = &simulator->rtus[i];
        if (strcmp(rtu->config.station_name, station_name) == 0) {
            for (int j = 0; j < rtu->config.sensor_count; j++) {
                if (rtu->sensors[j].slot == slot) {
                    *value = rtu->sensor_values[j];
                    if (quality) *quality = rtu->sensor_quality[j];
                    result = WTC_OK;
                    break;
                }
            }
            break;
        }
    }

    pthread_mutex_unlock(&simulator->lock);
    return result;
}

wtc_result_t simulator_command_actuator(simulator_t *simulator,
                                         const char *station_name,
                                         int slot,
                                         actuator_cmd_t command,
                                         uint8_t pwm_duty) {
    if (!simulator || !station_name) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&simulator->lock);

    wtc_result_t result = WTC_ERROR_NOT_FOUND;

    for (int i = 0; i < simulator->rtu_count; i++) {
        sim_rtu_t *rtu = &simulator->rtus[i];
        if (strcmp(rtu->config.station_name, station_name) == 0) {
            for (int j = 0; j < rtu->config.actuator_count; j++) {
                if (rtu->actuators[j].slot == slot) {
                    rtu->actuators[j].command = command;
                    rtu->actuators[j].pwm_duty = pwm_duty;
                    LOG_INFO("[SIM] Actuator command: %s/%d = %d (duty=%d)",
                             station_name, slot, command, pwm_duty);
                    result = WTC_OK;
                    break;
                }
            }
            break;
        }
    }

    pthread_mutex_unlock(&simulator->lock);
    return result;
}

wtc_result_t simulator_get_stats(simulator_t *simulator, simulator_stats_t *stats) {
    if (!simulator || !stats) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&simulator->lock);

    stats->rtu_count = simulator->rtu_count;
    stats->update_count = simulator->update_count;
    stats->start_time_ms = simulator->start_time_ms;
    stats->elapsed_time_ms = time_get_ms() - simulator->start_time_ms;
    stats->scenario = simulator->config.scenario;
    stats->running = simulator->running;

    /* Count sensors and actuators */
    stats->sensor_count = 0;
    stats->actuator_count = 0;
    for (int i = 0; i < simulator->rtu_count; i++) {
        stats->sensor_count += simulator->rtus[i].config.sensor_count;
        stats->actuator_count += simulator->rtus[i].config.actuator_count;
    }

    pthread_mutex_unlock(&simulator->lock);
    return WTC_OK;
}

wtc_result_t simulator_set_scenario(simulator_t *simulator, sim_scenario_t scenario) {
    if (!simulator) return WTC_ERROR_INVALID_PARAM;

    bool was_running = simulator->running;
    if (was_running) {
        simulator_stop(simulator);
    }

    load_scenario(simulator, scenario);

    if (was_running) {
        simulator_start(simulator);
    }

    return WTC_OK;
}

wtc_result_t simulator_inject_fault(simulator_t *simulator,
                                     const char *station_name,
                                     int fault_type) {
    if (!simulator || !station_name) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&simulator->lock);

    wtc_result_t result = WTC_ERROR_NOT_FOUND;

    for (int i = 0; i < simulator->rtu_count; i++) {
        if (strcmp(simulator->rtus[i].config.station_name, station_name) == 0) {
            simulator->rtus[i].fault_injected = true;
            simulator->rtus[i].fault_type = fault_type;
            LOG_WARN("[SIM] Fault injected on %s (type=%d)", station_name, fault_type);
            result = WTC_OK;
            break;
        }
    }

    pthread_mutex_unlock(&simulator->lock);
    return result;
}

wtc_result_t simulator_clear_fault(simulator_t *simulator,
                                    const char *station_name) {
    if (!simulator || !station_name) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&simulator->lock);

    wtc_result_t result = WTC_ERROR_NOT_FOUND;

    for (int i = 0; i < simulator->rtu_count; i++) {
        if (strcmp(simulator->rtus[i].config.station_name, station_name) == 0) {
            simulator->rtus[i].fault_injected = false;
            simulator->rtus[i].fault_type = 0;
            LOG_INFO("[SIM] Fault cleared on %s", station_name);
            result = WTC_OK;
            break;
        }
    }

    pthread_mutex_unlock(&simulator->lock);
    return result;
}

wtc_result_t simulator_list_rtus(simulator_t *simulator,
                                  sim_rtu_config_t **rtus,
                                  int *count,
                                  int max_count) {
    if (!simulator || !rtus || !count) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&simulator->lock);

    int n = simulator->rtu_count;
    if (n > max_count) n = max_count;

    *rtus = calloc(n, sizeof(sim_rtu_config_t));
    if (!*rtus) {
        pthread_mutex_unlock(&simulator->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    for (int i = 0; i < n; i++) {
        (*rtus)[i] = simulator->rtus[i].config;
    }

    *count = n;
    pthread_mutex_unlock(&simulator->lock);
    return WTC_OK;
}
