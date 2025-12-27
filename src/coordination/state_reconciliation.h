/*
 * Water Treatment Controller - State Reconciliation
 * Implements formal desired-state contract between Controller and RTU
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * This module ensures convergence after power loss, network loss, or partial
 * restarts by maintaining a versioned desired-state model shared between
 * Controller and RTU.
 */

#ifndef WTC_STATE_RECONCILIATION_H
#define WTC_STATE_RECONCILIATION_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Maximum actuator states per RTU */
#define MAX_DESIRED_ACTUATORS 64

/* State reconciliation version - increment on breaking changes */
#define STATE_RECONCILIATION_VERSION 1

/* Desired actuator state */
typedef struct {
    int slot;                     /* Actuator slot number */
    actuator_cmd_t command;       /* Desired command (OFF, ON, PWM) */
    uint8_t pwm_duty;             /* Desired PWM duty cycle */
    bool forced;                  /* Operator forced override */
    uint64_t set_time_ms;         /* When this state was set */
    uint32_t set_epoch;           /* Authority epoch when set */
} desired_actuator_state_t;

/* Desired PID loop state */
typedef struct {
    int loop_id;                  /* PID loop ID */
    pid_mode_t mode;              /* Desired mode (OFF, MANUAL, AUTO) */
    float setpoint;               /* Desired setpoint */
    float manual_output;          /* Manual output value */
    uint64_t set_time_ms;         /* When this state was set */
} desired_pid_state_t;

/* Complete desired state for an RTU */
typedef struct {
    /* Header */
    uint32_t version;             /* State format version */
    uint32_t sequence;            /* Sequence number - incremented on each change */
    uint32_t checksum;            /* CRC32 checksum of state data */
    uint64_t timestamp_ms;        /* Last modification time */
    char station_name[WTC_MAX_STATION_NAME];

    /* Actuator states */
    desired_actuator_state_t actuators[MAX_DESIRED_ACTUATORS];
    int actuator_count;

    /* PID states */
    desired_pid_state_t pid_loops[WTC_MAX_PID_LOOPS];
    int pid_loop_count;

    /* Validity */
    bool valid;                   /* State has been initialized */
    bool dirty;                   /* Unsaved changes pending */
} desired_state_t;

/* Reconciliation result */
typedef struct {
    int actuators_synced;         /* Actuators synchronized */
    int actuators_conflicted;     /* Actuators with conflicts */
    int pid_loops_synced;         /* PID loops synchronized */
    int pid_loops_conflicted;     /* PID loops with conflicts */
    uint64_t reconcile_time_ms;   /* Time taken to reconcile */
    bool success;                 /* Reconciliation succeeded */
} reconciliation_result_t;

/* State reconciliation manager handle */
typedef struct state_reconciler state_reconciler_t;

/* State reconciler configuration */
typedef struct {
    uint32_t snapshot_interval_ms;    /* How often to snapshot state */
    uint32_t sync_timeout_ms;         /* Timeout for state sync with RTU */
    bool persist_to_disk;             /* Persist state to disk */
    char persist_path[256];           /* Path for persisted state */
    bool auto_reconcile;              /* Auto-reconcile on reconnection */
} state_reconciler_config_t;

/* Callback for state conflicts */
typedef void (*state_conflict_callback_t)(const char *station_name,
                                           int slot,
                                           const desired_actuator_state_t *controller_state,
                                           const desired_actuator_state_t *rtu_state,
                                           void *ctx);

/* Initialize state reconciler */
wtc_result_t state_reconciler_init(state_reconciler_t **reconciler,
                                    const state_reconciler_config_t *config);

/* Cleanup state reconciler */
void state_reconciler_cleanup(state_reconciler_t *reconciler);

/* Set conflict callback */
void state_reconciler_set_conflict_callback(state_reconciler_t *reconciler,
                                             state_conflict_callback_t callback,
                                             void *ctx);

/* ============== Desired State Management ============== */

/* Set desired actuator state (called on command) */
wtc_result_t state_set_actuator(state_reconciler_t *reconciler,
                                 const char *station_name,
                                 int slot,
                                 actuator_cmd_t command,
                                 uint8_t pwm_duty,
                                 uint32_t epoch);

/* Set desired PID loop state */
wtc_result_t state_set_pid_loop(state_reconciler_t *reconciler,
                                 const char *station_name,
                                 int loop_id,
                                 pid_mode_t mode,
                                 float setpoint);

/* Get desired state for RTU */
wtc_result_t state_get_desired(state_reconciler_t *reconciler,
                                const char *station_name,
                                desired_state_t *state);

/* Get current sequence number for RTU */
uint32_t state_get_sequence(state_reconciler_t *reconciler,
                             const char *station_name);

/* ============== State Persistence ============== */

/* Snapshot current state to disk */
wtc_result_t state_snapshot(state_reconciler_t *reconciler,
                             const char *station_name);

/* Load state from disk */
wtc_result_t state_restore(state_reconciler_t *reconciler,
                            const char *station_name);

/* ============== State Reconciliation ============== */

/* Reconcile controller state with RTU state after reconnection
 * 1. Reads actual state from RTU
 * 2. Compares with desired state
 * 3. Applies desired state to RTU or raises conflicts
 */
wtc_result_t state_reconcile(state_reconciler_t *reconciler,
                              const char *station_name,
                              const desired_state_t *rtu_actual_state,
                              reconciliation_result_t *result);

/* Force controller state to RTU (override conflicts) */
wtc_result_t state_force_sync(state_reconciler_t *reconciler,
                               const char *station_name);

/* Accept RTU state as new desired state */
wtc_result_t state_accept_rtu_state(state_reconciler_t *reconciler,
                                     const char *station_name,
                                     const desired_state_t *rtu_state);

/* ============== State Validation ============== */

/* Validate state checksum */
bool state_validate_checksum(const desired_state_t *state);

/* Compute state checksum */
uint32_t state_compute_checksum(const desired_state_t *state);

/* Check if state is stale (older than threshold) */
bool state_is_stale(const desired_state_t *state, uint64_t threshold_ms);

/* ============== Utilities ============== */

/* Initialize desired state with defaults */
void desired_state_init(desired_state_t *state, const char *station_name);

/* Copy desired state */
void desired_state_copy(desired_state_t *dst, const desired_state_t *src);

/* Print state for debugging */
void desired_state_print(const desired_state_t *state);

#ifdef __cplusplus
}
#endif

#endif /* WTC_STATE_RECONCILIATION_H */
