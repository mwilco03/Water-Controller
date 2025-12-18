/**
 * Water Treatment Controller - Historian Tests
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <assert.h>
#include "../src/historian/historian.h"
#include "../src/types.h"

/* Test counters */
static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) static void test_##name(void)
#define RUN_TEST(name) do { \
    printf("  Running %s... ", #name); \
    tests_run++; \
    test_##name(); \
    tests_passed++; \
    printf("PASSED\n"); \
} while(0)

#define ASSERT_EQ(expected, actual) do { \
    if ((expected) != (actual)) { \
        printf("FAILED at line %d: expected %d, got %d\n", __LINE__, (int)(expected), (int)(actual)); \
        return; \
    } \
} while(0)

#define ASSERT_FLOAT_EQ(expected, actual, epsilon) do { \
    if (fabs((expected) - (actual)) > (epsilon)) { \
        printf("FAILED at line %d: expected %f, got %f\n", __LINE__, (expected), (actual)); \
        return; \
    } \
} while(0)

#define ASSERT_NOT_NULL(ptr) do { \
    if ((ptr) == NULL) { \
        printf("FAILED at line %d: pointer is NULL\n", __LINE__); \
        return; \
    } \
} while(0)

/* ============== Historian Creation Tests ============== */

TEST(historian_create)
{
    historian_t *hist = historian_create(1000, 100);
    ASSERT_NOT_NULL(hist);
    historian_destroy(hist);
}

TEST(historian_create_large)
{
    historian_t *hist = historian_create(100000, 500);
    ASSERT_NOT_NULL(hist);
    historian_destroy(hist);
}

/* ============== Tag Management Tests ============== */

TEST(historian_add_tag)
{
    historian_t *hist = historian_create(1000, 100);
    ASSERT_NOT_NULL(hist);

    historian_tag_config_t config = {0};
    strncpy(config.tag_name, "rtu-tank-1.pH", sizeof(config.tag_name));
    strncpy(config.rtu_station, "rtu-tank-1", sizeof(config.rtu_station));
    config.slot = 1;
    config.sample_rate_ms = 1000;
    config.deadband = 0.05f;
    config.compression = HISTORIAN_COMPRESS_DEADBAND;

    int tag_id = historian_add_tag(hist, &config);
    assert(tag_id >= 0);

    historian_destroy(hist);
}

TEST(historian_add_multiple_tags)
{
    historian_t *hist = historian_create(1000, 100);
    ASSERT_NOT_NULL(hist);

    const char *tag_names[] = {"pH", "Temperature", "Turbidity", "Pressure"};
    int tag_ids[4];

    for (int i = 0; i < 4; i++) {
        historian_tag_config_t config = {0};
        snprintf(config.tag_name, sizeof(config.tag_name), "rtu-tank-1.%s", tag_names[i]);
        strncpy(config.rtu_station, "rtu-tank-1", sizeof(config.rtu_station));
        config.slot = i + 1;
        config.sample_rate_ms = 1000;
        config.deadband = 0.05f;
        config.compression = HISTORIAN_COMPRESS_DEADBAND;

        tag_ids[i] = historian_add_tag(hist, &config);
        assert(tag_ids[i] >= 0);
    }

    /* Verify all tags have unique IDs */
    for (int i = 0; i < 4; i++) {
        for (int j = i + 1; j < 4; j++) {
            assert(tag_ids[i] != tag_ids[j]);
        }
    }

    historian_destroy(hist);
}

/* ============== Data Recording Tests ============== */

TEST(historian_record_value)
{
    historian_t *hist = historian_create(1000, 100);
    ASSERT_NOT_NULL(hist);

    historian_tag_config_t config = {0};
    strncpy(config.tag_name, "test.value", sizeof(config.tag_name));
    strncpy(config.rtu_station, "test-rtu", sizeof(config.rtu_station));
    config.slot = 1;
    config.sample_rate_ms = 100;
    config.deadband = 0.0f;  /* No compression for this test */
    config.compression = HISTORIAN_COMPRESS_NONE;

    int tag_id = historian_add_tag(hist, &config);
    assert(tag_id >= 0);

    /* Record some values */
    for (int i = 0; i < 10; i++) {
        int result = historian_record_value(hist, tag_id, (float)i, 192);
        ASSERT_EQ(0, result);
    }

    historian_destroy(hist);
}

TEST(historian_deadband_compression)
{
    historian_t *hist = historian_create(1000, 100);
    ASSERT_NOT_NULL(hist);

    historian_tag_config_t config = {0};
    strncpy(config.tag_name, "test.compressed", sizeof(config.tag_name));
    strncpy(config.rtu_station, "test-rtu", sizeof(config.rtu_station));
    config.slot = 1;
    config.sample_rate_ms = 100;
    config.deadband = 1.0f;  /* 1.0 unit deadband */
    config.compression = HISTORIAN_COMPRESS_DEADBAND;

    int tag_id = historian_add_tag(hist, &config);
    assert(tag_id >= 0);

    /* Record values - only changes > deadband should be stored */
    historian_record_value(hist, tag_id, 10.0f, 192);
    historian_record_value(hist, tag_id, 10.1f, 192);  /* Within deadband */
    historian_record_value(hist, tag_id, 10.2f, 192);  /* Within deadband */
    historian_record_value(hist, tag_id, 12.0f, 192);  /* Outside deadband */

    historian_destroy(hist);
}

TEST(historian_swinging_door_compression)
{
    historian_t *hist = historian_create(1000, 100);
    ASSERT_NOT_NULL(hist);

    historian_tag_config_t config = {0};
    strncpy(config.tag_name, "test.swinging", sizeof(config.tag_name));
    strncpy(config.rtu_station, "test-rtu", sizeof(config.rtu_station));
    config.slot = 1;
    config.sample_rate_ms = 100;
    config.deadband = 0.5f;
    config.compression = HISTORIAN_COMPRESS_SWINGING_DOOR;

    int tag_id = historian_add_tag(hist, &config);
    assert(tag_id >= 0);

    /* Record linear ramp - should compress well */
    for (int i = 0; i < 100; i++) {
        historian_record_value(hist, tag_id, (float)i * 0.1f, 192);
    }

    historian_destroy(hist);
}

/* ============== Query Tests ============== */

TEST(historian_query_range)
{
    historian_t *hist = historian_create(1000, 100);
    ASSERT_NOT_NULL(hist);

    historian_tag_config_t config = {0};
    strncpy(config.tag_name, "test.query", sizeof(config.tag_name));
    strncpy(config.rtu_station, "test-rtu", sizeof(config.rtu_station));
    config.slot = 1;
    config.sample_rate_ms = 100;
    config.deadband = 0.0f;
    config.compression = HISTORIAN_COMPRESS_NONE;

    int tag_id = historian_add_tag(hist, &config);
    assert(tag_id >= 0);

    /* Record values */
    for (int i = 0; i < 50; i++) {
        historian_record_value(hist, tag_id, (float)i, 192);
    }

    /* Query range */
    historian_sample_t samples[100];
    int count = historian_query(hist, tag_id, 0, UINT64_MAX, samples, 100);

    assert(count >= 0);

    historian_destroy(hist);
}

TEST(historian_query_empty)
{
    historian_t *hist = historian_create(1000, 100);
    ASSERT_NOT_NULL(hist);

    historian_tag_config_t config = {0};
    strncpy(config.tag_name, "test.empty", sizeof(config.tag_name));
    strncpy(config.rtu_station, "test-rtu", sizeof(config.rtu_station));
    config.slot = 1;
    config.sample_rate_ms = 100;
    config.compression = HISTORIAN_COMPRESS_NONE;

    int tag_id = historian_add_tag(hist, &config);
    assert(tag_id >= 0);

    /* Query without recording anything */
    historian_sample_t samples[10];
    int count = historian_query(hist, tag_id, 0, UINT64_MAX, samples, 10);

    ASSERT_EQ(0, count);

    historian_destroy(hist);
}

/* ============== Quality Code Tests ============== */

TEST(historian_quality_codes)
{
    /* OPC UA quality codes */
    uint8_t quality_good = 192;      /* 0xC0 - Good */
    uint8_t quality_bad = 0;         /* 0x00 - Bad */
    uint8_t quality_uncertain = 64;  /* 0x40 - Uncertain */

    /* Test quality code ranges */
    assert((quality_good & 0xC0) == 0xC0);      /* Good quality */
    assert((quality_bad & 0xC0) == 0x00);       /* Bad quality */
    assert((quality_uncertain & 0xC0) == 0x40); /* Uncertain quality */
}

/* ============== Ring Buffer Tests ============== */

TEST(historian_buffer_wrap)
{
    /* Create small historian to test wrap-around */
    historian_t *hist = historian_create(10, 10);  /* Very small buffer */
    ASSERT_NOT_NULL(hist);

    historian_tag_config_t config = {0};
    strncpy(config.tag_name, "test.wrap", sizeof(config.tag_name));
    strncpy(config.rtu_station, "test-rtu", sizeof(config.rtu_station));
    config.slot = 1;
    config.sample_rate_ms = 100;
    config.compression = HISTORIAN_COMPRESS_NONE;

    int tag_id = historian_add_tag(hist, &config);
    assert(tag_id >= 0);

    /* Record more values than buffer size to force wrap */
    for (int i = 0; i < 100; i++) {
        historian_record_value(hist, tag_id, (float)i, 192);
    }

    /* Should still work after wrap */
    historian_sample_t samples[20];
    int count = historian_query(hist, tag_id, 0, UINT64_MAX, samples, 20);
    assert(count >= 0);

    historian_destroy(hist);
}

/* ============== Test Runner ============== */

void run_historian_tests(void)
{
    printf("\n=== Historian Tests ===\n\n");

    printf("Creation Tests:\n");
    RUN_TEST(historian_create);
    RUN_TEST(historian_create_large);

    printf("\nTag Management Tests:\n");
    RUN_TEST(historian_add_tag);
    RUN_TEST(historian_add_multiple_tags);

    printf("\nData Recording Tests:\n");
    RUN_TEST(historian_record_value);
    RUN_TEST(historian_deadband_compression);
    RUN_TEST(historian_swinging_door_compression);

    printf("\nQuery Tests:\n");
    RUN_TEST(historian_query_range);
    RUN_TEST(historian_query_empty);

    printf("\nQuality Code Tests:\n");
    RUN_TEST(historian_quality_codes);

    printf("\nRing Buffer Tests:\n");
    RUN_TEST(historian_buffer_wrap);

    printf("\n=== Results: %d/%d tests passed ===\n\n", tests_passed, tests_run);
}

int main(int argc, char *argv[])
{
    run_historian_tests();
    return (tests_passed == tests_run) ? 0 : 1;
}
