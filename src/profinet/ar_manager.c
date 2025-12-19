/*
 * Water Treatment Controller - AR Manager Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "ar_manager.h"
#include "cyclic_exchange.h"
#include "profinet_frame.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <sys/socket.h>
#include <linux/if_packet.h>
#include <arpa/inet.h>

/* Maximum ARs */
#define MAX_ARS 64

/* AR manager structure */
struct ar_manager {
    int socket_fd;
    uint8_t controller_mac[6];
    int if_index;

    profinet_ar_t *ars[MAX_ARS];
    int ar_count;

    uint16_t session_key_counter;
    pthread_mutex_t lock;
};

/* Generate UUID */
static void generate_uuid(uint32_t uuid[4]) {
    /* Simple UUID generation - in production use proper UUID library */
    for (int i = 0; i < 4; i++) {
        uuid[i] = (uint32_t)rand() ^ ((uint32_t)time_get_ms() << i);
    }
}

/* Send raw frame */
static wtc_result_t send_frame(ar_manager_t *manager,
                                const uint8_t *dst_mac,
                                const uint8_t *frame,
                                size_t len) {
    struct sockaddr_ll sll;
    memset(&sll, 0, sizeof(sll));
    sll.sll_family = AF_PACKET;
    sll.sll_protocol = htons(PROFINET_ETHERTYPE);
    sll.sll_ifindex = manager->if_index;
    sll.sll_halen = ETH_ADDR_LEN;
    memcpy(sll.sll_addr, dst_mac, ETH_ADDR_LEN);

    ssize_t sent = sendto(manager->socket_fd, frame, len, 0,
                          (struct sockaddr *)&sll, sizeof(sll));
    if (sent < 0) {
        LOG_ERROR("Failed to send frame");
        return WTC_ERROR_IO;
    }

    return WTC_OK;
}

/* Build and send cyclic output frame */
static wtc_result_t send_cyclic_frame(ar_manager_t *manager, profinet_ar_t *ar) {
    if (!ar || ar->state != AR_STATE_RUN) {
        return WTC_ERROR_NOT_INITIALIZED;
    }

    /* Find output IOCR */
    int output_idx = -1;
    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].type == IOCR_TYPE_OUTPUT) {
            output_idx = i;
            break;
        }
    }

    if (output_idx < 0) {
        return WTC_ERROR_NOT_FOUND;
    }

    /* Build frame */
    uint8_t frame[1518];
    size_t pos = 0;

    /* Ethernet header */
    memcpy(frame + pos, ar->device_mac, 6);
    pos += 6;
    memcpy(frame + pos, manager->controller_mac, 6);
    pos += 6;
    uint16_t ethertype = htons(PROFINET_ETHERTYPE);
    memcpy(frame + pos, &ethertype, 2);
    pos += 2;

    /* Frame ID */
    uint16_t frame_id = htons(ar->iocr[output_idx].frame_id);
    memcpy(frame + pos, &frame_id, 2);
    pos += 2;

    /* Cyclic data */
    if (ar->iocr[output_idx].data_buffer && ar->iocr[output_idx].data_length > 0) {
        memcpy(frame + pos, ar->iocr[output_idx].data_buffer,
               ar->iocr[output_idx].data_length);
        pos += ar->iocr[output_idx].data_length;
    }

    /* IOPS for each slot */
    for (int i = 0; i < 8; i++) {
        frame[pos++] = IOPS_GOOD;
    }

    /* Cycle counter (16-bit) */
    static uint16_t cycle_counter = 0;
    uint16_t net_counter = htons(cycle_counter++);
    memcpy(frame + pos, &net_counter, 2);
    pos += 2;

    /* Data status */
    frame[pos++] = PROFINET_DATA_STATUS_STATE |
                   PROFINET_DATA_STATUS_VALID |
                   PROFINET_DATA_STATUS_RUN;

    /* Transfer status */
    frame[pos++] = 0x00;

    /* Pad to minimum frame size */
    while (pos < ETH_MIN_FRAME_LEN) {
        frame[pos++] = 0x00;
    }

    return send_frame(manager, ar->device_mac, frame, pos);
}

/* Public functions */

wtc_result_t ar_manager_init(ar_manager_t **manager,
                              int socket_fd,
                              const uint8_t *controller_mac) {
    if (!manager || socket_fd < 0 || !controller_mac) {
        return WTC_ERROR_INVALID_PARAM;
    }

    ar_manager_t *mgr = calloc(1, sizeof(ar_manager_t));
    if (!mgr) {
        return WTC_ERROR_NO_MEMORY;
    }

    mgr->socket_fd = socket_fd;
    memcpy(mgr->controller_mac, controller_mac, 6);
    mgr->session_key_counter = 1;
    pthread_mutex_init(&mgr->lock, NULL);

    /* Get interface index from socket */
    struct sockaddr_ll sll;
    socklen_t sll_len = sizeof(sll);
    if (getsockname(socket_fd, (struct sockaddr *)&sll, &sll_len) == 0) {
        mgr->if_index = sll.sll_ifindex;
    }

    *manager = mgr;
    LOG_DEBUG("AR manager initialized");
    return WTC_OK;
}

void ar_manager_cleanup(ar_manager_t *manager) {
    if (!manager) return;

    pthread_mutex_lock(&manager->lock);

    /* Free all ARs */
    for (int i = 0; i < manager->ar_count; i++) {
        if (manager->ars[i]) {
            free_iocr_buffers(manager->ars[i]);
            free(manager->ars[i]);
        }
    }

    pthread_mutex_unlock(&manager->lock);
    pthread_mutex_destroy(&manager->lock);
    free(manager);

    LOG_DEBUG("AR manager cleaned up");
}

wtc_result_t ar_manager_create_ar(ar_manager_t *manager,
                                   const ar_config_t *config,
                                   profinet_ar_t **ar) {
    if (!manager || !config || !ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    if (manager->ar_count >= MAX_ARS) {
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_FULL;
    }

    /* Check for duplicate */
    for (int i = 0; i < manager->ar_count; i++) {
        if (manager->ars[i] &&
            strcmp(manager->ars[i]->device_station_name, config->station_name) == 0) {
            pthread_mutex_unlock(&manager->lock);
            return WTC_ERROR_ALREADY_EXISTS;
        }
    }

    /* Create AR */
    profinet_ar_t *new_ar = calloc(1, sizeof(profinet_ar_t));
    if (!new_ar) {
        pthread_mutex_unlock(&manager->lock);
        return WTC_ERROR_NO_MEMORY;
    }

    generate_uuid(new_ar->ar_uuid);
    new_ar->session_key = manager->session_key_counter++;
    new_ar->type = AR_TYPE_IOCAR;
    new_ar->state = AR_STATE_INIT;

    strncpy(new_ar->device_station_name, config->station_name,
            sizeof(new_ar->device_station_name) - 1);
    memcpy(new_ar->device_mac, config->device_mac, 6);
    new_ar->device_ip = config->device_ip;
    new_ar->watchdog_ms = config->watchdog_ms > 0 ? config->watchdog_ms : 3000;

    /* Count input and output slots */
    int input_slots = 0, output_slots = 0;
    for (int i = 0; i < config->slot_count; i++) {
        if (config->slots[i].type == SLOT_TYPE_SENSOR) {
            input_slots++;
        } else if (config->slots[i].type == SLOT_TYPE_ACTUATOR) {
            output_slots++;
        }
    }

    /* Allocate IOCR buffers */
    wtc_result_t res = allocate_iocr_buffers(new_ar, input_slots, output_slots);
    if (res != WTC_OK) {
        free(new_ar);
        pthread_mutex_unlock(&manager->lock);
        return res;
    }

    /* Add to manager */
    manager->ars[manager->ar_count++] = new_ar;
    *ar = new_ar;

    pthread_mutex_unlock(&manager->lock);

    LOG_INFO("Created AR for %s (session_key=%u, inputs=%d, outputs=%d)",
             config->station_name, new_ar->session_key, input_slots, output_slots);

    return WTC_OK;
}

wtc_result_t ar_manager_delete_ar(ar_manager_t *manager,
                                   const char *station_name) {
    if (!manager || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&manager->lock);

    for (int i = 0; i < manager->ar_count; i++) {
        if (manager->ars[i] &&
            strcmp(manager->ars[i]->device_station_name, station_name) == 0) {
            free_iocr_buffers(manager->ars[i]);
            free(manager->ars[i]);

            /* Shift remaining ARs */
            for (int j = i; j < manager->ar_count - 1; j++) {
                manager->ars[j] = manager->ars[j + 1];
            }
            manager->ars[--manager->ar_count] = NULL;

            pthread_mutex_unlock(&manager->lock);
            LOG_INFO("Deleted AR for %s", station_name);
            return WTC_OK;
        }
    }

    pthread_mutex_unlock(&manager->lock);
    return WTC_ERROR_NOT_FOUND;
}

profinet_ar_t *ar_manager_get_ar(ar_manager_t *manager,
                                  const char *station_name) {
    if (!manager || !station_name) return NULL;

    for (int i = 0; i < manager->ar_count; i++) {
        if (manager->ars[i] &&
            strcmp(manager->ars[i]->device_station_name, station_name) == 0) {
            return manager->ars[i];
        }
    }

    return NULL;
}

profinet_ar_t *ar_manager_get_ar_by_frame_id(ar_manager_t *manager,
                                              uint16_t frame_id) {
    if (!manager) return NULL;

    for (int i = 0; i < manager->ar_count; i++) {
        if (manager->ars[i]) {
            for (int j = 0; j < manager->ars[i]->iocr_count; j++) {
                if (manager->ars[i]->iocr[j].frame_id == frame_id) {
                    return manager->ars[i];
                }
            }
        }
    }

    return NULL;
}

wtc_result_t ar_manager_process(ar_manager_t *manager) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Process each AR state machine */
    for (int i = 0; i < manager->ar_count; i++) {
        profinet_ar_t *ar = manager->ars[i];
        if (!ar) continue;

        switch (ar->state) {
        case AR_STATE_INIT:
            /* Waiting for connect request to be sent */
            break;

        case AR_STATE_CONNECT_REQ:
            /* Waiting for connect response */
            /* Timeout handling would go here */
            break;

        case AR_STATE_CONNECT_CNF:
            /* Connection confirmed, move to parameter server */
            ar->state = AR_STATE_PRMSRV;
            break;

        case AR_STATE_PRMSRV:
            /* Parameter server phase */
            /* Send parameter end when done */
            ar->state = AR_STATE_READY;
            break;

        case AR_STATE_READY:
            /* Ready for cyclic data exchange */
            ar->state = AR_STATE_RUN;
            LOG_INFO("AR %s entered RUN state", ar->device_station_name);
            break;

        case AR_STATE_RUN:
            /* Normal operation - cyclic data exchange */
            break;

        case AR_STATE_CLOSE:
        case AR_STATE_ABORT:
            /* AR is closing or aborted */
            break;
        }
    }

    return WTC_OK;
}

wtc_result_t ar_send_connect_request(ar_manager_t *manager,
                                      profinet_ar_t *ar) {
    if (!manager || !ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* In a full implementation, this would send a PROFINET RPC connect request */
    /* For now, we simulate immediate connection */
    ar->state = AR_STATE_CONNECT_REQ;
    ar->last_activity_ms = time_get_ms();

    LOG_INFO("Sending connect request to %s", ar->device_station_name);

    /* Simulate connection confirmation (in real implementation, wait for response) */
    ar->state = AR_STATE_CONNECT_CNF;

    return WTC_OK;
}

wtc_result_t ar_send_parameter_end(ar_manager_t *manager,
                                    profinet_ar_t *ar) {
    if (!manager || !ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Send parameter end RPC */
    ar->state = AR_STATE_READY;
    ar->last_activity_ms = time_get_ms();

    LOG_DEBUG("Sent parameter end to %s", ar->device_station_name);
    return WTC_OK;
}

wtc_result_t ar_send_application_ready(ar_manager_t *manager,
                                        profinet_ar_t *ar) {
    if (!manager || !ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Send application ready RPC */
    ar->state = AR_STATE_RUN;
    ar->last_activity_ms = time_get_ms();

    LOG_DEBUG("Sent application ready to %s", ar->device_station_name);
    return WTC_OK;
}

wtc_result_t ar_send_release_request(ar_manager_t *manager,
                                      profinet_ar_t *ar) {
    if (!manager || !ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Send release request RPC */
    ar->state = AR_STATE_CLOSE;
    ar->last_activity_ms = time_get_ms();

    LOG_INFO("Sent release request to %s", ar->device_station_name);
    return WTC_OK;
}

wtc_result_t ar_handle_rpc(ar_manager_t *manager,
                            const uint8_t *frame,
                            size_t len) {
    if (!manager || !frame) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Parse RPC frame and dispatch to appropriate AR */
    /* Full RPC parsing would go here */
    (void)len;

    return WTC_OK;
}

wtc_result_t ar_handle_rt_frame(ar_manager_t *manager,
                                 const uint8_t *frame,
                                 size_t len) {
    if (!manager || !frame || len < ETH_HEADER_LEN + 4) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Get frame ID */
    uint16_t frame_id = ntohs(*(uint16_t *)(frame + ETH_HEADER_LEN));

    /* Find AR by frame ID */
    profinet_ar_t *ar = ar_manager_get_ar_by_frame_id(manager, frame_id);
    if (!ar) {
        return WTC_ERROR_NOT_FOUND;
    }

    /* Find matching IOCR */
    for (int i = 0; i < ar->iocr_count; i++) {
        if (ar->iocr[i].frame_id == frame_id &&
            ar->iocr[i].type == IOCR_TYPE_INPUT) {
            /* Copy data to buffer */
            size_t data_offset = ETH_HEADER_LEN + 2; /* After frame ID */
            size_t data_len = ar->iocr[i].data_length;

            if (data_offset + data_len <= len && ar->iocr[i].data_buffer) {
                memcpy(ar->iocr[i].data_buffer, frame + data_offset, data_len);
                ar->iocr[i].last_frame_time_us = time_get_monotonic_us();
            }

            ar->last_activity_ms = time_get_ms();
            return WTC_OK;
        }
    }

    return WTC_ERROR_NOT_FOUND;
}

wtc_result_t ar_send_output_data(ar_manager_t *manager,
                                  profinet_ar_t *ar) {
    return send_cyclic_frame(manager, ar);
}

wtc_result_t ar_manager_get_all(ar_manager_t *manager,
                                 profinet_ar_t **ars,
                                 int *count,
                                 int max_count) {
    if (!manager || !ars || !count) {
        return WTC_ERROR_INVALID_PARAM;
    }

    int copy_count = manager->ar_count;
    if (copy_count > max_count) {
        copy_count = max_count;
    }

    for (int i = 0; i < copy_count; i++) {
        ars[i] = manager->ars[i];
    }
    *count = copy_count;

    return WTC_OK;
}

wtc_result_t ar_manager_check_health(ar_manager_t *manager) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint64_t now_ms = time_get_ms();

    for (int i = 0; i < manager->ar_count; i++) {
        profinet_ar_t *ar = manager->ars[i];
        if (!ar || ar->state != AR_STATE_RUN) continue;

        /* Check watchdog timeout */
        if (now_ms - ar->last_activity_ms > ar->watchdog_ms) {
            LOG_WARN("AR %s watchdog timeout", ar->device_station_name);
            ar->state = AR_STATE_ABORT;
        }
    }

    return WTC_OK;
}
