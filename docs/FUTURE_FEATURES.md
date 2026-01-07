# Future Feature Planning

This document outlines planned features for future development of the Water Treatment Controller.

---

## Recipe Management System

### Overview

A batch/recipe control system (ISA-88 compliant) for executing predefined sequences of operations in water treatment processes.

### Use Cases

| Use Case | Description |
|----------|-------------|
| Chemical Dosing | Automated coagulant/polymer dosing sequences based on jar test results |
| Filter Backwash | Timed valve sequences with flow verification for filter cleaning |
| CIP Procedures | Membrane cleaning with multi-step chemical sequences |
| Plant Startup | Coordinated startup of treatment trains |
| Plant Shutdown | Safe shutdown sequences with proper order of operations |

### Proposed Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Recipe Management                       │
├─────────────────────────────────────────────────────────────┤
│  Recipe Library                                             │
│  ├── Recipe Definition (procedure + default parameters)    │
│  ├── Version Control (approval workflow)                   │
│  └── Categories (dosing, backwash, CIP, startup)           │
├─────────────────────────────────────────────────────────────┤
│  Formula Manager                                            │
│  ├── Parameter Sets (specific values for a recipe)         │
│  ├── Site-Specific Adjustments                             │
│  └── Seasonal Variations                                   │
├─────────────────────────────────────────────────────────────┤
│  Batch Executor                                             │
│  ├── Unit Allocation (assign recipe to equipment)          │
│  ├── Step Sequencing (execute procedure steps)             │
│  ├── Parameter Prompts (operator input at runtime)         │
│  └── Batch Records (audit trail of execution)              │
├─────────────────────────────────────────────────────────────┤
│  Integration with Existing Systems                          │
│  ├── Sequence Engine (step execution)                      │
│  ├── Control Engine (PID/actuator commands)                │
│  ├── Alarm Manager (batch-related alarms)                  │
│  └── Historian (batch event logging)                       │
└─────────────────────────────────────────────────────────────┘
```

### Data Model

```python
# Recipe definition
class Recipe:
    recipe_id: int
    name: str
    version: str
    category: str  # dosing, backwash, cip, startup, shutdown
    description: str
    procedure: list[RecipeStep]
    default_parameters: dict[str, Parameter]
    approval_status: str  # draft, pending_review, approved
    approved_by: str
    approved_at: datetime

# Recipe step
class RecipeStep:
    step_number: int
    action: str  # set_output, wait_condition, wait_time, prompt_operator
    target_rtu: str
    target_slot: int
    value: float | str
    condition: str  # optional, for wait_condition
    timeout_sec: int
    on_timeout: str  # abort, skip, alarm

# Formula (parameter set for a recipe)
class Formula:
    formula_id: int
    recipe_id: int
    name: str
    parameters: dict[str, float | str]
    valid_from: datetime
    valid_to: datetime

# Batch record (execution history)
class BatchRecord:
    batch_id: int
    recipe_id: int
    formula_id: int
    start_time: datetime
    end_time: datetime
    status: str  # running, completed, aborted, failed
    operator: str
    unit_id: str
    step_log: list[StepExecution]
    parameter_values: dict[str, float]
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/recipes` | GET | List all recipes |
| `/api/v1/recipes` | POST | Create new recipe |
| `/api/v1/recipes/{id}` | GET | Get recipe details |
| `/api/v1/recipes/{id}` | PUT | Update recipe |
| `/api/v1/recipes/{id}/approve` | POST | Approve recipe for use |
| `/api/v1/formulas` | GET | List formulas |
| `/api/v1/formulas` | POST | Create formula for recipe |
| `/api/v1/batches` | GET | List batch executions |
| `/api/v1/batches` | POST | Start new batch |
| `/api/v1/batches/{id}` | GET | Get batch status |
| `/api/v1/batches/{id}/abort` | POST | Abort running batch |
| `/api/v1/batches/{id}/step` | POST | Advance to next step (manual) |

### UI Components

1. **Recipe Editor** - Visual step builder with drag-drop
2. **Formula Manager** - Parameter grid with validation
3. **Batch Launcher** - Select recipe, formula, unit, start batch
4. **Batch Monitor** - Real-time step progress with values
5. **Batch History** - Searchable log of past executions

### Implementation Steps

1. **Phase 1: Database Schema**
   - Add tables: recipes, recipe_steps, formulas, batch_records, step_executions
   - Create Alembic migrations

2. **Phase 2: Core API**
   - Recipe CRUD endpoints
   - Formula management
   - Batch execution engine

3. **Phase 3: Integration**
   - Connect to sequence_engine for step execution
   - Connect to control_engine for setpoint changes
   - Batch-related alarm rules

4. **Phase 4: UI**
   - Recipe editor page
   - Batch launcher modal
   - Batch monitoring dashboard

---

## Progressive Web App (PWA)

### Overview

Convert the existing Next.js frontend into a Progressive Web App to enable:
- **Push Notifications** - Critical alarm alerts to operators' phones
- **Offline Access** - View last-known data when network unavailable
- **Home Screen Install** - Native app-like experience without app stores

### Benefits for Water Treatment Operations

| Feature | Operator Benefit |
|---------|------------------|
| Push Notifications | On-call operators receive alarm alerts immediately |
| Offline Mode | View system status during network outages |
| Background Sync | Queue commands when offline, execute when reconnected |
| Home Screen | Quick access without opening browser |
| Full Screen | Dedicated app experience on tablets at plant |

### Technical Requirements

#### 1. Service Worker

```javascript
// sw.js - Cache critical assets and API responses
const CACHE_NAME = 'wtc-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/dashboard',
  '/alarms',
  '/rtus',
  '/offline.html',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
];

// Cache-first for assets, network-first for API
self.addEventListener('fetch', (event) => {
  if (event.request.url.includes('/api/')) {
    // Network first, fall back to cache
    event.respondWith(networkFirstStrategy(event.request));
  } else {
    // Cache first for static assets
    event.respondWith(cacheFirstStrategy(event.request));
  }
});
```

#### 2. Web App Manifest

```json
{
  "name": "Water Treatment Controller",
  "short_name": "WTC",
  "description": "Industrial SCADA for water treatment facilities",
  "start_url": "/dashboard",
  "display": "standalone",
  "background_color": "#1a1a2e",
  "theme_color": "#0f3460",
  "icons": [
    {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png"}
  ]
}
```

#### 3. Push Notification Setup

**Backend (FastAPI)**:
```python
from pywebpush import webpush

@router.post("/subscribe")
async def subscribe_push(subscription: PushSubscription, user: User = Depends(get_current_user)):
    # Store subscription in database
    await save_push_subscription(user.id, subscription)
    return {"status": "subscribed"}

async def send_alarm_notification(alarm: Alarm):
    subscriptions = await get_subscriptions_for_alarm(alarm)
    for sub in subscriptions:
        webpush(
            subscription_info=sub.dict(),
            data=json.dumps({
                "title": f"ALARM: {alarm.message}",
                "body": f"{alarm.rtu_station} - {alarm.severity}",
                "url": f"/alarms/{alarm.alarm_id}"
            }),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": "mailto:alerts@example.com"}
        )
```

**Frontend (React)**:
```typescript
// Request notification permission
async function subscribeToPush() {
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: VAPID_PUBLIC_KEY
  });
  await fetch('/api/v1/notifications/subscribe', {
    method: 'POST',
    body: JSON.stringify(subscription)
  });
}
```

#### 4. Offline Data Strategy

```typescript
// Store last-known RTU data in IndexedDB
import { openDB } from 'idb';

const db = await openDB('wtc-offline', 1, {
  upgrade(db) {
    db.createObjectStore('rtus', { keyPath: 'station_name' });
    db.createObjectStore('alarms', { keyPath: 'alarm_id' });
  }
});

// Update cache on each API response
async function fetchRTUs() {
  try {
    const response = await fetch('/api/v1/rtus');
    const rtus = await response.json();
    // Update IndexedDB cache
    for (const rtu of rtus) {
      await db.put('rtus', rtu);
    }
    return rtus;
  } catch (error) {
    // Offline - return cached data
    return await db.getAll('rtus');
  }
}
```

### Implementation Steps

1. **Phase 1: Basic PWA Setup**
   - Create `manifest.json` with app metadata
   - Add service worker for asset caching
   - Configure Next.js for PWA (next-pwa plugin)
   - Add install prompt UI

2. **Phase 2: Offline Support**
   - Implement IndexedDB storage for RTU/alarm cache
   - Add offline detection and UI indicators
   - Create offline fallback page
   - Background sync for queued commands

3. **Phase 3: Push Notifications**
   - Set up VAPID keys for web push
   - Add push subscription endpoints to API
   - Integrate with alarm manager for notification triggers
   - Create notification preferences UI

4. **Phase 4: Testing & Optimization**
   - Test on various mobile devices
   - Lighthouse PWA audit (target 90+ score)
   - Optimize cache strategies
   - Test offline scenarios

### Files to Create/Modify

| File | Changes |
|------|---------|
| `web/ui/public/manifest.json` | New - PWA manifest |
| `web/ui/public/sw.js` | New - Service worker |
| `web/ui/next.config.js` | Add PWA configuration |
| `web/ui/src/app/layout.tsx` | Add manifest link, SW registration |
| `web/ui/src/hooks/useOffline.ts` | New - Offline detection hook |
| `web/ui/src/lib/indexeddb.ts` | New - IndexedDB wrapper |
| `web/api/app/api/v1/notifications.py` | New - Push subscription API |
| `web/api/app/models/push_subscription.py` | New - Subscription model |

### Dependencies

**Frontend**:
- `next-pwa` - Next.js PWA plugin
- `idb` - IndexedDB wrapper
- `workbox-*` - Service worker libraries

**Backend**:
- `pywebpush` - Web push notifications

---

## Implementation Priority

| Feature | Priority | Effort | Dependencies |
|---------|----------|--------|--------------|
| PWA Basic (install + offline) | High | 1-2 weeks | None |
| Push Notifications | High | 1 week | PWA Basic |
| Maintenance Window Scheduling | High | 1 week | Existing shelving |
| Recipe Database Schema | Medium | 1 week | None |
| Recipe API | Medium | 2 weeks | Schema |
| Recipe UI | Medium | 2 weeks | API |
| Batch Executor | Medium | 2 weeks | Recipe API |

---

## Maintenance Window Scheduling

### Overview

Allow operators to pre-schedule alarm suppression for planned maintenance activities. This prevents alarm fatigue during known maintenance windows.

### Use Cases

| Use Case | Description |
|----------|-------------|
| Contractor Work | Suppress Pump 3 alarms from 8 AM - 4 PM tomorrow |
| Filter Maintenance | Suppress filter differential alarms during backwash |
| Calibration | Suppress sensor alarms while calibrating instruments |
| Seasonal Shutdown | Suppress system alarms during plant winterization |

### Proposed Features

1. **Scheduled Shelving** - Create shelf entries with future start times
2. **Duration Options** - Time-based (4h, 8h, 12h) or until manual release
3. **Equipment Grouping** - Shelve all alarms for a specific RTU or equipment group
4. **Work Order Integration** - Link scheduled shelves to maintenance work orders
5. **Calendar View** - Visual display of upcoming maintenance windows

### Implementation Notes

- Extends existing ISA-18.2 shelving mechanism
- Requires new API endpoints for scheduled shelves
- Should integrate with shift handoff to notify incoming operators
- Audit trail must capture who scheduled and why

---

## Explicitly Not Implementing

### Audio Notifications

**Status: Will NOT be implemented**

**Rationale:**
- Water treatment facilities are loud industrial environments
- Plant floor noise levels make browser audio alerts ineffective
- Operators wear hearing protection in many areas
- Visual indicators (flashing banners, color changes) are the industry standard
- Push notifications via PWA (phone vibration) are more practical for off-site alerting

**Alternatives in use:**
- ISA-101 compliant visual alarm banner with flashing animation
- Alarm carousel that cycles through active alarms
- Color-coded severity indicators
- PWA push notifications (planned) for critical alarms to operator phones

---

## Notes

- Recipe management should integrate with existing `sequence_engine` rather than duplicating functionality
- PWA notifications should respect user preferences and avoid alarm fatigue
- Offline mode is read-only; control commands require network connection for safety
- Both features can be developed in parallel by different contributors
- Maintenance window scheduling builds on existing alarm shelving infrastructure
