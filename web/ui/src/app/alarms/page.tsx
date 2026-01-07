'use client';

/**
 * Alarm Management Page
 * ISA-101 Compliant SCADA HMI
 *
 * Design principles:
 * - Gray is normal, color is abnormal
 * - Red for critical/alarm states
 * - Amber for warnings
 * - Light background for readability
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import AlarmSummary from '@/components/AlarmSummary';
import { AlarmInsights } from '@/components/hmi';

const PAGE_TITLE = 'Alarms - Water Treatment Controller';
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
  value?: number;
  threshold?: number;
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

// Shelve Dialog Component - ISA-101 Compliant
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
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-hmi-panel rounded-lg p-6 max-w-md w-full mx-4 border border-hmi-border shadow-lg">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-status-info/10 flex items-center justify-center">
            <svg className="w-6 h-6 text-status-info" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-hmi-text">Shelve Alarm</h3>
        </div>

        <p className="text-hmi-muted mb-4">
          Temporarily suppress alarm: <span className="font-bold text-hmi-text">{alarm.message}</span>
        </p>
        <p className="text-sm text-hmi-muted mb-4">
          RTU: {alarm.rtu_station} | Slot: {alarm.slot}
        </p>

        <div className="space-y-4">
          <div>
            <label className="text-sm text-hmi-muted block mb-2">Duration</label>
            <select
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="w-full bg-hmi-bg border border-hmi-border text-hmi-text rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-status-info"
            >
              <option value={60}>1 hour</option>
              <option value={120}>2 hours</option>
              <option value={240}>4 hours</option>
              <option value={480}>8 hours</option>
            </select>
          </div>

          <div>
            <label className="text-sm text-hmi-muted block mb-2">Reason (optional)</label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g., Scheduled maintenance"
              className="w-full bg-hmi-bg border border-hmi-border text-hmi-text rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-status-info"
            />
          </div>
        </div>

        <div className="flex gap-3 justify-end mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-hmi-bg hover:bg-hmi-border text-hmi-text rounded border border-hmi-border transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onShelve(duration, reason)}
            className="px-4 py-2 bg-status-info hover:bg-status-info/90 text-white rounded font-medium transition-colors"
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
  const [visibleHistoryCount, setVisibleHistoryCount] = useState(50);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);

  const fetchAlarms = useCallback(async () => {
    try {
      setError(null);
      const [activeRes, historyRes, shelvedRes] = await Promise.all([
        fetch('/api/v1/alarms'),
        fetch('/api/v1/alarms/history?limit=100'),
        fetch('/api/v1/alarms/shelved'),
      ]);

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
      setError(err instanceof Error ? err.message : 'Network error - unable to fetch alarms');
      alarmLogger.error('Error fetching alarms', err);
    } finally {
      setLoading(false);
    }
  }, []);

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
      fetchAlarms();
    });

    return () => {
      unsubRaised();
      unsubAck();
      unsubCleared();
    };
  }, [subscribe, fetchAlarms]);

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
      <ShelveDialog
        isOpen={shelveDialog.isOpen}
        alarm={shelveDialog.alarm}
        onClose={() => setShelveDialog({ isOpen: false, alarm: null })}
        onShelve={handleShelveAlarm}
      />

      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-hmi-text">Alarm Management</h1>
          {mode === 'view' && <CommandModeLogin showButton />}
        </div>

        {/* Statistics - ISA-101: color only for abnormal values */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="hmi-card p-4 text-center">
            <div className={`text-3xl font-bold font-mono ${stats.total > 0 ? 'text-status-alarm' : 'text-hmi-text'}`}>
              {stats.total}
            </div>
            <div className="text-sm text-hmi-muted">Active Alarms</div>
          </div>
          <div className="hmi-card p-4 text-center">
            <div className={`text-3xl font-bold font-mono ${stats.critical > 0 ? 'text-status-alarm' : 'text-hmi-muted'}`}>
              {stats.critical}
            </div>
            <div className="text-sm text-hmi-muted">Critical</div>
          </div>
          <div className="hmi-card p-4 text-center">
            <div className={`text-3xl font-bold font-mono ${stats.warning > 0 ? 'text-status-warning' : 'text-hmi-muted'}`}>
              {stats.warning}
            </div>
            <div className="text-sm text-hmi-muted">Warning</div>
          </div>
          <div className="hmi-card p-4 text-center">
            <div className={`text-3xl font-bold font-mono ${stats.unack > 0 ? 'text-status-info' : 'text-hmi-muted'}`}>
              {stats.unack}
            </div>
            <div className="text-sm text-hmi-muted">Unacknowledged</div>
          </div>
          <div className="hmi-card p-4 text-center">
            <div className="text-3xl font-bold font-mono text-hmi-muted">{stats.shelved}</div>
            <div className="text-sm text-hmi-muted">Shelved</div>
          </div>
        </div>

        {/* Alarm Insights - Shows frequently occurring alarms for chronic issue detection */}
        <AlarmInsights
          alarmHistory={history}
          onShelve={canCommand ? (rtuStation, slot) => {
            // Find a matching alarm to shelve
            const alarm = alarms.find(a => a.rtu_station === rtuStation && a.slot === slot);
            if (alarm) {
              setShelveDialog({ isOpen: true, alarm });
            }
          } : undefined}
        />

        {/* Tabs - ISA-101: subtle styling */}
        <div className="flex gap-4 border-b border-hmi-border">
          <button
            onClick={() => setActiveTab('active')}
            className={`pb-2 px-4 font-medium transition-colors ${
              activeTab === 'active'
                ? 'border-b-2 border-status-info text-status-info'
                : 'text-hmi-muted hover:text-hmi-text'
            }`}
          >
            Active Alarms ({alarms.length})
          </button>
          <button
            onClick={() => setActiveTab('shelved')}
            className={`pb-2 px-4 font-medium transition-colors ${
              activeTab === 'shelved'
                ? 'border-b-2 border-status-info text-status-info'
                : 'text-hmi-muted hover:text-hmi-text'
            }`}
          >
            Shelved ({shelvedAlarms.length})
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`pb-2 px-4 font-medium transition-colors ${
              activeTab === 'history'
                ? 'border-b-2 border-status-info text-status-info'
                : 'text-hmi-muted hover:text-hmi-text'
            }`}
          >
            History ({history.length})
          </button>
        </div>

        {/* Error state - ISA-101: red for errors */}
        {error && (
          <div className="bg-quality-bad border border-status-alarm/30 rounded-lg p-4 flex items-center gap-3">
            <svg className="w-6 h-6 text-status-alarm flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1">
              <p className="text-status-alarm font-medium">Error Loading Alarms</p>
              <p className="text-hmi-muted text-sm">{error}</p>
            </div>
            <button
              onClick={fetchAlarms}
              className="px-3 py-1 bg-status-alarm hover:bg-status-alarm/90 text-white text-sm rounded transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Alarm List */}
        <div className="hmi-card p-4">
          {loading ? (
            <div className="text-center text-hmi-muted py-8">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-hmi-border border-t-status-info mb-2"></div>
              <p>Loading alarms...</p>
            </div>
          ) : activeTab === 'active' ? (
            <div>
              {canCommand && alarms.length > 0 && (
                <div className="mb-4 p-3 bg-status-info/10 border border-status-info/30 rounded text-sm text-status-info">
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
                <div className="text-center text-hmi-muted py-8">No shelved alarms</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-hmi-muted text-sm border-b border-hmi-border">
                        <th className="pb-3 font-medium">RTU</th>
                        <th className="pb-3 font-medium">Slot</th>
                        <th className="pb-3 font-medium">Shelved By</th>
                        <th className="pb-3 font-medium">Duration</th>
                        <th className="pb-3 font-medium">Expires</th>
                        <th className="pb-3 font-medium">Reason</th>
                        <th className="pb-3 font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shelvedAlarms.map((shelf) => (
                        <tr key={shelf.id} className="border-b border-hmi-border/50">
                          <td className="py-3 text-sm text-hmi-text">{shelf.rtu_station}</td>
                          <td className="py-3 text-sm text-hmi-text font-mono">{shelf.slot}</td>
                          <td className="py-3 text-sm text-hmi-text">{shelf.shelved_by}</td>
                          <td className="py-3 text-sm text-hmi-muted">
                            {shelf.shelf_duration_minutes >= 60
                              ? `${Math.floor(shelf.shelf_duration_minutes / 60)}h`
                              : `${shelf.shelf_duration_minutes}m`}
                          </td>
                          <td className="py-3 text-sm text-hmi-muted">
                            {new Date(shelf.expires_at).toLocaleString()}
                          </td>
                          <td className="py-3 text-sm text-hmi-muted">{shelf.reason || '-'}</td>
                          <td className="py-3">
                            {canCommand && (
                              <button
                                onClick={() => handleUnshelve(shelf.id)}
                                className="text-xs bg-status-info hover:bg-status-info/90 text-white px-3 py-1 rounded transition-colors"
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
              <table className="w-full">
                <thead>
                  <tr className="text-left text-hmi-muted text-sm border-b border-hmi-border">
                    <th className="pb-3 font-medium">Time</th>
                    <th className="pb-3 font-medium">Severity</th>
                    <th className="pb-3 font-medium">RTU</th>
                    <th className="pb-3 font-medium">Message</th>
                    <th className="pb-3 font-medium">Value</th>
                    <th className="pb-3 font-medium">Ack By</th>
                  </tr>
                </thead>
                <tbody>
                  {history.slice(0, visibleHistoryCount).map((alarm) => (
                    <tr key={alarm.alarm_id} className="border-b border-hmi-border/50">
                      <td className="py-3 text-sm text-hmi-muted font-mono">
                        {new Date(alarm.timestamp).toLocaleString()}
                      </td>
                      <td className="py-3">
                        <span
                          className={`text-xs px-2 py-0.5 rounded font-medium ${
                            alarm.severity === 'CRITICAL' || alarm.severity === 'EMERGENCY'
                              ? 'bg-status-alarm text-white'
                              : alarm.severity === 'WARNING'
                              ? 'bg-status-warning text-white'
                              : 'bg-status-info text-white'
                          }`}
                        >
                          {alarm.severity}
                        </span>
                      </td>
                      <td className="py-3 text-sm text-hmi-text">{alarm.rtu_station}</td>
                      <td className="py-3 text-sm text-hmi-text">{alarm.message}</td>
                      <td className="py-3 text-sm text-hmi-muted font-mono">
                        {alarm.value?.toFixed(2)} / {alarm.threshold?.toFixed(2)}
                      </td>
                      <td className="py-3 text-sm text-hmi-muted">{alarm.ack_user || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {history.length > visibleHistoryCount && (
                <div className="text-center mt-4">
                  <button
                    onClick={() => setVisibleHistoryCount((prev) => prev + 50)}
                    className="px-4 py-2 bg-hmi-bg hover:bg-hmi-border text-hmi-text text-sm rounded border border-hmi-border transition-colors"
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
