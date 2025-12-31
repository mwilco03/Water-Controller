'use client';

/**
 * StatusHeader Component
 *
 * Answers the primary question: "Is the system OK?"
 *
 * Design principles:
 * - System state is immediately visible at a glance
 * - Uses ISA-101 color philosophy (gray normal, color abnormal)
 * - Shows icon + text + color (never color alone)
 * - Responsive: stacks on mobile, expands on desktop
 * - Touch-friendly for mobile interactions
 */

import { ReactNode } from 'react';
import clsx from 'clsx';

export type SystemStatus = 'ok' | 'warning' | 'alarm' | 'offline' | 'connecting';

interface StatusItem {
  /** Unique key */
  key: string;
  /** Item label */
  label: string;
  /** Current value */
  value: string | number;
  /** Optional status indicator */
  status?: 'ok' | 'warning' | 'alarm' | 'offline';
  /** Optional icon */
  icon?: ReactNode;
  /** Click handler */
  onClick?: () => void;
}

interface StatusHeaderProps {
  /** Overall system status */
  systemStatus: SystemStatus;
  /** Status headline text */
  headline?: string;
  /** Subtitle with additional context */
  subtitle?: string;
  /** Quick status items to display */
  statusItems?: StatusItem[];
  /** Last update timestamp */
  lastUpdate?: Date | string;
  /** Connection state */
  connected?: boolean;
  /** Show when data is stale */
  isStale?: boolean;
  /** Additional class names */
  className?: string;
}

const statusConfig: Record<SystemStatus, {
  icon: ReactNode;
  bgClass: string;
  textClass: string;
  borderClass: string;
  defaultHeadline: string;
}> = {
  ok: {
    icon: (
      <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
      </svg>
    ),
    bgClass: 'bg-status-ok-light',
    textClass: 'text-status-ok-dark',
    borderClass: 'border-status-ok',
    defaultHeadline: 'System Normal',
  },
  warning: {
    icon: (
      <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
      </svg>
    ),
    bgClass: 'bg-status-warning-light',
    textClass: 'text-status-warning-dark',
    borderClass: 'border-status-warning',
    defaultHeadline: 'Attention Required',
  },
  alarm: {
    icon: (
      <svg className="w-6 h-6 animate-alarm-flash" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
      </svg>
    ),
    bgClass: 'bg-status-alarm-light',
    textClass: 'text-status-alarm-dark',
    borderClass: 'border-status-alarm',
    defaultHeadline: 'Active Alarms',
  },
  offline: {
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3m8.293 8.293l1.414 1.414" />
      </svg>
    ),
    bgClass: 'bg-status-offline-light',
    textClass: 'text-status-offline-dark',
    borderClass: 'border-hmi-border',
    defaultHeadline: 'System Offline',
  },
  connecting: {
    icon: (
      <svg className="w-6 h-6 animate-spin-slow" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
    bgClass: 'bg-status-info-light',
    textClass: 'text-status-info-dark',
    borderClass: 'border-status-info',
    defaultHeadline: 'Connecting...',
  },
};

const itemStatusColors: Record<string, string> = {
  ok: 'text-status-ok-dark',
  warning: 'text-status-warning-dark',
  alarm: 'text-status-alarm-dark',
  offline: 'text-hmi-muted',
};

export function StatusHeader({
  systemStatus,
  headline,
  subtitle,
  statusItems = [],
  lastUpdate,
  connected = true,
  isStale = false,
  className,
}: StatusHeaderProps) {
  const config = statusConfig[systemStatus];
  const displayHeadline = headline || config.defaultHeadline;

  const formatLastUpdate = (date: Date | string | undefined): string => {
    if (!date) return '--';
    const d = typeof date === 'string' ? new Date(date) : date;
    const now = new Date();
    const diffSeconds = Math.floor((now.getTime() - d.getTime()) / 1000);

    if (diffSeconds < 0) return 'Just now';
    if (diffSeconds < 60) return `${diffSeconds}s ago`;
    if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
    if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
    return d.toLocaleDateString();
  };

  return (
    <header
      className={clsx(
        'rounded-hmi border-l-4 p-4',
        config.bgClass,
        config.borderClass,
        className
      )}
      role="banner"
      aria-live="polite"
    >
      {/* Main status row */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        {/* Status indicator */}
        <div className="flex items-center gap-3">
          <div className={config.textClass} aria-hidden="true">
            {config.icon}
          </div>
          <div>
            <h1 className={clsx('text-lg font-semibold', config.textClass)}>
              {displayHeadline}
            </h1>
            {subtitle && (
              <p className="text-sm text-hmi-muted">{subtitle}</p>
            )}
          </div>
        </div>

        {/* Connection and timestamp */}
        <div className="flex items-center gap-4 text-sm">
          {/* Connection status */}
          <div className="flex items-center gap-1.5">
            <span
              className={clsx(
                'w-2 h-2 rounded-full',
                connected ? 'bg-status-ok' : 'bg-status-alarm'
              )}
              aria-hidden="true"
            />
            <span className={connected ? 'text-status-ok-dark' : 'text-status-alarm-dark'}>
              {connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>

          {/* Last update */}
          {lastUpdate && (
            <div className={clsx('flex items-center gap-1.5', isStale && 'text-status-warning-dark')}>
              {isStale && (
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                </svg>
              )}
              <span className={isStale ? undefined : 'text-hmi-muted'}>
                {formatLastUpdate(lastUpdate)}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Quick status items */}
      {statusItems.length > 0 && (
        <div className="mt-4 pt-4 border-t border-hmi-border/50">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {statusItems.map((item) => (
              <button
                key={item.key}
                onClick={item.onClick}
                disabled={!item.onClick}
                className={clsx(
                  'flex flex-col items-center p-3 rounded-hmi-sm',
                  'bg-white/50 transition-colors',
                  item.onClick && 'hover:bg-white cursor-pointer',
                  !item.onClick && 'cursor-default'
                )}
              >
                {item.icon && (
                  <div className={clsx('mb-1', item.status && itemStatusColors[item.status])}>
                    {item.icon}
                  </div>
                )}
                <span className={clsx(
                  'text-xl font-bold font-mono',
                  item.status ? itemStatusColors[item.status] : 'text-hmi-text'
                )}>
                  {item.value}
                </span>
                <span className="text-xs text-hmi-muted">{item.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </header>
  );
}

export default StatusHeader;
