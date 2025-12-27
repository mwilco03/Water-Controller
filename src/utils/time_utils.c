/*
 * Water Treatment Controller - Time Utilities Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "time_utils.h"
#include <stdio.h>
#include <string.h>
#include <errno.h>

uint64_t time_get_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (uint64_t)ts.tv_sec * 1000 + (uint64_t)ts.tv_nsec / 1000000;
}

uint64_t time_get_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (uint64_t)ts.tv_sec * 1000000 + (uint64_t)ts.tv_nsec / 1000;
}

uint64_t time_get_monotonic_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000 + (uint64_t)ts.tv_nsec / 1000000;
}

uint64_t time_get_monotonic_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000 + (uint64_t)ts.tv_nsec / 1000;
}

void time_sleep_ms(uint32_t ms) {
    struct timespec ts;
    ts.tv_sec = ms / 1000;
    ts.tv_nsec = (ms % 1000) * 1000000;

    while (nanosleep(&ts, &ts) == -1 && errno == EINTR) {
        /* Continue sleeping */
    }
}

void time_sleep_us(uint64_t us) {
    struct timespec ts;
    ts.tv_sec = us / 1000000;
    ts.tv_nsec = (us % 1000000) * 1000;

    while (nanosleep(&ts, &ts) == -1 && errno == EINTR) {
        /* Continue sleeping */
    }
}

void time_ms_to_timespec(uint64_t ms, struct timespec *ts) {
    if (!ts) return;
    ts->tv_sec = ms / 1000;
    ts->tv_nsec = (ms % 1000) * 1000000;
}

uint64_t time_timespec_to_ms(const struct timespec *ts) {
    if (!ts) return 0;
    return (uint64_t)ts->tv_sec * 1000 + (uint64_t)ts->tv_nsec / 1000000;
}

void time_add_ms(struct timespec *ts, uint64_t ms) {
    if (!ts) return;

    ts->tv_sec += ms / 1000;
    ts->tv_nsec += (ms % 1000) * 1000000;

    while (ts->tv_nsec >= 1000000000) {
        ts->tv_sec++;
        ts->tv_nsec -= 1000000000;
    }
}

int time_compare(const struct timespec *a, const struct timespec *b) {
    if (!a || !b) return 0;

    if (a->tv_sec < b->tv_sec) return -1;
    if (a->tv_sec > b->tv_sec) return 1;
    if (a->tv_nsec < b->tv_nsec) return -1;
    if (a->tv_nsec > b->tv_nsec) return 1;
    return 0;
}

void time_format_iso8601(uint64_t ms, char *buf, size_t buf_size) {
    if (!buf || buf_size < 25) return;

    time_t secs = ms / 1000;
    int millis = ms % 1000;
    struct tm *tm_info = gmtime(&secs);

    strftime(buf, buf_size, "%Y-%m-%dT%H:%M:%S", tm_info);
    snprintf(buf + 19, buf_size - 19, ".%03dZ", millis);
}

void time_format_date(uint64_t ms, char *buf, size_t buf_size) {
    if (!buf || buf_size < 11) return;  /* YYYY-MM-DD + null */

    time_t secs = ms / 1000;
    struct tm *tm_info = gmtime(&secs);

    strftime(buf, buf_size, "%Y-%m-%d", tm_info);
}

uint64_t time_parse_iso8601(const char *str) {
    if (!str) return 0;

    struct tm tm_info = {0};
    int millis = 0;

    /* Parse basic format: YYYY-MM-DDTHH:MM:SS.sssZ */
    if (sscanf(str, "%d-%d-%dT%d:%d:%d.%d",
               &tm_info.tm_year, &tm_info.tm_mon, &tm_info.tm_mday,
               &tm_info.tm_hour, &tm_info.tm_min, &tm_info.tm_sec,
               &millis) >= 6) {
        tm_info.tm_year -= 1900;
        tm_info.tm_mon -= 1;
        time_t secs = timegm(&tm_info);
        return (uint64_t)secs * 1000 + millis;
    }

    /* Try without milliseconds */
    if (sscanf(str, "%d-%d-%dT%d:%d:%d",
               &tm_info.tm_year, &tm_info.tm_mon, &tm_info.tm_mday,
               &tm_info.tm_hour, &tm_info.tm_min, &tm_info.tm_sec) == 6) {
        tm_info.tm_year -= 1900;
        tm_info.tm_mon -= 1;
        time_t secs = timegm(&tm_info);
        return (uint64_t)secs * 1000;
    }

    return 0;
}

void timer_init(wtc_timer_t *timer) {
    if (!timer) return;
    timer->start_us = 0;
    timer->accumulated_us = 0;
    timer->running = false;
}

void timer_start(wtc_timer_t *timer) {
    if (!timer || timer->running) return;
    timer->start_us = time_get_monotonic_us();
    timer->running = true;
}

void timer_stop(wtc_timer_t *timer) {
    if (!timer || !timer->running) return;
    timer->accumulated_us += time_get_monotonic_us() - timer->start_us;
    timer->running = false;
}

void timer_reset(wtc_timer_t *timer) {
    if (!timer) return;
    timer->start_us = 0;
    timer->accumulated_us = 0;
    timer->running = false;
}

uint64_t timer_elapsed_us(const wtc_timer_t *timer) {
    if (!timer) return 0;

    uint64_t elapsed = timer->accumulated_us;
    if (timer->running) {
        elapsed += time_get_monotonic_us() - timer->start_us;
    }
    return elapsed;
}

uint64_t timer_elapsed_ms(const wtc_timer_t *timer) {
    return timer_elapsed_us(timer) / 1000;
}
