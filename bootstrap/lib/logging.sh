#!/bin/bash
# =============================================================================
# Water-Controller Bootstrap - Logging Functions
# =============================================================================
# All logging and output functions.
# Depends on: constants.sh

# Prevent double-sourcing
[[ -n "${_WTC_LOGGING_LOADED:-}" ]] && return 0
_WTC_LOGGING_LOADED=1

# =============================================================================
# Log Initialization
# =============================================================================

# Initialize log file
init_logging() {
    local log_dir
    log_dir=$(dirname "$BOOTSTRAP_LOG")
    local mkdir_error

    if [[ -w "$log_dir" ]] || [[ $EUID -eq 0 ]]; then
        if [[ $EUID -ne 0 ]]; then
            if ! mkdir_error=$(sudo mkdir -p "$log_dir" 2>&1); then
                echo "[WARN] Could not create log directory $log_dir: $mkdir_error" >&2
            fi
            if ! sudo touch "$BOOTSTRAP_LOG" 2>&1; then
                echo "[WARN] Could not create log file $BOOTSTRAP_LOG" >&2
            fi
            sudo chmod 644 "$BOOTSTRAP_LOG" 2>/dev/null || true
        else
            if ! mkdir_error=$(mkdir -p "$log_dir" 2>&1); then
                echo "[WARN] Could not create log directory $log_dir: $mkdir_error" >&2
            fi
            if ! touch "$BOOTSTRAP_LOG" 2>&1; then
                echo "[WARN] Could not create log file $BOOTSTRAP_LOG" >&2
            fi
        fi
    else
        echo "[INFO] Log directory $log_dir not writable and not root, logs may not be saved" >&2
    fi
}

# =============================================================================
# Log Writing
# =============================================================================

# Write to log file
write_log() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    if [[ -w "$BOOTSTRAP_LOG" ]] || [[ $EUID -eq 0 ]]; then
        if [[ $EUID -ne 0 ]]; then
            echo "[$timestamp] [$level] $message" | sudo tee -a "$BOOTSTRAP_LOG" >/dev/null 2>&1 || true
        else
            echo "[$timestamp] [$level] $message" >> "$BOOTSTRAP_LOG" 2>/dev/null || true
        fi
    fi
}

# =============================================================================
# Log Level Functions
# =============================================================================

log_info() {
    write_log "INFO" "$1"
    if [[ "$QUIET_MODE" != "true" ]]; then
        echo -e "${GREEN}[INFO]${NC} $1" >&2
    fi
}

log_warn() {
    write_log "WARN" "$1"
    if [[ "$QUIET_MODE" != "true" ]]; then
        echo -e "${YELLOW}[WARN]${NC} $1" >&2
    fi
}

log_error() {
    write_log "ERROR" "$1"
    # Errors always shown even in quiet mode
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_step() {
    write_log "STEP" "$1"
    if [[ "$QUIET_MODE" != "true" ]]; then
        echo -e "${BLUE}[STEP]${NC} $1" >&2
    fi
}

log_debug() {
    write_log "DEBUG" "$1"
    # Debug only goes to log file, never to console
}

log_verbose() {
    write_log "VERBOSE" "$1"
    # Verbose output only shown with --verbose flag
    if [[ "$VERBOSE_MODE" == "true" ]] && [[ "$QUIET_MODE" != "true" ]]; then
        echo -e "  $1" >&2
    fi
}
