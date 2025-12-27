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

/* Thread-local correlation context */
static __thread struct {
    char id[WTC_CORRELATION_ID_LEN];
    uint64_t start_time_ms;
    const char *operation;
    bool active;
} tls_correlation = {
    .id = "",
    .start_time_ms = 0,
    .operation = NULL,
    .active = false,
};

/* Global logger state */
static struct {
    log_level_t level;
    FILE *output;
    FILE *file;
    char log_file[256];
    bool use_colors;
    bool include_timestamp;
    bool include_source;
    bool include_correlation_id;
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
    .include_correlation_id = true,
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
        g_logger.include_correlation_id = config->include_correlation_id;
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

    /* Get correlation ID (thread-local) */
    char correlation[48] = "";
    if (g_logger.include_correlation_id && tls_correlation.active && tls_correlation.id[0]) {
        snprintf(correlation, sizeof(correlation), "[%s] ", tls_correlation.id);
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
        if (correlation[0]) {
            fprintf(g_logger.output, "%s", correlation);
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
            if (correlation[0]) {
                fprintf(g_logger.file, "%s", correlation);
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

/* ============== Correlation ID Implementation ============== */

/* Get current time in milliseconds */
static uint64_t get_time_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000 + (uint64_t)ts.tv_nsec / 1000000;
}

void correlation_id_generate(char *id_out) {
    if (!id_out) return;

    /* Generate a pseudo-random UUID v4 format:
     * xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
     * where x is any hexadecimal digit and y is one of 8, 9, A, or B */
    static __thread uint32_t counter = 0;
    uint64_t now = get_time_ms();
    uint32_t tid = (uint32_t)pthread_self();

    /* Mix time, thread id, and counter for uniqueness */
    uint32_t a = (uint32_t)(now >> 32) ^ tid;
    uint32_t b = (uint32_t)(now & 0xFFFFFFFF);
    uint32_t c = ++counter;
    uint32_t d = (uint32_t)(now >> 16) ^ (tid << 8) ^ counter;

    snprintf(id_out, WTC_CORRELATION_ID_LEN,
             "%08x-%04x-4%03x-%x%03x-%08x%04x",
             a,
             (b >> 16) & 0xFFFF,
             b & 0x0FFF,
             8 + (c & 0x3),  /* y is 8, 9, A, or B */
             (c >> 4) & 0x0FFF,
             d,
             (c >> 16) & 0xFFFF);
}

void correlation_id_set(const char *id) {
    if (id && id[0]) {
        strncpy(tls_correlation.id, id, WTC_CORRELATION_ID_LEN - 1);
        tls_correlation.id[WTC_CORRELATION_ID_LEN - 1] = '\0';
        tls_correlation.active = true;
    } else {
        tls_correlation.id[0] = '\0';
        tls_correlation.active = false;
        tls_correlation.operation = NULL;
        tls_correlation.start_time_ms = 0;
    }
}

const char *correlation_id_get(void) {
    return tls_correlation.active ? tls_correlation.id : NULL;
}

void correlation_id_start(const char *operation, char *id_out) {
    char id[WTC_CORRELATION_ID_LEN];
    correlation_id_generate(id);

    tls_correlation.start_time_ms = get_time_ms();
    tls_correlation.operation = operation;
    strncpy(tls_correlation.id, id, WTC_CORRELATION_ID_LEN - 1);
    tls_correlation.id[WTC_CORRELATION_ID_LEN - 1] = '\0';
    tls_correlation.active = true;

    if (id_out) {
        strncpy(id_out, id, WTC_CORRELATION_ID_LEN - 1);
        id_out[WTC_CORRELATION_ID_LEN - 1] = '\0';
    }
}

void correlation_id_end(void) {
    if (!tls_correlation.active) return;

    uint64_t duration_ms = get_time_ms() - tls_correlation.start_time_ms;

    /* Log the completion with duration */
    if (tls_correlation.operation) {
        LOG_DEBUG("Completed operation: %s [%s] (duration: %lums)",
                  tls_correlation.operation,
                  tls_correlation.id,
                  (unsigned long)duration_ms);
    }

    /* Clear the correlation context */
    tls_correlation.id[0] = '\0';
    tls_correlation.active = false;
    tls_correlation.operation = NULL;
    tls_correlation.start_time_ms = 0;
}

void correlation_id_copy(char *dest, size_t dest_size, const char *src) {
    if (!dest || dest_size == 0) return;

    if (src && src[0]) {
        size_t len = strlen(src);
        if (len >= dest_size) {
            len = dest_size - 1;
        }
        memcpy(dest, src, len);
        dest[len] = '\0';
    } else {
        dest[0] = '\0';
    }
}

bool correlation_id_parse(const char *input, char *id_out) {
    if (!input || !id_out) return false;

    /* Look for UUID pattern: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx */
    const char *p = input;
    while (*p) {
        /* Check if we have a potential UUID starting here */
        bool valid = true;
        int dash_count = 0;
        int hex_count = 0;

        for (int i = 0; i < 36 && p[i]; i++) {
            char c = p[i];
            if (i == 8 || i == 13 || i == 18 || i == 23) {
                if (c != '-') {
                    valid = false;
                    break;
                }
                dash_count++;
            } else {
                if (!((c >= '0' && c <= '9') ||
                      (c >= 'a' && c <= 'f') ||
                      (c >= 'A' && c <= 'F'))) {
                    valid = false;
                    break;
                }
                hex_count++;
            }
        }

        if (valid && dash_count == 4 && hex_count == 32) {
            memcpy(id_out, p, 36);
            id_out[36] = '\0';
            return true;
        }
        p++;
    }

    return false;
}
