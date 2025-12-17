/*
 * Water Treatment Controller - PROFINET IO Controller
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_PROFINET_CONTROLLER_H
#define WTC_PROFINET_CONTROLLER_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* PROFINET constants */
#define PROFINET_ETHERTYPE              0x8892
#define PROFINET_FRAME_ID_RTC1_MIN      0x8000
#define PROFINET_FRAME_ID_RTC1_MAX      0xBFFF
#define PROFINET_FRAME_ID_DCP           0xFEFC
#define PROFINET_FRAME_ID_DCP_HELLO     0xFEFD
#define PROFINET_FRAME_ID_DCP_GETSET    0xFEFE
#define PROFINET_FRAME_ID_DCP_IDENT     0xFEFF

#define PROFINET_MIN_CYCLE_TIME_US      31250   /* 31.25 µs (32 * 31.25 = 1ms) */
#define PROFINET_MAX_AR                 256
#define PROFINET_MAX_IOCR               64
#define PROFINET_MAX_API                256

/* Application Relationship (AR) types */
typedef enum {
    AR_TYPE_IOCAR = 0x0001,       /* IO Controller AR */
    AR_TYPE_SUPERVISOR = 0x0006,   /* Supervisor AR */
    AR_TYPE_SINGLE = 0x0010,       /* Single AR */
} ar_type_t;

/* AR state machine */
typedef enum {
    AR_STATE_INIT = 0,
    AR_STATE_CONNECT_REQ,
    AR_STATE_CONNECT_CNF,
    AR_STATE_PRMSRV,
    AR_STATE_READY,
    AR_STATE_RUN,
    AR_STATE_CLOSE,
    AR_STATE_ABORT,
} ar_state_t;

/* IO CR (Communication Relationship) types */
typedef enum {
    IOCR_TYPE_INPUT = 0x0001,
    IOCR_TYPE_OUTPUT = 0x0002,
    IOCR_TYPE_MULTICAST = 0x0003,
} iocr_type_t;

/* PROFINET controller configuration */
typedef struct {
    char interface_name[32];        /* Network interface (e.g., "eth0") */
    uint8_t mac_address[6];         /* Controller MAC address */
    uint32_t ip_address;            /* Controller IP address */
    uint32_t subnet_mask;           /* Subnet mask */
    uint32_t gateway;               /* Default gateway */

    uint16_t vendor_id;             /* Controller vendor ID */
    uint16_t device_id;             /* Controller device ID */
    char station_name[64];          /* Controller station name */

    uint32_t cycle_time_us;         /* Base cycle time in microseconds */
    uint16_t reduction_ratio;       /* Cycle time reduction ratio */
    uint16_t send_clock_factor;     /* Send clock factor (32 = 1ms) */

    bool use_raw_sockets;           /* Use raw sockets for RT frames */
    int socket_priority;            /* Socket priority for QoS */

    /* Callbacks */
    void (*on_device_added)(const rtu_device_t *device, void *ctx);
    void (*on_device_removed)(const char *station_name, void *ctx);
    void (*on_device_state_changed)(const char *station_name, profinet_state_t state, void *ctx);
    void (*on_data_received)(const char *station_name, int slot, const void *data, size_t len, void *ctx);
    void *callback_ctx;
} profinet_config_t;

/* AR (Application Relationship) handle */
typedef struct {
    uint32_t ar_uuid[4];            /* AR UUID */
    uint16_t session_key;
    ar_type_t type;
    ar_state_t state;

    char device_station_name[64];
    uint8_t device_mac[6];
    uint32_t device_ip;

    /* IO CRs */
    struct {
        iocr_type_t type;
        uint16_t frame_id;
        uint32_t send_clock_factor;
        uint32_t reduction_ratio;
        uint32_t data_length;
        uint8_t *data_buffer;
        uint64_t last_frame_time_us;
    } iocr[PROFINET_MAX_IOCR];
    int iocr_count;

    /* Timing */
    uint64_t last_activity_ms;
    uint32_t watchdog_ms;

    /* Internal */
    void *internal;
} profinet_ar_t;

/* PROFINET controller handle */
typedef struct profinet_controller profinet_controller_t;

/* Initialize PROFINET controller */
wtc_result_t profinet_controller_init(profinet_controller_t **controller,
                                       const profinet_config_t *config);

/* Cleanup PROFINET controller */
void profinet_controller_cleanup(profinet_controller_t *controller);

/* Start PROFINET controller */
wtc_result_t profinet_controller_start(profinet_controller_t *controller);

/* Stop PROFINET controller */
wtc_result_t profinet_controller_stop(profinet_controller_t *controller);

/* Process PROFINET frames (call from main loop or dedicated thread) */
wtc_result_t profinet_controller_process(profinet_controller_t *controller);

/* Connect to device */
wtc_result_t profinet_controller_connect(profinet_controller_t *controller,
                                          const char *station_name,
                                          const slot_config_t *slots,
                                          int slot_count);

/* Disconnect from device */
wtc_result_t profinet_controller_disconnect(profinet_controller_t *controller,
                                             const char *station_name);

/* Get device AR handle */
profinet_ar_t *profinet_controller_get_ar(profinet_controller_t *controller,
                                          const char *station_name);

/* Read input data from device */
wtc_result_t profinet_controller_read_input(profinet_controller_t *controller,
                                             const char *station_name,
                                             int slot,
                                             void *data,
                                             size_t *len,
                                             iops_t *status);

/* Write output data to device */
wtc_result_t profinet_controller_write_output(profinet_controller_t *controller,
                                               const char *station_name,
                                               int slot,
                                               const void *data,
                                               size_t len);

/* Read record data (acyclic) */
wtc_result_t profinet_controller_read_record(profinet_controller_t *controller,
                                              const char *station_name,
                                              uint32_t api,
                                              uint16_t slot,
                                              uint16_t subslot,
                                              uint16_t index,
                                              void *data,
                                              size_t *len);

/* Write record data (acyclic) */
wtc_result_t profinet_controller_write_record(profinet_controller_t *controller,
                                               const char *station_name,
                                               uint32_t api,
                                               uint16_t slot,
                                               uint16_t subslot,
                                               uint16_t index,
                                               const void *data,
                                               size_t len);

/* Get controller statistics */
wtc_result_t profinet_controller_get_stats(profinet_controller_t *controller,
                                            cycle_stats_t *stats);

#ifdef __cplusplus
}
#endif

#endif /* WTC_PROFINET_CONTROLLER_H */
