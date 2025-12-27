'use client';

/**
 * Alarm Banner Component
 * ISA-101 compliant alarm display banner
 *
 * - Visible at top of page when active alarms exist
 * - Hidden when no alarms
 * - Red background for critical/high priority
 * - Yellow/amber for warnings
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

export default function AlarmBanner({
  alarms,
  onAcknowledge,
  onAcknowledgeAll,
  className = '',
}: AlarmBannerProps) {
  const [currentIndex, setCurrentIndex] = useState(0);

  // Filter to only active alarms
  const activeAlarms = alarms.filter(a => a.state !== 'CLEARED');

  // Rotate through alarms every 5 seconds if multiple
  useEffect(() => {
    if (activeAlarms.length <= 1) return;

    const interval = setInterval(() => {
      setCurrentIndex(prev => (prev + 1) % activeAlarms.length);
    }, 5000);

    return () => clearInterval(interval);
  }, [activeAlarms.length]);

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

  // Determine banner color based on highest severity
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
        return 'bg-alarm-red text-white';
      case 'MEDIUM':
        return 'bg-alarm-yellow text-hmi-text';
      case 'LOW':
      case 'INFO':
      default:
        return 'bg-alarm-blue text-white';
    }
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'CRITICAL':
      case 'HIGH':
        return (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        );
      case 'MEDIUM':
        return (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        );
      default:
        return (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
        );
    }
  };

  const formatTimestamp = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleTimeString();
  };

  return (
    <div
      className={`
        px-4 py-2
        ${getBannerStyles()}
        ${hasUnacknowledged ? 'animate-alarm-flash' : ''}
        ${className}
      `}
      role="alert"
      aria-live="assertive"
    >
      <div className="max-w-[1800px] mx-auto flex items-center justify-between gap-4">
        {/* Alarm info */}
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {getSeverityIcon(currentAlarm.severity)}
          <span className="font-medium">{currentAlarm.severity}</span>
          <span className="text-sm opacity-90">|</span>
          <span className="font-mono text-sm">{currentAlarm.rtu_station}</span>
          <span className="text-sm opacity-90">|</span>
          <span className="text-sm truncate">{currentAlarm.message}</span>
          <span className="text-xs opacity-75">{formatTimestamp(currentAlarm.timestamp)}</span>
        </div>

        {/* Alarm count and navigation */}
        {activeAlarms.length > 1 && (
          <div className="flex items-center gap-2 text-sm">
            <button
              onClick={() => setCurrentIndex(prev => (prev - 1 + activeAlarms.length) % activeAlarms.length)}
              className="p-1 hover:bg-black/10 rounded"
              aria-label="Previous alarm"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <span className="font-mono">
              {currentIndex + 1}/{activeAlarms.length}
            </span>
            <button
              onClick={() => setCurrentIndex(prev => (prev + 1) % activeAlarms.length)}
              className="p-1 hover:bg-black/10 rounded"
              aria-label="Next alarm"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2">
          {currentAlarm.state === 'ACTIVE' && onAcknowledge && (
            <button
              onClick={() => onAcknowledge(currentAlarm.alarm_id)}
              className="px-3 py-1 text-sm bg-black/20 hover:bg-black/30 rounded transition-colors"
            >
              ACK
            </button>
          )}
          {hasUnacknowledged && activeAlarms.length > 1 && onAcknowledgeAll && (
            <button
              onClick={onAcknowledgeAll}
              className="px-3 py-1 text-sm bg-black/20 hover:bg-black/30 rounded transition-colors"
            >
              ACK All
            </button>
          )}
          <Link
            href="/alarms"
            className="px-3 py-1 text-sm bg-black/20 hover:bg-black/30 rounded transition-colors"
          >
            View All
          </Link>
        </div>
      </div>
    </div>
  );
}
