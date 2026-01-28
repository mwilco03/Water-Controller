/**
 * ISA-101 Color System
 * Centralized color definitions following ISA-101 HMI standards
 */

export const ISA101_COLORS = {
  /**
   * State colors for equipment status
   */
  states: {
    running: '#10b981',     // Green - equipment running/healthy
    connecting: '#f59e0b',  // Amber - connecting/transitioning
    offline: '#6b7280',     // Gray - offline/unknown
    error: '#ef4444',       // Red - error/fault
    discovery: '#3b82f6',   // Blue - discovery/scanning
  },

  /**
   * Alarm severity colors
   */
  alarms: {
    emergency: '#dc2626',   // Dark red - emergency
    critical: '#ef4444',    // Red - critical
    high: '#f97316',        // Orange - high
    medium: '#f59e0b',      // Amber - medium
    low: '#eab308',         // Yellow - low
    info: '#3b82f6',        // Blue - informational
  },

  /**
   * Data quality colors
   */
  quality: {
    good: '#10b981',        // Green - good quality
    uncertain: '#f59e0b',   // Amber - uncertain quality
    bad: '#ef4444',         // Red - bad quality
    notConnected: '#6b7280', // Gray - not connected
  },

  /**
   * Control state colors
   */
  control: {
    on: '#10b981',          // Green - on/running/open
    off: '#6b7280',         // Gray - off/stopped/closed
    fault: '#ef4444',       // Red - fault/error
    auto: '#3b82f6',        // Blue - automatic mode
    manual: '#8b5cf6',      // Purple - manual mode
  },

  /**
   * UI element colors
   */
  ui: {
    primary: '#3b82f6',     // Blue - primary actions
    secondary: '#6b7280',   // Gray - secondary actions
    success: '#10b981',     // Green - success states
    warning: '#f59e0b',     // Amber - warning states
    danger: '#ef4444',      // Red - danger/destructive
    info: '#0ea5e9',        // Sky blue - informational
  },
} as const;

/**
 * Get state color based on state string
 */
export function getStateColor(state: string | undefined): string {
  const normalized = state?.toUpperCase() ?? 'OFFLINE';
  switch (normalized) {
    case 'RUNNING':
    case 'ONLINE':
    case 'CONNECTED':
      return ISA101_COLORS.states.running;
    case 'CONNECTING':
    case 'STARTING':
    case 'STOPPING':
    case 'DISCONNECT':
      return ISA101_COLORS.states.connecting;
    case 'DISCOVERY':
    case 'SCANNING':
      return ISA101_COLORS.states.discovery;
    case 'ERROR':
    case 'FAULT':
    case 'FAILED':
      return ISA101_COLORS.states.error;
    case 'OFFLINE':
    case 'DISCONNECTED':
    case 'UNKNOWN':
    default:
      return ISA101_COLORS.states.offline;
  }
}

/**
 * Get control state color
 */
export function getControlColor(state: string | undefined): string {
  const normalized = state?.toUpperCase();
  switch (normalized) {
    case 'ON':
    case 'RUNNING':
    case 'OPEN':
      return ISA101_COLORS.control.on;
    case 'OFF':
    case 'STOPPED':
    case 'CLOSED':
      return ISA101_COLORS.control.off;
    case 'FAULT':
    case 'ERROR':
      return ISA101_COLORS.control.fault;
    case 'AUTO':
    case 'AUTOMATIC':
      return ISA101_COLORS.control.auto;
    case 'MANUAL':
      return ISA101_COLORS.control.manual;
    default:
      return ISA101_COLORS.control.off;
  }
}

/**
 * Get alarm severity color
 */
export function getAlarmColor(severity: string | undefined): string {
  const normalized = severity?.toUpperCase();
  switch (normalized) {
    case 'EMERGENCY':
      return ISA101_COLORS.alarms.emergency;
    case 'CRITICAL':
      return ISA101_COLORS.alarms.critical;
    case 'HIGH':
      return ISA101_COLORS.alarms.high;
    case 'MEDIUM':
      return ISA101_COLORS.alarms.medium;
    case 'LOW':
      return ISA101_COLORS.alarms.low;
    case 'INFO':
    default:
      return ISA101_COLORS.alarms.info;
  }
}

/**
 * Get quality color based on quality code
 */
export function getQualityColor(qualityCode: number): string {
  if (qualityCode === 0x00) return ISA101_COLORS.quality.good;
  if ((qualityCode & 0xC0) === 0x40) return ISA101_COLORS.quality.uncertain;
  if ((qualityCode & 0xC0) === 0x80) return ISA101_COLORS.quality.bad;
  return ISA101_COLORS.quality.notConnected;
}

/**
 * Get background color with transparency for a given state
 */
export function getStateBackgroundColor(state: string | undefined, opacity: number = 0.15): string {
  const baseColor = getStateColor(state);
  return `${baseColor}${Math.round(opacity * 255).toString(16).padStart(2, '0')}`;
}
