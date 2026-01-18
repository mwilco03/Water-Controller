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

interface ConnectionLabels {
  connected: string;
  disconnected: string;
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
  /** Custom connection state labels */
  connectionLabels?: ConnectionLabels;
  /** Show when data is stale */
  isStale?: boolean;
  /** Hide connection indicator */
  hideConnection?: boolean;
  /** Hide last update timestamp */
  hideTimestamp?: boolean;
  /** Additional class names */
  className?: string;
}

const statusConfig: Record<SystemStatus, {
  badge: string;
  badgeClass: string;
  bgClass: string;
  textClass: string;
  borderClass: string;
  defaultHeadline: string;
}> = {
  ok: {
    badge: 'OK',
    badgeClass: 'bg-status-ok text-white',
    bgClass: 'bg-status-ok-light',
    textClass: 'text-status-ok-dark',
    borderClass: 'border-status-ok',
    defaultHeadline: 'System Normal',
  },
  warning: {
    badge: 'WARN',
    badgeClass: 'bg-status-warning text-white',
    bgClass: 'bg-status-warning-light',
    textClass: 'text-status-warning-dark',
    borderClass: 'border-status-warning',
    defaultHeadline: 'Attention Required',
  },
  alarm: {
    badge: 'ALARM',
    badgeClass: 'bg-status-alarm text-white animate-alarm-flash',
    bgClass: 'bg-status-alarm-light',
    textClass: 'text-status-alarm-dark',
    borderClass: 'border-status-alarm',
    defaultHeadline: 'Active Alarms',
  },
  offline: {
    badge: 'OFFLINE',
    badgeClass: 'bg-hmi-muted text-white',
    bgClass: 'bg-status-offline-light',
    textClass: 'text-status-offline-dark',
    borderClass: 'border-hmi-border',
    defaultHeadline: 'System Offline',
  },
  connecting: {
    badge: 'SYNC',
    badgeClass: 'bg-status-info text-white animate-pulse',
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

const defaultConnectionLabels: ConnectionLabels = {
  connected: 'Connected',
  disconnected: 'Disconnected',
};

export function StatusHeader({
  systemStatus,
  headline,
  subtitle,
  statusItems = [],
  lastUpdate,
  connected = true,
  connectionLabels = defaultConnectionLabels,
  isStale = false,
  hideConnection = false,
  hideTimestamp = false,
  className,
}: StatusHeaderProps) {
  const config = statusConfig[systemStatus];
  const displayHeadline = headline || config.defaultHeadline;
  const labels = { ...defaultConnectionLabels, ...connectionLabels };

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
          <span
            className={clsx(
              'px-2 py-1 rounded text-xs font-bold uppercase tracking-wide',
              config.badgeClass
            )}
            aria-hidden="true"
          >
            {config.badge}
          </span>
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
        {(!hideConnection || (!hideTimestamp && lastUpdate)) && (
          <div className="flex items-center gap-4 text-sm">
            {/* Connection status */}
            {!hideConnection && (
              <div className="flex items-center gap-1.5">
                <span
                  className={clsx(
                    'w-2 h-2 rounded-full',
                    connected ? 'bg-status-ok' : 'bg-status-alarm'
                  )}
                  aria-hidden="true"
                />
                <span className={connected ? 'text-status-ok-dark' : 'text-status-alarm-dark'}>
                  {connected ? labels.connected : labels.disconnected}
                </span>
              </div>
            )}

            {/* Last update */}
            {!hideTimestamp && lastUpdate && (
              <div className={clsx('flex items-center gap-1.5', isStale && 'text-status-warning-dark')}>
                {isStale && (
                  <span className="px-1 py-0.5 rounded text-xs font-bold bg-status-warning text-white">
                    STALE
                  </span>
                )}
                <span className={isStale ? undefined : 'text-hmi-muted'}>
                  {formatLastUpdate(lastUpdate)}
                </span>
              </div>
            )}
          </div>
        )}
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
