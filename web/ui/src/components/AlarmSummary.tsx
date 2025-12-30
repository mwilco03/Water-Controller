'use client';

import { useState } from 'react';
import { alarmLogger } from '@/lib/logger';

interface Alarm {
  alarm_id: number;
  rtu_station: string;
  slot: number;
  severity: string;
  message: string;
  state: string;
  timestamp: string;
  value?: number;
  threshold?: number;
}

interface Props {
  alarms: Alarm[];
  onShelve?: (alarm: Alarm) => void;
}

export default function AlarmSummary({ alarms, onShelve }: Props) {
  const [filter, setFilter] = useState<string>('all');

  const getSeverityClass = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical':
      case 'emergency':
        return 'critical';
      case 'warning':
        return 'warning';
      default:
        return 'info';
    }
  };

  const isUnacknowledged = (state: string) => {
    return state === 'ACTIVE_UNACK' || state === 'CLEARED_UNACK';
  };

  const filteredAlarms = alarms.filter((alarm) => {
    if (filter === 'unack') return isUnacknowledged(alarm.state);
    if (filter === 'active') return alarm.state.includes('ACTIVE');
    return true;
  });

  const acknowledgeAlarm = async (alarmId: number) => {
    try {
      await fetch(`/api/v1/alarms/${alarmId}/acknowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: 'operator' }),
      });
    } catch (error) {
      alarmLogger.error('Failed to acknowledge alarm', error);
    }
  };

  const acknowledgeAll = async () => {
    try {
      await fetch('/api/v1/alarms/acknowledge-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: 'operator' }),
      });
    } catch (error) {
      alarmLogger.error('Failed to acknowledge all alarms', error);
    }
  };

  return (
    <div className="scada-panel p-4 h-full">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Active Alarms</h2>
        <div className="flex gap-2">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="text-xs bg-scada-accent text-white rounded px-2 py-1 border border-scada-accent"
          >
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="unack">Unacknowledged</option>
          </select>
          <button
            onClick={acknowledgeAll}
            className="text-xs bg-scada-highlight hover:bg-red-600 px-3 py-1 rounded transition-colors"
          >
            Ack All
          </button>
        </div>
      </div>

      <div className="space-y-2 max-h-96 overflow-y-auto">
        {filteredAlarms.map((alarm) => (
          <div
            key={alarm.alarm_id}
            className={`alarm-row ${getSeverityClass(alarm.severity)} ${
              isUnacknowledged(alarm.state) ? 'alarm-active' : ''
            } p-3 rounded bg-scada-accent/50`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`text-xs px-2 py-0.5 rounded ${
                      getSeverityClass(alarm.severity) === 'critical'
                        ? 'bg-red-600'
                        : getSeverityClass(alarm.severity) === 'warning'
                        ? 'bg-yellow-600'
                        : 'bg-blue-600'
                    }`}
                  >
                    {alarm.severity}
                  </span>
                  <span className="text-xs text-gray-400">
                    {alarm.rtu_station}
                  </span>
                </div>
                <div className="text-sm text-white mb-1">{alarm.message}</div>
                <div className="text-xs text-gray-400">
                  {new Date(alarm.timestamp).toLocaleString()}
                </div>
              </div>
              <div className="flex gap-1">
                {onShelve && (
                  <button
                    onClick={() => onShelve(alarm)}
                    className="text-xs bg-purple-700 hover:bg-purple-600 px-2 py-1 rounded transition-colors whitespace-nowrap"
                    title="Shelve alarm"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </button>
                )}
                {isUnacknowledged(alarm.state) && (
                  <button
                    onClick={() => acknowledgeAlarm(alarm.alarm_id)}
                    className="text-xs bg-scada-accent hover:bg-scada-highlight px-2 py-1 rounded transition-colors whitespace-nowrap"
                  >
                    ACK
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
        {filteredAlarms.length === 0 && (
          <div className="text-center text-gray-400 py-8">
            No alarms to display
          </div>
        )}
      </div>
    </div>
  );
}
