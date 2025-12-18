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

#define ASSERT_STR_EQ(expected, actual) do { \
    if (strcmp((expected), (actual)) != 0) { \
        printf("FAILED at line %d: expected '%s', got '%s'\n", __LINE__, (expected), (actual)); \
        return; \
    } \
} while(0)

/* ============== Registry Creation Tests ============== */

TEST(registry_create)
{
    rtu_registry_t *reg = rtu_registry_create(16);
    ASSERT_NOT_NULL(reg);
    rtu_registry_destroy(reg);
}

TEST(registry_create_large)
{
    rtu_registry_t *reg = rtu_registry_create(256);
    ASSERT_NOT_NULL(reg);
    rtu_registry_destroy(reg);
}

/* ============== Device Management Tests ============== */

TEST(registry_add_device)
{
    rtu_registry_t *reg = rtu_registry_create(16);
    ASSERT_NOT_NULL(reg);

    rtu_device_config_t config = {0};
    strncpy(config.station_name, "rtu-tank-1", sizeof(config.station_name));
    config.ip_address = 0xC0A80164;  /* 192.168.1.100 */
    config.vendor_id = 0x0001;
    config.device_id = 0x0001;
    config.slot_count = 16;

    int result = rtu_registry_add_device(reg, &config);
    ASSERT_EQ(0, result);

    rtu_registry_destroy(reg);
}

TEST(registry_add_multiple_devices)
{
    rtu_registry_t *reg = rtu_registry_create(16);
    ASSERT_NOT_NULL(reg);

    const char *names[] = {"rtu-tank-1", "rtu-pump-station", "rtu-filter-1", "rtu-dosing"};
    uint32_t ips[] = {0xC0A80164, 0xC0A80165, 0xC0A80166, 0xC0A80167};

    for (int i = 0; i < 4; i++) {
        rtu_device_config_t config = {0};
        strncpy(config.station_name, names[i], sizeof(config.station_name));
        config.ip_address = ips[i];
        config.vendor_id = 0x0001;
        config.device_id = 0x0001;
        config.slot_count = 16;

        int result = rtu_registry_add_device(reg, &config);
        ASSERT_EQ(0, result);
    }

    /* Verify count */
    int count = rtu_registry_get_device_count(reg);
    ASSERT_EQ(4, count);

    rtu_registry_destroy(reg);
}

TEST(registry_get_device)
{
    rtu_registry_t *reg = rtu_registry_create(16);
    ASSERT_NOT_NULL(reg);

    rtu_device_config_t config = {0};
    strncpy(config.station_name, "rtu-tank-1", sizeof(config.station_name));
    config.ip_address = 0xC0A80164;
    config.vendor_id = 0x0001;
    config.device_id = 0x0001;
    config.slot_count = 16;

    rtu_registry_add_device(reg, &config);

    rtu_device_t *device = rtu_registry_get_device(reg, "rtu-tank-1");
    ASSERT_NOT_NULL(device);
    ASSERT_STR_EQ("rtu-tank-1", device->station_name);

    rtu_registry_destroy(reg);
}

TEST(registry_get_nonexistent_device)
{
    rtu_registry_t *reg = rtu_registry_create(16);
    ASSERT_NOT_NULL(reg);

    rtu_device_t *device = rtu_registry_get_device(reg, "nonexistent");
    assert(device == NULL);

    rtu_registry_destroy(reg);
}

TEST(registry_remove_device)
{
    rtu_registry_t *reg = rtu_registry_create(16);
    ASSERT_NOT_NULL(reg);

    rtu_device_config_t config = {0};
    strncpy(config.station_name, "rtu-tank-1", sizeof(config.station_name));
    config.ip_address = 0xC0A80164;
    config.vendor_id = 0x0001;
    config.device_id = 0x0001;
    config.slot_count = 16;

    rtu_registry_add_device(reg, &config);

    int result = rtu_registry_remove_device(reg, "rtu-tank-1");
    ASSERT_EQ(0, result);

    /* Verify removed */
    rtu_device_t *device = rtu_registry_get_device(reg, "rtu-tank-1");
    assert(device == NULL);

    rtu_registry_destroy(reg);
}

/* ============== Slot Management Tests ============== */

TEST(registry_configure_sensor_slot)
{
    rtu_registry_t *reg = rtu_registry_create(16);
    ASSERT_NOT_NULL(reg);

    rtu_device_config_t config = {0};
    strncpy(config.station_name, "rtu-tank-1", sizeof(config.station_name));
    config.ip_address = 0xC0A80164;
    config.slot_count = 16;

    rtu_registry_add_device(reg, &config);

    slot_config_t slot = {0};
    slot.slot_number = 1;
    slot.type = SLOT_TYPE_SENSOR;
    slot.sensor.type = SENSOR_TYPE_PH;
    slot.sensor.scale_min = 0.0f;
    slot.sensor.scale_max = 14.0f;
    strncpy(slot.sensor.unit, "pH", sizeof(slot.sensor.unit));

    int result = rtu_registry_configure_slot(reg, "rtu-tank-1", &slot);
    ASSERT_EQ(0, result);

    rtu_registry_destroy(reg);
}

TEST(registry_configure_actuator_slot)
{
    rtu_registry_t *reg = rtu_registry_create(16);
    ASSERT_NOT_NULL(reg);

    rtu_device_config_t config = {0};
    strncpy(config.station_name, "rtu-tank-1", sizeof(config.station_name));
    config.ip_address = 0xC0A80164;
    config.slot_count = 16;

    rtu_registry_add_device(reg, &config);

    slot_config_t slot = {0};
    slot.slot_number = 9;
    slot.type = SLOT_TYPE_ACTUATOR;
    slot.actuator.type = ACTUATOR_TYPE_PUMP;
    slot.actuator.has_pwm = true;
    slot.actuator.pwm_min = 0;
    slot.actuator.pwm_max = 100;

    int result = rtu_registry_configure_slot(reg, "rtu-tank-1", &slot);
    ASSERT_EQ(0, result);

    rtu_registry_destroy(reg);
}

/* ============== Sensor Data Tests ============== */

TEST(registry_update_sensor)
{
    rtu_registry_t *reg = rtu_registry_create(16);
    ASSERT_NOT_NULL(reg);

    rtu_device_config_t config = {0};
    strncpy(config.station_name, "rtu-tank-1", sizeof(config.station_name));
    config.ip_address = 0xC0A80164;
    config.slot_count = 16;

    rtu_registry_add_device(reg, &config);

    /* Configure slot */
    slot_config_t slot = {0};
    slot.slot_number = 1;
    slot.type = SLOT_TYPE_SENSOR;
    slot.sensor.type = SENSOR_TYPE_PH;
    slot.sensor.scale_min = 0.0f;
    slot.sensor.scale_max = 14.0f;

    rtu_registry_configure_slot(reg, "rtu-tank-1", &slot);

    /* Update sensor value */
    sensor_data_t data = {0};
    data.raw_value = 32768;  /* Mid-scale */
    data.scaled_value = 7.0f;
    data.quality = 192;

    int result = rtu_registry_update_sensor(reg, "rtu-tank-1", 1, &data);
    ASSERT_EQ(0, result);

    /* Read back */
    sensor_data_t read_data;
    result = rtu_registry_get_sensor(reg, "rtu-tank-1", 1, &read_data);
    ASSERT_EQ(0, result);
    ASSERT_FLOAT_EQ(7.0f, read_data.scaled_value, 0.001f);

    rtu_registry_destroy(reg);
}

/* ============== Actuator Control Tests ============== */

TEST(registry_update_actuator)
{
    rtu_registry_t *reg = rtu_registry_create(16);
    ASSERT_NOT_NULL(reg);

    rtu_device_config_t config = {0};
    strncpy(config.station_name, "rtu-tank-1", sizeof(config.station_name));
    config.ip_address = 0xC0A80164;
    config.slot_count = 16;

    rtu_registry_add_device(reg, &config);

    /* Configure actuator slot */
    slot_config_t slot = {0};
    slot.slot_number = 9;
    slot.type = SLOT_TYPE_ACTUATOR;
    slot.actuator.type = ACTUATOR_TYPE_PUMP;
    slot.actuator.has_pwm = true;

    rtu_registry_configure_slot(reg, "rtu-tank-1", &slot);

    /* Update actuator */
    actuator_output_t output = {0};
    output.command = ACTUATOR_CMD_ON;
    output.pwm_duty = 0;
    output.forced = false;

    int result = rtu_registry_update_actuator(reg, "rtu-tank-1", 9, &output);
    ASSERT_EQ(0, result);

    rtu_registry_destroy(reg);
}

TEST(registry_actuator_pwm)
{
    rtu_registry_t *reg = rtu_registry_create(16);
    ASSERT_NOT_NULL(reg);

    rtu_device_config_t config = {0};
    strncpy(config.station_name, "rtu-tank-1", sizeof(config.station_name));
    config.ip_address = 0xC0A80164;
    config.slot_count = 16;

    rtu_registry_add_device(reg, &config);

    /* Configure PWM actuator */
    slot_config_t slot = {0};
    slot.slot_number = 12;
    slot.type = SLOT_TYPE_ACTUATOR;
    slot.actuator.type = ACTUATOR_TYPE_PUMP;
    slot.actuator.has_pwm = true;
    slot.actuator.pwm_min = 0;
    slot.actuator.pwm_max = 100;

    rtu_registry_configure_slot(reg, "rtu-tank-1", &slot);

    /* Set PWM duty */
    actuator_output_t output = {0};
    output.command = ACTUATOR_CMD_PWM;
    output.pwm_duty = 75;
    output.forced = false;

    int result = rtu_registry_update_actuator(reg, "rtu-tank-1", 12, &output);
    ASSERT_EQ(0, result);

    rtu_registry_destroy(reg);
}

/* ============== Connection State Tests ============== */

TEST(registry_connection_states)
{
    /* Test connection state values */
    ASSERT_EQ(0, RTU_STATE_OFFLINE);
    assert(RTU_STATE_DISCOVERING > RTU_STATE_OFFLINE);
    assert(RTU_STATE_CONNECTING > RTU_STATE_DISCOVERING);
    assert(RTU_STATE_RUNNING > RTU_STATE_CONNECTING);
}

TEST(registry_update_connection_state)
{
    rtu_registry_t *reg = rtu_registry_create(16);
    ASSERT_NOT_NULL(reg);

    rtu_device_config_t config = {0};
    strncpy(config.station_name, "rtu-tank-1", sizeof(config.station_name));
    config.ip_address = 0xC0A80164;
    config.slot_count = 16;

    rtu_registry_add_device(reg, &config);

    /* Update state */
    int result = rtu_registry_set_state(reg, "rtu-tank-1", RTU_STATE_RUNNING);
    ASSERT_EQ(0, result);

    /* Verify state */
    rtu_device_t *device = rtu_registry_get_device(reg, "rtu-tank-1");
    ASSERT_NOT_NULL(device);
    ASSERT_EQ(RTU_STATE_RUNNING, device->connection_state);

    rtu_registry_destroy(reg);
}

/* ============== Test Runner ============== */

void run_registry_tests(void)
{
    printf("\n=== RTU Registry Tests ===\n\n");

    printf("Creation Tests:\n");
    RUN_TEST(registry_create);
    RUN_TEST(registry_create_large);

    printf("\nDevice Management Tests:\n");
    RUN_TEST(registry_add_device);
    RUN_TEST(registry_add_multiple_devices);
    RUN_TEST(registry_get_device);
    RUN_TEST(registry_get_nonexistent_device);
    RUN_TEST(registry_remove_device);

    printf("\nSlot Management Tests:\n");
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

    printf("\n=== Results: %d/%d tests passed ===\n\n", tests_passed, tests_run);
}

int main(int argc, char *argv[])
{
    run_registry_tests();
    return (tests_passed == tests_run) ? 0 : 1;
}
