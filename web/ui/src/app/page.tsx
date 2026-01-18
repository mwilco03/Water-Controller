'use client';

/**
 * RTU Status Page - Default Landing Page
 * ISA-101 Compliant SCADA HMI for Water Treatment Controller
 *
 * Design principles:
 * - Mobile-first (360-390px width primary)
 * - Touch-friendly (48px+ targets)
 * - Status uses color + text (text-only, no icons)
 * - Progressive disclosure
 * - Skeleton loading for stable layout
 */

import { useEffect, useCallback } from 'react';
import { useRTUStatusData } from '@/hooks/useRTUStatusData';
import {
  AlarmBanner,
  SkeletonRTUCard,
  SkeletonStats,
  ErrorMessage,
  ErrorPresets,
  ShiftHandoff,
  QuickControlPanel,
  useHMIToast,
} from '@/components/hmi';
import type { RTUStatusData } from '@/components/hmi';
import Link from 'next/link';
import { TIMING } from '@/constants';
import { acknowledgeAlarm, acknowledgeAllAlarms } from '@/lib/api';

const PAGE_TITLE = 'RTU Status - Water Treatment Controller';

export default function RTUStatusPage() {
  const {
    rtus,
    alarms,
    loading,
    error,
    dataMode,
    connected,
    refetch,
  } = useRTUStatusData();

  const { showMessage } = useHMIToast();

  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);

  // Alarm acknowledgment handler
  const handleAcknowledge = useCallback(async (alarmId: number | string) => {
    try {
      const numericId = typeof alarmId === 'string' ? parseInt(alarmId, 10) : alarmId;
      await acknowledgeAlarm(numericId, 'operator');
      showMessage('success', `Alarm ${alarmId} acknowledged`);
      refetch();
    } catch (err) {
      showMessage('error', `Failed to acknowledge alarm: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [refetch, showMessage]);

  // Acknowledge all alarms handler
  const handleAcknowledgeAll = useCallback(async () => {
    try {
      await acknowledgeAllAlarms('operator');
      showMessage('success', 'All alarms acknowledged');
      refetch();
    } catch (err) {
      showMessage('error', `Failed to acknowledge alarms: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [refetch, showMessage]);

  // Loading state - use skeleton for stable layout
  if (loading) {
    return (
      <div className="space-y-6" aria-label="Loading RTU status...">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="skeleton h-7 w-32 mb-2" />
            <div className="skeleton h-4 w-64" />
          </div>
          <SkeletonStats />
        </div>
        <div className="hmi-grid hmi-grid-auto">
          {[1, 2, 3, 4].map((i) => (
            <SkeletonRTUCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  // Error state - use actionable ErrorMessage
  if (error && rtus.length === 0) {
    return (
      <div className="flex items-center justify-center py-4">
        <div className="max-w-md w-full">
          <ErrorMessage
            {...ErrorPresets.connectionFailed(refetch)}
            description={error}
          />
        </div>
      </div>
    );
  }

  const activeAlarmCount = alarms.filter(a => a.state !== 'CLEARED').length;
  const onlineRtuCount = rtus.filter(r => r.state === 'RUNNING').length;

  return (
    <div className="space-y-6">
      {/* Alarm Banner */}
      <AlarmBanner
        alarms={alarms}
        onAcknowledge={handleAcknowledge}
        onAcknowledgeAll={handleAcknowledgeAll}
      />

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-hmi-text">RTU Status</h1>
          <p className="text-sm text-hmi-muted mt-1">
            Real-time status of connected Remote Terminal Units
          </p>
        </div>

        {/* Summary Stats */}
        <div className="flex items-center gap-6">
          <div className="text-center">
            <div className="text-2xl font-semibold font-mono text-hmi-text">
              {onlineRtuCount}<span className="text-hmi-muted">/{rtus.length}</span>
            </div>
            <div className="text-xs text-hmi-muted">RTUs Online</div>
          </div>
          <div className="text-center">
            <div className={`text-2xl font-semibold font-mono ${activeAlarmCount > 0 ? 'text-status-alarm' : 'text-hmi-text'}`}>
              {activeAlarmCount}
            </div>
            <div className="text-xs text-hmi-muted">Active Alarms</div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`status-dot ${connected ? 'ok' : 'offline'}`} />
            <span className="text-sm text-hmi-muted">{connected ? 'Connected' : 'Offline'}</span>
          </div>
        </div>
      </div>

      {/* Quick Alarm Summary - Top 3 active alarms with one-tap acknowledge */}
      {activeAlarmCount > 0 && (
        <div className="hmi-card p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-hmi-text flex items-center gap-2">
              <span className="px-2 py-0.5 rounded bg-status-alarm text-white text-xs font-bold">!</span>
              Active Alarms
            </h2>
            <div className="flex items-center gap-3">
              {activeAlarmCount > 1 && (
                <button
                  onClick={handleAcknowledgeAll}
                  className="px-3 py-1.5 rounded-lg bg-status-alarm hover:bg-status-alarm/90 text-white text-sm font-medium transition-colors touch-manipulation"
                  title="Acknowledge all alarms"
                >
                  ACK All
                </button>
              )}
              <Link href="/alarms" className="text-sm text-status-info hover:underline">
                View All ({activeAlarmCount})
              </Link>
            </div>
          </div>
          <div className="space-y-2">
            {alarms
              .filter(a => a.state !== 'CLEARED')
              .slice(0, 3)
              .map((alarm) => {
                const isUnacked = alarm.state === 'ACTIVE';
                const isCritical = alarm.severity === 'CRITICAL';
                return (
                  <div
                    key={alarm.alarm_id}
                    className={`flex items-center justify-between gap-3 p-3 rounded-lg border ${
                      isCritical
                        ? 'bg-status-alarm-light border-status-alarm'
                        : 'bg-status-warning-light border-status-warning'
                    } ${isUnacked ? 'animate-pulse-subtle' : ''}`}
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <span className={`shrink-0 px-2 py-0.5 rounded text-xs font-bold text-white ${
                        isCritical ? 'bg-status-alarm' : 'bg-status-warning'
                      }`}>
                        {alarm.severity || 'HIGH'}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="font-medium text-hmi-text truncate">
                          {alarm.rtu_station}{alarm.slot !== undefined ? ` - Slot ${alarm.slot}` : ''}
                        </div>
                        <div className="text-sm text-hmi-muted truncate">
                          {alarm.message}
                        </div>
                      </div>
                      {isUnacked && (
                        <span className="shrink-0 w-2 h-2 rounded-full bg-status-alarm animate-pulse"
                              title="Unacknowledged" />
                      )}
                    </div>
                    <button
                      onClick={() => handleAcknowledge(alarm.alarm_id)}
                      className="shrink-0 px-3 py-2 rounded-lg bg-hmi-panel border border-hmi-border hover:bg-hmi-bg text-sm font-medium text-hmi-text transition-colors touch-manipulation min-h-touch"
                      title="Acknowledge alarm"
                    >
                      ACK
                    </button>
                  </div>
                );
              })}
          </div>
          {activeAlarmCount > 3 && (
            <div className="mt-3 text-center">
              <Link
                href="/alarms"
                className="text-sm text-status-info hover:underline"
              >
                +{activeAlarmCount - 3} more alarms
              </Link>
            </div>
          )}
        </div>
      )}

      {/* Quick Control Panel - Fast setpoint adjustments */}
      <QuickControlPanel />

      {/* RTU Grid */}
      {rtus.length > 0 ? (
        <div className="hmi-grid hmi-grid-auto">
          {rtus.map((rtu) => (
            <RTUCard key={rtu.station_name} rtu={rtu} />
          ))}
        </div>
      ) : (
        <div className="hmi-card p-6 text-center">
          <h3 className="text-base font-medium text-hmi-text mb-1">No RTUs Configured</h3>
          <p className="text-hmi-muted text-sm mb-4">Add RTU devices to start monitoring</p>
          <a href="/rtus" className="hmi-btn hmi-btn-primary">
            Add RTU
          </a>
        </div>
      )}

      {/* Shift Handoff Summary - Collapsible section for shift changes */}
      <ShiftHandoff rtus={rtus} alarms={alarms} />

      {/* Data Mode Indicator */}
      {dataMode === 'polling' && (
        <div className="p-3 bg-quality-uncertain border border-status-warning/30 rounded-lg flex items-center gap-3 text-sm">
          <span className="px-2 py-0.5 rounded bg-status-warning text-white text-xs font-bold shrink-0">WARN</span>
          <span className="text-hmi-text">
            <strong>Polling Mode:</strong> WebSocket disconnected. Data updates every {TIMING.POLLING.NORMAL / 1000} seconds.
          </span>
        </div>
      )}

      {dataMode === 'disconnected' && (
        <div className="p-3 bg-quality-bad border border-status-alarm/30 rounded-lg flex items-center gap-3 text-sm">
          <span className="px-2 py-0.5 rounded bg-status-alarm text-white text-xs font-bold shrink-0">ERROR</span>
          <span className="text-hmi-text flex-1">
            <strong>Disconnected:</strong> Cannot reach API server.
          </span>
          <button onClick={refetch} className="hmi-btn hmi-btn-danger text-sm">
            Retry
          </button>
        </div>
      )}
    </div>
  );
}

// Status text for ISA-101 compliance (never color alone)
const StatusText = ({ state }: { state: string }) => {
  const isOnline = state === 'RUNNING';
  const isOffline = state === 'STOPPED' || state === 'OFFLINE';
  const isFault = state === 'FAULT' || state === 'ERROR';

  if (isOnline) return <span className="font-mono text-xs">OK</span>;
  if (isFault) return <span className="font-mono text-xs">!</span>;
  if (isOffline) return <span className="font-mono text-xs">--</span>;
  return <span className="font-mono text-xs">?</span>;
};

// RTU Card Component - Touch-friendly with 48px+ targets
function RTUCard({ rtu }: { rtu: RTUStatusData }) {
  const isOnline = rtu.state === 'RUNNING';
  const isOffline = rtu.state === 'STOPPED' || rtu.state === 'OFFLINE';
  const isFault = rtu.state === 'FAULT' || rtu.state === 'ERROR';
  const stateClass = isOnline ? 'ok' : isOffline ? 'offline' : isFault ? 'alarm' : 'warning';
  const hasAlarms = (rtu.alarm_count ?? 0) > 0;

  const stateLabel = isOnline ? 'Running' :
    isFault ? 'Fault' :
    isOffline ? 'Offline' : rtu.state;

  return (
    <div className={`hmi-card overflow-hidden ${hasAlarms ? 'border-l-4 border-l-status-alarm' : ''}`}>
      {/* Header - Status with color + text */}
      <div className="p-4 border-b border-hmi-border">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-3 min-w-0">
            <div className={`status-indicator ${stateClass}`} aria-hidden="true">
              <StatusText state={rtu.state} />
            </div>
            <div className="min-w-0">
              <h3 className="font-medium text-hmi-text truncate">{rtu.station_name}</h3>
              {rtu.ip_address && (
                <p className="text-xs text-hmi-muted font-mono">{rtu.ip_address}</p>
              )}
            </div>
          </div>
          <span className={`status-badge ${stateClass}`}>
            {stateLabel}
          </span>
        </div>
      </div>

      {/* Stats - Touch-friendly spacing */}
      <div className="p-4">
        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="py-1">
            <div className="text-lg font-semibold font-mono text-hmi-text">
              {isOffline ? '--' : (rtu.sensor_count ?? 0)}
            </div>
            <div className="text-xs text-hmi-muted">Sensors</div>
          </div>
          <div className="py-1">
            <div className="text-lg font-semibold font-mono text-hmi-text">
              {isOffline ? '--' : (rtu.actuator_count ?? 0)}
            </div>
            <div className="text-xs text-hmi-muted">Actuators</div>
          </div>
          <div className="py-1">
            <div className={`text-lg font-semibold font-mono ${hasAlarms ? 'text-status-alarm' : 'text-hmi-text'}`}>
              {rtu.alarm_count ?? 0}
            </div>
            <div className="text-xs text-hmi-muted">Alarms</div>
          </div>
        </div>
      </div>

      {/* Footer - Touch-friendly link (48px+ height) */}
      <Link
        href={`/rtus/${encodeURIComponent(rtu.station_name)}`}
        className="flex items-center justify-between px-4 py-3 bg-hmi-bg border-t border-hmi-border min-h-[48px] hover:bg-hmi-border/50 transition-colors touch-list-item"
      >
        <span className="text-sm text-status-info font-medium">View Details</span>
        <span className="text-hmi-muted font-mono">&rarr;</span>
      </Link>
    </div>
  );
}
