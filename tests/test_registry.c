/**
 * Water Treatment Controller - RTU Registry Tests
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <assert.h>
#include "../src/registry/rtu_registry.h"
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

#define ASSERT_NULL(ptr) do { \
    if ((ptr) != NULL) { \
        printf("FAILED at line %d: pointer is not NULL\n", __LINE__); \
        return; \
    } \
} while(0)

#define ASSERT_STR_EQ(expected, actual) do { \
    if (strcmp((expected), (actual)) != 0) { \
        printf("FAILED at line %d: expected '%s', got '%s'\n", __LINE__, (expected), (actual)); \
        return; \
    } \
} while(0)

/* Helper to create a registry for tests */
static rtu_registry_t *create_test_registry(void) {
    rtu_registry_t *reg = NULL;
    registry_config_t config = {0};
    config.database_path = NULL;
    config.max_devices = 16;

    wtc_result_t result = rtu_registry_init(&reg, &config);
    if (result != WTC_OK) {
        return NULL;
    }
    return reg;
}

/* ============== Registry Creation Tests ============== */

TEST(registry_create)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);
    rtu_registry_cleanup(reg);
}

TEST(registry_create_with_config)
{
    rtu_registry_t *reg = NULL;
    registry_config_t config = {0};
    config.database_path = NULL;
    config.max_devices = 256;

    wtc_result_t result = rtu_registry_init(&reg, &config);
    ASSERT_EQ(WTC_OK, result);
    ASSERT_NOT_NULL(reg);
    rtu_registry_cleanup(reg);
}

/* ============== Device Management Tests ============== */

TEST(registry_add_device)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);

    wtc_result_t result = rtu_registry_add_device(reg, "rtu-tank-1", "192.168.1.100", NULL, 0);
    ASSERT_EQ(WTC_OK, result);

    rtu_registry_cleanup(reg);
}

TEST(registry_add_multiple_devices)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);

    const char *names[] = {"rtu-tank-1", "rtu-pump-station", "rtu-filter-1", "rtu-dosing"};
    const char *ips[] = {"192.168.1.100", "192.168.1.101", "192.168.1.102", "192.168.1.103"};

    for (int i = 0; i < 4; i++) {
        wtc_result_t result = rtu_registry_add_device(reg, names[i], ips[i], NULL, 0);
        ASSERT_EQ(WTC_OK, result);
    }

    /* Verify count */
    int count = rtu_registry_get_device_count(reg);
    ASSERT_EQ(4, count);

    rtu_registry_cleanup(reg);
}

TEST(registry_get_device)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);

    rtu_registry_add_device(reg, "rtu-tank-1", "192.168.1.100", NULL, 0);

    rtu_device_t *device = rtu_registry_get_device(reg, "rtu-tank-1");
    ASSERT_NOT_NULL(device);
    ASSERT_STR_EQ("rtu-tank-1", device->station_name);
    rtu_registry_free_device_copy(device);

    rtu_registry_cleanup(reg);
}

TEST(registry_get_nonexistent_device)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);

    rtu_device_t *device = rtu_registry_get_device(reg, "nonexistent");
    ASSERT_NULL(device);

    rtu_registry_cleanup(reg);
}

TEST(registry_remove_device)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);

    rtu_registry_add_device(reg, "rtu-tank-1", "192.168.1.100", NULL, 0);

    wtc_result_t result = rtu_registry_remove_device(reg, "rtu-tank-1");
    ASSERT_EQ(WTC_OK, result);

    /* Verify removed */
    rtu_device_t *device = rtu_registry_get_device(reg, "rtu-tank-1");
    ASSERT_NULL(device);

    rtu_registry_cleanup(reg);
}

/* ============== Slot Configuration Tests ============== */

TEST(registry_configure_sensor_slot)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);

    rtu_registry_add_device(reg, "rtu-tank-1", "192.168.1.100", NULL, 0);

    slot_config_t slot = {0};
    slot.slot = 1;
    slot.subslot = 1;
    slot.type = SLOT_TYPE_SENSOR;
    slot.measurement_type = MEASUREMENT_PH;
    slot.scale_min = 0.0f;
    slot.scale_max = 14.0f;
    strncpy(slot.unit, "pH", sizeof(slot.unit) - 1);
    strncpy(slot.name, "Tank 1 pH", sizeof(slot.name) - 1);
    slot.enabled = true;

    wtc_result_t result = rtu_registry_set_device_config(reg, "rtu-tank-1", &slot, 1);
    ASSERT_EQ(WTC_OK, result);

    rtu_registry_cleanup(reg);
}

TEST(registry_configure_actuator_slot)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);

    rtu_registry_add_device(reg, "rtu-tank-1", "192.168.1.100", NULL, 0);

    slot_config_t slot = {0};
    slot.slot = 9;
    slot.subslot = 1;
    slot.type = SLOT_TYPE_ACTUATOR;
    slot.actuator_type = ACTUATOR_PUMP;
    strncpy(slot.name, "Feed Pump", sizeof(slot.name) - 1);
    slot.enabled = true;

    wtc_result_t result = rtu_registry_set_device_config(reg, "rtu-tank-1", &slot, 1);
    ASSERT_EQ(WTC_OK, result);

    rtu_registry_cleanup(reg);
}

/* ============== Sensor Data Tests ============== */

TEST(registry_update_sensor)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);

    rtu_registry_add_device(reg, "rtu-tank-1", "192.168.1.100", NULL, 0);

    /* Configure slot */
    slot_config_t slot = {0};
    slot.slot = 1;
    slot.subslot = 1;
    slot.type = SLOT_TYPE_SENSOR;
    slot.measurement_type = MEASUREMENT_PH;
    slot.scale_min = 0.0f;
    slot.scale_max = 14.0f;
    slot.enabled = true;

    rtu_registry_set_device_config(reg, "rtu-tank-1", &slot, 1);

    /* Update sensor value with quality (5-byte format: Float32 + Quality) */
    wtc_result_t result = rtu_registry_update_sensor(reg, "rtu-tank-1", 1, 7.0f, IOPS_GOOD, QUALITY_GOOD);
    ASSERT_EQ(WTC_OK, result);

    /* Read back */
    sensor_data_t read_data = {0};
    result = rtu_registry_get_sensor(reg, "rtu-tank-1", 1, &read_data);
    ASSERT_EQ(WTC_OK, result);
    ASSERT_FLOAT_EQ(7.0f, read_data.value, 0.001f);
    ASSERT_EQ(IOPS_GOOD, read_data.status);

    rtu_registry_cleanup(reg);
}

/* ============== Actuator Control Tests ============== */

TEST(registry_update_actuator)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);

    rtu_registry_add_device(reg, "rtu-tank-1", "192.168.1.100", NULL, 0);

    /* Configure actuator slot */
    slot_config_t slot = {0};
    slot.slot = 9;
    slot.subslot = 1;
    slot.type = SLOT_TYPE_ACTUATOR;
    slot.actuator_type = ACTUATOR_PUMP;
    slot.enabled = true;

    rtu_registry_set_device_config(reg, "rtu-tank-1", &slot, 1);

    /* Update actuator */
    actuator_output_t output = {0};
    output.command = ACTUATOR_CMD_ON;
    output.pwm_duty = 0;

    wtc_result_t result = rtu_registry_update_actuator(reg, "rtu-tank-1", 9, &output);
    ASSERT_EQ(WTC_OK, result);

    rtu_registry_cleanup(reg);
}

TEST(registry_actuator_pwm)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);

    rtu_registry_add_device(reg, "rtu-tank-1", "192.168.1.100", NULL, 0);

    /* Configure PWM actuator */
    slot_config_t slot = {0};
    slot.slot = 12;
    slot.subslot = 1;
    slot.type = SLOT_TYPE_ACTUATOR;
    slot.actuator_type = ACTUATOR_PWM;
    slot.enabled = true;

    rtu_registry_set_device_config(reg, "rtu-tank-1", &slot, 1);

    /* Set PWM duty */
    actuator_output_t output = {0};
    output.command = ACTUATOR_CMD_PWM;
    output.pwm_duty = 75;

    wtc_result_t result = rtu_registry_update_actuator(reg, "rtu-tank-1", 12, &output);
    ASSERT_EQ(WTC_OK, result);

    rtu_registry_cleanup(reg);
}

/* ============== Connection State Tests ============== */

TEST(registry_connection_states)
{
    /* Test connection state values exist and are ordered */
    ASSERT_EQ(0, PROFINET_STATE_OFFLINE);
    assert(PROFINET_STATE_DISCOVERY > PROFINET_STATE_OFFLINE);
    assert(PROFINET_STATE_CONNECTING > PROFINET_STATE_DISCOVERY);
    assert(PROFINET_STATE_RUNNING > PROFINET_STATE_CONNECTING);
}

TEST(registry_update_connection_state)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);

    rtu_registry_add_device(reg, "rtu-tank-1", "192.168.1.100", NULL, 0);

    /* Update state */
    wtc_result_t result = rtu_registry_set_device_state(reg, "rtu-tank-1", PROFINET_STATE_RUNNING);
    ASSERT_EQ(WTC_OK, result);

    /* Verify state */
    rtu_device_t *device = rtu_registry_get_device(reg, "rtu-tank-1");
    ASSERT_NOT_NULL(device);
    ASSERT_EQ(PROFINET_STATE_RUNNING, device->connection_state);
    rtu_registry_free_device_copy(device);

    rtu_registry_cleanup(reg);
}

/* ============== Statistics Tests ============== */

TEST(registry_get_statistics)
{
    rtu_registry_t *reg = create_test_registry();
    ASSERT_NOT_NULL(reg);

    /* Add some devices */
    rtu_registry_add_device(reg, "rtu-tank-1", "192.168.1.100", NULL, 0);
    rtu_registry_add_device(reg, "rtu-tank-2", "192.168.1.101", NULL, 0);

    /* Get stats */
    registry_stats_t stats = {0};
    wtc_result_t result = rtu_registry_get_stats(reg, &stats);
    ASSERT_EQ(WTC_OK, result);
    ASSERT_EQ(2, stats.total_devices);

    rtu_registry_cleanup(reg);
}

/* ============== Test Runner ============== */

void run_registry_tests(void)
{
    printf("\n=== RTU Registry Tests ===\n\n");

    printf("Creation Tests:\n");
    RUN_TEST(registry_create);
    RUN_TEST(registry_create_with_config);

    printf("\nDevice Management Tests:\n");
    RUN_TEST(registry_add_device);
    RUN_TEST(registry_add_multiple_devices);
    RUN_TEST(registry_get_device);
    RUN_TEST(registry_get_nonexistent_device);
    RUN_TEST(registry_remove_device);

    printf("\nSlot Configuration Tests:\n");
    RUN_TEST(registry_configure_sensor_slot);
    RUN_TEST(registry_configure_actuator_slot);

    printf("\nSensor Data Tests:\n");
    RUN_TEST(registry_update_sensor);

    printf("\nActuator Control Tests:\n");
    RUN_TEST(registry_update_actuator);
    RUN_TEST(registry_actuator_pwm);

    printf("\nConnection State Tests:\n");
    RUN_TEST(registry_connection_states);
    RUN_TEST(registry_update_connection_state);

    printf("\nStatistics Tests:\n");
    RUN_TEST(registry_get_statistics);

    printf("\n=== Results: %d/%d tests passed ===\n\n", tests_passed, tests_run);
}

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;

    run_registry_tests();
    return (tests_passed == tests_run) ? 0 : 1;
}
