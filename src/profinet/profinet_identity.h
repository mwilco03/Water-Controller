/*
 * Water Treatment Controller - PROFINET Identity Constants
 * Copyright (C) 2024-2025
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * PROFINET identity utilities and UUID generation.
 * Identity values come from generated config (schemas/config/profinet.schema.yaml).
 *
 * Used for:
 *   - CMInitiatorObjectUUID in ARBlockReq (Connect Request)
 *   - Config defaults (vendor_id, device_id)
 *   - DCP validation
 *
 * Reference: IEC 61158-6-10 §4.10.3.2 (CMInitiatorObjectUUID format)
 */

#ifndef WTC_PROFINET_IDENTITY_H
#define WTC_PROFINET_IDENTITY_H

#include <stdint.h>
#include <string.h>
#include "generated/config_defaults.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * PROFINET Identity - sourced from schema (DO NOT hardcode here).
 * These values come from schemas/config/profinet.schema.yaml.
 * To change: edit schema, run `make generate`.
 */
#define PN_VENDOR_ID              WTC_DEFAULT_PROFINET_CONTROLLER_VENDOR_ID
#define PN_DEVICE_ID              WTC_DEFAULT_PROFINET_CONTROLLER_DEVICE_ID

/*
 * PROFINET Instance ID (controller instance).
 * Identifies this specific controller in the CMInitiatorObjectUUID.
 */
#define PN_INSTANCE_ID            0x0001

/*
 * Build CMInitiatorObjectUUID from controller identity.
 *
 * Per IEC 61158-6-10 §4.10.3.2, the CMInitiatorObjectUUID format is:
 *   DEA00000-6C97-11D1-8271-{InstanceHi}{InstanceLo}{DeviceHi}{DeviceLo}{VendorHi}{VendorLo}
 *
 * The first 10 bytes are fixed (the DEA00000 prefix + clock_seq + node prefix).
 * The last 6 bytes encode the controller's identity per PI assignment.
 *
 * This UUID goes into the ARBlockReq as the controller_uuid field
 * (CMInitiatorObjectUUID) and is stored in big-endian byte order
 * matching the PNIO block encoding.
 *
 * @param[out] uuid      16-byte output buffer
 * @param[in]  vendor_id Controller vendor ID (e.g., PN_VENDOR_ID)
 * @param[in]  device_id Controller device ID (e.g., PN_DEVICE_ID)
 * @param[in]  instance_id Controller instance (e.g., PN_INSTANCE_ID)
 */
static inline void pn_build_cm_initiator_uuid(uint8_t uuid[16],
                                               uint16_t vendor_id,
                                               uint16_t device_id,
                                               uint16_t instance_id)
{
    /* Fixed prefix: DEA00000-6C97-11D1-8271 */
    static const uint8_t prefix[10] = {
        0xDE, 0xA0, 0x00, 0x00, 0x6C, 0x97, 0x11, 0xD1, 0x82, 0x71
    };
    memcpy(uuid, prefix, 10);

    /* Variable suffix: instance, device, vendor (all big-endian) */
    uuid[10] = (uint8_t)(instance_id >> 8);
    uuid[11] = (uint8_t)(instance_id & 0xFF);
    uuid[12] = (uint8_t)(device_id >> 8);
    uuid[13] = (uint8_t)(device_id & 0xFF);
    uuid[14] = (uint8_t)(vendor_id >> 8);
    uuid[15] = (uint8_t)(vendor_id & 0xFF);
}

#ifdef __cplusplus
}
#endif

#endif /* WTC_PROFINET_IDENTITY_H */
