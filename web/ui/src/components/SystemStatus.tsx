'use client';

import { useState, useEffect } from 'react';

interface Props {
  connected: boolean;
  rtuCount: number;
  alarmCount: number;
}

export default function SystemStatus({ connected, rtuCount, alarmCount }: Props) {
  return (
    <div className="scada-panel p-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-6">
          {/* Connection Status */}
          <div className="flex items-center gap-2">
            <span
              className={`status-indicator ${connected ? 'online' : 'offline'}`}
            />
            <span className="text-sm text-gray-300">
              {connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>

          {/* RTU Count */}
          <div className="flex items-center gap-2">
            <svg
              className="w-4 h-4 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z"
              />
            </svg>
            <span className="text-sm text-gray-300">
              <span className="font-semibold text-white">{rtuCount}</span> RTUs
            </span>
          </div>

          {/* Alarm Count */}
          <div className="flex items-center gap-2">
            <svg
              className={`w-4 h-4 ${alarmCount > 0 ? 'text-red-400' : 'text-gray-400'}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
              />
            </svg>
            <span className="text-sm text-gray-300">
              <span className={`font-semibold ${alarmCount > 0 ? 'text-red-400' : 'text-white'}`}>
                {alarmCount}
              </span>{' '}
              Active Alarms
            </span>
          </div>
        </div>

        {/* System Time */}
        <div className="text-sm text-gray-400">
          <SystemTime />
        </div>
      </div>
    </div>
  );
}

function SystemTime() {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const interval = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  return <span>{time.toLocaleString()}</span>;
}
