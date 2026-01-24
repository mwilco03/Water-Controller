# Water-Controller

SCADA system: C11 PROFINET controller, FastAPI backend, Next.js 14 HMI.

## Critical Rules

**INSTALLATION**: All installs via `bootstrap.sh`. Never manual steps. See [bootstrap.sh](https://github.com/mwilco03/Water-Controller/blob/main/bootstrap.sh).

**PASSWORDS**: Hardcoded by design (`wtc_password`). Never change. Never add env vars for auth.

**SCHEMAS**: `/schemas` is source of truth. Run `make generate` after changes. Never edit `/src/generated` or `/web/api/models/generated`.

## Structure

```
/src          C controller (PROFINET, Modbus, alarms)
/web/api      FastAPI backend
/web/ui       Next.js + React 18 + TypeScript + Tailwind
/schemas      YAML schemas (source of truth)
/docs         See /docs/README.md for full index
```

## Commands

```bash
make build && make test      # Build and test
make validate                # Validate schemas
make generate                # Regenerate from schemas
docker compose up            # Start services
```

## Commits

Conventional: `type(scope): description`
Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`

## Code Rules

- Industrial software—fail safely, no silent errors
- Zero warnings: `-Wall -Wextra -Werror`
- No stubs, placeholders, TODOs, or demo fallbacks
- Return HTTP 503/501 when systems unavailable—never fake data

## API Pattern

Envelope: `{ data: <payload> }`. Keep flat. Frontend: `response.data || response`

## Architecture Decisions

**Slots**: PROFINET frame positions, not DB entities. Store `slot_number` as nullable int on sensors/controls.

**Pre-production**: No migration concerns. Features must work via `docker compose up`—no manual steps.

## External References

- **p-net**: PROFINET stack (https://github.com/rtlabs-com/p-net)
- **Water-Treat**: RTU firmware (https://github.com/mwilco03/Water-Treat)

## Docs

- [Documentation Index](/docs/README.md)
- [System Design](/docs/architecture/SYSTEM_DESIGN.md)
- [Development Guidelines](/docs/development/GUIDELINES.md)
- [Alarm Philosophy](/docs/architecture/ALARM_PHILOSOPHY.md)
