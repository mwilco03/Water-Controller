/*
 * Water Treatment Controller - RPC Connect Strategy System
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Progressive fallback strategies for PROFINET Connect Request wire format
 * variations. Different RTU firmware versions may expect different UUID
 * encodings, NDR header presence, and slot configurations.
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

/* Single connect strategy definition */
typedef struct {
    uuid_wire_format_t uuid_format;
    ndr_request_mode_t ndr_mode;
    slot_scope_t slot_scope;
    const char *description;
} rpc_connect_strategy_t;

/* Maximum strategies in the table */
#define RPC_MAX_STRATEGIES 8

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

/* Swap first 3 UUID fields in-place (toggles BE ↔ LE wire encoding).
 * Fields swapped:  time_low (bytes 0-3), time_mid (4-5), time_hi (6-7).
 * Fields kept:     clock_seq (8-9), node (10-15). */
void uuid_swap_fields(uint8_t *uuid);

#ifdef __cplusplus
}
#endif

#endif /* WTC_RPC_STRATEGY_H */
