'use client';

import { useMemo } from 'react';
import type { RTUSensor } from '@/lib/api';

interface Props {
  sensor: RTUSensor;
  size?: 'sm' | 'md' | 'lg';
  showDetails?: boolean;
}

// Quality code constants (OPC UA compatible)
const QUALITY_GOOD = 192;
const QUALITY_BAD = 0;

export default function SensorDisplay({ sensor, size = 'md', showDetails = false }: Props) {
  const dimensions = useMemo(() => {
    switch (size) {
      case 'sm': return { width: 100, height: 60, fontSize: 16 };
      case 'lg': return { width: 180, height: 100, fontSize: 28 };
      default: return { width: 140, height: 80, fontSize: 22 };
    }
  }, [size]);

  const isGoodQuality = sensor.last_quality >= QUALITY_GOOD;
  const value = sensor.last_value ?? null;

  // Get color based on sensor type and value
  const getColor = () => {
    if (!isGoodQuality) return '#ef4444'; // Red for bad quality
    if (value === null) return '#6b7280'; // Gray for no data

    const percentage = (value - sensor.scale_min) / (sensor.scale_max - sensor.scale_min);

    // Type-specific coloring
    switch (sensor.sensor_type) {
      case 'temperature':
        if (percentage > 0.9) return '#ef4444';
        if (percentage > 0.7) return '#f59e0b';
        return '#10b981';
      case 'ph':
        // pH: 6.5-8.5 is good (green), outside is warning/danger
        if (value < 6.0 || value > 9.0) return '#ef4444';
        if (value < 6.5 || value > 8.5) return '#f59e0b';
        return '#10b981';
      case 'level':
        if (percentage > 0.95 || percentage < 0.05) return '#ef4444';
        if (percentage > 0.85 || percentage < 0.15) return '#f59e0b';
        return '#10b981';
      case 'pressure':
        if (percentage > 0.9) return '#ef4444';
        if (percentage > 0.8) return '#f59e0b';
        return '#10b981';
      case 'flow':
        if (percentage < 0.05) return '#f59e0b'; // Low flow warning
        return '#10b981';
      default:
        return '#3b82f6'; // Blue for unknown types
    }
  };

  // Get icon based on sensor type
  const getIcon = () => {
    switch (sensor.sensor_type) {
      case 'temperature':
        return (
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2a2 2 0 0 0-2 2v9.354A4 4 0 1 0 16 17V4a2 2 0 0 0-2-2h-2zm0 18a2 2 0 1 1 0-4 2 2 0 0 1 0 4z" />
          </svg>
        );
      case 'ph':
        return <span className="text-xs font-bold">pH</span>;
      case 'level':
        return (
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2l-5.5 9h11L12 2zm0 11c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5z" />
          </svg>
        );
      case 'pressure':
        return (
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z" />
          </svg>
        );
      case 'flow':
        return (
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M17.66 8L12 2.35 6.34 8C4.78 9.56 4 11.64 4 13.64s.78 4.11 2.34 5.67 3.61 2.35 5.66 2.35 4.1-.79 5.66-2.35S20 15.64 20 13.64 19.22 9.56 17.66 8z" />
          </svg>
        );
      default:
        return (
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" />
          </svg>
        );
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
          <span style={{ color }}>{getIcon()}</span>
          <span className="text-xs truncate flex-1" title={sensor.name}>
            {sensor.name}
          </span>
          {!isGoodQuality && (
            <span className="text-xs text-red-500" title="Bad quality">!</span>
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
