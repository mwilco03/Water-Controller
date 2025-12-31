'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';

const PAGE_TITLE = 'Control - Water Treatment Controller';
import { useCommandMode } from '@/contexts/CommandModeContext';
import CommandModeLogin from '@/components/CommandModeLogin';
import CoupledActionsPanel from '@/components/control/CoupledActionsPanel';
import { wsLogger, logger } from '@/lib/logger';

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
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-hmi-panel rounded-lg p-6 max-w-md w-full mx-4 border border-hmi-border">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-status-warning/20 flex items-center justify-center">
            <svg className="w-6 h-6 text-status-warning" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-hmi-text">Confirm Control Change</h3>
        </div>

        <p className="text-hmi-muted mb-2">
          <span className="font-bold text-hmi-text">{action.name}</span>
        </p>
        <p className="text-hmi-muted mb-6">
          {action.description}
        </p>

        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 bg-hmi-border hover:bg-hmi-border/80 text-hmi-text rounded transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              action.onConfirm();
              onCancel();
            }}
            className="px-4 py-2 bg-status-warning hover:bg-status-warning/80 text-white rounded font-medium transition-colors"
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
  const [rtus, setRtus] = useState<RTU[]>([]);
  const [selectedRtu, setSelectedRtu] = useState<string | null>(null);
  const [pidLoops, setPidLoops] = useState<PIDLoop[]>([]);
  const [selectedLoop, setSelectedLoop] = useState<PIDLoop | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const [pendingSetpoint, setPendingSetpoint] = useState<number | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Set page title
  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);

  // Fetch RTU list first
  const fetchRtus = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/rtus');
      if (res.ok) {
        const data = await res.json();
        const rtuList = data.data || [];
        setRtus(rtuList);
        // Auto-select first RTU if none selected
        if (!selectedRtu && rtuList.length > 0) {
          setSelectedRtu(rtuList[0].station_name);
        }
      }
    } catch (error) {
      logger.error('Error fetching RTUs', error);
    }
  }, [selectedRtu]);

  // Fetch PID loops for selected RTU
  const fetchControlData = useCallback(async () => {
    if (!selectedRtu) {
      setLoading(false);
      return;
    }

    try {
      const pidRes = await fetch(`/api/v1/rtus/${encodeURIComponent(selectedRtu)}/pid`);

      if (pidRes.ok) {
        const data = await pidRes.json();
        const loops = (data.data || []).map((loop: PIDLoop) => ({
          ...loop,
          rtu_name: selectedRtu,
        }));
        setPidLoops(loops);
      } else {
        setPidLoops([]);
      }
    } catch (error) {
      logger.error('Error fetching control data', error);
      setPidLoops([]);
    } finally {
      setLoading(false);
    }
  }, [selectedRtu]);

  // WebSocket for real-time control updates
  const { connected, subscribe } = useWebSocket({
    onConnect: () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
        wsLogger.info('WebSocket connected - control polling disabled');
      }
    },
    onDisconnect: () => {
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(fetchControlData, 2000);
        wsLogger.info('WebSocket disconnected - control polling enabled');
      }
    },
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
    fetchRtus();
  }, [fetchRtus]);

  // Fetch PID loops when selected RTU changes
  useEffect(() => {
    if (selectedRtu) {
      setLoading(true);
      fetchControlData();
      pollIntervalRef.current = setInterval(fetchControlData, 2000);

      return () => {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
        }
      };
    }
  }, [selectedRtu, fetchControlData]);

  const doUpdateSetpoint = async (rtuName: string, loopId: number, setpoint: number) => {
    try {
      await fetch(`/api/v1/rtus/${encodeURIComponent(rtuName)}/pid/${loopId}/setpoint`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ setpoint }),
      });
      fetchControlData();
    } catch (error) {
      logger.error('Error updating setpoint', error);
    }
  };

  const updateSetpoint = (rtuName: string, loopId: number, setpoint: number, loopName: string) => {
    if (!canCommand) return;
    setPendingSetpoint(setpoint);
    setConfirmAction({
      type: 'setpoint',
      name: loopName,
      description: `Change setpoint to ${setpoint.toFixed(2)}?`,
      onConfirm: () => {
        doUpdateSetpoint(rtuName, loopId, setpoint);
        setPendingSetpoint(null);
      },
    });
  };

  const doToggleMode = async (rtuName: string, loopId: number, pidMode: string) => {
    try {
      await fetch(`/api/v1/rtus/${encodeURIComponent(rtuName)}/pid/${loopId}/mode`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: pidMode }),
      });
      fetchControlData();
    } catch (error) {
      logger.error('Error updating mode', error);
    }
  };

  const toggleMode = (rtuName: string, loopId: number, pidMode: string, loopName: string) => {
    if (!canCommand) return;
    setConfirmAction({
      type: 'mode',
      name: loopName,
      description: `Switch PID loop to ${pidMode} mode?`,
      onConfirm: () => doToggleMode(rtuName, loopId, pidMode),
    });
  };

  return (
    <>
      {/* Confirmation Modal */}
      <ConfirmationModal
        action={confirmAction}
        onCancel={() => {
          setConfirmAction(null);
          setPendingSetpoint(null);
        }}
      />

      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-hmi-text">Control System</h1>
          {mode === 'view' && <CommandModeLogin showButton />}
        </div>

      {/* Command Mode Notice */}
      {mode === 'view' && (
        <div className="flex items-center gap-3 p-4 bg-status-warning/10 border border-status-warning/30 rounded-lg">
          <svg className="w-5 h-5 text-status-warning" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-status-warning font-medium">View Mode Active</p>
            <p className="text-sm text-hmi-muted">Enter Command Mode to modify PID settings</p>
          </div>
        </div>
      )}

      {/* RTU Selector */}
      <div className="hmi-card p-4">
        <div className="flex items-center gap-4">
          <label className="text-sm text-hmi-muted">Select RTU:</label>
          <select
            value={selectedRtu || ''}
            onChange={(e) => {
              setSelectedRtu(e.target.value);
              setSelectedLoop(null);
            }}
            className="bg-hmi-panel text-hmi-text rounded px-3 py-2 min-w-[200px] border border-hmi-border"
          >
            {rtus.length === 0 && <option value="">No RTUs available</option>}
            {rtus.map((rtu) => (
              <option key={rtu.station_name} value={rtu.station_name}>
                {rtu.station_name} ({rtu.state})
              </option>
            ))}
          </select>
          {loading && (
            <span className="text-sm text-hmi-muted">Loading...</span>
          )}
        </div>
      </div>

      {/* PID Loops */}
      <div className="hmi-card p-4">
        <h2 className="text-lg font-semibold mb-4 text-hmi-text">
          PID Loops {selectedRtu && `- ${selectedRtu}`}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {pidLoops.map((loop) => (
            <div
              key={loop.id}
              className={`bg-hmi-panel rounded-lg p-4 cursor-pointer transition-colors border ${
                selectedLoop?.id === loop.id ? 'ring-2 ring-hmi-border border-hmi-border' : 'border-hmi-border'
              }`}
              onClick={() => setSelectedLoop(loop)}
            >
              <div className="flex justify-between items-start mb-3">
                <div>
                  <div className="font-medium text-hmi-text">{loop.name}</div>
                  <div className="text-xs text-hmi-muted">
                    PV: {loop.process_variable} → CV: {loop.control_output}
                  </div>
                </div>
                <span
                  className={`text-xs px-2 py-1 rounded text-white ${
                    loop.mode === 'AUTO'
                      ? 'bg-status-ok'
                      : loop.mode === 'MANUAL'
                      ? 'bg-status-warning'
                      : 'bg-hmi-border'
                  }`}
                >
                  {loop.mode}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-4 text-center">
                <div>
                  <div className="text-xs text-hmi-muted">PV</div>
                  <div className="text-lg font-bold text-hmi-text">{loop.pv?.toFixed(2) ?? '--'}</div>
                </div>
                <div>
                  <div className="text-xs text-hmi-muted">SP</div>
                  <div className="text-lg font-bold text-status-info">
                    {loop.setpoint?.toFixed(2) ?? '--'}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-hmi-muted">CV</div>
                  <div className="text-lg font-bold text-status-warning">
                    {loop.cv?.toFixed(1) ?? '--'}%
                  </div>
                </div>
              </div>

              {/* Progress bar showing CV */}
              <div className="mt-3 h-2 bg-hmi-bg rounded-full overflow-hidden">
                <div
                  className="h-full bg-status-warning transition-all duration-300"
                  style={{ width: `${Math.max(0, Math.min(100, loop.cv || 0))}%` }}
                />
              </div>
            </div>
          ))}
          {pidLoops.length === 0 && !loading && selectedRtu && (
            <div className="text-center text-hmi-muted py-8 col-span-full">
              No PID loops configured for {selectedRtu}
            </div>
          )}
          {!selectedRtu && !loading && (
            <div className="text-center text-hmi-muted py-8 col-span-full">
              Select an RTU to view PID loops
            </div>
          )}
        </div>
      </div>

      {/* Selected Loop Detail */}
      {selectedLoop && selectedRtu && (
        <div className="hmi-card p-4">
          <h2 className="text-lg font-semibold mb-4 text-hmi-text">
            {selectedLoop.name} - Tuning Parameters
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="text-xs text-hmi-muted block mb-1">Setpoint</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={pendingSetpoint ?? selectedLoop.setpoint}
                  onChange={(e) => setPendingSetpoint(parseFloat(e.target.value))}
                  className="flex-1 bg-hmi-panel text-hmi-text rounded px-3 py-2 border border-hmi-border disabled:opacity-50 disabled:cursor-not-allowed"
                  step="0.1"
                  disabled={!canCommand}
                />
                {pendingSetpoint !== null && pendingSetpoint !== selectedLoop.setpoint && (
                  <button
                    onClick={() => updateSetpoint(selectedRtu, selectedLoop.id, pendingSetpoint, selectedLoop.name)}
                    className="px-3 py-2 bg-status-info hover:bg-status-info/80 text-white rounded text-sm font-medium transition-colors"
                    disabled={!canCommand}
                  >
                    Set
                  </button>
                )}
              </div>
            </div>
            <div>
              <label className="text-xs text-hmi-muted block mb-1">Kp</label>
              <div className="bg-hmi-panel text-hmi-text rounded px-3 py-2 border border-hmi-border">
                {selectedLoop.kp}
              </div>
            </div>
            <div>
              <label className="text-xs text-hmi-muted block mb-1">Ki</label>
              <div className="bg-hmi-panel text-hmi-text rounded px-3 py-2 border border-hmi-border">
                {selectedLoop.ki}
              </div>
            </div>
            <div>
              <label className="text-xs text-hmi-muted block mb-1">Kd</label>
              <div className="bg-hmi-panel text-hmi-text rounded px-3 py-2 border border-hmi-border">
                {selectedLoop.kd}
              </div>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => toggleMode(selectedRtu, selectedLoop.id, 'AUTO', selectedLoop.name)}
              disabled={!canCommand || selectedLoop.mode === 'AUTO'}
              className={`px-4 py-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-white ${
                selectedLoop.mode === 'AUTO' ? 'bg-status-ok' : 'bg-hmi-border hover:bg-hmi-border/80'
              }`}
            >
              AUTO
            </button>
            <button
              onClick={() => toggleMode(selectedRtu, selectedLoop.id, 'MANUAL', selectedLoop.name)}
              disabled={!canCommand || selectedLoop.mode === 'MANUAL'}
              className={`px-4 py-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-white ${
                selectedLoop.mode === 'MANUAL' ? 'bg-status-warning' : 'bg-hmi-border hover:bg-hmi-border/80'
              }`}
            >
              MANUAL
            </button>
          </div>
        </div>
      )}

      {/* Coupled Actions Panel */}
      <div className="hmi-card p-4">
        <CoupledActionsPanel showAll />
      </div>
      </div>
    </>
  );
}
