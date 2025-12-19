'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';

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

export default function ControlPage() {
  const [pidLoops, setPidLoops] = useState<PIDLoop[]>([]);
  const [interlocks, setInterlocks] = useState<Interlock[]>([]);
  const [selectedLoop, setSelectedLoop] = useState<PIDLoop | null>(null);
  const [loading, setLoading] = useState(true);
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

  const updateSetpoint = async (loopId: number, setpoint: number) => {
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

  const toggleMode = async (loopId: number, mode: string) => {
    try {
      await fetch(`/api/v1/control/pid/${loopId}/mode`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      fetchControlData();
    } catch (error) {
      console.error('Error updating mode:', error);
    }
  };

  const resetInterlock = async (interlockId: number) => {
    try {
      await fetch(`/api/v1/control/interlocks/${interlockId}/reset`, {
        method: 'POST',
      });
      fetchControlData();
    } catch (error) {
      console.error('Error resetting interlock:', error);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Control System</h1>

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
                    {interlock.tripped && (
                      <button
                        onClick={() => resetInterlock(interlock.interlock_id)}
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
              <input
                type="number"
                value={selectedLoop.setpoint}
                onChange={(e) =>
                  updateSetpoint(selectedLoop.loop_id, parseFloat(e.target.value))
                }
                className="w-full bg-scada-accent text-white rounded px-3 py-2"
                step="0.1"
              />
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
              onClick={() => toggleMode(selectedLoop.loop_id, 'AUTO')}
              className={`px-4 py-2 rounded ${
                selectedLoop.mode === 'AUTO' ? 'bg-green-600' : 'bg-scada-accent'
              }`}
            >
              AUTO
            </button>
            <button
              onClick={() => toggleMode(selectedLoop.loop_id, 'MANUAL')}
              className={`px-4 py-2 rounded ${
                selectedLoop.mode === 'MANUAL' ? 'bg-yellow-600' : 'bg-scada-accent'
              }`}
            >
              MANUAL
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
