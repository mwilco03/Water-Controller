'use client';

import { useEffect, useState } from 'react';

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
  description?: string;
}

interface ModbusRegisterMapping {
  mapping_id?: number;
  modbus_addr: number;
  register_type: string;
  data_type: string;
  source_type: string;
  rtu_station: string;
  slot: number;
  description: string;
  scaling_enabled: boolean;
  scale_raw_min: number;
  scale_raw_max: number;
  scale_eng_min: number;
  scale_eng_max: number;
}

interface ModbusStats {
  server_running: boolean;
  tcp_connections: number;
  total_requests: number;
  total_errors: number;
  downstream_devices_online: number;
}

interface RTUDevice {
  station_name: string;
  slot_count: number;
}

export default function ModbusPage() {
  const [activeTab, setActiveTab] = useState<'server' | 'mappings' | 'downstream' | 'stats'>('server');
  const [serverConfig, setServerConfig] = useState<ModbusServerConfig | null>(null);
  const [downstreamDevices, setDownstreamDevices] = useState<ModbusDownstreamDevice[]>([]);
  const [registerMappings, setRegisterMappings] = useState<ModbusRegisterMapping[]>([]);
  const [stats, setStats] = useState<ModbusStats | null>(null);
  const [rtus, setRtus] = useState<RTUDevice[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Modal states
  const [showDeviceModal, setShowDeviceModal] = useState(false);
  const [showMappingModal, setShowMappingModal] = useState(false);
  const [editingDevice, setEditingDevice] = useState<ModbusDownstreamDevice | null>(null);
  const [editingMapping, setEditingMapping] = useState<ModbusRegisterMapping | null>(null);

  // New device form
  const [newDevice, setNewDevice] = useState<ModbusDownstreamDevice>({
    name: '',
    transport: 'TCP',
    tcp_host: '',
    tcp_port: 502,
    rtu_device: '/dev/ttyUSB0',
    rtu_baud_rate: 9600,
    slave_addr: 1,
    poll_interval_ms: 1000,
    timeout_ms: 1000,
    enabled: true,
    description: '',
  });

  // New mapping form
  const [newMapping, setNewMapping] = useState<ModbusRegisterMapping>({
    modbus_addr: 0,
    register_type: 'HOLDING',
    data_type: 'FLOAT32',
    source_type: 'PROFINET_SENSOR',
    rtu_station: '',
    slot: 1,
    description: '',
    scaling_enabled: false,
    scale_raw_min: 0,
    scale_raw_max: 65535,
    scale_eng_min: 0,
    scale_eng_max: 100,
  });

  useEffect(() => {
    fetchServerConfig();
    fetchDownstreamDevices();
    fetchRegisterMappings();
    fetchStats();
    fetchRtus();

    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, []);

  const showMsg = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const fetchServerConfig = async () => {
    try {
      const res = await fetch('/api/v1/modbus/server');
      if (res.ok) {
        setServerConfig(await res.json());
      }
    } catch (error) {
      console.error('Failed to fetch server config:', error);
    }
  };

  const fetchDownstreamDevices = async () => {
    try {
      const res = await fetch('/api/v1/modbus/downstream');
      if (res.ok) {
        setDownstreamDevices(await res.json());
      }
    } catch (error) {
      console.error('Failed to fetch downstream devices:', error);
    }
  };

  const fetchRegisterMappings = async () => {
    try {
      const res = await fetch('/api/v1/modbus/mappings');
      if (res.ok) {
        setRegisterMappings(await res.json());
      }
    } catch (error) {
      console.error('Failed to fetch register mappings:', error);
    }
  };

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/v1/modbus/stats');
      if (res.ok) {
        setStats(await res.json());
      }
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    }
  };

  const fetchRtus = async () => {
    try {
      const res = await fetch('/api/v1/rtus');
      if (res.ok) {
        setRtus(await res.json());
      }
    } catch (error) {
      console.error('Failed to fetch RTUs:', error);
    }
  };

  const saveServerConfig = async () => {
    if (!serverConfig) return;
    setLoading(true);
    try {
      const res = await fetch('/api/v1/modbus/server', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(serverConfig),
      });
      if (res.ok) {
        showMsg('success', 'Server configuration saved');
      } else {
        showMsg('error', 'Failed to save configuration');
      }
    } catch (error) {
      showMsg('error', 'Error saving configuration');
    } finally {
      setLoading(false);
    }
  };

  const restartGateway = async () => {
    try {
      const res = await fetch('/api/v1/modbus/restart', { method: 'POST' });
      if (res.ok) {
        showMsg('success', 'Gateway restart initiated');
      }
    } catch (error) {
      showMsg('error', 'Failed to restart gateway');
    }
  };

  // Downstream device CRUD
  const saveDevice = async () => {
    setLoading(true);
    try {
      const device = editingDevice || newDevice;
      const isEdit = editingDevice?.device_id != null;
      const url = isEdit
        ? `/api/v1/modbus/downstream/${editingDevice.device_id}`
        : '/api/v1/modbus/downstream';

      const res = await fetch(url, {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(device),
      });

      if (res.ok) {
        showMsg('success', isEdit ? 'Device updated' : 'Device added');
        setShowDeviceModal(false);
        setEditingDevice(null);
        setNewDevice({
          name: '',
          transport: 'TCP',
          tcp_host: '',
          tcp_port: 502,
          rtu_device: '/dev/ttyUSB0',
          rtu_baud_rate: 9600,
          slave_addr: 1,
          poll_interval_ms: 1000,
          timeout_ms: 1000,
          enabled: true,
          description: '',
        });
        fetchDownstreamDevices();
      } else {
        showMsg('error', 'Failed to save device');
      }
    } catch (error) {
      showMsg('error', 'Error saving device');
    } finally {
      setLoading(false);
    }
  };

  const deleteDevice = async (deviceId: number) => {
    if (!confirm('Are you sure you want to delete this device?')) return;

    try {
      const res = await fetch(`/api/v1/modbus/downstream/${deviceId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        showMsg('success', 'Device deleted');
        fetchDownstreamDevices();
      } else {
        showMsg('error', 'Failed to delete device');
      }
    } catch (error) {
      showMsg('error', 'Error deleting device');
    }
  };

  // Register mapping CRUD
  const saveMapping = async () => {
    setLoading(true);
    try {
      const mapping = editingMapping || newMapping;
      const isEdit = editingMapping?.mapping_id != null;
      const url = isEdit
        ? `/api/v1/modbus/mappings/${editingMapping.mapping_id}`
        : '/api/v1/modbus/mappings';

      const res = await fetch(url, {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mapping),
      });

      if (res.ok) {
        showMsg('success', isEdit ? 'Mapping updated' : 'Mapping created');
        setShowMappingModal(false);
        setEditingMapping(null);
        setNewMapping({
          modbus_addr: registerMappings.length > 0
            ? Math.max(...registerMappings.map(m => m.modbus_addr)) + 2
            : 0,
          register_type: 'HOLDING',
          data_type: 'FLOAT32',
          source_type: 'PROFINET_SENSOR',
          rtu_station: rtus[0]?.station_name || '',
          slot: 1,
          description: '',
          scaling_enabled: false,
          scale_raw_min: 0,
          scale_raw_max: 65535,
          scale_eng_min: 0,
          scale_eng_max: 100,
        });
        fetchRegisterMappings();
      } else {
        showMsg('error', 'Failed to save mapping');
      }
    } catch (error) {
      showMsg('error', 'Error saving mapping');
    } finally {
      setLoading(false);
    }
  };

  const deleteMapping = async (mappingId: number) => {
    if (!confirm('Are you sure you want to delete this mapping?')) return;

    try {
      const res = await fetch(`/api/v1/modbus/mappings/${mappingId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        showMsg('success', 'Mapping deleted');
        fetchRegisterMappings();
      } else {
        showMsg('error', 'Failed to delete mapping');
      }
    } catch (error) {
      showMsg('error', 'Error deleting mapping');
    }
  };

  const openEditDevice = (device: ModbusDownstreamDevice) => {
    setEditingDevice({ ...device });
    setShowDeviceModal(true);
  };

  const openEditMapping = (mapping: ModbusRegisterMapping) => {
    setEditingMapping({ ...mapping });
    setShowMappingModal(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-white">Modbus Gateway</h1>
        <button
          onClick={restartGateway}
          className="px-4 py-2 bg-yellow-600 hover:bg-yellow-700 rounded text-white"
        >
          Restart Gateway
        </button>
      </div>

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

      {/* Status Overview */}
      {stats && (
        <div className="grid grid-cols-5 gap-4">
          <div className="scada-panel p-4 text-center">
            <div className={`text-3xl font-bold ${stats.server_running ? 'text-green-400' : 'text-red-400'}`}>
              {stats.server_running ? 'ON' : 'OFF'}
            </div>
            <div className="text-sm text-gray-400">Server Status</div>
          </div>
          <div className="scada-panel p-4 text-center">
            <div className="text-3xl font-bold text-blue-400">{stats.tcp_connections}</div>
            <div className="text-sm text-gray-400">TCP Connections</div>
          </div>
          <div className="scada-panel p-4 text-center">
            <div className="text-3xl font-bold text-white">{stats.total_requests}</div>
            <div className="text-sm text-gray-400">Total Requests</div>
          </div>
          <div className="scada-panel p-4 text-center">
            <div className="text-3xl font-bold text-red-400">{stats.total_errors}</div>
            <div className="text-sm text-gray-400">Errors</div>
          </div>
          <div className="scada-panel p-4 text-center">
            <div className="text-3xl font-bold text-green-400">{stats.downstream_devices_online}</div>
            <div className="text-sm text-gray-400">Devices Online</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex space-x-4 border-b border-gray-700">
        {[
          { id: 'server', label: 'Server Config' },
          { id: 'mappings', label: 'Register Mappings' },
          { id: 'downstream', label: 'Downstream Devices' },
          { id: 'stats', label: 'Statistics' },
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

      {/* Server Config Tab */}
      {activeTab === 'server' && serverConfig && (
        <div className="scada-panel p-6">
          <h2 className="text-lg font-semibold text-white mb-6">Modbus Server Configuration</h2>

          <div className="grid grid-cols-2 gap-8">
            {/* TCP Settings */}
            <div className="space-y-4">
              <h3 className="font-medium text-gray-300 border-b border-gray-700 pb-2">TCP Server</h3>

              <label className="flex items-center space-x-3">
                <input
                  type="checkbox"
                  checked={serverConfig.tcp_enabled}
                  onChange={(e) => setServerConfig({ ...serverConfig, tcp_enabled: e.target.checked })}
                  className="w-4 h-4"
                />
                <span className="text-gray-300">Enable TCP Server</span>
              </label>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Port</label>
                <input
                  type="number"
                  value={serverConfig.tcp_port}
                  onChange={(e) => setServerConfig({ ...serverConfig, tcp_port: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Bind Address</label>
                <input
                  type="text"
                  value={serverConfig.tcp_bind_address}
                  onChange={(e) => setServerConfig({ ...serverConfig, tcp_bind_address: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>
            </div>

            {/* RTU Settings */}
            <div className="space-y-4">
              <h3 className="font-medium text-gray-300 border-b border-gray-700 pb-2">RTU Server (Serial)</h3>

              <label className="flex items-center space-x-3">
                <input
                  type="checkbox"
                  checked={serverConfig.rtu_enabled}
                  onChange={(e) => setServerConfig({ ...serverConfig, rtu_enabled: e.target.checked })}
                  className="w-4 h-4"
                />
                <span className="text-gray-300">Enable RTU Server</span>
              </label>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Serial Device</label>
                <input
                  type="text"
                  value={serverConfig.rtu_device}
                  onChange={(e) => setServerConfig({ ...serverConfig, rtu_device: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Baud Rate</label>
                  <select
                    value={serverConfig.rtu_baud_rate}
                    onChange={(e) => setServerConfig({ ...serverConfig, rtu_baud_rate: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  >
                    {[9600, 19200, 38400, 57600, 115200].map((rate) => (
                      <option key={rate} value={rate}>{rate}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Slave Address</label>
                  <input
                    type="number"
                    value={serverConfig.rtu_slave_addr}
                    onChange={(e) => setServerConfig({ ...serverConfig, rtu_slave_addr: parseInt(e.target.value) })}
                    min="1"
                    max="247"
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="mt-6">
            <button
              onClick={saveServerConfig}
              disabled={loading}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white disabled:opacity-50"
            >
              {loading ? 'Saving...' : 'Save Configuration'}
            </button>
          </div>
        </div>
      )}

      {/* Register Mappings Tab */}
      {activeTab === 'mappings' && (
        <div className="scada-panel p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-lg font-semibold text-white">Register Mappings</h2>
            <button
              onClick={() => {
                setEditingMapping(null);
                setShowMappingModal(true);
              }}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-white"
            >
              + Add Mapping
            </button>
          </div>

          {registerMappings.length === 0 ? (
            <p className="text-gray-400">No register mappings configured</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-2 px-3 text-gray-400">Address</th>
                    <th className="text-left py-2 px-3 text-gray-400">Type</th>
                    <th className="text-left py-2 px-3 text-gray-400">Data Type</th>
                    <th className="text-left py-2 px-3 text-gray-400">Source</th>
                    <th className="text-left py-2 px-3 text-gray-400">Description</th>
                    <th className="text-left py-2 px-3 text-gray-400">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {registerMappings.map((mapping) => (
                    <tr key={mapping.mapping_id} className="border-b border-gray-800">
                      <td className="py-2 px-3 font-mono">{mapping.modbus_addr}</td>
                      <td className="py-2 px-3">{mapping.register_type}</td>
                      <td className="py-2 px-3">{mapping.data_type}</td>
                      <td className="py-2 px-3">
                        {mapping.rtu_station}:{mapping.slot}
                      </td>
                      <td className="py-2 px-3 text-gray-400">{mapping.description}</td>
                      <td className="py-2 px-3">
                        <button
                          onClick={() => openEditMapping(mapping)}
                          className="text-blue-400 hover:text-blue-300 mr-3"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => deleteMapping(mapping.mapping_id!)}
                          className="text-red-400 hover:text-red-300"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Downstream Devices Tab */}
      {activeTab === 'downstream' && (
        <div className="scada-panel p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-lg font-semibold text-white">Downstream Modbus Devices</h2>
            <button
              onClick={() => {
                setEditingDevice(null);
                setShowDeviceModal(true);
              }}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-white"
            >
              + Add Device
            </button>
          </div>

          {downstreamDevices.length === 0 ? (
            <p className="text-gray-400">No downstream devices configured</p>
          ) : (
            <div className="space-y-4">
              {downstreamDevices.map((device) => (
                <div
                  key={device.device_id}
                  className="bg-gray-800 p-4 rounded-lg flex items-center justify-between"
                >
                  <div>
                    <div className="font-semibold text-white">{device.name}</div>
                    <div className="text-sm text-gray-400">
                      {device.transport === 'TCP'
                        ? `${device.tcp_host}:${device.tcp_port}`
                        : `${device.rtu_device} @ ${device.rtu_baud_rate}`}
                      {' - '}Slave {device.slave_addr}
                    </div>
                    {device.description && (
                      <div className="text-sm text-gray-500">{device.description}</div>
                    )}
                  </div>
                  <div className="flex items-center space-x-4">
                    <span className={device.enabled ? 'text-green-400' : 'text-gray-500'}>
                      {device.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                    <button
                      onClick={() => openEditDevice(device)}
                      className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => deleteDevice(device.device_id!)}
                      className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Statistics Tab */}
      {activeTab === 'stats' && stats && (
        <div className="scada-panel p-6">
          <h2 className="text-lg font-semibold text-white mb-6">Gateway Statistics</h2>

          <div className="grid grid-cols-2 gap-6">
            <div className="bg-gray-800 p-4 rounded-lg">
              <h3 className="font-medium text-gray-300 mb-4">Server Statistics</h3>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-400">Status</span>
                  <span className={stats.server_running ? 'text-green-400' : 'text-red-400'}>
                    {stats.server_running ? 'Running' : 'Stopped'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Active TCP Connections</span>
                  <span className="text-white">{stats.tcp_connections}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Total Requests</span>
                  <span className="text-white">{stats.total_requests}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Total Errors</span>
                  <span className="text-red-400">{stats.total_errors}</span>
                </div>
              </div>
            </div>

            <div className="bg-gray-800 p-4 rounded-lg">
              <h3 className="font-medium text-gray-300 mb-4">Downstream Devices</h3>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-400">Configured Devices</span>
                  <span className="text-white">{downstreamDevices.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Online</span>
                  <span className="text-green-400">{stats.downstream_devices_online}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Offline</span>
                  <span className="text-red-400">{downstreamDevices.length - stats.downstream_devices_online}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Device Modal */}
      {showDeviceModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-900 p-6 rounded-lg w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-semibold text-white mb-4">
              {editingDevice ? 'Edit Device' : 'Add Downstream Device'}
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-300 mb-1">Device Name</label>
                <input
                  type="text"
                  value={editingDevice?.name ?? newDevice.name}
                  onChange={(e) => editingDevice
                    ? setEditingDevice({ ...editingDevice, name: e.target.value })
                    : setNewDevice({ ...newDevice, name: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">Transport</label>
                <select
                  value={editingDevice?.transport ?? newDevice.transport}
                  onChange={(e) => editingDevice
                    ? setEditingDevice({ ...editingDevice, transport: e.target.value })
                    : setNewDevice({ ...newDevice, transport: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                >
                  <option value="TCP">TCP</option>
                  <option value="RTU">RTU (Serial)</option>
                </select>
              </div>

              {(editingDevice?.transport ?? newDevice.transport) === 'TCP' ? (
                <>
                  <div>
                    <label className="block text-sm text-gray-300 mb-1">Host</label>
                    <input
                      type="text"
                      value={editingDevice?.tcp_host ?? newDevice.tcp_host}
                      onChange={(e) => editingDevice
                        ? setEditingDevice({ ...editingDevice, tcp_host: e.target.value })
                        : setNewDevice({ ...newDevice, tcp_host: e.target.value })
                      }
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-300 mb-1">Port</label>
                    <input
                      type="number"
                      value={editingDevice?.tcp_port ?? newDevice.tcp_port}
                      onChange={(e) => editingDevice
                        ? setEditingDevice({ ...editingDevice, tcp_port: parseInt(e.target.value) })
                        : setNewDevice({ ...newDevice, tcp_port: parseInt(e.target.value) })
                      }
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                    />
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="block text-sm text-gray-300 mb-1">Serial Device</label>
                    <input
                      type="text"
                      value={editingDevice?.rtu_device ?? newDevice.rtu_device}
                      onChange={(e) => editingDevice
                        ? setEditingDevice({ ...editingDevice, rtu_device: e.target.value })
                        : setNewDevice({ ...newDevice, rtu_device: e.target.value })
                      }
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-300 mb-1">Baud Rate</label>
                    <select
                      value={editingDevice?.rtu_baud_rate ?? newDevice.rtu_baud_rate}
                      onChange={(e) => editingDevice
                        ? setEditingDevice({ ...editingDevice, rtu_baud_rate: parseInt(e.target.value) })
                        : setNewDevice({ ...newDevice, rtu_baud_rate: parseInt(e.target.value) })
                      }
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                    >
                      {[9600, 19200, 38400, 57600, 115200].map((rate) => (
                        <option key={rate} value={rate}>{rate}</option>
                      ))}
                    </select>
                  </div>
                </>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-300 mb-1">Slave Address</label>
                  <input
                    type="number"
                    value={editingDevice?.slave_addr ?? newDevice.slave_addr}
                    onChange={(e) => editingDevice
                      ? setEditingDevice({ ...editingDevice, slave_addr: parseInt(e.target.value) })
                      : setNewDevice({ ...newDevice, slave_addr: parseInt(e.target.value) })
                    }
                    min="1"
                    max="247"
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">Poll Interval (ms)</label>
                  <input
                    type="number"
                    value={editingDevice?.poll_interval_ms ?? newDevice.poll_interval_ms}
                    onChange={(e) => editingDevice
                      ? setEditingDevice({ ...editingDevice, poll_interval_ms: parseInt(e.target.value) })
                      : setNewDevice({ ...newDevice, poll_interval_ms: parseInt(e.target.value) })
                    }
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">Description</label>
                <input
                  type="text"
                  value={editingDevice?.description ?? newDevice.description}
                  onChange={(e) => editingDevice
                    ? setEditingDevice({ ...editingDevice, description: e.target.value })
                    : setNewDevice({ ...newDevice, description: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>

              <label className="flex items-center space-x-3">
                <input
                  type="checkbox"
                  checked={editingDevice?.enabled ?? newDevice.enabled}
                  onChange={(e) => editingDevice
                    ? setEditingDevice({ ...editingDevice, enabled: e.target.checked })
                    : setNewDevice({ ...newDevice, enabled: e.target.checked })
                  }
                  className="w-4 h-4"
                />
                <span className="text-gray-300">Enabled</span>
              </label>
            </div>

            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => {
                  setShowDeviceModal(false);
                  setEditingDevice(null);
                }}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white"
              >
                Cancel
              </button>
              <button
                onClick={saveDevice}
                disabled={loading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Mapping Modal */}
      {showMappingModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-900 p-6 rounded-lg w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-semibold text-white mb-4">
              {editingMapping ? 'Edit Mapping' : 'Add Register Mapping'}
            </h2>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-300 mb-1">Modbus Address</label>
                  <input
                    type="number"
                    value={editingMapping?.modbus_addr ?? newMapping.modbus_addr}
                    onChange={(e) => editingMapping
                      ? setEditingMapping({ ...editingMapping, modbus_addr: parseInt(e.target.value) })
                      : setNewMapping({ ...newMapping, modbus_addr: parseInt(e.target.value) })
                    }
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">Register Type</label>
                  <select
                    value={editingMapping?.register_type ?? newMapping.register_type}
                    onChange={(e) => editingMapping
                      ? setEditingMapping({ ...editingMapping, register_type: e.target.value })
                      : setNewMapping({ ...newMapping, register_type: e.target.value })
                    }
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  >
                    <option value="HOLDING">Holding Register</option>
                    <option value="INPUT">Input Register</option>
                    <option value="COIL">Coil</option>
                    <option value="DISCRETE">Discrete Input</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">Data Type</label>
                <select
                  value={editingMapping?.data_type ?? newMapping.data_type}
                  onChange={(e) => editingMapping
                    ? setEditingMapping({ ...editingMapping, data_type: e.target.value })
                    : setNewMapping({ ...newMapping, data_type: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                >
                  <option value="UINT16">UINT16 (1 register)</option>
                  <option value="INT16">INT16 (1 register)</option>
                  <option value="UINT32">UINT32 (2 registers)</option>
                  <option value="INT32">INT32 (2 registers)</option>
                  <option value="FLOAT32">FLOAT32 (2 registers)</option>
                  <option value="FLOAT64">FLOAT64 (4 registers)</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-300 mb-1">RTU Station</label>
                  <select
                    value={editingMapping?.rtu_station ?? newMapping.rtu_station}
                    onChange={(e) => editingMapping
                      ? setEditingMapping({ ...editingMapping, rtu_station: e.target.value })
                      : setNewMapping({ ...newMapping, rtu_station: e.target.value })
                    }
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  >
                    <option value="">Select RTU</option>
                    {rtus.map((rtu) => (
                      <option key={rtu.station_name} value={rtu.station_name}>
                        {rtu.station_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">Slot</label>
                  <input
                    type="number"
                    value={editingMapping?.slot ?? newMapping.slot}
                    onChange={(e) => editingMapping
                      ? setEditingMapping({ ...editingMapping, slot: parseInt(e.target.value) })
                      : setNewMapping({ ...newMapping, slot: parseInt(e.target.value) })
                    }
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">Description</label>
                <input
                  type="text"
                  value={editingMapping?.description ?? newMapping.description}
                  onChange={(e) => editingMapping
                    ? setEditingMapping({ ...editingMapping, description: e.target.value })
                    : setNewMapping({ ...newMapping, description: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>

              <label className="flex items-center space-x-3">
                <input
                  type="checkbox"
                  checked={editingMapping?.scaling_enabled ?? newMapping.scaling_enabled}
                  onChange={(e) => editingMapping
                    ? setEditingMapping({ ...editingMapping, scaling_enabled: e.target.checked })
                    : setNewMapping({ ...newMapping, scaling_enabled: e.target.checked })
                  }
                  className="w-4 h-4"
                />
                <span className="text-gray-300">Enable Scaling</span>
              </label>

              {(editingMapping?.scaling_enabled ?? newMapping.scaling_enabled) && (
                <div className="grid grid-cols-2 gap-4 bg-gray-800 p-4 rounded">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Raw Min</label>
                    <input
                      type="number"
                      value={editingMapping?.scale_raw_min ?? newMapping.scale_raw_min}
                      onChange={(e) => editingMapping
                        ? setEditingMapping({ ...editingMapping, scale_raw_min: parseFloat(e.target.value) })
                        : setNewMapping({ ...newMapping, scale_raw_min: parseFloat(e.target.value) })
                      }
                      className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Raw Max</label>
                    <input
                      type="number"
                      value={editingMapping?.scale_raw_max ?? newMapping.scale_raw_max}
                      onChange={(e) => editingMapping
                        ? setEditingMapping({ ...editingMapping, scale_raw_max: parseFloat(e.target.value) })
                        : setNewMapping({ ...newMapping, scale_raw_max: parseFloat(e.target.value) })
                      }
                      className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Eng Min</label>
                    <input
                      type="number"
                      value={editingMapping?.scale_eng_min ?? newMapping.scale_eng_min}
                      onChange={(e) => editingMapping
                        ? setEditingMapping({ ...editingMapping, scale_eng_min: parseFloat(e.target.value) })
                        : setNewMapping({ ...newMapping, scale_eng_min: parseFloat(e.target.value) })
                      }
                      className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Eng Max</label>
                    <input
                      type="number"
                      value={editingMapping?.scale_eng_max ?? newMapping.scale_eng_max}
                      onChange={(e) => editingMapping
                        ? setEditingMapping({ ...editingMapping, scale_eng_max: parseFloat(e.target.value) })
                        : setNewMapping({ ...newMapping, scale_eng_max: parseFloat(e.target.value) })
                      }
                      className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => {
                  setShowMappingModal(false);
                  setEditingMapping(null);
                }}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white"
              >
                Cancel
              </button>
              <button
                onClick={saveMapping}
                disabled={loading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
