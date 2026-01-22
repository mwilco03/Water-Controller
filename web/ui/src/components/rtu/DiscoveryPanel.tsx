'use client';

import { useState, useCallback } from 'react';
import { discoverRTUs, getCachedDiscovery, clearDiscoveryCache, pingScanSubnet, probeRtuConfig } from '@/lib/api';
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

  // RTU config probe state (when user clicks "Use IP")
  const [probingIp, setProbingIp] = useState<string | null>(null);
  const [probeError, setProbeError] = useState<string | null>(null);

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

  // Handler for "Use IP" button - fetches RTU config before selecting
  const handleUseIp = useCallback(async (ipAddress: string) => {
    if (probingIp) return; // Already probing another IP
    setProbingIp(ipAddress);
    setProbeError(null);

    try {
      // Fetch RTU config from /config endpoint
      const config = await probeRtuConfig(ipAddress, 9081, 5000);

      if (!config.reachable) {
        setProbeError(`Cannot reach ${ipAddress}: ${config.error || 'Connection failed'}`);
        return;
      }

      if (!config.station_name) {
        setProbeError(`RTU at ${ipAddress} did not return station_name in /config`);
        return;
      }

      // Create device with fetched config data
      const device: DiscoveredDevice = {
        id: 0,
        mac_address: '00:00:00:00:00:00', // Will be resolved via ARP/DCP at connect time
        ip_address: ipAddress,
        device_name: config.station_name,
        vendor_name: config.product_name || 'Water-Treat RTU',
        device_type: 'PROFINET Device',
        vendor_id: config.vendor_id,
        device_id: config.device_id,
        discovered_at: new Date().toISOString(),
        added_to_registry: false,
        rtu_name: null,
      };

      onDeviceSelect?.(device);
    } catch (err) {
      setProbeError(err instanceof Error ? err.message : `Failed to probe ${ipAddress}`);
    } finally {
      setProbingIp(null);
    }
  }, [probingIp, onDeviceSelect]);

  const formatMac = (mac: string) => {
    if (mac.includes(':')) return mac.toUpperCase();
    return mac.match(/.{2}/g)?.join(':').toUpperCase() || mac;
  };

  const filteredPingResults = pingResults?.results.filter(r => !showOnlyReachable || r.reachable) || [];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-hmi-text flex items-center gap-2">
          <span className="text-status-info font-bold">[*]</span>
          Network Discovery
        </h3>
        <div className="flex items-center gap-2 text-sm text-hmi-muted">
          {lastScan && (
            <span>Last scan: {lastScan.toLocaleTimeString()}</span>
          )}
        </div>
      </div>

      {/* PROFINET Discovery Controls */}
      <div className="p-4 bg-hmi-bg border border-hmi-border rounded-lg">
        <h4 className="text-sm font-medium text-hmi-text mb-3">PROFINET DCP Discovery</h4>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="text-sm text-hmi-muted">Timeout:</label>
            <select
              value={scanTimeout}
              onChange={(e) => setScanTimeout(Number(e.target.value))}
              className="px-2 py-1 bg-hmi-panel border border-hmi-border rounded text-hmi-text text-sm"
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
                ? 'bg-status-info/70 text-white cursor-wait'
                : 'bg-status-info hover:bg-status-info/90 text-white'
              }
            `}
          >
            {scanning ? (
              <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <span className="font-bold">[*]</span>
            )}
            {scanning ? 'Scanning...' : 'DCP Scan'}
          </button>

          <button
            onClick={handleLoadCached}
            disabled={scanning}
            className="px-3 py-2 bg-hmi-panel border border-hmi-border hover:bg-hmi-bg rounded-lg text-sm text-hmi-text transition-colors"
          >
            Load Cached
          </button>

          <button
            onClick={handleClearCache}
            disabled={scanning}
            className="px-3 py-2 bg-hmi-panel border border-hmi-border hover:bg-hmi-bg rounded-lg text-sm text-hmi-text transition-colors"
          >
            Clear Cache
          </button>
        </div>
      </div>

      {/* Ping Scan Controls */}
      <div className="p-4 bg-hmi-bg border border-hmi-border rounded-lg">
        <h4 className="text-sm font-medium text-hmi-text mb-3">Ping Scan (Debug)</h4>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="text-sm text-hmi-muted">Subnet:</label>
            <input
              type="text"
              value={pingSubnet}
              onChange={(e) => setPingSubnet(e.target.value)}
              placeholder="192.168.1.0/24"
              className="px-3 py-1 bg-hmi-panel border border-hmi-border rounded text-hmi-text text-sm font-mono w-40"
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
                ? 'bg-status-ok/70 text-white cursor-wait'
                : 'bg-status-ok hover:bg-status-ok/90 text-white'
              }
            `}
          >
            {pingScanning ? (
              <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <span className="font-bold">[~]</span>
            )}
            {pingScanning ? 'Scanning 254 hosts...' : 'Ping Scan'}
          </button>

          {pingResults && (
            <button
              onClick={() => setShowPingResults(!showPingResults)}
              className="px-3 py-2 bg-hmi-panel border border-hmi-border hover:bg-hmi-bg rounded-lg text-sm text-hmi-text transition-colors"
            >
              {showPingResults ? 'Hide Results' : 'Show Results'}
            </button>
          )}
        </div>

        {pingResults && (
          <div className="mt-2 text-sm text-hmi-muted">
            Found {pingResults.reachable_count} reachable / {pingResults.total_hosts} total in {pingResults.scan_duration_seconds}s
          </div>
        )}
      </div>

      {/* Error displays */}
      {error && (
        <div className="p-3 bg-status-alarm-light border border-status-alarm rounded-lg text-status-alarm text-sm">
          PROFINET Error: {error}
        </div>
      )}
      {pingError && (
        <div className="p-3 bg-status-alarm-light border border-status-alarm rounded-lg text-status-alarm text-sm">
          Ping Error: {pingError}
        </div>
      )}
      {probeError && (
        <div className="p-3 bg-status-alarm-light border border-status-alarm rounded-lg text-status-alarm text-sm flex justify-between items-center">
          <span>RTU Probe Error: {probeError}</span>
          <button
            onClick={() => setProbeError(null)}
            className="text-status-alarm hover:text-status-alarm/70 font-bold"
          >
            &times;
          </button>
        </div>
      )}

      {/* Scanning indicator */}
      {scanning && (
        <div className="flex items-center gap-3 p-4 bg-status-info-light border border-status-info/50 rounded-lg">
          <div className="relative">
            <div className="w-10 h-10 border-4 border-status-info/20 rounded-full" />
            <div className="absolute inset-0 w-10 h-10 border-4 border-status-info border-t-transparent rounded-full animate-spin" />
          </div>
          <div>
            <div className="text-hmi-text font-medium">Scanning PROFINET network...</div>
            <div className="text-sm text-hmi-muted">Sending DCP Identify All broadcast</div>
          </div>
        </div>
      )}

      {/* Ping scan results table */}
      {showPingResults && pingResults && (
        <div className="border border-hmi-border rounded-lg overflow-hidden">
          <div className="bg-hmi-bg px-4 py-2 flex items-center justify-between">
            <h4 className="text-sm font-medium text-hmi-text">
              Ping Scan Results: {pingResults.subnet}
            </h4>
            <label className="flex items-center gap-2 text-sm text-hmi-muted">
              <input
                type="checkbox"
                checked={showOnlyReachable}
                onChange={(e) => setShowOnlyReachable(e.target.checked)}
                className="rounded border-hmi-border"
              />
              Show only reachable
            </label>
          </div>
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-hmi-bg text-left text-xs text-hmi-muted sticky top-0">
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2">IP Address</th>
                  <th className="px-4 py-2">Response Time</th>
                  <th className="px-4 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hmi-border">
                {filteredPingResults.map((result) => (
                  <tr
                    key={result.ip_address}
                    className={result.reachable ? 'bg-status-ok-light' : 'bg-hmi-panel'}
                  >
                    <td className="px-4 py-2">
                      {result.reachable ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-status-ok/10 text-status-ok rounded text-xs font-medium">
                          [OK]
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-hmi-bg text-hmi-muted rounded text-xs">
                          [--]
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 font-mono text-sm text-hmi-text">
                      {result.ip_address}
                    </td>
                    <td className="px-4 py-2 text-sm text-hmi-muted">
                      {result.reachable && result.response_time_ms !== null
                        ? `${result.response_time_ms}ms`
                        : '-'}
                    </td>
                    <td className="px-4 py-2">
                      {result.reachable && (
                        <button
                          onClick={() => handleUseIp(result.ip_address)}
                          disabled={probingIp === result.ip_address}
                          className={`px-2 py-1 rounded text-xs text-white font-medium transition-colors ${
                            probingIp === result.ip_address
                              ? 'bg-status-info/50 cursor-wait'
                              : 'bg-status-info hover:bg-status-info/90'
                          }`}
                        >
                          {probingIp === result.ip_address ? (
                            <span className="flex items-center gap-1">
                              <span className="inline-block w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                              Fetching...
                            </span>
                          ) : (
                            'Use IP'
                          )}
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
        <div className="border border-hmi-border rounded-lg overflow-hidden">
          <div className="bg-hmi-bg px-4 py-2">
            <h4 className="text-sm font-medium text-hmi-text">PROFINET Devices Found</h4>
          </div>
          <table className="w-full">
            <thead>
              <tr className="bg-hmi-bg text-left text-sm text-hmi-muted">
                <th className="px-4 py-3">Device</th>
                <th className="px-4 py-3">MAC Address</th>
                <th className="px-4 py-3">IP Address</th>
                <th className="px-4 py-3">Vendor</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hmi-border">
              {devices.map((device) => (
                <tr
                  key={device.mac_address}
                  className={`transition-colors ${
                    device.added_to_registry
                      ? 'bg-status-ok-light'
                      : 'hover:bg-hmi-bg'
                  }`}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2 h-2 rounded-full"
                        style={{
                          backgroundColor: device.added_to_registry ? 'var(--status-ok)' : 'var(--status-info)',
                        }}
                      />
                      <div>
                        <div className="text-hmi-text font-medium">
                          {device.device_name || 'Unknown Device'}
                        </div>
                        <div className="text-xs text-hmi-muted">
                          {device.device_type || 'PROFINET Device'}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-sm text-hmi-text">
                    {formatMac(device.mac_address)}
                  </td>
                  <td className="px-4 py-3 font-mono text-sm text-hmi-text">
                    {device.ip_address || 'No IP'}
                  </td>
                  <td className="px-4 py-3 text-sm text-hmi-muted">
                    {device.vendor_name || 'Unknown'}
                    {device.vendor_id && (
                      <span className="text-xs text-hmi-muted ml-1">
                        (0x{device.vendor_id.toString(16).padStart(4, '0')})
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {device.added_to_registry ? (
                      <span className="inline-flex items-center gap-1 px-2 py-1 bg-status-ok/10 text-status-ok rounded text-xs font-medium">
                        [OK] Added
                      </span>
                    ) : (
                      <span className="px-2 py-1 bg-status-info/10 text-status-info rounded text-xs font-medium">
                        New
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {!device.added_to_registry && (
                      <button
                        onClick={() => onDeviceSelect?.(device)}
                        className="px-3 py-1 bg-status-ok hover:bg-status-ok/90 rounded text-xs text-white font-medium transition-colors"
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
        <div className="text-center py-6 text-hmi-muted">
          <div className="text-3xl mb-3 opacity-50">[?]</div>
          <p className="text-base font-medium text-hmi-text">No devices found</p>
          <p className="text-sm mt-1">
            Click &quot;DCP Scan&quot; for PROFINET discovery or &quot;Ping Scan&quot; to find active IPs
          </p>
        </div>
      )}

      {/* Help text */}
      <div className="text-xs text-hmi-muted space-y-1">
        <p>
          <strong className="text-hmi-text">DCP Scan:</strong> Uses PROFINET Discovery and Configuration Protocol to find devices.
        </p>
        <p>
          <strong className="text-hmi-text">Ping Scan:</strong> Pings all 254 hosts in the /24 subnet to find active IPs. Use this if DCP discovery fails.
        </p>
      </div>
    </div>
  );
}
