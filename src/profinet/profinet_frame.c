/*
 * Water Treatment Controller - PROFINET Frame Handling Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "profinet_frame.h"
#include "dcp_discovery.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <arpa/inet.h>

/* Frame builder functions */

wtc_result_t frame_builder_init(frame_builder_t *builder,
                                 uint8_t *buffer,
                                 size_t capacity,
                                 const uint8_t *src_mac) {
    if (!builder || !buffer) {
        return WTC_ERROR_INVALID_PARAM;
    }

    builder->buffer = buffer;
    builder->capacity = capacity;
    builder->position = 0;

    if (src_mac) {
        memcpy(builder->src_mac, src_mac, ETH_ADDR_LEN);
    } else {
        memset(builder->src_mac, 0, ETH_ADDR_LEN);
    }

    return WTC_OK;
}

void frame_builder_reset(frame_builder_t *builder) {
    if (builder) {
        builder->position = 0;
    }
}

size_t frame_builder_length(const frame_builder_t *builder) {
    return builder ? builder->position : 0;
}

wtc_result_t frame_build_ethernet(frame_builder_t *builder,
                                   const uint8_t *dst_mac,
                                   uint16_t ethertype) {
    if (!builder || !dst_mac) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (builder->position + ETH_HEADER_LEN > builder->capacity) {
        return WTC_ERROR_FULL;
    }

    /* Destination MAC */
    memcpy(builder->buffer + builder->position, dst_mac, ETH_ADDR_LEN);
    builder->position += ETH_ADDR_LEN;

    /* Source MAC */
    memcpy(builder->buffer + builder->position, builder->src_mac, ETH_ADDR_LEN);
    builder->position += ETH_ADDR_LEN;

    /* EtherType */
    uint16_t net_ethertype = htons(ethertype);
    memcpy(builder->buffer + builder->position, &net_ethertype, 2);
    builder->position += 2;

    return WTC_OK;
}

wtc_result_t frame_build_rt_header(frame_builder_t *builder,
                                    uint16_t frame_id) {
    if (!builder) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (builder->position + 2 > builder->capacity) {
        return WTC_ERROR_FULL;
    }

    uint16_t net_frame_id = htons(frame_id);
    memcpy(builder->buffer + builder->position, &net_frame_id, 2);
    builder->position += 2;

    return WTC_OK;
}

wtc_result_t frame_build_dcp_identify(frame_builder_t *builder,
                                       uint32_t xid,
                                       const char *station_name) {
    if (!builder) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Calculate data length */
    uint16_t data_length = 4; /* All selector block */
    if (station_name) {
        data_length = 4 + 4 + strlen(station_name); /* Name filter block */
        if (strlen(station_name) & 1) data_length++; /* Padding */
    }

    /* Check capacity */
    if (builder->position + 2 + 10 + data_length > builder->capacity) {
        return WTC_ERROR_FULL;
    }

    /* Frame ID */
    uint16_t frame_id = htons(PROFINET_FRAME_ID_DCP_IDENT);
    memcpy(builder->buffer + builder->position, &frame_id, 2);
    builder->position += 2;

    /* DCP header */
    builder->buffer[builder->position++] = DCP_SERVICE_IDENTIFY;
    builder->buffer[builder->position++] = DCP_SERVICE_TYPE_REQUEST;

    uint32_t net_xid = htonl(xid);
    memcpy(builder->buffer + builder->position, &net_xid, 4);
    builder->position += 4;

    uint16_t response_delay = htons(0x0080); /* 128 * 10ms = 1.28s max */
    memcpy(builder->buffer + builder->position, &response_delay, 2);
    builder->position += 2;

    uint16_t net_data_length = htons(data_length);
    memcpy(builder->buffer + builder->position, &net_data_length, 2);
    builder->position += 2;

    if (station_name) {
        /* Name filter block */
        builder->buffer[builder->position++] = DCP_OPTION_DEVICE;
        builder->buffer[builder->position++] = DCP_SUBOPTION_DEVICE_NAME;

        size_t name_len = strlen(station_name);
        uint16_t block_len = htons(name_len);
        memcpy(builder->buffer + builder->position, &block_len, 2);
        builder->position += 2;

        memcpy(builder->buffer + builder->position, station_name, name_len);
        builder->position += name_len;

        /* Padding */
        if (name_len & 1) {
            builder->buffer[builder->position++] = 0x00;
        }
    } else {
        /* All selector block */
        builder->buffer[builder->position++] = DCP_OPTION_ALL;
        builder->buffer[builder->position++] = 0xFF;

        uint16_t block_len = htons(0);
        memcpy(builder->buffer + builder->position, &block_len, 2);
        builder->position += 2;
    }

    return WTC_OK;
}

wtc_result_t frame_build_dcp_set(frame_builder_t *builder,
                                  const uint8_t *dst_mac,
                                  uint32_t xid,
                                  uint8_t option,
                                  uint8_t suboption,
                                  const void *data,
                                  size_t data_len) {
    if (!builder || !dst_mac || !data) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Calculate total data length */
    uint16_t total_data_len = 4 + data_len;
    if (data_len & 1) total_data_len++; /* Padding */

    /* Check capacity */
    if (builder->position + 2 + 10 + total_data_len > builder->capacity) {
        return WTC_ERROR_FULL;
    }

    /* Frame ID */
    uint16_t frame_id = htons(PROFINET_FRAME_ID_DCP_GETSET);
    memcpy(builder->buffer + builder->position, &frame_id, 2);
    builder->position += 2;

    /* DCP header */
    builder->buffer[builder->position++] = DCP_SERVICE_SET;
    builder->buffer[builder->position++] = DCP_SERVICE_TYPE_REQUEST;

    uint32_t net_xid = htonl(xid);
    memcpy(builder->buffer + builder->position, &net_xid, 4);
    builder->position += 4;

    uint16_t response_delay = htons(0x0001);
    memcpy(builder->buffer + builder->position, &response_delay, 2);
    builder->position += 2;

    uint16_t net_data_length = htons(total_data_len);
    memcpy(builder->buffer + builder->position, &net_data_length, 2);
    builder->position += 2;

    /* Block header */
    builder->buffer[builder->position++] = option;
    builder->buffer[builder->position++] = suboption;

    uint16_t block_len = htons(data_len);
    memcpy(builder->buffer + builder->position, &block_len, 2);
    builder->position += 2;

    /* Block data */
    memcpy(builder->buffer + builder->position, data, data_len);
    builder->position += data_len;

    /* Padding */
    if (data_len & 1) {
        builder->buffer[builder->position++] = 0x00;
    }

    return WTC_OK;
}

wtc_result_t frame_append_data(frame_builder_t *builder,
                                const void *data,
                                size_t len) {
    if (!builder || !data) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (builder->position + len > builder->capacity) {
        return WTC_ERROR_FULL;
    }

    memcpy(builder->buffer + builder->position, data, len);
    builder->position += len;

    return WTC_OK;
}

wtc_result_t frame_append_padding(frame_builder_t *builder,
                                   size_t min_length) {
    if (!builder) {
        return WTC_ERROR_INVALID_PARAM;
    }

    while (builder->position < min_length &&
           builder->position < builder->capacity) {
        builder->buffer[builder->position++] = 0x00;
    }

    return WTC_OK;
}

/* Frame parser functions */

wtc_result_t frame_parser_init(frame_parser_t *parser,
                                const uint8_t *buffer,
                                size_t length) {
    if (!parser || !buffer) {
        return WTC_ERROR_INVALID_PARAM;
    }

    parser->buffer = buffer;
    parser->length = length;
    parser->position = 0;

    return WTC_OK;
}

size_t frame_parser_remaining(const frame_parser_t *parser) {
    return parser ? parser->length - parser->position : 0;
}

wtc_result_t frame_parse_ethernet(frame_parser_t *parser,
                                   uint8_t *dst_mac,
                                   uint8_t *src_mac,
                                   uint16_t *ethertype) {
    if (!parser || frame_parser_remaining(parser) < ETH_HEADER_LEN) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (dst_mac) {
        memcpy(dst_mac, parser->buffer + parser->position, ETH_ADDR_LEN);
    }
    parser->position += ETH_ADDR_LEN;

    if (src_mac) {
        memcpy(src_mac, parser->buffer + parser->position, ETH_ADDR_LEN);
    }
    parser->position += ETH_ADDR_LEN;

    uint16_t etype = ntohs(*(uint16_t *)(parser->buffer + parser->position));
    parser->position += 2;

    /* Handle VLAN tagged frames (PN-H2 fix) */
    if (etype == PROFINET_ETHERTYPE_VLAN) {
        /* Check if we have enough bytes for VLAN TCI + real ethertype */
        if (frame_parser_remaining(parser) < 4) {
            return WTC_ERROR_PROTOCOL;
        }

        /* Skip VLAN TCI (2 bytes - contains PCP, DEI, VID) */
        parser->position += 2;

        /* Read the real ethertype */
        etype = ntohs(*(uint16_t *)(parser->buffer + parser->position));
        parser->position += 2;
    }

    if (ethertype) {
        *ethertype = etype;
    }

    return WTC_OK;
}

wtc_result_t frame_parse_rt_header(frame_parser_t *parser,
                                    uint16_t *frame_id) {
    if (!parser || frame_parser_remaining(parser) < 2) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (frame_id) {
        *frame_id = ntohs(*(uint16_t *)(parser->buffer + parser->position));
    }
    parser->position += 2;

    return WTC_OK;
}

wtc_result_t frame_parse_dcp_header(frame_parser_t *parser,
                                     profinet_dcp_header_t *header) {
    if (!parser || !header || frame_parser_remaining(parser) < 10) {
        return WTC_ERROR_INVALID_PARAM;
    }

    header->service_id = parser->buffer[parser->position++];
    header->service_type = parser->buffer[parser->position++];

    header->xid = ntohl(*(uint32_t *)(parser->buffer + parser->position));
    parser->position += 4;

    header->response_delay = ntohs(*(uint16_t *)(parser->buffer + parser->position));
    parser->position += 2;

    header->data_length = ntohs(*(uint16_t *)(parser->buffer + parser->position));
    parser->position += 2;

    return WTC_OK;
}

wtc_result_t frame_parse_dcp_block(frame_parser_t *parser,
                                    dcp_block_header_t *header,
                                    const uint8_t **data) {
    if (!parser || !header || frame_parser_remaining(parser) < 4) {
        return WTC_ERROR_INVALID_PARAM;
    }

    header->option = parser->buffer[parser->position++];
    header->suboption = parser->buffer[parser->position++];

    header->length = ntohs(*(uint16_t *)(parser->buffer + parser->position));
    parser->position += 2;

    if (frame_parser_remaining(parser) < header->length) {
        return WTC_ERROR_PROTOCOL;
    }

    if (data) {
        *data = parser->buffer + parser->position;
    }
    parser->position += header->length;

    return WTC_OK;
}

wtc_result_t frame_read_bytes(frame_parser_t *parser,
                               void *data,
                               size_t len) {
    if (!parser || !data || frame_parser_remaining(parser) < len) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memcpy(data, parser->buffer + parser->position, len);
    parser->position += len;

    return WTC_OK;
}

wtc_result_t frame_skip_bytes(frame_parser_t *parser, size_t len) {
    if (!parser || frame_parser_remaining(parser) < len) {
        return WTC_ERROR_INVALID_PARAM;
    }

    parser->position += len;
    return WTC_OK;
}

wtc_result_t frame_read_u8(frame_parser_t *parser, uint8_t *val) {
    if (!parser || !val || frame_parser_remaining(parser) < 1) {
        return WTC_ERROR_INVALID_PARAM;
    }

    *val = parser->buffer[parser->position++];
    return WTC_OK;
}

wtc_result_t frame_read_u16(frame_parser_t *parser, uint16_t *val) {
    if (!parser || !val || frame_parser_remaining(parser) < 2) {
        return WTC_ERROR_INVALID_PARAM;
    }

    *val = ntohs(*(uint16_t *)(parser->buffer + parser->position));
    parser->position += 2;
    return WTC_OK;
}

wtc_result_t frame_read_u32(frame_parser_t *parser, uint32_t *val) {
    if (!parser || !val || frame_parser_remaining(parser) < 4) {
        return WTC_ERROR_INVALID_PARAM;
    }

    *val = ntohl(*(uint32_t *)(parser->buffer + parser->position));
    parser->position += 4;
    return WTC_OK;
}

/* Utility functions */

void ip_to_string(uint32_t ip, char *buf, size_t buf_len) {
    if (!buf || buf_len < 16) return;

    snprintf(buf, buf_len, "%u.%u.%u.%u",
             (ip >> 24) & 0xFF,
             (ip >> 16) & 0xFF,
             (ip >> 8) & 0xFF,
             ip & 0xFF);
}

uint32_t string_to_ip(const char *str) {
    if (!str) return 0;

    unsigned int a, b, c, d;
    if (sscanf(str, "%u.%u.%u.%u", &a, &b, &c, &d) != 4) {
        return 0;
    }

    return (a << 24) | (b << 16) | (c << 8) | d;
}

void mac_to_string(const uint8_t *mac, char *buf, size_t buf_len) {
    if (!mac || !buf || buf_len < 18) return;

    snprintf(buf, buf_len, "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

bool string_to_mac(const char *str, uint8_t *mac) {
    if (!str || !mac) return false;

    unsigned int m[6];
    if (sscanf(str, "%x:%x:%x:%x:%x:%x",
               &m[0], &m[1], &m[2], &m[3], &m[4], &m[5]) != 6) {
        return false;
    }

    for (int i = 0; i < 6; i++) {
        mac[i] = (uint8_t)m[i];
    }

    return true;
}
