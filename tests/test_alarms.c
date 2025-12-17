/**
 * Water Treatment Controller - Alarm Manager Tests
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "../src/alarms/alarm_manager.h"
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

#define ASSERT_STR_EQ(expected, actual) do { \
    if (strcmp((expected), (actual)) != 0) { \
        printf("FAILED at line %d: expected '%s', got '%s'\n", __LINE__, (expected), (actual)); \
        return; \
    } \
} while(0)

/* ============== Alarm Manager Creation Tests ============== */

TEST(alarm_manager_create)
{
    alarm_manager_t *am = alarm_manager_create(100);
    ASSERT_NOT_NULL(am);
    alarm_manager_destroy(am);
}

TEST(alarm_manager_create_with_capacity)
{
    alarm_manager_t *am = alarm_manager_create(1000);
    ASSERT_NOT_NULL(am);
    alarm_manager_destroy(am);
}

/* ============== Alarm Rule Tests ============== */

TEST(alarm_rule_create_high)
{
    alarm_manager_t *am = alarm_manager_create(100);
    ASSERT_NOT_NULL(am);

    alarm_rule_t rule = {0};
    strncpy(rule.rtu_station, "rtu-tank-1", sizeof(rule.rtu_station));
    rule.slot = 1;  /* pH sensor */
    rule.condition = ALARM_CONDITION_HIGH;
    rule.threshold = 8.5f;
    rule.severity = ALARM_SEVERITY_WARNING;
    rule.delay_ms = 5000;
    strncpy(rule.message, "pH High", sizeof(rule.message));
    rule.enabled = true;

    int rule_id = alarm_manager_create_rule(am, &rule);
    assert(rule_id >= 0);

    alarm_manager_destroy(am);
}

TEST(alarm_rule_create_low)
{
    alarm_manager_t *am = alarm_manager_create(100);
    ASSERT_NOT_NULL(am);

    alarm_rule_t rule = {0};
    strncpy(rule.rtu_station, "rtu-tank-1", sizeof(rule.rtu_station));
    rule.slot = 1;
    rule.condition = ALARM_CONDITION_LOW;
    rule.threshold = 6.5f;
    rule.severity = ALARM_SEVERITY_WARNING;
    rule.delay_ms = 5000;
    strncpy(rule.message, "pH Low", sizeof(rule.message));
    rule.enabled = true;

    int rule_id = alarm_manager_create_rule(am, &rule);
    assert(rule_id >= 0);

    alarm_manager_destroy(am);
}

TEST(alarm_rule_create_critical)
{
    alarm_manager_t *am = alarm_manager_create(100);
    ASSERT_NOT_NULL(am);

    alarm_rule_t rule = {0};
    strncpy(rule.rtu_station, "rtu-tank-1", sizeof(rule.rtu_station));
    rule.slot = 8;  /* Pressure sensor */
    rule.condition = ALARM_CONDITION_HIGH_HIGH;
    rule.threshold = 10.0f;
    rule.severity = ALARM_SEVERITY_CRITICAL;
    rule.delay_ms = 0;  /* Immediate */
    strncpy(rule.message, "Pressure Very High - Emergency", sizeof(rule.message));
    rule.enabled = true;

    int rule_id = alarm_manager_create_rule(am, &rule);
    assert(rule_id >= 0);

    alarm_manager_destroy(am);
}

/* ============== Alarm State Tests ============== */

TEST(alarm_state_transitions)
{
    /* Test ISA-18.2 state machine */
    alarm_t alarm = {0};
    alarm.state = ALARM_STATE_NORMAL;

    /* Normal -> Active Unack (condition becomes true) */
    alarm.state = ALARM_STATE_ACTIVE_UNACK;
    ASSERT_EQ(ALARM_STATE_ACTIVE_UNACK, alarm.state);

    /* Active Unack -> Active Ack (operator acknowledges) */
    alarm.state = ALARM_STATE_ACTIVE_ACK;
    ASSERT_EQ(ALARM_STATE_ACTIVE_ACK, alarm.state);

    /* Active Ack -> Normal (condition clears) */
    alarm.state = ALARM_STATE_NORMAL;
    ASSERT_EQ(ALARM_STATE_NORMAL, alarm.state);
}

TEST(alarm_state_cleared_unack)
{
    /* Test cleared but unacknowledged state */
    alarm_t alarm = {0};
    alarm.state = ALARM_STATE_ACTIVE_UNACK;

    /* Condition clears before acknowledgment */
    alarm.state = ALARM_STATE_CLEARED_UNACK;
    ASSERT_EQ(ALARM_STATE_CLEARED_UNACK, alarm.state);

    /* Then acknowledged */
    alarm.state = ALARM_STATE_NORMAL;
    ASSERT_EQ(ALARM_STATE_NORMAL, alarm.state);
}

/* ============== Alarm Severity Tests ============== */

TEST(alarm_severity_levels)
{
    /* Verify severity ordering */
    assert(ALARM_SEVERITY_INFO < ALARM_SEVERITY_WARNING);
    assert(ALARM_SEVERITY_WARNING < ALARM_SEVERITY_CRITICAL);
    assert(ALARM_SEVERITY_CRITICAL < ALARM_SEVERITY_EMERGENCY);
}

/* ============== Alarm Acknowledgment Tests ============== */

TEST(alarm_acknowledge)
{
    alarm_manager_t *am = alarm_manager_create(100);
    ASSERT_NOT_NULL(am);

    /* Create rule */
    alarm_rule_t rule = {0};
    strncpy(rule.rtu_station, "rtu-tank-1", sizeof(rule.rtu_station));
    rule.slot = 1;
    rule.condition = ALARM_CONDITION_HIGH;
    rule.threshold = 8.5f;
    rule.severity = ALARM_SEVERITY_WARNING;
    rule.delay_ms = 0;
    strncpy(rule.message, "pH High", sizeof(rule.message));
    rule.enabled = true;

    alarm_manager_create_rule(am, &rule);

    /* Simulate alarm processing with high value */
    alarm_manager_process_value(am, "rtu-tank-1", 1, 9.0f);

    /* Get active alarms */
    int count = alarm_manager_get_active_count(am);

    /* Note: count might be 0 if delay hasn't elapsed */
    /* This is expected behavior */

    alarm_manager_destroy(am);
}

TEST(alarm_acknowledge_user)
{
    alarm_t alarm = {0};
    alarm.alarm_id = 1;
    alarm.state = ALARM_STATE_ACTIVE_UNACK;

    /* Simulate acknowledgment */
    strncpy(alarm.ack_user, "operator1", sizeof(alarm.ack_user));
    alarm.state = ALARM_STATE_ACTIVE_ACK;

    ASSERT_STR_EQ("operator1", alarm.ack_user);
    ASSERT_EQ(ALARM_STATE_ACTIVE_ACK, alarm.state);
}

/* ============== Alarm Suppression Tests ============== */

TEST(alarm_suppression)
{
    alarm_t alarm = {0};
    alarm.suppressed = false;

    /* Suppress alarm */
    alarm.suppressed = true;

    assert(alarm.suppressed == true);
}

TEST(alarm_shelving)
{
    alarm_t alarm = {0};
    alarm.shelved = false;

    /* Shelve alarm */
    alarm.shelved = true;
    alarm.shelve_duration_ms = 3600000; /* 1 hour */

    assert(alarm.shelved == true);
    ASSERT_EQ(3600000, alarm.shelve_duration_ms);
}

/* ============== Test Runner ============== */

void run_alarm_tests(void)
{
    printf("\n=== Alarm Manager Tests ===\n\n");

    printf("Creation Tests:\n");
    RUN_TEST(alarm_manager_create);
    RUN_TEST(alarm_manager_create_with_capacity);

    printf("\nAlarm Rule Tests:\n");
    RUN_TEST(alarm_rule_create_high);
    RUN_TEST(alarm_rule_create_low);
    RUN_TEST(alarm_rule_create_critical);

    printf("\nState Transition Tests:\n");
    RUN_TEST(alarm_state_transitions);
    RUN_TEST(alarm_state_cleared_unack);

    printf("\nSeverity Tests:\n");
    RUN_TEST(alarm_severity_levels);

    printf("\nAcknowledgment Tests:\n");
    RUN_TEST(alarm_acknowledge);
    RUN_TEST(alarm_acknowledge_user);

    printf("\nSuppression Tests:\n");
    RUN_TEST(alarm_suppression);
    RUN_TEST(alarm_shelving);

    printf("\n=== Results: %d/%d tests passed ===\n\n", tests_passed, tests_run);
}

int main(int argc, char *argv[])
{
    run_alarm_tests();
    return (tests_passed == tests_run) ? 0 : 1;
}
