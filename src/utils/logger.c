/*
 * Water Treatment Controller - Logger Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "logger.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <pthread.h>
#include <unistd.h>
#include <sys/stat.h>

/* ANSI color codes */
#define COLOR_RESET   "\033[0m"
#define COLOR_RED     "\033[31m"
#define COLOR_GREEN   "\033[32m"
#define COLOR_YELLOW  "\033[33m"
#define COLOR_BLUE    "\033[34m"
#define COLOR_MAGENTA "\033[35m"
#define COLOR_CYAN    "\033[36m"
#define COLOR_WHITE   "\033[37m"
#define COLOR_BOLD    "\033[1m"

/* Global logger state */
static struct {
    log_level_t level;
    FILE *output;
    FILE *file;
    char log_file[256];
    bool use_colors;
    bool include_timestamp;
    bool include_source;
    size_t max_file_size;
    int max_backup_files;
    pthread_mutex_t lock;
    bool initialized;
} g_logger = {
    .level = LOG_LEVEL_INFO,
    .output = NULL,
    .file = NULL,
    .use_colors = true,
    .include_timestamp = true,
    .include_source = true,
    .max_file_size = 10 * 1024 * 1024, /* 10MB */
    .max_backup_files = 5,
    .initialized = false,
};

/* Level strings */
static const char *level_strings[] = {
    "TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"
};

/* Level colors */
static const char *level_colors[] = {
    COLOR_CYAN,    /* TRACE */
    COLOR_BLUE,    /* DEBUG */
    COLOR_GREEN,   /* INFO */
    COLOR_YELLOW,  /* WARN */
    COLOR_RED,     /* ERROR */
    COLOR_BOLD COLOR_RED, /* FATAL */
};

/* Get file size */
static size_t get_file_size(FILE *fp) {
    if (!fp) return 0;
    long pos = ftell(fp);
    fseek(fp, 0, SEEK_END);
    size_t size = (size_t)ftell(fp);
    fseek(fp, pos, SEEK_SET);
    return size;
}

/* Rotate log files */
static void rotate_logs(void) {
    if (!g_logger.file || g_logger.log_file[0] == '\0') return;

    fclose(g_logger.file);
    g_logger.file = NULL;

    char old_path[280], new_path[280];

    /* Remove oldest backup */
    snprintf(old_path, sizeof(old_path), "%s.%d",
             g_logger.log_file, g_logger.max_backup_files);
    unlink(old_path);

    /* Rotate existing backups */
    for (int i = g_logger.max_backup_files - 1; i >= 1; i--) {
        snprintf(old_path, sizeof(old_path), "%s.%d", g_logger.log_file, i);
        snprintf(new_path, sizeof(new_path), "%s.%d", g_logger.log_file, i + 1);
        rename(old_path, new_path);
    }

    /* Rename current to .1 */
    snprintf(new_path, sizeof(new_path), "%s.1", g_logger.log_file);
    rename(g_logger.log_file, new_path);

    /* Open new file */
    g_logger.file = fopen(g_logger.log_file, "a");
}

wtc_result_t logger_init(const logger_config_t *config) {
    if (g_logger.initialized) {
        return WTC_OK;
    }

    pthread_mutex_init(&g_logger.lock, NULL);

    if (config) {
        g_logger.level = config->level;
        g_logger.output = config->output ? config->output : stderr;
        g_logger.use_colors = config->use_colors;
        g_logger.include_timestamp = config->include_timestamp;
        g_logger.include_source = config->include_source;
        g_logger.max_file_size = config->max_file_size > 0 ?
                                 config->max_file_size : g_logger.max_file_size;
        g_logger.max_backup_files = config->max_backup_files > 0 ?
                                    config->max_backup_files : g_logger.max_backup_files;

        if (config->log_file && config->log_file[0] != '\0') {
            strncpy(g_logger.log_file, config->log_file, sizeof(g_logger.log_file) - 1);
            g_logger.file = fopen(config->log_file, "a");
            if (!g_logger.file) {
                fprintf(stderr, "Warning: Could not open log file: %s\n", config->log_file);
            }
        }
    } else {
        g_logger.output = stderr;
    }

    g_logger.initialized = true;
    return WTC_OK;
}

void logger_cleanup(void) {
    if (!g_logger.initialized) return;

    pthread_mutex_lock(&g_logger.lock);

    if (g_logger.file) {
        fclose(g_logger.file);
        g_logger.file = NULL;
    }

    pthread_mutex_unlock(&g_logger.lock);
    pthread_mutex_destroy(&g_logger.lock);

    g_logger.initialized = false;
}

void logger_set_level(log_level_t level) {
    g_logger.level = level;
}

log_level_t logger_get_level(void) {
    return g_logger.level;
}

void logger_set_colors(bool enabled) {
    g_logger.use_colors = enabled;
}

void logger_vlog(log_level_t level, const char *file, int line,
                 const char *func, const char *fmt, va_list args) {
    (void)func;  /* Reserved for future use in extended log format */
    if (level < g_logger.level) return;

    if (!g_logger.initialized) {
        logger_init(NULL);
    }

    pthread_mutex_lock(&g_logger.lock);

    /* Get timestamp */
    char timestamp[32] = "";
    if (g_logger.include_timestamp) {
        time_t now = time(NULL);
        struct tm *tm_info = localtime(&now);
        strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S", tm_info);
    }

    /* Get source location */
    char source[128] = "";
    if (g_logger.include_source && file) {
        const char *basename = strrchr(file, '/');
        basename = basename ? basename + 1 : file;
        snprintf(source, sizeof(source), "%s:%d", basename, line);
    }

    /* Format message */
    char message[4096];
    vsnprintf(message, sizeof(message), fmt, args);

    /* Write to console */
    if (g_logger.output) {
        if (g_logger.use_colors && isatty(fileno(g_logger.output))) {
            fprintf(g_logger.output, "%s[%s]%s ",
                    level_colors[level], level_strings[level], COLOR_RESET);
        } else {
            fprintf(g_logger.output, "[%s] ", level_strings[level]);
        }

        if (timestamp[0]) {
            fprintf(g_logger.output, "%s ", timestamp);
        }
        if (source[0]) {
            fprintf(g_logger.output, "(%s) ", source);
        }
        fprintf(g_logger.output, "%s\n", message);
        fflush(g_logger.output);
    }

    /* Write to file */
    if (g_logger.file) {
        /* Check for rotation */
        if (g_logger.max_file_size > 0 &&
            get_file_size(g_logger.file) > g_logger.max_file_size) {
            rotate_logs();
        }

        if (g_logger.file) {
            fprintf(g_logger.file, "[%s] ", level_strings[level]);
            if (timestamp[0]) {
                fprintf(g_logger.file, "%s ", timestamp);
            }
            if (source[0]) {
                fprintf(g_logger.file, "(%s) ", source);
            }
            fprintf(g_logger.file, "%s\n", message);
            fflush(g_logger.file);
        }
    }

    pthread_mutex_unlock(&g_logger.lock);
}

void logger_log(log_level_t level, const char *file, int line,
                const char *func, const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    logger_vlog(level, file, line, func, fmt, args);
    va_end(args);
    (void)func; /* Unused for now */
}

void logger_hexdump(log_level_t level, const char *prefix,
                    const void *data, size_t len) {
    if (level < g_logger.level) return;

    const uint8_t *bytes = (const uint8_t *)data;
    char line[128];
    char ascii[17];
    size_t i;

    for (i = 0; i < len; i++) {
        if (i % 16 == 0) {
            if (i > 0) {
                logger_log(level, NULL, 0, NULL, "%s%s  %s",
                          prefix ? prefix : "", line, ascii);
            }
            snprintf(line, sizeof(line), "%04zx: ", i);
            memset(ascii, 0, sizeof(ascii));
        }

        char hex[4];
        snprintf(hex, sizeof(hex), "%02x ", bytes[i]);
        strncat(line, hex, sizeof(line) - strlen(line) - 1);

        ascii[i % 16] = (bytes[i] >= 32 && bytes[i] < 127) ? bytes[i] : '.';
    }

    /* Print last line */
    if (len > 0) {
        /* Pad if necessary */
        while (i % 16 != 0) {
            strncat(line, "   ", sizeof(line) - strlen(line) - 1);
            i++;
        }
        logger_log(level, NULL, 0, NULL, "%s%s  %s",
                  prefix ? prefix : "", line, ascii);
    }
}
