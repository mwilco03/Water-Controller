'use client';

/**
 * RTU Status Page - Default Landing Page
 * ISA-101 Compliant SCADA HMI for Water Treatment Controller
 *
 * Design principles:
 * - Mobile-first (360-390px width primary)
 * - Touch-friendly (44px+ targets)
 * - Two view modes: Cards (overview) and Table (detailed)
 * - Status uses color + text
 * - Progressive disclosure
 */

import { useEffect, useCallback, useState, useMemo } from 'react';
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
  DataTableView,
} from '@/components/hmi';
import type { RTUStatusData, DataPoint } from '@/components/hmi';
import Link from 'next/link';
import { TIMING, QUALITY_CODES } from '@/constants';
import { acknowledgeAlarm, acknowledgeAllAlarms, getRTUInventory } from '@/lib/api';

const PAGE_TITLE = 'RTU Status - Water Treatment Controller';

type ViewMode = 'cards' | 'table';

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
  const [viewMode, setViewMode] = useState<ViewMode>('cards');
  const [sensorData, setSensorData] = useState<DataPoint[]>([]);
  const [loadingSensors, setLoadingSensors] = useState(false);

  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);

  const loadAllSensors = useCallback(async () => {
    setLoadingSensors(true);
    try {
      const allSensors: DataPoint[] = [];

      // Fetch sensors from each RTU
      for (const rtu of rtus) {
        try {
          const inventory = await getRTUInventory(rtu.station_name);

          // Convert sensors to DataPoint format
          for (const sensor of inventory.sensors || []) {
            const quality = sensor.last_quality === QUALITY_CODES.GOOD ? 'good' :
                           sensor.last_quality === QUALITY_CODES.UNCERTAIN ? 'uncertain' :
                           sensor.last_quality === QUALITY_CODES.BAD ? 'bad' : 'stale';

            allSensors.push({
              id: sensor.id,
              rtuStation: rtu.station_name,
              name: sensor.name,
              type: sensor.sensor_type || 'unknown',
              value: sensor.last_value,
              unit: sensor.unit,
              quality,
              timestamp: sensor.last_update || new Date().toISOString(),
              highLimit: sensor.scale_max * 0.9, // 90% of max as high warning
              lowLimit: sensor.scale_min + (sensor.scale_max - sensor.scale_min) * 0.1, // 10% above min
              inAlarm: false, // Would need to cross-reference with alarms
            });
          }

          // Convert controls to DataPoint format
          for (const control of inventory.controls || []) {
            allSensors.push({
              id: `ctrl-${control.id}`,
              rtuStation: rtu.station_name,
              name: control.name,
              type: control.control_type || 'control',
              value: control.current_value,
              unit: control.current_state || '',
              quality: 'good',
              timestamp: control.last_update || new Date().toISOString(),
              isManual: control.is_manual || control.mode === 'manual' || control.mode === 'local',
            });
          }
        } catch (err) {
          console.error(`Failed to load sensors for ${rtu.station_name}:`, err);
        }
      }

      setSensorData(allSensors);
    } catch (err) {
      showMessage('error', 'Failed to load sensor data');
    } finally {
      setLoadingSensors(false);
    }
  }, [rtus, showMessage]);

  // Load sensor data when switching to table view
  useEffect(() => {
    if (viewMode === 'table' && rtus.length > 0 && sensorData.length === 0) {
      loadAllSensors();
    }
  }, [viewMode, rtus.length, sensorData.length, loadAllSensors]);

  // Mark sensors that have alarms
  const enrichedSensorData = useMemo(() => {
    const activeAlarms = alarms.filter(a => a.state !== 'CLEARED');
    return sensorData.map(sensor => ({
      ...sensor,
      inAlarm: activeAlarms.some(a =>
        a.rtu_station === sensor.rtuStation &&
        sensor.name.toLowerCase().includes(a.message?.toLowerCase().split(' ')[0] || '')
      ),
    }));
  }, [sensorData, alarms]);

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

  // Handle row click in table view
  const handleRowClick = useCallback((point: DataPoint) => {
    // Navigate to the RTU detail page
    window.location.href = `/rtus/${encodeURIComponent(point.rtuStation)}`;
  }, []);

  // Loading state
  if (loading) {
    return (
      <div className="space-y-4" aria-label="Loading RTU status...">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="skeleton h-6 w-32 mb-2" />
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

  // Error state
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
    <div className="space-y-4">
      {/* Alarm Banner */}
      <AlarmBanner
        alarms={alarms}
        onAcknowledge={handleAcknowledge}
        onAcknowledgeAll={handleAcknowledgeAll}
      />

      {/* Page Header with View Toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-hmi-text">RTU Status</h1>
          <p className="text-sm text-hmi-muted mt-1">
            {viewMode === 'cards' ? 'Overview of connected RTUs' : 'All sensor and control points'}
          </p>
        </div>

        <div className="flex items-center gap-4">
          {/* View Toggle */}
          <div className="flex rounded-lg border border-hmi-border overflow-hidden">
            <button
              onClick={() => setViewMode('cards')}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                viewMode === 'cards'
                  ? 'bg-status-info text-white'
                  : 'bg-hmi-panel text-hmi-muted hover:text-hmi-text'
              }`}
            >
              📊 Cards
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                viewMode === 'table'
                  ? 'bg-status-info text-white'
                  : 'bg-hmi-panel text-hmi-muted hover:text-hmi-text'
              }`}
            >
              📋 Table
            </button>
          </div>

          {/* Summary Stats */}
          <div className="hidden sm:flex items-center gap-4">
            <div className="text-center">
              <div className="text-xl font-semibold font-mono text-hmi-text">
                {onlineRtuCount}<span className="text-hmi-muted">/{rtus.length}</span>
              </div>
              <div className="text-xs text-hmi-muted">RTUs</div>
            </div>
            <div className="text-center">
              <div className={`text-xl font-semibold font-mono ${activeAlarmCount > 0 ? 'text-status-alarm' : 'text-hmi-text'}`}>
                {activeAlarmCount}
              </div>
              <div className="text-xs text-hmi-muted">Alarms</div>
            </div>
            <div className="flex items-center gap-1">
              <span className={`w-2 h-2 rounded-full ${connected ? 'bg-status-ok' : 'bg-status-offline'}`} />
              <span className="text-xs text-hmi-muted">{connected ? 'Live' : 'Offline'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Stats Row */}
      <div className="sm:hidden flex items-center justify-between px-1">
        <div className="flex items-center gap-4">
          <span className="text-sm">
            <span className="font-mono font-semibold">{onlineRtuCount}/{rtus.length}</span>
            <span className="text-hmi-muted ml-1">RTUs</span>
          </span>
          <span className="text-sm">
            <span className={`font-mono font-semibold ${activeAlarmCount > 0 ? 'text-status-alarm' : ''}`}>
              {activeAlarmCount}
            </span>
            <span className="text-hmi-muted ml-1">Alarms</span>
          </span>
        </div>
        <div className="flex items-center gap-1">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-status-ok' : 'bg-status-offline'}`} />
          <span className="text-xs text-hmi-muted">{connected ? 'Live' : 'Offline'}</span>
        </div>
      </div>

      {/* Quick Alarm Summary */}
      {activeAlarmCount > 0 && viewMode === 'cards' && (
        <div className="hmi-card p-3">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-semibold text-hmi-text text-sm flex items-center gap-2">
              <span className="px-1.5 py-0.5 rounded bg-status-alarm text-white text-xs font-bold">⚠</span>
              Active Alarms
            </h2>
            <div className="flex items-center gap-2">
              {activeAlarmCount > 1 && (
                <button
                  onClick={handleAcknowledgeAll}
                  className="px-2 py-1 rounded bg-status-alarm hover:bg-status-alarm/90 text-white text-xs font-medium transition-colors"
                >
                  ACK All
                </button>
              )}
              <Link href="/alarms" className="text-xs text-status-info hover:underline">
                View All
              </Link>
            </div>
          </div>
          <div className="space-y-1.5">
            {alarms
              .filter(a => a.state !== 'CLEARED')
              .slice(0, 3)
              .map((alarm) => {
                const isUnacked = alarm.state === 'ACTIVE';
                const isCritical = alarm.severity === 'CRITICAL';
                return (
                  <div
                    key={alarm.alarm_id}
                    className={`flex items-center justify-between gap-2 p-2 rounded border ${
                      isCritical
                        ? 'bg-status-alarm/10 border-status-alarm/30'
                        : 'bg-status-warning/10 border-status-warning/30'
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <span className={`shrink-0 px-1.5 py-0.5 rounded text-xs font-bold text-white ${
                        isCritical ? 'bg-status-alarm' : 'bg-status-warning'
                      }`}>
                        {alarm.severity?.substring(0, 4) || 'HIGH'}
                      </span>
                      <div className="min-w-0 flex-1">
                        <span className="text-sm text-hmi-text truncate block">
                          {alarm.rtu_station}: {alarm.message}
                        </span>
                      </div>
                      {isUnacked && (
                        <span className="shrink-0 w-2 h-2 rounded-full bg-status-alarm animate-pulse" />
                      )}
                    </div>
                    <button
                      onClick={() => handleAcknowledge(alarm.alarm_id)}
                      className="shrink-0 px-2 py-1 rounded bg-hmi-bg border border-hmi-border hover:bg-hmi-border text-xs font-medium"
                    >
                      ACK
                    </button>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Main Content: Cards or Table */}
      {viewMode === 'cards' ? (
        <>
          {/* Quick Control Panel */}
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
        </>
      ) : (
        /* Table View */
        <div>
          {loadingSensors ? (
            <div className="hmi-card p-6 text-center">
              <div className="inline-block animate-spin rounded-full h-6 w-6 border-2 border-hmi-border border-t-status-info mb-2" />
              <p className="text-sm text-hmi-muted">Loading sensor data...</p>
            </div>
          ) : enrichedSensorData.length > 0 ? (
            <DataTableView
              data={enrichedSensorData}
              groupByRtu={true}
              showSparklines={true}
              onRowClick={handleRowClick}
              sortable={true}
              compact={false}
            />
          ) : (
            <div className="hmi-card p-6 text-center">
              <span className="text-2xl text-hmi-muted mb-2 block">📋</span>
              <p className="text-hmi-muted">No sensor data available</p>
              <button
                onClick={loadAllSensors}
                className="mt-3 px-4 py-2 bg-status-info hover:bg-status-info/90 text-white rounded text-sm font-medium"
              >
                Load Sensors
              </button>
            </div>
          )}
        </div>
      )}

      {/* Shift Handoff Summary */}
      <ShiftHandoff rtus={rtus} alarms={alarms} />

      {/* Data Mode Indicator */}
      {dataMode === 'polling' && (
        <div className="p-2 bg-status-warning/10 border border-status-warning/30 rounded flex items-center gap-2 text-sm">
          <span className="px-1.5 py-0.5 rounded bg-status-warning text-white text-xs font-bold">⚠</span>
          <span className="text-hmi-text">
            Polling mode - updates every {TIMING.POLLING.NORMAL / 1000}s
          </span>
        </div>
      )}

      {dataMode === 'disconnected' && (
        <div className="p-2 bg-status-alarm/10 border border-status-alarm/30 rounded flex items-center gap-2 text-sm">
          <span className="px-1.5 py-0.5 rounded bg-status-alarm text-white text-xs font-bold">!</span>
          <span className="text-hmi-text flex-1">Disconnected from server</span>
          <button onClick={refetch} className="px-2 py-1 bg-status-alarm hover:bg-status-alarm/90 text-white rounded text-xs font-medium">
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
  const isFault = rtu.state === 'FAULT' || rtu.state === 'ERROR';
  const stateClass = isOnline ? 'ok' : isOffline ? 'offline' : isFault ? 'alarm' : 'warning';
  const hasAlarms = (rtu.alarm_count ?? 0) > 0;

  const stateLabel = isOnline ? 'Running' :
    isFault ? 'Fault' :
    isOffline ? 'Offline' : rtu.state;

  return (
    <div className={`hmi-card overflow-hidden ${hasAlarms ? 'border-l-4 border-l-status-alarm' : ''}`}>
      {/* Header */}
      <div className="p-3 border-b border-hmi-border">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className={`w-2 h-2 rounded-full ${
              isOnline ? 'bg-status-ok' : isFault ? 'bg-status-alarm' : 'bg-status-offline'
            }`} />
            <div className="min-w-0">
              <h3 className="font-medium text-hmi-text truncate text-sm">{rtu.station_name}</h3>
              {rtu.ip_address && (
                <p className="text-xs text-hmi-muted font-mono">{rtu.ip_address}</p>
              )}
            </div>
          </div>
          <span className={`status-badge ${stateClass} text-xs`}>
            {stateLabel}
          </span>
        </div>
      </div>

      {/* Stats */}
      <div className="p-3">
        <div className="grid grid-cols-3 gap-2 text-center">
          <div>
            <div className="text-base font-semibold font-mono text-hmi-text">
              {isOffline ? '--' : (rtu.sensor_count ?? 0)}
            </div>
            <div className="text-xs text-hmi-muted">Sensors</div>
          </div>
          <div>
            <div className="text-base font-semibold font-mono text-hmi-text">
              {isOffline ? '--' : (rtu.actuator_count ?? 0)}
            </div>
            <div className="text-xs text-hmi-muted">Controls</div>
          </div>
          <div>
            <div className={`text-base font-semibold font-mono ${hasAlarms ? 'text-status-alarm' : 'text-hmi-text'}`}>
              {rtu.alarm_count ?? 0}
            </div>
            <div className="text-xs text-hmi-muted">Alarms</div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <Link
        href={`/rtus/${encodeURIComponent(rtu.station_name)}`}
        className="flex items-center justify-between px-3 py-2 bg-hmi-bg border-t border-hmi-border hover:bg-hmi-border/50 transition-colors"
      >
        <span className="text-sm text-status-info font-medium">View Details</span>
        <span className="text-hmi-muted">→</span>
      </Link>
    </div>
  );
}
