/*
 * Water Treatment Controller - GSDML Cache (Phase 5)
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Fetches and caches GSDML XML from RTU HTTP server.
 * Cached GSDML enables direct full connect on subsequent
 * connections, skipping the DAP-only discovery pipeline.
 */

#ifndef WTC_GSDML_CACHE_H
#define WTC_GSDML_CACHE_H

#include "types.h"
#include "ar_manager.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Cache directory for GSDML files */
#define GSDML_CACHE_DIR "/var/cache/water-controller/gsdml"

/* RTU HTTP port for GSDML and slot endpoints */
#define RTU_HTTP_PORT   9081

/* Maximum GSDML file size (256 KB) */
#define GSDML_MAX_FILE_SIZE (256 * 1024)

/* HTTP fetch timeout in seconds */
#define GSDML_FETCH_TIMEOUT_SEC 10

/**
 * @brief Initialize GSDML cache (create cache directory).
 * @return WTC_OK on success
 */
wtc_result_t gsdml_cache_init(void);

/**
 * @brief Fetch GSDML from RTU via HTTP and cache locally.
 *
 * Sends HTTP GET to http://<rtu_ip>:9081/gsdml
 * and saves the XML response to GSDML_CACHE_DIR/<station_name>.xml
 *
 * @param[in] rtu_ip_str    RTU IP address string (e.g. "192.168.1.100")
 * @param[in] station_name  RTU station name (used as cache filename)
 * @return WTC_OK on success, error code on failure
 */
wtc_result_t gsdml_cache_fetch(const char *rtu_ip_str,
                                const char *station_name);

/**
 * @brief Check if GSDML cache exists for a station.
 *
 * @param[in] station_name  RTU station name
 * @return true if cached GSDML exists
 */
bool gsdml_cache_exists(const char *station_name);

/**
 * @brief Load module discovery from cached GSDML.
 *
 * Parses the cached GSDML XML to extract module/submodule configuration.
 * The result can be passed directly to ar_build_full_connect_params().
 *
 * @param[in]  station_name  RTU station name
 * @param[out] discovery     Module discovery result
 * @return WTC_OK on success, WTC_ERROR_NOT_FOUND if not cached
 */
wtc_result_t gsdml_cache_load_modules(const char *station_name,
                                       ar_module_discovery_t *discovery);

/**
 * @brief Fetch slot configuration from RTU via HTTP (Phase 6 fallback).
 *
 * Sends HTTP GET to http://<rtu_ip>:9081/slots
 * and parses the JSON response into module discovery format.
 *
 * @param[in]  rtu_ip_str    RTU IP address string
 * @param[out] discovery     Module discovery result
 * @return WTC_OK on success
 */
wtc_result_t gsdml_fetch_slots_http(const char *rtu_ip_str,
                                     ar_module_discovery_t *discovery);

#ifdef __cplusplus
}
#endif

#endif /* WTC_GSDML_CACHE_H */
