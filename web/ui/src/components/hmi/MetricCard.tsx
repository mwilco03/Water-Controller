'use client';

/**
 * MetricCard Component
 *
 * A comprehensive card for displaying metrics with context.
 *
 * Design principles:
 * - Clear information hierarchy
 * - Status at a glance
 * - Touch-friendly for mobile
 * - Expandable details (collapsed by default)
 * - Works equally on mobile and desktop
 */

import { ReactNode, useState } from 'react';
import clsx from 'clsx';

export type MetricStatus = 'normal' | 'warning' | 'alarm' | 'offline';

interface MetricDetail {
  label: string;
  value: string | number;
  unit?: string;
}

interface MetricCardProps {
  /** Card title */
  title: string;
  /** Optional description */
  description?: string;
  /** Primary metric value */
  value: string | number | null | undefined;
  /** Value unit */
  unit?: string;
  /** Current status */
  status?: MetricStatus;
  /** Status message */
  statusMessage?: string;
  /** Icon for the card */
  icon?: ReactNode;
  /** Additional details (shown when expanded) */
  details?: MetricDetail[];
  /** Whether details are initially expanded */
  defaultExpanded?: boolean;
  /** Timestamp of last update */
  lastUpdate?: Date | string;
  /** Click handler for the entire card */
  onClick?: () => void;
  /** Action buttons */
  actions?: ReactNode;
  /** Additional class names */
  className?: string;
}

const statusConfig: Record<MetricStatus, {
  border: string;
  bg: string;
  text: string;
  icon: ReactNode;
}> = {
  normal: {
    border: 'border-hmi-border',
    bg: '',
    text: 'text-hmi-text',
    icon: null,
  },
  warning: {
    border: 'border-status-warning',
    bg: 'bg-status-warning-light',
    text: 'text-status-warning-dark',
    icon: (
      <span className="w-5 h-5 inline-flex items-center justify-center text-sm font-bold" aria-hidden="true">/!\</span>
    ),
  },
  alarm: {
    border: 'border-status-alarm',
    bg: 'bg-status-alarm-light',
    text: 'text-status-alarm-dark',
    icon: (
      <span className="w-5 h-5 inline-flex items-center justify-center text-sm font-bold animate-alarm-flash" aria-hidden="true">[!]</span>
    ),
  },
  offline: {
    border: 'border-hmi-border',
    bg: 'bg-hmi-bg',
    text: 'text-hmi-offline',
    icon: (
      <span className="w-5 h-5 inline-flex items-center justify-center text-sm font-bold" aria-hidden="true">[--]</span>
    ),
  },
};

export function MetricCard({
  title,
  description,
  value,
  unit,
  status = 'normal',
  statusMessage,
  icon,
  details,
  defaultExpanded = false,
  lastUpdate,
  onClick,
  actions,
  className,
}: MetricCardProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const config = statusConfig[status];
  const hasDetails = details && details.length > 0;

  const formatValue = (): string => {
    if (value === null || value === undefined) return '--';
    return String(value);
  };

  const formatLastUpdate = (): string | null => {
    if (!lastUpdate) return null;
    const d = typeof lastUpdate === 'string' ? new Date(lastUpdate) : lastUpdate;
    const now = new Date();
    const diffSeconds = Math.floor((now.getTime() - d.getTime()) / 1000);

    if (diffSeconds < 0) return 'Just now';
    if (diffSeconds < 60) return `${diffSeconds}s ago`;
    if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
    if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
    return d.toLocaleDateString();
  };

  const CardWrapper = onClick ? 'button' : 'div';

  return (
    <div
      className={clsx(
        'rounded-hmi border bg-hmi-panel overflow-hidden',
        config.border,
        config.bg,
        className
      )}
    >
      {/* Main content */}
      <CardWrapper
        onClick={onClick}
        className={clsx(
          'w-full p-4',
          onClick && [
            'cursor-pointer transition-colors',
            'hover:bg-hmi-bg/50',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-status-info',
          ]
        )}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            {/* Icon */}
            {icon && (
              <div className={clsx('flex-shrink-0', config.text)}>
                {icon}
              </div>
            )}

            {/* Title and description */}
            <div className="min-w-0">
              <h3 className="font-semibold text-hmi-text truncate">{title}</h3>
              {description && (
                <p className="text-sm text-hmi-muted truncate">{description}</p>
              )}
            </div>
          </div>

          {/* Status icon */}
          {config.icon && (
            <div className={config.text} aria-hidden="true">
              {config.icon}
            </div>
          )}
        </div>

        {/* Value */}
        <div className="mt-3 flex items-baseline gap-1">
          <span className={clsx(
            'text-3xl font-bold font-mono',
            status === 'offline' ? 'text-hmi-offline' : 'text-hmi-text'
          )}>
            {formatValue()}
          </span>
          {unit && (
            <span className="text-lg text-hmi-muted">{unit}</span>
          )}
        </div>

        {/* Status message */}
        {statusMessage && (
          <div className={clsx('mt-2 text-sm flex items-center gap-1.5', config.text)}>
            {config.icon && <span className="w-4 h-4">{config.icon}</span>}
            <span>{statusMessage}</span>
          </div>
        )}

        {/* Last update */}
        {formatLastUpdate() && (
          <div className="mt-2 text-xs text-hmi-muted">
            Updated {formatLastUpdate()}
          </div>
        )}
      </CardWrapper>

      {/* Expandable details */}
      {hasDetails && (
        <>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className={clsx(
              'w-full px-4 py-2 flex items-center justify-between',
              'border-t border-hmi-border/50',
              'text-sm text-hmi-muted',
              'hover:bg-hmi-bg/50 transition-colors',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-status-info'
            )}
            aria-expanded={isExpanded}
          >
            <span>{isExpanded ? 'Hide details' : 'Show details'}</span>
            <span
              className={clsx(
                'w-4 h-4 inline-flex items-center justify-center text-sm transition-transform duration-fast',
                isExpanded && 'rotate-180'
              )}
              aria-hidden="true"
            >v</span>
          </button>

          {isExpanded && (
            <div className="px-4 pb-4 pt-2 border-t border-hmi-border/50 animate-slide-down">
              <dl className="grid grid-cols-2 gap-3">
                {details.map((detail, index) => (
                  <div key={index}>
                    <dt className="text-xs text-hmi-muted">{detail.label}</dt>
                    <dd className="font-mono font-medium text-hmi-text">
                      {detail.value}
                      {detail.unit && (
                        <span className="text-sm text-hmi-muted ml-0.5">{detail.unit}</span>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </>
      )}

      {/* Actions */}
      {actions && (
        <div className="px-4 py-3 border-t border-hmi-border/50 bg-hmi-bg/30">
          {actions}
        </div>
      )}
    </div>
  );
}

export default MetricCard;
