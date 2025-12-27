'use client';

/**
 * Connection Status Indicator Component
 * ISA-101 compliant connection state display
 *
 * Uses filled/empty circle pattern (not traffic light)
 * - Filled green: Online/Connected
 * - Filled yellow: Connecting/Degraded
 * - Filled red: Error
 * - Empty/hollow gray: Offline/Disconnected
 */

export type ConnectionState = 'ONLINE' | 'CONNECTING' | 'DEGRADED' | 'ERROR' | 'OFFLINE';

interface ConnectionStatusIndicatorProps {
  state: ConnectionState;
  label?: string;
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

// Map RTU states to connection states
export function connectionStateFromRtuState(rtuState: string): ConnectionState {
  switch (rtuState?.toUpperCase()) {
    case 'RUNNING':
      return 'ONLINE';
    case 'CONNECTING':
    case 'DISCOVERY':
      return 'CONNECTING';
    case 'DEGRADED':
      return 'DEGRADED';
    case 'ERROR':
      return 'ERROR';
    default:
      return 'OFFLINE';
  }
}

export default function ConnectionStatusIndicator({
  state,
  label,
  showLabel = true,
  size = 'md',
  className = '',
}: ConnectionStatusIndicatorProps) {
  const sizeClasses = {
    sm: 'w-2 h-2',
    md: 'w-3 h-3',
    lg: 'w-4 h-4',
  };

  const labelSizes = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base',
  };

  const getIndicatorStyle = () => {
    switch (state) {
      case 'ONLINE':
        return {
          backgroundColor: '#388E3C', // alarm-green
          border: 'none',
        };
      case 'CONNECTING':
        return {
          backgroundColor: '#FFA000', // alarm-yellow
          border: 'none',
        };
      case 'DEGRADED':
        return {
          backgroundColor: '#FFA000', // alarm-yellow
          border: 'none',
        };
      case 'ERROR':
        return {
          backgroundColor: '#D32F2F', // alarm-red
          border: 'none',
        };
      case 'OFFLINE':
      default:
        return {
          backgroundColor: 'transparent',
          border: '2px solid #9E9E9E', // hmi-offline
        };
    }
  };

  const getLabel = () => {
    if (label) return label;
    switch (state) {
      case 'ONLINE':
        return 'Online';
      case 'CONNECTING':
        return 'Connecting...';
      case 'DEGRADED':
        return 'Degraded';
      case 'ERROR':
        return 'Error';
      case 'OFFLINE':
      default:
        return 'Offline';
    }
  };

  const getLabelColor = () => {
    switch (state) {
      case 'ONLINE':
        return 'text-alarm-green';
      case 'CONNECTING':
      case 'DEGRADED':
        return 'text-alarm-yellow';
      case 'ERROR':
        return 'text-alarm-red';
      case 'OFFLINE':
      default:
        return 'text-hmi-offline';
    }
  };

  const indicatorStyle = getIndicatorStyle();

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div
        className={`${sizeClasses[size]} rounded-full flex-shrink-0`}
        style={indicatorStyle}
        role="status"
        aria-label={getLabel()}
      />
      {showLabel && (
        <span className={`${labelSizes[size]} font-medium ${getLabelColor()}`}>
          {getLabel()}
        </span>
      )}
    </div>
  );
}
