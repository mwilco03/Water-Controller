/*
 * Water Treatment Controller - Modbus RTU Implementation
 * Copyright (C) 2024
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "modbus_rtu.h"
#include "utils/logger.h"
#include "utils/time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <termios.h>
#include <sys/select.h>
#include <pthread.h>

#define LOG_TAG "MODBUS_RTU"

/* Modbus RTU context */
struct modbus_rtu {
    modbus_rtu_config_t config;
    int serial_fd;
    bool running;
    pthread_t server_thread;
    pthread_mutex_t lock;
    modbus_stats_t stats;
};

/* Convert baud rate to termios constant */
static speed_t get_baud_constant(uint32_t baud) {
    switch (baud) {
    case 1200:   return B1200;
    case 2400:   return B2400;
    case 4800:   return B4800;
    case 9600:   return B9600;
    case 19200:  return B19200;
    case 38400:  return B38400;
    case 57600:  return B57600;
    case 115200: return B115200;
    case 230400: return B230400;
    default:     return B9600;
    }
}

/* Calculate inter-frame delay in microseconds (3.5 character times) */
static uint32_t calc_inter_frame_delay(uint32_t baud) {
    /* Character time = (start + data + parity + stop) / baud
     * Assuming 11 bits per character (1+8+1+1)
     * 3.5 character times */
    uint32_t char_time_us = (11 * 1000000) / baud;
    uint32_t delay = char_time_us * 35 / 10;

    /* Minimum delay of 1750us for baud > 19200 */
    if (delay < 1750) delay = 1750;

    return delay;
}

/* Configure serial port */
static int configure_serial(int fd, const modbus_rtu_config_t *config) {
    struct termios tty;

    if (tcgetattr(fd, &tty) < 0) {
        return -1;
    }

    /* Set baud rate */
    speed_t baud = get_baud_constant(config->baud_rate);
    cfsetispeed(&tty, baud);
    cfsetospeed(&tty, baud);

    /* Raw mode */
    cfmakeraw(&tty);

    /* Data bits */
    tty.c_cflag &= ~CSIZE;
    if (config->data_bits == 7) {
        tty.c_cflag |= CS7;
    } else {
        tty.c_cflag |= CS8;
    }

    /* Parity */
    switch (config->parity) {
    case 'E':
        tty.c_cflag |= PARENB;
        tty.c_cflag &= ~PARODD;
        break;
    case 'O':
        tty.c_cflag |= PARENB;
        tty.c_cflag |= PARODD;
        break;
    default:
        tty.c_cflag &= ~PARENB;
        break;
    }

    /* Stop bits */
    if (config->stop_bits == 2) {
        tty.c_cflag |= CSTOPB;
    } else {
        tty.c_cflag &= ~CSTOPB;
    }

    /* Hardware flow control off */
    tty.c_cflag &= ~CRTSCTS;
    tty.c_cflag |= CLOCAL | CREAD;

    /* Software flow control off */
    tty.c_iflag &= ~(IXON | IXOFF | IXANY);

    /* Timeouts */
    tty.c_cc[VMIN] = 0;
    tty.c_cc[VTIME] = 1; /* 100ms timeout */

    if (tcsetattr(fd, TCSANOW, &tty) < 0) {
        return -1;
    }

    tcflush(fd, TCIOFLUSH);

    return 0;
}

/* Send RTU frame */
static int rtu_send_frame(modbus_rtu_t *ctx, uint8_t slave_addr,
                           const modbus_pdu_t *pdu) {
    uint8_t buffer[MODBUS_RTU_MAX_ADU_LEN];
    int len = 0;

    buffer[len++] = slave_addr;
    buffer[len++] = pdu->function_code;
    memcpy(&buffer[len], pdu->data, pdu->data_len);
    len += pdu->data_len;

    /* Append CRC */
    uint16_t crc = modbus_crc16(buffer, len);
    buffer[len++] = crc & 0xFF;        /* CRC low */
    buffer[len++] = (crc >> 8) & 0xFF; /* CRC high */

    /* Inter-frame delay before sending */
    usleep(ctx->config.inter_frame_delay_us);

    int written = write(ctx->serial_fd, buffer, len);
    if (written != len) {
        return -1;
    }

    tcdrain(ctx->serial_fd);

    pthread_mutex_lock(&ctx->lock);
    ctx->stats.bytes_sent += len;
    pthread_mutex_unlock(&ctx->lock);

    return 0;
}

/* Receive RTU frame */
static int rtu_recv_frame(modbus_rtu_t *ctx, uint8_t *slave_addr,
                           modbus_pdu_t *pdu, uint32_t timeout_ms) {
    uint8_t buffer[MODBUS_RTU_MAX_ADU_LEN];
    int len = 0;

    /* Read with timeout using select */
    uint64_t start_ms = time_get_ms();

    while (len < MODBUS_RTU_MAX_ADU_LEN) {
        fd_set read_fds;
        FD_ZERO(&read_fds);
        FD_SET(ctx->serial_fd, &read_fds);

        uint64_t elapsed = time_get_ms() - start_ms;
        if (elapsed >= timeout_ms) break;

        struct timeval tv;
        uint32_t remaining = timeout_ms - elapsed;
        tv.tv_sec = remaining / 1000;
        tv.tv_usec = (remaining % 1000) * 1000;

        int ready = select(ctx->serial_fd + 1, &read_fds, NULL, NULL, &tv);
        if (ready <= 0) break;

        int n = read(ctx->serial_fd, &buffer[len], MODBUS_RTU_MAX_ADU_LEN - len);
        if (n <= 0) break;

        len += n;

        /* Wait for inter-frame delay to detect end of frame */
        usleep(ctx->config.inter_frame_delay_us);

        /* Check if more data available */
        fd_set check_fds;
        FD_ZERO(&check_fds);
        FD_SET(ctx->serial_fd, &check_fds);
        tv.tv_sec = 0;
        tv.tv_usec = ctx->config.inter_frame_delay_us;

        if (select(ctx->serial_fd + 1, &check_fds, NULL, NULL, &tv) <= 0) {
            break; /* End of frame */
        }
    }

    if (len < 4) { /* Minimum: addr + fc + crc(2) */
        return -1;
    }

    pthread_mutex_lock(&ctx->lock);
    ctx->stats.bytes_received += len;
    pthread_mutex_unlock(&ctx->lock);

    /* Verify CRC */
    uint16_t received_crc = buffer[len - 2] | (buffer[len - 1] << 8);
    uint16_t calc_crc = modbus_crc16(buffer, len - 2);

    if (received_crc != calc_crc) {
        pthread_mutex_lock(&ctx->lock);
        ctx->stats.crc_errors++;
        pthread_mutex_unlock(&ctx->lock);
        return -1;
    }

    *slave_addr = buffer[0];
    pdu->function_code = buffer[1];
    pdu->data_len = len - 4; /* Subtract addr + fc + crc(2) */
    if (pdu->data_len > 0) {
        memcpy(pdu->data, &buffer[2], pdu->data_len);
    }

    return 0;
}

/* Server thread */
static void *server_thread_func(void *arg) {
    modbus_rtu_t *ctx = (modbus_rtu_t *)arg;

    LOG_INFO(LOG_TAG, "RTU server started on %s (addr=%d)",
             ctx->config.device, ctx->config.slave_addr);

    while (ctx->running) {
        uint8_t slave_addr;
        modbus_pdu_t request, response;

        if (rtu_recv_frame(ctx, &slave_addr, &request, 100) < 0) {
            continue;
        }

        /* Check if addressed to us (or broadcast) */
        if (slave_addr != ctx->config.slave_addr && slave_addr != 0) {
            continue;
        }

        pthread_mutex_lock(&ctx->lock);
        ctx->stats.requests_received++;
        pthread_mutex_unlock(&ctx->lock);

        memset(&response, 0, sizeof(response));

        /* Call request handler */
        modbus_exception_t ex = MODBUS_EX_SLAVE_DEVICE_FAILURE;
        if (ctx->config.request_handler) {
            ex = ctx->config.request_handler(ctx, slave_addr, &request, &response,
                                              ctx->config.user_data);
        }

        if (ex != MODBUS_EX_NONE) {
            response.function_code = request.function_code | 0x80;
            response.data[0] = ex;
            response.data_len = 1;

            pthread_mutex_lock(&ctx->lock);
            ctx->stats.exceptions++;
            pthread_mutex_unlock(&ctx->lock);
        }

        /* Don't respond to broadcast */
        if (slave_addr != 0) {
            if (rtu_send_frame(ctx, ctx->config.slave_addr, &response) == 0) {
                pthread_mutex_lock(&ctx->lock);
                ctx->stats.responses_sent++;
                pthread_mutex_unlock(&ctx->lock);
            }
        }
    }

    LOG_INFO(LOG_TAG, "RTU server stopped");
    return NULL;
}

wtc_result_t modbus_rtu_init(modbus_rtu_t **ctx, const modbus_rtu_config_t *config) {
    if (!ctx || !config || !config->device[0]) {
        return WTC_ERROR_INVALID_PARAM;
    }

    modbus_rtu_t *rtu = calloc(1, sizeof(modbus_rtu_t));
    if (!rtu) return WTC_ERROR_NO_MEMORY;

    memcpy(&rtu->config, config, sizeof(modbus_rtu_config_t));
    rtu->serial_fd = -1;

    /* Set defaults */
    if (rtu->config.baud_rate == 0) rtu->config.baud_rate = 9600;
    if (rtu->config.data_bits == 0) rtu->config.data_bits = 8;
    if (rtu->config.parity == 0) rtu->config.parity = 'N';
    if (rtu->config.stop_bits == 0) rtu->config.stop_bits = 1;
    if (rtu->config.timeout_ms == 0) rtu->config.timeout_ms = 1000;

    if (rtu->config.inter_frame_delay_us == 0) {
        rtu->config.inter_frame_delay_us = calc_inter_frame_delay(rtu->config.baud_rate);
    }

    pthread_mutex_init(&rtu->lock, NULL);

    *ctx = rtu;
    LOG_INFO(LOG_TAG, "Modbus RTU initialized (device=%s, baud=%d)",
             config->device, rtu->config.baud_rate);
    return WTC_OK;
}

void modbus_rtu_cleanup(modbus_rtu_t *ctx) {
    if (!ctx) return;

    modbus_rtu_server_stop(ctx);
    modbus_rtu_close(ctx);

    pthread_mutex_destroy(&ctx->lock);
    free(ctx);

    LOG_INFO(LOG_TAG, "Modbus RTU cleaned up");
}

wtc_result_t modbus_rtu_open(modbus_rtu_t *ctx) {
    if (!ctx) return WTC_ERROR_INVALID_PARAM;

    if (ctx->serial_fd >= 0) return WTC_OK;

    ctx->serial_fd = open(ctx->config.device, O_RDWR | O_NOCTTY);
    if (ctx->serial_fd < 0) {
        LOG_ERROR(LOG_TAG, "Failed to open %s: %s",
                  ctx->config.device, strerror(errno));
        return WTC_ERROR_IO;
    }

    if (configure_serial(ctx->serial_fd, &ctx->config) < 0) {
        LOG_ERROR(LOG_TAG, "Failed to configure serial port");
        close(ctx->serial_fd);
        ctx->serial_fd = -1;
        return WTC_ERROR_IO;
    }

    LOG_INFO(LOG_TAG, "Opened %s (%d %d%c%d)",
             ctx->config.device, ctx->config.baud_rate,
             ctx->config.data_bits, ctx->config.parity, ctx->config.stop_bits);

    return WTC_OK;
}

void modbus_rtu_close(modbus_rtu_t *ctx) {
    if (!ctx || ctx->serial_fd < 0) return;

    close(ctx->serial_fd);
    ctx->serial_fd = -1;

    LOG_INFO(LOG_TAG, "Closed %s", ctx->config.device);
}

bool modbus_rtu_is_open(modbus_rtu_t *ctx) {
    return ctx && ctx->serial_fd >= 0;
}

wtc_result_t modbus_rtu_server_start(modbus_rtu_t *ctx) {
    if (!ctx || ctx->config.role != MODBUS_ROLE_SERVER) {
        return WTC_ERROR_INVALID_PARAM;
    }

    if (modbus_rtu_open(ctx) != WTC_OK) {
        return WTC_ERROR_IO;
    }

    ctx->running = true;
    if (pthread_create(&ctx->server_thread, NULL, server_thread_func, ctx) != 0) {
        LOG_ERROR(LOG_TAG, "Failed to create server thread");
        ctx->running = false;
        return WTC_ERROR_INTERNAL;
    }

    return WTC_OK;
}

wtc_result_t modbus_rtu_server_stop(modbus_rtu_t *ctx) {
    if (!ctx || !ctx->running) return WTC_OK;

    ctx->running = false;
    pthread_join(ctx->server_thread, NULL);

    return WTC_OK;
}

wtc_result_t modbus_rtu_transact(modbus_rtu_t *ctx,
                                  uint8_t slave_addr,
                                  const modbus_pdu_t *request,
                                  modbus_pdu_t *response) {
    if (!ctx || !request || !response || ctx->serial_fd < 0) {
        return WTC_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&ctx->lock);

    /* Flush any stale data */
    tcflush(ctx->serial_fd, TCIOFLUSH);

    pthread_mutex_unlock(&ctx->lock);

    if (rtu_send_frame(ctx, slave_addr, request) < 0) {
        pthread_mutex_lock(&ctx->lock);
        ctx->stats.timeouts++;
        pthread_mutex_unlock(&ctx->lock);
        return WTC_ERROR_IO;
    }

    pthread_mutex_lock(&ctx->lock);
    ctx->stats.requests_sent++;
    pthread_mutex_unlock(&ctx->lock);

    uint8_t resp_addr;
    if (rtu_recv_frame(ctx, &resp_addr, response, ctx->config.timeout_ms) < 0) {
        pthread_mutex_lock(&ctx->lock);
        ctx->stats.timeouts++;
        pthread_mutex_unlock(&ctx->lock);
        return WTC_ERROR_TIMEOUT;
    }

    if (resp_addr != slave_addr) {
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

wtc_result_t modbus_rtu_read_holding_registers(modbus_rtu_t *ctx, uint8_t slave_addr,
                                                uint16_t start_addr, uint16_t quantity,
                                                uint16_t *values) {
    if (!ctx || !values || quantity > MODBUS_MAX_READ_REGISTERS) {
        return WTC_ERROR_INVALID_PARAM;
    }

    modbus_pdu_t request, response;
    modbus_build_read_request(&request, MODBUS_FC_READ_HOLDING_REGISTERS,
                              start_addr, quantity);

    wtc_result_t res = modbus_rtu_transact(ctx, slave_addr, &request, &response);
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

wtc_result_t modbus_rtu_read_input_registers(modbus_rtu_t *ctx, uint8_t slave_addr,
                                              uint16_t start_addr, uint16_t quantity,
                                              uint16_t *values) {
    if (!ctx || !values || quantity > MODBUS_MAX_READ_REGISTERS) {
        return WTC_ERROR_INVALID_PARAM;
    }

    modbus_pdu_t request, response;
    modbus_build_read_request(&request, MODBUS_FC_READ_INPUT_REGISTERS,
                              start_addr, quantity);

    wtc_result_t res = modbus_rtu_transact(ctx, slave_addr, &request, &response);
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

wtc_result_t modbus_rtu_read_coils(modbus_rtu_t *ctx, uint8_t slave_addr,
                                    uint16_t start_addr, uint16_t quantity,
                                    uint8_t *values) {
    if (!ctx || !values || quantity > MODBUS_MAX_READ_BITS) {
        return WTC_ERROR_INVALID_PARAM;
    }

    modbus_pdu_t request, response;
    modbus_build_read_request(&request, MODBUS_FC_READ_COILS, start_addr, quantity);

    wtc_result_t res = modbus_rtu_transact(ctx, slave_addr, &request, &response);
    if (res != WTC_OK) return res;

    if (modbus_is_exception(&response)) {
        return WTC_ERROR_PROTOCOL;
    }

    uint8_t byte_count = response.data[0];
    memcpy(values, &response.data[1], byte_count);

    return WTC_OK;
}

wtc_result_t modbus_rtu_read_discrete_inputs(modbus_rtu_t *ctx, uint8_t slave_addr,
                                              uint16_t start_addr, uint16_t quantity,
                                              uint8_t *values) {
    if (!ctx || !values || quantity > MODBUS_MAX_READ_BITS) {
        return WTC_ERROR_INVALID_PARAM;
    }

    modbus_pdu_t request, response;
    modbus_build_read_request(&request, MODBUS_FC_READ_DISCRETE_INPUTS,
                              start_addr, quantity);

    wtc_result_t res = modbus_rtu_transact(ctx, slave_addr, &request, &response);
    if (res != WTC_OK) return res;

    if (modbus_is_exception(&response)) {
        return WTC_ERROR_PROTOCOL;
    }

    uint8_t byte_count = response.data[0];
    memcpy(values, &response.data[1], byte_count);

    return WTC_OK;
}

wtc_result_t modbus_rtu_write_single_coil(modbus_rtu_t *ctx, uint8_t slave_addr,
                                           uint16_t addr, bool value) {
    if (!ctx) return WTC_ERROR_INVALID_PARAM;

    modbus_pdu_t request, response;
    modbus_build_write_single_coil(&request, addr, value);

    return modbus_rtu_transact(ctx, slave_addr, &request, &response);
}

wtc_result_t modbus_rtu_write_single_register(modbus_rtu_t *ctx, uint8_t slave_addr,
                                               uint16_t addr, uint16_t value) {
    if (!ctx) return WTC_ERROR_INVALID_PARAM;

    modbus_pdu_t request, response;
    modbus_build_write_single_register(&request, addr, value);

    return modbus_rtu_transact(ctx, slave_addr, &request, &response);
}

wtc_result_t modbus_rtu_write_multiple_coils(modbus_rtu_t *ctx, uint8_t slave_addr,
                                              uint16_t start_addr, uint16_t quantity,
                                              const uint8_t *values) {
    if (!ctx || !values) return WTC_ERROR_INVALID_PARAM;

    modbus_pdu_t request, response;
    modbus_build_write_multiple_coils(&request, start_addr, quantity, values);

    return modbus_rtu_transact(ctx, slave_addr, &request, &response);
}

wtc_result_t modbus_rtu_write_multiple_registers(modbus_rtu_t *ctx, uint8_t slave_addr,
                                                  uint16_t start_addr, uint16_t quantity,
                                                  const uint16_t *values) {
    if (!ctx || !values) return WTC_ERROR_INVALID_PARAM;

    modbus_pdu_t request, response;
    modbus_build_write_multiple_registers(&request, start_addr, quantity, values);

    return modbus_rtu_transact(ctx, slave_addr, &request, &response);
}

wtc_result_t modbus_rtu_get_stats(modbus_rtu_t *ctx, modbus_stats_t *stats) {
    if (!ctx || !stats) return WTC_ERROR_INVALID_PARAM;

    pthread_mutex_lock(&ctx->lock);
    memcpy(stats, &ctx->stats, sizeof(modbus_stats_t));
    pthread_mutex_unlock(&ctx->lock);

    return WTC_OK;
}

void modbus_rtu_flush(modbus_rtu_t *ctx) {
    if (ctx && ctx->serial_fd >= 0) {
        tcflush(ctx->serial_fd, TCIOFLUSH);
    }
}
