/*
 * Water Treatment Controller - Buffer Utilities
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_BUFFER_H
#define WTC_BUFFER_H

#include "types.h"
#include <pthread.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Circular buffer for data samples */
typedef struct {
    void *data;
    size_t element_size;
    size_t capacity;
    size_t head;
    size_t tail;
    size_t count;
    pthread_mutex_t lock;
} circular_buffer_t;

/* Initialize circular buffer */
wtc_result_t buffer_init(circular_buffer_t *buf, size_t element_size, size_t capacity);

/* Free circular buffer */
void buffer_free(circular_buffer_t *buf);

/* Push element to buffer (overwrites oldest if full) */
wtc_result_t buffer_push(circular_buffer_t *buf, const void *element);

/* Pop element from buffer */
wtc_result_t buffer_pop(circular_buffer_t *buf, void *element);

/* Peek at oldest element without removing */
wtc_result_t buffer_peek(const circular_buffer_t *buf, void *element);

/* Get element at index (0 = oldest) */
wtc_result_t buffer_get(const circular_buffer_t *buf, size_t index, void *element);

/* Get buffer count */
size_t buffer_count(const circular_buffer_t *buf);

/* Check if buffer is empty */
bool buffer_is_empty(const circular_buffer_t *buf);

/* Check if buffer is full */
bool buffer_is_full(const circular_buffer_t *buf);

/* Clear buffer */
void buffer_clear(circular_buffer_t *buf);

/* Byte buffer for network I/O */
typedef struct {
    uint8_t *data;
    size_t capacity;
    size_t read_pos;
    size_t write_pos;
} byte_buffer_t;

/* Initialize byte buffer */
wtc_result_t byte_buffer_init(byte_buffer_t *buf, size_t capacity);

/* Free byte buffer */
void byte_buffer_free(byte_buffer_t *buf);

/* Reset byte buffer */
void byte_buffer_reset(byte_buffer_t *buf);

/* Get remaining readable bytes */
size_t byte_buffer_readable(const byte_buffer_t *buf);

/* Get remaining writable space */
size_t byte_buffer_writable(const byte_buffer_t *buf);

/* Write bytes to buffer */
wtc_result_t byte_buffer_write(byte_buffer_t *buf, const void *data, size_t len);

/* Read bytes from buffer */
wtc_result_t byte_buffer_read(byte_buffer_t *buf, void *data, size_t len);

/* Peek bytes without advancing read position */
wtc_result_t byte_buffer_peek(const byte_buffer_t *buf, void *data, size_t len);

/* Skip bytes */
wtc_result_t byte_buffer_skip(byte_buffer_t *buf, size_t len);

/* Get read pointer */
const uint8_t *byte_buffer_read_ptr(const byte_buffer_t *buf);

/* Get write pointer */
uint8_t *byte_buffer_write_ptr(byte_buffer_t *buf);

/* Advance write position after external write */
void byte_buffer_advance_write(byte_buffer_t *buf, size_t len);

/* Write integer types (network byte order) */
wtc_result_t byte_buffer_write_u8(byte_buffer_t *buf, uint8_t val);
wtc_result_t byte_buffer_write_u16(byte_buffer_t *buf, uint16_t val);
wtc_result_t byte_buffer_write_u32(byte_buffer_t *buf, uint32_t val);
wtc_result_t byte_buffer_write_float(byte_buffer_t *buf, float val);

/* Read integer types (network byte order) */
wtc_result_t byte_buffer_read_u8(byte_buffer_t *buf, uint8_t *val);
wtc_result_t byte_buffer_read_u16(byte_buffer_t *buf, uint16_t *val);
wtc_result_t byte_buffer_read_u32(byte_buffer_t *buf, uint32_t *val);
wtc_result_t byte_buffer_read_float(byte_buffer_t *buf, float *val);

#ifdef __cplusplus
}
#endif

#endif /* WTC_BUFFER_H */
