/*
 * Water Treatment Controller - PROFINET Frame Handling
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_PROFINET_FRAME_H
#define WTC_PROFINET_FRAME_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Ethernet frame sizes */
#define ETH_ADDR_LEN        6
#define ETH_HEADER_LEN      14
#define ETH_MIN_FRAME_LEN   60
#define ETH_MAX_FRAME_LEN   1518
#define ETH_FCS_LEN         4

/* PROFINET Ethernet types */
#define PROFINET_ETHERTYPE          0x8892
#define PROFINET_ETHERTYPE_VLAN     0x8100

/* PROFINET Frame IDs */
#define PROFINET_FRAME_ID_DCP           0xFEFC
#define PROFINET_FRAME_ID_DCP_HELLO     0xFEFC
#define PROFINET_FRAME_ID_DCP_GETSET    0xFEFD
#define PROFINET_FRAME_ID_DCP_IDENT     0xFEFE
#define PROFINET_FRAME_ID_DCP_IDENT_RESP 0xFEFF  /* DCP Identify Response */
#define PROFINET_FRAME_ID_RT_CLASS1     0xC000  /* Start of RT Class 1 (IEC 61158-6) */
#define PROFINET_FRAME_ID_RT_CLASS1_END 0xF7FF  /* End of RT Class 1 */
#define PROFINET_FRAME_ID_RT_CLASS3     0x0100  /* RT Class 3 (IRT) */
#define PROFINET_FRAME_ID_RTC3_END      0x7FFF
#define PROFINET_FRAME_ID_ALARM_HIGH    0xFC01
#define PROFINET_FRAME_ID_ALARM_LOW     0xFE01
#define PROFINET_FRAME_ID_PTCP_SYNC     0xFF00
#define PROFINET_FRAME_ID_PTCP_DELAY    0xFF40

/* PROFINET frame header */
typedef struct __attribute__((packed)) {
    uint8_t dst_mac[ETH_ADDR_LEN];
    uint8_t src_mac[ETH_ADDR_LEN];
    uint16_t ethertype;
    uint16_t frame_id;
} profinet_frame_header_t;

/* PROFINET RT data header */
typedef struct __attribute__((packed)) {
    uint16_t cycle_counter;
    uint8_t data_status;
    uint8_t transfer_status;
} profinet_rt_header_t;

/* Data status bits */
#define PROFINET_DATA_STATUS_STATE      0x01    /* 0=Backup, 1=Primary */
#define PROFINET_DATA_STATUS_REDUNDANCY 0x02    /* 0=No redundancy */
#define PROFINET_DATA_STATUS_VALID      0x04    /* 0=Invalid, 1=Valid */
#define PROFINET_DATA_STATUS_RUN        0x10    /* 0=Stop, 1=Run */
#define PROFINET_DATA_STATUS_STATION_PROBLEM 0x20
#define PROFINET_DATA_STATUS_IGNORE     0x80    /* Provider ignore flag */

/* PROFINET DCP frame structure */
typedef struct __attribute__((packed)) {
    uint8_t service_id;
    uint8_t service_type;
    uint32_t xid;
    uint16_t response_delay;
    uint16_t data_length;
    /* Followed by DCP blocks */
} profinet_dcp_header_t;

/* DCP block header */
typedef struct __attribute__((packed)) {
    uint8_t option;
    uint8_t suboption;
    uint16_t length;
    /* Followed by block data */
} dcp_block_header_t;

/* PROFINET RPC (Remote Procedure Call) header */
typedef struct __attribute__((packed)) {
    uint8_t version;
    uint8_t packet_type;
    uint8_t flags1;
    uint8_t flags2;
    uint8_t drep[3];
    uint8_t serial_high;
    uint8_t object_uuid[16];
    uint8_t interface_uuid[16];
    uint8_t activity_uuid[16];
    uint32_t server_boot;
    uint32_t interface_version;
    uint32_t sequence_number;
    uint16_t opnum;
    uint16_t interface_hint;
    uint16_t activity_hint;
    uint16_t fragment_length;
    uint16_t fragment_number;
    uint8_t auth_protocol;
    uint8_t serial_low;
} profinet_rpc_header_t;

/* Frame builder context */
typedef struct {
    uint8_t *buffer;
    size_t capacity;
    size_t position;
    uint8_t src_mac[ETH_ADDR_LEN];
} frame_builder_t;

/* Initialize frame builder */
wtc_result_t frame_builder_init(frame_builder_t *builder,
                                 uint8_t *buffer,
                                 size_t capacity,
                                 const uint8_t *src_mac);

/* Reset frame builder */
void frame_builder_reset(frame_builder_t *builder);

/* Get current frame length */
size_t frame_builder_length(const frame_builder_t *builder);

/* Build Ethernet header */
wtc_result_t frame_build_ethernet(frame_builder_t *builder,
                                   const uint8_t *dst_mac,
                                   uint16_t ethertype);

/* Build PROFINET RT header */
wtc_result_t frame_build_rt_header(frame_builder_t *builder,
                                    uint16_t frame_id);

/* Build DCP identify request */
wtc_result_t frame_build_dcp_identify(frame_builder_t *builder,
                                       uint32_t xid,
                                       const char *station_name);

/* Build DCP set request */
wtc_result_t frame_build_dcp_set(frame_builder_t *builder,
                                  const uint8_t *dst_mac,
                                  uint32_t xid,
                                  uint8_t option,
                                  uint8_t suboption,
                                  const void *data,
                                  size_t data_len);

/* Append raw data */
wtc_result_t frame_append_data(frame_builder_t *builder,
                                const void *data,
                                size_t len);

/* Append padding to minimum frame size */
wtc_result_t frame_append_padding(frame_builder_t *builder,
                                   size_t min_length);

/* Frame parser context */
typedef struct {
    const uint8_t *buffer;
    size_t length;
    size_t position;
} frame_parser_t;

/* Initialize frame parser */
wtc_result_t frame_parser_init(frame_parser_t *parser,
                                const uint8_t *buffer,
                                size_t length);

/* Get remaining bytes */
size_t frame_parser_remaining(const frame_parser_t *parser);

/* Parse Ethernet header */
wtc_result_t frame_parse_ethernet(frame_parser_t *parser,
                                   uint8_t *dst_mac,
                                   uint8_t *src_mac,
                                   uint16_t *ethertype);

/* Parse PROFINET RT header */
wtc_result_t frame_parse_rt_header(frame_parser_t *parser,
                                    uint16_t *frame_id);

/* Parse DCP header */
wtc_result_t frame_parse_dcp_header(frame_parser_t *parser,
                                     profinet_dcp_header_t *header);

/* Parse DCP block */
wtc_result_t frame_parse_dcp_block(frame_parser_t *parser,
                                    dcp_block_header_t *header,
                                    const uint8_t **data);

/* Read raw bytes */
wtc_result_t frame_read_bytes(frame_parser_t *parser,
                               void *data,
                               size_t len);

/* Skip bytes */
wtc_result_t frame_skip_bytes(frame_parser_t *parser, size_t len);

/* Read integer types */
wtc_result_t frame_read_u8(frame_parser_t *parser, uint8_t *val);
wtc_result_t frame_read_u16(frame_parser_t *parser, uint16_t *val);
wtc_result_t frame_read_u32(frame_parser_t *parser, uint32_t *val);

/* Convert IP address to string */
void ip_to_string(uint32_t ip, char *buf, size_t buf_len);

/* Convert string to IP address */
uint32_t string_to_ip(const char *str);

/* Convert MAC address to string */
void mac_to_string(const uint8_t *mac, char *buf, size_t buf_len);

/* Parse MAC address string */
bool string_to_mac(const char *str, uint8_t *mac);

#ifdef __cplusplus
}
#endif

#endif /* WTC_PROFINET_FRAME_H */
