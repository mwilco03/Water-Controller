/*
 * Water Treatment Controller - RPC Timing & UUID Utilities
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Timing profiles for PROFINET IOCR and Alarm CR parameters,
 * and UUID field-swap for DCE-RPC DREP encoding.
 */

#ifndef WTC_RPC_STRATEGY_H
#define WTC_RPC_STRATEGY_H

#include "types.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Timing profile for IOCR and Alarm CR parameters.
 *
 *   DEFAULT      — standard parameters matching most devices
 *   AGGRESSIVE   — tight timing for Siemens-style stacks
 *   CONSERVATIVE — relaxed timing for legacy/slow devices
 */
typedef enum {
    TIMING_DEFAULT = 0,
    TIMING_AGGRESSIVE = 1,
    TIMING_CONSERVATIVE = 2,
    TIMING_PROFILE_COUNT = 3,
} timing_profile_t;

/* Resolved timing values for IOCR and Alarm CR blocks. */
typedef struct {
    uint16_t send_clock_factor;   /* Base cycle: N × 31.25µs (32=1ms) */
    uint16_t reduction_ratio;     /* Data update interval = SCF × RR × 31.25µs */
    uint16_t watchdog_factor;     /* Watchdog timeout = WD × RR × SCF × 31.25µs */
    uint16_t data_hold_factor;    /* Data hold = DHF × RR × SCF × 31.25µs */
    uint16_t rta_timeout_factor;  /* Alarm timeout = RTA × 100ms */
    uint16_t rta_retries;         /* Alarm retransmission attempts */
} timing_params_t;

/**
 * @brief Resolve timing profile to concrete parameter values.
 *
 * @param[in]  profile  Timing profile enum
 * @param[out] out      Filled timing parameters
 */
void rpc_strategy_get_timing(timing_profile_t profile, timing_params_t *out);

/* Swap first 3 UUID fields in-place (toggles BE ↔ LE wire encoding).
 * Fields swapped:  time_low (bytes 0-3), time_mid (4-5), time_hi (6-7).
 * Fields kept:     clock_seq (8-9), node (10-15). */
void uuid_swap_fields(uint8_t *uuid);

#ifdef __cplusplus
}
#endif

#endif /* WTC_RPC_STRATEGY_H */
