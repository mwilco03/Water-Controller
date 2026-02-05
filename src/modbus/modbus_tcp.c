/*
 * Water Treatment Controller - Modbus TCP Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "modbus_tcp.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <pthread.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <fcntl.h>

#define LOG_TAG "MODBUS_TCP"

/* Client connection info */
typedef struct {
    int fd;
    char ip[64];
    uint64_t last_activity_ms;
    bool active;
} tcp_client_t;

/* Modbus TCP context */
struct modbus_tcp {
    modbus_tcp_config_t config;
    int server_fd;
    int client_fd;
    bool running;
    pthread_t server_thread;
    pthread_mutex_t lock;

    tcp_client_t clients[MODBUS_TCP_MAX_CONNECTIONS];
    int client_count;

    uint16_t transaction_id;
    modbus_stats_t stats;
};

/* Set socket non-blocking */
static int set_nonblocking(int fd) {
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags < 0) return -1;
    return fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

/* Set socket options for Modbus */
static void configure_socket(int fd) {
    int flag = 1;
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &flag, sizeof(flag));

    struct timeval tv;
    tv.tv_sec = 5;
    tv.tv_usec = 0;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
}

/* Send TCP frame */
static int tcp_send_frame(int fd, uint8_t unit_id, uint16_t trans_id,
                           const modbus_pdu_t *pdu) {
    uint8_t buffer[MODBUS_TCP_MAX_ADU_LEN];
    uint16_t length = 1 + 1 + pdu->data_len; /* unit_id + fc + data */

    /* Build MBAP header */
    modbus_set_uint16_be(&buffer[0], trans_id);
    modbus_set_uint16_be(&buffer[2], 0); /* Protocol ID = 0 for Modbus */
    modbus_set_uint16_be(&buffer[4], length);
    buffer[6] = unit_id;
    buffer[7] = pdu->function_code;
    memcpy(&buffer[8], pdu->data, pdu->data_len);

    int total_len = MODBUS_TCP_HEADER_LEN + 1 + pdu->data_len;
    int sent = send(fd, buffer, total_len, 0);

    return (sent == total_len) ? 0 : -1;
}

/* Receive TCP frame */
static int tcp_recv_frame(int fd, uint8_t *unit_id, uint16_t *trans_id,
                           modbus_pdu_t *pdu, uint32_t timeout_ms) {
    uint8_t buffer[MODBUS_TCP_MAX_ADU_LEN];

    /* Set receive timeout */
    struct timeval tv;
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    /* Receive MBAP header */
    int received = recv(fd, buffer, MODBUS_TCP_HEADER_LEN, MSG_WAITALL);
    if (received != MODBUS_TCP_HEADER_LEN) {
        return -1;
    }

    /* Parse header */
    *trans_id = modbus_get_uint16_be(&buffer[0]);
    uint16_t protocol_id = modbus_get_uint16_be(&buffer[2]);
    uint16_t length = modbus_get_uint16_be(&buffer[4]);
    *unit_id = buffer[6];

    if (protocol_id != 0 || length < 2 || length > MODBUS_MAX_PDU_LEN + 1) {
        return -1;
    }

    /* Receive PDU */
    int pdu_len = length - 1; /* Subtract unit_id */
    received = recv(fd, &buffer[MODBUS_TCP_HEADER_LEN], pdu_len, MSG_WAITALL);
    if (received != pdu_len) {
        return -1;
    }

    pdu->function_code = buffer[MODBUS_TCP_HEADER_LEN];
    pdu->data_len = pdu_len - 1;
    if (pdu->data_len > 0) {
        memcpy(pdu->data, &buffer[MODBUS_TCP_HEADER_LEN + 1], pdu->data_len);
    }

    return 0;
}

/* Handle client request (server mode) */
static void handle_client_request(modbus_tcp_t *ctx, int client_fd) {
    uint8_t unit_id;
    uint16_t trans_id;
    modbus_pdu_t request, response;

    if (tcp_recv_frame(client_fd, &unit_id, &trans_id, &request,
                       ctx->config.timeout_ms) < 0) {
        return;
    }

    pthread_mutex_lock(&ctx->lock);
    ctx->stats.requests_received++;
    pthread_mutex_unlock(&ctx->lock);

    memset(&response, 0, sizeof(response));

    /* Call request handler */
    modbus_exception_t ex = MODBUS_EX_SLAVE_DEVICE_FAILURE;
    if (ctx->config.request_handler) {
        ex = ctx->config.request_handler(ctx, unit_id, &request, &response,
                                          ctx->config.user_data);
    }

    if (ex != MODBUS_EX_NONE) {
        /* Send exception response */
        response.function_code = request.function_code | 0x80;
        response.data[0] = ex;
        response.data_len = 1;

        pthread_mutex_lock(&ctx->lock);
        ctx->stats.exceptions++;
        pthread_mutex_unlock(&ctx->lock);
    }

    if (tcp_send_frame(client_fd, unit_id, trans_id, &response) == 0) {
        pthread_mutex_lock(&ctx->lock);
        ctx->stats.responses_sent++;
        pthread_mutex_unlock(&ctx->lock);
    }
}

/* Server thread */
static void *server_thread_func(void *arg) {
    modbus_tcp_t *ctx = (modbus_tcp_t *)arg;

    LOG_INFO(LOG_TAG, "Server thread started on port %d", ctx->config.port);

    while (ctx->running) {
        fd_set read_fds;
        FD_ZERO(&read_fds);
        FD_SET(ctx->server_fd, &read_fds);

        int max_fd = ctx->server_fd;

        /* Add client sockets */
        pthread_mutex_lock(&ctx->lock);
        for (int i = 0; i < MODBUS_TCP_MAX_CONNECTIONS; i++) {
            if (ctx->clients[i].active) {
                FD_SET(ctx->clients[i].fd, &read_fds);
                if (ctx->clients[i].fd > max_fd) {
                    max_fd = ctx->clients[i].fd;
                }
            }
        }
        pthread_mutex_unlock(&ctx->lock);

        struct timeval tv = { .tv_sec = 1, .tv_usec = 0 };
        int ready = select(max_fd + 1, &read_fds, NULL, NULL, &tv);

        if (ready < 0) {
            if (errno == EINTR) continue;
            break;
        }

        if (ready == 0) continue;

        /* Check for new connections */
        if (FD_ISSET(ctx->server_fd, &read_fds)) {
            struct sockaddr_in client_addr;
            socklen_t addr_len = sizeof(client_addr);
            int client_fd = accept(ctx->server_fd, (struct sockaddr *)&client_addr,
                                   &addr_len);

            if (client_fd >= 0) {
                char client_ip[64];
                inet_ntop(AF_INET, &client_addr.sin_addr, client_ip, sizeof(client_ip));

                configure_socket(client_fd);

                pthread_mutex_lock(&ctx->lock);

                /* Find free slot */
                int slot = -1;
                for (int i = 0; i < MODBUS_TCP_MAX_CONNECTIONS; i++) {
                    if (!ctx->clients[i].active) {
                        slot = i;
                        break;
                    }
                }

                if (slot >= 0 && ctx->client_count < (int)ctx->config.max_connections) {
                    ctx->clients[slot].fd = client_fd;
                    snprintf(ctx->clients[slot].ip, sizeof(ctx->clients[slot].ip), "%s", client_ip);
                    ctx->clients[slot].last_activity_ms = time_get_ms();
                    ctx->clients[slot].active = true;
                    ctx->client_count++;

                    LOG_INFO(LOG_TAG, "Client connected: %s (slot %d)", client_ip, slot);

                    if (ctx->config.on_connect) {
                        ctx->config.on_connect(ctx, client_fd, client_ip,
                                               ctx->config.user_data);
                    }
                } else {
                    close(client_fd);
                    LOG_WARN(LOG_TAG, "Connection rejected: max clients reached");
                }

                pthread_mutex_unlock(&ctx->lock);
            }
        }

        /* Handle client data */
        pthread_mutex_lock(&ctx->lock);
        for (int i = 0; i < MODBUS_TCP_MAX_CONNECTIONS; i++) {
            if (ctx->clients[i].active && FD_ISSET(ctx->clients[i].fd, &read_fds)) {
                int client_fd = ctx->clients[i].fd;
                pthread_mutex_unlock(&ctx->lock);

                /* Check for disconnect */
                char peek;
                int ret = recv(client_fd, &peek, 1, MSG_PEEK | MSG_DONTWAIT);
                if (ret == 0 || (ret < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) {
                    /* Client disconnected */
                    pthread_mutex_lock(&ctx->lock);
                    ctx->clients[i].active = false;
                    ctx->client_count--;

                    LOG_INFO(LOG_TAG, "Client disconnected: %s", ctx->clients[i].ip);

                    if (ctx->config.on_disconnect) {
                        ctx->config.on_disconnect(ctx, client_fd, ctx->config.user_data);
                    }

                    close(client_fd);
                    pthread_mutex_unlock(&ctx->lock);
                } else {
                    /* Handle request */
                    handle_client_request(ctx, client_fd);

                    pthread_mutex_lock(&ctx->lock);
                    ctx->clients[i].last_activity_ms = time_get_ms();
                }

                pthread_mutex_lock(&ctx->lock);
            }
        }
        pthread_mutex_unlock(&ctx->lock);
    }

    LOG_INFO(LOG_TAG, "Server thread stopped");
    return NULL;
}

wtc_result_t modbus_tcp_init(modbus_tcp_t **ctx, const modbus_tcp_config_t *config) {
    if (!ctx || !config) return WTC_ERROR_INVALID_PARAM;

    modbus_tcp_t *tcp = calloc(1, sizeof(modbus_tcp_t));
    if (!tcp) return WTC_ERROR_NO_MEMORY;

    memcpy(&tcp->config, config, sizeof(modbus_tcp_config_t));
    tcp->server_fd = -1;
    tcp->client_fd = -1;

    if (tcp->config.max_connections == 0 ||
        tcp->config.max_connections > MODBUS_TCP_MAX_CONNECTIONS) {
        tcp->config.max_connections = MODBUS_TCP_MAX_CONNECTIONS;
    }

    if (tcp->config.timeout_ms == 0) {
        tcp->config.timeout_ms = 5000;
    }

    pthread_mutex_init(&tcp->lock, NULL);

    *ctx = tcp;
    LOG_INFO(LOG_TAG, "Modbus TCP initialized (role=%s)",
             config->role == MODBUS_ROLE_SERVER ? "server" : "client");
    return WTC_OK;
}

void modbus_tcp_cleanup(modbus_tcp_t *ctx) {
    if (!ctx) return;

    modbus_tcp_server_stop(ctx);
    modbus_tcp_disconnect(ctx);

    pthread_mutex_destroy(&ctx->lock);
    free(ctx);

    LOG_INFO(LOG_TAG, "Modbus TCP cleaned up");
}

wtc_result_t modbus_tcp_server_start(modbus_tcp_t *ctx) {
    if (!ctx || ctx->config.role != MODBUS_ROLE_SERVER) {
        return WTC_ERROR_INVALID_PARAM;
    }

    /* Create socket */
    ctx->server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (ctx->server_fd < 0) {
        LOG_ERROR(LOG_TAG, "Failed to create socket: %s", strerror(errno));
        return WTC_ERROR_IO;
    }

    int opt = 1;
    setsockopt(ctx->server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(ctx->config.port);

    if (ctx->config.bind_address[0]) {
        inet_pton(AF_INET, ctx->config.bind_address, &addr.sin_addr);
    } else {
        addr.sin_addr.s_addr = INADDR_ANY;
    }

    if (bind(ctx->server_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        LOG_ERROR(LOG_TAG, "Failed to bind: %s", strerror(errno));
        close(ctx->server_fd);
        ctx->server_fd = -1;
        return WTC_ERROR_IO;
    }

    if (listen(ctx->server_fd, 10) < 0) {
        LOG_ERROR(LOG_TAG, "Failed to listen: %s", strerror(errno));
        close(ctx->server_fd);
        ctx->server_fd = -1;
        return WTC_ERROR_IO;
    }

    set_nonblocking(ctx->server_fd);

    ctx->running = true;
    if (pthread_create(&ctx->server_thread, NULL, server_thread_func, ctx) != 0) {
        LOG_ERROR(LOG_TAG, "Failed to create server thread");
        close(ctx->server_fd);
        ctx->server_fd = -1;
        ctx->running = false;
        return WTC_ERROR_INTERNAL;
    }

    LOG_INFO(LOG_TAG, "Server started on port %d", ctx->config.port);
    return WTC_OK;
}

wtc_result_t modbus_tcp_server_stop(modbus_tcp_t *ctx) {
    if (!ctx || !ctx->running) return WTC_OK;

    ctx->running = false;
    pthread_join(ctx->server_thread, NULL);

    /* Close all client connections */
    pthread_mutex_lock(&ctx->lock);
    for (int i = 0; i < MODBUS_TCP_MAX_CONNECTIONS; i++) {
        if (ctx->clients[i].active) {
            close(ctx->clients[i].fd);
            ctx->clients[i].active = false;
        }
    }
    ctx->client_count = 0;
    pthread_mutex_unlock(&ctx->lock);

    if (ctx->server_fd >= 0) {
        close(ctx->server_fd);
        ctx->server_fd = -1;
    }

    LOG_INFO(LOG_TAG, "Server stopped");
    return WTC_OK;
}

wtc_result_t modbus_tcp_connect(modbus_tcp_t *ctx, const char *host, uint16_t port) {
    if (!ctx || !host || ctx->config.role != MODBUS_ROLE_CLIENT) {
        return WTC_ERROR_INVALID_PARAM;
    }

    modbus_tcp_disconnect(ctx);

    ctx->client_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (ctx->client_fd < 0) {
        LOG_ERROR(LOG_TAG, "Failed to create socket");
        return WTC_ERROR_IO;
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);

    if (inet_pton(AF_INET, host, &addr.sin_addr) <= 0) {
        LOG_ERROR(LOG_TAG, "Invalid address: %s", host);
        close(ctx->client_fd);
        ctx->client_fd = -1;
        return WTC_ERROR_INVALID_PARAM;
    }

    /* MB-H1 fix: Non-blocking connect with configurable timeout */
    set_nonblocking(ctx->client_fd);

    int res = connect(ctx->client_fd, (struct sockaddr *)&addr, sizeof(addr));
    if (res < 0 && errno != EINPROGRESS) {
        LOG_ERROR(LOG_TAG, "Failed to connect to %s:%d: %s", host, port, strerror(errno));
        close(ctx->client_fd);
        ctx->client_fd = -1;
        return WTC_ERROR_IO;
    }

    if (res < 0) {
        /* Connection in progress - wait with timeout */
        fd_set write_fds, error_fds;
        FD_ZERO(&write_fds);
        FD_ZERO(&error_fds);
        FD_SET(ctx->client_fd, &write_fds);
        FD_SET(ctx->client_fd, &error_fds);

        struct timeval tv;
        uint32_t timeout_ms = ctx->config.timeout_ms > 0 ? ctx->config.timeout_ms : 5000;
        tv.tv_sec = timeout_ms / 1000;
        tv.tv_usec = (timeout_ms % 1000) * 1000;

        int sel_res = select(ctx->client_fd + 1, NULL, &write_fds, &error_fds, &tv);

        if (sel_res <= 0) {
            LOG_ERROR(LOG_TAG, "Connection timeout to %s:%d", host, port);
            close(ctx->client_fd);
            ctx->client_fd = -1;
            return WTC_ERROR_TIMEOUT;
        }

        if (FD_ISSET(ctx->client_fd, &error_fds)) {
            int error = 0;
            socklen_t len = sizeof(error);
            getsockopt(ctx->client_fd, SOL_SOCKET, SO_ERROR, &error, &len);
            LOG_ERROR(LOG_TAG, "Connection error to %s:%d: %s", host, port, strerror(error));
            close(ctx->client_fd);
            ctx->client_fd = -1;
            return WTC_ERROR_IO;
        }

        /* Check if connection succeeded */
        int error = 0;
        socklen_t len = sizeof(error);
        if (getsockopt(ctx->client_fd, SOL_SOCKET, SO_ERROR, &error, &len) < 0 || error != 0) {
            LOG_ERROR(LOG_TAG, "Connection failed to %s:%d: %s", host, port, strerror(error));
            close(ctx->client_fd);
            ctx->client_fd = -1;
            return WTC_ERROR_IO;
        }
    }

    /* Restore blocking mode and configure socket */
    int flags = fcntl(ctx->client_fd, F_GETFL, 0);
    if (flags >= 0) {
        fcntl(ctx->client_fd, F_SETFL, flags & ~O_NONBLOCK);
    }
    configure_socket(ctx->client_fd);

    LOG_INFO(LOG_TAG, "Connected to %s:%d", host, port);
    return WTC_OK;
}

void modbus_tcp_disconnect(modbus_tcp_t *ctx) {
    if (!ctx || ctx->client_fd < 0) return;

    close(ctx->client_fd);
    ctx->client_fd = -1;
    LOG_INFO(LOG_TAG, "Disconnected");
}

bool modbus_tcp_is_connected(modbus_tcp_t *ctx) {
    return ctx && ctx->client_fd >= 0;
}

wtc_result_t modbus_tcp_transact(modbus_tcp_t *ctx,
                                  uint8_t unit_id,
                                  const modbus_pdu_t *request,
                                  modbus_pdu_t *response) {
    if (!ctx || !request || !response || ctx->client_fd < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&ctx->lock);
    uint16_t trans_id = ++ctx->transaction_id;
    pthread_mutex_unlock(&ctx->lock);

    if (tcp_send_frame(ctx->client_fd, unit_id, trans_id, request) < 0) {
        pthread_mutex_lock(&ctx->lock);
        ctx->stats.timeouts++;
        pthread_mutex_unlock(&ctx->lock);
        return WTC_ERROR_IO;
    }

    pthread_mutex_lock(&ctx->lock);
    ctx->stats.requests_sent++;
    pthread_mutex_unlock(&ctx->lock);

    uint8_t resp_unit_id;
    uint16_t resp_trans_id;

    if (tcp_recv_frame(ctx->client_fd, &resp_unit_id, &resp_trans_id,
                       response, ctx->config.timeout_ms) < 0) {
        pthread_mutex_lock(&ctx->lock);
        ctx->stats.timeouts++;
        pthread_mutex_unlock(&ctx->lock);
        return WTC_ERROR_TIMEOUT;
    }

    if (resp_trans_id != trans_id) {
        return WTC_ERROR_PROTOCOL;
    }

    pthread_mutex_lock(&ctx->lock);
    ctx->stats.responses_received++;
    if (modbus_is_exception(response)) {
        ctx->stats.exceptions++;
    }
    pthread_mutex_unlock(&ctx->lock);

    return WTC_OK;
}

wtc_result_t modbus_tcp_read_holding_registers(modbus_tcp_t *ctx, uint8_t unit_id,
                                                uint16_t start_addr, uint16_t quantity,
                                                uint16_t *values) {
    if (!ctx || !values || quantity > MODBUS_MAX_READ_REGISTERS) {
        return WTC_ERROR_INVALID_PARAM;
    }

    modbus_pdu_t request, response;
    modbus_build_read_request(&request, MODBUS_FC_READ_HOLDING_REGISTERS,
                              start_addr, quantity);

    wtc_result_t res = modbus_tcp_transact(ctx, unit_id, &request, &response);
    if (res != WTC_OK) return res;

    if (modbus_is_exception(&response)) {
        return WTC_ERROR_PROTOCOL;
    }

    uint8_t byte_count = response.data[0];
    if (byte_count != quantity * 2) {
        return WTC_ERROR_PROTOCOL;
    }

    for (uint16_t i = 0; i < quantity; i++) {
        values[i] = modbus_get_uint16_be(&response.data[1 + i * 2]);
    }

    return WTC_OK;
}

wtc_result_t modbus_tcp_read_input_registers(modbus_tcp_t *ctx, uint8_t unit_id,
                                              uint16_t start_addr, uint16_t quantity,
                                              uint16_t *values) {
    if (!ctx || !values || quantity > MODBUS_MAX_READ_REGISTERS) {
        return WTC_ERROR_INVALID_PARAM;
    }

    modbus_pdu_t request, response;
    modbus_build_read_request(&request, MODBUS_FC_READ_INPUT_REGISTERS,
                              start_addr, quantity);

    wtc_result_t res = modbus_tcp_transact(ctx, unit_id, &request, &response);
    if (res != WTC_OK) return res;

    if (modbus_is_exception(&response)) {
        return WTC_ERROR_PROTOCOL;
    }

    uint8_t byte_count = response.data[0];
    if (byte_count != quantity * 2) {
        return WTC_ERROR_PROTOCOL;
    }

    for (uint16_t i = 0; i < quantity; i++) {
        values[i] = modbus_get_uint16_be(&response.data[1 + i * 2]);
    }

    return WTC_OK;
}

wtc_result_t modbus_tcp_read_coils(modbus_tcp_t *ctx, uint8_t unit_id,
                                    uint16_t start_addr, uint16_t quantity,
                                    uint8_t *values) {
    if (!ctx || !values || quantity > MODBUS_MAX_READ_BITS) {
        return WTC_ERROR_INVALID_PARAM;
    }

    modbus_pdu_t request, response;
    modbus_build_read_request(&request, MODBUS_FC_READ_COILS, start_addr, quantity);

    wtc_result_t res = modbus_tcp_transact(ctx, unit_id, &request, &response);
    if (res != WTC_OK) return res;

    if (modbus_is_exception(&response)) {
        return WTC_ERROR_PROTOCOL;
    }

    uint8_t byte_count = response.data[0];
    memcpy(values, &response.data[1], byte_count);

    return WTC_OK;
}

wtc_result_t modbus_tcp_read_discrete_inputs(modbus_tcp_t *ctx, uint8_t unit_id,
                                              uint16_t start_addr, uint16_t quantity,
                                              uint8_t *values) {
    if (!ctx || !values || quantity > MODBUS_MAX_READ_BITS) {
        return WTC_ERROR_INVALID_PARAM;
    }

    modbus_pdu_t request, response;
    modbus_build_read_request(&request, MODBUS_FC_READ_DISCRETE_INPUTS,
                              start_addr, quantity);

    wtc_result_t res = modbus_tcp_transact(ctx, unit_id, &request, &response);
    if (res != WTC_OK) return res;

    if (modbus_is_exception(&response)) {
        return WTC_ERROR_PROTOCOL;
    }

    uint8_t byte_count = response.data[0];
    memcpy(values, &response.data[1], byte_count);

    return WTC_OK;
}

wtc_result_t modbus_tcp_write_single_coil(modbus_tcp_t *ctx, uint8_t unit_id,
                                           uint16_t addr, bool value) {
    if (!ctx) return WTC_ERROR_INVALID_PARAM;

    modbus_pdu_t request, response;
    modbus_build_write_single_coil(&request, addr, value);

    return modbus_tcp_transact(ctx, unit_id, &request, &response);
}

wtc_result_t modbus_tcp_write_single_register(modbus_tcp_t *ctx, uint8_t unit_id,
                                               uint16_t addr, uint16_t value) {
    if (!ctx) return WTC_ERROR_INVALID_PARAM;

    modbus_pdu_t request, response;
    modbus_build_write_single_register(&request, addr, value);

    return modbus_tcp_transact(ctx, unit_id, &request, &response);
}

wtc_result_t modbus_tcp_write_multiple_coils(modbus_tcp_t *ctx, uint8_t unit_id,
                                              uint16_t start_addr, uint16_t quantity,
                                              const uint8_t *values) {
    if (!ctx || !values) return WTC_ERROR_INVALID_PARAM;

    modbus_pdu_t request, response;
    modbus_build_write_multiple_coils(&request, start_addr, quantity, values);

    return modbus_tcp_transact(ctx, unit_id, &request, &response);
}

wtc_result_t modbus_tcp_write_multiple_registers(modbus_tcp_t *ctx, uint8_t unit_id,
                                                  uint16_t start_addr, uint16_t quantity,
                                                  const uint16_t *values) {
    if (!ctx || !values) return WTC_ERROR_INVALID_PARAM;

    modbus_pdu_t request, response;
    modbus_build_write_multiple_registers(&request, start_addr, quantity, values);

    return modbus_tcp_transact(ctx, unit_id, &request, &response);
}

wtc_result_t modbus_tcp_get_stats(modbus_tcp_t *ctx, modbus_stats_t *stats) {
    if (!ctx || !stats) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&ctx->lock);
    memcpy(stats, &ctx->stats, sizeof(modbus_stats_t));
    pthread_mutex_unlock(&ctx->lock);

    return WTC_OK;
}

int modbus_tcp_get_connection_count(modbus_tcp_t *ctx) {
    if (!ctx) return 0;

    pthread_mutex_lock(&ctx->lock);
    int count = ctx->client_count;
    pthread_mutex_unlock(&ctx->lock);

    return count;
}
