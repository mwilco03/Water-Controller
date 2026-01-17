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

## References

- Architecture: `/docs/architecture/SYSTEM_DESIGN.md`
- Coding standards: `/docs/development/GUIDELINES.md`
- Alarm philosophy: `/docs/architecture/ALARM_PHILOSOPHY.md`
