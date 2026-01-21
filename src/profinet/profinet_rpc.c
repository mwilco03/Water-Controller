/*
 * Water Treatment Controller - PROFINET RPC Protocol Implementation
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Implementation of PROFINET RPC (Remote Procedure Call) protocol
 * for Application Relationship establishment per IEC 61158-6.
 */

#include "profinet_rpc.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <string.h>
#include <stdlib.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <poll.h>
#include <errno.h>
#include <unistd.h>

/* ============== Constants ============== */

/* RPC timeouts */
#define RPC_CONNECT_TIMEOUT_MS      5000
#define RPC_CONTROL_TIMEOUT_MS      3000
#define RPC_DEFAULT_TIMEOUT_MS      5000

/* Buffer sizes */
#define RPC_MAX_PDU_SIZE            1464
#define RPC_HEADER_SIZE             80

/* Block version */
#define BLOCK_VERSION_HIGH          1
#define BLOCK_VERSION_LOW           0

/* PROFINET IO Device Interface UUID */
const uint8_t PNIO_DEVICE_INTERFACE_UUID[16] = {
    0xDE, 0xA0, 0x00, 0x01, 0x6C, 0x97, 0x11, 0xD1,
    0x82, 0x71, 0x00, 0xA0, 0x24, 0x42, 0xDF, 0x7D
};

/* PROFINET IO Controller Interface UUID */
const uint8_t PNIO_CONTROLLER_INTERFACE_UUID[16] = {
    0xDE, 0xA0, 0x00, 0x02, 0x6C, 0x97, 0x11, 0xD1,
    0x82, 0x71, 0x00, 0xA0, 0x24, 0x42, 0xDF, 0x7D
};

/* ============== Internal Helpers ============== */

/**
 * @brief Write uint16 in network byte order to buffer.
 *
 * @param[out] buf   Destination buffer
 * @param[in]  val   Value to write
 * @param[in,out] pos Current position, incremented by 2
 *
 * @note Thread safety: SAFE
 * @note Memory: NO_ALLOC
 */
static void write_u16_be(uint8_t *buf, uint16_t val, size_t *pos)
{
    uint16_t be = htons(val);
    memcpy(buf + *pos, &be, 2);
    *pos += 2;
}

/**
 * @brief Write uint32 in network byte order to buffer.
 *
 * @param[out] buf   Destination buffer
 * @param[in]  val   Value to write
 * @param[in,out] pos Current position, incremented by 4
 *
 * @note Thread safety: SAFE
 * @note Memory: NO_ALLOC
 */
static void write_u32_be(uint8_t *buf, uint32_t val, size_t *pos)
{
    uint32_t be = htonl(val);
    memcpy(buf + *pos, &be, 4);
    *pos += 4;
}

/**
 * @brief Read uint16 from buffer in network byte order.
 *
 * @param[in]  buf   Source buffer
 * @param[in,out] pos Current position, incremented by 2
 * @return Host byte order value
 *
 * @note Thread safety: SAFE
 * @note Memory: NO_ALLOC
 */
static uint16_t read_u16_be(const uint8_t *buf, size_t *pos)
{
    uint16_t be;
    memcpy(&be, buf + *pos, 2);
    *pos += 2;
    return ntohs(be);
}

/**
 * @brief Read uint32 from buffer in network byte order.
 *
 * @param[in]  buf   Source buffer
 * @param[in,out] pos Current position, incremented by 4
 * @return Host byte order value
 *
 * @note Thread safety: SAFE
 * @note Memory: NO_ALLOC
 */
static uint32_t read_u32_be(const uint8_t *buf, size_t *pos)
{
    uint32_t be;
    memcpy(&be, buf + *pos, 4);
    *pos += 4;
    return ntohl(be);
}

/**
 * @brief Pad position to 4-byte alignment.
 *
 * @param[in,out] pos Position to align
 *
 * @note Thread safety: SAFE
 * @note Memory: NO_ALLOC
 */
static void align_to_4(size_t *pos)
{
    while ((*pos) % 4 != 0) {
        (*pos)++;
    }
}

/**
 * @brief Write single byte to buffer.
 *
 * @param[out] buf   Destination buffer
 * @param[in]  val   Value to write
 *
 * @note Thread safety: SAFE
 * @note Memory: NO_ALLOC
 */
static void write_u8(uint8_t *buf, uint8_t val)
{
    *buf = val;
}

/**
 * @brief Build RPC header for request.
 *
 * @param[out] buf              Output buffer
 * @param[in]  ctx              RPC context
 * @param[in]  object_uuid      AR UUID (object UUID)
 * @param[in]  opnum            Operation number
 * @param[in]  fragment_length  Length of data after header
 * @param[out] pos              Position after header
 *
 * @return WTC_OK on success, error code on failure
 *
 * @note Thread safety: SAFE
 * @note Memory: NO_ALLOC
 */
static wtc_result_t build_rpc_header(uint8_t *buf,
                                      rpc_context_t *ctx,
                                      const uint8_t *object_uuid,
                                      uint16_t opnum,
                                      uint16_t fragment_length,
                                      size_t *pos)
{
    profinet_rpc_header_t *hdr = (profinet_rpc_header_t *)buf;

    memset(hdr, 0, sizeof(profinet_rpc_header_t));

    hdr->version = RPC_VERSION_MAJOR;
    hdr->packet_type = RPC_PACKET_TYPE_REQUEST;
    hdr->flags1 = RPC_FLAG1_LAST_FRAGMENT | RPC_FLAG1_IDEMPOTENT;
    hdr->flags2 = 0;
    hdr->drep[0] = RPC_DREP_LITTLE_ENDIAN;
    hdr->drep[1] = RPC_DREP_ASCII;
    hdr->drep[2] = 0;
    hdr->serial_high = 0;

    /* Object UUID (AR UUID for this connection) */
    memcpy(hdr->object_uuid, object_uuid, 16);

    /* Interface UUID (PROFINET IO Device) */
    memcpy(hdr->interface_uuid, PNIO_DEVICE_INTERFACE_UUID, 16);

    /* Activity UUID (unique per request) */
    memcpy(hdr->activity_uuid, ctx->activity_uuid, 16);

    hdr->server_boot = 0;
    hdr->interface_version = htonl(1);
    hdr->sequence_number = htonl(ctx->sequence_number);
    ctx->sequence_number++;

    hdr->opnum = htons(opnum);
    hdr->interface_hint = 0xFFFF;
    hdr->activity_hint = 0xFFFF;
    hdr->fragment_length = htons(fragment_length);
    hdr->fragment_number = 0;
    hdr->auth_protocol = 0;
    hdr->serial_low = 0;

    *pos = sizeof(profinet_rpc_header_t);
    return WTC_OK;
}

/**
 * @brief Write block header to buffer.
 *
 * @param[out] buf     Output buffer
 * @param[in]  type    Block type
 * @param[in]  length  Block length (excluding type and length fields)
 * @param[in,out] pos  Position, incremented by 6
 *
 * @note Thread safety: SAFE
 * @note Memory: NO_ALLOC
 */
static void write_block_header(uint8_t *buf, uint16_t type,
                                uint16_t length, size_t *pos)
{
    write_u16_be(buf, type, pos);
    write_u16_be(buf, length, pos);
    buf[(*pos)++] = BLOCK_VERSION_HIGH;
    buf[(*pos)++] = BLOCK_VERSION_LOW;
}

/* ============== Public API Implementation ============== */

void rpc_generate_uuid(uint8_t *uuid)
{
    /* Generate pseudo-random UUID based on time and random */
    uint64_t now = time_get_ms();
    uint32_t rand1 = (uint32_t)random();
    uint32_t rand2 = (uint32_t)random();

    memcpy(uuid, &now, 8);
    memcpy(uuid + 8, &rand1, 4);
    memcpy(uuid + 12, &rand2, 4);

    /* Set version 4 (random) and variant bits */
    uuid[6] = (uuid[6] & 0x0F) | 0x40;  /* Version 4 */
    uuid[8] = (uuid[8] & 0x3F) | 0x80;  /* Variant 1 */
}

wtc_result_t rpc_context_init(rpc_context_t *ctx,
                               const uint8_t *controller_mac,
                               uint32_t controller_ip)
{
    if (!ctx || !controller_mac) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memset(ctx, 0, sizeof(rpc_context_t));

    /* Create UDP socket */
    ctx->socket_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (ctx->socket_fd < 0) {
        LOG_ERROR("Failed to create RPC socket: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    /* Bind to local port (any available) */
    struct sockaddr_in local_addr;
    memset(&local_addr, 0, sizeof(local_addr));
    local_addr.sin_family = AF_INET;
    local_addr.sin_addr.s_addr = controller_ip;
    local_addr.sin_port = 0;  /* Let kernel assign port */

    if (bind(ctx->socket_fd, (struct sockaddr *)&local_addr,
             sizeof(local_addr)) < 0) {
        LOG_ERROR("Failed to bind RPC socket: %s", strerror(errno));
        close(ctx->socket_fd);
        ctx->socket_fd = -1;
        return WTC_ERROR_IO;
    }

    /* Get assigned port */
    socklen_t addr_len = sizeof(local_addr);
    if (getsockname(ctx->socket_fd, (struct sockaddr *)&local_addr,
                    &addr_len) == 0) {
        ctx->controller_port = ntohs(local_addr.sin_port);
    }

    memcpy(ctx->controller_mac, controller_mac, 6);
    ctx->controller_ip = controller_ip;
    ctx->sequence_number = 1;

    /* Generate initial activity UUID */
    rpc_generate_uuid(ctx->activity_uuid);

    LOG_INFO("RPC context initialized, port %u", ctx->controller_port);
    return WTC_OK;
}

void rpc_context_cleanup(rpc_context_t *ctx)
{
    if (ctx && ctx->socket_fd >= 0) {
        close(ctx->socket_fd);
        ctx->socket_fd = -1;
    }
}

wtc_result_t rpc_build_connect_request(rpc_context_t *ctx,
                                        const connect_request_params_t *params,
                                        uint8_t *buffer,
                                        size_t *buf_len)
{
    if (!ctx || !params || !buffer || !buf_len) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (*buf_len < RPC_MAX_PDU_SIZE) {
        return WTC_ERROR_NO_MEMORY;
    }

    size_t pos = sizeof(profinet_rpc_header_t);  /* Skip header, fill later */
    size_t ar_args_start = pos;

    /*
     * Connect Request structure (per IEC 61158-6):
     * - AR Block Request
     * - IOCR Block Request(s)
     * - Alarm CR Block Request
     * - Expected Submodule Block(s)
     */

    /* ============== AR Block Request ============== */
    size_t ar_block_start = pos;
    pos += 6;  /* Skip block header, fill later */

    write_u16_be(buffer, (uint16_t)params->ar_type, &pos);
    memcpy(buffer + pos, params->ar_uuid, 16);
    pos += 16;
    write_u16_be(buffer, params->session_key, &pos);
    memcpy(buffer + pos, params->controller_mac, 6);
    pos += 6;
    memcpy(buffer + pos, params->controller_uuid, 16);
    pos += 16;
    write_u32_be(buffer, params->ar_properties, &pos);
    write_u16_be(buffer, params->activity_timeout, &pos);
    write_u16_be(buffer, ctx->controller_port, &pos);

    /* Station name */
    size_t name_len = strlen(params->station_name);
    write_u16_be(buffer, (uint16_t)name_len, &pos);
    memcpy(buffer + pos, params->station_name, name_len);
    pos += name_len;
    align_to_4(&pos);

    /* Fill AR block header */
    size_t ar_block_len = pos - ar_block_start - 4;  /* Exclude type + length */
    size_t save_pos = ar_block_start;
    write_block_header(buffer, BLOCK_TYPE_AR_BLOCK_REQ,
                        (uint16_t)ar_block_len, &save_pos);

    /* ============== IOCR Block Requests ============== */
    for (int i = 0; i < params->iocr_count; i++) {
        size_t iocr_block_start = pos;
        pos += 6;  /* Skip header */

        write_u16_be(buffer, params->iocr[i].type, &pos);
        write_u16_be(buffer, params->iocr[i].reference, &pos);
        write_u16_be(buffer, PROFINET_ETHERTYPE, &pos);  /* LT field */
        write_u32_be(buffer, IOCR_PROP_RT_CLASS_1, &pos);
        write_u16_be(buffer, params->iocr[i].data_length, &pos);
        write_u16_be(buffer, params->iocr[i].frame_id, &pos);
        write_u16_be(buffer, params->iocr[i].send_clock_factor, &pos);
        write_u16_be(buffer, params->iocr[i].reduction_ratio, &pos);
        write_u16_be(buffer, 0, &pos);  /* Phase */
        write_u16_be(buffer, 0, &pos);  /* Sequence (deprecated) */
        write_u32_be(buffer, 0, &pos);  /* Frame send offset */
        write_u16_be(buffer, params->iocr[i].watchdog_factor, &pos);
        write_u16_be(buffer, 3, &pos);  /* Data hold factor */
        write_u16_be(buffer, 0, &pos);  /* IOCR tag header */
        memset(buffer + pos, 0, 6);     /* Multicast MAC (not used) */
        pos += 6;

        /* API section */
        write_u16_be(buffer, 1, &pos);  /* Number of APIs */

        /* API 0 */
        write_u32_be(buffer, 0, &pos);  /* API number */

        /* Count slots for this IOCR type */
        int slot_count = 0;
        for (int j = 0; j < params->expected_count; j++) {
            bool is_input_iocr = (params->iocr[i].type == IOCR_TYPE_INPUT);
            if (params->expected_config[j].is_input == is_input_iocr) {
                slot_count++;
            }
        }
        write_u16_be(buffer, (uint16_t)slot_count, &pos);

        /* Slot data */
        for (int j = 0; j < params->expected_count; j++) {
            bool is_input_iocr = (params->iocr[i].type == IOCR_TYPE_INPUT);
            if (params->expected_config[j].is_input != is_input_iocr) {
                continue;
            }

            write_u16_be(buffer, params->expected_config[j].slot, &pos);
            write_u16_be(buffer, 1, &pos);  /* Subslot count */
            write_u16_be(buffer, params->expected_config[j].subslot, &pos);
            write_u16_be(buffer, params->expected_config[j].data_length, &pos);

            /* IOCS/IOPS length (consumer status) */
            write_u8(buffer + pos, 1);  /* 1 byte status */
            pos++;
            write_u8(buffer + pos, 1);
            pos++;
        }

        /* Fill IOCR block header */
        size_t iocr_block_len = pos - iocr_block_start - 4;
        save_pos = iocr_block_start;
        write_block_header(buffer, BLOCK_TYPE_IOCR_BLOCK_REQ,
                            (uint16_t)iocr_block_len, &save_pos);
    }

    /* ============== Alarm CR Block Request ============== */
    size_t alarm_block_start = pos;
    pos += 6;  /* Skip header */

    write_u16_be(buffer, 1, &pos);  /* Alarm CR type */
    write_u16_be(buffer, PROFINET_ETHERTYPE, &pos);  /* LT */
    write_u32_be(buffer, 0, &pos);  /* Alarm CR properties */
    write_u16_be(buffer, 100, &pos);  /* RTA timeout factor */
    write_u16_be(buffer, 3, &pos);    /* RTA retries */
    write_u16_be(buffer, 0x0001, &pos);  /* Local alarm reference */
    write_u16_be(buffer, params->max_alarm_data_length, &pos);
    write_u16_be(buffer, 0, &pos);  /* Tag header high */
    write_u16_be(buffer, 0, &pos);  /* Tag header low */

    size_t alarm_block_len = pos - alarm_block_start - 4;
    save_pos = alarm_block_start;
    write_block_header(buffer, BLOCK_TYPE_ALARM_CR_BLOCK_REQ,
                        (uint16_t)alarm_block_len, &save_pos);

    /* ============== Expected Submodule Block ============== */
    size_t exp_block_start = pos;
    pos += 6;  /* Skip header */

    write_u16_be(buffer, 1, &pos);  /* Number of APIs */

    /* API 0 */
    write_u32_be(buffer, 0, &pos);  /* API number */

    /* Count unique slots */
    int unique_slots = 0;
    uint16_t seen_slots[WTC_MAX_SLOTS] = {0};
    for (int j = 0; j < params->expected_count; j++) {
        bool found = false;
        for (int k = 0; k < unique_slots; k++) {
            if (seen_slots[k] == params->expected_config[j].slot) {
                found = true;
                break;
            }
        }
        if (!found && unique_slots < WTC_MAX_SLOTS) {
            seen_slots[unique_slots++] = params->expected_config[j].slot;
        }
    }
    write_u16_be(buffer, (uint16_t)unique_slots, &pos);

    /* Slot/Submodule data */
    for (int s = 0; s < unique_slots; s++) {
        uint16_t slot = seen_slots[s];
        write_u16_be(buffer, slot, &pos);

        /* Find module ident for this slot */
        uint32_t module_ident = 0;
        for (int j = 0; j < params->expected_count; j++) {
            if (params->expected_config[j].slot == slot) {
                module_ident = params->expected_config[j].module_ident;
                break;
            }
        }
        write_u32_be(buffer, module_ident, &pos);

        /* Count subslots in this slot */
        int subslot_count = 0;
        for (int j = 0; j < params->expected_count; j++) {
            if (params->expected_config[j].slot == slot) {
                subslot_count++;
            }
        }
        write_u16_be(buffer, (uint16_t)subslot_count, &pos);

        /* Subslot data */
        for (int j = 0; j < params->expected_count; j++) {
            if (params->expected_config[j].slot != slot) {
                continue;
            }
            write_u16_be(buffer, params->expected_config[j].subslot, &pos);
            write_u32_be(buffer, params->expected_config[j].submodule_ident, &pos);

            /* Submodule properties */
            uint16_t submod_props = params->expected_config[j].is_input ? 0x0001 : 0x0002;
            write_u16_be(buffer, submod_props, &pos);

            /* Data description */
            write_u16_be(buffer, params->expected_config[j].data_length, &pos);
            write_u8(buffer + pos, 1);  /* Length IOCS */
            pos++;
            write_u8(buffer + pos, 1);  /* Length IOPS */
            pos++;
        }
    }

    size_t exp_block_len = pos - exp_block_start - 4;
    save_pos = exp_block_start;
    write_block_header(buffer, BLOCK_TYPE_EXPECTED_SUBMOD_BLOCK,
                        (uint16_t)exp_block_len, &save_pos);

    /* ============== Finalize RPC Header ============== */
    uint16_t fragment_length = (uint16_t)(pos - sizeof(profinet_rpc_header_t));

    /* Generate new activity UUID for this request */
    rpc_generate_uuid(ctx->activity_uuid);

    build_rpc_header(buffer, ctx, params->ar_uuid, RPC_OPNUM_CONNECT,
                      fragment_length, &save_pos);

    *buf_len = pos;
    LOG_DEBUG("Built Connect Request PDU: %zu bytes", pos);
    return WTC_OK;
}

wtc_result_t rpc_parse_connect_response(const uint8_t *buffer,
                                         size_t buf_len,
                                         connect_response_t *response)
{
    if (!buffer || !response || buf_len < sizeof(profinet_rpc_header_t)) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memset(response, 0, sizeof(connect_response_t));

    const profinet_rpc_header_t *hdr = (const profinet_rpc_header_t *)buffer;

    /* Check packet type */
    if (hdr->packet_type == RPC_PACKET_TYPE_FAULT) {
        LOG_ERROR("Connect response: RPC fault received");
        response->success = false;
        response->error_code = PNIO_ERR_CODE_CONNECT;
        return WTC_ERROR_PROTOCOL;
    }

    if (hdr->packet_type != RPC_PACKET_TYPE_RESPONSE) {
        LOG_ERROR("Connect response: unexpected packet type %u", hdr->packet_type);
        response->success = false;
        return WTC_ERROR_PROTOCOL;
    }

    size_t pos = sizeof(profinet_rpc_header_t);

    /* Parse blocks */
    while (pos + 6 <= buf_len) {
        uint16_t block_type = read_u16_be(buffer, &pos);
        uint16_t block_length = read_u16_be(buffer, &pos);
        uint8_t version_high = buffer[pos++];
        uint8_t version_low = buffer[pos++];
        (void)version_high;
        (void)version_low;

        size_t block_end = pos + block_length - 2;  /* -2 for version bytes */

        switch (block_type) {
        case BLOCK_TYPE_AR_BLOCK_RES: {
            /* AR type */
            pos += 2;  /* Skip AR type */

            /* AR UUID */
            memcpy(response->ar_uuid, buffer + pos, 16);
            pos += 16;

            /* Session key */
            response->session_key = read_u16_be(buffer, &pos);

            /* Device MAC */
            memcpy(response->device_mac, buffer + pos, 6);
            pos += 6;

            /* Device port */
            response->device_port = read_u16_be(buffer, &pos);

            response->success = true;
            LOG_DEBUG("AR Block Response: session_key=%u, device_port=%u",
                      response->session_key, response->device_port);
            break;
        }

        case BLOCK_TYPE_IOCR_BLOCK_RES: {
            if (response->frame_id_count < 4) {
                pos += 2;  /* Skip IOCR type */
                uint16_t iocr_ref = read_u16_be(buffer, &pos);
                uint16_t frame_id = read_u16_be(buffer, &pos);

                response->frame_ids[response->frame_id_count].requested = iocr_ref;
                response->frame_ids[response->frame_id_count].assigned = frame_id;
                response->frame_id_count++;

                LOG_DEBUG("IOCR Block Response: ref=%u, frame_id=0x%04X",
                          iocr_ref, frame_id);
            }
            break;
        }

        case BLOCK_TYPE_ALARM_CR_BLOCK_RES: {
            pos += 2;  /* Skip alarm CR type */
            response->device_alarm_ref = read_u16_be(buffer, &pos);
            LOG_DEBUG("Alarm CR Block Response: alarm_ref=%u",
                      response->device_alarm_ref);
            break;
        }

        case BLOCK_TYPE_MODULE_DIFF_BLOCK: {
            response->has_diff = true;
            uint16_t api_count = read_u16_be(buffer, &pos);
            LOG_WARN("Module Diff Block: %u APIs with differences", api_count);
            response->diff_count = api_count;
            break;
        }

        default:
            LOG_DEBUG("Unknown block type 0x%04X, skipping", block_type);
            break;
        }

        pos = block_end;
        align_to_4(&pos);
    }

    if (!response->success) {
        LOG_ERROR("Connect response: no AR block found");
        return WTC_ERROR_PROTOCOL;
    }

    LOG_INFO("Connect response parsed successfully");
    return WTC_OK;
}

wtc_result_t rpc_build_control_request(rpc_context_t *ctx,
                                        const uint8_t *ar_uuid,
                                        uint16_t session_key,
                                        uint16_t control_command,
                                        uint8_t *buffer,
                                        size_t *buf_len)
{
    if (!ctx || !ar_uuid || !buffer || !buf_len) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (*buf_len < RPC_MAX_PDU_SIZE) {
        return WTC_ERROR_NO_MEMORY;
    }

    size_t pos = sizeof(profinet_rpc_header_t);

    /* IOD Control Request Block */
    size_t block_start = pos;
    pos += 6;  /* Skip header */

    write_u16_be(buffer, 0, &pos);  /* Reserved */
    memcpy(buffer + pos, ar_uuid, 16);
    pos += 16;
    write_u16_be(buffer, session_key, &pos);
    write_u16_be(buffer, 0, &pos);  /* Reserved */
    write_u16_be(buffer, control_command, &pos);
    write_u16_be(buffer, 0, &pos);  /* Control block properties */

    size_t block_len = pos - block_start - 4;
    size_t save_pos = block_start;
    write_block_header(buffer, BLOCK_TYPE_IOD_CONTROL_REQ,
                        (uint16_t)block_len, &save_pos);

    /* Build RPC header */
    uint16_t fragment_length = (uint16_t)(pos - sizeof(profinet_rpc_header_t));
    rpc_generate_uuid(ctx->activity_uuid);
    build_rpc_header(buffer, ctx, ar_uuid, RPC_OPNUM_CONTROL,
                      fragment_length, &save_pos);

    *buf_len = pos;

    const char *cmd_name = "unknown";
    switch (control_command) {
    case CONTROL_CMD_PRM_END:
        cmd_name = "ParameterEnd";
        break;
    case CONTROL_CMD_APP_READY:
        cmd_name = "ApplicationReady";
        break;
    case CONTROL_CMD_RELEASE:
        cmd_name = "Release";
        break;
    }
    LOG_DEBUG("Built %s request: %zu bytes", cmd_name, pos);
    return WTC_OK;
}

wtc_result_t rpc_parse_control_response(const uint8_t *buffer,
                                         size_t buf_len,
                                         uint16_t expected_command,
                                         bool *success)
{
    if (!buffer || !success || buf_len < sizeof(profinet_rpc_header_t)) {
        return WTC_ERROR_INVALID_PARAM;
    }

    *success = false;

    const profinet_rpc_header_t *hdr = (const profinet_rpc_header_t *)buffer;

    if (hdr->packet_type == RPC_PACKET_TYPE_FAULT) {
        LOG_ERROR("Control response: RPC fault");
        return WTC_ERROR_PROTOCOL;
    }

    if (hdr->packet_type != RPC_PACKET_TYPE_RESPONSE) {
        LOG_ERROR("Control response: unexpected packet type %u", hdr->packet_type);
        return WTC_ERROR_PROTOCOL;
    }

    size_t pos = sizeof(profinet_rpc_header_t);

    /* Parse control response block */
    if (pos + 6 > buf_len) {
        return WTC_ERROR_PROTOCOL;
    }

    uint16_t block_type = read_u16_be(buffer, &pos);
    if (block_type != BLOCK_TYPE_IOD_CONTROL_RES) {
        LOG_ERROR("Control response: unexpected block type 0x%04X", block_type);
        return WTC_ERROR_PROTOCOL;
    }

    uint16_t block_length = read_u16_be(buffer, &pos);
    (void)block_length;
    pos += 2;  /* Version */
    pos += 2;  /* Reserved */
    pos += 16; /* AR UUID */
    pos += 2;  /* Session key */
    pos += 2;  /* Reserved */

    uint16_t control_command = read_u16_be(buffer, &pos);

    if (control_command != expected_command) {
        LOG_WARN("Control response: command mismatch, expected %u got %u",
                 expected_command, control_command);
    }

    *success = true;
    LOG_DEBUG("Control response: command %u confirmed", control_command);
    return WTC_OK;
}

wtc_result_t rpc_build_release_request(rpc_context_t *ctx,
                                        const uint8_t *ar_uuid,
                                        uint16_t session_key,
                                        uint8_t *buffer,
                                        size_t *buf_len)
{
    return rpc_build_control_request(ctx, ar_uuid, session_key,
                                      CONTROL_CMD_RELEASE, buffer, buf_len);
}

wtc_result_t rpc_send_and_receive(rpc_context_t *ctx,
                                   uint32_t device_ip,
                                   const uint8_t *request,
                                   size_t req_len,
                                   uint8_t *response,
                                   size_t *resp_len,
                                   uint32_t timeout_ms)
{
    if (!ctx || !request || !response || !resp_len) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (ctx->socket_fd < 0) {
        LOG_ERROR("RPC socket not initialized");
        return WTC_ERROR_IO;
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(PNIO_RPC_PORT);
    addr.sin_addr.s_addr = device_ip;

    /* Send request */
    ssize_t sent = sendto(ctx->socket_fd, request, req_len, 0,
                          (struct sockaddr *)&addr, sizeof(addr));
    if (sent < 0) {
        LOG_ERROR("RPC send failed: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    LOG_DEBUG("RPC request sent: %zd bytes to %08X:%u",
              sent, ntohl(device_ip), PNIO_RPC_PORT);

    /* Wait for response */
    struct pollfd pfd;
    pfd.fd = ctx->socket_fd;
    pfd.events = POLLIN;

    int poll_result = poll(&pfd, 1, (int)timeout_ms);
    if (poll_result < 0) {
        LOG_ERROR("RPC poll failed: %s", strerror(errno));
        return WTC_ERROR_IO;
    }
    if (poll_result == 0) {
        LOG_WARN("RPC timeout after %u ms", timeout_ms);
        return WTC_ERROR_TIMEOUT;
    }

    /* Receive response */
    socklen_t addr_len = sizeof(addr);
    ssize_t received = recvfrom(ctx->socket_fd, response, *resp_len, 0,
                                 (struct sockaddr *)&addr, &addr_len);
    if (received < 0) {
        LOG_ERROR("RPC receive failed: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    *resp_len = (size_t)received;
    LOG_DEBUG("RPC response received: %zd bytes", received);
    return WTC_OK;
}

wtc_result_t rpc_connect(rpc_context_t *ctx,
                          uint32_t device_ip,
                          const connect_request_params_t *params,
                          connect_response_t *response)
{
    if (!ctx || !params || !response) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint8_t req_buf[RPC_MAX_PDU_SIZE];
    uint8_t resp_buf[RPC_MAX_PDU_SIZE];
    size_t req_len = sizeof(req_buf);
    size_t resp_len = sizeof(resp_buf);

    wtc_result_t res;

    /* Build connect request */
    res = rpc_build_connect_request(ctx, params, req_buf, &req_len);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to build connect request");
        return res;
    }

    /* Send and receive */
    res = rpc_send_and_receive(ctx, device_ip, req_buf, req_len,
                                resp_buf, &resp_len, RPC_CONNECT_TIMEOUT_MS);
    if (res != WTC_OK) {
        LOG_ERROR("Connect RPC failed");
        return res;
    }

    /* Parse response */
    res = rpc_parse_connect_response(resp_buf, resp_len, response);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to parse connect response");
        return res;
    }

    LOG_INFO("RPC Connect successful to %08X", ntohl(device_ip));
    return WTC_OK;
}

wtc_result_t rpc_parameter_end(rpc_context_t *ctx,
                                uint32_t device_ip,
                                const uint8_t *ar_uuid,
                                uint16_t session_key)
{
    if (!ctx || !ar_uuid) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint8_t req_buf[RPC_MAX_PDU_SIZE];
    uint8_t resp_buf[RPC_MAX_PDU_SIZE];
    size_t req_len = sizeof(req_buf);
    size_t resp_len = sizeof(resp_buf);
    bool success = false;

    wtc_result_t res;

    res = rpc_build_control_request(ctx, ar_uuid, session_key,
                                     CONTROL_CMD_PRM_END, req_buf, &req_len);
    if (res != WTC_OK) {
        return res;
    }

    res = rpc_send_and_receive(ctx, device_ip, req_buf, req_len,
                                resp_buf, &resp_len, RPC_CONTROL_TIMEOUT_MS);
    if (res != WTC_OK) {
        return res;
    }

    res = rpc_parse_control_response(resp_buf, resp_len,
                                      CONTROL_CMD_PRM_END, &success);
    if (res != WTC_OK || !success) {
        LOG_ERROR("ParameterEnd failed");
        return res != WTC_OK ? res : WTC_ERROR_PROTOCOL;
    }

    LOG_INFO("ParameterEnd successful");
    return WTC_OK;
}

wtc_result_t rpc_application_ready(rpc_context_t *ctx,
                                    uint32_t device_ip,
                                    const uint8_t *ar_uuid,
                                    uint16_t session_key)
{
    if (!ctx || !ar_uuid) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint8_t req_buf[RPC_MAX_PDU_SIZE];
    uint8_t resp_buf[RPC_MAX_PDU_SIZE];
    size_t req_len = sizeof(req_buf);
    size_t resp_len = sizeof(resp_buf);
    bool success = false;

    wtc_result_t res;

    res = rpc_build_control_request(ctx, ar_uuid, session_key,
                                     CONTROL_CMD_APP_READY, req_buf, &req_len);
    if (res != WTC_OK) {
        return res;
    }

    res = rpc_send_and_receive(ctx, device_ip, req_buf, req_len,
                                resp_buf, &resp_len, RPC_CONTROL_TIMEOUT_MS);
    if (res != WTC_OK) {
        return res;
    }

    res = rpc_parse_control_response(resp_buf, resp_len,
                                      CONTROL_CMD_APP_READY, &success);
    if (res != WTC_OK || !success) {
        LOG_ERROR("ApplicationReady failed");
        return res != WTC_OK ? res : WTC_ERROR_PROTOCOL;
    }

    LOG_INFO("ApplicationReady successful");
    return WTC_OK;
}

wtc_result_t rpc_release(rpc_context_t *ctx,
                          uint32_t device_ip,
                          const uint8_t *ar_uuid,
                          uint16_t session_key)
{
    if (!ctx || !ar_uuid) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint8_t req_buf[RPC_MAX_PDU_SIZE];
    uint8_t resp_buf[RPC_MAX_PDU_SIZE];
    size_t req_len = sizeof(req_buf);
    size_t resp_len = sizeof(resp_buf);
    bool success = false;

    wtc_result_t res;

    res = rpc_build_release_request(ctx, ar_uuid, session_key,
                                     req_buf, &req_len);
    if (res != WTC_OK) {
        return res;
    }

    res = rpc_send_and_receive(ctx, device_ip, req_buf, req_len,
                                resp_buf, &resp_len, RPC_CONTROL_TIMEOUT_MS);
    if (res != WTC_OK) {
        /* Release can timeout if device already disconnected - not an error */
        LOG_WARN("Release RPC did not receive response (device may be offline)");
        return WTC_OK;
    }

    res = rpc_parse_control_response(resp_buf, resp_len,
                                      CONTROL_CMD_RELEASE, &success);
    if (res != WTC_OK) {
        LOG_WARN("Release response parse failed");
        return WTC_OK;  /* Still consider release successful */
    }

    LOG_INFO("Release successful");
    return WTC_OK;
}
