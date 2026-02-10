/*
 * Water Treatment Controller - PROFINET Identity & Protocol Constants
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Shared header for all PROFINET identity constants used across
 * controller and RTU code. These MUST match GSDML and RTU config.
 *
 * Reference: GSDML-V2.4-WaterTreat-RTU-20241222.xml
 * Reference: IEC 61158-6-10:2023
 */

#ifndef SHARED_PROFINET_IDENTITY_H
#define SHARED_PROFINET_IDENTITY_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============== Device Identity ============== */

/*
 * Controller identity - sourced from schema (DO NOT hardcode).
 * Values come from schemas/config/profinet.schema.yaml.
 * To change: edit schema, run `make generate`.
 *
 * Note: This header provides protocol constants, but controller identity
 * comes from generated config. Include "generated/config_defaults.h" if needed.
 */
#ifndef PN_VENDOR_ID
  #warning "PN_VENDOR_ID not defined - include generated/config_defaults.h or profinet/profinet_identity.h"
  #define PN_VENDOR_ID            0xFFFF  /* Placeholder - should come from config */
#endif

#ifndef PN_DEVICE_ID
  #warning "PN_DEVICE_ID not defined - include generated/config_defaults.h or profinet/profinet_identity.h"
  #define PN_DEVICE_ID            0xFFFF  /* Placeholder - should come from config */
#endif

#ifndef PN_INSTANCE_ID
  #define PN_INSTANCE_ID          0x0001  /* Controller instance - can be hardcoded */
#endif

/* ============== DAP (Device Access Point) ============== */

#define GSDML_MOD_DAP               0x00000001
#define GSDML_SUBMOD_DAP            0x00000001
#define GSDML_SUBMOD_DAP_INTERFACE  0x00000100
#define GSDML_SUBMOD_DAP_PORT       0x00000200

/* ============== Sensor Modules (INPUT) ============== */

#define GSDML_MOD_PH                0x00000010
#define GSDML_SUBMOD_PH             0x00000011
#define GSDML_MOD_TDS               0x00000020
#define GSDML_SUBMOD_TDS            0x00000021
#define GSDML_MOD_TURBIDITY         0x00000030
#define GSDML_SUBMOD_TURBIDITY      0x00000031
#define GSDML_MOD_TEMPERATURE       0x00000040
#define GSDML_SUBMOD_TEMPERATURE    0x00000041
#define GSDML_MOD_FLOW              0x00000050
#define GSDML_SUBMOD_FLOW           0x00000051
#define GSDML_MOD_LEVEL             0x00000060
#define GSDML_SUBMOD_LEVEL          0x00000061

/* ============== Actuator Modules (OUTPUT) ============== */

#define GSDML_MOD_PUMP              0x00000100
#define GSDML_SUBMOD_PUMP           0x00000101
#define GSDML_MOD_VALVE             0x00000110
#define GSDML_SUBMOD_VALVE          0x00000111

/* ============== I/O Data Sizes ============== */

/* Input: 4 bytes IEEE754-BE float + 1 byte quality */
#define GSDML_INPUT_DATA_SIZE       5
/* Output: 1 byte cmd + 1 byte duty + 2 bytes reserved */
#define GSDML_OUTPUT_DATA_SIZE      4

/* ============== Timing ============== */

#define PN_MIN_DEVICE_INTERVAL      32       /* 32 x 31.25us = 1ms */
#define PN_TICK_US                  1000     /* 1ms base tick */

/* ============== Protocol Constants ============== */

#define PN_IOCR_PHASE               1        /* Phase 1-128, use 1 */
#define PN_ALARM_TAG_HIGH           0xC000   /* VLAN priority 6 */
#define PN_ALARM_TAG_LOW            0xA000   /* VLAN priority 5 */

/* Minimum C-SDU length for RT_CLASS_1 frame */
#define PN_MIN_CSDU_LENGTH          40

/* ============== Record Indices ============== */

#define PN_RECORD_INDEX_REAL_IDENT  0xE001   /* RealIdentificationData for one AR */
#define PN_RECORD_INDEX_EXPECTED    0xE000   /* ExpectedIdentificationData for one AR */
#define PN_RECORD_INDEX_IM0         0xAFF0   /* I&M0 */
#define PN_RECORD_INDEX_IM1         0xAFF1   /* I&M1 */

/* ============== GSDML Cache ============== */

#define PN_GSDML_CACHE_DIR          "/var/cache/water-controller/gsdml"
#define PN_RTU_HTTP_PORT            9081

/* ============== Module Discovery ============== */

/* Maximum modules an RTU can report via Record Read 0xE001 */
#define PN_MAX_DISCOVERED_MODULES   64

/* Discovered module from RealIdentificationData */
typedef struct {
    uint16_t slot;
    uint16_t subslot;
    uint32_t module_ident;
    uint32_t submodule_ident;
} pn_discovered_module_t;

/* Result of module discovery (Record Read 0xE001) */
typedef struct {
    pn_discovered_module_t modules[PN_MAX_DISCOVERED_MODULES];
    int module_count;
} pn_module_discovery_t;

#ifdef __cplusplus
}
#endif

#endif /* SHARED_PROFINET_IDENTITY_H */
