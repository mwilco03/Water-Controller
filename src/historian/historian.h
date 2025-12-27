/*
 * Water Treatment Controller - Data Historian
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_HISTORIAN_H
#define WTC_HISTORIAN_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Historian handle */
typedef struct historian historian_t;

/* Historian configuration */
typedef struct {
    const char *database_path;
    int max_tags;
    int buffer_size;                /* In-memory buffer size per tag */
    uint32_t default_sample_rate_ms;
    float default_deadband;
    compression_t default_compression;
    int retention_days;             /* Data retention period */
    bool async_writes;              /* Use async database writes */
} historian_config_t;

/* Initialize historian */
wtc_result_t historian_init(historian_t **historian,
                             const historian_config_t *config);

/* Cleanup historian */
void historian_cleanup(historian_t *historian);

/* Start historian */
wtc_result_t historian_start(historian_t *historian);

/* Stop historian */
wtc_result_t historian_stop(historian_t *historian);

/* Set RTU registry for data access */
struct rtu_registry;
wtc_result_t historian_set_registry(historian_t *historian,
                                     struct rtu_registry *registry);

/* ============== Tag Management ============== */

/* Add historian tag */
wtc_result_t historian_add_tag(historian_t *historian,
                                const char *rtu_station,
                                int slot,
                                const char *tag_name,
                                uint32_t sample_rate_ms,
                                float deadband,
                                compression_t compression,
                                int *tag_id);

/* Remove historian tag */
wtc_result_t historian_remove_tag(historian_t *historian, int tag_id);

/* Get tag by ID */
wtc_result_t historian_get_tag(historian_t *historian,
                                int tag_id,
                                historian_tag_t *tag);

/* Find tag by station and slot */
wtc_result_t historian_find_tag(historian_t *historian,
                                 const char *rtu_station,
                                 int slot,
                                 int *tag_id);

/* List all tags */
wtc_result_t historian_list_tags(historian_t *historian,
                                  historian_tag_t **tags,
                                  int *count,
                                  int max_count);

/* Update tag settings */
wtc_result_t historian_update_tag(historian_t *historian,
                                   int tag_id,
                                   uint32_t sample_rate_ms,
                                   float deadband,
                                   compression_t compression);

/* ============== Data Recording ============== */

/* Record a sample manually */
wtc_result_t historian_record_sample(historian_t *historian,
                                      int tag_id,
                                      uint64_t timestamp_ms,
                                      float value,
                                      uint8_t quality);

/* Process (collect data from RTUs) */
wtc_result_t historian_process(historian_t *historian);

/* Flush buffers to database */
wtc_result_t historian_flush(historian_t *historian);

/* ============== Data Query ============== */

/* Query data for a single tag
 * HIST-C2 fix: Returns copies to caller-provided array instead of pointers
 * to avoid dangling reference issues with ring buffer
 */
wtc_result_t historian_query(historian_t *historian,
                              int tag_id,
                              uint64_t start_time_ms,
                              uint64_t end_time_ms,
                              historian_sample_t *samples_out,
                              int *count,
                              int max_count);

/* Query data for multiple tags */
typedef struct {
    int tag_id;
    historian_sample_t *samples;
    int count;
} historian_dataset_t;

wtc_result_t historian_query_multi(historian_t *historian,
                                    const int *tag_ids,
                                    int tag_count,
                                    uint64_t start_time_ms,
                                    uint64_t end_time_ms,
                                    historian_dataset_t *datasets);

/* Query aggregated data (min, max, avg over intervals) */
typedef struct {
    uint64_t timestamp_ms;
    float min;
    float max;
    float avg;
    int count;
} historian_aggregate_t;

wtc_result_t historian_query_aggregate(historian_t *historian,
                                        int tag_id,
                                        uint64_t start_time_ms,
                                        uint64_t end_time_ms,
                                        uint32_t interval_ms,
                                        historian_aggregate_t **aggregates,
                                        int *count,
                                        int max_count);

/* Get current (latest) value for a tag */
wtc_result_t historian_get_current(historian_t *historian,
                                    int tag_id,
                                    float *value,
                                    uint64_t *timestamp_ms,
                                    uint8_t *quality);

/* ============== Export/Import ============== */

/* Export data to CSV */
wtc_result_t historian_export_csv(historian_t *historian,
                                   const int *tag_ids,
                                   int tag_count,
                                   uint64_t start_time_ms,
                                   uint64_t end_time_ms,
                                   const char *filename);

/* Import data from CSV */
wtc_result_t historian_import_csv(historian_t *historian,
                                   const char *filename);

/* ============== Maintenance ============== */

/* Purge old data */
wtc_result_t historian_purge_old_data(historian_t *historian,
                                       int retention_days);

/* Get tag statistics */
wtc_result_t historian_get_tag_stats(historian_t *historian,
                                      int tag_id,
                                      uint64_t *total_samples,
                                      uint64_t *compressed_samples,
                                      float *compression_ratio,
                                      uint64_t *storage_bytes);

/* Get total statistics */
typedef struct {
    int total_tags;
    uint64_t total_samples;
    uint64_t samples_in_buffer;
    uint64_t storage_bytes;
    float avg_compression_ratio;
    uint64_t oldest_sample_ms;
    uint64_t newest_sample_ms;
} historian_stats_t;

wtc_result_t historian_get_stats(historian_t *historian,
                                  historian_stats_t *stats);

#ifdef __cplusplus
}
#endif

#endif /* WTC_HISTORIAN_H */
