/*
 * Water Treatment Controller - AR Manager Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "ar_manager.h"
#include "cyclic_exchange.h"
#include "gsdml_cache.h"
#include "profinet_frame.h"
#include "profinet_identity.h"
#include "profinet_rpc.h"
#include "rpc_strategy.h"
#include "gsdml_modules.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <sys/socket.h>
#include <linux/if_packet.h>
#include <arpa/inet.h>
#include <unistd.h>

/* Maximum ARs */
#define MAX_ARS 64

/* Connect request timeout in milliseconds (PN-C3 fix) */
#define AR_CONNECT_TIMEOUT_MS 10000

/* Maximum retry attempts for ABORT recovery (PN-C4 fix) */
#define AR_MAX_RETRY_ATTEMPTS 3

/* Minimum c_sdu_length for RT_CLASS_1 per IEC 61158-6 */
#define IOCR_MIN_C_SDU_LENGTH  40

/* AR manager structure */
struct ar_manager {
    int socket_fd;
    uint8_t controller_mac[6];
    uint32_t controller_ip;
    int if_index;
    char interface_name[32]; /* PROFINET NIC — passed to RPC for SO_BINDTODEVICE */

    profinet_ar_t *ars[MAX_ARS];
    int ar_count;

    uint16_t session_key_counter;
    pthread_mutex_t lock;

    /* RPC context for PROFINET connection establishment */
    rpc_context_t rpc_ctx;
    bool rpc_initialized;

    /* Controller UUID (generated once at startup) */
    uint8_t controller_uuid[16];

    /* Controller NameOfStation (CMInitiatorStationName in ARBlockReq).
     * This is the CONTROLLER's identity, not the device's. */
    char controller_station_name[64];

    /* State change notification */
    ar_state_change_callback_t state_callback;
    void *state_callback_ctx;
};

/* Notify state change if callback is registered */
static void notify_state_change(ar_manager_t *manager,
                                 profinet_ar_t *ar,
                                 ar_state_t old_state,
                                 ar_state_t new_state) {
    if (manager->state_callback && old_state != new_state) {
        manager->state_callback(ar->device_station_name,
                                old_state, new_state,
                                manager->state_callback_ctx);
    }
}

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

    /* Fill IOPS bytes in the C-SDU buffer (1 per IODataObject, after user data) */
    if (ar->iocr[output_idx].data_buffer) {
        uint16_t iops_off = ar->iocr[output_idx].user_data_length;
        for (int i = 0; i < ar->iocr[output_idx].iodata_count; i++) {
            ar->iocr[output_idx].data_buffer[iops_off + i] = IOPS_GOOD;
        }
        /* Fill IOCS bytes (1 per IOCS entry, acknowledges received input data) */
        uint16_t iocs_off = iops_off + ar->iocr[output_idx].iodata_count;
        for (int i = 0; i < ar->iocr[output_idx].iocs_count; i++) {
            ar->iocr[output_idx].data_buffer[iocs_off + i] = IOPS_GOOD;
        }
    }

    /* Send complete C-SDU (user data + IOPS + IOCS) */
    if (ar->iocr[output_idx].data_buffer && ar->iocr[output_idx].data_length > 0) {
        memcpy(frame + pos, ar->iocr[output_idx].data_buffer,
               ar->iocr[output_idx].data_length);
        pos += ar->iocr[output_idx].data_length;
    }

    /* Cycle counter (16-bit, per-IOCR for correct sequencing) */
    uint16_t net_counter = htons(ar->iocr[output_idx].cycle_counter++);
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
                              const uint8_t *controller_mac,
                              const char *controller_station_name,
                              uint16_t vendor_id,
                              uint16_t device_id,
                              const char *interface_name) {
    if (!manager || socket_fd < 0 || !controller_mac || !controller_station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    ar_manager_t *mgr = calloc(1, sizeof(ar_manager_t));
    if (!mgr) {
        return WTC_ERROR_NO_MEMORY;
    }

    mgr->socket_fd = socket_fd;
    memcpy(mgr->controller_mac, controller_mac, 6);
    strncpy(mgr->controller_station_name, controller_station_name,
            sizeof(mgr->controller_station_name) - 1);
    mgr->session_key_counter = 1;
    pthread_mutex_init(&mgr->lock, NULL);

    /* Store interface name for RPC socket binding (SO_BINDTODEVICE) */
    if (interface_name) {
        strncpy(mgr->interface_name, interface_name,
                sizeof(mgr->interface_name) - 1);
    }

    /* Store controller station name for CMInitiatorStationName in ARBlockReq.
     * This MUST be the controller's NameOfStation, not the device's. */
    strncpy(mgr->controller_station_name, controller_station_name,
            sizeof(mgr->controller_station_name) - 1);

    /* Get interface index from socket */
    struct sockaddr_ll sll;
    socklen_t sll_len = sizeof(sll);
    if (getsockname(socket_fd, (struct sockaddr *)&sll, &sll_len) == 0) {
        mgr->if_index = sll.sll_ifindex;
    }

    /*
     * Build CMInitiatorObjectUUID per IEC 61158-6-10 §4.10.3.2:
     *   DEA00000-6C97-11D1-8271-{instance}{device}{vendor}
     * This identifies the controller in the ARBlockReq.
     */
    pn_build_cm_initiator_uuid(mgr->controller_uuid,
                                vendor_id, device_id, PN_INSTANCE_ID);

    *manager = mgr;
    LOG_DEBUG("AR manager initialized: station='%s', interface=%s",
              controller_station_name, interface_name ? interface_name : "any");
    return WTC_OK;
}

void ar_manager_set_controller_ip(ar_manager_t *manager, uint32_t ip) {
    if (!manager) return;

    pthread_mutex_lock(&manager->lock);
    manager->controller_ip = ip;

    /* If RPC was already initialized with different IP, cleanup and reinit */
    if (manager->rpc_initialized && manager->rpc_ctx.controller_ip != ip) {
        LOG_INFO("Controller IP changed, reinitializing RPC context");
        rpc_context_cleanup(&manager->rpc_ctx);
        manager->rpc_initialized = false;
    }

    pthread_mutex_unlock(&manager->lock);
    LOG_INFO("Controller IP set to %08X", ip);
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

    /* Clean up RPC context if initialized */
    if (manager->rpc_initialized) {
        rpc_context_cleanup(&manager->rpc_ctx);
        manager->rpc_initialized = false;
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
    new_ar->device_vendor_id = config->vendor_id;
    new_ar->device_device_id = config->device_id;
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

    /* Store slot configuration for GSDML module identification */
    new_ar->slot_count = 0;
    for (int i = 0; i < config->slot_count && new_ar->slot_count < WTC_MAX_SLOTS; i++) {
        ar_slot_info_t *info = &new_ar->slot_info[new_ar->slot_count];
        info->slot = (uint16_t)config->slots[i].slot;
        info->subslot = (uint16_t)config->slots[i].subslot;
        info->type = config->slots[i].type;
        info->measurement_type = config->slots[i].measurement_type;
        info->actuator_type = config->slots[i].actuator_type;
        new_ar->slot_count++;
    }

    /* Add to manager */
    manager->ars[manager->ar_count++] = new_ar;
    *ar = new_ar;

    pthread_mutex_unlock(&manager->lock);

    LOG_INFO("Created AR for %s (session_key=%u, inputs=%d, outputs=%d, slots=%d)",
             config->station_name, new_ar->session_key, input_slots, output_slots,
             new_ar->slot_count);

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

/* Timeout for waiting for ApplicationReady from device (30 seconds) */
#define AR_APP_READY_TIMEOUT_MS 30000

wtc_result_t ar_manager_process(ar_manager_t *manager) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint64_t now_ms = time_get_ms();

    /*
     * Poll for incoming RPC requests from devices.
     * Devices send ApplicationReady after we send PrmEnd.
     * Per IEC 61158-6-10: Device sends ApplicationReady TO Controller.
     */
    if (manager->rpc_initialized) {
        uint8_t recv_buf[RPC_MAX_PDU_SIZE];
        size_t recv_len = 0;
        uint32_t source_ip = 0;
        uint16_t source_port = 0;

        wtc_result_t res = rpc_poll_incoming(&manager->rpc_ctx, recv_buf,
                                              sizeof(recv_buf), &recv_len,
                                              &source_ip, &source_port);
        if (res == WTC_OK && recv_len > 0) {
            /* Parse incoming RPC */
            incoming_control_request_t incoming_req;
            res = rpc_parse_incoming_control_request(recv_buf, recv_len, &incoming_req);

            if (res == WTC_OK) {
                incoming_req.source_ip = source_ip;
                incoming_req.source_port = source_port;

                /* Handle based on control command */
                if (incoming_req.control_command == CONTROL_CMD_APP_READY) {
                    LOG_INFO("Received ApplicationReady from device at %d.%d.%d.%d:%u",
                             source_ip & 0xFF, (source_ip >> 8) & 0xFF,
                             (source_ip >> 16) & 0xFF, (source_ip >> 24) & 0xFF,
                             source_port);

                    /* Find AR by session key and/or AR UUID (under lock) */
                    pthread_mutex_lock(&manager->lock);
                    profinet_ar_t *ar = NULL;
                    for (int i = 0; i < manager->ar_count; i++) {
                        if (manager->ars[i] &&
                            manager->ars[i]->session_key == incoming_req.session_key &&
                            memcmp(manager->ars[i]->ar_uuid, incoming_req.ar_uuid, 16) == 0) {
                            ar = manager->ars[i];
                            break;
                        }
                    }

                    if (ar) {
                        if (ar->state == AR_STATE_READY) {
                            /* Build and send response */
                            uint8_t resp_buf[RPC_MAX_PDU_SIZE];
                            size_t resp_len = sizeof(resp_buf);

                            res = rpc_build_control_response(&manager->rpc_ctx,
                                                              &incoming_req,
                                                              resp_buf, &resp_len);
                            if (res == WTC_OK) {
                                res = rpc_send_response(&manager->rpc_ctx,
                                                         source_ip, source_port,
                                                         resp_buf, resp_len);
                            }

                            if (res == WTC_OK) {
                                ar_state_t old_state = ar->state;
                                ar->state = AR_STATE_RUN;
                                ar->last_activity_ms = now_ms;
                                notify_state_change(manager, ar, old_state, AR_STATE_RUN);
                                LOG_INFO("AR %s received ApplicationReady, now RUNNING",
                                         ar->device_station_name);
                            } else {
                                LOG_ERROR("Failed to respond to ApplicationReady for %s",
                                          ar->device_station_name);
                            }
                        } else {
                            LOG_WARN("Received ApplicationReady for AR %s in unexpected state %d",
                                     ar->device_station_name, ar->state);
                        }
                    } else {
                        LOG_WARN("Received ApplicationReady for unknown AR (session_key=%u)",
                                 incoming_req.session_key);
                    }
                    pthread_mutex_unlock(&manager->lock);
                } else {
                    LOG_DEBUG("Received incoming RPC with command %u (not ApplicationReady)",
                              incoming_req.control_command);
                }
            }
        }
    }

    /* Process each AR state machine under lock to prevent concurrent
     * modification (e.g. ar_manager_delete_ar shifting the array). */
    pthread_mutex_lock(&manager->lock);

    for (int i = 0; i < manager->ar_count; i++) {
        profinet_ar_t *ar = manager->ars[i];
        if (!ar || __atomic_load_n(&ar->connecting, __ATOMIC_ACQUIRE)) continue;

        switch (ar->state) {
        case AR_STATE_INIT:
            break;

        case AR_STATE_CONNECT_REQ:
            if (now_ms - ar->last_activity_ms > AR_CONNECT_TIMEOUT_MS) {
                LOG_WARN("AR %s connect request timeout after %d ms",
                         ar->device_station_name, AR_CONNECT_TIMEOUT_MS);
                ar->state = AR_STATE_ABORT;
                ar->last_activity_ms = now_ms;
            }
            break;

        case AR_STATE_CONNECT_CNF:
            LOG_DEBUG("AR %s connection confirmed, entering PRMSRV phase",
                      ar->device_station_name);
            ar->state = AR_STATE_PRMSRV;
            ar->last_activity_ms = now_ms;
            break;

        case AR_STATE_PRMSRV:
            LOG_DEBUG("AR %s in PRMSRV, sending ParameterEnd",
                      ar->device_station_name);
            if (ar_send_parameter_end(manager, ar) != WTC_OK) {
                LOG_ERROR("AR %s ParameterEnd failed, aborting",
                          ar->device_station_name);
            }
            break;

        case AR_STATE_READY:
            if (now_ms - ar->last_activity_ms > AR_APP_READY_TIMEOUT_MS) {
                LOG_ERROR("AR %s timeout waiting for ApplicationReady from device",
                          ar->device_station_name);
                ar->state = AR_STATE_ABORT;
                ar->last_activity_ms = now_ms;
            }
            break;

        case AR_STATE_RUN:
            break;

        case AR_STATE_CLOSE:
            break;

        case AR_STATE_ABORT: {
            /* Retry limit: permanent errors (PROTOCOL) give up immediately.
             * Transient errors (TIMEOUT, CONNECTION_FAILED, IO) retry with
             * exponential backoff up to AR_MAX_RETRY_ATTEMPTS. */
            bool is_permanent = (ar->last_error == WTC_ERROR_PROTOCOL ||
                                 ar->last_error == WTC_ERROR_PERMISSION);

            if (is_permanent || ar->retry_count >= AR_MAX_RETRY_ATTEMPTS) {
                LOG_ERROR("AR %s: giving up after %d attempts (last_error=%d, %s)",
                          ar->device_station_name, ar->retry_count,
                          ar->last_error,
                          is_permanent ? "permanent" : "max retries");
                ar_state_t old_state = ar->state;
                ar->state = AR_STATE_CLOSE;
                notify_state_change(manager, ar, old_state, AR_STATE_CLOSE);
                break;
            }

            /* Exponential backoff: 5s, 10s, 20s (capped at 30s).
             * Add jitter ±25% to prevent synchronized retry storms
             * when multiple RTUs fail simultaneously. */
            uint32_t base_ms = 5000u << (ar->retry_count > 3 ? 3 : ar->retry_count);
            if (base_ms > 30000) base_ms = 30000;
            uint32_t jitter = base_ms / 4;
            uint32_t backoff_ms = base_ms - jitter + (uint32_t)(now_ms % (2 * jitter + 1));

            uint32_t elapsed = (uint32_t)(now_ms - ar->last_activity_ms);
            if (elapsed < backoff_ms) {
                break;
            }

            LOG_INFO("AR %s: ABORT recovery attempt %d/%d after %u ms",
                     ar->device_station_name, ar->retry_count + 1,
                     AR_MAX_RETRY_ATTEMPTS, elapsed);

            /*
             * Send Release to clean up any stale AR on the RTU before
             * retrying Connect.  Without this, the RTU has a partially-
             * created AR from the previous attempt and silently drops
             * new Connect requests (empty response, then no response).
             *
             * Copy fields under lock, release lock for blocking I/O,
             * then re-acquire — same pattern as read_record/write_record.
             */
            if (manager->rpc_initialized && ar->device_ip != 0) {
                uint8_t rel_uuid[16];
                uint16_t rel_session = ar->session_key;
                uint32_t rel_ip = ar->device_ip;
                memcpy(rel_uuid, ar->ar_uuid, 16);

                pthread_mutex_unlock(&manager->lock);

                LOG_DEBUG("AR %s: sending Release to clear stale AR",
                          ar->device_station_name);
                rpc_release(&manager->rpc_ctx, rel_ip,
                            rel_uuid, rel_session);

                pthread_mutex_lock(&manager->lock);
                /* AR may have been deleted while unlocked — re-validate */
                if (i >= manager->ar_count || manager->ars[i] != ar) {
                    break;
                }
            }

            ar_state_t old_state = ar->state;
            ar->retry_count++;
            ar_send_connect_request(manager, ar);

            if (ar->state != old_state) {
                notify_state_change(manager, ar, old_state, ar->state);
            } else {
                /* Connect failed again — stay in ABORT, backoff will increase */
                ar->last_activity_ms = now_ms;
            }
            break;
        }
        }
    }

    pthread_mutex_unlock(&manager->lock);

    return WTC_OK;
}

/**
 * @brief Ensure RPC context is initialized.
 *
 * Lazily initializes the RPC context when first needed. The controller IP
 * must be set before calling this function.
 *
 * @param[in] manager   AR manager instance
 * @return WTC_OK on success, error code on failure
 *
 * @note Thread safety: Must hold manager lock
 * @note Memory: First call allocates UDP socket
 */
static wtc_result_t ensure_rpc_initialized(ar_manager_t *manager) {
    if (manager->rpc_initialized) {
        return WTC_OK;
    }

    if (manager->controller_ip == 0) {
        LOG_ERROR("Controller IP not set, cannot initialize RPC");
        return WTC_ERROR_NOT_INITIALIZED;
    }

    wtc_result_t res = rpc_context_init(&manager->rpc_ctx,
                                         manager->controller_mac,
                                         manager->controller_ip,
                                         manager->interface_name);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to initialize RPC context");
        return res;
    }

    manager->rpc_initialized = true;
    LOG_INFO("RPC context initialized for controller IP %08X on %s",
             manager->controller_ip,
             manager->interface_name[0] ? manager->interface_name : "any");
    return WTC_OK;
}

/**
 * @brief Build connect request parameters from AR configuration.
 *
 * @param[in]  manager  AR manager instance
 * @param[in]  ar       AR to connect
 * @param[out] params   Filled connect request parameters
 *
 * @note Thread safety: SAFE (read-only access to ar)
 * @note Memory: NO_ALLOC
 */
static void build_connect_params(ar_manager_t *manager,
                                  profinet_ar_t *ar,
                                  connect_request_params_t *params) {
    memset(params, 0, sizeof(connect_request_params_t));

    /* AR configuration */
    memcpy(params->ar_uuid, ar->ar_uuid, 16);
    params->session_key = ar->session_key;
    params->ar_type = ar->type;
    params->ar_properties = AR_PROP_STATE_ACTIVE |
                            AR_PROP_PARAMETERIZATION_TYPE |
                            AR_PROP_STARTUP_MODE_LEGACY;

    /* ARBlockReq carries CMInitiatorStationName — the CONTROLLER's name,
     * not the device's.  Using the device name here causes p-net to reject
     * the connect request (silent drop or invalid response). */
    strncpy(params->station_name, manager->controller_station_name,
            sizeof(params->station_name) - 1);

    /* Controller info */
    memcpy(params->controller_mac, manager->controller_mac, 6);
    memcpy(params->controller_uuid, manager->controller_uuid, 16);
    params->controller_port = manager->rpc_ctx.controller_port;
    params->activity_timeout = 100;  /* 100 * 100ms = 10 seconds */

    /* IOCR configuration from AR.
     * Conservative timing: 2ms cycle (SCF=64), 256ms update (RR=128),
     * 2.56s watchdog (WDF=10), 20s alarm timeout, 5 retries.
     * Clamp c_sdu_length to minimum 40 per IEC 61158-6. */
    timing_params_t tp;
    rpc_strategy_get_timing(TIMING_CONSERVATIVE, &tp);

    params->iocr_count = 0;
    for (int i = 0; i < ar->iocr_count && params->iocr_count < 4; i++) {
        params->iocr[params->iocr_count].type = ar->iocr[i].type;
        params->iocr[params->iocr_count].reference = (uint16_t)(i + 1);
        params->iocr[params->iocr_count].frame_id = ar->iocr[i].frame_id;

        /* Enforce minimum c_sdu_length of 40 for the wire format */
        uint16_t dl = (uint16_t)ar->iocr[i].data_length;
        if (dl < IOCR_MIN_C_SDU_LENGTH) {
            dl = IOCR_MIN_C_SDU_LENGTH;
        }
        params->iocr[params->iocr_count].data_length = dl;

        params->iocr[params->iocr_count].send_clock_factor = tp.send_clock_factor;
        params->iocr[params->iocr_count].reduction_ratio = tp.reduction_ratio;
        params->iocr[params->iocr_count].watchdog_factor = tp.watchdog_factor;
        params->iocr_count++;
    }
    params->data_hold_factor = tp.data_hold_factor;
    params->rta_timeout_factor = tp.rta_timeout_factor;
    params->rta_retries = tp.rta_retries;

    /*
     * Expected configuration using GSDML-defined module identifiers.
     * Module identifiers must match the Water-Treat RTU GSDML exactly.
     */
    params->expected_count = 0;

    /* DAP slot 0 — 3 mandatory submodules per IEC 61158-6:
     *   Subslot 0x0001: DAP identity (submod 0x00000001)
     *   Subslot 0x8000: Interface   (submod 0x00000100)
     *   Subslot 0x8001: Port        (submod 0x00000200)
     * All have data_length=0 (PNET_DIR_NO_IO). */
    params->expected_config[params->expected_count].slot = 0;
    params->expected_config[params->expected_count].module_ident = GSDML_MOD_DAP;
    params->expected_config[params->expected_count].subslot = 0x0001;
    params->expected_config[params->expected_count].submodule_ident = GSDML_SUBMOD_DAP;
    params->expected_config[params->expected_count].data_length = 0;
    params->expected_config[params->expected_count].is_input = true;
    params->expected_count++;

    params->expected_config[params->expected_count].slot = 0;
    params->expected_config[params->expected_count].module_ident = GSDML_MOD_DAP;
    params->expected_config[params->expected_count].subslot = 0x8000;
    params->expected_config[params->expected_count].submodule_ident = GSDML_SUBMOD_INTERFACE;
    params->expected_config[params->expected_count].data_length = 0;
    params->expected_config[params->expected_count].is_input = true;
    params->expected_count++;

    params->expected_config[params->expected_count].slot = 0;
    params->expected_config[params->expected_count].module_ident = GSDML_MOD_DAP;
    params->expected_config[params->expected_count].subslot = 0x8001;
    params->expected_config[params->expected_count].submodule_ident = GSDML_SUBMOD_PORT;
    params->expected_config[params->expected_count].data_length = 0;
    params->expected_config[params->expected_count].is_input = true;
    params->expected_count++;

    /* Add slots from stored slot configuration with GSDML module IDs */
    for (int i = 0; i < ar->slot_count && params->expected_count < WTC_MAX_SLOTS; i++) {
        ar_slot_info_t *slot = &ar->slot_info[i];
        uint32_t mod_ident, submod_ident;
        uint16_t data_length;
        bool is_input;

        if (slot->type == SLOT_TYPE_SENSOR) {
            /* Input module - use measurement type for GSDML ID */
            mod_ident = gsdml_get_input_module_ident(slot->measurement_type);
            submod_ident = gsdml_get_input_submodule_ident(slot->measurement_type);
            data_length = GSDML_INPUT_DATA_SIZE;  /* 5 bytes: 4B float + 1B quality */
            is_input = true;
        } else if (slot->type == SLOT_TYPE_ACTUATOR) {
            /* Output module - use actuator type for GSDML ID */
            mod_ident = gsdml_get_output_module_ident(slot->actuator_type);
            submod_ident = gsdml_get_output_submodule_ident(slot->actuator_type);
            data_length = GSDML_OUTPUT_DATA_SIZE;  /* 4 bytes: 1B cmd + 1B duty + 2B reserved */
            is_input = false;
        } else {
            continue;  /* Skip unknown slot types */
        }

        params->expected_config[params->expected_count].slot = slot->slot;
        params->expected_config[params->expected_count].module_ident = mod_ident;
        params->expected_config[params->expected_count].subslot = slot->subslot > 0 ? slot->subslot : 1;
        params->expected_config[params->expected_count].submodule_ident = submod_ident;
        params->expected_config[params->expected_count].data_length = data_length;
        params->expected_config[params->expected_count].is_input = is_input;
        params->expected_count++;

        LOG_DEBUG("Slot %d: type=%s mod=0x%08X submod=0x%08X len=%u",
                  slot->slot, is_input ? "INPUT" : "OUTPUT",
                  mod_ident, submod_ident, data_length);
    }

    params->max_alarm_data_length = 200;
}

wtc_result_t ar_send_connect_request(ar_manager_t *manager,
                                      profinet_ar_t *ar) {
    if (!manager || !ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Set controller IP from device IP network (assume same subnet) */
    if (manager->controller_ip == 0 && ar->device_ip != 0) {
        /* Use device's network with .1 as controller IP (gateway heuristic)
         * IP is stored in network byte order (big-endian):
         *   192.168.1.100 = 0xC0A80164
         * Mask off last octet and set to .1:
         *   0xC0A80164 & 0xFFFFFF00 = 0xC0A80100 (192.168.1.0)
         *   0xC0A80100 | 0x00000001 = 0xC0A80101 (192.168.1.1)
         * This is a heuristic - in production, controller IP should be configured
         */
        manager->controller_ip = (ar->device_ip & 0xFFFFFF00) | 0x00000001;
        LOG_DEBUG("Auto-configured controller IP: %08X", manager->controller_ip);
    }

    /* Ensure RPC context is initialized */
    wtc_result_t res = ensure_rpc_initialized(manager);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to initialize RPC for connect request");
        ar->state = AR_STATE_ABORT;
        return res;
    }

    ar->state = AR_STATE_CONNECT_REQ;
    ar->last_activity_ms = time_get_ms();

    LOG_INFO("=== PROFINET Connect: %s (IP: %d.%d.%d.%d) ===",
             ar->device_station_name,
             (ar->device_ip >> 24) & 0xFF, (ar->device_ip >> 16) & 0xFF,
             (ar->device_ip >> 8) & 0xFF, ar->device_ip & 0xFF);

    /* Generate fresh AR UUID and session key for this attempt */
    rpc_generate_uuid((uint8_t *)ar->ar_uuid);
    ar->session_key = manager->session_key_counter++;

    /* Build connect parameters with conservative timing and full expected config.
     * The connect request builder (rpc_build_connect_request) now always includes
     * the NDR header and uses the correct wire format: UUID fields swapped to LE
     * per DREP, OpNum=0 (Connect), VLAN priority tags set. */
    connect_request_params_t params;
    build_connect_params(manager, ar, &params);

    /* Single connect attempt — the wire format is now correct,
     * no brute-force strategy cycling needed. */
    connect_response_t response;
    res = rpc_connect(&manager->rpc_ctx, ar->device_ip, &params, &response);

    if (res == WTC_OK && response.success) {
        /* Update AR with response data */
        memcpy(ar->device_mac, response.device_mac, 6);

        /* Store the device-assigned session key. The device may accept our
         * proposed key or assign a different one — we must use its value
         * for all subsequent RPC calls (ParameterEnd, Release, etc.). */
        ar->session_key = response.session_key;

        for (int i = 0; i < response.frame_id_count &&
                        i < ar->iocr_count; i++) {
            if (ar->iocr[i].frame_id != response.frame_ids[i].assigned) {
                LOG_DEBUG("Frame ID updated IOCR %d: 0x%04X -> 0x%04X",
                          i, ar->iocr[i].frame_id,
                          response.frame_ids[i].assigned);
                ar->iocr[i].frame_id = response.frame_ids[i].assigned;
            }
        }

        if (response.has_diff) {
            LOG_WARN("Device reported module differences, "
                     "AR may have limited functionality");
        }

        ar->state = AR_STATE_CONNECT_CNF;
        ar->last_activity_ms = time_get_ms();
        ar->retry_count = 0;
        ar->last_error = WTC_OK;
        ar->missed_cycles = 0;

        LOG_INFO("=== CONNECT SUCCESS for %s (session_key=%u) ===",
                 ar->device_station_name, response.session_key);
        return WTC_OK;
    }

    /* Connect failed — classify the error for the ABORT retry handler.
     * PROTOCOL errors (RPC fault, wrong opnum) are permanent.
     * TIMEOUT and IO errors are transient — worth retrying. */
    ar->state = AR_STATE_ABORT;
    ar->last_activity_ms = time_get_ms();
    ar->last_error = (res != WTC_OK) ? res : WTC_ERROR_CONNECTION_FAILED;

    LOG_ERROR("=== CONNECT FAILED for %s: error=%d ===",
              ar->device_station_name, ar->last_error);
    LOG_INFO("  Will retry from ABORT state with backoff (attempt %d/%d).",
             ar->retry_count, AR_MAX_RETRY_ATTEMPTS);

    return WTC_ERROR_CONNECTION_FAILED;
}

wtc_result_t ar_send_parameter_end(ar_manager_t *manager,
                                    profinet_ar_t *ar) {
    if (!manager || !ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (!manager->rpc_initialized) {
        LOG_ERROR("RPC not initialized for parameter end");
        return WTC_ERROR_NOT_INITIALIZED;
    }

    LOG_INFO("Sending RPC ParameterEnd to %s", ar->device_station_name);

    wtc_result_t res = rpc_parameter_end(&manager->rpc_ctx,
                                          ar->device_ip,
                                          (const uint8_t *)ar->ar_uuid,
                                          ar->session_key);
    if (res != WTC_OK) {
        LOG_ERROR("RPC ParameterEnd failed for %s: error %d",
                  ar->device_station_name, res);
        ar->state = AR_STATE_ABORT;
        ar->last_activity_ms = time_get_ms();
        return res;
    }

    ar->state = AR_STATE_READY;
    ar->last_activity_ms = time_get_ms();

    LOG_INFO("RPC ParameterEnd successful for %s", ar->device_station_name);
    return WTC_OK;
}

wtc_result_t ar_send_application_ready(ar_manager_t *manager,
                                        profinet_ar_t *ar) {
    if (!manager || !ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (!manager->rpc_initialized) {
        LOG_ERROR("RPC not initialized for application ready");
        return WTC_ERROR_NOT_INITIALIZED;
    }

    LOG_INFO("Sending RPC ApplicationReady to %s", ar->device_station_name);

    wtc_result_t res = rpc_application_ready(&manager->rpc_ctx,
                                              ar->device_ip,
                                              (const uint8_t *)ar->ar_uuid,
                                              ar->session_key);
    if (res != WTC_OK) {
        LOG_ERROR("RPC ApplicationReady failed for %s: error %d",
                  ar->device_station_name, res);
        ar->state = AR_STATE_ABORT;
        ar->last_activity_ms = time_get_ms();
        return res;
    }

    ar_state_t old_state = ar->state;
    ar->state = AR_STATE_RUN;
    ar->last_activity_ms = time_get_ms();

    LOG_INFO("RPC ApplicationReady successful for %s - AR now RUNNING",
             ar->device_station_name);
    notify_state_change(manager, ar, old_state, AR_STATE_RUN);
    return WTC_OK;
}

wtc_result_t ar_send_release_request(ar_manager_t *manager,
                                      profinet_ar_t *ar) {
    if (!manager || !ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    ar_state_t old_state = ar->state;
    ar->state = AR_STATE_CLOSE;
    ar->last_activity_ms = time_get_ms();

    if (!manager->rpc_initialized) {
        /* RPC not initialized - just transition to close state */
        LOG_WARN("RPC not initialized, skipping release RPC for %s",
                 ar->device_station_name);
        notify_state_change(manager, ar, old_state, AR_STATE_CLOSE);
        return WTC_OK;
    }

    LOG_INFO("Sending RPC Release to %s", ar->device_station_name);

    /* Send release - don't fail if device doesn't respond */
    wtc_result_t res = rpc_release(&manager->rpc_ctx,
                                    ar->device_ip,
                                    (const uint8_t *)ar->ar_uuid,
                                    ar->session_key);
    if (res != WTC_OK) {
        LOG_WARN("RPC Release did not complete cleanly for %s (error %d), "
                 "AR will be closed anyway",
                 ar->device_station_name, res);
    } else {
        LOG_INFO("RPC Release successful for %s", ar->device_station_name);
    }

    notify_state_change(manager, ar, old_state, AR_STATE_CLOSE);
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

/* Number of consecutive watchdog misses before ABORT.
 * With 3s watchdog, 3 misses = 9s total before disconnect.
 * This prevents one late frame from tearing down the AR. */
#define WATCHDOG_MISS_THRESHOLD 3

wtc_result_t ar_manager_check_health(ar_manager_t *manager) {
    if (!manager) {
        return WTC_ERROR_INVALID_PARAM;
    }

    uint64_t now_ms = time_get_ms();

    for (int i = 0; i < manager->ar_count; i++) {
        profinet_ar_t *ar = manager->ars[i];
        if (!ar || ar->state != AR_STATE_RUN ||
            __atomic_load_n(&ar->connecting, __ATOMIC_ACQUIRE)) continue;

        /* Progressive watchdog: track consecutive misses */
        if (now_ms - ar->last_activity_ms > ar->watchdog_ms) {
            ar->missed_cycles++;

            if (ar->missed_cycles == 1) {
                LOG_WARN("AR %s watchdog miss (%d/%d)",
                         ar->device_station_name,
                         ar->missed_cycles, WATCHDOG_MISS_THRESHOLD);
            } else if (ar->missed_cycles >= WATCHDOG_MISS_THRESHOLD) {
                LOG_ERROR("AR %s watchdog ABORT after %d consecutive misses",
                          ar->device_station_name, ar->missed_cycles);
                ar_state_t old_state = ar->state;
                ar->missed_cycles = 0;
                ar->last_error = WTC_ERROR_TIMEOUT;
                ar->state = AR_STATE_ABORT;
                notify_state_change(manager, ar, old_state, AR_STATE_ABORT);
            } else {
                LOG_WARN("AR %s watchdog miss (%d/%d)",
                         ar->device_station_name,
                         ar->missed_cycles, WATCHDOG_MISS_THRESHOLD);
            }
        } else {
            /* Receiving data — reset miss counter */
            if (ar->missed_cycles > 0) {
                LOG_DEBUG("AR %s watchdog recovered after %d misses",
                          ar->device_station_name, ar->missed_cycles);
                ar->missed_cycles = 0;
            }
        }
    }

    return WTC_OK;
}

void ar_manager_set_state_callback(ar_manager_t *manager,
                                    ar_state_change_callback_t callback,
                                    void *ctx) {
    if (manager) {
        manager->state_callback = callback;
        manager->state_callback_ctx = ctx;
    }
}

/* ============== Phase 2-4: Discovery Pipeline ============== */

/**
 * @brief Build DAP-only connect parameters.
 *
 * Creates connect request params with only DAP (slot 0) submodules:
 *   Subslot 0x0001: DAP identity
 *   Subslot 0x8000: Interface
 *   Subslot 0x8001: Port
 *
 * IOCRs use minimum data_length (40 bytes) since no application I/O.
 */
static void build_dap_connect_params(ar_manager_t *manager,
                                      profinet_ar_t *ar,
                                      connect_request_params_t *params) {
    memset(params, 0, sizeof(connect_request_params_t));

    /* AR configuration */
    memcpy(params->ar_uuid, ar->ar_uuid, 16);
    params->session_key = ar->session_key;
    params->ar_type = ar->type;
    params->ar_properties = AR_PROP_STATE_ACTIVE |
                            AR_PROP_PARAMETERIZATION_TYPE |
                            AR_PROP_STARTUP_MODE_LEGACY;

    /* ARBlockReq carries CMInitiatorStationName — the CONTROLLER's name,
     * not the device's.  Using the device name here causes p-net to reject
     * the connect request (silent drop or invalid response). */
    strncpy(params->station_name, manager->controller_station_name,
            sizeof(params->station_name) - 1);

    /* Controller info */
    memcpy(params->controller_mac, manager->controller_mac, 6);
    memcpy(params->controller_uuid, manager->controller_uuid, 16);
    params->controller_port = manager->rpc_ctx.controller_port;
    params->activity_timeout = 100;

    /* Conservative timing */
    timing_params_t tp;
    rpc_strategy_get_timing(TIMING_CONSERVATIVE, &tp);

    /* Input IOCR: minimum data_length for RT_CLASS_1 */
    params->iocr_count = 2;
    params->iocr[0].type = IOCR_TYPE_INPUT;
    params->iocr[0].reference = 1;
    params->iocr[0].frame_id = 0xC001;
    params->iocr[0].data_length = IOCR_MIN_C_SDU_LENGTH;
    params->iocr[0].send_clock_factor = tp.send_clock_factor;
    params->iocr[0].reduction_ratio = tp.reduction_ratio;
    params->iocr[0].watchdog_factor = tp.watchdog_factor;

    /* Output IOCR: minimum data_length */
    params->iocr[1].type = IOCR_TYPE_OUTPUT;
    params->iocr[1].reference = 2;
    params->iocr[1].frame_id = 0xFFFF; /* Device assigns */
    params->iocr[1].data_length = IOCR_MIN_C_SDU_LENGTH;
    params->iocr[1].send_clock_factor = tp.send_clock_factor;
    params->iocr[1].reduction_ratio = tp.reduction_ratio;
    params->iocr[1].watchdog_factor = tp.watchdog_factor;

    params->data_hold_factor = tp.data_hold_factor;
    params->rta_timeout_factor = tp.rta_timeout_factor;
    params->rta_retries = tp.rta_retries;

    /* DAP-only expected configuration (3 submodules) */
    params->expected_count = 0;

    params->expected_config[0].slot = 0;
    params->expected_config[0].module_ident = GSDML_MOD_DAP;
    params->expected_config[0].subslot = 0x0001;
    params->expected_config[0].submodule_ident = GSDML_SUBMOD_DAP;
    params->expected_config[0].data_length = 0;
    params->expected_config[0].is_input = true;

    params->expected_config[1].slot = 0;
    params->expected_config[1].module_ident = GSDML_MOD_DAP;
    params->expected_config[1].subslot = 0x8000;
    params->expected_config[1].submodule_ident = GSDML_SUBMOD_INTERFACE;
    params->expected_config[1].data_length = 0;
    params->expected_config[1].is_input = true;

    params->expected_config[2].slot = 0;
    params->expected_config[2].module_ident = GSDML_MOD_DAP;
    params->expected_config[2].subslot = 0x8001;
    params->expected_config[2].submodule_ident = GSDML_SUBMOD_PORT;
    params->expected_config[2].data_length = 0;
    params->expected_config[2].is_input = true;

    params->expected_count = 3;
    params->max_alarm_data_length = 200;
}

/**
 * @brief Determine if a discovered module is an input (sensor) module.
 *
 * Uses module_ident ranges from GSDML:
 *   0x10-0x70: sensor modules (input)
 *   0x100+: actuator modules (output)
 */
static bool is_input_module(uint32_t module_ident) {
    return (module_ident >= GSDML_MOD_PH && module_ident <= GSDML_MOD_GENERIC_AI);
}

/**
 * @brief Get I/O data size for a module ident.
 */
static uint16_t get_module_data_size(uint32_t module_ident) {
    if (is_input_module(module_ident)) {
        return GSDML_INPUT_DATA_SIZE;
    }
    return GSDML_OUTPUT_DATA_SIZE;
}

wtc_result_t ar_send_dap_connect_request(ar_manager_t *manager,
                                          profinet_ar_t *ar) {
    if (!manager || !ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Set controller IP if needed */
    if (manager->controller_ip == 0 && ar->device_ip != 0) {
        manager->controller_ip = (ar->device_ip & 0xFFFFFF00) | 0x00000001;
        LOG_DEBUG("Auto-configured controller IP: %08X", manager->controller_ip);
    }

    wtc_result_t res = ensure_rpc_initialized(manager);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to initialize RPC for DAP connect");
        return res;
    }

    LOG_INFO("=== Phase 2: DAP-only Connect to %s ===", ar->device_station_name);

    /* Generate fresh AR UUID and session key */
    rpc_generate_uuid((uint8_t *)ar->ar_uuid);
    ar->session_key = manager->session_key_counter++;

    /* Build DAP-only connect parameters */
    connect_request_params_t params;
    build_dap_connect_params(manager, ar, &params);

    /* Send connect request */
    connect_response_t response;
    res = rpc_connect(&manager->rpc_ctx, ar->device_ip, &params, &response);

    if (res == WTC_OK && response.success) {
        memcpy(ar->device_mac, response.device_mac, 6);

        /* Store the device-assigned session key for subsequent RPC calls */
        ar->session_key = response.session_key;

        ar->state = AR_STATE_CONNECT_CNF;
        ar->last_activity_ms = time_get_ms();

        LOG_INFO("=== DAP Connect SUCCESS for %s (session_key=%u) ===",
                 ar->device_station_name, ar->session_key);

        if (response.has_diff) {
            LOG_DEBUG("DAP connect: module diff block present (expected for DAP-only)");
        }

        return WTC_OK;
    }

    LOG_ERROR("=== DAP Connect FAILED for %s: error=%d ===",
              ar->device_station_name, res);
    return WTC_ERROR_CONNECTION_FAILED;
}

wtc_result_t ar_read_real_identification(ar_manager_t *manager,
                                          profinet_ar_t *ar,
                                          ar_module_discovery_t *discovery) {
    if (!manager || !ar || !discovery) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (!manager->rpc_initialized) {
        LOG_ERROR("RPC not initialized for Record Read");
        return WTC_ERROR_NOT_INITIALIZED;
    }

    memset(discovery, 0, sizeof(ar_module_discovery_t));

    LOG_INFO("=== Phase 3: Record Read 0xF844 from %s ===",
             ar->device_station_name);

    /* Build Record Read parameters */
    read_request_params_t read_params;
    memset(&read_params, 0, sizeof(read_params));
    memcpy(read_params.ar_uuid, ar->ar_uuid, 16);
    read_params.session_key = ar->session_key;
    read_params.api = 0x00000000;
    read_params.slot = 0;          /* DAP slot */
    read_params.subslot = 0x0001;  /* DAP identity subslot */
    read_params.index = 0xF844;    /* RealIdentificationData */
    read_params.max_record_length = RPC_MAX_PDU_SIZE;

    /* Execute Record Read */
    read_response_t read_response;
    wtc_result_t res = rpc_read_record(&manager->rpc_ctx, ar->device_ip,
                                        &read_params, &read_response);
    if (res != WTC_OK) {
        LOG_ERROR("Record Read 0xF844 failed for %s: error=%d",
                  ar->device_station_name, res);
        return res;
    }

    if (!read_response.success) {
        LOG_ERROR("Record Read 0xF844 returned error for %s",
                  ar->device_station_name);
        return WTC_ERROR_PROTOCOL;
    }

    /* Copy discovered modules to output */
    for (int i = 0; i < read_response.module_count &&
                    i < AR_MAX_DISCOVERED_MODULES; i++) {
        discovery->modules[i].slot = read_response.modules[i].slot;
        discovery->modules[i].subslot = read_response.modules[i].subslot;
        discovery->modules[i].module_ident = read_response.modules[i].module_ident;
        discovery->modules[i].submodule_ident = read_response.modules[i].submodule_ident;
    }
    discovery->module_count = read_response.module_count;
    discovery->from_cache = false;

    LOG_INFO("=== Module Discovery: %d modules found on %s ===",
             discovery->module_count, ar->device_station_name);

    for (int i = 0; i < discovery->module_count; i++) {
        ar_discovered_module_t *m = &discovery->modules[i];
        LOG_DEBUG("  Slot %u.0x%04X: module=0x%08X submod=0x%08X",
                  m->slot, m->subslot, m->module_ident, m->submodule_ident);
    }

    return WTC_OK;
}

wtc_result_t ar_build_full_connect_params(ar_manager_t *manager,
                                           profinet_ar_t *ar,
                                           const ar_module_discovery_t *discovery) {
    if (!manager || !ar || !discovery) {
        return WTC_ERROR_INVALID_PARAM;
    }

    LOG_INFO("Building full connect params from %d discovered modules",
             discovery->module_count);

    /* Count input and output data sizes for IOCR calculation */
    uint16_t input_data_total = 0;
    uint16_t input_submod_count = 0;
    uint16_t output_data_total = 0;
    uint16_t output_submod_count = 0;

    for (int i = 0; i < discovery->module_count; i++) {
        const ar_discovered_module_t *m = &discovery->modules[i];

        /* Skip DAP submodules (slot 0) - they have no I/O data */
        if (m->slot == 0) {
            continue;
        }

        uint16_t data_size = get_module_data_size(m->module_ident);

        if (is_input_module(m->module_ident)) {
            input_data_total += data_size;
            input_submod_count++;
        } else {
            output_data_total += data_size;
            output_submod_count++;
        }
    }

    /* Update IOCR buffers on the AR to match discovered layout.
     * IOCR data_length = 40 + user_data + IOPS_count (1 per submodule) */
    if (ar->iocr_count >= 2) {
        uint16_t input_csdu = IOCR_MIN_C_SDU_LENGTH + input_data_total +
                              input_submod_count;
        if (input_csdu < IOCR_MIN_C_SDU_LENGTH) {
            input_csdu = IOCR_MIN_C_SDU_LENGTH;
        }
        ar->iocr[0].data_length = input_csdu;
        ar->iocr[0].user_data_length = input_data_total;
        ar->iocr[0].iodata_count = input_submod_count;

        uint16_t output_csdu = IOCR_MIN_C_SDU_LENGTH + output_data_total +
                               output_submod_count;
        if (output_csdu < IOCR_MIN_C_SDU_LENGTH) {
            output_csdu = IOCR_MIN_C_SDU_LENGTH;
        }
        ar->iocr[1].data_length = output_csdu;
        ar->iocr[1].user_data_length = output_data_total;
        ar->iocr[1].iodata_count = output_submod_count;
    }

    /* Store discovered modules as slot_info for full connect */
    ar->slot_count = 0;
    for (int i = 0; i < discovery->module_count && ar->slot_count < WTC_MAX_SLOTS; i++) {
        const ar_discovered_module_t *m = &discovery->modules[i];
        if (m->slot == 0) continue;  /* DAP handled separately in build_connect_params */

        ar_slot_info_t *info = &ar->slot_info[ar->slot_count];
        info->slot = m->slot;
        info->subslot = m->subslot;

        if (is_input_module(m->module_ident)) {
            info->type = SLOT_TYPE_SENSOR;
            /* Reverse-map module ident to measurement type */
            switch (m->module_ident) {
            case GSDML_MOD_PH:          info->measurement_type = MEASUREMENT_PH; break;
            case GSDML_MOD_TDS:         info->measurement_type = MEASUREMENT_TDS; break;
            case GSDML_MOD_TURBIDITY:   info->measurement_type = MEASUREMENT_TURBIDITY; break;
            case GSDML_MOD_TEMPERATURE: info->measurement_type = MEASUREMENT_TEMPERATURE; break;
            case GSDML_MOD_FLOW:        info->measurement_type = MEASUREMENT_FLOW_RATE; break;
            case GSDML_MOD_LEVEL:       info->measurement_type = MEASUREMENT_LEVEL; break;
            default:                    info->measurement_type = MEASUREMENT_CUSTOM; break;
            }
        } else {
            info->type = SLOT_TYPE_ACTUATOR;
            switch (m->module_ident) {
            case GSDML_MOD_PUMP:  info->actuator_type = ACTUATOR_PUMP; break;
            case GSDML_MOD_VALVE: info->actuator_type = ACTUATOR_VALVE; break;
            default:              info->actuator_type = ACTUATOR_RELAY; break;
            }
        }

        ar->slot_count++;
    }

    LOG_INFO("Full connect params: %d slots, input_data=%u output_data=%u",
             ar->slot_count, input_data_total, output_data_total);

    return WTC_OK;
}

wtc_result_t ar_connect_with_discovery(ar_manager_t *manager,
                                        profinet_ar_t *ar) {
    if (!manager || !ar) {
        return WTC_ERROR_INVALID_PARAM;
    }

    LOG_INFO("=== Starting Discovery Pipeline for %s ===",
             ar->device_station_name);

    wtc_result_t res;
    ar_module_discovery_t discovery;
    bool need_profinet_discovery = true;

    /* Phase 5 shortcut: Check GSDML cache first.
     * If cached GSDML exists for this station, skip DAP-only connect
     * and Record Read (Phases 2-3) entirely. */
    if (gsdml_cache_exists(ar->device_station_name)) {
        LOG_INFO("GSDML cache found for %s, skipping Phases 2-3",
                 ar->device_station_name);

        res = gsdml_cache_load_modules(ar->device_station_name, &discovery);
        if (res == WTC_OK && discovery.module_count > 0) {
            need_profinet_discovery = false;
            LOG_INFO("Loaded %d modules from cached GSDML",
                     discovery.module_count);
        } else {
            LOG_WARN("GSDML cache load failed, falling back to PROFINET discovery");
        }
    }

    /* Phases 2-3: PROFINET-based module discovery */
    if (need_profinet_discovery) {
        /* Phase 2: DAP-only connect */
        res = ar_send_dap_connect_request(manager, ar);
        if (res != WTC_OK) {
            LOG_ERROR("Phase 2 (DAP connect) failed for %s",
                      ar->device_station_name);

            /* Phase 6 fallback: try HTTP /slots if PROFINET fails */
            LOG_INFO("Attempting Phase 6 HTTP fallback for %s",
                     ar->device_station_name);

            /* Convert device_ip (host order uint32) to string */
            char ip_str[16];
            snprintf(ip_str, sizeof(ip_str), "%u.%u.%u.%u",
                     (ar->device_ip >> 24) & 0xFF,
                     (ar->device_ip >> 16) & 0xFF,
                     (ar->device_ip >> 8) & 0xFF,
                     ar->device_ip & 0xFF);

            res = gsdml_fetch_slots_http(ip_str, &discovery);
            if (res != WTC_OK) {
                LOG_ERROR("HTTP fallback also failed for %s",
                          ar->device_station_name);
                return WTC_ERROR_CONNECTION_FAILED;
            }
            /* HTTP fallback succeeded — skip to Phase 4 */
            need_profinet_discovery = false;
        }

        if (need_profinet_discovery) {
            /* Phase 2b: ParameterEnd to enable acyclic services (Record Read).
             * Per IEC 61158-6-10, Record Read requires AR parameterization
             * to be complete before acyclic services are available. */
            LOG_DEBUG("Sending ParameterEnd for DAP-only AR before Record Read");
            res = ar_send_parameter_end(manager, ar);
            if (res != WTC_OK) {
                LOG_ERROR("Phase 2b (ParameterEnd) failed for %s",
                          ar->device_station_name);
                ar_send_release_request(manager, ar);
                return res;
            }

            /* Phase 3: Record Read 0xF844 */
            res = ar_read_real_identification(manager, ar, &discovery);
            if (res != WTC_OK) {
                LOG_ERROR("Phase 3 (Record Read) failed for %s",
                          ar->device_station_name);
                ar_send_release_request(manager, ar);
                return res;
            }

            /* Release DAP-only AR before full connect */
            LOG_INFO("Releasing DAP-only AR for %s before full connect",
                     ar->device_station_name);
            ar_send_release_request(manager, ar);

            /* Brief pause for device to clean up the old AR */
            struct timespec ts = {0, 100000000}; /* 100ms */
            nanosleep(&ts, NULL);
        }
    }

    /* Phase 4: Build full params from discovered modules */
    res = ar_build_full_connect_params(manager, ar, &discovery);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to build full connect params for %s",
                  ar->device_station_name);
        return res;
    }

    /* Phase 4: Full connect with discovered configuration */
    LOG_INFO("=== Phase 4: Full Connect to %s with %d discovered modules ===",
             ar->device_station_name, discovery.module_count);

    /* Reset AR state for full connect */
    ar->state = AR_STATE_INIT;
    res = ar_send_connect_request(manager, ar);
    if (res != WTC_OK) {
        LOG_ERROR("Phase 4 (full connect) failed for %s",
                  ar->device_station_name);
        return res;
    }

    /* Phase 5: Background GSDML cache fetch (if not already cached) */
    if (!discovery.from_cache) {
        char ip_str[16];
        snprintf(ip_str, sizeof(ip_str), "%u.%u.%u.%u",
                 (ar->device_ip >> 24) & 0xFF,
                 (ar->device_ip >> 16) & 0xFF,
                 (ar->device_ip >> 8) & 0xFF,
                 ar->device_ip & 0xFF);

        wtc_result_t cache_res = gsdml_cache_fetch(ip_str,
                                                     ar->device_station_name);
        if (cache_res != WTC_OK) {
            LOG_DEBUG("GSDML cache fetch failed (non-critical) for %s",
                      ar->device_station_name);
        }
    }

    LOG_INFO("=== Discovery Pipeline COMPLETE for %s ===",
             ar->device_station_name);
    return WTC_OK;
}
