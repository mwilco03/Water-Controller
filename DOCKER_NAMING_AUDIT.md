# Docker File Naming Consistency Audit

**Date:** 2026-01-17
**Auditor:** Claude Code
**Scope:** Docker configuration files, image naming, container naming, service naming

---

## Executive Summary

**Status:** ⚠️ INCONSISTENCY FOUND

The Docker configuration contains a **naming inconsistency** between the Dockerfile name and its purpose. The file `Dockerfile.web` builds the **API service** (FastAPI backend), not a generic "web" service. This creates confusion and violates the principle of clear, self-documenting naming.

---

## Findings

### 1. Dockerfile Naming

Located in `/home/user/Water-Controller/docker/`:

| Dockerfile | Purpose | Container Name | Image Name (prod) | Service Name |
|------------|---------|----------------|-------------------|--------------|
| `Dockerfile.controller` | C PROFINET controller | `wtc-controller` | N/A (not published) | `controller` |
| `Dockerfile.web` ⚠️ | **FastAPI backend** | `wtc-api` | `ghcr.io/.../api` | `api` |
| `Dockerfile.ui` | Next.js frontend | `wtc-ui` | `ghcr.io/.../ui` | `ui` |

### 2. Image Naming (GitHub Container Registry)

Published to `ghcr.io/mwilco03/water-controller/`:
- `api:${VERSION}` - Built from `Dockerfile.web` ⚠️
- `ui:${VERSION}` - Built from `Dockerfile.ui` ✓

### 3. Container Naming

All containers consistently use `wtc-` prefix:
- `wtc-database` ✓
- `wtc-api` ✓
- `wtc-ui` ✓
- `wtc-controller` ✓
- `wtc-grafana` ✓
- `wtc-loki` ✓
- `wtc-promtail` ✓
- `wtc-openplc` ✓

### 4. Service Naming (docker-compose.yml)

Service names are clear and consistent:
- `database` ✓
- `api` ✓
- `ui` ✓
- `controller` ✓
- `grafana` ✓
- `loki` ✓
- `promtail` ✓
- `openplc` ✓

---

## Issues Identified

### 🔴 CRITICAL: Dockerfile.web vs API Service

**Issue:** `Dockerfile.web` builds the FastAPI API service, but the name suggests a generic "web" component.

**Evidence:**
```yaml
# docker-compose.yml
api:
  build:
    dockerfile: docker/Dockerfile.web  # ⚠️ Naming mismatch
  container_name: wtc-api
```

```yaml
# GitHub workflow (.github/workflows/docker.yml)
build-api:
  name: Build API Image
  ...
  file: docker/Dockerfile.web  # ⚠️ Builds API from "web" Dockerfile
  images: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/api
```

**Impact:**
- **Confusion**: New developers expect `Dockerfile.web` to build web/UI components
- **Maintainability**: Violates principle of least surprise
- **Documentation**: Creates cognitive dissonance between filename and purpose

**Why This Matters:**
- The repository has THREE web-related components (controller web server, API, UI)
- The API is specifically a FastAPI REST backend, NOT a generic "web" service
- Current naming obscures the architecture

---

## Recommendations

### Priority 1: Rename Dockerfile.web → Dockerfile.api

**Rationale:**
- Aligns with service name (`api`)
- Aligns with container name (`wtc-api`)
- Aligns with published image name (`ghcr.io/.../api`)
- Matches the actual purpose (FastAPI backend)

**Changes Required:**

1. **Rename file:**
   ```bash
   git mv docker/Dockerfile.web docker/Dockerfile.api
   ```

2. **Update docker-compose.yml:**
   ```yaml
   api:
     build:
       dockerfile: docker/Dockerfile.api  # Changed from Dockerfile.web
   ```

3. **Update docker-compose.prod.yml:**
   - No changes needed (uses pre-built images)

4. **Update GitHub workflow (.github/workflows/docker.yml):**
   ```yaml
   build-api:
     ...
     with:
       file: docker/Dockerfile.api  # Changed from Dockerfile.web
   ```

5. **Update documentation:**
   - `CLAUDE.md`
   - `README.md`
   - Any architecture diagrams

**Estimated Effort:** 15 minutes
**Risk:** Low (rename operation, clear search-and-replace)

---

## Positive Findings

### ✅ Consistent Prefixing
- All containers use `wtc-` prefix
- All volumes use `wtc-` or descriptive names
- Networks use `wtc-network` / `wtc-internal` / `wtc-external`

### ✅ Clear Service Names
- Service names in docker-compose match their purpose
- No abbreviations or unclear names

### ✅ Image Repository Structure
- Clear hierarchy: `ghcr.io/owner/water-controller/{component}`
- Component names match services (api, ui)

### ✅ Build Context Consistency
- All Dockerfiles correctly use `context: ..` (parent directory)
- Proper separation of concerns (each Dockerfile builds one component)

---

## Conclusion

The Docker configuration is **mostly well-structured** with consistent naming patterns for containers, services, and images. However, the `Dockerfile.web` → API service mismatch creates unnecessary confusion and should be corrected.

**Action Items:**
1. ✅ Rename `Dockerfile.web` to `Dockerfile.api`
2. ✅ Update all references in compose files and workflows
3. ✅ Update documentation

**After Fix:**
The naming will be perfectly consistent across all layers:
```
Dockerfile.api → wtc-api container → api service → ghcr.io/.../api image
Dockerfile.ui  → wtc-ui container  → ui service  → ghcr.io/.../ui image
```
