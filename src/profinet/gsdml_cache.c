/*
 * Water Treatment Controller - GSDML Cache Implementation
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Phase 5: Fetch and cache GSDML from RTU HTTP server.
 * Phase 6: HTTP fallback for slot configuration.
 */

#include "gsdml_cache.h"
#include "gsdml_modules.h"
#include "utils/logger.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <errno.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <poll.h>

/* HTTP request/response buffer size */
#define HTTP_BUF_SIZE  (GSDML_MAX_FILE_SIZE + 4096)

/**
 * @brief Create directory tree recursively.
 */
static int mkdirs(const char *path, mode_t mode) {
    char tmp[256];
    snprintf(tmp, sizeof(tmp), "%s", path);

    for (char *p = tmp + 1; *p; p++) {
        if (*p == '/') {
            *p = '\0';
            if (mkdir(tmp, mode) != 0 && errno != EEXIST) {
                return -1;
            }
            *p = '/';
        }
    }
    return mkdir(tmp, mode) == 0 || errno == EEXIST ? 0 : -1;
}

/**
 * @brief Connect to RTU HTTP server.
 * @return socket fd on success, -1 on failure
 */
static int http_connect(const char *ip_str, uint16_t port) {
    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) {
        LOG_ERROR("GSDML cache: socket creation failed: %s", strerror(errno));
        return -1;
    }

    /* Set non-blocking for connect with timeout */
    int flags = fcntl(sock, F_GETFL, 0);
    fcntl(sock, F_SETFL, flags | O_NONBLOCK);

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    if (inet_pton(AF_INET, ip_str, &addr.sin_addr) != 1) {
        LOG_ERROR("GSDML cache: invalid IP address: %s", ip_str);
        close(sock);
        return -1;
    }

    int ret = connect(sock, (struct sockaddr *)&addr, sizeof(addr));
    if (ret < 0 && errno != EINPROGRESS) {
        LOG_ERROR("GSDML cache: connect to %s:%u failed: %s",
                  ip_str, port, strerror(errno));
        close(sock);
        return -1;
    }

    /* Wait for connect with timeout */
    struct pollfd pfd = {.fd = sock, .events = POLLOUT};
    ret = poll(&pfd, 1, GSDML_FETCH_TIMEOUT_SEC * 1000);
    if (ret <= 0) {
        LOG_ERROR("GSDML cache: connect timeout to %s:%u", ip_str, port);
        close(sock);
        return -1;
    }

    /* Check for connect error */
    int error = 0;
    socklen_t errlen = sizeof(error);
    getsockopt(sock, SOL_SOCKET, SO_ERROR, &error, &errlen);
    if (error != 0) {
        LOG_ERROR("GSDML cache: connect error: %s", strerror(error));
        close(sock);
        return -1;
    }

    /* Restore blocking mode */
    fcntl(sock, F_SETFL, flags);
    return sock;
}

/**
 * @brief Send HTTP GET and receive response.
 * @return response body length on success, -1 on failure
 */
static ssize_t http_get(const char *ip_str, uint16_t port,
                         const char *path, char *body, size_t body_size) {
    int sock = http_connect(ip_str, port);
    if (sock < 0) {
        return -1;
    }

    /* Build and send request */
    char request[512];
    int req_len = snprintf(request, sizeof(request),
                            "GET %s HTTP/1.0\r\nHost: %s:%u\r\n"
                            "Connection: close\r\n\r\n",
                            path, ip_str, port);

    if (send(sock, request, (size_t)req_len, 0) != req_len) {
        LOG_ERROR("GSDML cache: HTTP send failed");
        close(sock);
        return -1;
    }

    /* Receive response */
    char *buf = malloc(HTTP_BUF_SIZE);
    if (!buf) {
        close(sock);
        return -1;
    }

    size_t total = 0;
    while (total < HTTP_BUF_SIZE - 1) {
        struct pollfd pfd = {.fd = sock, .events = POLLIN};
        int ready = poll(&pfd, 1, GSDML_FETCH_TIMEOUT_SEC * 1000);
        if (ready <= 0) break;

        ssize_t n = recv(sock, buf + total, HTTP_BUF_SIZE - 1 - total, 0);
        if (n <= 0) break;
        total += (size_t)n;
    }
    buf[total] = '\0';
    close(sock);

    /* Parse status line */
    if (total < 12 || strncmp(buf, "HTTP/", 5) != 0) {
        LOG_ERROR("GSDML cache: invalid HTTP response");
        free(buf);
        return -1;
    }

    int status_code = atoi(buf + 9);
    if (status_code != 200) {
        LOG_ERROR("GSDML cache: HTTP %d from %s%s", status_code, ip_str, path);
        free(buf);
        return -1;
    }

    /* Find body (after \r\n\r\n) */
    char *body_start = strstr(buf, "\r\n\r\n");
    if (!body_start) {
        LOG_ERROR("GSDML cache: no HTTP body delimiter");
        free(buf);
        return -1;
    }
    body_start += 4;

    size_t body_len = total - (size_t)(body_start - buf);
    if (body_len > body_size - 1) {
        body_len = body_size - 1;
    }
    memcpy(body, body_start, body_len);
    body[body_len] = '\0';

    free(buf);
    return (ssize_t)body_len;
}

wtc_result_t gsdml_cache_init(void) {
    if (mkdirs(GSDML_CACHE_DIR, 0755) != 0) {
        LOG_WARN("GSDML cache: could not create %s: %s",
                 GSDML_CACHE_DIR, strerror(errno));
        return WTC_ERROR_IO;
    }
    LOG_INFO("GSDML cache initialized at %s", GSDML_CACHE_DIR);
    return WTC_OK;
}

wtc_result_t gsdml_cache_fetch(const char *rtu_ip_str,
                                const char *station_name) {
    if (!rtu_ip_str || !station_name) {
        return WTC_ERROR_INVALID_PARAM;
    }

    LOG_INFO("=== Phase 5: Fetching GSDML from %s ===", rtu_ip_str);

    char *body = malloc(GSDML_MAX_FILE_SIZE);
    if (!body) {
        return WTC_ERROR_NO_MEMORY;
    }

    ssize_t body_len = http_get(rtu_ip_str, RTU_HTTP_PORT,
                                 "/api/v1/gsdml", body, GSDML_MAX_FILE_SIZE);
    if (body_len <= 0) {
        LOG_ERROR("GSDML fetch failed from %s", rtu_ip_str);
        free(body);
        return WTC_ERROR_IO;
    }

    /* Validate: should start with XML declaration or GSDML element */
    if (strstr(body, "<?xml") == NULL && strstr(body, "<GSDML") == NULL) {
        LOG_ERROR("GSDML response is not valid XML");
        free(body);
        return WTC_ERROR_PROTOCOL;
    }

    /* Ensure cache directory exists */
    gsdml_cache_init();

    /* Write to cache file */
    char filepath[256];
    snprintf(filepath, sizeof(filepath), "%s/%s.xml",
             GSDML_CACHE_DIR, station_name);

    FILE *f = fopen(filepath, "w");
    if (!f) {
        LOG_ERROR("Failed to write GSDML cache: %s: %s",
                  filepath, strerror(errno));
        free(body);
        return WTC_ERROR_IO;
    }

    fwrite(body, 1, (size_t)body_len, f);
    fclose(f);
    free(body);

    LOG_INFO("GSDML cached: %s (%zd bytes)", filepath, body_len);
    return WTC_OK;
}

bool gsdml_cache_exists(const char *station_name) {
    if (!station_name) return false;

    char filepath[256];
    snprintf(filepath, sizeof(filepath), "%s/%s.xml",
             GSDML_CACHE_DIR, station_name);

    return access(filepath, R_OK) == 0;
}

/**
 * @brief Minimal XML parser for extracting ModuleItem entries from GSDML.
 *
 * Looks for patterns like:
 *   <ModuleItem ModuleIdentNumber="0x00000010" ...>
 *     <VirtualSubmoduleItem SubmoduleIdentNumber="0x00000011" .../>
 *   </ModuleItem>
 */
static wtc_result_t parse_gsdml_modules(const char *xml, size_t xml_len,
                                          ar_module_discovery_t *discovery) {
    discovery->module_count = 0;
    uint16_t slot_num = 1;  /* Application slots start at 1 */

    /* Add DAP modules first (always present) */
    discovery->modules[0].slot = 0;
    discovery->modules[0].subslot = 0x0001;
    discovery->modules[0].module_ident = GSDML_MOD_DAP;
    discovery->modules[0].submodule_ident = GSDML_SUBMOD_DAP;

    discovery->modules[1].slot = 0;
    discovery->modules[1].subslot = 0x8000;
    discovery->modules[1].module_ident = GSDML_MOD_DAP;
    discovery->modules[1].submodule_ident = GSDML_SUBMOD_INTERFACE;

    discovery->modules[2].slot = 0;
    discovery->modules[2].subslot = 0x8001;
    discovery->modules[2].module_ident = GSDML_MOD_DAP;
    discovery->modules[2].submodule_ident = GSDML_SUBMOD_PORT;

    discovery->module_count = 3;

    /* Scan for ModuleItem elements */
    const char *pos = xml;
    const char *end = xml + xml_len;

    while (pos < end && discovery->module_count < AR_MAX_DISCOVERED_MODULES) {
        const char *mod = strstr(pos, "ModuleIdentNumber=\"0x");
        if (!mod || mod >= end) break;

        /* Parse module ident with validation */
        const char *hex_start = mod + strlen("ModuleIdentNumber=\"0x");
        char *endptr = NULL;
        unsigned long mod_ident = strtoul(hex_start, &endptr, 16);
        if (endptr == hex_start || mod_ident == 0) {
            LOG_WARN("GSDML: invalid ModuleIdentNumber at offset %td, skipping",
                     hex_start - xml);
            pos = hex_start;
            continue;
        }

        /* Skip DAP module (we already added it) */
        if (mod_ident == GSDML_MOD_DAP) {
            pos = hex_start;
            continue;
        }

        /* Find matching SubmoduleIdentNumber */
        const char *submod = strstr(hex_start, "SubmoduleIdentNumber=\"0x");
        if (!submod || submod >= end) break;

        const char *sub_hex = submod + strlen("SubmoduleIdentNumber=\"0x");
        unsigned long submod_ident = strtoul(sub_hex, &endptr, 16);
        if (endptr == sub_hex || submod_ident == 0) {
            LOG_WARN("GSDML: invalid SubmoduleIdentNumber at offset %td, skipping",
                     sub_hex - xml);
            pos = sub_hex;
            continue;
        }

        ar_discovered_module_t *m = &discovery->modules[discovery->module_count];
        m->slot = slot_num++;
        m->subslot = 1;
        m->module_ident = (uint32_t)mod_ident;
        m->submodule_ident = (uint32_t)submod_ident;
        discovery->module_count++;

        LOG_DEBUG("GSDML parsed: slot %u module=0x%08lX submod=0x%08lX",
                  m->slot, mod_ident, submod_ident);

        pos = sub_hex;
    }

    LOG_INFO("Parsed %d modules from GSDML", discovery->module_count);
    return discovery->module_count > 0 ? WTC_OK : WTC_ERROR_PROTOCOL;
}

wtc_result_t gsdml_cache_load_modules(const char *station_name,
                                       ar_module_discovery_t *discovery) {
    if (!station_name || !discovery) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memset(discovery, 0, sizeof(ar_module_discovery_t));

    char filepath[256];
    snprintf(filepath, sizeof(filepath), "%s/%s.xml",
             GSDML_CACHE_DIR, station_name);

    FILE *f = fopen(filepath, "r");
    if (!f) {
        LOG_DEBUG("No cached GSDML for %s", station_name);
        return WTC_ERROR_NOT_FOUND;
    }

    /* Get file size */
    fseek(f, 0, SEEK_END);
    long file_size = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (file_size <= 0 || file_size > GSDML_MAX_FILE_SIZE) {
        LOG_ERROR("Cached GSDML invalid size: %ld", file_size);
        fclose(f);
        return WTC_ERROR_IO;
    }

    char *xml = malloc((size_t)file_size + 1);
    if (!xml) {
        fclose(f);
        return WTC_ERROR_NO_MEMORY;
    }

    size_t read_len = fread(xml, 1, (size_t)file_size, f);
    fclose(f);
    xml[read_len] = '\0';

    wtc_result_t res = parse_gsdml_modules(xml, read_len, discovery);
    free(xml);

    if (res == WTC_OK) {
        discovery->from_cache = true;
        LOG_INFO("Loaded %d modules from cached GSDML for %s",
                 discovery->module_count, station_name);
    }

    return res;
}

/**
 * @brief Minimal JSON parser for slot configuration.
 *
 * Expected format:
 * {"slot_count":N,"slots":[{"slot":1,"subslot":1,"module_ident":16,
 *   "submodule_ident":17,"direction":"input","data_size":5}, ...]}
 */
static wtc_result_t parse_slots_json(const char *json,
                                      ar_module_discovery_t *discovery) {
    discovery->module_count = 0;

    /* Add DAP modules first */
    discovery->modules[0].slot = 0;
    discovery->modules[0].subslot = 0x0001;
    discovery->modules[0].module_ident = GSDML_MOD_DAP;
    discovery->modules[0].submodule_ident = GSDML_SUBMOD_DAP;

    discovery->modules[1].slot = 0;
    discovery->modules[1].subslot = 0x8000;
    discovery->modules[1].module_ident = GSDML_MOD_DAP;
    discovery->modules[1].submodule_ident = GSDML_SUBMOD_INTERFACE;

    discovery->modules[2].slot = 0;
    discovery->modules[2].subslot = 0x8001;
    discovery->modules[2].module_ident = GSDML_MOD_DAP;
    discovery->modules[2].submodule_ident = GSDML_SUBMOD_PORT;

    discovery->module_count = 3;

    /* Parse each slot object */
    const char *pos = json;
    while ((pos = strstr(pos, "\"slot\"")) != NULL &&
           discovery->module_count < AR_MAX_DISCOVERED_MODULES) {

        ar_discovered_module_t *m = &discovery->modules[discovery->module_count];

        /* Parse "slot": N — with validation */
        const char *colon = strchr(pos + 6, ':');
        if (!colon) break;
        char *endptr = NULL;
        long slot_val = strtol(colon + 1, &endptr, 10);
        if (endptr == colon + 1 || slot_val < 0 || slot_val > 0xFFFF) {
            LOG_WARN("HTTP /slots: invalid slot number, skipping");
            pos = colon + 1;
            continue;
        }
        m->slot = (uint16_t)slot_val;

        /* Parse "subslot": N */
        const char *subslot = strstr(pos, "\"subslot\"");
        if (subslot) {
            colon = strchr(subslot + 9, ':');
            if (colon) {
                long ss_val = strtol(colon + 1, &endptr, 10);
                m->subslot = (endptr != colon + 1 && ss_val > 0)
                             ? (uint16_t)ss_val : 1;
            }
        } else {
            m->subslot = 1;
        }

        /* Parse "module_ident": N */
        const char *mod = strstr(pos, "\"module_ident\"");
        if (mod) {
            colon = strchr(mod + 14, ':');
            if (colon) {
                unsigned long mi = strtoul(colon + 1, &endptr, 0);
                m->module_ident = (endptr != colon + 1) ? (uint32_t)mi : 0;
            }
        }

        /* Parse "submodule_ident": N */
        const char *submod = strstr(pos, "\"submodule_ident\"");
        if (submod) {
            colon = strchr(submod + 17, ':');
            if (colon) {
                unsigned long si = strtoul(colon + 1, &endptr, 0);
                m->submodule_ident = (endptr != colon + 1) ? (uint32_t)si : 0;
            }
        }

        /* Skip slot 0 entries (DAP already added) */
        if (m->slot > 0) {
            discovery->module_count++;
            LOG_DEBUG("Parsed slot %u: module=0x%08X submod=0x%08X",
                      m->slot, m->module_ident, m->submodule_ident);
        }

        pos = colon ? colon + 1 : pos + 6;
    }

    LOG_INFO("Parsed %d modules from HTTP /slots", discovery->module_count);
    return discovery->module_count > 0 ? WTC_OK : WTC_ERROR_PROTOCOL;
}

wtc_result_t gsdml_fetch_slots_http(const char *rtu_ip_str,
                                     ar_module_discovery_t *discovery) {
    if (!rtu_ip_str || !discovery) {
        return WTC_ERROR_INVALID_PARAM;
    }

    memset(discovery, 0, sizeof(ar_module_discovery_t));

    LOG_INFO("=== Phase 6: HTTP Fallback /slots from %s ===", rtu_ip_str);

    char *body = malloc(64 * 1024);
    if (!body) {
        return WTC_ERROR_NO_MEMORY;
    }

    ssize_t body_len = http_get(rtu_ip_str, RTU_HTTP_PORT,
                                 "/api/v1/slots", body, 64 * 1024);
    if (body_len <= 0) {
        LOG_ERROR("HTTP /slots fetch failed from %s", rtu_ip_str);
        free(body);
        return WTC_ERROR_IO;
    }

    wtc_result_t res = parse_slots_json(body, discovery);
    free(body);

    if (res == WTC_OK) {
        discovery->from_cache = false;
        LOG_INFO("=== HTTP Fallback: %d modules from %s ===",
                 discovery->module_count, rtu_ip_str);
    }

    return res;
}
