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

/**
 * Convert numeric OPC UA quality codes to DataQuality enum.
 * Per WT-SPEC-001 Section 5.2:
 *   0x00 = GOOD (fresh, valid measurement)
 *   0x40 = UNCERTAIN (stale, degraded, or at limits)
 *   0x80 = BAD (sensor failure, invalid data)
 *   0xC0 = NOT_CONNECTED (no communication with sensor)
 *
 * Uses bit mask on bits 6-7 to determine quality category.
 */
export function qualityFromCode(code: number): DataQuality {
  if (code === 0x00) return 'GOOD';

  const qualityMask = code & 0xC0;
  if (qualityMask === 0x40) return 'UNCERTAIN';
  if (qualityMask === 0x80) return 'BAD';
  if (qualityMask === 0xC0) return 'NOT_CONNECTED';

  return 'GOOD';
}

// Check if data is stale based on timestamp
export function isStale(timestamp: Date | string | null | undefined, thresholdSeconds: number = 30): boolean {
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
          <span className="w-4 h-4 inline-flex items-center justify-center text-xs font-bold text-alarm-yellow" aria-hidden="true">/!\</span>
        );
      case 'BAD':
        return (
          <span className="w-4 h-4 inline-flex items-center justify-center text-xs font-bold text-alarm-red" aria-hidden="true">[X]</span>
        );
      case 'NOT_CONNECTED':
        return (
          <span className="w-4 h-4 inline-flex items-center justify-center text-xs font-bold text-hmi-offline" aria-hidden="true">[--]</span>
        );
      case 'STALE':
        return (
          <span className="w-4 h-4 inline-flex items-center justify-center text-xs font-bold text-hmi-offline" aria-hidden="true">[T]</span>
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
