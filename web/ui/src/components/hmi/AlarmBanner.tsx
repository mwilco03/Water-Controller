'use client';

/**
 * Alarm Banner Component
 * ISA-101 compliant alarm display banner
 *
 * Design principles:
 * - Visible at top of page when active alarms exist
 * - Hidden when no alarms (gray = normal)
 * - Red for critical/high priority
 * - Amber for warnings
 * - Unacknowledged alarms flash at 1Hz
 */

import { useState, useEffect } from 'react';
import Link from 'next/link';

export interface AlarmData {
  alarm_id: number | string;
  rtu_station: string;
  slot?: number;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';
  message: string;
  state: 'ACTIVE' | 'ACTIVE_ACK' | 'CLEARED';
  timestamp: string;
  acknowledged?: boolean;
}

interface AlarmBannerProps {
  alarms: AlarmData[];
  onAcknowledge?: (alarmId: number | string) => void;
  onAcknowledgeAll?: () => void;
  className?: string;
}

// Carousel rotation time in ms - increased for better readability during shift
const ALARM_ROTATION_MS = 10000; // 10 seconds per alarm

export default function AlarmBanner({
  alarms,
  onAcknowledge,
  onAcknowledgeAll,
  className = '',
}: AlarmBannerProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);

  // Filter to only active alarms
  const activeAlarms = alarms.filter(a => a.state !== 'CLEARED');

  // Rotate through alarms - pauses on hover/touch for operator reading
  useEffect(() => {
    if (activeAlarms.length <= 1 || isPaused) return;
    const interval = setInterval(() => {
      setCurrentIndex(prev => (prev + 1) % activeAlarms.length);
    }, ALARM_ROTATION_MS);
    return () => clearInterval(interval);
  }, [activeAlarms.length, isPaused]);

  // Reset index if alarms change
  useEffect(() => {
    if (currentIndex >= activeAlarms.length) {
      setCurrentIndex(0);
    }
  }, [activeAlarms.length, currentIndex]);

  // Don't render if no active alarms
  if (activeAlarms.length === 0) {
    return null;
  }

  const currentAlarm = activeAlarms[currentIndex];
  const hasUnacknowledged = activeAlarms.some(a => a.state === 'ACTIVE');

  // Determine banner style based on highest severity
  const getHighestSeverity = () => {
    const severityOrder = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
    for (const severity of severityOrder) {
      if (activeAlarms.some(a => a.severity === severity)) {
        return severity;
      }
    }
    return 'INFO';
  };

  const highestSeverity = getHighestSeverity();

  const getBannerStyles = () => {
    switch (highestSeverity) {
      case 'CRITICAL':
      case 'HIGH':
        return 'bg-status-alarm text-white';
      case 'MEDIUM':
        return 'bg-status-warning text-hmi-text';
      case 'LOW':
      case 'INFO':
      default:
        return 'bg-status-info text-white';
    }
  };

  const formatTimestamp = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleTimeString();
  };

  return (
    <div
      className={`
        px-4 py-2 rounded-lg
        ${getBannerStyles()}
        ${hasUnacknowledged ? 'alarm-flash' : ''}
        ${className}
      `}
      role="alert"
      aria-live="assertive"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
      onTouchStart={() => setIsPaused(true)}
      onTouchEnd={() => setIsPaused(false)}
    >
      <div className="flex items-center justify-between gap-4 flex-wrap">
        {/* Alarm info */}
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <span className="shrink-0 px-1.5 py-0.5 text-xs font-bold bg-white/20 rounded">
            {highestSeverity === 'CRITICAL' || highestSeverity === 'HIGH' ? 'ALARM' : 'WARN'}
          </span>
          <span className="font-semibold text-sm">{currentAlarm.severity}</span>
          <span className="opacity-60">|</span>
          <span className="font-mono text-sm">{currentAlarm.rtu_station}</span>
          <span className="opacity-60">|</span>
          <span className="text-sm truncate">{currentAlarm.message}</span>
          <span className="text-xs opacity-75 shrink-0">{formatTimestamp(currentAlarm.timestamp)}</span>
        </div>

        {/* Alarm navigation */}
        {activeAlarms.length > 1 && (
          <div className="flex items-center gap-2 text-sm">
            <button
              onClick={() => setCurrentIndex(prev => (prev - 1 + activeAlarms.length) % activeAlarms.length)}
              className="px-2 py-0.5 hover:bg-black/10 rounded font-bold text-sm"
              aria-label="Previous alarm"
            >
              &lt;
            </button>
            <span className="font-mono">{currentIndex + 1}/{activeAlarms.length}</span>
            <button
              onClick={() => setCurrentIndex(prev => (prev + 1) % activeAlarms.length)}
              className="px-2 py-0.5 hover:bg-black/10 rounded font-bold text-sm"
              aria-label="Next alarm"
            >
              &gt;
            </button>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2">
          {currentAlarm.state === 'ACTIVE' && onAcknowledge && (
            <button
              onClick={() => onAcknowledge(currentAlarm.alarm_id)}
              className="px-3 py-1 text-sm bg-white/20 hover:bg-white/30 rounded transition-colors"
            >
              ACK
            </button>
          )}
          {hasUnacknowledged && activeAlarms.length > 1 && onAcknowledgeAll && (
            <button
              onClick={onAcknowledgeAll}
              className="px-3 py-1 text-sm bg-white/20 hover:bg-white/30 rounded transition-colors"
            >
              ACK All
            </button>
          )}
          <Link
            href="/alarms"
            className="px-3 py-1 text-sm bg-white/20 hover:bg-white/30 rounded transition-colors"
          >
            View All
          </Link>
        </div>
      </div>
    </div>
  );
}
