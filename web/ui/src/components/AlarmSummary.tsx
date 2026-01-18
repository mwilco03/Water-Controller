'use client';

import { useState } from 'react';
import Link from 'next/link';
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

// Acknowledgment Dialog with optional operator note
function AckDialog({
  isOpen,
  alarm,
  isBulk,
  onClose,
  onConfirm,
}: {
  isOpen: boolean;
  alarm: Alarm | null;
  isBulk: boolean;
  onClose: () => void;
  onConfirm: (note: string) => void;
}) {
  const [note, setNote] = useState('');

  if (!isOpen) return null;

  const handleConfirm = () => {
    onConfirm(note);
    setNote('');
  };

  const handleClose = () => {
    setNote('');
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-hmi-panel rounded-lg p-6 max-w-md w-full mx-4 border border-hmi-border shadow-lg">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-status-info/10 flex items-center justify-center">
            <svg className="w-6 h-6 text-status-info" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-hmi-text">
            {isBulk ? 'Acknowledge All Alarms' : 'Acknowledge Alarm'}
          </h3>
        </div>

        {!isBulk && alarm && (
          <div className="mb-4 p-3 bg-hmi-bg rounded border border-hmi-border">
            <p className="text-sm text-hmi-text font-medium">{alarm.message}</p>
            <p className="text-xs text-hmi-muted mt-1">
              {alarm.rtu_station} | Slot {alarm.slot} | {alarm.severity}
            </p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="text-sm text-hmi-muted block mb-2">
              Operator Note (optional)
            </label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g., Contractor hit flow sensor during maintenance"
              className="w-full bg-hmi-bg border border-hmi-border text-hmi-text rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-status-info"
              maxLength={256}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleConfirm();
                if (e.key === 'Escape') handleClose();
              }}
            />
            <p className="text-xs text-hmi-muted mt-1">
              Note is saved to alarm history for shift handoff
            </p>
          </div>
        </div>

        <div className="flex gap-3 justify-end mt-6">
          <button
            onClick={handleClose}
            className="px-4 py-2 bg-hmi-bg hover:bg-hmi-border text-hmi-text rounded border border-hmi-border transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            className="px-4 py-2 bg-status-info hover:bg-status-info/90 text-white rounded font-medium transition-colors"
          >
            {isBulk ? 'ACK All' : 'Acknowledge'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AlarmSummary({ alarms, onShelve }: Props) {
  const [filter, setFilter] = useState<string>('all');
  const [ackDialog, setAckDialog] = useState<{
    isOpen: boolean;
    alarm: Alarm | null;
    isBulk: boolean;
  }>({ isOpen: false, alarm: null, isBulk: false });

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

  const openAckDialog = (alarm: Alarm) => {
    setAckDialog({ isOpen: true, alarm, isBulk: false });
  };

  const openBulkAckDialog = () => {
    setAckDialog({ isOpen: true, alarm: null, isBulk: true });
  };

  const closeAckDialog = () => {
    setAckDialog({ isOpen: false, alarm: null, isBulk: false });
  };

  const handleAckConfirm = async (note: string) => {
    try {
      if (ackDialog.isBulk) {
        await fetch('/api/v1/alarms/acknowledge-all', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user: 'operator', note: note || null }),
        });
      } else if (ackDialog.alarm) {
        await fetch(`/api/v1/alarms/${ackDialog.alarm.alarm_id}/acknowledge`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user: 'operator', note: note || null }),
        });
      }
      closeAckDialog();
    } catch (error) {
      alarmLogger.error('Failed to acknowledge alarm', error);
    }
  };

  return (
    <>
      <AckDialog
        isOpen={ackDialog.isOpen}
        alarm={ackDialog.alarm}
        isBulk={ackDialog.isBulk}
        onClose={closeAckDialog}
        onConfirm={handleAckConfirm}
      />
      <div className="bg-hmi-panel border border-hmi-border rounded-lg p-4 h-full">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-hmi-text">Active Alarms</h2>
          <div className="flex gap-2">
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="text-xs bg-hmi-bg text-hmi-text rounded px-2 py-1.5 border border-hmi-border"
            >
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="unack">Unacknowledged</option>
            </select>
            <button
              onClick={openBulkAckDialog}
              className="text-xs bg-status-alarm hover:bg-status-alarm/90 text-white px-3 py-1.5 rounded transition-colors font-medium"
            >
              Ack All
            </button>
          </div>
        </div>

        <div className="space-y-2 max-h-96 overflow-y-auto">
          {filteredAlarms.map((alarm) => {
            const severityClass = getSeverityClass(alarm.severity);
            const isUnack = isUnacknowledged(alarm.state);
            const bgColor = severityClass === 'critical'
              ? 'bg-status-alarm-light border-status-alarm'
              : severityClass === 'warning'
              ? 'bg-status-warning-light border-status-warning'
              : 'bg-status-info-light border-status-info';
            const badgeColor = severityClass === 'critical'
              ? 'bg-status-alarm text-white'
              : severityClass === 'warning'
              ? 'bg-status-warning text-white'
              : 'bg-status-info text-white';

            return (
              <div
                key={alarm.alarm_id}
                className={`p-3 rounded-lg border ${bgColor} ${isUnack ? 'ring-2 ring-status-alarm/50' : ''}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-xs px-2 py-0.5 rounded font-medium ${badgeColor}`}>
                        {alarm.severity}
                      </span>
                      <span className="text-xs text-hmi-muted">
                        {alarm.rtu_station}
                      </span>
                    </div>
                    <div className="text-sm text-hmi-text mb-1 truncate">{alarm.message}</div>
                    <div className="text-xs text-hmi-muted">
                      {new Date(alarm.timestamp).toLocaleString()}
                    </div>
                  </div>
                  <div className="flex gap-1 flex-shrink-0">
                    <Link
                      href={`/trends?rtu=${encodeURIComponent(alarm.rtu_station)}&slot=${alarm.slot}`}
                      className="text-xs bg-status-info hover:bg-status-info/90 text-white px-2 py-1.5 rounded transition-colors"
                      title="View sensor trend"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                      </svg>
                    </Link>
                    {onShelve && (
                      <button
                        onClick={() => onShelve(alarm)}
                        className="text-xs bg-purple-600 hover:bg-purple-700 text-white px-2 py-1.5 rounded transition-colors"
                        title="Shelve alarm"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </button>
                    )}
                    {isUnack && (
                      <button
                        onClick={() => openAckDialog(alarm)}
                        className="text-xs bg-hmi-text hover:bg-gray-700 text-white px-2 py-1.5 rounded transition-colors font-medium"
                      >
                        ACK
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
          {filteredAlarms.length === 0 && (
            <div className="text-center text-hmi-muted py-3 text-sm">
              No alarms to display
            </div>
          )}
        </div>
      </div>
    </>
  );
}
