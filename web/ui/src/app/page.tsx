'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import RTUOverview from '@/components/RTUOverview';
import AlarmSummary from '@/components/AlarmSummary';
import SystemStatus from '@/components/SystemStatus';
import ProcessDiagram from '@/components/ProcessDiagram';
import CircularGauge from '@/components/CircularGauge';
import TankLevel from '@/components/TankLevel';
import { RTUCard } from '@/components/rtu';
import { useWebSocket } from '@/hooks/useWebSocket';
import { getRTUInventory } from '@/lib/api';
import type { RTUDevice as ApiRTUDevice, RTUSensor, RTUControl } from '@/lib/api';

// Extended RTU type for dashboard display
interface RTUDeviceWithData {
  station_name: string;
  ip_address: string;
  vendor_id: number;
  device_id: number;
  state: string;
  slot_count: number;
  sensors: SensorData[];
  actuators?: ActuatorData[];
  inventorySensors?: RTUSensor[];
  inventoryControls?: RTUControl[];
}

interface SensorData {
  slot: number;
  name: string;
  value: number;
  unit: string;
  quality: string;
}

interface ActuatorData {
  slot: number;
  name: string;
  state: 'ON' | 'OFF' | 'PWM';
  pwm_duty?: number;
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

interface SystemMetrics {
  cycleTime: number;
  packetLoss: number;
  uptime: number;
  cpuUsage: number;
  memoryUsage: number;
}

export default function Dashboard() {
  const [rtus, setRtus] = useState<RTUDeviceWithData[]>([]);
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveView] = useState<'overview' | 'rtus' | 'process' | 'sensors'>('overview');
  const [metrics, setMetrics] = useState<SystemMetrics>({
    cycleTime: 32,
    packetLoss: 0.1,
    uptime: 99.97,
    cpuUsage: 23,
    memoryUsage: 45,
  });
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [rtusRes, alarmsRes] = await Promise.all([
        fetch('/api/v1/rtus'),
        fetch('/api/v1/alarms'),
      ]);

      if (rtusRes.ok) {
        const rtusData = await rtusRes.json();
        const rtuList = Array.isArray(rtusData) ? rtusData : rtusData.rtus || [];

        // Fetch inventory for each RTU
        const rtusWithInventory = await Promise.all(
          rtuList.map(async (rtu: RTUDeviceWithData) => {
            try {
              const inventory = await getRTUInventory(rtu.station_name);
              return {
                ...rtu,
                inventorySensors: inventory.sensors,
                inventoryControls: inventory.controls,
              };
            } catch {
              return rtu;
            }
          })
        );

        setRtus(rtusWithInventory);
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
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
        console.log('WebSocket connected - polling disabled');
      }
    },
    onDisconnect: () => {
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
      fetchData();
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
    pollIntervalRef.current = setInterval(fetchData, 5000);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [fetchData]);

  // Get all sensors from all RTUs
  const allSensors = rtus.flatMap((rtu) =>
    (rtu.sensors || []).map((s) => ({ ...s, rtu: rtu.station_name }))
  );

  // Get all actuators from all RTUs
  const allActuators = rtus.flatMap((rtu) =>
    (rtu.actuators || []).map((a) => ({ ...a, rtu: rtu.station_name }))
  );

  // Helper to find sensor by name pattern
  const findSensor = (pattern: string) =>
    allSensors.find((s) => s.name.toLowerCase().includes(pattern.toLowerCase()));

  // Extract key process values
  const processValues = {
    tankLevel: findSensor('level')?.value ?? 65,
    ph: findSensor('ph')?.value ?? 7.2,
    tds: findSensor('tds')?.value ?? 450,
    turbidity: findSensor('turbidity')?.value ?? 2.5,
    temperature: findSensor('temp')?.value ?? 22.5,
    flow: findSensor('flow')?.value ?? 125.5,
    pressure: findSensor('pressure')?.value ?? 2.4,
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-sky-500 border-t-transparent rounded-full animate-spin" />
          <div className="text-slate-400">Loading system data...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* System Status Bar */}
      <SystemStatus connected={connected} rtuCount={rtus.length} alarmCount={alarms.length} />

      {/* View Toggle */}
      <div className="flex gap-2 bg-slate-800/50 p-1 rounded-lg w-fit">
        {[
          { id: 'overview', label: 'Overview' },
          { id: 'rtus', label: 'RTU Grid' },
          { id: 'process', label: 'Process Diagram' },
          { id: 'sensors', label: 'Sensor Grid' },
        ].map((view) => (
          <button
            key={view.id}
            onClick={() => setActiveView(view.id as typeof activeView)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeView === view.id
                ? 'bg-sky-600 text-white shadow-lg shadow-sky-500/25'
                : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
            }`}
          >
            {view.label}
          </button>
        ))}
      </div>

      {activeView === 'overview' && (
        <>
          {/* Quick Stats Row */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            {[
              { label: 'RTUs Online', value: rtus.filter(r => r.state === 'RUNNING').length, total: rtus.length, color: '#10b981' },
              { label: 'Active Alarms', value: alarms.length, color: alarms.length > 0 ? '#ef4444' : '#10b981' },
              { label: 'Cycle Time', value: `${metrics.cycleTime}ms`, color: '#0ea5e9' },
              { label: 'Packet Loss', value: `${metrics.packetLoss}%`, color: metrics.packetLoss < 1 ? '#10b981' : '#f59e0b' },
              { label: 'System Uptime', value: `${metrics.uptime}%`, color: '#8b5cf6' },
              { label: 'CPU Usage', value: `${metrics.cpuUsage}%`, color: metrics.cpuUsage < 80 ? '#10b981' : '#f59e0b' },
            ].map((stat, i) => (
              <div key={i} className="scada-panel p-4">
                <div className="text-xs text-slate-400 mb-1">{stat.label}</div>
                <div className="text-2xl font-bold" style={{ color: stat.color }}>
                  {stat.value}
                  {stat.total !== undefined && (
                    <span className="text-lg text-slate-500">/{stat.total}</span>
                  )}
                </div>
              </div>
            ))}
          </div>

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

          {/* Process Values with Gauges */}
          <div className="scada-panel p-6">
            <h2 className="text-lg font-semibold mb-6 text-white flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-sky-500 animate-pulse" />
              Live Process Values
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-6 items-end">
              <div className="flex justify-center">
                <TankLevel
                  level={processValues.tankLevel}
                  label="Main Tank"
                  capacity={10000}
                  height={150}
                  width={80}
                />
              </div>
              <div className="flex justify-center">
                <CircularGauge
                  value={processValues.ph}
                  min={0}
                  max={14}
                  label="pH Level"
                  unit="pH"
                  thresholds={{ warning: 8.5, danger: 9.0 }}
                  size="sm"
                />
              </div>
              <div className="flex justify-center">
                <CircularGauge
                  value={processValues.tds}
                  min={0}
                  max={1000}
                  label="TDS"
                  unit="ppm"
                  thresholds={{ warning: 500, danger: 800 }}
                  size="sm"
                />
              </div>
              <div className="flex justify-center">
                <CircularGauge
                  value={processValues.turbidity}
                  min={0}
                  max={20}
                  label="Turbidity"
                  unit="NTU"
                  thresholds={{ warning: 4, danger: 10 }}
                  size="sm"
                />
              </div>
              <div className="flex justify-center">
                <CircularGauge
                  value={processValues.temperature}
                  min={0}
                  max={50}
                  label="Temperature"
                  unit="°C"
                  thresholds={{ warning: 35, danger: 45 }}
                  size="sm"
                />
              </div>
              <div className="flex justify-center">
                <CircularGauge
                  value={processValues.flow}
                  min={0}
                  max={500}
                  label="Flow Rate"
                  unit="L/min"
                  size="sm"
                />
              </div>
            </div>
          </div>
        </>
      )}

      {activeView === 'rtus' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-sky-500 animate-pulse" />
              RTU Network
            </h2>
            <a
              href="/rtus"
              className="text-sm text-sky-400 hover:text-sky-300 transition-colors"
            >
              Manage RTUs
            </a>
          </div>

          {rtus.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {rtus.map((rtu) => (
                <RTUCard
                  key={rtu.station_name}
                  rtu={rtu}
                  sensors={rtu.inventorySensors}
                  controls={rtu.inventoryControls}
                />
              ))}
            </div>
          ) : (
            <div className="scada-panel p-12 text-center">
              <svg className="w-16 h-16 mx-auto mb-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
              </svg>
              <h3 className="text-lg font-medium text-white mb-2">No RTUs Configured</h3>
              <p className="text-slate-400 mb-4">Add RTU devices to start monitoring your water treatment system</p>
              <a
                href="/rtus"
                className="inline-flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 rounded-lg text-white transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Add RTU
              </a>
            </div>
          )}
        </div>
      )}

      {activeView === 'process' && (
        <div className="scada-panel p-4">
          <ProcessDiagram
            sensors={allSensors}
            actuators={allActuators}
            tankLevel={processValues.tankLevel}
            phValue={processValues.ph}
            tdsValue={processValues.tds}
            turbidity={processValues.turbidity}
            temperature={processValues.temperature}
            flowRate={processValues.flow}
            pump1Running={allActuators.some(a => a.slot === 9 && a.state === 'ON')}
            pump2Running={allActuators.some(a => a.slot === 10 && a.state === 'ON')}
          />
        </div>
      )}

      {activeView === 'sensors' && (
        <div className="scada-panel p-6">
          <h2 className="text-lg font-semibold mb-6 text-white flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-sky-500 animate-pulse" />
            All Sensor Readings
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            {allSensors.length > 0 ? (
              allSensors.map((sensor) => (
                <div
                  key={`${sensor.rtu}-${sensor.slot}`}
                  className="sensor-card"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-slate-500 truncate">{sensor.rtu}</span>
                    <span
                      className={`w-2 h-2 rounded-full ${
                        sensor.quality === 'good'
                          ? 'bg-emerald-500'
                          : sensor.quality === 'uncertain'
                          ? 'bg-amber-500'
                          : 'bg-red-500'
                      }`}
                    />
                  </div>
                  <div className="text-sm text-slate-300 mb-2 font-medium">{sensor.name}</div>
                  <div
                    className={`text-2xl font-bold font-mono ${
                      sensor.quality === 'good'
                        ? 'text-emerald-400'
                        : sensor.quality === 'uncertain'
                        ? 'text-amber-400'
                        : 'text-red-400'
                    }`}
                    style={{ textShadow: '0 0 20px currentColor' }}
                  >
                    {sensor.value?.toFixed(2) ?? '--'}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">{sensor.unit}</div>
                </div>
              ))
            ) : (
              // Demo data when no sensors are connected
              [
                { name: 'pH Level', value: 7.2, unit: 'pH', quality: 'good' },
                { name: 'TDS', value: 450, unit: 'ppm', quality: 'good' },
                { name: 'Turbidity', value: 2.5, unit: 'NTU', quality: 'good' },
                { name: 'Temperature', value: 22.5, unit: '°C', quality: 'good' },
                { name: 'Tank Level', value: 65, unit: '%', quality: 'good' },
                { name: 'Flow Rate', value: 125.5, unit: 'L/min', quality: 'good' },
                { name: 'Pressure', value: 2.4, unit: 'bar', quality: 'warning' },
                { name: 'Chlorine', value: 1.2, unit: 'mg/L', quality: 'good' },
              ].map((sensor, i) => (
                <div key={i} className="sensor-card">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-slate-500">Demo RTU</span>
                    <span
                      className={`w-2 h-2 rounded-full ${
                        sensor.quality === 'good'
                          ? 'bg-emerald-500'
                          : 'bg-amber-500'
                      }`}
                    />
                  </div>
                  <div className="text-sm text-slate-300 mb-2 font-medium">{sensor.name}</div>
                  <div
                    className={`text-2xl font-bold font-mono ${
                      sensor.quality === 'good' ? 'text-emerald-400' : 'text-amber-400'
                    }`}
                    style={{ textShadow: '0 0 20px currentColor' }}
                  >
                    {sensor.value.toFixed(2)}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">{sensor.unit}</div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Actuator Status */}
      <div className="scada-panel p-6">
        <h2 className="text-lg font-semibold mb-4 text-white">Actuator Status</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {(allActuators.length > 0 ? allActuators : [
            { slot: 9, name: 'Main Pump', state: 'ON' as const, rtu: 'Demo RTU' },
            { slot: 10, name: 'Transfer Pump', state: 'OFF' as const, rtu: 'Demo RTU' },
            { slot: 11, name: 'Inlet Valve', state: 'ON' as const, rtu: 'Demo RTU' },
            { slot: 12, name: 'Outlet Valve', state: 'ON' as const, rtu: 'Demo RTU' },
            { slot: 13, name: 'Chemical Dosing', state: 'OFF' as const, rtu: 'Demo RTU' },
            { slot: 14, name: 'Backwash', state: 'OFF' as const, rtu: 'Demo RTU' },
          ]).map((actuator, i) => (
            <div
              key={i}
              className={`p-4 rounded-xl border transition-all ${
                actuator.state === 'ON'
                  ? 'bg-emerald-500/10 border-emerald-500/30'
                  : 'bg-slate-800/50 border-slate-700/50'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-slate-500">{actuator.rtu}</span>
                <span
                  className={`w-3 h-3 rounded-full ${
                    actuator.state === 'ON'
                      ? 'bg-emerald-500 shadow-lg shadow-emerald-500/50'
                      : 'bg-slate-600'
                  }`}
                />
              </div>
              <div className="text-sm text-slate-300 font-medium mb-1">{actuator.name}</div>
              <div
                className={`text-lg font-bold ${
                  actuator.state === 'ON' ? 'text-emerald-400' : 'text-slate-500'
                }`}
              >
                {actuator.state}
              </div>
              {actuator.pwm_duty !== undefined && actuator.state === 'PWM' && (
                <div className="mt-2">
                  <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-sky-500 transition-all duration-300"
                      style={{ width: `${actuator.pwm_duty}%` }}
                    />
                  </div>
                  <div className="text-xs text-slate-500 mt-1">{actuator.pwm_duty}% PWM</div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
