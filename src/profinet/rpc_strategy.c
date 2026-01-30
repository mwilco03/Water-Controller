/*
 * Water Treatment Controller - RPC Connect Strategy Implementation
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "rpc_strategy.h"
#include "utils/logger.h"
#include "utils/time_utils.h"
#include <string.h>

/*
 * Strategy table — ordered by empirical likelihood of success.
 *
 * Strategy 0 matches the wire format observed in known-working pcap
 * captures (big-endian UUIDs with drep=0x10, no NDR header in request,
 * full slot configuration).
 *
 * The remaining strategies progressively alter one dimension at a time
 * so that when a strategy succeeds, we know which format aspect mattered.
 */
static const rpc_connect_strategy_t strategy_table[] = {
    /* 0: Baseline — matches known working pcap */
    { UUID_WIRE_AS_STORED,   NDR_REQUEST_ABSENT,  SLOT_SCOPE_FULL,
      "as-stored UUIDs, no NDR, full slots" },

    /* 1: Add NDR header (some stacks require it in the request) */
    { UUID_WIRE_AS_STORED,   NDR_REQUEST_PRESENT, SLOT_SCOPE_FULL,
      "as-stored UUIDs, with NDR, full slots" },

    /* 2: Swap UUID fields to strict DCE-RPC LE encoding */
    { UUID_WIRE_SWAP_FIELDS, NDR_REQUEST_ABSENT,  SLOT_SCOPE_FULL,
      "swapped UUIDs, no NDR, full slots" },

    /* 3: Swapped UUIDs + NDR header */
    { UUID_WIRE_SWAP_FIELDS, NDR_REQUEST_PRESENT, SLOT_SCOPE_FULL,
      "swapped UUIDs, with NDR, full slots" },

    /* 4: DAP-only — rules out slot configuration mismatch */
    { UUID_WIRE_AS_STORED,   NDR_REQUEST_ABSENT,  SLOT_SCOPE_DAP_ONLY,
      "as-stored UUIDs, no NDR, DAP only" },

    /* 5: DAP-only + NDR header */
    { UUID_WIRE_AS_STORED,   NDR_REQUEST_PRESENT, SLOT_SCOPE_DAP_ONLY,
      "as-stored UUIDs, with NDR, DAP only" },

    /* 6: Swapped UUIDs, DAP-only */
    { UUID_WIRE_SWAP_FIELDS, NDR_REQUEST_ABSENT,  SLOT_SCOPE_DAP_ONLY,
      "swapped UUIDs, no NDR, DAP only" },

    /* 7: Swapped UUIDs, DAP-only, with NDR */
    { UUID_WIRE_SWAP_FIELDS, NDR_REQUEST_PRESENT, SLOT_SCOPE_DAP_ONLY,
      "swapped UUIDs, with NDR, DAP only" },
};

#define STRATEGY_COUNT ((int)(sizeof(strategy_table) / sizeof(strategy_table[0])))

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
