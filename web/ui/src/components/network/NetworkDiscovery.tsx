'use client';

import { useState, useCallback, useEffect } from 'react';
import { networkLogger } from '@/lib/logger';

// Response from /api/v1/discover/rtu endpoint
interface ApiDiscoveredDevice {
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
  firmware_version: string | null;
}

// UI display format
interface DiscoveredDevice {
  mac_address: string;
  ip_address: string | null;
  device_name: string;
  device_type: string;
  vendor_id: number;
  device_id: number;
  vendor_name: string;
  profinet_role: 'device' | 'controller' | 'supervisor';
  status: 'online' | 'offline' | 'configuring';
  configured: boolean;
  station_name?: string;
  last_seen: string;
  response_time_ms?: number;
  firmware_version?: string;
}

// Map API response to UI format
function mapApiDevice(dev: ApiDiscoveredDevice): DiscoveredDevice {
  return {
    mac_address: dev.mac_address,
    ip_address: dev.ip_address,
    device_name: dev.device_name || dev.rtu_name || 'Unknown Device',
    device_type: dev.device_type || 'PROFINET Device',
    vendor_id: dev.vendor_id || 0,
    device_id: dev.device_id || 0,
    vendor_name: dev.vendor_name || 'Unknown',
    profinet_role: 'device', // DCP only discovers devices
    status: 'online', // If discovered, it responded
    configured: dev.added_to_registry,
    station_name: dev.rtu_name || undefined,
    last_seen: dev.discovered_at,
    firmware_version: dev.firmware_version || undefined,
  };
}

interface ScanProgress {
  phase: 'idle' | 'dcp_identify' | 'lldp_scan' | 'arp_scan' | 'complete';
  progress: number;
  devices_found: number;
  message: string;
}

interface Props {
  onDeviceSelect?: (device: DiscoveredDevice) => void;
  onAddDevice?: (device: DiscoveredDevice) => void;
}

const deviceTypeIcons: Record<string, JSX.Element> = {
  'IO-Device': (
    <span className="text-sm font-bold">[IO]</span>
  ),
  'Controller': (
    <span className="text-sm font-bold">[CTL]</span>
  ),
  'Switch': (
    <span className="text-sm font-bold">[SW]</span>
  ),
  'HMI': (
    <span className="text-sm font-bold">[HMI]</span>
  ),
  'Drive': (
    <span className="text-sm font-bold">[VFD]</span>
  ),
};

export default function NetworkDiscovery({ onDeviceSelect, onAddDevice }: Props) {
  const [devices, setDevices] = useState<DiscoveredDevice[]>([]);
  const [scanning, setScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState<ScanProgress>({
    phase: 'idle',
    progress: 0,
    devices_found: 0,
    message: 'Ready to scan',
  });
  const [selectedDevice, setSelectedDevice] = useState<DiscoveredDevice | null>(null);
  const [filter, setFilter] = useState<'all' | 'unconfigured' | 'online'>('all');
  const [sortBy, setSortBy] = useState<'name' | 'ip' | 'vendor' | 'response'>('name');
  const [networkRange, setNetworkRange] = useState('192.168.1.0/24');
  const [scanMethods, setScanMethods] = useState({
    dcp: true,
    lldp: true,
    arp: false,
  });

  const startScan = useCallback(async () => {
    setScanning(true);
    setDevices([]);
    setScanProgress({ phase: 'dcp_identify', progress: 0, devices_found: 0, message: 'Starting PROFINET DCP discovery...' });

    try {
      // Call the real DCP discovery endpoint
      const res = await fetch('/api/v1/discover/rtu', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subnet: networkRange,
          timeout_seconds: 10,
        }),
      });

      if (res.ok) {
        const response = await res.json();
        // Backend wraps in { data: { devices: [...], scan_duration_seconds: ... } }
        const data = response.data || response;
        const apiDevices: ApiDiscoveredDevice[] = data.devices || [];
        const mappedDevices = apiDevices.map(mapApiDevice);

        setDevices(mappedDevices);
        setScanProgress({
          phase: 'complete',
          progress: 100,
          devices_found: mappedDevices.length,
          message: `Scan complete. Found ${mappedDevices.length} devices in ${data.scan_duration_seconds || 0}s.`,
        });
      } else {
        const errorData = await res.json().catch(() => ({}));
        networkLogger.error('Network discovery failed', { status: res.status, error: errorData });

        // Extract error message from various formats
        let errorMsg = 'Check network connection and container permissions.';
        if (errorData.detail) {
          if (typeof errorData.detail === 'string') {
            errorMsg = errorData.detail;
          } else if (errorData.detail.message) {
            errorMsg = errorData.detail.message;
          }
        }

        setScanProgress({
          phase: 'complete',
          progress: 100,
          devices_found: 0,
          message: `Scan failed: ${errorMsg}`,
        });
      }
    } catch (err) {
      networkLogger.error('Network discovery error', { error: err });
      setScanProgress({
        phase: 'complete',
        progress: 100,
        devices_found: 0,
        message: 'Scan failed. Check network connection.',
      });
    } finally {
      setScanning(false);
    }
  }, [networkRange]);

  const handleDeviceClick = (device: DiscoveredDevice) => {
    setSelectedDevice(device);
    onDeviceSelect?.(device);
  };

  const handleAddDevice = (device: DiscoveredDevice) => {
    onAddDevice?.(device);
  };

  const filteredDevices = devices
    .filter(d => {
      if (filter === 'unconfigured') return !d.configured;
      if (filter === 'online') return d.status === 'online';
      return true;
    })
    .sort((a, b) => {
      switch (sortBy) {
        case 'ip':
          return (a.ip_address || '').localeCompare(b.ip_address || '');
        case 'vendor':
          return a.vendor_name.localeCompare(b.vendor_name);
        case 'response':
          return (a.response_time_ms || 999) - (b.response_time_ms || 999);
        default:
          return a.device_name.localeCompare(b.device_name);
      }
    });

  return (
    <div className="space-y-4">
      {/* Scan Controls */}
      <div className="bg-gray-800/50 rounded-lg p-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs text-gray-400 mb-1">Network Range</label>
            <input
              type="text"
              value={networkRange}
              onChange={(e) => setNetworkRange(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
              placeholder="192.168.1.0/24"
              disabled={scanning}
            />
          </div>

          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={scanMethods.dcp}
                onChange={(e) => setScanMethods(prev => ({ ...prev, dcp: e.target.checked }))}
                disabled={scanning}
                className="rounded"
              />
              DCP
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={scanMethods.lldp}
                onChange={(e) => setScanMethods(prev => ({ ...prev, lldp: e.target.checked }))}
                disabled={scanning}
                className="rounded"
              />
              LLDP
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={scanMethods.arp}
                onChange={(e) => setScanMethods(prev => ({ ...prev, arp: e.target.checked }))}
                disabled={scanning}
                className="rounded"
              />
              ARP
            </label>
          </div>

          <button
            onClick={startScan}
            disabled={scanning}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 rounded text-white font-medium transition-colors"
          >
            {scanning ? (
              <>
                <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Scanning...
              </>
            ) : (
              <>
                <span className="text-sm font-bold">[*]</span>
                Start Scan
              </>
            )}
          </button>
        </div>

        {/* Progress Bar */}
        {scanning && (
          <div className="mt-4">
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>{scanProgress.message}</span>
              <span>{scanProgress.progress}%</span>
            </div>
            <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 transition-all duration-300"
                style={{ width: `${scanProgress.progress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Filter & Sort */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">Filter:</span>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as typeof filter)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
          >
            <option value="all">All Devices</option>
            <option value="unconfigured">Unconfigured</option>
            <option value="online">Online Only</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">Sort:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
          >
            <option value="name">Name</option>
            <option value="ip">IP Address</option>
            <option value="vendor">Vendor</option>
            <option value="response">Response Time</option>
          </select>
        </div>
        <div className="ml-auto text-sm text-gray-400">
          {filteredDevices.length} device{filteredDevices.length !== 1 ? 's' : ''}
        </div>
      </div>

      {/* Device List */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Device Cards */}
        <div className="space-y-3 max-h-[600px] overflow-y-auto">
          {filteredDevices.length === 0 && !scanning ? (
            <div className="text-center py-6 text-gray-400">
              <div className="text-3xl mb-3 opacity-50">[?]</div>
              <p className="text-base">No devices found</p>
              <p className="text-sm mt-1">Click &quot;Start Scan&quot; to discover network devices</p>
            </div>
          ) : (
            filteredDevices.map((device) => (
              <div
                key={device.mac_address}
                onClick={() => handleDeviceClick(device)}
                className={`bg-gray-800/50 rounded-lg p-4 cursor-pointer border-2 transition-all ${
                  selectedDevice?.mac_address === device.mac_address
                    ? 'border-blue-500 bg-blue-900/20'
                    : 'border-transparent hover:border-gray-600'
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                    device.status === 'online' ? 'bg-green-600/20 text-green-400' :
                    device.status === 'configuring' ? 'bg-yellow-600/20 text-yellow-400' :
                    'bg-gray-600/20 text-gray-400'
                  }`}>
                    {deviceTypeIcons[device.device_type] || deviceTypeIcons['IO-Device']}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-white truncate">{device.device_name}</span>
                      {device.configured && (
                        <span className="text-xs px-1.5 py-0.5 bg-green-600/20 text-green-400 rounded">
                          Configured
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-gray-400">{device.vendor_name}</div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                      <span className="font-mono">{device.ip_address || 'No IP'}</span>
                      <span className="font-mono">{device.mac_address}</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`w-2 h-2 rounded-full ${
                      device.status === 'online' ? 'bg-green-400' :
                      device.status === 'configuring' ? 'bg-yellow-400 animate-pulse' :
                      'bg-gray-400'
                    }`} />
                    {device.response_time_ms && (
                      <div className="text-xs text-gray-500 mt-1">
                        {device.response_time_ms}ms
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Device Details */}
        <div className="bg-gray-800/50 rounded-lg p-4">
          {selectedDevice ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-medium text-white">{selectedDevice.device_name}</h3>
                <div className={`px-2 py-1 rounded text-xs font-medium ${
                  selectedDevice.status === 'online' ? 'bg-green-600/20 text-green-400' :
                  selectedDevice.status === 'configuring' ? 'bg-yellow-600/20 text-yellow-400' :
                  'bg-gray-600/20 text-gray-400'
                }`}>
                  {selectedDevice.status.toUpperCase()}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-gray-400 text-xs mb-1">Device Type</div>
                  <div className="text-white">{selectedDevice.device_type}</div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs mb-1">PROFINET Role</div>
                  <div className="text-white capitalize">{selectedDevice.profinet_role}</div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs mb-1">IP Address</div>
                  <div className="text-white font-mono">{selectedDevice.ip_address || 'Not assigned'}</div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs mb-1">MAC Address</div>
                  <div className="text-white font-mono">{selectedDevice.mac_address}</div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs mb-1">Vendor</div>
                  <div className="text-white">{selectedDevice.vendor_name}</div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs mb-1">Vendor/Device ID</div>
                  <div className="text-white font-mono">
                    {selectedDevice.vendor_id != null ? `0x${selectedDevice.vendor_id.toString(16).toUpperCase().padStart(4, '0')}` : 'N/A'} /
                    {selectedDevice.device_id != null ? `0x${selectedDevice.device_id.toString(16).toUpperCase().padStart(4, '0')}` : 'N/A'}
                  </div>
                </div>
                {selectedDevice.firmware_version && (
                  <div>
                    <div className="text-gray-400 text-xs mb-1">Firmware</div>
                    <div className="text-white">{selectedDevice.firmware_version}</div>
                  </div>
                )}
                {selectedDevice.response_time_ms && (
                  <div>
                    <div className="text-gray-400 text-xs mb-1">Response Time</div>
                    <div className="text-white">{selectedDevice.response_time_ms} ms</div>
                  </div>
                )}
                <div>
                  <div className="text-gray-400 text-xs mb-1">Last Seen</div>
                  <div className="text-white">{new Date(selectedDevice.last_seen).toLocaleString()}</div>
                </div>
                {selectedDevice.station_name && (
                  <div>
                    <div className="text-gray-400 text-xs mb-1">Station Name</div>
                    <div className="text-white">{selectedDevice.station_name}</div>
                  </div>
                )}
              </div>

              {!selectedDevice.configured && selectedDevice.profinet_role === 'device' && (
                <div className="flex gap-2 pt-4 border-t border-gray-700">
                  <button
                    onClick={() => handleAddDevice(selectedDevice)}
                    className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-500 rounded text-white font-medium transition-colors"
                  >
                    Add as RTU
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-6 text-gray-400">
              <div className="text-2xl mb-2 opacity-50">[+]</div>
              <p className="text-sm">Select a device to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
