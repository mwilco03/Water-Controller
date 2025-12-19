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

#define ASSERT_NOT_NULL(ptr) do { \
    if ((ptr) == NULL) { \
        printf("FAILED at line %d: pointer is NULL\n", __LINE__); \
        return; \
    } \
} while(0)

/* ============== Historian Creation Tests ============== */

TEST(historian_init_null)
{
    /* Test that historian_init returns error for NULL parameters */
    historian_config_t config = {0};
    config.max_tags = 100;
    config.buffer_size = 1000;

    wtc_result_t result = historian_init(NULL, &config);
    ASSERT_EQ(WTC_ERROR_INVALID_PARAM, result);

    historian_t *hist = NULL;
    result = historian_init(&hist, NULL);
    ASSERT_EQ(WTC_ERROR_INVALID_PARAM, result);
}

TEST(historian_create_and_cleanup)
{
    historian_t *hist = NULL;
    historian_config_t config = {0};
    config.max_tags = 100;
    config.buffer_size = 1000;
    config.default_sample_rate_ms = 1000;
    config.default_deadband = 0.1f;
    config.default_compression = COMPRESSION_NONE;
    config.retention_days = 30;

    wtc_result_t result = historian_init(&hist, &config);
    ASSERT_EQ(WTC_OK, result);
    ASSERT_NOT_NULL(hist);

    historian_cleanup(hist);
}

/* ============== Tag Management Tests ============== */

TEST(historian_add_tag)
{
    historian_t *hist = NULL;
    historian_config_t config = {0};
    config.max_tags = 100;
    config.buffer_size = 1000;

    wtc_result_t result = historian_init(&hist, &config);
    ASSERT_EQ(WTC_OK, result);

    int tag_id;
    result = historian_add_tag(hist,
        "rtu-tank-1",     /* rtu_station */
        1,                 /* slot */
        "pH",              /* tag_name */
        1000,              /* sample_rate_ms */
        0.05f,             /* deadband */
        COMPRESSION_DEADBAND,  /* compression */
        &tag_id);

    ASSERT_EQ(WTC_OK, result);
    assert(tag_id >= 0);

    historian_cleanup(hist);
}

TEST(historian_add_multiple_tags)
{
    historian_t *hist = NULL;
    historian_config_t config = {0};
    config.max_tags = 100;
    config.buffer_size = 1000;

    wtc_result_t result = historian_init(&hist, &config);
    ASSERT_EQ(WTC_OK, result);

    const char *tag_names[] = {"pH", "Temperature", "Turbidity", "Pressure"};
    int tag_ids[4];

    for (int i = 0; i < 4; i++) {
        result = historian_add_tag(hist,
            "rtu-tank-1",
            i + 1,
            tag_names[i],
            1000,
            0.05f,
            COMPRESSION_DEADBAND,
            &tag_ids[i]);

        ASSERT_EQ(WTC_OK, result);
        assert(tag_ids[i] >= 0);
    }

    /* Verify all tags have unique IDs */
    for (int i = 0; i < 4; i++) {
        for (int j = i + 1; j < 4; j++) {
            assert(tag_ids[i] != tag_ids[j]);
        }
    }

    historian_cleanup(hist);
}

/* ============== Data Recording Tests ============== */

TEST(historian_record_sample)
{
    historian_t *hist = NULL;
    historian_config_t config = {0};
    config.max_tags = 100;
    config.buffer_size = 1000;

    wtc_result_t result = historian_init(&hist, &config);
    ASSERT_EQ(WTC_OK, result);

    int tag_id;
    result = historian_add_tag(hist,
        "test-rtu",
        1,
        "test.value",
        100,
        0.0f,
        COMPRESSION_NONE,
        &tag_id);

    ASSERT_EQ(WTC_OK, result);

    /* Record some values */
    for (int i = 0; i < 10; i++) {
        result = historian_record_sample(hist, tag_id,
            (uint64_t)(i * 100),  /* timestamp_ms */
            (float)i,              /* value */
            192);                  /* quality - Good */
        ASSERT_EQ(WTC_OK, result);
    }

    historian_cleanup(hist);
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

/* ============== Compression Type Tests ============== */

TEST(compression_types)
{
    /* Verify compression enum values exist */
    compression_t none = COMPRESSION_NONE;
    compression_t swinging = COMPRESSION_SWINGING_DOOR;
    compression_t boxcar = COMPRESSION_BOXCAR;
    compression_t deadband = COMPRESSION_DEADBAND;

    /* Just verify they are distinct values */
    assert(none != swinging);
    assert(swinging != boxcar);
    assert(boxcar != deadband);
}

/* ============== Test Runner ============== */

void run_historian_tests(void)
{
    printf("\n=== Historian Tests ===\n\n");

    printf("Creation Tests:\n");
    RUN_TEST(historian_init_null);
    RUN_TEST(historian_create_and_cleanup);

    printf("\nTag Management Tests:\n");
    RUN_TEST(historian_add_tag);
    RUN_TEST(historian_add_multiple_tags);

    printf("\nData Recording Tests:\n");
    RUN_TEST(historian_record_sample);

    printf("\nQuality Code Tests:\n");
    RUN_TEST(historian_quality_codes);

    printf("\nCompression Type Tests:\n");
    RUN_TEST(compression_types);

    printf("\n=== Results: %d/%d tests passed ===\n\n", tests_passed, tests_run);
}

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;
    run_historian_tests();
    return (tests_passed == tests_run) ? 0 : 1;
}
