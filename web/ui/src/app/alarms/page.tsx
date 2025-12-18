'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import AlarmSummary from '@/components/AlarmSummary';
import { useWebSocket } from '@/hooks/useWebSocket';

interface Alarm {
  alarm_id: number;
  rtu_station: string;
  slot: number;
  severity: string;
  message: string;
  state: string;
  timestamp: string;
  value: number;
  threshold: number;
  ack_user?: string;
  ack_time?: string;
}

export default function AlarmsPage() {
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [history, setHistory] = useState<Alarm[]>([]);
  const [activeTab, setActiveTab] = useState<'active' | 'history'>('active');
  const [loading, setLoading] = useState(true);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchAlarms = useCallback(async () => {
    try {
      const [activeRes, historyRes] = await Promise.all([
        fetch('/api/v1/alarms'),
        fetch('/api/v1/alarms/history?limit=100'),
      ]);

      if (activeRes.ok) {
        const data = await activeRes.json();
        setAlarms(data.alarms || []);
      }

      if (historyRes.ok) {
        const data = await historyRes.json();
        setHistory(data.alarms || []);
      }
    } catch (error) {
      console.error('Error fetching alarms:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  // WebSocket for real-time alarm updates
  const { connected, subscribe } = useWebSocket({
    onConnect: () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
        console.log('WebSocket connected - alarm polling disabled');
      }
    },
    onDisconnect: () => {
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(fetchAlarms, 5000);
        console.log('WebSocket disconnected - alarm polling enabled');
      }
    },
  });

  // Subscribe to alarm events
  useEffect(() => {
    const unsubRaised = subscribe('alarm_raised', (_, alarm) => {
      setAlarms((prev) => {
        const existing = prev.findIndex((a) => a.alarm_id === alarm.alarm_id);
        if (existing >= 0) {
          const updated = [...prev];
          updated[existing] = alarm;
          return updated;
        }
        return [alarm, ...prev];
      });
    });

    const unsubAck = subscribe('alarm_acknowledged', (_, data) => {
      setAlarms((prev) =>
        prev.map((a) =>
          a.alarm_id === data.alarm_id ? { ...a, state: 'ACTIVE_ACK' } : a
        )
      );
    });

    const unsubCleared = subscribe('alarm_cleared', (_, data) => {
      setAlarms((prev) => prev.filter((a) => a.alarm_id !== data.alarm_id));
      // Refresh history when alarm clears
      fetchAlarms();
    });

    return () => {
      unsubRaised();
      unsubAck();
      unsubCleared();
    };
  }, [subscribe, fetchAlarms]);

  // Initial fetch and polling setup
  useEffect(() => {
    fetchAlarms();
    pollIntervalRef.current = setInterval(fetchAlarms, 5000);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [fetchAlarms]);

  const stats = {
    total: alarms.length,
    critical: alarms.filter((a) => a.severity === 'CRITICAL' || a.severity === 'EMERGENCY').length,
    warning: alarms.filter((a) => a.severity === 'WARNING').length,
    unack: alarms.filter((a) => a.state === 'ACTIVE_UNACK' || a.state === 'CLEARED_UNACK').length,
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Alarm Management</h1>

      {/* Statistics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="scada-panel p-4 text-center">
          <div className="text-3xl font-bold text-white">{stats.total}</div>
          <div className="text-sm text-gray-400">Active Alarms</div>
        </div>
        <div className="scada-panel p-4 text-center">
          <div className="text-3xl font-bold text-red-500">{stats.critical}</div>
          <div className="text-sm text-gray-400">Critical</div>
        </div>
        <div className="scada-panel p-4 text-center">
          <div className="text-3xl font-bold text-yellow-500">{stats.warning}</div>
          <div className="text-sm text-gray-400">Warning</div>
        </div>
        <div className="scada-panel p-4 text-center">
          <div className="text-3xl font-bold text-blue-400">{stats.unack}</div>
          <div className="text-sm text-gray-400">Unacknowledged</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-scada-accent">
        <button
          onClick={() => setActiveTab('active')}
          className={`pb-2 px-4 ${
            activeTab === 'active'
              ? 'border-b-2 border-scada-highlight text-white'
              : 'text-gray-400'
          }`}
        >
          Active Alarms ({alarms.length})
        </button>
        <button
          onClick={() => setActiveTab('history')}
          className={`pb-2 px-4 ${
            activeTab === 'history'
              ? 'border-b-2 border-scada-highlight text-white'
              : 'text-gray-400'
          }`}
        >
          History ({history.length})
        </button>
      </div>

      {/* Alarm List */}
      <div className="scada-panel p-4">
        {loading ? (
          <div className="text-center text-gray-400 py-8">Loading...</div>
        ) : activeTab === 'active' ? (
          <AlarmSummary alarms={alarms} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-gray-400 text-sm border-b border-scada-accent">
                  <th className="pb-3">Time</th>
                  <th className="pb-3">Severity</th>
                  <th className="pb-3">RTU</th>
                  <th className="pb-3">Message</th>
                  <th className="pb-3">Value</th>
                  <th className="pb-3">Ack By</th>
                </tr>
              </thead>
              <tbody>
                {history.map((alarm) => (
                  <tr key={alarm.alarm_id} className="border-b border-scada-accent/50">
                    <td className="py-2 text-sm text-gray-400">
                      {new Date(alarm.timestamp).toLocaleString()}
                    </td>
                    <td className="py-2">
                      <span
                        className={`text-xs px-2 py-0.5 rounded ${
                          alarm.severity === 'CRITICAL' || alarm.severity === 'EMERGENCY'
                            ? 'bg-red-600'
                            : alarm.severity === 'WARNING'
                            ? 'bg-yellow-600'
                            : 'bg-blue-600'
                        }`}
                      >
                        {alarm.severity}
                      </span>
                    </td>
                    <td className="py-2 text-sm text-gray-300">{alarm.rtu_station}</td>
                    <td className="py-2 text-sm text-white">{alarm.message}</td>
                    <td className="py-2 text-sm text-gray-300">
                      {alarm.value?.toFixed(2)} / {alarm.threshold?.toFixed(2)}
                    </td>
                    <td className="py-2 text-sm text-gray-400">{alarm.ack_user || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
