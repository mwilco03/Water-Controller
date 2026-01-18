'use client';

/**
 * Quick Control Panel Component
 *
 * Provides fast access to common setpoint adjustments from the dashboard.
 * Designed for operators who need to make quick changes without navigating
 * to the full control page.
 *
 * Features:
 * - One-tap +/- adjustments for common increments
 * - Shows current PV vs SP at a glance
 * - Requires command mode to make changes
 * - Touch-friendly large buttons
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useCommandMode } from '@/contexts/CommandModeContext';
import { useHMIToast } from '@/components/hmi';
import clsx from 'clsx';
import Link from 'next/link';

interface PIDLoop {
  id: number;
  name: string;
  setpoint: number;
  pv: number | null;
  cv: number | null;
  mode: string;
  output_min: number;
  output_max: number;
  rtu_name: string;
}

interface QuickControlPanelProps {
  className?: string;
}

// Common adjustment increments
const INCREMENTS = [0.1, 0.5, 1.0, 5.0];

export function QuickControlPanel({ className }: QuickControlPanelProps) {
  const { canCommand, mode } = useCommandMode();
  const { showMessage, addToast } = useHMIToast();
  const [loops, setLoops] = useState<PIDLoop[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedLoop, setExpandedLoop] = useState<number | null>(null);
  const [selectedIncrement, setSelectedIncrement] = useState(1.0);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch PID loops from all RTUs
  const fetchLoops = useCallback(async () => {
    try {
      // First get RTU list
      const rtusRes = await fetch('/api/v1/rtus');
      if (!rtusRes.ok) return;

      const rtusData = await rtusRes.json();
      const rtuList = rtusData.data || [];

      // Fetch PID loops from each RTU
      const allLoops: PIDLoop[] = [];
      for (const rtu of rtuList) {
        try {
          const pidRes = await fetch(`/api/v1/rtus/${encodeURIComponent(rtu.station_name)}/pid`);
          if (pidRes.ok) {
            const pidData = await pidRes.json();
            const loops = (pidData.data || []).map((loop: Omit<PIDLoop, 'rtu_name'>) => ({
              ...loop,
              rtu_name: rtu.station_name,
            }));
            allLoops.push(...loops);
          }
        } catch {
          // Skip RTUs that fail
        }
      }

      setLoops(allLoops);
    } catch (error) {
      console.error('Error fetching PID loops', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLoops();
    // Poll every 5 seconds for updates
    pollIntervalRef.current = setInterval(fetchLoops, 5000);
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [fetchLoops]);

  // Track last change for undo
  const lastChangeRef = useRef<{
    rtuName: string;
    loopId: number;
    loopName: string;
    previousValue: number;
    newValue: number;
  } | null>(null);

  // Adjust setpoint
  const adjustSetpoint = async (loop: PIDLoop, delta: number) => {
    if (!canCommand) {
      showMessage('warning', 'Enter Command Mode to make changes');
      return;
    }

    const previousValue = loop.setpoint;
    const newSetpoint = loop.setpoint + delta;

    try {
      const res = await fetch(
        `/api/v1/rtus/${encodeURIComponent(loop.rtu_name)}/pid/${loop.id}/setpoint`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ setpoint: newSetpoint }),
        }
      );

      if (res.ok) {
        // Store for undo
        lastChangeRef.current = {
          rtuName: loop.rtu_name,
          loopId: loop.id,
          loopName: loop.name,
          previousValue,
          newValue: newSetpoint,
        };

        // Show toast with undo
        addToast({
          type: 'success',
          title: `${loop.name}: SP ${delta > 0 ? '+' : ''}${delta.toFixed(1)} → ${newSetpoint.toFixed(2)}`,
          duration: 6000,
          action: {
            label: 'Undo',
            onClick: async () => {
              const last = lastChangeRef.current;
              if (last) {
                try {
                  await fetch(
                    `/api/v1/rtus/${encodeURIComponent(last.rtuName)}/pid/${last.loopId}/setpoint`,
                    {
                      method: 'PUT',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ setpoint: last.previousValue }),
                    }
                  );
                  showMessage('success', `Reverted ${last.loopName} to ${last.previousValue.toFixed(2)}`);
                  fetchLoops();
                } catch {
                  showMessage('error', 'Failed to undo');
                }
                lastChangeRef.current = null;
              }
            },
          },
        });

        // Update local state immediately for responsiveness
        setLoops(prev =>
          prev.map(l =>
            l.id === loop.id && l.rtu_name === loop.rtu_name
              ? { ...l, setpoint: newSetpoint }
              : l
          )
        );
      } else {
        showMessage('error', 'Failed to update setpoint');
      }
    } catch (error) {
      console.error('Error updating setpoint', error);
      showMessage('error', 'Error updating setpoint');
    }
  };

  if (loading) {
    return (
      <div className={clsx('hmi-card p-4', className)}>
        <div className="flex items-center gap-3 mb-4">
          <div className="skeleton h-5 w-5 rounded" />
          <div className="skeleton h-5 w-32" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[1, 2].map(i => (
            <div key={i} className="skeleton h-24 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (loops.length === 0) {
    return null; // Don't show panel if no loops configured
  }

  // Show top 4 loops (can be expanded)
  const displayedLoops = loops.slice(0, 4);
  const hasMore = loops.length > 4;

  return (
    <div className={clsx('hmi-card overflow-hidden', className)}>
      {/* Header */}
      <div className="p-4 border-b border-hmi-border flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-status-info font-bold">[CTRL]</span>
          <span className="font-semibold text-hmi-text">Quick Controls</span>
        </div>
        <div className="flex items-center gap-2">
          {/* Increment selector */}
          <select
            value={selectedIncrement}
            onChange={(e) => setSelectedIncrement(parseFloat(e.target.value))}
            className="text-sm bg-hmi-bg border border-hmi-border rounded px-2 py-1 text-hmi-text"
            title="Adjustment increment"
          >
            {INCREMENTS.map(inc => (
              <option key={inc} value={inc}>
                ±{inc}
              </option>
            ))}
          </select>
          <Link
            href="/control"
            className="text-sm text-status-info hover:underline"
          >
            Full Controls
          </Link>
        </div>
      </div>

      {/* Command mode warning */}
      {mode === 'view' && (
        <div className="px-4 py-2 bg-status-warning/10 border-b border-status-warning/30 text-sm text-status-warning">
          Enter Command Mode to adjust setpoints
        </div>
      )}

      {/* PID Loop Cards */}
      <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
        {displayedLoops.map((loop) => {
          const isExpanded = expandedLoop === loop.id;
          const error = loop.pv !== null ? (loop.setpoint - loop.pv) : null;
          const isInBand = error !== null && Math.abs(error) < 0.5;

          return (
            <div
              key={`${loop.rtu_name}-${loop.id}`}
              className={clsx(
                'bg-hmi-bg rounded-lg border border-hmi-border overflow-hidden transition-all',
                isExpanded && 'ring-2 ring-status-info'
              )}
            >
              {/* Loop header */}
              <button
                onClick={() => setExpandedLoop(isExpanded ? null : loop.id)}
                className="w-full p-3 flex items-center justify-between hover:bg-hmi-border/30 transition-colors text-left"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-hmi-text truncate">{loop.name}</div>
                  <div className="text-xs text-hmi-muted">{loop.rtu_name}</div>
                </div>
                <div className="flex items-center gap-3">
                  {/* PV vs SP indicator */}
                  <div className="text-right">
                    <div className="text-sm font-mono">
                      <span className="text-hmi-muted">PV:</span>{' '}
                      <span className={clsx(isInBand ? 'text-status-ok' : 'text-hmi-text')}>
                        {loop.pv?.toFixed(1) ?? '--'}
                      </span>
                    </div>
                    <div className="text-sm font-mono">
                      <span className="text-hmi-muted">SP:</span>{' '}
                      <span className="text-status-info font-bold">
                        {loop.setpoint.toFixed(1)}
                      </span>
                    </div>
                  </div>
                  {/* Mode badge */}
                  <span
                    className={clsx(
                      'px-2 py-0.5 rounded text-xs font-medium text-white',
                      loop.mode === 'AUTO' ? 'bg-status-ok' : 'bg-status-warning'
                    )}
                  >
                    {loop.mode}
                  </span>
                </div>
              </button>

              {/* Expanded controls */}
              {isExpanded && (
                <div className="p-3 border-t border-hmi-border bg-hmi-panel">
                  <div className="flex items-center justify-center gap-2">
                    {/* Decrease buttons */}
                    <button
                      onClick={() => adjustSetpoint(loop, -selectedIncrement * 5)}
                      disabled={!canCommand}
                      className={clsx(
                        'w-9 h-9 rounded-lg font-bold text-base transition-colors',
                        'bg-status-alarm/20 text-status-alarm hover:bg-status-alarm/30',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                        'touch-manipulation'
                      )}
                      title={`-${(selectedIncrement * 5).toFixed(1)}`}
                    >
                      --
                    </button>
                    <button
                      onClick={() => adjustSetpoint(loop, -selectedIncrement)}
                      disabled={!canCommand}
                      className={clsx(
                        'w-10 h-10 rounded-lg font-bold text-lg transition-colors',
                        'bg-status-alarm/20 text-status-alarm hover:bg-status-alarm/30',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                        'touch-manipulation'
                      )}
                      title={`-${selectedIncrement.toFixed(1)}`}
                    >
                      −
                    </button>

                    {/* Current setpoint display */}
                    <div className="px-4 py-2 min-w-[100px] text-center">
                      <div className="text-2xl font-bold font-mono text-status-info">
                        {loop.setpoint.toFixed(2)}
                      </div>
                      <div className="text-xs text-hmi-muted">Setpoint</div>
                    </div>

                    {/* Increase buttons */}
                    <button
                      onClick={() => adjustSetpoint(loop, selectedIncrement)}
                      disabled={!canCommand}
                      className={clsx(
                        'w-10 h-10 rounded-lg font-bold text-lg transition-colors',
                        'bg-status-ok/20 text-status-ok hover:bg-status-ok/30',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                        'touch-manipulation'
                      )}
                      title={`+${selectedIncrement.toFixed(1)}`}
                    >
                      +
                    </button>
                    <button
                      onClick={() => adjustSetpoint(loop, selectedIncrement * 5)}
                      disabled={!canCommand}
                      className={clsx(
                        'w-9 h-9 rounded-lg font-bold text-base transition-colors',
                        'bg-status-ok/20 text-status-ok hover:bg-status-ok/30',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                        'touch-manipulation'
                      )}
                      title={`+${(selectedIncrement * 5).toFixed(1)}`}
                    >
                      ++
                    </button>
                  </div>

                  {/* CV bar */}
                  <div className="mt-3">
                    <div className="flex justify-between text-xs text-hmi-muted mb-1">
                      <span>Output</span>
                      <span>{loop.cv?.toFixed(1) ?? '--'}%</span>
                    </div>
                    <div className="h-2 bg-hmi-border rounded-full overflow-hidden">
                      <div
                        className="h-full bg-status-warning transition-all duration-300"
                        style={{ width: `${Math.max(0, Math.min(100, loop.cv || 0))}%` }}
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Show more link */}
      {hasMore && (
        <div className="px-4 pb-4 text-center">
          <Link
            href="/control"
            className="text-sm text-status-info hover:underline"
          >
            +{loops.length - 4} more control loops →
          </Link>
        </div>
      )}
    </div>
  );
}

export default QuickControlPanel;
