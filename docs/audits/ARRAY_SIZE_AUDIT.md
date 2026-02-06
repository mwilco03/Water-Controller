# Array Size Audit - 2026-02-06

## Purpose
Audit all hardcoded array sizes in the codebase to ensure:
1. Sizes use constants (DRY principle)
2. Sizes match system limits (e.g., WTC_MAX_SLOTS)
3. No magic numbers that should be config-driven

## Critical Findings

### ❌ VIOLATION: Hardcoded 64 instead of WTC_MAX_SLOTS
**Fixed in commit 7ba561d**

- **Files:** `profinet_controller.h`, `profinet_rpc.h`, `profinet_rpc.c`, `ar_manager.c`
- **Issue:** `discovered_modules[64]` should be `discovered_modules[WTC_MAX_SLOTS]` (247)
- **Impact:** RTUs with >64 modules would have been silently truncated
- **Status:** ✅ FIXED

---

## Protocol Constants (Justified Hardcoded Values)

These are defined by protocol specifications and should NOT be changed:

| Constant | Size | Justification | Location |
|----------|------|---------------|----------|
| MAC address | `[6]` | IEEE 802 standard | All MAC arrays |
| UUID | `[16]` | RFC 4122 standard | All UUID arrays |
| IPv4 address | `[16]` | "xxx.xxx.xxx.xxx\0" | IP string buffers |
| IPv6 address | `[46]` | "xxxx:xxxx:...:xxxx\0" | IPv6 buffers (if added) |

---

## Configuration Strings

### Station Names: `char station_name[64]`
**Status:** ✅ OK - Matches PROFINET spec (63 chars + null)

**Occurrences:**
- `profinet_controller.h:83`
- `profinet_controller.h:117`
- `profinet_rpc.h:357`
- `dcp_discovery.h:69`
- `ar_manager.h:30`

**Recommendation:** Consider defining `PROFINET_STATION_NAME_MAX 64` constant.

### Interface Names: `char interface_name[32]`
**Status:** ⚠️ INCONSISTENT with Linux IFNAMSIZ (16)

**Occurrences:**
- `config_manager.h:27`
- `profinet_controller.h:75`
- `profinet_rpc.h:345`
- `ar_manager.c:44`
- `dcp_discovery.c:44`

**Issue:** Linux defines `IFNAMSIZ = 16`, but we use 32.

**Recommendation:**
```c
#define WTC_INTERFACE_NAME_MAX 32  // Generous buffer, truncate to IFNAMSIZ when passing to kernel
```

### IP Strings: `char ip_str[16]`
**Status:** ✅ OK - "xxx.xxx.xxx.xxx\0" = 15+1

**Occurrences:**
- `profinet_controller.c:74, 236, 731, 1723, 1796`

### MAC Strings: `char mac_str[18]`
**Status:** ✅ OK - "xx:xx:xx:xx:xx:xx\0" = 17+1

**Occurrences:**
- `profinet_controller.c:121, 350, 712`
- `dcp_discovery.c:442, 481`

---

## System Limits

### ✅ Using Constants Correctly

| Constant | Value | Usage |
|----------|-------|-------|
| `WTC_MAX_SLOTS` | 247 | Slot arrays (PROFINET spec limit) |
| `PROFINET_MAX_AR` | 256 | Max ARs per controller |
| `PROFINET_MAX_IOCR` | 64 | Max IOCRs per AR |
| `PROFINET_MAX_API` | 256 | Max APIs |
| `AR_MAX_RETRY_ATTEMPTS` | 3 | Connection retry limit |

---

## Configuration Buffers

### Paths: `char path[256]`
**Status:** ✅ OK - Standard for filesystem paths

**Occurrences:**
- `config_manager.h:24` (log_file)
- `config_manager.c:28` (config_path)
- `modbus_gateway.h:75` (register_map_file)
- `modbus_gateway_main.c:42` (config_file)
- `gsdml_cache.c:225, 248, 349` (filepath)

**Recommendation:** Consider `PATH_MAX` from `<limits.h>` (typically 4096), but 256 is reasonable for embedded systems.

### Hostnames: `char host[64]`
**Status:** ✅ OK - RFC 1035 limits hostnames to 63 chars

**Occurrences:**
- `config_manager.h:33, 49` (db_host, api_host)
- `modbus_gateway.h:39` (host)

### Device Paths: `char device[64]`
**Status:** ✅ OK - "/dev/ttyUSB0" etc. are short

**Occurrences:**
- `modbus_rtu.h:31`
- `modbus_gateway.h:43`

---

## Temporary/Work Buffers

### Large Buffers

| Buffer | Size | Purpose | Status |
|--------|------|---------|--------|
| `char line[512]` | 512 | Config file parsing | ✅ OK |
| `char message[4096]` | 4096 | Log messages | ✅ OK |
| `uint8_t request[512]` | 512 | GSDML HTTP request | ✅ OK |
| `uint8_t response[2048]` | 2048 | GSDML HTTP response | ⚠️ Consider `GSDML_MAX_RESPONSE` |
| `uint8_t frame[1518]` | 1518 | Ethernet frame (MTU) | ✅ OK (1500 + 14 + 4) |

### Small Buffers

| Buffer | Size | Purpose | Status |
|--------|------|---------|--------|
| `char timestamp[32]` | 32 | ISO 8601 timestamp | ✅ OK |
| `char correlation[48]` | 48 | Correlation ID | ✅ OK |
| `char source[128]` | 128 | Log source | ✅ OK |
| `char section[64]` | 64 | INI section name | ✅ OK |
| `char log_level[16]` | 16 | "DEBUG\0" etc. | ✅ OK |

---

## CRC Tables

### `static const uint16_t crc16_table[256]`
**Status:** ✅ OK - CRC-16 lookup table (256 entries)

**Occurrences:**
- `utils/crc.c:10`
- `modbus/modbus_common.c:11`

### `static const uint32_t crc32_table[256]`
**Status:** ✅ OK - CRC-32 lookup table (256 entries)

**Occurrences:**
- `utils/crc.c:46`

---

## Recommendations

### 1. **Define Constants for Common Sizes**

```c
// In types.h or new constants.h
#define WTC_STATION_NAME_MAX    64   // PROFINET station name limit
#define WTC_INTERFACE_NAME_MAX  32   // Network interface name (larger than IFNAMSIZ for safety)
#define WTC_HOSTNAME_MAX        64   // RFC 1035 hostname limit
#define WTC_PATH_MAX            256  // Filesystem path limit (embedded system)
#define WTC_DEVICE_PATH_MAX     64   // Device path (/dev/xxx)
#define WTC_MAC_STRING_MAX      18   // "xx:xx:xx:xx:xx:xx\0"
#define WTC_IPV4_STRING_MAX     16   // "xxx.xxx.xxx.xxx\0"
```

### 2. **Protocol-Defined Constants**

```c
// In profinet_protocol.h or profinet_constants.h
#define PROFINET_STATION_NAME_MAX  64   // From PROFINET spec
#define PROFINET_UUID_SIZE         16   // RFC 4122
#define PROFINET_MAC_SIZE          6    // IEEE 802
#define PROFINET_ETHERNET_MTU      1518 // 1500 + 14 + 4
```

### 3. **Replace Magic Numbers**

Before:
```c
char station_name[64];
char interface_name[32];
char mac_str[18];
```

After:
```c
char station_name[WTC_STATION_NAME_MAX];
char interface_name[WTC_INTERFACE_NAME_MAX];
char mac_str[WTC_MAC_STRING_MAX];
```

### 4. **Audit Trigger**

Add to CI/CD pipeline:
```bash
# Fail if new hardcoded array sizes are added without review
git diff HEAD~1 | grep -E '\[[0-9]+\]' && echo "WARNING: New hardcoded array size detected"
```

---

## Conclusion

**Status:** ✅ MOSTLY COMPLIANT

- **Critical Issue:** Hardcoded 64 vs WTC_MAX_SLOTS - **FIXED**
- **Minor Issue:** Lack of named constants for common sizes
- **Recommendation:** Define constants in next refactor pass

**No immediate action required**, but consider adding constants in future work.
