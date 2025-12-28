'use client';

/**
 * Degraded Mode Banner Component
 * Displays a prominent warning when the system is operating in degraded mode.
 *
 * ISA-101 Compliance:
 * - Yellow/amber for warning state
 * - Fixed position for constant visibility
 * - Clear explanation of what's degraded
 * - Flashing animation for attention
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

const REASON_CONFIG: Record<DegradedReason, { icon: React.ReactNode; title: string }> = {
  websocket_disconnected: {
    title: 'Real-Time Updates Unavailable',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3m8.293 8.293l1.414 1.414" />
      </svg>
    ),
  },
  api_unreachable: {
    title: 'API Server Unreachable',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
      </svg>
    ),
  },
  profinet_offline: {
    title: 'PROFINET Communication Lost',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
  },
  stale_data: {
    title: 'Data May Be Stale',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  partial_connectivity: {
    title: 'Partial System Connectivity',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  },
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

  const config = REASON_CONFIG[degradedInfo.reason];

  return (
    <div
      className={`
        bg-alarm-yellow text-hmi-text
        animate-pulse
        ${className}
      `}
      role="alert"
      aria-live="polite"
    >
      <div className="max-w-[1800px] mx-auto px-4 py-2 flex items-center justify-between gap-4">
        {/* Warning Info */}
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0">
            {config.icon}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold">{config.title}</span>
            <span className="text-sm opacity-80">|</span>
            <span className="text-sm">{degradedInfo.message}</span>
            {elapsed && (
              <>
                <span className="text-sm opacity-80">|</span>
                <span className="text-sm font-mono">Duration: {elapsed}</span>
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
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
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
