/*
 * Water Treatment Controller - Buffer Utilities Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "buffer.h"
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <arpa/inet.h>

/* Circular buffer implementation */

wtc_result_t buffer_init(circular_buffer_t *buf, size_t element_size, size_t capacity) {
    if (!buf || element_size == 0 || capacity == 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    buf->data = calloc(capacity, element_size);
    if (!buf->data) {
        return WTC_ERROR_NO_MEMORY;
    }

    buf->element_size = element_size;
    buf->capacity = capacity;
    buf->head = 0;
    buf->tail = 0;
    buf->count = 0;

    pthread_mutex_init(&buf->lock, NULL);

    return WTC_OK;
}

void buffer_free(circular_buffer_t *buf) {
    if (!buf) return;

    pthread_mutex_destroy(&buf->lock);
    free(buf->data);
    buf->data = NULL;
    buf->capacity = 0;
    buf->count = 0;
}

wtc_result_t buffer_push(circular_buffer_t *buf, const void *element) {
    if (!buf || !buf->data || !element) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&buf->lock);

    /* Copy element to head position */
    memcpy((uint8_t *)buf->data + buf->head * buf->element_size,
           element, buf->element_size);

    buf->head = (buf->head + 1) % buf->capacity;

    if (buf->count < buf->capacity) {
        buf->count++;
    } else {
        /* Buffer full, advance tail (drop oldest) */
        buf->tail = (buf->tail + 1) % buf->capacity;
    }

    pthread_mutex_unlock(&buf->lock);
    return WTC_OK;
}

wtc_result_t buffer_pop(circular_buffer_t *buf, void *element) {
    if (!buf || !buf->data || !element) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&buf->lock);

    if (buf->count == 0) {
        pthread_mutex_unlock(&buf->lock);
        return WTC_ERROR_EMPTY;
    }

    memcpy(element, (uint8_t *)buf->data + buf->tail * buf->element_size,
           buf->element_size);

    buf->tail = (buf->tail + 1) % buf->capacity;
    buf->count--;

    pthread_mutex_unlock(&buf->lock);
    return WTC_OK;
}

wtc_result_t buffer_peek(const circular_buffer_t *buf, void *element) {
    if (!buf || !buf->data || !element) {
        return WTC_ERROR_INVALID_PARAM;
    }

    circular_buffer_t *mut_buf = (circular_buffer_t *)buf;
    pthread_mutex_lock(&mut_buf->lock);

    if (buf->count == 0) {
        pthread_mutex_unlock(&mut_buf->lock);
        return WTC_ERROR_EMPTY;
    }

    memcpy(element, (uint8_t *)buf->data + buf->tail * buf->element_size,
           buf->element_size);

    pthread_mutex_unlock(&mut_buf->lock);
    return WTC_OK;
}

wtc_result_t buffer_get(const circular_buffer_t *buf, size_t index, void *element) {
    if (!buf || !buf->data || !element) {
        return WTC_ERROR_INVALID_PARAM;
    }

    circular_buffer_t *mut_buf = (circular_buffer_t *)buf;
    pthread_mutex_lock(&mut_buf->lock);

    if (index >= buf->count) {
        pthread_mutex_unlock(&mut_buf->lock);
        return WTC_ERROR_INVALID_PARAM;
    }

    size_t actual_index = (buf->tail + index) % buf->capacity;
    memcpy(element, (uint8_t *)buf->data + actual_index * buf->element_size,
           buf->element_size);

    pthread_mutex_unlock(&mut_buf->lock);
    return WTC_OK;
}

size_t buffer_count(const circular_buffer_t *buf) {
    return buf ? buf->count : 0;
}

bool buffer_is_empty(const circular_buffer_t *buf) {
    return buf ? buf->count == 0 : true;
}

bool buffer_is_full(const circular_buffer_t *buf) {
    return buf ? buf->count == buf->capacity : false;
}

void buffer_clear(circular_buffer_t *buf) {
    if (!buf) return;

    pthread_mutex_lock(&buf->lock);
    buf->head = 0;
    buf->tail = 0;
    buf->count = 0;
    pthread_mutex_unlock(&buf->lock);
}

/* Byte buffer implementation */

wtc_result_t byte_buffer_init(byte_buffer_t *buf, size_t capacity) {
    if (!buf || capacity == 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    buf->data = malloc(capacity);
    if (!buf->data) {
        return WTC_ERROR_NO_MEMORY;
    }

    buf->capacity = capacity;
    buf->read_pos = 0;
    buf->write_pos = 0;

    return WTC_OK;
}

void byte_buffer_free(byte_buffer_t *buf) {
    if (!buf) return;
    free(buf->data);
    buf->data = NULL;
    buf->capacity = 0;
}

void byte_buffer_reset(byte_buffer_t *buf) {
    if (!buf) return;
    buf->read_pos = 0;
    buf->write_pos = 0;
}

size_t byte_buffer_readable(const byte_buffer_t *buf) {
    return buf ? buf->write_pos - buf->read_pos : 0;
}

size_t byte_buffer_writable(const byte_buffer_t *buf) {
    return buf ? buf->capacity - buf->write_pos : 0;
}

wtc_result_t byte_buffer_write(byte_buffer_t *buf, const void *data, size_t len) {
    if (!buf || !buf->data || !data) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (byte_buffer_writable(buf) < len) {
        return WTC_ERROR_FULL;
    }

    memcpy(buf->data + buf->write_pos, data, len);
    buf->write_pos += len;

    return WTC_OK;
}

wtc_result_t byte_buffer_read(byte_buffer_t *buf, void *data, size_t len) {
    if (!buf || !buf->data || !data) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (byte_buffer_readable(buf) < len) {
        return WTC_ERROR_EMPTY;
    }

    memcpy(data, buf->data + buf->read_pos, len);
    buf->read_pos += len;

    return WTC_OK;
}

wtc_result_t byte_buffer_peek(const byte_buffer_t *buf, void *data, size_t len) {
    if (!buf || !buf->data || !data) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (byte_buffer_readable(buf) < len) {
        return WTC_ERROR_EMPTY;
    }

    memcpy(data, buf->data + buf->read_pos, len);
    return WTC_OK;
}

wtc_result_t byte_buffer_skip(byte_buffer_t *buf, size_t len) {
    if (!buf) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (byte_buffer_readable(buf) < len) {
        return WTC_ERROR_EMPTY;
    }

    buf->read_pos += len;
    return WTC_OK;
}

const uint8_t *byte_buffer_read_ptr(const byte_buffer_t *buf) {
    return buf ? buf->data + buf->read_pos : NULL;
}

uint8_t *byte_buffer_write_ptr(byte_buffer_t *buf) {
    return buf ? buf->data + buf->write_pos : NULL;
}

void byte_buffer_advance_write(byte_buffer_t *buf, size_t len) {
    if (buf && buf->write_pos + len <= buf->capacity) {
        buf->write_pos += len;
    }
}

wtc_result_t byte_buffer_write_u8(byte_buffer_t *buf, uint8_t val) {
    return byte_buffer_write(buf, &val, sizeof(val));
}

wtc_result_t byte_buffer_write_u16(byte_buffer_t *buf, uint16_t val) {
    uint16_t net_val = htons(val);
    return byte_buffer_write(buf, &net_val, sizeof(net_val));
}

wtc_result_t byte_buffer_write_u32(byte_buffer_t *buf, uint32_t val) {
    uint32_t net_val = htonl(val);
    return byte_buffer_write(buf, &net_val, sizeof(net_val));
}

wtc_result_t byte_buffer_write_float(byte_buffer_t *buf, float val) {
    /* IEEE 754 float, network byte order */
    uint32_t int_val;
    memcpy(&int_val, &val, sizeof(int_val));
    return byte_buffer_write_u32(buf, int_val);
}

wtc_result_t byte_buffer_read_u8(byte_buffer_t *buf, uint8_t *val) {
    return byte_buffer_read(buf, val, sizeof(*val));
}

wtc_result_t byte_buffer_read_u16(byte_buffer_t *buf, uint16_t *val) {
    wtc_result_t res = byte_buffer_read(buf, val, sizeof(*val));
    if (res == WTC_OK) {
        *val = ntohs(*val);
    }
    return res;
}

wtc_result_t byte_buffer_read_u32(byte_buffer_t *buf, uint32_t *val) {
    wtc_result_t res = byte_buffer_read(buf, val, sizeof(*val));
    if (res == WTC_OK) {
        *val = ntohl(*val);
    }
    return res;
}

wtc_result_t byte_buffer_read_float(byte_buffer_t *buf, float *val) {
    uint32_t int_val;
    wtc_result_t res = byte_buffer_read_u32(buf, &int_val);
    if (res == WTC_OK) {
        memcpy(val, &int_val, sizeof(*val));
    }
    return res;
}
