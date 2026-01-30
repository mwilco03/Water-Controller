/*
 * Water Treatment Controller - RPC Connect Strategy Implementation
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "rpc_strategy.h"
#include "utils/logger.h"
#include "utils/time_utils.h"
#include <string.h>

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

/* ============== OpNum Wire Values ============== */

/* Map opnum_variant_t → RPC OpNum for the wire header. */
static const uint16_t opnum_wire_values[OPNUM_VARIANT_COUNT] = {
    [OPNUM_STANDARD] = 0,   /* RPC_OPNUM_CONNECT */
    [OPNUM_WRITE]    = 3,   /* RPC_OPNUM_WRITE   */
};

/* ============== Strategy Table ============== */

/*
 * 48-entry strategy table:
 *   5 dimensions: UUID(2) × NDR(2) × Slot(2) × Timing(3) × OpNum(2) = 48
 *
 * Layout:
 *   [ 0 .. 23]  OPNUM_STANDARD (OpNum=0, Connect)
 *     [ 0 ..  7]  DEFAULT timing, 8 wire-format combos
 *     [ 8 .. 15]  AGGRESSIVE timing
 *     [16 .. 23]  CONSERVATIVE timing
 *   [24 .. 47]  OPNUM_WRITE (OpNum=3, Write)
 *     [24 .. 31]  DEFAULT timing, 8 wire-format combos
 *     [32 .. 39]  AGGRESSIVE timing
 *     [40 .. 47]  CONSERVATIVE timing
 *
 * Within each timing group, wire formats are ordered:
 *   +0: as-stored, no NDR, full      +4: as-stored, no NDR, DAP
 *   +1: as-stored, +NDR, full        +5: as-stored, +NDR, DAP
 *   +2: swapped, no NDR, full        +6: swapped, no NDR, DAP
 *   +3: swapped, +NDR, full          +7: swapped, +NDR, DAP
 */

/* Helper macro — one strategy entry */
#define S(uuid, ndr, scope, timing_id, opn, desc) \
    { (uuid), (ndr), (scope), (timing_id), (opn), (desc) }

/* Wire-format block macro — 8 entries for one timing+opnum combo */
#define WIRE8(T, O, tname, oname) \
    S(UUID_WIRE_AS_STORED,   NDR_REQUEST_ABSENT,  SLOT_SCOPE_FULL,     T, O, tname " " oname ": as-stored, no NDR, full"), \
    S(UUID_WIRE_AS_STORED,   NDR_REQUEST_PRESENT, SLOT_SCOPE_FULL,     T, O, tname " " oname ": as-stored, +NDR, full"), \
    S(UUID_WIRE_SWAP_FIELDS, NDR_REQUEST_ABSENT,  SLOT_SCOPE_FULL,     T, O, tname " " oname ": swapped, no NDR, full"), \
    S(UUID_WIRE_SWAP_FIELDS, NDR_REQUEST_PRESENT, SLOT_SCOPE_FULL,     T, O, tname " " oname ": swapped, +NDR, full"), \
    S(UUID_WIRE_AS_STORED,   NDR_REQUEST_ABSENT,  SLOT_SCOPE_DAP_ONLY, T, O, tname " " oname ": as-stored, no NDR, DAP"), \
    S(UUID_WIRE_AS_STORED,   NDR_REQUEST_PRESENT, SLOT_SCOPE_DAP_ONLY, T, O, tname " " oname ": as-stored, +NDR, DAP"), \
    S(UUID_WIRE_SWAP_FIELDS, NDR_REQUEST_ABSENT,  SLOT_SCOPE_DAP_ONLY, T, O, tname " " oname ": swapped, no NDR, DAP"), \
    S(UUID_WIRE_SWAP_FIELDS, NDR_REQUEST_PRESENT, SLOT_SCOPE_DAP_ONLY, T, O, tname " " oname ": swapped, +NDR, DAP")

static const rpc_connect_strategy_t strategy_table[] = {
    /* === OpNum=0 (Connect) — indices 0..23 === */
    WIRE8(TIMING_DEFAULT,      OPNUM_STANDARD, "default",      "op0"),  /*  0.. 7 */
    WIRE8(TIMING_AGGRESSIVE,   OPNUM_STANDARD, "aggressive",   "op0"),  /*  8..15 */
    WIRE8(TIMING_CONSERVATIVE, OPNUM_STANDARD, "conservative", "op0"),  /* 16..23 */

    /* === OpNum=3 (Write) — indices 24..47 === */
    WIRE8(TIMING_DEFAULT,      OPNUM_WRITE,    "default",      "op3"),  /* 24..31 */
    WIRE8(TIMING_AGGRESSIVE,   OPNUM_WRITE,    "aggressive",   "op3"),  /* 32..39 */
    WIRE8(TIMING_CONSERVATIVE, OPNUM_WRITE,    "conservative", "op3"),  /* 40..47 */
};

#undef S
#undef WIRE8

#define STRATEGY_COUNT ((int)(sizeof(strategy_table) / sizeof(strategy_table[0])))

/* ============== Known Vendor IDs ============== */

#define VENDOR_SIEMENS       0x002A
#define VENDOR_HILSCHER      0x0051
#define VENDOR_PHOENIX       0x00B0
#define VENDOR_BECKHOFF      0x0120
#define VENDOR_WAGO          0x0297

/* ============== Public API ============== */

void rpc_strategy_init(rpc_strategy_state_t *state)
{
    memset(state, 0, sizeof(*state));
    state->total_strategies = STRATEGY_COUNT;
    state->last_success_index = -1;
}

const rpc_connect_strategy_t *rpc_strategy_current(const rpc_strategy_state_t *state)
{
    int idx = state->current_index;
    if (idx < 0 || idx >= STRATEGY_COUNT) {
        idx = 0;
    }
    return &strategy_table[idx];
}

void rpc_strategy_advance(rpc_strategy_state_t *state)
{
    state->current_index++;
    if (state->current_index >= STRATEGY_COUNT) {
        state->current_index = 0;
        state->cycle_count++;
        LOG_WARN("RPC strategy: completed cycle %d through all %d strategies — "
                 "restarting from beginning",
                 state->cycle_count, STRATEGY_COUNT);
    }

    const rpc_connect_strategy_t *next = &strategy_table[state->current_index];
    LOG_INFO("RPC strategy: advancing to [%d/%d] %s",
             state->current_index + 1, STRATEGY_COUNT, next->description);
}

void rpc_strategy_mark_success(rpc_strategy_state_t *state)
{
    const rpc_connect_strategy_t *s = rpc_strategy_current(state);
    LOG_INFO("RPC strategy: ** SUCCESS ** with [%d/%d] %s "
             "(total attempts: %d, cycles: %d)",
             state->current_index + 1, STRATEGY_COUNT,
             s->description,
             state->attempt_count, state->cycle_count);
    state->last_success_index = state->current_index;
}

void rpc_strategy_reset(rpc_strategy_state_t *state)
{
    int saved = state->last_success_index;

    if (saved >= 0 && saved < STRATEGY_COUNT) {
        state->current_index = saved;
        LOG_INFO("RPC strategy: reset — starting at last working [%d] %s",
                 saved + 1, strategy_table[saved].description);
    } else {
        state->current_index = 0;
        LOG_INFO("RPC strategy: reset — no prior success, starting from [1]");
    }

    state->attempt_count = 0;
    state->cycle_count = 0;
    state->first_attempt_ms = 0;
    state->last_attempt_ms = 0;
}

const rpc_connect_strategy_t *rpc_strategy_table(int *count)
{
    if (count) {
        *count = STRATEGY_COUNT;
    }
    return strategy_table;
}

void rpc_strategy_get_timing(timing_profile_t profile, timing_params_t *out)
{
    if (!out) return;

    if (profile < 0 || profile >= TIMING_PROFILE_COUNT) {
        profile = TIMING_DEFAULT;
    }

    *out = timing_profiles[profile];
}

uint16_t rpc_strategy_get_opnum(opnum_variant_t variant)
{
    if (variant < 0 || variant >= OPNUM_VARIANT_COUNT) {
        variant = OPNUM_STANDARD;
    }
    return opnum_wire_values[variant];
}

void rpc_strategy_apply_vendor_hint(rpc_strategy_state_t *state,
                                     uint16_t vendor_id)
{
    if (!state) return;

    /* Only apply vendor hints before first connection attempt or after
     * a full reset.  If we already have a known-working strategy, don't
     * override it. */
    if (state->last_success_index >= 0) {
        LOG_DEBUG("RPC strategy: vendor hint skipped — already have "
                  "working strategy [%d]",
                  state->last_success_index + 1);
        return;
    }

    int hint_index = -1;
    const char *vendor_name = "unknown";

    switch (vendor_id) {
    case VENDOR_SIEMENS:
        /* Siemens S7-1200/1500: swapped UUIDs, aggressive timing, full slots.
         * Strategy index 10 = aggressive group (8) + swapped/no-NDR/full (2). */
        hint_index = 10;
        vendor_name = "Siemens";
        break;

    case VENDOR_WAGO:
        /* WAGO: as-stored UUIDs, default timing, full slots.
         * Strategy index 0 = default baseline. */
        hint_index = 0;
        vendor_name = "WAGO";
        break;

    case VENDOR_HILSCHER:
        /* Hilscher netX/netLINK: swapped UUIDs, default timing, full slots.
         * Strategy index 2 = default group + swapped/no-NDR/full. */
        hint_index = 2;
        vendor_name = "Hilscher";
        break;

    case VENDOR_PHOENIX:
        /* Phoenix Contact: as-stored UUIDs, default timing.
         * Strategy index 0 = default baseline. */
        hint_index = 0;
        vendor_name = "Phoenix Contact";
        break;

    case VENDOR_BECKHOFF:
        /* Beckhoff TwinCAT: as-stored UUIDs, aggressive timing.
         * Strategy index 8 = aggressive group + as-stored/no-NDR/full. */
        hint_index = 8;
        vendor_name = "Beckhoff";
        break;

    default:
        /* Unknown vendor — start from beginning (default baseline). */
        break;
    }

    if (hint_index >= 0 && hint_index < STRATEGY_COUNT) {
        state->current_index = hint_index;
        LOG_INFO("RPC strategy: vendor hint applied — %s (0x%04X) → "
                 "starting at [%d/%d] %s",
                 vendor_name, vendor_id,
                 hint_index + 1, STRATEGY_COUNT,
                 strategy_table[hint_index].description);
    } else {
        LOG_INFO("RPC strategy: no vendor hint for vendor_id=0x%04X, "
                 "starting from default [1/%d]",
                 vendor_id, STRATEGY_COUNT);
    }
}

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
