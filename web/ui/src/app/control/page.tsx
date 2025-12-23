'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useCommandMode } from '@/contexts/CommandModeContext';
import CommandModeLogin from '@/components/CommandModeLogin';

interface PIDLoop {
  loop_id: number;
  name: string;
  enabled: boolean;
  input_rtu: string;
  input_slot: number;
  output_rtu: string;
  output_slot: number;
  kp: number;
  ki: number;
  kd: number;
  setpoint: number;
  pv: number;
  cv: number;
  mode: string;
}

interface Interlock {
  interlock_id: number;
  name: string;
  enabled: boolean;
  tripped: boolean;
  condition_rtu: string;
  condition_slot: number;
  threshold: number;
}

interface ConfirmAction {
  type: 'setpoint' | 'mode' | 'interlock';
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
      <div className="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4 border border-gray-600">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-yellow-600/20 flex items-center justify-center">
            <svg className="w-6 h-6 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-white">
            {action.type === 'interlock' ? 'Confirm Interlock Reset' : 'Confirm Control Change'}
          </h3>
        </div>

        <p className="text-gray-300 mb-2">
          <span className="font-bold text-white">{action.name}</span>
        </p>
        <p className="text-gray-300 mb-6">
          {action.description}
        </p>

        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              action.onConfirm();
              onCancel();
            }}
            className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-white rounded font-medium transition-colors"
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
  const [pidLoops, setPidLoops] = useState<PIDLoop[]>([]);
  const [interlocks, setInterlocks] = useState<Interlock[]>([]);
  const [selectedLoop, setSelectedLoop] = useState<PIDLoop | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const [pendingSetpoint, setPendingSetpoint] = useState<number | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchControlData = useCallback(async () => {
    try {
      const [pidRes, interlockRes] = await Promise.all([
        fetch('/api/v1/control/pid'),
        fetch('/api/v1/control/interlocks'),
      ]);

      if (pidRes.ok) {
        const data = await pidRes.json();
        setPidLoops(data.loops || []);
      }

      if (interlockRes.ok) {
        const data = await interlockRes.json();
        setInterlocks(data.interlocks || []);
      }
    } catch (error) {
      console.error('Error fetching control data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  // WebSocket for real-time control updates
  const { connected, subscribe } = useWebSocket({
    onConnect: () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
        console.log('WebSocket connected - control polling disabled');
      }
    },
    onDisconnect: () => {
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(fetchControlData, 2000);
        console.log('WebSocket disconnected - control polling enabled');
      }
    },
  });

  // Subscribe to PID and interlock updates
  useEffect(() => {
    const unsubPid = subscribe('pid_update', (_, data) => {
      setPidLoops((prev) =>
        prev.map((loop) =>
          loop.loop_id === data.loop_id
            ? { ...loop, pv: data.pv, cv: data.cv, setpoint: data.setpoint, mode: data.mode }
            : loop
        )
      );
      // Update selected loop if it matches
      setSelectedLoop((prev) =>
        prev && prev.loop_id === data.loop_id
          ? { ...prev, pv: data.pv, cv: data.cv, setpoint: data.setpoint, mode: data.mode }
          : prev
      );
    });

    const unsubInterlock = subscribe('interlock_update', (_, data) => {
      setInterlocks((prev) =>
        prev.map((il) =>
          il.interlock_id === data.interlock_id
            ? { ...il, tripped: data.tripped }
            : il
        )
      );
    });

    return () => {
      unsubPid();
      unsubInterlock();
    };
  }, [subscribe]);

  // Initial fetch and polling setup
  useEffect(() => {
    fetchControlData();
    pollIntervalRef.current = setInterval(fetchControlData, 2000);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [fetchControlData]);

  const doUpdateSetpoint = async (loopId: number, setpoint: number) => {
    try {
      await fetch(`/api/v1/control/pid/${loopId}/setpoint`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ setpoint }),
      });
      fetchControlData();
    } catch (error) {
      console.error('Error updating setpoint:', error);
    }
  };

  const updateSetpoint = (loopId: number, setpoint: number, loopName: string) => {
    if (!canCommand) return;
    setPendingSetpoint(setpoint);
    setConfirmAction({
      type: 'setpoint',
      name: loopName,
      description: `Change setpoint to ${setpoint.toFixed(2)}?`,
      onConfirm: () => {
        doUpdateSetpoint(loopId, setpoint);
        setPendingSetpoint(null);
      },
    });
  };

  const doToggleMode = async (loopId: number, pidMode: string) => {
    try {
      await fetch(`/api/v1/control/pid/${loopId}/mode`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: pidMode }),
      });
      fetchControlData();
    } catch (error) {
      console.error('Error updating mode:', error);
    }
  };

  const toggleMode = (loopId: number, pidMode: string, loopName: string) => {
    if (!canCommand) return;
    setConfirmAction({
      type: 'mode',
      name: loopName,
      description: `Switch PID loop to ${pidMode} mode?`,
      onConfirm: () => doToggleMode(loopId, pidMode),
    });
  };

  const doResetInterlock = async (interlockId: number) => {
    try {
      await fetch(`/api/v1/control/interlocks/${interlockId}/reset`, {
        method: 'POST',
      });
      fetchControlData();
    } catch (error) {
      console.error('Error resetting interlock:', error);
    }
  };

  const resetInterlock = (interlockId: number, interlockName: string) => {
    if (!canCommand) return;
    setConfirmAction({
      type: 'interlock',
      name: interlockName,
      description: 'Are you sure you want to reset this safety interlock? Ensure conditions are safe before proceeding.',
      onConfirm: () => doResetInterlock(interlockId),
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
          <h1 className="text-2xl font-bold text-white">Control System</h1>
          {mode === 'view' && <CommandModeLogin showButton />}
        </div>

      {/* Command Mode Notice */}
      {mode === 'view' && (
        <div className="flex items-center gap-3 p-4 bg-orange-900/20 border border-orange-700/50 rounded-lg">
          <svg className="w-5 h-5 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-orange-200 font-medium">View Mode Active</p>
            <p className="text-sm text-orange-300/70">Enter Command Mode to modify PID settings and reset interlocks</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* PID Loops */}
        <div className="scada-panel p-4">
          <h2 className="text-lg font-semibold mb-4 text-white">PID Loops</h2>
          <div className="space-y-4">
            {pidLoops.map((loop) => (
              <div
                key={loop.loop_id}
                className={`bg-scada-accent/50 rounded-lg p-4 cursor-pointer transition-colors ${
                  selectedLoop?.loop_id === loop.loop_id ? 'ring-2 ring-scada-highlight' : ''
                }`}
                onClick={() => setSelectedLoop(loop)}
              >
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <div className="font-medium text-white">{loop.name}</div>
                    <div className="text-xs text-gray-400">
                      {loop.input_rtu} → {loop.output_rtu}
                    </div>
                  </div>
                  <span
                    className={`text-xs px-2 py-1 rounded ${
                      loop.mode === 'AUTO'
                        ? 'bg-green-600'
                        : loop.mode === 'MANUAL'
                        ? 'bg-yellow-600'
                        : 'bg-gray-600'
                    }`}
                  >
                    {loop.mode}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <div className="text-xs text-gray-400">PV</div>
                    <div className="scada-value text-lg">{loop.pv?.toFixed(2) || '--'}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400">SP</div>
                    <div className="text-lg font-bold text-blue-400">
                      {loop.setpoint?.toFixed(2) || '--'}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400">CV</div>
                    <div className="text-lg font-bold text-yellow-400">
                      {loop.cv?.toFixed(1) || '--'}%
                    </div>
                  </div>
                </div>

                {/* Progress bar showing CV */}
                <div className="mt-3 h-2 bg-scada-bg rounded-full overflow-hidden">
                  <div
                    className="h-full bg-yellow-500 transition-all duration-300"
                    style={{ width: `${Math.max(0, Math.min(100, loop.cv || 0))}%` }}
                  />
                </div>
              </div>
            ))}
            {pidLoops.length === 0 && !loading && (
              <div className="text-center text-gray-400 py-8">No PID loops configured</div>
            )}
          </div>
        </div>

        {/* Interlocks */}
        <div className="scada-panel p-4">
          <h2 className="text-lg font-semibold mb-4 text-white">Safety Interlocks</h2>
          <div className="space-y-3">
            {interlocks.map((interlock) => (
              <div
                key={interlock.interlock_id}
                className={`p-3 rounded-lg ${
                  interlock.tripped
                    ? 'bg-red-900/50 border border-red-500'
                    : 'bg-scada-accent/50'
                }`}
              >
                <div className="flex justify-between items-center">
                  <div>
                    <div className="font-medium text-white">{interlock.name}</div>
                    <div className="text-xs text-gray-400">
                      {interlock.condition_rtu} slot {interlock.condition_slot} &lt;{' '}
                      {interlock.threshold}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={`text-xs px-2 py-1 rounded ${
                        interlock.tripped ? 'bg-red-600 alarm-active' : 'bg-green-600'
                      }`}
                    >
                      {interlock.tripped ? 'TRIPPED' : 'OK'}
                    </span>
                    {interlock.tripped && canCommand && (
                      <button
                        onClick={() => resetInterlock(interlock.interlock_id, interlock.name)}
                        className="text-xs bg-scada-highlight hover:bg-red-600 px-3 py-1 rounded transition-colors"
                      >
                        Reset
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {interlocks.length === 0 && !loading && (
              <div className="text-center text-gray-400 py-8">No interlocks configured</div>
            )}
          </div>
        </div>
      </div>

      {/* Selected Loop Detail */}
      {selectedLoop && (
        <div className="scada-panel p-4">
          <h2 className="text-lg font-semibold mb-4 text-white">
            {selectedLoop.name} - Tuning Parameters
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Setpoint</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={pendingSetpoint ?? selectedLoop.setpoint}
                  onChange={(e) => setPendingSetpoint(parseFloat(e.target.value))}
                  className="flex-1 bg-scada-accent text-white rounded px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  step="0.1"
                  disabled={!canCommand}
                />
                {pendingSetpoint !== null && pendingSetpoint !== selectedLoop.setpoint && (
                  <button
                    onClick={() => updateSetpoint(selectedLoop.loop_id, pendingSetpoint, selectedLoop.name)}
                    className="px-3 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium transition-colors"
                    disabled={!canCommand}
                  >
                    Set
                  </button>
                )}
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Kp</label>
              <div className="bg-scada-accent text-white rounded px-3 py-2">
                {selectedLoop.kp}
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Ki</label>
              <div className="bg-scada-accent text-white rounded px-3 py-2">
                {selectedLoop.ki}
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Kd</label>
              <div className="bg-scada-accent text-white rounded px-3 py-2">
                {selectedLoop.kd}
              </div>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => toggleMode(selectedLoop.loop_id, 'AUTO', selectedLoop.name)}
              disabled={!canCommand || selectedLoop.mode === 'AUTO'}
              className={`px-4 py-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                selectedLoop.mode === 'AUTO' ? 'bg-green-600' : 'bg-scada-accent hover:bg-scada-accent/80'
              }`}
            >
              AUTO
            </button>
            <button
              onClick={() => toggleMode(selectedLoop.loop_id, 'MANUAL', selectedLoop.name)}
              disabled={!canCommand || selectedLoop.mode === 'MANUAL'}
              className={`px-4 py-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                selectedLoop.mode === 'MANUAL' ? 'bg-yellow-600' : 'bg-scada-accent hover:bg-scada-accent/80'
              }`}
            >
              MANUAL
            </button>
          </div>
        </div>
      )}
      </div>
    </>
  );
}
