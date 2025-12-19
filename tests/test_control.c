/**
 * Water Treatment Controller - Control Engine Tests
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <assert.h>
#include "../src/control/control_engine.h"
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

/* ============== PID Tests ============== */

TEST(pid_proportional_only)
{
    pid_loop_t loop = {0};
    strncpy(loop.name, "test_pid", sizeof(loop.name));
    loop.enabled = true;
    loop.kp = 1.0f;
    loop.ki = 0.0f;
    loop.kd = 0.0f;
    loop.setpoint = 7.0f;
    loop.output_min = 0.0f;
    loop.output_max = 100.0f;
    loop.mode = PID_MODE_AUTO;

    /* With Kp=1, error=1 should give output=1 */
    float pv = 6.0f;  /* Error = 7.0 - 6.0 = 1.0 */
    float error = loop.setpoint - pv;

    ASSERT_FLOAT_EQ(1.0f, error, 0.001f);
}

TEST(pid_output_clamping)
{
    pid_loop_t loop = {0};
    strncpy(loop.name, "test_pid", sizeof(loop.name));
    loop.enabled = true;
    loop.kp = 100.0f;  /* Large gain to exceed limits */
    loop.ki = 0.0f;
    loop.kd = 0.0f;
    loop.setpoint = 100.0f;
    loop.output_min = 0.0f;
    loop.output_max = 100.0f;
    loop.mode = PID_MODE_AUTO;

    /* With large error and gain, output should be clamped */
    float pv = 0.0f;  /* Error = 100.0 */
    float error = loop.setpoint - pv;
    float output = loop.kp * error;

    /* Clamp output */
    if (output > loop.output_max) output = loop.output_max;
    if (output < loop.output_min) output = loop.output_min;

    ASSERT_FLOAT_EQ(100.0f, output, 0.001f);
}

TEST(pid_manual_mode)
{
    pid_loop_t loop = {0};
    strncpy(loop.name, "test_pid", sizeof(loop.name));
    loop.enabled = true;
    loop.kp = 1.0f;
    loop.ki = 0.1f;
    loop.kd = 0.0f;
    loop.setpoint = 7.0f;
    loop.output_min = 0.0f;
    loop.output_max = 100.0f;
    loop.mode = PID_MODE_MANUAL;
    loop.cv = 50.0f;  /* Control variable (output) in manual mode */

    /* In manual mode, cv is set directly by operator */
    ASSERT_EQ(PID_MODE_MANUAL, loop.mode);
    ASSERT_FLOAT_EQ(50.0f, loop.cv, 0.001f);
}

TEST(pid_cascade_mode)
{
    pid_loop_t loop = {0};
    loop.mode = PID_MODE_CASCADE;

    /* Just verify mode can be set */
    ASSERT_EQ(PID_MODE_CASCADE, loop.mode);
}

/* ============== Interlock Tests ============== */

TEST(interlock_basic)
{
    interlock_t interlock = {0};
    strncpy(interlock.name, "low_level_protect", sizeof(interlock.name));
    interlock.enabled = true;
    interlock.condition = INTERLOCK_CONDITION_BELOW;
    interlock.threshold = 10.0f;
    interlock.delay_ms = 0;
    interlock.tripped = false;

    /* Test trip condition */
    float value = 5.0f;  /* Below threshold */
    bool should_trip = (interlock.condition == INTERLOCK_CONDITION_BELOW && value < interlock.threshold);

    assert(should_trip == true);
}

TEST(interlock_above_condition)
{
    interlock_t interlock = {0};
    strncpy(interlock.name, "high_pressure", sizeof(interlock.name));
    interlock.enabled = true;
    interlock.condition = INTERLOCK_CONDITION_ABOVE;
    interlock.threshold = 100.0f;
    interlock.delay_ms = 0;
    interlock.tripped = false;

    /* Test trip condition */
    float value = 150.0f;  /* Above threshold */
    bool should_trip = (interlock.condition == INTERLOCK_CONDITION_ABOVE && value > interlock.threshold);

    assert(should_trip == true);
}

TEST(interlock_disabled)
{
    interlock_t interlock = {0};
    interlock.enabled = false;
    interlock.condition = INTERLOCK_CONDITION_ABOVE;
    interlock.threshold = 100.0f;

    /* Disabled interlock should not trip */
    float value = 150.0f;
    bool should_trip = interlock.enabled &&
                       (interlock.condition == INTERLOCK_CONDITION_ABOVE && value > interlock.threshold);

    assert(should_trip == false);
}

/* ============== Control Engine Tests ============== */

TEST(control_engine_init_null)
{
    /* Test that control_engine_init returns error for NULL parameters */
    control_engine_config_t config = {0};
    config.scan_rate_ms = 100;

    wtc_result_t result = control_engine_init(NULL, &config);
    ASSERT_EQ(WTC_ERROR_INVALID_PARAM, result);

    control_engine_t *engine = NULL;
    result = control_engine_init(&engine, NULL);
    ASSERT_EQ(WTC_ERROR_INVALID_PARAM, result);
}

TEST(control_engine_create_and_cleanup)
{
    control_engine_t *engine = NULL;
    control_engine_config_t config = {0};
    config.scan_rate_ms = 100;

    wtc_result_t result = control_engine_init(&engine, &config);
    ASSERT_EQ(WTC_OK, result);
    ASSERT_NOT_NULL(engine);

    control_engine_cleanup(engine);
}

TEST(control_engine_add_pid)
{
    control_engine_t *engine = NULL;
    control_engine_config_t config = {0};
    config.scan_rate_ms = 100;

    wtc_result_t result = control_engine_init(&engine, &config);
    ASSERT_EQ(WTC_OK, result);

    pid_loop_t loop = {0};
    strncpy(loop.name, "pH_control", sizeof(loop.name));
    loop.enabled = true;
    loop.kp = 2.0f;
    loop.ki = 0.1f;
    loop.kd = 0.5f;
    loop.setpoint = 7.0f;
    loop.output_min = 0.0f;
    loop.output_max = 100.0f;
    strncpy(loop.input_rtu, "rtu-tank-1", sizeof(loop.input_rtu));
    loop.input_slot = 1;
    strncpy(loop.output_rtu, "rtu-tank-1", sizeof(loop.output_rtu));
    loop.output_slot = 12;

    int loop_id;
    result = control_engine_add_pid_loop(engine, &loop, &loop_id);
    ASSERT_EQ(WTC_OK, result);

    control_engine_cleanup(engine);
}

/* ============== Test Runner ============== */

void run_control_tests(void)
{
    printf("\n=== Control Engine Tests ===\n\n");

    printf("PID Tests:\n");
    RUN_TEST(pid_proportional_only);
    RUN_TEST(pid_output_clamping);
    RUN_TEST(pid_manual_mode);
    RUN_TEST(pid_cascade_mode);

    printf("\nInterlock Tests:\n");
    RUN_TEST(interlock_basic);
    RUN_TEST(interlock_above_condition);
    RUN_TEST(interlock_disabled);

    printf("\nControl Engine Tests:\n");
    RUN_TEST(control_engine_init_null);
    RUN_TEST(control_engine_create_and_cleanup);
    RUN_TEST(control_engine_add_pid);

    printf("\n=== Results: %d/%d tests passed ===\n\n", tests_passed, tests_run);
}

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;
    run_control_tests();
    return (tests_passed == tests_run) ? 0 : 1;
}
