/*
 * Water Treatment Controller - PROFINET RPC Protocol
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Implementation of PROFINET RPC (Remote Procedure Call) protocol
 * for Application Relationship establishment per IEC 61158-6.
 */

#ifndef WTC_PROFINET_RPC_H
#define WTC_PROFINET_RPC_H

#include "types.h"
#include "profinet_frame.h"
#include "profinet_controller.h"
#include "rpc_strategy.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ============== RPC Constants (IEC 61158-6) ============== */

/* Maximum RPC PDU size */
#define RPC_MAX_PDU_SIZE            1464

/* RPC Port */
#define PNIO_RPC_PORT               34964

/* RPC Version */
#define RPC_VERSION_MAJOR           4
#define RPC_VERSION_MINOR           0

/* RPC Packet Types */
#define RPC_PACKET_TYPE_REQUEST     0
#define RPC_PACKET_TYPE_PING        1
#define RPC_PACKET_TYPE_RESPONSE    2
#define RPC_PACKET_TYPE_FAULT       3
#define RPC_PACKET_TYPE_WORKING     4
#define RPC_PACKET_TYPE_NOCALL      5
#define RPC_PACKET_TYPE_REJECT      6
#define RPC_PACKET_TYPE_ACK         7
#define RPC_PACKET_TYPE_CANCEL      8

/* RPC Operation Numbers (OpNum) - PROFINET IO */
#define RPC_OPNUM_CONNECT           0
#define RPC_OPNUM_RELEASE           1
#define RPC_OPNUM_READ              2
#define RPC_OPNUM_WRITE             3
#define RPC_OPNUM_CONTROL           4
#define RPC_OPNUM_READ_IMPLICIT     5

/* RPC Flags */
#define RPC_FLAG1_LAST_FRAGMENT     0x02
#define RPC_FLAG1_FRAGMENT          0x04
#define RPC_FLAG1_NO_FAS            0x08
#define RPC_FLAG1_MAYBE             0x10
#define RPC_FLAG1_IDEMPOTENT        0x20
#define RPC_FLAG1_BROADCAST         0x40

/* Data Representation (DREP) */
#define RPC_DREP_LITTLE_ENDIAN      0x10
#define RPC_DREP_ASCII              0x00

/* ============== PROFINET Block Types ============== */

/* Request blocks */
#define BLOCK_TYPE_AR_BLOCK_REQ             0x0101
#define BLOCK_TYPE_IOCR_BLOCK_REQ           0x0102
#define BLOCK_TYPE_ALARM_CR_BLOCK_REQ       0x0103
#define BLOCK_TYPE_EXPECTED_SUBMOD_BLOCK    0x0104
#define BLOCK_TYPE_PRM_SERVER_BLOCK         0x0105
#define BLOCK_TYPE_MCR_BLOCK_REQ            0x0106
#define BLOCK_TYPE_AR_RPC_BLOCK_REQ         0x0107
#define BLOCK_TYPE_IR_INFO_BLOCK            0x0108

/* Response blocks */
#define BLOCK_TYPE_AR_BLOCK_RES             0x8101
#define BLOCK_TYPE_IOCR_BLOCK_RES           0x8102
#define BLOCK_TYPE_ALARM_CR_BLOCK_RES       0x8103
#define BLOCK_TYPE_MODULE_DIFF_BLOCK        0x8104
#define BLOCK_TYPE_AR_RPC_BLOCK_RES         0x8107

/* Control blocks */
#define BLOCK_TYPE_IOD_CONTROL_REQ          0x0110
#define BLOCK_TYPE_IOD_CONTROL_RES          0x8110
#define BLOCK_TYPE_IOX_CONTROL_REQ          0x0112
#define BLOCK_TYPE_IOX_CONTROL_RES          0x8112

/* Read/Write blocks */
#define BLOCK_TYPE_IOD_READ_REQ_HEADER      0x0009
#define BLOCK_TYPE_IOD_READ_RES_HEADER      0x8009
#define BLOCK_TYPE_IOD_WRITE_REQ_HEADER     0x0008
#define BLOCK_TYPE_IOD_WRITE_RES_HEADER     0x8008

/* Release block */
#define BLOCK_TYPE_IOD_RELEASE_BLOCK        0x0114

/* ============== AR Properties ============== */

#define AR_PROP_STATE_ACTIVE            0x00000001
#define AR_PROP_PARAMETERIZATION_TYPE   0x00000002  /* 0=device, 1=controller */
#define AR_PROP_SUPERVISOR_TAKEOVER     0x00000008
#define AR_PROP_DATA_RATE_MASK          0x00000030  /* 0=reserved, 1=class1, 2=class2, 3=class3 */
#define AR_PROP_DEVICE_ACCESS           0x00000100
#define AR_PROP_COMPANION_AR            0x00000200
#define AR_PROP_ACKNOWLEDGE_COMPANION   0x00000400
#define AR_PROP_STARTUP_MODE_LEGACY     0x00000000
#define AR_PROP_STARTUP_MODE_ADVANCED   0x40000000
#define AR_PROP_PULL_MODULE_ALARM       0x80000000

/* ============== IOCR Properties ============== */

#define IOCR_PROP_RT_CLASS_MASK         0x0000000F
#define IOCR_PROP_RT_CLASS_1            0x00000001
#define IOCR_PROP_RT_CLASS_2            0x00000002
#define IOCR_PROP_RT_CLASS_3            0x00000003
#define IOCR_PROP_RT_CLASS_UDP          0x00000004
#define IOCR_PROP_MEDIA_REDUNDANCY      0x00000800

/* ============== Control Command Types ============== */

#define CONTROL_CMD_PRM_END             0x0001
#define CONTROL_CMD_APP_READY           0x0002
#define CONTROL_CMD_RELEASE             0x0003
#define CONTROL_CMD_PRM_BEGIN           0x0004
#define CONTROL_CMD_READY_FOR_COMPANION 0x0005
#define CONTROL_CMD_READY_FOR_RTC3      0x0006

/* ============== Error Codes ============== */

#define PNIO_ERR_CODE_OK                0x00
#define PNIO_ERR_CODE_CONNECT           0xC0
#define PNIO_ERR_CODE_RELEASE           0xC1
#define PNIO_ERR_CODE_READ              0xC2
#define PNIO_ERR_CODE_WRITE             0xC3
#define PNIO_ERR_CODE_CONTROL           0xC4

/* ============== UUIDs ============== */

/* PROFINET IO Device Interface UUID */
extern const uint8_t PNIO_DEVICE_INTERFACE_UUID[16];

/* PROFINET IO Controller Interface UUID */
extern const uint8_t PNIO_CONTROLLER_INTERFACE_UUID[16];

/* ============== Structures ============== */

/* Block header (common to all PROFINET blocks) */
typedef struct __attribute__((packed)) {
    uint16_t type;          /* Block type */
    uint16_t length;        /* Block length (excluding type and length) */
    uint8_t version_high;   /* Block version major */
    uint8_t version_low;    /* Block version minor */
} pnio_block_header_t;

/* AR Block Request (Connect Request) */
typedef struct __attribute__((packed)) {
    pnio_block_header_t header;
    uint16_t ar_type;               /* AR type (IOCAR, supervisor, etc.) */
    uint8_t ar_uuid[16];            /* AR UUID (generated by controller) */
    uint16_t session_key;           /* Session key */
    uint8_t cm_initiator_mac[6];    /* Controller MAC address */
    uint8_t cm_initiator_uuid[16];  /* Controller object UUID */
    uint32_t ar_properties;         /* AR properties */
    uint16_t cm_initiator_activity_timeout; /* Timeout factor */
    uint16_t cm_initiator_udp_port; /* Controller RPC port (usually 34964) */
    uint16_t station_name_length;   /* Length of station name */
    /* Followed by station name (padded to 4-byte boundary) */
} pnio_ar_block_req_t;

/* AR Block Response */
typedef struct __attribute__((packed)) {
    pnio_block_header_t header;
    uint16_t ar_type;
    uint8_t ar_uuid[16];
    uint16_t session_key;
    uint8_t cm_responder_mac[6];    /* Device MAC address */
    uint16_t cm_responder_udp_port; /* Device RPC port */
} pnio_ar_block_res_t;

/* IOCR Block Request */
typedef struct __attribute__((packed)) {
    pnio_block_header_t header;
    uint16_t iocr_type;             /* Input (1) or Output (2) */
    uint16_t iocr_reference;        /* IOCR reference (local identifier) */
    uint16_t lt_field;              /* LT field (Ethertype, usually 0x8892) */
    uint32_t iocr_properties;       /* RT class, redundancy */
    uint16_t data_length;           /* Total data length */
    uint16_t frame_id;              /* Assigned Frame ID */
    uint16_t send_clock_factor;     /* 32 = 1ms cycle */
    uint16_t reduction_ratio;       /* Reduction from base cycle */
    uint16_t phase;                 /* Send phase */
    uint16_t sequence;              /* Sequence number */
    uint32_t frame_send_offset;     /* Time offset in ns */
    uint16_t watchdog_factor;       /* Watchdog timeout factor */
    uint16_t data_hold_factor;      /* Data hold timeout factor */
    uint16_t iocr_tag_header;       /* VLAN tag handling */
    uint8_t iocr_multicast_mac[6];  /* Multicast MAC (if used) */
    uint16_t api_count;             /* Number of APIs in this IOCR */
    /* Followed by API structures */
} pnio_iocr_block_req_t;

/* API structure within IOCR */
typedef struct __attribute__((packed)) {
    uint32_t api;                   /* API number (usually 0) */
    uint16_t slot_count;            /* Number of slots */
    /* Followed by slot data */
} pnio_iocr_api_t;

/* Slot/Subslot structure */
typedef struct __attribute__((packed)) {
    uint16_t slot_number;
    uint32_t module_ident;
    uint16_t subslot_count;
    /* Followed by subslot data */
} pnio_slot_t;

typedef struct __attribute__((packed)) {
    uint16_t subslot_number;
    uint32_t submodule_ident;
} pnio_subslot_t;

/* IOCR Block Response */
typedef struct __attribute__((packed)) {
    pnio_block_header_t header;
    uint16_t iocr_type;
    uint16_t iocr_reference;
    uint16_t frame_id;              /* Assigned Frame ID (may differ) */
} pnio_iocr_block_res_t;

/* Alarm CR Block Request */
typedef struct __attribute__((packed)) {
    pnio_block_header_t header;
    uint16_t alarm_cr_type;         /* Alarm CR type (always 1) */
    uint16_t lt_field;              /* LT field (0x8892) */
    uint32_t alarm_cr_properties;   /* Properties */
    uint16_t rta_timeout_factor;    /* RTA timeout */
    uint16_t rta_retries;           /* RTA retries */
    uint16_t local_alarm_ref;       /* Local alarm reference */
    uint16_t max_alarm_data_length; /* Max alarm data (200 typical) */
    uint16_t alarm_cr_tag_header_high;
    uint16_t alarm_cr_tag_header_low;
} pnio_alarm_cr_block_req_t;

/* Alarm CR Block Response */
typedef struct __attribute__((packed)) {
    pnio_block_header_t header;
    uint16_t alarm_cr_type;
    uint16_t local_alarm_ref;       /* Device's local alarm reference */
    uint16_t max_alarm_data_length;
} pnio_alarm_cr_block_res_t;

/* Expected Submodule Block */
typedef struct __attribute__((packed)) {
    pnio_block_header_t header;
    uint16_t api_count;
    /* Followed by expected configuration */
} pnio_expected_submod_block_t;

/* IOD Control Request (PrmEnd, ApplicationReady, Release) */
typedef struct __attribute__((packed)) {
    pnio_block_header_t header;
    uint16_t reserved1;
    uint8_t ar_uuid[16];
    uint16_t session_key;
    uint16_t reserved2;
    uint16_t control_command;       /* PrmEnd, AppReady, Release */
    uint16_t control_block_properties;
} pnio_iod_control_req_t;

/* IOD Control Response */
typedef struct __attribute__((packed)) {
    pnio_block_header_t header;
    uint16_t reserved1;
    uint8_t ar_uuid[16];
    uint16_t session_key;
    uint16_t reserved2;
    uint16_t control_command;
    uint16_t control_block_properties;
} pnio_iod_control_res_t;

/* Release Block */
typedef struct __attribute__((packed)) {
    pnio_block_header_t header;
    uint16_t reserved1;
    uint8_t ar_uuid[16];
    uint16_t session_key;
    uint16_t reserved2;
    uint16_t control_command;       /* Always CONTROL_CMD_RELEASE */
    uint16_t control_block_properties;
} pnio_release_block_t;

/* Module Diff Block (in Connect Response when configuration differs) */
typedef struct __attribute__((packed)) {
    pnio_block_header_t header;
    uint16_t api_count;
    /* Followed by diff information */
} pnio_module_diff_block_t;

/* ============== RPC Context ============== */

typedef struct {
    int socket_fd;              /* UDP socket */
    uint8_t controller_mac[6];  /* Our MAC address */
    uint32_t controller_ip;     /* Our IP address */
    uint16_t controller_port;   /* Our RPC port */
    uint32_t sequence_number;   /* RPC sequence counter */
    uint8_t activity_uuid[16];  /* Current activity UUID */
} rpc_context_t;

/* ============== Connect Request/Response ============== */

/* Full Connect Request parameters */
typedef struct {
    /* AR configuration */
    uint8_t ar_uuid[16];        /* Generated AR UUID */
    uint16_t session_key;       /* Session key */
    ar_type_t ar_type;          /* AR type */
    uint32_t ar_properties;     /* AR properties */
    char station_name[64];      /* Device station name */

    /* Controller info */
    uint8_t controller_mac[6];
    uint8_t controller_uuid[16];
    uint16_t controller_port;
    uint16_t activity_timeout;

    /* IOCR configuration */
    struct {
        uint16_t type;          /* Input or Output */
        uint16_t reference;     /* Local reference */
        uint16_t frame_id;      /* Desired Frame ID */
        uint16_t data_length;   /* Data length */
        uint16_t send_clock_factor;
        uint16_t reduction_ratio;
        uint16_t watchdog_factor;
    } iocr[4];
    int iocr_count;

    /* Expected configuration */
    struct {
        uint16_t slot;
        uint32_t module_ident;
        uint16_t subslot;
        uint32_t submodule_ident;
        uint16_t data_length;
        bool is_input;
    } expected_config[WTC_MAX_SLOTS];
    int expected_count;

    /* Alarm CR */
    uint16_t max_alarm_data_length;
    uint16_t rta_timeout_factor;    /* RTA timeout (0 = use default 100) */
    uint16_t rta_retries;           /* RTA retries (0 = use default 3) */
    uint16_t data_hold_factor;      /* Data hold factor (0 = use default 3) */
} connect_request_params_t;

/* Connect Response result */
typedef struct {
    bool success;
    uint8_t ar_uuid[16];        /* Confirmed AR UUID */
    uint16_t session_key;
    uint8_t device_mac[6];      /* Device MAC */
    uint16_t device_port;       /* Device RPC port */

    /* Assigned Frame IDs (may differ from requested) */
    struct {
        uint16_t requested;
        uint16_t assigned;
    } frame_ids[4];
    int frame_id_count;

    /* Device alarm reference */
    uint16_t device_alarm_ref;

    /* Module differences (if any) */
    bool has_diff;
    int diff_count;

    /* Error info */
    uint8_t error_code;
    uint8_t error_decode;
    uint16_t error_code1;
    uint16_t error_code2;
} connect_response_t;

/* ============== Function Prototypes ============== */

/* Initialize RPC context */
wtc_result_t rpc_context_init(rpc_context_t *ctx,
                               const uint8_t *controller_mac,
                               uint32_t controller_ip);

/* Cleanup RPC context */
void rpc_context_cleanup(rpc_context_t *ctx);

/* Build Connect Request PDU */
wtc_result_t rpc_build_connect_request(rpc_context_t *ctx,
                                        const connect_request_params_t *params,
                                        uint8_t *buffer,
                                        size_t *buf_len);

/* Parse Connect Response PDU */
wtc_result_t rpc_parse_connect_response(const uint8_t *buffer,
                                         size_t buf_len,
                                         connect_response_t *response);

/* Build Control Request (PrmEnd, ApplicationReady) */
wtc_result_t rpc_build_control_request(rpc_context_t *ctx,
                                        const uint8_t *ar_uuid,
                                        uint16_t session_key,
                                        uint16_t control_command,
                                        uint8_t *buffer,
                                        size_t *buf_len);

/* Parse Control Response */
wtc_result_t rpc_parse_control_response(const uint8_t *buffer,
                                         size_t buf_len,
                                         uint16_t expected_command,
                                         bool *success);

/* Build Release Request */
wtc_result_t rpc_build_release_request(rpc_context_t *ctx,
                                        const uint8_t *ar_uuid,
                                        uint16_t session_key,
                                        uint8_t *buffer,
                                        size_t *buf_len);

/* Send RPC request and wait for response */
wtc_result_t rpc_send_and_receive(rpc_context_t *ctx,
                                   uint32_t device_ip,
                                   const uint8_t *request,
                                   size_t req_len,
                                   uint8_t *response,
                                   size_t *resp_len,
                                   uint32_t timeout_ms);

/* Generate UUID */
void rpc_generate_uuid(uint8_t *uuid);

/* High-level connect function */
wtc_result_t rpc_connect(rpc_context_t *ctx,
                          uint32_t device_ip,
                          const connect_request_params_t *params,
                          connect_response_t *response);

/* High-level parameter end function */
wtc_result_t rpc_parameter_end(rpc_context_t *ctx,
                                uint32_t device_ip,
                                const uint8_t *ar_uuid,
                                uint16_t session_key);

/* High-level application ready function */
wtc_result_t rpc_application_ready(rpc_context_t *ctx,
                                    uint32_t device_ip,
                                    const uint8_t *ar_uuid,
                                    uint16_t session_key);

/* High-level release function */
wtc_result_t rpc_release(rpc_context_t *ctx,
                          uint32_t device_ip,
                          const uint8_t *ar_uuid,
                          uint16_t session_key);

/* ============== Record Read/Write ============== */

/* Maximum discovered modules from a single Record Read 0xF844 */
#define RPC_MAX_DISCOVERED_MODULES  64

/* Record Read timeout */
#define RPC_READ_TIMEOUT_MS         5000

/* RealIdentificationData block type */
#define BLOCK_TYPE_REAL_IDENT_DATA  0x0240

/* Record Read request parameters */
typedef struct {
    uint8_t ar_uuid[16];        /* AR UUID (from connect) */
    uint16_t session_key;       /* Session key */
    uint32_t api;               /* API number (0 = default) */
    uint16_t slot;              /* Slot (0xFFFF = all) */
    uint16_t subslot;           /* Subslot (0xFFFF = all) */
    uint16_t index;             /* Record index (e.g. 0xF844) */
    uint32_t max_record_length; /* Max response data length */
} read_request_params_t;

/* Discovered module from RealIdentificationData (0xF844) */
typedef struct {
    uint16_t slot;
    uint16_t subslot;
    uint32_t module_ident;
    uint32_t submodule_ident;
} discovered_module_t;

/* Record Read response */
typedef struct {
    bool success;
    uint16_t index;             /* Echoed record index */
    uint32_t record_data_length;/* Actual data length */

    /* For 0xF844 (RealIdentificationData) parsing */
    discovered_module_t modules[RPC_MAX_DISCOVERED_MODULES];
    int module_count;

    /* Error info */
    uint8_t error_code;
    uint16_t error_code1;
    uint16_t error_code2;
} read_response_t;

/* Build Record Read Request PDU (OpNum 2) */
wtc_result_t rpc_build_read_request(rpc_context_t *ctx,
                                     const read_request_params_t *params,
                                     uint8_t *buffer,
                                     size_t *buf_len);

/* Parse Record Read Response PDU */
wtc_result_t rpc_parse_read_response(const uint8_t *buffer,
                                      size_t buf_len,
                                      read_response_t *response);

/* High-level Record Read: send request, receive and parse response */
wtc_result_t rpc_read_record(rpc_context_t *ctx,
                              uint32_t device_ip,
                              const read_request_params_t *params,
                              read_response_t *response);

/* ============== RPC Server (for incoming requests from device) ============== */

/* Incoming Control Request info (parsed from device's ApplicationReady) */
typedef struct {
    uint8_t ar_uuid[16];        /* AR UUID from request */
    uint16_t session_key;       /* Session key from request */
    uint16_t control_command;   /* Control command (APP_READY, etc.) */
    uint32_t source_ip;         /* Source IP of the request */
    uint16_t source_port;       /* Source port of the request */
    uint8_t activity_uuid[16];  /* Activity UUID for response */
    uint32_t sequence_number;   /* Sequence number for response */
} incoming_control_request_t;

/**
 * @brief Poll for incoming RPC requests (non-blocking).
 *
 * Checks the RPC socket for incoming UDP packets from devices.
 * Used to receive ApplicationReady callbacks from RTU.
 *
 * @param[in]  ctx       RPC context
 * @param[out] buffer    Buffer to receive data
 * @param[in]  buf_size  Size of buffer
 * @param[out] recv_len  Actual received length (0 if no data)
 * @param[out] source_ip Source IP address (network byte order)
 * @param[out] source_port Source port (host byte order)
 * @return WTC_OK on success (check recv_len for data), error on failure
 */
wtc_result_t rpc_poll_incoming(rpc_context_t *ctx,
                                uint8_t *buffer,
                                size_t buf_size,
                                size_t *recv_len,
                                uint32_t *source_ip,
                                uint16_t *source_port);

/**
 * @brief Parse incoming Control Request (ApplicationReady from device).
 *
 * @param[in]  buffer    Received RPC packet
 * @param[in]  buf_len   Length of received data
 * @param[out] request   Parsed request info
 * @return WTC_OK on success, error code on failure
 */
wtc_result_t rpc_parse_incoming_control_request(const uint8_t *buffer,
                                                  size_t buf_len,
                                                  incoming_control_request_t *request);

/**
 * @brief Build Control Response for incoming request.
 *
 * Builds a response to send back to device after receiving ApplicationReady.
 *
 * @param[in]  ctx             RPC context
 * @param[in]  request         The incoming request we're responding to
 * @param[out] buffer          Output buffer
 * @param[in,out] buf_len      Buffer size in, PDU length out
 * @return WTC_OK on success, error code on failure
 */
wtc_result_t rpc_build_control_response(rpc_context_t *ctx,
                                         const incoming_control_request_t *request,
                                         uint8_t *buffer,
                                         size_t *buf_len);

/**
 * @brief Send Control Response to device.
 *
 * @param[in] ctx        RPC context
 * @param[in] dest_ip    Destination IP (network byte order)
 * @param[in] dest_port  Destination port (host byte order)
 * @param[in] response   Response buffer
 * @param[in] resp_len   Response length
 * @return WTC_OK on success, error code on failure
 */
wtc_result_t rpc_send_response(rpc_context_t *ctx,
                                uint32_t dest_ip,
                                uint16_t dest_port,
                                const uint8_t *response,
                                size_t resp_len);

#ifdef __cplusplus
}
#endif

#endif /* WTC_PROFINET_RPC_H */
