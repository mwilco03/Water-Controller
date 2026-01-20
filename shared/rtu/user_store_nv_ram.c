/**
 * @file user_store_nv_ram.c
 * @brief RAM-based NV storage backend implementation
 *
 * Provides non-persistent storage for testing and development.
 *
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "user_store_nv_ram.h"
#include <string.h>

/* Storage size: header (16 bytes) + 16 users * 100 bytes each = ~1.7KB */
#define RAM_STORAGE_SIZE    2048

/* Static RAM buffer */
static uint8_t g_ram_storage[RAM_STORAGE_SIZE];
static size_t g_ram_used = 0;

/* ============== NV Operations Implementation ============== */

static int ram_read(uint32_t offset, void *data, size_t len) {
    if (!data) {
        return -1;
    }

    if (offset + len > RAM_STORAGE_SIZE) {
        return -1;
    }

    memcpy(data, &g_ram_storage[offset], len);

    /* Track high water mark */
    if (offset + len > g_ram_used) {
        g_ram_used = offset + len;
    }

    return 0;
}

static int ram_write(uint32_t offset, const void *data, size_t len) {
    if (!data) {
        return -1;
    }

    if (offset + len > RAM_STORAGE_SIZE) {
        return -1;
    }

    memcpy(&g_ram_storage[offset], data, len);

    /* Track high water mark */
    if (offset + len > g_ram_used) {
        g_ram_used = offset + len;
    }

    return 0;
}

static int ram_flush(void) {
    /* No-op for RAM storage */
    return 0;
}

/* Static ops structure */
static const user_store_nv_ops_t g_ram_ops = {
    .read = ram_read,
    .write = ram_write,
    .flush = ram_flush,
};

/* ============== Public API ============== */

const user_store_nv_ops_t *user_store_nv_ram_ops(void) {
    return &g_ram_ops;
}

void user_store_nv_ram_reset(void) {
    memset(g_ram_storage, 0, RAM_STORAGE_SIZE);
    g_ram_used = 0;
}

size_t user_store_nv_ram_usage(void) {
    return g_ram_used;
}
