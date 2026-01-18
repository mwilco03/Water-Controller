'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import Link from 'next/link';

const PAGE_TITLE = 'RTU Management - Water Treatment Controller';
import { useWebSocket } from '@/hooks/useWebSocket';
import { DiscoveryPanel, RtuStateBadge, AddRtuModal, DeleteRtuModal, StaleIndicator } from '@/components/rtu';
import { useHMIToast } from '@/components/hmi';
import type { DiscoveredDevice } from '@/lib/api';
import { wsLogger, rtuLogger } from '@/lib/logger';

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
  const toast = useHMIToast();

  // Set page title
  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);

  // Prefill data for add modal (used when selecting from discovery)
  const [addPrefill, setAddPrefill] = useState<AddRtuPrefill | undefined>(undefined);

  const fetchRtus = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/rtus');
      if (res.ok) {
        const json = await res.json();
        const arr = Array.isArray(json) ? json : (json.data || []);
        setRtus(arr);

        // Fetch health for each RTU
        for (const rtu of arr) {
          fetchHealth(rtu.station_name);
        }
      }
    } catch (error) {
      rtuLogger.error('Failed to fetch RTUs', error);
    }
  }, []);

  // WebSocket for real-time updates
  const { connected, subscribe } = useWebSocket({
    onConnect: () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
        wsLogger.info('WebSocket connected - RTU polling disabled');
      }
    },
    onDisconnect: () => {
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(fetchRtus, 5000);
        wsLogger.info('WebSocket disconnected - RTU polling enabled');
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
        return 'text-status-ok';
      case 'CONNECTING':
        return 'text-status-warning';
      case 'ERROR':
        return 'text-status-alarm';
      default:
        return 'text-hmi-muted';
    }
  };

  const getStateBadge = (state: string) => {
    const colors: { [key: string]: string } = {
      RUNNING: 'bg-status-ok/10 text-status-ok',
      CONNECTING: 'bg-status-warning/10 text-status-warning',
      ERROR: 'bg-status-alarm/10 text-status-alarm',
      OFFLINE: 'bg-hmi-panel text-hmi-muted',
    };
    return colors[state] || 'bg-hmi-panel text-hmi-muted';
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
        <h1 className="text-2xl font-bold text-hmi-text">RTU Management</h1>
        <div className="flex gap-3">
          <button
            onClick={() => setShowDiscovery(!showDiscovery)}
            className={`px-4 py-2 rounded text-white transition-colors ${
              showDiscovery
                ? 'bg-status-info hover:bg-status-info/90'
                : 'bg-hmi-panel hover:bg-hmi-panel/90'
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
            className="px-4 py-2 bg-status-ok hover:bg-status-ok/90 rounded text-white flex items-center gap-2"
          >
            <span className="text-lg font-bold">+</span>
            Add RTU
          </button>
        </div>
      </div>

      {/* Discovery Panel */}
      {showDiscovery && (
        <div className="hmi-card p-4">
          <DiscoveryPanel onDeviceSelect={handleDiscoveredDeviceSelect} />
        </div>
      )}

      {/* RTU Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* RTU List */}
        <div className="lg:col-span-1 hmi-card p-4">
          <h2 className="text-lg font-semibold text-hmi-text mb-4">Registered RTUs</h2>

          {rtus.length === 0 ? (
            <div className="text-center py-4">
              <p className="text-hmi-muted mb-3 text-sm">No RTUs registered</p>
              <button
                onClick={handleOpenAddModal}
                className="px-3 py-1.5 bg-status-info hover:bg-status-info/90 rounded text-white text-sm"
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
                      ? 'bg-status-info/10 border border-status-info'
                      : 'bg-hmi-panel hover:bg-hmi-panel/90 border border-transparent'
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-hmi-text truncate">{rtu.station_name}</div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-sm text-hmi-muted">{rtu.ip_address}</span>
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
        <div className="lg:col-span-2 hmi-card p-4">
          {selectedRtu ? (
            <div className="space-y-6">
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-xl font-semibold text-hmi-text">{selectedRtu.station_name}</h2>
                  <p className="text-hmi-muted">{selectedRtu.ip_address}</p>
                </div>
                <div className="flex items-center space-x-2">
                  <RtuStateBadge state={selectedRtu.connection_state} size="md" />
                  {selectedRtu.connection_state === 'OFFLINE' ? (
                    <button
                      onClick={() => connectRtu(selectedRtu.station_name)}
                      disabled={actionLoading === `connect-${selectedRtu.station_name}`}
                      className="px-3 py-1.5 bg-status-ok hover:bg-status-ok/90 rounded text-sm text-white flex items-center gap-1.5 disabled:opacity-50"
                    >
                      {actionLoading === `connect-${selectedRtu.station_name}` && (
                        <span className="animate-spin inline-block">&#8635;</span>
                      )}
                      Connect
                    </button>
                  ) : selectedRtu.connection_state !== 'CONNECTING' && (
                    <button
                      onClick={() => disconnectRtu(selectedRtu.station_name)}
                      disabled={actionLoading === `disconnect-${selectedRtu.station_name}`}
                      className="px-3 py-1.5 bg-status-warning hover:bg-status-warning/90 rounded text-sm text-white flex items-center gap-1.5 disabled:opacity-50"
                    >
                      {actionLoading === `disconnect-${selectedRtu.station_name}` && (
                        <span className="animate-spin inline-block">&#8635;</span>
                      )}
                      Disconnect
                    </button>
                  )}
                  <button
                    onClick={() => setShowDeleteModal(selectedRtu.station_name)}
                    className="px-3 py-1.5 bg-status-alarm hover:bg-status-alarm/90 rounded text-sm text-white"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {/* Device Info */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-hmi-panel p-4 rounded">
                  <div className="text-sm text-hmi-muted">Vendor ID</div>
                  <div className="text-hmi-text font-mono">0x{selectedRtu.vendor_id.toString(16).padStart(4, '0')}</div>
                </div>
                <div className="bg-hmi-panel p-4 rounded">
                  <div className="text-sm text-hmi-muted">Device ID</div>
                  <div className="text-hmi-text font-mono">0x{selectedRtu.device_id.toString(16).padStart(4, '0')}</div>
                </div>
                <div className="bg-hmi-panel p-4 rounded">
                  <div className="text-sm text-hmi-muted">Slot Count</div>
                  <div className="text-hmi-text">{selectedRtu.slot_count}</div>
                </div>
                <div className="bg-hmi-panel p-4 rounded">
                  <div className="text-sm text-hmi-muted">Connection State</div>
                  <div className={getStateColor(selectedRtu.connection_state)}>
                    {selectedRtu.connection_state}
                  </div>
                </div>
              </div>

              {/* Health Info */}
              {rtuHealth[selectedRtu.station_name] && (
                <div className="bg-hmi-panel p-4 rounded">
                  <h3 className="font-medium text-hmi-text mb-3">Health Status</h3>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <div className="text-sm text-hmi-muted">Healthy</div>
                      <div className={rtuHealth[selectedRtu.station_name].healthy ? 'text-status-ok' : 'text-status-alarm'}>
                        {rtuHealth[selectedRtu.station_name].healthy ? 'Yes' : 'No'}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-hmi-muted">Packet Loss</div>
                      <div className="text-hmi-text">
                        {rtuHealth[selectedRtu.station_name].packet_loss_percent.toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-hmi-muted">In Failover</div>
                      <div className={rtuHealth[selectedRtu.station_name].in_failover ? 'text-status-warning' : 'text-hmi-muted'}>
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
                  className="px-3 py-1.5 bg-status-info hover:bg-status-info/90 rounded text-sm text-white transition-colors"
                >
                  Full Details
                </Link>
                <Link
                  href={`/trends?rtu=${selectedRtu.station_name}`}
                  className="px-3 py-1.5 bg-hmi-panel hover:bg-hmi-panel/90 rounded text-sm text-hmi-text transition-colors"
                >
                  View Trends
                </Link>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center py-4 text-hmi-muted text-sm">
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
