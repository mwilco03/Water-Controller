'use client';

/**
 * Alarm Insights Component
 *
 * Analyzes alarm history to identify frequently occurring alarms
 * and trends. Helps operators identify chronic issues that need
 * permanent resolution rather than repeated acknowledgment.
 *
 * Features:
 * - Top 5 most frequent alarms this week
 * - Week-over-week comparison (up/down %)
 * - Quick links to shelve/trend chronic alarms
 */

import { useState, useMemo } from 'react';
import Link from 'next/link';

interface AlarmHistoryItem {
  alarm_id: number;
  rtu_station: string;
  slot: number;
  severity: string;
  message: string;
  timestamp: string;
}

interface AlarmFrequency {
  key: string; // rtu_station:slot
  rtuStation: string;
  slot: number;
  message: string;
  severity: string;
  countThisWeek: number;
  countLastWeek: number;
  changePercent: number;
}

interface AlarmInsightsProps {
  alarmHistory: AlarmHistoryItem[];
  onShelve?: (rtuStation: string, slot: number) => void;
}

export default function AlarmInsights({ alarmHistory, onShelve }: AlarmInsightsProps) {
  const [expanded, setExpanded] = useState(false);

  // Calculate alarm frequencies
  const frequencies = useMemo(() => {
    const now = new Date();
    const oneWeekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    const twoWeeksAgo = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000);

    // Group alarms by key (rtu_station:slot)
    const thisWeekCounts = new Map<string, { count: number; alarm: AlarmHistoryItem }>();
    const lastWeekCounts = new Map<string, number>();

    alarmHistory.forEach(alarm => {
      const key = `${alarm.rtu_station}:${alarm.slot}`;
      const alarmTime = new Date(alarm.timestamp);

      if (alarmTime >= oneWeekAgo) {
        const existing = thisWeekCounts.get(key);
        if (existing) {
          existing.count++;
        } else {
          thisWeekCounts.set(key, { count: 1, alarm });
        }
      } else if (alarmTime >= twoWeeksAgo) {
        lastWeekCounts.set(key, (lastWeekCounts.get(key) || 0) + 1);
      }
    });

    // Build frequency list with comparisons
    const result: AlarmFrequency[] = [];
    thisWeekCounts.forEach(({ count, alarm }, key) => {
      const lastWeekCount = lastWeekCounts.get(key) || 0;
      const changePercent = lastWeekCount > 0
        ? Math.round(((count - lastWeekCount) / lastWeekCount) * 100)
        : count > 0 ? 100 : 0; // New alarm = 100% increase

      result.push({
        key,
        rtuStation: alarm.rtu_station,
        slot: alarm.slot,
        message: alarm.message,
        severity: alarm.severity,
        countThisWeek: count,
        countLastWeek: lastWeekCount,
        changePercent,
      });
    });

    // Sort by count (most frequent first)
    result.sort((a, b) => b.countThisWeek - a.countThisWeek);

    return result.slice(0, 5); // Top 5
  }, [alarmHistory]);

  if (frequencies.length === 0) {
    return null;
  }

  const hasChronicAlarms = frequencies.some(f => f.countThisWeek >= 5);

  return (
    <div className="hmi-card p-4">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-status-info" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <h3 className="font-semibold text-hmi-text">Alarm Insights</h3>
          {hasChronicAlarms && (
            <span className="px-2 py-0.5 text-xs font-medium bg-status-warning/20 text-status-warning rounded">
              Chronic issues detected
            </span>
          )}
        </div>
        <svg
          className={`w-5 h-5 text-hmi-muted transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="mt-4 space-y-3">
          <p className="text-sm text-hmi-muted">
            Most frequent alarms this week. Consider permanent solutions for chronic issues.
          </p>

          <div className="space-y-2">
            {frequencies.map((freq) => (
              <div
                key={freq.key}
                className="p-3 bg-hmi-bg rounded-lg border border-hmi-border"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                        freq.severity === 'CRITICAL' || freq.severity === 'HIGH'
                          ? 'bg-status-alarm text-white'
                          : freq.severity === 'WARNING'
                          ? 'bg-status-warning text-white'
                          : 'bg-status-info text-white'
                      }`}>
                        {freq.severity}
                      </span>
                      <span className="text-xs text-hmi-muted font-mono">
                        {freq.rtuStation}:{freq.slot}
                      </span>
                    </div>
                    <p className="text-sm text-hmi-text truncate">{freq.message}</p>
                  </div>

                  <div className="text-right shrink-0">
                    <div className="text-lg font-bold font-mono text-hmi-text">
                      {freq.countThisWeek}x
                    </div>
                    <div className={`text-xs font-medium ${
                      freq.changePercent > 0
                        ? 'text-status-alarm'
                        : freq.changePercent < 0
                        ? 'text-status-ok'
                        : 'text-hmi-muted'
                    }`}>
                      {freq.changePercent > 0 && '+'}
                      {freq.changePercent < 0 && ''}
                      {freq.changePercent !== 0 && `${freq.changePercent}%`}
                      {freq.changePercent === 0 && 'no change'}
                      <span className="text-hmi-muted ml-1">vs last week</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 mt-2 pt-2 border-t border-hmi-border">
                  <Link
                    href={`/trends?rtu=${encodeURIComponent(freq.rtuStation)}&slot=${freq.slot}`}
                    className="text-xs text-status-info hover:underline flex items-center gap-1"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4" />
                    </svg>
                    View Trend
                  </Link>
                  {onShelve && freq.countThisWeek >= 5 && (
                    <button
                      onClick={() => onShelve(freq.rtuStation, freq.slot)}
                      className="text-xs text-status-info hover:underline flex items-center gap-1"
                    >
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Shelve
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {hasChronicAlarms && (
            <div className="p-3 bg-status-warning/10 border border-status-warning/30 rounded-lg text-sm">
              <strong className="text-status-warning">Recommendation:</strong>
              <span className="text-hmi-text ml-1">
                Alarms firing 5+ times/week indicate a chronic issue.
                Consider scheduling maintenance or adjusting alarm thresholds.
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
