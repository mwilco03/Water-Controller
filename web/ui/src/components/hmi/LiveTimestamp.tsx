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
  <svg
    className="w-3 h-3"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={2}
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
    />
  </svg>
);

const WarningIcon = () => (
  <svg
    className="w-3 h-3"
    fill="currentColor"
    viewBox="0 0 20 20"
    aria-hidden="true"
  >
    <path
      fillRule="evenodd"
      d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
      clipRule="evenodd"
    />
  </svg>
);

const ErrorIcon = () => (
  <svg
    className="w-3 h-3"
    fill="currentColor"
    viewBox="0 0 20 20"
    aria-hidden="true"
  >
    <path
      fillRule="evenodd"
      d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
      clipRule="evenodd"
    />
  </svg>
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
