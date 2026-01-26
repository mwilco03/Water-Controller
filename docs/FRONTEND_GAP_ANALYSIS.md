# Frontend Gap Analysis

**Date:** 2026-01-26
**Scope:** `/web/ui` - Next.js 14 HMI Frontend
**Total Files:** 107 TypeScript/React files

---

## Executive Summary

The frontend is **70% functional** with core SCADA workflows operational. However, there are significant gaps:

- **2 pages are disabled stubs** (Users, I/O Tags)
- **3 hooks are duplicated/redundant**
- **Settings page duplicates** most of Modbus page functionality
- **Several backend APIs have no frontend UI**
- **Control couplings panel exists but isn't wired into any page**

---

## 1. PAGE STATUS AUDIT

### Fully Functional Pages (8)

| Page | Route | Status | Notes |
|------|-------|--------|-------|
| Home/Dashboard | `/` | **Working** | RTU cards, alarms, shift handoff |
| Alarms | `/alarms` | **Working** | ISA-18.2 shelving, history, insights |
| Control | `/control` | **Working** | PID loops, setpoint editing, mode switching |
| RTU List | `/rtus` | **Working** | Add/delete, discovery, health |
| RTU Detail | `/rtus/[name]` | **Working** | Sensors, controls, PROFINET diagnostics |
| Trends | `/trends` | **Working** | Historical charts, export to CSV/JSON/Excel |
| System | `/system` | **Working** | Health, logs, audit trail, diagnostics |
| Wizard | `/wizard` | **Working** | RTU onboarding flow |

### Functional but Redundant Pages (2)

| Page | Route | Status | Notes |
|------|-------|--------|-------|
| Network | `/network` | **Working** | IP config, interfaces - **but rarely used in Docker deployments** |
| Modbus | `/modbus` | **Working** | Full CRUD for server, mappings, downstream - **duplicated in Settings** |

### Disabled/Stub Pages (2)

| Page | Route | Status | Missing Backend |
|------|-------|--------|-----------------|
| Users | `/users` | **STUB** | Needs `/api/v1/users` CRUD endpoints |
| I/O Tags | `/io-tags` | **STUB** | Old slots API removed; needs refactor to use sensors/controls API |

### Settings Page - Consolidation Candidate

The Settings page (`/settings`) has **6 tabs** that duplicate other pages:

| Tab | Duplicates |
|-----|------------|
| General | Unique (config import/export) |
| Backup & Restore | Unique |
| **Modbus Gateway** | **100% duplicates `/modbus` page** |
| Log Forwarding | Unique (external log destinations) |
| Services | Unique (start/stop/restart) |
| Simulation Mode | Unique (demo mode scenarios) |

**Recommendation:** Remove Modbus tab from Settings OR remove standalone `/modbus` page.

---

## 2. CONSOLIDATION OPPORTUNITIES

### 2.1 Duplicate Hooks

| Hook | Location | Issue |
|------|----------|-------|
| `useRTUs.ts` | `/hooks/useRTUs.ts` | **Superseded** by `useRTUStatusData.ts` |
| `useRTUStatusData.ts` | `/hooks/useRTUStatusData.ts` | Current primary - fetches RTUs + alarms + WebSocket |

**Action:** Delete `useRTUs.ts` and migrate any remaining usages.

### 2.2 Duplicate Modbus Configuration

Settings page Modbus tab calls:
- `/api/v1/modbus/server/config`
- `/api/v1/modbus/devices`

Modbus page calls:
- `/api/v1/modbus/server`
- `/api/v1/modbus/downstream`
- `/api/v1/modbus/mappings`
- `/api/v1/modbus/stats`

**These are different API endpoints with similar purposes.** Backend API inconsistency.

### 2.3 Component Duplication

| Component Pattern | Instances | Action |
|-------------------|-----------|--------|
| Modal wrappers | `Modal.tsx`, `ConfirmModal.tsx`, `ConfirmDialog.tsx` | Consolidate to 1 generic + 1 confirm |
| Status badges | `RtuStateBadge`, `SystemStatusIndicator`, `ConnectionStatusIndicator`, `DataQualityIndicator` | Keep - each has different semantics |
| Form inputs | Good - single `forms/` directory | No action |

---

## 3. UNUSED/ORPHANED COMPONENTS

### 3.1 Components Not Wired to Any Page

| Component | Location | Status |
|-----------|----------|--------|
| `CoupledActionsPanel.tsx` | `/components/control/` | **EXISTS but NOT used anywhere** |
| `MaintenanceScheduler.tsx` | `/components/hmi/` | **EXISTS but NOT used anywhere** |
| `ShiftHandoff.tsx` | `/components/hmi/` | Used on home page only |

**CoupledActionsPanel** - This displays PID→control, interlock→control, control→control relationships. The backend `/api/v1/control/couplings` exists but:
- No page includes this panel
- No way to CREATE couplings from UI (only view)
- Should be added to `/control` page

**MaintenanceScheduler** - Backend has `/api/v1/alarms/maintenance` for scheduled maintenance windows but:
- No UI to schedule maintenance
- Alarms page could have this added

### 3.2 API Endpoints Without UI

| Backend Endpoint | Purpose | Frontend Coverage |
|------------------|---------|-------------------|
| `POST /api/v1/control/couplings` | Create control couplings | **NONE** |
| `DELETE /api/v1/control/couplings/{id}` | Delete couplings | **NONE** |
| `POST /api/v1/alarms/maintenance` | Schedule maintenance | **NONE** |
| `DELETE /api/v1/alarms/maintenance/{id}` | Cancel maintenance | **NONE** |
| `POST /api/v1/rtus/{name}/provision` | Provision sensors from discovery | Used only in Wizard |
| `POST /api/v1/rtus/{name}/pid/{id}/auto-tune` | PID auto-tuning | **NONE** |
| `GET /api/v1/trends/optimized` | Optimized trend query | **NONE** |
| `POST /api/v1/trends/export` | Server-side trend export | **NONE** (client-side used) |
| `GET /api/v1/users` | User management | **STUB PAGE** |
| `POST /api/v1/templates` | Configuration templates | **NONE** |
| `POST /api/v1/templates/{id}/apply` | Apply template | **NONE** |
| `GET /api/v1/metrics/json` | Prometheus metrics | **NONE** |

---

## 4. WORKFLOW ISSUES

### 4.1 RTU Onboarding Flow Gaps

**Current Wizard Flow:**
1. Enter IP address ✓
2. Add RTU ✓
3. Connect ✓
4. Discover sensors (I2C/1-Wire scan) ✓
5. Configure sensors ✓
6. Run test ✓
7. Complete ✓

**Missing:**
- No way to discover PROFINET modules (only I2C/1-Wire)
- `POST /rtus/{name}/discover` endpoint exists but wizard uses different discovery
- No historian tag creation during wizard (checkbox exists but may not work)
- No alarm rule creation during wizard

### 4.2 Alarm Acknowledgment Workflow

**Current:**
- Can ack single alarm
- Can ack all alarms
- Can shelve alarms (ISA-18.2)

**Missing:**
- No confirmation dialog for "Ack All" (dangerous operation)
- No filtering before bulk ack (e.g., "ack all LOW priority")

### 4.3 Control Command Workflow

**Current:**
- Requires Command Mode login ✓
- 4-hour session timeout ✓
- Confirmation dialog for commands ✓

**Missing:**
- No idempotency key sent (backend supports it, UI doesn't use it)
- No ramp time option for analog commands (VFD speed changes)
- No interlock visibility before command (shows AFTER failure only)

### 4.4 Trends Workflow

**Current:**
- Multi-tag selection ✓
- Time range selector ✓
- Export to CSV/JSON/Excel ✓
- WebSocket real-time updates ✓

**Missing:**
- No date picker for custom range (only presets: 1h, 6h, 24h, 7d, 30d)
- No trend annotations (mark events on chart)
- No comparison mode (overlay same tag from different time periods)

---

## 5. SENSORS & ACTUATORS - WIRING STATUS

### 5.1 Schema-Defined Sensors (12 types)

| Sensor Type | Schema | Backend API | Frontend Display |
|-------------|--------|-------------|------------------|
| pH | ✓ | ✓ | ✓ RTU detail |
| Temperature | ✓ | ✓ | ✓ RTU detail |
| Turbidity | ✓ | ✓ | ✓ RTU detail |
| TDS | ✓ | ✓ | ✓ RTU detail |
| Dissolved Oxygen | ✓ | ✓ | ✓ RTU detail |
| Flow Rate | ✓ | ✓ | ✓ RTU detail |
| Level | ✓ | ✓ | ✓ RTU detail |
| Pressure | ✓ | ✓ | ✓ RTU detail |
| Conductivity | ✓ | ✓ | ✓ RTU detail |
| ORP | ✓ | ✓ | ✓ RTU detail |
| Chlorine | ✓ | ✓ | ✓ RTU detail |
| Custom | ✓ | ✓ | ✓ RTU detail |

**All sensor types are properly wired.** Display uses `SensorDisplay.tsx` and `SensorList.tsx`.

### 5.2 Schema-Defined Actuators (6 types)

| Actuator Type | Schema | Backend API | Frontend Control |
|---------------|--------|-------------|------------------|
| Relay (ON/OFF) | ✓ | ✓ | ✓ ControlWidget |
| PWM (0-255) | ✓ | ✓ | **PARTIAL** - UI shows toggle, not slider |
| Pump | ✓ | ✓ | ✓ ControlWidget |
| Valve | ✓ | ✓ | ✓ ControlWidget |
| Latching Relay | ✓ | ✓ | ✓ ControlWidget |
| Momentary Output | ✓ | ✓ | ✓ ControlWidget |

**Issue:** PWM controls show as toggle buttons. Need slider/numeric input for PWM duty cycle (0-255).

### 5.3 Hanging Backend Features

| Feature | Backend | Frontend |
|---------|---------|----------|
| Analog ramp time | `ramp_seconds` param | **NOT EXPOSED** |
| Idempotency keys | `idempotency_key` param | **NOT USED** |
| Interlock status | `interlock_active` field | Shown only after command fails |
| PWM duty cycle | `commanded_value` 0-255 | **Toggle only, no slider** |
| Control mode (AUTO/MANUAL) | Mode field | **NOT SHOWN** |

### 5.4 Hanging Frontend Features

| Feature | Frontend | Backend |
|---------|----------|---------|
| Coupled Actions Panel | Component exists | API exists but **panel not used** |
| Maintenance Scheduler | Component exists | API exists but **panel not used** |
| PID Auto-Tune button | **MISSING** | API exists |
| User Management | Stub page | **API MISSING** |
| I/O Tag editor | Stub page | Old API removed |

---

## 6. RECOMMENDATIONS

### 6.1 Immediate (High Priority)

1. **Remove `useRTUs.ts` hook** - redundant with `useRTUStatusData.ts`
2. **Add CoupledActionsPanel to Control page** - feature exists, just not wired
3. **Add MaintenanceScheduler to Alarms page** - feature exists, just not wired
4. **Fix PWM controls** - add slider input for duty cycle 0-255
5. **Consolidate Modbus configuration** - choose Settings OR standalone page

### 6.2 Short-Term (Medium Priority)

1. **Implement I/O Tags page** using sensors/controls API (not old slots API)
2. **Add PID Auto-Tune button** to Control page
3. **Add custom date range picker** to Trends page
4. **Add interlock status display** to ControlWidget (before attempting command)
5. **Send idempotency keys** in control commands for retry safety

### 6.3 Long-Term (Lower Priority)

1. **Implement User Management** - requires backend endpoints
2. **Add ramp time option** for analog control commands
3. **Add trend annotations** for event marking
4. **Add configuration templates UI** - backend exists
5. **Add Prometheus metrics viewer** - backend exists

---

## 7. COMPONENT INVENTORY

### 7.1 Used Components (Healthy)

```
/components/hmi/
├── ActionBar.tsx          ✓ Used in RTU detail
├── AlarmBanner.tsx        ✓ Used in layout
├── AlarmInsights.tsx      ✓ Used in Alarms page
├── AuthenticationModal    ✓ Used globally
├── BottomNavigation.tsx   ✓ Used in layout (mobile)
├── ConfirmDialog.tsx      ✓ Used everywhere
├── ConnectionStatus       ✓ Used in layout
├── ControlGuard.tsx       ✓ Wraps control actions
├── DataQualityIndicator   ✓ Used with sensor values
├── DataTable.tsx          ✓ Used in multiple pages
├── DegradedModeBanner     ✓ Used in layout
├── EmptyState.tsx         ✓ Used when no data
├── ErrorMessage.tsx       ✓ Used on errors
├── GlobalStatusBar.tsx    ✓ Used in layout
├── LiveTimestamp.tsx      ✓ Used in header
├── MetricCard.tsx         ✓ Used on dashboard
├── Modal.tsx              ✓ Used everywhere
├── QuickControlPanel.tsx  ✓ Used on dashboard
├── RTUStatusCard.tsx      ✓ Used on dashboard
├── SessionIndicator.tsx   ✓ Used in header
├── SideNav.tsx            ✓ Used in layout
├── Skeleton.tsx           ✓ Used during loading
├── Sparkline.tsx          ✓ Used in cards
├── StatusHeader.tsx       ✓ Used on pages
├── SystemStatusBar.tsx    ✓ Used in layout
├── Toast.tsx              ✓ Used globally
├── ValueDisplay.tsx       ✓ Used with sensors

/components/rtu/
├── AddRtuModal.tsx        ✓ Used in RTU list
├── BulkOperationsPanel    ✓ Used in RTU list
├── ControlList.tsx        ✓ Used in RTU detail
├── ControlWidget.tsx      ✓ Used in RTU detail
├── DeleteRtuModal.tsx     ✓ Used in RTU list
├── DiscoveryPanel.tsx     ✓ Used in RTU list
├── InventoryRefresh.tsx   ✓ Used in RTU detail
├── ProfinetDiagnostics    ✓ Used in RTU detail
├── ProfinetStatus.tsx     ✓ Used in RTU detail
├── RTUCard.tsx            ✓ Used on dashboard
├── RtuStateIndicator      ✓ Used everywhere
├── SensorDisplay.tsx      ✓ Used in RTU detail
├── SensorList.tsx         ✓ Used in RTU detail
├── StaleIndicator.tsx     ✓ Used with old data
```

### 7.2 Unused Components (Need Wiring)

```
/components/hmi/
├── MaintenanceScheduler.tsx    ✗ NOT WIRED
├── ShiftHandoff.tsx            ~ Used only on dashboard

/components/control/
├── CoupledActionsPanel.tsx     ✗ NOT WIRED
```

---

## 8. FILE SIZE CONCERNS

| File | Lines | Concern |
|------|-------|---------|
| `/app/settings/page.tsx` | 1258 | **Too large** - should split into sub-components |
| `/app/modbus/page.tsx` | 1115 | **Too large** - lots of modal UI inline |
| `/lib/api.ts` | 687 | Acceptable for API client |
| `/app/system/page.tsx` | 930 | Borderline - has 4 tabs inline |
| `/app/wizard/page.tsx` | 904 | Borderline - has 7 steps inline |

---

## 9. CONCLUSION

The frontend is **production-ready for core SCADA operations** (monitoring, alarms, basic control). The main gaps are:

1. **User management** - requires backend implementation
2. **Advanced control features** - couplings, auto-tune, ramp time
3. **Maintenance scheduling** - UI component exists but not wired
4. **PWM control type** - needs proper slider input

The codebase is well-organized with clear separation of concerns. Most gaps are due to backend API changes or features that exist but weren't integrated into pages.
