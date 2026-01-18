'use client';

/**
 * LiveTimestamp - Real-time data freshness indicator
 *
 * Shows how fresh data is with clear severity levels:
 * - Normal: < 5 seconds old
 * - Warning: 5-30 seconds old
 * - Critical: > 30 seconds old
 *
 * Features:
 * - Updates every second
 * - Color + icon + text (never color alone)
 * - Accessible with ARIA labels
 * - Touch-friendly on mobile
 */

import { useState, useEffect, useCallback } from 'react';

interface LiveTimestampProps {
  timestamp: Date | string | null | undefined;
  warningThresholdSeconds?: number;
  criticalThresholdSeconds?: number;
  showIcon?: boolean;
  className?: string;
  compact?: boolean;
}

type Severity = 'normal' | 'warning' | 'critical' | 'unknown';

function getSeverity(
  ageSeconds: number,
  warningThreshold: number,
  criticalThreshold: number
): Severity {
  if (ageSeconds >= criticalThreshold) return 'critical';
  if (ageSeconds >= warningThreshold) return 'warning';
  return 'normal';
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
}

const ClockIcon = () => (
  <span className="w-3 h-3 inline-flex items-center justify-center text-xs font-bold" aria-hidden="true">[T]</span>
);

const WarningIcon = () => (
  <span className="w-3 h-3 inline-flex items-center justify-center text-xs font-bold" aria-hidden="true">/!\</span>
);

const ErrorIcon = () => (
  <span className="w-3 h-3 inline-flex items-center justify-center text-xs font-bold" aria-hidden="true">[X]</span>
);

export default function LiveTimestamp({
  timestamp,
  warningThresholdSeconds = 5,
  criticalThresholdSeconds = 30,
  showIcon = true,
  className = '',
  compact = false,
}: LiveTimestampProps) {
  const [ageSeconds, setAgeSeconds] = useState<number | null>(null);

  const calculateAge = useCallback(() => {
    if (!timestamp) return null;
    const ts = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    if (isNaN(ts.getTime())) return null;
    return Math.floor((Date.now() - ts.getTime()) / 1000);
  }, [timestamp]);

  useEffect(() => {
    setAgeSeconds(calculateAge());
    const interval = setInterval(() => {
      setAgeSeconds(calculateAge());
    }, 1000);
    return () => clearInterval(interval);
  }, [calculateAge]);

  // No timestamp - show placeholder
  if (ageSeconds === null) {
    return (
      <span
        className={`stale-indicator ${className}`}
        aria-label="No data timestamp available"
      >
        {showIcon && <ClockIcon />}
        <span>---</span>
      </span>
    );
  }

  const severity = getSeverity(ageSeconds, warningThresholdSeconds, criticalThresholdSeconds);
  const formattedAge = formatAge(ageSeconds);

  const getSeverityClass = () => {
    switch (severity) {
      case 'critical':
        return 'critical';
      case 'warning':
        return 'warning';
      default:
        return '';
    }
  };

  const getIcon = () => {
    if (!showIcon) return null;
    switch (severity) {
      case 'critical':
        return <ErrorIcon />;
      case 'warning':
        return <WarningIcon />;
      default:
        return <ClockIcon />;
    }
  };

  const ariaLabel = `Data is ${formattedAge} old${
    severity === 'critical' ? ', data may be stale' :
    severity === 'warning' ? ', approaching stale' : ''
  }`;

  if (compact) {
    return (
      <span
        className={`stale-indicator ${getSeverityClass()} ${className}`}
        aria-label={ariaLabel}
        title={ariaLabel}
      >
        {getIcon()}
        <span>{formattedAge}</span>
      </span>
    );
  }

  return (
    <span
      className={`stale-indicator ${getSeverityClass()} ${className}`}
      aria-label={ariaLabel}
      role="status"
    >
      {getIcon()}
      <span>
        {severity === 'critical' && 'Stale: '}
        {severity === 'warning' && 'Updated '}
        {formattedAge}
        {severity === 'normal' && ' ago'}
      </span>
    </span>
  );
}

export { LiveTimestamp };
