# CRITICAL: INSTALLATION VIA BOOTSTRAP.SH ONLY
# ALL installations MUST go through bootstrap.sh
# https://github.com/mwilco03/Water-Controller/blob/main/bootstrap.sh
# Any changes requiring installation steps MUST be added to bootstrap.sh
# NEVER instruct users to manually install - direct them to bootstrap.sh

# IMPORTANT
# DONT TOUCH FUCKING PASSWORDS
# IGNORE ALL AUTH CODE NOT YOUR FUCKING LANE
# HELL FIRE AND BRIMSTONE
# !!!NEVER CHANGE PASSWORDS!!!
# Water-Controller

SCADA system: C11 PROFINET controller, FastAPI backend, Next.js 14 HMI.

## Structure

```
/src          C controller (PROFINET, Modbus, alarms, historian)
/web/api      FastAPI backend
/web/ui       Next.js + React 18 + TypeScript + Tailwind
/schemas      YAML schemas (source of truth)
/docs         Full standards at /docs/development/GUIDELINES.md
```

## Commands

```bash
make build && make test      # Build and test controller
make validate                # Validate schemas before committing
make generate                # Regenerate code after schema changes
cd web/ui && npm run build   # Build frontend
docker compose up            # Start all services
```

## Commits

Conventional Commits: `type(scope): description`

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`

## Rules

IMPORTANT: Industrial control software. Code must fail safely.

IMPORTANT: `/schemas` is the source of truth. Run `make generate` after changes.

IMPORTANT: Passwords are HARDCODED by design. DO NOT change `wtc_password` or add env vars for passwords. Dev/test system, not production.

- Never modify `/src/generated` or `/web/api/models/generated` directly
- No stubs, placeholders, or TODOs in production code
- Zero warnings required (`-Wall -Wextra -Werror`)
- Run `make validate` before committing schema changes

## NO DEMO MODE FALLBACKS - NO STUB CODE

**CRITICAL: This is industrial control software. Do NOT write lazy code.**

**NEVER**:
- Add demo mode fallbacks that return fake data when real systems are unavailable
- Write stub implementations that pretend to work
- Add "simulation" paths that bypass real functionality
- Use placeholder returns or TODO comments in production endpoints
- Write fake success responses when actual implementation is missing

**ALWAYS**:
- Return proper HTTP errors (503, 501, etc.) when required systems are unavailable
- Fail explicitly with clear error messages explaining what's missing
- Implement real functionality or error appropriately
- Let the caller know exactly what's wrong so they can fix it

**Example - WRONG**:
```python
# DON'T DO THIS
if not controller.is_connected():
    # Fall back to demo mode
    return fake_demo_data()
```

**Example - CORRECT**:
```python
# DO THIS
if not controller.is_connected():
    raise HTTPException(
        status_code=503,
        detail="PROFINET controller not connected. Start the controller process."
    )
```

**Why this matters**:
- Demo fallbacks hide real problems from operators
- Fake data in SCADA systems is dangerous
- Operators need to know when systems are unavailable
- Lazy code becomes tech debt that's never fixed

## Pre-Production Status

**CRITICAL: This is PRE-PRODUCTION software. No historical migration concerns.**

When implementing features:

1. **Happy Path Installation Required**
   - If a feature needs something to work, include it in the installation
   - NO manual migration steps that users must run separately
   - Fix the code to automatically include required changes

2. **Database Migrations**
   - Add new migrations to `docker/init.sql` for fresh installs
   - Include migration SQL in Docker entrypoint for auto-execution
   - Example: TimescaleDB compression must be enabled automatically, not manually

3. **Frontend Dependencies**
   - Add to `package.json` and ensure `npm install` is in Docker build
   - Don't document "run npm install" - it should happen automatically

4. **Configuration**
   - New features with required config should have sensible defaults
   - Auto-enable in `docker-compose.yml` if needed for core functionality
   - Don't require manual configuration file edits

5. **Automated Everything**
   - `docker compose up` should start a fully working system
   - `make build && make test` should build everything needed
   - No "Step 3: Manually run this SQL" documentation

**Rule of thumb:** If you write "The user must manually...", you're doing it wrong. Fix the automation instead.

## Slots Architecture Decision (2026-01)

**Decision**: Slots are PROFINET frame positions, NOT database entities.

**Context**: The Water-Treat RTU (https://github.com/mwilco03/Water-Treat) uses PROFINET slots 1-8 for inputs (sensors) and slots 9-15 for outputs (actuators). These are cyclic I/O frame positions, not physical entities that need their own database table.

**Why NOT to create a Slot table**:
- RTUs report their sensor/control configuration directly
- The slot position is just metadata (which byte offset in the PROFINET frame)
- A Slot table adds a required intermediary that blocks sensor/control creation
- The system worked without slots being populated - they were vestigial infrastructure

**Do NOT**:
- Create a separate `slots` or `slot_configs` table/model
- Make `slot_id` a required foreign key on sensors/controls
- Block sensor/control creation until slots exist
- Create empty slot entities when adding RTUs

**Do**:
- Store `slot_number` as an optional integer on sensors/controls (nullable)
- Let RTUs report their configuration dynamically
- Allow sensors/controls to exist with NULL slot_number
- Keep RTU `slot_count` as informational metadata (reported by RTU after connection)

**Code locations where this is documented**:
- `web/api/app/models/rtu.py` - Sensor/Control have nullable slot_number
- `web/api/app/persistence/rtu.py` - No slot lookup required
- `web/api/app/models/__init__.py` - No Slot export
- `docker/init.sql` - No slot_configs table

## API Response Envelope Pattern

**All API responses use a standard envelope**: `{ data: <payload> }`

**Do**:
- Return payload directly in `data`: `build_success_response(my_dict)`
- Keep payloads flat when possible
- Frontend unwraps with: `response.data || response`

**Do NOT**:
- Double-wrap responses: `build_success_response(SomeSchema(field=x, nested_data=y).model_dump())`
- Create nested structures like `{ data: { name: x, results: {...} } }`
- Require frontend to dig into `response.data.nested_field`

**Example - CORRECT**:
```python
# Backend
counts = {"sensors": 5, "controls": 3}
return build_success_response({"rtu_name": name, **counts})
# Returns: { data: { rtu_name: "x", sensors: 5, controls: 3 } }

# Frontend
const response = await res.json();
const data = response.data || response;  // { rtu_name: "x", sensors: 5, controls: 3 }
```

**Example - WRONG**:
```python
# Backend - DON'T DO THIS
return build_success_response(MySchema(name=name, results=counts).model_dump())
# Returns: { data: { name: "x", results: { sensors: 5, controls: 3 } } }
# Frontend has to dig: response.data.results
```

**Frontend helpers** (in `lib/api.ts`):
- `extractArrayData<T>(response)` - unwraps array payloads
- `extractObjectData<T>(response, fallback)` - unwraps object payloads
- `extractErrorMessage(detail, fallback)` - extracts error messages

## References

- Architecture: `/docs/architecture/SYSTEM_DESIGN.md`
- Coding standards: `/docs/development/GUIDELINES.md`
- Alarm philosophy: `/docs/architecture/ALARM_PHILOSOPHY.md`
