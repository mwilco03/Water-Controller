/*
 * Water Treatment Controller - RPC Timing & UUID Utilities
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "rpc_strategy.h"

/* ============== Timing Profiles ============== */

/*
 * Concrete timing parameter sets for each profile.
 *
 * DEFAULT:       Standard IEC 61158-6 values.  1ms base, 32ms update,
 *                96ms watchdog, 10s alarm timeout, 3 retries.
 *
 * AGGRESSIVE:    Tight timing for modern Siemens-style stacks.
 *                1ms base, 16ms update, 16ms watchdog (= 1× reduction),
 *                6s alarm timeout, 3 retries.
 *
 * CONSERVATIVE:  Relaxed timing for legacy or slow-response devices.
 *                2ms base, 256ms update, 2.56s watchdog (10× reduction),
 *                20s alarm timeout, 5 retries.
 */
static const timing_params_t timing_profiles[TIMING_PROFILE_COUNT] = {
    [TIMING_DEFAULT] = {
        .send_clock_factor = 32,    /* 1ms base cycle */
        .reduction_ratio   = 32,    /* 32ms data update */
        .watchdog_factor   = 3,     /* 96ms watchdog */
        .data_hold_factor  = 3,     /* 96ms data hold */
        .rta_timeout_factor = 100,  /* 10s alarm timeout */
        .rta_retries       = 3,
    },
    [TIMING_AGGRESSIVE] = {
        .send_clock_factor = 32,    /* 1ms base cycle */
        .reduction_ratio   = 16,    /* 16ms data update */
        .watchdog_factor   = 1,     /* 16ms watchdog (tight) */
        .data_hold_factor  = 3,     /* 48ms data hold */
        .rta_timeout_factor = 60,   /* 6s alarm timeout */
        .rta_retries       = 3,
    },
    [TIMING_CONSERVATIVE] = {
        .send_clock_factor = 64,    /* 2ms base cycle */
        .reduction_ratio   = 128,   /* 256ms data update */
        .watchdog_factor   = 10,    /* 2.56s watchdog (very relaxed) */
        .data_hold_factor  = 5,     /* 1.28s data hold */
        .rta_timeout_factor = 200,  /* 20s alarm timeout */
        .rta_retries       = 5,
    },
};

void rpc_strategy_get_timing(timing_profile_t profile, timing_params_t *out)
{
    if (!out) return;

    if (profile < 0 || profile >= TIMING_PROFILE_COUNT) {
        profile = TIMING_DEFAULT;
    }

    *out = timing_profiles[profile];
}

/* ============== UUID Wire Encoding ============== */

void uuid_swap_fields(uint8_t *uuid)
{
    uint8_t tmp;

    /* time_low (bytes 0-3): reverse 4 bytes */
    tmp = uuid[0]; uuid[0] = uuid[3]; uuid[3] = tmp;
    tmp = uuid[1]; uuid[1] = uuid[2]; uuid[2] = tmp;

    /* time_mid (bytes 4-5): reverse 2 bytes */
    tmp = uuid[4]; uuid[4] = uuid[5]; uuid[5] = tmp;

    /* time_hi_and_version (bytes 6-7): reverse 2 bytes */
    tmp = uuid[6]; uuid[6] = uuid[7]; uuid[7] = tmp;

    /* clock_seq_hi, clock_seq_low, node (bytes 8-15): unchanged */
}
