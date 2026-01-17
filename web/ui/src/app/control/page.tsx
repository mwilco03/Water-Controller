'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useHMIToast } from '@/components/hmi';
import { useCommandMode } from '@/contexts/CommandModeContext';
import { wsLogger, logger } from '@/lib/logger';

const PAGE_TITLE = 'Control - Water Treatment Controller';
const POLL_INTERVAL_MS = 2000;

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

export default function ControlPage() {
  const { canCommand, mode, enterCommandMode, exitCommandMode } = useCommandMode();
  const { showMessage, addToast } = useHMIToast();
  const [rtus, setRtus] = useState<RTU[]>([]);
  const [selectedRtu, setSelectedRtu] = useState<string | null>(null);
  const [pidLoops, setPidLoops] = useState<PIDLoop[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingLoop, setEditingLoop] = useState<number | null>(null);
  const [editValue, setEditValue] = useState<string>('');
  const [confirmAction, setConfirmAction] = useState<{
    message: string;
    onConfirm: () => void;
  } | null>(null);

  // Auth dialog state
  const [showAuth, setShowAuth] = useState(false);
  const [authUser, setAuthUser] = useState('');
  const [authPass, setAuthPass] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');

  // Refs for cleanup
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const selectedRtuRef = useRef<string | null>(null);
  const isMountedRef = useRef(true);

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
    }, POLL_INTERVAL_MS);
  }, [fetchControlData]);

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
    return () => ctrl.abort();
  }, [fetchRtus]);

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
        message: `Change ${loop.name} SP: ${loop.setpoint.toFixed(1)} → ${val.toFixed(1)}?`,
        onConfirm: () => handleSetpoint(loop, val),
      });
    }
    setEditingLoop(null);
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

  return (
    <div className="p-4 max-w-5xl mx-auto">
      {/* Confirm Dialog */}
      {confirmAction && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setConfirmAction(null)}>
          <div className="bg-white rounded shadow-lg p-4 max-w-xs" onClick={e => e.stopPropagation()}>
            <p className="text-sm mb-4">{confirmAction.message}</p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setConfirmAction(null)} className="px-3 py-1 text-sm border rounded hover:bg-gray-50">Cancel</button>
              <button onClick={() => { confirmAction.onConfirm(); setConfirmAction(null); }} className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700">OK</button>
            </div>
          </div>
        </div>
      )}

      {/* Auth Dialog */}
      {showAuth && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setShowAuth(false)}>
          <form onSubmit={handleAuth} className="bg-white rounded shadow-lg p-4 w-72" onClick={e => e.stopPropagation()}>
            <div className="text-sm font-medium mb-3">Enter Command Mode</div>
            <input
              type="text"
              placeholder="Username"
              value={authUser}
              onChange={e => setAuthUser(e.target.value)}
              className="w-full border rounded px-2 py-1 text-sm mb-2"
              autoFocus
            />
            <input
              type="password"
              placeholder="Password"
              value={authPass}
              onChange={e => setAuthPass(e.target.value)}
              className="w-full border rounded px-2 py-1 text-sm mb-2"
            />
            {authError && <div className="text-xs text-red-600 mb-2">{authError}</div>}
            <div className="flex gap-2">
              <button type="button" onClick={() => setShowAuth(false)} className="flex-1 px-2 py-1 text-sm border rounded">Cancel</button>
              <button type="submit" disabled={authLoading} className="flex-1 px-2 py-1 text-sm bg-blue-600 text-white rounded disabled:opacity-50">
                {authLoading ? '...' : 'Login'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">PID Control</h1>
          <select
            value={selectedRtu || ''}
            onChange={e => setSelectedRtu(e.target.value)}
            className="text-sm border rounded px-2 py-1"
          >
            {rtus.length === 0 && <option value="">No RTUs</option>}
            {rtus.map(r => <option key={r.station_name} value={r.station_name}>{r.station_name}</option>)}
          </select>
          {loading && <span className="text-xs text-gray-400">Loading...</span>}
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-gray-300'}`} title={connected ? 'WebSocket connected' : 'Polling'} />
        </div>
        <div className="flex items-center gap-2">
          {mode === 'command' ? (
            <>
              <span className="text-xs text-green-700 bg-green-100 px-2 py-0.5 rounded">CMD</span>
              <button onClick={exitCommandMode} className="text-xs text-gray-500 hover:text-gray-700">Exit</button>
            </>
          ) : (
            <button onClick={() => setShowAuth(true)} className="text-xs bg-orange-500 text-white px-2 py-1 rounded hover:bg-orange-600">
              Command Mode
            </button>
          )}
        </div>
      </div>

      {/* PID Table */}
      <div className="border rounded overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-3 py-2 font-medium text-gray-600">Loop</th>
              <th className="text-right px-3 py-2 font-medium text-gray-600 w-24">PV</th>
              <th className="text-right px-3 py-2 font-medium text-gray-600 w-24">SP</th>
              <th className="text-right px-3 py-2 font-medium text-gray-600 w-20">CV%</th>
              <th className="text-center px-3 py-2 font-medium text-gray-600 w-28">Mode</th>
            </tr>
          </thead>
          <tbody>
            {pidLoops.map(loop => {
              const pv = loop.pv ?? 0;
              const sp = loop.setpoint ?? 0;
              const err = Math.abs(pv - sp);
              const errPct = sp > 0 ? (err / sp) * 100 : 0;
              const isEditing = editingLoop === loop.id;

              return (
                <tr key={loop.id} className="border-b last:border-b-0 hover:bg-gray-50">
                  <td className="px-3 py-2">
                    <div className="font-medium text-gray-900">{loop.name}</div>
                    <div className="text-xs text-gray-400">{loop.process_variable}</div>
                  </td>
                  <td className={`px-3 py-2 text-right font-mono tabular-nums ${errPct > 10 ? 'text-orange-600 font-semibold' : 'text-gray-900'}`}>
                    {loop.pv?.toFixed(2) ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {isEditing ? (
                      <input
                        type="number"
                        value={editValue}
                        onChange={e => setEditValue(e.target.value)}
                        onBlur={() => commitEdit(loop)}
                        onKeyDown={e => { if (e.key === 'Enter') commitEdit(loop); if (e.key === 'Escape') setEditingLoop(null); }}
                        className="w-20 text-right font-mono border rounded px-1 py-0.5 text-sm"
                        autoFocus
                        step="0.1"
                      />
                    ) : (
                      <button
                        onClick={() => startEdit(loop)}
                        disabled={!canCommand}
                        className={`font-mono tabular-nums ${canCommand ? 'text-blue-600 hover:underline cursor-pointer' : 'text-gray-900'}`}
                        title={canCommand ? 'Click to edit' : 'Enter command mode to edit'}
                      >
                        {loop.setpoint?.toFixed(2) ?? '—'}
                      </button>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <div className="w-10 h-1 bg-gray-200 rounded overflow-hidden">
                        <div className="h-full bg-blue-500" style={{ width: `${Math.min(100, loop.cv || 0)}%` }} />
                      </div>
                      <span className="font-mono tabular-nums text-gray-700 w-8 text-right">{loop.cv?.toFixed(0) ?? '—'}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex justify-center gap-1">
                      <button
                        onClick={() => loop.mode !== 'AUTO' && setConfirmAction({ message: `Set ${loop.name} to AUTO?`, onConfirm: () => handleMode(loop, 'AUTO') })}
                        disabled={!canCommand || loop.mode === 'AUTO'}
                        className={`px-2 py-0.5 text-xs rounded ${loop.mode === 'AUTO' ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200 disabled:opacity-50'}`}
                      >
                        A
                      </button>
                      <button
                        onClick={() => loop.mode !== 'MANUAL' && setConfirmAction({ message: `Set ${loop.name} to MANUAL?`, onConfirm: () => handleMode(loop, 'MANUAL') })}
                        disabled={!canCommand || loop.mode === 'MANUAL'}
                        className={`px-2 py-0.5 text-xs rounded ${loop.mode === 'MANUAL' ? 'bg-orange-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200 disabled:opacity-50'}`}
                      >
                        M
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {pidLoops.length === 0 && !loading && (
              <tr><td colSpan={5} className="px-3 py-8 text-center text-gray-400">No PID loops configured</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Loop Detail - shown when clicking a loop or for tuning info */}
      {pidLoops.length > 0 && (
        <div className="mt-4 text-xs text-gray-500 flex gap-6">
          <span>Tuning: Kp={pidLoops[0]?.kp} Ki={pidLoops[0]?.ki} Kd={pidLoops[0]?.kd}</span>
          <span>Output: {pidLoops[0]?.output_min}–{pidLoops[0]?.output_max}%</span>
        </div>
      )}
    </div>
  );
}
