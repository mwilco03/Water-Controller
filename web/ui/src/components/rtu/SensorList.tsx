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
      <div className="text-center py-4 text-gray-400">
        <span className="block text-2xl font-bold mb-2 opacity-50">[SENSOR]</span>
        <p className="text-sm">No sensors discovered</p>
        <p className="text-xs mt-1">Refresh inventory to discover sensors from RTU</p>
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
  const labelClass = 'text-xs font-medium text-gray-500';
  switch (groupName.toLowerCase()) {
    case 'temperature':
      return <span className={labelClass}>[TEMP]</span>;
    case 'level':
      return <span className={labelClass}>[LVL]</span>;
    case 'pressure':
      return <span className={labelClass}>[PSI]</span>;
    case 'flow':
      return <span className={labelClass}>[FLOW]</span>;
    case 'ph':
      return <span className={labelClass}>[pH]</span>;
    case 'turbidity':
      return <span className={labelClass}>[TURB]</span>;
    case 'chlorine':
      return <span className={labelClass}>[CL]</span>;
    default:
      return <span className={labelClass}>[SENS]</span>;
  }
}
