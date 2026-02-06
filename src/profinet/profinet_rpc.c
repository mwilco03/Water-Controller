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

/* Bug 0.3: RPC header fields are written via direct struct assignment which
 * produces the correct little-endian encoding only on LE platforms.
 * Fail at compile time if this assumption is violated. */
_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__,
               "RPC header relies on LE platform; use explicit conversion for BE");

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

    /*
     * DREP = 0x10 (Little-Endian integers, ASCII characters).
     *
     * All multi-byte fields in the RPC header (interface_version,
     * sequence_number, opnum, fragment_length, etc.) MUST be encoded
     * in little-endian byte order to match this DREP declaration.
     *
     * UUIDs: first 3 fields (time_low, time_mid, time_hi_and_version)
     * are stored in LE; remaining bytes (clock_seq, node) are unchanged.
     * All three UUID fields (Object, Interface, Activity) are stored
     * in BE and swapped to LE after memcpy.  p-net decodes all UUID
     * fields per DREP using pf_get_uuid() before comparison.
     *
     * Note: PNIO block payloads (ARBlockReq, IOCRBlockReq, etc.) are
     * always big-endian per IEC 61158-6, independent of DREP.
     */
    hdr->drep[0] = RPC_DREP_LITTLE_ENDIAN;
    hdr->drep[1] = RPC_DREP_ASCII;
    hdr->drep[2] = 0;
    hdr->serial_high = 0;

    /* Object UUID (AR UUID) — swap from BE storage to LE wire format */
    memcpy(hdr->object_uuid, object_uuid, 16);
    uuid_swap_fields(hdr->object_uuid);

    /*
     * Interface UUID (PROFINET IO Device) — swap to LE per DREP.
     *
     * The constant is stored in big-endian byte order (DE A0 00 01 ...).
     * p-net parses ALL UUID fields in the RPC header per DREP using
     * pf_get_uuid() → pf_get_uint32()/pf_get_uint16(), then compares
     * the decoded pf_uuid_t struct via memcmp against its internal
     * constant {0xDEA00001, 0x6C97, 0x11D1, ...}.
     *
     * With DREP=0x10 (LE), the first 3 UUID fields MUST be LE-encoded
     * on the wire so p-net decodes them to the correct host values.
     * Without the swap, p-net reads 0x0100A0DE instead of 0xDEA00001,
     * the UUID check fails, and the packet is silently dropped.
     */
    memcpy(hdr->interface_uuid, PNIO_DEVICE_INTERFACE_UUID, 16);
    uuid_swap_fields(hdr->interface_uuid);

    /* Activity UUID (unique per request) — swap to LE */
    memcpy(hdr->activity_uuid, ctx->activity_uuid, 16);
    uuid_swap_fields(hdr->activity_uuid);

    /* All multi-byte header fields in LE (native on this platform) */
    hdr->server_boot = 0;
    hdr->interface_version = 1;
    hdr->sequence_number = ctx->sequence_number;
    ctx->sequence_number++;

    hdr->opnum = opnum;
    hdr->interface_hint = 0xFFFF;
    hdr->activity_hint = 0xFFFF;
    hdr->fragment_length = fragment_length;
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

/* ============== DREP-Aware RPC Header Field Decoding ============== */

/**
 * @brief Decode uint16 from RPC header based on DREP byte order.
 *
 * The sender's DREP field specifies how multi-byte fields in the RPC
 * header are encoded.  DREP[0] & 0x10 = LE, otherwise BE.
 *
 * @param[in] hdr  RPC header
 * @param[in] val  Raw field value from the packed struct
 * @return Decoded host-order value
 */
static uint16_t rpc_hdr_u16(const profinet_rpc_header_t *hdr, uint16_t val)
{
    if (hdr->drep[0] & 0x10) {
        /* Sender encoded as LE — on an LE host the raw value is already correct */
        return val;
    }
    return ntohs(val);  /* Sender encoded as BE */
}

/**
 * @brief Decode uint32 from RPC header based on DREP byte order.
 */
static uint32_t rpc_hdr_u32(const profinet_rpc_header_t *hdr, uint32_t val)
{
    if (hdr->drep[0] & 0x10) {
        return val;  /* LE on LE host */
    }
    return ntohl(val);  /* BE */
}

/* ============== NDR Header Support ============== */

/* Size of NDR request header inserted before PNIO blocks */
#define NDR_REQUEST_HEADER_SIZE 20

/**
 * @brief Write 20-byte NDR request header in little-endian format.
 *
 * Layout (all uint32 LE):
 *   ArgsMaximum  — maximum response size the caller can accept
 *   ArgsLength   — actual payload length following this header
 *   MaxCount     — NDR conformant array max (= ArgsLength)
 *   Offset       — NDR array offset (always 0)
 *   ActualCount  — NDR array actual count (= ArgsLength)
 *
 * @param[out] buf           Destination buffer
 * @param[in]  pos           Byte offset where the header starts
 * @param[in]  args_maximum  Maximum PDU payload capacity
 * @param[in]  args_length   Actual PNIO block payload length
 */
static void write_ndr_request_header(uint8_t *buf, size_t pos,
                                      uint32_t args_maximum,
                                      uint32_t args_length)
{
    size_t p = pos;

    /* ArgsMaximum (4 bytes LE) */
    buf[p++] = (uint8_t)(args_maximum);
    buf[p++] = (uint8_t)(args_maximum >> 8);
    buf[p++] = (uint8_t)(args_maximum >> 16);
    buf[p++] = (uint8_t)(args_maximum >> 24);

    /* ArgsLength (4 bytes LE) */
    buf[p++] = (uint8_t)(args_length);
    buf[p++] = (uint8_t)(args_length >> 8);
    buf[p++] = (uint8_t)(args_length >> 16);
    buf[p++] = (uint8_t)(args_length >> 24);

    /* MaxCount = ArgsLength (4 bytes LE) */
    buf[p++] = (uint8_t)(args_length);
    buf[p++] = (uint8_t)(args_length >> 8);
    buf[p++] = (uint8_t)(args_length >> 16);
    buf[p++] = (uint8_t)(args_length >> 24);

    /* Offset = 0 (4 bytes) */
    buf[p++] = 0; buf[p++] = 0; buf[p++] = 0; buf[p++] = 0;

    /* ActualCount = ArgsLength (4 bytes LE) */
    buf[p++] = (uint8_t)(args_length);
    buf[p++] = (uint8_t)(args_length >> 8);
    buf[p++] = (uint8_t)(args_length >> 16);
    buf[p++] = (uint8_t)(args_length >> 24);
}

/**
 * @brief Detect whether an NDR header is present after the RPC header.
 *
 * Heuristic: PNIO response block types start with 0x81xx (response) or
 * 0x01xx (request).  An NDR header starts with ArgsMaximum which is
 * a LE uint32 — its first byte is never 0x81 or 0x01 for realistic
 * PDU sizes, so we can distinguish by checking the first two bytes as
 * a big-endian block type.
 *
 * @param[in] buf  Response buffer
 * @param[in] pos  Byte offset right after RPC header
 * @param[in] len  Total buffer length
 * @return true if NDR header appears present, false if blocks start directly
 */
static bool response_has_ndr_header(const uint8_t *buf, size_t pos, size_t len)
{
    if (pos + 6 > len) {
        return false;
    }

    /* Read first 2 bytes as big-endian (potential block type) */
    uint16_t maybe_type = (uint16_t)((buf[pos] << 8) | buf[pos + 1]);

    /* Valid response block types: 0x8101-0x810F */
    if (maybe_type >= 0x8101 && maybe_type <= 0x810F) {
        return false;
    }
    /* Valid request block types: 0x0101-0x010F */
    if (maybe_type >= 0x0101 && maybe_type <= 0x010F) {
        return false;
    }

    return true;
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
                               uint32_t controller_ip,
                               const char *interface_name)
{
    if (!ctx || !controller_mac) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memset(ctx, 0, sizeof(rpc_context_t));

    /* Store interface name for diagnostics */
    if (interface_name) {
        strncpy(ctx->interface_name, interface_name,
                sizeof(ctx->interface_name) - 1);
    }

    /* Create UDP socket */
    ctx->socket_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (ctx->socket_fd < 0) {
        LOG_ERROR("Failed to create RPC socket: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    /*
     * Bind socket to the PROFINET interface via SO_BINDTODEVICE.
     *
     * On multi-homed hosts (common in Docker with host networking), the
     * kernel routing table may direct UDP packets through a non-PROFINET
     * interface (e.g. eth0 for management).  DCP uses raw L2 sockets
     * bound to the interface by AF_PACKET and is unaffected, but RPC
     * uses AF_INET and follows the routing table.
     *
     * SO_BINDTODEVICE forces all traffic on this socket through the
     * specified interface, ensuring RPC Connect requests reach the
     * RTU on the PROFINET network segment.
     *
     * Requires CAP_NET_RAW (already granted for the raw socket).
     */
    if (interface_name && interface_name[0]) {
        if (setsockopt(ctx->socket_fd, SOL_SOCKET, SO_BINDTODEVICE,
                       interface_name, strlen(interface_name) + 1) < 0) {
            LOG_ERROR("Failed to bind RPC socket to interface %s: %s "
                      "(UDP packets may be sent on wrong interface)",
                      interface_name, strerror(errno));
            /* Non-fatal: fall through and try INADDR_ANY binding.
             * On single-NIC systems this is fine; on multi-NIC it may
             * cause the "no UDP on wire" symptom. */
        } else {
            LOG_INFO("RPC socket bound to interface %s", interface_name);
        }
    }

    /* Bind to controller IP + ephemeral port.
     * If controller_ip is known, bind to it so the source address in
     * outgoing UDP packets is correct (RTU checks this against the
     * CMInitiatorIPAddress in the ARBlockReq).  If unknown (0),
     * bind to INADDR_ANY and rely on SO_BINDTODEVICE for routing. */
    struct sockaddr_in local_addr;
    memset(&local_addr, 0, sizeof(local_addr));
    local_addr.sin_family = AF_INET;
    local_addr.sin_addr.s_addr = (controller_ip != 0)
        ? htonl(controller_ip) : INADDR_ANY;
    local_addr.sin_port = 0;  /* Let kernel assign port */

    if (bind(ctx->socket_fd, (struct sockaddr *)&local_addr,
             sizeof(local_addr)) < 0) {
        LOG_ERROR("Failed to bind RPC socket to %d.%d.%d.%d: %s",
                  (controller_ip >> 24) & 0xFF,
                  (controller_ip >> 16) & 0xFF,
                  (controller_ip >> 8) & 0xFF,
                  controller_ip & 0xFF,
                  strerror(errno));
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

    LOG_INFO("RPC context initialized on %s, IP %d.%d.%d.%d, port %u",
             interface_name ? interface_name : "any",
             (controller_ip >> 24) & 0xFF,
             (controller_ip >> 16) & 0xFF,
             (controller_ip >> 8) & 0xFF,
             controller_ip & 0xFF,
             ctx->controller_port);
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
     * Bug 0.4 fix: NDR header is mandatory — p-net rejects requests without
     * it (pf_cmrpc.c:4622-4634).  Reserve 20 bytes between the RPC header
     * and the first PNIO block; the actual values are filled in after all
     * blocks are built (we need the total PNIO payload length).
     *
     * Connect Request layout:
     *   [RPC Header][NDR Header][AR Block][IOCR Block(s)][AlarmCR Block][ExpSubmod Block]
     */
    size_t ndr_header_pos = pos;
    pos += NDR_REQUEST_HEADER_SIZE;  /* Reserve 20 bytes for NDR */
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

    /* Bug 0.1 fix: Calculate block_length BEFORE adding inter-block padding.
     * block_length = content bytes after type+length fields, excluding padding.
     * p-net validates at pf_cmrpc.c:1176: exact match required. */
    size_t ar_block_len = pos - ar_block_start - 4;  /* Exclude type + length */
    size_t save_pos = ar_block_start;
    write_block_header(buffer, BLOCK_TYPE_AR_BLOCK_REQ,
                        (uint16_t)ar_block_len, &save_pos);

    /* Bug 0.5 fix: Zero-fill alignment padding to avoid leaking buffer content */
    while (pos % 4 != 0) {
        buffer[pos++] = 0;
    }

    /* ============== IOCR Block Requests (IEC 61158-6 format) ============== */
    for (int i = 0; i < params->iocr_count; i++) {
        size_t iocr_block_start = pos;
        pos += 6;  /* Skip block header, fill later */

        bool is_input_iocr = (params->iocr[i].type == IOCR_TYPE_INPUT);

        write_u16_be(buffer, params->iocr[i].type, &pos);
        write_u16_be(buffer, params->iocr[i].reference, &pos);
        write_u16_be(buffer, PROFINET_ETHERTYPE, &pos);  /* LT field */
        write_u32_be(buffer, IOCR_PROP_RT_CLASS_1, &pos);
        write_u16_be(buffer, params->iocr[i].data_length, &pos);
        write_u16_be(buffer, params->iocr[i].frame_id, &pos);
        write_u16_be(buffer, params->iocr[i].send_clock_factor, &pos);
        write_u16_be(buffer, params->iocr[i].reduction_ratio, &pos);
        write_u16_be(buffer, 1, &pos);  /* Phase (must be >= 1 per IEC 61158-6) */
        write_u16_be(buffer, 0, &pos);  /* Sequence (deprecated in V2.3+) */
        write_u32_be(buffer, 0xFFFFFFFF, &pos);  /* FrameSendOffset: best effort */
        write_u16_be(buffer, params->iocr[i].watchdog_factor, &pos);
        write_u16_be(buffer, params->data_hold_factor ? params->data_hold_factor : 3, &pos);
        write_u16_be(buffer, 0, &pos);  /* IOCR tag header */
        memset(buffer + pos, 0, 6);     /* Multicast MAC (not used for Class 1) */
        pos += 6;

        /* ---- API section (IEC 61158-6 §5.2.7.6) ---- */
        write_u16_be(buffer, 1, &pos);  /* NumberOfAPIs = 1 */
        write_u32_be(buffer, 0, &pos);  /* API = 0 */

        /*
         * IOData objects: submodules whose data appears in THIS IOCR's frame.
         *
         * Directional submodules (data_length > 0):
         *   Input IOCR  ← input submodules only
         *   Output IOCR ← output submodules only
         *
         * NO_IO submodules (data_length == 0, e.g., DAP slot 0):
         *   Appear in BOTH IOCRs as IODataObjects with FrameOffset but
         *   zero data contribution.  This is required per IEC 61158-6
         *   so that each submodule gets an IOPS byte in the cyclic frame.
         *
         * Each IODataObject = SlotNumber(u16) + SubslotNumber(u16)
         *                   + IODataObjectFrameOffset(u16) = 6 bytes
         *
         * Frame layout: [user_data_0][user_data_1]...[iops_0][iops_1]...[iocs_0]...
         */
        int iodata_count = 0;
        uint16_t iodata_frame_offset = 0;
        for (int j = 0; j < params->expected_count; j++) {
            if (params->expected_config[j].data_length == 0 ||
                params->expected_config[j].is_input == is_input_iocr) {
                iodata_count++;
            }
        }
        write_u16_be(buffer, (uint16_t)iodata_count, &pos);

        uint16_t running_offset = 0;
        for (int j = 0; j < params->expected_count; j++) {
            if (params->expected_config[j].data_length != 0 &&
                params->expected_config[j].is_input != is_input_iocr) {
                continue;
            }
            write_u16_be(buffer, params->expected_config[j].slot, &pos);
            write_u16_be(buffer, params->expected_config[j].subslot, &pos);
            write_u16_be(buffer, running_offset, &pos);
            running_offset += params->expected_config[j].data_length;
        }
        /* IOPS bytes follow user data (1 per IOData submodule) */
        iodata_frame_offset = running_offset + (uint16_t)iodata_count;

        /*
         * IOCS objects: consumer status bytes.
         *
         * Directional submodules:
         *   Input IOCR  ← IOCS for output submodules
         *   Output IOCR ← IOCS for input submodules
         *
         * NO_IO submodules: appear in BOTH IOCRs as IOCS (same as IOData).
         */
        int iocs_count = 0;
        for (int j = 0; j < params->expected_count; j++) {
            if (params->expected_config[j].data_length == 0 ||
                params->expected_config[j].is_input != is_input_iocr) {
                iocs_count++;
            }
        }
        write_u16_be(buffer, (uint16_t)iocs_count, &pos);

        uint16_t iocs_offset = iodata_frame_offset;
        for (int j = 0; j < params->expected_count; j++) {
            if (params->expected_config[j].data_length != 0 &&
                params->expected_config[j].is_input == is_input_iocr) {
                continue;
            }
            write_u16_be(buffer, params->expected_config[j].slot, &pos);
            write_u16_be(buffer, params->expected_config[j].subslot, &pos);
            write_u16_be(buffer, iocs_offset, &pos);
            iocs_offset += 1;  /* Each IOCS is 1 byte */
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
    write_u16_be(buffer, params->rta_timeout_factor ? params->rta_timeout_factor : 100, &pos);
    write_u16_be(buffer, params->rta_retries ? params->rta_retries : 3, &pos);
    write_u16_be(buffer, 0x0001, &pos);  /* Local alarm reference */
    write_u16_be(buffer, params->max_alarm_data_length, &pos);
    /* Bug 0.2 fix: VLAN priority tags are mandatory.
     * p-net rejects 0x0000 at pf_cmdev.c:4088-4098 (error code 11/12). */
    write_u16_be(buffer, IOCR_TAG_HEADER_HIGH, &pos);  /* VLAN prio 6 */
    write_u16_be(buffer, IOCR_TAG_HEADER_LOW, &pos);   /* VLAN prio 5 */

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
        write_u16_be(buffer, 0x0000, &pos);  /* ModuleProperties */

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

            /* SubmoduleProperties: bits 0-1 = Type per IEC 61158-6
             *   0 = NO_IO  → 0 DataDescriptions
             *   1 = INPUT  → 1 DataDescription (type 0x0001)
             *   2 = OUTPUT → 1 DataDescription (type 0x0002)
             */
            bool is_no_io = (params->expected_config[j].data_length == 0);
            uint16_t submod_props;
            if (is_no_io) {
                submod_props = 0x0000;  /* NO_IO */
            } else if (params->expected_config[j].is_input) {
                submod_props = 0x0001;  /* INPUT */
            } else {
                submod_props = 0x0002;  /* OUTPUT */
            }
            write_u16_be(buffer, submod_props, &pos);

            /* DataDescription: 1 block for INPUT/OUTPUT, 0 for NO_IO.
             * Format per IEC 61158-6:
             *   DataDescription(u16) + SubmoduleDataLength(u16) +
             *   LengthIOPS(u8) + LengthIOCS(u8) */
            if (!is_no_io) {
                uint16_t data_desc_type = params->expected_config[j].is_input
                                          ? 0x0001 : 0x0002;
                write_u16_be(buffer, data_desc_type, &pos);
                write_u16_be(buffer, params->expected_config[j].data_length, &pos);
                write_u8(buffer + pos, 1);  /* LengthIOPS */
                pos++;
                write_u8(buffer + pos, 1);  /* LengthIOCS */
                pos++;
            }
        }
    }

    size_t exp_block_len = pos - exp_block_start - 4;
    save_pos = exp_block_start;
    write_block_header(buffer, BLOCK_TYPE_EXPECTED_SUBMOD_BLOCK,
                        (uint16_t)exp_block_len, &save_pos);

    /* ============== Finalize NDR Header and RPC Header ============== */

    /* Verify we didn't exceed buffer size */
    if (pos > RPC_MAX_PDU_SIZE) {
        LOG_ERROR("Connect Request PDU too large: %zu bytes (max %d)",
                  pos, RPC_MAX_PDU_SIZE);
        return WTC_ERROR_NO_MEMORY;
    }

    /* Fill in NDR request header now that we know the PNIO payload length */
    uint32_t pnio_len = (uint32_t)(pos - pnio_blocks_start);
    uint32_t args_max = (uint32_t)(RPC_MAX_PDU_SIZE - sizeof(profinet_rpc_header_t));
    write_ndr_request_header(buffer, ndr_header_pos, args_max, pnio_len);

    /* fragment_length = NDR header + PNIO blocks */
    uint16_t fragment_length = (uint16_t)(pos - sizeof(profinet_rpc_header_t));

    /* Generate new activity UUID for this request */
    rpc_generate_uuid(ctx->activity_uuid);

    build_rpc_header(buffer, ctx, params->ar_uuid, RPC_OPNUM_CONNECT,
                      fragment_length, &save_pos);

    *buf_len = pos;
    LOG_DEBUG("Built Connect Request PDU: %zu bytes (NDR: %d, PNIO: %u)",
              pos, NDR_REQUEST_HEADER_SIZE, pnio_len);
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

    /* Validate OpNum — DREP-aware decode, log mismatch but don't reject,
     * since non-standard stacks may echo a different opnum. */
    uint16_t resp_opnum = rpc_hdr_u16(hdr, hdr->opnum);
    if (resp_opnum != RPC_OPNUM_CONNECT) {
        LOG_WARN("Connect response: opnum=%u (expected %u) — "
                 "device may use non-standard opnum mapping",
                 resp_opnum, RPC_OPNUM_CONNECT);
    }

    size_t pos = sizeof(profinet_rpc_header_t);

    /*
     * PNIO Connect Response format (after RPC header):
     *
     * Some devices include an NDR header (24 bytes):
     *   ArgsMaximum (4 LE), ErrorStatus1 (4 LE), ErrorStatus2 (4 LE),
     *   MaxCount (4 LE), Offset (4 LE), ActualCount (4 LE)
     * Others send PNIO blocks directly.
     *
     * We auto-detect which format is present.
     */
    bool has_ndr = response_has_ndr_header(buffer, pos, buf_len);

    if (has_ndr) {
        if (pos + 24 > buf_len) {
            LOG_ERROR("Connect response too short for NDR header");
            return WTC_ERROR_PROTOCOL;
        }

        /* Parse NDR/PNIO header - values are little-endian */
        uint32_t args_maximum = buffer[pos] | (buffer[pos+1] << 8) |
                                (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
        pos += 4;
        (void)args_maximum;

        uint32_t error_status1 = buffer[pos] | (buffer[pos+1] << 8) |
                                 (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
        pos += 4;

        uint32_t error_status2 = buffer[pos] | (buffer[pos+1] << 8) |
                                 (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
        pos += 4;

        LOG_DEBUG("Connect response NDR: error1=0x%08X, error2=0x%08X",
                  error_status1, error_status2);

        /* Check for PNIO-level errors */
        if (error_status1 != 0 || error_status2 != 0) {
            LOG_ERROR("Connect response PNIO error: status1=0x%08X, status2=0x%08X",
                      error_status1, error_status2);
            response->success = false;
            response->error_code = (uint8_t)(error_status2 & 0xFF);
            return WTC_ERROR_PROTOCOL;
        }

        /* Skip NDR array conformance header */
        uint32_t max_count = buffer[pos] | (buffer[pos+1] << 8) |
                             (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
        pos += 4;

        pos += 4;  /* Skip offset (always 0) */

        uint32_t actual_count = buffer[pos] | (buffer[pos+1] << 8) |
                                (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
        pos += 4;

        LOG_DEBUG("Connect response NDR array: max=%u, actual=%u",
                  max_count, actual_count);

        if (actual_count == 0) {
            LOG_ERROR("Connect response: no PNIO data in response");
            return WTC_ERROR_PROTOCOL;
        }
    } else {
        LOG_DEBUG("Connect response: no NDR header detected, parsing blocks directly");
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

    /*
     * Bug 0.4 applies here too: NDR header is mandatory for all RPC requests.
     * p-net rejects requests without it (pf_cmrpc.c:4622-4634).
     * Without NDR, ParameterEnd is silently dropped by the RTU and the AR
     * never transitions to READY → ApplicationReady never arrives →
     * connection aborts → reconnect loops indefinitely.
     */
    size_t ndr_header_pos = pos;
    pos += NDR_REQUEST_HEADER_SIZE;
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

    /* Fill NDR request header */
    uint32_t pnio_len = (uint32_t)(pos - pnio_blocks_start);
    uint32_t args_max = (uint32_t)(RPC_MAX_PDU_SIZE - sizeof(profinet_rpc_header_t));
    write_ndr_request_header(buffer, ndr_header_pos, args_max, pnio_len);

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

    /* Validate OpNum — DREP-aware decode; Control operations use OpNum 4 */
    uint16_t ctrl_opnum = rpc_hdr_u16(hdr, hdr->opnum);
    if (ctrl_opnum != RPC_OPNUM_CONTROL) {
        LOG_WARN("Control response: opnum=%u (expected %u)",
                 ctrl_opnum, RPC_OPNUM_CONTROL);
    }

    size_t pos = sizeof(profinet_rpc_header_t);

    /* Skip NDR response header if present (some devices include it) */
    bool has_ndr = response_has_ndr_header(buffer, pos, buf_len);
    if (has_ndr) {
        if (pos + 24 > buf_len) {
            LOG_ERROR("Control response too short for NDR header");
            return WTC_ERROR_PROTOCOL;
        }
        pos += 4;  /* ArgsMaximum */

        uint32_t error_status1 = buffer[pos] | (buffer[pos+1] << 8) |
                                 (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
        pos += 4;
        uint32_t error_status2 = buffer[pos] | (buffer[pos+1] << 8) |
                                 (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
        pos += 4;

        if (error_status1 != 0 || error_status2 != 0) {
            LOG_ERROR("Control response PNIO error: status1=0x%08X, status2=0x%08X",
                      error_status1, error_status2);
            return WTC_ERROR_PROTOCOL;
        }

        pos += 4;  /* MaxCount */
        pos += 4;  /* Offset */
        pos += 4;  /* ActualCount */
    }

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

    /* Extract opnum from RPC header for logging BEFORE send */
    uint16_t log_opnum = 0;
    const char *opnum_name = "UNKNOWN";
    if (req_len >= sizeof(profinet_rpc_header_t)) {
        const profinet_rpc_header_t *hdr = (const profinet_rpc_header_t *)request;
        log_opnum = hdr->opnum;
        switch (log_opnum) {
        case RPC_OPNUM_CONNECT:  opnum_name = "CONNECT"; break;
        case RPC_OPNUM_RELEASE:  opnum_name = "RELEASE"; break;
        case RPC_OPNUM_READ:     opnum_name = "READ"; break;
        case RPC_OPNUM_WRITE:    opnum_name = "WRITE"; break;
        case RPC_OPNUM_CONTROL:  opnum_name = "CONTROL"; break;
        default: break;
        }
    }

    /*
     * Detailed pre-send diagnostics for "no packet on wire" debugging.
     * Log: dst IP (hex + dotted), dst port, local socket info, payload preview.
     */
    char dst_ip_str[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &addr.sin_addr, dst_ip_str, sizeof(dst_ip_str));

    /* Get local socket binding info via getsockname() */
    struct sockaddr_in local_addr;
    socklen_t local_len = sizeof(local_addr);
    char local_ip_str[INET_ADDRSTRLEN] = "unknown";
    uint16_t local_port = 0;
    if (getsockname(ctx->socket_fd, (struct sockaddr *)&local_addr, &local_len) == 0) {
        inet_ntop(AF_INET, &local_addr.sin_addr, local_ip_str, sizeof(local_ip_str));
        local_port = ntohs(local_addr.sin_port);
    }

    /* Log first 32 bytes of payload in hex for protocol analysis */
    char payload_hex[97] = {0};  /* 32 bytes * 3 chars + null */
    size_t hex_len = req_len > 32 ? 32 : req_len;
    for (size_t i = 0; i < hex_len; i++) {
        snprintf(payload_hex + i*3, 4, "%02X ", request[i]);
    }

    LOG_INFO("RPC %s PRE-SEND: dst=%s:%u (0x%08X), local=%s:%u, fd=%d, len=%zu",
             opnum_name, dst_ip_str, PNIO_RPC_PORT, device_ip,
             local_ip_str, local_port, ctx->socket_fd, req_len);
    LOG_INFO("RPC %s PAYLOAD[0:32]: %s", opnum_name, payload_hex);

    /*
     * Use connect() + send() instead of sendto() to force early routing
     * resolution. This can help with edge cases where sendto() succeeds
     * but packets don't reach the wire due to deferred routing decisions.
     *
     * For UDP, connect() doesn't establish a connection - it just sets
     * the default destination and forces the kernel to resolve the route
     * immediately. If routing fails, connect() returns an error.
     */
    if (connect(ctx->socket_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        LOG_ERROR("RPC connect() failed for %s:%u: %s (errno=%d, fd=%d)",
                  dst_ip_str, PNIO_RPC_PORT, strerror(errno), errno, ctx->socket_fd);
        return WTC_ERROR_IO;
    }

    /* Send request using send() on connected socket */
    ssize_t sent = send(ctx->socket_fd, request, req_len, 0);
    if (sent < 0) {
        LOG_ERROR("RPC send FAILED: %s (errno=%d, fd=%d)",
                  strerror(errno), errno, ctx->socket_fd);
        return WTC_ERROR_IO;
    }

    if ((size_t)sent != req_len) {
        LOG_WARN("RPC send incomplete: sent %zd of %zu bytes", sent, req_len);
    } else {
        LOG_INFO("RPC %s: sent %zd bytes OK", opnum_name, sent);
    }

    /* Wait for response */
    struct pollfd pfd;
    pfd.fd = ctx->socket_fd;
    pfd.events = POLLIN;

    int poll_result = poll(&pfd, 1, (int)timeout_ms);

    /* Log poll result with revents for debugging */
    LOG_INFO("RPC %s POLL: result=%d, revents=0x%04X (POLLIN=%d, POLLERR=%d, POLLHUP=%d)",
             opnum_name, poll_result, pfd.revents,
             (pfd.revents & POLLIN) ? 1 : 0,
             (pfd.revents & POLLERR) ? 1 : 0,
             (pfd.revents & POLLHUP) ? 1 : 0);

    if (poll_result < 0) {
        LOG_ERROR("RPC poll failed: %s (errno=%d)", strerror(errno), errno);
        return WTC_ERROR_IO;
    }
    if (poll_result == 0) {
        LOG_WARN("RPC %s TIMEOUT after %u ms (no response received)", opnum_name, timeout_ms);
        return WTC_ERROR_TIMEOUT;
    }

    /* Receive response */
    struct sockaddr_in recv_addr;
    socklen_t recv_addr_len = sizeof(recv_addr);
    memset(&recv_addr, 0, sizeof(recv_addr));

    ssize_t received = recvfrom(ctx->socket_fd, response, *resp_len, 0,
                                 (struct sockaddr *)&recv_addr, &recv_addr_len);
    if (received < 0) {
        LOG_ERROR("RPC receive failed: %s (errno=%d)", strerror(errno), errno);
        return WTC_ERROR_IO;
    }

    /* Log response source for debugging */
    char recv_ip_str[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &recv_addr.sin_addr, recv_ip_str, sizeof(recv_ip_str));
    LOG_INFO("RPC %s RECV: %zd bytes from %s:%u",
             opnum_name, received, recv_ip_str, ntohs(recv_addr.sin_port));

    *resp_len = (size_t)received;

    /* Extract packet type from response for logging */
    const char *pkt_type_name = "UNKNOWN";
    if ((size_t)received >= sizeof(profinet_rpc_header_t)) {
        const profinet_rpc_header_t *resp_hdr = (const profinet_rpc_header_t *)response;
        switch (resp_hdr->packet_type) {
        case RPC_PACKET_TYPE_RESPONSE: pkt_type_name = "RESPONSE"; break;
        case RPC_PACKET_TYPE_FAULT:    pkt_type_name = "FAULT"; break;
        case RPC_PACKET_TYPE_REJECT:   pkt_type_name = "REJECT"; break;
        case RPC_PACKET_TYPE_WORKING:  pkt_type_name = "WORKING"; break;
        default: break;
        }
    }

    /* Log response payload preview */
    char resp_hex[97] = {0};
    size_t resp_hex_len = (size_t)received > 32 ? 32 : (size_t)received;
    for (size_t i = 0; i < resp_hex_len; i++) {
        snprintf(resp_hex + i*3, 4, "%02X ", response[i]);
    }
    LOG_INFO("RPC %s RESPONSE[0:32]: %s", pkt_type_name, resp_hex);
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

    /* Validate response AR UUID matches our request.
     * A mismatched UUID means we received a stale response from
     * a previous AR or from a different device on the same IP. */
    if (memcmp(response->ar_uuid, params->ar_uuid, 16) != 0) {
        LOG_WARN("Connect response AR UUID mismatch — stale or cross-device response");
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

    /* Check opnum — DREP-aware decode for ApplicationReady */
    uint16_t opnum = rpc_hdr_u16(hdr, hdr->opnum);
    if (opnum != RPC_OPNUM_CONTROL) {
        LOG_DEBUG("Incoming RPC: unexpected opnum %u (expected CONTROL=%u)",
                  opnum, RPC_OPNUM_CONTROL);
        return WTC_ERROR_PROTOCOL;
    }

    /* Save activity UUID and sequence for response — DREP-aware decode */
    memcpy(request->activity_uuid, hdr->activity_uuid, 16);
    request->sequence_number = rpc_hdr_u32(hdr, hdr->sequence_number);

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

    /* Object UUID (AR UUID) — swap to LE wire format */
    memcpy(hdr->object_uuid, request->ar_uuid, 16);
    uuid_swap_fields(hdr->object_uuid);

    /* Interface UUID (Controller) — swap to LE per DREP, same as build_rpc_header */
    memcpy(hdr->interface_uuid, PNIO_CONTROLLER_INTERFACE_UUID, 16);
    uuid_swap_fields(hdr->interface_uuid);

    /* Activity UUID — must match request, already in wire format from device */
    memcpy(hdr->activity_uuid, request->activity_uuid, 16);

    /* All multi-byte header fields in LE (matching DREP=0x10) */
    hdr->server_boot = 0;
    hdr->interface_version = 1;
    hdr->sequence_number = request->sequence_number;

    hdr->opnum = RPC_OPNUM_CONTROL;
    hdr->interface_hint = 0xFFFF;
    hdr->activity_hint = 0xFFFF;

    /* Build IOD Control Response block */
    size_t pos = sizeof(profinet_rpc_header_t);
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

    /* Update fragment length in RPC header (LE, matching DREP) */
    uint16_t fragment_length = (uint16_t)(pos - sizeof(profinet_rpc_header_t));
    hdr->fragment_length = fragment_length;
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

/* ============== Record Read (Phase 3: Module Discovery) ============== */

/**
 * @brief Read uint32 in network byte order from buffer.
 */
static uint32_t read_u32_be(const uint8_t *buf, size_t *pos)
{
    uint32_t be;
    memcpy(&be, buf + *pos, 4);
    *pos += 4;
    return ntohl(be);
}

wtc_result_t rpc_build_read_request(rpc_context_t *ctx,
                                     const read_request_params_t *params,
                                     uint8_t *buffer,
                                     size_t *buf_len)
{
    if (!ctx || !params || !buffer || !buf_len) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (*buf_len < RPC_MAX_PDU_SIZE) {
        return WTC_ERROR_NO_MEMORY;
    }

    size_t pos = sizeof(profinet_rpc_header_t);

    /* NDR request header — reserve 20 bytes, fill after blocks are built */
    size_t ndr_header_pos = pos;
    pos += NDR_REQUEST_HEADER_SIZE;
    size_t pnio_blocks_start = pos;

    /* IODReadReqHeader block (IEC 61158-6 §5.2.3.9) */
    size_t block_start = pos;
    pos += 6;  /* Skip block header, fill later */

    write_u16_be(buffer, 1, &pos);             /* SeqNumber */
    memcpy(buffer + pos, params->ar_uuid, 16); /* ARUUID */
    pos += 16;
    write_u32_be(buffer, params->api, &pos);   /* API */
    write_u16_be(buffer, params->slot, &pos);  /* SlotNumber */
    write_u16_be(buffer, params->subslot, &pos); /* SubslotNumber */
    write_u16_be(buffer, 0, &pos);             /* Padding */
    write_u16_be(buffer, params->index, &pos); /* Index */
    write_u32_be(buffer, params->max_record_length, &pos); /* RecordDataLength */

    /* TargetARUUID — 16 bytes of zeros (not used for explicit reads) */
    memset(buffer + pos, 0, 16);
    pos += 16;

    /* Padding to 4-byte alignment (8 bytes padding per spec) */
    memset(buffer + pos, 0, 8);
    pos += 8;

    /* Fill block header */
    size_t block_len = pos - block_start - 4;
    size_t save_pos = block_start;
    write_block_header(buffer, BLOCK_TYPE_IOD_READ_REQ_HEADER,
                        (uint16_t)block_len, &save_pos);

    /* Fill NDR header */
    uint32_t pnio_len = (uint32_t)(pos - pnio_blocks_start);
    uint32_t args_max = (uint32_t)(RPC_MAX_PDU_SIZE - sizeof(profinet_rpc_header_t));
    write_ndr_request_header(buffer, ndr_header_pos, args_max, pnio_len);

    /* Build RPC header (OpNum = READ) */
    uint16_t fragment_length = (uint16_t)(pos - sizeof(profinet_rpc_header_t));
    rpc_generate_uuid(ctx->activity_uuid);
    build_rpc_header(buffer, ctx, params->ar_uuid, RPC_OPNUM_READ,
                      fragment_length, &save_pos);

    *buf_len = pos;
    LOG_DEBUG("Built Read Request PDU: %zu bytes, index=0x%04X, slot=%u, subslot=%u",
              pos, params->index, params->slot, params->subslot);
    return WTC_OK;
}

/**
 * @brief Parse RealIdentificationData (index 0xF844) from response data.
 *
 * Format: NumberOfAPIs(u16), then for each API:
 *   API(u32), NumberOfSlots(u16), then for each slot:
 *     SlotNumber(u16), ModuleIdentNumber(u32), NumberOfSubslots(u16),
 *     then for each subslot:
 *       SubslotNumber(u16), SubmoduleIdentNumber(u32)
 */
static wtc_result_t parse_real_identification_data(const uint8_t *data,
                                                     size_t data_len,
                                                     read_response_t *response)
{
    size_t pos = 0;

    /* Parse block header if present (BlockType 0x0240) */
    if (pos + 6 <= data_len) {
        uint16_t block_type = read_u16_be(data, &pos);
        if (block_type == BLOCK_TYPE_REAL_IDENT_DATA) {
            pos += 2;  /* block_length */
            pos += 2;  /* version */
        } else {
            /* Not a block header, reset and parse raw data */
            pos = 0;
        }
    }

    if (pos + 2 > data_len) {
        LOG_ERROR("RealIdentificationData too short for API count");
        return WTC_ERROR_PROTOCOL;
    }

    uint16_t api_count = read_u16_be(data, &pos);
    LOG_DEBUG("RealIdentificationData: %u APIs", api_count);

    response->module_count = 0;

    for (uint16_t a = 0; a < api_count && pos + 6 <= data_len; a++) {
        uint32_t api = read_u32_be(data, &pos);
        if (pos + 2 > data_len) break;
        uint16_t slot_count = read_u16_be(data, &pos);

        LOG_DEBUG("  API %u: %u slots", api, slot_count);

        for (uint16_t s = 0; s < slot_count && pos + 8 <= data_len; s++) {
            uint16_t slot_num = read_u16_be(data, &pos);
            uint32_t module_ident = read_u32_be(data, &pos);
            if (pos + 2 > data_len) break;
            uint16_t subslot_count = read_u16_be(data, &pos);

            LOG_DEBUG("    Slot %u: module=0x%08X, %u subslots",
                      slot_num, module_ident, subslot_count);

            for (uint16_t ss = 0; ss < subslot_count && pos + 6 <= data_len; ss++) {
                uint16_t subslot_num = read_u16_be(data, &pos);
                uint32_t submod_ident = read_u32_be(data, &pos);

                if (response->module_count < RPC_MAX_DISCOVERED_MODULES) {
                    discovered_module_t *m = &response->modules[response->module_count];
                    m->slot = slot_num;
                    m->subslot = subslot_num;
                    m->module_ident = module_ident;
                    m->submodule_ident = submod_ident;
                    response->module_count++;

                    LOG_DEBUG("      Subslot 0x%04X: submod=0x%08X",
                              subslot_num, submod_ident);
                }
            }

            (void)api;
        }
    }

    LOG_INFO("RealIdentificationData: discovered %d modules", response->module_count);
    return WTC_OK;
}

wtc_result_t rpc_parse_read_response(const uint8_t *buffer,
                                      size_t buf_len,
                                      read_response_t *response)
{
    if (!buffer || !response || buf_len < sizeof(profinet_rpc_header_t)) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memset(response, 0, sizeof(read_response_t));

    const profinet_rpc_header_t *hdr = (const profinet_rpc_header_t *)buffer;

    if (hdr->packet_type == RPC_PACKET_TYPE_FAULT) {
        LOG_ERROR("Read response: RPC fault received");
        response->success = false;
        response->error_code = PNIO_ERR_CODE_READ;
        return WTC_ERROR_PROTOCOL;
    }

    if (hdr->packet_type != RPC_PACKET_TYPE_RESPONSE) {
        LOG_ERROR("Read response: unexpected packet type %u", hdr->packet_type);
        response->success = false;
        return WTC_ERROR_PROTOCOL;
    }

    size_t pos = sizeof(profinet_rpc_header_t);

    /* NDR response header (24 bytes):
     * ArgsMaximum(4), ErrorStatus1(4), ErrorStatus2(4),
     * MaxCount(4), Offset(4), ActualCount(4) */
    bool has_ndr = response_has_ndr_header(buffer, pos, buf_len);

    if (has_ndr) {
        if (pos + 24 > buf_len) {
            LOG_ERROR("Read response too short for NDR header");
            return WTC_ERROR_PROTOCOL;
        }

        pos += 4;  /* ArgsMaximum */

        uint32_t error_status1 = buffer[pos] | (buffer[pos+1] << 8) |
                                 (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
        pos += 4;
        uint32_t error_status2 = buffer[pos] | (buffer[pos+1] << 8) |
                                 (buffer[pos+2] << 16) | (buffer[pos+3] << 24);
        pos += 4;

        if (error_status1 != 0 || error_status2 != 0) {
            LOG_ERROR("Read response PNIO error: status1=0x%08X, status2=0x%08X",
                      error_status1, error_status2);
            response->success = false;
            response->error_code = (uint8_t)(error_status2 & 0xFF);
            return WTC_ERROR_PROTOCOL;
        }

        pos += 4;  /* MaxCount */
        pos += 4;  /* Offset */
        pos += 4;  /* ActualCount */
    }

    /* Parse IODReadResHeader block (0x8009) */
    if (pos + 6 > buf_len) {
        LOG_ERROR("Read response: no block header");
        return WTC_ERROR_PROTOCOL;
    }

    uint16_t block_type = read_u16_be(buffer, &pos);
    uint16_t block_length = read_u16_be(buffer, &pos);

    if (block_type != BLOCK_TYPE_IOD_READ_RES_HEADER) {
        LOG_ERROR("Read response: unexpected block type 0x%04X (expected 0x8009)",
                  block_type);
        return WTC_ERROR_PROTOCOL;
    }

    if (block_length < 2) {
        LOG_ERROR("Read response: block length too small: %u", block_length);
        return WTC_ERROR_PROTOCOL;
    }

    pos += 2;  /* Version */
    pos += 2;  /* SeqNumber */
    pos += 16; /* ARUUID */
    pos += 4;  /* API */
    pos += 2;  /* SlotNumber */
    pos += 2;  /* SubslotNumber */
    pos += 2;  /* Padding */

    if (pos + 6 > buf_len) {
        LOG_ERROR("Read response: truncated after header fields");
        return WTC_ERROR_PROTOCOL;
    }

    response->index = read_u16_be(buffer, &pos);
    response->record_data_length = read_u32_be(buffer, &pos);

    /* Skip additional padding (20 bytes: TargetARUUID + padding) */
    size_t remaining_header = (block_length + 4) - (pos - (pos - block_length - 4 + 6));
    /* Simpler: advance to where record data starts based on block_length */
    /* IODReadResHeader total = 6 (header) + block_length bytes
     * We've parsed: 6 (header) + 2(ver) + 2(seq) + 16(uuid) + 4(api) +
     *               2(slot) + 2(subslot) + 2(pad) + 2(index) + 4(len) = 42
     * Remaining in block: block_length - (42 - 6) = block_length - 36
     * This includes TargetARUUID(16) + padding(8) = 24 bytes */
    (void)remaining_header;
    if (pos + 24 <= buf_len) {
        pos += 16; /* TargetARUUID */
        pos += 8;  /* Padding */
    }

    response->success = true;

    LOG_DEBUG("Read response: index=0x%04X, data_length=%u",
              response->index, response->record_data_length);

    /* Parse the record data payload */
    if (response->record_data_length > 0 && pos < buf_len) {
        size_t data_available = buf_len - pos;
        if (data_available > response->record_data_length) {
            data_available = response->record_data_length;
        }

        /* If this is RealIdentificationData (0xF844), parse the modules */
        if (response->index == 0xF844) {
            wtc_result_t res = parse_real_identification_data(
                buffer + pos, data_available, response);
            if (res != WTC_OK) {
                LOG_WARN("Failed to parse RealIdentificationData, "
                         "response still valid");
            }
        }
    }

    return WTC_OK;
}

wtc_result_t rpc_read_record(rpc_context_t *ctx,
                              uint32_t device_ip,
                              const read_request_params_t *params,
                              read_response_t *response)
{
    if (!ctx || !params || !response) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint8_t req_buf[RPC_MAX_PDU_SIZE];
    uint8_t resp_buf[RPC_MAX_PDU_SIZE];
    size_t req_len = sizeof(req_buf);
    size_t resp_len = sizeof(resp_buf);

    wtc_result_t res;

    res = rpc_build_read_request(ctx, params, req_buf, &req_len);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to build read request");
        return res;
    }

    res = rpc_send_and_receive(ctx, device_ip, req_buf, req_len,
                                resp_buf, &resp_len, RPC_READ_TIMEOUT_MS);
    if (res != WTC_OK) {
        LOG_ERROR("Read RPC failed");
        return res;
    }

    res = rpc_parse_read_response(resp_buf, resp_len, response);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to parse read response");
        return res;
    }

    LOG_INFO("RPC Read successful: index=0x%04X, %d modules discovered",
             response->index, response->module_count);
    return WTC_OK;
}
