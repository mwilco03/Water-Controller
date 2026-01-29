'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import Link from 'next/link';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useHMIToast } from '@/components/hmi';
import { useCommandMode } from '@/contexts/CommandModeContext';
import { logger } from '@/lib/logger';

const PAGE_TITLE = 'Control - Water Treatment Controller';
const POLL_INTERVAL_MS = 2000;
const ERROR_THRESHOLD_PCT = 10; // PV deviation from SP that triggers "alarm" highlight
const CV_MAX_PCT = 100; // Control valve max percentage

interface RTU {
  station_name: string;
  ip_address: string;
  state: string;
}

interface PIDLoop {
  id: number;
  name: string;
  enabled: boolean;
  process_variable: string;
  control_output: string;
  kp: number;
  ki: number;
  kd: number;
  setpoint: number;
  pv: number | null;
  cv: number | null;
  error: number | null;
  mode: string;
  output_min: number;
  output_max: number;
  rtu_name?: string;
}

interface AlarmSummary {
  total: number;
  critical: number;
  unack: number;
}

type FilterMode = 'all' | 'alarm' | 'manual' | 'auto';

export default function ControlPage() {
  const { canCommand, mode, enterCommandMode, exitCommandMode } = useCommandMode();
  const { showMessage } = useHMIToast();
  const [rtus, setRtus] = useState<RTU[]>([]);
  const [selectedRtu, setSelectedRtu] = useState<string | null>(null);
  const [pidLoops, setPidLoops] = useState<PIDLoop[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingLoop, setEditingLoop] = useState<number | null>(null);
  const [editValue, setEditValue] = useState<string>('');
  const [filter, setFilter] = useState<FilterMode>('all');
  const [alarmSummary, setAlarmSummary] = useState<AlarmSummary>({ total: 0, critical: 0, unack: 0 });
  const [confirmAction, setConfirmAction] = useState<{ message: string; onConfirm: () => void } | null>(null);

  // Auth dialog state
  const [showAuth, setShowAuth] = useState(false);
  const [authUser, setAuthUser] = useState('');
  const [authPass, setAuthPass] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');

  // Refs for cleanup and stable callbacks
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const selectedRtuRef = useRef<string | null>(null);
  const isMountedRef = useRef(true);
  const inputRefs = useRef<Map<number, HTMLInputElement | HTMLButtonElement>>(new Map());

  useEffect(() => { selectedRtuRef.current = selectedRtu; }, [selectedRtu]);

  useEffect(() => {
    isMountedRef.current = true;
    document.title = PAGE_TITLE;
    return () => {
      isMountedRef.current = false;
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, []);

  // Fetch alarms for banner
  const fetchAlarms = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch('/api/v1/alarms', { signal });
      if (!isMountedRef.current) return;
      if (res.ok) {
        const data = await res.json();
        const alarms = data.data || [];
        setAlarmSummary({
          total: alarms.length,
          critical: alarms.filter((a: { severity: string }) =>
            a.severity === 'CRITICAL' || a.severity === 'EMERGENCY'
          ).length,
          unack: alarms.filter((a: { state: string }) =>
            a.state === 'ACTIVE_UNACK'
          ).length,
        });
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return;
    }
  }, []);

  const fetchRtus = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch('/api/v1/rtus', { signal });
      if (!isMountedRef.current) return;
      if (res.ok) {
        const data = await res.json();
        const list = data.data || [];
        setRtus(list);
        if (!selectedRtuRef.current && list.length > 0) {
          setSelectedRtu(list[0].station_name);
        }
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return;
      logger.error('Error fetching RTUs', e);
    }
  }, []);

  const fetchControlData = useCallback(async (signal?: AbortSignal) => {
    const rtu = selectedRtuRef.current;
    if (!rtu) { setLoading(false); return; }
    try {
      const res = await fetch(`/api/v1/rtus/${encodeURIComponent(rtu)}/pid`, { signal });
      if (!isMountedRef.current) return;
      if (res.ok) {
        const data = await res.json();
        setPidLoops((data.data || []).map((loop: PIDLoop) => ({ ...loop, rtu_name: rtu })));
      } else {
        setPidLoops([]);
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return;
      logger.error('Error fetching PID data', e);
      setPidLoops([]);
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, []);

  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) return;
    pollIntervalRef.current = setInterval(() => {
      fetchControlData(abortControllerRef.current?.signal);
      fetchAlarms(abortControllerRef.current?.signal);
    }, POLL_INTERVAL_MS);
  }, [fetchControlData, fetchAlarms]);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  const onWsConnectRef = useRef(stopPolling);
  const onWsDisconnectRef = useRef(() => { if (selectedRtuRef.current) startPolling(); });
  useEffect(() => {
    onWsConnectRef.current = stopPolling;
    onWsDisconnectRef.current = () => { if (selectedRtuRef.current) startPolling(); };
  }, [startPolling, stopPolling]);

  const { connected, subscribe } = useWebSocket({
    onConnect: useCallback(() => onWsConnectRef.current(), []),
    onDisconnect: useCallback(() => onWsDisconnectRef.current(), []),
  });

  useEffect(() => {
    const unsub = subscribe('pid_update', (_, data) => {
      setPidLoops(prev => prev.map(loop =>
        loop.id === data.loop_id
          ? { ...loop, pv: data.pv, cv: data.cv, setpoint: data.setpoint, mode: data.mode }
          : loop
      ));
    });
    return unsub;
  }, [subscribe]);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchRtus(ctrl.signal);
    fetchAlarms(ctrl.signal);
    return () => ctrl.abort();
  }, [fetchRtus, fetchAlarms]);

  useEffect(() => {
    if (!selectedRtu) return;
    if (abortControllerRef.current) abortControllerRef.current.abort();
    abortControllerRef.current = new AbortController();
    setLoading(true);
    fetchControlData(abortControllerRef.current.signal);
    if (!connected) startPolling();
    return () => { stopPolling(); abortControllerRef.current?.abort(); };
  }, [selectedRtu, connected, fetchControlData, startPolling, stopPolling]);

  const handleSetpoint = async (loop: PIDLoop, newSp: number) => {
    if (!canCommand || !loop.rtu_name) return;
    try {
      const res = await fetch(`/api/v1/rtus/${encodeURIComponent(loop.rtu_name)}/pid/${loop.id}/setpoint`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ setpoint: newSp }),
      });
      if (res.ok) {
        showMessage('success', `SP → ${newSp.toFixed(1)}`);
        fetchControlData();
      } else {
        showMessage('error', 'Failed to update setpoint');
      }
    } catch {
      showMessage('error', 'Network error');
    }
  };

  const handleMode = async (loop: PIDLoop, newMode: string) => {
    if (!canCommand || !loop.rtu_name) return;
    try {
      const res = await fetch(`/api/v1/rtus/${encodeURIComponent(loop.rtu_name)}/pid/${loop.id}/mode`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: newMode }),
      });
      if (res.ok) {
        showMessage('success', `Mode → ${newMode}`);
        fetchControlData();
      } else {
        showMessage('error', 'Failed to change mode');
      }
    } catch {
      showMessage('error', 'Network error');
    }
  };

  const startEdit = (loop: PIDLoop) => {
    if (!canCommand) return;
    setEditingLoop(loop.id);
    setEditValue(loop.setpoint.toString());
  };

  const commitEdit = (loop: PIDLoop) => {
    const val = parseFloat(editValue);
    if (!isNaN(val) && val !== loop.setpoint) {
      setConfirmAction({
        message: `${loop.name}: SP ${loop.setpoint.toFixed(1)} → ${val.toFixed(1)}`,
        onConfirm: () => handleSetpoint(loop, val),
      });
    }
    setEditingLoop(null);
  };

  // Keyboard navigation (desktop only)
  const handleKeyDown = (e: React.KeyboardEvent, loop: PIDLoop, loopIndex: number) => {
    const loops = getFilteredLoops();

    if (e.key === 'ArrowDown' && loopIndex < loops.length - 1) {
      e.preventDefault();
      const nextLoop = loops[loopIndex + 1];
      inputRefs.current.get(nextLoop.id)?.focus();
    } else if (e.key === 'ArrowUp' && loopIndex > 0) {
      e.preventDefault();
      const prevLoop = loops[loopIndex - 1];
      inputRefs.current.get(prevLoop.id)?.focus();
    } else if (e.key === 'Enter' && editingLoop === loop.id) {
      commitEdit(loop);
    } else if (e.key === 'Escape') {
      setEditingLoop(null);
    } else if (e.key === 'a' && canCommand && !editingLoop) {
      e.preventDefault();
      if (loop.mode !== 'AUTO') {
        setConfirmAction({ message: `${loop.name} → AUTO`, onConfirm: () => handleMode(loop, 'AUTO') });
      }
    } else if (e.key === 'm' && canCommand && !editingLoop) {
      e.preventDefault();
      if (loop.mode !== 'MANUAL') {
        setConfirmAction({ message: `${loop.name} → MANUAL`, onConfirm: () => handleMode(loop, 'MANUAL') });
      }
    }
  };

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthLoading(true);
    setAuthError('');
    const ok = await enterCommandMode(authUser, authPass);
    setAuthLoading(false);
    if (ok) {
      setShowAuth(false);
      setAuthUser('');
      setAuthPass('');
    } else {
      setAuthError('Invalid credentials');
    }
  };

  // Filter loops
  const getFilteredLoops = useCallback(() => {
    return pidLoops.filter(loop => {
      if (filter === 'manual') return loop.mode === 'MANUAL';
      if (filter === 'auto') return loop.mode === 'AUTO';
      if (filter === 'alarm') {
        const pv = loop.pv ?? 0;
        const sp = loop.setpoint ?? 0;
        const errPct = sp > 0 ? (Math.abs(pv - sp) / sp) * 100 : 0;
        return errPct > ERROR_THRESHOLD_PCT;
      }
      return true;
    });
  }, [pidLoops, filter]);

  const filteredLoops = getFilteredLoops();
  const manualCount = pidLoops.filter(l => l.mode === 'MANUAL').length;
  const alarmLoopCount = pidLoops.filter(l => {
    const pv = l.pv ?? 0;
    const sp = l.setpoint ?? 0;
    return sp > 0 && (Math.abs(pv - sp) / sp) * 100 > ERROR_THRESHOLD_PCT;
  }).length;

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      {/* Confirm Dialog - touch friendly */}
      {confirmAction && (
        <div
          className="fixed inset-0 bg-black/30 flex items-center justify-center z-modal p-4"
          onClick={() => setConfirmAction(null)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-dialog-title"
        >
          <div className="bg-white rounded-lg shadow-lg p-4 max-w-sm w-full" onClick={e => e.stopPropagation()}>
            <p id="confirm-dialog-title" className="text-base font-medium mb-4">{confirmAction.message}</p>
            <div className="flex gap-3">
              <button onClick={() => setConfirmAction(null)} className="flex-1 px-4 py-3 text-base border rounded-lg hover:bg-gray-50 active:bg-gray-100">Cancel</button>
              <button onClick={() => { confirmAction.onConfirm(); setConfirmAction(null); }} className="flex-1 px-4 py-3 text-base bg-blue-600 text-white rounded-lg hover:bg-blue-700 active:bg-blue-800">OK</button>
            </div>
          </div>
        </div>
      )}

      {/* Auth Dialog - touch friendly */}
      {showAuth && (
        <div
          className="fixed inset-0 bg-black/30 flex items-center justify-center z-modal p-4"
          onClick={() => setShowAuth(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="auth-dialog-title"
        >
          <form onSubmit={handleAuth} className="bg-white rounded-lg shadow-lg p-4 w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div id="auth-dialog-title" className="text-base font-medium mb-4">Enter Command Mode</div>
            <input type="text" placeholder="Username" value={authUser} onChange={e => setAuthUser(e.target.value)} className="w-full border rounded-lg px-3 py-3 text-base mb-3" autoFocus />
            <input type="password" placeholder="Password" value={authPass} onChange={e => setAuthPass(e.target.value)} className="w-full border rounded-lg px-3 py-3 text-base mb-3" />
            {authError && <div className="text-sm text-red-600 mb-3">{authError}</div>}
            <div className="flex gap-3">
              <button type="button" onClick={() => setShowAuth(false)} className="flex-1 px-4 py-3 text-base border rounded-lg">Cancel</button>
              <button type="submit" disabled={authLoading} className="flex-1 px-4 py-3 text-base bg-blue-600 text-white rounded-lg disabled:opacity-50">{authLoading ? '...' : 'Login'}</button>
            </div>
          </form>
        </div>
      )}

      {/* Alarm Banner */}
      {alarmSummary.total > 0 && (
        <Link href="/alarms" className={`flex items-center justify-between px-3 sm:px-4 py-2 ${alarmSummary.critical > 0 ? 'bg-red-600 animate-pulse' : 'bg-orange-500'} text-white text-sm`}>
          <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
            <span className="w-5 h-5 flex-shrink-0 flex items-center justify-center font-bold text-lg">!</span>
            <span className="font-semibold">{alarmSummary.total} ALARM{alarmSummary.total !== 1 ? 'S' : ''}</span>
            {alarmSummary.critical > 0 && <span className="bg-white/20 px-2 py-0.5 rounded text-xs">{alarmSummary.critical} CRIT</span>}
            {alarmSummary.unack > 0 && <span className="bg-white/20 px-2 py-0.5 rounded text-xs hidden sm:inline">{alarmSummary.unack} UNACK</span>}
          </div>
          <span className="text-xs">&rarr;</span>
        </Link>
      )}

      {/* Header Bar - responsive */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between px-3 sm:px-4 py-2 border-b bg-gray-50 flex-shrink-0 gap-2">
        <div className="flex items-center gap-2 sm:gap-3">
          <h1 className="text-base font-semibold text-gray-800">PID</h1>
          <select value={selectedRtu || ''} onChange={e => setSelectedRtu(e.target.value)} className="text-sm border rounded px-2 py-1.5 bg-white flex-1 sm:flex-none min-w-0">
            {rtus.length === 0 && <option value="">No RTUs</option>}
            {rtus.map(r => <option key={r.station_name} value={r.station_name}>{r.station_name}</option>)}
          </select>
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${connected ? 'bg-green-500' : 'bg-gray-300'}`} title={connected ? 'Live' : 'Polling'} />
          {loading && <span className="text-xs text-gray-400">...</span>}

          {/* Command mode - inline on mobile */}
          <div className="sm:hidden ml-auto">
            {mode === 'command' ? (
              <button onClick={exitCommandMode} className="text-xs text-green-700 bg-green-100 px-2 py-1 rounded font-medium">CMD ✕</button>
            ) : (
              <button onClick={() => setShowAuth(true)} className="text-xs bg-orange-500 text-white px-2 py-1 rounded font-medium">CMD</button>
            )}
          </div>
        </div>

        {/* Filter + Command mode */}
        <div className="flex items-center gap-2 justify-between sm:justify-end">
          <div className="flex border rounded overflow-hidden text-xs">
            <button onClick={() => setFilter('all')} className={`px-2 sm:px-3 py-1.5 ${filter === 'all' ? 'bg-gray-200' : 'bg-white'}`}>All</button>
            <button onClick={() => setFilter('alarm')} className={`px-2 sm:px-3 py-1.5 border-l ${filter === 'alarm' ? 'bg-orange-100 text-orange-700' : 'bg-white'} ${alarmLoopCount > 0 ? 'text-orange-600 font-medium' : ''}`}>
              Err{alarmLoopCount > 0 ? ` ${alarmLoopCount}` : ''}
            </button>
            <button onClick={() => setFilter('manual')} className={`px-2 sm:px-3 py-1.5 border-l ${filter === 'manual' ? 'bg-blue-100 text-blue-700' : 'bg-white'} ${manualCount > 0 ? 'text-orange-600 font-medium' : ''}`}>
              Man{manualCount > 0 ? ` ${manualCount}` : ''}
            </button>
          </div>

          {/* Command mode - desktop */}
          <div className="hidden sm:flex items-center gap-1">
            {mode === 'command' ? (
              <>
                <span className="text-xs text-green-700 bg-green-100 px-2 py-1 rounded font-medium">CMD</span>
                <button onClick={exitCommandMode} className="text-xs text-gray-500 hover:text-gray-700 px-1">✕</button>
              </>
            ) : (
              <button onClick={() => setShowAuth(true)} className="text-xs bg-orange-500 text-white px-3 py-1.5 rounded hover:bg-orange-600 font-medium">
                Cmd Mode
              </button>
            )}
          </div>
        </div>
      </div>

      {/* PID Table - horizontal scroll on mobile */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm min-w-[400px]">
          <thead className="bg-gray-100 sticky top-0 z-10 border-b">
            <tr>
              <th className="text-left px-2 sm:px-3 py-2 font-medium text-gray-600 text-xs uppercase tracking-wide">Loop</th>
              <th className="text-right px-2 sm:px-3 py-2 font-medium text-gray-600 text-xs uppercase tracking-wide">PV</th>
              <th className="text-right px-2 sm:px-3 py-2 font-medium text-gray-600 text-xs uppercase tracking-wide">SP</th>
              <th className="text-right px-2 sm:px-3 py-2 font-medium text-gray-600 text-xs uppercase tracking-wide hidden sm:table-cell">CV%</th>
              <th className="text-center px-2 sm:px-3 py-2 font-medium text-gray-600 text-xs uppercase tracking-wide">Mode</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filteredLoops.map((loop, idx) => {
              const pv = loop.pv ?? 0;
              const sp = loop.setpoint ?? 0;
              const err = Math.abs(pv - sp);
              const errPct = sp > 0 ? (err / sp) * 100 : 0;
              const isEditing = editingLoop === loop.id;
              const inAlarm = errPct > ERROR_THRESHOLD_PCT;

              return (
                <tr
                  key={loop.id}
                  className={`${inAlarm ? 'bg-orange-50' : 'hover:bg-gray-50 active:bg-gray-100'} ${loop.mode === 'MANUAL' ? 'border-l-2 border-l-orange-400' : ''}`}
                  tabIndex={0}
                  onKeyDown={(e) => handleKeyDown(e, loop, idx)}
                >
                  <td className="px-2 sm:px-3 py-2 sm:py-1">
                    <div className="font-medium text-gray-900 text-sm">{loop.name}</div>
                    <div className="text-gray-400 text-xs hidden sm:block">{loop.process_variable}</div>
                  </td>
                  <td className={`px-2 sm:px-3 py-2 sm:py-1 text-right font-mono text-sm tabular-nums ${inAlarm ? 'text-orange-600 font-semibold' : 'text-gray-900'}`}>
                    {loop.pv?.toFixed(1) ?? '—'}
                  </td>
                  <td className="px-2 sm:px-3 py-2 sm:py-1 text-right">
                    {isEditing ? (
                      <input
                        ref={el => { if (el) inputRefs.current.set(loop.id, el); }}
                        type="number"
                        value={editValue}
                        onChange={e => setEditValue(e.target.value)}
                        onBlur={() => commitEdit(loop)}
                        onKeyDown={e => { if (e.key === 'Enter') commitEdit(loop); if (e.key === 'Escape') setEditingLoop(null); }}
                        className="w-16 sm:w-20 text-right font-mono border border-blue-400 rounded px-1 py-1 text-sm bg-blue-50"
                        autoFocus
                        step="0.1"
                      />
                    ) : (
                      <button
                        ref={el => { if (el) inputRefs.current.set(loop.id, el); }}
                        onClick={() => startEdit(loop)}
                        disabled={!canCommand}
                        className={`font-mono text-sm tabular-nums px-1 py-1 rounded ${canCommand ? 'text-blue-600 hover:bg-blue-50 active:bg-blue-100 cursor-pointer' : 'text-gray-900'}`}
                        title={canCommand ? 'Tap to edit' : 'Enter command mode first'}
                      >
                        {loop.setpoint?.toFixed(1) ?? '—'}
                      </button>
                    )}
                  </td>
                  <td className="px-2 sm:px-3 py-2 sm:py-1 text-right hidden sm:table-cell">
                    <div className="flex items-center justify-end gap-1">
                      <div className="w-8 h-1.5 bg-gray-200 rounded overflow-hidden">
                        <div className="h-full bg-blue-500 transition-all" style={{ width: `${Math.min(CV_MAX_PCT, loop.cv || 0)}%` }} />
                      </div>
                      <span className="font-mono text-xs tabular-nums text-gray-600 w-6 text-right">{loop.cv?.toFixed(0) ?? '—'}</span>
                    </div>
                  </td>
                  <td className="px-2 sm:px-3 py-2 sm:py-1">
                    <div className="flex justify-center gap-1">
                      <button
                        onClick={() => loop.mode !== 'AUTO' && canCommand && setConfirmAction({ message: `${loop.name} → AUTO`, onConfirm: () => handleMode(loop, 'AUTO') })}
                        disabled={!canCommand || loop.mode === 'AUTO'}
                        className={`w-10 sm:w-8 h-10 sm:h-auto sm:py-1 text-xs rounded-l font-medium ${loop.mode === 'AUTO' ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200 active:bg-gray-300 disabled:opacity-40'}`}
                        title="AUTO"
                      >A</button>
                      <button
                        onClick={() => loop.mode !== 'MANUAL' && canCommand && setConfirmAction({ message: `${loop.name} → MANUAL`, onConfirm: () => handleMode(loop, 'MANUAL') })}
                        disabled={!canCommand || loop.mode === 'MANUAL'}
                        className={`w-10 sm:w-8 h-10 sm:h-auto sm:py-1 text-xs rounded-r font-medium ${loop.mode === 'MANUAL' ? 'bg-orange-500 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200 active:bg-gray-300 disabled:opacity-40'}`}
                        title="MANUAL"
                      >M</button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {filteredLoops.length === 0 && !loading && (
              <tr><td colSpan={5} className="px-3 py-3 text-center text-gray-400 text-sm">
                {pidLoops.length === 0 ? 'No PID loops configured' : 'No loops match filter'}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Footer - keyboard hints (desktop only) */}
      <div className="hidden sm:flex px-4 py-1.5 bg-gray-50 border-t text-xs text-gray-500 justify-between flex-shrink-0">
        <span>↑↓ Navigate • Enter Edit SP • A/M Change Mode</span>
        <span>{pidLoops.length} loop{pidLoops.length !== 1 ? 's' : ''} • {connected ? 'Live' : 'Polling'}</span>
      </div>
    </div>
  );
}
