'use client';

import { useMemo } from 'react';
import type { RTUSensor } from '@/lib/api';
import { QUALITY_CODES, ISA101_COLORS } from '@/constants';

interface Props {
  sensor: RTUSensor;
  size?: 'sm' | 'md' | 'lg';
  showDetails?: boolean;
}

export default function SensorDisplay({ sensor, size = 'md', showDetails = false }: Props) {
  const dimensions = useMemo(() => {
    switch (size) {
      case 'sm': return { width: 100, height: 60, fontSize: 16 };
      case 'lg': return { width: 180, height: 100, fontSize: 28 };
      default: return { width: 140, height: 80, fontSize: 22 };
    }
  }, [size]);

  /* Check quality from 5-byte sensor format */
  const isGoodQuality = sensor.last_quality === QUALITY_CODES.GOOD;
  const isUncertainQuality = sensor.last_quality === QUALITY_CODES.UNCERTAIN;
  const isBadQuality = sensor.last_quality === QUALITY_CODES.BAD;
  const isNotConnected = sensor.last_quality === QUALITY_CODES.NOT_CONNECTED;
  const value = sensor.last_value ?? null;

  /* Get quality indicator per ISA-101 */
  const getQualityIndicator = () => {
    if (isGoodQuality) return null;
    if (isUncertainQuality) return '?';  /* Uncertain */
    if (isBadQuality) return 'X';        /* Bad */
    if (isNotConnected) return '-';      /* Not connected */
    return '!';
  };

  // Get color based on sensor type and value
  const getColor = () => {
    if (!isGoodQuality) return ISA101_COLORS.quality.bad; // Red for bad quality
    if (value === null) return ISA101_COLORS.states.offline; // Gray for no data

    const percentage = (value - sensor.scale_min) / (sensor.scale_max - sensor.scale_min);

    // Type-specific coloring using ISA-101 colors
    switch (sensor.sensor_type) {
      case 'temperature':
        if (percentage > 0.9) return ISA101_COLORS.alarms.critical;
        if (percentage > 0.7) return ISA101_COLORS.alarms.medium;
        return ISA101_COLORS.quality.good;
      case 'ph':
        // pH: 6.5-8.5 is good (green), outside is warning/danger
        if (value < 6.0 || value > 9.0) return ISA101_COLORS.alarms.critical;
        if (value < 6.5 || value > 8.5) return ISA101_COLORS.alarms.medium;
        return ISA101_COLORS.quality.good;
      case 'level':
        if (percentage > 0.95 || percentage < 0.05) return ISA101_COLORS.alarms.critical;
        if (percentage > 0.85 || percentage < 0.15) return ISA101_COLORS.alarms.medium;
        return ISA101_COLORS.quality.good;
      case 'pressure':
        if (percentage > 0.9) return ISA101_COLORS.alarms.critical;
        if (percentage > 0.8) return ISA101_COLORS.alarms.medium;
        return ISA101_COLORS.quality.good;
      case 'flow':
        if (percentage < 0.05) return ISA101_COLORS.alarms.medium; // Low flow warning
        return ISA101_COLORS.quality.good;
      default:
        return ISA101_COLORS.ui.primary; // Blue for unknown types
    }
  };

  // Get label based on sensor type
  const getTypeLabel = () => {
    switch (sensor.sensor_type) {
      case 'temperature':
        return <span className="text-xs font-bold">T</span>;
      case 'ph':
        return <span className="text-xs font-bold">pH</span>;
      case 'level':
        return <span className="text-xs font-bold">L</span>;
      case 'pressure':
        return <span className="text-xs font-bold">P</span>;
      case 'flow':
        return <span className="text-xs font-bold">F</span>;
      case 'turbidity':
        return <span className="text-xs font-bold">Tu</span>;
      case 'chlorine':
        return <span className="text-xs font-bold">Cl</span>;
      case 'conductivity':
        return <span className="text-xs font-bold">EC</span>;
      case 'dissolved_oxygen':
        return <span className="text-xs font-bold">DO</span>;
      default:
        return <span className="text-xs font-bold">S</span>;
    }
  };

  const color = getColor();
  const percentage = value !== null ?
    Math.max(0, Math.min(100, ((value - sensor.scale_min) / (sensor.scale_max - sensor.scale_min)) * 100)) : 0;

  return (
    <div
      className="relative rounded-lg overflow-hidden"
      style={{
        width: dimensions.width,
        minHeight: dimensions.height,
        backgroundColor: 'rgba(15, 23, 42, 0.8)',
        border: '1px solid rgba(71, 85, 105, 0.5)',
      }}
    >
      {/* Background bar */}
      <div
        className="absolute bottom-0 left-0 right-0 transition-all duration-500"
        style={{
          height: `${percentage}%`,
          backgroundColor: `${color}20`,
          borderTop: `2px solid ${color}`,
        }}
      />

      {/* Content */}
      <div className="relative p-2 flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center gap-1 text-gray-400 mb-1">
          <span style={{ color }}>{getTypeLabel()}</span>
          <span className="text-xs truncate flex-1" title={sensor.name}>
            {sensor.name}
          </span>
          {!isGoodQuality && (
            <span
              className={`text-xs font-bold ${isUncertainQuality ? 'text-yellow-500' : 'text-red-500'}`}
              title={isUncertainQuality ? 'Uncertain quality' : isBadQuality ? 'Bad quality' : isNotConnected ? 'Not connected' : 'Unknown quality'}
            >
              {getQualityIndicator()}
            </span>
          )}
        </div>

        {/* Value */}
        <div className="flex-1 flex items-center justify-center">
          <span
            className="font-mono font-bold"
            style={{
              fontSize: dimensions.fontSize,
              color,
              textShadow: `0 0 10px ${color}40`,
            }}
          >
            {value !== null ? value.toFixed(1) : '--'}
          </span>
          <span className="ml-1 text-gray-400 text-sm">{sensor.unit}</span>
        </div>

        {/* Details */}
        {showDetails && (
          <div className="text-xs text-gray-500 mt-1 space-y-0.5">
            <div className="flex justify-between">
              <span>Range:</span>
              <span>{sensor.scale_min} - {sensor.scale_max}</span>
            </div>
            <div className="flex justify-between">
              <span>Type:</span>
              <span className="capitalize">{sensor.sensor_type}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
