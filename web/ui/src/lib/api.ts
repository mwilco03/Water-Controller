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

/* Quality codes (OPC UA compatible - 5-byte sensor format) */
export const QUALITY_GOOD = 0x00;
export const QUALITY_UNCERTAIN = 0x40;
export const QUALITY_BAD = 0x80;
export const QUALITY_NOT_CONNECTED = 0xC0;

export interface SensorData {
  slot: number;
  name: string;
  value: number;
  unit: string;
  quality: string;           /* Human-readable quality name */
  quality_code?: number;     /* OPC UA quality code from 5-byte format */
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

// RTU Inventory types (discovered from RTU)
export interface RTUSensor {
  id: number;
  rtu_station: string;
  sensor_id: string;
  sensor_type: string;
  name: string;
  unit: string;
  register_address: number;
  data_type: string;
  scale_min: number;
  scale_max: number;
  last_value: number | null;
  last_quality: number;
  last_update: string | null;
  created_at: string;
}

export interface RTUControl {
  id: number;
  rtu_station: string;
  control_id: string;
  control_type: string;
  name: string;
  command_type: string;
  register_address: number;
  feedback_register: number | null;
  range_min: number | null;
  range_max: number | null;
  current_state: string;
  current_value: number | null;
  last_command: string | null;
  last_update: string | null;
  created_at: string;
}

export interface RTUInventory {
  rtu_station: string;
  sensors: RTUSensor[];
  controls: RTUControl[];
  last_refresh: string | null;
}

export interface DiscoveredDevice {
  id: number;
  mac_address: string;
  ip_address: string | null;
  device_name: string | null;
  vendor_name: string | null;
  device_type: string | null;
  vendor_id: number | null;
  device_id: number | null;
  discovered_at: string;
  added_to_registry: boolean;
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

// RTU Inventory API
export async function getRTUInventory(stationName: string): Promise<RTUInventory> {
  return apiFetch<RTUInventory>(`/api/v1/rtus/${encodeURIComponent(stationName)}/inventory`);
}

export async function refreshRTUInventory(stationName: string): Promise<RTUInventory> {
  return apiFetch<RTUInventory>(`/api/v1/rtus/${encodeURIComponent(stationName)}/inventory/refresh`, {
    method: 'POST',
  });
}

export async function sendControlCommand(
  stationName: string,
  controlId: string,
  command: string,
  value?: number
): Promise<void> {
  await apiFetch(`/api/v1/rtus/${encodeURIComponent(stationName)}/control/${encodeURIComponent(controlId)}`, {
    method: 'POST',
    body: JSON.stringify({ command, value }),
  });
}

// DCP Discovery API
export async function discoverRTUs(timeoutMs = 5000): Promise<DiscoveredDevice[]> {
  const data = await apiFetch<{ devices: DiscoveredDevice[]; scan_duration_ms: number }>(
    '/api/v1/discover/rtu',
    {
      method: 'POST',
      body: JSON.stringify({ timeout_ms: timeoutMs }),
    }
  );
  return data.devices || [];
}

export async function getCachedDiscovery(): Promise<DiscoveredDevice[]> {
  const data = await apiFetch<{ devices: DiscoveredDevice[] }>('/api/v1/discover/cached');
  return data.devices || [];
}

export async function clearDiscoveryCache(): Promise<void> {
  await apiFetch('/api/v1/discover/cache', { method: 'DELETE' });
}
