'use client';

/**
 * RTU Card Component
 * ISA-101 compliant RTU summary card
 *
 * Design principles (ISA-101):
 * - Gray is normal, color is abnormal
 * - Light gray backgrounds, white panels
 * - Color only for status indication (alarms, states)
 * - High contrast text for readability
 */

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
  const stateLabel = getRtuStateLabel(rtu.state);
  const isOnline = rtu.state === 'RUNNING';
  const isOffline = rtu.state === 'STOPPED' || rtu.state === 'OFFLINE';

  // Calculate summary stats
  const activeSensors = Array.isArray(sensors) ? sensors.filter((s) => s.last_quality >= 192).length : 0;
  const activeControls = Array.isArray(controls) ? controls.filter((c) => isActiveState(c.current_state)).length : 0;

  // Get key sensor values for quick display
  const keySensors = Array.isArray(sensors) ? sensors.slice(0, 3) : [];

  // ISA-101 compliant state colors
  const getStatusDotClass = () => {
    if (isOnline) return 'bg-status-ok';
    if (isOffline) return 'bg-hmi-equipment';
    return 'bg-status-warning';
  };

  const getStatusBadgeClass = () => {
    if (isOnline) return 'bg-status-ok/10 text-status-ok';
    if (isOffline) return 'bg-hmi-bg text-hmi-muted';
    return 'bg-status-warning/10 text-status-warning';
  };

  if (compact) {
    return (
      <Link
        href={`/rtus/${rtu.station_name}`}
        className="block hmi-card p-3 transition-all hover:shadow-md"
      >
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full flex-shrink-0 ${getStatusDotClass()}`} />
          <span className="font-medium text-hmi-text flex-1 truncate">
            {rtu.station_name}
          </span>
          <span className="text-xs text-hmi-muted">{rtu.slot_count} slots</span>
        </div>
      </Link>
    );
  }

  return (
    <div className="hmi-card overflow-hidden transition-all hover:shadow-md">
      {/* Header */}
      <div className="p-4 border-b border-hmi-border">
        <div className="flex items-center gap-3">
          <div className={`w-4 h-4 rounded-full flex-shrink-0 ${getStatusDotClass()}`} />
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-hmi-text truncate">{rtu.station_name}</h3>
            <p className="text-xs text-hmi-muted font-mono">{rtu.ip_address || 'No IP'}</p>
          </div>
          <span className={`text-xs px-2 py-1 rounded font-medium ${getStatusBadgeClass()}`}>
            {stateLabel}
          </span>
        </div>
      </div>

      {/* Stats - ISA-101: gray dividers, clear numbers */}
      <div className="grid grid-cols-3 divide-x divide-hmi-border">
        <div className="p-3 text-center">
          <div className={`text-2xl font-bold font-mono ${isOffline ? 'text-hmi-muted' : 'text-hmi-text'}`}>
            {isOffline ? '--' : rtu.slot_count}
          </div>
          <div className="text-xs text-hmi-muted">Slots</div>
        </div>
        <div className="p-3 text-center">
          <div className={`text-2xl font-bold font-mono ${isOffline ? 'text-hmi-muted' : 'text-hmi-text'}`}>
            {isOffline ? '--' : activeSensors}
          </div>
          <div className="text-xs text-hmi-muted">Sensors</div>
        </div>
        <div className="p-3 text-center">
          <div className={`text-2xl font-bold font-mono ${isOffline ? 'text-hmi-muted' : 'text-hmi-text'}`}>
            {isOffline ? '--' : activeControls}
          </div>
          <div className="text-xs text-hmi-muted">Active</div>
        </div>
      </div>

      {/* Key Sensors Preview - ISA-101: subtle background, clear values */}
      {keySensors.length > 0 && (
        <div className="p-3 border-t border-hmi-border bg-hmi-bg">
          <div className="flex flex-wrap gap-2">
            {keySensors.map((sensor) => (
              <div
                key={sensor.id}
                className="flex items-center gap-1 px-2 py-1 rounded bg-hmi-panel border border-hmi-border text-xs"
              >
                <span className="text-hmi-muted">{sensor.name}:</span>
                <span className="font-mono text-hmi-text font-medium">
                  {sensor.last_value?.toFixed(1) ?? '--'}
                </span>
                <span className="text-hmi-muted">{sensor.unit}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Footer - ISA-101: clear action buttons */}
      <div className="p-3 border-t border-hmi-border flex gap-2">
        <Link
          href={`/rtus/${rtu.station_name}`}
          className="flex-1 text-center text-sm py-2 rounded bg-status-info hover:bg-status-info/90 text-white font-medium transition-colors"
        >
          Details
        </Link>
        <Link
          href={`/trends?rtu=${rtu.station_name}`}
          className="flex-1 text-center text-sm py-2 rounded bg-hmi-bg hover:bg-hmi-border text-hmi-text font-medium transition-colors border border-hmi-border"
        >
          Trends
        </Link>
      </div>
    </div>
  );
}
