/**
 * @file user_store_nv_ram.h
 * @brief RAM-based NV storage backend for testing
 *
 * This module provides a RAM-only implementation of the user_store_nv_ops_t
 * interface for testing and development. Data is lost on restart.
 *
 * For production RTUs, implement a real backend using:
 * - EEPROM (I2C/SPI)
 * - SPI Flash (with wear leveling)
 * - Filesystem (if available)
 *
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef RTU_USER_STORE_NV_RAM_H
#define RTU_USER_STORE_NV_RAM_H

#include "user_store.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Get RAM-based NV operations
 *
 * Returns a pointer to a static user_store_nv_ops_t structure
 * that implements RAM-only storage.
 *
 * @return  Pointer to NV operations structure (never NULL)
 */
const user_store_nv_ops_t *user_store_nv_ram_ops(void);

/**
 * @brief Reset RAM storage to empty state
 *
 * Clears all stored data. Useful for testing.
 */
void user_store_nv_ram_reset(void);

/**
 * @brief Get current RAM storage usage
 *
 * @return  Number of bytes currently stored
 */
size_t user_store_nv_ram_usage(void);

#ifdef __cplusplus
}
#endif

#endif /* RTU_USER_STORE_NV_RAM_H */
