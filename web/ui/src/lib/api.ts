/**
 * Water Treatment Controller - API Client
 * Clean REST API client for SCADA/HMI frontend
 *
 * Authentication:
 * - GET requests: No auth required (view access)
 * - POST/PUT/DELETE requests: Auth required for control actions
 * - Use setAuthToken() after login to enable authenticated requests
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

// Auth token storage (in-memory for security - cleared on page refresh)
let authToken: string | null = null;

/**
 * Set the authentication token for API requests.
 * Call this after successful login.
 */
export function setAuthToken(token: string | null): void {
  authToken = token;
}

/**
 * Get the current authentication token.
 */
export function getAuthToken(): string | null {
  return authToken;
}

/**
 * Check if user is authenticated.
 */
export function isAuthenticated(): boolean {
  return authToken !== null;
}

export interface RTUDevice {
  station_name: string;
  ip_address: string;
  state: string;
  // Optional fields - not all endpoints return these
  id?: number;
  vendor_id?: string | null;  // Hex string e.g. "0x002A"
  device_id?: string | null;  // Hex string e.g. "0x0405"
  slot_count?: number | null;
  state_since?: string;
  last_seen?: string;
  healthy?: boolean;
  sensors?: SensorData[];
  actuators?: ActuatorState[];
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
  /** True if control is in manual override mode (local control, not auto/PID) */
  is_manual?: boolean;
  /** Mode of operation: 'auto', 'manual', 'local', 'remote' */
  mode?: 'auto' | 'manual' | 'local' | 'remote';
}

export interface RTUInventory {
  rtu_station: string;
  sensors: RTUSensor[];
  controls: RTUControl[];
  last_refresh: string | null;
}

// Note: Slot types removed - slots are PROFINET frame positions, not database entities
// See CLAUDE.md "Slots Architecture Decision" for rationale

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
  rtu_name: string | null;
}

// Generic fetch wrapper with error handling and automatic auth
async function apiFetch<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  // Build headers with auth token if available
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options?.headers,
  };

  // Add Authorization header if token is available
  if (authToken) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${authToken}`;
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => 'Unknown error');

    // Handle 401 specifically for auth errors
    if (res.status === 401) {
      // Clear invalid token
      authToken = null;
      throw new Error('Authentication required. Please log in.');
    }

    throw new Error(`API Error ${res.status}: ${errorText}`);
  }

  return res.json();
}

// RTU API
export async function getRTUs(): Promise<RTUDevice[]> {
  const response = await apiFetch<{ data?: RTUDevice[]; rtus?: RTUDevice[] }>('/api/v1/rtus');
  // Handle both { data: [...] } and { rtus: [...] } formats
  return response.data || response.rtus || [];
}

export async function getRTU(stationName: string): Promise<RTUDevice> {
  const response = await apiFetch<{ data?: RTUDevice } | RTUDevice>(`/api/v1/rtus/${encodeURIComponent(stationName)}`);
  // Handle both { data: {...} } and direct object formats
  return (response as { data?: RTUDevice }).data || (response as RTUDevice);
}

export async function getSensors(stationName: string): Promise<SensorData[]> {
  const response = await apiFetch<{ data?: SensorData[]; sensors?: SensorData[] }>(
    `/api/v1/rtus/${encodeURIComponent(stationName)}/sensors`
  );
  // Handle both { data: [...] } and { sensors: [...] } formats
  return response.data || response.sensors || [];
}

// Note: getSlots function removed - slots are PROFINET frame positions, not database entities

export async function commandControl(
  stationName: string,
  controlTag: string,
  command: 'ON' | 'OFF' | 'OPEN' | 'CLOSE' | 'START' | 'STOP',
  value?: number
): Promise<void> {
  await apiFetch(`/api/v1/rtus/${encodeURIComponent(stationName)}/controls/${encodeURIComponent(controlTag)}/command`, {
    method: 'POST',
    body: JSON.stringify({ command, value }),
  });
}

// Alarm API
export async function getAlarms(): Promise<Alarm[]> {
  const response = await apiFetch<{ data?: Alarm[]; alarms?: Alarm[] }>('/api/v1/alarms');
  // Handle both { data: [...] } and { alarms: [...] } formats
  return response.data || response.alarms || [];
}

export async function getAlarmHistory(limit = 100): Promise<Alarm[]> {
  const response = await apiFetch<{ data?: Alarm[]; alarms?: Alarm[] }>(
    `/api/v1/alarms/history?limit=${limit}`
  );
  // Handle both { data: [...] } and { alarms: [...] } formats
  return response.data || response.alarms || [];
}

export async function acknowledgeAlarm(alarmId: number, user: string, note?: string): Promise<void> {
  await apiFetch(`/api/v1/alarms/${alarmId}/acknowledge`, {
    method: 'POST',
    body: JSON.stringify({ user, note: note || null }),
  });
}

export async function acknowledgeAllAlarms(user: string, note?: string): Promise<void> {
  await apiFetch('/api/v1/alarms/acknowledge-all', {
    method: 'POST',
    body: JSON.stringify({ user, note: note || null }),
  });
}

// Alarm Shelving API (ISA-18.2)
export interface ShelvedAlarm {
  id: number;
  rtu_station: string;
  slot: number;
  shelved_by: string;
  shelved_at: string;
  shelf_duration_minutes: number;
  expires_at: string;
  reason: string | null;
  active: number;
}

export async function getShelvedAlarms(): Promise<ShelvedAlarm[]> {
  const data = await apiFetch<{ shelved_alarms: ShelvedAlarm[] }>('/api/v1/alarms/shelved');
  return data.shelved_alarms || [];
}

export async function shelveAlarm(
  rtuStation: string,
  slot: number,
  durationMinutes: number,
  reason?: string
): Promise<{ shelf_id: number }> {
  return apiFetch(`/api/v1/alarms/shelve/${encodeURIComponent(rtuStation)}/${slot}`, {
    method: 'POST',
    body: JSON.stringify({
      duration_minutes: durationMinutes,
      reason: reason || null,
    }),
  });
}

export async function unshelveAlarm(shelfId: number): Promise<void> {
  await apiFetch(`/api/v1/alarms/shelve/${shelfId}`, {
    method: 'DELETE',
  });
}

export async function isAlarmShelved(rtuStation: string, slot: number): Promise<boolean> {
  const data = await apiFetch<{ is_shelved: boolean }>(
    `/api/v1/alarms/shelved/check/${encodeURIComponent(rtuStation)}/${slot}`
  );
  return data.is_shelved;
}

// Control API
export async function getRtuPIDLoops(stationName: string): Promise<PIDLoop[]> {
  const data = await apiFetch<{ loops: PIDLoop[] }>(
    `/api/v1/rtus/${encodeURIComponent(stationName)}/pid`
  );
  return data.loops || [];
}

export async function setSetpoint(stationName: string, loopId: number, setpoint: number): Promise<void> {
  await apiFetch(`/api/v1/rtus/${encodeURIComponent(stationName)}/pid/${loopId}/setpoint`, {
    method: 'PUT',
    body: JSON.stringify({ setpoint }),
  });
}

export async function setPIDMode(stationName: string, loopId: number, mode: 'AUTO' | 'MANUAL' | 'CASCADE'): Promise<void> {
  await apiFetch(`/api/v1/rtus/${encodeURIComponent(stationName)}/pid/${loopId}/mode`, {
    method: 'PUT',
    body: JSON.stringify({ mode }),
  });
}

export async function setPIDTuning(
  stationName: string,
  loopId: number,
  kp: number,
  ki: number,
  kd: number
): Promise<void> {
  await apiFetch(`/api/v1/rtus/${encodeURIComponent(stationName)}/pid/${loopId}/tuning`, {
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
  // Note: /health endpoint returns subsystem status, not cycle_time_ms
  // For detailed system metrics, use /api/v1/system/status
  return apiFetch<SystemHealth>('/api/v1/system/status');
}

// Configuration export/import uses the backup API
// Export returns a ZIP file with all configuration
export async function exportConfiguration(): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/v1/system`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to export configuration');
  return res.blob();
}

// Import restores configuration from a backup ZIP file
export async function importConfiguration(configFile: File): Promise<void> {
  const formData = new FormData();
  formData.append('file', configFile);

  const res = await fetch(`${API_BASE}/api/v1/backup/restore`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) throw new Error('Failed to import configuration');
}

// Backup API
// Note: The backup API creates and downloads in a single request.
// There is no persistent backup storage on the server.
export async function createAndDownloadBackup(): Promise<Blob> {
  // POST to /backup creates and immediately returns backup as ZIP
  const res = await fetch(`${API_BASE}/api/v1/backup`, {
    method: 'POST',
    headers: authToken ? { 'Authorization': `Bearer ${authToken}` } : {},
  });
  if (!res.ok) throw new Error('Failed to create backup');
  return res.blob();
}

export async function restoreBackup(file: File): Promise<{ success: boolean; error?: string }> {
  const formData = new FormData();
  formData.append('file', file);

  const headers: HeadersInit = {};
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const res = await fetch(`${API_BASE}/api/v1/backup/restore`, {
    method: 'POST',
    headers,
    body: formData,
  });
  if (!res.ok) throw new Error('Failed to restore backup');
  return res.json();
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

// RTU Discovery API
// Note: RTU inventory comes from PROFINET discovery, not stored locally
export async function discoverRTUDevices(stationName: string): Promise<unknown> {
  return apiFetch(`/api/v1/rtus/${encodeURIComponent(stationName)}/discover`, {
    method: 'POST',
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

// ============== Ping Scan ==============

export interface PingResult {
  ip_address: string;
  reachable: boolean;
  response_time_ms: number | null;
  hostname: string | null;
}

export interface PingScanResponse {
  subnet: string;
  total_hosts: number;
  reachable_count: number;
  unreachable_count: number;
  scan_duration_seconds: number;
  results: PingResult[];
}

export async function pingScanSubnet(subnet: string, timeoutMs = 500): Promise<PingScanResponse> {
  const response = await apiFetch<{ data?: PingScanResponse } | PingScanResponse>('/api/v1/discover/ping-scan', {
    method: 'POST',
    body: JSON.stringify({ subnet, timeout_ms: timeoutMs }),
  });
  // Handle both { data: {...} } and direct object formats
  return (response as { data?: PingScanResponse }).data || (response as PingScanResponse);
}

// ============== Response Data Extraction Utilities ==============
// These utilities safely handle API responses that may be wrapped in { data: ... }
// or returned as raw arrays/objects, preventing "x.map is not a function" errors.

/**
 * Safely extracts array data from API responses.
 * Handles both raw arrays and wrapped { data: [...] } responses.
 *
 * @param response - The JSON response from the API
 * @returns The extracted array, or empty array if extraction fails
 *
 * @example
 * const res = await fetch('/api/v1/users');
 * const json = await res.json();
 * setUsers(extractArrayData<User>(json));
 */
export function extractArrayData<T>(response: unknown): T[] {
  // Handle null/undefined
  if (response == null) {
    return [];
  }

  // If it's already an array, return it
  if (Array.isArray(response)) {
    return response as T[];
  }

  // If it's a wrapped response with 'data' property
  if (typeof response === 'object' && 'data' in response) {
    const data = (response as { data: unknown }).data;
    if (Array.isArray(data)) {
      return data as T[];
    }
  }

  // Return empty array as fallback
  return [];
}

/**
 * Safely extracts object data from API responses.
 * Handles both raw objects and wrapped { data: {...} } responses.
 *
 * @param response - The JSON response from the API
 * @param fallback - Fallback value if extraction fails
 * @returns The extracted object, or fallback if extraction fails
 *
 * @example
 * const res = await fetch('/api/v1/config');
 * const json = await res.json();
 * setConfig(extractObjectData<Config>(json, defaultConfig));
 */
export function extractObjectData<T extends object>(response: unknown, fallback: T): T {
  // Handle null/undefined
  if (response == null) {
    return fallback;
  }

  // If it's an object (but not array)
  if (typeof response === 'object' && !Array.isArray(response)) {
    // If it has a 'data' property that's an object, extract it
    if ('data' in response) {
      const data = (response as { data: unknown }).data;
      if (data != null && typeof data === 'object' && !Array.isArray(data)) {
        return data as T;
      }
    }
    // Otherwise return the response itself (it might be the raw data)
    return response as T;
  }

  return fallback;
}

/**
 * Safely extracts an error message from API error responses.
 * Handles Pydantic v2 validation errors (array of {type, loc, msg, input, ctx} objects),
 * single error objects, and plain string messages.
 *
 * IMPORTANT: Always use this function to extract error messages before rendering.
 * Never render `data.detail` directly in JSX - it may be an object which causes
 * React error #31 "Objects are not valid as a React child".
 *
 * @param detail - The detail field from the error response (can be string, object, or array)
 * @param fallback - Fallback message if extraction fails (default: 'An error occurred')
 * @returns A string error message safe to render in JSX
 *
 * @example
 * const res = await fetch('/api/v1/rtus', { method: 'POST', body: ... });
 * if (!res.ok) {
 *   const data = await res.json();
 *   setError(extractErrorMessage(data.detail, 'Failed to create RTU'));
 * }
 */
export function extractErrorMessage(detail: unknown, fallback = 'An error occurred'): string {
  // Handle null/undefined
  if (detail == null) {
    return fallback;
  }

  // If it's already a string, return it
  if (typeof detail === 'string') {
    return detail;
  }

  // If it's an array (Pydantic v2 validation errors)
  if (Array.isArray(detail)) {
    const messages = detail
      .map((err: { msg?: string; message?: string }) => err.msg || err.message || 'Invalid value')
      .filter(Boolean);
    return messages.length > 0 ? messages.join('; ') : fallback;
  }

  // If it's an object with a msg or message property
  if (typeof detail === 'object') {
    const obj = detail as { msg?: string; message?: string; detail?: string };
    if (obj.msg) return obj.msg;
    if (obj.message) return obj.message;
    if (obj.detail && typeof obj.detail === 'string') return obj.detail;
  }

  // Fallback - don't try to render the object
  return fallback;
}
