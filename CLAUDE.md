# Water-Controller

SCADA system for water treatment: PROFINET IO Controller, FastAPI backend, Next.js HMI.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Controller | C11 (CMake), PROFINET RT |
| Backend | Python 3, FastAPI, PostgreSQL |
| Frontend | Next.js 14, React 18, TypeScript, Tailwind |
| Infra | Docker, systemd |

## Directory Structure

- `/src` - C controller code (PROFINET, Modbus, alarms, historian)
- `/web/api` - FastAPI backend
- `/web/ui` - Next.js frontend
- `/schemas` - YAML schemas (source of truth for code generation)
- `/docker` - Container definitions
- `/docs` - See `/docs/development/GUIDELINES.md` for full standards

## Key Commands

```bash
# Controller (C)
make build              # Build controller
make test               # Run C tests
make validate           # Validate schemas + sync check
make generate           # Regenerate code from schemas

# Frontend (web/ui)
npm run build           # Production build
npm run test            # Jest tests
npm run lint            # ESLint

# Docker
docker compose up       # Start all services
```

## Commit Message Format

Use Conventional Commits: `type(scope): description`

**Types:** `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`

**Examples:**
- `feat(profinet): Add device discovery timeout`
- `fix(api): Resolve race condition in alarm queries`
- `docs(readme): Update installation steps`

## Critical Rules

- IMPORTANT: This is industrial control software. Code must fail safely.
- IMPORTANT: Schemas in `/schemas` are the source of truth. Run `make generate` after schema changes.
- Do not modify files in `/src/generated` or `/web/api/models/generated` directly.
- No stubs, placeholders, or TODO markers in production code.
- Build must succeed with zero warnings (`-Wall -Wextra -Werror`).
- Always run `make validate` before committing schema changes.

## Architecture Reference

See `/docs/architecture/SYSTEM_DESIGN.md` for full architecture.
See `/docs/development/GUIDELINES.md` for coding standards.
