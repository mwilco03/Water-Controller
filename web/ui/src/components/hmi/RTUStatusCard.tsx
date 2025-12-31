'use client';

/**
 * RTU Status Card Component
 * ISA-101 compliant RTU summary card for the landing page
 *
 * Design principles:
 * - Gray card when normal (no unnecessary color)
 * - Red accent when alarm active
 * - Gray text when offline
 * - Connection indicator uses filled/empty circle pattern
 */

import Link from 'next/link';
import ConnectionStatusIndicator, { ConnectionState, connectionStateFromRtuState } from './ConnectionStatusIndicator';
import DataQualityIndicator, { DataQuality, qualityFromCode } from './DataQualityIndicator';

export interface RTUStatusData {
  station_name: string;
  ip_address?: string;
  state: string;
  slot_count: number;
  sensor_count?: number;
  actuator_count?: number;
  last_communication?: string | Date;
  alarm_count?: number;
  has_unacknowledged_alarms?: boolean;
  healthy?: boolean;
}

interface RTUStatusCardProps {
  rtu: RTUStatusData;
  onClick?: () => void;
  className?: string;
}

export default function RTUStatusCard({
  rtu,
  onClick,
  className = '',
}: RTUStatusCardProps) {
  const connectionState = connectionStateFromRtuState(rtu.state);
  const isOnline = connectionState === 'ONLINE';
  const isOffline = connectionState === 'OFFLINE';
  const hasAlarms = (rtu.alarm_count ?? 0) > 0;
  const hasUnacknowledged = rtu.has_unacknowledged_alarms ?? false;

  // Calculate data staleness
  const getLastSeenText = () => {
    if (!rtu.last_communication) return '--';
    const lastSeen = typeof rtu.last_communication === 'string'
      ? new Date(rtu.last_communication)
      : rtu.last_communication;
    const seconds = Math.floor((Date.now() - lastSeen.getTime()) / 1000);

    if (seconds < 0) return 'Just now';
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
  };

  const isStale = () => {
    if (!rtu.last_communication || isOffline) return false;
    const lastSeen = typeof rtu.last_communication === 'string'
      ? new Date(rtu.last_communication)
      : rtu.last_communication;
    return (Date.now() - lastSeen.getTime()) / 1000 > 30;
  };

  // Card border style based on state
  const getCardBorderStyle = () => {
    if (hasUnacknowledged) return 'border-2 border-status-alarm';
    if (hasAlarms) return 'border border-status-alarm';
    if (isOffline) return 'border border-hmi-border';
    return 'border border-hmi-border';
  };

  // Text style based on state
  const getTextStyle = () => {
    if (isOffline) return 'text-hmi-offline';
    return 'text-hmi-text';
  };

  const CardContent = (
    <div
      className={`
        bg-hmi-panel rounded-lg shadow-hmi-card p-4
        ${getCardBorderStyle()}
        ${isOffline ? 'opacity-75' : ''}
        ${hasUnacknowledged ? 'animate-alarm-flash' : ''}
        transition-all duration-150
        hover:shadow-md
        ${onClick ? 'cursor-pointer' : ''}
        ${className}
      `}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => e.key === 'Enter' && onClick() : undefined}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <ConnectionStatusIndicator
            state={connectionState}
            showLabel={false}
            size="md"
          />
          <h3 className={`font-semibold truncate ${getTextStyle()}`}>
            {rtu.station_name}
          </h3>
        </div>
        <span className={`text-xs font-mono ${getTextStyle()}`}>
          {rtu.ip_address || 'No IP'}
        </span>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-2 text-center mb-3">
        <div>
          <div className={`text-lg font-bold font-mono ${isOffline ? 'text-hmi-offline' : 'text-hmi-text'}`}>
            {isOffline ? '--' : (rtu.sensor_count ?? rtu.slot_count)}
          </div>
          <div className="text-xs text-hmi-text-secondary">sensors</div>
        </div>
        <div>
          <div className={`text-lg font-bold font-mono ${isOffline ? 'text-hmi-offline' : 'text-hmi-text'}`}>
            {isOffline ? '--' : (rtu.actuator_count ?? 0)}
          </div>
          <div className="text-xs text-hmi-text-secondary">actuators</div>
        </div>
        <div>
          <div className={`text-lg font-bold font-mono ${getTextStyle()}`}>
            {getLastSeenText()}
            {isStale() && !isOffline && (
              <span className="text-status-warning ml-1">!</span>
            )}
          </div>
          <div className="text-xs text-hmi-text-secondary">last seen</div>
        </div>
      </div>

      {/* Alarm indicator */}
      <div className={`
        rounded px-2 py-1.5 text-sm flex items-center justify-between
        ${hasAlarms ? (hasUnacknowledged ? 'bg-status-alarm text-white' : 'bg-quality-bad text-status-alarm') : 'bg-hmi-bg text-hmi-muted'}
      `}>
        {hasAlarms ? (
          <>
            <span className="flex items-center gap-1">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              {rtu.alarm_count} alarm{rtu.alarm_count !== 1 ? 's' : ''}
            </span>
            {hasUnacknowledged && <span className="text-xs font-medium">UNACK</span>}
          </>
        ) : connectionState === 'OFFLINE' ? (
          <span className="flex items-center gap-1">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3m8.293 8.293l1.414 1.414" />
            </svg>
            COMM FAIL
          </span>
        ) : (
          <span>No alarms</span>
        )}
      </div>
    </div>
  );

  // Wrap in Link if no custom onClick
  if (!onClick) {
    return (
      <Link href={`/rtus/${rtu.station_name}`} className="block">
        {CardContent}
      </Link>
    );
  }

  return CardContent;
}
