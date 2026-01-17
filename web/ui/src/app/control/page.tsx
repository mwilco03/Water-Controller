'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useHMIToast } from '@/components/hmi';

const PAGE_TITLE = 'Control - Water Treatment Controller';
import { useCommandMode } from '@/contexts/CommandModeContext';
import CommandModeLogin from '@/components/CommandModeLogin';
import CoupledActionsPanel from '@/components/control/CoupledActionsPanel';
import { wsLogger, logger } from '@/lib/logger';

// Polling interval constant
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
  rtu_name?: string;  // Added for display
}

interface ConfirmAction {
  type: 'setpoint' | 'mode';
  name: string;
  description: string;
  onConfirm: () => void;
}

// Confirmation Modal Component
function ConfirmationModal({
  action,
  onCancel,
}: {
  action: ConfirmAction | null;
  onCancel: () => void;
}) {
  if (!action) return null;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-hmi-panel rounded-lg shadow-hmi-modal max-w-sm w-full border border-hmi-border">
        <div className="p-4 border-b border-hmi-border">
          <h3 className="font-semibold text-hmi-text">Confirm Change</h3>
        </div>
        <div className="p-4">
          <p className="text-sm text-hmi-text mb-1 font-medium">{action.name}</p>
          <p className="text-sm text-hmi-muted">{action.description}</p>
        </div>
        <div className="flex gap-2 p-4 pt-0 justify-end">
          <button onClick={onCancel} className="hmi-btn hmi-btn-secondary">
            Cancel
          </button>
          <button
            onClick={() => { action.onConfirm(); onCancel(); }}
            className="hmi-btn bg-status-warning hover:bg-status-warning/90 text-white"
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ControlPage() {
  const { canCommand, mode } = useCommandMode();
  const { showMessage, addToast } = useHMIToast();
  const [rtus, setRtus] = useState<RTU[]>([]);
  const [selectedRtu, setSelectedRtu] = useState<string | null>(null);
  const [pidLoops, setPidLoops] = useState<PIDLoop[]>([]);
  const [selectedLoop, setSelectedLoop] = useState<PIDLoop | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const [pendingSetpoint, setPendingSetpoint] = useState<number | null>(null);

  // Refs for cleanup and stable callbacks
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const selectedRtuRef = useRef<string | null>(null);
  const isMountedRef = useRef(true);

  // Track last setpoint change for undo
  const lastSetpointChangeRef = useRef<{
    rtuName: string;
    loopId: number;
    loopName: string;
    previousValue: number;
    newValue: number;
  } | null>(null);
  // Track last mode change for undo
  const lastModeChangeRef = useRef<{
    rtuName: string;
    loopId: number;
    loopName: string;
    previousMode: string;
    newMode: string;
  } | null>(null);

  // Keep ref in sync with state
  useEffect(() => {
    selectedRtuRef.current = selectedRtu;
  }, [selectedRtu]);

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Set page title
  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);

  // Fetch RTU list first
  const fetchRtus = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch('/api/v1/rtus', { signal });
      if (!isMountedRef.current) return;
      if (res.ok) {
        const data = await res.json();
        const rtuList = data.data || [];
        setRtus(rtuList);
        // Auto-select first RTU if none selected
        if (!selectedRtuRef.current && rtuList.length > 0) {
          setSelectedRtu(rtuList[0].station_name);
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return;
      logger.error('Error fetching RTUs', error);
    }
  }, []);

  // Fetch PID loops for selected RTU - uses ref to avoid stale closures
  const fetchControlData = useCallback(async (signal?: AbortSignal) => {
    const rtu = selectedRtuRef.current;
    if (!rtu) {
      setLoading(false);
      return;
    }

    try {
      const pidRes = await fetch(`/api/v1/rtus/${encodeURIComponent(rtu)}/pid`, { signal });
      if (!isMountedRef.current) return;

      if (pidRes.ok) {
        const data = await pidRes.json();
        const loops = (data.data || []).map((loop: PIDLoop) => ({
          ...loop,
          rtu_name: rtu,
        }));
        setPidLoops(loops);
      } else {
        setPidLoops([]);
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return;
      logger.error('Error fetching control data', error);
      setPidLoops([]);
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  // Stable polling functions using refs
  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) return; // Already polling
    pollIntervalRef.current = setInterval(() => {
      fetchControlData(abortControllerRef.current?.signal);
    }, POLL_INTERVAL_MS);
    wsLogger.info('Polling started');
  }, [fetchControlData]);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
      wsLogger.info('Polling stopped');
    }
  }, []);

  // Store callbacks in refs to avoid recreating WebSocket on every render
  const onWsConnectRef = useRef(() => {
    stopPolling();
    wsLogger.info('WebSocket connected - polling disabled');
  });
  const onWsDisconnectRef = useRef(() => {
    if (selectedRtuRef.current) {
      startPolling();
      wsLogger.info('WebSocket disconnected - polling enabled');
    }
  });

  // Update refs when callbacks change
  useEffect(() => {
    onWsConnectRef.current = () => {
      stopPolling();
      wsLogger.info('WebSocket connected - polling disabled');
    };
    onWsDisconnectRef.current = () => {
      if (selectedRtuRef.current) {
        startPolling();
        wsLogger.info('WebSocket disconnected - polling enabled');
      }
    };
  }, [startPolling, stopPolling]);

  // WebSocket for real-time control updates - use stable callback wrappers
  const { connected, subscribe } = useWebSocket({
    onConnect: useCallback(() => onWsConnectRef.current(), []),
    onDisconnect: useCallback(() => onWsDisconnectRef.current(), []),
  });

  // Subscribe to PID updates
  useEffect(() => {
    const unsubPid = subscribe('pid_update', (_, data) => {
      setPidLoops((prev) =>
        prev.map((loop) =>
          loop.id === data.loop_id
            ? { ...loop, pv: data.pv, cv: data.cv, setpoint: data.setpoint, mode: data.mode }
            : loop
        )
      );
      // Update selected loop if it matches
      setSelectedLoop((prev) =>
        prev && prev.id === data.loop_id
          ? { ...prev, pv: data.pv, cv: data.cv, setpoint: data.setpoint, mode: data.mode }
          : prev
      );
    });

    return () => {
      unsubPid();
    };
  }, [subscribe]);

  // Fetch RTUs on mount
  useEffect(() => {
    const controller = new AbortController();
    fetchRtus(controller.signal);
    return () => controller.abort();
  }, [fetchRtus]);

  // Fetch PID loops when selected RTU changes - SINGLE source of polling
  useEffect(() => {
    if (!selectedRtu) return;

    // Cancel any pending requests
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setLoading(true);
    fetchControlData(abortControllerRef.current.signal);

    // Only start polling if WebSocket is not connected
    if (!connected) {
      startPolling();
    }

    return () => {
      stopPolling();
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [selectedRtu, connected, fetchControlData, startPolling, stopPolling]);

  const doUpdateSetpoint = async (
    rtuName: string,
    loopId: number,
    setpoint: number,
    loopName: string,
    previousValue?: number,
    isUndo?: boolean
  ) => {
    try {
      const res = await fetch(`/api/v1/rtus/${encodeURIComponent(rtuName)}/pid/${loopId}/setpoint`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ setpoint }),
      });
      if (res.ok) {
        // Store the change for potential undo (only if not already an undo action)
        if (!isUndo && previousValue !== undefined) {
          lastSetpointChangeRef.current = {
            rtuName,
            loopId,
            loopName,
            previousValue,
            newValue: setpoint,
          };

          // Show toast with undo action
          addToast({
            type: 'success',
            title: `Setpoint updated to ${setpoint.toFixed(2)}`,
            message: `${loopName} - Previous: ${previousValue.toFixed(2)}`,
            duration: 8000, // Longer duration to give time for undo
            action: {
              label: 'Undo',
              onClick: () => {
                const last = lastSetpointChangeRef.current;
                if (last) {
                  doUpdateSetpoint(last.rtuName, last.loopId, last.previousValue, last.loopName, undefined, true);
                  lastSetpointChangeRef.current = null;
                }
              },
            },
          });
        } else if (isUndo) {
          showMessage('success', `Setpoint reverted to ${setpoint.toFixed(2)}`);
        } else {
          showMessage('success', `Setpoint updated to ${setpoint.toFixed(2)}`);
        }
      } else {
        showMessage('error', 'Failed to update setpoint');
      }
      fetchControlData();
    } catch (error) {
      logger.error('Error updating setpoint', error);
      showMessage('error', 'Error updating setpoint');
    }
  };

  const updateSetpoint = (rtuName: string, loopId: number, setpoint: number, loopName: string, currentValue: number) => {
    if (!canCommand) return;
    setPendingSetpoint(setpoint);
    setConfirmAction({
      type: 'setpoint',
      name: loopName,
      description: `Change setpoint from ${currentValue.toFixed(2)} to ${setpoint.toFixed(2)}?`,
      onConfirm: () => {
        doUpdateSetpoint(rtuName, loopId, setpoint, loopName, currentValue);
        setPendingSetpoint(null);
      },
    });
  };

  const doToggleMode = async (
    rtuName: string,
    loopId: number,
    pidMode: string,
    loopName: string,
    previousMode?: string,
    isUndo?: boolean
  ) => {
    try {
      const res = await fetch(`/api/v1/rtus/${encodeURIComponent(rtuName)}/pid/${loopId}/mode`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: pidMode }),
      });
      if (res.ok) {
        // Store the change for potential undo (only if not already an undo action)
        if (!isUndo && previousMode) {
          lastModeChangeRef.current = {
            rtuName,
            loopId,
            loopName,
            previousMode,
            newMode: pidMode,
          };

          // Show toast with undo action
          addToast({
            type: 'success',
            title: `PID mode changed to ${pidMode}`,
            message: `${loopName} - Previous: ${previousMode}`,
            duration: 8000,
            action: {
              label: 'Undo',
              onClick: () => {
                const last = lastModeChangeRef.current;
                if (last) {
                  doToggleMode(last.rtuName, last.loopId, last.previousMode, last.loopName, undefined, true);
                  lastModeChangeRef.current = null;
                }
              },
            },
          });
        } else if (isUndo) {
          showMessage('success', `PID mode reverted to ${pidMode}`);
        } else {
          showMessage('success', `PID mode changed to ${pidMode}`);
        }
      } else {
        showMessage('error', 'Failed to change mode');
      }
      fetchControlData();
    } catch (error) {
      logger.error('Error updating mode', error);
      showMessage('error', 'Error changing PID mode');
    }
  };

  const toggleMode = (rtuName: string, loopId: number, pidMode: string, loopName: string, currentMode: string) => {
    if (!canCommand) return;
    setConfirmAction({
      type: 'mode',
      name: loopName,
      description: `Switch PID loop from ${currentMode} to ${pidMode} mode?`,
      onConfirm: () => doToggleMode(rtuName, loopId, pidMode, loopName, currentMode),
    });
  };

  return (
    <>
      <ConfirmationModal
        action={confirmAction}
        onCancel={() => { setConfirmAction(null); setPendingSetpoint(null); }}
      />

      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-hmi-text">PID Control</h1>
            {selectedRtu && (
              <select
                value={selectedRtu}
                onChange={(e) => { setSelectedRtu(e.target.value); setSelectedLoop(null); }}
                className="text-sm bg-hmi-panel border border-hmi-border rounded px-2 py-1 text-hmi-text"
              >
                {rtus.map((rtu) => (
                  <option key={rtu.station_name} value={rtu.station_name}>
                    {rtu.station_name}
                  </option>
                ))}
              </select>
            )}
            {loading && <span className="text-xs text-hmi-muted">Loading...</span>}
          </div>
          {mode === 'view' ? (
            <CommandModeLogin showButton />
          ) : (
            <span className="text-xs px-2 py-1 rounded bg-status-ok-light text-status-ok font-medium">
              Command Mode
            </span>
          )}
        </div>

        {/* View Mode Notice - compact */}
        {mode === 'view' && (
          <div className="text-sm text-status-warning bg-status-warning-light px-3 py-2 rounded border border-status-warning/20">
            View only. Enter Command Mode to make changes.
          </div>
        )}

        {/* PID Loop Table - Data-dense layout */}
        <div className="hmi-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-hmi-bg border-b border-hmi-border">
                <th className="text-left px-3 py-2 font-medium text-hmi-muted">Loop</th>
                <th className="text-right px-3 py-2 font-medium text-hmi-muted">PV</th>
                <th className="text-right px-3 py-2 font-medium text-hmi-muted">SP</th>
                <th className="text-right px-3 py-2 font-medium text-hmi-muted">CV%</th>
                <th className="text-center px-3 py-2 font-medium text-hmi-muted">Mode</th>
                <th className="px-3 py-2 w-24"></th>
              </tr>
            </thead>
            <tbody>
              {pidLoops.map((loop) => {
                const isSelected = selectedLoop?.id === loop.id;
                const error = loop.pv !== null && loop.setpoint !== null
                  ? Math.abs(loop.pv - loop.setpoint)
                  : null;
                const hasLargeError = error !== null && error > loop.setpoint * 0.1;

                return (
                  <tr
                    key={loop.id}
                    className={`border-b border-hmi-border cursor-pointer transition-colors ${
                      isSelected ? 'bg-status-info-light' : 'hover:bg-hmi-bg'
                    }`}
                    onClick={() => setSelectedLoop(loop)}
                  >
                    <td className="px-3 py-2">
                      <div className="font-medium text-hmi-text">{loop.name}</div>
                      <div className="text-xs text-hmi-muted">{loop.process_variable}</div>
                    </td>
                    <td className={`px-3 py-2 text-right font-mono ${hasLargeError ? 'text-status-warning font-semibold' : 'text-hmi-text'}`}>
                      {loop.pv?.toFixed(2) ?? '--'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-status-info font-semibold">
                      {loop.setpoint?.toFixed(2) ?? '--'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-12 h-1.5 bg-hmi-border rounded-full overflow-hidden">
                          <div
                            className="h-full bg-status-info rounded-full"
                            style={{ width: `${Math.max(0, Math.min(100, loop.cv || 0))}%` }}
                          />
                        </div>
                        <span className="font-mono text-hmi-text w-10 text-right">
                          {loop.cv?.toFixed(0) ?? '--'}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                        loop.mode === 'AUTO' ? 'bg-status-ok-light text-status-ok-dark' :
                        loop.mode === 'MANUAL' ? 'bg-status-warning-light text-status-warning-dark' :
                        'bg-hmi-bg text-hmi-muted'
                      }`}>
                        {loop.mode}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      {isSelected && <span className="text-xs text-status-info">Selected</span>}
                    </td>
                  </tr>
                );
              })}
              {pidLoops.length === 0 && !loading && (
                <tr>
                  <td colSpan={6} className="px-3 py-8 text-center text-hmi-muted">
                    {selectedRtu ? `No PID loops for ${selectedRtu}` : 'Select an RTU'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Selected Loop Controls */}
        {selectedLoop && selectedRtu && (
          <div className="hmi-card p-4">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h2 className="font-semibold text-hmi-text">{selectedLoop.name}</h2>
                <p className="text-xs text-hmi-muted">{selectedLoop.process_variable} → {selectedLoop.control_output}</p>
              </div>

              {/* Mode Toggle */}
              <div className="flex gap-1 p-1 bg-hmi-bg rounded">
                <button
                  onClick={() => toggleMode(selectedRtu, selectedLoop.id, 'AUTO', selectedLoop.name, selectedLoop.mode)}
                  disabled={!canCommand || selectedLoop.mode === 'AUTO'}
                  className={`px-3 py-1 text-sm rounded transition-colors ${
                    selectedLoop.mode === 'AUTO'
                      ? 'bg-status-ok text-white'
                      : 'text-hmi-muted hover:text-hmi-text disabled:opacity-50'
                  }`}
                >
                  AUTO
                </button>
                <button
                  onClick={() => toggleMode(selectedRtu, selectedLoop.id, 'MANUAL', selectedLoop.name, selectedLoop.mode)}
                  disabled={!canCommand || selectedLoop.mode === 'MANUAL'}
                  className={`px-3 py-1 text-sm rounded transition-colors ${
                    selectedLoop.mode === 'MANUAL'
                      ? 'bg-status-warning text-white'
                      : 'text-hmi-muted hover:text-hmi-text disabled:opacity-50'
                  }`}
                >
                  MANUAL
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 mt-4">
              {/* Setpoint - editable */}
              <div className="col-span-2">
                <label className="text-xs text-hmi-muted block mb-1">Setpoint</label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    value={pendingSetpoint ?? selectedLoop.setpoint}
                    onChange={(e) => setPendingSetpoint(parseFloat(e.target.value))}
                    className="flex-1 bg-hmi-bg text-hmi-text rounded px-3 py-1.5 border border-hmi-border text-sm font-mono disabled:opacity-50"
                    step="0.1"
                    disabled={!canCommand}
                  />
                  {pendingSetpoint !== null && pendingSetpoint !== selectedLoop.setpoint && (
                    <button
                      onClick={() => updateSetpoint(selectedRtu, selectedLoop.id, pendingSetpoint, selectedLoop.name, selectedLoop.setpoint)}
                      className="hmi-btn hmi-btn-primary text-sm py-1"
                      disabled={!canCommand}
                    >
                      Apply
                    </button>
                  )}
                </div>
              </div>

              {/* Tuning params - read only */}
              <div>
                <label className="text-xs text-hmi-muted block mb-1">Kp</label>
                <div className="text-sm font-mono text-hmi-text">{selectedLoop.kp}</div>
              </div>
              <div>
                <label className="text-xs text-hmi-muted block mb-1">Ki</label>
                <div className="text-sm font-mono text-hmi-text">{selectedLoop.ki}</div>
              </div>
              <div>
                <label className="text-xs text-hmi-muted block mb-1">Kd</label>
                <div className="text-sm font-mono text-hmi-text">{selectedLoop.kd}</div>
              </div>
            </div>
          </div>
        )}

        {/* Coupled Actions - collapsible */}
        <details className="hmi-card">
          <summary className="px-4 py-3 cursor-pointer text-sm font-medium text-hmi-text hover:bg-hmi-bg transition-colors">
            Coupled Actions
          </summary>
          <div className="px-4 pb-4 border-t border-hmi-border pt-4">
            <CoupledActionsPanel showAll />
          </div>
        </details>
      </div>
    </>
  );
}
