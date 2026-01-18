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
export type TrendMeaning = 'positive' | 'negative' | 'neutral';
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
  /** What does "up" trend mean for this value? (default: positive=good) */
  trendMeaning?: TrendMeaning;
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
    icon: <span className="text-sm font-bold" aria-hidden="true">?</span>,
    label: 'Uncertain',
  },
  bad: {
    container: 'bg-status-alarm-light border-status-alarm',
    value: 'text-status-alarm-dark line-through',
    icon: <span className="text-sm font-bold" aria-hidden="true">X</span>,
    label: 'Bad Quality',
  },
  stale: {
    container: 'bg-hmi-bg border-hmi-border border-dashed',
    value: 'text-hmi-muted',
    icon: <span className="text-sm" aria-hidden="true">...</span>,
    label: 'Stale Data',
  },
  notConnected: {
    container: 'bg-hmi-bg border-hmi-border',
    value: 'text-hmi-offline',
    icon: <span className="text-sm font-bold" aria-hidden="true">/</span>,
    label: 'Not Connected',
  },
};

// Trend color based on meaning (e.g., temperature rising might be bad, not good)
function getTrendColor(trend: ValueTrend, meaning: TrendMeaning): string {
  if (meaning === 'neutral') return 'text-hmi-muted';
  if (trend === 'stable') return 'text-hmi-muted';

  // For 'positive' meaning: up=good, down=bad
  // For 'negative' meaning: up=bad, down=good
  const isGood = meaning === 'positive' ? trend === 'up' : trend === 'down';
  return isGood ? 'text-status-ok' : 'text-status-alarm';
}

const TrendIcon = ({ trend, meaning }: { trend: ValueTrend; meaning: TrendMeaning }) => {
  const colorClass = getTrendColor(trend, meaning);

  const trendSymbols: Record<ValueTrend, string> = {
    up: '\u2191',    // ↑
    down: '\u2193',  // ↓
    stable: '\u2192' // →
  };

  return (
    <span className={clsx('text-sm font-bold', colorClass)} aria-hidden="true">
      {trendSymbols[trend]}
    </span>
  );
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
  trendMeaning = 'positive',
  onClick,
  className,
}: ValueDisplayProps) {
  const sizeConfig = sizeClasses[size];
  const qualityConfig = qualityStyles[quality];

  // Format the value
  const formatValue = (): string => {
    if (value === null || value === undefined) return '--';
    if (typeof value === 'string') return value;
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
            <TrendIcon trend={trend} meaning={trendMeaning} />
          </span>
        )}
      </div>
    </Component>
  );
}

export default ValueDisplay;
