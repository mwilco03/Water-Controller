'use client';

/**
 * Shift Handoff Component
 *
 * Provides operators with a summary view for shift handoffs.
 *
 * Features:
 * - Current system status at a glance
 * - Active alarms summary
 * - Handoff notes (persisted to localStorage)
 * - Copy-to-clipboard for quick documentation
 * - Print-friendly format
 */

import { useState, useEffect, useCallback } from 'react';
import { format } from 'date-fns';
import clsx from 'clsx';
import type { AlarmData, RTUStatusData } from '@/components/hmi';

interface ShiftHandoffProps {
  rtus: RTUStatusData[];
  alarms: AlarmData[];
  onClose?: () => void;
  isModal?: boolean;
}

interface HandoffNote {
  id: string;
  timestamp: Date;
  text: string;
  acknowledged: boolean;
}

const NOTES_STORAGE_KEY = 'wtc-shift-handoff-notes';

export function ShiftHandoff({ rtus, alarms, onClose, isModal = false }: ShiftHandoffProps) {
  const [notes, setNotes] = useState<HandoffNote[]>([]);
  const [newNote, setNewNote] = useState('');
  const [copySuccess, setCopySuccess] = useState(false);

  // Load notes from localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem(NOTES_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        // Convert timestamp strings back to Date objects
        const notesWithDates = parsed.map((n: HandoffNote & { timestamp: string }) => ({
          ...n,
          timestamp: new Date(n.timestamp),
        }));
        setNotes(notesWithDates);
      }
    } catch {
      console.error('Failed to load handoff notes');
    }
  }, []);

  // Save notes to localStorage
  const saveNotes = useCallback((updatedNotes: HandoffNote[]) => {
    try {
      localStorage.setItem(NOTES_STORAGE_KEY, JSON.stringify(updatedNotes));
      setNotes(updatedNotes);
    } catch {
      console.error('Failed to save handoff notes');
    }
  }, []);

  // Add new note
  const addNote = () => {
    if (!newNote.trim()) return;
    const note: HandoffNote = {
      id: `note-${Date.now()}`,
      timestamp: new Date(),
      text: newNote.trim(),
      acknowledged: false,
    };
    saveNotes([note, ...notes]);
    setNewNote('');
  };

  // Acknowledge note (mark as read by incoming shift)
  const acknowledgeNote = (id: string) => {
    const updated = notes.map(n => n.id === id ? { ...n, acknowledged: true } : n);
    saveNotes(updated);
  };

  // Delete old notes (older than 24 hours and acknowledged)
  const cleanupOldNotes = () => {
    const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000);
    const filtered = notes.filter(n => !n.acknowledged || n.timestamp > cutoff);
    saveNotes(filtered);
  };

  // Calculate summary stats
  const onlineRtus = rtus.filter(r => r.state === 'RUNNING').length;
  const faultedRtus = rtus.filter(r => r.state === 'FAULT' || r.state === 'ERROR').length;
  const activeAlarms = alarms.filter(a => a.state !== 'CLEARED');
  const unackedAlarms = activeAlarms.filter(a => a.state === 'ACTIVE');
  const criticalAlarms = activeAlarms.filter(a => a.severity === 'CRITICAL');

  // Generate handoff summary text
  const generateSummaryText = () => {
    const now = new Date();
    const lines = [
      '=== SHIFT HANDOFF SUMMARY ===',
      `Generated: ${format(now, 'yyyy-MM-dd HH:mm:ss')}`,
      '',
      '--- SYSTEM STATUS ---',
      `RTUs: ${onlineRtus}/${rtus.length} Online${faultedRtus > 0 ? `, ${faultedRtus} FAULTED` : ''}`,
      `Alarms: ${activeAlarms.length} Active (${unackedAlarms.length} Unacknowledged)`,
      criticalAlarms.length > 0 ? `CRITICAL ALARMS: ${criticalAlarms.length}` : '',
      '',
    ];

    if (activeAlarms.length > 0) {
      lines.push('--- ACTIVE ALARMS ---');
      activeAlarms.forEach(a => {
        lines.push(`[${a.severity || 'HIGH'}] ${a.rtu_station}: ${a.message} (${a.state})`);
      });
      lines.push('');
    }

    const unackedNotes = notes.filter(n => !n.acknowledged);
    if (unackedNotes.length > 0) {
      lines.push('--- HANDOFF NOTES ---');
      unackedNotes.forEach(n => {
        lines.push(`[${format(n.timestamp, 'HH:mm')}] ${n.text}`);
      });
      lines.push('');
    }

    lines.push('=== END OF SUMMARY ===');
    return lines.filter(l => l !== '').join('\n');
  };

  // Copy summary to clipboard
  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(generateSummaryText());
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch {
      console.error('Failed to copy to clipboard');
    }
  };

  // Print summary
  const printSummary = () => {
    const printWindow = window.open('', '_blank');
    if (printWindow) {
      printWindow.document.write(`
        <html>
          <head>
            <title>Shift Handoff Summary</title>
            <style>
              body { font-family: monospace; padding: 20px; }
              pre { white-space: pre-wrap; }
            </style>
          </head>
          <body>
            <pre>${generateSummaryText()}</pre>
          </body>
        </html>
      `);
      printWindow.document.close();
      printWindow.print();
    }
  };

  const Container = isModal ? 'div' : 'details';
  const containerProps = isModal ? {} : { open: true };

  return (
    <Container
      {...containerProps}
      className={clsx(
        'hmi-card overflow-hidden',
        isModal && 'max-h-[80vh] flex flex-col'
      )}
    >
      {/* Header */}
      {!isModal && (
        <summary className="p-4 cursor-pointer bg-hmi-bg border-b border-hmi-border hover:bg-hmi-border/30 transition-colors list-none">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="w-5 h-5 flex items-center justify-center text-status-info font-bold text-sm">[H]</span>
              <span className="font-semibold text-hmi-text">Shift Handoff</span>
            </div>
            <div className="flex items-center gap-2 text-sm text-hmi-muted">
              <span>{format(new Date(), 'HH:mm')}</span>
              {notes.filter(n => !n.acknowledged).length > 0 && (
                <span className="px-2 py-0.5 bg-status-warning text-white rounded-full text-xs font-bold">
                  {notes.filter(n => !n.acknowledged).length} notes
                </span>
              )}
            </div>
          </div>
        </summary>
      )}

      {isModal && (
        <div className="p-4 border-b border-hmi-border bg-hmi-bg flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="w-5 h-5 flex items-center justify-center text-status-info font-bold text-sm">[H]</span>
            <span className="font-semibold text-hmi-text">Shift Handoff Summary</span>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="p-2 hover:bg-hmi-border/50 rounded-lg transition-colors text-hmi-muted font-bold"
              aria-label="Close"
            >
              X
            </button>
          )}
        </div>
      )}

      <div className={clsx('p-4 space-y-4', isModal && 'flex-1 overflow-y-auto')}>
        {/* Quick Status Summary */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="text-center p-3 bg-hmi-bg rounded-lg">
            <div className={clsx(
              'text-2xl font-bold font-mono',
              faultedRtus > 0 ? 'text-status-alarm' : 'text-hmi-text'
            )}>
              {onlineRtus}/{rtus.length}
            </div>
            <div className="text-xs text-hmi-muted">RTUs Online</div>
          </div>
          <div className="text-center p-3 bg-hmi-bg rounded-lg">
            <div className={clsx(
              'text-2xl font-bold font-mono',
              criticalAlarms.length > 0 ? 'text-status-alarm animate-pulse' : activeAlarms.length > 0 ? 'text-status-warning' : 'text-hmi-text'
            )}>
              {activeAlarms.length}
            </div>
            <div className="text-xs text-hmi-muted">Active Alarms</div>
          </div>
          <div className="text-center p-3 bg-hmi-bg rounded-lg">
            <div className={clsx(
              'text-2xl font-bold font-mono',
              unackedAlarms.length > 0 ? 'text-status-alarm' : 'text-hmi-text'
            )}>
              {unackedAlarms.length}
            </div>
            <div className="text-xs text-hmi-muted">Unacked Alarms</div>
          </div>
          <div className="text-center p-3 bg-hmi-bg rounded-lg">
            <div className="text-2xl font-bold font-mono text-hmi-text">
              {format(new Date(), 'HH:mm')}
            </div>
            <div className="text-xs text-hmi-muted">{format(new Date(), 'MMM dd')}</div>
          </div>
        </div>

        {/* Critical Alarms Warning */}
        {criticalAlarms.length > 0 && (
          <div className="p-3 bg-status-alarm-light border border-status-alarm rounded-lg">
            <div className="flex items-center gap-2 font-semibold text-status-alarm-dark mb-2">
              <span className="w-5 h-5 flex items-center justify-center bg-status-alarm text-white rounded text-xs font-bold">!</span>
              {criticalAlarms.length} CRITICAL ALARM{criticalAlarms.length > 1 ? 'S' : ''}
            </div>
            {criticalAlarms.slice(0, 3).map(alarm => (
              <div key={alarm.alarm_id} className="text-sm text-hmi-text py-1">
                <span className="font-medium">{alarm.rtu_station}:</span> {alarm.message}
              </div>
            ))}
          </div>
        )}

        {/* Handoff Notes */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-hmi-text">Handoff Notes</h3>
            {notes.some(n => n.acknowledged) && (
              <button
                onClick={cleanupOldNotes}
                className="text-xs text-hmi-muted hover:text-hmi-text transition-colors"
              >
                Clear old notes
              </button>
            )}
          </div>

          {/* Add note input */}
          <div className="flex gap-2 mb-3">
            <input
              type="text"
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addNote()}
              placeholder="Add a note for incoming shift..."
              className="flex-1 px-3 py-2 bg-hmi-bg border border-hmi-border rounded-lg text-hmi-text placeholder-hmi-muted focus:outline-none focus:ring-2 focus:ring-status-info"
            />
            <button
              onClick={addNote}
              disabled={!newNote.trim()}
              className="px-4 py-2 bg-status-info text-white rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:bg-status-info/90 transition-colors min-h-touch"
            >
              Add
            </button>
          </div>

          {/* Notes list */}
          {notes.length > 0 ? (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {notes.map(note => (
                <div
                  key={note.id}
                  className={clsx(
                    'p-3 rounded-lg border flex items-start gap-3',
                    note.acknowledged
                      ? 'bg-hmi-bg border-hmi-border opacity-60'
                      : 'bg-status-warning-light border-status-warning'
                  )}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-hmi-muted mb-1">
                      {format(note.timestamp, 'HH:mm')} - {format(note.timestamp, 'MMM dd')}
                    </div>
                    <div className="text-sm text-hmi-text">{note.text}</div>
                  </div>
                  {!note.acknowledged && (
                    <button
                      onClick={() => acknowledgeNote(note.id)}
                      className="shrink-0 px-2 py-1 text-xs bg-status-ok text-white rounded hover:bg-status-ok/90 transition-colors"
                      title="Mark as read"
                    >
                      ACK
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-hmi-muted text-center py-4">
              No handoff notes. Add notes for the incoming shift above.
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2 pt-2 border-t border-hmi-border">
          <button
            onClick={copyToClipboard}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors min-h-touch',
              copySuccess
                ? 'bg-status-ok text-white'
                : 'bg-hmi-bg border border-hmi-border text-hmi-text hover:bg-hmi-border/50'
            )}
          >
            {copySuccess ? (
              <>
                <span className="text-sm font-bold">[OK]</span>
                Copied!
              </>
            ) : (
              <>
                <span className="text-sm font-bold">[=]</span>
                Copy Summary
              </>
            )}
          </button>
          <button
            onClick={printSummary}
            className="flex items-center gap-2 px-4 py-2 bg-hmi-bg border border-hmi-border text-hmi-text rounded-lg font-medium hover:bg-hmi-border/50 transition-colors min-h-touch"
          >
            <span className="text-sm font-bold">[P]</span>
            Print
          </button>
        </div>
      </div>
    </Container>
  );
}

export default ShiftHandoff;
