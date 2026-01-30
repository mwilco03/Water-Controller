/*
 * Water Treatment Controller - AR Manager Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "ar_manager.h"
#include "cyclic_exchange.h"
#include "profinet_frame.h"
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

/* Number of strategies to try per ar_send_connect_request call.
 * Each attempt may block for up to RPC_CONNECT_TIMEOUT_MS (5s),
 * so total blocking time per call is bounded at
 * AR_STRATEGIES_PER_CALL * (5s + 0.5s inter-attempt delay). */
#define AR_STRATEGIES_PER_CALL  RPC_MAX_STRATEGIES

/* Delay in microseconds between strategy attempts within one call */
#define AR_INTER_ATTEMPT_DELAY_US  500000  /* 500ms */

/* AR manager structure */
struct ar_manager {
    int socket_fd;
    uint8_t controller_mac[6];
    uint32_t controller_ip;
    int if_index;

    profinet_ar_t *ars[MAX_ARS];
    int ar_count;

    uint16_t session_key_counter;
    pthread_mutex_t lock;

    /* RPC context for PROFINET connection establishment */
    rpc_context_t rpc_ctx;
    bool rpc_initialized;

    /* Controller UUID (generated once at startup) */
    uint8_t controller_uuid[16];

    /* Connection strategy state — persists across ABORT recovery cycles
     * so that if a format worked before, we try it first on reconnection. */
    rpc_strategy_state_t strategy_state;

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

    /* Generate controller UUID (used in Connect Request) */
    rpc_generate_uuid(mgr->controller_uuid);

    /* Initialize connection strategy state */
    rpc_strategy_init(&mgr->strategy_state);
    LOG_INFO("RPC strategy system initialized with %d strategies",
             mgr->strategy_state.total_strategies);

    *manager = mgr;
    LOG_DEBUG("AR manager initialized");
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

                    /* Find AR by session key and/or AR UUID */
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
                                /* Transition to RUN state */
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
                } else {
                    LOG_DEBUG("Received incoming RPC with command %u (not ApplicationReady)",
                              incoming_req.control_command);
                }
            }
        }
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
            /* Waiting for connect response - check timeout (PN-C3 fix) */
            if (now_ms - ar->last_activity_ms > AR_CONNECT_TIMEOUT_MS) {
                LOG_WARN("AR %s connect request timeout after %d ms",
                         ar->device_station_name, AR_CONNECT_TIMEOUT_MS);
                ar->state = AR_STATE_ABORT;
                ar->last_activity_ms = now_ms;
            }
            break;

        case AR_STATE_CONNECT_CNF:
            /* Connection confirmed, move to parameter server phase */
            LOG_DEBUG("AR %s connection confirmed, entering PRMSRV phase",
                      ar->device_station_name);
            ar->state = AR_STATE_PRMSRV;
            ar->last_activity_ms = now_ms;
            break;

        case AR_STATE_PRMSRV:
            /* Parameter server phase - send ParameterEnd RPC */
            LOG_DEBUG("AR %s in PRMSRV, sending ParameterEnd",
                      ar->device_station_name);
            if (ar_send_parameter_end(manager, ar) != WTC_OK) {
                LOG_ERROR("AR %s ParameterEnd failed, aborting",
                          ar->device_station_name);
                /* State already set to ABORT by ar_send_parameter_end */
            }
            /* ar_send_parameter_end sets state to READY on success */
            break;

        case AR_STATE_READY:
            /*
             * Waiting for ApplicationReady from device.
             * Per IEC 61158-6-10: After PrmEnd, the DEVICE sends ApplicationReady
             * to the CONTROLLER, not the other way around.
             * The RPC polling above handles incoming ApplicationReady.
             */
            if (now_ms - ar->last_activity_ms > AR_APP_READY_TIMEOUT_MS) {
                LOG_ERROR("AR %s timeout waiting for ApplicationReady from device",
                          ar->device_station_name);
                ar->state = AR_STATE_ABORT;
                ar->last_activity_ms = now_ms;
            }
            break;

        case AR_STATE_RUN:
            /* Normal operation - cyclic data exchange */
            break;

        case AR_STATE_CLOSE:
            /* AR is closing - allow graceful shutdown */
            break;

        case AR_STATE_ABORT: {
            /*
             * PROFINET Communication Resiliency: auto-reconnect with
             * exponential backoff.  Strategy state is preserved across
             * ABORT cycles so known-working formats are tried first.
             *
             * Backoff: 5s base, doubles per strategy cycle, max 60s.
             * After backoff, directly attempts reconnection (blocking).
             */
            uint32_t backoff_ms = 5000;
            int cycles = manager->strategy_state.cycle_count;
            if (cycles > 0) {
                /* 5s, 10s, 20s, 40s, capped at 60s */
                int shift = cycles < 4 ? cycles : 3;
                backoff_ms = 5000U << shift;
                if (backoff_ms > 60000) {
                    backoff_ms = 60000;
                }
            }

            if (now_ms - ar->last_activity_ms > backoff_ms) {
                LOG_INFO("AR %s: ABORT recovery after %u ms backoff "
                         "(attempts: %d, cycles: %d, last_success: %d)",
                         ar->device_station_name, backoff_ms,
                         manager->strategy_state.attempt_count,
                         manager->strategy_state.cycle_count,
                         manager->strategy_state.last_success_index);

                /* Directly attempt reconnection — the strategy loop
                 * in ar_send_connect_request will try all formats. */
                ar_state_t old_state = ar->state;
                ar_send_connect_request(manager, ar);

                /* If connect succeeded, AR is now in CONNECT_CNF.
                 * If it failed, AR is back in ABORT with fresh timestamp.
                 * Either way, notify the state change. */
                if (ar->state != old_state) {
                    notify_state_change(manager, ar, old_state, ar->state);
                }
            }
            break;
        }
        }
    }

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
                                         manager->controller_ip);
    if (res != WTC_OK) {
        LOG_ERROR("Failed to initialize RPC context");
        return res;
    }

    manager->rpc_initialized = true;
    LOG_INFO("RPC context initialized for controller IP %08X",
             manager->controller_ip);
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
    strncpy(params->station_name, ar->device_station_name,
            sizeof(params->station_name) - 1);

    /* Controller info */
    memcpy(params->controller_mac, manager->controller_mac, 6);
    memcpy(params->controller_uuid, manager->controller_uuid, 16);
    params->controller_port = manager->rpc_ctx.controller_port;
    params->activity_timeout = 100;  /* 100 * 100ms = 10 seconds */

    /* IOCR configuration from AR */
    params->iocr_count = 0;
    for (int i = 0; i < ar->iocr_count && params->iocr_count < 4; i++) {
        params->iocr[params->iocr_count].type = ar->iocr[i].type;
        params->iocr[params->iocr_count].reference = (uint16_t)(i + 1);
        params->iocr[params->iocr_count].frame_id = ar->iocr[i].frame_id;
        params->iocr[params->iocr_count].data_length = ar->iocr[i].data_length;
        params->iocr[params->iocr_count].send_clock_factor = 32;  /* 1ms cycle */
        params->iocr[params->iocr_count].reduction_ratio = 32;    /* 32ms update */
        params->iocr[params->iocr_count].watchdog_factor = 3;     /* 3x reduction */
        params->iocr_count++;
    }

    /*
     * Expected configuration using GSDML-defined module identifiers.
     * Module identifiers must match the Water-Treat RTU GSDML exactly.
     */
    params->expected_count = 0;

    /* Add DAP slot 0 (Device Access Point - always present) */
    params->expected_config[params->expected_count].slot = 0;
    params->expected_config[params->expected_count].module_ident = GSDML_MOD_DAP;
    params->expected_config[params->expected_count].subslot = 1;
    params->expected_config[params->expected_count].submodule_ident = GSDML_SUBMOD_DAP;
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
    LOG_INFO("  Strategy state: index=%d, last_success=%d, "
             "total_attempts=%d, cycles=%d",
             manager->strategy_state.current_index,
             manager->strategy_state.last_success_index,
             manager->strategy_state.attempt_count,
             manager->strategy_state.cycle_count);

    /*
     * PROFINET Communication Resiliency: iterate through wire format
     * strategies until one succeeds or we exhaust the current set.
     *
     * Each strategy varies UUID encoding, NDR header, and/or slot
     * configuration.  On success the working strategy is remembered
     * so reconnections start with a known-good format.
     */
    const int max_attempts = AR_STRATEGIES_PER_CALL;

    for (int attempt = 0; attempt < max_attempts; attempt++) {
        const rpc_connect_strategy_t *strategy =
            rpc_strategy_current(&manager->strategy_state);

        manager->strategy_state.attempt_count++;
        manager->strategy_state.last_attempt_ms = time_get_ms();
        if (manager->strategy_state.first_attempt_ms == 0) {
            manager->strategy_state.first_attempt_ms =
                manager->strategy_state.last_attempt_ms;
        }

        LOG_INFO("  Attempt %d/%d: strategy [%d/%d] %s",
                 attempt + 1, max_attempts,
                 manager->strategy_state.current_index + 1,
                 manager->strategy_state.total_strategies,
                 strategy->description);

        /* Regenerate AR UUID and session key for each attempt to avoid
         * the device rejecting a retried UUID from a failed attempt. */
        rpc_generate_uuid((uint8_t *)ar->ar_uuid);
        ar->session_key = manager->session_key_counter++;

        /* Build full connect parameters */
        connect_request_params_t params;
        build_connect_params(manager, ar, &params);

        /* Attempt connect with this strategy */
        connect_response_t response;
        res = rpc_connect_with_strategy(&manager->rpc_ctx, ar->device_ip,
                                         &params, strategy, &response);

        if (res == WTC_OK && response.success) {
            /* === Strategy succeeded === */
            rpc_strategy_mark_success(&manager->strategy_state);

            /* Update AR with response data */
            memcpy(ar->device_mac, response.device_mac, 6);

            for (int i = 0; i < response.frame_id_count &&
                            i < ar->iocr_count; i++) {
                if (ar->iocr[i].frame_id !=
                    response.frame_ids[i].assigned) {
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

            LOG_INFO("=== CONNECT SUCCESS for %s (session_key=%u, "
                     "strategy=%s) ===",
                     ar->device_station_name, response.session_key,
                     strategy->description);
            return WTC_OK;
        }

        /* === Strategy failed === */
        LOG_WARN("  Attempt %d FAILED: error=%d, strategy=%s",
                 attempt + 1, res, strategy->description);

        rpc_strategy_advance(&manager->strategy_state);

        /* Brief pause between attempts to avoid flooding the RTU */
        if (attempt + 1 < max_attempts) {
            usleep(AR_INTER_ATTEMPT_DELAY_US);
        }
    }

    /* All strategies exhausted for this call */
    ar->state = AR_STATE_ABORT;
    ar->last_activity_ms = time_get_ms();

    LOG_ERROR("=== CONNECT FAILED for %s: all %d strategies exhausted "
              "(total attempts: %d, cycles: %d) ===",
              ar->device_station_name, max_attempts,
              manager->strategy_state.attempt_count,
              manager->strategy_state.cycle_count);
    LOG_INFO("  Will retry from ABORT state with exponential backoff. "
             "Strategy state preserved for next attempt.");

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
            ar_state_t old_state = ar->state;
            ar->state = AR_STATE_ABORT;
            notify_state_change(manager, ar, old_state, AR_STATE_ABORT);
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
