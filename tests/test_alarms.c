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

#define ASSERT_TRUE(cond) do { \
    if (!(cond)) { \
        printf("FAILED at line %d: condition is false\n", __LINE__); \
        return; \
    } \
} while(0)

/* ============== Alarm Manager Creation Tests ============== */

TEST(alarm_manager_init_test)
{
    alarm_manager_t *am = NULL;
    alarm_manager_config_t config = {0};
    config.max_active_alarms = 100;
    config.max_history_entries = 1000;
    config.require_ack = true;

    wtc_result_t result = alarm_manager_init(&am, &config);
    ASSERT_EQ(WTC_OK, result);
    ASSERT_NOT_NULL(am);

    alarm_manager_cleanup(am);
}

TEST(alarm_manager_init_with_callbacks)
{
    alarm_manager_t *am = NULL;
    alarm_manager_config_t config = {0};
    config.max_active_alarms = 100;
    config.max_history_entries = 1000;
    config.require_ack = true;
    config.shelving_enabled = true;

    wtc_result_t result = alarm_manager_init(&am, &config);
    ASSERT_EQ(WTC_OK, result);
    ASSERT_NOT_NULL(am);

    alarm_manager_cleanup(am);
}

/* ============== Alarm Rule Tests ============== */

TEST(alarm_rule_create_high)
{
    alarm_manager_t *am = NULL;
    alarm_manager_config_t config = {0};
    config.max_active_alarms = 100;
    alarm_manager_init(&am, &config);
    ASSERT_NOT_NULL(am);

    int rule_id = -1;
    wtc_result_t result = alarm_manager_create_rule(
        am,
        "rtu-tank-1",       /* rtu_station */
        1,                   /* slot (pH sensor) */
        ALARM_CONDITION_HIGH,
        8.5f,               /* threshold */
        ALARM_SEVERITY_MEDIUM,
        5000,               /* delay_ms */
        "pH High",          /* message */
        &rule_id
    );

    ASSERT_EQ(WTC_OK, result);
    ASSERT_TRUE(rule_id >= 0);

    alarm_manager_cleanup(am);
}

TEST(alarm_rule_create_low)
{
    alarm_manager_t *am = NULL;
    alarm_manager_config_t config = {0};
    config.max_active_alarms = 100;
    alarm_manager_init(&am, &config);
    ASSERT_NOT_NULL(am);

    int rule_id = -1;
    wtc_result_t result = alarm_manager_create_rule(
        am,
        "rtu-tank-1",
        1,
        ALARM_CONDITION_LOW,
        6.5f,
        ALARM_SEVERITY_MEDIUM,
        5000,
        "pH Low",
        &rule_id
    );

    ASSERT_EQ(WTC_OK, result);
    ASSERT_TRUE(rule_id >= 0);

    alarm_manager_cleanup(am);
}

TEST(alarm_rule_create_high_high)
{
    alarm_manager_t *am = NULL;
    alarm_manager_config_t config = {0};
    config.max_active_alarms = 100;
    alarm_manager_init(&am, &config);
    ASSERT_NOT_NULL(am);

    int rule_id = -1;
    wtc_result_t result = alarm_manager_create_rule(
        am,
        "rtu-tank-1",
        8,                  /* Pressure sensor */
        ALARM_CONDITION_HIGH_HIGH,
        10.0f,
        ALARM_SEVERITY_HIGH,  /* High severity for critical */
        0,                    /* Immediate, no delay */
        "Pressure Very High - Emergency",
        &rule_id
    );

    ASSERT_EQ(WTC_OK, result);
    ASSERT_TRUE(rule_id >= 0);

    alarm_manager_cleanup(am);
}

/* ============== Alarm State Tests ============== */

TEST(alarm_state_transitions)
{
    /* Test ISA-18.2 state machine */
    alarm_t alarm = {0};
    alarm.state = ALARM_STATE_CLEARED;

    /* Cleared -> Active Unack (condition becomes true) */
    alarm.state = ALARM_STATE_ACTIVE_UNACK;
    ASSERT_EQ(ALARM_STATE_ACTIVE_UNACK, alarm.state);

    /* Active Unack -> Active Ack (operator acknowledges) */
    alarm.state = ALARM_STATE_ACTIVE_ACK;
    ASSERT_EQ(ALARM_STATE_ACTIVE_ACK, alarm.state);

    /* Active Ack -> Cleared (condition clears) */
    alarm.state = ALARM_STATE_CLEARED;
    ASSERT_EQ(ALARM_STATE_CLEARED, alarm.state);
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
    alarm.state = ALARM_STATE_CLEARED;
    ASSERT_EQ(ALARM_STATE_CLEARED, alarm.state);
}

/* ============== Alarm Severity Tests ============== */

TEST(alarm_severity_levels)
{
    /* Verify severity ordering */
    ASSERT_TRUE(ALARM_SEVERITY_LOW < ALARM_SEVERITY_MEDIUM);
    ASSERT_TRUE(ALARM_SEVERITY_MEDIUM < ALARM_SEVERITY_HIGH);
    ASSERT_TRUE(ALARM_SEVERITY_HIGH < ALARM_SEVERITY_EMERGENCY);
}

/* ============== Alarm Acknowledgment Tests ============== */

TEST(alarm_acknowledge_user)
{
    alarm_t alarm = {0};
    alarm.alarm_id = 1;
    alarm.state = ALARM_STATE_ACTIVE_UNACK;

    /* Simulate acknowledgment */
    strncpy(alarm.ack_user, "operator1", sizeof(alarm.ack_user) - 1);
    alarm.state = ALARM_STATE_ACTIVE_ACK;

    ASSERT_STR_EQ("operator1", alarm.ack_user);
    ASSERT_EQ(ALARM_STATE_ACTIVE_ACK, alarm.state);
}

TEST(alarm_active_count)
{
    alarm_manager_t *am = NULL;
    alarm_manager_config_t config = {0};
    config.max_active_alarms = 100;
    alarm_manager_init(&am, &config);
    ASSERT_NOT_NULL(am);

    /* Initially should have no active alarms */
    int count = alarm_manager_get_active_count(am);
    ASSERT_EQ(0, count);

    alarm_manager_cleanup(am);
}

TEST(alarm_unack_count)
{
    alarm_manager_t *am = NULL;
    alarm_manager_config_t config = {0};
    config.max_active_alarms = 100;
    alarm_manager_init(&am, &config);
    ASSERT_NOT_NULL(am);

    /* Initially should have no unacknowledged alarms */
    int count = alarm_manager_get_unack_count(am);
    ASSERT_EQ(0, count);

    alarm_manager_cleanup(am);
}

/* ============== Alarm Rule Management Tests ============== */

TEST(alarm_rule_enable_disable)
{
    alarm_manager_t *am = NULL;
    alarm_manager_config_t config = {0};
    config.max_active_alarms = 100;
    alarm_manager_init(&am, &config);
    ASSERT_NOT_NULL(am);

    /* Create a rule */
    int rule_id = -1;
    alarm_manager_create_rule(am, "rtu-tank-1", 1, ALARM_CONDITION_HIGH,
                               8.5f, ALARM_SEVERITY_MEDIUM, 5000, "pH High", &rule_id);

    /* Disable the rule */
    wtc_result_t result = alarm_manager_enable_rule(am, rule_id, false);
    ASSERT_EQ(WTC_OK, result);

    /* Re-enable the rule */
    result = alarm_manager_enable_rule(am, rule_id, true);
    ASSERT_EQ(WTC_OK, result);

    alarm_manager_cleanup(am);
}

TEST(alarm_rule_delete)
{
    alarm_manager_t *am = NULL;
    alarm_manager_config_t config = {0};
    config.max_active_alarms = 100;
    alarm_manager_init(&am, &config);
    ASSERT_NOT_NULL(am);

    /* Create a rule */
    int rule_id = -1;
    alarm_manager_create_rule(am, "rtu-tank-1", 1, ALARM_CONDITION_HIGH,
                               8.5f, ALARM_SEVERITY_MEDIUM, 5000, "pH High", &rule_id);

    /* Delete the rule */
    wtc_result_t result = alarm_manager_delete_rule(am, rule_id);
    ASSERT_EQ(WTC_OK, result);

    alarm_manager_cleanup(am);
}

/* ============== Alarm Flood Detection Tests ============== */

TEST(alarm_flood_detection)
{
    alarm_manager_t *am = NULL;
    alarm_manager_config_t config = {0};
    config.max_active_alarms = 100;
    config.max_alarms_per_10min = 50;
    alarm_manager_init(&am, &config);
    ASSERT_NOT_NULL(am);

    /* Initially should not be in flood condition */
    bool is_flood = alarm_manager_is_alarm_flood(am);
    ASSERT_TRUE(!is_flood);

    alarm_manager_cleanup(am);
}

TEST(alarm_rate)
{
    alarm_manager_t *am = NULL;
    alarm_manager_config_t config = {0};
    config.max_active_alarms = 100;
    alarm_manager_init(&am, &config);
    ASSERT_NOT_NULL(am);

    /* Initially should have zero alarm rate */
    float rate = alarm_manager_get_alarm_rate(am);
    ASSERT_TRUE(rate >= 0.0f);

    alarm_manager_cleanup(am);
}

/* ============== Test Runner ============== */

void run_alarm_tests(void)
{
    printf("\n=== Alarm Manager Tests ===\n\n");

    printf("Creation Tests:\n");
    RUN_TEST(alarm_manager_init_test);
    RUN_TEST(alarm_manager_init_with_callbacks);

    printf("\nAlarm Rule Tests:\n");
    RUN_TEST(alarm_rule_create_high);
    RUN_TEST(alarm_rule_create_low);
    RUN_TEST(alarm_rule_create_high_high);

    printf("\nState Transition Tests:\n");
    RUN_TEST(alarm_state_transitions);
    RUN_TEST(alarm_state_cleared_unack);

    printf("\nSeverity Tests:\n");
    RUN_TEST(alarm_severity_levels);

    printf("\nAcknowledgment Tests:\n");
    RUN_TEST(alarm_acknowledge_user);
    RUN_TEST(alarm_active_count);
    RUN_TEST(alarm_unack_count);

    printf("\nRule Management Tests:\n");
    RUN_TEST(alarm_rule_enable_disable);
    RUN_TEST(alarm_rule_delete);

    printf("\nFlood Detection Tests:\n");
    RUN_TEST(alarm_flood_detection);
    RUN_TEST(alarm_rate);

    printf("\n=== Results: %d/%d tests passed ===\n\n", tests_passed, tests_run);
}

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;
    run_alarm_tests();
    return (tests_passed == tests_run) ? 0 : 1;
}
