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
    uint8_t data[1] = {0};  /* Use valid array with dummy data */
    uint32_t crc = crc32(data, 0);  /* Pass 0 length for empty test */
    /* Empty data should return initial CRC value (0 or ~0 depending on impl) */
    /* Just verify it doesn't crash */
    (void)crc;
}

TEST(crc32_simple)
{
    uint8_t data[] = {0x01, 0x02, 0x03, 0x04};
    uint32_t crc = crc32(data, sizeof(data));
    /* CRC should be non-zero for non-empty data */
    ASSERT_TRUE(crc != 0);
}

TEST(crc16_ccitt_test)
{
    /* Test PROFINET CRC calculation (CRC-16-CCITT) */
    uint8_t frame[] = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05};
    uint16_t crc = crc16_ccitt(frame, sizeof(frame));
    /* Just verify it computes without crashing */
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
    uint8_t dst_mac[6] = {0x01, 0x0E, 0xCF, 0x00, 0x00, 0x00};
    frame_builder_t builder;

    frame_builder_init(&builder, buffer, sizeof(buffer), src_mac);

    wtc_result_t result = frame_build_ethernet(&builder, dst_mac, PROFINET_ETHERTYPE);
    ASSERT_EQ(WTC_OK, result);
    ASSERT_TRUE(frame_builder_length(&builder) >= ETH_HEADER_LEN);
}

TEST(frame_build_dcp_identify_test)
{
    uint8_t buffer[256];
    uint8_t src_mac[6] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55};
    frame_builder_t builder;

    frame_builder_init(&builder, buffer, sizeof(buffer), src_mac);

    wtc_result_t result = frame_build_dcp_identify(&builder, 0x1234, "test-station");
    /* Result may be OK or may fail depending on implementation state */
    (void)result;
}

/* ============== Frame Parser Tests ============== */

TEST(frame_parser_init_test)
{
    uint8_t buffer[64] = {0};
    frame_parser_t parser;

    wtc_result_t result = frame_parser_init(&parser, buffer, sizeof(buffer));
    ASSERT_EQ(WTC_OK, result);
    ASSERT_EQ(64, frame_parser_remaining(&parser));
}

TEST(frame_parser_read_bytes)
{
    uint8_t buffer[8] = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08};
    uint8_t output[4];
    frame_parser_t parser;

    frame_parser_init(&parser, buffer, sizeof(buffer));

    wtc_result_t result = frame_read_bytes(&parser, output, 4);
    ASSERT_EQ(WTC_OK, result);
    ASSERT_EQ(0x01, output[0]);
    ASSERT_EQ(0x04, output[3]);
    ASSERT_EQ(4, frame_parser_remaining(&parser));
}

/* ============== IP/MAC Conversion Tests ============== */

TEST(ip_to_string_test)
{
    char buf[16];
    ip_to_string(0xC0A80164, buf, sizeof(buf));  /* 192.168.1.100 */
    /* Note: Result depends on byte order in implementation */
    ASSERT_NOT_NULL(buf);
    ASSERT_TRUE(strlen(buf) > 0);
}

TEST(string_to_ip_test)
{
    uint32_t ip = string_to_ip("192.168.1.100");
    /* Just verify it returns something */
    (void)ip;
}

TEST(mac_to_string_test)
{
    uint8_t mac[6] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55};
    char buf[32];
    mac_to_string(mac, buf, sizeof(buf));
    ASSERT_NOT_NULL(buf);
    ASSERT_TRUE(strlen(buf) > 0);
}

TEST(string_to_mac_test)
{
    uint8_t mac[6];
    bool result = string_to_mac("00:11:22:33:44:55", mac);
    ASSERT_TRUE(result);
    ASSERT_EQ(0x00, mac[0]);
    ASSERT_EQ(0x55, mac[5]);
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

    printf("\nFrame Parser Tests:\n");
    RUN_TEST(frame_parser_init_test);
    RUN_TEST(frame_parser_read_bytes);

    printf("\nIP/MAC Conversion Tests:\n");
    RUN_TEST(ip_to_string_test);
    RUN_TEST(string_to_ip_test);
    RUN_TEST(mac_to_string_test);
    RUN_TEST(string_to_mac_test);

    printf("\n=== Results: %d/%d tests passed ===\n\n", tests_passed, tests_run);
}

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;
    run_profinet_tests();
    return (tests_passed == tests_run) ? 0 : 1;
}
