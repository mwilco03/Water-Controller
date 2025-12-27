'use client';

/**
 * Data Quality Indicator Component
 * ISA-101 compliant visual treatment for data quality states
 *
 * Quality States:
 * - GOOD: No decoration, clean display
 * - UNCERTAIN: Yellow dashed border, italic value
 * - BAD: Red border, strikethrough value, fault indication
 * - NOT_CONNECTED: Gray background, "---" display
 * - STALE: Timestamp shown, clock icon (>30s old)
 */

import { ReactNode } from 'react';

export type DataQuality = 'GOOD' | 'UNCERTAIN' | 'BAD' | 'NOT_CONNECTED' | 'STALE';

interface DataQualityIndicatorProps {
  quality: DataQuality;
  value: string | number | null;
  unit?: string;
  timestamp?: Date | string | null;
  staleThresholdSeconds?: number;
  className?: string;
  children?: ReactNode;
}

// Convert numeric quality codes to quality enum
export function qualityFromCode(code: number): DataQuality {
  if (code >= 192) return 'GOOD';        // 0xC0+
  if (code >= 64) return 'UNCERTAIN';    // 0x40-0xBF
  if (code === 0) return 'NOT_CONNECTED';
  return 'BAD';
}

// Check if data is stale based on timestamp
export function isStale(timestamp: Date | string | null, thresholdSeconds: number = 30): boolean {
  if (!timestamp) return false;
  const ts = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
  const now = new Date();
  return (now.getTime() - ts.getTime()) / 1000 > thresholdSeconds;
}

export default function DataQualityIndicator({
  quality,
  value,
  unit,
  timestamp,
  staleThresholdSeconds = 30,
  className = '',
  children,
}: DataQualityIndicatorProps) {
  // Check for staleness
  const stale = isStale(timestamp, staleThresholdSeconds);
  const effectiveQuality = stale ? 'STALE' : quality;

  // Get quality-specific styles
  const getContainerStyles = () => {
    switch (effectiveQuality) {
      case 'GOOD':
        return 'bg-transparent border-transparent';
      case 'UNCERTAIN':
        return 'bg-quality-uncertain-bg border-2 border-dashed border-alarm-yellow';
      case 'BAD':
        return 'bg-quality-bad-bg border-2 border-solid border-alarm-red';
      case 'NOT_CONNECTED':
        return 'bg-quality-stale-bg border-2 border-dotted border-hmi-offline';
      case 'STALE':
        return 'bg-transparent border border-dashed border-hmi-offline';
      default:
        return '';
    }
  };

  const getValueStyles = () => {
    switch (effectiveQuality) {
      case 'GOOD':
        return 'text-hmi-text';
      case 'UNCERTAIN':
        return 'text-hmi-text italic';
      case 'BAD':
        return 'text-alarm-red line-through';
      case 'NOT_CONNECTED':
        return 'text-hmi-offline';
      case 'STALE':
        return 'text-hmi-text-secondary';
      default:
        return 'text-hmi-text';
    }
  };

  const getIcon = () => {
    switch (effectiveQuality) {
      case 'UNCERTAIN':
        return (
          <svg className="w-4 h-4 text-alarm-yellow" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        );
      case 'BAD':
        return (
          <svg className="w-4 h-4 text-alarm-red" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
        );
      case 'NOT_CONNECTED':
        return (
          <svg className="w-4 h-4 text-hmi-offline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="8" strokeWidth="2" strokeDasharray="4 2" />
          </svg>
        );
      case 'STALE':
        return (
          <svg className="w-4 h-4 text-hmi-offline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        );
      default:
        return null;
    }
  };

  const formatTimestamp = () => {
    if (!timestamp) return null;
    const ts = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    const now = new Date();
    const seconds = Math.floor((now.getTime() - ts.getTime()) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    return ts.toLocaleTimeString();
  };

  const displayValue = effectiveQuality === 'NOT_CONNECTED' ? '---' :
    (value !== null && value !== undefined ?
      (typeof value === 'number' ? value.toFixed(2) : value) : '--');

  return (
    <div className={`rounded px-2 py-1 ${getContainerStyles()} ${className}`}>
      <div className="flex items-center gap-2">
        {getIcon()}
        <span className={`font-mono text-base ${getValueStyles()}`}>
          {displayValue}
          {unit && effectiveQuality !== 'NOT_CONNECTED' && (
            <span className="text-hmi-text-secondary text-sm ml-1">{unit}</span>
          )}
        </span>
        {children}
      </div>
      {effectiveQuality === 'STALE' && timestamp && (
        <div className="text-xs text-hmi-offline mt-1">
          Last: {formatTimestamp()}
        </div>
      )}
      {effectiveQuality === 'BAD' && (
        <div className="text-xs text-alarm-red font-medium mt-1">FAULT</div>
      )}
    </div>
  );
}
