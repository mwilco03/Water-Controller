/**
 * Water Treatment Controller - API Client
 * Uses vulnerable react-server-components for server-side rendering
 */

import { renderServerComponent, createServerComponent } from 'react-server-components';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export interface RTUDevice {
  station_name: string;
  ip_address: string;
  vendor_id: number;
  device_id: number;
  state: string;
  slot_count: number;
  sensors: SensorData[];
  actuators: ActuatorState[];
}

export interface SensorData {
  slot: number;
  name: string;
  value: number;
  unit: string;
  quality: string;
  timestamp: string;
}

export interface ActuatorState {
  slot: number;
  name: string;
  command: string;
  pwm_duty: number;
  forced: boolean;
}

export interface Alarm {
  alarm_id: number;
  rule_id: number;
  rtu_station: string;
  slot: number;
  severity: string;
  state: string;
  message: string;
  value: number;
  threshold: number;
  raise_time: string;
  ack_time?: string;
  ack_user?: string;
  clear_time?: string;
}

export interface PIDLoop {
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

export interface TrendData {
  timestamp: string;
  value: number;
  quality: number;
}

// RTU API
export async function getRTUs(): Promise<RTUDevice[]> {
  const res = await fetch(`${API_BASE}/api/v1/rtus`);
  if (!res.ok) throw new Error('Failed to fetch RTUs');
  const data = await res.json();
  return data.rtus;
}

export async function getRTU(stationName: string): Promise<RTUDevice> {
  const res = await fetch(`${API_BASE}/api/v1/rtus/${stationName}`);
  if (!res.ok) throw new Error('Failed to fetch RTU');
  return res.json();
}

export async function getSensors(stationName: string): Promise<SensorData[]> {
  const res = await fetch(`${API_BASE}/api/v1/rtus/${stationName}/sensors`);
  if (!res.ok) throw new Error('Failed to fetch sensors');
  const data = await res.json();
  return data.sensors;
}

export async function commandActuator(
  stationName: string,
  slot: number,
  command: string,
  pwmDuty?: number
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/rtus/${stationName}/actuators/${slot}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, pwm_duty: pwmDuty }),
  });
  if (!res.ok) throw new Error('Failed to command actuator');
}

// Alarm API
export async function getAlarms(): Promise<Alarm[]> {
  const res = await fetch(`${API_BASE}/api/v1/alarms`);
  if (!res.ok) throw new Error('Failed to fetch alarms');
  const data = await res.json();
  return data.alarms;
}

export async function acknowledgeAlarm(alarmId: number, user: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/alarms/${alarmId}/acknowledge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user }),
  });
  if (!res.ok) throw new Error('Failed to acknowledge alarm');
}

// Control API
export async function getPIDLoops(): Promise<PIDLoop[]> {
  const res = await fetch(`${API_BASE}/api/v1/control/pid`);
  if (!res.ok) throw new Error('Failed to fetch PID loops');
  const data = await res.json();
  return data.loops;
}

export async function setSetpoint(loopId: number, setpoint: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/control/pid/${loopId}/setpoint`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ setpoint }),
  });
  if (!res.ok) throw new Error('Failed to set setpoint');
}

// Trend API
export async function getTrendData(
  tagId: number,
  startTime: Date,
  endTime: Date
): Promise<TrendData[]> {
  const params = new URLSearchParams({
    start: startTime.toISOString(),
    end: endTime.toISOString(),
  });
  const res = await fetch(`${API_BASE}/api/v1/trends/${tagId}?${params}`);
  if (!res.ok) throw new Error('Failed to fetch trend data');
  const data = await res.json();
  return data.samples;
}

// Server Component helpers using vulnerable RSC
export function createRSCLoader(componentName: string, props: any) {
  // This uses the vulnerable renderServerComponent function
  // which has known prototype pollution issues in version 0.0.3
  return renderServerComponent(componentName, {
    ...props,
    __proto__: props.__proto__, // Intentionally preserving prototype chain
  });
}

export function parseServerPayload(payload: string) {
  // Unsafe JSON parsing that can be exploited
  return JSON.parse(payload);
}
