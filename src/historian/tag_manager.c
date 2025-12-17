/*
 * Water Treatment Controller - Tag Manager Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "tag_manager.h"
#include "logger.h"
#include <stdlib.h>
#include <string.h>

#define LOG_TAG "TAG_MGR"

/* Tag manager structure */
struct tag_manager {
    managed_tag_t *tags;
    int tag_count;
    int max_tags;
    int next_tag_id;
};

/* Initialize tag manager */
wtc_result_t tag_manager_init(tag_manager_t **mgr, int max_tags) {
    if (!mgr || max_tags <= 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    tag_manager_t *tm = calloc(1, sizeof(tag_manager_t));
    if (!tm) {
        return WTC_ERROR_NO_MEMORY;
    }

    tm->tags = calloc(max_tags, sizeof(managed_tag_t));
    if (!tm->tags) {
        free(tm);
        return WTC_ERROR_NO_MEMORY;
    }

    tm->max_tags = max_tags;
    tm->tag_count = 0;
    tm->next_tag_id = 1;

    LOG_INFO(LOG_TAG, "Tag manager initialized (max %d tags)", max_tags);
    *mgr = tm;
    return WTC_OK;
}

/* Cleanup tag manager */
void tag_manager_cleanup(tag_manager_t *mgr) {
    if (!mgr) return;
    free(mgr->tags);
    free(mgr);
    LOG_INFO(LOG_TAG, "Tag manager cleaned up");
}

/* Add a tag */
wtc_result_t tag_manager_add(tag_manager_t *mgr, const historian_tag_t *tag) {
    if (!mgr || !tag) return WTC_ERROR_INVALID_PARAM;

    /* Check if tag already exists */
    for (int i = 0; i < mgr->tag_count; i++) {
        if (mgr->tags[i].config.tag_id == tag->tag_id) {
            /* Update existing */
            memcpy(&mgr->tags[i].config, tag, sizeof(historian_tag_t));
            compression_init(&mgr->tags[i].compression,
                             tag->compression, tag->deadband);
            LOG_DEBUG(LOG_TAG, "Updated tag %d: %s", tag->tag_id, tag->tag_name);
            return WTC_OK;
        }
    }

    if (mgr->tag_count >= mgr->max_tags) {
        LOG_ERROR(LOG_TAG, "Maximum tags reached (%d)", mgr->max_tags);
        return WTC_ERROR_FULL;
    }

    managed_tag_t *mt = &mgr->tags[mgr->tag_count];
    memcpy(&mt->config, tag, sizeof(historian_tag_t));

    /* Assign tag ID if not set */
    if (mt->config.tag_id == 0) {
        mt->config.tag_id = mgr->next_tag_id++;
    } else if (mt->config.tag_id >= mgr->next_tag_id) {
        mgr->next_tag_id = mt->config.tag_id + 1;
    }

    /* Initialize compression state */
    compression_init(&mt->compression, tag->compression, tag->deadband);

    mt->next_sample_time = 0;
    mt->enabled = true;
    mgr->tag_count++;

    LOG_INFO(LOG_TAG, "Added tag %d: %s (%s.%d)",
             mt->config.tag_id, mt->config.tag_name,
             mt->config.rtu_station, mt->config.slot);

    return WTC_OK;
}

/* Remove a tag */
wtc_result_t tag_manager_remove(tag_manager_t *mgr, int tag_id) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->tag_count; i++) {
        if (mgr->tags[i].config.tag_id == tag_id) {
            /* Shift remaining tags */
            memmove(&mgr->tags[i], &mgr->tags[i + 1],
                    (mgr->tag_count - i - 1) * sizeof(managed_tag_t));
            mgr->tag_count--;
            LOG_INFO(LOG_TAG, "Removed tag %d", tag_id);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Get a tag by ID */
wtc_result_t tag_manager_get(tag_manager_t *mgr, int tag_id, managed_tag_t *tag) {
    if (!mgr || !tag) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->tag_count; i++) {
        if (mgr->tags[i].config.tag_id == tag_id) {
            memcpy(tag, &mgr->tags[i], sizeof(managed_tag_t));
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Find tag by station and slot */
wtc_result_t tag_manager_find(tag_manager_t *mgr, const char *rtu_station, int slot,
                               int *tag_id) {
    if (!mgr || !rtu_station || !tag_id) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->tag_count; i++) {
        if (strcmp(mgr->tags[i].config.rtu_station, rtu_station) == 0 &&
            mgr->tags[i].config.slot == slot) {
            *tag_id = mgr->tags[i].config.tag_id;
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Update tag configuration */
wtc_result_t tag_manager_update(tag_manager_t *mgr, int tag_id,
                                 uint32_t sample_rate_ms, float deadband,
                                 compression_t compression) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->tag_count; i++) {
        if (mgr->tags[i].config.tag_id == tag_id) {
            mgr->tags[i].config.sample_rate_ms = sample_rate_ms;
            mgr->tags[i].config.deadband = deadband;
            mgr->tags[i].config.compression = compression;

            /* Reinitialize compression with new settings */
            compression_init(&mgr->tags[i].compression, compression, deadband);

            LOG_INFO(LOG_TAG, "Updated tag %d: rate=%ums, deadband=%.2f",
                     tag_id, sample_rate_ms, deadband);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* Enable/disable tag */
wtc_result_t tag_manager_enable(tag_manager_t *mgr, int tag_id, bool enabled) {
    if (!mgr) return WTC_ERROR_INVALID_PARAM;

    for (int i = 0; i < mgr->tag_count; i++) {
        if (mgr->tags[i].config.tag_id == tag_id) {
            mgr->tags[i].enabled = enabled;
            LOG_INFO(LOG_TAG, "%s tag %d", enabled ? "Enabled" : "Disabled", tag_id);
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

/* List all tags */
wtc_result_t tag_manager_list(tag_manager_t *mgr, historian_tag_t **tags,
                               int *count, int max_count) {
    if (!mgr || !tags || !count) return WTC_ERROR_INVALID_PARAM;

    int copy_count = mgr->tag_count;
    if (copy_count > max_count) copy_count = max_count;

    *tags = calloc(copy_count, sizeof(historian_tag_t));
    if (!*tags) {
        return WTC_ERROR_NO_MEMORY;
    }

    for (int i = 0; i < copy_count; i++) {
        memcpy(&(*tags)[i], &mgr->tags[i].config, sizeof(historian_tag_t));
    }

    *count = copy_count;
    return WTC_OK;
}

/* Get tag count */
int tag_manager_count(tag_manager_t *mgr) {
    return mgr ? mgr->tag_count : 0;
}

/* Check if a tag needs sampling now */
bool tag_manager_needs_sample(tag_manager_t *mgr, int tag_id, uint64_t now_ms) {
    if (!mgr) return false;

    for (int i = 0; i < mgr->tag_count; i++) {
        if (mgr->tags[i].config.tag_id == tag_id) {
            if (!mgr->tags[i].enabled) return false;
            return now_ms >= mgr->tags[i].next_sample_time;
        }
    }

    return false;
}

/* Record that a sample was taken */
void tag_manager_record_sample(tag_manager_t *mgr, int tag_id,
                                float value, uint64_t timestamp_ms) {
    if (!mgr) return;

    for (int i = 0; i < mgr->tag_count; i++) {
        if (mgr->tags[i].config.tag_id == tag_id) {
            mgr->tags[i].config.last_value = value;
            mgr->tags[i].config.last_sample_ms = timestamp_ms;
            mgr->tags[i].config.total_samples++;
            mgr->tags[i].next_sample_time = timestamp_ms +
                                             mgr->tags[i].config.sample_rate_ms;
            return;
        }
    }
}

/* Get tags that need sampling */
wtc_result_t tag_manager_get_due_tags(tag_manager_t *mgr, uint64_t now_ms,
                                       int *tag_ids, int *count, int max_count) {
    if (!mgr || !tag_ids || !count) return WTC_ERROR_INVALID_PARAM;

    *count = 0;

    for (int i = 0; i < mgr->tag_count && *count < max_count; i++) {
        if (mgr->tags[i].enabled && now_ms >= mgr->tags[i].next_sample_time) {
            tag_ids[(*count)++] = mgr->tags[i].config.tag_id;
        }
    }

    return WTC_OK;
}
