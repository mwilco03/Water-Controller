'use client';

import { useMemo } from 'react';
import type { RTUControl } from '@/lib/api';
import ControlWidget from './ControlWidget';

interface Props {
  controls: RTUControl[];
  rtuStation: string;
  groupByType?: boolean;
  disabled?: boolean;
  interactive?: boolean; // If false, shows status only (view mode)
  onCommandSent?: () => void;
}

export default function ControlList({
  controls,
  rtuStation,
  groupByType = true,
  disabled = false,
  interactive = true,
  onCommandSent,
}: Props) {
  const groupedControls = useMemo(() => {
    if (!groupByType) {
      return { 'All Controls': controls };
    }

    const groups: Record<string, RTUControl[]> = {};
    for (const control of controls) {
      const type = control.control_type || 'other';
      const label = formatTypeLabel(type);
      if (!groups[label]) {
        groups[label] = [];
      }
      groups[label].push(control);
    }

    // Sort groups by priority
    const orderedGroups: Record<string, RTUControl[]> = {};
    const priority = ['Pumps', 'Valves', 'Motors', 'Heaters', 'Dosing', 'Other'];
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
  }, [controls, groupByType]);

  if (controls.length === 0) {
    return (
      <div className="text-center py-4 text-gray-400">
        <span className="block text-2xl font-bold mb-2 opacity-50">[CTRL]</span>
        <p className="text-sm">No controls discovered</p>
        <p className="text-xs mt-1">Refresh inventory to discover controls from RTU</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {Object.entries(groupedControls).map(([groupName, groupControls]) => (
        <div key={groupName}>
          {groupByType && (
            <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
              {getGroupIcon(groupName)}
              {groupName}
              <span className="text-xs text-gray-500">({groupControls.length})</span>
            </h3>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {groupControls.map((control) => (
              <ControlWidget
                key={control.id}
                control={control}
                rtuStation={rtuStation}
                disabled={disabled}
                interactive={interactive}
                onCommandSent={onCommandSent}
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
    pump: 'Pumps',
    valve: 'Valves',
    motor: 'Motors',
    heater: 'Heaters',
    dosing: 'Dosing',
    relay: 'Relays',
    actuator: 'Actuators',
    other: 'Other',
  };
  return labels[type.toLowerCase()] || type.charAt(0).toUpperCase() + type.slice(1) + 's';
}

function getGroupIcon(groupName: string) {
  const labelClass = 'text-xs font-medium text-gray-500';
  switch (groupName.toLowerCase()) {
    case 'pumps':
      return <span className={labelClass}>[PUMP]</span>;
    case 'valves':
      return <span className={labelClass}>[VLV]</span>;
    case 'motors':
      return <span className={labelClass}>[MTR]</span>;
    case 'heaters':
      return <span className={labelClass}>[HTR]</span>;
    case 'dosing':
      return <span className={labelClass}>[DOS]</span>;
    case 'relays':
      return <span className={labelClass}>[RLY]</span>;
    case 'actuators':
      return <span className={labelClass}>[ACT]</span>;
    default:
      return <span className={labelClass}>[CTRL]</span>;
  }
}
