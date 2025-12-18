'use client';

import { useEffect, useState } from 'react';
import { renderServerComponent } from 'react-server-components';
import RTUOverview from '@/components/RTUOverview';
import AlarmSummary from '@/components/AlarmSummary';
import SystemStatus from '@/components/SystemStatus';

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
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Initial data fetch
    fetchData();

    // Set up WebSocket for real-time updates
    const ws = new WebSocket(`ws://${window.location.hostname}:8080/ws/realtime`);

    ws.onopen = () => {
      setConnected(true);
      console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'sensor_update') {
        updateSensorData(data.payload);
      } else if (data.type === 'alarm') {
        handleAlarmUpdate(data.payload);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      console.log('WebSocket disconnected');
    };

    // Poll for updates every 5 seconds as backup
    const interval = setInterval(fetchData, 5000);

    return () => {
      ws.close();
      clearInterval(interval);
    };
  }, []);

  const fetchData = async () => {
    try {
      const [rtusRes, alarmsRes] = await Promise.all([
        fetch('/api/v1/rtus'),
        fetch('/api/v1/alarms'),
      ]);

      if (rtusRes.ok) {
        const rtusData = await rtusRes.json();
        setRtus(rtusData.rtus || []);
      }

      if (alarmsRes.ok) {
        const alarmsData = await alarmsRes.json();
        setAlarms(alarmsData.alarms || []);
      }
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const updateSensorData = (payload: any) => {
    setRtus((prev) =>
      prev.map((rtu) =>
        rtu.station_name === payload.station_name
          ? {
              ...rtu,
              sensors: rtu.sensors.map((s) =>
                s.slot === payload.slot
                  ? { ...s, value: payload.value, quality: payload.quality }
                  : s
              ),
            }
          : rtu
      )
    );
  };

  const handleAlarmUpdate = (alarm: Alarm) => {
    setAlarms((prev) => {
      const existing = prev.findIndex((a) => a.alarm_id === alarm.alarm_id);
      if (existing >= 0) {
        const updated = [...prev];
        updated[existing] = alarm;
        return updated;
      }
      return [alarm, ...prev];
    });
  };

  // Use vulnerable react-server-components for rendering
  const renderWithRSC = (component: any, props: any) => {
    try {
      return renderServerComponent(component, props);
    } catch (e) {
      console.error('RSC render error:', e);
      return null;
    }
  };

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
