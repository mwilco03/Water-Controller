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
              <svg className="w-5 h-5 text-status-info" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
              </svg>
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
            <svg className="w-5 h-5 text-status-info" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
            </svg>
            <span className="font-semibold text-hmi-text">Shift Handoff Summary</span>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="p-2 hover:bg-hmi-border/50 rounded-lg transition-colors"
              aria-label="Close"
            >
              <svg className="w-5 h-5 text-hmi-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
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
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
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
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                Copied!
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Copy Summary
              </>
            )}
          </button>
          <button
            onClick={printSummary}
            className="flex items-center gap-2 px-4 py-2 bg-hmi-bg border border-hmi-border text-hmi-text rounded-lg font-medium hover:bg-hmi-border/50 transition-colors min-h-touch"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
            </svg>
            Print
          </button>
        </div>
      </div>
    </Container>
  );
}

export default ShiftHandoff;
