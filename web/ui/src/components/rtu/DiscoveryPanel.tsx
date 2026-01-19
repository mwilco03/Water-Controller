'use client';

import { useState, useCallback } from 'react';
import { discoverRTUs, getCachedDiscovery, clearDiscoveryCache, pingScanSubnet } from '@/lib/api';
import type { DiscoveredDevice, PingResult, PingScanResponse } from '@/lib/api';

interface Props {
  onDeviceSelect?: (device: DiscoveredDevice) => void;
}

export default function DiscoveryPanel({ onDeviceSelect }: Props) {
  const [devices, setDevices] = useState<DiscoveredDevice[]>([]);
  const [scanning, setScanning] = useState(false);
  const [lastScan, setLastScan] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scanTimeout, setScanTimeout] = useState(5000);

  // Ping scan state
  const [pingSubnet, setPingSubnet] = useState('192.168.1.0/24');
  const [pingScanning, setPingScanning] = useState(false);
  const [pingResults, setPingResults] = useState<PingScanResponse | null>(null);
  const [pingError, setPingError] = useState<string | null>(null);
  const [showPingResults, setShowPingResults] = useState(false);
  const [showOnlyReachable, setShowOnlyReachable] = useState(true);

  const handleScan = useCallback(async () => {
    if (scanning) return;
    setScanning(true);
    setError(null);

    try {
      const discoveredDevices = await discoverRTUs(scanTimeout);
      setDevices(discoveredDevices);
      setLastScan(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scan failed');
    } finally {
      setScanning(false);
    }
  }, [scanning, scanTimeout]);

  const handleLoadCached = useCallback(async () => {
    try {
      const cachedDevices = await getCachedDiscovery();
      setDevices(cachedDevices);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load cached devices');
    }
  }, []);

  const handleClearCache = useCallback(async () => {
    try {
      await clearDiscoveryCache();
      setDevices([]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear cache');
    }
  }, []);

  const handlePingScan = useCallback(async () => {
    if (pingScanning) return;
    setPingScanning(true);
    setPingError(null);

    try {
      const results = await pingScanSubnet(pingSubnet, 500);
      setPingResults(results);
      setShowPingResults(true);
    } catch (err) {
      setPingError(err instanceof Error ? err.message : 'Ping scan failed');
    } finally {
      setPingScanning(false);
    }
  }, [pingScanning, pingSubnet]);

  const formatMac = (mac: string) => {
    if (mac.includes(':')) return mac.toUpperCase();
    return mac.match(/.{2}/g)?.join(':').toUpperCase() || mac;
  };

  const filteredPingResults = pingResults?.results.filter(r => !showOnlyReachable || r.reachable) || [];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <span className="text-blue-400 font-bold">[*]</span>
          Network Discovery
        </h3>
        <div className="flex items-center gap-2 text-sm text-gray-400">
          {lastScan && (
            <span>Last scan: {lastScan.toLocaleTimeString()}</span>
          )}
        </div>
      </div>

      {/* PROFINET Discovery Controls */}
      <div className="p-4 bg-gray-800/50 border border-gray-700 rounded-lg">
        <h4 className="text-sm font-medium text-gray-300 mb-3">PROFINET DCP Discovery</h4>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-400">Timeout:</label>
            <select
              value={scanTimeout}
              onChange={(e) => setScanTimeout(Number(e.target.value))}
              className="px-2 py-1 bg-gray-800 border border-gray-700 rounded text-white text-sm"
              disabled={scanning}
            >
              <option value={3000}>3 seconds</option>
              <option value={5000}>5 seconds</option>
              <option value={10000}>10 seconds</option>
              <option value={15000}>15 seconds</option>
            </select>
          </div>

          <button
            onClick={handleScan}
            disabled={scanning}
            className={`
              flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm
              transition-all duration-200
              ${scanning
                ? 'bg-blue-700 text-blue-300 cursor-wait'
                : 'bg-blue-600 hover:bg-blue-500 text-white hover:shadow-lg hover:shadow-blue-600/25'
              }
            `}
          >
            {scanning ? (
              <span className="inline-block w-4 h-4 border-2 border-blue-300/30 border-t-blue-300 rounded-full animate-spin" />
            ) : (
              <span className="font-bold">[*]</span>
            )}
            {scanning ? 'Scanning...' : 'DCP Scan'}
          </button>

          <button
            onClick={handleLoadCached}
            disabled={scanning}
            className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-white transition-colors"
          >
            Load Cached
          </button>

          <button
            onClick={handleClearCache}
            disabled={scanning}
            className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-white transition-colors"
          >
            Clear Cache
          </button>
        </div>
      </div>

      {/* Ping Scan Controls */}
      <div className="p-4 bg-gray-800/50 border border-gray-700 rounded-lg">
        <h4 className="text-sm font-medium text-gray-300 mb-3">Ping Scan (Debug)</h4>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-400">Subnet:</label>
            <input
              type="text"
              value={pingSubnet}
              onChange={(e) => setPingSubnet(e.target.value)}
              placeholder="192.168.1.0/24"
              className="px-3 py-1 bg-gray-800 border border-gray-700 rounded text-white text-sm font-mono w-40"
              disabled={pingScanning}
            />
          </div>

          <button
            onClick={handlePingScan}
            disabled={pingScanning}
            className={`
              flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm
              transition-all duration-200
              ${pingScanning
                ? 'bg-green-700 text-green-300 cursor-wait'
                : 'bg-green-600 hover:bg-green-500 text-white hover:shadow-lg hover:shadow-green-600/25'
              }
            `}
          >
            {pingScanning ? (
              <span className="inline-block w-4 h-4 border-2 border-green-300/30 border-t-green-300 rounded-full animate-spin" />
            ) : (
              <span className="font-bold">[~]</span>
            )}
            {pingScanning ? 'Scanning 254 hosts...' : 'Ping Scan'}
          </button>

          {pingResults && (
            <button
              onClick={() => setShowPingResults(!showPingResults)}
              className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-white transition-colors"
            >
              {showPingResults ? 'Hide Results' : 'Show Results'}
            </button>
          )}
        </div>

        {pingResults && (
          <div className="mt-2 text-sm text-gray-400">
            Found {pingResults.reachable_count} reachable / {pingResults.total_hosts} total in {pingResults.scan_duration_seconds}s
          </div>
        )}
      </div>

      {/* Error displays */}
      {error && (
        <div className="p-3 bg-red-900/50 border border-red-700 rounded-lg text-red-200 text-sm">
          PROFINET Error: {error}
        </div>
      )}
      {pingError && (
        <div className="p-3 bg-red-900/50 border border-red-700 rounded-lg text-red-200 text-sm">
          Ping Error: {pingError}
        </div>
      )}

      {/* Scanning indicator */}
      {scanning && (
        <div className="flex items-center gap-3 p-4 bg-blue-900/30 border border-blue-700/50 rounded-lg">
          <div className="relative">
            <div className="w-10 h-10 border-4 border-blue-900 rounded-full" />
            <div className="absolute inset-0 w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
          <div>
            <div className="text-white font-medium">Scanning PROFINET network...</div>
            <div className="text-sm text-gray-400">Sending DCP Identify All broadcast</div>
          </div>
        </div>
      )}

      {/* Ping scan results table */}
      {showPingResults && pingResults && (
        <div className="border border-gray-700 rounded-lg overflow-hidden">
          <div className="bg-gray-800 px-4 py-2 flex items-center justify-between">
            <h4 className="text-sm font-medium text-gray-300">
              Ping Scan Results: {pingResults.subnet}
            </h4>
            <label className="flex items-center gap-2 text-sm text-gray-400">
              <input
                type="checkbox"
                checked={showOnlyReachable}
                onChange={(e) => setShowOnlyReachable(e.target.checked)}
                className="rounded"
              />
              Show only reachable
            </label>
          </div>
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-800/50 text-left text-xs text-gray-400 sticky top-0">
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2">IP Address</th>
                  <th className="px-4 py-2">Response Time</th>
                  <th className="px-4 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700/50">
                {filteredPingResults.map((result) => (
                  <tr
                    key={result.ip_address}
                    className={result.reachable ? 'bg-green-900/10' : 'bg-gray-800/30'}
                  >
                    <td className="px-4 py-2">
                      {result.reachable ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-green-900/50 text-green-300 rounded text-xs">
                          [OK]
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-700 text-gray-400 rounded text-xs">
                          [--]
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 font-mono text-sm text-gray-300">
                      {result.ip_address}
                    </td>
                    <td className="px-4 py-2 text-sm text-gray-400">
                      {result.reachable && result.response_time_ms !== null
                        ? `${result.response_time_ms}ms`
                        : '-'}
                    </td>
                    <td className="px-4 py-2">
                      {result.reachable && (
                        <button
                          onClick={() => {
                            // Create a mock device for selection
                            const mockDevice: DiscoveredDevice = {
                              id: 0,
                              mac_address: '00:00:00:00:00:00',
                              ip_address: result.ip_address,
                              device_name: null,
                              vendor_name: 'Unknown (from ping)',
                              device_type: 'Unknown',
                              vendor_id: null,
                              device_id: null,
                              discovered_at: new Date().toISOString(),
                              added_to_registry: false,
                              rtu_name: null,
                            };
                            onDeviceSelect?.(mockDevice);
                          }}
                          className="px-2 py-1 bg-blue-600 hover:bg-blue-500 rounded text-xs text-white font-medium transition-colors"
                        >
                          Use IP
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* PROFINET Device list */}
      {!scanning && devices.length > 0 && (
        <div className="border border-gray-700 rounded-lg overflow-hidden">
          <div className="bg-gray-800 px-4 py-2">
            <h4 className="text-sm font-medium text-gray-300">PROFINET Devices Found</h4>
          </div>
          <table className="w-full">
            <thead>
              <tr className="bg-gray-800/50 text-left text-sm text-gray-400">
                <th className="px-4 py-3">Device</th>
                <th className="px-4 py-3">MAC Address</th>
                <th className="px-4 py-3">IP Address</th>
                <th className="px-4 py-3">Vendor</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {devices.map((device) => (
                <tr
                  key={device.mac_address}
                  className={`transition-colors ${
                    device.added_to_registry
                      ? 'bg-green-900/10'
                      : 'hover:bg-gray-800/50'
                  }`}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2 h-2 rounded-full"
                        style={{
                          backgroundColor: device.added_to_registry ? '#10b981' : '#3b82f6',
                        }}
                      />
                      <div>
                        <div className="text-white font-medium">
                          {device.device_name || 'Unknown Device'}
                        </div>
                        <div className="text-xs text-gray-500">
                          {device.device_type || 'PROFINET Device'}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-sm text-gray-300">
                    {formatMac(device.mac_address)}
                  </td>
                  <td className="px-4 py-3 font-mono text-sm text-gray-300">
                    {device.ip_address || 'No IP'}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-400">
                    {device.vendor_name || 'Unknown'}
                    {device.vendor_id && (
                      <span className="text-xs text-gray-500 ml-1">
                        (0x{device.vendor_id.toString(16).padStart(4, '0')})
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {device.added_to_registry ? (
                      <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-900/50 text-green-300 rounded text-xs">
                        [OK] Added
                      </span>
                    ) : (
                      <span className="px-2 py-1 bg-blue-900/50 text-blue-300 rounded text-xs">
                        New
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {!device.added_to_registry && (
                      <button
                        onClick={() => onDeviceSelect?.(device)}
                        className="px-3 py-1 bg-green-600 hover:bg-green-500 rounded text-xs text-white font-medium transition-colors"
                      >
                        Add RTU
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty state */}
      {!scanning && devices.length === 0 && !showPingResults && (
        <div className="text-center py-6 text-gray-400">
          <div className="text-3xl mb-3 opacity-50">[?]</div>
          <p className="text-base font-medium text-gray-300">No devices found</p>
          <p className="text-sm mt-1">
            Click &quot;DCP Scan&quot; for PROFINET discovery or &quot;Ping Scan&quot; to find active IPs
          </p>
        </div>
      )}

      {/* Help text */}
      <div className="text-xs text-gray-500 space-y-1">
        <p>
          <strong>DCP Scan:</strong> Uses PROFINET Discovery and Configuration Protocol to find devices.
        </p>
        <p>
          <strong>Ping Scan:</strong> Pings all 254 hosts in the /24 subnet to find active IPs. Use this if DCP discovery fails.
        </p>
      </div>
    </div>
  );
}
