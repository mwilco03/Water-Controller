/*
 * Water Treatment Controller - DCP Discovery Protocol
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef WTC_DCP_DISCOVERY_H
#define WTC_DCP_DISCOVERY_H

#include "types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* DCP Service IDs */
#define DCP_SERVICE_GET         0x03
#define DCP_SERVICE_SET         0x04
#define DCP_SERVICE_IDENTIFY    0x05
#define DCP_SERVICE_HELLO       0x06

/* DCP Service Types */
#define DCP_SERVICE_TYPE_REQUEST        0x00
#define DCP_SERVICE_TYPE_RESPONSE_OK    0x01
#define DCP_SERVICE_TYPE_RESPONSE_ERR   0x05

/* DCP Block Options */
#define DCP_OPTION_IP               0x01
#define DCP_OPTION_DEVICE           0x02
#define DCP_OPTION_DHCP             0x03
#define DCP_OPTION_CONTROL          0x05
#define DCP_OPTION_DEVICE_INITIATIVE 0x06
#define DCP_OPTION_ALL              0xFF

/* DCP Block Suboptions - IP */
#define DCP_SUBOPTION_IP_MAC        0x01
#define DCP_SUBOPTION_IP_PARAMETER  0x02
#define DCP_SUBOPTION_IP_FULL       0x03

/* DCP Block Suboptions - Device */
#define DCP_SUBOPTION_DEVICE_VENDOR         0x01
#define DCP_SUBOPTION_DEVICE_NAME           0x02
#define DCP_SUBOPTION_DEVICE_ID             0x03
#define DCP_SUBOPTION_DEVICE_ROLE           0x04
#define DCP_SUBOPTION_DEVICE_OPTIONS        0x05
#define DCP_SUBOPTION_DEVICE_ALIAS          0x06
#define DCP_SUBOPTION_DEVICE_INSTANCE       0x07
#define DCP_SUBOPTION_DEVICE_OEM_ID         0x08

/* DCP Block Suboptions - Control */
#define DCP_SUBOPTION_CONTROL_START         0x01
#define DCP_SUBOPTION_CONTROL_STOP          0x02
#define DCP_SUBOPTION_CONTROL_SIGNAL        0x03
#define DCP_SUBOPTION_CONTROL_RESPONSE      0x04
#define DCP_SUBOPTION_CONTROL_RESET_TO_FACTORY 0x05

/* DCP discovered device info */
typedef struct {
    uint8_t mac_address[6];
    uint32_t ip_address;
    uint32_t subnet_mask;
    uint32_t gateway;
    char station_name[64];
    char vendor_name[64];
    uint16_t vendor_id;
    uint16_t device_id;
    uint16_t device_role;
    char device_instance[16];
    bool ip_set;
    bool name_set;
    uint64_t discovered_time_ms;
} dcp_device_info_t;

/* DCP discovery context */
typedef struct dcp_discovery dcp_discovery_t;

/* Discovery callback */
typedef void (*dcp_discovery_callback_t)(const dcp_device_info_t *device, void *ctx);

/* Initialize DCP discovery */
wtc_result_t dcp_discovery_init(dcp_discovery_t **discovery,
                                 const char *interface_name);

/* Cleanup DCP discovery */
void dcp_discovery_cleanup(dcp_discovery_t *discovery);

/* Start discovery process */
wtc_result_t dcp_discovery_start(dcp_discovery_t *discovery,
                                  dcp_discovery_callback_t callback,
                                  void *ctx);

/* Stop discovery process */
wtc_result_t dcp_discovery_stop(dcp_discovery_t *discovery);

/* Send identify request (broadcast) */
wtc_result_t dcp_discovery_identify_all(dcp_discovery_t *discovery);

/* Send identify request for specific station name */
wtc_result_t dcp_discovery_identify_name(dcp_discovery_t *discovery,
                                          const char *station_name);

/* Set device IP address */
wtc_result_t dcp_set_ip_address(dcp_discovery_t *discovery,
                                 const uint8_t *mac_address,
                                 uint32_t ip_address,
                                 uint32_t subnet_mask,
                                 uint32_t gateway,
                                 bool permanent);

/* Set device station name */
wtc_result_t dcp_set_station_name(dcp_discovery_t *discovery,
                                   const uint8_t *mac_address,
                                   const char *station_name,
                                   bool permanent);

/* Blink device LED (signal) */
wtc_result_t dcp_signal_device(dcp_discovery_t *discovery,
                                const uint8_t *mac_address);

/* Reset device to factory defaults */
wtc_result_t dcp_reset_to_factory(dcp_discovery_t *discovery,
                                   const uint8_t *mac_address);

/* Process received DCP frame */
wtc_result_t dcp_process_frame(dcp_discovery_t *discovery,
                                const uint8_t *frame,
                                size_t len);

/* Get list of discovered devices */
wtc_result_t dcp_get_devices(dcp_discovery_t *discovery,
                              dcp_device_info_t *devices,
                              int *count,
                              int max_count);

/* Clear discovered devices cache */
void dcp_clear_cache(dcp_discovery_t *discovery);

#ifdef __cplusplus
}
#endif

#endif /* WTC_DCP_DISCOVERY_H */
