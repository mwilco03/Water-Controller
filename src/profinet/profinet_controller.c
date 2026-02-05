/*
 * Water Treatment Controller - PROFINET IO Controller Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "profinet_controller.h"
#include "profinet_identity.h"
#include "profinet_rpc.h"
#include "rpc_strategy.h"
#include "dcp_discovery.h"
#include "profinet_frame.h"
#include "ar_manager.h"
#include "gsdml_modules.h"
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
#include <net/if_arp.h>

/* Receive buffer size */
#define RECV_BUFFER_SIZE 2048

/* Maximum pending auto-connect entries */
#define MAX_PENDING_CONNECTS 64

/* Internal controller structure */
struct profinet_controller {
    profinet_config_t config;

    /* Sockets */
    int raw_socket;
    /* Note: RPC socket is owned by ar_manager->rpc_ctx, not here.
     * This avoids duplicate sockets and clarifies ownership. */

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
    uint32_t ip_address;  /* Auto-detected from interface */

    /* Auto-connect queue: DCP-discovered devices pending RPC Connect.
     * Written by dcp_callback (under ctrl->lock from recv thread),
     * drained by profinet_controller_process (from main loop, no lock). */
    struct {
        char station_name[64];
        char ip_str[16];
    } pending_connects[MAX_PENDING_CONNECTS];
    int pending_connect_count;
};

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

    /* Get IP address - use AF_INET socket for this ioctl */
    int ip_sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (ip_sock >= 0) {
        memset(&ifr, 0, sizeof(ifr));
        strncpy(ifr.ifr_name, ctrl->config.interface_name, IFNAMSIZ - 1);
        if (ioctl(ip_sock, SIOCGIFADDR, &ifr) >= 0) {
            struct sockaddr_in *addr = (struct sockaddr_in *)&ifr.ifr_addr;
            ctrl->ip_address = ntohl(addr->sin_addr.s_addr);
        } else {
            LOG_WARN("Failed to get IP address for %s: %s (will use config or heuristic)",
                     ctrl->config.interface_name, strerror(errno));
            ctrl->ip_address = 0;
        }
        close(ip_sock);
    } else {
        LOG_WARN("Failed to create socket for IP query: %s", strerror(errno));
        ctrl->ip_address = 0;
    }

    char mac_str[18];
    mac_to_string(ctrl->mac_address, mac_str, sizeof(mac_str));

    char ip_str[INET_ADDRSTRLEN] = "none";
    if (ctrl->ip_address != 0) {
        struct in_addr addr;
        addr.s_addr = htonl(ctrl->ip_address);
        inet_ntop(AF_INET, &addr, ip_str, sizeof(ip_str));
    }

    LOG_INFO("Interface %s: index=%d, MAC=%s, IP=%s",
             ctrl->config.interface_name, ctrl->if_index, mac_str, ip_str);

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

/* Map AR state to PROFINET connection state */
static profinet_state_t ar_state_to_profinet_state(ar_state_t ar_state) {
    switch (ar_state) {
    case AR_STATE_RUN:
        return PROFINET_STATE_RUNNING;
    case AR_STATE_INIT:
    case AR_STATE_CONNECT_REQ:
    case AR_STATE_CONNECT_CNF:
    case AR_STATE_PRMSRV:
    case AR_STATE_READY:
        return PROFINET_STATE_CONNECTING;
    case AR_STATE_CLOSE:
        return PROFINET_STATE_OFFLINE;
    case AR_STATE_ABORT:
        return PROFINET_STATE_ERROR;
    default:
        return PROFINET_STATE_OFFLINE;
    }
}

/* AR state change callback - forwards to profinet_config_t callbacks */
static void ar_state_change_callback(const char *station_name,
                                      ar_state_t old_state,
                                      ar_state_t new_state,
                                      void *ctx) {
    profinet_controller_t *ctrl = (profinet_controller_t *)ctx;

    if (ctrl->config.on_device_state_changed) {
        profinet_state_t pn_state = ar_state_to_profinet_state(new_state);
        ctrl->config.on_device_state_changed(station_name, pn_state,
                                              ctrl->config.callback_ctx);
    }

    /* Notify device removed when AR closes */
    if (new_state == AR_STATE_CLOSE && old_state != AR_STATE_CLOSE) {
        if (ctrl->config.on_device_removed) {
            ctrl->config.on_device_removed(station_name,
                                            ctrl->config.callback_ctx);
        }
    }
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
        snprintf(rtu.station_name, sizeof(rtu.station_name), "%s", device->station_name);
        snprintf(rtu.ip_address, sizeof(rtu.ip_address), "%s", ip_str);
        rtu.vendor_id = device->vendor_id;
        rtu.device_id = device->device_id;
        rtu.connection_state = PROFINET_STATE_OFFLINE;

        ctrl->config.on_device_added(&rtu, ctrl->config.callback_ctx);
    }

    /*
     * Queue for auto-connect.  This callback runs under ctrl->lock (from
     * recv_thread_func), so we cannot call profinet_controller_connect()
     * directly (it also takes ctrl->lock → deadlock).  Instead, enqueue
     * the device; profinet_controller_process() drains the queue from the
     * main loop where no lock is held.
     */
    profinet_ar_t *existing = ar_manager_get_ar(ctrl->ar_manager,
                                                 device->station_name);
    if (!existing) {
        bool already_pending = false;
        for (int i = 0; i < ctrl->pending_connect_count; i++) {
            if (strcmp(ctrl->pending_connects[i].station_name,
                       device->station_name) == 0) {
                already_pending = true;
                break;
            }
        }

        if (!already_pending &&
            ctrl->pending_connect_count < MAX_PENDING_CONNECTS) {
            snprintf(ctrl->pending_connects[ctrl->pending_connect_count].station_name,
                     sizeof(ctrl->pending_connects[0].station_name), "%s",
                     device->station_name);
            snprintf(ctrl->pending_connects[ctrl->pending_connect_count].ip_str,
                     sizeof(ctrl->pending_connects[0].ip_str), "%s",
                     ip_str);
            ctrl->pending_connect_count++;
            LOG_INFO("Queued auto-connect for discovered device: %s (%s)",
                     device->station_name, ip_str);
        }
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
                frame_id <= PROFINET_FRAME_ID_DCP_IDENT_RESP) {
                /* DCP frame */
                char src_mac_str[18];
                mac_to_string(src_mac, src_mac_str, sizeof(src_mac_str));
                LOG_DEBUG("DCP frame received: frame_id=0x%04X, src=%s, len=%zd",
                          frame_id, src_mac_str, len);
                dcp_process_frame(ctrl->dcp, buffer, len);
            } else if (frame_id >= PROFINET_FRAME_ID_RTC1_MIN &&
                       frame_id <= PROFINET_FRAME_ID_RTC1_MAX) {
                /* RT Class 1 frame (cyclic data) */
                wtc_result_t rt_res = ar_handle_rt_frame(ctrl->ar_manager,
                                                          buffer, len);

                /* Forward input data to application via on_data_received.
                 * Parse per-slot sensor data from the IOCR buffer and
                 * invoke the callback so the registry/historian gets
                 * updated with live values.
                 *
                 * The callback receives a 0-based sensor index (not the
                 * raw PROFINET slot number) so the registry's sensor[]
                 * array is addressed correctly regardless of slot layout. */
                if (rt_res == WTC_OK && ctrl->config.on_data_received) {
                    profinet_ar_t *ar = ar_manager_get_ar_by_frame_id(
                        ctrl->ar_manager, frame_id);
                    if (ar && ar->state == AR_STATE_RUN) {
                        for (int j = 0; j < ar->iocr_count; j++) {
                            if (ar->iocr[j].type != IOCR_TYPE_INPUT ||
                                ar->iocr[j].frame_id != frame_id ||
                                !ar->iocr[j].data_buffer) {
                                continue;
                            }
                            uint16_t offset = 0;
                            int sensor_idx = 0;
                            for (int s = 0; s < ar->slot_count; s++) {
                                if (ar->slot_info[s].type == SLOT_TYPE_SENSOR) {
                                    if (offset + GSDML_INPUT_DATA_SIZE <=
                                        ar->iocr[j].user_data_length) {
                                        ctrl->config.on_data_received(
                                            ar->device_station_name,
                                            sensor_idx,
                                            ar->iocr[j].data_buffer + offset,
                                            GSDML_INPUT_DATA_SIZE,
                                            ctrl->config.callback_ctx);
                                    }
                                    offset += GSDML_INPUT_DATA_SIZE;
                                    sensor_idx++;
                                }
                            }
                            break;
                        }
                    }
                }
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

    /* Note: RPC socket for PNIO-CM is created lazily by ar_manager when needed
     * (via rpc_context_init). This avoids duplicate sockets and ensures the
     * socket is configured with the correct controller IP at connect time. */

    /* Initialize DCP discovery */
    res = dcp_discovery_init(&ctrl->dcp, ctrl->config.interface_name);
    if (res != WTC_OK) {
        close(ctrl->raw_socket);
        free(ctrl);
        return res;
    }

    /* Have DCP use the controller's raw socket for sending frames.
     * This ensures DCP frames are sent/received on the same socket that
     * the receive thread is polling, avoiding potential delivery issues
     * with multiple raw sockets bound to the same interface.
     */
    dcp_set_socket(ctrl->dcp, ctrl->raw_socket);

    /* Determine controller station name (CMInitiatorStationName in ARBlockReq).
     * If not configured, derive from MAC address like RTUs do (e.g., "controller-1396"). */
    char controller_station_name[64];
    if (config->station_name[0]) {
        strncpy(controller_station_name, config->station_name,
                sizeof(controller_station_name) - 1);
        controller_station_name[sizeof(controller_station_name) - 1] = '\0';
    } else {
        snprintf(controller_station_name, sizeof(controller_station_name),
                 "controller-%02x%02x",
                 ctrl->mac_address[4], ctrl->mac_address[5]);
        LOG_INFO("No station_name configured, using MAC-derived: %s",
                 controller_station_name);
    }

    /* Initialize AR manager with controller identity for CMInitiatorObjectUUID.
     * Pass interface_name so the RPC socket can be bound to the PROFINET NIC
     * via SO_BINDTODEVICE — ensures UDP RPC packets egress the correct
     * interface on multi-homed hosts (Docker with host networking).
     * Pass controller_station_name for CMInitiatorStationName in ARBlockReq. */
    res = ar_manager_init(&ctrl->ar_manager, ctrl->raw_socket, ctrl->mac_address,
                           controller_station_name,
                           config->vendor_id, config->device_id,
                           ctrl->config.interface_name);
    if (res != WTC_OK) {
        dcp_discovery_cleanup(ctrl->dcp);
        close(ctrl->raw_socket);
        free(ctrl);
        return res;
    }

    /* Register AR state change callback for config sync and notifications */
    ar_manager_set_state_callback(ctrl->ar_manager, ar_state_change_callback, ctrl);

    /* Set controller IP for RPC communication
     * Priority: config->ip_address > auto-detected from interface > .1 heuristic (in ar_manager)
     */
    uint32_t controller_ip = config->ip_address;
    if (controller_ip == 0 && ctrl->ip_address != 0) {
        controller_ip = ctrl->ip_address;
        LOG_INFO("Using auto-detected controller IP: %d.%d.%d.%d",
                 (controller_ip >> 24) & 0xFF,
                 (controller_ip >> 16) & 0xFF,
                 (controller_ip >> 8) & 0xFF,
                 controller_ip & 0xFF);
    }
    if (controller_ip != 0) {
        ar_manager_set_controller_ip(ctrl->ar_manager, controller_ip);
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
    /* RPC socket is owned and cleaned up by ar_manager */

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

/*
 * Lookup MAC address via ARP for a given IP address.
 * This is used as a fallback when DCP discovery hasn't populated the cache.
 * Returns WTC_OK if MAC was found, WTC_ERROR_NOT_FOUND otherwise.
 */
static wtc_result_t arp_lookup_mac(const char *interface_name,
                                   uint32_t ip_address,
                                   uint8_t *mac_out) {
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        LOG_ERROR("Failed to create socket for ARP lookup: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    struct arpreq arp_req;
    memset(&arp_req, 0, sizeof(arp_req));

    struct sockaddr_in *sin = (struct sockaddr_in *)&arp_req.arp_pa;
    sin->sin_family = AF_INET;
    sin->sin_addr.s_addr = htonl(ip_address);

    snprintf(arp_req.arp_dev, sizeof(arp_req.arp_dev), "%s", interface_name);

    if (ioctl(sock, SIOCGARP, &arp_req) < 0) {
        LOG_DEBUG("ARP lookup failed for 0x%08X: %s (may need to ping first)",
                  ip_address, strerror(errno));
        close(sock);
        return WTC_ERROR_NOT_FOUND;
    }

    close(sock);

    if (!(arp_req.arp_flags & ATF_COM)) {
        LOG_DEBUG("ARP entry incomplete for 0x%08X", ip_address);
        return WTC_ERROR_NOT_FOUND;
    }

    memcpy(mac_out, arp_req.arp_ha.sa_data, 6);

    char mac_str[18];
    mac_to_string(mac_out, mac_str, sizeof(mac_str));
    LOG_INFO("ARP lookup successful: IP 0x%08X -> MAC %s", ip_address, mac_str);

    return WTC_OK;
}

wtc_result_t profinet_controller_process(profinet_controller_t *controller) {
    if (!controller) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /*
     * Drain pending auto-connect queue.
     *
     * Copy entries under lock, then connect outside lock.
     * profinet_controller_connect() takes ctrl->lock internally,
     * so we must not hold it here.
     */
    struct { char station_name[64]; char ip_str[16]; } local[MAX_PENDING_CONNECTS];
    int count = 0;

    pthread_mutex_lock(&controller->lock);
    count = controller->pending_connect_count;
    if (count > 0) {
        memcpy(local, controller->pending_connects,
               (size_t)count * sizeof(local[0]));
        controller->pending_connect_count = 0;
    }
    pthread_mutex_unlock(&controller->lock);

    for (int i = 0; i < count; i++) {
        LOG_INFO("Auto-connecting to discovered device: %s (%s)",
                 local[i].station_name, local[i].ip_str);
        wtc_result_t res = profinet_controller_connect(
            controller, local[i].station_name, local[i].ip_str, NULL, 0);
        if (res != WTC_OK && res != WTC_ERROR_ALREADY_EXISTS) {
            LOG_ERROR("Auto-connect failed for %s: error %d",
                      local[i].station_name, res);
        }
    }

    /* Manual AR processing when threads are not running */
    if (!controller->running) {
        pthread_mutex_lock(&controller->lock);
        ar_manager_process(controller->ar_manager);
        pthread_mutex_unlock(&controller->lock);
    }

    return WTC_OK;
}

wtc_result_t profinet_controller_connect(profinet_controller_t *controller,
                                          const char *station_name,
                                          const char *device_ip_str,
                                          const slot_config_t *slots,
                                          int slot_count) {
    if (!controller || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /*
     * No hardcoded default slots.  The controller must always discover
     * the RTU's actual module layout via the PROFINET discovery pipeline
     * (DAP-only connect → Record Read 0xF844 → full connect with
     * discovered modules).  Hardcoding slot counts violates CLAUDE.md
     * ("NEVER hardcode RTU data") and causes module mismatch when the
     * RTU has fewer slots than assumed (e.g. just CPU temp on slot 1).
     */
    bool use_discovery = (!slots || slot_count <= 0);
    if (use_discovery) {
        slots = NULL;
        slot_count = 0;
        LOG_INFO("No slot config provided — will discover from device");
    }

    pthread_mutex_lock(&controller->lock);

    /* Check if already connected */
    profinet_ar_t *existing = ar_manager_get_ar(controller->ar_manager, station_name);
    if (existing) {
        pthread_mutex_unlock(&controller->lock);
        LOG_WARN("Already connected to %s", station_name);
        return WTC_ERROR_ALREADY_EXISTS;
    }

    /* Parse IP address if provided (for fallback lookup) */
    uint32_t target_ip = 0;
    if (device_ip_str && device_ip_str[0]) {
        struct in_addr addr;
        if (inet_pton(AF_INET, device_ip_str, &addr) == 1) {
            target_ip = ntohl(addr.s_addr);
            LOG_DEBUG("Target IP for lookup: %s (0x%08X)", device_ip_str, target_ip);
        }
    }

    /*
     * Refresh DCP discovery before connect to ensure we have current device info.
     * RTUs may change vendor_id/device_id dynamically, so stale cache causes issues.
     * This is a quick multicast identify - responses update the cache.
     */
    LOG_DEBUG("Refreshing DCP cache before connect attempt");
    dcp_discovery_identify_all(controller->dcp);

    /* Get device info from DCP cache */
    dcp_device_info_t devices[64];
    int device_count = 64;
    dcp_get_devices(controller->dcp, devices, &device_count, 64);

    LOG_INFO("DCP cache has %d devices, searching for '%s' or IP 0x%08X",
             device_count, station_name, target_ip);

    dcp_device_info_t *device = NULL;

    /* First try: match by station_name */
    for (int i = 0; i < device_count; i++) {
        LOG_DEBUG("DCP device %d: station='%s', ip=0x%08X",
                  i, devices[i].station_name, devices[i].ip_address);
        if (strcmp(devices[i].station_name, station_name) == 0) {
            device = &devices[i];
            LOG_INFO("Found device by station_name: %s", station_name);
            break;
        }
    }

    /* Second try: match by IP address */
    if (!device && target_ip != 0) {
        for (int i = 0; i < device_count; i++) {
            if (devices[i].ip_address == target_ip) {
                device = &devices[i];
                LOG_INFO("Found device by IP (station_name mismatch): DCP has '%s', we requested '%s'",
                         devices[i].station_name, station_name);
                break;
            }
        }
    }

    /*
     * Third try: ARP lookup fallback when DCP cache is empty but we have IP
     * This allows connecting to RTUs discovered via HTTP /config endpoint
     * when DCP multicast isn't working (network issues, firewall, etc.)
     */
    dcp_device_info_t synthetic_device;
    if (!device && target_ip != 0) {
        LOG_WARN("Device not in DCP cache, attempting ARP lookup for IP 0x%08X", target_ip);

        uint8_t mac[6];
        if (arp_lookup_mac(controller->config.interface_name, target_ip, mac) == WTC_OK) {
            memset(&synthetic_device, 0, sizeof(synthetic_device));
            memcpy(synthetic_device.mac_address, mac, 6);
            synthetic_device.ip_address = target_ip;
            strncpy(synthetic_device.station_name, station_name,
                    sizeof(synthetic_device.station_name) - 1);
            /* Use identity constants for Water-Treat RTU (must match GSDML) */
            synthetic_device.vendor_id = PN_VENDOR_ID;
            synthetic_device.device_id = PN_DEVICE_ID;
            synthetic_device.ip_set = true;
            synthetic_device.name_set = true;

            device = &synthetic_device;
            LOG_INFO("Using ARP-discovered device: station='%s', ip=0x%08X",
                     station_name, target_ip);
        }
    }

    if (!device) {
        pthread_mutex_unlock(&controller->lock);
        LOG_ERROR("Device not found: name='%s', ip='%s' (DCP cache has %d devices, ARP failed)",
                  station_name, device_ip_str ? device_ip_str : "none", device_count);
        return WTC_ERROR_NOT_FOUND;
    }

    /* Create AR configuration
     *
     * Note: vendor_id/device_id here are for tracking purposes only.
     * The CMInitiatorObjectUUID (used in Connect request) is built with
     * the CONTROLLER's identity (PN_VENDOR_ID/PN_DEVICE_ID), not the device's.
     * Using consistent values here avoids issues if RTU changes its advertised IDs.
     */
    ar_config_t ar_config;
    memset(&ar_config, 0, sizeof(ar_config));
    strncpy(ar_config.station_name, station_name, sizeof(ar_config.station_name) - 1);
    memcpy(ar_config.device_mac, device->mac_address, 6);
    ar_config.device_ip = device->ip_address;
    ar_config.vendor_id = PN_VENDOR_ID;   /* Use controller's identity */
    ar_config.device_id = PN_DEVICE_ID;   /* Use controller's identity */

    if (slots && slot_count > 0) {
        memcpy(ar_config.slots, slots, slot_count * sizeof(slot_config_t));
        ar_config.slot_count = slot_count;
    } else {
        ar_config.slot_count = 0;
    }

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

    /*
     * Connection strategy:
     * - If explicit slots were provided by the caller, use direct connect
     *   (caller knows the module layout).
     * - Otherwise, use the discovery pipeline which learns the actual
     *   module layout from the device (DAP connect → Record Read →
     *   full connect with discovered modules).
     *
     * The RPC connect calls are blocking (up to 5s timeout each).
     * Set ar->connecting so the cyclic thread skips this AR, then
     * release ctrl->lock so recv/cyclic threads can continue processing
     * other ARs and incoming frames.
     */
    __atomic_store_n(&ar->connecting, true, __ATOMIC_RELEASE);
    pthread_mutex_unlock(&controller->lock);

    if (!use_discovery) {
        /* Caller provided explicit slot configuration */
        res = ar_send_connect_request(controller->ar_manager, ar);
    } else {
        /* No explicit slots — discover from device.
         * Pipeline: GSDML cache → DAP connect → Record Read → Full connect
         * Falls back to HTTP /slots if PROFINET discovery fails. */
        res = ar_connect_with_discovery(controller->ar_manager, ar);
    }

    pthread_mutex_lock(&controller->lock);
    __atomic_store_n(&ar->connecting, false, __ATOMIC_RELEASE);

    if (res != WTC_OK) {
        /* Move AR to ABORT state so ar_manager_process() retries with
         * exponential backoff.  Don't delete — deletion would prevent
         * the retry mechanism from ever firing, since the DCP auto-connect
         * callback only fires once per discovered device. */
        LOG_WARN("Connect failed for %s (error=%d), entering ABORT for retry",
                 station_name, res);
        ar->state = AR_STATE_ABORT;
        ar->last_error = res;
        ar->retry_count++;
        ar->last_activity_ms = time_get_ms();
        pthread_mutex_unlock(&controller->lock);
        return res;
    }
    pthread_mutex_unlock(&controller->lock);

    LOG_INFO("Connection initiated to %s", station_name);

    /* Notify application of the discovered slot layout so the registry
     * can be updated to match PROFINET-discovered modules rather than
     * the generic counts from HTTP self-registration. */
    if (controller->config.on_slots_discovered && ar->slot_count > 0) {
        slot_config_t discovered[WTC_MAX_SLOTS];
        int count = 0;
        for (int i = 0; i < ar->slot_count && count < WTC_MAX_SLOTS; i++) {
            discovered[count].slot = ar->slot_info[i].slot;
            discovered[count].subslot = ar->slot_info[i].subslot;
            discovered[count].type = ar->slot_info[i].type;
            discovered[count].measurement_type = ar->slot_info[i].measurement_type;
            discovered[count].actuator_type = ar->slot_info[i].actuator_type;
            discovered[count].enabled = true;
            memset(discovered[count].name, 0, sizeof(discovered[count].name));
            memset(discovered[count].unit, 0, sizeof(discovered[count].unit));
            count++;
        }
        controller->config.on_slots_discovered(
            station_name, discovered, count,
            controller->config.callback_ctx);
    }

    return WTC_OK;
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

    /* Find input IOCR and compute offset by iterating slot_info.
     * This matches the recv_thread_func logic: accumulate a running offset
     * for each SLOT_TYPE_SENSOR slot rather than using hardcoded arithmetic,
     * so non-contiguous or mixed-type slot layouts are handled correctly. */
    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_INPUT && ar->iocr[i].data_buffer) {
            uint16_t offset = 0;
            for (int s = 0; s < ar->slot_count; s++) {
                if (ar->slot_info[s].type == SLOT_TYPE_SENSOR) {
                    if (ar->slot_info[s].slot == (uint16_t)slot) {
                        if ((uint32_t)(offset + GSDML_INPUT_DATA_SIZE) <= ar->iocr[i].data_length) {
                            size_t copy_len = (*len >= GSDML_INPUT_DATA_SIZE)
                                              ? GSDML_INPUT_DATA_SIZE : *len;
                            memcpy(data, ar->iocr[i].data_buffer + offset, copy_len);
                            *len = copy_len;
                            if (status) *status = IOPS_GOOD;
                            pthread_mutex_unlock(&controller->lock);
                            return WTC_OK;
                        }
                        break;
                    }
                    offset += GSDML_INPUT_DATA_SIZE;
                }
            }
            break;
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

    /* Find output IOCR and compute offset by iterating slot_info.
     * Accumulate a running offset for each SLOT_TYPE_ACTUATOR slot,
     * matching the per-slot structure in the IOCR buffer. */
    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_OUTPUT && ar->iocr[i].data_buffer) {
            uint16_t offset = 0;
            for (int s = 0; s < ar->slot_count; s++) {
                if (ar->slot_info[s].type == SLOT_TYPE_ACTUATOR) {
                    if (ar->slot_info[s].slot == (uint16_t)slot) {
                        size_t write_len = (len <= GSDML_OUTPUT_DATA_SIZE)
                                           ? len : GSDML_OUTPUT_DATA_SIZE;
                        if (offset + write_len <= ar->iocr[i].data_length) {
                            memcpy(ar->iocr[i].data_buffer + offset, data, write_len);
                            pthread_mutex_unlock(&controller->lock);
                            return WTC_OK;
                        }
                        break;
                    }
                    offset += GSDML_OUTPUT_DATA_SIZE;
                }
            }
            break;
        }
    }

    pthread_mutex_unlock(&controller->lock);
    return WTC_ERROR_NOT_FOUND;
}

/* PROFINET RPC constants */
#define PNIO_RPC_PORT           34964
#define RPC_VERSION             4
#define RPC_PACKET_REQUEST      0
#define RPC_PACKET_RESPONSE     2
#define RPC_OPNUM_READ          2  /* IEC 61158-6: OpNum 2 = Read */
#define RPC_OPNUM_WRITE         3  /* IEC 61158-6: OpNum 3 = Write */
#define RPC_TIMEOUT_MS          5000

/* PNIO_DEVICE_INTERFACE_UUID is provided by profinet_rpc.h */

/* Build RPC read/write request */
static wtc_result_t build_rpc_record_request(
    uint8_t *buffer, size_t *buf_len,
    const uint8_t *ar_uuid, uint16_t session_key,
    uint32_t api, uint16_t slot, uint16_t subslot, uint16_t index,
    const void *write_data, size_t write_len, bool is_write)
{
    (void)session_key;  /* Reserved for session validation */
    if (*buf_len < sizeof(profinet_rpc_header_t) + 64) {
        return WTC_ERROR_NO_MEMORY;
    }

    size_t pos = 0;
    profinet_rpc_header_t *rpc = (profinet_rpc_header_t *)buffer;

    /* RPC header */
    memset(rpc, 0, sizeof(profinet_rpc_header_t));
    rpc->version = RPC_VERSION;
    rpc->packet_type = RPC_PACKET_REQUEST;
    rpc->flags1 = 0x22; /* LAST_FRAGMENT (0x02) | IDEMPOTENT (0x20) */
    rpc->drep[0] = 0x10; /* Little-endian */

    /* Activity UUID — generate and swap to LE per DREP */
    rpc_generate_uuid(rpc->activity_uuid);
    uuid_swap_fields(rpc->activity_uuid);

    /* Interface UUID — swap to LE per DREP (p-net parses per DREP) */
    memcpy(rpc->interface_uuid, PNIO_DEVICE_INTERFACE_UUID, 16);
    uuid_swap_fields(rpc->interface_uuid);

    /* Object UUID (AR UUID) — swap to LE per DREP */
    memcpy(rpc->object_uuid, ar_uuid, 16);
    uuid_swap_fields(rpc->object_uuid);

    rpc->interface_version = 1;
    /* opnum in LE (native on LE host) matching DREP=0x10 — no htons */
    rpc->opnum = is_write ? RPC_OPNUM_WRITE : RPC_OPNUM_READ;

    pos = sizeof(profinet_rpc_header_t);

    /* IODReadReq / IODWriteReq block */
    /* Block header */
    uint16_t block_type = htons(is_write ? 0x0008 : 0x0009); /* IODWriteReqHeader / IODReadReqHeader */
    memcpy(buffer + pos, &block_type, 2); pos += 2;

    uint16_t block_length = htons(is_write ? (uint16_t)(24 + write_len) : 24);
    memcpy(buffer + pos, &block_length, 2); pos += 2;

    buffer[pos++] = 1; /* Block version high */
    buffer[pos++] = 0; /* Block version low */

    /* Sequence number */
    uint16_t seq = htons(1);
    memcpy(buffer + pos, &seq, 2); pos += 2;

    /* AR UUID */
    memcpy(buffer + pos, ar_uuid, 16); pos += 16;

    /* API */
    uint32_t api_be = htonl(api);
    memcpy(buffer + pos, &api_be, 4); pos += 4;

    /* Slot number */
    uint16_t slot_be = htons(slot);
    memcpy(buffer + pos, &slot_be, 2); pos += 2;

    /* Subslot number */
    uint16_t subslot_be = htons(subslot);
    memcpy(buffer + pos, &subslot_be, 2); pos += 2;

    /* Padding */
    buffer[pos++] = 0;
    buffer[pos++] = 0;

    /* Index */
    uint16_t index_be = htons(index);
    memcpy(buffer + pos, &index_be, 2); pos += 2;

    /* Record data length */
    uint32_t rec_len = htonl(is_write ? (uint32_t)write_len : 0);
    memcpy(buffer + pos, &rec_len, 4); pos += 4;

    /* For write requests, append the data */
    if (is_write && write_data && write_len > 0) {
        memcpy(buffer + pos, write_data, write_len);
        pos += write_len;
    }

    /* Update fragment length in RPC header */
    rpc->fragment_length = htons((uint16_t)(pos - sizeof(profinet_rpc_header_t)));

    *buf_len = pos;
    return WTC_OK;
}

/* Send RPC request and wait for response */
static wtc_result_t send_rpc_request(
    int socket_fd, uint32_t device_ip,
    const uint8_t *request, size_t req_len,
    uint8_t *response, size_t *resp_len)
{
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(PNIO_RPC_PORT);
    addr.sin_addr.s_addr = htonl(device_ip);  /* Convert host to network byte order */

    /* Send request */
    ssize_t sent = sendto(socket_fd, request, req_len, 0,
                          (struct sockaddr *)&addr, sizeof(addr));
    if (sent < 0) {
        LOG_ERROR("Failed to send RPC request: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    /* Wait for response with timeout */
    struct pollfd pfd;
    pfd.fd = socket_fd;
    pfd.events = POLLIN;

    int poll_result = poll(&pfd, 1, RPC_TIMEOUT_MS);
    if (poll_result < 0) {
        LOG_ERROR("Poll failed: %s", strerror(errno));
        return WTC_ERROR_IO;
    }
    if (poll_result == 0) {
        LOG_WARN("RPC request timeout");
        return WTC_ERROR_TIMEOUT;
    }

    /* Receive response */
    socklen_t addr_len = sizeof(addr);
    ssize_t received = recvfrom(socket_fd, response, *resp_len, 0,
                                 (struct sockaddr *)&addr, &addr_len);
    if (received < 0) {
        LOG_ERROR("Failed to receive RPC response: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    *resp_len = (size_t)received;
    return WTC_OK;
}

wtc_result_t profinet_controller_read_record(profinet_controller_t *controller,
                                              const char *station_name,
                                              uint32_t api,
                                              uint16_t slot,
                                              uint16_t subslot,
                                              uint16_t index,
                                              void *data,
                                              size_t *len) {
    if (!controller || !station_name || !data || !len) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Copy AR fields under lock, then release before blocking RPC.
     * This prevents starving the cyclic thread and causing watchdog
     * timeouts on all connected RTUs during a 5-second RPC wait. */
    uint8_t ar_uuid_copy[16];
    uint16_t session_key_copy;
    uint32_t device_ip_copy;

    pthread_mutex_lock(&controller->lock);

    profinet_ar_t *ar = ar_manager_get_ar(controller->ar_manager, station_name);
    if (!ar) {
        pthread_mutex_unlock(&controller->lock);
        LOG_WARN("Device %s not found for record read", station_name);
        return WTC_ERROR_NOT_FOUND;
    }

    if (ar->state != AR_STATE_RUN) {
        pthread_mutex_unlock(&controller->lock);
        LOG_WARN("Device %s not in RUN state for record read", station_name);
        return WTC_ERROR_NOT_CONNECTED;
    }

    memcpy(ar_uuid_copy, ar->ar_uuid, 16);
    session_key_copy = ar->session_key;
    device_ip_copy = ar->device_ip;

    pthread_mutex_unlock(&controller->lock);

    /* Get RPC socket from ar_manager (it owns the properly configured socket) */
    rpc_context_t *rpc_ctx = ar_manager_get_rpc_context(controller->ar_manager);
    if (!rpc_ctx) {
        LOG_ERROR("RPC context not available for record read");
        return WTC_ERROR_NOT_CONNECTED;
    }

    /* Build RPC request from copied fields (no lock held) */
    uint8_t request[512];
    size_t req_len = sizeof(request);
    wtc_result_t result = build_rpc_record_request(
        request, &req_len,
        ar_uuid_copy, session_key_copy,
        api, slot, subslot, index,
        NULL, 0, false);

    if (result != WTC_OK) {
        return result;
    }

    /* Send request and receive response (blocking, no lock held) */
    uint8_t response[2048];
    size_t resp_len = sizeof(response);

    result = send_rpc_request(rpc_ctx->socket_fd, device_ip_copy,
                               request, req_len, response, &resp_len);

    if (result != WTC_OK) {
        return result;
    }

    /* Parse response - skip RPC header and find record data */
    if (resp_len < sizeof(profinet_rpc_header_t) + 40) {
        LOG_ERROR("RPC response too short");
        return WTC_ERROR_PROTOCOL;
    }

    /* Check for error in response */
    profinet_rpc_header_t *rpc_resp = (profinet_rpc_header_t *)response;
    if (rpc_resp->packet_type != RPC_PACKET_RESPONSE) {
        LOG_ERROR("Invalid RPC response type: %d", rpc_resp->packet_type);
        return WTC_ERROR_PROTOCOL;
    }

    /* Extract record data from IODReadRes block */
    /* Skip: RPC header (80) + block header (4) + sequence (2) + AR UUID (16) */
    /* + API (4) + slot (2) + subslot (2) + padding (2) + index (2) + length (4) */
    size_t data_offset = sizeof(profinet_rpc_header_t) + 38;
    if (data_offset >= resp_len) {
        LOG_WARN("No record data in response");
        *len = 0;
        return WTC_OK;
    }

    /* Get record data length from response */
    uint32_t record_len_be;
    memcpy(&record_len_be, response + sizeof(profinet_rpc_header_t) + 34, 4);
    uint32_t record_len = ntohl(record_len_be);

    if (record_len > resp_len - data_offset) {
        record_len = resp_len - data_offset;
    }

    size_t copy_len = (record_len < *len) ? record_len : *len;
    memcpy(data, response + data_offset, copy_len);
    *len = copy_len;

    LOG_DEBUG("Read record: station=%s, api=%u, slot=%u, subslot=%u, index=0x%04X, len=%zu",
              station_name, api, slot, subslot, index, copy_len);

    return WTC_OK;
}

wtc_result_t profinet_controller_write_record(profinet_controller_t *controller,
                                               const char *station_name,
                                               uint32_t api,
                                               uint16_t slot,
                                               uint16_t subslot,
                                               uint16_t index,
                                               const void *data,
                                               size_t len) {
    if (!controller || !station_name || (!data && len > 0)) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Copy AR fields under lock, then release before blocking RPC.
     * Same pattern as read_record — avoids starving cyclic thread. */
    uint8_t ar_uuid_copy[16];
    uint16_t session_key_copy;
    uint32_t device_ip_copy;

    pthread_mutex_lock(&controller->lock);

    profinet_ar_t *ar = ar_manager_get_ar(controller->ar_manager, station_name);
    if (!ar) {
        pthread_mutex_unlock(&controller->lock);
        LOG_WARN("Device %s not found for record write", station_name);
        return WTC_ERROR_NOT_FOUND;
    }

    if (ar->state != AR_STATE_RUN) {
        pthread_mutex_unlock(&controller->lock);
        LOG_WARN("Device %s not in RUN state for record write", station_name);
        return WTC_ERROR_NOT_CONNECTED;
    }

    memcpy(ar_uuid_copy, ar->ar_uuid, 16);
    session_key_copy = ar->session_key;
    device_ip_copy = ar->device_ip;

    pthread_mutex_unlock(&controller->lock);

    /* Get RPC socket from ar_manager (it owns the properly configured socket) */
    rpc_context_t *rpc_ctx = ar_manager_get_rpc_context(controller->ar_manager);
    if (!rpc_ctx) {
        LOG_ERROR("RPC context not available for record write");
        return WTC_ERROR_NOT_CONNECTED;
    }

    /* Build RPC request from copied fields (no lock held) */
    uint8_t request[2048];
    size_t req_len = sizeof(request);
    wtc_result_t result = build_rpc_record_request(
        request, &req_len,
        ar_uuid_copy, session_key_copy,
        api, slot, subslot, index,
        data, len, true);

    if (result != WTC_OK) {
        return result;
    }

    /* Send request and receive response (blocking, no lock held) */
    uint8_t response[512];
    size_t resp_len = sizeof(response);

    result = send_rpc_request(rpc_ctx->socket_fd, device_ip_copy,
                               request, req_len, response, &resp_len);

    if (result != WTC_OK) {
        return result;
    }

    /* Check response */
    if (resp_len < sizeof(profinet_rpc_header_t)) {
        LOG_ERROR("RPC write response too short");
        return WTC_ERROR_PROTOCOL;
    }

    profinet_rpc_header_t *rpc_resp = (profinet_rpc_header_t *)response;
    if (rpc_resp->packet_type != RPC_PACKET_RESPONSE) {
        LOG_ERROR("Invalid RPC write response type: %d", rpc_resp->packet_type);
        return WTC_ERROR_PROTOCOL;
    }

    LOG_DEBUG("Write record: station=%s, api=%u, slot=%u, subslot=%u, index=0x%04X, len=%zu",
              station_name, api, slot, subslot, index, len);

    return WTC_OK;
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

/* Trigger DCP Identify All broadcast via the controller's DCP instance */
wtc_result_t profinet_controller_discover_all(profinet_controller_t *controller) {
    if (!controller || !controller->dcp) {
        return WTC_ERROR_INVALID_PARAM;
    }
    return dcp_discovery_identify_all(controller->dcp);
}

/* Get discovered devices from the controller's DCP cache */
wtc_result_t profinet_controller_get_discovered_devices(
    profinet_controller_t *controller,
    dcp_device_info_t *devices,
    int *count,
    int max_devices) {
    if (!controller || !controller->dcp || !devices || !count) {
        return WTC_ERROR_INVALID_PARAM;
    }
    return dcp_get_devices(controller->dcp, devices, count, max_devices);
}
