'use client';

/**
 * RTU Status Page - Default Landing Page
 * ISA-101 Compliant SCADA HMI for Water Treatment Controller
 *
 * Design principles:
 * - Gray is normal, color is abnormal
 * - Clean, minimal interface
 * - Responsive grid layout
 * - High-contrast process values
 */

import { useEffect } from 'react';
import { useRTUStatusData } from '@/hooks/useRTUStatusData';
import { AlarmBanner } from '@/components/hmi';
import type { RTUStatusData } from '@/components/hmi';

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

  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-3 border-status-info border-t-transparent rounded-full spinner" />
          <p className="text-hmi-muted">Loading RTU Status...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error && rtus.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="hmi-card max-w-md w-full text-center p-8">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-quality-bad flex items-center justify-center">
            <svg className="w-6 h-6 text-status-alarm" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-hmi-text mb-2">Connection Error</h2>
          <p className="text-hmi-muted mb-6">{error}</p>
          <button onClick={refetch} className="hmi-btn hmi-btn-primary">
            Retry Connection
          </button>
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
        onAcknowledge={() => {}}
        onAcknowledgeAll={() => {}}
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

      {/* RTU Grid */}
      {rtus.length > 0 ? (
        <div className="hmi-grid hmi-grid-auto">
          {rtus.map((rtu) => (
            <RTUCard key={rtu.station_name} rtu={rtu} />
          ))}
        </div>
      ) : (
        <div className="hmi-card p-12 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-hmi-bg flex items-center justify-center">
            <svg className="w-8 h-8 text-hmi-equipment" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-hmi-text mb-2">No RTUs Configured</h3>
          <p className="text-hmi-muted mb-6">Add RTU devices to start monitoring</p>
          <a href="/rtus" className="hmi-btn hmi-btn-primary">
            Add RTU
          </a>
        </div>
      )}

      {/* Data Mode Indicator */}
      {dataMode === 'polling' && (
        <div className="p-3 bg-quality-uncertain border border-status-warning/30 rounded-lg flex items-center gap-3 text-sm">
          <svg className="w-5 h-5 text-status-warning shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          <span className="text-hmi-text">
            <strong>Polling Mode:</strong> WebSocket disconnected. Data updates every 5 seconds.
          </span>
        </div>
      )}

      {dataMode === 'disconnected' && (
        <div className="p-3 bg-quality-bad border border-status-alarm/30 rounded-lg flex items-center gap-3 text-sm">
          <svg className="w-5 h-5 text-status-alarm shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
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

// RTU Card Component
function RTUCard({ rtu }: { rtu: RTUStatusData }) {
  const isOnline = rtu.state === 'RUNNING';
  const isOffline = rtu.state === 'STOPPED' || rtu.state === 'OFFLINE';
  const stateClass = isOnline ? 'ok' : isOffline ? 'offline' : 'warning';
  const hasAlarms = (rtu.alarm_count ?? 0) > 0;

  return (
    <div className={`hmi-card overflow-hidden ${hasAlarms ? 'border-status-alarm' : ''}`}>
      {/* Header */}
      <div className="p-4 border-b border-hmi-border">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-3 min-w-0">
            <span className={`status-dot ${stateClass}`} />
            <div className="min-w-0">
              <h3 className="font-medium text-hmi-text truncate">{rtu.station_name}</h3>
              {rtu.ip_address && (
                <p className="text-xs text-hmi-muted font-mono">{rtu.ip_address}</p>
              )}
            </div>
          </div>
          <span className={`status-badge ${stateClass}`}>
            {rtu.state}
          </span>
        </div>
      </div>

      {/* Stats */}
      <div className="p-4">
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="text-lg font-semibold font-mono text-hmi-text">
              {isOffline ? '--' : (rtu.sensor_count ?? 0)}
            </div>
            <div className="text-xs text-hmi-muted">Sensors</div>
          </div>
          <div>
            <div className="text-lg font-semibold font-mono text-hmi-text">
              {isOffline ? '--' : (rtu.actuator_count ?? 0)}
            </div>
            <div className="text-xs text-hmi-muted">Actuators</div>
          </div>
          <div>
            <div className={`text-lg font-semibold font-mono ${hasAlarms ? 'text-status-alarm' : 'text-hmi-text'}`}>
              {rtu.alarm_count ?? 0}
            </div>
            <div className="text-xs text-hmi-muted">Alarms</div>
          </div>
        </div>
      </div>

      {/* Footer - View Details Link */}
      <div className="px-4 py-3 bg-hmi-bg border-t border-hmi-border">
        <a
          href={`/rtus/${encodeURIComponent(rtu.station_name)}`}
          className="text-sm text-status-info hover:underline flex items-center gap-1"
        >
          View Details
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </a>
      </div>
    </div>
  );
}
