# Next Steps Beyond Tech Debt Audit

This document outlines gaps and opportunities discovered during the tech debt audit that were **not part of the original scope** but are important for production readiness.

## Why These Weren't Included

The original audit focused on:
- Code duplication and overlaps
- Poor coding practices
- Hardcoded values that could be programmatic
- Hardcoded strings that should be variables

The following areas are **orthogonal concerns** that require dedicated effort:

---

## 1. Database Migrations (ADDED)

**Status:** ✅ Added in this session

**What was missing:** No version-controlled schema migrations existed. Tables were created via `Base.metadata.create_all()` at startup.

**Why it matters:**
- Schema changes in production require migrations, not table drops
- Team members need reproducible database states
- Rollback capability is essential for production deployments

**Files added:**
- `web/api/alembic.ini` - Alembic configuration
- `web/api/alembic/env.py` - Migration environment
- `web/api/alembic/versions/20250103_0001_initial_schema.py` - Baseline migration

**Usage:**
```bash
# For existing databases (stamp without running):
alembic stamp head

# For new databases:
alembic upgrade head

# Create new migration after model changes:
alembic revision --autogenerate -m "description"
```

---

## 2. Test Coverage Gaps

**Status:** ⚠️ Partial coverage exists

**Current state:**
- `tests/test_pid.py` - PID endpoint tests
- `tests/test_templates.py` - Template endpoint tests
- `tests/test_backup.py` - Backup/restore tests
- `tests/test_mixin.py` - DictSerializableMixin tests (ADDED)

**Missing test coverage:**
- Persistence layer unit tests
- Service layer tests (AlarmService, etc.)
- WebSocket endpoint tests
- Authentication/authorization tests
- Error handling edge cases

**Why it wasn't in scope:** The audit focused on code quality, not test coverage metrics.

---

## 3. Security Audit

**Status:** ⚠️ Not performed

**Areas needing review:**
- Authentication token handling
- Session management security
- SQL injection prevention (SQLAlchemy helps, but verify)
- Input validation at API boundaries
- Rate limiting
- CORS configuration

**Why it wasn't in scope:** Security is a specialized concern requiring dedicated penetration testing.

---

## 4. Performance Profiling

**Status:** ⚠️ Not performed

**Potential bottlenecks:**
- Database query N+1 patterns
- Large result set pagination
- WebSocket message throughput
- RTU polling intervals

**Why it wasn't in scope:** Performance optimization requires production metrics and profiling tools.

---

## 5. Observability

**Status:** ⚠️ Partial

**Current state:**
- Python `logging` module is used
- Grafana stack exists in Docker

**Missing:**
- Structured logging (JSON format for log aggregation)
- Distributed tracing (OpenTelemetry)
- Metrics export (Prometheus format)
- Health check endpoints with dependencies

**Why it wasn't in scope:** Observability is infrastructure, not code quality.

---

## 6. API Versioning Strategy

**Status:** ⚠️ Exists but undocumented

**Current state:**
- API routes are under `/api/v1/`
- No clear migration strategy documented

**Needs:**
- Deprecation policy documentation
- Version negotiation headers
- Backward compatibility guidelines

---

## 7. Error Handling Standardization

**Status:** ⚠️ Inconsistent

**Current state:**
- Some endpoints return `{"error": {"code": "...", "message": "..."}}`
- Some use FastAPI's HTTPException directly
- Error codes are not centralized

**Recommendation:**
- Create `app/core/errors.py` with all error codes
- Standardize error response schema
- Add correlation IDs for traceability

---

## 8. Documentation

**Status:** ⚠️ Minimal

**Missing:**
- API documentation (OpenAPI descriptions)
- Architecture decision records (ADRs)
- Deployment runbook
- Troubleshooting guide

**Why it wasn't in scope:** Documentation is a writing task, not code review.

---

## Priority Matrix

| Item | Impact | Effort | Priority |
|------|--------|--------|----------|
| Database Migrations | High | Low | ✅ Done |
| Test Coverage | High | Medium | P1 |
| Security Audit | Critical | High | P1 |
| Error Standardization | Medium | Low | P2 |
| Observability | Medium | Medium | P2 |
| Performance Profiling | Medium | High | P3 |
| API Versioning Docs | Low | Low | P3 |
| Documentation | Low | Medium | P4 |

---

## Files Changed in This Session

### Added
- `web/api/tests/test_mixin.py` - Tests for DictSerializableMixin
- `web/api/alembic.ini` - Alembic configuration
- `web/api/alembic/env.py` - Migration environment
- `web/api/alembic/versions/20250103_0001_initial_schema.py` - Initial schema

### Modified
- `web/api/requirements.txt` - Added alembic dependency
- `web/api/app/models/user.py` - Added `_serialize_field` override for UserSession
- `web/api/app/persistence/sessions.py` - Removed `_session_to_dict()`, uses mixin

---

## Summary

The tech debt audit successfully addressed **code quality issues** (duplication, hardcoding, naming). However, production readiness requires attention to:

1. **Testing** - Expand coverage to reach 80% target
2. **Security** - Dedicated security review
3. **Operations** - Observability, error handling, documentation

These are separate initiatives that complement but don't overlap with the original audit scope.
