/**
 * Alarm Constants
 * Centralized alarm severity and state definitions
 */

export const ALARM_SEVERITY = {
  EMERGENCY: 'EMERGENCY',
  CRITICAL: 'CRITICAL',
  HIGH: 'HIGH',
  MEDIUM: 'MEDIUM',
  LOW: 'LOW',
  INFO: 'INFO',
} as const;

export type AlarmSeverity = typeof ALARM_SEVERITY[keyof typeof ALARM_SEVERITY];

export const ALARM_STATE = {
  ACTIVE: 'ACTIVE',
  ACTIVE_ACK: 'ACTIVE_ACK',
  CLEARED: 'CLEARED',
  CLEARED_UNACK: 'CLEARED_UNACK',
} as const;

export type AlarmState = typeof ALARM_STATE[keyof typeof ALARM_STATE];

/**
 * High severity alarms that require immediate attention
 */
export const HIGH_SEVERITY = [
  ALARM_SEVERITY.EMERGENCY,
  ALARM_SEVERITY.CRITICAL,
  ALARM_SEVERITY.HIGH,
] as const;

/**
 * Check if an alarm is high severity (emergency, critical, or high)
 */
export function isHighSeverity(severity: string | undefined): boolean {
  const normalized = severity?.toUpperCase();
  return HIGH_SEVERITY.includes(normalized as typeof HIGH_SEVERITY[number]);
}

/**
 * Check if an alarm requires acknowledgement
 */
export function requiresAcknowledgement(state: string | undefined): boolean {
  const normalized = state?.toUpperCase();
  return normalized === ALARM_STATE.ACTIVE || normalized === ALARM_STATE.CLEARED_UNACK;
}

/**
 * Check if an alarm is currently active
 */
export function isAlarmActive(state: string | undefined): boolean {
  const normalized = state?.toUpperCase();
  return normalized === ALARM_STATE.ACTIVE || normalized === ALARM_STATE.ACTIVE_ACK;
}

/**
 * Get severity priority (lower number = higher priority)
 */
export function getSeverityPriority(severity: string | undefined): number {
  switch (severity?.toUpperCase()) {
    case ALARM_SEVERITY.EMERGENCY:
      return 0;
    case ALARM_SEVERITY.CRITICAL:
      return 1;
    case ALARM_SEVERITY.HIGH:
      return 2;
    case ALARM_SEVERITY.MEDIUM:
      return 3;
    case ALARM_SEVERITY.LOW:
      return 4;
    case ALARM_SEVERITY.INFO:
      return 5;
    default:
      return 999;
  }
}

/**
 * Get a human-readable label for alarm severity
 */
export function getSeverityLabel(severity: string | undefined): string {
  switch (severity?.toUpperCase()) {
    case ALARM_SEVERITY.EMERGENCY:
      return 'Emergency';
    case ALARM_SEVERITY.CRITICAL:
      return 'Critical';
    case ALARM_SEVERITY.HIGH:
      return 'High';
    case ALARM_SEVERITY.MEDIUM:
      return 'Medium';
    case ALARM_SEVERITY.LOW:
      return 'Low';
    case ALARM_SEVERITY.INFO:
      return 'Info';
    default:
      return 'Unknown';
  }
}
