'use client';

/**
 * Maintenance Scheduler Component
 *
 * Allows operators to schedule future maintenance windows for alarm suppression.
 * Pre-planned maintenance reduces alarm fatigue during known work periods.
 *
 * Features:
 * - Schedule future alarm suppression windows
 * - Target specific RTU or all RTUs
 * - Work order reference for audit trail
 * - View upcoming and active maintenance windows
 * - Cancel scheduled windows
 */

import { useState, useEffect, useCallback } from 'react';
import { format, parseISO, addHours, addDays } from 'date-fns';
import { ConfirmModal } from './Modal';

interface MaintenanceWindow {
  id: number;
  rtu_station: string;
  slot: number;
  scheduled_by: string;
  scheduled_at: string;
  start_time: string;
  end_time: string;
  reason: string;
  work_order: string | null;
  status: 'SCHEDULED' | 'ACTIVE' | 'COMPLETED' | 'CANCELLED';
}

interface MaintenanceSchedulerProps {
  rtus?: { station_name: string }[];
  onScheduled?: () => void;
}

export default function MaintenanceScheduler({ rtus: propRtus, onScheduled }: MaintenanceSchedulerProps) {
  const [windows, setWindows] = useState<MaintenanceWindow[]>([]);
  const [rtus, setRtus] = useState<{ station_name: string }[]>(propRtus || []);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [windowToCancel, setWindowToCancel] = useState<MaintenanceWindow | null>(null);

  // Fetch RTUs if not provided
  useEffect(() => {
    if (propRtus && propRtus.length > 0) {
      setRtus(propRtus);
      return;
    }

    const fetchRtus = async () => {
      try {
        const response = await fetch('/api/v1/rtus');
        if (response.ok) {
          const data = await response.json();
          setRtus(data.data?.map((r: { station_name: string }) => ({ station_name: r.station_name })) || []);
        }
      } catch (err) {
        console.error('Failed to fetch RTUs:', err);
      }
    };
    fetchRtus();
  }, [propRtus]);

  // Form state
  const [formData, setFormData] = useState({
    rtu_station: '',
    slot: -1,
    start_time: '',
    end_time: '',
    reason: '',
    work_order: '',
  });

  // Preset durations for quick selection
  const presetDurations = [
    { label: '4 hours', hours: 4 },
    { label: '8 hours', hours: 8 },
    { label: '12 hours', hours: 12 },
    { label: '24 hours', hours: 24 },
  ];

  const fetchWindows = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/alarms/maintenance');
      if (response.ok) {
        const data = await response.json();
        setWindows(data.data || []);
      }
    } catch (err) {
      console.error('Failed to fetch maintenance windows:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWindows();
  }, [fetchWindows]);

  const handlePresetDuration = (hours: number) => {
    const now = new Date();
    const start = addHours(now, 1); // Start 1 hour from now
    const end = addHours(start, hours);

    setFormData(prev => ({
      ...prev,
      start_time: format(start, "yyyy-MM-dd'T'HH:mm"),
      end_time: format(end, "yyyy-MM-dd'T'HH:mm"),
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const response = await fetch('/api/v1/alarms/maintenance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rtu_station: formData.rtu_station,
          slot: formData.slot,
          start_time: new Date(formData.start_time).toISOString(),
          end_time: new Date(formData.end_time).toISOString(),
          reason: formData.reason,
          work_order: formData.work_order || null,
        }),
      });

      const data = await response.json();

      if (response.ok && data.data?.id) {
        setShowForm(false);
        setFormData({
          rtu_station: '',
          slot: -1,
          start_time: '',
          end_time: '',
          reason: '',
          work_order: '',
        });
        fetchWindows();
        onScheduled?.();
      } else {
        setError(data.data?.message || 'Failed to schedule maintenance window');
      }
    } catch (err) {
      setError('Network error - please try again');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancelClick = (window: MaintenanceWindow) => {
    setWindowToCancel(window);
  };

  const confirmCancelWindow = async () => {
    if (!windowToCancel) return;

    try {
      const response = await fetch(`/api/v1/alarms/maintenance/${windowToCancel.id}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        fetchWindows();
      }
    } catch (err) {
      console.error('Failed to cancel maintenance window:', err);
    } finally {
      setWindowToCancel(null);
    }
  };

  const formatDateTime = (isoString: string) => {
    try {
      return format(parseISO(isoString), 'MMM d, h:mm a');
    } catch {
      return isoString;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'ACTIVE':
        return 'bg-status-ok text-white';
      case 'SCHEDULED':
        return 'bg-status-info text-white';
      case 'COMPLETED':
        return 'bg-hmi-muted text-white';
      case 'CANCELLED':
        return 'bg-status-alarm/50 text-white';
      default:
        return 'bg-hmi-muted text-white';
    }
  };

  return (
    <div className="hmi-card p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="w-5 h-5 inline-flex items-center justify-center text-sm font-bold text-status-info" aria-hidden="true">[C]</span>
          <h3 className="font-semibold text-hmi-text">Maintenance Windows</h3>
          {windows.filter(w => w.status === 'ACTIVE').length > 0 && (
            <span className="px-2 py-0.5 text-xs font-medium bg-status-ok text-white rounded">
              {windows.filter(w => w.status === 'ACTIVE').length} Active
            </span>
          )}
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-3 py-1.5 bg-status-info hover:bg-status-info/90 text-white text-sm rounded font-medium transition-colors"
        >
          {showForm ? 'Cancel' : '+ Schedule'}
        </button>
      </div>

      {/* Schedule Form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="mb-4 p-4 bg-hmi-bg rounded-lg border border-hmi-border">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* RTU Selection */}
            <div>
              <label className="block text-sm text-hmi-muted mb-1">RTU Station</label>
              <select
                value={formData.rtu_station}
                onChange={(e) => setFormData(prev => ({ ...prev, rtu_station: e.target.value }))}
                className="w-full bg-hmi-panel border border-hmi-border text-hmi-text rounded px-3 py-2"
                required
              >
                <option value="">Select RTU...</option>
                {rtus.map(rtu => (
                  <option key={rtu.station_name} value={rtu.station_name}>
                    {rtu.station_name}
                  </option>
                ))}
              </select>
            </div>

            {/* Slot Selection */}
            <div>
              <label className="block text-sm text-hmi-muted mb-1">Slot (optional)</label>
              <input
                type="number"
                value={formData.slot === -1 ? '' : formData.slot}
                onChange={(e) => setFormData(prev => ({
                  ...prev,
                  slot: e.target.value === '' ? -1 : parseInt(e.target.value)
                }))}
                placeholder="All slots (-1)"
                className="w-full bg-hmi-panel border border-hmi-border text-hmi-text rounded px-3 py-2"
                min="-1"
              />
              <p className="text-xs text-hmi-muted mt-1">Leave empty or -1 for all slots</p>
            </div>

            {/* Duration Presets */}
            <div className="md:col-span-2">
              <label className="block text-sm text-hmi-muted mb-1">Quick Duration</label>
              <div className="flex gap-2">
                {presetDurations.map(preset => (
                  <button
                    key={preset.hours}
                    type="button"
                    onClick={() => handlePresetDuration(preset.hours)}
                    className="px-3 py-1 bg-hmi-panel border border-hmi-border text-hmi-text text-sm rounded hover:bg-hmi-border transition-colors"
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Start Time */}
            <div>
              <label className="block text-sm text-hmi-muted mb-1">Start Time</label>
              <input
                type="datetime-local"
                value={formData.start_time}
                onChange={(e) => setFormData(prev => ({ ...prev, start_time: e.target.value }))}
                className="w-full bg-hmi-panel border border-hmi-border text-hmi-text rounded px-3 py-2"
                required
              />
            </div>

            {/* End Time */}
            <div>
              <label className="block text-sm text-hmi-muted mb-1">End Time</label>
              <input
                type="datetime-local"
                value={formData.end_time}
                onChange={(e) => setFormData(prev => ({ ...prev, end_time: e.target.value }))}
                className="w-full bg-hmi-panel border border-hmi-border text-hmi-text rounded px-3 py-2"
                required
              />
            </div>

            {/* Reason */}
            <div className="md:col-span-2">
              <label className="block text-sm text-hmi-muted mb-1">Reason (required)</label>
              <input
                type="text"
                value={formData.reason}
                onChange={(e) => setFormData(prev => ({ ...prev, reason: e.target.value }))}
                placeholder="e.g., Contractor working on Pump 3 bearings"
                className="w-full bg-hmi-panel border border-hmi-border text-hmi-text rounded px-3 py-2"
                required
                minLength={5}
              />
            </div>

            {/* Work Order */}
            <div className="md:col-span-2">
              <label className="block text-sm text-hmi-muted mb-1">Work Order (optional)</label>
              <input
                type="text"
                value={formData.work_order}
                onChange={(e) => setFormData(prev => ({ ...prev, work_order: e.target.value }))}
                placeholder="e.g., WO-2024-0123"
                className="w-full bg-hmi-panel border border-hmi-border text-hmi-text rounded px-3 py-2"
              />
            </div>
          </div>

          {error && (
            <div className="mt-3 p-2 bg-status-alarm/10 border border-status-alarm/30 rounded text-sm text-status-alarm">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 mt-4">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="px-4 py-2 bg-hmi-panel border border-hmi-border text-hmi-text rounded hover:bg-hmi-border transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 bg-status-info hover:bg-status-info/90 text-white rounded font-medium transition-colors disabled:opacity-50"
            >
              {submitting ? 'Scheduling...' : 'Schedule Window'}
            </button>
          </div>
        </form>
      )}

      {/* Windows List */}
      {loading ? (
        <div className="text-center text-hmi-muted py-4">Loading...</div>
      ) : windows.length === 0 ? (
        <div className="text-center text-hmi-muted py-4">
          No scheduled maintenance windows
        </div>
      ) : (
        <div className="space-y-2">
          {windows.map(window => (
            <div
              key={window.id}
              className="p-3 bg-hmi-bg rounded-lg border border-hmi-border"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${getStatusBadge(window.status)}`}>
                      {window.status}
                    </span>
                    <span className="text-sm font-medium text-hmi-text">
                      {window.rtu_station}
                      {window.slot >= 0 && <span className="text-hmi-muted">:{window.slot}</span>}
                    </span>
                    {window.work_order && (
                      <span className="text-xs text-hmi-muted font-mono">
                        [{window.work_order}]
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-hmi-text mb-1">{window.reason}</p>
                  <p className="text-xs text-hmi-muted">
                    {formatDateTime(window.start_time)} - {formatDateTime(window.end_time)}
                  </p>
                </div>

                {(window.status === 'SCHEDULED' || window.status === 'ACTIVE') && (
                  <button
                    onClick={() => handleCancelClick(window)}
                    className="px-2 py-1 text-xs bg-status-alarm/20 hover:bg-status-alarm/30 text-status-alarm rounded transition-colors"
                    title="Cancel maintenance window"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Cancel Maintenance Window Confirmation */}
      <ConfirmModal
        isOpen={windowToCancel !== null}
        onClose={() => setWindowToCancel(null)}
        onConfirm={confirmCancelWindow}
        title="Cancel Maintenance Window"
        message={`Are you sure you want to cancel the maintenance window for ${windowToCancel?.rtu_station}? Alarm suppression will end immediately.`}
        confirmLabel="Cancel Window"
        cancelLabel="Keep Active"
        variant="warning"
      />
    </div>
  );
}
