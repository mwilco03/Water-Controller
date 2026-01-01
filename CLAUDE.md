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

- Never modify `/src/generated` or `/web/api/models/generated` directly
- No stubs, placeholders, or TODOs in production code
- Zero warnings required (`-Wall -Wextra -Werror`)
- Run `make validate` before committing schema changes

## References

- Architecture: `/docs/architecture/SYSTEM_DESIGN.md`
- Coding standards: `/docs/development/GUIDELINES.md`
- Alarm philosophy: `/docs/architecture/ALARM_PHILOSOPHY.md`
