'use client';

/**
 * System Status Indicator Component
 * Provides visible system health status for operators.
 *
 * Anti-patterns addressed:
 * - "UI treats 'no data' as 'nothing to show'"
 * - "Silent UI failure"
 *
 * ISA-101 Compliance:
 * - Explicit states: connecting, stale, disconnected
 * - Operator-visible warnings
 * - Data freshness indicators
 */

import { useState, useEffect, useCallback } from 'react';

export type SystemState =
  | 'connecting'      // Initial connection attempt
  | 'connected'       // Fully operational
  | 'reconnecting'    // Lost connection, attempting to reconnect
  | 'stale'           // Connected but data is old
  | 'degraded'        // Partial functionality
  | 'disconnected'    // No connection, not attempting
  | 'error';          // Error state

interface SystemHealth {
  state: SystemState;
  lastUpdate: Date | null;
  dataAge: number;  // seconds since last data
  apiReachable: boolean;
  wsConnected: boolean;
  controllerConnected: boolean;
  degradedComponents: string[];
  message: string;
}

interface SystemStatusIndicatorProps {
  className?: string;
  compact?: boolean;
  showDetails?: boolean;
}

const STATE_CONFIG: Record<SystemState, {
  color: string;
  bgColor: string;
  icon: React.ReactNode;
  label: string;
}> = {
  connecting: {
    color: 'text-yellow-600',
    bgColor: 'bg-yellow-100',
    label: 'Connecting...',
    icon: (
      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
      </svg>
    ),
  },
  connected: {
    color: 'text-green-600',
    bgColor: 'bg-green-100',
    label: 'Connected',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
      </svg>
    ),
  },
  reconnecting: {
    color: 'text-yellow-600',
    bgColor: 'bg-yellow-100',
    label: 'Reconnecting...',
    icon: (
      <svg className="w-4 h-4 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
  },
  stale: {
    color: 'text-orange-600',
    bgColor: 'bg-orange-100',
    label: 'Data Stale',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  degraded: {
    color: 'text-yellow-600',
    bgColor: 'bg-yellow-100',
    label: 'Degraded',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  },
  disconnected: {
    color: 'text-red-600',
    bgColor: 'bg-red-100',
    label: 'Disconnected',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3m8.293 8.293l1.414 1.414" />
      </svg>
    ),
  },
  error: {
    color: 'text-red-600',
    bgColor: 'bg-red-100',
    label: 'Error',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
      </svg>
    ),
  },
};

// Stale data threshold in seconds
const STALE_THRESHOLD_SECONDS = 30;

export default function SystemStatusIndicator({
  className = '',
  compact = false,
  showDetails = false,
}: SystemStatusIndicatorProps) {
  const [health, setHealth] = useState<SystemHealth>({
    state: 'connecting',
    lastUpdate: null,
    dataAge: 0,
    apiReachable: false,
    wsConnected: false,
    controllerConnected: false,
    degradedComponents: [],
    message: 'Initializing...',
  });
  const [showTooltip, setShowTooltip] = useState(false);

  // Check API health
  const checkApiHealth = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/health/functional', {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        signal: AbortSignal.timeout(5000),
      });

      if (!response.ok) {
        return { reachable: false, data: null };
      }

      const data = await response.json();
      return { reachable: true, data };
    } catch {
      return { reachable: false, data: null };
    }
  }, []);

  // Update data age
  useEffect(() => {
    const interval = setInterval(() => {
      setHealth(prev => {
        if (!prev.lastUpdate) return prev;

        const age = Math.floor((Date.now() - prev.lastUpdate.getTime()) / 1000);
        let newState = prev.state;

        // Determine state based on data age
        if (age > STALE_THRESHOLD_SECONDS && prev.state === 'connected') {
          newState = 'stale';
        } else if (age <= STALE_THRESHOLD_SECONDS && prev.state === 'stale') {
          newState = 'connected';
        }

        return {
          ...prev,
          dataAge: age,
          state: newState,
          message: newState === 'stale'
            ? `Data is ${age}s old - may be stale`
            : prev.message,
        };
      });
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  // Periodic health check
  useEffect(() => {
    const checkHealth = async () => {
      const { reachable, data } = await checkApiHealth();

      setHealth(prev => {
        const now = new Date();
        const degradedComponents: string[] = [];

        if (!reachable) {
          return {
            ...prev,
            state: 'disconnected',
            apiReachable: false,
            message: 'Cannot reach API server',
          };
        }

        // Parse health response
        const status = data?.status || 'unknown';
        const checks = data?.checks || {};

        // Check for degraded components
        if (checks.ui_assets?.status === 'error') {
          degradedComponents.push('UI Assets');
        }
        if (checks.profinet_controller?.status !== 'ok') {
          degradedComponents.push('PROFINET Controller');
        }
        if (checks.data_freshness?.status === 'degraded') {
          degradedComponents.push('Data Freshness');
        }

        let newState: SystemState;
        let message: string;

        if (status === 'critical') {
          newState = 'error';
          message = 'Critical system failure';
        } else if (status === 'degraded' || degradedComponents.length > 0) {
          newState = 'degraded';
          message = `Degraded: ${degradedComponents.join(', ')}`;
        } else if (status === 'healthy') {
          newState = 'connected';
          message = 'All systems operational';
        } else {
          newState = 'degraded';
          message = `Status: ${status}`;
        }

        return {
          state: newState,
          lastUpdate: now,
          dataAge: 0,
          apiReachable: true,
          wsConnected: prev.wsConnected,
          controllerConnected: checks.profinet_controller?.status === 'ok',
          degradedComponents,
          message,
        };
      });
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000); // Check every 30s

    return () => clearInterval(interval);
  }, [checkApiHealth]);

  const config = STATE_CONFIG[health.state];

  // Compact view (just icon + label)
  if (compact) {
    return (
      <div
        className={`flex items-center gap-1 px-2 py-1 rounded ${config.bgColor} ${config.color} ${className}`}
        title={health.message}
      >
        {config.icon}
        <span className="text-xs font-medium">{config.label}</span>
      </div>
    );
  }

  // Full view with tooltip
  return (
    <div className={`relative ${className}`}>
      <button
        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${config.bgColor} ${config.color} transition-colors hover:opacity-90`}
        onClick={() => setShowTooltip(!showTooltip)}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        aria-label={`System status: ${config.label}`}
      >
        {config.icon}
        <span className="text-sm font-medium">{config.label}</span>
        {health.dataAge > 0 && health.state !== 'connecting' && (
          <span className="text-xs opacity-75">
            ({health.dataAge}s ago)
          </span>
        )}
      </button>

      {/* Tooltip with details */}
      {(showTooltip || showDetails) && (
        <div className="absolute right-0 top-full mt-2 w-72 bg-slate-800 rounded-lg shadow-xl border border-slate-700 p-4 z-50">
          <h3 className="text-white font-semibold mb-3">System Status</h3>

          <div className="space-y-2 text-sm">
            {/* Status line */}
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Status:</span>
              <span className={config.color}>{config.label}</span>
            </div>

            {/* API */}
            <div className="flex items-center justify-between">
              <span className="text-slate-400">API:</span>
              <span className={health.apiReachable ? 'text-green-400' : 'text-red-400'}>
                {health.apiReachable ? 'Reachable' : 'Unreachable'}
              </span>
            </div>

            {/* Controller */}
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Controller:</span>
              <span className={health.controllerConnected ? 'text-green-400' : 'text-yellow-400'}>
                {health.controllerConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>

            {/* Data age */}
            {health.lastUpdate && (
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Data Age:</span>
                <span className={health.dataAge > STALE_THRESHOLD_SECONDS ? 'text-orange-400' : 'text-slate-300'}>
                  {health.dataAge}s
                </span>
              </div>
            )}

            {/* Degraded components */}
            {health.degradedComponents.length > 0 && (
              <div className="mt-3 pt-3 border-t border-slate-700">
                <span className="text-yellow-400 text-xs font-medium">Degraded Components:</span>
                <ul className="mt-1 text-xs text-slate-400">
                  {health.degradedComponents.map((c, i) => (
                    <li key={i}>• {c}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Message */}
            <div className="mt-3 pt-3 border-t border-slate-700">
              <p className="text-xs text-slate-400">{health.message}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Data Freshness Indicator
 * Shows how fresh the displayed data is.
 */
export function DataFreshnessIndicator({
  lastUpdate,
  staleThresholdSeconds = 30,
  className = '',
}: {
  lastUpdate: Date | null;
  staleThresholdSeconds?: number;
  className?: string;
}) {
  const [age, setAge] = useState(0);

  useEffect(() => {
    if (!lastUpdate) return;

    const update = () => {
      setAge(Math.floor((Date.now() - lastUpdate.getTime()) / 1000));
    };

    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [lastUpdate]);

  if (!lastUpdate) {
    return (
      <span className={`text-xs text-slate-500 ${className}`}>
        No data
      </span>
    );
  }

  const isStale = age > staleThresholdSeconds;

  return (
    <span
      className={`text-xs ${isStale ? 'text-orange-400' : 'text-slate-400'} ${className}`}
      title={`Last updated: ${lastUpdate.toLocaleTimeString()}`}
    >
      {isStale && (
        <svg className="w-3 h-3 inline mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      )}
      {age < 60 ? `${age}s ago` : `${Math.floor(age / 60)}m ago`}
    </span>
  );
}
