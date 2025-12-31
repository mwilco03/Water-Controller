'use client';

/**
 * ValueDisplay Component
 *
 * Displays a process value with label, unit, and quality indication.
 *
 * Design principles:
 * - Large, readable monospace numbers
 * - Data quality indicated visually (not color alone)
 * - Trends shown when available
 * - Touch-friendly for mobile
 * - Clear labeling
 */

import { ReactNode } from 'react';
import clsx from 'clsx';

export type ValueQuality = 'good' | 'uncertain' | 'bad' | 'stale' | 'notConnected';
export type ValueTrend = 'up' | 'down' | 'stable';
export type ValueSize = 'sm' | 'md' | 'lg' | 'xl';

interface ValueDisplayProps {
  /** Display label */
  label: string;
  /** Current value (null/undefined shows '--') */
  value: number | string | null | undefined;
  /** Engineering unit */
  unit?: string;
  /** Value quality */
  quality?: ValueQuality;
  /** Trend indicator */
  trend?: ValueTrend;
  /** Display size */
  size?: ValueSize;
  /** Number of decimal places */
  decimals?: number;
  /** Prefix (e.g., currency symbol) */
  prefix?: string;
  /** Additional icon */
  icon?: ReactNode;
  /** Whether the value is within normal range */
  inRange?: boolean;
  /** Low threshold for out-of-range indication */
  lowThreshold?: number;
  /** High threshold for out-of-range indication */
  highThreshold?: number;
  /** Click handler */
  onClick?: () => void;
  /** Additional class names */
  className?: string;
}

const sizeClasses: Record<ValueSize, {
  value: string;
  label: string;
  unit: string;
  container: string;
}> = {
  sm: {
    value: 'text-lg',
    label: 'text-xs',
    unit: 'text-xs',
    container: 'p-2',
  },
  md: {
    value: 'text-2xl',
    label: 'text-sm',
    unit: 'text-sm',
    container: 'p-3',
  },
  lg: {
    value: 'text-3xl',
    label: 'text-base',
    unit: 'text-base',
    container: 'p-4',
  },
  xl: {
    value: 'text-4xl',
    label: 'text-lg',
    unit: 'text-lg',
    container: 'p-5',
  },
};

const qualityStyles: Record<ValueQuality, {
  container: string;
  value: string;
  icon: ReactNode;
  label: string;
}> = {
  good: {
    container: '',
    value: 'text-hmi-text',
    icon: null,
    label: '',
  },
  uncertain: {
    container: 'bg-status-warning-light border-status-warning border-dashed',
    value: 'text-status-warning-dark italic',
    icon: (
      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
      </svg>
    ),
    label: 'Uncertain',
  },
  bad: {
    container: 'bg-status-alarm-light border-status-alarm',
    value: 'text-status-alarm-dark line-through',
    icon: (
      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
      </svg>
    ),
    label: 'Bad Quality',
  },
  stale: {
    container: 'bg-hmi-bg border-hmi-border border-dashed',
    value: 'text-hmi-muted',
    icon: (
      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
      </svg>
    ),
    label: 'Stale Data',
  },
  notConnected: {
    container: 'bg-hmi-bg border-hmi-border',
    value: 'text-hmi-offline',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3m8.293 8.293l1.414 1.414" />
      </svg>
    ),
    label: 'Not Connected',
  },
};

const trendIcons: Record<ValueTrend, ReactNode> = {
  up: (
    <svg className="w-4 h-4 text-status-ok" fill="currentColor" viewBox="0 0 20 20">
      <path fillRule="evenodd" d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 7.414V15a1 1 0 11-2 0V7.414L6.707 9.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
    </svg>
  ),
  down: (
    <svg className="w-4 h-4 text-status-alarm" fill="currentColor" viewBox="0 0 20 20">
      <path fillRule="evenodd" d="M14.707 10.293a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 12.586V5a1 1 0 012 0v7.586l2.293-2.293a1 1 0 011.414 0z" clipRule="evenodd" />
    </svg>
  ),
  stable: (
    <svg className="w-4 h-4 text-hmi-muted" fill="currentColor" viewBox="0 0 20 20">
      <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
    </svg>
  ),
};

export function ValueDisplay({
  label,
  value,
  unit,
  quality = 'good',
  trend,
  size = 'md',
  decimals,
  prefix,
  icon,
  inRange,
  lowThreshold,
  highThreshold,
  onClick,
  className,
}: ValueDisplayProps) {
  const sizeConfig = sizeClasses[size];
  const qualityConfig = qualityStyles[quality];

  // Format the value
  const formatValue = (): string => {
    if (value === null || value === undefined) return '--';
    if (typeof value === 'string') return value;

    // Check thresholds
    if (typeof lowThreshold === 'number' && value < lowThreshold) {
      // Below low threshold
    }
    if (typeof highThreshold === 'number' && value > highThreshold) {
      // Above high threshold
    }

    if (typeof decimals === 'number') {
      return value.toFixed(decimals);
    }
    return String(value);
  };

  // Determine if out of range
  const isOutOfRange = (): boolean => {
    if (inRange === false) return true;
    if (typeof value !== 'number') return false;
    if (typeof lowThreshold === 'number' && value < lowThreshold) return true;
    if (typeof highThreshold === 'number' && value > highThreshold) return true;
    return false;
  };

  const outOfRange = isOutOfRange();

  const Component = onClick ? 'button' : 'div';

  return (
    <Component
      onClick={onClick}
      className={clsx(
        'flex flex-col rounded-hmi border bg-hmi-panel',
        sizeConfig.container,
        qualityConfig.container,
        outOfRange && quality === 'good' && 'border-status-warning',
        onClick && [
          'cursor-pointer transition-all duration-fast',
          'hover:shadow-md active:scale-[0.98]',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info',
        ],
        !onClick && 'border-hmi-border',
        className
      )}
      role={onClick ? 'button' : undefined}
      aria-label={onClick ? `${label}: ${formatValue()} ${unit || ''}` : undefined}
    >
      {/* Header row: label + quality indicator */}
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-1.5">
          {icon && (
            <span className="text-hmi-muted" aria-hidden="true">
              {icon}
            </span>
          )}
          <span className={clsx('font-medium text-hmi-text', sizeConfig.label)}>
            {label}
          </span>
        </div>

        {/* Quality badge */}
        {quality !== 'good' && (
          <div
            className={clsx(
              'flex items-center gap-1 px-1.5 py-0.5 rounded-full',
              'text-xs',
              quality === 'uncertain' && 'text-status-warning-dark',
              quality === 'bad' && 'text-status-alarm-dark',
              quality === 'stale' && 'text-hmi-muted',
              quality === 'notConnected' && 'text-hmi-offline'
            )}
            role="status"
          >
            {qualityConfig.icon}
            <span className="sr-only">{qualityConfig.label}</span>
          </div>
        )}
      </div>

      {/* Value row */}
      <div className="flex items-baseline gap-1">
        {prefix && (
          <span className={clsx('font-mono', sizeConfig.unit, qualityConfig.value)}>
            {prefix}
          </span>
        )}
        <span className={clsx(
          'font-mono font-bold',
          sizeConfig.value,
          qualityConfig.value,
          outOfRange && quality === 'good' && 'text-status-warning-dark'
        )}>
          {formatValue()}
        </span>
        {unit && (
          <span className={clsx('text-hmi-muted', sizeConfig.unit)}>
            {unit}
          </span>
        )}
        {trend && (
          <span className="ml-1" aria-label={`Trend: ${trend}`}>
            {trendIcons[trend]}
          </span>
        )}
      </div>
    </Component>
  );
}

export default ValueDisplay;
