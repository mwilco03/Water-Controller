/*
 * Water Treatment Controller - RPC Connect Strategy System
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Progressive fallback strategies for PROFINET Connect Request wire format
 * variations. Different RTU firmware versions may expect different UUID
 * encodings, NDR header presence, slot configurations, and timing parameters.
 *
 * PROFINET Communication Resiliency Mandate:
 * - Always attempt communication — never refuse to try
 * - Never stop after first failure — retry with progressive fallbacks
 * - Retries are stateful and adaptive, not blind repeats
 * - Full transparency — log every attempt, format change, and response
 * - Compatibility over ideology — non-standard formats are valid if they work
 */

#ifndef WTC_RPC_STRATEGY_H
#define WTC_RPC_STRATEGY_H

#include "types.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* UUID wire encoding mode.
 *
 * DCE-RPC with drep=0x10 (LE) specifies that UUID fields time_low,
 * time_mid, and time_hi_and_version are stored in little-endian byte
 * order, while clock_seq and node remain in big-endian (network) order.
 *
 * AS_STORED copies UUIDs byte-for-byte from their C storage.
 * SWAP_FIELDS toggles the endianness of the first 3 UUID fields.
 */
typedef enum {
    UUID_WIRE_AS_STORED = 0,
    UUID_WIRE_SWAP_FIELDS = 1,
} uuid_wire_format_t;

/* NDR header presence in Connect Request.
 *
 * Some PROFINET stacks expect a 20-byte NDR header (ArgsMaximum,
 * ArgsLength, MaxCount, Offset, ActualCount) between the RPC header
 * and the first PNIO block.  Others parse blocks directly.
 */
typedef enum {
    NDR_REQUEST_ABSENT = 0,
    NDR_REQUEST_PRESENT = 1,
} ndr_request_mode_t;

/* Slot configuration scope.
 *
 * FULL sends all configured slots (DAP + sensors + actuators).
 * DAP_ONLY sends only slot 0 (Device Access Point) for a minimal
 * handshake that rules out slot mismatch as the failure cause.
 */
typedef enum {
    SLOT_SCOPE_FULL = 0,
    SLOT_SCOPE_DAP_ONLY = 1,
} slot_scope_t;

/* RPC OpNum variant for Connect Request.
 *
 * IEC 61158-6 defines OpNum=0 for Connect.  However, some non-standard
 * PROFINET stacks may interpret or route the request differently based
 * on the operation number.  The pcap-observed historical bug (commit
 * 18b657d) showed that wrong opnum causes silent failures — so trying
 * alternative opnums can reveal firmware-specific expectations.
 *
 * STANDARD:  OpNum 0 (Connect per IEC 61158-6)
 * WRITE:     OpNum 3 (Write — some stacks accept connect-via-write)
 */
typedef enum {
    OPNUM_STANDARD = 0,
    OPNUM_WRITE    = 1,
    OPNUM_VARIANT_COUNT = 2,
} opnum_variant_t;

/* Timing profile for IOCR and Alarm CR parameters.
 *
 * Different PROFINET devices expect different timing parameters.
 * The profile selects a coherent set of values:
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

/* Resolved timing values for IOCR and Alarm CR blocks.
 *
 * These are applied to the connect request by rpc_connect_with_strategy().
 * The values are determined by the timing_profile_t of the strategy.
 */
typedef struct {
    uint16_t send_clock_factor;   /* Base cycle: N × 31.25µs (32=1ms) */
    uint16_t reduction_ratio;     /* Data update interval = SCF × RR × 31.25µs */
    uint16_t watchdog_factor;     /* Watchdog timeout = WD × RR × SCF × 31.25µs */
    uint16_t data_hold_factor;    /* Data hold = DHF × RR × SCF × 31.25µs */
    uint16_t rta_timeout_factor;  /* Alarm timeout = RTA × 100ms */
    uint16_t rta_retries;         /* Alarm retransmission attempts */
} timing_params_t;

/* Single connect strategy definition */
typedef struct {
    uuid_wire_format_t uuid_format;
    ndr_request_mode_t ndr_mode;
    slot_scope_t slot_scope;
    timing_profile_t timing;
    opnum_variant_t opnum;
    const char *description;
} rpc_connect_strategy_t;

/* Maximum strategies: 8 wire formats × 3 timing profiles × 2 opnum = 48 */
#define RPC_MAX_STRATEGIES 48

/* Strategy iteration state — persists across ABORT recovery cycles */
typedef struct {
    int current_index;
    int total_strategies;
    int last_success_index;     /* -1 if no strategy has ever succeeded */
    int attempt_count;          /* cumulative attempts this session */
    int cycle_count;            /* full rotations through strategy list */
    uint64_t first_attempt_ms;
    uint64_t last_attempt_ms;
} rpc_strategy_state_t;

/* Initialize strategy state to defaults */
void rpc_strategy_init(rpc_strategy_state_t *state);

/* Get the strategy to try next */
const rpc_connect_strategy_t *rpc_strategy_current(const rpc_strategy_state_t *state);

/* Advance to next strategy after a failed attempt */
void rpc_strategy_advance(rpc_strategy_state_t *state);

/* Record that the current strategy succeeded */
void rpc_strategy_mark_success(rpc_strategy_state_t *state);

/* Reset state for a new reconnection session (preserves last_success_index) */
void rpc_strategy_reset(rpc_strategy_state_t *state);

/* Access the full strategy table */
const rpc_connect_strategy_t *rpc_strategy_table(int *count);

/**
 * @brief Resolve timing profile to concrete parameter values.
 *
 * @param[in]  profile  Timing profile enum
 * @param[out] out      Filled timing parameters
 */
void rpc_strategy_get_timing(timing_profile_t profile, timing_params_t *out);

/**
 * @brief Resolve opnum variant to the wire-value for the RPC header.
 *
 * @param[in] variant  Opnum variant enum
 * @return uint16_t    RPC OpNum value for the header
 */
uint16_t rpc_strategy_get_opnum(opnum_variant_t variant);

/**
 * @brief Apply vendor hint to reorder strategy starting point.
 *
 * Uses the DCP-discovered vendor_id to jump to the most likely
 * working strategy for that vendor's PROFINET stack, avoiding a
 * full sequential search on every connection.
 *
 * Known vendor preferences:
 *   Siemens  (0x002A) — swapped UUIDs, aggressive timing
 *   WAGO     (0x0297) — as-stored UUIDs, default timing
 *   Hilscher (0x0051) — swapped UUIDs, default timing
 *   Phoenix  (0x00B0) — as-stored UUIDs, default timing
 *   Beckhoff (0x0120) — as-stored UUIDs, aggressive timing
 *
 * Unknown vendors start at strategy 0 (baseline).
 *
 * @param[in,out] state     Strategy state to reorder
 * @param[in]     vendor_id DCP-discovered vendor ID
 */
void rpc_strategy_apply_vendor_hint(rpc_strategy_state_t *state,
                                     uint16_t vendor_id);

/* Swap first 3 UUID fields in-place (toggles BE ↔ LE wire encoding).
 * Fields swapped:  time_low (bytes 0-3), time_mid (4-5), time_hi (6-7).
 * Fields kept:     clock_seq (8-9), node (10-15). */
void uuid_swap_fields(uint8_t *uuid);

#ifdef __cplusplus
}
#endif

#endif /* WTC_RPC_STRATEGY_H */
