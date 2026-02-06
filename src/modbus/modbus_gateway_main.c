/*
 * Water Treatment Controller - Standalone Modbus Gateway
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * This standalone executable provides Modbus TCP/RTU gateway functionality
 * that bridges to the main water treatment controller via shared memory.
 */

#include "modbus_gateway.h"
#include "modbus_tcp.h"
#include "modbus_rtu.h"
#include "register_map.h"
#include "../utils/logger.h"
#include "../utils/time_utils.h"
#include "../ipc/ipc_server.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <getopt.h>
#include <errno.h>

#ifdef HAVE_SYSTEMD
#include <systemd/sd-daemon.h>
#else
#define sd_notify(unset_environment, state) ((void)0)
#endif

#define LOG_TAG "MODBUS_MAIN"
#define VERSION "1.0.0"

/* Global state */
static volatile sig_atomic_t g_running = 1;
static volatile sig_atomic_t g_reload = 0;
static modbus_gateway_t *g_gateway = NULL;

/* Configuration */
static struct {
    char config_file[256];
    char log_level[16];
    bool tcp_enabled;
    uint16_t tcp_port;
    char tcp_bind[64];
    bool rtu_enabled;
    char rtu_device[64];
    int rtu_baud;
    uint8_t rtu_slave_addr;
    int poll_interval_ms;
} g_config = {
    .config_file = "/etc/water-controller/modbus.conf",
    .log_level = "INFO",
    .tcp_enabled = true,
    .tcp_port = 502,
    .tcp_bind = "0.0.0.0",
    .rtu_enabled = false,
    .rtu_device = "/dev/ttyUSB0",
    .rtu_baud = 9600,
    .rtu_slave_addr = 1,
    .poll_interval_ms = 100,
};

/* Signal handlers */
static void signal_handler(int sig) {
    switch (sig) {
        case SIGTERM:
        case SIGINT:
            g_running = 0;
            break;
        case SIGHUP:
            g_reload = 1;
            break;
    }
}

static void setup_signals(void) {
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = signal_handler;
    sigemptyset(&sa.sa_mask);

    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGHUP, &sa, NULL);

    /* Ignore SIGPIPE for network operations */
    signal(SIGPIPE, SIG_IGN);
}

/* Parse configuration file */
static int parse_config_file(const char *filename) {
    FILE *fp = fopen(filename, "r");
    if (!fp) {
        if (errno == ENOENT) {
            LOG_WARN("Config file %s not found, using defaults", filename);
            return 0;
        }
        LOG_ERROR("Failed to open config file %s: %s", filename, strerror(errno));
        return -1;
    }

    char line[256];
    char section[64] = "";

    while (fgets(line, sizeof(line), fp)) {
        /* Skip comments and empty lines */
        char *p = line;
        while (*p == ' ' || *p == '\t') p++;
        if (*p == '#' || *p == ';' || *p == '\n' || *p == '\0') continue;

        /* Check for section header */
        if (*p == '[') {
            char *end = strchr(p, ']');
            if (end) {
                *end = '\0';
                strncpy(section, p + 1, sizeof(section) - 1);
            }
            continue;
        }

        /* Parse key=value */
        char *eq = strchr(p, '=');
        if (!eq) continue;

        *eq = '\0';
        char *key = p;
        char *value = eq + 1;

        /* Trim whitespace */
        while (*key == ' ' || *key == '\t') key++;
        char *key_end = key + strlen(key) - 1;
        while (key_end > key && (*key_end == ' ' || *key_end == '\t')) *key_end-- = '\0';

        while (*value == ' ' || *value == '\t') value++;
        char *value_end = value + strlen(value) - 1;
        while (value_end > value && (*value_end == ' ' || *value_end == '\t' || *value_end == '\n')) *value_end-- = '\0';

        /* Apply configuration */
        if (strcmp(section, "server") == 0) {
            if (strcmp(key, "tcp_enabled") == 0) {
                g_config.tcp_enabled = (strcmp(value, "true") == 0 || strcmp(value, "1") == 0);
            } else if (strcmp(key, "tcp_port") == 0) {
                g_config.tcp_port = (uint16_t)atoi(value);
            } else if (strcmp(key, "tcp_bind_address") == 0) {
                strncpy(g_config.tcp_bind, value, sizeof(g_config.tcp_bind) - 1);
            } else if (strcmp(key, "rtu_enabled") == 0) {
                g_config.rtu_enabled = (strcmp(value, "true") == 0 || strcmp(value, "1") == 0);
            } else if (strcmp(key, "rtu_device") == 0) {
                strncpy(g_config.rtu_device, value, sizeof(g_config.rtu_device) - 1);
            } else if (strcmp(key, "rtu_baud_rate") == 0) {
                g_config.rtu_baud = atoi(value);
            } else if (strcmp(key, "rtu_slave_addr") == 0) {
                g_config.rtu_slave_addr = (uint8_t)atoi(value);
            }
        } else if (strcmp(section, "general") == 0) {
            if (strcmp(key, "log_level") == 0) {
                strncpy(g_config.log_level, value, sizeof(g_config.log_level) - 1);
            } else if (strcmp(key, "poll_interval_ms") == 0) {
                g_config.poll_interval_ms = atoi(value);
            }
        }
    }

    fclose(fp);
    return 0;
}

/* Print usage */
static void print_usage(const char *progname) {
    printf("Water Treatment Controller - Modbus Gateway v%s\n", VERSION);
    printf("\nUsage: %s [OPTIONS]\n\n", progname);
    printf("Options:\n");
    printf("  -c, --config FILE    Configuration file (default: %s)\n", g_config.config_file);
    printf("  -p, --port PORT      TCP port (default: %d)\n", g_config.tcp_port);
    printf("  -b, --bind ADDR      Bind address (default: %s)\n", g_config.tcp_bind);
    printf("  -d, --device DEV     RTU serial device\n");
    printf("  -s, --slave ADDR     RTU slave address (default: %d)\n", g_config.rtu_slave_addr);
    printf("  -l, --log-level LVL  Log level (DEBUG, INFO, WARN, ERROR)\n");
    printf("  -h, --help           Show this help message\n");
    printf("  -v, --version        Show version\n");
    printf("\n");
}

/* Parse command line arguments */
static int parse_args(int argc, char *argv[]) {
    static struct option long_options[] = {
        {"config",    required_argument, 0, 'c'},
        {"port",      required_argument, 0, 'p'},
        {"bind",      required_argument, 0, 'b'},
        {"device",    required_argument, 0, 'd'},
        {"slave",     required_argument, 0, 's'},
        {"log-level", required_argument, 0, 'l'},
        {"help",      no_argument,       0, 'h'},
        {"version",   no_argument,       0, 'v'},
        {0, 0, 0, 0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "c:p:b:d:s:l:hv", long_options, NULL)) != -1) {
        switch (opt) {
            case 'c':
                strncpy(g_config.config_file, optarg, sizeof(g_config.config_file) - 1);
                break;
            case 'p':
                g_config.tcp_port = (uint16_t)atoi(optarg);
                break;
            case 'b':
                strncpy(g_config.tcp_bind, optarg, sizeof(g_config.tcp_bind) - 1);
                break;
            case 'd':
                strncpy(g_config.rtu_device, optarg, sizeof(g_config.rtu_device) - 1);
                g_config.rtu_enabled = true;
                break;
            case 's':
                g_config.rtu_slave_addr = (uint8_t)atoi(optarg);
                break;
            case 'l':
                strncpy(g_config.log_level, optarg, sizeof(g_config.log_level) - 1);
                break;
            case 'h':
                print_usage(argv[0]);
                exit(0);
            case 'v':
                printf("modbus_gateway version %s\n", VERSION);
                exit(0);
            default:
                print_usage(argv[0]);
                return -1;
        }
    }

    return 0;
}

/* Initialize gateway */
static int init_gateway(void) {
    modbus_gateway_config_t mb_config = {
        .server = {
            .tcp_enabled = g_config.tcp_enabled,
            .tcp_port = g_config.tcp_port,
            .tcp_bind_address = {0},
            .rtu_enabled = g_config.rtu_enabled,
            .rtu_device = {0},
            .rtu_baud_rate = (uint32_t)g_config.rtu_baud,
            .rtu_slave_addr = g_config.rtu_slave_addr,
        },
        .downstream_count = 0,
        .register_map_file = {0},
        .auto_generate_map = true,
    };

    strncpy(mb_config.server.tcp_bind_address, g_config.tcp_bind, sizeof(mb_config.server.tcp_bind_address) - 1);
    mb_config.server.tcp_bind_address[sizeof(mb_config.server.tcp_bind_address) - 1] = '\0';
    strncpy(mb_config.server.rtu_device, g_config.rtu_device, sizeof(mb_config.server.rtu_device) - 1);
    mb_config.server.rtu_device[sizeof(mb_config.server.rtu_device) - 1] = '\0';

    wtc_result_t res = modbus_gateway_init(&g_gateway, &mb_config);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to initialize Modbus gateway: %d", res);
        return -1;
    }

    /* Connect to main controller via shared memory */
    /* Note: Gateway will operate in standalone mode if controller not running */

    return 0;
}

/* Main loop */
static void main_loop(void) {
    uint64_t last_process_ms = 0;

    /* Notify systemd we're ready */
    sd_notify(0, "READY=1");

    while (g_running) {
        uint64_t now_ms = time_get_monotonic_ms();

        /* Handle reload signal */
        if (g_reload) {
            g_reload = 0;
            LOG_INFO("Reloading configuration...");
            parse_config_file(g_config.config_file);
            /* Note: Full reload would require restart */
        }

        /* Process Modbus requests and downstream polling */
        if (now_ms - last_process_ms >= (uint64_t)g_config.poll_interval_ms) {
            modbus_gateway_process(g_gateway);
            last_process_ms = now_ms;
        }

        /* Watchdog notification */
        sd_notify(0, "WATCHDOG=1");

        /* Sleep to avoid busy loop */
        usleep(1000);  /* 1ms */
    }

    sd_notify(0, "STOPPING=1");
}

/* Cleanup */
static void cleanup(void) {
    if (g_gateway) {
        modbus_gateway_stop(g_gateway);
        modbus_gateway_cleanup(g_gateway);
        g_gateway = NULL;
    }
}

/* Main entry point */
int main(int argc, char *argv[]) {
    int ret = 0;

    /* Parse command line (before config file for -c option) */
    if (parse_args(argc, argv) != 0) {
        return 1;
    }

    /* Parse configuration file */
    if (parse_config_file(g_config.config_file) != 0) {
        return 1;
    }

    /* Re-parse args to override config file */
    optind = 1;
    parse_args(argc, argv);

    /* Initialize logging */
    log_level_t level = LOG_LEVEL_INFO;
    if (strcmp(g_config.log_level, "DEBUG") == 0) level = LOG_LEVEL_DEBUG;
    else if (strcmp(g_config.log_level, "WARN") == 0) level = LOG_LEVEL_WARN;
    else if (strcmp(g_config.log_level, "ERROR") == 0) level = LOG_LEVEL_ERROR;
    logger_config_t log_config = {
        .level = level,
        .output = NULL,
        .log_file = NULL,
        .use_colors = true,
        .include_timestamp = true,
        .include_source = true,
        .include_correlation_id = false,
        .max_file_size = 0,
        .max_backup_files = 0,
    };
    logger_init(&log_config);

    LOG_INFO("Starting Modbus Gateway v%s", VERSION);
    LOG_INFO("TCP: %s, Port: %d, Bind: %s",
             g_config.tcp_enabled ? "enabled" : "disabled",
             g_config.tcp_port, g_config.tcp_bind);
    if (g_config.rtu_enabled) {
        LOG_INFO("RTU: enabled, Device: %s, Slave: %d",
                 g_config.rtu_device, g_config.rtu_slave_addr);
    }

    /* Setup signal handlers */
    setup_signals();

    /* Initialize gateway */
    if (init_gateway() != 0) {
        ret = 1;
        goto cleanup;
    }

    /* Start gateway */
    wtc_result_t res = modbus_gateway_start(g_gateway);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to start Modbus gateway");
        ret = 1;
        goto cleanup;
    }

    /* Run main loop */
    main_loop();

cleanup:
    cleanup();
    LOG_INFO("Modbus Gateway stopped");
    return ret;
}
