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
      <div className="text-center py-8 text-gray-400">
        <svg className="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
        <p>No controls discovered</p>
        <p className="text-sm mt-1">Refresh inventory to discover controls from RTU</p>
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
  const iconClass = 'w-4 h-4 text-gray-500';
  switch (groupName.toLowerCase()) {
    case 'pumps':
      return (
        <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83" stroke="currentColor" strokeWidth="2" fill="none" />
        </svg>
      );
    case 'valves':
      return (
        <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 2L8 6h8l-4-4zM8 18l4 4 4-4H8zM2 8v8h4V8H2zm16 0v8h4V8h-4zM8 8v8h8V8H8z" />
        </svg>
      );
    case 'motors':
      return (
        <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24">
          <rect x="2" y="6" width="20" height="12" rx="2" />
          <circle cx="6" cy="12" r="2" fill="rgba(0,0,0,0.3)" />
        </svg>
      );
    case 'heaters':
      return (
        <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 2a7 7 0 0 0-7 7c0 2.38 1.19 4.47 3 5.74V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.26c1.81-1.27 3-3.36 3-5.74a7 7 0 0 0-7-7z" />
        </svg>
      );
    default:
      return (
        <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
        </svg>
      );
  }
}
