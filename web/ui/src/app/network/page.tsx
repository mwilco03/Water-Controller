'use client';

import { useEffect, useState } from 'react';
import { networkLogger } from '@/lib/logger';
import { PORTS, getCurrentHost } from '@/config/ports';

interface NetworkConfig {
  mode: 'dhcp' | 'static';
  ip_address: string;
  netmask: string;
  gateway: string;
  dns_primary: string;
  dns_secondary: string;
  hostname: string;
}

interface WebConfig {
  port: number;
  bind_address: string;
  https_enabled: boolean;
  https_port: number;
}

interface NetworkInterface {
  name: string;
  ip_address: string;
  netmask: string;
  mac_address: string;
  state: string;
  speed: string;
}

export default function NetworkPage() {
  const [networkConfig, setNetworkConfig] = useState<NetworkConfig>({
    mode: 'dhcp',
    ip_address: '',
    netmask: '255.255.255.0',
    gateway: '',
    dns_primary: '',
    dns_secondary: '',
    hostname: 'water-controller',
  });
  const [webConfig, setWebConfig] = useState<WebConfig>({
    port: PORTS.ui,
    bind_address: '0.0.0.0',
    https_enabled: false,
    https_port: PORTS.uiHttps,
  });
  const [interfaces, setInterfaces] = useState<NetworkInterface[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'warning'; text: string } | null>(null);
  const [showApplyConfirm, setShowApplyConfirm] = useState(false);

  useEffect(() => {
    fetchNetworkConfig();
    fetchWebConfig();
    fetchInterfaces();
  }, []);

  const showMessage = (type: 'success' | 'error' | 'warning', text: string) => {
    setMessage({ type, text });
    if (type !== 'warning') {
      setTimeout(() => setMessage(null), 5000);
    }
  };

  const fetchNetworkConfig = async () => {
    try {
      const res = await fetch('/api/v1/system/network');
      if (res.ok) {
        setNetworkConfig(await res.json());
      }
    } catch (error) {
      networkLogger.error('Failed to fetch network config', error);
    }
  };

  const fetchWebConfig = async () => {
    try {
      const res = await fetch('/api/v1/system/web');
      if (res.ok) {
        setWebConfig(await res.json());
      }
    } catch (error) {
      networkLogger.error('Failed to fetch web config', error);
    }
  };

  const fetchInterfaces = async () => {
    try {
      const res = await fetch('/api/v1/system/interfaces');
      if (res.ok) {
        const json = await res.json();
        const arr = Array.isArray(json) ? json : (json.data || json.interfaces || []);
        setInterfaces(arr);
      }
    } catch (error) {
      networkLogger.error('Failed to fetch interfaces', error);
    }
  };

  const validateIP = (ip: string): boolean => {
    const pattern = /^(\d{1,3}\.){3}\d{1,3}$/;
    if (!pattern.test(ip)) return false;
    const parts = ip.split('.').map(Number);
    return parts.every((p) => p >= 0 && p <= 255);
  };

  const validateConfig = (): string | null => {
    if (networkConfig.mode === 'static') {
      if (!validateIP(networkConfig.ip_address)) {
        return 'Invalid IP address format';
      }
      if (!validateIP(networkConfig.netmask)) {
        return 'Invalid netmask format';
      }
      if (networkConfig.gateway && !validateIP(networkConfig.gateway)) {
        return 'Invalid gateway format';
      }
      if (networkConfig.dns_primary && !validateIP(networkConfig.dns_primary)) {
        return 'Invalid primary DNS format';
      }
    }
    return null;
  };

  const applyNetworkConfig = async () => {
    const error = validateConfig();
    if (error) {
      showMessage('error', error);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch('/api/v1/system/network', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(networkConfig),
      });

      if (res.ok) {
        showMessage('warning', 'Network configuration applied. If you changed the IP address, you may need to reconnect to the new address.');
        setShowApplyConfirm(false);
      } else {
        const data = await res.json();
        showMessage('error', data.detail || 'Failed to apply network configuration');
      }
    } catch (error) {
      showMessage('error', 'Error applying network configuration');
    } finally {
      setLoading(false);
    }
  };

  const applyWebConfig = async () => {
    if (webConfig.port < 1 || webConfig.port > 65535) {
      showMessage('error', 'Port must be between 1 and 65535');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch('/api/v1/system/web', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(webConfig),
      });

      if (res.ok) {
        showMessage('success', 'Web server configuration saved. Restart required for port changes.');
      } else {
        const data = await res.json();
        showMessage('error', data.detail || 'Failed to save web configuration');
      }
    } catch (error) {
      showMessage('error', 'Error saving web configuration');
    } finally {
      setLoading(false);
    }
  };

  const getInterfaceStateBadge = (state: string) => {
    const colors: { [key: string]: string } = {
      UP: 'bg-status-ok text-white',
      DOWN: 'bg-status-alarm text-white',
      UNKNOWN: 'bg-hmi-panel text-hmi-muted',
    };
    return colors[state] || 'bg-hmi-panel text-hmi-muted';
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-hmi-text">Network Configuration</h1>

      {/* Message Banner */}
      {message && (
        <div
          className={`p-4 rounded-lg ${
            message.type === 'success'
              ? 'bg-status-ok text-white'
              : message.type === 'warning'
              ? 'bg-status-warning text-white'
              : 'bg-status-alarm text-white'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Network Interfaces */}
      <div className="hmi-card p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-hmi-text">Network Interfaces</h2>
          <button
            onClick={fetchInterfaces}
            className="px-3 py-1 bg-hmi-panel hover:bg-hmi-border rounded text-sm text-hmi-text"
          >
            Refresh
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {interfaces.map((iface) => (
            <div key={iface.name} className="bg-hmi-panel p-4 rounded">
              <div className="flex justify-between items-center mb-2">
                <span className="font-medium text-hmi-text">{iface.name}</span>
                <span className={`px-2 py-1 rounded text-xs ${getInterfaceStateBadge(iface.state)}`}>
                  {iface.state}
                </span>
              </div>
              <div className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-hmi-muted">IP Address:</span>
                  <span className="text-hmi-text font-mono">{iface.ip_address || 'Not assigned'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-hmi-muted">MAC:</span>
                  <span className="text-hmi-text font-mono">{iface.mac_address}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-hmi-muted">Speed:</span>
                  <span className="text-hmi-text">{iface.speed || 'Unknown'}</span>
                </div>
              </div>
            </div>
          ))}
        </div>

        {interfaces.length === 0 && (
          <p className="text-hmi-muted">No network interfaces detected</p>
        )}
      </div>

      {/* IP Configuration */}
      <div className="hmi-card p-6">
        <h2 className="text-lg font-semibold text-hmi-text mb-4">IP Configuration</h2>

        <div className="space-y-6">
          {/* Mode Selection */}
          <div>
            <label className="block text-sm text-hmi-muted mb-2">Network Mode</label>
            <div className="flex space-x-4">
              <label className="flex items-center">
                <input
                  type="radio"
                  name="networkMode"
                  checked={networkConfig.mode === 'dhcp'}
                  onChange={() => setNetworkConfig({ ...networkConfig, mode: 'dhcp' })}
                  className="mr-2"
                />
                <span className="text-hmi-text">DHCP (Automatic)</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="networkMode"
                  checked={networkConfig.mode === 'static'}
                  onChange={() => setNetworkConfig({ ...networkConfig, mode: 'static' })}
                  className="mr-2"
                />
                <span className="text-hmi-text">Static IP</span>
              </label>
            </div>
          </div>

          {/* Static IP Fields */}
          {networkConfig.mode === 'static' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-hmi-muted mb-1">IP Address</label>
                <input
                  type="text"
                  value={networkConfig.ip_address}
                  onChange={(e) =>
                    setNetworkConfig({ ...networkConfig, ip_address: e.target.value })
                  }
                  placeholder="192.168.1.100"
                  className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text font-mono"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Subnet Mask</label>
                <input
                  type="text"
                  value={networkConfig.netmask}
                  onChange={(e) => setNetworkConfig({ ...networkConfig, netmask: e.target.value })}
                  placeholder="255.255.255.0"
                  className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text font-mono"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Gateway</label>
                <input
                  type="text"
                  value={networkConfig.gateway}
                  onChange={(e) => setNetworkConfig({ ...networkConfig, gateway: e.target.value })}
                  placeholder="192.168.1.1"
                  className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text font-mono"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Hostname</label>
                <input
                  type="text"
                  value={networkConfig.hostname}
                  onChange={(e) => setNetworkConfig({ ...networkConfig, hostname: e.target.value })}
                  placeholder="water-controller"
                  className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Primary DNS</label>
                <input
                  type="text"
                  value={networkConfig.dns_primary}
                  onChange={(e) =>
                    setNetworkConfig({ ...networkConfig, dns_primary: e.target.value })
                  }
                  placeholder="8.8.8.8"
                  className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text font-mono"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Secondary DNS</label>
                <input
                  type="text"
                  value={networkConfig.dns_secondary}
                  onChange={(e) =>
                    setNetworkConfig({ ...networkConfig, dns_secondary: e.target.value })
                  }
                  placeholder="8.8.4.4"
                  className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text font-mono"
                />
              </div>
            </div>
          )}

          <div className="flex justify-end">
            <button
              onClick={() => setShowApplyConfirm(true)}
              className="px-4 py-2 bg-status-info hover:bg-status-info/90 rounded text-white"
            >
              Apply Network Settings
            </button>
          </div>
        </div>
      </div>

      {/* Web Server Configuration */}
      <div className="hmi-card p-6">
        <h2 className="text-lg font-semibold text-hmi-text mb-4">Web Server Configuration</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-hmi-muted mb-1">HTTP Port</label>
            <input
              type="number"
              value={webConfig.port}
              onChange={(e) => setWebConfig({ ...webConfig, port: parseInt(e.target.value) })}
              min="1"
              max="65535"
              className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
            />
            <p className="text-xs text-hmi-muted mt-1">Default: 8080</p>
          </div>

          <div>
            <label className="block text-sm text-hmi-muted mb-1">Bind Address</label>
            <input
              type="text"
              value={webConfig.bind_address}
              onChange={(e) => setWebConfig({ ...webConfig, bind_address: e.target.value })}
              placeholder="0.0.0.0"
              className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text font-mono"
            />
            <p className="text-xs text-hmi-muted mt-1">0.0.0.0 = all interfaces</p>
          </div>

          <div className="flex items-center space-x-2 pt-4">
            <input
              type="checkbox"
              id="httpsEnabled"
              checked={webConfig.https_enabled}
              onChange={(e) => setWebConfig({ ...webConfig, https_enabled: e.target.checked })}
            />
            <label htmlFor="httpsEnabled" className="text-sm text-hmi-muted">
              Enable HTTPS
            </label>
          </div>

          {webConfig.https_enabled && (
            <div>
              <label className="block text-sm text-hmi-muted mb-1">HTTPS Port</label>
              <input
                type="number"
                value={webConfig.https_port}
                onChange={(e) =>
                  setWebConfig({ ...webConfig, https_port: parseInt(e.target.value) })
                }
                min="1"
                max="65535"
                className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
              />
            </div>
          )}
        </div>

        <div className="flex justify-end mt-6">
          <button
            onClick={applyWebConfig}
            disabled={loading}
            className="px-4 py-2 bg-status-info hover:bg-status-info/90 rounded text-white disabled:opacity-50"
          >
            {loading ? 'Saving...' : 'Save Web Settings'}
          </button>
        </div>
      </div>

      {/* Current Connection Info */}
      <div className="hmi-card p-6">
        <h2 className="text-lg font-semibold text-hmi-text mb-4">Current Connection</h2>
        <div className="bg-hmi-panel p-4 rounded">
          <p className="text-hmi-muted">
            You are currently connected to this controller at:{' '}
            <span className="text-hmi-text font-mono">
              {getCurrentHost()}
            </span>
          </p>
          <p className="text-sm text-hmi-muted mt-2">
            If you change the IP address or port, you may need to reconnect using the new address.
          </p>
        </div>
      </div>

      {/* Apply Confirmation Modal */}
      {showApplyConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-hmi-bg p-6 rounded-lg w-full max-w-md">
            <h2 className="text-xl font-semibold text-hmi-text mb-4">Apply Network Configuration</h2>

            <div className="bg-status-warning text-white p-4 rounded mb-4">
              <strong>Warning:</strong> Changing network settings may cause you to lose connection to
              this device. Make sure you know the new address before applying.
            </div>

            {networkConfig.mode === 'static' && (
              <div className="bg-hmi-panel p-4 rounded mb-4">
                <p className="text-hmi-muted text-sm">
                  New IP address:{' '}
                  <span className="text-hmi-text font-mono">{networkConfig.ip_address}</span>
                </p>
              </div>
            )}

            <div className="flex justify-end space-x-3">
              <button
                onClick={() => setShowApplyConfirm(false)}
                className="px-4 py-2 bg-hmi-panel hover:bg-hmi-border rounded text-hmi-text"
              >
                Cancel
              </button>
              <button
                onClick={applyNetworkConfig}
                disabled={loading}
                className="px-4 py-2 bg-status-alarm hover:bg-status-alarm/90 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Applying...' : 'Apply Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
