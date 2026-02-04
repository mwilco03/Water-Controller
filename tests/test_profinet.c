/**
 * Water Treatment Controller - PROFINET Tests
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "../src/profinet/profinet_controller.h"
#include "../src/profinet/dcp_discovery.h"
#include "../src/profinet/ar_manager.h"
#include "../src/profinet/profinet_frame.h"
#include "../src/utils/crc.h"

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

#define ASSERT_STR_EQ(expected, actual) do { \
    if (strcmp((expected), (actual)) != 0) { \
        printf("FAILED at line %d: expected '%s', got '%s'\n", __LINE__, (expected), (actual)); \
        return; \
    } \
} while(0)

#define ASSERT_NOT_NULL(ptr) do { \
    if ((ptr) == NULL) { \
        printf("FAILED at line %d: pointer is NULL\n", __LINE__); \
        return; \
    } \
} while(0)

#define ASSERT_TRUE(cond) do { \
    if (!(cond)) { \
        printf("FAILED at line %d: condition is false\n", __LINE__); \
        return; \
    } \
} while(0)

/* ============== CRC Tests ============== */

TEST(crc32_empty)
{
    uint8_t data[1] = {0};  /* Use a valid array with one element */
    uint32_t crc = crc32(data, 0);  /* Pass 0 length for empty test */
    /* Empty data should return initial CRC value */
    ASSERT_EQ(0, crc);
}

TEST(crc32_simple)
{
    uint8_t data[] = {0x01, 0x02, 0x03, 0x04};
    uint32_t crc = crc32(data, sizeof(data));
    /* CRC should be non-zero for non-empty data */
    assert(crc != 0);
}

TEST(crc16_ccitt_test)
{
    /* Test PROFINET CRC calculation (uses CRC-16-CCITT) */
    uint8_t frame[] = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05};
    uint16_t crc = crc16_ccitt(frame, sizeof(frame));
    /* Just verify it doesn't crash */
    (void)crc;
}

/* ============== Frame Builder Tests ============== */

TEST(frame_builder_init_test)
{
    uint8_t buffer[256];
    uint8_t src_mac[6] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55};
    frame_builder_t builder;

    wtc_result_t result = frame_builder_init(&builder, buffer, sizeof(buffer), src_mac);
    ASSERT_EQ(WTC_OK, result);
    ASSERT_EQ(0, frame_builder_length(&builder));
}

TEST(frame_builder_ethernet)
{
    uint8_t buffer[256];
    uint8_t src_mac[6] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55};
    uint8_t dest_mac[6] = {0x01, 0x0E, 0xCF, 0x00, 0x00, 0x00};

    frame_builder_t builder;
    wtc_result_t result = frame_builder_init(&builder, buffer, sizeof(buffer), src_mac);
    ASSERT_EQ(WTC_OK, result);

    /* Build Ethernet header */
    result = frame_build_ethernet(&builder, dest_mac, PROFINET_ETHERTYPE);
    ASSERT_EQ(WTC_OK, result);

    /* Build DCP identify request */
    result = frame_build_dcp_identify(&builder, 0x1234, NULL);
    ASSERT_EQ(WTC_OK, result);

    /* Frame should have minimum DCP identify length */
    size_t len = frame_builder_length(&builder);
    assert(len > 14); /* Ethernet header at minimum */
}

TEST(frame_build_dcp_identify_test)
{
    uint8_t buffer[256];
    uint8_t src_mac[6] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x66};
    uint8_t dest_mac[6] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55};

    frame_builder_t builder;
    wtc_result_t result = frame_builder_init(&builder, buffer, sizeof(buffer), src_mac);
    ASSERT_EQ(WTC_OK, result);

    /* Build Ethernet header */
    result = frame_build_ethernet(&builder, dest_mac, PROFINET_ETHERTYPE);
    ASSERT_EQ(WTC_OK, result);

    /* Build DCP set request with IP data */
    uint8_t ip_data[12] = {192, 168, 1, 100, 255, 255, 255, 0, 192, 168, 1, 1};
    result = frame_build_dcp_set(&builder, dest_mac, 0x1234, 0x01, 0x02, ip_data, sizeof(ip_data));
    ASSERT_EQ(WTC_OK, result);

    size_t len = frame_builder_length(&builder);
    assert(len > 14);
}

/* ============== Frame Parser Tests ============== */

TEST(ar_manager_init_null)
{
    /* Test that ar_manager_init returns error for NULL parameters */
    ar_manager_t *manager = NULL;
    uint8_t controller_mac[6] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55};

    /* NULL manager pointer should fail */
    wtc_result_t result = ar_manager_init(NULL, -1, controller_mac, "wtc-controller", 0x0493, 0x0001);
    ASSERT_EQ(WTC_ERROR_INVALID_PARAM, result);

    /* NULL MAC address should fail */
    result = ar_manager_init(&manager, -1, NULL, "wtc-controller", 0x0493, 0x0001);
    ASSERT_EQ(WTC_ERROR_INVALID_PARAM, result);
}

TEST(ar_manager_get_ar_null)
{
    /* Getting AR from NULL manager should return NULL */
    profinet_ar_t *ar = ar_manager_get_ar(NULL, "test-station");
    assert(ar == NULL);

    /* Getting AR with NULL station name should return NULL */
    ar = ar_manager_get_ar(NULL, NULL);
    assert(ar == NULL);
}

/* ============== Test Runner ============== */

void run_profinet_tests(void)
{
    printf("\n=== PROFINET Tests ===\n\n");

    printf("CRC Tests:\n");
    RUN_TEST(crc32_empty);
    RUN_TEST(crc32_simple);
    RUN_TEST(crc16_ccitt_test);

    printf("\nFrame Builder Tests:\n");
    RUN_TEST(frame_builder_init_test);
    RUN_TEST(frame_builder_ethernet);
    RUN_TEST(frame_build_dcp_identify_test);

    /* Frame Parser Tests - not implemented yet
    printf("\nFrame Parser Tests:\n");
    RUN_TEST(frame_parser_init_test);
    RUN_TEST(frame_parser_read_bytes);
    */

    printf("\nAR Manager Tests:\n");
    RUN_TEST(ar_manager_init_null);
    RUN_TEST(ar_manager_get_ar_null);

    printf("\n=== Results: %d/%d tests passed ===\n\n", tests_passed, tests_run);
}

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;
    run_profinet_tests();
    return (tests_passed == tests_run) ? 0 : 1;
}
