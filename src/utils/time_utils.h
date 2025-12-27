/*
 * Water Treatment Controller - Time Utilities
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_TIME_UTILS_H
#define WTC_TIME_UTILS_H

#include "types.h"
#include <time.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Get current time in milliseconds since epoch */
uint64_t time_get_ms(void);

/* Get current time in microseconds since epoch */
uint64_t time_get_us(void);

/* Get monotonic time in milliseconds (for timing/intervals) */
uint64_t time_get_monotonic_ms(void);

/* Get monotonic time in microseconds */
uint64_t time_get_monotonic_us(void);

/* Sleep for specified milliseconds */
void time_sleep_ms(uint32_t ms);

/* Sleep for specified microseconds */
void time_sleep_us(uint64_t us);

/* Convert milliseconds to timespec */
void time_ms_to_timespec(uint64_t ms, struct timespec *ts);

/* Convert timespec to milliseconds */
uint64_t time_timespec_to_ms(const struct timespec *ts);

/* Add milliseconds to timespec */
void time_add_ms(struct timespec *ts, uint64_t ms);

/* Compare timespecs: returns <0 if a<b, 0 if equal, >0 if a>b */
int time_compare(const struct timespec *a, const struct timespec *b);

/* Format timestamp as ISO 8601 string */
void time_format_iso8601(uint64_t ms, char *buf, size_t buf_size);

/* Format timestamp as date only (YYYY-MM-DD) */
void time_format_date(uint64_t ms, char *buf, size_t buf_size);

/* Parse ISO 8601 string to milliseconds */
uint64_t time_parse_iso8601(const char *str);

/* Timer structure for measuring intervals */
typedef struct {
    uint64_t start_us;
    uint64_t accumulated_us;
    bool running;
} wtc_timer_t;

/* Initialize timer */
void timer_init(wtc_timer_t *timer);

/* Start timer */
void timer_start(wtc_timer_t *timer);

/* Stop timer and accumulate elapsed time */
void timer_stop(wtc_timer_t *timer);

/* Reset timer */
void timer_reset(wtc_timer_t *timer);

/* Get elapsed time in microseconds */
uint64_t timer_elapsed_us(const wtc_timer_t *timer);

/* Get elapsed time in milliseconds */
uint64_t timer_elapsed_ms(const wtc_timer_t *timer);

#ifdef __cplusplus
}
#endif

#endif /* WTC_TIME_UTILS_H */
