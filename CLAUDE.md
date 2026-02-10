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

## PROFINET Connection Sequence (IEC 61158-6-10)

The PROFINET AR (Application Relationship) lifecycle per the specification:

```
IO Controller                                    IO Device (RTU)
     │                                                │
     │─── 1. DCP Identify Request (multicast) ───────►│
     │◄────────── DCP Identify Response ──────────────│
     │       (controller reads IP + station name)     │
     │                                                │
     │═══ 2. RPC Connect Request ════════════════════►│
     │◄══════════ Connect Response ═══════════════════│
     │         (includes Module-Diff-Block if         │
     │          expected ≠ actual submodules)         │
     │                                                │
     │═══ 3. RPC Write (parameters) ═════════════════►│
     │◄═════════ Write Response ══════════════════════│
     │                                                │
     │═══ 4. RPC PrmEnd (IODControlReq) ═════════════►│
     │◄════════ PrmEnd Response ══════════════════════│
     │                                                │
     │◄══ 5. RPC ApplicationReady (IODControlReq) ════│  ← DEVICE initiates!
     │═══════ ApplicationReady Response ═════════════►│
     │                                                │
     │◄══════════ Cyclic Input Data ══════════════════│
     │═══════════ Cyclic Output Data ════════════════►│
     │              (RT frames, 1ms cycle)            │
```

**Key points:**
- **Controller initiates** steps 1-4 (discovery, connect, parameterization)
- **Device initiates** step 5 (ApplicationReady) - signals readiness for I/O
- **No DCP Set** — controller does NOT assign IP or station name. RTU owns its identity (name from MAC, IP from DHCP/static). Controller reads both from the DCP Identify Response.
- ApplicationReady timeout: up to 300 seconds per spec
- Cyclic watchdog: 3 seconds default

**References:**
- [IEC 61158-6-10:2023](https://webstore.iec.ch/publication/83457) - PROFINET Protocol
- [CODESYS PROFINET Connection](https://content.helpme-codesys.com/en/CODESYS%20PROFINET/_pnio_protocol_connection.html)
- [Felser PROFINET Manual](https://www.felser.ch/profinet-manual/pn_kommunikationsbeziehung.html)

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

- **p-net**: PROFINET stack — our fork (https://github.com/mwilco03/p-net), upstream (https://github.com/rtlabs-com/p-net)
- **Water-Treat**: RTU firmware (https://github.com/mwilco03/Water-treat)

## Docs

- [Documentation Index](/docs/README.md)
- [System Design](/docs/architecture/SYSTEM_DESIGN.md)
- [Development Guidelines](/docs/development/GUIDELINES.md)
- [Alarm Philosophy](/docs/architecture/ALARM_PHILOSOPHY.md)

## PROFINET RPC Communication

**STATUS (2026-02-10): Full PROFINET cyclic data exchange WORKING. 17 bugs fixed.**

See [docs/development/PROFINET_RPC_BUG_FIXES.md](docs/development/PROFINET_RPC_BUG_FIXES.md) for the complete bug fix history.

Full lifecycle: DCP → Connect → PrmEnd → ApplicationReady → CControl → Cyclic I/O (DATA state).
p-net reaches `PF_CMDEV_STATE_DATA` — stable, no timeouts.

**CRITICAL: RPC timeouts are NOT a networking issue. The network is fine.**

PROFINET RPC failures are caused by **code bugs** in the controller, not firewalls/connectivity. P-net silently rejects malformed packets. The 17 bugs fixed:

1. Inter-block padding — blocks must be contiguous, no alignment bytes
2. UUID byte ordering — fields 1-3 must be LE-swapped per DREP=0x10
3. NDR header — mandatory 20-byte header between RPC and PNIO blocks
4. IOCRTagHeader — VLAN priority 6 (0xC000), not 0
5. ARProperties — bit 4 (0x10), not bit 1 (0x02)
6. ExpectedSubmoduleBlockReq — complete rewrite to IEC 61158-6 wire format
7. IOCR NO_IO placement — IOData in INPUT IOCR only, IOCS in OUTPUT only
8. IOCR frame offset overlap — each entry needs data_length+1 for IOPS byte
9. AlarmCR rta_timeout_factor — must be <=100 (IEC 61158-6 max)
10. NDR response parser — 20 bytes with PNIOStatus first, not 24-byte format
11. Activity UUID reuse — all RPC ops must share Connect's activity UUID
12. Connect response alignment — blocks are contiguous (no align_to_4 in parser)
13. ModuleDiffBlock — DAP-only diffs are informational, proceed to PrmEnd
14. CControl response — NDR header, block type 0x8112, DONE cmd, DREP-aware UUIDs
15. ControlCommand bitfield — IEC 61158-6 Table 777 bit positions, not sequential
16. VLAN tag on output frames — 802.1Q tag with PCP=6 required by CPM
17. DataStatus + VLAN receive — StationProblem bit 0x20, VLAN-aware frame offset

After code fixes, **rebuild controller container** to deploy changes:
```bash
cd /opt/water-controller/docker
./generate-build-env.sh
docker compose build controller --no-cache
docker compose up -d controller
```

## Known Technical Debt

The following files contain discovery-first violations (hardcoded RTU IPs/names). They are acknowledged technical debt, not to be expanded:

| File | Issue | Future Fix |
|------|-------|------------|
| `web/api/app/services/demo_mode.py` | Hardcoded RTU IPs and station names | Remove entirely (violates no-demo-fallbacks rule) |
| `src/simulation/simulator.c` | Hardcoded RTU IPs and station names | Refactor to use discovered devices or remove |
| `web/api/app/api/v1/modbus.py:39` | Default `/dev/ttyUSB0` serial device | Remove default, require explicit config |
