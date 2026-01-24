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

/* For htole16/htole32 (host to little-endian) - portable byte order conversion */
#ifdef __linux__
#include <endian.h>
#elif defined(__APPLE__)
#include <libkern/OSByteOrder.h>
#define htole16(x) OSSwapHostToLittleInt16(x)
#define htole32(x) OSSwapHostToLittleInt32(x)
#elif defined(_WIN32)
/* Windows is always little-endian on supported architectures */
#define htole16(x) (x)
#define htole32(x) (x)
#else
/* Fallback: assume little-endian, but warn at compile time */
#warning "Unknown platform - assuming little-endian byte order"
#define htole16(x) (x)
#define htole32(x) (x)
#endif

/* ============== Constants ============== */

/* RPC timeouts */
#define RPC_CONNECT_TIMEOUT_MS      5000
#define RPC_CONTROL_TIMEOUT_MS      3000
#define RPC_DEFAULT_TIMEOUT_MS      5000

/* Buffer sizes */
#define RPC_HEADER_SIZE             80

/* Block version */
#define BLOCK_VERSION_HIGH          1
#define BLOCK_VERSION_LOW           0

/*
 * PROFINET IO Device Interface UUID: DEA00001-6C97-11D1-8271-00A02442DF7D
 *
 * DCE-RPC UUID wire format with drep=little-endian (0x10):
 * - data1 (uint32): 0xDEA00001 → little-endian bytes: 01 00 A0 DE
 * - data2 (uint16): 0x6C97 → little-endian bytes: 97 6C
 * - data3 (uint16): 0x11D1 → little-endian bytes: D1 11
 * - data4 (8 bytes): unchanged: 82 71 00 A0 24 42 DF 7D
 */
const uint8_t PNIO_DEVICE_INTERFACE_UUID[16] = {
    0x01, 0x00, 0xA0, 0xDE,  /* data1: 0xDEA00001 LE */
    0x97, 0x6C,              /* data2: 0x6C97 LE */
    0xD1, 0x11,              /* data3: 0x11D1 LE */
    0x82, 0x71, 0x00, 0xA0, 0x24, 0x42, 0xDF, 0x7D  /* data4: unchanged */
};

/*
 * PROFINET IO Controller Interface UUID: DEA00002-6C97-11D1-8271-00A02442DF7D
 * Same format as above but with data1 = 0xDEA00002
 */
const uint8_t PNIO_CONTROLLER_INTERFACE_UUID[16] = {
    0x02, 0x00, 0xA0, 0xDE,  /* data1: 0xDEA00002 LE */
    0x97, 0x6C,              /* data2: 0x6C97 LE */
    0xD1, 0x11,              /* data3: 0x11D1 LE */
    0x82, 0x71, 0x00, 0xA0, 0x24, 0x42, 0xDF, 0x7D  /* data4: unchanged */
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
 * @brief Write uint32 in network byte order (big-endian) to buffer.
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
 * @brief Write uint32 in little-endian byte order to buffer.
 *
 * Used for NDR header fields when drep=little-endian.
 *
 * @param[out] buf   Destination buffer
 * @param[in]  val   Value to write
 * @param[in,out] pos Current position, incremented by 4
 *
 * @note Thread safety: SAFE
 * @note Memory: NO_ALLOC
 */
static void write_u32_le(uint8_t *buf, uint32_t val, size_t *pos)
{
    uint32_t le = htole32(val);
    memcpy(buf + *pos, &le, 4);
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
    /*
     * drep[0] = RPC_DREP_LITTLE_ENDIAN means all multi-byte fields must be
     * little-endian on the wire. Use htole16/htole32 for portability:
     * - On little-endian (x86, most ARM): no-op
     * - On big-endian (some ARM, PowerPC): byte-swap
     */
    hdr->interface_version = htole32(1);
    hdr->sequence_number = htole32(ctx->sequence_number);
    ctx->sequence_number++;

    hdr->opnum = htole16(opnum);
    hdr->interface_hint = htole16(0xFFFF);
    hdr->activity_hint = htole16(0xFFFF);
    hdr->fragment_length = htole16(fragment_length);
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

    /* Bind to local port (any available on all interfaces) */
    struct sockaddr_in local_addr;
    memset(&local_addr, 0, sizeof(local_addr));
    local_addr.sin_family = AF_INET;
    local_addr.sin_addr.s_addr = INADDR_ANY;  /* Listen on all interfaces */
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

    /*
     * Connect Request structure (per IEC 61158-6 / PN-AL-Protocol 4.10.3.4):
     * - NDR Header (20 bytes, little-endian per drep)
     *   - ArgsMaximum (4 bytes)
     *   - ArgsLength (4 bytes)
     *   - MaxCount (4 bytes)
     *   - Offset (4 bytes) - always 0
     *   - ActualCount (4 bytes)
     * - PNIO Blocks (big-endian per PROFINET spec):
     *   - AR Block Request
     *   - IOCR Block Request(s)
     *   - Alarm CR Block Request
     *   - Expected Submodule Block(s)
     */

    /* Reserve space for NDR header - fill in after we know block lengths */
    size_t ndr_header_pos = pos;
    pos += 20;  /* 5 x uint32 = 20 bytes */

    /* Track start of PNIO blocks for length calculation */
    size_t pnio_blocks_start = pos;

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

    /* Calculate block length: 54 + station_name_length
     * = 2 (version) + 52 (fixed fields) + name_len */
    size_t ar_block_len = pos - ar_block_start - 4;  /* Exclude type + length */

    /* Fill AR block header - NO padding between blocks, they must be contiguous */
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
        write_u16_be(buffer, 1, &pos);  /* Phase: must be >= 1 and <= reduction_ratio */
        write_u16_be(buffer, 0, &pos);  /* Sequence (deprecated) */
        write_u32_be(buffer, 0, &pos);  /* Frame send offset */
        write_u16_be(buffer, params->iocr[i].watchdog_factor, &pos);
        write_u16_be(buffer, 3, &pos);  /* Data hold factor */
        write_u16_be(buffer, 0, &pos);  /* IOCR tag header */
        memset(buffer + pos, 0, 6);     /* Multicast MAC (not used) */
        pos += 6;

        /* API section - structure per PROFINET spec / p-net pf_get_iocr_api_entry() */
        write_u16_be(buffer, 1, &pos);  /* Number of APIs */

        /* API 0 */
        write_u32_be(buffer, 0, &pos);  /* API number */

        /*
         * Count IODataObjects for this IOCR type.
         * Skip entries with data_length == 0 (e.g., DAP slot 0) - they don't
         * have cyclic I/O data and shouldn't be in the IOCR data mapping.
         */
        int io_data_count = 0;
        for (int j = 0; j < params->expected_count; j++) {
            bool is_input_iocr = (params->iocr[i].type == IOCR_TYPE_INPUT);
            if (params->expected_config[j].is_input == is_input_iocr &&
                params->expected_config[j].data_length > 0) {
                io_data_count++;
            }
        }
        write_u16_be(buffer, (uint16_t)io_data_count, &pos);  /* NumberOfIODataObjects */

        /* IODataObjects - each has slot, subslot, frame_offset */
        uint16_t frame_offset = 0;
        for (int j = 0; j < params->expected_count; j++) {
            bool is_input_iocr = (params->iocr[i].type == IOCR_TYPE_INPUT);
            /* Skip non-matching direction and zero-length entries (DAP) */
            if (params->expected_config[j].is_input != is_input_iocr ||
                params->expected_config[j].data_length == 0) {
                continue;
            }

            write_u16_be(buffer, params->expected_config[j].slot, &pos);
            write_u16_be(buffer, params->expected_config[j].subslot, &pos);
            write_u16_be(buffer, frame_offset, &pos);  /* IODataObjectFrameOffset */
            frame_offset += params->expected_config[j].data_length;
        }

        /* IOCS section - same slots but for consumer status */
        write_u16_be(buffer, (uint16_t)io_data_count, &pos);  /* NumberOfIOCS */

        frame_offset = 0;
        for (int j = 0; j < params->expected_count; j++) {
            bool is_input_iocr = (params->iocr[i].type == IOCR_TYPE_INPUT);
            /* Skip non-matching direction and zero-length entries (DAP) */
            if (params->expected_config[j].is_input != is_input_iocr ||
                params->expected_config[j].data_length == 0) {
                continue;
            }

            write_u16_be(buffer, params->expected_config[j].slot, &pos);
            write_u16_be(buffer, params->expected_config[j].subslot, &pos);
            write_u16_be(buffer, frame_offset, &pos);  /* IOCS FrameOffset */
            frame_offset += 1;  /* IOCS is 1 byte per submodule */
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
    /*
     * Alarm CR Tag Headers (VLAN priority for alarm frames):
     * Format: Priority (3 bits) << 13 | DEI (1 bit) << 12 | VLAN_ID (12 bits)
     * High priority = 6 (0xC000), Low priority = 5 (0xA000)
     */
    write_u16_be(buffer, 0xC000, &pos);  /* Tag header high: priority 6 */
    write_u16_be(buffer, 0xA000, &pos);  /* Tag header low: priority 5 */

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

    /* ============== Fill NDR Header ============== */

    /*
     * NDR header fields (little-endian per drep):
     * - ArgsMaximum: max buffer size for response (use same as ArgsLength)
     * - ArgsLength: length of PNIO blocks that follow
     * - MaxCount: NDR array max (same as ArgsLength for conformant array)
     * - Offset: always 0
     * - ActualCount: actual length (same as ArgsLength)
     */
    uint32_t pnio_blocks_len = (uint32_t)(pos - pnio_blocks_start);
    size_t ndr_pos = ndr_header_pos;
    write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  /* ArgsMaximum */
    write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  /* ArgsLength */
    write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  /* MaxCount */
    write_u32_le(buffer, 0, &ndr_pos);                /* Offset - always 0 */
    write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  /* ActualCount */

    LOG_DEBUG("NDR header: ArgsLen=%u bytes of PNIO blocks", pnio_blocks_len);

    /* ============== Finalize RPC Header ============== */

    /* Verify we didn't exceed buffer size */
    if (pos > RPC_MAX_PDU_SIZE) {
        LOG_ERROR("Connect Request PDU too large: %zu bytes (max %d)",
                  pos, RPC_MAX_PDU_SIZE);
        return WTC_ERROR_NO_MEMORY;
    }

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

    LOG_INFO("Connect response: total_len=%zu bytes (RPC hdr=%zu, need NDR=%zu)",
             buf_len, pos, pos + 20);

    /*
     * PNIO Connect Response NDR format (after RPC header):
     * - ArgsMaximum (4 bytes, always 0)
     * - ArgsLength (4 bytes) - length of PNIO data
     * - MaxCount (4 bytes) - NDR array max
     * - Offset (4 bytes) - NDR array offset (always 0)
     * - ActualCount (4 bytes) - NDR array actual count
     * - Then the PNIO blocks (ARBlockRes, IOCRBlockRes, etc.)
     *
     * Note: There is NO error status in this header. PNIO errors are
     * indicated by RPC FAULT packet type or missing/invalid blocks.
     */
    if (pos + 20 > buf_len) {
        LOG_ERROR("Connect response too short for NDR header: got %zu bytes, need %zu",
                  buf_len, pos + 20);
        /* Log first bytes for diagnosis */
        if (buf_len >= 4) {
            LOG_ERROR("Response first 4 bytes: %02X %02X %02X %02X",
                      buffer[0], buffer[1], buffer[2], buffer[3]);
        }
        return WTC_ERROR_PROTOCOL;
    }

    /* Parse NDR header - values are little-endian */
    uint32_t args_maximum = buffer[pos] | (buffer[pos+1] << 8) |
                            (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
    pos += 4;
    (void)args_maximum;

    uint32_t args_length = buffer[pos] | (buffer[pos+1] << 8) |
                           (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
    pos += 4;

    uint32_t max_count = buffer[pos] | (buffer[pos+1] << 8) |
                         (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
    pos += 4;

    pos += 4;  /* Skip offset (always 0) */

    uint32_t actual_count = buffer[pos] | (buffer[pos+1] << 8) |
                            (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
    pos += 4;

    LOG_DEBUG("Connect response NDR: args_len=%u, max=%u, actual=%u",
              args_length, max_count, actual_count);

    if (actual_count == 0 || args_length == 0) {
        LOG_ERROR("Connect response: empty PNIO data (args_len=%u, actual=%u)",
                  args_length, actual_count);

        /* Dump raw response for diagnosis */
        LOG_ERROR("RPC header: version=%u type=%u flags1=0x%02X flags2=0x%02X",
                  hdr->version, hdr->packet_type, hdr->flags1, hdr->flags2);
        LOG_ERROR("RPC header: frag_num=%u opnum=%u frag_len=%u",
                  hdr->fragment_number, hdr->opnum, hdr->fragment_length);

        /* Dump first 40 bytes as hex for analysis */
        char hex_dump[128];
        size_t dump_len = buf_len < 40 ? buf_len : 40;
        for (size_t i = 0; i < dump_len && i * 3 < sizeof(hex_dump) - 1; i++) {
            snprintf(hex_dump + i * 3, 4, "%02X ", buffer[i]);
        }
        LOG_ERROR("Response hex (first %zu bytes): %s", dump_len, hex_dump);

        /* Check if this might be a PNIO error response */
        /* The NDR ArgsMaximum field might contain error info in some implementations */
        LOG_ERROR("NDR ArgsMaximum=0x%08X (might contain status)", args_maximum);

        response->success = false;
        response->error_code = PNIO_ERR_CODE_CONNECT;
        return WTC_ERROR_PROTOCOL;
    }

    /* Parse blocks */
    while (pos + 6 <= buf_len) {
        uint16_t block_type = read_u16_be(buffer, &pos);
        uint16_t block_length = read_u16_be(buffer, &pos);
        uint8_t version_high = buffer[pos++];
        uint8_t version_low = buffer[pos++];
        (void)version_high;
        (void)version_low;

        /* Validate block length (must be at least 2 for version bytes) */
        if (block_length < 2) {
            LOG_WARN("Invalid block length %u for block type 0x%04X",
                     block_length, block_type);
            break;
        }

        size_t block_end = pos + block_length - 2;  /* -2 for version bytes already read */
        if (block_end > buf_len) {
            LOG_WARN("Block extends past buffer end");
            break;
        }

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

    /* Reserve space for NDR header (20 bytes) */
    size_t ndr_header_pos = pos;
    pos += 20;

    /* Track start of PNIO blocks */
    size_t pnio_blocks_start = pos;

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

    /* Fill NDR header (little-endian per drep) */
    uint32_t pnio_blocks_len = (uint32_t)(pos - pnio_blocks_start);
    size_t ndr_pos = ndr_header_pos;
    write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  /* ArgsMaximum */
    write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  /* ArgsLength */
    write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  /* MaxCount */
    write_u32_le(buffer, 0, &ndr_pos);                /* Offset */
    write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  /* ActualCount */

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
    addr.sin_addr.s_addr = htonl(device_ip);  /* Convert host to network byte order */

    /* Send request */
    ssize_t sent = sendto(ctx->socket_fd, request, req_len, 0,
                          (struct sockaddr *)&addr, sizeof(addr));
    if (sent < 0) {
        LOG_ERROR("RPC send failed: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    LOG_DEBUG("RPC request sent: %zd bytes to %d.%d.%d.%d:%u",
              sent,
              (device_ip >> 24) & 0xFF, (device_ip >> 16) & 0xFF,
              (device_ip >> 8) & 0xFF, device_ip & 0xFF,
              PNIO_RPC_PORT);

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
    LOG_INFO("RPC response received: %zd bytes from %d.%d.%d.%d",
             received,
             ntohl(addr.sin_addr.s_addr) >> 24,
             (ntohl(addr.sin_addr.s_addr) >> 16) & 0xFF,
             (ntohl(addr.sin_addr.s_addr) >> 8) & 0xFF,
             ntohl(addr.sin_addr.s_addr) & 0xFF);
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

/* ============== RPC Server Functions (receive callbacks from device) ============== */

wtc_result_t rpc_poll_incoming(rpc_context_t *ctx,
                                uint8_t *buffer,
                                size_t buf_size,
                                size_t *recv_len,
                                uint32_t *source_ip,
                                uint16_t *source_port)
{
    if (!ctx || !buffer || !recv_len || !source_ip || !source_port) {
        return WTC_ERROR_INVALID_PARAM;
    }

    *recv_len = 0;

    if (ctx->socket_fd < 0) {
        return WTC_ERROR_NOT_INITIALIZED;
    }

    /* Non-blocking poll */
    struct pollfd pfd;
    pfd.fd = ctx->socket_fd;
    pfd.events = POLLIN;

    int poll_result = poll(&pfd, 1, 0);  /* 0 = non-blocking */
    if (poll_result < 0) {
        if (errno == EINTR) {
            return WTC_OK;  /* Interrupted, no data */
        }
        LOG_ERROR("RPC poll failed: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    if (poll_result == 0) {
        return WTC_OK;  /* No data available */
    }

    /* Data available, receive it */
    struct sockaddr_in src_addr;
    socklen_t addr_len = sizeof(src_addr);

    ssize_t received = recvfrom(ctx->socket_fd, buffer, buf_size, 0,
                                 (struct sockaddr *)&src_addr, &addr_len);
    if (received < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            return WTC_OK;  /* No data */
        }
        LOG_ERROR("RPC recvfrom failed: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    *recv_len = (size_t)received;
    *source_ip = src_addr.sin_addr.s_addr;
    *source_port = ntohs(src_addr.sin_port);

    LOG_DEBUG("RPC received %zd bytes from %d.%d.%d.%d:%u",
              received,
              (*source_ip) & 0xFF, (*source_ip >> 8) & 0xFF,
              (*source_ip >> 16) & 0xFF, (*source_ip >> 24) & 0xFF,
              *source_port);

    return WTC_OK;
}

wtc_result_t rpc_parse_incoming_control_request(const uint8_t *buffer,
                                                  size_t buf_len,
                                                  incoming_control_request_t *request)
{
    if (!buffer || !request || buf_len < sizeof(profinet_rpc_header_t)) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memset(request, 0, sizeof(incoming_control_request_t));

    const profinet_rpc_header_t *hdr = (const profinet_rpc_header_t *)buffer;

    /* Check packet type - should be REQUEST from device */
    if (hdr->packet_type != RPC_PACKET_TYPE_REQUEST) {
        LOG_DEBUG("Incoming RPC: not a request (type=%u)", hdr->packet_type);
        return WTC_ERROR_PROTOCOL;
    }

    /* Check opnum - should be CONTROL for ApplicationReady */
    uint16_t opnum = ntohs(hdr->opnum);
    if (opnum != RPC_OPNUM_CONTROL) {
        LOG_DEBUG("Incoming RPC: unexpected opnum %u (expected CONTROL=%u)",
                  opnum, RPC_OPNUM_CONTROL);
        return WTC_ERROR_PROTOCOL;
    }

    /* Save activity UUID and sequence for response */
    memcpy(request->activity_uuid, hdr->activity_uuid, 16);
    request->sequence_number = ntohl(hdr->sequence_number);

    /* Parse the IOD Control Request block */
    size_t pos = sizeof(profinet_rpc_header_t);

    if (pos + 6 > buf_len) {
        LOG_ERROR("Incoming control request too short for block header");
        return WTC_ERROR_PROTOCOL;
    }

    uint16_t block_type = read_u16_be(buffer, &pos);
    if (block_type != BLOCK_TYPE_IOD_CONTROL_REQ) {
        LOG_ERROR("Incoming control request: unexpected block type 0x%04X", block_type);
        return WTC_ERROR_PROTOCOL;
    }

    uint16_t block_length = read_u16_be(buffer, &pos);
    (void)block_length;

    pos += 2;  /* Version */
    pos += 2;  /* Reserved */

    if (pos + 16 > buf_len) {
        return WTC_ERROR_PROTOCOL;
    }
    memcpy(request->ar_uuid, buffer + pos, 16);
    pos += 16;

    if (pos + 2 > buf_len) {
        return WTC_ERROR_PROTOCOL;
    }
    request->session_key = read_u16_be(buffer, &pos);

    pos += 2;  /* Reserved */

    if (pos + 2 > buf_len) {
        return WTC_ERROR_PROTOCOL;
    }
    request->control_command = read_u16_be(buffer, &pos);

    const char *cmd_name = "unknown";
    switch (request->control_command) {
    case CONTROL_CMD_PRM_END:
        cmd_name = "PrmEnd";
        break;
    case CONTROL_CMD_APP_READY:
        cmd_name = "ApplicationReady";
        break;
    case CONTROL_CMD_RELEASE:
        cmd_name = "Release";
        break;
    }

    LOG_INFO("Received incoming %s request (session_key=%u)",
             cmd_name, request->session_key);

    return WTC_OK;
}

wtc_result_t rpc_build_control_response(rpc_context_t *ctx,
                                         const incoming_control_request_t *request,
                                         uint8_t *buffer,
                                         size_t *buf_len)
{
    if (!ctx || !request || !buffer || !buf_len) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (*buf_len < RPC_MAX_PDU_SIZE) {
        return WTC_ERROR_NO_MEMORY;
    }

    /* Build RPC header for RESPONSE */
    profinet_rpc_header_t *hdr = (profinet_rpc_header_t *)buffer;
    memset(hdr, 0, sizeof(profinet_rpc_header_t));

    hdr->version = RPC_VERSION_MAJOR;
    hdr->packet_type = RPC_PACKET_TYPE_RESPONSE;
    hdr->flags1 = RPC_FLAG1_LAST_FRAGMENT | RPC_FLAG1_IDEMPOTENT;
    hdr->flags2 = 0;
    hdr->drep[0] = RPC_DREP_LITTLE_ENDIAN;
    hdr->drep[1] = RPC_DREP_ASCII;
    hdr->drep[2] = 0;
    hdr->serial_high = 0;

    /* Object UUID (AR UUID) */
    memcpy(hdr->object_uuid, request->ar_uuid, 16);

    /* Interface UUID - use Controller interface for response */
    memcpy(hdr->interface_uuid, PNIO_CONTROLLER_INTERFACE_UUID, 16);

    /* Activity UUID - must match the request */
    memcpy(hdr->activity_uuid, request->activity_uuid, 16);

    hdr->server_boot = 0;
    /* RPC header fields use little-endian per drep */
    hdr->interface_version = htole32(1);
    hdr->sequence_number = htole32(request->sequence_number);

    hdr->opnum = htole16(RPC_OPNUM_CONTROL);
    hdr->interface_hint = htole16(0xFFFF);
    hdr->activity_hint = htole16(0xFFFF);

    size_t pos = sizeof(profinet_rpc_header_t);

    /* Reserve space for NDR header */
    size_t ndr_header_pos = pos;
    pos += 20;

    /* Track start of PNIO blocks */
    size_t pnio_blocks_start = pos;

    /* Build IOD Control Response block */
    size_t block_start = pos;
    pos += 6;  /* Skip header, fill later */

    write_u16_be(buffer, 0, &pos);  /* Reserved */
    memcpy(buffer + pos, request->ar_uuid, 16);
    pos += 16;
    write_u16_be(buffer, request->session_key, &pos);
    write_u16_be(buffer, 0, &pos);  /* Reserved */
    write_u16_be(buffer, request->control_command, &pos);  /* Echo command */
    write_u16_be(buffer, 0, &pos);  /* Control block properties */

    /* Fill block header */
    size_t block_len = pos - block_start - 4;
    size_t save_pos = block_start;
    write_block_header(buffer, BLOCK_TYPE_IOD_CONTROL_RES,
                        (uint16_t)block_len, &save_pos);

    /* Fill NDR header (little-endian per drep) */
    uint32_t pnio_blocks_len = (uint32_t)(pos - pnio_blocks_start);
    size_t ndr_pos = ndr_header_pos;
    write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  /* ArgsMaximum */
    write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  /* ArgsLength */
    write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  /* MaxCount */
    write_u32_le(buffer, 0, &ndr_pos);                /* Offset */
    write_u32_le(buffer, pnio_blocks_len, &ndr_pos);  /* ActualCount */

    /* Update fragment length in RPC header */
    uint16_t fragment_length = (uint16_t)(pos - sizeof(profinet_rpc_header_t));
    hdr->fragment_length = htole16(fragment_length);
    hdr->fragment_number = 0;
    hdr->auth_protocol = 0;
    hdr->serial_low = 0;

    *buf_len = pos;

    LOG_DEBUG("Built control response: %zu bytes", pos);
    return WTC_OK;
}

wtc_result_t rpc_send_response(rpc_context_t *ctx,
                                uint32_t dest_ip,
                                uint16_t dest_port,
                                const uint8_t *response,
                                size_t resp_len)
{
    if (!ctx || !response || resp_len == 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (ctx->socket_fd < 0) {
        return WTC_ERROR_NOT_INITIALIZED;
    }

    struct sockaddr_in dest_addr;
    memset(&dest_addr, 0, sizeof(dest_addr));
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_addr.s_addr = dest_ip;
    dest_addr.sin_port = htons(dest_port);

    ssize_t sent = sendto(ctx->socket_fd, response, resp_len, 0,
                           (struct sockaddr *)&dest_addr, sizeof(dest_addr));
    if (sent < 0) {
        LOG_ERROR("RPC sendto failed: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    if ((size_t)sent != resp_len) {
        LOG_WARN("RPC partial send: %zd of %zu bytes", sent, resp_len);
    }

    LOG_DEBUG("RPC response sent: %zd bytes to %d.%d.%d.%d:%u",
              sent,
              dest_ip & 0xFF, (dest_ip >> 8) & 0xFF,
              (dest_ip >> 16) & 0xFF, (dest_ip >> 24) & 0xFF,
              dest_port);

    return WTC_OK;
}

/* ============== Error Analysis Implementation ============== */

/**
 * @brief Map block error code1 to block type.
 */
static uint16_t error_code1_to_block_type(uint8_t err_code1) {
    switch (err_code1) {
    case PNIO_CM_ERR1_AR_BLOCK:       return BLOCK_TYPE_AR_BLOCK_REQ;
    case PNIO_CM_ERR1_IOCR_BLOCK:     return BLOCK_TYPE_IOCR_BLOCK_REQ;
    case PNIO_CM_ERR1_ALARM_CR_BLOCK: return BLOCK_TYPE_ALARM_CR_BLOCK_REQ;
    case PNIO_CM_ERR1_EXPECTED_SUBMOD: return BLOCK_TYPE_EXPECTED_SUBMOD_BLOCK;
    default: return 0;
    }
}

/**
 * @brief Get human-readable description for IOCR error.
 */
static const char *get_iocr_error_desc(uint8_t err_code2) {
    switch (err_code2) {
    case PNIO_IOCR_ERR2_TYPE:        return "Invalid IOCR type";
    case PNIO_IOCR_ERR2_LT_FIELD:    return "Invalid LT field (must be 0x8892)";
    case PNIO_IOCR_ERR2_RT_CLASS:    return "Invalid RT class";
    case PNIO_IOCR_ERR2_RESERVED:    return "Reserved bits not zero";
    case PNIO_IOCR_ERR2_CSDU_LENGTH: return "C_SDU length out of range";
    case PNIO_IOCR_ERR2_FRAME_ID:    return "Invalid frame ID for IOCR type";
    case PNIO_IOCR_ERR2_SEND_CLOCK:  return "Invalid send clock factor";
    case PNIO_IOCR_ERR2_REDUCTION:   return "Invalid reduction ratio";
    case PNIO_IOCR_ERR2_PHASE:       return "Invalid phase (must be >= 1)";
    case PNIO_IOCR_ERR2_DATA_LENGTH: return "Data length too large";
    case PNIO_IOCR_ERR2_FRAME_OFFSET: return "Invalid frame send offset";
    case PNIO_IOCR_ERR2_WATCHDOG:    return "Invalid watchdog factor";
    case PNIO_IOCR_ERR2_DATA_HOLD:   return "Invalid data hold factor";
    default: return "Unknown IOCR error";
    }
}

void rpc_analyze_error(const connect_response_t *response,
                       error_analysis_t *analysis) {
    if (!response || !analysis) {
        return;
    }

    memset(analysis, 0, sizeof(error_analysis_t));
    analysis->err_decode = response->error_decode;
    analysis->err_code1 = response->error_code1 & 0xFF;
    analysis->err_code2 = response->error_code2 & 0xFF;

    /* If no error info, check if response indicates general failure */
    if (response->error_code == PNIO_ERR_CODE_OK && response->success) {
        analysis->action = RECOVERY_NONE;
        analysis->description = "No error";
        return;
    }

    /* Check for PNIO-CM errors (connection manager) */
    if (response->error_decode == PNIO_ERR_DECODE_PNIOCM) {
        analysis->is_block_error = true;
        analysis->problem_block = error_code1_to_block_type(analysis->err_code1);

        switch (analysis->err_code1) {
        case PNIO_CM_ERR1_CONNECT:
            /* General connect error */
            switch (analysis->err_code2) {
            case PNIO_CM_ERR2_UNKNOWN_BLOCK:
                analysis->action = RECOVERY_TRY_MINIMAL;
                analysis->description = "Unknown block type - try minimal config";
                break;
            case PNIO_CM_ERR2_INVALID_LENGTH:
                analysis->action = RECOVERY_FIX_BLOCK_LENGTH;
                analysis->description = "Invalid block length";
                break;
            case PNIO_CM_ERR2_RESOURCE:
                analysis->action = RECOVERY_WAIT_AND_RETRY;
                analysis->description = "Device out of resources";
                break;
            default:
                analysis->action = RECOVERY_RETRY_SAME;
                analysis->description = "General connect error";
            }
            break;

        case PNIO_CM_ERR1_AR_BLOCK:
            /* AR Block error - often station name mismatch */
            analysis->action = RECOVERY_TRY_LOWERCASE;
            analysis->description = "AR block error - check station name";
            break;

        case PNIO_CM_ERR1_IOCR_BLOCK:
            /* IOCR Block error */
            analysis->description = get_iocr_error_desc(analysis->err_code2);
            switch (analysis->err_code2) {
            case PNIO_IOCR_ERR2_PHASE:
                analysis->action = RECOVERY_FIX_PHASE;
                break;
            case PNIO_IOCR_ERR2_SEND_CLOCK:
            case PNIO_IOCR_ERR2_REDUCTION:
            case PNIO_IOCR_ERR2_WATCHDOG:
            case PNIO_IOCR_ERR2_DATA_HOLD:
                analysis->action = RECOVERY_FIX_TIMING;
                break;
            default:
                analysis->action = RECOVERY_TRY_MINIMAL;
            }
            break;

        case PNIO_CM_ERR1_ALARM_CR_BLOCK:
            /* Alarm CR error */
            if (analysis->err_code2 == PNIO_ALARM_ERR2_LENGTH) {
                analysis->action = RECOVERY_FIX_BLOCK_LENGTH;
                analysis->description = "Invalid AlarmCR block length";
            } else {
                analysis->action = RECOVERY_TRY_MINIMAL;
                analysis->description = "AlarmCR block error";
            }
            break;

        case PNIO_CM_ERR1_EXPECTED_SUBMOD:
            /* Expected submodule config mismatch */
            analysis->action = RECOVERY_TRY_MINIMAL;
            analysis->description = "Expected submodule mismatch - try minimal config";
            break;

        default:
            analysis->action = RECOVERY_RETRY_SAME;
            analysis->description = "Unknown PNIO-CM error";
        }
    } else if (response->error_code == PNIO_ERR_CODE_CONNECT) {
        /* Generic connect failure */
        analysis->action = RECOVERY_REDISCOVER;
        analysis->description = "Connect failed - try rediscovery";
    } else {
        /* Unknown error type */
        analysis->action = RECOVERY_WAIT_AND_RETRY;
        analysis->description = "Unknown error type";
    }

    LOG_INFO("Error analysis: decode=0x%02X code1=0x%02X code2=0x%02X -> %s (action=%d)",
             analysis->err_decode, analysis->err_code1, analysis->err_code2,
             analysis->description, analysis->action);
}
