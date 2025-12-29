'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import AlarmSummary from '@/components/AlarmSummary';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useCommandMode } from '@/contexts/CommandModeContext';
import CommandModeLogin from '@/components/CommandModeLogin';
import { wsLogger, alarmLogger } from '@/lib/logger';

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

interface ShelvedAlarm {
  id: number;
  rtu_station: string;
  slot: number;
  shelved_by: string;
  shelved_at: string;
  shelf_duration_minutes: number;
  expires_at: string;
  reason: string | null;
  active: number;
}

interface ShelveDialogState {
  isOpen: boolean;
  alarm: Alarm | null;
}

// Shelve Dialog Component
function ShelveDialog({
  isOpen,
  alarm,
  onClose,
  onShelve,
}: {
  isOpen: boolean;
  alarm: Alarm | null;
  onClose: () => void;
  onShelve: (duration: number, reason: string) => void;
}) {
  const [duration, setDuration] = useState(60);
  const [reason, setReason] = useState('');

  if (!isOpen || !alarm) return null;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4 border border-gray-600">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-blue-600/20 flex items-center justify-center">
            <svg className="w-6 h-6 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-white">Shelve Alarm</h3>
        </div>

        <p className="text-gray-300 mb-4">
          Temporarily suppress alarm: <span className="font-bold text-white">{alarm.message}</span>
        </p>
        <p className="text-sm text-gray-400 mb-4">
          RTU: {alarm.rtu_station} | Slot: {alarm.slot}
        </p>

        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-2">Duration</label>
            <select
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="w-full bg-gray-700 text-white rounded px-3 py-2"
            >
              <option value={60}>1 hour</option>
              <option value={120}>2 hours</option>
              <option value={240}>4 hours</option>
              <option value={480}>8 hours</option>
            </select>
          </div>

          <div>
            <label className="text-sm text-gray-400 block mb-2">Reason (optional)</label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g., Scheduled maintenance"
              className="w-full bg-gray-700 text-white rounded px-3 py-2"
            />
          </div>
        </div>

        <div className="flex gap-3 justify-end mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onShelve(duration, reason)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded font-medium transition-colors"
          >
            Shelve Alarm
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AlarmsPage() {
  const { canCommand, mode } = useCommandMode();
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [history, setHistory] = useState<Alarm[]>([]);
  const [shelvedAlarms, setShelvedAlarms] = useState<ShelvedAlarm[]>([]);
  const [activeTab, setActiveTab] = useState<'active' | 'shelved' | 'history'>('active');
  const [loading, setLoading] = useState(true);
  const [shelveDialog, setShelveDialog] = useState<ShelveDialogState>({ isOpen: false, alarm: null });
  const [error, setError] = useState<string | null>(null);
  const [visibleHistoryCount, setVisibleHistoryCount] = useState(50); /* UI-M2: Simple virtualization */
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchAlarms = useCallback(async () => {
    try {
      setError(null);
      const [activeRes, historyRes, shelvedRes] = await Promise.all([
        fetch('/api/v1/alarms'),
        fetch('/api/v1/alarms/history?limit=100'),
        fetch('/api/v1/alarms/shelved'),
      ]);

      /* UI-M1: Better error state handling */
      if (!activeRes.ok) {
        setError(`Failed to fetch active alarms: ${activeRes.status}`);
      } else {
        const data = await activeRes.json();
        setAlarms(data.alarms || []);
      }

      if (historyRes.ok) {
        const data = await historyRes.json();
        setHistory(data.alarms || []);
      }

      if (shelvedRes.ok) {
        const data = await shelvedRes.json();
        setShelvedAlarms(data.shelved_alarms || []);
      }
    } catch (err) {
      /* UI-M1: Show user-facing error message */
      setError(err instanceof Error ? err.message : 'Network error - unable to fetch alarms');
      alarmLogger.error('Error fetching alarms', err);
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
        wsLogger.info('WebSocket connected - alarm polling disabled');
      }
    },
    onDisconnect: () => {
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(fetchAlarms, 5000);
        wsLogger.info('WebSocket disconnected - alarm polling enabled');
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

  const handleShelveAlarm = async (duration: number, reason: string) => {
    if (!shelveDialog.alarm) return;
    try {
      const res = await fetch('/api/v1/alarms/shelve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rtu_station: shelveDialog.alarm.rtu_station,
          slot: shelveDialog.alarm.slot,
          duration_minutes: duration,
          reason: reason || null,
        }),
      });
      if (res.ok) {
        fetchAlarms();
        setShelveDialog({ isOpen: false, alarm: null });
      }
    } catch (error) {
      alarmLogger.error('Error shelving alarm', error);
    }
  };

  const handleUnshelve = async (shelfId: number) => {
    try {
      const res = await fetch(`/api/v1/alarms/shelved/${shelfId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        fetchAlarms();
      }
    } catch (error) {
      alarmLogger.error('Error unshelving alarm', error);
    }
  };

  const stats = {
    total: alarms.length,
    critical: alarms.filter((a) => a.severity === 'CRITICAL' || a.severity === 'EMERGENCY').length,
    warning: alarms.filter((a) => a.severity === 'WARNING').length,
    unack: alarms.filter((a) => a.state === 'ACTIVE_UNACK' || a.state === 'CLEARED_UNACK').length,
    shelved: shelvedAlarms.length,
  };

  return (
    <>
      {/* Shelve Dialog */}
      <ShelveDialog
        isOpen={shelveDialog.isOpen}
        alarm={shelveDialog.alarm}
        onClose={() => setShelveDialog({ isOpen: false, alarm: null })}
        onShelve={handleShelveAlarm}
      />

      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-white">Alarm Management</h1>
          {mode === 'view' && <CommandModeLogin showButton />}
        </div>

        {/* Statistics */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
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
          <div className="scada-panel p-4 text-center">
            <div className="text-3xl font-bold text-purple-400">{stats.shelved}</div>
            <div className="text-sm text-gray-400">Shelved</div>
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
            onClick={() => setActiveTab('shelved')}
            className={`pb-2 px-4 ${
              activeTab === 'shelved'
                ? 'border-b-2 border-scada-highlight text-white'
                : 'text-gray-400'
            }`}
          >
            Shelved ({shelvedAlarms.length})
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

        {/* UI-M1: Error state display */}
        {error && (
          <div className="bg-red-900/30 border border-red-500/50 rounded-lg p-4 flex items-center gap-3">
            <svg className="w-6 h-6 text-red-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1">
              <p className="text-red-300 font-medium">Error Loading Alarms</p>
              <p className="text-red-400 text-sm">{error}</p>
            </div>
            <button
              onClick={fetchAlarms}
              className="px-3 py-1 bg-red-600 hover:bg-red-500 text-white text-sm rounded transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Alarm List */}
        <div className="scada-panel p-4">
          {loading ? (
            <div className="text-center text-gray-400 py-8">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-gray-600 border-t-blue-500 mb-2"></div>
              <p>Loading alarms...</p>
            </div>
          ) : activeTab === 'active' ? (
            <div>
              {/* Shelve instruction */}
              {canCommand && alarms.length > 0 && (
                <div className="mb-4 p-3 bg-blue-900/20 border border-blue-700/50 rounded text-sm text-blue-300">
                  <svg className="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Click the clock icon to shelve an alarm temporarily (ISA-18.2)
                </div>
              )}
              <AlarmSummary
                alarms={alarms}
                onShelve={canCommand ? (alarm: Alarm) => setShelveDialog({ isOpen: true, alarm }) : undefined}
              />
            </div>
          ) : activeTab === 'shelved' ? (
            <div>
              {shelvedAlarms.length === 0 ? (
                <div className="text-center text-gray-400 py-8">No shelved alarms</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-gray-400 text-sm border-b border-scada-accent">
                        <th className="pb-3">RTU</th>
                        <th className="pb-3">Slot</th>
                        <th className="pb-3">Shelved By</th>
                        <th className="pb-3">Duration</th>
                        <th className="pb-3">Expires</th>
                        <th className="pb-3">Reason</th>
                        <th className="pb-3">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shelvedAlarms.map((shelf) => (
                        <tr key={shelf.id} className="border-b border-scada-accent/50">
                          <td className="py-2 text-sm text-gray-300">{shelf.rtu_station}</td>
                          <td className="py-2 text-sm text-gray-300">{shelf.slot}</td>
                          <td className="py-2 text-sm text-gray-300">{shelf.shelved_by}</td>
                          <td className="py-2 text-sm text-gray-300">
                            {shelf.shelf_duration_minutes >= 60
                              ? `${Math.floor(shelf.shelf_duration_minutes / 60)}h`
                              : `${shelf.shelf_duration_minutes}m`}
                          </td>
                          <td className="py-2 text-sm text-gray-400">
                            {new Date(shelf.expires_at).toLocaleString()}
                          </td>
                          <td className="py-2 text-sm text-gray-400">{shelf.reason || '-'}</td>
                          <td className="py-2">
                            {canCommand && (
                              <button
                                onClick={() => handleUnshelve(shelf.id)}
                                className="text-xs bg-purple-600 hover:bg-purple-500 px-3 py-1 rounded transition-colors"
                              >
                                Unshelve
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              {/* UI-M2: Simple virtualization with pagination */}
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
                  {history.slice(0, visibleHistoryCount).map((alarm) => (
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
              {/* UI-M2: Load more button for virtualization */}
              {history.length > visibleHistoryCount && (
                <div className="text-center mt-4">
                  <button
                    onClick={() => setVisibleHistoryCount((prev) => prev + 50)}
                    className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded transition-colors"
                  >
                    Load More ({history.length - visibleHistoryCount} remaining)
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
