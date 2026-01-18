/**
 * System State Constants
 * Centralized definitions for PROFINET, service, and system health states
 * ISA-101 compliant - ensures consistent state handling across the HMI
 *
 * IMPORTANT: System states are MUTUALLY EXCLUSIVE
 * The UI must never show contradictory states (e.g., "Offline" and "Connected")
 */

/**
 * Primary System Operational State
 * These states are MUTUALLY EXCLUSIVE - only one can be true at a time
 * Order indicates priority for display (highest priority first)
 */
export const SYSTEM_OPERATIONAL_STATES = {
  /** Network disconnected - cannot reach backend API */
  DISCONNECTED: 'DISCONNECTED',
  /** System not configured - no RTUs, initial setup required */
  UNCONFIGURED: 'UNCONFIGURED',
  /** Connected but real-time transport degraded (polling fallback) */
  DEGRADED: 'DEGRADED',
  /** Fully operational - all systems connected and streaming */
  OPERATIONAL: 'OPERATIONAL',
} as const;

export type SystemOperationalState = typeof SYSTEM_OPERATIONAL_STATES[keyof typeof SYSTEM_OPERATIONAL_STATES];

/**
 * Get the primary system state label for display
 * This is the SINGLE source of truth for system state text
 */
export function getSystemOperationalStateLabel(state: SystemOperationalState): string {
  switch (state) {
    case SYSTEM_OPERATIONAL_STATES.UNCONFIGURED:
      return 'Setup Required';
    case SYSTEM_OPERATIONAL_STATES.DISCONNECTED:
      return 'Disconnected';
    case SYSTEM_OPERATIONAL_STATES.DEGRADED:
      return 'Degraded Mode';
    case SYSTEM_OPERATIONAL_STATES.OPERATIONAL:
      return 'Operational';
    default:
      return 'Unknown';
  }
}

/**
 * Get the action text for each system state
 * Tells the operator what to do to restore normal operation
 */
export function getSystemStateAction(state: SystemOperationalState): string {
  switch (state) {
    case SYSTEM_OPERATIONAL_STATES.UNCONFIGURED:
      return 'Add RTU devices to begin monitoring';
    case SYSTEM_OPERATIONAL_STATES.DISCONNECTED:
      return 'Check network connection to API server';
    case SYSTEM_OPERATIONAL_STATES.DEGRADED:
      return 'Real-time updates unavailable, using polling';
    case SYSTEM_OPERATIONAL_STATES.OPERATIONAL:
      return '';
    default:
      return '';
  }
}

/**
 * Get ISA-101 status class for system operational state
 */
export function getSystemOperationalStateClass(state: SystemOperationalState): 'ok' | 'warning' | 'alarm' | 'offline' {
  switch (state) {
    case SYSTEM_OPERATIONAL_STATES.OPERATIONAL:
      return 'ok';
    case SYSTEM_OPERATIONAL_STATES.DEGRADED:
      return 'warning';
    case SYSTEM_OPERATIONAL_STATES.DISCONNECTED:
      return 'alarm';
    case SYSTEM_OPERATIONAL_STATES.UNCONFIGURED:
      return 'offline';
    default:
      return 'offline';
  }
}

/**
 * Determine the primary system operational state from various inputs
 * This function implements the state priority logic
 * States are checked in priority order - first matching state wins
 */
export function deriveSystemOperationalState(params: {
  isApiConnected: boolean;
  isWebSocketConnected: boolean;
  rtuCount: number;
}): SystemOperationalState {
  const { isApiConnected, isWebSocketConnected, rtuCount } = params;

  // Priority 1: API disconnected is the most critical state
  if (!isApiConnected) {
    return SYSTEM_OPERATIONAL_STATES.DISCONNECTED;
  }

  // Priority 2: No RTUs configured - system is empty
  if (rtuCount === 0) {
    return SYSTEM_OPERATIONAL_STATES.UNCONFIGURED;
  }

  // Priority 3: WebSocket degraded (polling fallback)
  if (!isWebSocketConnected) {
    return SYSTEM_OPERATIONAL_STATES.DEGRADED;
  }

  // All systems operational
  return SYSTEM_OPERATIONAL_STATES.OPERATIONAL;
}

/**
 * Data Freshness States
 * For indicating when displayed values may be stale
 */
export const DATA_FRESHNESS_STATES = {
  /** Data is current (received within expected interval) */
  FRESH: 'FRESH',
  /** Data may be slightly outdated (5-30 seconds old) */
  STALE: 'STALE',
  /** Data is significantly outdated (>30 seconds old) */
  EXPIRED: 'EXPIRED',
} as const;

export type DataFreshnessState = typeof DATA_FRESHNESS_STATES[keyof typeof DATA_FRESHNESS_STATES];

/**
 * Get data freshness state from timestamp
 */
export function getDataFreshnessState(
  lastUpdate: Date | string | undefined,
  staleThresholdMs: number = 5000,
  expiredThresholdMs: number = 30000
): DataFreshnessState {
  if (!lastUpdate) return DATA_FRESHNESS_STATES.EXPIRED;

  const timestamp = typeof lastUpdate === 'string' ? new Date(lastUpdate) : lastUpdate;
  const ageMs = Date.now() - timestamp.getTime();

  if (ageMs > expiredThresholdMs) return DATA_FRESHNESS_STATES.EXPIRED;
  if (ageMs > staleThresholdMs) return DATA_FRESHNESS_STATES.STALE;
  return DATA_FRESHNESS_STATES.FRESH;
}

/**
 * PROFINET I/O Controller States
 * Based on PROFINET IO Controller state machine
 */
export const PROFINET_STATES = {
  /** Controller running and communicating */
  RUN: 'RUN',
  /** Controller stopped, no cyclic communication */
  STOP: 'STOP',
  /** Controller in fault state, communication failed */
  FAULT: 'FAULT',
  /** Controller starting up, not yet operational */
  STARTUP: 'STARTUP',
  /** Controller performing parameterization */
  PARAMETERIZING: 'PARAMETERIZING',
  /** Controller not responding */
  NOT_CONNECTED: 'NOT_CONNECTED',
} as const;

export type ProfinetState = typeof PROFINET_STATES[keyof typeof PROFINET_STATES];

/**
 * Service Health States
 * Used for backend services status
 */
export const SERVICE_STATES = {
  /** Service running normally */
  RUNNING: 'RUNNING',
  /** Service starting up */
  STARTING: 'STARTING',
  /** Service stopped */
  STOPPED: 'STOPPED',
  /** Service in degraded state */
  DEGRADED: 'DEGRADED',
  /** Service failed/crashed */
  FAILED: 'FAILED',
  /** Service status unknown */
  UNKNOWN: 'UNKNOWN',
} as const;

export type ServiceState = typeof SERVICE_STATES[keyof typeof SERVICE_STATES];

/**
 * System Health States
 * Overall system status indicator
 */
export const SYSTEM_HEALTH_STATES = {
  /** All systems normal */
  HEALTHY: 'HEALTHY',
  /** Some systems degraded but operational */
  DEGRADED: 'DEGRADED',
  /** System has active alarms */
  WARNING: 'WARNING',
  /** System in critical state */
  CRITICAL: 'CRITICAL',
  /** System offline or unreachable */
  OFFLINE: 'OFFLINE',
} as const;

export type SystemHealthState = typeof SYSTEM_HEALTH_STATES[keyof typeof SYSTEM_HEALTH_STATES];

/**
 * Historian States
 * Recording status for data historian
 */
export const HISTORIAN_STATES = {
  /** Actively recording data to database */
  RECORDING: 'RECORDING',
  /** Buffering data locally, database unavailable */
  BUFFER_ONLY: 'BUFFER_ONLY',
  /** Historian offline */
  OFFLINE: 'OFFLINE',
  /** Connection error to database */
  ERROR: 'ERROR',
} as const;

export type HistorianState = typeof HISTORIAN_STATES[keyof typeof HISTORIAN_STATES];

/**
 * Resource Usage Thresholds
 * Warning and critical levels for system resources
 */
export const RESOURCE_THRESHOLDS = {
  CPU: {
    WARNING_PERCENT: 70,
    CRITICAL_PERCENT: 90,
  },
  MEMORY: {
    WARNING_PERCENT: 80,
    CRITICAL_PERCENT: 95,
  },
  DISK: {
    WARNING_PERCENT: 80,
    CRITICAL_PERCENT: 95,
  },
  CYCLE_TIME: {
    /** Expected cycle time in ms */
    EXPECTED_MS: 1000,
    /** Warning if cycle time exceeds expected + this value */
    WARNING_DELTA_MS: 100,
    /** Critical if cycle time exceeds expected + this value */
    CRITICAL_DELTA_MS: 500,
  },
} as const;

/**
 * Get health status from resource usage percentage
 */
export function getResourceHealthStatus(
  value: number,
  thresholds: { WARNING_PERCENT: number; CRITICAL_PERCENT: number }
): 'ok' | 'warning' | 'alarm' {
  if (value >= thresholds.CRITICAL_PERCENT) return 'alarm';
  if (value >= thresholds.WARNING_PERCENT) return 'warning';
  return 'ok';
}

/**
 * Get PROFINET state display label
 */
export function getProfinetStateLabel(state: ProfinetState | string | undefined): string {
  switch (state) {
    case PROFINET_STATES.RUN:
      return 'Running';
    case PROFINET_STATES.STOP:
      return 'Stopped';
    case PROFINET_STATES.FAULT:
      return 'Fault';
    case PROFINET_STATES.STARTUP:
      return 'Starting';
    case PROFINET_STATES.PARAMETERIZING:
      return 'Configuring';
    case PROFINET_STATES.NOT_CONNECTED:
      return 'Not Connected';
    default:
      return 'Unknown';
  }
}

/**
 * Get service state display label
 */
export function getServiceStateLabel(state: ServiceState | string | undefined): string {
  switch (state?.toUpperCase()) {
    case SERVICE_STATES.RUNNING:
      return 'Running';
    case SERVICE_STATES.STARTING:
      return 'Starting';
    case SERVICE_STATES.STOPPED:
      return 'Stopped';
    case SERVICE_STATES.DEGRADED:
      return 'Degraded';
    case SERVICE_STATES.FAILED:
      return 'Failed';
    default:
      return 'Unknown';
  }
}

/**
 * Get historian state display label
 */
export function getHistorianStateLabel(state: HistorianState | string | undefined): string {
  switch (state) {
    case HISTORIAN_STATES.RECORDING:
      return 'Recording';
    case HISTORIAN_STATES.BUFFER_ONLY:
      return 'Buffering';
    case HISTORIAN_STATES.OFFLINE:
      return 'Offline';
    case HISTORIAN_STATES.ERROR:
      return 'Error';
    default:
      return 'Unknown';
  }
}

/**
 * Map state to ISA-101 status indicator class
 */
export function getProfinetStateClass(state: ProfinetState | string | undefined): 'ok' | 'warning' | 'alarm' | 'offline' {
  switch (state) {
    case PROFINET_STATES.RUN:
      return 'ok';
    case PROFINET_STATES.STARTUP:
    case PROFINET_STATES.PARAMETERIZING:
      return 'warning';
    case PROFINET_STATES.FAULT:
      return 'alarm';
    case PROFINET_STATES.STOP:
    case PROFINET_STATES.NOT_CONNECTED:
    default:
      return 'offline';
  }
}

/**
 * Map service state to ISA-101 status indicator class
 */
export function getServiceStateClass(state: ServiceState | string | undefined): 'ok' | 'warning' | 'alarm' | 'offline' {
  switch (state?.toUpperCase()) {
    case SERVICE_STATES.RUNNING:
      return 'ok';
    case SERVICE_STATES.STARTING:
    case SERVICE_STATES.DEGRADED:
      return 'warning';
    case SERVICE_STATES.FAILED:
      return 'alarm';
    case SERVICE_STATES.STOPPED:
    case SERVICE_STATES.UNKNOWN:
    default:
      return 'offline';
  }
}

/**
 * Map historian state to ISA-101 status indicator class
 */
export function getHistorianStateClass(state: HistorianState | string | undefined): 'ok' | 'warning' | 'alarm' | 'offline' {
  switch (state) {
    case HISTORIAN_STATES.RECORDING:
      return 'ok';
    case HISTORIAN_STATES.BUFFER_ONLY:
      return 'warning';
    case HISTORIAN_STATES.ERROR:
      return 'alarm';
    case HISTORIAN_STATES.OFFLINE:
    default:
      return 'offline';
  }
}

/**
 * System restart reason codes
 */
export const RESTART_REASONS = {
  NORMAL: 'NORMAL',
  WATCHDOG: 'WATCHDOG',
  CRASH: 'CRASH',
  POWER_CYCLE: 'POWER_CYCLE',
  USER_REQUEST: 'USER_REQUEST',
  UPGRADE: 'UPGRADE',
  UNKNOWN: 'UNKNOWN',
} as const;

export type RestartReason = typeof RESTART_REASONS[keyof typeof RESTART_REASONS];

/**
 * Get restart reason label
 */
export function getRestartReasonLabel(reason: RestartReason | string | undefined): string {
  switch (reason) {
    case RESTART_REASONS.NORMAL:
      return 'Normal Startup';
    case RESTART_REASONS.WATCHDOG:
      return 'Watchdog Reset';
    case RESTART_REASONS.CRASH:
      return 'Crash Recovery';
    case RESTART_REASONS.POWER_CYCLE:
      return 'Power Cycle';
    case RESTART_REASONS.USER_REQUEST:
      return 'User Requested';
    case RESTART_REASONS.UPGRADE:
      return 'After Upgrade';
    default:
      return 'Unknown';
  }
}

/**
 * Check if restart reason is abnormal (should be highlighted)
 */
export function isAbnormalRestart(reason: RestartReason | string | undefined): boolean {
  return reason === RESTART_REASONS.WATCHDOG ||
         reason === RESTART_REASONS.CRASH ||
         reason === RESTART_REASONS.UNKNOWN;
}
