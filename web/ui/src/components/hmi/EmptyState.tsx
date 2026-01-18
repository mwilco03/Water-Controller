'use client';

/**
 * HMI Empty State Component
 *
 * Displays a message when there's no data or content to show:
 * - No alarms (positive empty state)
 * - No search results
 * - No data available
 * - Error loading data
 *
 * Design principles:
 * - Clear, concise messaging
 * - Appropriate icons for context
 * - Optional action button
 * - ISA-101 compliant colors
 */

import { ReactNode } from 'react';
import clsx from 'clsx';

export type EmptyStateVariant = 'default' | 'success' | 'warning' | 'error' | 'offline';

interface EmptyStateProps {
  /** Main title */
  title: string;
  /** Description text */
  description?: string;
  /** Variant determines icon and colors */
  variant?: EmptyStateVariant;
  /** Custom icon (overrides variant icon) */
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
  icon: string;
  title: string;
  description: string;
  padding: string;
}> = {
  sm: {
    icon: 'w-8 h-8 max-w-8 max-h-8',
    title: 'text-sm',
    description: 'text-xs',
    padding: 'py-4 px-3',
  },
  md: {
    icon: 'w-10 h-10 max-w-10 max-h-10',
    title: 'text-base',
    description: 'text-sm',
    padding: 'py-6 px-4',
  },
  lg: {
    icon: 'w-12 h-12 max-w-12 max-h-12',
    title: 'text-lg',
    description: 'text-sm',
    padding: 'py-8 px-6',
  },
};

const variantConfig: Record<EmptyStateVariant, {
  iconBg: string;
  iconColor: string;
  icon: ReactNode;
}> = {
  default: {
    iconBg: 'bg-hmi-bg',
    iconColor: 'text-hmi-muted',
    icon: (
      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
      </svg>
    ),
  },
  success: {
    iconBg: 'bg-status-ok-light',
    iconColor: 'text-status-ok-dark',
    icon: (
      <svg fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
      </svg>
    ),
  },
  warning: {
    iconBg: 'bg-status-warning-light',
    iconColor: 'text-status-warning-dark',
    icon: (
      <svg fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
      </svg>
    ),
  },
  error: {
    iconBg: 'bg-status-alarm-light',
    iconColor: 'text-status-alarm-dark',
    icon: (
      <svg fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
      </svg>
    ),
  },
  offline: {
    iconBg: 'bg-status-offline-light',
    iconColor: 'text-status-offline-dark',
    icon: (
      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3m8.293 8.293l1.414 1.414" />
      </svg>
    ),
  },
};

export function EmptyState({
  title,
  description,
  variant = 'default',
  icon,
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
      {/* Icon */}
      <div
        className={clsx(
          'flex items-center justify-center rounded-full mb-4',
          sizeStyles.icon,
          'p-3',
          variantStyles.iconBg,
          variantStyles.iconColor
        )}
        aria-hidden="true"
      >
        <div className="w-full h-full">
          {icon || variantStyles.icon}
        </div>
      </div>

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
        <div className="flex flex-col sm:flex-row items-center gap-3 mt-6">
          {action && (
            <button
              type="button"
              onClick={action.onClick}
              className={clsx(
                'min-h-touch px-5 py-2.5 rounded-hmi font-medium',
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
                'min-h-touch px-5 py-2.5 rounded-hmi font-medium',
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
      description="All systems are operating normally. No alarms require attention."
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
      description="There is no data to display at this time."
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
      description="Unable to connect to the system. Please check your network connection and try again."
      action={onRetry ? { label: 'Retry Connection', onClick: onRetry } : undefined}
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
      description={message || "Something went wrong while loading the data. Please try again."}
      action={onRetry ? { label: 'Try Again', onClick: onRetry } : undefined}
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
      title="No Results Found"
      description={
        query
          ? `No results match "${query}". Try adjusting your search or filters.`
          : "No results match your search criteria."
      }
      action={onClear ? { label: 'Clear Search', onClick: onClear } : undefined}
      icon={
        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      }
      className={className}
    />
  );
}

export default EmptyState;
