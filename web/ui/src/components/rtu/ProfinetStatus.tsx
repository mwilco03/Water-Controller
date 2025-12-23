'use client';

import { useState, useEffect, useCallback } from 'react';
import StaleIndicator from './StaleIndicator';

interface ProfinetStatusData {
  ar_handle: string;
  uptime_seconds: number;
  session_seconds: number;
  cycle_time_target_ms: number;
  cycle_time_actual_ms: number;
  packet_loss_percent: number;
  jitter_ms: number;
  last_error: string | null;
  input_bytes: number;
  output_bytes: number;
  last_io_update: string;
  data_quality: 'GOOD' | 'UNCERTAIN' | 'BAD' | 'NOT_CONNECTED';
}

interface Props {
  stationName: string;
  autoRefresh?: boolean;
  refreshIntervalMs?: number;
}

function formatDuration(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);

  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

function getQualityConfig(quality: ProfinetStatusData['data_quality']) {
  const configs = {
    GOOD: {
      color: '#10b981',
      bgColor: 'rgba(16, 185, 129, 0.15)',
      label: 'GOOD',
      percentage: 100,
    },
    UNCERTAIN: {
      color: '#f59e0b',
      bgColor: 'rgba(245, 158, 11, 0.15)',
      label: 'UNCERTAIN',
      percentage: 50,
    },
    BAD: {
      color: '#ef4444',
      bgColor: 'rgba(239, 68, 68, 0.15)',
      label: 'BAD',
      percentage: 25,
    },
    NOT_CONNECTED: {
      color: '#6b7280',
      bgColor: 'rgba(107, 114, 128, 0.15)',
      label: 'NOT CONNECTED',
      percentage: 0,
    },
  };

  return configs[quality] || configs.NOT_CONNECTED;
}

export default function ProfinetStatus({
  stationName,
  autoRefresh = true,
  refreshIntervalMs = 5000,
}: Props) {
  const [status, setStatus] = useState<ProfinetStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/rtus/${encodeURIComponent(stationName)}/profinet/status`);

      if (res.ok) {
        const data = await res.json();
        setStatus(data);
        setError(null);
        setLastFetch(new Date().toISOString());
      } else if (res.status === 404) {
        setError('PROFINET status not available');
        setStatus(null);
      } else {
        setError('Failed to fetch status');
      }
    } catch (err) {
      setError('Unable to reach server');
    } finally {
      setLoading(false);
    }
  }, [stationName]);

  // Initial fetch
  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(fetchStatus, refreshIntervalMs);
    return () => clearInterval(interval);
  }, [autoRefresh, refreshIntervalMs, fetchStatus]);

  const qualityConfig = status ? getQualityConfig(status.data_quality) : getQualityConfig('NOT_CONNECTED');

  // Quality bar segments (10 segments)
  const qualitySegments = 10;
  const filledSegments = Math.round((qualityConfig.percentage / 100) * qualitySegments);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">PROFINET Status</h3>
        </div>
        <div className="flex items-center gap-3 p-4 bg-gray-800/50 rounded-lg">
          <svg className="animate-spin h-5 w-5 text-blue-400" viewBox="0 0 24 24">
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
              fill="none"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span className="text-gray-400">Loading PROFINET status...</span>
        </div>
      </div>
    );
  }

  if (error && !status) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">PROFINET Status</h3>
          <button
            onClick={fetchStatus}
            className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
          >
            Retry
          </button>
        </div>
        <div className="p-4 bg-gray-800/50 rounded-lg border border-gray-700">
          <p className="text-gray-400">{error}</p>
        </div>
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">PROFINET Status</h3>
        <div className="flex items-center gap-3">
          <StaleIndicator
            lastUpdated={lastFetch}
            thresholds={{ warning: 10000, critical: 30000 }}
            size="sm"
            variant="badge"
          />
          <button
            onClick={fetchStatus}
            className="text-sm text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* Connection Health Card */}
      <div className="bg-gray-800/50 rounded-lg border border-gray-700 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700/50">
          <span className="text-white font-medium">PROFINET Connection</span>
          <span
            className="px-2 py-1 rounded text-xs font-medium"
            style={{
              backgroundColor: status.data_quality === 'GOOD' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
              color: status.data_quality === 'GOOD' ? '#10b981' : '#ef4444',
            }}
          >
            {status.data_quality === 'GOOD' ? 'RUNNING' : status.data_quality}
          </span>
        </div>
        <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="text-xs text-gray-400 mb-1">AR Handle</div>
            <div className="text-white font-mono text-sm">{status.ar_handle}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400 mb-1">Uptime</div>
            <div className="text-white font-mono text-sm">{formatDuration(status.uptime_seconds)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400 mb-1">Session Time</div>
            <div className="text-white font-mono text-sm">{formatDuration(status.session_seconds)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400 mb-1">Cycle Time</div>
            <div className="text-white font-mono text-sm">
              <span className={status.cycle_time_actual_ms > status.cycle_time_target_ms ? 'text-amber-400' : ''}>
                {status.cycle_time_actual_ms.toFixed(1)}
              </span>
              <span className="text-gray-500">/{status.cycle_time_target_ms}</span>
              <span className="text-gray-500">ms</span>
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-400 mb-1">Packet Loss</div>
            <div className={`font-mono text-sm ${status.packet_loss_percent > 1 ? 'text-amber-400' : 'text-white'}`}>
              {status.packet_loss_percent.toFixed(2)}%
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-400 mb-1">Jitter</div>
            <div className={`font-mono text-sm ${status.jitter_ms > 1 ? 'text-amber-400' : 'text-white'}`}>
              {status.jitter_ms.toFixed(2)}ms
            </div>
          </div>
          <div className="col-span-2">
            <div className="text-xs text-gray-400 mb-1">Last Error</div>
            <div className={`text-sm ${status.last_error ? 'text-red-400' : 'text-gray-500'}`}>
              {status.last_error || 'None'}
            </div>
          </div>
        </div>
      </div>

      {/* I/O Data Card */}
      <div className="bg-gray-800/50 rounded-lg border border-gray-700 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-700/50">
          <span className="text-white font-medium">I/O Status</span>
        </div>
        <div className="p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div>
              <div className="text-xs text-gray-400 mb-1">Input Bytes</div>
              <div className="text-white font-mono text-sm">{status.input_bytes}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">Output Bytes</div>
              <div className="text-white font-mono text-sm">{status.output_bytes}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">Last Update</div>
              <div className="text-white text-sm">
                <StaleIndicator
                  lastUpdated={status.last_io_update}
                  size="xs"
                  variant="text"
                />
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">Quality</div>
              <div className="text-sm" style={{ color: qualityConfig.color }}>
                {qualityConfig.label}
              </div>
            </div>
          </div>

          {/* Quality Bar */}
          <div>
            <div className="text-xs text-gray-400 mb-2">Data Quality</div>
            <div className="flex items-center gap-2">
              <div className="flex gap-0.5 flex-1">
                {Array.from({ length: qualitySegments }).map((_, i) => (
                  <div
                    key={i}
                    className="h-3 flex-1 rounded-sm"
                    style={{
                      backgroundColor: i < filledSegments ? qualityConfig.color : 'rgba(107, 114, 128, 0.3)',
                    }}
                  />
                ))}
              </div>
              <span className="text-sm font-medium" style={{ color: qualityConfig.color }}>
                {qualityConfig.label}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
