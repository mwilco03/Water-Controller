/*
 * Water Treatment Controller - State Reconciliation Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "state_reconciliation.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <stdio.h>

/* Maximum tracked RTUs */
#define MAX_STATE_ENTRIES 256

/* CRC32 lookup table */
static uint32_t crc32_table[256];
static bool crc32_initialized = false;

/* Initialize CRC32 table */
static void init_crc32_table(void) {
    if (crc32_initialized) return;

    for (uint32_t i = 0; i < 256; i++) {
        uint32_t crc = i;
        for (int j = 0; j < 8; j++) {
            crc = (crc >> 1) ^ ((crc & 1) ? 0xEDB88320 : 0);
        }
        crc32_table[i] = crc;
    }
    crc32_initialized = true;
}

/* Compute CRC32 */
static uint32_t compute_crc32(const uint8_t *data, size_t len) {
    init_crc32_table();
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; i++) {
        crc = crc32_table[(crc ^ data[i]) & 0xFF] ^ (crc >> 8);
    }
    return crc ^ 0xFFFFFFFF;
}

/* State entry for a single RTU */
typedef struct {
    char station_name[WTC_MAX_STATION_NAME];
    desired_state_t state;
    uint64_t last_snapshot_ms;
    bool in_use;
} state_entry_t;

/* State reconciler structure */
struct state_reconciler {
    state_reconciler_config_t config;
    state_entry_t entries[MAX_STATE_ENTRIES];
    int entry_count;

    state_conflict_callback_t conflict_callback;
    void *callback_ctx;

    pthread_mutex_t lock;
};

/* Find or create state entry for RTU */
static state_entry_t *find_or_create_entry(state_reconciler_t *reconciler,
                                             const char *station_name) {
    /* First, look for existing entry */
    for (int i = 0; i < MAX_STATE_ENTRIES; i++) {
        if (reconciler->entries[i].in_use &&
            strcmp(reconciler->entries[i].station_name, station_name) == 0) {
            return &reconciler->entries[i];
        }
    }

    /* Create new entry */
    for (int i = 0; i < MAX_STATE_ENTRIES; i++) {
        if (!reconciler->entries[i].in_use) {
            state_entry_t *entry = &reconciler->entries[i];
            memset(entry, 0, sizeof(*entry));
            strncpy(entry->station_name, station_name,
                    sizeof(entry->station_name) - 1);
            desired_state_init(&entry->state, station_name);
            entry->in_use = true;
            reconciler->entry_count++;
            return entry;
        }
    }

    return NULL;
}

/* Find state entry for RTU */
static state_entry_t *find_entry(state_reconciler_t *reconciler,
                                   const char *station_name) {
    for (int i = 0; i < MAX_STATE_ENTRIES; i++) {
        if (reconciler->entries[i].in_use &&
            strcmp(reconciler->entries[i].station_name, station_name) == 0) {
            return &reconciler->entries[i];
        }
    }
    return NULL;
}

/* Public API */

wtc_result_t state_reconciler_init(state_reconciler_t **reconciler,
                                    const state_reconciler_config_t *config) {
    if (!reconciler) {
        return WTC_ERROR_INVALID_PARAM;
    }

    state_reconciler_t *rec = calloc(1, sizeof(state_reconciler_t));
    if (!rec) {
        return WTC_ERROR_NO_MEMORY;
    }

    if (config) {
        rec->config = *config;
    } else {
        rec->config.snapshot_interval_ms = 30000;  /* 30 seconds */
        rec->config.sync_timeout_ms = 5000;        /* 5 seconds */
        rec->config.persist_to_disk = true;
        strncpy(rec->config.persist_path, "/var/lib/wtc/state",
                sizeof(rec->config.persist_path) - 1);
        rec->config.auto_reconcile = true;
    }

    pthread_mutex_init(&rec->lock, NULL);
    init_crc32_table();

    *reconciler = rec;
    LOG_INFO("State reconciler initialized (snapshot_interval=%ums, persist=%s)",
             rec->config.snapshot_interval_ms,
             rec->config.persist_to_disk ? "true" : "false");

    return WTC_OK;
}

void state_reconciler_cleanup(state_reconciler_t *reconciler) {
    if (!reconciler) return;

    /* Snapshot all dirty states before cleanup */
    pthread_mutex_lock(&reconciler->lock);
    for (int i = 0; i < MAX_STATE_ENTRIES; i++) {
        if (reconciler->entries[i].in_use && reconciler->entries[i].state.dirty) {
            state_snapshot(reconciler, reconciler->entries[i].station_name);
        }
    }
    pthread_mutex_unlock(&reconciler->lock);

    pthread_mutex_destroy(&reconciler->lock);
    free(reconciler);
    LOG_DEBUG("State reconciler cleaned up");
}

void state_reconciler_set_conflict_callback(state_reconciler_t *reconciler,
                                             state_conflict_callback_t callback,
                                             void *ctx) {
    if (!reconciler) return;

    pthread_mutex_lock(&reconciler->lock);
    reconciler->conflict_callback = callback;
    reconciler->callback_ctx = ctx;
    pthread_mutex_unlock(&reconciler->lock);
}

wtc_result_t state_set_actuator(state_reconciler_t *reconciler,
                                 const char *station_name,
                                 int slot,
                                 actuator_cmd_t command,
                                 uint8_t pwm_duty,
                                 uint32_t epoch) {
    if (!reconciler || !station_name || slot < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&reconciler->lock);

    state_entry_t *entry = find_or_create_entry(reconciler, station_name);
    if (!entry) {
        pthread_mutex_unlock(&reconciler->lock);
        return WTC_ERROR_FULL;
    }

    desired_state_t *state = &entry->state;

    /* Find existing actuator or add new one */
    int idx = -1;
    for (int i = 0; i < state->actuator_count; i++) {
        if (state->actuators[i].slot == slot) {
            idx = i;
            break;
        }
    }

    if (idx < 0) {
        if (state->actuator_count >= MAX_DESIRED_ACTUATORS) {
            pthread_mutex_unlock(&reconciler->lock);
            return WTC_ERROR_FULL;
        }
        idx = state->actuator_count++;
    }

    /* Update state */
    state->actuators[idx].slot = slot;
    state->actuators[idx].command = command;
    state->actuators[idx].pwm_duty = pwm_duty;
    state->actuators[idx].set_time_ms = time_get_ms();
    state->actuators[idx].set_epoch = epoch;

    /* Update header */
    state->sequence++;
    state->timestamp_ms = time_get_ms();
    state->dirty = true;
    state->checksum = state_compute_checksum(state);

    LOG_DEBUG("State updated: %s slot=%d cmd=%d pwm=%d seq=%u",
              station_name, slot, command, pwm_duty, state->sequence);

    pthread_mutex_unlock(&reconciler->lock);
    return WTC_OK;
}

wtc_result_t state_set_pid_loop(state_reconciler_t *reconciler,
                                 const char *station_name,
                                 int loop_id,
                                 pid_mode_t mode,
                                 float setpoint) {
    if (!reconciler || !station_name || loop_id < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&reconciler->lock);

    state_entry_t *entry = find_or_create_entry(reconciler, station_name);
    if (!entry) {
        pthread_mutex_unlock(&reconciler->lock);
        return WTC_ERROR_FULL;
    }

    desired_state_t *state = &entry->state;

    /* Find existing loop or add new one */
    int idx = -1;
    for (int i = 0; i < state->pid_loop_count; i++) {
        if (state->pid_loops[i].loop_id == loop_id) {
            idx = i;
            break;
        }
    }

    if (idx < 0) {
        if (state->pid_loop_count >= WTC_MAX_PID_LOOPS) {
            pthread_mutex_unlock(&reconciler->lock);
            return WTC_ERROR_FULL;
        }
        idx = state->pid_loop_count++;
    }

    /* Update state */
    state->pid_loops[idx].loop_id = loop_id;
    state->pid_loops[idx].mode = mode;
    state->pid_loops[idx].setpoint = setpoint;
    state->pid_loops[idx].set_time_ms = time_get_ms();

    /* Update header */
    state->sequence++;
    state->timestamp_ms = time_get_ms();
    state->dirty = true;
    state->checksum = state_compute_checksum(state);

    pthread_mutex_unlock(&reconciler->lock);
    return WTC_OK;
}

wtc_result_t state_get_desired(state_reconciler_t *reconciler,
                                const char *station_name,
                                desired_state_t *state) {
    if (!reconciler || !station_name || !state) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&reconciler->lock);

    state_entry_t *entry = find_entry(reconciler, station_name);
    if (!entry) {
        pthread_mutex_unlock(&reconciler->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    desired_state_copy(state, &entry->state);

    pthread_mutex_unlock(&reconciler->lock);
    return WTC_OK;
}

uint32_t state_get_sequence(state_reconciler_t *reconciler,
                             const char *station_name) {
    if (!reconciler || !station_name) {
        return 0;
    }

    pthread_mutex_lock(&reconciler->lock);

    state_entry_t *entry = find_entry(reconciler, station_name);
    uint32_t seq = entry ? entry->state.sequence : 0;

    pthread_mutex_unlock(&reconciler->lock);
    return seq;
}

wtc_result_t state_snapshot(state_reconciler_t *reconciler,
                             const char *station_name) {
    if (!reconciler || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (!reconciler->config.persist_to_disk) {
        return WTC_OK;
    }

    pthread_mutex_lock(&reconciler->lock);

    state_entry_t *entry = find_entry(reconciler, station_name);
    if (!entry) {
        pthread_mutex_unlock(&reconciler->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    /* Build filename */
    char filename[512];
    snprintf(filename, sizeof(filename), "%s/%s.state",
             reconciler->config.persist_path, station_name);

    /* Update checksum before saving */
    entry->state.checksum = state_compute_checksum(&entry->state);

    /* Write to file */
    FILE *fp = fopen(filename, "wb");
    if (!fp) {
        LOG_WARN("Failed to open state file for writing: %s", filename);
        pthread_mutex_unlock(&reconciler->lock);
        return WTC_ERROR_IO;
    }

    size_t written = fwrite(&entry->state, sizeof(desired_state_t), 1, fp);
    fclose(fp);

    if (written != 1) {
        LOG_WARN("Failed to write state file: %s", filename);
        pthread_mutex_unlock(&reconciler->lock);
        return WTC_ERROR_IO;
    }

    entry->state.dirty = false;
    entry->last_snapshot_ms = time_get_ms();

    LOG_DEBUG("State snapshot saved: %s (seq=%u)", station_name, entry->state.sequence);

    pthread_mutex_unlock(&reconciler->lock);
    return WTC_OK;
}

wtc_result_t state_restore(state_reconciler_t *reconciler,
                            const char *station_name) {
    if (!reconciler || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Build filename */
    char filename[512];
    snprintf(filename, sizeof(filename), "%s/%s.state",
             reconciler->config.persist_path, station_name);

    FILE *fp = fopen(filename, "rb");
    if (!fp) {
        LOG_DEBUG("No persisted state found for %s", station_name);
        return WTC_ERROR_NOT_FOUND;
    }

    desired_state_t loaded_state;
    size_t read = fread(&loaded_state, sizeof(desired_state_t), 1, fp);
    fclose(fp);

    if (read != 1) {
        LOG_WARN("Failed to read state file: %s", filename);
        return WTC_ERROR_IO;
    }

    /* Validate checksum */
    if (!state_validate_checksum(&loaded_state)) {
        LOG_WARN("State file checksum invalid: %s", filename);
        return WTC_ERROR_PROTOCOL;
    }

    /* Validate version */
    if (loaded_state.version != STATE_RECONCILIATION_VERSION) {
        LOG_WARN("State file version mismatch: %s (got %u, expected %u)",
                 filename, loaded_state.version, STATE_RECONCILIATION_VERSION);
        return WTC_ERROR_PROTOCOL;
    }

    pthread_mutex_lock(&reconciler->lock);

    state_entry_t *entry = find_or_create_entry(reconciler, station_name);
    if (!entry) {
        pthread_mutex_unlock(&reconciler->lock);
        return WTC_ERROR_FULL;
    }

    desired_state_copy(&entry->state, &loaded_state);
    entry->state.dirty = false;

    LOG_INFO("State restored for %s (seq=%u, actuators=%d, pid_loops=%d)",
             station_name, entry->state.sequence,
             entry->state.actuator_count, entry->state.pid_loop_count);

    pthread_mutex_unlock(&reconciler->lock);
    return WTC_OK;
}

wtc_result_t state_reconcile(state_reconciler_t *reconciler,
                              const char *station_name,
                              const desired_state_t *rtu_actual_state,
                              reconciliation_result_t *result) {
    if (!reconciler || !station_name || !result) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint64_t start_ms = time_get_ms();
    memset(result, 0, sizeof(*result));

    pthread_mutex_lock(&reconciler->lock);

    state_entry_t *entry = find_entry(reconciler, station_name);
    if (!entry) {
        pthread_mutex_unlock(&reconciler->lock);
        result->success = true;  /* No state to reconcile */
        return WTC_OK;
    }

    desired_state_t *desired = &entry->state;

    /* Compare actuator states */
    for (int i = 0; i < desired->actuator_count; i++) {
        const desired_actuator_state_t *ds = &desired->actuators[i];
        bool found = false;
        bool conflict = false;

        if (rtu_actual_state) {
            for (int j = 0; j < rtu_actual_state->actuator_count; j++) {
                const desired_actuator_state_t *rs = &rtu_actual_state->actuators[j];
                if (rs->slot == ds->slot) {
                    found = true;
                    if (rs->command != ds->command || rs->pwm_duty != ds->pwm_duty) {
                        conflict = true;
                        result->actuators_conflicted++;

                        /* Notify conflict callback */
                        if (reconciler->conflict_callback) {
                            reconciler->conflict_callback(station_name, ds->slot,
                                                           ds, rs,
                                                           reconciler->callback_ctx);
                        }
                    }
                    break;
                }
            }
        }

        if (!conflict) {
            result->actuators_synced++;
        }
    }

    /* Compare PID loop states */
    for (int i = 0; i < desired->pid_loop_count; i++) {
        const desired_pid_state_t *ds = &desired->pid_loops[i];
        bool conflict = false;

        if (rtu_actual_state) {
            for (int j = 0; j < rtu_actual_state->pid_loop_count; j++) {
                const desired_pid_state_t *rs = &rtu_actual_state->pid_loops[j];
                if (rs->loop_id == ds->loop_id) {
                    if (rs->mode != ds->mode || rs->setpoint != ds->setpoint) {
                        conflict = true;
                        result->pid_loops_conflicted++;
                    }
                    break;
                }
            }
        }

        if (!conflict) {
            result->pid_loops_synced++;
        }
    }

    result->reconcile_time_ms = time_get_ms() - start_ms;
    result->success = (result->actuators_conflicted == 0 &&
                       result->pid_loops_conflicted == 0);

    LOG_INFO("State reconciliation for %s: actuators=%d/%d synced, pid=%d/%d synced, %s",
             station_name,
             result->actuators_synced,
             result->actuators_synced + result->actuators_conflicted,
             result->pid_loops_synced,
             result->pid_loops_synced + result->pid_loops_conflicted,
             result->success ? "SUCCESS" : "CONFLICTS");

    pthread_mutex_unlock(&reconciler->lock);
    return WTC_OK;
}

wtc_result_t state_force_sync(state_reconciler_t *reconciler,
                               const char *station_name) {
    if (!reconciler || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&reconciler->lock);

    state_entry_t *entry = find_entry(reconciler, station_name);
    if (!entry) {
        pthread_mutex_unlock(&reconciler->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    /* Increment sequence to indicate forced sync */
    entry->state.sequence++;
    entry->state.timestamp_ms = time_get_ms();
    entry->state.dirty = true;

    LOG_INFO("Forcing state sync for %s (seq=%u)", station_name, entry->state.sequence);

    pthread_mutex_unlock(&reconciler->lock);
    return WTC_OK;
}

wtc_result_t state_accept_rtu_state(state_reconciler_t *reconciler,
                                     const char *station_name,
                                     const desired_state_t *rtu_state) {
    if (!reconciler || !station_name || !rtu_state) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&reconciler->lock);

    state_entry_t *entry = find_or_create_entry(reconciler, station_name);
    if (!entry) {
        pthread_mutex_unlock(&reconciler->lock);
        return WTC_ERROR_FULL;
    }

    /* Copy RTU state as new desired state */
    desired_state_copy(&entry->state, rtu_state);
    entry->state.sequence++;  /* Increment sequence */
    entry->state.timestamp_ms = time_get_ms();
    entry->state.dirty = true;
    entry->state.checksum = state_compute_checksum(&entry->state);

    LOG_INFO("Accepted RTU state as desired for %s (seq=%u)",
             station_name, entry->state.sequence);

    pthread_mutex_unlock(&reconciler->lock);
    return WTC_OK;
}

bool state_validate_checksum(const desired_state_t *state) {
    if (!state) return false;

    uint32_t expected = state->checksum;
    uint32_t computed = state_compute_checksum(state);
    return expected == computed;
}

uint32_t state_compute_checksum(const desired_state_t *state) {
    if (!state) return 0;

    /* Compute CRC32 excluding the checksum field itself */
    desired_state_t temp;
    memcpy(&temp, state, sizeof(temp));
    temp.checksum = 0;

    return compute_crc32((const uint8_t *)&temp, sizeof(temp));
}

bool state_is_stale(const desired_state_t *state, uint64_t threshold_ms) {
    if (!state || !state->valid) return true;

    uint64_t age = time_get_ms() - state->timestamp_ms;
    return age > threshold_ms;
}

void desired_state_init(desired_state_t *state, const char *station_name) {
    if (!state) return;

    memset(state, 0, sizeof(*state));
    state->version = STATE_RECONCILIATION_VERSION;
    state->sequence = 1;
    state->timestamp_ms = time_get_ms();
    if (station_name) {
        strncpy(state->station_name, station_name,
                sizeof(state->station_name) - 1);
    }
    state->valid = true;
    state->checksum = state_compute_checksum(state);
}

void desired_state_copy(desired_state_t *dst, const desired_state_t *src) {
    if (!dst || !src) return;
    memcpy(dst, src, sizeof(*dst));
}

void desired_state_print(const desired_state_t *state) {
    if (!state) return;

    LOG_DEBUG("=== Desired State: %s ===", state->station_name);
    LOG_DEBUG("  Version: %u, Sequence: %u", state->version, state->sequence);
    LOG_DEBUG("  Timestamp: %lu ms", (unsigned long)state->timestamp_ms);
    LOG_DEBUG("  Actuators: %d", state->actuator_count);
    for (int i = 0; i < state->actuator_count; i++) {
        LOG_DEBUG("    [%d] slot=%d cmd=%d pwm=%d epoch=%u",
                  i, state->actuators[i].slot, state->actuators[i].command,
                  state->actuators[i].pwm_duty, state->actuators[i].set_epoch);
    }
    LOG_DEBUG("  PID Loops: %d", state->pid_loop_count);
    for (int i = 0; i < state->pid_loop_count; i++) {
        LOG_DEBUG("    [%d] loop=%d mode=%d sp=%.2f",
                  i, state->pid_loops[i].loop_id, state->pid_loops[i].mode,
                  state->pid_loops[i].setpoint);
    }
}
