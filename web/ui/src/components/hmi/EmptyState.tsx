'use client';

/**
 * HMI Empty State Component
 *
 * Displays a message when there's no data or content to show.
 * Uses text-only design for clarity per ISA-101 guidelines.
 */

import { ReactNode } from 'react';
import clsx from 'clsx';

export type EmptyStateVariant = 'default' | 'success' | 'warning' | 'error' | 'offline';

interface EmptyStateProps {
  /** Main title */
  title: string;
  /** Description text */
  description?: string;
  /** Variant determines colors */
  variant?: EmptyStateVariant;
  /** Custom icon (deprecated - ignored) */
  icon?: ReactNode;
  /** Primary action */
  action?: {
    label: string;
    onClick: () => void;
  };
  /** Secondary action */
  secondaryAction?: {
    label: string;
    onClick: () => void;
  };
  /** Size variant */
  size?: 'sm' | 'md' | 'lg';
  /** Additional class names */
  className?: string;
}

const sizeConfig: Record<string, {
  title: string;
  description: string;
  padding: string;
  indicator: string;
}> = {
  sm: {
    title: 'text-sm',
    description: 'text-xs',
    padding: 'py-4 px-3',
    indicator: 'text-xs px-2 py-0.5',
  },
  md: {
    title: 'text-sm',
    description: 'text-xs',
    padding: 'py-3 px-3',
    indicator: 'text-xs px-2 py-0.5',
  },
  lg: {
    title: 'text-base',
    description: 'text-sm',
    padding: 'py-4 px-4',
    indicator: 'text-sm px-3 py-1',
  },
};

const variantConfig: Record<EmptyStateVariant, {
  bg: string;
  text: string;
  label: string;
}> = {
  default: {
    bg: 'bg-hmi-bg',
    text: 'text-hmi-muted',
    label: '—',
  },
  success: {
    bg: 'bg-status-ok-light',
    text: 'text-status-ok-dark',
    label: 'OK',
  },
  warning: {
    bg: 'bg-status-warning-light',
    text: 'text-status-warning-dark',
    label: 'WARN',
  },
  error: {
    bg: 'bg-status-alarm-light',
    text: 'text-status-alarm-dark',
    label: 'ERROR',
  },
  offline: {
    bg: 'bg-status-offline-light',
    text: 'text-status-offline-dark',
    label: 'OFFLINE',
  },
};

export function EmptyState({
  title,
  description,
  variant = 'default',
  action,
  secondaryAction,
  size = 'md',
  className,
}: EmptyStateProps) {
  const sizeStyles = sizeConfig[size];
  const variantStyles = variantConfig[variant];

  return (
    <div
      className={clsx(
        'flex flex-col items-center justify-center text-center',
        sizeStyles.padding,
        className
      )}
    >
      {/* Status indicator */}
      {variant !== 'default' && (
        <span
          className={clsx(
            'rounded font-mono font-bold mb-2',
            sizeStyles.indicator,
            variantStyles.bg,
            variantStyles.text
          )}
        >
          {variantStyles.label}
        </span>
      )}

      {/* Title */}
      <h3
        className={clsx(
          'font-semibold text-hmi-text',
          sizeStyles.title
        )}
      >
        {title}
      </h3>

      {/* Description */}
      {description && (
        <p
          className={clsx(
            'text-hmi-muted mt-1 max-w-md',
            sizeStyles.description
          )}
        >
          {description}
        </p>
      )}

      {/* Actions */}
      {(action || secondaryAction) && (
        <div className="flex flex-col sm:flex-row items-center gap-3 mt-4">
          {action && (
            <button
              type="button"
              onClick={action.onClick}
              className={clsx(
                'min-h-touch px-4 py-2 rounded-hmi font-medium text-sm',
                'bg-status-info text-white',
                'hover:bg-status-info/90',
                'transition-colors duration-fast',
                'touch-manipulation',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info focus-visible:ring-offset-2'
              )}
            >
              {action.label}
            </button>
          )}
          {secondaryAction && (
            <button
              type="button"
              onClick={secondaryAction.onClick}
              className={clsx(
                'min-h-touch px-4 py-2 rounded-hmi font-medium text-sm',
                'text-hmi-text',
                'hover:bg-hmi-bg',
                'transition-colors duration-fast',
                'touch-manipulation',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info'
              )}
            >
              {secondaryAction.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Pre-built empty state variants for common SCADA scenarios
 */

export function NoAlarmsState({ className }: { className?: string }) {
  return (
    <EmptyState
      variant="success"
      title="No Active Alarms"
      description="All systems operating normally."
      className={className}
    />
  );
}

export function NoDataState({
  onRetry,
  className,
}: {
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <EmptyState
      variant="default"
      title="No Data Available"
      description="There is no data to display."
      action={onRetry ? { label: 'Refresh', onClick: onRetry } : undefined}
      className={className}
    />
  );
}

export function ConnectionErrorState({
  onRetry,
  className,
}: {
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <EmptyState
      variant="offline"
      title="Connection Lost"
      description="Unable to connect. Check network and retry."
      action={onRetry ? { label: 'Retry', onClick: onRetry } : undefined}
      className={className}
    />
  );
}

export function LoadErrorState({
  message,
  onRetry,
  className,
}: {
  message?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <EmptyState
      variant="error"
      title="Failed to Load"
      description={message || "Something went wrong. Please try again."}
      action={onRetry ? { label: 'Retry', onClick: onRetry } : undefined}
      className={className}
    />
  );
}

export function NoSearchResultsState({
  query,
  onClear,
  className,
}: {
  query?: string;
  onClear?: () => void;
  className?: string;
}) {
  return (
    <EmptyState
      variant="default"
      title="No Results"
      description={
        query
          ? `No results for "${query}".`
          : "No results match your criteria."
      }
      action={onClear ? { label: 'Clear', onClick: onClear } : undefined}
      className={className}
    />
  );
}

export default EmptyState;
