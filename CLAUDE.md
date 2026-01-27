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

**CRITICAL - NO HARDCODED RTU DATA:**
- NEVER hardcode RTU IP addresses (e.g., 192.168.x.x)
- NEVER hardcode RTU station names (e.g., rtu-xxxx)
- RTUs are discovered via DCP multicast: `POST /api/v1/discover/rtu`
- RTU station_name comes from the device itself via DCP discovery
- All RTU configuration flows from discovery, not from code
- Violation of this rule is grounds for session termination

## API Pattern

Envelope: `{ data: <payload> }`. Keep flat. Frontend: `response.data || response`

## Architecture Decisions

## Docker Deployment Architecture

**CRITICAL: Bootstrap uses Docker mode by default. There is NO build directory on the host.**

The controller binary is compiled and runs INSIDE the `wtc-controller` container:
- Source cloned to: `/opt/water-controller/` (on host)
- Binary location: `/usr/local/bin/water_treat_controller` (inside container)
- Container built from: `docker/Dockerfile.controller`

**To rebuild the controller after code changes:**
```bash
cd /opt/water-controller/docker
docker compose build controller
docker compose up -d controller
```

**To view controller logs:**
```bash
docker logs wtc-controller -f
```

**The controller logs its version at startup:**
```
Starting Water Treatment Controller v1.2.0 (build abc1234)
Build date: 2026-01-24 00:27:06 +0000
```

This tells you exactly which commit is running.

## External Codebases

**Pre-production**: No migration concerns. Features must work via `docker compose up`—no manual steps.

## External References

- **p-net**: PROFINET stack (https://github.com/rtlabs-com/p-net)
- **Water-Treat**: RTU firmware (https://github.com/mwilco03/Water-Treat)

## Docs

- [Documentation Index](/docs/README.md)
- [System Design](/docs/architecture/SYSTEM_DESIGN.md)
- [Development Guidelines](/docs/development/GUIDELINES.md)
- [Alarm Philosophy](/docs/architecture/ALARM_PHILOSOPHY.md)
