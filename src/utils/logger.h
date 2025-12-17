/*
 * Water Treatment Controller - Logger
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_LOGGER_H
#define WTC_LOGGER_H

#include "types.h"
#include <stdio.h>
#include <stdarg.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Logger configuration */
typedef struct {
    log_level_t level;
    FILE *output;
    const char *log_file;
    bool use_colors;
    bool include_timestamp;
    bool include_source;
    size_t max_file_size;
    int max_backup_files;
} logger_config_t;

/* Initialize logger with configuration */
wtc_result_t logger_init(const logger_config_t *config);

/* Cleanup logger */
void logger_cleanup(void);

/* Set log level */
void logger_set_level(log_level_t level);

/* Get current log level */
log_level_t logger_get_level(void);

/* Enable/disable colors */
void logger_set_colors(bool enabled);

/* Log functions */
void logger_log(log_level_t level, const char *file, int line,
                const char *func, const char *fmt, ...);
void logger_vlog(log_level_t level, const char *file, int line,
                 const char *func, const char *fmt, va_list args);

/* Convenience macros */
#define LOG_TRACE(...) logger_log(LOG_LEVEL_TRACE, __FILE__, __LINE__, __func__, __VA_ARGS__)
#define LOG_DEBUG(...) logger_log(LOG_LEVEL_DEBUG, __FILE__, __LINE__, __func__, __VA_ARGS__)
#define LOG_INFO(...)  logger_log(LOG_LEVEL_INFO, __FILE__, __LINE__, __func__, __VA_ARGS__)
#define LOG_WARN(...)  logger_log(LOG_LEVEL_WARN, __FILE__, __LINE__, __func__, __VA_ARGS__)
#define LOG_ERROR(...) logger_log(LOG_LEVEL_ERROR, __FILE__, __LINE__, __func__, __VA_ARGS__)
#define LOG_FATAL(...) logger_log(LOG_LEVEL_FATAL, __FILE__, __LINE__, __func__, __VA_ARGS__)

/* Hex dump for debugging */
void logger_hexdump(log_level_t level, const char *prefix,
                    const void *data, size_t len);

#ifdef __cplusplus
}
#endif

#endif /* WTC_LOGGER_H */
