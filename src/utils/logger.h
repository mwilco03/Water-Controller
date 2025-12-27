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

/* Correlation ID for distributed tracing */
#define WTC_CORRELATION_ID_LEN 37  /* UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx + null */

typedef struct {
    char id[WTC_CORRELATION_ID_LEN];
    uint64_t start_time_ms;
    const char *operation;
} correlation_context_t;

/* Logger configuration */
typedef struct {
    log_level_t level;
    FILE *output;
    const char *log_file;
    bool use_colors;
    bool include_timestamp;
    bool include_source;
    bool include_correlation_id;
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

/* ============== Correlation ID Support ============== */

/**
 * Generate a new correlation ID.
 * Returns a UUID-format string that can be used to track related operations.
 */
void correlation_id_generate(char *id_out);

/**
 * Set the correlation ID for the current thread.
 * All subsequent log messages from this thread will include this ID.
 * Pass NULL to clear the correlation ID.
 */
void correlation_id_set(const char *id);

/**
 * Get the current thread's correlation ID.
 * Returns NULL if no correlation ID is set.
 */
const char *correlation_id_get(void);

/**
 * Start a new correlated operation.
 * Generates a new correlation ID and sets it for the current thread.
 * Returns the generated ID in id_out (if not NULL).
 */
void correlation_id_start(const char *operation, char *id_out);

/**
 * End the current correlated operation.
 * Logs operation completion with duration and clears the correlation ID.
 */
void correlation_id_end(void);

/**
 * Copy correlation ID from source to destination.
 * Used for propagating correlation IDs across IPC/network boundaries.
 */
void correlation_id_copy(char *dest, size_t dest_size, const char *src);

/**
 * Parse correlation ID from a message/packet.
 * Returns true if a valid correlation ID was found.
 */
bool correlation_id_parse(const char *input, char *id_out);

/* Convenience macros for correlated logging */
#define LOG_CORRELATED_START(op) \
    do { \
        char _cid[WTC_CORRELATION_ID_LEN]; \
        correlation_id_start(op, _cid); \
        LOG_DEBUG("Starting operation: %s [%s]", op, _cid); \
    } while(0)

#define LOG_CORRELATED_END() \
    do { \
        correlation_id_end(); \
    } while(0)

/* Log with explicit correlation ID (for cross-process correlation) */
#define LOG_WITH_CID(level, cid, ...) \
    do { \
        const char *_old_cid = correlation_id_get(); \
        correlation_id_set(cid); \
        logger_log(level, __FILE__, __LINE__, __func__, __VA_ARGS__); \
        correlation_id_set(_old_cid); \
    } while(0)

#ifdef __cplusplus
}
#endif

#endif /* WTC_LOGGER_H */
