'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

interface DiagnosticAlarm {
  code: number;
  slot: number;
  subslot: number;
  channel: number;
  severity: 'info' | 'warning' | 'error' | 'fault';
  message: string;
  timestamp: string;
  active: boolean;
}

interface ModuleStatus {
  slot: number;
  subslot: number;
  module_type: string;
  module_state: 'OK' | 'SUBSTITUTE' | 'WRONG' | 'NO_MODULE' | 'DISABLED';
  ident_number: number;
  io_data_length: number;
  input_length: number;
  output_length: number;
  last_error?: string;
}

interface CycleTimeStats {
  current_ms: number;
  min_ms: number;
  max_ms: number;
  avg_ms: number;
  jitter_ms: number;
  overruns: number;
  target_ms: number;
}

interface IOStats {
  input_bytes: number;
  output_bytes: number;
  frames_sent: number;
  frames_received: number;
  frames_missed: number;
  crc_errors: number;
  sequence_errors: number;
}

interface ARStatus {
  ar_handle: number;
  ar_type: string;
  ar_state: 'OFFLINE' | 'CONNECT' | 'READ' | 'ONLINE' | 'DATA';
  session_uuid: string;
  device_mac: string;
  device_ip: string;
  controller_mac: string;
  controller_ip: string;
  established_at: string;
  last_activity: string;
}

interface ProfinetDiagnostics {
  ar_status: ARStatus;
  cycle_stats: CycleTimeStats;
  io_stats: IOStats;
  modules: ModuleStatus[];
  alarms: DiagnosticAlarm[];
  device_info: {
    vendor_name: string;
    device_name: string;
    order_id: string;
    serial_number: string;
    hw_revision: string;
    sw_revision: string;
    profinet_version: string;
  };
}

interface Props {
  stationName: string;
  onClose?: () => void;
}

const moduleStateColors = {
  OK: { bg: 'bg-green-600/20', text: 'text-green-400', border: 'border-green-500' },
  SUBSTITUTE: { bg: 'bg-yellow-600/20', text: 'text-yellow-400', border: 'border-yellow-500' },
  WRONG: { bg: 'bg-red-600/20', text: 'text-red-400', border: 'border-red-500' },
  NO_MODULE: { bg: 'bg-gray-600/20', text: 'text-gray-400', border: 'border-gray-500' },
  DISABLED: { bg: 'bg-gray-600/20', text: 'text-gray-500', border: 'border-gray-600' },
};

const severityConfig = {
  info: { color: 'text-blue-400', bg: 'bg-blue-600/20', icon: 'ℹ' },
  warning: { color: 'text-yellow-400', bg: 'bg-yellow-600/20', icon: '⚠' },
  error: { color: 'text-orange-400', bg: 'bg-orange-600/20', icon: '⛔' },
  fault: { color: 'text-red-400', bg: 'bg-red-600/20', icon: '🔴' },
};

export default function ProfinetDiagnosticsPanel({ stationName, onClose }: Props) {
  const [diagnostics, setDiagnostics] = useState<ProfinetDiagnostics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'modules' | 'alarms' | 'stats'>('overview');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchDiagnostics = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch(
        `/api/v1/rtus/${encodeURIComponent(stationName)}/profinet/diagnostics`,
        { signal }
      );

      if (signal?.aborted) return;

      if (res.ok) {
        const data = await res.json();
        setDiagnostics(data);
        setError(null);
      } else if (res.status === 404) {
        // Use mock data only in development
        if (process.env.NODE_ENV === 'development') {
          console.warn('[DEV] Diagnostics API unavailable, using mock data');
          setDiagnostics(getMockDiagnostics(stationName));
          setError(null);
        } else {
          setError('Diagnostics not available for this device');
        }
      } else {
        setError('Failed to load diagnostics');
      }
    } catch (err) {
      // Ignore abort errors
      if (err instanceof Error && err.name === 'AbortError') return;

      // Use mock data only in development
      if (process.env.NODE_ENV === 'development') {
        console.warn('[DEV] Diagnostics API unavailable, using mock data');
        setDiagnostics(getMockDiagnostics(stationName));
        setError(null);
      } else {
        setError('Failed to load diagnostics. Check network connection.');
      }
    } finally {
      setLoading(false);
    }
  }, [stationName]);

  useEffect(() => {
    const controller = new AbortController();
    abortControllerRef.current = controller;

    fetchDiagnostics(controller.signal);

    let interval: NodeJS.Timeout | undefined;
    if (autoRefresh) {
      interval = setInterval(() => {
        fetchDiagnostics(controller.signal);
      }, 2000);
    }

    return () => {
      controller.abort();
      if (interval) clearInterval(interval);
    };
  }, [fetchDiagnostics, autoRefresh]);

  const formatUptime = (startTime: string): string => {
    const start = new Date(startTime);
    const now = new Date();
    const diffMs = now.getTime() - start.getTime();

    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((diffMs % (1000 * 60)) / 1000);

    return `${hours}h ${minutes}m ${seconds}s`;
  };

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <svg className="animate-spin h-8 w-8 text-blue-400" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    );
  }

  if (error || !diagnostics) {
    return (
      <div className="p-6 text-center">
        <p className="text-red-400">{error || 'No diagnostics available'}</p>
        <button onClick={() => fetchDiagnostics()} className="mt-4 px-4 py-2 bg-blue-600 rounded text-white">
          Retry
        </button>
      </div>
    );
  }

  const { ar_status, cycle_stats, io_stats, modules, alarms, device_info } = diagnostics;
  const activeAlarms = alarms.filter(a => a.active);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${ar_status.ar_state === 'DATA' ? 'bg-green-400' : ar_status.ar_state === 'ONLINE' ? 'bg-yellow-400 animate-pulse' : 'bg-gray-400'}`} />
          <h2 className="text-xl font-semibold text-white">PROFINET Diagnostics</h2>
          <span className="text-sm text-gray-400">- {stationName}</span>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-400">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded"
            />
            Auto-refresh
          </label>
          <button
            onClick={() => fetchDiagnostics()}
            className="p-2 rounded bg-gray-700 hover:bg-gray-600 text-gray-300"
            aria-label="Refresh diagnostics"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
          {onClose && (
            <button onClick={onClose} className="p-2 rounded bg-gray-700 hover:bg-gray-600 text-gray-300">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-700">
        {(['overview', 'modules', 'alarms', 'stats'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${
              activeTab === tab
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            {tab}
            {tab === 'alarms' && activeAlarms.length > 0 && (
              <span className="ml-2 px-1.5 py-0.5 text-xs bg-red-600 rounded-full">
                {activeAlarms.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="min-h-[400px]">
        {activeTab === 'overview' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Device Info */}
            <div className="bg-gray-800/50 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-400 mb-3">Device Information</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Vendor</span>
                  <span className="text-white">{device_info.vendor_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Device</span>
                  <span className="text-white">{device_info.device_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Order ID</span>
                  <span className="text-white font-mono">{device_info.order_id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Serial</span>
                  <span className="text-white font-mono">{device_info.serial_number}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">HW Rev</span>
                  <span className="text-white">{device_info.hw_revision}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">SW Rev</span>
                  <span className="text-white">{device_info.sw_revision}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">PN Version</span>
                  <span className="text-white">{device_info.profinet_version}</span>
                </div>
              </div>
            </div>

            {/* AR Status */}
            <div className="bg-gray-800/50 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-400 mb-3">Application Relationship</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">AR State</span>
                  <span className={`font-medium ${ar_status.ar_state === 'DATA' ? 'text-green-400' : 'text-yellow-400'}`}>
                    {ar_status.ar_state}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">AR Handle</span>
                  <span className="text-white font-mono">0x{ar_status.ar_handle.toString(16).toUpperCase()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Device IP</span>
                  <span className="text-white font-mono">{ar_status.device_ip}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Device MAC</span>
                  <span className="text-white font-mono">{ar_status.device_mac}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Controller IP</span>
                  <span className="text-white font-mono">{ar_status.controller_ip}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Uptime</span>
                  <span className="text-white">{formatUptime(ar_status.established_at)}</span>
                </div>
              </div>
            </div>

            {/* Cycle Time Performance */}
            <div className="bg-gray-800/50 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-400 mb-3">Cycle Time Performance</h3>
              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-400">Current</span>
                    <span className={`font-mono ${cycle_stats.current_ms <= cycle_stats.target_ms ? 'text-green-400' : 'text-red-400'}`}>
                      {cycle_stats.current_ms.toFixed(2)} ms
                    </span>
                  </div>
                  <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all ${cycle_stats.current_ms <= cycle_stats.target_ms ? 'bg-green-500' : 'bg-red-500'}`}
                      style={{ width: `${Math.min(100, (cycle_stats.current_ms / cycle_stats.target_ms) * 100)}%` }}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center text-sm">
                  <div className="bg-gray-700/50 rounded p-2">
                    <div className="text-gray-400 text-xs">Min</div>
                    <div className="text-white font-mono">{cycle_stats.min_ms.toFixed(2)}</div>
                  </div>
                  <div className="bg-gray-700/50 rounded p-2">
                    <div className="text-gray-400 text-xs">Avg</div>
                    <div className="text-white font-mono">{cycle_stats.avg_ms.toFixed(2)}</div>
                  </div>
                  <div className="bg-gray-700/50 rounded p-2">
                    <div className="text-gray-400 text-xs">Max</div>
                    <div className="text-white font-mono">{cycle_stats.max_ms.toFixed(2)}</div>
                  </div>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Jitter</span>
                  <span className="text-white font-mono">{cycle_stats.jitter_ms.toFixed(3)} ms</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Overruns</span>
                  <span className={`font-mono ${cycle_stats.overruns > 0 ? 'text-yellow-400' : 'text-green-400'}`}>
                    {cycle_stats.overruns}
                  </span>
                </div>
              </div>
            </div>

            {/* I/O Statistics */}
            <div className="bg-gray-800/50 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-400 mb-3">I/O Statistics</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Input Bytes</span>
                  <span className="text-white font-mono">{io_stats.input_bytes}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Output Bytes</span>
                  <span className="text-white font-mono">{io_stats.output_bytes}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Frames Sent</span>
                  <span className="text-white font-mono">{io_stats.frames_sent.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Frames Received</span>
                  <span className="text-white font-mono">{io_stats.frames_received.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Frames Missed</span>
                  <span className={`font-mono ${io_stats.frames_missed > 0 ? 'text-yellow-400' : 'text-green-400'}`}>
                    {io_stats.frames_missed}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">CRC Errors</span>
                  <span className={`font-mono ${io_stats.crc_errors > 0 ? 'text-red-400' : 'text-green-400'}`}>
                    {io_stats.crc_errors}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'modules' && (
          <div className="space-y-3">
            {modules.map((module) => {
              const stateConfig = moduleStateColors[module.module_state];
              return (
                <div
                  key={`${module.slot}-${module.subslot}`}
                  className={`${stateConfig.bg} border ${stateConfig.border} rounded-lg p-4`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <span className="text-white font-medium">
                        Slot {module.slot}.{module.subslot}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded ${stateConfig.bg} ${stateConfig.text}`}>
                        {module.module_state}
                      </span>
                    </div>
                    <span className="text-gray-400 text-sm font-mono">
                      ID: 0x{module.ident_number.toString(16).toUpperCase().padStart(8, '0')}
                    </span>
                  </div>
                  <div className="text-sm text-gray-300 mb-2">{module.module_type}</div>
                  <div className="grid grid-cols-3 gap-4 text-xs">
                    <div>
                      <span className="text-gray-500">I/O Data</span>
                      <span className="text-gray-300 ml-2">{module.io_data_length} bytes</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Input</span>
                      <span className="text-green-400 ml-2">{module.input_length} bytes</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Output</span>
                      <span className="text-blue-400 ml-2">{module.output_length} bytes</span>
                    </div>
                  </div>
                  {module.last_error && (
                    <div className="mt-2 text-xs text-red-400">
                      Last Error: {module.last_error}
                    </div>
                  )}
                </div>
              );
            })}
            {modules.length === 0 && (
              <div className="text-center py-8 text-gray-400">No modules configured</div>
            )}
          </div>
        )}

        {activeTab === 'alarms' && (
          <div className="space-y-3">
            {alarms.length === 0 ? (
              <div className="text-center py-8 text-gray-400">No diagnostic alarms</div>
            ) : (
              alarms.map((alarm, index) => {
                const config = severityConfig[alarm.severity];
                return (
                  <div
                    key={index}
                    className={`${config.bg} rounded-lg p-4 ${!alarm.active ? 'opacity-50' : ''}`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-lg">{config.icon}</span>
                        <div>
                          <div className={`font-medium ${config.color}`}>
                            Alarm Code 0x{alarm.code.toString(16).toUpperCase()}
                          </div>
                          <div className="text-sm text-gray-300">{alarm.message}</div>
                          <div className="text-xs text-gray-500 mt-1">
                            Slot {alarm.slot}.{alarm.subslot} Channel {alarm.channel}
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`text-xs ${alarm.active ? 'text-red-400' : 'text-gray-500'}`}>
                          {alarm.active ? 'ACTIVE' : 'CLEARED'}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          {new Date(alarm.timestamp).toLocaleString()}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {activeTab === 'stats' && (
          <div className="space-y-4">
            {/* Frame Statistics Chart */}
            <div className="bg-gray-800/50 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-400 mb-4">Frame Statistics</h3>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-400">Sent</span>
                    <span className="text-green-400 font-mono">{io_stats.frames_sent.toLocaleString()}</span>
                  </div>
                  <div className="h-4 bg-gray-700 rounded-full overflow-hidden">
                    <div className="h-full bg-green-500" style={{ width: '100%' }} />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-400">Received</span>
                    <span className="text-blue-400 font-mono">{io_stats.frames_received.toLocaleString()}</span>
                  </div>
                  <div className="h-4 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500"
                      style={{ width: `${(io_stats.frames_received / io_stats.frames_sent) * 100}%` }}
                    />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-400">Missed</span>
                    <span className="text-yellow-400 font-mono">{io_stats.frames_missed}</span>
                  </div>
                  <div className="h-4 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-yellow-500"
                      style={{ width: `${Math.min(100, (io_stats.frames_missed / io_stats.frames_sent) * 10000)}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Error Summary */}
            <div className="bg-gray-800/50 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-400 mb-3">Error Summary</h3>
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-4 bg-gray-700/50 rounded-lg">
                  <div className={`text-2xl font-bold ${io_stats.crc_errors > 0 ? 'text-red-400' : 'text-green-400'}`}>
                    {io_stats.crc_errors}
                  </div>
                  <div className="text-xs text-gray-400 mt-1">CRC Errors</div>
                </div>
                <div className="text-center p-4 bg-gray-700/50 rounded-lg">
                  <div className={`text-2xl font-bold ${io_stats.sequence_errors > 0 ? 'text-red-400' : 'text-green-400'}`}>
                    {io_stats.sequence_errors}
                  </div>
                  <div className="text-xs text-gray-400 mt-1">Sequence Errors</div>
                </div>
                <div className="text-center p-4 bg-gray-700/50 rounded-lg">
                  <div className={`text-2xl font-bold ${cycle_stats.overruns > 0 ? 'text-yellow-400' : 'text-green-400'}`}>
                    {cycle_stats.overruns}
                  </div>
                  <div className="text-xs text-gray-400 mt-1">Cycle Overruns</div>
                </div>
              </div>
            </div>

            {/* Quality Metrics */}
            <div className="bg-gray-800/50 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-400 mb-3">Quality Metrics</h3>
              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-400">Frame Delivery Rate</span>
                    <span className="text-white">
                      {((io_stats.frames_received / io_stats.frames_sent) * 100).toFixed(4)}%
                    </span>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-400">Error Rate</span>
                    <span className="text-white">
                      {(((io_stats.crc_errors + io_stats.sequence_errors) / io_stats.frames_received) * 100).toFixed(6)}%
                    </span>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-400">Cycle Time Stability</span>
                    <span className="text-white">
                      {(100 - (cycle_stats.jitter_ms / cycle_stats.target_ms) * 100).toFixed(2)}%
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Mock data for demonstration
function getMockDiagnostics(stationName: string): ProfinetDiagnostics {
  return {
    ar_status: {
      ar_handle: 0x0001,
      ar_type: 'IOCARSingle',
      ar_state: 'DATA',
      session_uuid: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      device_mac: '00:0E:8C:12:34:56',
      device_ip: '192.168.1.100',
      controller_mac: '00:0E:8C:AB:CD:EF',
      controller_ip: '192.168.1.1',
      established_at: new Date(Date.now() - 3600000).toISOString(),
      last_activity: new Date().toISOString(),
    },
    cycle_stats: {
      current_ms: 31.25 + (Math.random() - 0.5) * 2,
      min_ms: 30.8,
      max_ms: 33.2,
      avg_ms: 31.25,
      jitter_ms: 0.15 + Math.random() * 0.1,
      overruns: Math.floor(Math.random() * 3),
      target_ms: 32,
    },
    io_stats: {
      input_bytes: 128,
      output_bytes: 64,
      frames_sent: 115200 + Math.floor(Math.random() * 100),
      frames_received: 115198 + Math.floor(Math.random() * 100),
      frames_missed: Math.floor(Math.random() * 5),
      crc_errors: 0,
      sequence_errors: 0,
    },
    modules: [
      {
        slot: 1,
        subslot: 1,
        module_type: 'ET 200SP AI 8xI 2/4-wire High Speed',
        module_state: 'OK',
        ident_number: 0x00000032,
        io_data_length: 16,
        input_length: 16,
        output_length: 0,
      },
      {
        slot: 2,
        subslot: 1,
        module_type: 'ET 200SP DI 16x24VDC Standard',
        module_state: 'OK',
        ident_number: 0x00000021,
        io_data_length: 2,
        input_length: 2,
        output_length: 0,
      },
      {
        slot: 3,
        subslot: 1,
        module_type: 'ET 200SP DQ 16x24VDC/0.5A Standard',
        module_state: 'OK',
        ident_number: 0x00000022,
        io_data_length: 2,
        input_length: 0,
        output_length: 2,
      },
      {
        slot: 4,
        subslot: 1,
        module_type: 'ET 200SP AQ 4xU/I Standard',
        module_state: 'SUBSTITUTE',
        ident_number: 0x00000041,
        io_data_length: 8,
        input_length: 0,
        output_length: 8,
        last_error: 'Module substituted - original module replaced',
      },
    ],
    alarms: [
      {
        code: 0x8000,
        slot: 4,
        subslot: 1,
        channel: 0,
        severity: 'warning',
        message: 'Module substituted',
        timestamp: new Date(Date.now() - 1800000).toISOString(),
        active: true,
      },
      {
        code: 0x0001,
        slot: 1,
        subslot: 1,
        channel: 3,
        severity: 'info',
        message: 'Wire break detected on channel 3',
        timestamp: new Date(Date.now() - 7200000).toISOString(),
        active: false,
      },
    ],
    device_info: {
      vendor_name: 'Siemens AG',
      device_name: `ET 200SP ${stationName}`,
      order_id: '6ES7155-6AU01-0BN0',
      serial_number: 'S C-J4K123456789',
      hw_revision: 'V3.0',
      sw_revision: 'V2.9.3',
      profinet_version: 'V2.35',
    },
  };
}
