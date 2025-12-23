'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import Link from 'next/link';
import { useWebSocket } from '@/hooks/useWebSocket';
import { DiscoveryPanel, RtuStateBadge, AddRtuModal, DeleteRtuModal, StaleIndicator } from '@/components/rtu';
import { useToast } from '@/components/ui/Toast';
import type { DiscoveredDevice } from '@/lib/api';

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

interface AddRtuPrefill {
  station_name?: string;
  ip_address?: string;
  vendor_id?: string;
  device_id?: string;
}

export default function RTUsPage() {
  const [rtus, setRtus] = useState<RTUDevice[]>([]);
  const [selectedRtu, setSelectedRtu] = useState<RTUDevice | null>(null);
  const [rtuHealth, setRtuHealth] = useState<{ [key: string]: RTUHealth }>({});
  const [showAddModal, setShowAddModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState<string | null>(null);
  const [showDiscovery, setShowDiscovery] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const toast = useToast();

  // Prefill data for add modal (used when selecting from discovery)
  const [addPrefill, setAddPrefill] = useState<AddRtuPrefill | undefined>(undefined);

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

  const fetchHealth = async (stationName: string) => {
    try {
      const res = await fetch(`/api/v1/rtus/${stationName}/health`);
      if (res.ok) {
        const health = await res.json();
        setRtuHealth((prev) => ({ ...prev, [stationName]: health }));
      }
    } catch {
      // Silently fail - health data is supplementary
    }
  };

  const handleAddSuccess = useCallback((rtu: { station_name: string }) => {
    setShowAddModal(false);
    setAddPrefill(undefined);
    toast.success('RTU added successfully', `${rtu.station_name} has been registered`);
    fetchRtus();
  }, [toast, fetchRtus]);

  const handleDeleteSuccess = useCallback((result: { deleted: { alarm_rules: number; pid_loops: number; historian_tags: number } }) => {
    const deleted = result.deleted;
    const stationName = showDeleteModal;
    setShowDeleteModal(null);
    if (selectedRtu?.station_name === stationName) {
      setSelectedRtu(null);
    }
    toast.success(
      'RTU deleted',
      `Cleaned up: ${deleted.alarm_rules} alarm rules, ${deleted.pid_loops} PID loops, ${deleted.historian_tags} historian tags`
    );
    fetchRtus();
  }, [showDeleteModal, selectedRtu, toast, fetchRtus]);

  const connectRtu = async (stationName: string) => {
    setActionLoading(`connect-${stationName}`);
    try {
      const res = await fetch(`/api/v1/rtus/${stationName}/connect`, {
        method: 'POST',
      });
      if (res.ok) {
        toast.info('Connecting...', `Establishing connection to ${stationName}`);
        fetchRtus();
      } else {
        toast.error('Connection failed', 'Check RTU status and network connectivity');
      }
    } catch {
      toast.error('Connection failed', 'Unable to reach server');
    } finally {
      setActionLoading(null);
    }
  };

  const disconnectRtu = async (stationName: string) => {
    setActionLoading(`disconnect-${stationName}`);
    try {
      const res = await fetch(`/api/v1/rtus/${stationName}/disconnect`, {
        method: 'POST',
      });
      if (res.ok) {
        toast.success('Disconnected', `${stationName} has been disconnected`);
        fetchRtus();
      } else {
        toast.error('Disconnect failed', 'Unable to disconnect RTU');
      }
    } catch {
      toast.error('Disconnect failed', 'Unable to reach server');
    } finally {
      setActionLoading(null);
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

  // Handle device selection from discovery panel
  const handleDiscoveredDeviceSelect = (device: DiscoveredDevice) => {
    // Pre-fill the add RTU form with discovered device info
    setAddPrefill({
      station_name: device.device_name || `rtu-${device.mac_address.replace(/:/g, '').slice(-6)}`,
      ip_address: device.ip_address || '',
      vendor_id: device.vendor_id ? `0x${device.vendor_id.toString(16).padStart(4, '0')}` : undefined,
      device_id: device.device_id ? `0x${device.device_id.toString(16).padStart(4, '0')}` : undefined,
    });
    setShowAddModal(true);
  };

  const handleOpenAddModal = () => {
    setAddPrefill(undefined);
    setShowAddModal(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-white">RTU Management</h1>
        <div className="flex gap-3">
          <button
            onClick={() => setShowDiscovery(!showDiscovery)}
            className={`px-4 py-2 rounded text-white transition-colors ${
              showDiscovery
                ? 'bg-blue-600 hover:bg-blue-700'
                : 'bg-gray-600 hover:bg-gray-500'
            }`}
          >
            {showDiscovery ? 'Hide Discovery' : 'Scan Network'}
          </button>
          <Link
            href="/wizard"
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded text-white transition-colors"
          >
            Setup Wizard
          </Link>
          <button
            onClick={handleOpenAddModal}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-white flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            Add RTU
          </button>
        </div>
      </div>

      {/* Discovery Panel */}
      {showDiscovery && (
        <div className="scada-panel p-4">
          <DiscoveryPanel onDeviceSelect={handleDiscoveredDeviceSelect} />
        </div>
      )}

      {/* RTU Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* RTU List */}
        <div className="lg:col-span-1 scada-panel p-4">
          <h2 className="text-lg font-semibold text-white mb-4">Registered RTUs</h2>

          {rtus.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-gray-400 mb-4">No RTUs registered</p>
              <button
                onClick={handleOpenAddModal}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-white text-sm"
              >
                Add Your First RTU
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {rtus.map((rtu) => (
                <div
                  key={rtu.station_name}
                  onClick={() => setSelectedRtu(rtu)}
                  className={`p-3 rounded cursor-pointer transition-all ${
                    selectedRtu?.station_name === rtu.station_name
                      ? 'bg-blue-900/50 border border-blue-500'
                      : 'bg-gray-800 hover:bg-gray-700 border border-transparent'
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-white truncate">{rtu.station_name}</div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-sm text-gray-400">{rtu.ip_address}</span>
                        {rtu.last_seen && (
                          <StaleIndicator
                            lastUpdated={rtu.last_seen}
                            size="xs"
                            variant="dot"
                          />
                        )}
                      </div>
                    </div>
                    <RtuStateBadge state={rtu.connection_state} size="sm" />
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
                <div className="flex items-center space-x-2">
                  <RtuStateBadge state={selectedRtu.connection_state} size="md" />
                  {selectedRtu.connection_state === 'OFFLINE' ? (
                    <button
                      onClick={() => connectRtu(selectedRtu.station_name)}
                      disabled={actionLoading === `connect-${selectedRtu.station_name}`}
                      className="px-3 py-1.5 bg-green-600 hover:bg-green-500 rounded text-sm text-white flex items-center gap-1.5 disabled:opacity-50"
                    >
                      {actionLoading === `connect-${selectedRtu.station_name}` && (
                        <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                      )}
                      Connect
                    </button>
                  ) : selectedRtu.connection_state !== 'CONNECTING' && (
                    <button
                      onClick={() => disconnectRtu(selectedRtu.station_name)}
                      disabled={actionLoading === `disconnect-${selectedRtu.station_name}`}
                      className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 rounded text-sm text-white flex items-center gap-1.5 disabled:opacity-50"
                    >
                      {actionLoading === `disconnect-${selectedRtu.station_name}` && (
                        <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                      )}
                      Disconnect
                    </button>
                  )}
                  <button
                    onClick={() => setShowDeleteModal(selectedRtu.station_name)}
                    className="px-3 py-1.5 bg-red-600 hover:bg-red-500 rounded text-sm text-white"
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
              <div className="flex flex-wrap gap-3">
                <Link
                  href={`/rtus/${selectedRtu.station_name}`}
                  className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm text-white transition-colors"
                >
                  Full Details
                </Link>
                <Link
                  href={`/trends?rtu=${selectedRtu.station_name}`}
                  className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm text-white transition-colors"
                >
                  View Trends
                </Link>
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
      <AddRtuModal
        isOpen={showAddModal}
        onClose={() => {
          setShowAddModal(false);
          setAddPrefill(undefined);
        }}
        onSuccess={handleAddSuccess}
        prefillData={addPrefill}
      />

      {/* Delete RTU Modal */}
      <DeleteRtuModal
        isOpen={showDeleteModal !== null}
        stationName={showDeleteModal || ''}
        onClose={() => setShowDeleteModal(null)}
        onSuccess={handleDeleteSuccess}
      />
    </div>
  );
}
