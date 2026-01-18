'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { getRTU, getRTUInventory, refreshRTUInventory } from '@/lib/api';
import type { RTUDevice, RTUInventory } from '@/lib/api';
import { SensorList, ControlList, InventoryRefresh, RtuStateBadge, ProfinetStatus, StaleIndicator } from '@/components/rtu';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useCommandMode } from '@/contexts/CommandModeContext';
import CommandModeLogin from '@/components/CommandModeLogin';
import { rtuLogger } from '@/lib/logger';

type Tab = 'overview' | 'sensors' | 'controls' | 'profinet';

export default function RTUDetailPage() {
  const params = useParams();
  const stationName = params.station_name as string;
  const { canCommand, mode } = useCommandMode();

  const [rtu, setRtu] = useState<RTUDevice | null>(null);
  const [inventory, setInventory] = useState<RTUInventory | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [rtuData, inventoryData] = await Promise.all([
        getRTU(stationName),
        getRTUInventory(stationName),
      ]);
      setRtu(rtuData);
      setInventory(inventoryData);
      setError(null);
    } catch (err) {
      rtuLogger.error('Failed to fetch RTU data', err);
      setError(err instanceof Error ? err.message : 'Failed to load RTU data');
    } finally {
      setLoading(false);
    }
  }, [stationName]);

  // WebSocket for real-time updates
  const { connected, subscribe } = useWebSocket({
    onConnect: () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    },
    onDisconnect: () => {
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(fetchData, 5000);
      }
    },
  });

  // Subscribe to RTU updates
  useEffect(() => {
    const unsub = subscribe('rtu_update', (_event: string, data: { station_name?: string }) => {
      if (!data?.station_name || data.station_name === stationName) {
        fetchData();
      }
    });

    const unsubSensor = subscribe('sensor_update', (_event: string, data: { rtu_station?: string }) => {
      if (data?.rtu_station === stationName) {
        fetchData();
      }
    });

    return () => {
      unsub();
      unsubSensor();
    };
  }, [subscribe, stationName, fetchData]);

  // Initial fetch and polling
  useEffect(() => {
    fetchData();
    pollIntervalRef.current = setInterval(fetchData, 5000);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [fetchData]);

  const handleInventoryRefresh = useCallback((newInventory: RTUInventory) => {
    setInventory(newInventory);
  }, []);

  const getStateColor = (state: string) => {
    switch (state) {
      case 'RUNNING':
        return '#10b981';
      case 'CONNECTING':
      case 'DISCOVERY':
        return '#f59e0b';
      case 'ERROR':
        return '#ef4444';
      default:
        return '#6b7280';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-status-info" />
      </div>
    );
  }

  if (error || !rtu) {
    return (
      <div className="text-center py-12">
        <div className="text-status-alarm mb-4">{error || 'RTU not found'}</div>
        <Link href="/rtus" className="text-status-info hover:underline">
          Back to RTU List
        </Link>
      </div>
    );
  }

  const stateColor = getStateColor(rtu.state);
  const isOnline = rtu.state === 'RUNNING';
  const sensors = inventory?.sensors ?? [];
  const controls = inventory?.controls ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Link
            href="/rtus"
            className="p-2 rounded-lg bg-hmi-bg hover:bg-hmi-border transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-hmi-text">{rtu.station_name}</h1>
              <RtuStateBadge state={rtu.state} size="md" />
            </div>
            <p className="text-hmi-muted font-mono mt-1">{rtu.ip_address || 'No IP address'}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 text-sm">
          <span className={`flex items-center gap-1 ${connected ? 'text-status-ok' : 'text-status-warning'}`}>
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-status-ok' : 'bg-status-warning'}`} />
            {connected ? 'Live' : 'Polling'}
          </span>
        </div>
      </div>

      {/* Inventory Refresh */}
      <div className="bg-hmi-panel border border-hmi-border rounded-lg p-4">
        <InventoryRefresh
          rtuStation={stationName}
          lastRefresh={inventory?.last_refresh}
          onRefreshComplete={handleInventoryRefresh}
        />
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-hmi-panel border border-hmi-border rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-hmi-text">{rtu.slot_count}</div>
          <div className="text-sm text-hmi-muted">Slots</div>
        </div>
        <div className="bg-hmi-panel border border-hmi-border rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-status-ok">{sensors.length}</div>
          <div className="text-sm text-hmi-muted">Sensors</div>
        </div>
        <div className="bg-hmi-panel border border-hmi-border rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-status-info">{controls.length}</div>
          <div className="text-sm text-hmi-muted">Controls</div>
        </div>
        <div className="bg-hmi-panel border border-hmi-border rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-control-manual">
            {controls.filter((c) =>
              ['ON', 'RUNNING', 'OPEN'].includes(c.current_state?.toUpperCase() ?? '')
            ).length}
          </div>
          <div className="text-sm text-hmi-muted">Active</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-hmi-border">
        <nav className="flex gap-4">
          {(['overview', 'sensors', 'controls', 'profinet'] as Tab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`py-3 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === tab
                  ? 'border-status-info text-status-info'
                  : 'border-transparent text-hmi-muted hover:text-hmi-text hover:border-hmi-border'
              }`}
            >
              {tab === 'overview' && 'Overview'}
              {tab === 'sensors' && `Sensors (${sensors.length})`}
              {tab === 'controls' && `Controls (${controls.length})`}
              {tab === 'profinet' && 'PROFINET'}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="bg-hmi-panel border border-hmi-border rounded-lg p-6">
        {activeTab === 'overview' && (
          <div className="space-y-8">
            {/* Device Info */}
            <div>
              <h3 className="text-lg font-semibold text-hmi-text mb-4">Device Information</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="bg-hmi-bg/50 p-3 rounded">
                  <div className="text-xs text-hmi-muted">Vendor ID</div>
                  <div className="text-hmi-text font-mono">0x{rtu.vendor_id.toString(16).padStart(4, '0')}</div>
                </div>
                <div className="bg-hmi-bg/50 p-3 rounded">
                  <div className="text-xs text-hmi-muted">Device ID</div>
                  <div className="text-hmi-text font-mono">0x{rtu.device_id.toString(16).padStart(4, '0')}</div>
                </div>
                <div className="bg-hmi-bg/50 p-3 rounded">
                  <div className="text-xs text-hmi-muted">State</div>
                  <div style={{ color: stateColor }}>{rtu.state}</div>
                </div>
                <div className="bg-hmi-bg/50 p-3 rounded">
                  <div className="text-xs text-hmi-muted">Slots</div>
                  <div className="text-hmi-text">{rtu.slot_count}</div>
                </div>
              </div>
            </div>

            {/* Sensors Preview */}
            {sensors.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-hmi-text">Sensors</h3>
                  <button
                    onClick={() => setActiveTab('sensors')}
                    className="text-sm text-status-info hover:underline"
                  >
                    View all
                  </button>
                </div>
                <SensorList sensors={sensors.slice(0, 6)} size="sm" groupByType={false} />
              </div>
            )}

            {/* Controls Preview */}
            {controls.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-hmi-text">Controls</h3>
                  <button
                    onClick={() => setActiveTab('controls')}
                    className="text-sm text-status-info hover:underline"
                  >
                    View all
                  </button>
                </div>
                <ControlList
                  controls={controls.slice(0, 4)}
                  rtuStation={stationName}
                  groupByType={false}
                  disabled={!isOnline}
                  interactive={canCommand}
                  onCommandSent={fetchData}
                />
              </div>
            )}

            {/* Empty State */}
            {sensors.length === 0 && controls.length === 0 && (
              <div className="text-center py-4 text-hmi-muted">
                <svg className="w-8 h-8 max-w-8 max-h-8 mx-auto mb-2 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                </svg>
                <p className="text-sm">No inventory data</p>
                <p className="text-xs mt-1">Click &quot;Refresh Inventory&quot; to query the RTU</p>
              </div>
            )}

            {/* Quick Links */}
            <div className="flex flex-wrap gap-3 pt-4 border-t border-hmi-border">
              <Link
                href={`/trends?rtu=${stationName}`}
                className="px-4 py-2 rounded bg-hmi-border hover:bg-gray-600 text-hmi-text text-sm transition-colors"
              >
                View Trends
              </Link>
              <Link
                href={`/alarms?rtu=${stationName}`}
                className="px-4 py-2 rounded bg-hmi-border hover:bg-gray-600 text-hmi-text text-sm transition-colors"
              >
                View Alarms
              </Link>
              <Link
                href={`/control?rtu=${stationName}`}
                className="px-4 py-2 rounded bg-hmi-border hover:bg-gray-600 text-hmi-text text-sm transition-colors"
              >
                PID Control
              </Link>
            </div>
          </div>
        )}

        {activeTab === 'sensors' && (
          <SensorList sensors={sensors} size="md" groupByType />
        )}

        {activeTab === 'controls' && (
          <div className="space-y-4">
            {/* Command Mode Notice */}
            {mode === 'view' && controls.length > 0 && (
              <div className="flex items-center justify-between p-4 bg-orange-900/20 border border-orange-700/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <svg className="w-5 h-5 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <div>
                    <p className="text-orange-200 font-medium">View Mode Active</p>
                    <p className="text-sm text-orange-300/70">Enter Command Mode to control equipment</p>
                  </div>
                </div>
                <CommandModeLogin showButton />
              </div>
            )}
            <ControlList
              controls={controls}
              rtuStation={stationName}
              groupByType
              disabled={!isOnline}
              interactive={canCommand}
              onCommandSent={fetchData}
            />
          </div>
        )}

        {activeTab === 'profinet' && (
          <ProfinetStatus
            stationName={stationName}
            autoRefresh={true}
            refreshIntervalMs={5000}
          />
        )}
      </div>
    </div>
  );
}
