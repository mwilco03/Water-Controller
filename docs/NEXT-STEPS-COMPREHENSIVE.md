# Water-Controller HMI - Comprehensive Next Steps

## Executive Summary

This document outlines the remaining implementation work needed to bring the Water-Controller HMI to production readiness. Priority areas include the onboarding wizard flow, RTU lifecycle management, operator feedback improvements, and PROFINET diagnostics.

---

## 1. ONBOARDING WIZARD FLOW

### Current State
The `/wizard` page exists with 7 steps but needs verification of end-to-end functionality.

### Required Work

#### 1.1 Wizard Step Validation
Verify each step works correctly:

| Step | Page | Function | Verify |
|------|------|----------|--------|
| 1. Welcome | Introduction | Show system overview | Navigation to step 2 |
| 2. Add RTU | Form entry | Collect station_name, IP, slot_count | Validation, API call to POST /api/v1/rtus |
| 3. Connect | PROFINET AR | Establish connection | Call POST /api/v1/rtus/{name}/connect, show status |
| 4. Discover | Sensor scan | I2C/1-Wire discovery | Call POST /api/v1/rtus/{name}/discover, display found sensors |
| 5. Configure | Tag setup | Name sensors, set scaling/alarms | PUT /api/v1/rtus/{name}/slots/{slot} for each |
| 6. Test | Communication check | Verify read/write works | POST /api/v1/rtus/{name}/test, show results |
| 7. Complete | Summary | Show what was configured | Link to RTU detail page |

#### 1.2 Missing Features to Add
```
- [ ] Progress persistence (resume wizard if browser closed)
- [ ] Back button works at each step
- [ ] Error handling with retry option at each step
- [ ] Skip optional steps (e.g., skip discovery if manual config)
- [ ] Bulk sensor configuration template
- [ ] Import config from existing RTU
```

#### 1.3 Entry Points
Add wizard access from:
- Dashboard: "Add First RTU" button when no RTUs exist
- RTUs page: "Add RTU" button in header
- Settings: Quick setup section

---

## 2. RTU LIFECYCLE MANAGEMENT

### 2.1 Adding RTUs

#### Manual Add Flow
```
User clicks "Add RTU" → Modal form → Validate IP uniqueness →
POST /api/v1/rtus → Show in list as OFFLINE →
User clicks "Connect" → POST /connect → Status changes to CONNECTING → RUNNING
```

**Required UI Elements:**
- Add RTU modal with fields: station_name, ip_address, vendor_id, device_id, slot_count
- IP address validation (format + ping check optional)
- Station name uniqueness check
- Duplicate IP warning

#### Discovery Add Flow
```
User clicks "Scan Network" → POST /api/v1/discover/rtu →
Show discovered devices list → User selects device →
Pre-fill form with discovered info → Continue manual add flow
```

**Required UI Elements:**
- Network scan button with progress indicator
- Discovered devices table (IP, MAC, Vendor, Device ID)
- "Add" button per discovered device
- Filter already-added devices from list

### 2.2 Removing RTUs

#### Delete Flow with Cascading Cleanup
```
User clicks "Delete RTU" → Show confirmation modal with impact summary →
User confirms → DELETE /api/v1/rtus/{name} →
Backend cascades: slots, sensors, controls, alarms, historian tags
```

**Confirmation Modal Must Show:**
```
┌─────────────────────────────────────────────────────┐
│ Delete RTU: WaterPlant1                             │
├─────────────────────────────────────────────────────┤
│ This will permanently delete:                       │
│                                                     │
│   • 4 slot configurations                           │
│   • 12 sensor definitions                           │
│   • 6 control definitions                           │
│   • 3 active alarms                                 │
│   • 2 PID loops referencing this RTU                │
│   • 1,234 historian samples                         │
│                                                     │
│ This action cannot be undone.                       │
│                                                     │
│ Type "WaterPlant1" to confirm: [______________]     │
│                                                     │
│                    [Cancel]  [Delete]               │
└─────────────────────────────────────────────────────┘
```

**Backend must return cleanup stats:**
```json
{
  "deleted": {
    "slots": 4,
    "sensors": 12,
    "controls": 6,
    "alarms": 3,
    "pid_loops": 2,
    "historian_samples": 1234
  }
}
```

### 2.3 RTU State Machine

```
                    ┌─────────────┐
                    │   OFFLINE   │ ← Initial state after add
                    └──────┬──────┘
                           │ connect()
                           ▼
                    ┌─────────────┐
         ┌─────────│ CONNECTING  │
         │         └──────┬──────┘
         │                │ AR established
         │                ▼
         │         ┌─────────────┐
         │         │  DISCOVERY  │ ← Optional: auto-discover sensors
         │         └──────┬──────┘
         │                │ discovery complete
         │                ▼
         │         ┌─────────────┐
    timeout/       │   RUNNING   │ ← Normal operation
    error          └──────┬──────┘
         │                │ disconnect() or error
         │                ▼
         │         ┌─────────────┐
         └────────▶│    ERROR    │
                   └──────┬──────┘
                          │ reconnect()
                          ▼
                   (back to CONNECTING)
```

**UI State Indicators:**
| State | Color | Icon | Actions Available |
|-------|-------|------|-------------------|
| OFFLINE | Gray | ○ | Connect, Delete |
| CONNECTING | Yellow (pulsing) | ◐ | Cancel, Delete |
| DISCOVERY | Blue (pulsing) | ◑ | Cancel |
| RUNNING | Green | ● | Disconnect, View, Delete |
| ERROR | Red | ✕ | Reconnect, View Logs, Delete |

---

## 3. COUPLED ACTIONS INDICATOR

### 3.1 What Are Coupled Actions?
When an operator action triggers automated responses:
- Turning on Pump 1 → VFD ramps up → Discharge valve opens
- High level alarm → Auto-start drain pump → Alarm suppression
- Mode change AUTO → PID takes control → Setpoint becomes active

### 3.2 Required Implementation

#### Backend: Track Action Chains
```python
# When command is sent, return coupled actions
POST /api/v1/rtus/{name}/control/{id}
Response:
{
  "command": "ON",
  "result": "success",
  "coupled_actions": [
    {"type": "interlock", "name": "IL-001", "action": "enabled", "delay_ms": 0},
    {"type": "actuator", "name": "DV-101", "action": "OPEN", "delay_ms": 500},
    {"type": "pid", "name": "FC-001", "action": "setpoint_active", "delay_ms": 1000}
  ]
}
```

#### Frontend: Show Coupled Actions Timeline
```
┌─────────────────────────────────────────────────────────────────┐
│ Command Executed: Pump 1 → ON                                   │
├─────────────────────────────────────────────────────────────────┤
│ Coupled Actions:                                                │
│                                                                 │
│ ├── 0ms    ✓ Interlock IL-001 enabled                          │
│ ├── 500ms  ✓ Valve DV-101 opening...                           │
│ └── 1000ms ○ PID FC-001 setpoint will activate                 │
│                                                                 │
│ [Close]                                                         │
└─────────────────────────────────────────────────────────────────┘
```

#### Visual Linking in UI
On RTU detail page, show connections:
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Pump 1     │────▶│  Valve 1    │────▶│  PID Loop   │
│  [ON/OFF]   │     │  [Linked]   │     │  [Linked]   │
└─────────────┘     └─────────────┘     └─────────────┘
     │
     └──────────────────────────────────┐
                                        ▼
                               ┌─────────────────┐
                               │ Interlock IL-001│
                               │ [Monitoring]    │
                               └─────────────────┘
```

---

## 4. PROFINET DIAGNOSTICS DISPLAY

### 4.1 Required Data to Display

#### Connection Health
```
┌─────────────────────────────────────────────────────────────────┐
│ PROFINET Connection: WaterPlant1                                │
├─────────────────────────────────────────────────────────────────┤
│ Status: RUNNING                     AR Handle: 0x1234           │
│ Uptime: 5d 12h 34m                  Session: 00:45:23           │
│                                                                 │
│ Communication Statistics:                                       │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Cycle Time:     1.0 ms (target) / 1.02 ms (actual)        │  │
│ │ Packet Loss:    0.001% (12 of 1,234,567 frames)           │  │
│ │ Jitter:         ±0.15 ms                                   │  │
│ │ Last Error:     None                                       │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│ I/O Data:                                                       │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Input Bytes:    64 bytes  (Slot 1-4)                      │  │
│ │ Output Bytes:   32 bytes  (Slot 1-4)                      │  │
│ │ Last Update:    < 1 second ago                            │  │
│ │ Data Quality:   GOOD (0x00)                               │  │
│ └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

#### Slot-Level Diagnostics
```
┌─────────────────────────────────────────────────────────────────┐
│ Slot Configuration                                              │
├──────┬────────────┬────────────┬──────────┬──────────┬─────────┤
│ Slot │ Module     │ Subslot    │ I/O Type │ Bytes    │ Status  │
├──────┼────────────┼────────────┼──────────┼──────────┼─────────┤
│ 1    │ 0x0001     │ 1          │ Input    │ 16       │ ● OK    │
│ 2    │ 0x0002     │ 1          │ Input    │ 16       │ ● OK    │
│ 3    │ 0x0003     │ 1          │ Output   │ 8        │ ● OK    │
│ 4    │ 0x0004     │ 1          │ Output   │ 8        │ ○ Empty │
└──────┴────────────┴────────────┴──────────┴──────────┴─────────┘
```

#### Alarm/Diagnostic Messages
```
┌─────────────────────────────────────────────────────────────────┐
│ PROFINET Diagnostics (Last 24h)                                 │
├─────────────────────────────────────────────────────────────────┤
│ 14:32:15  [INFO]  AR established with WaterPlant1               │
│ 14:32:16  [INFO]  Parameter end received, I/O active            │
│ 09:15:02  [WARN]  Packet loss exceeded 0.01% threshold          │
│ 09:15:05  [INFO]  Packet loss recovered to normal               │
│ Yesterday [ERROR] Connection lost - cable disconnect            │
│ Yesterday [INFO]  Connection restored after 5.2 seconds         │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Backend API Requirements

```
GET /api/v1/rtus/{name}/profinet/status
{
  "ar_handle": "0x1234",
  "state": "DATA_EXCHANGE",
  "uptime_seconds": 475234,
  "session_seconds": 2723,
  "cycle_time_target_ms": 1.0,
  "cycle_time_actual_ms": 1.02,
  "packet_loss_percent": 0.001,
  "packets_sent": 1234567,
  "packets_lost": 12,
  "jitter_ms": 0.15,
  "input_bytes": 64,
  "output_bytes": 32,
  "last_update_ms": 50,
  "data_quality": "GOOD"
}

GET /api/v1/rtus/{name}/profinet/slots
[
  {"slot": 1, "module_id": "0x0001", "subslot": 1, "io_type": "input", "bytes": 16, "status": "OK"},
  {"slot": 2, "module_id": "0x0002", "subslot": 1, "io_type": "input", "bytes": 16, "status": "OK"},
  ...
]

GET /api/v1/rtus/{name}/profinet/diagnostics?hours=24
[
  {"timestamp": "2024-01-15T14:32:15Z", "level": "INFO", "message": "AR established"},
  ...
]
```

---

## 5. ADDITIONAL UI IMPROVEMENTS

### 5.1 Stale Data Indicator (GAP-04)
Add "last updated X seconds ago" to:
- Dashboard sensor values
- RTU detail page sensors
- Trends current value

```typescript
// Component: StaleIndicator.tsx
function StaleIndicator({ lastUpdate }: { lastUpdate: Date }) {
  const [age, setAge] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setAge(Math.floor((Date.now() - lastUpdate.getTime()) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [lastUpdate]);

  if (age < 5) return <span className="text-green-500">Live</span>;
  if (age < 30) return <span className="text-yellow-500">{age}s ago</span>;
  return <span className="text-red-500">{age}s ago (stale)</span>;
}
```

### 5.2 Keyboard Shortcuts (GAP-05)
| Shortcut | Action |
|----------|--------|
| `Ctrl+A` | Go to Alarms |
| `Ctrl+D` | Go to Dashboard |
| `Ctrl+R` | Go to RTUs |
| `Ctrl+T` | Go to Trends |
| `Ctrl+M` | Enter Command Mode |
| `Escape` | Close modal / Exit Command Mode |
| `Enter` | Acknowledge focused alarm |

### 5.3 Trend Export (GAP-06)
Add to trends page:
- Export to CSV button
- Export to PDF button
- Date range selection for export
- Include metadata (RTU, sensor, time range)

---

## 6. TESTING REQUIREMENTS

### 6.1 End-to-End Scenarios to Test

| Scenario | Steps | Expected Result |
|----------|-------|-----------------|
| First-time setup | Open app → Wizard → Add RTU → Connect → Discover → Configure → Test | RTU shows in list as RUNNING |
| RTU disconnect | Unplug RTU network cable | Status changes to ERROR within 10s, alarms raised |
| RTU reconnect | Reconnect cable | Auto-reconnects, status → RUNNING, alarms clear |
| Delete RTU with data | Delete RTU with historian data | All related data cleaned up, no orphans |
| Alarm shelving | Shelve alarm for 1h | Alarm hidden, auto-returns after 1h |
| Control with confirm | Turn on pump | Confirmation modal shown, command executes on confirm |
| Command mode timeout | Enter command mode, wait 5 min | Auto-exits to view mode |

### 6.2 Browser Compatibility
Test on:
- Chrome (latest)
- Firefox (latest)
- Edge (latest)
- Safari (latest)
- Chrome on iPad

### 6.3 Performance Targets
| Metric | Target |
|--------|--------|
| Page load | < 2s |
| WebSocket update | < 100ms latency |
| Alarm display | < 500ms from raise to UI |
| Control response | < 1s from click to state change |

---

## 7. IMPLEMENTATION PRIORITY

### Phase 1: Core Functionality (Must Have)
1. RTU Add/Delete with confirmation
2. Wizard flow verification
3. Stale data indicators
4. PROFINET status display

### Phase 2: Enhanced UX (Should Have)
1. Coupled actions display
2. Keyboard shortcuts
3. Trend export

### Phase 3: Polish (Nice to Have)
1. PROFINET detailed diagnostics
2. Bulk RTU operations
3. Configuration templates

---

## 8. FILES TO MODIFY/CREATE

### Frontend
```
src/app/wizard/page.tsx           - Verify/fix wizard flow
src/app/rtus/page.tsx             - Add delete confirmation, discovery UI
src/app/rtus/[name]/page.tsx      - Add PROFINET diagnostics tab
src/components/DeleteRtuModal.tsx - New: cascading delete confirmation
src/components/CoupledActions.tsx - New: action chain display
src/components/StaleIndicator.tsx - New: data age display
src/components/ProfinetStatus.tsx - New: connection diagnostics
src/hooks/useKeyboardShortcuts.ts - New: global shortcuts
src/lib/api.ts                    - Add PROFINET endpoints
```

### Backend
```
web/api/main.py                   - Add PROFINET status endpoints
web/api/db_persistence.py         - Add cascade delete stats
```

---

*Document Version: 1.0*
*Created: 2025-12-23*
