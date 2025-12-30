'use client';

/**
 * RTU Status Page - Default Landing Page
 * ISA-101 compliant SCADA HMI for Water Treatment Controller
 *
 * Design principles:
 * - Gray is normal, color is abnormal
 * - Operators view without barriers
 * - Data quality visually distinguished
 * - RTU connection status prominently displayed
 */

import { useEffect } from 'react';
import { alarmLogger } from '@/lib/logger';
import { useRTUStatusData } from '@/hooks/useRTUStatusData';
import {
  RTUStatusCard,
  AlarmBanner,
  SystemStatusBar,
  ConnectionStatusIndicator,
} from '@/components/hmi';
import type { ConnectionState } from '@/components/hmi';

const PAGE_TITLE = 'RTU Status - Water Treatment Controller';

export default function RTUStatusPage() {
  const {
    rtus,
    alarms,
    loading,
    error,
    dataMode,
    metrics,
    connected,
    refetch,
  } = useRTUStatusData();

  // Set page title
  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);

  // Handle alarm acknowledge
  const handleAcknowledgeAlarm = async (alarmId: number | string) => {
    try {
      await fetch(`/api/v1/alarms/${alarmId}/acknowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: 'operator' }),
      });
    } catch (err) {
      alarmLogger.error('Failed to acknowledge alarm', err);
    }
  };

  const handleAcknowledgeAll = async () => {
    try {
      await fetch('/api/v1/alarms/acknowledge-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: 'operator' }),
      });
    } catch (err) {
      alarmLogger.error('Failed to acknowledge all alarms', err);
    }
  };

  // Calculate overall PROFINET status
  const getProfinetStatus = (): ConnectionState => {
    if (rtus.length === 0) return 'OFFLINE';
    const onlineCount = rtus.filter(r => r.state === 'RUNNING').length;
    if (onlineCount === rtus.length) return 'ONLINE';
    if (onlineCount > 0) return 'DEGRADED';
    return 'OFFLINE';
  };

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-hmi-bg flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-alarm-blue border-t-transparent rounded-full animate-spin" />
          <div className="text-hmi-text-secondary">Loading RTU Status...</div>
        </div>
      </div>
    );
  }

  // Error state
  if (error && rtus.length === 0) {
    return (
      <div className="min-h-screen bg-hmi-bg flex items-center justify-center">
        <div className="bg-hmi-panel rounded-lg shadow-hmi-card p-8 max-w-md text-center">
          <svg className="w-16 h-16 mx-auto mb-4 text-alarm-red" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <h2 className="text-xl font-semibold text-hmi-text mb-2">Connection Error</h2>
          <p className="text-hmi-text-secondary mb-4">{error}</p>
          <button
            onClick={refetch}
            className="px-4 py-2 bg-alarm-blue text-white rounded-lg hover:bg-alarm-blue/90 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const activeAlarmCount = alarms.filter(a => a.state !== 'CLEARED').length;
  const onlineRtuCount = rtus.filter(r => r.state === 'RUNNING').length;
  const profinetStatus = getProfinetStatus();

  return (
    <div className="min-h-screen bg-hmi-bg flex flex-col">
      {/* Alarm Banner - visible at top when alarms exist */}
      <AlarmBanner
        alarms={alarms}
        onAcknowledge={handleAcknowledgeAlarm}
        onAcknowledgeAll={handleAcknowledgeAll}
      />

      {/* Main Content Area */}
      <main className="flex-1 p-6 max-w-[1800px] mx-auto w-full">
        {/* Page Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-hmi-text">RTU Status</h1>
              <p className="text-sm text-hmi-text-secondary mt-1">
                Real-time status of all connected Remote Terminal Units
              </p>
            </div>

            {/* Quick Stats */}
            <div className="flex items-center gap-6">
              <div className="text-center">
                <div className="text-2xl font-bold font-mono text-hmi-text">
                  {onlineRtuCount}
                  <span className="text-lg text-hmi-text-secondary">/{rtus.length}</span>
                </div>
                <div className="text-xs text-hmi-text-secondary">RTUs Online</div>
              </div>
              <div className="text-center">
                <div className={`text-2xl font-bold font-mono ${activeAlarmCount > 0 ? 'text-alarm-red' : 'text-hmi-text'}`}>
                  {activeAlarmCount}
                </div>
                <div className="text-xs text-hmi-text-secondary">Active Alarms</div>
              </div>
              <div className="flex items-center gap-2">
                <ConnectionStatusIndicator
                  state={profinetStatus}
                  label={profinetStatus === 'ONLINE' ? 'All Connected' : profinetStatus === 'DEGRADED' ? 'Partial' : 'Disconnected'}
                  size="lg"
                />
              </div>
            </div>
          </div>
        </div>

        {/* RTU Grid */}
        {rtus.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {rtus.map((rtu) => (
              <RTUStatusCard key={rtu.station_name} rtu={rtu} />
            ))}
          </div>
        ) : (
          <div className="bg-hmi-panel rounded-lg shadow-hmi-card p-12 text-center">
            <svg className="w-16 h-16 mx-auto mb-4 text-hmi-equipment" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
            <h3 className="text-lg font-medium text-hmi-text mb-2">No RTUs Configured</h3>
            <p className="text-hmi-text-secondary mb-4">Add RTU devices to start monitoring your water treatment system</p>
            <a
              href="/rtus"
              className="inline-flex items-center gap-2 px-4 py-2 bg-alarm-blue hover:bg-alarm-blue/90 rounded-lg text-white transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add RTU
            </a>
          </div>
        )}

        {/* Data Mode Indicator for degraded states */}
        {dataMode === 'polling' && (
          <div className="mt-4 p-3 bg-quality-uncertain-bg border border-alarm-yellow rounded-lg flex items-center gap-2 text-sm">
            <svg className="w-4 h-4 text-alarm-yellow" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <span className="text-hmi-text">
              <strong>Reduced Connectivity:</strong> WebSocket disconnected. Using polling fallback (5s refresh).
            </span>
          </div>
        )}

        {dataMode === 'disconnected' && (
          <div className="mt-4 p-3 bg-quality-bad-bg border border-alarm-red rounded-lg flex items-center gap-2 text-sm">
            <svg className="w-4 h-4 text-alarm-red" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <span className="text-hmi-text">
              <strong>Communication Lost:</strong> Cannot reach API server.
            </span>
            <button
              onClick={refetch}
              className="ml-auto px-3 py-1 bg-alarm-red text-white rounded hover:bg-alarm-red/90 transition-colors"
            >
              Retry
            </button>
          </div>
        )}
      </main>

      {/* System Status Bar */}
      <SystemStatusBar
        profinetStatus={profinetStatus}
        websocketStatus={connected ? 'ONLINE' : 'OFFLINE'}
        cycleTimeMs={metrics.cycleTimeMs}
        pendingWrites={metrics.pendingWrites}
        dataMode={dataMode}
        pollIntervalSeconds={5}
      />
    </div>
  );
}
