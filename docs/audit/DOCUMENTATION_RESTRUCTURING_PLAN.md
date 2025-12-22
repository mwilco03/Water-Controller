# Documentation Restructuring Plan

## Target Structure

Both repositories should adopt this standardized documentation structure:

```
repository/
├── README.md                          # Project overview, quick start
├── CHANGELOG.md                       # Keep a Changelog format
├── CONTRIBUTING.md                    # Contributor guidelines
├── docs/
│   ├── generated/                     # Git-ignored, rebuilt by CI
│   │   ├── api/
│   │   │   └── openapi.yaml          # Generated OpenAPI spec
│   │   ├── coverage/
│   │   │   └── index.html            # Test coverage reports
│   │   └── c-api/
│   │       └── index.html            # Doxygen-generated C API docs
│   │
│   ├── versioned/                     # Stable reference per release
│   │   └── v1.0/
│   │       ├── operations-manual.md
│   │       ├── safety-interlocks.md
│   │       ├── alarm-reference.md
│   │       ├── commissioning.md
│   │       └── configuration-reference.md
│   │
│   ├── architecture/                  # Evergreen architecture docs
│   │   ├── system-overview.md
│   │   ├── profinet-integration.md
│   │   ├── data-flow.md
│   │   └── diagrams/
│   │
│   ├── development/                   # Developer documentation
│   │   ├── setup.md
│   │   ├── testing.md
│   │   ├── contributing.md
│   │   └── code-style.md
│   │
│   ├── templates/                     # Document templates
│   │   ├── calibration-record.md
│   │   ├── commissioning-checklist.md
│   │   └── incident-report.md
│   │
│   ├── audit/                         # Audit reports (this directory)
│   │   └── DOCUMENTATION_AUDIT_REPORT.md
│   │
│   └── specifications/                # Technical specifications
│       └── PROFINET_DATA_FORMAT_SPECIFICATION.md
│
├── .github/
│   └── workflows/
│       └── docs.yml                   # Documentation CI pipeline
│
└── .gitignore                         # Include docs/generated/
```

---

## Migration Tasks

### Foundation Layer (No Dependencies)

These tasks can be completed in any order and have no prerequisites:

| Task | Repository | Effort | Description |
|------|------------|--------|-------------|
| F-1 | Both | Small | Create `docs/generated/` directory and add to `.gitignore` |
| F-2 | Both | Small | Create `docs/versioned/` directory structure |
| F-3 | Both | Small | Create `docs/templates/` directory |
| F-4 | Both | Small | Create `docs/architecture/` directory |
| F-5 | Both | Small | Create `docs/development/` directory |
| F-6 | Water-Controller | Small | Move `docs/PROFINET_DATA_FORMAT_SPECIFICATION.md` to `docs/specifications/` |
| F-7 | Water-Treat | Small | Move `docs/PROFINET_DATA_FORMAT_SPECIFICATION.md` to `docs/specifications/` |
| F-8 | Both | Small | Create `CONTRIBUTING.md` from DEVELOPMENT_GUIDELINES.md excerpt |

### Critical Safety Documentation (Foundation Complete)

These are safety-critical and should be prioritized after foundation:

| Task | Repository | Effort | Depends On | Description |
|------|------------|--------|------------|-------------|
| C-1 | Water-Treat | Large | F-2 | **Create safety interlock documentation** - Document all RTU-side interlocks, safe states, testing procedures |
| C-2 | Both | Medium | F-2, F-3 | **Create commissioning checklist** - Pre-power, communication, calibration, interlock verification |
| C-3 | Water-Treat | Small | F-2 | **Fix OPERATOR.md Appendix B** - Update sensor data format to 5-byte |
| C-4 | Water-Treat | Small | None | **Fix README.md I/O table** - Update to 5-byte format |
| C-5 | Both | Medium | F-2 | **Create alarm response procedures** - Document each alarm type with cause/effect/response |

### High Priority Operations Documentation (Foundation Complete)

| Task | Repository | Effort | Depends On | Description |
|------|------------|--------|------------|-------------|
| H-1 | Water-Controller | Medium | F-1 | **Generate OpenAPI specification** - Extract from FastAPI, add to CI |
| H-2 | Water-Controller | Medium | F-2 | **Create Modbus gateway documentation** - Configuration guide with examples |
| H-3 | Water-Controller | Medium | F-2 | **Create log forwarding guide** - Elastic, Graylog, Syslog configuration |
| H-4 | Water-Treat | Medium | F-2 | **Create sensor calibration guide** - Detailed procedures with record templates |
| H-5 | Both | Small | F-2 | **Create configuration reference** - Document all config file options |

### Medium Priority Development Documentation (Foundation Complete)

| Task | Repository | Effort | Depends On | Description |
|------|------------|--------|------------|-------------|
| M-1 | Both | Large | F-1 | **Add Doxygen configuration** - Generate C API documentation |
| M-2 | Both | Medium | M-1 | **Improve code comment coverage** - Priority: public API functions |
| M-3 | Both | Medium | F-4 | **Create architecture diagrams** - Mermaid/PlantUML versions |
| M-4 | Both | Small | F-5 | **Consolidate development setup guide** - Single source of truth |
| M-5 | Water-Controller | Medium | H-1 | **Add API examples** - curl/Python examples for each endpoint |

### Low Priority Supplementary Documentation (All Others Complete)

| Task | Repository | Effort | Depends On | Description |
|------|------------|--------|------------|-------------|
| L-1 | Both | Small | F-5 | **Create code style guide** - Document linter configuration rationale |
| L-2 | Water-Controller | Small | None | **Create roadmap document** - Future development plans |
| L-3 | Both | Small | F-3 | **Create incident report template** - For operational incidents |

### Ongoing Maintenance Tasks

| Task | Repository | Frequency | Description |
|------|------------|-----------|-------------|
| O-1 | Both | Per Release | Update CHANGELOG.md following Keep a Changelog |
| O-2 | Both | Per Release | Create/update versioned documentation snapshot |
| O-3 | Both | Per Commit | Regenerate API documentation via CI |
| O-4 | Both | Quarterly | Review and update accuracy of all documentation |

---

## Dependency Graph

```
Foundation Tasks (F-1 through F-8)
          │
          ├─────────────────────────────────────────────┐
          │                                             │
          ▼                                             ▼
┌─────────────────────┐                    ┌─────────────────────┐
│  Critical Safety    │                    │   High Priority     │
│  (C-1 through C-5)  │                    │   (H-1 through H-5) │
└─────────┬───────────┘                    └─────────┬───────────┘
          │                                          │
          │    ┌─────────────────────────────────────┘
          │    │
          ▼    ▼
┌─────────────────────┐
│   Medium Priority   │
│  (M-1 through M-5)  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│    Low Priority     │
│  (L-1 through L-3)  │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│ Ongoing Maintenance │
│  (O-1 through O-4)  │
└─────────────────────┘
```

---

## Documentation Classification (Hybrid Model)

### Auto-Generated (Living) - `docs/generated/`

**Rebuild on every commit via CI. Git-ignored.**

| Document | Source | Generator | Repository |
|----------|--------|-----------|------------|
| OpenAPI spec | FastAPI code | `python -m uvicorn --export-openapi` | Water-Controller |
| C API reference | Source comments | Doxygen | Both |
| Coverage reports | Test runs | pytest-cov / gcov | Both |
| Dependency graph | Source | CMake/pip | Both |

### Auto-Generated but Committed (Living with History)

**Generated but committed for visibility.**

| Document | Source | Generator | Repository |
|----------|--------|-----------|------------|
| CHANGELOG.md | Git commits | manual or conventional-changelog | Both |

### Versioned per Release (Stable Reference) - `docs/versioned/vX.Y/`

**Snapshot at each release. Operators need docs matching their version.**

| Document | Contents | Repository |
|----------|----------|------------|
| operations-manual.md | Day-to-day operations | Both |
| safety-interlocks.md | Interlock configuration and testing | Water-Treat |
| alarm-reference.md | All alarm types with responses | Both |
| commissioning.md | Commissioning checklist | Both |
| configuration-reference.md | All config options | Both |

### Manually Maintained (Evergreen) - `docs/` root

**Stable concepts that change rarely.**

| Document | Contents | Repository |
|----------|----------|------------|
| README.md | Project overview, quick start | Both |
| CONTRIBUTING.md | How to contribute | Both |
| architecture/*.md | System design, data flow | Both |
| development/*.md | Development setup, testing | Both |
| specifications/*.md | Technical specifications | Both |

---

## File Migration Map

### Water-Controller

| Current Location | New Location | Action |
|-----------------|--------------|--------|
| `docs/PROFINET_DATA_FORMAT_SPECIFICATION.md` | `docs/specifications/PROFINET_DATA_FORMAT_SPECIFICATION.md` | Move |
| `docs/DEPLOYMENT.md` | `docs/versioned/v1.0/operations-manual.md` | Rename + version |
| `docs/DEVELOPMENT_GUIDELINES.md` | `docs/development/guidelines.md` | Move |
| `docs/ALARM_ARCHITECTURE.md` | `docs/architecture/alarm-architecture.md` | Move |
| `docs/INTEGRATION_AUDIT_REPORT.md` | `docs/audit/integration-audit.md` | Move |
| `docs/CROSS_SYSTEM_GUIDELINES_ADDENDUM.md` | `docs/architecture/cross-system-integration.md` | Move |
| (new) | `docs/versioned/v1.0/commissioning.md` | Create |
| (new) | `docs/versioned/v1.0/alarm-reference.md` | Create |
| (new) | `docs/generated/api/openapi.yaml` | Generate |
| (new) | `CONTRIBUTING.md` | Create |

### Water-Treat

| Current Location | New Location | Action |
|-----------------|--------------|--------|
| `OPERATOR.md` | `docs/versioned/v1.0/operations-manual.md` | Move + fix Appendix B |
| `INSTALL.md` | `docs/development/installation.md` | Move |
| `SOURCES.md` | `docs/architecture/source-overview.md` | Move |
| `CONTROLLER_SPEC.md` | `docs/specifications/controller-spec.md` | Move |
| `REVIEW.md` | `docs/audit/code-review.md` | Move |
| `docs/PROFINET_DATA_FORMAT_SPECIFICATION.md` | `docs/specifications/PROFINET_DATA_FORMAT_SPECIFICATION.md` | Move |
| `docs/DEVELOPMENT_GUIDELINES.md` | `docs/development/guidelines.md` | Move |
| `docs/LOGGER_ARCHITECTURE.md` | `docs/architecture/logger-architecture.md` | Move |
| `docs/IO_CONFIGURATION_UI_SPEC.md` | `docs/specifications/io-configuration-ui.md` | Move |
| (new) | `docs/versioned/v1.0/safety-interlocks.md` | Create |
| (new) | `docs/versioned/v1.0/commissioning.md` | Create |
| (new) | `docs/templates/calibration-record.md` | Create |
| (new) | `CONTRIBUTING.md` | Create |

---

## CI/CD Integration

### GitHub Actions Workflow

See `.github/workflows/docs.yml` for the complete workflow that:

1. **On every push:**
   - Generates OpenAPI spec from FastAPI
   - Runs Doxygen for C API documentation
   - Validates markdown links
   - Checks for broken internal references

2. **On release:**
   - Creates versioned documentation snapshot
   - Deploys to GitHub Pages
   - Updates version badge

3. **Scheduled (weekly):**
   - Checks for documentation staleness
   - Reports undocumented public functions

---

## Success Criteria

### Phase 1 Complete (Foundation + Critical)
- [ ] Directory structure created in both repos
- [ ] Safety interlock documentation complete
- [ ] Commissioning checklist complete
- [ ] All sensor format references corrected
- [ ] Alarm response procedures documented

### Phase 2 Complete (High Priority)
- [ ] OpenAPI specification generated and published
- [ ] Modbus gateway documentation complete
- [ ] Log forwarding guide complete
- [ ] Sensor calibration guide complete
- [ ] Configuration reference complete

### Phase 3 Complete (Medium Priority)
- [ ] Doxygen generating C API docs
- [ ] Code comment coverage > 70%
- [ ] Architecture diagrams in Mermaid/PlantUML
- [ ] Development setup guide consolidated
- [ ] API examples for all endpoints

### Phase 4 Complete (Low Priority + Ongoing)
- [ ] Code style guide documented
- [ ] Roadmap documented
- [ ] Incident report template created
- [ ] CI pipeline for docs fully operational
- [ ] Quarterly review process established

---

## Resource Requirements

### Tools Required

| Tool | Purpose | Installation |
|------|---------|-------------|
| Doxygen | C API documentation | `apt install doxygen` |
| Graphviz | Doxygen diagrams | `apt install graphviz` |
| Mermaid CLI | Diagram generation | `npm install -g @mermaid-js/mermaid-cli` |
| markdown-link-check | Link validation | `npm install -g markdown-link-check` |

### Effort Estimates (by task size)

| Size | Typical Effort | Examples |
|------|----------------|----------|
| Small | 1-2 hours | Directory creation, file moves, minor fixes |
| Medium | 4-8 hours | New document creation, configuration guides |
| Large | 1-3 days | Comprehensive guides, significant research required |

---

*Plan created: 2024-12-22*
*Review scheduled: Upon completion of each phase*
