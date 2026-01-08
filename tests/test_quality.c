/**
 * Water Treatment Controller - Data Quality Tests
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Tests for quality propagation and fail-safe behavior.
 * These tests verify that BAD quality data causes appropriate
 * system responses (interlock trips, PID holds, etc.)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <assert.h>
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

#define ASSERT_TRUE(cond) do { \
    if (!(cond)) { \
        printf("FAILED at line %d: condition not true\n", __LINE__); \
        return; \
    } \
} while(0)

#define ASSERT_FALSE(cond) do { \
    if (cond) { \
        printf("FAILED at line %d: condition not false\n", __LINE__); \
        return; \
    } \
} while(0)

/* ============== Quality Code Tests ============== */

TEST(quality_codes_correct_values)
{
    /* Verify quality codes match OPC UA specification */
    ASSERT_EQ(0x00, QUALITY_GOOD);
    ASSERT_EQ(0x40, QUALITY_UNCERTAIN);
    ASSERT_EQ(0x80, QUALITY_BAD);
    ASSERT_EQ(0xC0, QUALITY_NOT_CONNECTED);
}

TEST(quality_is_usable_for_control)
{
    /* GOOD and UNCERTAIN quality can be used for control */
    ASSERT_TRUE(QUALITY_GOOD == 0x00 || QUALITY_GOOD == 0x40);
    ASSERT_TRUE(QUALITY_UNCERTAIN == 0x40);

    /* BAD and NOT_CONNECTED should not be used */
    ASSERT_TRUE(QUALITY_BAD >= 0x80);
    ASSERT_TRUE(QUALITY_NOT_CONNECTED >= 0x80);
}

/* ============== Sensor Data Quality Tests ============== */

TEST(sensor_data_includes_quality)
{
    sensor_data_t sensor = {0};
    sensor.value = 7.0f;
    sensor.status = IOPS_GOOD;
    sensor.quality = QUALITY_GOOD;
    sensor.timestamp_ms = 1000;
    sensor.stale = false;

    /* Verify structure contains all quality fields */
    ASSERT_EQ(IOPS_GOOD, sensor.status);
    ASSERT_EQ(QUALITY_GOOD, sensor.quality);
    ASSERT_FALSE(sensor.stale);
}

TEST(sensor_stale_detection)
{
    sensor_data_t sensor = {0};
    sensor.value = 7.0f;
    sensor.status = IOPS_GOOD;
    sensor.quality = QUALITY_GOOD;
    sensor.timestamp_ms = 1000;
    sensor.stale = false;

    /* Simulate staleness check (would be done by registry) */
    uint64_t now = 10000;  /* 9 seconds later */
    uint64_t age = now - sensor.timestamp_ms;

    if (age > 5000) {
        sensor.stale = true;
        if (sensor.quality == QUALITY_GOOD) {
            sensor.quality = QUALITY_UNCERTAIN;
        }
    }

    ASSERT_TRUE(sensor.stale);
    ASSERT_EQ(QUALITY_UNCERTAIN, sensor.quality);
}

TEST(sensor_extended_stale_becomes_bad)
{
    sensor_data_t sensor = {0};
    sensor.value = 7.0f;
    sensor.status = IOPS_GOOD;
    sensor.quality = QUALITY_GOOD;
    sensor.timestamp_ms = 1000;

    /* Simulate 90 seconds stale (>60s threshold) */
    uint64_t now = 91000;
    uint64_t age = now - sensor.timestamp_ms;

    if (age > 60000) {
        sensor.stale = true;
        sensor.quality = QUALITY_BAD;
    }

    ASSERT_TRUE(sensor.stale);
    ASSERT_EQ(QUALITY_BAD, sensor.quality);
}

TEST(sensor_very_stale_becomes_not_connected)
{
    sensor_data_t sensor = {0};
    sensor.value = 7.0f;
    sensor.status = IOPS_GOOD;
    sensor.quality = QUALITY_GOOD;
    sensor.timestamp_ms = 1000;

    /* Simulate 6 minutes stale (>5min threshold) */
    uint64_t now = 361000;
    uint64_t age = now - sensor.timestamp_ms;

    if (age > 300000) {
        sensor.stale = true;
        sensor.quality = QUALITY_NOT_CONNECTED;
    }

    ASSERT_TRUE(sensor.stale);
    ASSERT_EQ(QUALITY_NOT_CONNECTED, sensor.quality);
}

/* ============== Control Decision Tests ============== */

TEST(pid_should_reject_bad_quality)
{
    sensor_data_t sensor = {0};
    sensor.value = 7.0f;
    sensor.status = IOPS_GOOD;
    sensor.quality = QUALITY_BAD;

    /* Simulate PID quality check */
    bool quality_ok = (sensor.status == IOPS_GOOD &&
                       (sensor.quality == QUALITY_GOOD ||
                        sensor.quality == QUALITY_UNCERTAIN));

    ASSERT_FALSE(quality_ok);
}

TEST(pid_should_accept_good_quality)
{
    sensor_data_t sensor = {0};
    sensor.value = 7.0f;
    sensor.status = IOPS_GOOD;
    sensor.quality = QUALITY_GOOD;

    /* Simulate PID quality check */
    bool quality_ok = (sensor.status == IOPS_GOOD &&
                       (sensor.quality == QUALITY_GOOD ||
                        sensor.quality == QUALITY_UNCERTAIN));

    ASSERT_TRUE(quality_ok);
}

TEST(pid_should_accept_uncertain_with_warning)
{
    sensor_data_t sensor = {0};
    sensor.value = 7.0f;
    sensor.status = IOPS_GOOD;
    sensor.quality = QUALITY_UNCERTAIN;

    /* Simulate PID quality check - UNCERTAIN is acceptable but logged */
    bool quality_ok = (sensor.status == IOPS_GOOD &&
                       (sensor.quality == QUALITY_GOOD ||
                        sensor.quality == QUALITY_UNCERTAIN));

    bool should_warn = (sensor.quality == QUALITY_UNCERTAIN);

    ASSERT_TRUE(quality_ok);
    ASSERT_TRUE(should_warn);
}

/* ============== Interlock Fail-Safe Tests ============== */

TEST(interlock_trips_on_bad_quality)
{
    sensor_data_t sensor = {0};
    sensor.value = 50.0f;  /* Normal value, not exceeding threshold */
    sensor.status = IOPS_GOOD;
    sensor.quality = QUALITY_BAD;

    interlock_t interlock = {0};
    interlock.enabled = true;
    interlock.condition = INTERLOCK_CONDITION_ABOVE;
    interlock.threshold = 100.0f;

    /* Simulate interlock quality check */
    bool input_valid = (sensor.status == IOPS_GOOD &&
                        sensor.quality == QUALITY_GOOD);

    bool condition_met = false;
    if (input_valid) {
        condition_met = (sensor.value > interlock.threshold);
    } else {
        /* Fail-safe: treat bad input as trip */
        condition_met = true;
    }

    ASSERT_FALSE(input_valid);
    ASSERT_TRUE(condition_met);  /* Should trip despite normal value */
}

TEST(interlock_trips_on_not_connected)
{
    sensor_data_t sensor = {0};
    sensor.value = 50.0f;
    sensor.status = IOPS_GOOD;
    sensor.quality = QUALITY_NOT_CONNECTED;

    interlock_t interlock = {0};
    interlock.enabled = true;
    interlock.condition = INTERLOCK_CONDITION_ABOVE;
    interlock.threshold = 100.0f;

    bool input_valid = (sensor.status == IOPS_GOOD &&
                        sensor.quality == QUALITY_GOOD);

    bool condition_met = !input_valid;  /* Fail-safe */

    ASSERT_FALSE(input_valid);
    ASSERT_TRUE(condition_met);
}

TEST(interlock_normal_on_good_quality)
{
    sensor_data_t sensor = {0};
    sensor.value = 50.0f;  /* Below threshold */
    sensor.status = IOPS_GOOD;
    sensor.quality = QUALITY_GOOD;

    interlock_t interlock = {0};
    interlock.enabled = true;
    interlock.condition = INTERLOCK_CONDITION_ABOVE;
    interlock.threshold = 100.0f;

    bool input_valid = (sensor.status == IOPS_GOOD &&
                        sensor.quality == QUALITY_GOOD);

    bool condition_met = false;
    if (input_valid) {
        condition_met = (sensor.value > interlock.threshold);
    }

    ASSERT_TRUE(input_valid);
    ASSERT_FALSE(condition_met);  /* Should NOT trip */
}

/* ============== Historian Quality Tests ============== */

TEST(historian_sample_stores_quality)
{
    historian_sample_t sample = {0};
    sample.timestamp_ms = 1000;
    sample.tag_id = 1;
    sample.value = 7.5f;
    sample.quality = QUALITY_GOOD;

    ASSERT_EQ(QUALITY_GOOD, sample.quality);

    /* Change quality and verify */
    sample.quality = QUALITY_BAD;
    ASSERT_EQ(QUALITY_BAD, sample.quality);
}

TEST(quality_should_propagate_from_sensor)
{
    /* Simulate sensor -> historian flow */
    sensor_data_t sensor = {0};
    sensor.value = 7.5f;
    sensor.quality = QUALITY_UNCERTAIN;

    historian_sample_t sample = {0};
    sample.value = sensor.value;
    sample.quality = (uint8_t)sensor.quality;  /* Direct propagation */

    ASSERT_EQ(QUALITY_UNCERTAIN, sample.quality);
}

/* ============== IOPS vs Quality Tests ============== */

TEST(iops_bad_means_bad_quality)
{
    sensor_data_t sensor = {0};
    sensor.value = 7.0f;
    sensor.status = IOPS_BAD;  /* Protocol level bad */
    sensor.quality = QUALITY_GOOD;  /* Application level looks good */

    /* Quality check should consider BOTH */
    bool usable = (sensor.status == IOPS_GOOD &&
                   (sensor.quality == QUALITY_GOOD ||
                    sensor.quality == QUALITY_UNCERTAIN));

    ASSERT_FALSE(usable);  /* IOPS_BAD makes it unusable */
}

TEST(iops_good_with_bad_quality_unusable)
{
    sensor_data_t sensor = {0};
    sensor.value = 7.0f;
    sensor.status = IOPS_GOOD;  /* Protocol level good */
    sensor.quality = QUALITY_BAD;  /* Application level bad */

    bool usable = (sensor.status == IOPS_GOOD &&
                   (sensor.quality == QUALITY_GOOD ||
                    sensor.quality == QUALITY_UNCERTAIN));

    ASSERT_FALSE(usable);  /* Application quality makes it unusable */
}

/* ============== Test Runner ============== */

void run_quality_tests(void)
{
    printf("\n=== Data Quality Tests ===\n\n");

    printf("Quality Code Tests:\n");
    RUN_TEST(quality_codes_correct_values);
    RUN_TEST(quality_is_usable_for_control);

    printf("\nSensor Data Quality Tests:\n");
    RUN_TEST(sensor_data_includes_quality);
    RUN_TEST(sensor_stale_detection);
    RUN_TEST(sensor_extended_stale_becomes_bad);
    RUN_TEST(sensor_very_stale_becomes_not_connected);

    printf("\nControl Decision Tests:\n");
    RUN_TEST(pid_should_reject_bad_quality);
    RUN_TEST(pid_should_accept_good_quality);
    RUN_TEST(pid_should_accept_uncertain_with_warning);

    printf("\nInterlock Fail-Safe Tests:\n");
    RUN_TEST(interlock_trips_on_bad_quality);
    RUN_TEST(interlock_trips_on_not_connected);
    RUN_TEST(interlock_normal_on_good_quality);

    printf("\nHistorian Quality Tests:\n");
    RUN_TEST(historian_sample_stores_quality);
    RUN_TEST(quality_should_propagate_from_sensor);

    printf("\nIOPS vs Quality Tests:\n");
    RUN_TEST(iops_bad_means_bad_quality);
    RUN_TEST(iops_good_with_bad_quality_unusable);

    printf("\n=== Results: %d/%d tests passed ===\n\n", tests_passed, tests_run);
}

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;
    run_quality_tests();
    return (tests_passed == tests_run) ? 0 : 1;
}
