'use client';

/**
 * Degraded Mode Banner Component
 * Displays a warning when the system is operating in degraded mode.
 *
 * ISA-101 Compliance:
 * - Amber/warning color for degraded state
 * - Clear explanation of what's degraded
 */

import { useState, useEffect } from 'react';

export type DegradedReason =
  | 'websocket_disconnected'
  | 'api_unreachable'
  | 'profinet_offline'
  | 'stale_data'
  | 'partial_connectivity';

interface DegradedInfo {
  reason: DegradedReason;
  message: string;
  details?: string;
  since?: Date;
}

interface DegradedModeBannerProps {
  degradedInfo: DegradedInfo | null;
  onDismiss?: () => void;
  className?: string;
}

const REASON_TITLES: Record<DegradedReason, string> = {
  websocket_disconnected: 'Real-Time Updates Unavailable',
  api_unreachable: 'API Server Unreachable',
  profinet_offline: 'PROFINET Communication Lost',
  stale_data: 'Data May Be Stale',
  partial_connectivity: 'Partial System Connectivity',
};

export default function DegradedModeBanner({
  degradedInfo,
  onDismiss,
  className = '',
}: DegradedModeBannerProps) {
  const [elapsed, setElapsed] = useState<string>('');

  // Update elapsed time
  useEffect(() => {
    if (!degradedInfo?.since) return;

    const updateElapsed = () => {
      const seconds = Math.floor((Date.now() - degradedInfo.since!.getTime()) / 1000);
      if (seconds < 60) {
        setElapsed(`${seconds}s`);
      } else if (seconds < 3600) {
        setElapsed(`${Math.floor(seconds / 60)}m`);
      } else {
        setElapsed(`${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`);
      }
    };

    updateElapsed();
    const interval = setInterval(updateElapsed, 1000);
    return () => clearInterval(interval);
  }, [degradedInfo?.since]);

  if (!degradedInfo) return null;

  const title = REASON_TITLES[degradedInfo.reason];

  return (
    <div
      className={`bg-status-warning text-hmi-text ${className}`}
      role="alert"
      aria-live="polite"
    >
      <div className="hmi-container py-2 flex items-center justify-between gap-4 flex-wrap">
        {/* Warning Info */}
        <div className="flex items-center gap-3">
          <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div className="flex items-center gap-2 flex-wrap text-sm">
            <span className="font-semibold">{title}</span>
            <span className="opacity-60">|</span>
            <span>{degradedInfo.message}</span>
            {elapsed && (
              <>
                <span className="opacity-60">|</span>
                <span className="font-mono">{elapsed}</span>
              </>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {degradedInfo.details && (
            <span className="text-xs bg-black/10 px-2 py-1 rounded">
              {degradedInfo.details}
            </span>
          )}
          <button
            onClick={() => window.location.reload()}
            className="px-3 py-1 text-sm bg-black/20 hover:bg-black/30 rounded transition-colors"
          >
            Refresh
          </button>
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="p-1 hover:bg-black/20 rounded transition-colors"
              aria-label="Dismiss"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Hook to manage degraded mode state
 */
export function useDegradedMode() {
  const [degradedInfo, setDegradedInfo] = useState<DegradedInfo | null>(null);

  const setDegraded = (reason: DegradedReason, message: string, details?: string) => {
    setDegradedInfo({
      reason,
      message,
      details,
      since: new Date(),
    });
  };

  const clearDegraded = () => {
    setDegradedInfo(null);
  };

  return {
    degradedInfo,
    isDegraded: degradedInfo !== null,
    setDegraded,
    clearDegraded,
  };
}
