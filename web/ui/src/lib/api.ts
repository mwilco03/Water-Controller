/**
 * Water Treatment Controller - API Client
 * Clean REST API client for SCADA/HMI frontend
 */

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

export interface SystemHealth {
  cycle_time_ms: number;
  packet_loss_percent: number;
  uptime_percent: number;
  cpu_usage_percent: number;
  memory_usage_percent: number;
  rtus_connected: number;
  rtus_total: number;
  active_alarms: number;
}

// Generic fetch wrapper with error handling
async function apiFetch<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${res.status}: ${errorText}`);
  }

  return res.json();
}

// RTU API
export async function getRTUs(): Promise<RTUDevice[]> {
  const data = await apiFetch<{ rtus: RTUDevice[] }>('/api/v1/rtus');
  return data.rtus || [];
}

export async function getRTU(stationName: string): Promise<RTUDevice> {
  return apiFetch<RTUDevice>(`/api/v1/rtus/${encodeURIComponent(stationName)}`);
}

export async function getSensors(stationName: string): Promise<SensorData[]> {
  const data = await apiFetch<{ sensors: SensorData[] }>(
    `/api/v1/rtus/${encodeURIComponent(stationName)}/sensors`
  );
  return data.sensors || [];
}

export async function commandActuator(
  stationName: string,
  slot: number,
  command: 'ON' | 'OFF' | 'PWM',
  pwmDuty?: number
): Promise<void> {
  await apiFetch(`/api/v1/rtus/${encodeURIComponent(stationName)}/actuators/${slot}`, {
    method: 'POST',
    body: JSON.stringify({ command, pwm_duty: pwmDuty }),
  });
}

// Alarm API
export async function getAlarms(): Promise<Alarm[]> {
  const data = await apiFetch<{ alarms: Alarm[] }>('/api/v1/alarms');
  return data.alarms || [];
}

export async function getAlarmHistory(limit = 100): Promise<Alarm[]> {
  const data = await apiFetch<{ alarms: Alarm[] }>(
    `/api/v1/alarms/history?limit=${limit}`
  );
  return data.alarms || [];
}

export async function acknowledgeAlarm(alarmId: number, user: string): Promise<void> {
  await apiFetch(`/api/v1/alarms/${alarmId}/acknowledge`, {
    method: 'POST',
    body: JSON.stringify({ user }),
  });
}

export async function acknowledgeAllAlarms(user: string): Promise<void> {
  await apiFetch('/api/v1/alarms/acknowledge-all', {
    method: 'POST',
    body: JSON.stringify({ user }),
  });
}

// Control API
export async function getPIDLoops(): Promise<PIDLoop[]> {
  const data = await apiFetch<{ loops: PIDLoop[] }>('/api/v1/control/pid');
  return data.loops || [];
}

export async function setSetpoint(loopId: number, setpoint: number): Promise<void> {
  await apiFetch(`/api/v1/control/pid/${loopId}/setpoint`, {
    method: 'PUT',
    body: JSON.stringify({ setpoint }),
  });
}

export async function setPIDMode(loopId: number, mode: 'AUTO' | 'MANUAL' | 'CASCADE'): Promise<void> {
  await apiFetch(`/api/v1/control/pid/${loopId}/mode`, {
    method: 'PUT',
    body: JSON.stringify({ mode }),
  });
}

export async function setPIDTuning(
  loopId: number,
  kp: number,
  ki: number,
  kd: number
): Promise<void> {
  await apiFetch(`/api/v1/control/pid/${loopId}/tuning`, {
    method: 'PUT',
    body: JSON.stringify({ kp, ki, kd }),
  });
}

// Trend API
export async function getTrendData(
  tagId: number,
  startTime: Date,
  endTime: Date
): Promise<TrendData[]> {
  const params = new URLSearchParams({
    start_time: startTime.toISOString(),
    end_time: endTime.toISOString(),
  });
  const data = await apiFetch<{ samples: TrendData[] }>(
    `/api/v1/trends/${tagId}?${params}`
  );
  return data.samples || [];
}

export async function getTrendTags(): Promise<Array<{
  tag_id: number;
  rtu_station: string;
  slot: number;
  tag_name: string;
  sample_rate_ms: number;
}>> {
  return apiFetch('/api/v1/trends/tags');
}

// System API
export async function getSystemHealth(): Promise<SystemHealth> {
  return apiFetch<SystemHealth>('/api/v1/system/health');
}

export async function exportConfiguration(): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/v1/system/config`);
  if (!res.ok) throw new Error('Failed to export configuration');
  return res.blob();
}

export async function importConfiguration(configFile: File): Promise<void> {
  const formData = new FormData();
  formData.append('config', configFile);

  const res = await fetch(`${API_BASE}/api/v1/system/config`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) throw new Error('Failed to import configuration');
}

// Backup API
export async function createBackup(): Promise<{ backup_id: string }> {
  return apiFetch('/api/v1/backups', { method: 'POST' });
}

export async function listBackups(): Promise<Array<{
  id: string;
  created_at: string;
  size_bytes: number;
}>> {
  return apiFetch('/api/v1/backups');
}

export async function downloadBackup(backupId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/v1/backups/${backupId}/download`);
  if (!res.ok) throw new Error('Failed to download backup');
  return res.blob();
}

export async function restoreBackup(backupId: string): Promise<void> {
  await apiFetch(`/api/v1/backups/${backupId}/restore`, { method: 'POST' });
}
