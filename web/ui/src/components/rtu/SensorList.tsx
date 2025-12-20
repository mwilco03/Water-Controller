'use client';

import { useMemo } from 'react';
import type { RTUSensor } from '@/lib/api';
import SensorDisplay from './SensorDisplay';

interface Props {
  sensors: RTUSensor[];
  groupByType?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export default function SensorList({ sensors, groupByType = true, size = 'md' }: Props) {
  const groupedSensors = useMemo(() => {
    if (!groupByType) {
      return { 'All Sensors': sensors };
    }

    const groups: Record<string, RTUSensor[]> = {};
    for (const sensor of sensors) {
      const type = sensor.sensor_type || 'other';
      const label = formatTypeLabel(type);
      if (!groups[label]) {
        groups[label] = [];
      }
      groups[label].push(sensor);
    }

    // Sort groups by priority
    const orderedGroups: Record<string, RTUSensor[]> = {};
    const priority = ['Temperature', 'Level', 'Pressure', 'Flow', 'pH', 'Turbidity', 'Chlorine', 'Other'];
    for (const p of priority) {
      if (groups[p]) {
        orderedGroups[p] = groups[p];
      }
    }
    // Add any remaining groups
    for (const [key, value] of Object.entries(groups)) {
      if (!orderedGroups[key]) {
        orderedGroups[key] = value;
      }
    }

    return orderedGroups;
  }, [sensors, groupByType]);

  if (sensors.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400">
        <svg className="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
        </svg>
        <p>No sensors discovered</p>
        <p className="text-sm mt-1">Refresh inventory to discover sensors from RTU</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {Object.entries(groupedSensors).map(([groupName, groupSensors]) => (
        <div key={groupName}>
          {groupByType && (
            <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
              {getGroupIcon(groupName)}
              {groupName}
              <span className="text-xs text-gray-500">({groupSensors.length})</span>
            </h3>
          )}
          <div className="flex flex-wrap gap-3">
            {groupSensors.map((sensor) => (
              <SensorDisplay
                key={sensor.id}
                sensor={sensor}
                size={size}
                showDetails={size === 'lg'}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function formatTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    temperature: 'Temperature',
    level: 'Level',
    pressure: 'Pressure',
    flow: 'Flow',
    ph: 'pH',
    turbidity: 'Turbidity',
    chlorine: 'Chlorine',
    conductivity: 'Conductivity',
    dissolved_oxygen: 'Dissolved Oxygen',
    other: 'Other',
  };
  return labels[type.toLowerCase()] || type.charAt(0).toUpperCase() + type.slice(1);
}

function getGroupIcon(groupName: string) {
  const iconClass = 'w-4 h-4 text-gray-500';
  switch (groupName.toLowerCase()) {
    case 'temperature':
      return (
        <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 2a2 2 0 0 0-2 2v9.354A4 4 0 1 0 16 17V4a2 2 0 0 0-2-2h-2z" />
        </svg>
      );
    case 'level':
      return (
        <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 2l-5.5 9h11L12 2zm0 11c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5z" />
        </svg>
      );
    case 'pressure':
      return (
        <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="M12 6v6l4 2" stroke="currentColor" strokeWidth="2" fill="none" />
        </svg>
      );
    case 'flow':
      return (
        <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24">
          <path d="M17.66 8L12 2.35 6.34 8C4.78 9.56 4 11.64 4 13.64s.78 4.11 2.34 5.67 3.61 2.35 5.66 2.35 4.1-.79 5.66-2.35S20 15.64 20 13.64 19.22 9.56 17.66 8z" />
        </svg>
      );
    default:
      return (
        <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
        </svg>
      );
  }
}
