/*
 * Water Treatment Controller - Main Application
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * PROFINET IO Controller for Water Treatment RTU Network
 *
 * ARCHITECTURE:
 * =============
 * This is the CONTROLLER PLANE (Management/Control):
 *   - HMI / Web UI
 *   - Data Collection & Historian
 *   - Alarm Aggregation & Notification
 *   - Configuration Management
 *   - Log Forwarding (Elastic/Graylog)
 *   - Modbus Gateway for external systems
 *   - Failover & Health Monitoring
 *
 * The RTU PLANE (Sensor/Actuator) lives on separate devices:
 *   - Physical sensors (pH, Temp, Flow, etc.)
 *   - Actuators (Pumps, Valves) - COMMANDED via RTU
 *   - Local I/O interfaces
 *   - Offline autonomy capability
 *
 * Communication between planes: PROFINET / Modbus
 */

#include "types.h"
#include "profinet/profinet_controller.h"
#include "registry/rtu_registry.h"
#include "control/control_engine.h"
#include "alarms/alarm_manager.h"
#include "historian/historian.h"
#include "ipc/ipc_server.h"
#include "modbus/modbus_gateway.h"
#include "db/database.h"
#include "coordination/failover.h"
#include "simulation/simulator.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <getopt.h>
#include <dirent.h>

/* Global running flag */
static volatile bool g_running = true;

/* Controller components */
static profinet_controller_t *g_profinet = NULL;
static rtu_registry_t *g_registry = NULL;
static control_engine_t *g_control = NULL;
static alarm_manager_t *g_alarms = NULL;
static historian_t *g_historian = NULL;
static ipc_server_t *g_ipc = NULL;
static modbus_gateway_t *g_modbus = NULL;
static wtc_database_t *g_database = NULL;
static failover_manager_t *g_failover = NULL;
static simulator_t *g_simulator = NULL;

/* Configuration */
typedef struct {
    char interface[32];
    char config_file[256];
    char log_file[256];
    log_level_t log_level;
    uint32_t cycle_time_ms;
    uint16_t web_port;
    bool daemon_mode;
    bool modbus_tcp_enabled;
    uint16_t modbus_tcp_port;
    bool modbus_rtu_enabled;
    char modbus_rtu_device[64];
    uint8_t modbus_slave_addr;
    /* Database configuration */
    char db_host[128];
    int db_port;
    char db_name[64];
    char db_user[64];
    char db_password[128];
    bool db_enabled;
    /* Failover configuration */
    bool failover_enabled;
    uint32_t failover_timeout_ms;
    /* Log forwarding */
    char log_forward_host[128];
    int log_forward_port;
    char log_forward_type[32];  /* "elastic", "graylog", "syslog" */
    bool log_forward_enabled;
    /* Simulation mode */
    bool simulation_mode;
    char simulation_scenario[64];
} app_config_t;

static app_config_t g_config = {
    .interface = "",  /* Empty = auto-detect */
    .config_file = "",
    .log_file = "",
    .log_level = LOG_LEVEL_INFO,
    .cycle_time_ms = 1000,
    .web_port = 8080,
    .daemon_mode = false,
    .modbus_tcp_enabled = true,
    .modbus_tcp_port = 1502,  /* Non-privileged port, matches WTC_MODBUS_TCP_PORT */
    .modbus_rtu_enabled = false,
    .modbus_rtu_device = "",
    .modbus_slave_addr = 1,
    /* Database defaults */
    .db_host = "localhost",
    .db_port = 5432,
    .db_name = "water_treatment",  /* Matches WTC_DB_NAME across codebase */
    .db_user = "wtc",
    .db_password = "",
    .db_enabled = true,
    /* Failover defaults */
    .failover_enabled = true,
    .failover_timeout_ms = 5000,
    /* Log forwarding defaults */
    .log_forward_host = "",
    .log_forward_port = 0,
    .log_forward_type = "",
    .log_forward_enabled = false,
    /* Simulation mode defaults */
    .simulation_mode = false,
    .simulation_scenario = "water_treatment_plant",
};

/* Signal handler */
static void signal_handler(int sig) {
    LOG_INFO("Received signal %d, shutting down...", sig);
    g_running = false;
}

/* Failover callback - notify when RTU goes offline/online */
static void on_failover_event(const char *primary, const char *backup,
                               bool failed_over, void *ctx) {
    (void)ctx;
    char message[256];

    if (failed_over) {
        LOG_WARN("RTU OFFLINE: %s - failing over to %s", primary, backup ? backup : "none");
        snprintf(message, sizeof(message), "RTU offline - failing over to %s",
                 backup ? backup : "none");
        if (g_ipc) {
            ipc_server_post_notification(g_ipc, WTC_EVENT_RTU_OFFLINE, primary, message);
        }
    } else {
        LOG_INFO("RTU ONLINE: %s - restored from failover", primary);
        snprintf(message, sizeof(message), "RTU online - restored from failover");
        if (g_ipc) {
            ipc_server_post_notification(g_ipc, WTC_EVENT_RTU_ONLINE, primary, message);
        }
    }
}

/* Load configuration from database */
static wtc_result_t load_config_from_database(void) {
    if (!g_database || !database_is_connected(g_database)) {
        LOG_WARN("Database not connected, skipping config load");
        return WTC_OK;
    }

    LOG_INFO("Loading configuration from database...");

    /* Load RTUs */
    rtu_device_t *rtus = NULL;
    int rtu_count = 0;
    if (database_list_rtus(g_database, &rtus, &rtu_count, WTC_MAX_RTUS) == WTC_OK) {
        for (int i = 0; i < rtu_count; i++) {
            rtu_registry_add_device(g_registry,
                                    rtus[i].station_name,
                                    rtus[i].ip_address,
                                    rtus[i].slots,
                                    rtus[i].slot_count);
            LOG_INFO("  Loaded RTU: %s", rtus[i].station_name);
        }
        free(rtus);
    }

    /* Load alarm rules */
    alarm_rule_t *rules = NULL;
    int rule_count = 0;
    if (database_load_alarm_rules(g_database, &rules, &rule_count, WTC_MAX_ALARM_RULES) == WTC_OK) {
        for (int i = 0; i < rule_count; i++) {
            int rule_id;
            alarm_manager_create_rule(g_alarms,
                                      rules[i].rtu_station,
                                      rules[i].slot,
                                      rules[i].condition,
                                      rules[i].threshold,
                                      rules[i].severity,
                                      rules[i].delay_ms,
                                      rules[i].message_template,
                                      &rule_id);
        }
        LOG_INFO("  Loaded %d alarm rules", rule_count);
        free(rules);
    }

    /* Load PID loops */
    pid_loop_t *loops = NULL;
    int loop_count = 0;
    if (database_load_pid_loops(g_database, &loops, &loop_count, WTC_MAX_PID_LOOPS) == WTC_OK) {
        for (int i = 0; i < loop_count; i++) {
            int loop_id;
            control_engine_add_pid_loop(g_control, &loops[i], &loop_id);
        }
        LOG_INFO("  Loaded %d PID loops", loop_count);
        free(loops);
    }

    /* Load historian tags */
    historian_tag_t *tags = NULL;
    int tag_count = 0;
    if (database_load_historian_tags(g_database, &tags, &tag_count, WTC_MAX_HISTORIAN_TAGS) == WTC_OK) {
        for (int i = 0; i < tag_count; i++) {
            int tag_id;
            historian_add_tag(g_historian,
                              tags[i].rtu_station,
                              tags[i].slot,
                              tags[i].tag_name,
                              tags[i].sample_rate_ms,
                              tags[i].deadband,
                              tags[i].compression,
                              &tag_id);
        }
        LOG_INFO("  Loaded %d historian tags", tag_count);
        free(tags);
    }

    LOG_INFO("Configuration loaded successfully");
    return WTC_OK;
}

/* Save configuration to database */
static wtc_result_t save_config_to_database(void) {
    if (!g_database || !database_is_connected(g_database)) {
        LOG_WARN("Database not connected, skipping config save");
        return WTC_OK;
    }

    LOG_INFO("Saving configuration to database...");

    /* Save RTUs */
    rtu_device_t *rtus = NULL;
    int rtu_count = 0;
    if (rtu_registry_list_devices(g_registry, &rtus, &rtu_count, WTC_MAX_RTUS) == WTC_OK) {
        for (int i = 0; i < rtu_count; i++) {
            database_save_rtu(g_database, &rtus[i]);
        }
        free(rtus);
    }
    LOG_INFO("  Saved %d RTUs", rtu_count);

    /* Save PID loops */
    if (g_control) {
        pid_loop_t *loops = NULL;
        int loop_count = 0;
        if (control_engine_list_pid_loops(g_control, &loops, &loop_count, WTC_MAX_PID_LOOPS) == WTC_OK) {
            for (int i = 0; i < loop_count; i++) {
                database_save_pid_loop(g_database, &loops[i]);
            }
            free(loops);
        }
        LOG_INFO("  Saved %d PID loops", loop_count);

        /* Save interlocks */
        interlock_t *interlocks = NULL;
        int interlock_count = 0;
        if (control_engine_list_interlocks(g_control, &interlocks, &interlock_count, WTC_MAX_INTERLOCKS) == WTC_OK) {
            for (int i = 0; i < interlock_count; i++) {
                database_save_interlock(g_database, &interlocks[i]);
            }
            free(interlocks);
        }
        LOG_INFO("  Saved %d interlocks", interlock_count);
    }

    /* Save alarm rules */
    if (g_alarms) {
        alarm_rule_t *rules = NULL;
        int rule_count = 0;
        if (alarm_manager_list_rules(g_alarms, &rules, &rule_count, WTC_MAX_ALARM_RULES) == WTC_OK) {
            for (int i = 0; i < rule_count; i++) {
                database_save_alarm_rule(g_database, &rules[i]);
            }
            free(rules);
        }
        LOG_INFO("  Saved %d alarm rules", rule_count);
    }

    LOG_INFO("Configuration saved successfully");
    return WTC_OK;
}

/* Print usage */
static void print_usage(const char *program) {
    printf("Water Treatment Controller - PROFINET IO Controller\n");
    printf("Version %s (build %s)\n\n", WTC_VERSION, WTC_BUILD_COMMIT);
    printf("Usage: %s [options]\n\n", program);
    printf("Options:\n");
    printf("  -i, --interface <name>   Network interface (default: auto-detect)\n");
    printf("  -c, --config <file>      Configuration file\n");
    printf("  -l, --log <file>         Log file\n");
    printf("  -v, --verbose            Increase verbosity\n");
    printf("  -q, --quiet              Decrease verbosity\n");
    printf("  -t, --cycle <ms>         Cycle time in milliseconds (default: 1000)\n");
    printf("  -p, --port <port>        Web server port (default: 8080)\n");
    printf("  -d, --daemon             Run as daemon\n");
    printf("  --db-host <host>         PostgreSQL host (default: localhost)\n");
    printf("  --db-port <port>         PostgreSQL port (default: 5432)\n");
    printf("  --db-name <name>         Database name (default: water_controller)\n");
    printf("  --db-user <user>         Database user (default: wtc)\n");
    printf("  --db-password <pass>     Database password\n");
    printf("  --no-db                  Disable database persistence\n");
    printf("  --log-forward <host:port> Forward logs to Elastic/Graylog\n");
    printf("  --log-forward-type <type> Log forward type: elastic, graylog, syslog\n");
    printf("  -s, --simulation         Run in simulation mode (no real hardware)\n");
    printf("  --scenario <name>        Simulation scenario (default: water_treatment_plant)\n");
    printf("                           Options: normal, startup, alarms, high_load,\n");
    printf("                                    maintenance, water_treatment_plant\n");
    printf("  -h, --help               Show this help\n");
}

/* Parse command line arguments */
static void parse_args(int argc, char *argv[]) {
    enum {
        OPT_DB_HOST = 256,
        OPT_DB_PORT,
        OPT_DB_NAME,
        OPT_DB_USER,
        OPT_DB_PASSWORD,
        OPT_NO_DB,
        OPT_LOG_FORWARD,
        OPT_LOG_FORWARD_TYPE,
        OPT_SCENARIO,
    };

    static struct option long_options[] = {
        {"interface",        required_argument, 0, 'i'},
        {"config",           required_argument, 0, 'c'},
        {"log",              required_argument, 0, 'l'},
        {"verbose",          no_argument,       0, 'v'},
        {"quiet",            no_argument,       0, 'q'},
        {"cycle",            required_argument, 0, 't'},
        {"port",             required_argument, 0, 'p'},
        {"daemon",           no_argument,       0, 'd'},
        {"db-host",          required_argument, 0, OPT_DB_HOST},
        {"db-port",          required_argument, 0, OPT_DB_PORT},
        {"db-name",          required_argument, 0, OPT_DB_NAME},
        {"db-user",          required_argument, 0, OPT_DB_USER},
        {"db-password",      required_argument, 0, OPT_DB_PASSWORD},
        {"no-db",            no_argument,       0, OPT_NO_DB},
        {"log-forward",      required_argument, 0, OPT_LOG_FORWARD},
        {"log-forward-type", required_argument, 0, OPT_LOG_FORWARD_TYPE},
        {"simulation",       no_argument,       0, 's'},
        {"scenario",         required_argument, 0, OPT_SCENARIO},
        {"help",             no_argument,       0, 'h'},
        {0, 0, 0, 0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "i:c:l:vqt:p:dsh", long_options, NULL)) != -1) {
        switch (opt) {
        case 'i':
            strncpy(g_config.interface, optarg, sizeof(g_config.interface) - 1);
            break;
        case 'c':
            strncpy(g_config.config_file, optarg, sizeof(g_config.config_file) - 1);
            break;
        case 'l':
            strncpy(g_config.log_file, optarg, sizeof(g_config.log_file) - 1);
            break;
        case 'v':
            if (g_config.log_level > LOG_LEVEL_TRACE) {
                g_config.log_level--;
            }
            break;
        case 'q':
            if (g_config.log_level < LOG_LEVEL_FATAL) {
                g_config.log_level++;
            }
            break;
        case 't':
            g_config.cycle_time_ms = atoi(optarg);
            break;
        case 'p':
            g_config.web_port = atoi(optarg);
            break;
        case 'd':
            g_config.daemon_mode = true;
            break;
        case OPT_DB_HOST:
            strncpy(g_config.db_host, optarg, sizeof(g_config.db_host) - 1);
            break;
        case OPT_DB_PORT:
            g_config.db_port = atoi(optarg);
            break;
        case OPT_DB_NAME:
            strncpy(g_config.db_name, optarg, sizeof(g_config.db_name) - 1);
            break;
        case OPT_DB_USER:
            strncpy(g_config.db_user, optarg, sizeof(g_config.db_user) - 1);
            break;
        case OPT_DB_PASSWORD:
            strncpy(g_config.db_password, optarg, sizeof(g_config.db_password) - 1);
            break;
        case OPT_NO_DB:
            g_config.db_enabled = false;
            break;
        case OPT_LOG_FORWARD:
            {
                /* Parse host:port */
                char *colon = strchr(optarg, ':');
                if (colon) {
                    *colon = '\0';
                    strncpy(g_config.log_forward_host, optarg, sizeof(g_config.log_forward_host) - 1);
                    g_config.log_forward_port = atoi(colon + 1);
                    g_config.log_forward_enabled = true;
                }
            }
            break;
        case OPT_LOG_FORWARD_TYPE:
            strncpy(g_config.log_forward_type, optarg, sizeof(g_config.log_forward_type) - 1);
            break;
        case 's':
            g_config.simulation_mode = true;
            break;
        case OPT_SCENARIO:
            strncpy(g_config.simulation_scenario, optarg, sizeof(g_config.simulation_scenario) - 1);
            break;
        case 'h':
        default:
            print_usage(argv[0]);
            exit(opt == 'h' ? 0 : 1);
        }
    }

    /* Check environment variables for simulation mode */
    const char *env_sim = getenv("WTC_SIMULATION_MODE");
    if (env_sim && (strcmp(env_sim, "1") == 0 || strcmp(env_sim, "true") == 0)) {
        g_config.simulation_mode = true;
    }
    const char *env_scenario = getenv("WTC_SIMULATION_SCENARIO");
    if (env_scenario && env_scenario[0]) {
        strncpy(g_config.simulation_scenario, env_scenario,
                sizeof(g_config.simulation_scenario) - 1);
    }
}

/* Device added callback — from DCP discovery via PROFINET controller */
static void on_device_added(const rtu_device_t *device, void *ctx) {
    (void)ctx;
    LOG_INFO("Device discovered: %s (%s)", device->station_name, device->ip_address);

    /* Register in RTU registry so the rest of the system (historian,
     * alarms, IPC, Modbus gateway) can see this device.  Slot config
     * is NULL/0 — the discovery pipeline will learn the actual module
     * layout from the device during RPC Connect. */
    if (g_registry) {
        rtu_registry_add_device(g_registry, device->station_name,
                                device->ip_address, NULL, 0);
    }
}

/* Device state changed callback — from RTU registry (4-param signature) */
static void on_device_state_changed(const char *station_name,
                                     profinet_state_t old_state,
                                     profinet_state_t new_state,
                                     void *ctx) {
    (void)ctx;
    (void)old_state;
    LOG_INFO("Device %s state changed to %d", station_name, new_state);
}

/* PROFINET state changed callback — from AR manager (3-param signature) */
static void on_profinet_state_changed(const char *station_name,
                                       profinet_state_t state,
                                       void *ctx) {
    (void)ctx;
    LOG_INFO("Device %s PROFINET state: %d", station_name, state);

    if (g_registry) {
        rtu_registry_set_device_state(g_registry, station_name, state);
    }
}

/* Alarm raised callback */
static void on_alarm_raised(const alarm_t *alarm, void *ctx) {
    (void)ctx;
    LOG_WARN("ALARM [%d]: %s - %s (severity=%d)",
             alarm->alarm_id, alarm->rtu_station, alarm->message, alarm->severity);
}

/* Initialize all components */
static wtc_result_t initialize_components(void) {
    wtc_result_t res;

    /* Initialize database (first, so we can load config) */
    if (g_config.db_enabled) {
        database_config_t db_config = {
            .host = g_config.db_host,
            .port = g_config.db_port,
            .database = g_config.db_name,
            .username = g_config.db_user,
            .password = g_config.db_password,
            .max_connections = 5,
            .connection_timeout_ms = 5000,
            .use_ssl = false,
        };

        res = database_init(&g_database, &db_config);
        if (res != WTC_OK) {
            LOG_WARN("Failed to initialize database - running without persistence");
            g_database = NULL;
        } else {
            res = database_connect(g_database);
            if (res != WTC_OK) {
                LOG_WARN("Failed to connect to database - running without persistence");
                database_cleanup(g_database);
                g_database = NULL;
            } else {
                LOG_INFO("Connected to PostgreSQL database");
                /* Run schema migrations */
                database_migrate(g_database);
            }
        }
    }

    /* Initialize RTU registry */
    registry_config_t reg_config = {
        .database_path = NULL,
        .max_devices = WTC_MAX_RTUS,
        .on_device_added = on_device_added,
        .on_device_state_changed = on_device_state_changed,
        .callback_ctx = NULL,
    };

    res = rtu_registry_init(&g_registry, &reg_config);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to initialize RTU registry");
        return res;
    }

    /* Initialize PROFINET controller or Simulator */
    if (g_config.simulation_mode) {
        /* Simulation mode - use virtual RTU simulator */
        LOG_INFO("*** SIMULATION MODE ENABLED ***");
        LOG_INFO("Scenario: %s", g_config.simulation_scenario);

        simulator_config_t sim_config = {
            .scenario = simulator_parse_scenario(g_config.simulation_scenario),
            .update_rate_hz = 1.0f,
            .enable_alarms = true,
            .enable_pid_response = true,
            .time_scale = 1.0f,
        };

        res = simulator_init(&g_simulator, &sim_config);
        if (res != WTC_OK) {
            LOG_ERROR("Failed to initialize simulator");
            return res;
        }
        simulator_set_registry(g_simulator, g_registry);
    } else {
        /* Normal mode - use real PROFINET controller */
        profinet_config_t pn_config = {
            .cycle_time_us = g_config.cycle_time_ms * 1000,
            .send_clock_factor = 32,
            .use_raw_sockets = true,
            .socket_priority = 6,
            .on_device_added = on_device_added,
            .on_device_state_changed = on_profinet_state_changed,
            .callback_ctx = NULL,
        };
        strncpy(pn_config.interface_name, g_config.interface,
                sizeof(pn_config.interface_name) - 1);

        res = profinet_controller_init(&g_profinet, &pn_config);
        if (res != WTC_OK) {
            LOG_ERROR("Failed to initialize PROFINET controller");
            return res;
        }
    }

    /* Initialize control engine */
    control_engine_config_t ctrl_config = {
        .scan_rate_ms = 100,
    };

    res = control_engine_init(&g_control, &ctrl_config);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to initialize control engine");
        return res;
    }
    control_engine_set_registry(g_control, g_registry);

    /* Initialize alarm manager */
    alarm_manager_config_t alarm_config = {
        .max_active_alarms = 256,
        .max_history_entries = 10000,
        .max_alarms_per_10min = 100,
        .require_ack = true,
        .on_alarm_raised = on_alarm_raised,
    };

    res = alarm_manager_init(&g_alarms, &alarm_config);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to initialize alarm manager");
        return res;
    }
    alarm_manager_set_registry(g_alarms, g_registry);

    /* Initialize historian */
    historian_config_t hist_config = {
        .max_tags = WTC_MAX_HISTORIAN_TAGS,
        .buffer_size = 1000,
        .default_sample_rate_ms = 1000,
        .default_deadband = 0.1f,
        .retention_days = 365,
    };

    res = historian_init(&g_historian, &hist_config);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to initialize historian");
        return res;
    }
    historian_set_registry(g_historian, g_registry);

    /* Initialize IPC server for API communication */
    res = ipc_server_init(&g_ipc);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to initialize IPC server");
        return res;
    }
    ipc_server_set_registry(g_ipc, g_registry);
    ipc_server_set_alarm_manager(g_ipc, g_alarms);
    ipc_server_set_control_engine(g_ipc, g_control);
    ipc_server_set_profinet(g_ipc, g_profinet);

    /* Initialize Modbus gateway */
    modbus_gateway_config_t mb_config = {
        .server = {
            .tcp_enabled = g_config.modbus_tcp_enabled,
            .tcp_port = g_config.modbus_tcp_port,
            .rtu_enabled = g_config.modbus_rtu_enabled,
            .rtu_baud_rate = 9600,
            .rtu_slave_addr = g_config.modbus_slave_addr,
        },
        .auto_generate_map = true,
        .sensor_base_addr = 0,
        .actuator_base_addr = 1000,
    };
    if (g_config.modbus_rtu_device[0]) {
        strncpy(mb_config.server.rtu_device, g_config.modbus_rtu_device, 63);
    }

    res = modbus_gateway_init(&g_modbus, &mb_config);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to initialize Modbus gateway");
        return res;
    }
    modbus_gateway_set_registry(g_modbus, g_registry);
    modbus_gateway_set_control_engine(g_modbus, g_control);
    modbus_gateway_set_alarm_manager(g_modbus, g_alarms);

    /* Initialize failover manager */
    if (g_config.failover_enabled) {
        failover_config_t fo_config = {
            .mode = FAILOVER_MODE_AUTO,
            .heartbeat_interval_ms = 1000,
            .timeout_ms = g_config.failover_timeout_ms,
            .max_retries = 3,
        };

        res = failover_init(&g_failover, &fo_config);
        if (res != WTC_OK) {
            LOG_WARN("Failed to initialize failover manager - running without failover");
            g_failover = NULL;
        } else {
            failover_set_registry(g_failover, g_registry);
            failover_set_callback(g_failover, on_failover_event, NULL);
            LOG_INFO("Failover manager initialized");
        }
    }

    /* Load configuration from database */
    load_config_from_database();

    LOG_INFO("All components initialized successfully");
    return WTC_OK;
}

/* Start all components */
static wtc_result_t start_components(void) {
    wtc_result_t res;

    if (g_config.simulation_mode) {
        res = simulator_start(g_simulator);
        if (res != WTC_OK) {
            LOG_ERROR("Failed to start simulator");
            return res;
        }
    } else {
        res = profinet_controller_start(g_profinet);
        if (res != WTC_OK) {
            LOG_ERROR("Failed to start PROFINET controller");
            return res;
        }
    }

    res = control_engine_start(g_control);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to start control engine");
        return res;
    }

    res = alarm_manager_start(g_alarms);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to start alarm manager");
        return res;
    }

    res = historian_start(g_historian);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to start historian");
        return res;
    }

    res = ipc_server_start(g_ipc);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to start IPC server");
        return res;
    }

    res = modbus_gateway_start(g_modbus);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to start Modbus gateway");
        return res;
    }

    /* Start failover manager */
    if (g_failover) {
        res = failover_start(g_failover);
        if (res != WTC_OK) {
            LOG_WARN("Failed to start failover manager");
        }
    }

    LOG_INFO("All components started successfully");
    return WTC_OK;
}

/* Stop all components */
static void stop_components(void) {
    LOG_INFO("Stopping components...");

    /* Stop failover first */
    if (g_failover) failover_stop(g_failover);

    if (g_modbus) modbus_gateway_stop(g_modbus);
    if (g_ipc) ipc_server_stop(g_ipc);
    if (g_historian) historian_stop(g_historian);
    if (g_alarms) alarm_manager_stop(g_alarms);
    if (g_control) control_engine_stop(g_control);
    if (g_simulator) simulator_stop(g_simulator);
    if (g_profinet) profinet_controller_stop(g_profinet);

    /* Save configuration to database before shutdown */
    save_config_to_database();
}

/* Cleanup all components */
static void cleanup_components(void) {
    LOG_INFO("Cleaning up components...");

    /* Cleanup in reverse order of initialization */
    if (g_failover) failover_cleanup(g_failover);
    modbus_gateway_cleanup(g_modbus);
    ipc_server_cleanup(g_ipc);
    historian_cleanup(g_historian);
    alarm_manager_cleanup(g_alarms);
    control_engine_cleanup(g_control);
    if (g_simulator) simulator_cleanup(g_simulator);
    if (g_profinet) profinet_controller_cleanup(g_profinet);
    rtu_registry_cleanup(g_registry);

    /* Disconnect and cleanup database last */
    if (g_database) {
        database_disconnect(g_database);
        database_cleanup(g_database);
    }
}

/* Auto-detect network interface if not specified */
static bool detect_network_interface(char *interface, size_t size) {
    DIR *net_dir = opendir("/sys/class/net");
    if (!net_dir) {
        return false;
    }

    struct dirent *entry;
    char state_path[512];
    char state[32];
    FILE *fp;
    bool found = false;

    /* First pass: find UP interfaces */
    while ((entry = readdir(net_dir)) != NULL) {
        const char *name = entry->d_name;

        /* Skip . and .. */
        if (name[0] == '.') continue;

        /* Skip loopback and virtual interfaces */
        if (strcmp(name, "lo") == 0) continue;
        if (strncmp(name, "docker", 6) == 0) continue;
        if (strncmp(name, "veth", 4) == 0) continue;
        if (strncmp(name, "br-", 3) == 0) continue;
        if (strncmp(name, "virbr", 5) == 0) continue;

        /* Check if interface is UP */
        snprintf(state_path, sizeof(state_path), "/sys/class/net/%s/operstate", name);
        fp = fopen(state_path, "r");
        if (fp) {
            if (fgets(state, sizeof(state), fp)) {
                /* Remove newline */
                state[strcspn(state, "\n")] = 0;
                if (strcmp(state, "up") == 0) {
                    snprintf(interface, size, "%s", name);
                    found = true;
                    fclose(fp);
                    break;
                }
            }
            fclose(fp);
        }
    }

    /* Second pass if no UP interface found: take first physical interface */
    if (!found) {
        rewinddir(net_dir);
        while ((entry = readdir(net_dir)) != NULL) {
            const char *name = entry->d_name;
            if (name[0] == '.') continue;
            if (strcmp(name, "lo") == 0) continue;
            if (strncmp(name, "docker", 6) == 0) continue;
            if (strncmp(name, "veth", 4) == 0) continue;
            if (strncmp(name, "br-", 3) == 0) continue;
            if (strncmp(name, "virbr", 5) == 0) continue;

            snprintf(interface, size, "%s", name);
            found = true;
            break;
        }
    }

    closedir(net_dir);
    return found;
}

/* Main function */
int main(int argc, char *argv[]) {
    /* Parse command line arguments */
    parse_args(argc, argv);

    /* Auto-detect interface if not specified */
    if (g_config.interface[0] == '\0') {
        if (!detect_network_interface(g_config.interface, sizeof(g_config.interface))) {
            fprintf(stderr, "ERROR: No network interface available and none specified.\n");
            fprintf(stderr, "Use -i/--interface to specify one.\n");
            return 1;
        }
        /* Interface will be logged below after logger init */
    }

    /* Initialize logger */
    logger_config_t log_config = {
        .level = g_config.log_level,
        .output = stderr,
        .log_file = g_config.log_file[0] ? g_config.log_file : NULL,
        .use_colors = true,
        .include_timestamp = true,
        .include_source = true,
    };
    logger_init(&log_config);

    LOG_INFO("Starting Water Treatment Controller v%s (build %s)",
             WTC_VERSION, WTC_BUILD_COMMIT);
    LOG_INFO("Build date: %s", WTC_BUILD_DATE);
    LOG_INFO("Interface: %s, Cycle time: %u ms", g_config.interface, g_config.cycle_time_ms);

    /* Set up signal handlers */
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    /* Initialize components */
    if (initialize_components() != WTC_OK) {
        LOG_FATAL("Failed to initialize components");
        cleanup_components();
        return 1;
    }

    /* Start components */
    if (start_components() != WTC_OK) {
        LOG_FATAL("Failed to start components");
        stop_components();
        cleanup_components();
        return 1;
    }

    LOG_INFO("Controller running. Press Ctrl+C to stop.");

    /* Main loop */
    while (g_running) {
        /* Main loop processing */
        time_sleep_ms(100);

        /* Process simulator if in simulation mode */
        if (g_simulator) {
            simulator_process(g_simulator);
        }

        /* Process PROFINET pending connections (auto-connect after DCP discovery) */
        if (g_profinet) {
            profinet_controller_process(g_profinet);
        }

        /* Update IPC shared memory and process commands */
        ipc_server_update(g_ipc);
        ipc_server_process_commands(g_ipc);

        /* Process Modbus gateway (poll downstream devices) */
        modbus_gateway_process(g_modbus);

        /* Process failover logic (check RTU health, trigger failovers) */
        if (g_failover) {
            failover_process(g_failover);
        }

        /* Periodic status (every 10 seconds) */
        static uint64_t last_status_ms = 0;
        uint64_t now_ms = time_get_ms();
        if (now_ms - last_status_ms >= 10000) {
            last_status_ms = now_ms;

            registry_stats_t reg_stats;
            rtu_registry_get_stats(g_registry, &reg_stats);

            alarm_stats_t alarm_stats;
            alarm_manager_get_statistics(g_alarms, &alarm_stats);

            if (g_simulator) {
                simulator_stats_t sim_stats;
                simulator_get_stats(g_simulator, &sim_stats);
                LOG_DEBUG("Status [SIMULATION]: RTUs=%d, Sensors=%d, Updates=%d",
                         sim_stats.rtu_count, sim_stats.sensor_count, sim_stats.update_count);
            }
            LOG_DEBUG("Status: RTUs=%d/%d, Alarms=%d (unack=%d)",
                     reg_stats.connected_devices, reg_stats.total_devices,
                     alarm_stats.active_alarms, alarm_stats.unack_alarms);

            /* Log failover status if enabled */
            if (g_failover) {
                failover_status_t fo_status;
                if (failover_get_status(g_failover, &fo_status) == WTC_OK) {
                    if (fo_status.failed_count > 0 || fo_status.in_failover_count > 0) {
                        LOG_WARN("Failover: healthy=%d, failed=%d, in_failover=%d",
                                 fo_status.healthy_count, fo_status.failed_count,
                                 fo_status.in_failover_count);
                    }
                }
            }
        }
    }

    /* Shutdown */
    LOG_INFO("Shutting down...");
    stop_components();
    cleanup_components();
    logger_cleanup();

    LOG_INFO("Controller stopped");
    return 0;
}
