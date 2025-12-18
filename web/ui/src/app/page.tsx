'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import RTUOverview from '@/components/RTUOverview';
import AlarmSummary from '@/components/AlarmSummary';
import SystemStatus from '@/components/SystemStatus';
import { useWebSocket } from '@/hooks/useWebSocket';

interface RTUDevice {
  station_name: string;
  ip_address: string;
  state: string;
  slot_count: number;
  sensors: SensorData[];
}

interface SensorData {
  slot: number;
  name: string;
  value: number;
  unit: string;
  quality: string;
}

interface Alarm {
  alarm_id: number;
  rtu_station: string;
  slot: number;
  severity: string;
  message: string;
  state: string;
  timestamp: string;
}

export default function Dashboard() {
  const [rtus, setRtus] = useState<RTUDevice[]>([]);
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(true);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [rtusRes, alarmsRes] = await Promise.all([
        fetch('/api/v1/rtus'),
        fetch('/api/v1/alarms'),
      ]);

      if (rtusRes.ok) {
        const rtusData = await rtusRes.json();
        setRtus(Array.isArray(rtusData) ? rtusData : rtusData.rtus || []);
      }

      if (alarmsRes.ok) {
        const alarmsData = await alarmsRes.json();
        setAlarms(Array.isArray(alarmsData) ? alarmsData : alarmsData.alarms || []);
      }
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  // WebSocket for real-time updates
  const { connected, subscribe } = useWebSocket({
    onConnect: () => {
      // Stop polling when WebSocket connects
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
        console.log('WebSocket connected - polling disabled');
      }
    },
    onDisconnect: () => {
      // Start polling as fallback when WebSocket disconnects
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(fetchData, 5000);
        console.log('WebSocket disconnected - polling enabled as fallback');
      }
    },
  });

  // Subscribe to real-time updates
  useEffect(() => {
    const unsubSensor = subscribe('sensor_update', (_, payload) => {
      setRtus((prev) =>
        prev.map((rtu) =>
          rtu.station_name === payload.station_name
            ? {
                ...rtu,
                sensors: (rtu.sensors || []).map((s) =>
                  s.slot === payload.slot
                    ? { ...s, value: payload.value, quality: payload.quality }
                    : s
                ),
              }
            : rtu
        )
      );
    });

    const unsubRtu = subscribe('rtu_update', () => {
      fetchData(); // Refresh RTU list
    });

    const unsubAlarm = subscribe('alarm_raised', (_, alarm) => {
      setAlarms((prev) => {
        const existing = prev.findIndex((a) => a.alarm_id === alarm.alarm_id);
        if (existing >= 0) {
          const updated = [...prev];
          updated[existing] = alarm;
          return updated;
        }
        return [alarm, ...prev];
      });
    });

    const unsubAlarmAck = subscribe('alarm_acknowledged', (_, data) => {
      setAlarms((prev) =>
        prev.map((a) =>
          a.alarm_id === data.alarm_id ? { ...a, state: 'ACTIVE_ACK' } : a
        )
      );
    });

    const unsubAlarmClear = subscribe('alarm_cleared', (_, data) => {
      setAlarms((prev) => prev.filter((a) => a.alarm_id !== data.alarm_id));
    });

    return () => {
      unsubSensor();
      unsubRtu();
      unsubAlarm();
      unsubAlarmAck();
      unsubAlarmClear();
    };
  }, [subscribe, fetchData]);

  // Initial data fetch
  useEffect(() => {
    fetchData();

    // Start polling initially (will be disabled when WebSocket connects)
    pollIntervalRef.current = setInterval(fetchData, 5000);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* System Status Bar */}
      <SystemStatus connected={connected} rtuCount={rtus.length} alarmCount={alarms.length} />

      {/* Main Dashboard Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* RTU Overview - 2 columns */}
        <div className="lg:col-span-2">
          <RTUOverview rtus={rtus} />
        </div>

        {/* Alarm Summary - 1 column */}
        <div>
          <AlarmSummary alarms={alarms} />
        </div>
      </div>

      {/* Process Values */}
      <div className="scada-panel p-4">
        <h2 className="text-lg font-semibold mb-4 text-white">Live Process Values</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {rtus.flatMap((rtu) =>
            (rtu.sensors || []).map((sensor) => (
              <div
                key={`${rtu.station_name}-${sensor.slot}`}
                className="bg-scada-accent rounded-lg p-3 text-center"
              >
                <div className="text-xs text-gray-400 mb-1">
                  {rtu.station_name}
                </div>
                <div className="text-sm text-gray-300 mb-2">{sensor.name}</div>
                <div
                  className={`scada-value ${
                    sensor.quality === 'good'
                      ? 'good'
                      : sensor.quality === 'uncertain'
                      ? 'warning'
                      : 'bad'
                  }`}
                >
                  {sensor.value?.toFixed(2) || '--'}
                </div>
                <div className="text-xs text-gray-400">{sensor.unit}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
