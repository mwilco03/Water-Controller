# Water-Controller Naming Pattern Audit - Findings Report

**Date:** 2026-01-17
**Branch:** claude/standardize-env-vars-rdZZM
**Critical Issue:** Auth failure due to environment variable naming inconsistencies

---

## EXECUTIVE SUMMARY

**ROOT CAUSE IDENTIFIED:** Multiple naming pattern inconsistencies causing database authentication failures.

### Critical Mismatches:
1. **bootstrap.sh** generates `DB_PASSWORD` and `GRAFANA_PASSWORD`
2. **docker-compose.yml** hardcodes `POSTGRES_PASSWORD: wtc_password` (ignores bootstrap vars)
3. **wtc-api** expects `WTC_DB_PASSWORD` (not `DB_PASSWORD`)
4. **DATABASE_URL** in docker-compose.yml line 55 hardcodes password as `wtc_password`

**Impact:** Bootstrap-generated passwords never reach the database or API, causing auth failures.

---

## 1. BOOTSTRAP.SH NAMING PATTERNS

### Variables (UPPER_SNAKE_CASE):
```bash
# Constants (readonly)
BOOTSTRAP_VERSION="1.1.0"
REPO_URL="https://github.com/..."
INSTALL_DIR="/opt/water-controller"
VERSION_FILE, MANIFEST_FILE, CONFIG_DIR, DATA_DIR, LOG_DIR, BACKUP_DIR
BOOTSTRAP_LOG, MIN_DISK_SPACE_MB, REQUIRED_TOOLS, CHECKSUM_FILE

# Global state
QUIET_MODE="false"
DEPLOYMENT_MODE=""
CLEANUP_DIRS=()

# Colors
RED, GREEN, YELLOW, BLUE, NC

# Generated passwords (CRITICAL)
GRAFANA_PASSWORD=$(generate_password 24)   # Line 743
DB_PASSWORD=$(generate_password 32)        # Line 748
```

### Functions (lower_snake_case):
```bash
init_logging, write_log, log_info, log_warn, log_error, log_step, log_debug
run_privileged, run_privileged_env, cleanup_all, register_cleanup, prompt_user
detect_system_state, get_installed_version, get_installed_sha
check_root, check_required_tools, check_network, install_docker
validate_docker_requirements, generate_password, wait_for_health_checks
verify_endpoints, create_systemd_service, create_quick_commands
do_docker_install, do_install, do_upgrade, do_remove
```

### Port Variables (Referenced but not set):
```bash
WTC_API_PORT=${WTC_API_PORT:-8000}
WTC_UI_PORT=${WTC_UI_PORT:-8080}
WTC_GRAFANA_PORT=${WTC_GRAFANA_PORT:-3000}
WTC_DB_PORT=${WTC_DB_PORT:-5432}
WTC_DOCKER_UI_INTERNAL_PORT=${WTC_DOCKER_UI_INTERNAL_PORT:-3000}
```

---

## 2. DOCKER-COMPOSE.YML ENVIRONMENT VARIABLES

### Database Service (Lines 18-43):
```yaml
POSTGRES_USER: wtc                    # Hardcoded
POSTGRES_PASSWORD: wtc_password       # ❌ HARDCODED, should use ${DB_PASSWORD}
POSTGRES_DB: water_treatment          # Hardcoded
```

### API Service (Lines 54-58):
```yaml
DATABASE_URL: postgresql://wtc:wtc_password@database:${WTC_DB_PORT:-5432}/water_treatment
  # ❌ HARDCODED PASSWORD, should use ${DB_PASSWORD}
API_HOST: 0.0.0.0
WTC_API_PORT: ${WTC_API_PORT:-8000}
WTC_UI_PORT: ${WTC_UI_PORT:-8080}
```

### Grafana Service (Lines 166-168):
```yaml
GF_SECURITY_ADMIN_USER: admin
GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:?GRAFANA_PASSWORD must be set}
  # ✓ CORRECT - Uses env var with required check
GF_INSTALL_PLUGINS: grafana-clock-panel,grafana-simple-json-datasource
```

### Controller Service (Lines 90-92):
```yaml
WT_INTERFACE: ${PROFINET_INTERFACE:-eth0}
WT_CYCLE_TIME: 1000
WT_LOG_LEVEL: INFO
```

---

## 3. WTC-API NAMING PATTERNS

### Python Code Standards (PEP 8 Compliant):

#### Functions/Variables (snake_case):
```python
# From main.py
async def lifespan(app: FastAPI)
async def health_check() -> dict[str, Any]
async def root()

# From auth.py
async def get_token_from_header(...)
async def get_current_session(...)
async def require_control_access(...)
async def optional_session_for_audit(...)
def log_control_action(...)

# Variables
logger, startup_result, session, token, credentials
db_url, api_port, ui_port, db_host, db_port
```

#### Classes (PascalCase):
```python
FastAPI, LoginRequest, LoginResponse, SessionResponse
AuthService, TimeoutConfig, PollingConfig, CircuitBreakerConfig
HistorianConfig, RtuDefaults, Settings
```

#### Constants (UPPER_SNAKE_CASE):
```python
SESSION_DURATION_HOURS = 8
COMMAND_MODE_DURATION_MINUTES = 5
LOG_LEVEL = os.environ.get("WTC_LOG_LEVEL", "INFO")
LOG_STRUCTURED = os.environ.get("WTC_LOG_STRUCTURED", "false")
```

### Environment Variables Read by wtc-api:

#### Database Configuration (web/api/app/core/ports.py:163-188):
```python
# Priority order:
DATABASE_URL               # Docker standard (line 164)
WTC_DATABASE_URL          # Explicit override (line 169)
WTC_DB_HOST               # Component-based (line 174)
WTC_DB_PORT               # Component-based (line 177)
WTC_DB_USER               # Component-based (line 178, default: "wtc")
WTC_DB_PASSWORD           # ❌ EXPECTS THIS, bootstrap sets DB_PASSWORD (line 179)
WTC_DB_NAME               # Component-based (line 180, default: "water_treatment")
WTC_DB_PATH               # SQLite fallback (line 187)
WTC_DB_ECHO               # Debug SQL (line 31)
```

#### Logging Configuration:
```python
WTC_LOG_LEVEL             # main.py:52
WTC_LOG_STRUCTURED        # main.py:53
```

#### Startup Validation:
```python
WTC_API_ONLY              # main.py:69
WTC_SIMULATION_MODE       # main.py:70
WTC_STARTUP_MODE          # Referenced in startup.py
WTC_DEBUG                 # config.py:176
```

#### CORS Configuration:
```python
WTC_CORS_ORIGINS          # ports.py:138
```

#### Ports:
```python
WTC_API_PORT              # ports.py:70
WTC_UI_PORT               # ports.py:75
WTC_DB_PORT               # ports.py:80
WTC_DB_HOST               # ports.py:85
WTC_API_HOST              # ports.py:112
WTC_UI_HOST               # ports.py:126
```

#### IPC Configuration:
```python
WTC_SHM_NAME              # .env.example:56
```

---

## 4. CROSS-REFERENCE: BOOTSTRAP → DOCKER → API

### Critical Path Trace (Database Password):

```
STEP 1: bootstrap.sh generates password
  └─ DB_PASSWORD=$(generate_password 32)        # Line 748
  └─ Saved to: /opt/water-controller/config/.docker-credentials
  └─ Written to: docker/.env                     # Lines 601-602

STEP 2: bootstrap.sh exports to environment
  └─ export DB_PASSWORD="$DB_PASSWORD"          # Lines 775, 807

STEP 3: docker-compose.yml database service
  └─ POSTGRES_PASSWORD: wtc_password            # ❌ IGNORES $DB_PASSWORD
  └─ Should be: ${DB_PASSWORD}

STEP 4: docker-compose.yml API service
  └─ DATABASE_URL: postgresql://wtc:wtc_password@...  # ❌ HARDCODED
  └─ Should be: postgresql://wtc:${DB_PASSWORD}@...

STEP 5: wtc-api reads database password
  └─ ports.py reads: WTC_DB_PASSWORD            # ❌ WRONG VAR NAME
  └─ bootstrap sets: DB_PASSWORD                # ❌ MISMATCH
  └─ Result: Password mismatch → Auth failure
```

### Variable Name Mapping:

| Concept | bootstrap.sh | docker-compose.yml | wtc-api expects | Match? |
|---------|--------------|-------------------|----------------|--------|
| Database password | `DB_PASSWORD` | `POSTGRES_PASSWORD` (hardcoded) | `WTC_DB_PASSWORD` | ❌ NO |
| Grafana password | `GRAFANA_PASSWORD` | `GRAFANA_PASSWORD` | N/A | ✓ YES |
| API port | `WTC_API_PORT` | `WTC_API_PORT` | `WTC_API_PORT` | ✓ YES |
| UI port | `WTC_UI_PORT` | `WTC_UI_PORT` | `WTC_UI_PORT` | ✓ YES |
| DB host | N/A | `database` (service name) | `WTC_DB_HOST` | ⚠️ IMPLICIT |
| DB port | `WTC_DB_PORT` | `WTC_DB_PORT` | `WTC_DB_PORT` | ✓ YES |

---

## 5. NAMING CONVENTION VIOLATIONS

### SNAKE_CASE Violations (Python Standard):
**Status:** ✓ CLEAN - All Python code follows PEP 8

### UPPER_SNAKE Violations (Bash env vars):
**Status:** ✓ MOSTLY CLEAN - Bootstrap follows conventions

### Inconsistencies (Same concept, different names):

#### Database Password (CRITICAL):
- bootstrap.sh: `DB_PASSWORD`
- docker-compose.yml database: `POSTGRES_PASSWORD` (hardcoded `wtc_password`)
- docker-compose.yml API: `DATABASE_URL` with hardcoded `wtc_password`
- wtc-api expects: `WTC_DB_PASSWORD`
- **Impact:** ❌ COMPLETE MISMATCH - Auth failure

#### Database-related variables:
- bootstrap.sh: `DB_PASSWORD` (no WTC_ prefix)
- wtc-api: `WTC_DB_PASSWORD`, `WTC_DB_HOST`, `WTC_DB_PORT`, `WTC_DB_USER`, `WTC_DB_NAME`
- **Pattern:** wtc-api expects WTC_ prefix, bootstrap omits it

---

## 6. ENV VAR CONFLICTS

### docker-compose.yml declares:
```yaml
POSTGRES_USER: wtc                    # Database service
POSTGRES_PASSWORD: wtc_password       # ❌ Should be ${DB_PASSWORD}
POSTGRES_DB: water_treatment
DATABASE_URL: postgresql://wtc:wtc_password@...  # ❌ Should use ${DB_PASSWORD}
API_HOST: 0.0.0.0
WTC_API_PORT: ${WTC_API_PORT:-8000}
WTC_UI_PORT: ${WTC_UI_PORT:-8080}
```

### bootstrap.sh sets:
```bash
GRAFANA_PASSWORD=$(generate_password 24)
DB_PASSWORD=$(generate_password 32)
WTC_API_PORT=${WTC_API_PORT:-8000}
WTC_UI_PORT=${WTC_UI_PORT:-8080}
WTC_GRAFANA_PORT=${WTC_GRAFANA_PORT:-3000}
WTC_DB_PORT=${WTC_DB_PORT:-5432}
```

### wtc-api reads (os.getenv):
```python
DATABASE_URL or WTC_DATABASE_URL or construct from:
  - WTC_DB_HOST
  - WTC_DB_PORT
  - WTC_DB_USER
  - WTC_DB_PASSWORD  # ❌ EXPECTS THIS
  - WTC_DB_NAME
```

### Conflicts Summary:
1. **bootstrap sets `DB_PASSWORD`** → wtc-api expects **`WTC_DB_PASSWORD`**
2. **docker-compose hardcodes `wtc_password`** → Ignores both bootstrap and wtc-api vars
3. **DATABASE_URL construction mismatch** → Hardcoded in docker-compose, dynamic in wtc-api

---

## 7. AUTH PATH FAILURE TRACE

### Exact Failure Point:

```
1. bootstrap.sh generates DB_PASSWORD
   ✓ Password generated: $(generate_password 32)
   ✓ Exported to environment
   ✓ Written to /opt/water-controller/docker/.env

2. docker compose up reads .env
   ❌ POSTGRES_PASSWORD ignores DB_PASSWORD
   ❌ Uses hardcoded: wtc_password
   Result: PostgreSQL user 'wtc' has password 'wtc_password'

3. wtc-api container starts
   ❌ DATABASE_URL hardcoded with wtc_password in docker-compose.yml
   Result: Connects successfully (but uses weak default password)

4. If DATABASE_URL not set, wtc-api constructs from components:
   ❌ Reads WTC_DB_PASSWORD (not DB_PASSWORD)
   ❌ Gets empty string (default in ports.py:179)
   Result: postgresql://wtc:@database:5432/water_treatment
   ❌ Auth failure: password mismatch

5. Failure occurs at:
   Database connection attempt (models/base.py:29)
   Mismatch: Empty password vs 'wtc_password'
```

**Conclusion:** System currently "works" by accident because DATABASE_URL is hardcoded with the weak default password. If anyone tries to use the bootstrap-generated secure password, auth fails.

---

## 8. STANDARDIZATION PLAN

### Principle: Use WTC_ prefix for all Water Treatment Controller variables

### Python (wtc-api) - Already Compliant:
- ✓ Functions/variables: `snake_case`
- ✓ Classes: `PascalCase`
- ✓ Constants: `UPPER_SNAKE`
- ✓ Private: `_leading_underscore`

### Shell (bootstrap.sh) - Needs Updates:
- Env vars: `WTC_*` prefix (add WTC_ to DB_PASSWORD → WTC_DB_PASSWORD)
- Local vars: `lower_snake`
- Functions: `lower_snake`

### Config/Env - Standardize on WTC_ prefix:
- All env vars: `WTC_UPPER_SNAKE`
- Config file keys: `lower_snake` (YAML) or `WTC_UPPER_SNAKE` (env files)

---

## 9. RENAME MAP (CRITICAL FOR AUTH FIX)

### High Priority (Auth Failure Fix):

| Current | Standard | Scope | Files |
|---------|----------|-------|-------|
| `DB_PASSWORD` | `WTC_DB_PASSWORD` | bootstrap.sh | Lines 602, 746-748, 760-761, 774-775, 806-807, 851 |
| `POSTGRES_PASSWORD: wtc_password` | `POSTGRES_PASSWORD: ${WTC_DB_PASSWORD}` | docker-compose.yml | Line 23 |
| `DATABASE_URL: postgresql://wtc:wtc_password@...` | `DATABASE_URL: postgresql://wtc:${WTC_DB_PASSWORD}@...` | docker-compose.yml | Line 55 |
| `GRAFANA_PASSWORD` | `WTC_GRAFANA_PASSWORD` | bootstrap.sh, docker-compose.yml | Multiple locations (optional - already works) |

### Medium Priority (Consistency):

| Current | Standard | Scope | Files |
|---------|----------|-------|-------|
| `DEPLOYMENT_MODE` | `WTC_DEPLOYMENT_MODE` | bootstrap.sh | Global variable |
| `QUIET_MODE` | Keep as-is (script internal) | bootstrap.sh | Global variable |

---

## 10. IMMEDIATE FIX (AUTH FAILURE)

### Required Changes:

#### File 1: `/home/user/Water-Controller/bootstrap.sh`
```bash
# Change line 602:
- echo "DB_PASSWORD=${DB_PASSWORD}"
+ echo "WTC_DB_PASSWORD=${WTC_DB_PASSWORD}"

# Change lines 746-748:
- if [[ -z "${DB_PASSWORD:-}" ]]; then
-     log_info "Generating secure database password..."
-     export DB_PASSWORD=$(generate_password 32)
+ if [[ -z "${WTC_DB_PASSWORD:-}" ]]; then
+     log_info "Generating secure database password..."
+     export WTC_DB_PASSWORD=$(generate_password 32)

# Change line 760:
- echo "DB_PASSWORD=$DB_PASSWORD"
+ echo "WTC_DB_PASSWORD=$WTC_DB_PASSWORD"

# Change lines 774-775, 806-807 (4 occurrences):
- export DB_PASSWORD="$DB_PASSWORD"
+ export WTC_DB_PASSWORD="$WTC_DB_PASSWORD"

# Change line 851 (display only, not critical):
# No change needed - display value
```

#### File 2: `/home/user/Water-Controller/docker/docker-compose.yml`
```yaml
# Change line 23:
-     POSTGRES_PASSWORD: wtc_password
+     POSTGRES_PASSWORD: ${WTC_DB_PASSWORD}

# Change line 55:
-     DATABASE_URL: postgresql://wtc:wtc_password@database:${WTC_DB_PORT:-5432}/water_treatment
+     DATABASE_URL: postgresql://wtc:${WTC_DB_PASSWORD}@database:${WTC_DB_PORT:-5432}/water_treatment
```

#### File 3: `/home/user/Water-Controller/docker/docker-compose.prod.yml`
```yaml
# Change line 53:
-     POSTGRES_PASSWORD: wtc_password
+     POSTGRES_PASSWORD: ${WTC_DB_PASSWORD}

# Change line 91:
-     DATABASE_URL: postgresql://wtc:wtc_password@database:${WTC_DB_PORT:-5432}/water_treatment
+     DATABASE_URL: postgresql://wtc:${WTC_DB_PASSWORD}@database:${WTC_DB_PORT:-5432}/water_treatment

# Change line 190 (optional, already uses env var):
-     GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
+     GF_SECURITY_ADMIN_PASSWORD: ${WTC_GRAFANA_PASSWORD:-admin}
```

---

## 11. POST-FIX VALIDATION

### Verification Steps:

```bash
# 1. Check environment variables are set
grep -r "WTC_DB_PASSWORD" bootstrap.sh docker/docker-compose*.yml

# 2. Verify no hardcoded passwords remain
grep -r "wtc_password" docker/docker-compose*.yml
# Should only appear in comments, not in actual values

# 3. Build and start
docker compose down -v
export WTC_DB_PASSWORD=$(openssl rand -base64 32)
export WTC_GRAFANA_PASSWORD=$(openssl rand -base64 24)
docker compose up --build -d

# 4. Check API logs for successful database connection
docker logs wtc-api | grep -i "database"

# 5. Test auth endpoint
curl http://localhost:8000/health
# Should show database: "status": "ok"

# 6. Verify database password in container
docker exec wtc-database psql -U wtc -d water_treatment -c "SELECT 1"
# Should connect successfully

# 7. Check .env file created by bootstrap
cat /opt/water-controller/docker/.env
# Should contain WTC_DB_PASSWORD=<generated-value>
```

### Expected Outcomes:
- [ ] docker-compose up builds without env var warnings
- [ ] wtc-api logs show successful config load
- [ ] Auth endpoint responds with healthy database status
- [ ] All env vars from bootstrap reach wtc-api
- [ ] No undefined variable errors in logs
- [ ] Generated secure passwords are actually used (not defaults)

---

## 12. ADDITIONAL FINDINGS

### Security Concerns:
1. ❌ Hardcoded weak default password `wtc_password` in multiple locations
2. ❌ Generated secure passwords from bootstrap are ignored
3. ⚠️ Password stored in plaintext in .env files (acceptable for Docker, but document)

### Documentation Updates Needed:
1. Update README.md to remove references to `wtc_password`
2. Update docs/guides/DOCKER_DEPLOYMENT.md with new variable names
3. Update docs/guides/CONFIGURATION.md with standardized naming
4. Update .env.example files to use WTC_ prefix consistently

### Test Coverage Needed:
1. Integration test for bootstrap → docker → API password flow
2. Unit test for env var precedence in ports.py
3. E2E test for auth system with generated passwords

---

## 13. REFERENCES

### Files Analyzed:
- `/home/user/Water-Controller/bootstrap.sh` (1858 lines)
- `/home/user/Water-Controller/docker/docker-compose.yml` (296 lines)
- `/home/user/Water-Controller/docker/docker-compose.prod.yml`
- `/home/user/Water-Controller/web/api/app/main.py` (417 lines)
- `/home/user/Water-Controller/web/api/app/core/auth.py` (222 lines)
- `/home/user/Water-Controller/web/api/app/core/config.py` (181 lines)
- `/home/user/Water-Controller/web/api/app/core/ports.py` (235 lines)
- `/home/user/Water-Controller/web/api/app/models/base.py` (123 lines)
- `/home/user/Water-Controller/web/api/.env.example` (73 lines)
- `/home/user/Water-Controller/config/ports.env` (94 lines)

### Related Issues:
- Industrial SCADA security best practices
- PEP 8 Python naming conventions
- Bash scripting best practices (UPPER_SNAKE for env vars)
- Docker environment variable precedence
- PostgreSQL authentication mechanisms

---

**Report Generated:** 2026-01-17
**Auditor:** Claude (Sonnet 4.5)
**Priority:** CRITICAL - Auth system currently non-functional with secure passwords
