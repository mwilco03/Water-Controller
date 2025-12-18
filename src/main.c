/*
 * Water Treatment Controller - Main Application
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * PROFINET IO Controller for Water Treatment RTU Network
 */

#include "types.h"
#include "profinet/profinet_controller.h"
#include "registry/rtu_registry.h"
#include "control/control_engine.h"
#include "alarms/alarm_manager.h"
#include "historian/historian.h"
#include "ipc/ipc_server.h"
#include "modbus/modbus_gateway.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <getopt.h>

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
} app_config_t;

static app_config_t g_config = {
    .interface = "eth0",
    .config_file = "",
    .log_file = "",
    .log_level = LOG_LEVEL_INFO,
    .cycle_time_ms = 1000,
    .web_port = 8080,
    .daemon_mode = false,
    .modbus_tcp_enabled = true,
    .modbus_tcp_port = 502,
    .modbus_rtu_enabled = false,
    .modbus_rtu_device = "",
    .modbus_slave_addr = 1,
};

/* Signal handler */
static void signal_handler(int sig) {
    LOG_INFO("Received signal %d, shutting down...", sig);
    g_running = false;
}

/* Print usage */
static void print_usage(const char *program) {
    printf("Water Treatment Controller - PROFINET IO Controller\n");
    printf("Version %s\n\n", WTC_VERSION_STRING);
    printf("Usage: %s [options]\n\n", program);
    printf("Options:\n");
    printf("  -i, --interface <name>   Network interface (default: eth0)\n");
    printf("  -c, --config <file>      Configuration file\n");
    printf("  -l, --log <file>         Log file\n");
    printf("  -v, --verbose            Increase verbosity\n");
    printf("  -q, --quiet              Decrease verbosity\n");
    printf("  -t, --cycle <ms>         Cycle time in milliseconds (default: 1000)\n");
    printf("  -p, --port <port>        Web server port (default: 8080)\n");
    printf("  -d, --daemon             Run as daemon\n");
    printf("  -h, --help               Show this help\n");
}

/* Parse command line arguments */
static void parse_args(int argc, char *argv[]) {
    static struct option long_options[] = {
        {"interface", required_argument, 0, 'i'},
        {"config",    required_argument, 0, 'c'},
        {"log",       required_argument, 0, 'l'},
        {"verbose",   no_argument,       0, 'v'},
        {"quiet",     no_argument,       0, 'q'},
        {"cycle",     required_argument, 0, 't'},
        {"port",      required_argument, 0, 'p'},
        {"daemon",    no_argument,       0, 'd'},
        {"help",      no_argument,       0, 'h'},
        {0, 0, 0, 0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "i:c:l:vqt:p:dh", long_options, NULL)) != -1) {
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
        case 'h':
        default:
            print_usage(argv[0]);
            exit(opt == 'h' ? 0 : 1);
        }
    }
}

/* Device added callback */
static void on_device_added(const rtu_device_t *device, void *ctx) {
    (void)ctx;
    LOG_INFO("Device discovered: %s (%s)", device->station_name, device->ip_address);
}

/* Device state changed callback */
static void on_device_state_changed(const char *station_name,
                                     profinet_state_t old_state,
                                     profinet_state_t new_state,
                                     void *ctx) {
    (void)ctx;
    (void)old_state;
    LOG_INFO("Device %s state changed to %d", station_name, new_state);
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

    /* Initialize PROFINET controller */
    profinet_config_t pn_config = {
        .cycle_time_us = g_config.cycle_time_ms * 1000,
        .send_clock_factor = 32,
        .use_raw_sockets = true,
        .socket_priority = 6,
    };
    strncpy(pn_config.interface_name, g_config.interface,
            sizeof(pn_config.interface_name) - 1);

    res = profinet_controller_init(&g_profinet, &pn_config);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to initialize PROFINET controller");
        return res;
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

    LOG_INFO("All components initialized successfully");
    return WTC_OK;
}

/* Start all components */
static wtc_result_t start_components(void) {
    wtc_result_t res;

    res = profinet_controller_start(g_profinet);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to start PROFINET controller");
        return res;
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

    LOG_INFO("All components started successfully");
    return WTC_OK;
}

/* Stop all components */
static void stop_components(void) {
    LOG_INFO("Stopping components...");

    if (g_modbus) modbus_gateway_stop(g_modbus);
    if (g_ipc) ipc_server_stop(g_ipc);
    if (g_historian) historian_stop(g_historian);
    if (g_alarms) alarm_manager_stop(g_alarms);
    if (g_control) control_engine_stop(g_control);
    if (g_profinet) profinet_controller_stop(g_profinet);
}

/* Cleanup all components */
static void cleanup_components(void) {
    LOG_INFO("Cleaning up components...");

    modbus_gateway_cleanup(g_modbus);
    ipc_server_cleanup(g_ipc);
    historian_cleanup(g_historian);
    alarm_manager_cleanup(g_alarms);
    control_engine_cleanup(g_control);
    profinet_controller_cleanup(g_profinet);
    rtu_registry_cleanup(g_registry);
}

/* Main function */
int main(int argc, char *argv[]) {
    /* Parse command line arguments */
    parse_args(argc, argv);

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

    LOG_INFO("Starting Water Treatment Controller v%s", WTC_VERSION_STRING);
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

        /* Update IPC shared memory and process commands */
        ipc_server_update(g_ipc);
        ipc_server_process_commands(g_ipc);

        /* Process Modbus gateway (poll downstream devices) */
        modbus_gateway_process(g_modbus);

        /* Periodic status (every 10 seconds) */
        static uint64_t last_status_ms = 0;
        uint64_t now_ms = time_get_ms();
        if (now_ms - last_status_ms >= 10000) {
            last_status_ms = now_ms;

            registry_stats_t reg_stats;
            rtu_registry_get_stats(g_registry, &reg_stats);

            alarm_stats_t alarm_stats;
            alarm_manager_get_statistics(g_alarms, &alarm_stats);

            LOG_DEBUG("Status: RTUs=%d/%d, Alarms=%d (unack=%d)",
                     reg_stats.connected_devices, reg_stats.total_devices,
                     alarm_stats.active_alarms, alarm_stats.unack_alarms);
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
