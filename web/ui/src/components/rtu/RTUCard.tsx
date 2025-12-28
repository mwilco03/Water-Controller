'use client';

import Link from 'next/link';
import type { RTUSensor, RTUControl } from '@/lib/api';
import { getStateColor, getRtuStateLabel, isActiveState } from '@/constants';

// Minimal RTU info needed for the card
interface RTUInfo {
  station_name: string;
  ip_address?: string;
  state: string;
  slot_count: number;
  vendor_id?: number;
  device_id?: number;
}

interface Props {
  rtu: RTUInfo;
  sensors?: RTUSensor[];
  controls?: RTUControl[];
  compact?: boolean;
}

export default function RTUCard({ rtu, sensors = [], controls = [], compact = false }: Props) {
  const stateColor = getStateColor(rtu.state);
  const stateLabel = getRtuStateLabel(rtu.state);
  const isOnline = rtu.state === 'RUNNING';

  // Calculate summary stats
  const activeSensors = sensors.filter((s) => s.last_quality >= 192).length;
  const activeControls = controls.filter((c) => isActiveState(c.current_state)).length;

  // Get key sensor values for quick display
  const keySensors = sensors.slice(0, 3);

  if (compact) {
    return (
      <Link
        href={`/rtus/${rtu.station_name}`}
        className="block rounded-lg p-3 transition-all hover:scale-[1.02]"
        style={{
          backgroundColor: 'rgba(15, 23, 42, 0.8)',
          border: `1px solid ${stateColor}40`,
          boxShadow: isOnline ? `0 0 20px ${stateColor}15` : 'none',
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-3 h-3 rounded-full animate-pulse"
            style={{ backgroundColor: stateColor }}
          />
          <span className="font-medium text-white flex-1 truncate">
            {rtu.station_name}
          </span>
          <span className="text-xs text-gray-400">{rtu.slot_count} slots</span>
        </div>
      </Link>
    );
  }

  return (
    <div
      className="rounded-lg overflow-hidden transition-all hover:scale-[1.01]"
      style={{
        backgroundColor: 'rgba(15, 23, 42, 0.9)',
        border: `1px solid ${stateColor}40`,
        boxShadow: isOnline ? `0 0 30px ${stateColor}10` : 'none',
      }}
    >
      {/* Header */}
      <div
        className="p-4 flex items-center gap-3"
        style={{ borderBottom: `1px solid ${stateColor}30` }}
      >
        <div
          className="w-4 h-4 rounded-full flex-shrink-0"
          style={{
            backgroundColor: stateColor,
            boxShadow: `0 0 10px ${stateColor}`,
            animation: isOnline ? 'pulse 2s infinite' : 'none',
          }}
        />
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-white truncate">{rtu.station_name}</h3>
          <p className="text-xs text-gray-400 font-mono">{rtu.ip_address || 'No IP'}</p>
        </div>
        <span
          className="text-xs px-2 py-1 rounded"
          style={{
            backgroundColor: `${stateColor}20`,
            color: stateColor,
          }}
        >
          {stateLabel}
        </span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 divide-x divide-gray-700/50">
        <div className="p-3 text-center">
          <div className="text-2xl font-bold text-white">{rtu.slot_count}</div>
          <div className="text-xs text-gray-400">Slots</div>
        </div>
        <div className="p-3 text-center">
          <div className="text-2xl font-bold text-green-400">{activeSensors}</div>
          <div className="text-xs text-gray-400">Sensors</div>
        </div>
        <div className="p-3 text-center">
          <div className="text-2xl font-bold text-blue-400">{activeControls}</div>
          <div className="text-xs text-gray-400">Active</div>
        </div>
      </div>

      {/* Key Sensors Preview */}
      {keySensors.length > 0 && (
        <div className="p-3 border-t border-gray-700/50">
          <div className="flex flex-wrap gap-2">
            {keySensors.map((sensor) => (
              <div
                key={sensor.id}
                className="flex items-center gap-1 px-2 py-1 rounded bg-gray-800/50 text-xs"
              >
                <span className="text-gray-400">{sensor.name}:</span>
                <span className="font-mono text-white">
                  {sensor.last_value?.toFixed(1) ?? '--'}
                </span>
                <span className="text-gray-500">{sensor.unit}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="p-3 border-t border-gray-700/50 flex gap-2">
        <Link
          href={`/rtus/${rtu.station_name}`}
          className="flex-1 text-center text-sm py-2 rounded bg-blue-600 hover:bg-blue-500 text-white transition-colors"
        >
          Details
        </Link>
        <Link
          href={`/trends?rtu=${rtu.station_name}`}
          className="flex-1 text-center text-sm py-2 rounded bg-gray-700 hover:bg-gray-600 text-white transition-colors"
        >
          Trends
        </Link>
      </div>
    </div>
  );
}
