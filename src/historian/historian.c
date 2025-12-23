/*
 * Water Treatment Controller - Data Historian Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "historian.h"
#include "registry/rtu_registry.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <pthread.h>
#include <math.h>

/* Default buffer size */
#define DEFAULT_BUFFER_SIZE 1000

/* Tag buffer structure */
typedef struct {
    historian_sample_t *samples;
    int capacity;
    int count;
    int write_pos;
} tag_buffer_t;

/* Internal tag structure */
typedef struct {
    historian_tag_t info;
    tag_buffer_t buffer;
    float last_stored_value;
    uint64_t last_sample_time_ms;
    bool enabled;
} historian_tag_internal_t;

/* Historian structure */
struct historian {
    historian_config_t config;
    rtu_registry_t *registry;

    /* Tags */
    historian_tag_internal_t *tags;
    int tag_count;
    int tag_capacity;
    int next_tag_id;

    /* Thread management */
    pthread_t collect_thread;
    volatile bool running;
    pthread_mutex_t lock;

    /* Statistics */
    historian_stats_t stats;
};

/* Swinging door compression (reserved for batch compression) */
__attribute__((unused))
static bool swinging_door_compress(float last_value, float current_value,
                                    float next_value, float deadband) {
    if (deadband <= 0) return false;

    /* Calculate slopes */
    float slope1 = current_value - last_value;
    float slope2 = next_value - last_value;

    /* Check if point is within the swing */
    float error = fabsf(slope2 - slope1 * 2);
    return error <= deadband;
}

/* Initialize tag buffer */
static wtc_result_t init_tag_buffer(tag_buffer_t *buffer, int capacity) {
    buffer->samples = calloc(capacity, sizeof(historian_sample_t));
    if (!buffer->samples) {
        return WTC_ERROR_NO_MEMORY;
    }
    buffer->capacity = capacity;
    buffer->count = 0;
    buffer->write_pos = 0;
    return WTC_OK;
}

/* Free tag buffer */
static void free_tag_buffer(tag_buffer_t *buffer) {
    free(buffer->samples);
    buffer->samples = NULL;
    buffer->capacity = 0;
    buffer->count = 0;
}

/* Add sample to buffer */
static void buffer_add_sample(tag_buffer_t *buffer, const historian_sample_t *sample) {
    if (!buffer->samples) return;

    memcpy(&buffer->samples[buffer->write_pos], sample, sizeof(historian_sample_t));
    buffer->write_pos = (buffer->write_pos + 1) % buffer->capacity;
    if (buffer->count < buffer->capacity) {
        buffer->count++;
    }
}

/* Collection thread function */
static void *collect_thread_func(void *arg) {
    historian_t *historian = (historian_t *)arg;
    uint64_t next_collect_ms = time_get_monotonic_ms();

    LOG_DEBUG("Historian collection thread started");

    while (historian->running) {
        pthread_mutex_lock(&historian->lock);
        historian_process(historian);
        pthread_mutex_unlock(&historian->lock);

        /* Sleep until next collection */
        next_collect_ms += 100; /* 100ms base rate */
        uint64_t now = time_get_monotonic_ms();
        if (now < next_collect_ms) {
            time_sleep_ms(next_collect_ms - now);
        } else {
            next_collect_ms = now + 100;
        }
    }

    LOG_DEBUG("Historian collection thread stopped");
    return NULL;
}

/* Public functions */

wtc_result_t historian_init(historian_t **historian,
                             const historian_config_t *config) {
    if (!historian) {
        return WTC_ERROR_INVALID_PARAM;
    }

    historian_t *hist = calloc(1, sizeof(historian_t));
    if (!hist) {
        return WTC_ERROR_NO_MEMORY;
    }

    if (config) {
        memcpy(&hist->config, config, sizeof(historian_config_t));
    }

    /* Set defaults */
    if (hist->config.max_tags == 0) {
        hist->config.max_tags = WTC_MAX_HISTORIAN_TAGS;
    }
    if (hist->config.buffer_size == 0) {
        hist->config.buffer_size = DEFAULT_BUFFER_SIZE;
    }
    if (hist->config.default_sample_rate_ms == 0) {
        hist->config.default_sample_rate_ms = 1000;
    }
    if (hist->config.retention_days == 0) {
        hist->config.retention_days = 365;
    }

    /* Allocate tags array */
    hist->tag_capacity = hist->config.max_tags;
    hist->tags = calloc(hist->tag_capacity, sizeof(historian_tag_internal_t));
    if (!hist->tags) {
        free(hist);
        return WTC_ERROR_NO_MEMORY;
    }

    hist->next_tag_id = 1;
    pthread_mutex_init(&hist->lock, NULL);

    *historian = hist;
    LOG_INFO("Historian initialized (max_tags=%d, buffer_size=%d)",
             hist->config.max_tags, hist->config.buffer_size);
    return WTC_OK;
}

void historian_cleanup(historian_t *historian) {
    if (!historian) return;

    historian_stop(historian);

    /* Free tag buffers */
    for (int i = 0; i < historian->tag_count; i++) {
        free_tag_buffer(&historian->tags[i].buffer);
    }

    pthread_mutex_destroy(&historian->lock);
    free(historian->tags);
    free(historian);

    LOG_INFO("Historian cleaned up");
}

wtc_result_t historian_start(historian_t *historian) {
    if (!historian) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (historian->running) {
        return WTC_OK;
    }

    historian->running = true;

    if (pthread_create(&historian->collect_thread, NULL,
                       collect_thread_func, historian) != 0) {
        LOG_ERROR("Failed to create historian thread");
        historian->running = false;
        return WTC_ERROR;
    }

    LOG_INFO("Historian started");
    return WTC_OK;
}

wtc_result_t historian_stop(historian_t *historian) {
    if (!historian || !historian->running) {
        return WTC_OK;
    }

    historian->running = false;
    pthread_join(historian->collect_thread, NULL);

    /* Flush remaining data */
    historian_flush(historian);

    LOG_INFO("Historian stopped");
    return WTC_OK;
}

wtc_result_t historian_set_registry(historian_t *historian,
                                     struct rtu_registry *registry) {
    if (!historian) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&historian->lock);
    historian->registry = registry;
    pthread_mutex_unlock(&historian->lock);

    return WTC_OK;
}

wtc_result_t historian_add_tag(historian_t *historian,
                                const char *rtu_station,
                                int slot,
                                const char *tag_name,
                                uint32_t sample_rate_ms,
                                float deadband,
                                compression_t compression,
                                int *tag_id) {
    if (!historian || !rtu_station) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&historian->lock);

    if (historian->tag_count >= historian->tag_capacity) {
        pthread_mutex_unlock(&historian->lock);
        return WTC_ERROR_FULL;
    }

    /* Check for duplicate */
    for (int i = 0; i < historian->tag_count; i++) {
        if (strcmp(historian->tags[i].info.rtu_station, rtu_station) == 0 &&
            historian->tags[i].info.slot == slot) {
            pthread_mutex_unlock(&historian->lock);
            return WTC_ERROR_ALREADY_EXISTS;
        }
    }

    historian_tag_internal_t *tag = &historian->tags[historian->tag_count];
    memset(tag, 0, sizeof(historian_tag_internal_t));

    tag->info.tag_id = historian->next_tag_id++;
    strncpy(tag->info.rtu_station, rtu_station, WTC_MAX_STATION_NAME - 1);
    tag->info.slot = slot;

    if (tag_name) {
        strncpy(tag->info.tag_name, tag_name, sizeof(tag->info.tag_name) - 1);
    } else {
        snprintf(tag->info.tag_name, sizeof(tag->info.tag_name),
                 "%s.slot%d", rtu_station, slot);
    }

    tag->info.sample_rate_ms = sample_rate_ms > 0 ?
                               sample_rate_ms : historian->config.default_sample_rate_ms;
    tag->info.deadband = deadband >= 0 ?
                         deadband : historian->config.default_deadband;
    tag->info.compression = compression;

    /* Initialize buffer */
    wtc_result_t res = init_tag_buffer(&tag->buffer, historian->config.buffer_size);
    if (res != WTC_OK) {
        pthread_mutex_unlock(&historian->lock);
        return res;
    }

    tag->enabled = true;
    historian->tag_count++;

    if (tag_id) {
        *tag_id = tag->info.tag_id;
    }

    pthread_mutex_unlock(&historian->lock);

    LOG_INFO("Added historian tag %d: %s (rate=%u ms, deadband=%.2f)",
             tag->info.tag_id, tag->info.tag_name, tag->info.sample_rate_ms,
             tag->info.deadband);
    return WTC_OK;
}

wtc_result_t historian_remove_tag(historian_t *historian, int tag_id) {
    if (!historian) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&historian->lock);

    for (int i = 0; i < historian->tag_count; i++) {
        if (historian->tags[i].info.tag_id == tag_id) {
            free_tag_buffer(&historian->tags[i].buffer);

            /* Shift remaining tags */
            for (int j = i; j < historian->tag_count - 1; j++) {
                historian->tags[j] = historian->tags[j + 1];
            }
            historian->tag_count--;

            pthread_mutex_unlock(&historian->lock);
            LOG_INFO("Removed historian tag %d", tag_id);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&historian->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t historian_get_tag(historian_t *historian,
                                int tag_id,
                                historian_tag_t *tag) {
    if (!historian || !tag) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&historian->lock);

    for (int i = 0; i < historian->tag_count; i++) {
        if (historian->tags[i].info.tag_id == tag_id) {
            memcpy(tag, &historian->tags[i].info, sizeof(historian_tag_t));
            pthread_mutex_unlock(&historian->lock);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&historian->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t historian_record_sample(historian_t *historian,
                                      int tag_id,
                                      uint64_t timestamp_ms,
                                      float value,
                                      uint8_t quality) {
    if (!historian) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&historian->lock);

    /* Find tag */
    historian_tag_internal_t *tag = NULL;
    for (int i = 0; i < historian->tag_count; i++) {
        if (historian->tags[i].info.tag_id == tag_id) {
            tag = &historian->tags[i];
            break;
        }
    }

    if (!tag) {
        pthread_mutex_unlock(&historian->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    /* Create sample */
    historian_sample_t sample;
    sample.timestamp_ms = timestamp_ms;
    sample.tag_id = tag_id;
    sample.value = value;
    sample.quality = quality;

    /* Add to buffer */
    buffer_add_sample(&tag->buffer, &sample);

    /* Update tag stats */
    tag->info.total_samples++;
    tag->info.last_value = value;
    tag->info.last_sample_ms = timestamp_ms;
    tag->last_stored_value = value;

    historian->stats.total_samples++;

    pthread_mutex_unlock(&historian->lock);
    return WTC_OK;
}

wtc_result_t historian_process(historian_t *historian) {
    if (!historian || !historian->registry) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint64_t now_ms = time_get_ms();

    for (int i = 0; i < historian->tag_count; i++) {
        historian_tag_internal_t *tag = &historian->tags[i];
        if (!tag->enabled) continue;

        /* Check if it's time to sample */
        if (now_ms - tag->last_sample_time_ms < (uint64_t)tag->info.sample_rate_ms) {
            continue;
        }

        /* Read sensor value */
        sensor_data_t sensor;
        wtc_result_t res = rtu_registry_get_sensor(historian->registry,
                                                    tag->info.rtu_station,
                                                    tag->info.slot,
                                                    &sensor);

        if (res != WTC_OK) continue;

        /* Apply compression if enabled */
        bool store = true;
        if (tag->info.compression == COMPRESSION_DEADBAND) {
            float diff = fabsf(sensor.value - tag->last_stored_value);
            store = diff >= tag->info.deadband;
        } else if (tag->info.compression == COMPRESSION_SWINGING_DOOR) {
            /* Need previous values for swinging door */
            /* Simplified: use deadband for now */
            float diff = fabsf(sensor.value - tag->last_stored_value);
            store = diff >= tag->info.deadband;
        }

        if (store || tag->info.total_samples == 0) {
            /* Create sample */
            historian_sample_t sample;
            sample.timestamp_ms = now_ms;
            sample.tag_id = tag->info.tag_id;
            sample.value = sensor.value;
            sample.quality = sensor.status == IOPS_GOOD ? 192 : 0;

            /* Add to buffer */
            buffer_add_sample(&tag->buffer, &sample);

            /* Update tag stats */
            tag->info.total_samples++;
            tag->info.last_value = sensor.value;
            tag->info.last_sample_ms = now_ms;
            tag->last_stored_value = sensor.value;

            historian->stats.total_samples++;
        } else {
            tag->info.compressed_samples++;
        }

        tag->last_sample_time_ms = now_ms;

        /* Update compression ratio */
        if (tag->info.total_samples > 0) {
            tag->info.compression_ratio =
                (float)(tag->info.total_samples + tag->info.compressed_samples) /
                (float)tag->info.total_samples;
        }
    }

    historian->stats.samples_in_buffer = 0;
    for (int i = 0; i < historian->tag_count; i++) {
        historian->stats.samples_in_buffer += historian->tags[i].buffer.count;
    }

    return WTC_OK;
}

wtc_result_t historian_flush(historian_t *historian) {
    if (!historian) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* In a full implementation, this would write to database */
    LOG_DEBUG("Historian flush: %lu samples in buffers",
              historian->stats.samples_in_buffer);

    return WTC_OK;
}

wtc_result_t historian_query(historian_t *historian,
                              int tag_id,
                              uint64_t start_time_ms,
                              uint64_t end_time_ms,
                              historian_sample_t **samples,
                              int *count,
                              int max_count) {
    if (!historian || !samples || !count) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&historian->lock);

    /* Find tag */
    historian_tag_internal_t *tag = NULL;
    for (int i = 0; i < historian->tag_count; i++) {
        if (historian->tags[i].info.tag_id == tag_id) {
            tag = &historian->tags[i];
            break;
        }
    }

    if (!tag) {
        pthread_mutex_unlock(&historian->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    /* Query from buffer */
    int result_count = 0;
    for (int i = 0; i < tag->buffer.count && result_count < max_count; i++) {
        int idx = (tag->buffer.write_pos - tag->buffer.count + i + tag->buffer.capacity)
                  % tag->buffer.capacity;
        historian_sample_t *sample = &tag->buffer.samples[idx];

        if (sample->timestamp_ms >= start_time_ms &&
            sample->timestamp_ms <= end_time_ms) {
            samples[result_count++] = sample;
        }
    }

    *count = result_count;

    pthread_mutex_unlock(&historian->lock);
    return WTC_OK;
}

wtc_result_t historian_get_current(historian_t *historian,
                                    int tag_id,
                                    float *value,
                                    uint64_t *timestamp_ms,
                                    uint8_t *quality) {
    if (!historian || !value) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&historian->lock);

    for (int i = 0; i < historian->tag_count; i++) {
        if (historian->tags[i].info.tag_id == tag_id) {
            *value = historian->tags[i].info.last_value;
            if (timestamp_ms) {
                *timestamp_ms = historian->tags[i].info.last_sample_ms;
            }
            if (quality) {
                *quality = 192; /* Good quality */
            }
            pthread_mutex_unlock(&historian->lock);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&historian->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t historian_export_csv(historian_t *historian,
                                   const int *tag_ids,
                                   int tag_count,
                                   uint64_t start_time_ms,
                                   uint64_t end_time_ms,
                                   const char *filename) {
    if (!historian || !tag_ids || !filename) {
        return WTC_ERROR_INVALID_PARAM;
    }

    FILE *fp = fopen(filename, "w");
    if (!fp) {
        return WTC_ERROR_IO;
    }

    /* Write header */
    fprintf(fp, "timestamp");
    for (int i = 0; i < tag_count; i++) {
        historian_tag_t tag;
        if (historian_get_tag(historian, tag_ids[i], &tag) == WTC_OK) {
            fprintf(fp, ",%s", tag.tag_name);
        }
    }
    fprintf(fp, "\n");

    /* Write data (simplified - would need proper time alignment) */
    pthread_mutex_lock(&historian->lock);

    for (int t = 0; t < tag_count; t++) {
        for (int i = 0; i < historian->tag_count; i++) {
            if (historian->tags[i].info.tag_id == tag_ids[t]) {
                tag_buffer_t *buffer = &historian->tags[i].buffer;
                for (int j = 0; j < buffer->count; j++) {
                    int idx = (buffer->write_pos - buffer->count + j + buffer->capacity)
                              % buffer->capacity;
                    historian_sample_t *sample = &buffer->samples[idx];

                    if (sample->timestamp_ms >= start_time_ms &&
                        sample->timestamp_ms <= end_time_ms) {
                        char ts[32];
                        time_format_iso8601(sample->timestamp_ms, ts, sizeof(ts));
                        fprintf(fp, "%s,%.4f\n", ts, sample->value);
                    }
                }
                break;
            }
        }
    }

    pthread_mutex_unlock(&historian->lock);
    fclose(fp);

    LOG_INFO("Exported historian data to %s", filename);
    return WTC_OK;
}

wtc_result_t historian_get_stats(historian_t *historian, historian_stats_t *stats) {
    if (!historian || !stats) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&historian->lock);

    stats->total_tags = historian->tag_count;
    stats->total_samples = historian->stats.total_samples;
    stats->samples_in_buffer = historian->stats.samples_in_buffer;

    /* Calculate average compression ratio */
    float total_ratio = 0;
    for (int i = 0; i < historian->tag_count; i++) {
        total_ratio += historian->tags[i].info.compression_ratio;
    }
    stats->avg_compression_ratio = historian->tag_count > 0 ?
                                   total_ratio / historian->tag_count : 1.0f;

    pthread_mutex_unlock(&historian->lock);
    return WTC_OK;
}
