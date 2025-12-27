'use client';

/**
 * System Status Bar Component
 * ISA-101 compliant status bar at bottom of HMI
 *
 * Shows:
 * - PROFINET connection status
 * - WebSocket connection status
 * - Cycle time / update rate
 * - Pending writes count
 * - System health indicators
 */

import ConnectionStatusIndicator, { ConnectionState } from './ConnectionStatusIndicator';

interface SystemStatusBarProps {
  profinetStatus: ConnectionState;
  websocketStatus: ConnectionState;
  cycleTimeMs?: number;
  pendingWrites?: number;
  dataMode?: 'streaming' | 'polling' | 'disconnected';
  pollIntervalSeconds?: number;
  className?: string;
}

export default function SystemStatusBar({
  profinetStatus,
  websocketStatus,
  cycleTimeMs = 1000,
  pendingWrites = 0,
  dataMode = 'streaming',
  pollIntervalSeconds = 5,
  className = '',
}: SystemStatusBarProps) {
  const getDataModeLabel = () => {
    switch (dataMode) {
      case 'streaming':
        return 'WebSocket: Connected';
      case 'polling':
        return `Data: Polling (${pollIntervalSeconds}s)`;
      case 'disconnected':
        return 'API: UNREACHABLE';
    }
  };

  const getDataModeColor = () => {
    switch (dataMode) {
      case 'streaming':
        return 'text-alarm-green';
      case 'polling':
        return 'text-alarm-yellow';
      case 'disconnected':
        return 'text-alarm-red';
    }
  };

  return (
    <div className={`bg-hmi-panel border-t border-hmi-border px-4 py-2 ${className}`}>
      <div className="max-w-[1800px] mx-auto flex items-center justify-between gap-6 text-sm">
        {/* Left section - Connection status */}
        <div className="flex items-center gap-6">
          {/* PROFINET Status */}
          <div className="flex items-center gap-2">
            <span className="text-hmi-text-secondary">PROFINET:</span>
            <ConnectionStatusIndicator
              state={profinetStatus}
              size="sm"
              showLabel={true}
            />
          </div>

          {/* Data/WebSocket Status */}
          <div className="flex items-center gap-2">
            <span className={`font-mono ${getDataModeColor()}`}>
              {getDataModeLabel()}
            </span>
          </div>
        </div>

        {/* Center section - Cycle info */}
        <div className="flex items-center gap-6 text-hmi-text-secondary">
          <div className="flex items-center gap-2">
            <span>Cycle:</span>
            <span className="font-mono text-hmi-text">{cycleTimeMs}ms</span>
          </div>

          <div className="flex items-center gap-2">
            <span>Pending Writes:</span>
            <span className={`font-mono ${pendingWrites > 0 ? 'text-alarm-yellow' : 'text-hmi-text'}`}>
              {pendingWrites}
            </span>
          </div>
        </div>

        {/* Right section - Timestamp */}
        <div className="text-hmi-text-secondary font-mono">
          {new Date().toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
}
