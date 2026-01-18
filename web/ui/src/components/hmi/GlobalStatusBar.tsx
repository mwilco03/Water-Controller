'use client';

/**
 * GlobalStatusBar Component
 * Persistent status bar showing critical system information
 *
 * Design Philosophy:
 * - TEXT is primary, icons are secondary
 * - States are MUTUALLY EXCLUSIVE - never show contradictory information
 * - Always answer: "Is it working?" and "What should I do?"
 * - ISA-101: Gray is normal, color is abnormal
 *
 * Shows (in priority order):
 * 1. System Operational State (single, unambiguous)
 * 2. PROFINET Controller state
 * 3. RTU connection summary
 * 4. Active alarm count with severity
 * 5. Data freshness indicator
 */

import { useMemo } from 'react';
import Link from 'next/link';
import {
  SYSTEM_OPERATIONAL_STATES,
  deriveSystemOperationalState,
  getSystemOperationalStateLabel,
  getSystemOperationalStateClass,
  getProfinetStateLabel,
  getProfinetStateClass,
  getDataFreshnessState,
  DATA_FRESHNESS_STATES,
} from '@/constants/system';
import type { SystemOperationalState, ProfinetState, DataFreshnessState } from '@/constants/system';

export interface RTUStatusSummary {
  stationName: string;
  state: string;
  hasAlarms: boolean;
}

export interface GlobalStatusBarProps {
  /** Is the API backend reachable */
  isApiConnected: boolean;
  /** Is WebSocket real-time transport connected */
  isWebSocketConnected: boolean;
  /** PROFINET controller state */
  profinetState?: ProfinetState | string;
  /** PROFINET cycle time in milliseconds */
  cycleTimeMs?: number;
  /** List of RTU statuses for summary */
  rtus: RTUStatusSummary[];
  /** Number of active alarms */
  activeAlarmCount: number;
  /** Highest alarm severity among active alarms */
  highestAlarmSeverity?: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO' | null;
  /** Last data update timestamp */
  lastUpdate?: Date | string;
  /** Number of pending writes (uncommitted changes) */
  pendingWrites?: number;
}

/**
 * Status indicator styles based on ISA-101
 */
const STATUS_STYLES = {
  ok: {
    text: 'text-status-ok',
    bg: 'bg-status-ok-light',
    border: 'border-status-ok',
    dot: 'bg-status-ok',
  },
  warning: {
    text: 'text-status-warning',
    bg: 'bg-status-warning-light',
    border: 'border-status-warning',
    dot: 'bg-status-warning',
  },
  alarm: {
    text: 'text-status-alarm',
    bg: 'bg-status-alarm-light',
    border: 'border-status-alarm',
    dot: 'bg-status-alarm',
  },
  offline: {
    text: 'text-hmi-muted',
    bg: 'bg-hmi-bg',
    border: 'border-hmi-border',
    dot: 'bg-hmi-equipment',
  },
} as const;

type StatusType = keyof typeof STATUS_STYLES;

/**
 * Status text with optional indicator dot
 * Text-first design - no large icons
 */
function StatusText({
  status,
  label,
  sublabel,
  href,
  showDot = true,
  pulseDot = false,
  className = '',
}: {
  status: StatusType;
  label: string;
  sublabel?: string;
  href?: string;
  showDot?: boolean;
  pulseDot?: boolean;
  className?: string;
}) {
  const styles = STATUS_STYLES[status];

  const content = (
    <div className={`flex items-center gap-2 ${className}`}>
      {showDot && (
        <span
          className={`w-2 h-2 rounded-full ${styles.dot} ${pulseDot ? 'animate-pulse' : ''}`}
          aria-hidden="true"
        />
      )}
      <span className={`text-sm font-medium ${status !== 'ok' ? styles.text : 'text-hmi-text'}`}>
        {label}
      </span>
      {sublabel && (
        <span className="text-sm text-hmi-muted">
          {sublabel}
        </span>
      )}
    </div>
  );

  if (href) {
    return (
      <Link
        href={href}
        className="hover:bg-hmi-bg px-2 py-1 rounded transition-colors"
        title={`${label}${sublabel ? ` - ${sublabel}` : ''}`}
      >
        {content}
      </Link>
    );
  }

  return <div className="px-2 py-1">{content}</div>;
}

/**
 * Divider between status items
 */
function StatusDivider() {
  return <div className="w-px h-4 bg-hmi-border mx-1 hidden sm:block" />;
}

/**
 * Format time since last update
 */
function formatTimeSince(date: Date | string | undefined): string {
  if (!date) return '--';
  const timestamp = typeof date === 'string' ? new Date(date) : date;
  const seconds = Math.floor((Date.now() - timestamp.getTime()) / 1000);

  if (seconds < 0) return 'now';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

export function GlobalStatusBar({
  isApiConnected,
  isWebSocketConnected,
  profinetState,
  cycleTimeMs,
  rtus,
  activeAlarmCount,
  highestAlarmSeverity,
  lastUpdate,
  pendingWrites = 0,
}: GlobalStatusBarProps) {
  // Derive the primary system operational state
  const systemState = useMemo(() =>
    deriveSystemOperationalState({
      isApiConnected,
      isWebSocketConnected,
      rtuCount: rtus.length,
    }),
    [isApiConnected, isWebSocketConnected, rtus.length]
  );

  // Calculate RTU summary
  const rtuSummary = useMemo(() => {
    const total = rtus.length;
    const online = rtus.filter(r => r.state === 'RUNNING').length;
    const offline = rtus.filter(r =>
      r.state === 'OFFLINE' || r.state === 'ERROR' || r.state === 'FAULT'
    );
    return {
      total,
      online,
      offlineCount: offline.length,
      offlineNames: offline.slice(0, 3).map(r => r.stationName),
    };
  }, [rtus]);

  // Data freshness
  const dataFreshness = getDataFreshnessState(lastUpdate);

  // Determine status types
  const systemStateClass = getSystemOperationalStateClass(systemState);
  const systemStateLabel = getSystemOperationalStateLabel(systemState);

  const profinetStatus = profinetState
    ? getProfinetStateClass(profinetState)
    : 'offline';
  const profinetLabel = profinetState
    ? getProfinetStateLabel(profinetState)
    : 'Unknown';

  const rtuStatus: StatusType =
    rtuSummary.total === 0
      ? 'offline'
      : rtuSummary.online === rtuSummary.total
      ? 'ok'
      : rtuSummary.online > 0
      ? 'warning'
      : 'alarm';

  const alarmStatus: StatusType =
    activeAlarmCount === 0
      ? 'ok'
      : highestAlarmSeverity === 'CRITICAL' || highestAlarmSeverity === 'HIGH'
      ? 'alarm'
      : 'warning';

  const freshnessStatus: StatusType =
    dataFreshness === DATA_FRESHNESS_STATES.FRESH
      ? 'ok'
      : dataFreshness === DATA_FRESHNESS_STATES.STALE
      ? 'warning'
      : 'alarm';

  // If system is not operational, show simplified status
  if (systemState !== SYSTEM_OPERATIONAL_STATES.OPERATIONAL) {
    return (
      <div className="flex items-center gap-2" role="status" aria-label="System status">
        <StatusText
          status={systemStateClass}
          label={systemStateLabel}
          showDot={true}
          pulseDot={systemState === SYSTEM_OPERATIONAL_STATES.DISCONNECTED}
        />
        {systemState === SYSTEM_OPERATIONAL_STATES.DEGRADED && lastUpdate && (
          <>
            <StatusDivider />
            <StatusText
              status={freshnessStatus}
              label={`Updated ${formatTimeSince(lastUpdate)}`}
              showDot={false}
            />
          </>
        )}
      </div>
    );
  }

  // Full status bar for operational system
  return (
    <div className="flex items-center flex-wrap gap-y-1" role="status" aria-label="System status">
      {/* PROFINET Status - always show for operational systems */}
      {profinetState && (
        <StatusText
          status={profinetStatus}
          label={`PN: ${profinetLabel}`}
          sublabel={cycleTimeMs !== undefined ? `${cycleTimeMs}ms` : undefined}
          href="/system"
          showDot={true}
        />
      )}

      <StatusDivider />

      {/* RTU Summary */}
      <StatusText
        status={rtuStatus}
        label={`RTUs: ${rtuSummary.online}/${rtuSummary.total}`}
        sublabel={
          rtuSummary.offlineCount > 0
            ? `(${rtuSummary.offlineNames[0]}${rtuSummary.offlineCount > 1 ? ` +${rtuSummary.offlineCount - 1}` : ''} down)`
            : undefined
        }
        href="/rtus"
        showDot={true}
      />

      <StatusDivider />

      {/* Active Alarms */}
      <StatusText
        status={alarmStatus}
        label={
          activeAlarmCount === 0
            ? 'No Alarms'
            : `${activeAlarmCount} Alarm${activeAlarmCount !== 1 ? 's' : ''}`
        }
        sublabel={
          activeAlarmCount > 0 && highestAlarmSeverity
            ? `(${highestAlarmSeverity})`
            : undefined
        }
        href="/alarms"
        showDot={true}
        pulseDot={alarmStatus === 'alarm'}
      />

      {/* Data Freshness - only show if not fresh */}
      {dataFreshness !== DATA_FRESHNESS_STATES.FRESH && (
        <>
          <StatusDivider />
          <StatusText
            status={freshnessStatus}
            label={`Data: ${formatTimeSince(lastUpdate)}`}
            showDot={true}
          />
        </>
      )}

      {/* Pending Writes */}
      {pendingWrites > 0 && (
        <>
          <StatusDivider />
          <StatusText
            status="warning"
            label={`${pendingWrites} Unsaved`}
            showDot={true}
          />
        </>
      )}
    </div>
  );
}

export default GlobalStatusBar;
