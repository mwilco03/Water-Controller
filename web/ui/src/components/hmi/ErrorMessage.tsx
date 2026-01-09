'use client';

/**
 * ErrorMessage - Actionable error message component
 *
 * Design principles:
 * - Shows "What happened" + "What to do next"
 * - Touch-friendly action buttons (48px+)
 * - Clear visual hierarchy
 * - Accessible with ARIA
 *
 * Bad: "Error: Connection refused"
 * Good: "Cannot reach RTU. Check network connection or contact maintenance."
 */

import { ReactNode } from 'react';

type ErrorSeverity = 'error' | 'warning' | 'info';

interface ErrorAction {
  label: string;
  onClick: () => void;
  primary?: boolean;
}

interface ErrorMessageProps {
  title: string;
  description?: string;
  suggestion?: string;
  severity?: ErrorSeverity;
  actions?: ErrorAction[];
  icon?: ReactNode;
  className?: string;
  dismissible?: boolean;
  onDismiss?: () => void;
}

const DefaultIcons: Record<ErrorSeverity, ReactNode> = {
  error: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  ),
  warning: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  info: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
};

const severityStyles: Record<ErrorSeverity, { container: string; icon: string; title: string }> = {
  error: {
    container: 'bg-quality-bad border-status-alarm',
    icon: 'text-status-alarm',
    title: 'text-status-alarm',
  },
  warning: {
    container: 'bg-quality-uncertain border-status-warning',
    icon: 'text-status-warning',
    title: 'text-status-warning',
  },
  info: {
    container: 'bg-blue-50 border-status-info',
    icon: 'text-status-info',
    title: 'text-status-info',
  },
};

export default function ErrorMessage({
  title,
  description,
  suggestion,
  severity = 'error',
  actions = [],
  icon,
  className = '',
  dismissible = false,
  onDismiss,
}: ErrorMessageProps) {
  const styles = severityStyles[severity];
  const displayIcon = icon ?? DefaultIcons[severity];

  return (
    <div
      className={`hmi-card p-4 border-l-4 ${styles.container} ${className}`}
      role="alert"
      aria-live="polite"
    >
      <div className="flex gap-4">
        {/* Icon */}
        <div className={`flex-shrink-0 ${styles.icon}`} aria-hidden="true">
          {displayIcon}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Title */}
          <h3 className={`font-semibold ${styles.title}`}>
            {title}
          </h3>

          {/* Description - What happened */}
          {description && (
            <p className="mt-1 text-sm text-hmi-text">
              {description}
            </p>
          )}

          {/* Suggestion - What to do */}
          {suggestion && (
            <p className="mt-2 text-sm text-hmi-muted">
              <span className="font-medium">Suggestion:</span> {suggestion}
            </p>
          )}

          {/* Actions */}
          {actions.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-3">
              {actions.map((action, index) => (
                <button
                  key={index}
                  onClick={action.onClick}
                  className={`hmi-btn ${
                    action.primary
                      ? severity === 'error'
                        ? 'hmi-btn-danger'
                        : 'hmi-btn-primary'
                      : 'hmi-btn-secondary'
                  }`}
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Dismiss button */}
        {dismissible && onDismiss && (
          <button
            onClick={onDismiss}
            className="flex-shrink-0 p-2 -m-2 text-hmi-muted hover:text-hmi-text transition-colors"
            aria-label="Dismiss message"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Common error message presets for industrial HMI scenarios
 */
export const ErrorPresets = {
  connectionFailed: (onRetry: () => void) => ({
    title: 'Connection Lost',
    description: 'Cannot reach the RTU. The device may be offline or unreachable.',
    suggestion: 'Check network connection or contact maintenance.',
    severity: 'error' as ErrorSeverity,
    actions: [{ label: 'Retry Connection', onClick: onRetry, primary: true }],
  }),

  commandFailed: (command: string, onRetry: () => void) => ({
    title: 'Command Failed',
    description: `The ${command} command could not be executed.`,
    suggestion: 'Try again. If the problem persists, check the RTU status.',
    severity: 'error' as ErrorSeverity,
    actions: [{ label: 'Retry', onClick: onRetry, primary: true }],
  }),

  validationError: (field: string, requirement: string) => ({
    title: 'Invalid Input',
    description: `${field} is not valid.`,
    suggestion: requirement,
    severity: 'warning' as ErrorSeverity,
  }),

  staleData: (dataName: string, ageSeconds: number, onRefresh: () => void) => ({
    title: 'Data May Be Stale',
    description: `${dataName} was last updated ${ageSeconds} seconds ago.`,
    suggestion: 'Refresh to get the latest values.',
    severity: 'warning' as ErrorSeverity,
    actions: [{ label: 'Refresh Now', onClick: onRefresh, primary: true }],
  }),

  networkOffline: () => ({
    title: 'Network Offline',
    description: 'No network connection detected.',
    suggestion: 'Check your network connection. Commands will be queued and sent when connection is restored.',
    severity: 'error' as ErrorSeverity,
  }),

  serverError: (onReport?: () => void) => ({
    title: 'System Error',
    description: 'An unexpected error occurred on the server.',
    suggestion: 'Your changes are preserved. Try again or contact support.',
    severity: 'error' as ErrorSeverity,
    actions: onReport
      ? [{ label: 'Report Issue', onClick: onReport }]
      : [],
  }),

  /** Interlock preventing command execution */
  interlockActive: (interlockName: string, condition: string) => ({
    title: 'Interlock Active',
    description: `${interlockName} is preventing this operation.`,
    suggestion: `Condition: ${condition}. Resolve the condition before retrying. Interlocks cannot be bypassed from this system.`,
    severity: 'warning' as ErrorSeverity,
  }),

  /** Data quality degraded - sensor may be unreliable */
  qualityDegraded: (sensorName: string, quality: 'UNCERTAIN' | 'BAD' | 'NOT_CONNECTED') => ({
    title: quality === 'NOT_CONNECTED' ? 'Sensor Not Connected' : 'Data Quality Issue',
    description: quality === 'NOT_CONNECTED'
      ? `Cannot communicate with ${sensorName}.`
      : `${sensorName} is reporting ${quality.toLowerCase()} quality data.`,
    suggestion: quality === 'NOT_CONNECTED'
      ? 'Check RTU connection and sensor wiring. Contact maintenance if issue persists.'
      : quality === 'BAD'
        ? 'Sensor may be faulty. Do not rely on this reading for control decisions.'
        : 'Data may be stale or at sensor limits. Verify reading against local gauge if available.',
    severity: quality === 'UNCERTAIN' ? 'warning' as ErrorSeverity : 'error' as ErrorSeverity,
  }),

  /** Session expired, need to re-authenticate */
  sessionExpired: (onLogin: () => void) => ({
    title: 'Session Expired',
    description: 'Your session has timed out for security.',
    suggestion: 'Log in again to continue. Any unsaved changes may be lost.',
    severity: 'warning' as ErrorSeverity,
    actions: [{ label: 'Log In', onClick: onLogin, primary: true }],
  }),

  /** Rate limited - too many requests */
  rateLimited: (retryAfterSeconds?: number) => ({
    title: 'Too Many Requests',
    description: 'Request rate limit exceeded.',
    suggestion: retryAfterSeconds
      ? `Please wait ${retryAfterSeconds} seconds before trying again.`
      : 'Please wait a moment before trying again.',
    severity: 'warning' as ErrorSeverity,
  }),

  /** RTU version mismatch - informational only */
  versionMismatch: (rtuName: string, rtuVersion: string, controllerVersion: string) => ({
    title: 'Version Mismatch',
    description: `${rtuName} is running v${rtuVersion}, controller expects v${controllerVersion}.`,
    suggestion: 'System continues operating normally. Schedule coordinated update during next maintenance window.',
    severity: 'info' as ErrorSeverity,
  }),

  /** Command rejected by RTU */
  commandRejected: (command: string, reason: string) => ({
    title: 'Command Rejected',
    description: `${command} was rejected by the RTU.`,
    suggestion: reason || 'Check equipment status and interlocks. The RTU may be in a state that prevents this operation.',
    severity: 'error' as ErrorSeverity,
  }),

  /** Historian not recording */
  historianOffline: (onCheckStatus: () => void) => ({
    title: 'Historian Not Recording',
    description: 'Historical data is not being saved.',
    suggestion: 'Current sensor values are still available. Check database connection and disk space.',
    severity: 'warning' as ErrorSeverity,
    actions: [{ label: 'Check Status', onClick: onCheckStatus }],
  }),

  /** RTU in maintenance mode */
  rtuMaintenance: (rtuName: string) => ({
    title: 'RTU in Maintenance Mode',
    description: `${rtuName} is in maintenance mode.`,
    suggestion: 'Control commands are disabled. The RTU is operating in safe state. Contact maintenance for estimated completion.',
    severity: 'info' as ErrorSeverity,
  }),
};

export { ErrorMessage };
