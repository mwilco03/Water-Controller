/*
 * Water Treatment Controller - DCP Discovery Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "dcp_discovery.h"
#include "profinet_frame.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <linux/if_packet.h>
#include <linux/if_ether.h>
#include <arpa/inet.h>

/* DCP multicast address */
static const uint8_t DCP_MULTICAST_ADDR[6] = {0x01, 0x0E, 0xCF, 0x00, 0x00, 0x00};

/* Maximum discovered devices */
#define MAX_DISCOVERED_DEVICES 256

/* Default discovery timeout (PN-H3 fix) */
#define DCP_DEFAULT_TIMEOUT_MS 1280

/* DCP discovery context */
struct dcp_discovery {
    char interface_name[32];
    int socket_fd;
    int if_index;
    uint8_t mac_address[6];

    /* Discovery state */
    dcp_discovery_callback_t callback;
    void *callback_ctx;
    volatile bool running;
    pthread_mutex_t lock;

    /* Device cache */
    dcp_device_info_t devices[MAX_DISCOVERED_DEVICES];
    int device_count;

    /* Transaction ID */
    uint32_t xid_counter;

    /* Configurable discovery timeout in milliseconds (PN-H3 fix) */
    uint32_t discovery_timeout_ms;
};

/* Get interface info */
static wtc_result_t get_interface_info(dcp_discovery_t *dcp) {
    struct ifreq ifr;

    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, dcp->interface_name, IFNAMSIZ - 1);

    /* Get interface index */
    if (ioctl(dcp->socket_fd, SIOCGIFINDEX, &ifr) < 0) {
        LOG_ERROR("Failed to get interface index");
        return WTC_ERROR_IO;
    }
    dcp->if_index = ifr.ifr_ifindex;

    /* Get MAC address */
    if (ioctl(dcp->socket_fd, SIOCGIFHWADDR, &ifr) < 0) {
        LOG_ERROR("Failed to get MAC address");
        return WTC_ERROR_IO;
    }
    memcpy(dcp->mac_address, ifr.ifr_hwaddr.sa_data, 6);

    return WTC_OK;
}

/* Send DCP frame */
static wtc_result_t send_dcp_frame(dcp_discovery_t *dcp,
                                    const uint8_t *frame,
                                    size_t len) {
    struct sockaddr_ll sll;
    memset(&sll, 0, sizeof(sll));
    sll.sll_family = AF_PACKET;
    sll.sll_protocol = htons(PROFINET_ETHERTYPE);
    sll.sll_ifindex = dcp->if_index;
    sll.sll_halen = ETH_ADDR_LEN;
    memcpy(sll.sll_addr, frame, ETH_ADDR_LEN); /* Destination MAC */

    ssize_t sent = sendto(dcp->socket_fd, frame, len, 0,
                          (struct sockaddr *)&sll, sizeof(sll));
    if (sent < 0) {
        LOG_ERROR("Failed to send DCP frame");
        return WTC_ERROR_IO;
    }

    return WTC_OK;
}

/* Find device in cache */
static dcp_device_info_t *find_device(dcp_discovery_t *dcp,
                                       const uint8_t *mac_address) {
    for (int i = 0; i < dcp->device_count; i++) {
        if (memcmp(dcp->devices[i].mac_address, mac_address, 6) == 0) {
            return &dcp->devices[i];
        }
    }
    return NULL;
}

/* Add or update device in cache */
static dcp_device_info_t *add_or_update_device(dcp_discovery_t *dcp,
                                                const uint8_t *mac_address) {
    dcp_device_info_t *device = find_device(dcp, mac_address);
    if (device) {
        return device;
    }

    if (dcp->device_count >= MAX_DISCOVERED_DEVICES) {
        LOG_WARN("Device cache full, cannot add new device");
        return NULL;
    }

    device = &dcp->devices[dcp->device_count++];
    memset(device, 0, sizeof(dcp_device_info_t));
    memcpy(device->mac_address, mac_address, 6);
    device->discovered_time_ms = time_get_ms();

    return device;
}

/* Parse DCP response blocks */
static void parse_dcp_blocks(dcp_discovery_t *dcp,
                              dcp_device_info_t *device,
                              frame_parser_t *parser,
                              uint16_t data_length) {
    (void)dcp;  /* Device info is passed directly */
    size_t end_pos = parser->position + data_length;

    while (parser->position < end_pos && frame_parser_remaining(parser) >= 4) {
        dcp_block_header_t block;
        const uint8_t *block_data;

        if (frame_parse_dcp_block(parser, &block, &block_data) != WTC_OK) {
            break;
        }

        switch (block.option) {
        case DCP_OPTION_IP:
            if (block.suboption == DCP_SUBOPTION_IP_PARAMETER && block.length >= 12) {
                /* Skip block info (2 bytes) */
                device->ip_address = ntohl(*(uint32_t *)(block_data + 2));
                device->subnet_mask = ntohl(*(uint32_t *)(block_data + 6));
                device->gateway = ntohl(*(uint32_t *)(block_data + 10));
                device->ip_set = true;
            } else if (block.suboption == DCP_SUBOPTION_IP_MAC && block.length >= 6) {
                memcpy(device->mac_address, block_data, 6);
            }
            break;

        case DCP_OPTION_DEVICE:
            if (block.suboption == DCP_SUBOPTION_DEVICE_VENDOR && block.length > 2) {
                size_t name_len = block.length - 2;
                if (name_len >= sizeof(device->vendor_name)) {
                    name_len = sizeof(device->vendor_name) - 1;
                }
                memcpy(device->vendor_name, block_data + 2, name_len);
                device->vendor_name[name_len] = '\0';
            } else if (block.suboption == DCP_SUBOPTION_DEVICE_NAME && block.length > 2) {
                size_t name_len = block.length - 2;
                if (name_len >= sizeof(device->station_name)) {
                    name_len = sizeof(device->station_name) - 1;
                }
                memcpy(device->station_name, block_data + 2, name_len);
                device->station_name[name_len] = '\0';
                device->name_set = true;
            } else if (block.suboption == DCP_SUBOPTION_DEVICE_ID && block.length >= 6) {
                device->vendor_id = ntohs(*(uint16_t *)(block_data + 2));
                device->device_id = ntohs(*(uint16_t *)(block_data + 4));
            } else if (block.suboption == DCP_SUBOPTION_DEVICE_ROLE && block.length >= 4) {
                device->device_role = ntohs(*(uint16_t *)(block_data + 2));
            }
            break;

        default:
            break;
        }

        /* Align to 16-bit boundary */
        if (block.length & 1) {
            frame_skip_bytes(parser, 1);
        }
    }
}

/* Public functions */

wtc_result_t dcp_discovery_init(dcp_discovery_t **discovery,
                                 const char *interface_name) {
    if (!discovery || !interface_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    dcp_discovery_t *dcp = calloc(1, sizeof(dcp_discovery_t));
    if (!dcp) {
        return WTC_ERROR_NO_MEMORY;
    }

    strncpy(dcp->interface_name, interface_name, sizeof(dcp->interface_name) - 1);
    pthread_mutex_init(&dcp->lock, NULL);
    dcp->discovery_timeout_ms = DCP_DEFAULT_TIMEOUT_MS; /* PN-H3 fix */

    /* Create raw socket */
    dcp->socket_fd = socket(AF_PACKET, SOCK_RAW, htons(PROFINET_ETHERTYPE));
    if (dcp->socket_fd < 0) {
        LOG_ERROR("Failed to create DCP socket");
        free(dcp);
        return WTC_ERROR_IO;
    }

    /* Get interface info */
    wtc_result_t res = get_interface_info(dcp);
    if (res != WTC_OK) {
        close(dcp->socket_fd);
        free(dcp);
        return res;
    }

    /* Bind to interface */
    struct sockaddr_ll sll;
    memset(&sll, 0, sizeof(sll));
    sll.sll_family = AF_PACKET;
    sll.sll_protocol = htons(PROFINET_ETHERTYPE);
    sll.sll_ifindex = dcp->if_index;

    if (bind(dcp->socket_fd, (struct sockaddr *)&sll, sizeof(sll)) < 0) {
        LOG_ERROR("Failed to bind DCP socket");
        close(dcp->socket_fd);
        free(dcp);
        return WTC_ERROR_IO;
    }

    *discovery = dcp;
    LOG_INFO("DCP discovery initialized on %s", interface_name);
    return WTC_OK;
}

void dcp_discovery_cleanup(dcp_discovery_t *discovery) {
    if (!discovery) return;

    dcp_discovery_stop(discovery);

    if (discovery->socket_fd >= 0) {
        close(discovery->socket_fd);
    }

    pthread_mutex_destroy(&discovery->lock);
    free(discovery);

    LOG_INFO("DCP discovery cleaned up");
}

wtc_result_t dcp_discovery_start(dcp_discovery_t *discovery,
                                  dcp_discovery_callback_t callback,
                                  void *ctx) {
    if (!discovery) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&discovery->lock);
    discovery->callback = callback;
    discovery->callback_ctx = ctx;
    discovery->running = true;
    pthread_mutex_unlock(&discovery->lock);

    LOG_INFO("DCP discovery started");
    return WTC_OK;
}

wtc_result_t dcp_discovery_stop(dcp_discovery_t *discovery) {
    if (!discovery) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&discovery->lock);
    discovery->running = false;
    discovery->callback = NULL;
    discovery->callback_ctx = NULL;
    pthread_mutex_unlock(&discovery->lock);

    LOG_INFO("DCP discovery stopped");
    return WTC_OK;
}

wtc_result_t dcp_discovery_identify_all(dcp_discovery_t *discovery) {
    if (!discovery) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint8_t frame[128];
    frame_builder_t builder;
    frame_builder_init(&builder, frame, sizeof(frame), discovery->mac_address);

    /* Build Ethernet header */
    frame_build_ethernet(&builder, DCP_MULTICAST_ADDR, PROFINET_ETHERTYPE);

    /* Build DCP identify request */
    uint32_t xid = ++discovery->xid_counter;
    frame_build_dcp_identify(&builder, xid, NULL);

    /* Pad to minimum frame size */
    frame_append_padding(&builder, ETH_MIN_FRAME_LEN);

    pthread_mutex_lock(&discovery->lock);
    wtc_result_t res = send_dcp_frame(discovery, frame, frame_builder_length(&builder));
    pthread_mutex_unlock(&discovery->lock);

    if (res == WTC_OK) {
        LOG_DEBUG("Sent DCP identify all request (xid=0x%08X)", xid);
    }

    return res;
}

wtc_result_t dcp_discovery_identify_name(dcp_discovery_t *discovery,
                                          const char *station_name) {
    if (!discovery || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint8_t frame[256];
    frame_builder_t builder;
    frame_builder_init(&builder, frame, sizeof(frame), discovery->mac_address);

    /* Build Ethernet header */
    frame_build_ethernet(&builder, DCP_MULTICAST_ADDR, PROFINET_ETHERTYPE);

    /* Build DCP identify request with station name filter */
    uint32_t xid = ++discovery->xid_counter;
    frame_build_dcp_identify(&builder, xid, station_name);

    /* Pad to minimum frame size */
    frame_append_padding(&builder, ETH_MIN_FRAME_LEN);

    pthread_mutex_lock(&discovery->lock);
    wtc_result_t res = send_dcp_frame(discovery, frame, frame_builder_length(&builder));
    pthread_mutex_unlock(&discovery->lock);

    if (res == WTC_OK) {
        LOG_DEBUG("Sent DCP identify request for '%s' (xid=0x%08X)", station_name, xid);
    }

    return res;
}

wtc_result_t dcp_set_ip_address(dcp_discovery_t *discovery,
                                 const uint8_t *mac_address,
                                 uint32_t ip_address,
                                 uint32_t subnet_mask,
                                 uint32_t gateway,
                                 bool permanent) {
    if (!discovery || !mac_address) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint8_t frame[128];
    frame_builder_t builder;
    frame_builder_init(&builder, frame, sizeof(frame), discovery->mac_address);

    /* Build Ethernet header */
    frame_build_ethernet(&builder, mac_address, PROFINET_ETHERTYPE);

    /* Build IP parameter block */
    uint8_t ip_data[14];
    uint16_t block_info = permanent ? 0x0001 : 0x0000;
    memcpy(ip_data, &block_info, 2);

    uint32_t net_ip = htonl(ip_address);
    uint32_t net_mask = htonl(subnet_mask);
    uint32_t net_gw = htonl(gateway);
    memcpy(ip_data + 2, &net_ip, 4);
    memcpy(ip_data + 6, &net_mask, 4);
    memcpy(ip_data + 10, &net_gw, 4);

    uint32_t xid = ++discovery->xid_counter;
    frame_build_dcp_set(&builder, mac_address, xid,
                        DCP_OPTION_IP, DCP_SUBOPTION_IP_PARAMETER,
                        ip_data, sizeof(ip_data));

    /* Pad to minimum frame size */
    frame_append_padding(&builder, ETH_MIN_FRAME_LEN);

    pthread_mutex_lock(&discovery->lock);
    wtc_result_t res = send_dcp_frame(discovery, frame, frame_builder_length(&builder));
    pthread_mutex_unlock(&discovery->lock);

    char ip_str[16];
    ip_to_string(ip_address, ip_str, sizeof(ip_str));
    LOG_INFO("Sent DCP set IP request: %s (permanent=%d)", ip_str, permanent);

    return res;
}

wtc_result_t dcp_set_station_name(dcp_discovery_t *discovery,
                                   const uint8_t *mac_address,
                                   const char *station_name,
                                   bool permanent) {
    if (!discovery || !mac_address || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    size_t name_len = strlen(station_name);
    if (name_len > 60) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint8_t frame[256];
    frame_builder_t builder;
    frame_builder_init(&builder, frame, sizeof(frame), discovery->mac_address);

    /* Build Ethernet header */
    frame_build_ethernet(&builder, mac_address, PROFINET_ETHERTYPE);

    /* Build name block */
    uint8_t name_data[64];
    uint16_t block_info = permanent ? 0x0001 : 0x0000;
    memcpy(name_data, &block_info, 2);
    memcpy(name_data + 2, station_name, name_len);

    uint32_t xid = ++discovery->xid_counter;
    frame_build_dcp_set(&builder, mac_address, xid,
                        DCP_OPTION_DEVICE, DCP_SUBOPTION_DEVICE_NAME,
                        name_data, 2 + name_len);

    /* Pad to minimum frame size */
    frame_append_padding(&builder, ETH_MIN_FRAME_LEN);

    pthread_mutex_lock(&discovery->lock);
    wtc_result_t res = send_dcp_frame(discovery, frame, frame_builder_length(&builder));
    pthread_mutex_unlock(&discovery->lock);

    LOG_INFO("Sent DCP set station name request: '%s' (permanent=%d)",
             station_name, permanent);

    return res;
}

wtc_result_t dcp_signal_device(dcp_discovery_t *discovery,
                                const uint8_t *mac_address) {
    if (!discovery || !mac_address) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint8_t frame[128];
    frame_builder_t builder;
    frame_builder_init(&builder, frame, sizeof(frame), discovery->mac_address);

    /* Build Ethernet header */
    frame_build_ethernet(&builder, mac_address, PROFINET_ETHERTYPE);

    /* Build signal block */
    uint8_t signal_data[4];
    uint16_t block_info = 0x0000;
    uint16_t signal_value = htons(0x0100); /* Blink LED */
    memcpy(signal_data, &block_info, 2);
    memcpy(signal_data + 2, &signal_value, 2);

    uint32_t xid = ++discovery->xid_counter;
    frame_build_dcp_set(&builder, mac_address, xid,
                        DCP_OPTION_CONTROL, DCP_SUBOPTION_CONTROL_SIGNAL,
                        signal_data, sizeof(signal_data));

    /* Pad to minimum frame size */
    frame_append_padding(&builder, ETH_MIN_FRAME_LEN);

    pthread_mutex_lock(&discovery->lock);
    wtc_result_t res = send_dcp_frame(discovery, frame, frame_builder_length(&builder));
    pthread_mutex_unlock(&discovery->lock);

    char mac_str[18];
    mac_to_string(mac_address, mac_str, sizeof(mac_str));
    LOG_INFO("Sent DCP signal request to %s", mac_str);

    return res;
}

wtc_result_t dcp_reset_to_factory(dcp_discovery_t *discovery,
                                   const uint8_t *mac_address) {
    if (!discovery || !mac_address) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint8_t frame[128];
    frame_builder_t builder;
    frame_builder_init(&builder, frame, sizeof(frame), discovery->mac_address);

    /* Build Ethernet header */
    frame_build_ethernet(&builder, mac_address, PROFINET_ETHERTYPE);

    /* Build reset block */
    uint8_t reset_data[4];
    uint16_t block_info = 0x0000;
    uint16_t reset_mode = htons(0x0002); /* Reset to factory */
    memcpy(reset_data, &block_info, 2);
    memcpy(reset_data + 2, &reset_mode, 2);

    uint32_t xid = ++discovery->xid_counter;
    frame_build_dcp_set(&builder, mac_address, xid,
                        DCP_OPTION_CONTROL, DCP_SUBOPTION_CONTROL_RESET_TO_FACTORY,
                        reset_data, sizeof(reset_data));

    /* Pad to minimum frame size */
    frame_append_padding(&builder, ETH_MIN_FRAME_LEN);

    pthread_mutex_lock(&discovery->lock);
    wtc_result_t res = send_dcp_frame(discovery, frame, frame_builder_length(&builder));
    pthread_mutex_unlock(&discovery->lock);

    char mac_str[18];
    mac_to_string(mac_address, mac_str, sizeof(mac_str));
    LOG_WARN("Sent DCP reset to factory request to %s", mac_str);

    return res;
}

wtc_result_t dcp_process_frame(dcp_discovery_t *discovery,
                                const uint8_t *frame,
                                size_t len) {
    if (!discovery || !frame) {
        return WTC_ERROR_INVALID_PARAM;
    }

    frame_parser_t parser;
    frame_parser_init(&parser, frame, len);

    /* Parse Ethernet header */
    uint8_t dst_mac[6], src_mac[6];
    uint16_t ethertype;

    if (frame_parse_ethernet(&parser, dst_mac, src_mac, &ethertype) != WTC_OK) {
        return WTC_ERROR_PROTOCOL;
    }

    if (ethertype != PROFINET_ETHERTYPE) {
        return WTC_ERROR_PROTOCOL;
    }

    /* Check frame ID */
    uint16_t frame_id;
    if (frame_read_u16(&parser, &frame_id) != WTC_OK) {
        return WTC_ERROR_PROTOCOL;
    }

    if (frame_id < PROFINET_FRAME_ID_DCP ||
        frame_id > PROFINET_FRAME_ID_DCP_IDENT) {
        return WTC_ERROR_PROTOCOL;
    }

    /* Parse DCP header */
    profinet_dcp_header_t dcp_header;
    if (frame_parse_dcp_header(&parser, &dcp_header) != WTC_OK) {
        return WTC_ERROR_PROTOCOL;
    }

    /* Only process identify responses */
    if (dcp_header.service_id != DCP_SERVICE_IDENTIFY ||
        dcp_header.service_type != DCP_SERVICE_TYPE_RESPONSE_OK) {
        return WTC_OK;
    }

    pthread_mutex_lock(&discovery->lock);

    /* Add or update device */
    dcp_device_info_t *device = add_or_update_device(discovery, src_mac);
    if (!device) {
        pthread_mutex_unlock(&discovery->lock);
        return WTC_ERROR_FULL;
    }

    /* Parse DCP blocks */
    parse_dcp_blocks(discovery, device, &parser, dcp_header.data_length);

    /* Invoke callback */
    if (discovery->running && discovery->callback) {
        discovery->callback(device, discovery->callback_ctx);
    }

    pthread_mutex_unlock(&discovery->lock);
    return WTC_OK;
}

wtc_result_t dcp_get_devices(dcp_discovery_t *discovery,
                              dcp_device_info_t *devices,
                              int *count,
                              int max_count) {
    if (!discovery || !devices || !count) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&discovery->lock);

    int copy_count = discovery->device_count;
    if (copy_count > max_count) {
        copy_count = max_count;
    }

    memcpy(devices, discovery->devices, copy_count * sizeof(dcp_device_info_t));
    *count = copy_count;

    pthread_mutex_unlock(&discovery->lock);
    return WTC_OK;
}

void dcp_clear_cache(dcp_discovery_t *discovery) {
    if (!discovery) return;

    pthread_mutex_lock(&discovery->lock);
    discovery->device_count = 0;
    memset(discovery->devices, 0, sizeof(discovery->devices));
    pthread_mutex_unlock(&discovery->lock);

    LOG_DEBUG("DCP device cache cleared");
}

/* Set discovery timeout (PN-H3 fix) */
wtc_result_t dcp_set_discovery_timeout(dcp_discovery_t *discovery,
                                        uint32_t timeout_ms) {
    if (!discovery) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Clamp to valid range: 100ms - 10000ms */
    if (timeout_ms < 100) {
        timeout_ms = 100;
    } else if (timeout_ms > 10000) {
        timeout_ms = 10000;
    }

    pthread_mutex_lock(&discovery->lock);
    discovery->discovery_timeout_ms = timeout_ms;
    pthread_mutex_unlock(&discovery->lock);

    LOG_INFO("DCP discovery timeout set to %u ms", timeout_ms);
    return WTC_OK;
}

/* Get current discovery timeout (PN-H3 fix) */
uint32_t dcp_get_discovery_timeout(dcp_discovery_t *discovery) {
    if (!discovery) {
        return DCP_DEFAULT_TIMEOUT_MS;
    }

    pthread_mutex_lock(&discovery->lock);
    uint32_t timeout = discovery->discovery_timeout_ms;
    pthread_mutex_unlock(&discovery->lock);

    return timeout;
}
