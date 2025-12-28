#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# p-net deterministic build script
#
# Goals:
# - No silent fallbacks
# - No internet dependency beyond initial fetch
# - Correct upstream build invocation
# - Field-safe failure behavior
###############################################################################

# -------------------------
# Configuration
# -------------------------
PNET_REPO="https://github.com/rtlabs-com/p-net.git"

# Pin to a COMMIT, not a tag or branch
# (example commit – replace with the one you have validated)
PNET_COMMIT="6d2c3c0e4e9e8c7b0c9d9bfae8c0a6f4a1b2c3d4"

PREFIX="/usr/local"
BUILD_ROOT="/opt/water-controller/deps"
SRC_DIR="${BUILD_ROOT}/pnet-src"
BUILD_DIR="${BUILD_ROOT}/pnet-build"

ARCH="$(uname -m)"

# -------------------------
# Helpers
# -------------------------
log() {
  echo "[p-net] $*"
}

fail() {
  echo "[p-net][ERROR] $*" >&2
  exit 1
}

# -------------------------
# Pre-flight checks
# -------------------------
log "Starting p-net build"
log "Architecture: ${ARCH}"
log "Install prefix: ${PREFIX}"

command -v git >/dev/null || fail "git not installed"
command -v make >/dev/null || fail "make not installed"
command -v gcc >/dev/null || fail "gcc not installed"

# -------------------------
# Prepare directories
# -------------------------
mkdir -p "${BUILD_ROOT}"

# -------------------------
# Fetch source (deterministic)
# -------------------------
if [[ ! -d "${SRC_DIR}/.git" ]]; then
  log "Cloning p-net repository"
  git clone "${PNET_REPO}" "${SRC_DIR}"
else
  log "Using existing p-net source tree"
fi

cd "${SRC_DIR}"

log "Checking out pinned commit ${PNET_COMMIT}"
git fetch --all --tags
git checkout --detach "${PNET_COMMIT}" || fail "Failed to checkout pinned commit"

# -------------------------
# Verify build system
# -------------------------
if [[ -f Makefile ]]; then
  BUILD_SYSTEM="make"
elif [[ -f CMakeLists.txt ]]; then
  BUILD_SYSTEM="cmake"
else
  fail "Unsupported p-net build system (no Makefile or CMakeLists.txt found)"
fi

log "Detected build system: ${BUILD_SYSTEM}"

# -------------------------
# Clean previous build
# -------------------------
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

# -------------------------
# Build
# -------------------------
case "${BUILD_SYSTEM}" in
  make)
    log "Building p-net using Makefile"

    make clean || true

    make -j"$(nproc)" \
      PREFIX="${PREFIX}"

    log "Installing p-net"
    make install PREFIX="${PREFIX}"
    ;;

  cmake)
    log "Building p-net using CMake"

    cd "${BUILD_DIR}"

    cmake "${SRC_DIR}" \
      -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
      -DCMAKE_BUILD_TYPE=Release

    make -j"$(nproc)"
    make install
    ;;

  *)
    fail "Unknown build system"
    ;;
esac

# -------------------------
# Post-install verification
# -------------------------
log "Verifying installation"

if [[ ! -d "${PREFIX}/include/pnet" && ! -f "${PREFIX}/lib/libpnet.so" ]]; then
  fail "p-net installation incomplete or missing artifacts"
fi

log "p-net build and installation successful"
