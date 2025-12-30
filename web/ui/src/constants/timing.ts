/**
 * Timing Constants
 * Centralized timing configuration for polling, animations, and timeouts
 */

export const TIMING = {
  /**
   * Polling intervals for data refresh
   */
  POLLING: {
    /** Real-time critical data (1 second) */
    FAST: 1000,
    /** Standard status updates (5 seconds) */
    NORMAL: 5000,
    /** Background/non-critical data (30 seconds) */
    SLOW: 30000,
    /** Very slow polling for rarely-changing data (60 seconds) */
    VERY_SLOW: 60000,
  },

  /**
   * Stale data thresholds - when data is considered stale
   */
  STALE_THRESHOLDS: {
    /** Warning: data may be slightly outdated (5 seconds) */
    WARNING_MS: 5000,
    /** Critical: data is significantly outdated (30 seconds) */
    CRITICAL_MS: 30000,
  },

  /**
   * Toast notification durations
   */
  TOAST: {
    /** Default duration for info/success toasts (5 seconds) */
    DEFAULT_MS: 5000,
    /** Duration for error toasts (8 seconds) */
    ERROR_MS: 8000,
    /** Permanent toast (0 = no auto-dismiss) */
    PERMANENT: 0,
  },

  /**
   * Animation durations
   */
  ANIMATION: {
    /** Standard transition duration (150ms) */
    TRANSITION_MS: 150,
    /** Alarm flash animation interval (500ms) */
    ALARM_FLASH_MS: 500,
    /** Fade in/out duration (200ms) */
    FADE_MS: 200,
  },

  /**
   * Timeout durations
   */
  TIMEOUTS: {
    /** API request timeout (10 seconds) */
    API_REQUEST_MS: 10000,
    /** Network discovery timeout (5 seconds) */
    DISCOVERY_MS: 5000,
    /** Control command timeout (5 seconds) */
    CONTROL_COMMAND_MS: 5000,
    /** Debounce delay for search inputs (300ms) */
    DEBOUNCE_MS: 300,
  },

  /**
   * Session and authentication
   */
  SESSION: {
    /** Command mode timeout (5 minutes) */
    COMMAND_MODE_MS: 5 * 60 * 1000,
    /** Session refresh interval (1 minute) */
    REFRESH_MS: 60000,
  },

  /**
   * WebSocket connection settings
   */
  WEBSOCKET: {
    /** Reconnect attempt interval (3 seconds) */
    RECONNECT_INTERVAL_MS: 3000,
    /** Maximum reconnection attempts before giving up */
    MAX_RECONNECT_ATTEMPTS: 10,
  },
} as const;

/**
 * Embedded system timing configuration
 * Use these values for resource-constrained devices
 */
export const EMBEDDED_TIMING = {
  POLLING: {
    FAST: 2000,      // Reduced from 1000
    NORMAL: 10000,   // Reduced from 5000
    SLOW: 60000,     // Reduced from 30000
    VERY_SLOW: 120000,
  },
} as const;

/**
 * Get appropriate timing based on device capabilities
 */
export function getPollingInterval(
  type: keyof typeof TIMING.POLLING,
  isEmbedded: boolean = false
): number {
  return isEmbedded ? EMBEDDED_TIMING.POLLING[type] : TIMING.POLLING[type];
}
