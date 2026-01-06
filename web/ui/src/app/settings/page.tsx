'use client';

import { useEffect, useState } from 'react';
import { configLogger, systemLogger, modbusLogger } from '@/lib/logger';
import { ConfirmModal } from '@/components/hmi';

const PAGE_TITLE = 'Settings - Water Treatment Controller';

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
  const [activeTab, setActiveTab] = useState<'general' | 'backup' | 'modbus' | 'services' | 'logging' | 'simulation'>('general');
  const [services, setServices] = useState<ServiceStatus>({});
  const [modbusConfig, setModbusConfig] = useState<ModbusServerConfig | null>(null);
  const [downstreamDevices, setDownstreamDevices] = useState<ModbusDownstreamDevice[]>([]);
  const [logConfig, setLogConfig] = useState<LogForwardingConfig | null>(null);
  const [logDestinations, setLogDestinations] = useState<LogDestination[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [fileToRestore, setFileToRestore] = useState<File | null>(null);

  // Demo mode state
  const [demoStatus, setDemoStatus] = useState<{
    enabled: boolean;
    scenario: string | null;
    uptime_seconds: number;
    rtu_count: number;
    alarm_count: number;
    pid_loop_count: number;
  } | null>(null);
  const [demoScenarios, setDemoScenarios] = useState<Record<string, {
    name: string;
    description: string;
    rtus: number;
    features: string[];
  }>>({});
  const [selectedScenario, setSelectedScenario] = useState('water_treatment_plant');

  // Set page title
  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);

  useEffect(() => {
    fetchServices();
    fetchModbusConfig();
    fetchLogConfig();
    fetchDemoStatus();
    fetchDemoScenarios();
  }, []);

  // ============== Demo Mode Functions ==============

  const fetchDemoStatus = async () => {
    try {
      const res = await fetch('/api/v1/demo/status');
      if (res.ok) {
        const data = await res.json();
        setDemoStatus(data.data);
      }
    } catch (error) {
      systemLogger.error('Failed to fetch demo status', error);
    }
  };

  const fetchDemoScenarios = async () => {
    try {
      const res = await fetch('/api/v1/demo/scenarios');
      if (res.ok) {
        const data = await res.json();
        setDemoScenarios(data.data?.scenarios || {});
        if (data.data?.default) {
          setSelectedScenario(data.data.default);
        }
      }
    } catch (error) {
      systemLogger.error('Failed to fetch demo scenarios', error);
    }
  };

  const enableDemoMode = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/demo/enable', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: selectedScenario }),
      });

      if (res.ok) {
        showMessage('success', `Simulation mode enabled with "${selectedScenario}" scenario`);
        await fetchDemoStatus();
      } else {
        showMessage('error', 'Failed to enable simulation mode');
      }
    } catch (error) {
      showMessage('error', 'Error enabling simulation mode');
    } finally {
      setLoading(false);
    }
  };

  const disableDemoMode = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/demo/disable', {
        method: 'POST',
      });

      if (res.ok) {
        showMessage('success', 'Simulation mode disabled');
        await fetchDemoStatus();
      } else {
        showMessage('error', 'Failed to disable simulation mode');
      }
    } catch (error) {
      showMessage('error', 'Error disabling simulation mode');
    } finally {
      setLoading(false);
    }
  };

  const formatUptime = (seconds: number): string => {
    if (seconds < 60) return `${Math.floor(seconds)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  // ============== Backup Functions ==============
  // Note: The server creates and returns backups immediately (no server-side storage).
  // Backups should be saved locally by the user.

  const createBackup = async () => {
    setLoading(true);
    try {
      // POST to /api/v1/system/ creates and immediately returns backup as ZIP
      const res = await fetch('/api/v1/system/', {
        method: 'POST',
      });

      if (res.ok) {
        // Download the backup file
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `wtc_backup_${new Date().toISOString().replace(/[:.]/g, '-')}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showMessage('success', 'Backup downloaded successfully');
      } else {
        showMessage('error', 'Failed to create backup');
      }
    } catch (error) {
      showMessage('error', 'Error creating backup');
    } finally {
      setLoading(false);
    }
  };

  const confirmRestoreBackup = async () => {
    if (!fileToRestore) return;

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', fileToRestore);

      const res = await fetch('/api/v1/backup/restore', {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        const result = await res.json();
        if (result.success) {
          showMessage('success', 'Configuration restored successfully');
        } else {
          showMessage('error', result.error || 'Failed to restore backup');
        }
      } else {
        showMessage('error', 'Failed to restore backup');
      }
    } catch (error) {
      showMessage('error', 'Error restoring backup');
    } finally {
      setLoading(false);
      setFileToRestore(null);
    }
  };

  const handleRestoreFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setFileToRestore(file);
    }
    // Reset input so same file can be selected again
    event.target.value = '';
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
        return 'text-status-ok';
      case 'inactive':
        return 'text-hmi-muted';
      case 'failed':
        return 'text-status-alarm';
      default:
        return 'text-status-warning';
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-hmi-text">Settings</h1>

      {/* Message Banner */}
      {message && (
        <div
          className={`p-4 rounded-lg ${
            message.type === 'success' ? 'bg-status-ok text-white' : 'bg-status-alarm text-white'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Tabs */}
      <div className="flex space-x-4 border-b border-hmi-border overflow-x-auto">
        {[
          { id: 'general', label: 'General' },
          { id: 'backup', label: 'Backup & Restore' },
          { id: 'modbus', label: 'Modbus Gateway' },
          { id: 'logging', label: 'Log Forwarding' },
          { id: 'services', label: 'Services' },
          { id: 'simulation', label: 'Simulation Mode' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-4 py-2 -mb-px ${
              activeTab === tab.id
                ? 'border-b-2 border-status-info text-status-info'
                : 'text-hmi-muted hover:text-hmi-text'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* General Tab */}
      {activeTab === 'general' && (
        <div className="hmi-card p-6 space-y-6">
          <h2 className="text-lg font-semibold text-hmi-text">Configuration Import/Export</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-hmi-text">Export Configuration</h3>
              <p className="text-sm text-hmi-muted">
                Download the current system configuration as a JSON file.
              </p>
              <button
                onClick={exportConfig}
                className="px-4 py-2 bg-status-info hover:bg-status-info/80 rounded text-white"
              >
                Export Configuration
              </button>
            </div>

            <div className="space-y-4">
              <h3 className="text-sm font-medium text-hmi-text">Import Configuration</h3>
              <p className="text-sm text-hmi-muted">
                Upload a configuration file to restore settings.
              </p>
              <label className="px-4 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded text-hmi-text cursor-pointer inline-block">
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
          <div className="hmi-card p-6">
            <h2 className="text-lg font-semibold text-hmi-text mb-4">Create Backup</h2>
            <p className="text-sm text-hmi-muted mb-4">
              Create a backup of the current configuration. The backup will be downloaded
              as a ZIP file containing database and configuration files.
            </p>
            <button
              onClick={createBackup}
              disabled={loading}
              className="px-4 py-2 bg-status-ok hover:bg-status-ok/80 rounded text-white disabled:opacity-50"
            >
              {loading ? 'Creating...' : 'Download Backup'}
            </button>
          </div>

          {/* Restore from File */}
          <div className="hmi-card p-6">
            <h2 className="text-lg font-semibold text-hmi-text mb-4">Restore from Backup</h2>
            <p className="text-sm text-hmi-muted mb-4">
              Select a backup file (.zip) to restore the configuration.
              This will overwrite the current configuration.
            </p>
            <label className="inline-block px-4 py-2 bg-status-info hover:bg-status-info/80 rounded text-white cursor-pointer">
              <input
                type="file"
                accept=".zip"
                onChange={handleRestoreFileSelect}
                className="hidden"
                disabled={loading}
              />
              {loading ? 'Restoring...' : 'Select Backup File to Restore'}
            </label>
          </div>
        </div>
      )}

      {/* Modbus Tab */}
      {activeTab === 'modbus' && modbusConfig && (
        <div className="space-y-6">
          {/* Server Configuration */}
          <div className="hmi-card p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-hmi-text">Modbus Server Configuration</h2>
              <button
                onClick={restartModbus}
                className="px-3 py-1 bg-status-warning hover:bg-status-warning/80 rounded text-sm text-white"
              >
                Restart Gateway
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* TCP Settings */}
              <div className="space-y-4">
                <h3 className="font-medium text-hmi-text">TCP Server</h3>

                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="tcpEnabled"
                    checked={modbusConfig.tcp_enabled}
                    onChange={(e) =>
                      setModbusConfig({ ...modbusConfig, tcp_enabled: e.target.checked })
                    }
                  />
                  <label htmlFor="tcpEnabled" className="text-sm text-hmi-text">
                    Enable TCP Server
                  </label>
                </div>

                <div>
                  <label className="block text-sm text-hmi-muted mb-1">Port</label>
                  <input
                    type="number"
                    value={modbusConfig.tcp_port}
                    onChange={(e) =>
                      setModbusConfig({ ...modbusConfig, tcp_port: parseInt(e.target.value) })
                    }
                    className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                  />
                </div>

                <div>
                  <label className="block text-sm text-hmi-muted mb-1">Bind Address</label>
                  <input
                    type="text"
                    value={modbusConfig.tcp_bind_address}
                    onChange={(e) =>
                      setModbusConfig({ ...modbusConfig, tcp_bind_address: e.target.value })
                    }
                    className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                  />
                </div>
              </div>

              {/* RTU Settings */}
              <div className="space-y-4">
                <h3 className="font-medium text-hmi-text">RTU Server (Serial)</h3>

                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="rtuEnabled"
                    checked={modbusConfig.rtu_enabled}
                    onChange={(e) =>
                      setModbusConfig({ ...modbusConfig, rtu_enabled: e.target.checked })
                    }
                  />
                  <label htmlFor="rtuEnabled" className="text-sm text-hmi-text">
                    Enable RTU Server
                  </label>
                </div>

                <div>
                  <label className="block text-sm text-hmi-muted mb-1">Serial Device</label>
                  <input
                    type="text"
                    value={modbusConfig.rtu_device}
                    onChange={(e) =>
                      setModbusConfig({ ...modbusConfig, rtu_device: e.target.value })
                    }
                    className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-hmi-muted mb-1">Baud Rate</label>
                    <select
                      value={modbusConfig.rtu_baud_rate}
                      onChange={(e) =>
                        setModbusConfig({ ...modbusConfig, rtu_baud_rate: parseInt(e.target.value) })
                      }
                      className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                    >
                      {[9600, 19200, 38400, 57600, 115200].map((rate) => (
                        <option key={rate} value={rate}>
                          {rate}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm text-hmi-muted mb-1">Slave Address</label>
                    <input
                      type="number"
                      value={modbusConfig.rtu_slave_addr}
                      onChange={(e) =>
                        setModbusConfig({ ...modbusConfig, rtu_slave_addr: parseInt(e.target.value) })
                      }
                      min="1"
                      max="247"
                      className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm text-hmi-muted mb-1">Parity</label>
                    <select
                      value={modbusConfig.rtu_parity}
                      onChange={(e) =>
                        setModbusConfig({ ...modbusConfig, rtu_parity: e.target.value })
                      }
                      className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                    >
                      <option value="N">None</option>
                      <option value="E">Even</option>
                      <option value="O">Odd</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm text-hmi-muted mb-1">Data Bits</label>
                    <select
                      value={modbusConfig.rtu_data_bits}
                      onChange={(e) =>
                        setModbusConfig({ ...modbusConfig, rtu_data_bits: parseInt(e.target.value) })
                      }
                      className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                    >
                      <option value={7}>7</option>
                      <option value={8}>8</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm text-hmi-muted mb-1">Stop Bits</label>
                    <select
                      value={modbusConfig.rtu_stop_bits}
                      onChange={(e) =>
                        setModbusConfig({ ...modbusConfig, rtu_stop_bits: parseInt(e.target.value) })
                      }
                      className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
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
                className="px-4 py-2 bg-status-info hover:bg-status-info/80 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Saving...' : 'Save Configuration'}
              </button>
            </div>
          </div>

          {/* Downstream Devices */}
          <div className="hmi-card p-6">
            <h2 className="text-lg font-semibold text-hmi-text mb-4">Downstream Modbus Devices</h2>

            {downstreamDevices.length === 0 ? (
              <p className="text-hmi-muted">No downstream devices configured</p>
            ) : (
              <div className="space-y-3">
                {downstreamDevices.map((device) => (
                  <div
                    key={device.device_id}
                    className="flex items-center justify-between p-4 bg-hmi-panel rounded"
                  >
                    <div>
                      <div className="font-medium text-hmi-text">{device.name}</div>
                      <div className="text-sm text-hmi-muted">
                        {device.transport === 'TCP'
                          ? `${device.tcp_host}:${device.tcp_port}`
                          : `${device.rtu_device} @ ${device.rtu_baud_rate}`}
                        {' - '}
                        Slave {device.slave_addr}
                      </div>
                    </div>
                    <div className={device.enabled ? 'text-status-ok' : 'text-hmi-muted'}>
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
          <div className="hmi-card p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-hmi-text">Log Forwarding Configuration</h2>
              <div className="flex space-x-2">
                <button
                  onClick={testLogForwarding}
                  disabled={loading || !logConfig.enabled}
                  className="px-3 py-1 bg-status-warning hover:bg-status-warning/80 disabled:opacity-50 rounded text-sm text-white"
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
                <label htmlFor="logEnabled" className="text-sm text-hmi-text">
                  Enable Log Forwarding
                </label>
              </div>

              {/* Destination Type */}
              <div>
                <label className="block text-sm text-hmi-muted mb-1">Destination Type</label>
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
                  className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                >
                  {logDestinations.map((dest) => (
                    <option key={dest.type} value={dest.type}>
                      {dest.name}
                    </option>
                  ))}
                </select>
                {getSelectedDestination() && (
                  <p className="text-xs text-hmi-muted mt-1">{getSelectedDestination()?.description}</p>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Host */}
                <div>
                  <label className="block text-sm text-hmi-muted mb-1">Host</label>
                  <input
                    type="text"
                    value={logConfig.host}
                    onChange={(e) => setLogConfig({ ...logConfig, host: e.target.value })}
                    placeholder="localhost"
                    className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                  />
                </div>

                {/* Port */}
                <div>
                  <label className="block text-sm text-hmi-muted mb-1">Port</label>
                  <input
                    type="number"
                    value={logConfig.port}
                    onChange={(e) => setLogConfig({ ...logConfig, port: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                  />
                </div>

                {/* Protocol */}
                <div>
                  <label className="block text-sm text-hmi-muted mb-1">Protocol</label>
                  <select
                    value={logConfig.protocol}
                    onChange={(e) => setLogConfig({ ...logConfig, protocol: e.target.value })}
                    className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
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
                    <label className="block text-sm text-hmi-muted mb-1">Index Name</label>
                    <input
                      type="text"
                      value={logConfig.index || ''}
                      onChange={(e) => setLogConfig({ ...logConfig, index: e.target.value })}
                      placeholder="wtc-logs"
                      className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-hmi-muted mb-1">API Key (optional)</label>
                    <input
                      type="password"
                      value={logConfig.api_key || ''}
                      onChange={(e) => setLogConfig({ ...logConfig, api_key: e.target.value })}
                      placeholder="Enter API key"
                      className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
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
                  <label htmlFor="tlsEnabled" className="text-sm text-hmi-text">
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
                  <label htmlFor="tlsVerify" className={`text-sm ${logConfig.tls_enabled ? 'text-hmi-text' : 'text-hmi-muted'}`}>
                    Verify Certificate
                  </label>
                </div>
              </div>
            </div>
          </div>

          {/* Log Content Settings */}
          <div className="hmi-card p-6">
            <h2 className="text-lg font-semibold text-hmi-text mb-4">Log Content</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-hmi-muted mb-1">Minimum Log Level</label>
                <select
                  value={logConfig.log_level}
                  onChange={(e) => setLogConfig({ ...logConfig, log_level: e.target.value })}
                  className="w-full md:w-48 px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
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
                  <label htmlFor="includeAlarms" className="text-sm text-hmi-text">
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
                  <label htmlFor="includeEvents" className="text-sm text-hmi-text">
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
                  <label htmlFor="includeAudit" className="text-sm text-hmi-text">
                    Include Audit Logs
                  </label>
                </div>
              </div>
            </div>

            <div className="mt-6">
              <button
                onClick={saveLogConfig}
                disabled={loading}
                className="px-4 py-2 bg-status-info hover:bg-status-info/80 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Saving...' : 'Save Configuration'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Services Tab */}
      {activeTab === 'services' && (
        <div className="hmi-card p-6">
          <h2 className="text-lg font-semibold text-hmi-text mb-4">System Services</h2>

          <div className="space-y-4">
            {Object.entries(services).map(([service, status]) => (
              <div
                key={service}
                className="flex items-center justify-between p-4 bg-hmi-panel rounded"
              >
                <div>
                  <div className="font-medium text-hmi-text">{service}</div>
                  <div className={`text-sm ${getServiceStatusClass(status)}`}>
                    {status}
                  </div>
                </div>
                <div className="flex space-x-2">
                  <button
                    onClick={() => controlService(service, 'start')}
                    disabled={loading || status === 'active'}
                    className="px-3 py-1 bg-status-ok hover:bg-status-ok/80 disabled:opacity-50 rounded text-sm text-white"
                  >
                    Start
                  </button>
                  <button
                    onClick={() => controlService(service, 'stop')}
                    disabled={loading || status !== 'active'}
                    className="px-3 py-1 bg-status-alarm hover:bg-status-alarm/80 disabled:opacity-50 rounded text-sm text-white"
                  >
                    Stop
                  </button>
                  <button
                    onClick={() => controlService(service, 'restart')}
                    disabled={loading}
                    className="px-3 py-1 bg-status-warning hover:bg-status-warning/80 disabled:opacity-50 rounded text-sm text-white"
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
              className="px-4 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded text-hmi-text"
            >
              Refresh Status
            </button>
          </div>
        </div>
      )}

      {/* Simulation Mode Tab */}
      {activeTab === 'simulation' && (
        <div className="space-y-6">
          {/* Simulation Status */}
          <div className="hmi-card p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-hmi-text">Simulation Mode</h2>
              <div className={`px-3 py-1 rounded text-sm font-medium ${
                demoStatus?.enabled
                  ? 'bg-status-info/20 text-status-info'
                  : 'bg-hmi-panel text-hmi-muted'
              }`}>
                {demoStatus?.enabled ? 'Demo Active' : 'Inactive'}
              </div>
            </div>

            <p className="text-sm text-hmi-muted mb-6">
              Simulation mode provides realistic virtual RTU data for testing, operator training, and
              development without requiring real PROFINET hardware. When enabled, the system generates
              water treatment plant sensor values, responds to actuator commands, and creates alarm conditions.
            </p>

            {demoStatus?.enabled ? (
              /* Active Simulation Mode */
              <div className="space-y-6">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-hmi-panel p-4 rounded">
                    <div className="text-sm text-hmi-muted">Scenario</div>
                    <div className="text-lg font-medium text-hmi-text capitalize">
                      {demoStatus.scenario?.replace(/_/g, ' ') || 'Unknown'}
                    </div>
                  </div>
                  <div className="bg-hmi-panel p-4 rounded">
                    <div className="text-sm text-hmi-muted">Uptime</div>
                    <div className="text-lg font-medium text-hmi-text">
                      {formatUptime(demoStatus.uptime_seconds)}
                    </div>
                  </div>
                  <div className="bg-hmi-panel p-4 rounded">
                    <div className="text-sm text-hmi-muted">Simulated RTUs</div>
                    <div className="text-lg font-medium text-hmi-text">
                      {demoStatus.rtu_count}
                    </div>
                  </div>
                  <div className="bg-hmi-panel p-4 rounded">
                    <div className="text-sm text-hmi-muted">Active Alarms</div>
                    <div className="text-lg font-medium text-hmi-text">
                      {demoStatus.alarm_count}
                    </div>
                  </div>
                </div>

                <div className="flex space-x-4">
                  <button
                    onClick={disableDemoMode}
                    disabled={loading}
                    className="px-4 py-2 bg-status-alarm hover:bg-status-alarm/80 rounded text-white disabled:opacity-50"
                  >
                    {loading ? 'Stopping...' : 'Stop Simulation'}
                  </button>
                  <button
                    onClick={fetchDemoStatus}
                    className="px-4 py-2 bg-hmi-panel hover:bg-hmi-panel/80 rounded text-hmi-text"
                  >
                    Refresh
                  </button>
                </div>
              </div>
            ) : (
              /* Inactive - Show Scenario Selection */
              <div className="space-y-6">
                <div>
                  <label className="block text-sm text-hmi-muted mb-2">Select Scenario</label>
                  <select
                    value={selectedScenario}
                    onChange={(e) => setSelectedScenario(e.target.value)}
                    className="w-full md:w-96 px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
                  >
                    {Object.entries(demoScenarios).map(([key, scenario]) => (
                      <option key={key} value={key}>
                        {scenario.name} ({scenario.rtus} RTU{scenario.rtus !== 1 ? 's' : ''})
                      </option>
                    ))}
                  </select>
                </div>

                {demoScenarios[selectedScenario] && (
                  <div className="bg-hmi-panel p-4 rounded">
                    <h3 className="font-medium text-hmi-text mb-2">
                      {demoScenarios[selectedScenario].name}
                    </h3>
                    <p className="text-sm text-hmi-muted mb-3">
                      {demoScenarios[selectedScenario].description}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {demoScenarios[selectedScenario].features.map((feature, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-1 bg-hmi-background text-xs text-hmi-muted rounded"
                        >
                          {feature}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <button
                  onClick={enableDemoMode}
                  disabled={loading}
                  className="px-4 py-2 bg-status-info hover:bg-status-info/80 rounded text-white disabled:opacity-50"
                >
                  {loading ? 'Starting...' : 'Start Simulation'}
                </button>
              </div>
            )}
          </div>

          {/* Environment Variable Info */}
          <div className="hmi-card p-6">
            <h2 className="text-lg font-semibold text-hmi-text mb-4">Auto-Enable on Startup</h2>
            <p className="text-sm text-hmi-muted mb-4">
              Simulation mode can be automatically enabled when the controller or API server starts
              by setting environment variables:
            </p>
            <div className="bg-hmi-panel p-4 rounded font-mono text-sm text-hmi-text space-y-1">
              <div className="text-hmi-muted"># For C controller:</div>
              <div>WTC_SIMULATION_MODE=1</div>
              <div>WTC_SIMULATION_SCENARIO=water_treatment_plant</div>
              <div className="text-hmi-muted mt-2"># Or use command line:</div>
              <div>./water_treat_controller --simulation --scenario water_treatment_plant</div>
            </div>
          </div>
        </div>
      )}

      {/* Restore Backup Confirmation Modal */}
      <ConfirmModal
        isOpen={fileToRestore !== null}
        onClose={() => setFileToRestore(null)}
        onConfirm={confirmRestoreBackup}
        title="Restore Backup"
        message={`Are you sure you want to restore "${fileToRestore?.name}"? Current configuration will be overwritten. This action cannot be undone.`}
        confirmLabel="Restore"
        cancelLabel="Cancel"
        variant="warning"
        isLoading={loading}
      />
    </div>
  );
}
