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
    <span className="inline-flex items-center justify-center w-6 h-6 text-xs font-bold bg-status-alarm text-white rounded">
      !
    </span>
  ),
  warning: (
    <span className="inline-flex items-center justify-center w-6 h-6 text-xs font-bold bg-status-warning text-white rounded">
      !
    </span>
  ),
  info: (
    <span className="inline-flex items-center justify-center w-6 h-6 text-xs font-bold bg-status-info text-white rounded">
      i
    </span>
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
            <span className="inline-flex items-center justify-center w-5 h-5 text-sm font-bold">
              X
            </span>
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
};
