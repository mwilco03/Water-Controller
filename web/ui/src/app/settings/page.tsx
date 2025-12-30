'use client';

import { useEffect, useState } from 'react';
import { configLogger, systemLogger, modbusLogger } from '@/lib/logger';

const PAGE_TITLE = 'Settings - Water Treatment Controller';

interface Backup {
  backup_id: string;
  filename: string;
  created_at: string;
  size_bytes: number;
  description?: string;
  includes_historian: boolean;
}

interface ServiceStatus {
  [key: string]: string;
}

interface ModbusServerConfig {
  tcp_enabled: boolean;
  tcp_port: number;
  tcp_bind_address: string;
  rtu_enabled: boolean;
  rtu_device: string;
  rtu_baud_rate: number;
  rtu_parity: string;
  rtu_data_bits: number;
  rtu_stop_bits: number;
  rtu_slave_addr: number;
}

interface ModbusDownstreamDevice {
  device_id?: number;
  name: string;
  transport: string;
  tcp_host?: string;
  tcp_port: number;
  rtu_device?: string;
  rtu_baud_rate: number;
  slave_addr: number;
  poll_interval_ms: number;
  timeout_ms: number;
  enabled: boolean;
}

interface LogForwardingConfig {
  enabled: boolean;
  forward_type: string;
  host: string;
  port: number;
  protocol: string;
  index?: string;
  api_key?: string;
  tls_enabled: boolean;
  tls_verify: boolean;
  include_alarms: boolean;
  include_events: boolean;
  include_audit: boolean;
  log_level: string;
}

interface LogDestination {
  type: string;
  name: string;
  description: string;
  default_port: number;
  protocols: string[];
  requires_index?: boolean;
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<'general' | 'backup' | 'modbus' | 'services' | 'logging'>('general');
  const [backups, setBackups] = useState<Backup[]>([]);
  const [services, setServices] = useState<ServiceStatus>({});
  const [modbusConfig, setModbusConfig] = useState<ModbusServerConfig | null>(null);
  const [downstreamDevices, setDownstreamDevices] = useState<ModbusDownstreamDevice[]>([]);
  const [logConfig, setLogConfig] = useState<LogForwardingConfig | null>(null);
  const [logDestinations, setLogDestinations] = useState<LogDestination[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [newBackupDesc, setNewBackupDesc] = useState('');

  // Set page title
  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);
  const [includeHistorian, setIncludeHistorian] = useState(false);

  useEffect(() => {
    fetchBackups();
    fetchServices();
    fetchModbusConfig();
    fetchLogConfig();
  }, []);

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  // ============== Backup Functions ==============

  const fetchBackups = async () => {
    try {
      const res = await fetch('/api/v1/backups');
      if (res.ok) {
        setBackups(await res.json());
      }
    } catch (error) {
      configLogger.error('Failed to fetch backups', error);
    }
  };

  const createBackup = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/backups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: newBackupDesc,
          include_historian: includeHistorian,
        }),
      });

      if (res.ok) {
        showMessage('success', 'Backup created successfully');
        setNewBackupDesc('');
        fetchBackups();
      } else {
        showMessage('error', 'Failed to create backup');
      }
    } catch (error) {
      showMessage('error', 'Error creating backup');
    } finally {
      setLoading(false);
    }
  };

  const restoreBackup = async (backupId: string) => {
    if (!confirm('Are you sure you want to restore this backup? Current configuration will be overwritten.')) {
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`/api/v1/backups/${backupId}/restore`, {
        method: 'POST',
      });

      if (res.ok) {
        showMessage('success', 'Configuration restored successfully');
      } else {
        showMessage('error', 'Failed to restore backup');
      }
    } catch (error) {
      showMessage('error', 'Error restoring backup');
    } finally {
      setLoading(false);
    }
  };

  const downloadBackup = (backupId: string) => {
    window.open(`/api/v1/backups/${backupId}/download`, '_blank');
  };

  const deleteBackup = async (backupId: string) => {
    if (!confirm('Are you sure you want to delete this backup?')) {
      return;
    }

    try {
      const res = await fetch(`/api/v1/backups/${backupId}`, {
        method: 'DELETE',
      });

      if (res.ok) {
        showMessage('success', 'Backup deleted');
        fetchBackups();
      } else {
        showMessage('error', 'Failed to delete backup');
      }
    } catch (error) {
      showMessage('error', 'Error deleting backup');
    }
  };

  const exportConfig = async () => {
    try {
      const res = await fetch('/api/v1/system/config');
      if (res.ok) {
        const config = await res.json();
        const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `wtc_config_${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);
        showMessage('success', 'Configuration exported');
      }
    } catch (error) {
      showMessage('error', 'Failed to export configuration');
    }
  };

  const importConfig = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const config = JSON.parse(text);

      const res = await fetch('/api/v1/system/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });

      if (res.ok) {
        showMessage('success', 'Configuration imported successfully');
      } else {
        showMessage('error', 'Failed to import configuration');
      }
    } catch (error) {
      showMessage('error', 'Invalid configuration file');
    }

    event.target.value = '';
  };

  // ============== Service Functions ==============

  const fetchServices = async () => {
    try {
      const res = await fetch('/api/v1/services');
      if (res.ok) {
        setServices(await res.json());
      }
    } catch (error) {
      systemLogger.error('Failed to fetch services', error);
    }
  };

  const controlService = async (service: string, action: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/services/${service}/${action}`, {
        method: 'POST',
      });

      if (res.ok) {
        showMessage('success', `Service ${service} ${action}ed`);
        setTimeout(fetchServices, 2000);
      } else {
        showMessage('error', `Failed to ${action} ${service}`);
      }
    } catch (error) {
      showMessage('error', `Error ${action}ing service`);
    } finally {
      setLoading(false);
    }
  };

  // ============== Modbus Functions ==============

  const fetchModbusConfig = async () => {
    try {
      const [serverRes, devicesRes] = await Promise.all([
        fetch('/api/v1/modbus/server'),
        fetch('/api/v1/modbus/downstream'),
      ]);

      if (serverRes.ok) {
        setModbusConfig(await serverRes.json());
      }
      if (devicesRes.ok) {
        setDownstreamDevices(await devicesRes.json());
      }
    } catch (error) {
      modbusLogger.error('Failed to fetch Modbus config', error);
    }
  };

  const saveModbusConfig = async () => {
    if (!modbusConfig) return;

    setLoading(true);
    try {
      const res = await fetch('/api/v1/modbus/server', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(modbusConfig),
      });

      if (res.ok) {
        showMessage('success', 'Modbus configuration saved');
      } else {
        showMessage('error', 'Failed to save Modbus configuration');
      }
    } catch (error) {
      showMessage('error', 'Error saving configuration');
    } finally {
      setLoading(false);
    }
  };

  const restartModbus = async () => {
    try {
      const res = await fetch('/api/v1/modbus/restart', { method: 'POST' });
      if (res.ok) {
        showMessage('success', 'Modbus gateway restarting...');
      }
    } catch (error) {
      showMessage('error', 'Failed to restart Modbus gateway');
    }
  };

  // ============== Log Forwarding Functions ==============

  const fetchLogConfig = async () => {
    try {
      const [configRes, destRes] = await Promise.all([
        fetch('/api/v1/logging/config'),
        fetch('/api/v1/logging/destinations'),
      ]);

      if (configRes.ok) {
        setLogConfig(await configRes.json());
      }
      if (destRes.ok) {
        const data = await destRes.json();
        setLogDestinations(data.destinations || []);
      }
    } catch (error) {
      configLogger.error('Failed to fetch log config', error);
    }
  };

  const saveLogConfig = async () => {
    if (!logConfig) return;

    setLoading(true);
    try {
      const res = await fetch('/api/v1/logging/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(logConfig),
      });

      if (res.ok) {
        showMessage('success', 'Log forwarding configuration saved');
      } else {
        showMessage('error', 'Failed to save log configuration');
      }
    } catch (error) {
      showMessage('error', 'Error saving configuration');
    } finally {
      setLoading(false);
    }
  };

  const testLogForwarding = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/logging/test', { method: 'POST' });
      if (res.ok) {
        showMessage('success', 'Test log message sent successfully');
      } else {
        const data = await res.json();
        showMessage('error', data.detail || 'Failed to send test log');
      }
    } catch (error) {
      showMessage('error', 'Error sending test log');
    } finally {
      setLoading(false);
    }
  };

  const getSelectedDestination = (): LogDestination | undefined => {
    return logDestinations.find(d => d.type === logConfig?.forward_type);
  };

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  const getServiceStatusClass = (status: string) => {
    switch (status) {
      case 'active':
        return 'text-green-400';
      case 'inactive':
        return 'text-gray-400';
      case 'failed':
        return 'text-red-400';
      default:
        return 'text-yellow-400';
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Settings</h1>

      {/* Message Banner */}
      {message && (
        <div
          className={`p-4 rounded-lg ${
            message.type === 'success' ? 'bg-green-900 text-green-200' : 'bg-red-900 text-red-200'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Tabs */}
      <div className="flex space-x-4 border-b border-gray-700">
        {[
          { id: 'general', label: 'General' },
          { id: 'backup', label: 'Backup & Restore' },
          { id: 'modbus', label: 'Modbus Gateway' },
          { id: 'logging', label: 'Log Forwarding' },
          { id: 'services', label: 'Services' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-4 py-2 -mb-px ${
              activeTab === tab.id
                ? 'border-b-2 border-blue-500 text-blue-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* General Tab */}
      {activeTab === 'general' && (
        <div className="scada-panel p-6 space-y-6">
          <h2 className="text-lg font-semibold text-white">Configuration Import/Export</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-gray-300">Export Configuration</h3>
              <p className="text-sm text-gray-400">
                Download the current system configuration as a JSON file.
              </p>
              <button
                onClick={exportConfig}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white"
              >
                Export Configuration
              </button>
            </div>

            <div className="space-y-4">
              <h3 className="text-sm font-medium text-gray-300">Import Configuration</h3>
              <p className="text-sm text-gray-400">
                Upload a configuration file to restore settings.
              </p>
              <label className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white cursor-pointer inline-block">
                Import Configuration
                <input
                  type="file"
                  accept=".json"
                  onChange={importConfig}
                  className="hidden"
                />
              </label>
            </div>
          </div>
        </div>
      )}

      {/* Backup Tab */}
      {activeTab === 'backup' && (
        <div className="space-y-6">
          {/* Create Backup */}
          <div className="scada-panel p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Create New Backup</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-300 mb-1">Description (optional)</label>
                <input
                  type="text"
                  value={newBackupDesc}
                  onChange={(e) => setNewBackupDesc(e.target.value)}
                  placeholder="e.g., Before upgrade, Production config"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>

              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="includeHistorian"
                  checked={includeHistorian}
                  onChange={(e) => setIncludeHistorian(e.target.checked)}
                  className="rounded"
                />
                <label htmlFor="includeHistorian" className="text-sm text-gray-300">
                  Include historian data (larger backup)
                </label>
              </div>

              <button
                onClick={createBackup}
                disabled={loading}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Creating...' : 'Create Backup'}
              </button>
            </div>
          </div>

          {/* Backup List */}
          <div className="scada-panel p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Available Backups</h2>

            {backups.length === 0 ? (
              <p className="text-gray-400">No backups found</p>
            ) : (
              <div className="space-y-3">
                {backups.map((backup) => (
                  <div
                    key={backup.backup_id}
                    className="flex items-center justify-between p-4 bg-gray-800 rounded"
                  >
                    <div>
                      <div className="font-medium text-white">{backup.filename}</div>
                      <div className="text-sm text-gray-400">
                        {formatDate(backup.created_at)} - {formatBytes(backup.size_bytes)}
                        {backup.includes_historian && (
                          <span className="ml-2 px-2 py-0.5 bg-blue-900 text-blue-300 rounded text-xs">
                            Full
                          </span>
                        )}
                      </div>
                      {backup.description && (
                        <div className="text-sm text-gray-500">{backup.description}</div>
                      )}
                    </div>
                    <div className="flex space-x-2">
                      <button
                        onClick={() => downloadBackup(backup.backup_id)}
                        className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm text-white"
                      >
                        Download
                      </button>
                      <button
                        onClick={() => restoreBackup(backup.backup_id)}
                        className="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm text-white"
                      >
                        Restore
                      </button>
                      <button
                        onClick={() => deleteBackup(backup.backup_id)}
                        className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm text-white"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modbus Tab */}
      {activeTab === 'modbus' && modbusConfig && (
        <div className="space-y-6">
          {/* Server Configuration */}
          <div className="scada-panel p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-white">Modbus Server Configuration</h2>
              <button
                onClick={restartModbus}
                className="px-3 py-1 bg-yellow-600 hover:bg-yellow-700 rounded text-sm text-white"
              >
                Restart Gateway
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* TCP Settings */}
              <div className="space-y-4">
                <h3 className="font-medium text-gray-300">TCP Server</h3>

                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="tcpEnabled"
                    checked={modbusConfig.tcp_enabled}
                    onChange={(e) =>
                      setModbusConfig({ ...modbusConfig, tcp_enabled: e.target.checked })
                    }
                  />
                  <label htmlFor="tcpEnabled" className="text-sm text-gray-300">
                    Enable TCP Server
                  </label>
                </div>

                <div>
                  <label className="block text-sm text-gray-400 mb-1">Port</label>
                  <input
                    type="number"
                    value={modbusConfig.tcp_port}
                    onChange={(e) =>
                      setModbusConfig({ ...modbusConfig, tcp_port: parseInt(e.target.value) })
                    }
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  />
                </div>

                <div>
                  <label className="block text-sm text-gray-400 mb-1">Bind Address</label>
                  <input
                    type="text"
                    value={modbusConfig.tcp_bind_address}
                    onChange={(e) =>
                      setModbusConfig({ ...modbusConfig, tcp_bind_address: e.target.value })
                    }
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  />
                </div>
              </div>

              {/* RTU Settings */}
              <div className="space-y-4">
                <h3 className="font-medium text-gray-300">RTU Server (Serial)</h3>

                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="rtuEnabled"
                    checked={modbusConfig.rtu_enabled}
                    onChange={(e) =>
                      setModbusConfig({ ...modbusConfig, rtu_enabled: e.target.checked })
                    }
                  />
                  <label htmlFor="rtuEnabled" className="text-sm text-gray-300">
                    Enable RTU Server
                  </label>
                </div>

                <div>
                  <label className="block text-sm text-gray-400 mb-1">Serial Device</label>
                  <input
                    type="text"
                    value={modbusConfig.rtu_device}
                    onChange={(e) =>
                      setModbusConfig({ ...modbusConfig, rtu_device: e.target.value })
                    }
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Baud Rate</label>
                    <select
                      value={modbusConfig.rtu_baud_rate}
                      onChange={(e) =>
                        setModbusConfig({ ...modbusConfig, rtu_baud_rate: parseInt(e.target.value) })
                      }
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                    >
                      {[9600, 19200, 38400, 57600, 115200].map((rate) => (
                        <option key={rate} value={rate}>
                          {rate}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Slave Address</label>
                    <input
                      type="number"
                      value={modbusConfig.rtu_slave_addr}
                      onChange={(e) =>
                        setModbusConfig({ ...modbusConfig, rtu_slave_addr: parseInt(e.target.value) })
                      }
                      min="1"
                      max="247"
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Parity</label>
                    <select
                      value={modbusConfig.rtu_parity}
                      onChange={(e) =>
                        setModbusConfig({ ...modbusConfig, rtu_parity: e.target.value })
                      }
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                    >
                      <option value="N">None</option>
                      <option value="E">Even</option>
                      <option value="O">Odd</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Data Bits</label>
                    <select
                      value={modbusConfig.rtu_data_bits}
                      onChange={(e) =>
                        setModbusConfig({ ...modbusConfig, rtu_data_bits: parseInt(e.target.value) })
                      }
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                    >
                      <option value={7}>7</option>
                      <option value={8}>8</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Stop Bits</label>
                    <select
                      value={modbusConfig.rtu_stop_bits}
                      onChange={(e) =>
                        setModbusConfig({ ...modbusConfig, rtu_stop_bits: parseInt(e.target.value) })
                      }
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                    >
                      <option value={1}>1</option>
                      <option value={2}>2</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-6">
              <button
                onClick={saveModbusConfig}
                disabled={loading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Saving...' : 'Save Configuration'}
              </button>
            </div>
          </div>

          {/* Downstream Devices */}
          <div className="scada-panel p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Downstream Modbus Devices</h2>

            {downstreamDevices.length === 0 ? (
              <p className="text-gray-400">No downstream devices configured</p>
            ) : (
              <div className="space-y-3">
                {downstreamDevices.map((device) => (
                  <div
                    key={device.device_id}
                    className="flex items-center justify-between p-4 bg-gray-800 rounded"
                  >
                    <div>
                      <div className="font-medium text-white">{device.name}</div>
                      <div className="text-sm text-gray-400">
                        {device.transport === 'TCP'
                          ? `${device.tcp_host}:${device.tcp_port}`
                          : `${device.rtu_device} @ ${device.rtu_baud_rate}`}
                        {' - '}
                        Slave {device.slave_addr}
                      </div>
                    </div>
                    <div className={device.enabled ? 'text-green-400' : 'text-gray-500'}>
                      {device.enabled ? 'Enabled' : 'Disabled'}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Logging Tab */}
      {activeTab === 'logging' && logConfig && (
        <div className="space-y-6">
          {/* Destination Configuration */}
          <div className="scada-panel p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-white">Log Forwarding Configuration</h2>
              <div className="flex space-x-2">
                <button
                  onClick={testLogForwarding}
                  disabled={loading || !logConfig.enabled}
                  className="px-3 py-1 bg-yellow-600 hover:bg-yellow-700 disabled:opacity-50 rounded text-sm text-white"
                >
                  Test Connection
                </button>
              </div>
            </div>

            <div className="space-y-6">
              {/* Enable Toggle */}
              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="logEnabled"
                  checked={logConfig.enabled}
                  onChange={(e) => setLogConfig({ ...logConfig, enabled: e.target.checked })}
                />
                <label htmlFor="logEnabled" className="text-sm text-gray-300">
                  Enable Log Forwarding
                </label>
              </div>

              {/* Destination Type */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">Destination Type</label>
                <select
                  value={logConfig.forward_type}
                  onChange={(e) => {
                    const dest = logDestinations.find(d => d.type === e.target.value);
                    setLogConfig({
                      ...logConfig,
                      forward_type: e.target.value,
                      port: dest?.default_port || logConfig.port,
                      protocol: dest?.protocols[0] || logConfig.protocol,
                    });
                  }}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                >
                  {logDestinations.map((dest) => (
                    <option key={dest.type} value={dest.type}>
                      {dest.name}
                    </option>
                  ))}
                </select>
                {getSelectedDestination() && (
                  <p className="text-xs text-gray-500 mt-1">{getSelectedDestination()?.description}</p>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Host */}
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Host</label>
                  <input
                    type="text"
                    value={logConfig.host}
                    onChange={(e) => setLogConfig({ ...logConfig, host: e.target.value })}
                    placeholder="localhost"
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  />
                </div>

                {/* Port */}
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Port</label>
                  <input
                    type="number"
                    value={logConfig.port}
                    onChange={(e) => setLogConfig({ ...logConfig, port: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  />
                </div>

                {/* Protocol */}
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Protocol</label>
                  <select
                    value={logConfig.protocol}
                    onChange={(e) => setLogConfig({ ...logConfig, protocol: e.target.value })}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  >
                    {(getSelectedDestination()?.protocols || ['udp', 'tcp']).map((proto) => (
                      <option key={proto} value={proto}>
                        {proto.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Elasticsearch-specific: Index */}
              {logConfig.forward_type === 'elastic' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Index Name</label>
                    <input
                      type="text"
                      value={logConfig.index || ''}
                      onChange={(e) => setLogConfig({ ...logConfig, index: e.target.value })}
                      placeholder="wtc-logs"
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">API Key (optional)</label>
                    <input
                      type="password"
                      value={logConfig.api_key || ''}
                      onChange={(e) => setLogConfig({ ...logConfig, api_key: e.target.value })}
                      placeholder="Enter API key"
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                    />
                  </div>
                </div>
              )}

              {/* TLS Settings */}
              <div className="flex items-center space-x-6">
                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="tlsEnabled"
                    checked={logConfig.tls_enabled}
                    onChange={(e) => setLogConfig({ ...logConfig, tls_enabled: e.target.checked })}
                  />
                  <label htmlFor="tlsEnabled" className="text-sm text-gray-300">
                    Enable TLS
                  </label>
                </div>
                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="tlsVerify"
                    checked={logConfig.tls_verify}
                    onChange={(e) => setLogConfig({ ...logConfig, tls_verify: e.target.checked })}
                    disabled={!logConfig.tls_enabled}
                  />
                  <label htmlFor="tlsVerify" className={`text-sm ${logConfig.tls_enabled ? 'text-gray-300' : 'text-gray-500'}`}>
                    Verify Certificate
                  </label>
                </div>
              </div>
            </div>
          </div>

          {/* Log Content Settings */}
          <div className="scada-panel p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Log Content</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Minimum Log Level</label>
                <select
                  value={logConfig.log_level}
                  onChange={(e) => setLogConfig({ ...logConfig, log_level: e.target.value })}
                  className="w-full md:w-48 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                >
                  <option value="DEBUG">DEBUG</option>
                  <option value="INFO">INFO</option>
                  <option value="WARNING">WARNING</option>
                  <option value="ERROR">ERROR</option>
                  <option value="CRITICAL">CRITICAL</option>
                </select>
              </div>

              <div className="flex flex-wrap gap-6">
                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="includeAlarms"
                    checked={logConfig.include_alarms}
                    onChange={(e) => setLogConfig({ ...logConfig, include_alarms: e.target.checked })}
                  />
                  <label htmlFor="includeAlarms" className="text-sm text-gray-300">
                    Include Alarm Events
                  </label>
                </div>
                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="includeEvents"
                    checked={logConfig.include_events}
                    onChange={(e) => setLogConfig({ ...logConfig, include_events: e.target.checked })}
                  />
                  <label htmlFor="includeEvents" className="text-sm text-gray-300">
                    Include System Events
                  </label>
                </div>
                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="includeAudit"
                    checked={logConfig.include_audit}
                    onChange={(e) => setLogConfig({ ...logConfig, include_audit: e.target.checked })}
                  />
                  <label htmlFor="includeAudit" className="text-sm text-gray-300">
                    Include Audit Logs
                  </label>
                </div>
              </div>
            </div>

            <div className="mt-6">
              <button
                onClick={saveLogConfig}
                disabled={loading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Saving...' : 'Save Configuration'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Services Tab */}
      {activeTab === 'services' && (
        <div className="scada-panel p-6">
          <h2 className="text-lg font-semibold text-white mb-4">System Services</h2>

          <div className="space-y-4">
            {Object.entries(services).map(([service, status]) => (
              <div
                key={service}
                className="flex items-center justify-between p-4 bg-gray-800 rounded"
              >
                <div>
                  <div className="font-medium text-white">{service}</div>
                  <div className={`text-sm ${getServiceStatusClass(status)}`}>
                    {status}
                  </div>
                </div>
                <div className="flex space-x-2">
                  <button
                    onClick={() => controlService(service, 'start')}
                    disabled={loading || status === 'active'}
                    className="px-3 py-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 rounded text-sm text-white"
                  >
                    Start
                  </button>
                  <button
                    onClick={() => controlService(service, 'stop')}
                    disabled={loading || status !== 'active'}
                    className="px-3 py-1 bg-red-600 hover:bg-red-700 disabled:opacity-50 rounded text-sm text-white"
                  >
                    Stop
                  </button>
                  <button
                    onClick={() => controlService(service, 'restart')}
                    disabled={loading}
                    className="px-3 py-1 bg-yellow-600 hover:bg-yellow-700 disabled:opacity-50 rounded text-sm text-white"
                  >
                    Restart
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6">
            <button
              onClick={fetchServices}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white"
            >
              Refresh Status
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
