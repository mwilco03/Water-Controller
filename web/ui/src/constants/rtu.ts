/**
 * RTU State Constants
 * Centralized RTU state definitions for consistent usage across components
 */

export const RTU_STATES = {
  OFFLINE: 'OFFLINE',
  DISCOVERY: 'DISCOVERY',
  CONNECTING: 'CONNECTING',
  CONNECTED: 'CONNECTED',
  RUNNING: 'RUNNING',
  ERROR: 'ERROR',
  DISCONNECT: 'DISCONNECT',
} as const;

export type RtuState = typeof RTU_STATES[keyof typeof RTU_STATES];

/**
 * Control State Constants
 * States for control outputs (pumps, valves, etc.)
 */
export const CONTROL_STATES = {
  ON: 'ON',
  OFF: 'OFF',
  RUNNING: 'RUNNING',
  STOPPED: 'STOPPED',
  OPEN: 'OPEN',
  CLOSED: 'CLOSED',
  FAULT: 'FAULT',
  ERROR: 'ERROR',
  AUTO: 'AUTO',
  MANUAL: 'MANUAL',
} as const;

export type ControlState = typeof CONTROL_STATES[keyof typeof CONTROL_STATES];

/**
 * Active states - states that indicate the control is in an "on" or "active" position
 */
export const ACTIVE_STATES = [
  CONTROL_STATES.ON,
  CONTROL_STATES.RUNNING,
  CONTROL_STATES.OPEN,
] as const;

/**
 * Check if a state is an active/on state
 */
export function isActiveState(state: string | undefined): boolean {
  const normalized = state?.toUpperCase();
  return ACTIVE_STATES.includes(normalized as typeof ACTIVE_STATES[number]);
}

/**
 * Check if a state is an error/fault state
 */
export function isErrorState(state: string | undefined): boolean {
  const normalized = state?.toUpperCase();
  return normalized === CONTROL_STATES.FAULT || normalized === CONTROL_STATES.ERROR;
}

/**
 * Get a human-readable label for an RTU state
 */
export function getRtuStateLabel(state: string | undefined): string {
  switch (state?.toUpperCase()) {
    case RTU_STATES.OFFLINE:
      return 'Offline';
    case RTU_STATES.DISCOVERY:
      return 'Discovery';
    case RTU_STATES.CONNECTING:
      return 'Connecting';
    case RTU_STATES.CONNECTED:
      return 'Connected';
    case RTU_STATES.RUNNING:
      return 'Running';
    case RTU_STATES.ERROR:
      return 'Error';
    case RTU_STATES.DISCONNECT:
      return 'Disconnecting';
    default:
      return 'Unknown';
  }
}
