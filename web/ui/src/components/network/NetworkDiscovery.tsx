'use client';

import { useState, useCallback, useEffect } from 'react';
import { networkLogger } from '@/lib/logger';

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
  signal_strength?: number;
  firmware_version?: string;
  response_time_ms?: number;
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
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
    </svg>
  ),
  'Controller': (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
    </svg>
  ),
  'Switch': (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l4-4 4 4m0 6l-4 4-4-4" />
    </svg>
  ),
  'HMI': (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  ),
  'Drive': (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
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

  // Justification: simulateScan is a development-only fallback that reads current state.
  // Including it as a dependency would require converting it to useCallback, adding complexity
  // for a dev-only code path. startScan recreates when networkRange/scanMethods change.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const startScan = useCallback(async () => {
    setScanning(true);
    setDevices([]);
    setScanProgress({ phase: 'dcp_identify', progress: 0, devices_found: 0, message: 'Starting DCP Identify scan...' });

    try {
      const res = await fetch('/api/v1/network/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          network_range: networkRange,
          methods: scanMethods,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setDevices(data.devices || []);
        setScanProgress({
          phase: 'complete',
          progress: 100,
          devices_found: data.devices?.length || 0,
          message: `Scan complete. Found ${data.devices?.length || 0} devices.`,
        });
      } else {
        // Use mock data only in development
        if (process.env.NODE_ENV === 'development') {
          networkLogger.debug('Network discovery API unavailable, using mock data');
          await simulateScan();
        } else {
          setScanProgress({
            phase: 'complete',
            progress: 100,
            devices_found: 0,
            message: 'Scan failed. Check network connection.',
          });
        }
      }
    } catch (err) {
      // Use mock data only in development
      if (process.env.NODE_ENV === 'development') {
        networkLogger.debug('Network discovery API unavailable, using mock data');
        await simulateScan();
      } else {
        setScanProgress({
          phase: 'complete',
          progress: 100,
          devices_found: 0,
          message: 'Scan failed. Check network connection.',
        });
      }
    } finally {
      setScanning(false);
    }
  }, [networkRange, scanMethods]);

  const simulateScan = async () => {
    // Simulate DCP scan
    setScanProgress({ phase: 'dcp_identify', progress: 20, devices_found: 0, message: 'Sending DCP Identify requests...' });
    await new Promise(r => setTimeout(r, 800));

    setScanProgress({ phase: 'dcp_identify', progress: 40, devices_found: 2, message: 'Processing DCP responses...' });
    await new Promise(r => setTimeout(r, 600));

    // Simulate LLDP scan
    if (scanMethods.lldp) {
      setScanProgress({ phase: 'lldp_scan', progress: 60, devices_found: 3, message: 'Scanning LLDP neighbors...' });
      await new Promise(r => setTimeout(r, 700));
    }

    // Simulate ARP scan
    if (scanMethods.arp) {
      setScanProgress({ phase: 'arp_scan', progress: 80, devices_found: 4, message: 'Performing ARP scan...' });
      await new Promise(r => setTimeout(r, 500));
    }

    const mockDevices = getMockDevices();
    setDevices(mockDevices);
    setScanProgress({
      phase: 'complete',
      progress: 100,
      devices_found: mockDevices.length,
      message: `Scan complete. Found ${mockDevices.length} devices.`,
    });
  };

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
                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Scanning...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
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
              <svg className="w-10 h-10 max-w-10 max-h-10 mx-auto mb-3 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
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
                    0x{selectedDevice.vendor_id.toString(16).toUpperCase().padStart(4, '0')} /
                    0x{selectedDevice.device_id.toString(16).toUpperCase().padStart(4, '0')}
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

              <div className="flex gap-2 pt-4 border-t border-gray-700">
                {!selectedDevice.configured && selectedDevice.profinet_role === 'device' && (
                  <button
                    onClick={() => handleAddDevice(selectedDevice)}
                    className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-500 rounded text-white font-medium transition-colors"
                  >
                    Add as RTU
                  </button>
                )}
                <button
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white transition-colors"
                >
                  Configure IP
                </button>
                <button
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white transition-colors"
                >
                  Set Name
                </button>
              </div>
            </div>
          ) : (
            <div className="text-center py-6 text-gray-400">
              <svg className="w-8 h-8 max-w-8 max-h-8 mx-auto mb-2 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
              </svg>
              <p className="text-sm">Select a device to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Mock discovered devices
function getMockDevices(): DiscoveredDevice[] {
  return [
    {
      mac_address: '00:0E:8C:12:34:56',
      ip_address: '192.168.1.100',
      device_name: 'ET200SP-Station1',
      device_type: 'IO-Device',
      vendor_id: 0x002A,
      device_id: 0x0601,
      vendor_name: 'Siemens AG',
      profinet_role: 'device',
      status: 'online',
      configured: true,
      station_name: 'RTU-001',
      last_seen: new Date().toISOString(),
      firmware_version: 'V2.9.3',
      response_time_ms: 2,
    },
    {
      mac_address: '00:0E:8C:12:34:57',
      ip_address: '192.168.1.101',
      device_name: 'ET200SP-Station2',
      device_type: 'IO-Device',
      vendor_id: 0x002A,
      device_id: 0x0601,
      vendor_name: 'Siemens AG',
      profinet_role: 'device',
      status: 'online',
      configured: false,
      last_seen: new Date().toISOString(),
      firmware_version: 'V2.9.3',
      response_time_ms: 3,
    },
    {
      mac_address: '00:1B:1B:AA:BB:CC',
      ip_address: '192.168.1.50',
      device_name: 'SCALANCE X208',
      device_type: 'Switch',
      vendor_id: 0x002A,
      device_id: 0x0208,
      vendor_name: 'Siemens AG',
      profinet_role: 'device',
      status: 'online',
      configured: true,
      last_seen: new Date().toISOString(),
      firmware_version: 'V5.4.2',
      response_time_ms: 1,
    },
    {
      mac_address: '00:0E:8C:AB:CD:EF',
      ip_address: '192.168.1.1',
      device_name: 'Water-Controller',
      device_type: 'Controller',
      vendor_id: 0x002A,
      device_id: 0x030D,
      vendor_name: 'Siemens AG',
      profinet_role: 'controller',
      status: 'online',
      configured: true,
      last_seen: new Date().toISOString(),
      firmware_version: 'V4.5.0',
      response_time_ms: 0,
    },
    {
      mac_address: '00:30:DE:11:22:33',
      ip_address: null,
      device_name: 'New-Device',
      device_type: 'IO-Device',
      vendor_id: 0x00A0,
      device_id: 0x0001,
      vendor_name: 'Phoenix Contact',
      profinet_role: 'device',
      status: 'offline',
      configured: false,
      last_seen: new Date(Date.now() - 300000).toISOString(),
      response_time_ms: undefined,
    },
    {
      mac_address: '00:0E:8C:99:88:77',
      ip_address: '192.168.1.102',
      device_name: 'G120-VFD-01',
      device_type: 'Drive',
      vendor_id: 0x002A,
      device_id: 0x040B,
      vendor_name: 'Siemens AG',
      profinet_role: 'device',
      status: 'online',
      configured: false,
      last_seen: new Date().toISOString(),
      firmware_version: 'V4.8.1',
      response_time_ms: 4,
    },
  ];
}
