'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';

interface RTUDevice {
  station_name: string;
  ip_address: string;
  vendor_id: number;
  device_id: number;
  connection_state: string;
  slot_count: number;
  last_seen?: string;
}

interface RTUHealth {
  station_name: string;
  connection_state: string;
  healthy: boolean;
  last_seen?: string;
  packet_loss_percent: number;
  consecutive_failures: number;
  in_failover: boolean;
}

export default function RTUsPage() {
  const [rtus, setRtus] = useState<RTUDevice[]>([]);
  const [selectedRtu, setSelectedRtu] = useState<RTUDevice | null>(null);
  const [rtuHealth, setRtuHealth] = useState<{ [key: string]: RTUHealth }>({});
  const [showAddModal, setShowAddModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Form state for adding RTU
  const [newRtu, setNewRtu] = useState({
    station_name: '',
    ip_address: '',
    vendor_id: 0x0493,
    device_id: 0x0001,
    slot_count: 16,
  });

  const fetchRtus = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/rtus');
      if (res.ok) {
        const data = await res.json();
        setRtus(data);

        // Fetch health for each RTU
        for (const rtu of data) {
          fetchHealth(rtu.station_name);
        }
      }
    } catch (error) {
      console.error('Failed to fetch RTUs:', error);
    }
  }, []);

  // WebSocket for real-time updates
  const { connected, subscribe } = useWebSocket({
    onConnect: () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
        console.log('WebSocket connected - RTU polling disabled');
      }
    },
    onDisconnect: () => {
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(fetchRtus, 5000);
        console.log('WebSocket disconnected - RTU polling enabled');
      }
    },
  });

  // Subscribe to RTU updates
  useEffect(() => {
    const unsub = subscribe('rtu_update', () => {
      fetchRtus();
    });

    const unsubScan = subscribe('network_scan_complete', () => {
      fetchRtus();
    });

    return () => {
      unsub();
      unsubScan();
    };
  }, [subscribe, fetchRtus]);

  // Initial fetch and polling setup
  useEffect(() => {
    fetchRtus();
    pollIntervalRef.current = setInterval(fetchRtus, 5000);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [fetchRtus]);

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const fetchHealth = async (stationName: string) => {
    try {
      const res = await fetch(`/api/v1/rtus/${stationName}/health`);
      if (res.ok) {
        const health = await res.json();
        setRtuHealth((prev) => ({ ...prev, [stationName]: health }));
      }
    } catch (error) {
      console.error('Failed to fetch health:', error);
    }
  };

  const addRtu = async () => {
    if (!newRtu.station_name || !newRtu.ip_address) {
      showMessage('error', 'Station name and IP address are required');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch('/api/v1/rtus', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newRtu),
      });

      if (res.ok) {
        showMessage('success', `RTU ${newRtu.station_name} added successfully`);
        setShowAddModal(false);
        setNewRtu({
          station_name: '',
          ip_address: '',
          vendor_id: 0x0493,
          device_id: 0x0001,
          slot_count: 16,
        });
        fetchRtus();
      } else {
        const error = await res.json();
        showMessage('error', error.detail || 'Failed to add RTU');
      }
    } catch (error) {
      showMessage('error', 'Error adding RTU');
    } finally {
      setLoading(false);
    }
  };

  const deleteRtu = async (stationName: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/rtus/${stationName}?cascade=true`, {
        method: 'DELETE',
      });

      if (res.ok) {
        const result = await res.json();
        const deleted = result.cascade_deleted;
        showMessage(
          'success',
          `RTU ${stationName} deleted. Cleaned up: ${deleted.alarm_rules} alarm rules, ` +
            `${deleted.pid_loops} PID loops, ${deleted.historian_tags} historian tags`
        );
        setShowDeleteModal(null);
        if (selectedRtu?.station_name === stationName) {
          setSelectedRtu(null);
        }
        fetchRtus();
      } else {
        showMessage('error', 'Failed to delete RTU');
      }
    } catch (error) {
      showMessage('error', 'Error deleting RTU');
    } finally {
      setLoading(false);
    }
  };

  const connectRtu = async (stationName: string) => {
    try {
      const res = await fetch(`/api/v1/rtus/${stationName}/connect`, {
        method: 'POST',
      });
      if (res.ok) {
        showMessage('success', `Connecting to ${stationName}...`);
        fetchRtus();
      }
    } catch (error) {
      showMessage('error', 'Connection failed');
    }
  };

  const disconnectRtu = async (stationName: string) => {
    try {
      const res = await fetch(`/api/v1/rtus/${stationName}/disconnect`, {
        method: 'POST',
      });
      if (res.ok) {
        showMessage('success', `Disconnected from ${stationName}`);
        fetchRtus();
      }
    } catch (error) {
      showMessage('error', 'Disconnect failed');
    }
  };

  const getStateColor = (state: string) => {
    switch (state) {
      case 'RUNNING':
        return 'text-green-400';
      case 'CONNECTING':
        return 'text-yellow-400';
      case 'ERROR':
        return 'text-red-400';
      default:
        return 'text-gray-400';
    }
  };

  const getStateBadge = (state: string) => {
    const colors: { [key: string]: string } = {
      RUNNING: 'bg-green-900 text-green-300',
      CONNECTING: 'bg-yellow-900 text-yellow-300',
      ERROR: 'bg-red-900 text-red-300',
      OFFLINE: 'bg-gray-700 text-gray-300',
    };
    return colors[state] || 'bg-gray-700 text-gray-300';
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-white">RTU Management</h1>
        <button
          onClick={() => setShowAddModal(true)}
          className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-white"
        >
          + Add RTU
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

      {/* RTU Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* RTU List */}
        <div className="lg:col-span-1 scada-panel p-4">
          <h2 className="text-lg font-semibold text-white mb-4">Registered RTUs</h2>

          {rtus.length === 0 ? (
            <p className="text-gray-400">No RTUs registered</p>
          ) : (
            <div className="space-y-2">
              {rtus.map((rtu) => (
                <div
                  key={rtu.station_name}
                  onClick={() => setSelectedRtu(rtu)}
                  className={`p-3 rounded cursor-pointer transition-colors ${
                    selectedRtu?.station_name === rtu.station_name
                      ? 'bg-blue-900 border border-blue-500'
                      : 'bg-gray-800 hover:bg-gray-700'
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <div>
                      <div className="font-medium text-white">{rtu.station_name}</div>
                      <div className="text-sm text-gray-400">{rtu.ip_address}</div>
                    </div>
                    <span className={`px-2 py-1 rounded text-xs ${getStateBadge(rtu.connection_state)}`}>
                      {rtu.connection_state}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* RTU Details */}
        <div className="lg:col-span-2 scada-panel p-4">
          {selectedRtu ? (
            <div className="space-y-6">
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-xl font-semibold text-white">{selectedRtu.station_name}</h2>
                  <p className="text-gray-400">{selectedRtu.ip_address}</p>
                </div>
                <div className="flex space-x-2">
                  {selectedRtu.connection_state === 'OFFLINE' ? (
                    <button
                      onClick={() => connectRtu(selectedRtu.station_name)}
                      className="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm text-white"
                    >
                      Connect
                    </button>
                  ) : (
                    <button
                      onClick={() => disconnectRtu(selectedRtu.station_name)}
                      className="px-3 py-1 bg-yellow-600 hover:bg-yellow-700 rounded text-sm text-white"
                    >
                      Disconnect
                    </button>
                  )}
                  <button
                    onClick={() => setShowDeleteModal(selectedRtu.station_name)}
                    className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm text-white"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {/* Device Info */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-gray-800 p-4 rounded">
                  <div className="text-sm text-gray-400">Vendor ID</div>
                  <div className="text-white font-mono">0x{selectedRtu.vendor_id.toString(16).padStart(4, '0')}</div>
                </div>
                <div className="bg-gray-800 p-4 rounded">
                  <div className="text-sm text-gray-400">Device ID</div>
                  <div className="text-white font-mono">0x{selectedRtu.device_id.toString(16).padStart(4, '0')}</div>
                </div>
                <div className="bg-gray-800 p-4 rounded">
                  <div className="text-sm text-gray-400">Slot Count</div>
                  <div className="text-white">{selectedRtu.slot_count}</div>
                </div>
                <div className="bg-gray-800 p-4 rounded">
                  <div className="text-sm text-gray-400">Connection State</div>
                  <div className={getStateColor(selectedRtu.connection_state)}>
                    {selectedRtu.connection_state}
                  </div>
                </div>
              </div>

              {/* Health Info */}
              {rtuHealth[selectedRtu.station_name] && (
                <div className="bg-gray-800 p-4 rounded">
                  <h3 className="font-medium text-white mb-3">Health Status</h3>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <div className="text-sm text-gray-400">Healthy</div>
                      <div className={rtuHealth[selectedRtu.station_name].healthy ? 'text-green-400' : 'text-red-400'}>
                        {rtuHealth[selectedRtu.station_name].healthy ? 'Yes' : 'No'}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-400">Packet Loss</div>
                      <div className="text-white">
                        {rtuHealth[selectedRtu.station_name].packet_loss_percent.toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-400">In Failover</div>
                      <div className={rtuHealth[selectedRtu.station_name].in_failover ? 'text-yellow-400' : 'text-gray-400'}>
                        {rtuHealth[selectedRtu.station_name].in_failover ? 'Yes' : 'No'}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Quick Links */}
              <div className="flex space-x-4">
                <a href={`/rtus/${selectedRtu.station_name}/sensors`} className="text-blue-400 hover:underline">
                  View Sensors
                </a>
                <a href={`/rtus/${selectedRtu.station_name}/actuators`} className="text-blue-400 hover:underline">
                  View Actuators
                </a>
                <a href={`/trends?rtu=${selectedRtu.station_name}`} className="text-blue-400 hover:underline">
                  View Trends
                </a>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-64 text-gray-400">
              Select an RTU to view details
            </div>
          )}
        </div>
      </div>

      {/* Add RTU Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-900 p-6 rounded-lg w-full max-w-md">
            <h2 className="text-xl font-semibold text-white mb-4">Add New RTU</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-300 mb-1">Station Name</label>
                <input
                  type="text"
                  value={newRtu.station_name}
                  onChange={(e) => setNewRtu({ ...newRtu, station_name: e.target.value })}
                  placeholder="e.g., water-treat-rtu"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">IP Address</label>
                <input
                  type="text"
                  value={newRtu.ip_address}
                  onChange={(e) => setNewRtu({ ...newRtu, ip_address: e.target.value })}
                  placeholder="e.g., 192.168.1.100"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-300 mb-1">Vendor ID</label>
                  <input
                    type="text"
                    value={`0x${newRtu.vendor_id.toString(16).padStart(4, '0')}`}
                    onChange={(e) => setNewRtu({ ...newRtu, vendor_id: parseInt(e.target.value, 16) || 0 })}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">Device ID</label>
                  <input
                    type="text"
                    value={`0x${newRtu.device_id.toString(16).padStart(4, '0')}`}
                    onChange={(e) => setNewRtu({ ...newRtu, device_id: parseInt(e.target.value, 16) || 0 })}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">Slot Count</label>
                <select
                  value={newRtu.slot_count}
                  onChange={(e) => setNewRtu({ ...newRtu, slot_count: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                >
                  {[8, 16, 32, 64].map((count) => (
                    <option key={count} value={count}>
                      {count} slots
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white"
              >
                Cancel
              </button>
              <button
                onClick={addRtu}
                disabled={loading}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Adding...' : 'Add RTU'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-900 p-6 rounded-lg w-full max-w-md">
            <h2 className="text-xl font-semibold text-white mb-4">Delete RTU</h2>

            <p className="text-gray-300 mb-4">
              Are you sure you want to delete <strong>{showDeleteModal}</strong>?
            </p>

            <div className="bg-yellow-900 text-yellow-200 p-3 rounded mb-4">
              <strong>Warning:</strong> This will also delete all associated:
              <ul className="list-disc ml-5 mt-2">
                <li>Alarm rules</li>
                <li>PID loops</li>
                <li>Historian tags</li>
                <li>Modbus mappings</li>
                <li>Active alarms</li>
              </ul>
            </div>

            <div className="flex justify-end space-x-3">
              <button
                onClick={() => setShowDeleteModal(null)}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteRtu(showDeleteModal)}
                disabled={loading}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Deleting...' : 'Delete RTU'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
