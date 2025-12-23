'use client';

import { useState, useEffect, useMemo } from 'react';

interface ThresholdConfig {
  warning: number;  // milliseconds
  critical: number; // milliseconds
}

const DEFAULT_THRESHOLDS: ThresholdConfig = {
  warning: 5000,    // 5 seconds
  critical: 30000,  // 30 seconds
};

type FreshnessLevel = 'fresh' | 'warning' | 'critical' | 'unknown';

interface FreshnessConfig {
  color: string;
  bgColor: string;
  borderColor: string;
  label: string;
  textColor: string;
}

const FRESHNESS_CONFIG: Record<FreshnessLevel, FreshnessConfig> = {
  fresh: {
    color: '#10b981',
    bgColor: 'rgba(16, 185, 129, 0.15)',
    borderColor: 'rgba(16, 185, 129, 0.3)',
    label: 'Fresh',
    textColor: '#10b981',
  },
  warning: {
    color: '#f59e0b',
    bgColor: 'rgba(245, 158, 11, 0.15)',
    borderColor: 'rgba(245, 158, 11, 0.3)',
    label: 'Aging',
    textColor: '#f59e0b',
  },
  critical: {
    color: '#ef4444',
    bgColor: 'rgba(239, 68, 68, 0.15)',
    borderColor: 'rgba(239, 68, 68, 0.3)',
    label: 'Stale',
    textColor: '#ef4444',
  },
  unknown: {
    color: '#6b7280',
    bgColor: 'rgba(107, 114, 128, 0.15)',
    borderColor: 'rgba(107, 114, 128, 0.3)',
    label: 'Unknown',
    textColor: '#6b7280',
  },
};

function formatAge(ageMs: number): string {
  if (ageMs < 0) return '--';

  const seconds = Math.floor(ageMs / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h`;
  }

  const days = Math.floor(hours / 24);
  return `${days}d`;
}

function formatTimestamp(timestamp: string | Date | number | null | undefined): string {
  if (!timestamp) return 'Never';

  try {
    const date = timestamp instanceof Date ? timestamp : new Date(timestamp);
    if (isNaN(date.getTime())) return 'Invalid';

    return date.toISOString();
  } catch {
    return 'Invalid';
  }
}

function parseTimestamp(timestamp: string | Date | number | null | undefined): number | null {
  if (!timestamp) return null;

  try {
    const date = timestamp instanceof Date ? timestamp : new Date(timestamp);
    const time = date.getTime();
    return isNaN(time) ? null : time;
  } catch {
    return null;
  }
}

interface Props {
  lastUpdated: string | Date | number | null | undefined;
  thresholds?: Partial<ThresholdConfig>;
  showLabel?: boolean;
  showTooltip?: boolean;
  size?: 'xs' | 'sm' | 'md';
  variant?: 'text' | 'badge' | 'dot';
  className?: string;
}

export default function StaleIndicator({
  lastUpdated,
  thresholds: customThresholds,
  showLabel = true,
  showTooltip = true,
  size = 'sm',
  variant = 'text',
  className = '',
}: Props) {
  const [now, setNow] = useState(Date.now());

  const thresholds = useMemo(() => ({
    ...DEFAULT_THRESHOLDS,
    ...customThresholds,
  }), [customThresholds]);

  // Update age every second
  useEffect(() => {
    const interval = setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  const timestamp = parseTimestamp(lastUpdated);
  const age = timestamp !== null ? now - timestamp : -1;

  const freshnessLevel: FreshnessLevel = useMemo(() => {
    if (timestamp === null) return 'unknown';
    if (age < thresholds.warning) return 'fresh';
    if (age < thresholds.critical) return 'warning';
    return 'critical';
  }, [timestamp, age, thresholds]);

  const config = FRESHNESS_CONFIG[freshnessLevel];
  const ageText = age >= 0 ? formatAge(age) : '--';
  const tooltipText = `Last update: ${formatTimestamp(lastUpdated)}`;

  const sizeConfig = {
    xs: { text: 'text-[10px]', dot: 'w-1.5 h-1.5', padding: 'px-1 py-0.5' },
    sm: { text: 'text-xs', dot: 'w-2 h-2', padding: 'px-1.5 py-0.5' },
    md: { text: 'text-sm', dot: 'w-2.5 h-2.5', padding: 'px-2 py-1' },
  };

  const styles = sizeConfig[size];

  // Dot-only variant
  if (variant === 'dot') {
    return (
      <div
        className={`${styles.dot} rounded-full ${className}`}
        style={{ backgroundColor: config.color }}
        title={showTooltip ? tooltipText : undefined}
      />
    );
  }

  // Badge variant
  if (variant === 'badge') {
    return (
      <span
        className={`inline-flex items-center gap-1 rounded ${styles.padding} ${styles.text} font-medium ${className}`}
        style={{
          backgroundColor: config.bgColor,
          color: config.textColor,
          border: `1px solid ${config.borderColor}`,
        }}
        title={showTooltip ? tooltipText : undefined}
      >
        <span
          className={`${styles.dot} rounded-full`}
          style={{ backgroundColor: config.color }}
        />
        {showLabel && <span>{ageText} ago</span>}
      </span>
    );
  }

  // Text variant (default)
  return (
    <span
      className={`inline-flex items-center gap-1 ${styles.text} ${className}`}
      style={{ color: config.textColor }}
      title={showTooltip ? tooltipText : undefined}
    >
      <span
        className={`${styles.dot} rounded-full`}
        style={{ backgroundColor: config.color }}
      />
      {showLabel && <span>{ageText} ago</span>}
    </span>
  );
}

// Export a utility hook for data freshness
export function useDataFreshness(
  lastUpdated: string | Date | number | null | undefined,
  thresholds: ThresholdConfig = DEFAULT_THRESHOLDS
): {
  freshnessLevel: FreshnessLevel;
  ageMs: number;
  ageText: string;
  isFresh: boolean;
  isStale: boolean;
} {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const interval = setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  const timestamp = parseTimestamp(lastUpdated);
  const ageMs = timestamp !== null ? now - timestamp : -1;

  const freshnessLevel: FreshnessLevel = (() => {
    if (timestamp === null) return 'unknown';
    if (ageMs < thresholds.warning) return 'fresh';
    if (ageMs < thresholds.critical) return 'warning';
    return 'critical';
  })();

  return {
    freshnessLevel,
    ageMs,
    ageText: formatAge(ageMs),
    isFresh: freshnessLevel === 'fresh',
    isStale: freshnessLevel === 'critical',
  };
}

// Export a combined value + freshness display component
interface ValueWithFreshnessProps {
  value: string | number | null | undefined;
  unit?: string;
  lastUpdated: string | Date | number | null | undefined;
  thresholds?: Partial<ThresholdConfig>;
  valueClassName?: string;
  size?: 'sm' | 'md' | 'lg';
}

export function ValueWithFreshness({
  value,
  unit,
  lastUpdated,
  thresholds,
  valueClassName = '',
  size = 'md',
}: ValueWithFreshnessProps) {
  const displayValue = value !== null && value !== undefined ? value : '--';

  const sizeConfig = {
    sm: { value: 'text-lg', unit: 'text-xs', stale: 'text-[10px]' },
    md: { value: 'text-2xl', unit: 'text-sm', stale: 'text-xs' },
    lg: { value: 'text-4xl', unit: 'text-base', stale: 'text-sm' },
  };

  const styles = sizeConfig[size];

  return (
    <div className="flex flex-col">
      <div className="flex items-baseline gap-1">
        <span className={`font-mono font-bold ${styles.value} ${valueClassName}`}>
          {displayValue}
        </span>
        {unit && (
          <span className={`text-gray-400 ${styles.unit}`}>{unit}</span>
        )}
      </div>
      <StaleIndicator
        lastUpdated={lastUpdated}
        thresholds={thresholds}
        size="xs"
        variant="text"
      />
    </div>
  );
}
