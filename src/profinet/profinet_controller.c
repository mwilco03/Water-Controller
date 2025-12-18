/*
 * Water Treatment Controller - PROFINET IO Controller Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "profinet_controller.h"
#include "dcp_discovery.h"
#include "profinet_frame.h"
#include "ar_manager.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <netinet/in.h>
#include <linux/if_packet.h>
#include <linux/if_ether.h>
#include <arpa/inet.h>
#include <errno.h>
#include <poll.h>

/* Internal controller structure */
struct profinet_controller {
    profinet_config_t config;

    /* Sockets */
    int raw_socket;
    int rpc_socket;

    /* DCP discovery */
    dcp_discovery_t *dcp;

    /* AR manager */
    ar_manager_t *ar_manager;

    /* Thread management */
    pthread_t recv_thread;
    pthread_t cyclic_thread;
    volatile bool running;
    pthread_mutex_t lock;

    /* Statistics */
    cycle_stats_t stats;
    uint64_t last_stats_reset_ms;

    /* Interface info */
    int if_index;
    uint8_t mac_address[6];
};

/* Receive buffer size */
#define RECV_BUFFER_SIZE 2048

/* Get interface info */
static wtc_result_t get_interface_info(profinet_controller_t *ctrl) {
    struct ifreq ifr;

    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, ctrl->config.interface_name, IFNAMSIZ - 1);

    /* Get interface index */
    if (ioctl(ctrl->raw_socket, SIOCGIFINDEX, &ifr) < 0) {
        LOG_ERROR("Failed to get interface index for %s: %s",
                  ctrl->config.interface_name, strerror(errno));
        return WTC_ERROR_IO;
    }
    ctrl->if_index = ifr.ifr_ifindex;

    /* Get MAC address */
    if (ioctl(ctrl->raw_socket, SIOCGIFHWADDR, &ifr) < 0) {
        LOG_ERROR("Failed to get MAC address for %s: %s",
                  ctrl->config.interface_name, strerror(errno));
        return WTC_ERROR_IO;
    }
    memcpy(ctrl->mac_address, ifr.ifr_hwaddr.sa_data, 6);

    char mac_str[18];
    mac_to_string(ctrl->mac_address, mac_str, sizeof(mac_str));
    LOG_INFO("Interface %s: index=%d, MAC=%s",
             ctrl->config.interface_name, ctrl->if_index, mac_str);

    return WTC_OK;
}

/* Create raw socket for PROFINET frames */
static wtc_result_t create_raw_socket(profinet_controller_t *ctrl) {
    ctrl->raw_socket = socket(AF_PACKET, SOCK_RAW, htons(PROFINET_ETHERTYPE));
    if (ctrl->raw_socket < 0) {
        LOG_ERROR("Failed to create raw socket: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    /* Get interface info */
    wtc_result_t res = get_interface_info(ctrl);
    if (res != WTC_OK) {
        close(ctrl->raw_socket);
        ctrl->raw_socket = -1;
        return res;
    }

    /* Bind to interface */
    struct sockaddr_ll sll;
    memset(&sll, 0, sizeof(sll));
    sll.sll_family = AF_PACKET;
    sll.sll_protocol = htons(PROFINET_ETHERTYPE);
    sll.sll_ifindex = ctrl->if_index;

    if (bind(ctrl->raw_socket, (struct sockaddr *)&sll, sizeof(sll)) < 0) {
        LOG_ERROR("Failed to bind raw socket: %s", strerror(errno));
        close(ctrl->raw_socket);
        ctrl->raw_socket = -1;
        return WTC_ERROR_IO;
    }

    /* Set socket priority if specified */
    if (ctrl->config.socket_priority > 0) {
        int prio = ctrl->config.socket_priority;
        if (setsockopt(ctrl->raw_socket, SOL_SOCKET, SO_PRIORITY,
                      &prio, sizeof(prio)) < 0) {
            LOG_WARN("Failed to set socket priority: %s", strerror(errno));
        }
    }

    /* Enable promiscuous mode */
    struct packet_mreq mreq;
    memset(&mreq, 0, sizeof(mreq));
    mreq.mr_ifindex = ctrl->if_index;
    mreq.mr_type = PACKET_MR_PROMISC;
    if (setsockopt(ctrl->raw_socket, SOL_PACKET, PACKET_ADD_MEMBERSHIP,
                  &mreq, sizeof(mreq)) < 0) {
        LOG_WARN("Failed to enable promiscuous mode: %s", strerror(errno));
    }

    LOG_INFO("Raw socket created and bound to %s", ctrl->config.interface_name);
    return WTC_OK;
}

/* DCP discovery callback */
static void dcp_callback(const dcp_device_info_t *device, void *ctx) {
    profinet_controller_t *ctrl = (profinet_controller_t *)ctx;

    char mac_str[18], ip_str[16];
    mac_to_string(device->mac_address, mac_str, sizeof(mac_str));
    ip_to_string(device->ip_address, ip_str, sizeof(ip_str));

    LOG_INFO("Discovered device: station=%s, MAC=%s, IP=%s, vendor=0x%04X, device=0x%04X",
             device->station_name, mac_str, ip_str,
             device->vendor_id, device->device_id);

    /* Notify callback if registered */
    if (ctrl->config.on_device_added) {
        rtu_device_t rtu;
        memset(&rtu, 0, sizeof(rtu));
        strncpy(rtu.station_name, device->station_name, sizeof(rtu.station_name) - 1);
        strncpy(rtu.ip_address, ip_str, sizeof(rtu.ip_address) - 1);
        rtu.vendor_id = device->vendor_id;
        rtu.device_id = device->device_id;
        rtu.connection_state = PROFINET_STATE_OFFLINE;

        ctrl->config.on_device_added(&rtu, ctrl->config.callback_ctx);
    }
}

/* Receive thread function */
static void *recv_thread_func(void *arg) {
    profinet_controller_t *ctrl = (profinet_controller_t *)arg;
    uint8_t buffer[RECV_BUFFER_SIZE];
    struct pollfd pfd;

    pfd.fd = ctrl->raw_socket;
    pfd.events = POLLIN;

    LOG_DEBUG("Receive thread started");

    while (ctrl->running) {
        int ret = poll(&pfd, 1, 100); /* 100ms timeout */
        if (ret < 0) {
            if (errno == EINTR) continue;
            LOG_ERROR("poll() failed: %s", strerror(errno));
            break;
        }

        if (ret == 0) continue; /* Timeout */

        if (pfd.revents & POLLIN) {
            ssize_t len = recv(ctrl->raw_socket, buffer, sizeof(buffer), 0);
            if (len < 0) {
                if (errno == EINTR || errno == EAGAIN) continue;
                LOG_ERROR("recv() failed: %s", strerror(errno));
                continue;
            }

            if (len < (ssize_t)sizeof(profinet_frame_header_t)) {
                continue; /* Too short */
            }

            /* Parse frame header */
            frame_parser_t parser;
            frame_parser_init(&parser, buffer, len);

            uint8_t dst_mac[6], src_mac[6];
            uint16_t ethertype;

            if (frame_parse_ethernet(&parser, dst_mac, src_mac, &ethertype) != WTC_OK) {
                continue;
            }

            if (ethertype != PROFINET_ETHERTYPE) {
                continue; /* Not PROFINET */
            }

            uint16_t frame_id;
            if (frame_read_u16(&parser, &frame_id) != WTC_OK) {
                continue;
            }

            /* Route frame based on frame ID */
            pthread_mutex_lock(&ctrl->lock);

            if (frame_id >= PROFINET_FRAME_ID_DCP &&
                frame_id <= PROFINET_FRAME_ID_DCP_IDENT) {
                /* DCP frame */
                dcp_process_frame(ctrl->dcp, buffer, len);
            } else if (frame_id >= PROFINET_FRAME_ID_RTC1_MIN &&
                       frame_id <= PROFINET_FRAME_ID_RTC1_MAX) {
                /* RT Class 1 frame (cyclic data) */
                ar_handle_rt_frame(ctrl->ar_manager, buffer, len);
            }

            pthread_mutex_unlock(&ctrl->lock);
        }
    }

    LOG_DEBUG("Receive thread stopped");
    return NULL;
}

/* Cyclic thread function */
static void *cyclic_thread_func(void *arg) {
    profinet_controller_t *ctrl = (profinet_controller_t *)arg;
    uint64_t cycle_time_us = ctrl->config.cycle_time_us;
    uint64_t next_cycle_us;
    wtc_timer_t timer;

    timer_init(&timer);
    next_cycle_us = time_get_monotonic_us() + cycle_time_us;

    LOG_DEBUG("Cyclic thread started, cycle time: %lu us", cycle_time_us);

    while (ctrl->running) {
        timer_start(&timer);

        pthread_mutex_lock(&ctrl->lock);

        /* Process AR state machines */
        ar_manager_process(ctrl->ar_manager);

        /* Check AR health (watchdog) */
        ar_manager_check_health(ctrl->ar_manager);

        /* Send output data for all running ARs */
        profinet_ar_t *ars[WTC_MAX_RTUS];
        int ar_count = 0;
        ar_manager_get_all(ctrl->ar_manager, ars, &ar_count, WTC_MAX_RTUS);

        for (int i = 0; i < ar_count; i++) {
            if (ars[i]->state == AR_STATE_RUN) {
                ar_send_output_data(ctrl->ar_manager, ars[i]);
            }
        }

        pthread_mutex_unlock(&ctrl->lock);

        timer_stop(&timer);

        /* Update statistics */
        uint64_t elapsed_us = timer_elapsed_us(&timer);
        ctrl->stats.cycle_count++;

        if (elapsed_us < ctrl->stats.cycle_time_us_min ||
            ctrl->stats.cycle_time_us_min == 0) {
            ctrl->stats.cycle_time_us_min = elapsed_us;
        }
        if (elapsed_us > ctrl->stats.cycle_time_us_max) {
            ctrl->stats.cycle_time_us_max = elapsed_us;
        }

        /* Running average */
        ctrl->stats.cycle_time_us_avg =
            (ctrl->stats.cycle_time_us_avg * (ctrl->stats.cycle_count - 1) +
             elapsed_us) / ctrl->stats.cycle_count;

        if (elapsed_us > cycle_time_us) {
            ctrl->stats.overruns++;
        }

        timer_reset(&timer);

        /* Wait for next cycle */
        uint64_t now_us = time_get_monotonic_us();
        if (now_us < next_cycle_us) {
            time_sleep_us(next_cycle_us - now_us);
        }
        next_cycle_us += cycle_time_us;

        /* Prevent drift accumulation */
        if (next_cycle_us < now_us) {
            next_cycle_us = now_us + cycle_time_us;
        }
    }

    LOG_DEBUG("Cyclic thread stopped");
    return NULL;
}

/* Public functions */

wtc_result_t profinet_controller_init(profinet_controller_t **controller,
                                       const profinet_config_t *config) {
    if (!controller || !config) {
        return WTC_ERROR_INVALID_PARAM;
    }

    profinet_controller_t *ctrl = calloc(1, sizeof(profinet_controller_t));
    if (!ctrl) {
        return WTC_ERROR_NO_MEMORY;
    }

    memcpy(&ctrl->config, config, sizeof(profinet_config_t));
    ctrl->raw_socket = -1;
    ctrl->rpc_socket = -1;
    ctrl->running = false;

    pthread_mutex_init(&ctrl->lock, NULL);

    /* Set defaults */
    if (ctrl->config.cycle_time_us == 0) {
        ctrl->config.cycle_time_us = 1000000; /* 1ms default */
    }
    if (ctrl->config.send_clock_factor == 0) {
        ctrl->config.send_clock_factor = 32; /* 1ms */
    }

    /* Create raw socket */
    wtc_result_t res = create_raw_socket(ctrl);
    if (res != WTC_OK) {
        free(ctrl);
        return res;
    }

    /* Initialize DCP discovery */
    res = dcp_discovery_init(&ctrl->dcp, ctrl->config.interface_name);
    if (res != WTC_OK) {
        close(ctrl->raw_socket);
        free(ctrl);
        return res;
    }

    /* Initialize AR manager */
    res = ar_manager_init(&ctrl->ar_manager, ctrl->raw_socket, ctrl->mac_address);
    if (res != WTC_OK) {
        dcp_discovery_cleanup(ctrl->dcp);
        close(ctrl->raw_socket);
        free(ctrl);
        return res;
    }

    *controller = ctrl;
    LOG_INFO("PROFINET controller initialized");
    return WTC_OK;
}

void profinet_controller_cleanup(profinet_controller_t *controller) {
    if (!controller) return;

    profinet_controller_stop(controller);

    ar_manager_cleanup(controller->ar_manager);
    dcp_discovery_cleanup(controller->dcp);

    if (controller->raw_socket >= 0) {
        close(controller->raw_socket);
    }
    if (controller->rpc_socket >= 0) {
        close(controller->rpc_socket);
    }

    pthread_mutex_destroy(&controller->lock);
    free(controller);

    LOG_INFO("PROFINET controller cleaned up");
}

wtc_result_t profinet_controller_start(profinet_controller_t *controller) {
    if (!controller) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (controller->running) {
        return WTC_OK;
    }

    controller->running = true;

    /* Start DCP discovery */
    dcp_discovery_start(controller->dcp, dcp_callback, controller);

    /* Start receive thread */
    if (pthread_create(&controller->recv_thread, NULL,
                       recv_thread_func, controller) != 0) {
        LOG_ERROR("Failed to create receive thread");
        controller->running = false;
        return WTC_ERROR;
    }

    /* Start cyclic thread */
    if (pthread_create(&controller->cyclic_thread, NULL,
                       cyclic_thread_func, controller) != 0) {
        LOG_ERROR("Failed to create cyclic thread");
        controller->running = false;
        pthread_join(controller->recv_thread, NULL);
        return WTC_ERROR;
    }

    /* Send initial DCP identify */
    dcp_discovery_identify_all(controller->dcp);

    LOG_INFO("PROFINET controller started");
    return WTC_OK;
}

wtc_result_t profinet_controller_stop(profinet_controller_t *controller) {
    if (!controller || !controller->running) {
        return WTC_OK;
    }

    controller->running = false;

    /* Stop threads */
    pthread_join(controller->recv_thread, NULL);
    pthread_join(controller->cyclic_thread, NULL);

    /* Stop DCP discovery */
    dcp_discovery_stop(controller->dcp);

    LOG_INFO("PROFINET controller stopped");
    return WTC_OK;
}

wtc_result_t profinet_controller_process(profinet_controller_t *controller) {
    if (!controller) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Manual processing mode - not needed if threads are running */
    if (controller->running) {
        return WTC_OK;
    }

    pthread_mutex_lock(&controller->lock);
    ar_manager_process(controller->ar_manager);
    pthread_mutex_unlock(&controller->lock);

    return WTC_OK;
}

wtc_result_t profinet_controller_connect(profinet_controller_t *controller,
                                          const char *station_name,
                                          const slot_config_t *slots,
                                          int slot_count) {
    if (!controller || !station_name || !slots || slot_count <= 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&controller->lock);

    /* Check if already connected */
    profinet_ar_t *existing = ar_manager_get_ar(controller->ar_manager, station_name);
    if (existing) {
        pthread_mutex_unlock(&controller->lock);
        LOG_WARN("Already connected to %s", station_name);
        return WTC_ERROR_ALREADY_EXISTS;
    }

    /* Get device info from DCP cache */
    dcp_device_info_t devices[64];
    int device_count = 64;
    dcp_get_devices(controller->dcp, devices, &device_count, 64);

    dcp_device_info_t *device = NULL;
    for (int i = 0; i < device_count; i++) {
        if (strcmp(devices[i].station_name, station_name) == 0) {
            device = &devices[i];
            break;
        }
    }

    if (!device) {
        pthread_mutex_unlock(&controller->lock);
        LOG_ERROR("Device not found: %s", station_name);
        return WTC_ERROR_NOT_FOUND;
    }

    /* Create AR configuration */
    ar_config_t ar_config;
    memset(&ar_config, 0, sizeof(ar_config));
    strncpy(ar_config.station_name, station_name, sizeof(ar_config.station_name) - 1);
    memcpy(ar_config.device_mac, device->mac_address, 6);
    ar_config.device_ip = device->ip_address;
    ar_config.vendor_id = device->vendor_id;
    ar_config.device_id = device->device_id;

    memcpy(ar_config.slots, slots, slot_count * sizeof(slot_config_t));
    ar_config.slot_count = slot_count;

    ar_config.cycle_time_us = controller->config.cycle_time_us;
    ar_config.reduction_ratio = controller->config.reduction_ratio;
    ar_config.watchdog_ms = 3000; /* 3 second watchdog */

    /* Create AR */
    profinet_ar_t *ar;
    wtc_result_t res = ar_manager_create_ar(controller->ar_manager, &ar_config, &ar);
    if (res != WTC_OK) {
        pthread_mutex_unlock(&controller->lock);
        return res;
    }

    /* Initiate connection */
    res = ar_send_connect_request(controller->ar_manager, ar);

    pthread_mutex_unlock(&controller->lock);

    if (res == WTC_OK) {
        LOG_INFO("Connection initiated to %s", station_name);
    }

    return res;
}

wtc_result_t profinet_controller_disconnect(profinet_controller_t *controller,
                                             const char *station_name) {
    if (!controller || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&controller->lock);

    profinet_ar_t *ar = ar_manager_get_ar(controller->ar_manager, station_name);
    if (!ar) {
        pthread_mutex_unlock(&controller->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    /* Send release request */
    ar_send_release_request(controller->ar_manager, ar);

    /* Delete AR */
    wtc_result_t res = ar_manager_delete_ar(controller->ar_manager, station_name);

    pthread_mutex_unlock(&controller->lock);

    LOG_INFO("Disconnected from %s", station_name);
    return res;
}

profinet_ar_t *profinet_controller_get_ar(profinet_controller_t *controller,
                                          const char *station_name) {
    if (!controller || !station_name) return NULL;

    pthread_mutex_lock(&controller->lock);
    profinet_ar_t *ar = ar_manager_get_ar(controller->ar_manager, station_name);
    pthread_mutex_unlock(&controller->lock);

    return ar;
}

wtc_result_t profinet_controller_read_input(profinet_controller_t *controller,
                                             const char *station_name,
                                             int slot,
                                             void *data,
                                             size_t *len,
                                             iops_t *status) {
    if (!controller || !station_name || !data || !len) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&controller->lock);

    profinet_ar_t *ar = ar_manager_get_ar(controller->ar_manager, station_name);
    if (!ar) {
        pthread_mutex_unlock(&controller->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    if (ar->state != AR_STATE_RUN) {
        pthread_mutex_unlock(&controller->lock);
        if (status) *status = IOPS_BAD;
        return WTC_ERROR_NOT_INITIALIZED;
    }

    /* Find input IOCR for this slot */
    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_INPUT) {
            /* Calculate offset for slot */
            size_t offset = (slot - 1) * 4; /* 4 bytes per sensor slot */
            if (offset + 4 <= ar->iocr[i].data_length && ar->iocr[i].data_buffer) {
                memcpy(data, ar->iocr[i].data_buffer + offset, 4);
                if (*len > 4) *len = 4;
                if (status) *status = IOPS_GOOD;
                pthread_mutex_unlock(&controller->lock);
                return WTC_OK;
            }
        }
    }

    pthread_mutex_unlock(&controller->lock);
    if (status) *status = IOPS_BAD;
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t profinet_controller_write_output(profinet_controller_t *controller,
                                               const char *station_name,
                                               int slot,
                                               const void *data,
                                               size_t len) {
    if (!controller || !station_name || !data) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&controller->lock);

    profinet_ar_t *ar = ar_manager_get_ar(controller->ar_manager, station_name);
    if (!ar) {
        pthread_mutex_unlock(&controller->lock);
        return WTC_ERROR_NOT_FOUND;
    }

    if (ar->state != AR_STATE_RUN) {
        pthread_mutex_unlock(&controller->lock);
        return WTC_ERROR_NOT_INITIALIZED;
    }

    /* Find output IOCR for this slot
     * slot is a 0-based index into the output data buffer
     * RTU dictates slot configuration; controller adapts dynamically
     */
    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_OUTPUT) {
            /* Calculate offset - no hardcoded slot assumptions */
            size_t offset = slot * 4; /* 4 bytes per actuator slot */
            if (offset + len <= ar->iocr[i].data_length && ar->iocr[i].data_buffer) {
                memcpy(ar->iocr[i].data_buffer + offset, data, len);
                pthread_mutex_unlock(&controller->lock);
                return WTC_OK;
            }
        }
    }

    pthread_mutex_unlock(&controller->lock);
    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t profinet_controller_read_record(profinet_controller_t *controller,
                                              const char *station_name,
                                              uint32_t api,
                                              uint16_t slot,
                                              uint16_t subslot,
                                              uint16_t index,
                                              void *data,
                                              size_t *len) {
    /* Acyclic read via RPC - implementation pending */
    (void)controller;
    (void)station_name;
    (void)api;
    (void)slot;
    (void)subslot;
    (void)index;
    (void)data;
    (void)len;
    return WTC_ERROR_NOT_INITIALIZED;
}

wtc_result_t profinet_controller_write_record(profinet_controller_t *controller,
                                               const char *station_name,
                                               uint32_t api,
                                               uint16_t slot,
                                               uint16_t subslot,
                                               uint16_t index,
                                               const void *data,
                                               size_t len) {
    /* Acyclic write via RPC - implementation pending */
    (void)controller;
    (void)station_name;
    (void)api;
    (void)slot;
    (void)subslot;
    (void)index;
    (void)data;
    (void)len;
    return WTC_ERROR_NOT_INITIALIZED;
}

wtc_result_t profinet_controller_get_stats(profinet_controller_t *controller,
                                            cycle_stats_t *stats) {
    if (!controller || !stats) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&controller->lock);
    memcpy(stats, &controller->stats, sizeof(cycle_stats_t));
    pthread_mutex_unlock(&controller->lock);

    return WTC_OK;
}
