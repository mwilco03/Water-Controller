# Database Authentication Security Audit

**Date:** 2026-01-17
**Auditor:** Claude Code
**Scope:** Database credentials, authentication configuration, security best practices

---

## Executive Summary

**Status:** 🔴 CRITICAL SECURITY ISSUES FOUND

The database authentication configuration contains **multiple critical security vulnerabilities**:
1. **Weak default password** used across development and production configurations
2. **Hardcoded credentials** in schemas and generated code
3. **Insufficient enforcement** of strong passwords in production
4. **Password leakage risk** through default values

These issues violate industrial control system security best practices and create significant risk for production deployments.

---

## Findings

### 1. Default Password Usage

#### 🔴 CRITICAL: Weak Default Password "wtc_password"

**Locations Found:**

| File/Location | Default Value | Environment Variable | Required? |
|---------------|---------------|---------------------|-----------|
| `docker/docker-compose.yml` | `wtc_password` | `DB_PASSWORD` | ❌ Optional |
| `docker/docker-compose.prod.yml` | `wtc_password` | `DB_PASSWORD` | ❌ Optional |
| `docker/grafana/provisioning/datasources/datasources.yml` | `wtc_password` | `DB_PASSWORD` | ❌ Optional |
| `schemas/config/historian.schema.yaml` | `wtc_password` | `WTC_TIMESCALE_PASSWORD` | ❌ Optional |
| `web/api/models/generated/config_models.py` | `wtc_password` | N/A | ❌ Optional |
| `schemas/config/controller.schema.yaml` | `""` (empty) | `WTC_DB_PASSWORD` | ❌ Optional |

**Evidence:**

```yaml
# docker/docker-compose.yml (line 25-26)
environment:
  POSTGRES_PASSWORD: ${DB_PASSWORD:-wtc_password}  # ⚠️ Weak default
```

```yaml
# docker/docker-compose.yml (line 59)
DATABASE_URL: postgresql://wtc:${DB_PASSWORD:-wtc_password}@database:5432/water_treatment
```

```yaml
# docker/grafana/provisioning/datasources/datasources.yml (line 16-17)
secureJsonData:
  password: ${DB_PASSWORD:-wtc_password}  # ⚠️ Same weak default
```

```python
# web/api/models/generated/config_models.py (line 1234)
password: str = Field(default="wtc_password", description="TimescaleDB password")
```

**Impact:**
- **Production Risk**: If `DB_PASSWORD` is not explicitly set, production systems use a widely-known weak password
- **Attack Surface**: Password is visible in public repository, making it known to attackers
- **Compliance**: Violates security standards requiring strong, unique passwords
- **Industrial Safety**: SCADA systems with weak credentials are prime targets for industrial espionage and sabotage

### 2. Password Enforcement

#### ⚠️ Inconsistent Password Requirements

**Grafana (STRICT):**
```yaml
# docker-compose.yml
GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:?GRAFANA_PASSWORD must be set}
```
✅ **Good**: Uses `?` syntax to fail if not set

**Database (PERMISSIVE):**
```yaml
POSTGRES_PASSWORD: ${DB_PASSWORD:-wtc_password}
```
❌ **Bad**: Falls back to weak default instead of failing

**Why the Inconsistency?**
- Grafana correctly enforces password requirement
- Database silently accepts weak default
- No clear rationale for different approaches

### 3. Database Connection String Construction

**Code Analysis (`web/api/app/core/ports.py`):**

```python
def get_database_url() -> str:
    """Priority order:
    1. DATABASE_URL (Docker/production standard)
    2. WTC_DATABASE_URL (explicit override)
    3. Construct PostgreSQL URL from WTC_DB_* components
    4. Fall back to SQLite with WTC_DB_PATH
    """
    
    # Check components
    db_host = os.environ.get("WTC_DB_HOST")
    if db_host:
        password = os.environ.get("WTC_DB_PASSWORD", "")  # ⚠️ Empty default
        
        if password:
            return f"postgresql://{user}:{password}@{db_host}:{port}/{database}"
        return f"postgresql://{user}@{db_host}:{port}/{database}"  # ⚠️ No password!
```

**Issues:**
1. ✅ **Good**: Supports passwordless connections (for peer auth, trust auth)
2. ⚠️ **Risk**: Silently constructs passwordless URLs if `WTC_DB_PASSWORD` is not set
3. ⚠️ **Risk**: No validation that PostgreSQL actually allows passwordless auth

**When Passwordless Auth Is Valid:**
- PostgreSQL `peer` authentication (local Unix socket connections)
- PostgreSQL `trust` authentication (development only)
- Certificate-based authentication

**Problem:** Code doesn't validate that the chosen auth method is appropriate for the environment.

### 4. Password Storage in Schemas

#### 🔴 Hardcoded Defaults in Source of Truth

**schemas/config/historian.schema.yaml:**
```yaml
password:
  type: string
  default: "wtc_password"  # ⚠️ Hardcoded weak password
  description: "TimescaleDB password"
  x-env-var: "WTC_TIMESCALE_PASSWORD"
  x-sensitive: true
```

**Impact:**
- Schema is marked as "source of truth" (per `CLAUDE.md`)
- Running `make generate` propagates weak default to generated code
- No mechanism to prevent weak defaults from being committed

### 5. Credential Management Infrastructure

**Positive Findings:**

✅ **Credential Setup Script Exists** (`scripts/setup-credentials.sh`):
```bash
# Generate cryptographically secure password
generate_password() {
    local length="${1:-32}"
    # Implementation generates secure random passwords
}

DB_PASSWORD=$(generate_password 32)
```

✅ **Docker Secrets Support:**
```bash
echo "$DB_PASSWORD" | docker secret create wtc_db_password -
```

✅ **Secure Storage Path:**
```bash
echo "$DB_PASSWORD" > /var/lib/water-controller/secrets/db_password
chmod 600 /var/lib/water-controller/secrets/db_password
```

**Problem:** Script is **not integrated** into main deployment workflow. Developers can easily skip it.

---

## Security Risks

### 🔴 CRITICAL RISKS

1. **Known Credential Attack**
   - Default password `wtc_password` is in public repository
   - Attacker can access any deployment where admin forgot to change password
   - SCADA systems are high-value targets

2. **Credential Stuffing**
   - Weak password enables brute force attacks
   - TimescaleDB contains sensitive industrial data (process values, alarms, audit logs)

3. **Lateral Movement**
   - Database credentials are reused across API, Grafana, and potentially controller
   - Compromise of one component exposes all components

4. **Industrial Control System Attack**
   - Database contains historian data used for process control decisions
   - Unauthorized access could enable data poisoning attacks
   - Alarm history tampering could mask critical safety events

### ⚠️ HIGH RISKS

5. **No Password Rotation**
   - No documented process for changing database password
   - Credentials likely persist across deployments

6. **Plaintext Password in Environment**
   - Environment variables visible in `docker inspect`
   - Visible in process listings (`ps auxe`)

7. **Development/Production Parity**
   - Same weak default used in both environments
   - Risk of accidental production deployment with dev credentials

---

## Compliance & Standards

### Industrial Control System Standards

**IEC 62443 (Industrial Cybersecurity):**
- ❌ **Requirement 5.1.3.1**: Strength of password-based authentication
  - Violation: Default password does not meet complexity requirements
- ❌ **Requirement 5.1.5.1**: Authenticator management
  - Violation: No enforced password change on first use

**NIST SP 800-82 (Guide to ICS Security):**
- ❌ **Section 6.2.1**: Weak or default passwords should be eliminated
  - Violation: System ships with weak default password

### General Security Standards

**OWASP Top 10:**
- ❌ **A07:2021 – Identification and Authentication Failures**
  - Violation: Permits use of default credentials

**CIS Controls:**
- ❌ **Control 5.2**: Use unique passwords
  - Violation: Default password is public knowledge

---

## Recommendations

### Priority 1: Eliminate Weak Defaults (CRITICAL)

#### 1.1 Require DB_PASSWORD in Production

**docker/docker-compose.prod.yml:**
```yaml
database:
  environment:
    # Fail fast if password not set
    POSTGRES_PASSWORD: ${DB_PASSWORD:?ERROR: DB_PASSWORD must be set. Run scripts/setup-credentials.sh}

api:
  environment:
    # Fail fast if password not set
    DATABASE_URL: postgresql://wtc:${DB_PASSWORD:?ERROR: DB_PASSWORD must be set}@database:5432/water_treatment
```

**Impact:**
- ✅ Prevents accidental production deployment with weak password
- ✅ Forces operator to set secure password
- ✅ Matches Grafana's security posture

**Estimated Effort:** 10 minutes
**Risk:** Low (improves security)

#### 1.2 Remove Password Defaults from Schemas

**schemas/config/historian.schema.yaml:**
```yaml
password:
  type: string
  # REMOVED: default: "wtc_password"  
  description: "TimescaleDB password (REQUIRED in production)"
  x-env-var: "WTC_TIMESCALE_PASSWORD"
  x-sensitive: true
  x-required-in-production: true
```

**schemas/config/controller.schema.yaml:**
```yaml
password:
  type: string
  description: "Database password (REQUIRED in production)"
  x-env-var: "WTC_DB_PASSWORD"
  x-sensitive: true
  x-required-in-production: true
```

**Follow-up:** Run `make generate` to update generated models

**Impact:**
- ✅ Removes hardcoded password from source of truth
- ✅ Generated code won't have insecure defaults
- ⚠️ May break existing configurations (BREAKING CHANGE)

**Estimated Effort:** 30 minutes (including regeneration and testing)
**Risk:** Medium (breaking change, requires migration guide)

#### 1.3 Keep Permissive Development Config

**docker/docker-compose.yml (development only):**
```yaml
database:
  environment:
    # Dev-only: Allow weak password for convenience
    # NEVER use this configuration in production
    POSTGRES_PASSWORD: ${DB_PASSWORD:-wtc_dev_password_NEVER_USE_IN_PROD}
```

Add prominent warning in file:
```yaml
# ============================================================================
# DEVELOPMENT CONFIGURATION - DO NOT USE IN PRODUCTION
# ============================================================================
# This file uses weak default passwords for development convenience.
# For production deployment, use docker-compose.prod.yml which requires
# explicit credentials via environment variables.
#
# Security: Run scripts/setup-credentials.sh before production deployment.
# ============================================================================
```

**Impact:**
- ✅ Maintains development convenience
- ✅ Clear labeling prevents production misuse
- ✅ Educates developers about security requirements

**Estimated Effort:** 5 minutes
**Risk:** Low

### Priority 2: Enhance Credential Management

#### 2.1 Integrate Credential Setup into Bootstrap

**scripts/bootstrap.sh:**
```bash
# After dependency installation, before first run
if [[ ! -f /var/lib/water-controller/secrets/db_password ]]; then
    echo "No database password found. Running credential setup..."
    ./scripts/setup-credentials.sh
fi
```

**Impact:**
- ✅ Automatic credential generation on first run
- ✅ Reduces operator error
- ✅ Ensures production systems never use defaults

#### 2.2 Add Credential Validation Script

**scripts/validate-credentials.sh:**
```bash
#!/bin/bash
# Validate that production credentials are set

check_password_strength() {
    local password="$1"
    local min_length=16
    
    if [[ ${#password} -lt $min_length ]]; then
        echo "ERROR: Password must be at least $min_length characters"
        return 1
    fi
    
    if ! echo "$password" | grep -q '[A-Z]'; then
        echo "ERROR: Password must contain uppercase letters"
        return 1
    fi
    
    if ! echo "$password" | grep -q '[a-z]'; then
        echo "ERROR: Password must contain lowercase letters"
        return 1
    fi
    
    if ! echo "$password" | grep -q '[0-9]'; then
        echo "ERROR: Password must contain numbers"
        return 1
    fi
    
    if echo "$password" | grep -iq "wtc_password"; then
        echo "ERROR: Cannot use default password"
        return 1
    fi
    
    return 0
}

# Validate DB_PASSWORD
if [[ -z "$DB_PASSWORD" ]]; then
    echo "ERROR: DB_PASSWORD not set"
    exit 1
fi

check_password_strength "$DB_PASSWORD" || exit 1

echo "✓ Database credentials validated"
```

**Integration:**
```yaml
# docker-compose.prod.yml
services:
  database:
    healthcheck:
      test: |
        /scripts/validate-credentials.sh && 
        pg_isready -U wtc -d water_treatment
```

#### 2.3 Add Pre-Deployment Checklist

**docs/deployment/PRE_DEPLOYMENT_CHECKLIST.md:**
```markdown
# Production Deployment Checklist

## Security

- [ ] Database password set (`DB_PASSWORD` environment variable)
- [ ] Database password is NOT `wtc_password` or any default value
- [ ] Database password meets complexity requirements:
  - [ ] Minimum 16 characters
  - [ ] Contains uppercase, lowercase, numbers, special characters
- [ ] Grafana password set (`GRAFANA_PASSWORD` environment variable)
- [ ] All secrets stored securely (Docker secrets or encrypted vault)
- [ ] `.env` files are NOT committed to version control
- [ ] `docker-compose.prod.yml` is used (NOT `docker-compose.yml`)
```

### Priority 3: Improve Documentation

#### 3.1 Update CLAUDE.md

```markdown
## Security

IMPORTANT: Industrial control systems require strong authentication.

- **NEVER** use default passwords in production
- Run `scripts/setup-credentials.sh` before first deployment
- Use `docker-compose.prod.yml` for production (enforces credential requirements)
- Use `docker-compose.yml` ONLY for local development
```

#### 3.2 Add Security Warning to README

```markdown
## 🔒 Security Notice

This SCADA system controls critical infrastructure. Before deploying:

1. **Generate secure credentials:**
   ```bash
   sudo ./scripts/setup-credentials.sh
   ```

2. **Never use default passwords.** The development configuration includes
   weak defaults for convenience. Production deployment will FAIL if you
   don't set `DB_PASSWORD` and `GRAFANA_PASSWORD`.

3. **Use docker-compose.prod.yml for production:**
   ```bash
   cd docker
   docker-compose -f docker-compose.prod.yml up -d
   ```

See `docs/deployment/SECURITY.md` for complete security guidelines.
```

### Priority 4: Consider Alternative Authentication

#### 4.1 Certificate-Based Authentication (Long-term)

**Benefits:**
- Eliminates password transmission
- Stronger authentication
- Supports mutual TLS

**Implementation:**
```yaml
database:
  environment:
    POSTGRES_PASSWORD: ""  # Disabled
    POSTGRES_HOST_AUTH_METHOD: cert
  volumes:
    - ./certs/server.crt:/var/lib/postgresql/server.crt:ro
    - ./certs/server.key:/var/lib/postgresql/server.key:ro
```

**Effort:** High (requires certificate infrastructure)
**Priority:** Low (future enhancement)

---

## Positive Findings

### ✅ Good Security Practices Observed

1. **Credential Setup Script**
   - Generates cryptographically strong passwords (32 characters)
   - Uses Docker secrets
   - Proper file permissions (600)

2. **Grafana Enforcement**
   - Requires explicit password with `${GRAFANA_PASSWORD:?...}` syntax
   - Sets good example for other services

3. **Separation of Dev/Prod Configs**
   - Separate `docker-compose.yml` (dev) and `docker-compose.prod.yml`
   - Opportunity to enforce different security levels

4. **Sensitive Field Marking**
   - Schemas mark password fields as `x-sensitive: true`
   - Shows awareness of credential sensitivity

5. **Connection URL Flexibility**
   - Supports both passworded and passwordless PostgreSQL auth
   - Allows for peer authentication, certificates, etc.

---

## Summary Table

| Issue | Severity | Effort | Priority | Status |
|-------|----------|--------|----------|--------|
| Weak default password "wtc_password" | 🔴 Critical | Low | P1 | ❌ Open |
| No password enforcement in prod compose | 🔴 Critical | Low | P1 | ❌ Open |
| Hardcoded password in schemas | 🔴 Critical | Medium | P1 | ❌ Open |
| Hardcoded password in generated models | 🔴 Critical | Medium | P1 | ❌ Open |
| No credential setup integration | ⚠️ High | Medium | P2 | ❌ Open |
| No password validation | ⚠️ High | Medium | P2 | ❌ Open |
| Missing security documentation | ⚠️ High | Low | P3 | ❌ Open |
| No password rotation process | ⚠️ Medium | High | P4 | ❌ Open |

---

## Conclusion

The database authentication configuration contains **critical security vulnerabilities** that must be addressed before production deployment:

1. **Immediate Action Required:**
   - Add password requirements to `docker-compose.prod.yml` (use `:?` syntax)
   - Remove hardcoded password from `historian.schema.yaml`
   - Regenerate models with `make generate`

2. **Short-term Actions:**
   - Integrate credential setup into bootstrap process
   - Add credential validation
   - Update security documentation

3. **Long-term Considerations:**
   - Implement certificate-based authentication
   - Add password rotation automation
   - Consider secrets management vault (HashiCorp Vault, AWS Secrets Manager)

**Estimated Total Effort:** 2-3 hours for Priority 1 fixes

**Risk of Not Fixing:** 
- 🔴 **CRITICAL** - Known credential attack vector
- 🔴 **CRITICAL** - Compliance violations (IEC 62443, NIST SP 800-82)
- 🔴 **CRITICAL** - Industrial safety risk (SCADA system compromise)

**Recommendation:** Address Priority 1 issues **before** any production deployment.
