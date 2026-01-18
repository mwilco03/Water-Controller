'use client';

/**
 * AlarmSummary - Grouped alarm display with expand/collapse
 *
 * Design principles:
 * - Default grouped by condition (message) to surface nuisance alarms
 * - Show occurrence count prominently ("fired 42 times")
 * - Click to expand and see individual instances
 * - One-click ack for authenticated users
 */

import { useState, useMemo } from 'react';
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
  /** If true, skip the ack dialog and ack immediately */
  quickAck?: boolean;
}

interface AlarmGroup {
  key: string;
  message: string;
  rtuStation: string;
  slot: number;
  severity: string;
  alarms: Alarm[];
  firstTimestamp: string;
  lastTimestamp: string;
  hasUnack: boolean;
}

// Acknowledgment Dialog with optional operator note
function AckDialog({
  isOpen,
  alarm,
  isBulk,
  groupCount,
  onClose,
  onConfirm,
}: {
  isOpen: boolean;
  alarm: Alarm | null;
  isBulk: boolean;
  groupCount?: number;
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

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      handleClose();
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-modal"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="ack-dialog-title"
    >
      <div className="bg-hmi-panel rounded-lg p-4 max-w-md w-full mx-4 border border-hmi-border shadow-lg" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-3 mb-3">
          <span className="text-xl">&#10003;</span>
          <h3 id="ack-dialog-title" className="font-semibold text-hmi-text">
            {isBulk ? 'Acknowledge All Alarms' : groupCount && groupCount > 1 ? `Acknowledge ${groupCount} Alarms` : 'Acknowledge Alarm'}
          </h3>
        </div>

        {!isBulk && alarm && (
          <div className="mb-3 p-2 bg-hmi-bg rounded border border-hmi-border">
            <p className="text-sm text-hmi-text font-medium">{alarm.message}</p>
            <p className="text-xs text-hmi-muted mt-1">
              {alarm.rtu_station} | Slot {alarm.slot} | {alarm.severity}
            </p>
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="text-sm text-hmi-muted block mb-1">
              Operator Note (optional)
            </label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g., Sensor maintenance in progress"
              className="w-full bg-hmi-bg border border-hmi-border text-hmi-text rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-status-info"
              maxLength={256}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleConfirm();
                if (e.key === 'Escape') handleClose();
              }}
            />
          </div>
        </div>

        <div className="flex gap-2 justify-end mt-4">
          <button
            onClick={handleClose}
            className="px-3 py-1.5 bg-hmi-bg hover:bg-hmi-border text-hmi-text rounded border border-hmi-border text-sm transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            className="px-3 py-1.5 bg-status-info hover:bg-status-info/90 text-white rounded text-sm font-medium transition-colors"
          >
            {isBulk ? 'ACK All' : 'Acknowledge'}
          </button>
        </div>
      </div>
    </div>
  );
}

// Individual alarm row (shown when group is expanded)
function AlarmRow({
  alarm,
  onAck,
  onShelve,
}: {
  alarm: Alarm;
  onAck?: () => void;
  onShelve?: () => void;
}) {
  const isUnack = alarm.state === 'ACTIVE_UNACK' || alarm.state === 'CLEARED_UNACK';

  return (
    <div className="flex items-center justify-between py-2 px-3 bg-hmi-bg/50 rounded text-sm">
      <div className="flex items-center gap-3">
        <span className="text-xs text-hmi-muted font-mono">
          {new Date(alarm.timestamp).toLocaleTimeString()}
        </span>
        {alarm.value !== undefined && (
          <span className="text-xs text-hmi-muted">
            {alarm.value.toFixed(1)} / {alarm.threshold?.toFixed(1)}
          </span>
        )}
      </div>
      <div className="flex gap-1">
        {onShelve && (
          <button
            onClick={onShelve}
            className="text-xs px-2 py-1 text-hmi-muted hover:text-hmi-text transition-colors"
            title="Shelve"
          >
            🕐
          </button>
        )}
        {isUnack && onAck && (
          <button
            onClick={onAck}
            className="text-xs bg-hmi-text hover:bg-gray-700 text-white px-2 py-1 rounded transition-colors"
          >
            ACK
          </button>
        )}
      </div>
    </div>
  );
}

// Grouped alarm card
function AlarmGroupCard({
  group,
  isExpanded,
  onToggle,
  onAck,
  onAckGroup,
  onShelve,
}: {
  group: AlarmGroup;
  isExpanded: boolean;
  onToggle: () => void;
  onAck: (alarm: Alarm) => void;
  onAckGroup: (group: AlarmGroup) => void;
  onShelve?: (alarm: Alarm) => void;
}) {
  const severityClass = getSeverityClass(group.severity);
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

  const count = group.alarms.length;
  const unackCount = group.alarms.filter(a => a.state === 'ACTIVE_UNACK' || a.state === 'CLEARED_UNACK').length;

  return (
    <div className={`rounded-lg border ${bgColor} ${group.hasUnack ? 'ring-2 ring-status-alarm/30' : ''}`}>
      {/* Group header - always visible */}
      <div className="p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${badgeColor}`}>
                {group.severity}
              </span>
              <span className="text-xs text-hmi-muted">
                {group.rtuStation} · Slot {group.slot}
              </span>
              {count > 1 && (
                <span className="text-xs font-medium text-status-alarm bg-status-alarm/10 px-2 py-0.5 rounded">
                  ×{count} occurrences
                </span>
              )}
            </div>
            <div className="text-sm text-hmi-text font-medium truncate">{group.message}</div>
            <div className="text-xs text-hmi-muted mt-1">
              {count > 1 ? (
                <>First: {new Date(group.firstTimestamp).toLocaleString()} · Last: {new Date(group.lastTimestamp).toLocaleString()}</>
              ) : (
                new Date(group.firstTimestamp).toLocaleString()
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1 flex-shrink-0">
            <Link
              href={`/trends?rtu=${encodeURIComponent(group.rtuStation)}&slot=${group.slot}`}
              className="text-xs px-2 py-1.5 text-status-info hover:bg-status-info/10 rounded transition-colors"
              title="View trend"
            >
              📈
            </Link>
            {onShelve && (
              <button
                onClick={() => onShelve(group.alarms[0])}
                className="text-xs px-2 py-1.5 text-hmi-muted hover:bg-hmi-bg rounded transition-colors"
                title="Shelve"
              >
                🕐
              </button>
            )}
            {unackCount > 0 && (
              <button
                onClick={() => onAckGroup(group)}
                className="text-xs bg-hmi-text hover:bg-gray-700 text-white px-2 py-1.5 rounded transition-colors font-medium"
                title={count > 1 ? `Acknowledge all ${unackCount} unacked` : 'Acknowledge'}
              >
                ACK{unackCount > 1 && ` (${unackCount})`}
              </button>
            )}
          </div>
        </div>

        {/* Expand/collapse for groups with multiple alarms */}
        {count > 1 && (
          <button
            onClick={onToggle}
            className="mt-2 text-xs text-hmi-muted hover:text-hmi-text flex items-center gap-1 transition-colors"
          >
            <span>{isExpanded ? '▼' : '▶'}</span>
            <span>{isExpanded ? 'Hide' : 'Show'} {count} occurrences</span>
          </button>
        )}
      </div>

      {/* Expanded view - individual alarms */}
      {isExpanded && count > 1 && (
        <div className="border-t border-hmi-border/50 p-2 space-y-1">
          {group.alarms.map((alarm) => (
            <AlarmRow
              key={alarm.alarm_id}
              alarm={alarm}
              onAck={() => onAck(alarm)}
              onShelve={onShelve ? () => onShelve(alarm) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function getSeverityClass(severity: string): 'critical' | 'warning' | 'info' {
  switch (severity.toLowerCase()) {
    case 'critical':
    case 'emergency':
      return 'critical';
    case 'warning':
      return 'warning';
    default:
      return 'info';
  }
}

export default function AlarmSummary({ alarms, onShelve, quickAck = false }: Props) {
  const [filter, setFilter] = useState<'all' | 'unack' | 'active'>('all');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [ackDialog, setAckDialog] = useState<{
    isOpen: boolean;
    alarm: Alarm | null;
    isBulk: boolean;
    groupCount?: number;
  }>({ isOpen: false, alarm: null, isBulk: false });

  // Group alarms by condition (rtu_station + slot + message)
  const groupedAlarms = useMemo(() => {
    const groups = new Map<string, AlarmGroup>();

    alarms.forEach(alarm => {
      const key = `${alarm.rtu_station}-${alarm.slot}-${alarm.message}`;

      if (!groups.has(key)) {
        groups.set(key, {
          key,
          message: alarm.message,
          rtuStation: alarm.rtu_station,
          slot: alarm.slot,
          severity: alarm.severity,
          alarms: [],
          firstTimestamp: alarm.timestamp,
          lastTimestamp: alarm.timestamp,
          hasUnack: false,
        });
      }

      const group = groups.get(key)!;
      group.alarms.push(alarm);

      // Update timestamps
      if (new Date(alarm.timestamp) < new Date(group.firstTimestamp)) {
        group.firstTimestamp = alarm.timestamp;
      }
      if (new Date(alarm.timestamp) > new Date(group.lastTimestamp)) {
        group.lastTimestamp = alarm.timestamp;
      }

      // Check for unack
      if (alarm.state === 'ACTIVE_UNACK' || alarm.state === 'CLEARED_UNACK') {
        group.hasUnack = true;
      }

      // Use highest severity in group
      const currentSeverityRank = getSeverityRank(group.severity);
      const alarmSeverityRank = getSeverityRank(alarm.severity);
      if (alarmSeverityRank > currentSeverityRank) {
        group.severity = alarm.severity;
      }
    });

    // Convert to array and sort by: hasUnack first, then severity, then lastTimestamp
    return Array.from(groups.values()).sort((a, b) => {
      if (a.hasUnack !== b.hasUnack) return a.hasUnack ? -1 : 1;
      const severityDiff = getSeverityRank(b.severity) - getSeverityRank(a.severity);
      if (severityDiff !== 0) return severityDiff;
      return new Date(b.lastTimestamp).getTime() - new Date(a.lastTimestamp).getTime();
    });
  }, [alarms]);

  // Filter groups
  const filteredGroups = useMemo(() => {
    return groupedAlarms.filter(group => {
      if (filter === 'unack') return group.hasUnack;
      if (filter === 'active') return group.alarms.some(a => a.state.includes('ACTIVE'));
      return true;
    });
  }, [groupedAlarms, filter]);

  const toggleGroup = (key: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleAck = async (alarm: Alarm, note: string = '') => {
    try {
      await fetch(`/api/v1/alarms/${alarm.alarm_id}/acknowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: 'operator', note: note || null }),
      });
    } catch (error) {
      alarmLogger.error('Failed to acknowledge alarm', error);
    }
  };

  const handleAckGroup = async (group: AlarmGroup, note: string = '') => {
    try {
      // Ack all unacknowledged alarms in the group
      const unackAlarms = group.alarms.filter(a => a.state === 'ACTIVE_UNACK' || a.state === 'CLEARED_UNACK');
      await Promise.all(
        unackAlarms.map(alarm =>
          fetch(`/api/v1/alarms/${alarm.alarm_id}/acknowledge`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user: 'operator', note: note || null }),
          })
        )
      );
    } catch (error) {
      alarmLogger.error('Failed to acknowledge alarm group', error);
    }
  };

  const handleAckAll = async (note: string = '') => {
    try {
      await fetch('/api/v1/alarms/acknowledge-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: 'operator', note: note || null }),
      });
    } catch (error) {
      alarmLogger.error('Failed to acknowledge all alarms', error);
    }
  };

  const openAckDialog = (alarm: Alarm) => {
    if (quickAck) {
      handleAck(alarm);
    } else {
      setAckDialog({ isOpen: true, alarm, isBulk: false });
    }
  };

  const openGroupAckDialog = (group: AlarmGroup) => {
    const unackCount = group.alarms.filter(a => a.state === 'ACTIVE_UNACK' || a.state === 'CLEARED_UNACK').length;
    if (quickAck || unackCount === 1) {
      handleAckGroup(group);
    } else {
      setAckDialog({ isOpen: true, alarm: group.alarms[0], isBulk: false, groupCount: unackCount });
    }
  };

  const openBulkAckDialog = () => {
    if (quickAck) {
      handleAckAll();
    } else {
      setAckDialog({ isOpen: true, alarm: null, isBulk: true });
    }
  };

  const closeAckDialog = () => {
    setAckDialog({ isOpen: false, alarm: null, isBulk: false });
  };

  const handleAckConfirm = async (note: string) => {
    if (ackDialog.isBulk) {
      await handleAckAll(note);
    } else if (ackDialog.groupCount && ackDialog.groupCount > 1 && ackDialog.alarm) {
      // Find the group and ack all
      const group = groupedAlarms.find(g => g.alarms.some(a => a.alarm_id === ackDialog.alarm!.alarm_id));
      if (group) {
        await handleAckGroup(group, note);
      }
    } else if (ackDialog.alarm) {
      await handleAck(ackDialog.alarm, note);
    }
    closeAckDialog();
  };

  const totalAlarms = alarms.length;
  const totalUnack = alarms.filter(a => a.state === 'ACTIVE_UNACK' || a.state === 'CLEARED_UNACK').length;

  return (
    <>
      <AckDialog
        isOpen={ackDialog.isOpen}
        alarm={ackDialog.alarm}
        isBulk={ackDialog.isBulk}
        groupCount={ackDialog.groupCount}
        onClose={closeAckDialog}
        onConfirm={handleAckConfirm}
      />

      <div className="bg-hmi-panel border border-hmi-border rounded-lg p-4">
        {/* Header with filter and bulk ack */}
        <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
          <h2 className="font-semibold text-hmi-text">
            Active Alarms
            <span className="text-hmi-muted font-normal ml-2">
              ({filteredGroups.length} {filteredGroups.length === 1 ? 'condition' : 'conditions'}, {totalAlarms} total)
            </span>
          </h2>
          <div className="flex gap-2">
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as typeof filter)}
              className="text-xs bg-hmi-bg text-hmi-text rounded px-2 py-1.5 border border-hmi-border"
            >
              <option value="all">All ({groupedAlarms.length})</option>
              <option value="unack">Unacked ({groupedAlarms.filter(g => g.hasUnack).length})</option>
              <option value="active">Active only</option>
            </select>
            {totalUnack > 0 && (
              <button
                onClick={openBulkAckDialog}
                className="text-xs bg-status-alarm hover:bg-status-alarm/90 text-white px-3 py-1.5 rounded transition-colors font-medium"
              >
                ACK All ({totalUnack})
              </button>
            )}
          </div>
        </div>

        {/* Grouped alarm list */}
        <div className="space-y-2 max-h-[500px] overflow-y-auto">
          {filteredGroups.map((group) => (
            <AlarmGroupCard
              key={group.key}
              group={group}
              isExpanded={expandedGroups.has(group.key)}
              onToggle={() => toggleGroup(group.key)}
              onAck={openAckDialog}
              onAckGroup={openGroupAckDialog}
              onShelve={onShelve}
            />
          ))}
          {filteredGroups.length === 0 && (
            <div className="text-center text-hmi-muted py-6 text-sm">
              {filter === 'all' ? 'No active alarms' : 'No alarms matching filter'}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function getSeverityRank(severity: string): number {
  switch (severity.toLowerCase()) {
    case 'emergency':
      return 5;
    case 'critical':
      return 4;
    case 'high':
      return 3;
    case 'warning':
      return 2;
    case 'low':
      return 1;
    default:
      return 0;
  }
}
