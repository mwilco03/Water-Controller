# User Credential Synchronization: Controller → RTU

**Document Class:** Architecture Design (requires coordinated changes to Water-Controller and Water-Treat)

**Applies to:** Water-Controller (API + C Controller), Water-Treat (RTU firmware)

**References:**
- [CROSS_SYSTEM.md Part 5](CROSS_SYSTEM.md) — Wire protocol, DJB2 hash, record index 0xF840
- [SYSTEM_DESIGN.md Principle 2](SYSTEM_DESIGN.md) — Separation of responsibility
- [SYSTEM_DESIGN.md Principle 1](SYSTEM_DESIGN.md) — Design for failure before features
- [GUIDELINES.md Part 1](../development/GUIDELINES.md) — Production standards

---

## 1. Problem Statement

The web HMI has a User Management page (`/users`) with a `sync_to_rtus` flag per user. The C controller has `user_sync.c` which serializes users and sends them via PROFINET acyclic write to record index `0xF840`. The RTU firmware has `user_sync.c` which receives and persists credentials to NV storage for local TUI authentication.

**None of these components are wired together.** The API CRUD endpoints do not trigger sync. The result: the `sync_to_rtus` checkbox does nothing.

### What Exists Today

| Layer | Component | Status |
|-------|-----------|--------|
| HMI | Users page with `sync_to_rtus` toggle | IMPLEMENTED |
| API | `GET /api/v1/users/sync` (read-only query) | IMPLEMENTED |
| API | `POST /api/v1/users/sync/{station}` (trigger) | **NOT IMPLEMENTED** |
| API | Auto-sync on user CRUD | **NOT IMPLEMENTED** |
| SHM | `SHM_CMD_USER_SYNC` (14), `SHM_CMD_USER_SYNC_ALL` (15) | IMPLEMENTED |
| SHM Client | `sync_users_to_rtu()`, `sync_users_to_all_rtus()` | IMPLEMENTED |
| C Controller | `user_sync_serialize()` + `profinet_controller_write_record()` | IMPLEMENTED |
| RTU | Record handler for 0xF840, NV persistence, TUI auth | IMPLEMENTED |

### What Needs to Be Built

1. **API trigger endpoint** — `POST /api/v1/users/sync/{station_name}`
2. **Auto-sync hook** — after user create, update, or delete, push to all connected RTUs
3. **Sync status reporting** — API endpoint and HMI indicator for last sync time and result
4. **Auto-sync on RTU connect** — when an RTU reaches RUNNING state, push current users

---

## 2. Architecture

### 2.1 Data Flow

```
                        ┌─────────────────────────────────────────────┐
                        │              Web HMI (/users)               │
                        │                                             │
                        │  [Create User]  [Edit User]  [Delete User]  │
                        │  [x] Sync to RTUs                           │
                        │  [Manual Sync] button per RTU               │
                        └─────────────────┬───────────────────────────┘
                                          │ POST/PUT/DELETE /api/v1/users
                                          ▼
                        ┌─────────────────────────────────────────────┐
                        │           FastAPI Backend                    │
                        │                                             │
                        │  1. Execute user CRUD                       │
                        │  2. Log audit entry                         │
                        │  3. If sync_to_rtus affected:               │
                        │     call shm_client.sync_users_to_all_rtus()│
                        └─────────────────┬───────────────────────────┘
                                          │ SHM_CMD_USER_SYNC_ALL (15)
                                          ▼
                        ┌─────────────────────────────────────────────┐
                        │       C Controller (ipc_server.c)           │
                        │                                             │
                        │  1. Read command from SHM queue             │
                        │  2. Serialize users (user_sync_serialize)   │
                        │  3. For each connected RTU:                 │
                        │     profinet_controller_write_record(0xF840)│
                        └────────┬────────────────────┬───────────────┘
                                 │ PROFINET Acyclic    │
                          ┌──────▼──────┐       ┌─────▼───────┐
                          │   RTU #1    │       │   RTU #N    │
                          │ user_sync.c │       │ user_sync.c │
                          │ NV storage  │       │ NV storage  │
                          │ TUI auth    │       │ TUI auth    │
                          └─────────────┘       └─────────────┘
```

### 2.2 Responsibility Boundaries

Per Principle 2 (Separation of Responsibility):

| Component | Responsibility | Does NOT Do |
|-----------|---------------|-------------|
| **HMI** | Display sync status, trigger manual sync | Hash passwords, serialize payloads |
| **API** | User CRUD, trigger sync via SHM command | Serialize PROFINET payloads, talk to RTU |
| **C Controller** | Serialize user payload, send via PROFINET record write | Store users, validate passwords, manage DB |
| **RTU** | Receive payload, persist to NV, authenticate TUI users | Create users, manage policy, talk to API |

---

## 3. API Changes

### 3.1 New Endpoint: Trigger Sync

```http
POST /api/v1/users/sync/{station_name}
Authorization: Bearer <admin_token>
```

**Response (success):**
```json
{
  "data": {
    "station_name": "rtu-ec3b",
    "status": "sent",
    "user_count": 3,
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**Response (RTU not connected):**
```json
{
  "status": 503,
  "detail": {
    "error": "RTU not connected",
    "code": "RTU_NOT_CONNECTED",
    "message": "Cannot sync users to 'rtu-ec3b': RTU is not in RUNNING state"
  }
}
```

**NOTE:** `status: "sent"` means the command was placed in the SHM queue. Delivery confirmation is asynchronous — the C controller writes the record and reports success/failure via the SHM command result.

### 3.2 New Endpoint: Sync to All RTUs

```http
POST /api/v1/users/sync
Authorization: Bearer <admin_token>
```

**Response:**
```json
{
  "data": {
    "status": "sent",
    "user_count": 3,
    "target_rtus": 2,
    "correlation_id": "550e8400-e29b-41d4-a716-446655440001"
  }
}
```

### 3.3 New Endpoint: Sync Status

```http
GET /api/v1/users/sync/status
Authorization: Bearer <admin_token>
```

**Response:**
```json
{
  "data": {
    "last_sync": "2026-02-10T16:30:00Z",
    "last_sync_by": "admin",
    "last_sync_result": "ok",
    "rtus": [
      {
        "station_name": "rtu-ec3b",
        "last_sync": "2026-02-10T16:30:00Z",
        "last_result": "ok",
        "synced_user_count": 3
      }
    ]
  }
}
```

### 3.4 Auto-Sync on User CRUD

The following API operations trigger automatic sync to all connected RTUs when the affected user has `sync_to_rtus=True` (or when a user with `sync_to_rtus=True` is deleted):

| Operation | Trigger Condition | Sync Action |
|-----------|-------------------|-------------|
| `POST /users` (create) | `body.sync_to_rtus == True` | `SHM_CMD_USER_SYNC_ALL` |
| `PUT /users/{id}` (update) | User has `sync_to_rtus=True` OR `sync_to_rtus` changed | `SHM_CMD_USER_SYNC_ALL` |
| `DELETE /users/{id}` | Deleted user had `sync_to_rtus=True` | `SHM_CMD_USER_SYNC_ALL` |

**Why full sync, not incremental?** The PROFINET record write replaces the entire user table on the RTU (operation `0x00 FULL_SYNC`). This is simpler, idempotent, and avoids partial-state bugs. With a maximum of 16 users and a 1612-byte payload, the overhead is negligible.

**Implementation pattern** (in `users.py` after CRUD + audit log):

```python
# After successful create/update/delete, trigger RTU sync
try:
    from ...shm_client import get_client
    client = get_client()
    if client:
        sync_users = get_users_for_sync()
        count = client.sync_users_to_all_rtus(sync_users)
        logger.info(f"User sync triggered to {count} RTUs after {operation}")
except Exception:
    # Sync failure must NOT fail the CRUD operation
    # Log and continue — sync will retry on next change or manual trigger
    logger.warning(f"Failed to trigger user sync after {operation}", exc_info=True)
```

**CRITICAL:** Sync failure is non-fatal. The user CRUD operation succeeds regardless. Per Principle 1, the system degrades gracefully — RTUs keep their last-synced credentials until the next successful sync.

### 3.5 Auto-Sync on RTU Connect

When an RTU transitions to `RUNNING` state, the C controller should automatically push the current user set. This is already supported by `user_sync_on_rtu_connect()` in `user_sync.c` but must be enabled in the controller's startup configuration.

**C Controller change** (in `profinet_controller.c` or state machine callback):

```c
/* Called when RTU AR reaches DATA state */
void on_rtu_connected(const char *station_name) {
    if (g_user_sync_config.auto_sync_on_connect) {
        user_sync_to_rtu(station_name);
    }
}
```

**Default configuration:** `auto_sync_on_connect = true`

---

## 4. HMI Changes

### 4.1 Users Page Additions

Add to the `/users` page:

1. **Sync Status Banner** (top of page, below header):
   ```
   ┌────────────────────────────────────────────────────────┐
   │ RTU Sync: Last synced 2m ago to 1 RTU (3 users)  [Sync Now] │
   └────────────────────────────────────────────────────────┘
   ```

   States:
   - `GOOD` (green): Last sync < 5 minutes ago, all RTUs received
   - `STALE` (yellow): Last sync > 5 minutes ago OR some RTUs missed
   - `NEVER` (gray): No sync has occurred
   - `FAILED` (red): Last sync attempt failed

2. **Per-RTU Sync Status** (expandable detail):
   ```
   RTU          Last Sync           Users   Status
   rtu-ec3b     2026-02-10 16:30   3       OK
   rtu-a1b2     Never               --      NOT_CONNECTED
   ```

3. **Manual Sync Button**: Calls `POST /api/v1/users/sync` and shows result toast.

### 4.2 RTU Detail Page Addition

On the RTU detail page Overview tab, add a "User Sync" row to the Device Information grid:

```
User Sync    Last synced 2m ago (3 users)
```

Or if never synced:

```
User Sync    Never synced
```

---

## 5. Failure Modes

Per Principle 1 (Design for Failure):

| Failure | Impact | Recovery |
|---------|--------|----------|
| SHM client unavailable | Sync command not sent | Log warning. CRUD succeeds. Sync retries on next user change or manual trigger. |
| C controller not running | Command sits in SHM queue | Controller processes queued commands on restart. |
| RTU not connected | Record write fails | C controller logs error. Sync retries automatically when RTU reconnects (auto_sync_on_connect). |
| RTU rejects payload (CRC mismatch) | RTU keeps old credentials | C controller logs error with RTU response. Admin investigates via audit log. |
| RTU NV storage full | RTU cannot persist | RTU uses credentials in RAM until reboot, then falls back to local DB. RTU alarm raised. |
| Network partition during sync | Partial delivery | Full sync is idempotent. Next sync attempt delivers complete user set. |

**Visibility Requirements** (per Principle 4):
- Every sync attempt logged in audit trail with correlation ID
- Sync failures generate a system alarm (severity: WARNING, not CRITICAL — RTU still functions with cached credentials)
- HMI shows sync freshness with quality indicator

---

## 6. Security

### 6.1 What Crosses the Wire

| Field | Encoding | Exposure Risk |
|-------|----------|---------------|
| `username` | Plaintext (32 bytes, null-terminated) | Low — usernames are not secret |
| `password_hash` | DJB2 salted hash (`DJB2:XXXXXXXX:XXXXXXXX`) | Medium — hash is irreversible but DJB2 is not cryptographically strong |
| `role` | Enum byte (0-3) | None |
| `flags` | Bit field | None |

### 6.2 DJB2 Limitations

DJB2 is a fast non-cryptographic hash. It is adequate for this use case because:
- The network is a dedicated industrial VLAN (not internet-facing)
- PROFINET Layer 2 frames do not leave the local switch
- The salt prevents rainbow table attacks
- Constant-time comparison prevents timing attacks

DJB2 is **NOT** adequate for internet-facing authentication. If the system is ever exposed to untrusted networks, upgrade to bcrypt/scrypt/argon2.

### 6.3 Audit Trail

Every sync operation is logged:

```
{
  "timestamp": "2026-02-10T16:30:00Z",
  "user": "admin",
  "action": "user_sync",
  "resource_type": "rtu",
  "resource_id": "rtu-ec3b",
  "details": "Synced 3 users to RTU (correlation: 550e8400-...)",
  "ip_address": "192.168.6.13"
}
```

---

## 7. Implementation Plan

### Phase 1: API Wiring (Water-Controller — this team)

**Files to modify:**

| File | Change |
|------|--------|
| `web/api/app/api/v1/users.py` | Add `POST /sync`, `POST /sync/{station}`, `GET /sync/status`. Add auto-sync calls after create/update/delete. |
| `web/api/shm_client.py` | Verify `sync_users_to_rtu()` and `sync_users_to_all_rtus()` work with current SHM layout. Add sync result tracking. |
| `web/ui/src/app/users/page.tsx` | Add sync status banner, manual sync button, per-RTU sync detail. |

**Estimated scope:** ~150 lines Python, ~80 lines TypeScript.

### Phase 2: C Controller Auto-Sync (Water-Controller — this team)

**Files to modify:**

| File | Change |
|------|--------|
| `src/user/user_sync.c` | Enable `auto_sync_on_connect` by default. Verify `user_sync_on_rtu_connect()` callback is registered. |
| `src/ipc/ipc_server.c` | Verify `handle_user_sync_command()` processes both CMD 14 and CMD 15 correctly. Add result reporting to SHM. |
| `src/profinet/profinet_controller.c` | Register `on_rtu_connected` callback that calls `user_sync_on_rtu_connect()`. |

**Estimated scope:** ~50 lines C (mostly wiring existing functions).

### Phase 3: RTU Verification (Water-Treat — RTU team)

**Action required from RTU team:**

1. Verify `user_sync.c` record handler is registered for index `0xF840` in the p-net application ready callback
2. Verify NV storage backend (`user_sync_set_nv_backend()`) is initialized with working read/write/flush functions for the ODROID's storage
3. Verify `auth_authenticate()` checks synced users before local DB
4. Test: send a record write with a known test payload and verify TUI login works with synced credentials
5. Verify `auth_awaiting_controller_sync()` displays correctly on TUI when no synced users exist

**Test procedure for RTU team:**
```bash
# On controller (after Phase 1 + 2):
# 1. Create a test user via web UI with sync_to_rtus=True
# 2. Verify RTU receives the record write (check p-net debug log)
# 3. On RTU TUI, login with the synced credentials
# 4. Kill controller, verify RTU TUI still authenticates from NV storage
# 5. Reboot RTU, verify NV-stored credentials survive reboot
```

---

## 8. Testing Strategy

### Unit Tests

| Test | Location | Validates |
|------|----------|-----------|
| `test_users_sync_trigger_on_create` | `web/api/tests/test_users.py` | User create with `sync_to_rtus=True` triggers SHM command |
| `test_users_sync_trigger_on_update` | `web/api/tests/test_users.py` | User update triggers SHM command |
| `test_users_sync_trigger_on_delete` | `web/api/tests/test_users.py` | User delete triggers SHM command |
| `test_users_sync_no_trigger_when_false` | `web/api/tests/test_users.py` | User create with `sync_to_rtus=False` does NOT trigger |
| `test_users_sync_failure_nonfatal` | `web/api/tests/test_users.py` | CRUD succeeds even when SHM client unavailable |
| `test_users_sync_endpoint_manual` | `web/api/tests/test_users.py` | `POST /sync` returns correct response |
| `test_users_sync_endpoint_rtu_offline` | `web/api/tests/test_users.py` | `POST /sync/{station}` returns 503 when RTU offline |

### Integration Tests

| Test | Validates |
|------|-----------|
| API → SHM → C Controller → PROFINET record write | End-to-end command delivery |
| RTU connect → auto-sync trigger | Credentials pushed on connection |
| User delete → full sync → RTU removes user | Deleted users cannot authenticate on RTU |

### Cross-System Test (requires both teams)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Create user `testop` (operator, sync=true) via web UI | User appears in DB |
| 2 | Observe RTU p-net log | Record write at 0xF840, 1 user in payload |
| 3 | Login as `testop` on RTU TUI | Authentication succeeds |
| 4 | Change `testop` password via web UI | New record write to RTU |
| 5 | Login with old password on RTU TUI | Authentication fails |
| 6 | Login with new password on RTU TUI | Authentication succeeds |
| 7 | Delete `testop` via web UI | Record write with 0 users matching `testop` |
| 8 | Login as `testop` on RTU TUI | Authentication fails |
| 9 | Reboot RTU | NV storage cleared of `testop` |
| 10 | Disconnect controller, login as `admin` on RTU | Local fallback works |

---

## 9. Open Questions for RTU Team

1. **NV storage backend**: Is `user_sync_set_nv_backend()` currently wired to a real storage driver on the ODROID? Or is it using RAM-only? If RAM-only, synced users are lost on reboot.

2. **p-net record write handler**: Is the `IODWriteInd` callback for index `0xF840` registered in the p-net application? The code exists in `user_sync.c` but may not be connected to the p-net callback table.

3. **TUI authentication priority**: Does `auth_authenticate()` check synced users first, then local DB? Or the reverse? The design intent is synced-first (controller is authoritative when available).

4. **Maximum users**: The wire protocol supports 16 users. Is this sufficient for your deployment? If not, the record can be extended (but PROFINET acyclic writes have a 64KB limit, so practical max is ~650 users).

5. **Role mapping**: The controller uses 3 roles (viewer/operator/admin). The RTU uses 4 (viewer/operator/engineer/admin). The current mapping is `engineer → operator` on the RTU side. Is this acceptable?

---

## Appendix A: Existing Code References

| File | Purpose |
|------|---------|
| **Controller** | |
| `src/user/user_sync.h` | Sync manager API: serialize, send, callbacks |
| `src/user/user_sync.c` | DJB2 hash, CRC16, PROFINET record write, auto-sync |
| `src/ipc/ipc_server.h` | SHM_CMD_USER_SYNC (14), SHM_CMD_USER_SYNC_ALL (15) |
| `src/ipc/ipc_server.c` | `handle_user_sync_command()` — reads SHM, calls user_sync |
| `web/api/shm_client.py` | Python SHM client: `sync_users_to_rtu()`, `sync_users_to_all_rtus()` |
| `web/api/app/api/v1/users.py` | User CRUD API (sync trigger goes here) |
| `web/api/app/persistence/users.py` | `get_users_for_sync()` — query users with flag |
| `shared/include/user_sync_protocol.h` | Wire format shared between controller and RTU |
| **RTU** | |
| `src/auth/auth.c` | Core auth: local DB, session, DJB2 verify |
| `src/auth/user_sync.c` | Record handler, NV persistence, deserialization |
| `src/tui/pages/page_login.c` | TUI login screen (ncurses) |

## Appendix B: Wire Protocol Quick Reference

See [CROSS_SYSTEM.md Part 5](CROSS_SYSTEM.md) for complete specification.

```
Record Index: 0xF840 (vendor-specific)
Header:       12 bytes (version, count, CRC16, timestamp, nonce)
Per User:     100 bytes (username[32], hash[64], role, flags, reserved[2])
Max Users:    16
Max Payload:  1612 bytes
Hash:         DJB2 with salt "NaCl4Life", format "DJB2:%08X:%08X"
CRC:          CRC16-CCITT (poly 0x1021, init 0xFFFF) over user records
```
