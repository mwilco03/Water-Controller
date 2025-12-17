/*
 * Water Treatment Controller - Tag Manager
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_TAG_MANAGER_H
#define WTC_TAG_MANAGER_H

#include "types.h"
#include "compression.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Tag manager handle */
typedef struct tag_manager tag_manager_t;

/* Tag with runtime state */
typedef struct {
    historian_tag_t config;
    compression_state_t compression;
    uint64_t next_sample_time;
    bool enabled;
} managed_tag_t;

/* Initialize tag manager */
wtc_result_t tag_manager_init(tag_manager_t **mgr, int max_tags);

/* Cleanup tag manager */
void tag_manager_cleanup(tag_manager_t *mgr);

/* Add a tag */
wtc_result_t tag_manager_add(tag_manager_t *mgr, const historian_tag_t *tag);

/* Remove a tag */
wtc_result_t tag_manager_remove(tag_manager_t *mgr, int tag_id);

/* Get a tag by ID */
wtc_result_t tag_manager_get(tag_manager_t *mgr, int tag_id, managed_tag_t *tag);

/* Find tag by station and slot */
wtc_result_t tag_manager_find(tag_manager_t *mgr, const char *rtu_station, int slot,
                               int *tag_id);

/* Update tag configuration */
wtc_result_t tag_manager_update(tag_manager_t *mgr, int tag_id,
                                 uint32_t sample_rate_ms, float deadband,
                                 compression_t compression);

/* Enable/disable tag */
wtc_result_t tag_manager_enable(tag_manager_t *mgr, int tag_id, bool enabled);

/* List all tags */
wtc_result_t tag_manager_list(tag_manager_t *mgr, historian_tag_t **tags,
                               int *count, int max_count);

/* Get tag count */
int tag_manager_count(tag_manager_t *mgr);

/* Check if a tag needs sampling now */
bool tag_manager_needs_sample(tag_manager_t *mgr, int tag_id, uint64_t now_ms);

/* Record that a sample was taken */
void tag_manager_record_sample(tag_manager_t *mgr, int tag_id,
                                float value, uint64_t timestamp_ms);

/* Get tags that need sampling */
wtc_result_t tag_manager_get_due_tags(tag_manager_t *mgr, uint64_t now_ms,
                                       int *tag_ids, int *count, int max_count);

#ifdef __cplusplus
}
#endif

#endif /* WTC_TAG_MANAGER_H */
