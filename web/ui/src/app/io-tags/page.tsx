'use client';

import { useEffect, useState, useCallback } from 'react';
import { rtuLogger, configLogger } from '@/lib/logger';
import { useHMIToast, ConfirmModal } from '@/components/hmi';

interface RTUDevice {
  station_name: string;
  ip_address: string;
  slot_count: number;
}

interface SlotConfig {
  id: number;
  rtu_station: string;
  slot: number;
  subslot: number;
  slot_type: string;
  name: string;
  unit: string;
  measurement_type: string;
  actuator_type: string;
  scale_min: number;
  scale_max: number;
  alarm_low: number | null;
  alarm_high: number | null;
  alarm_low_low: number | null;
  alarm_high_high: number | null;
  deadband: number;
  enabled: boolean;
}

interface HistorianTag {
  id: number;
  rtu_station: string;
  slot: number;
  tag_name: string;
  unit: string;
  sample_rate_ms: number;
  deadband: number;
  compression: string;
}

export default function IOTagsPage() {
  const [rtus, setRtus] = useState<RTUDevice[]>([]);
  const [selectedRtu, setSelectedRtu] = useState<string>('');
  const [slotConfigs, setSlotConfigs] = useState<SlotConfig[]>([]);
  const [historianTags, setHistorianTags] = useState<HistorianTag[]>([]);
  const [activeTab, setActiveTab] = useState<'slots' | 'historian'>('slots');
  const [showEditModal, setShowEditModal] = useState<SlotConfig | null>(null);
  const [showHistorianModal, setShowHistorianModal] = useState<HistorianTag | null>(null);
  const [tagToDelete, setTagToDelete] = useState<HistorianTag | null>(null);
  const [loading, setLoading] = useState(false);
  const { showMessage } = useHMIToast();

  const fetchRtus = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/rtus');
      if (res.ok) {
        const json = await res.json();
        const arr = Array.isArray(json) ? json : (json.data || []);
        setRtus(arr);
        if (arr.length > 0 && !selectedRtu) {
          setSelectedRtu(arr[0].station_name);
        }
      }
    } catch (error) {
      rtuLogger.error('Failed to fetch RTUs', error);
    }
  }, [selectedRtu]);

  const fetchSlotConfigs = useCallback(async () => {
    if (!selectedRtu) return;
    try {
      const res = await fetch(`/api/v1/rtus/${selectedRtu}/slots`);
      if (res.ok) {
        const json = await res.json();
        const arr = Array.isArray(json) ? json : (json.data || []);
        setSlotConfigs(arr);
      }
    } catch (error) {
      configLogger.error('Failed to fetch slot configs', error);
    }
  }, [selectedRtu]);

  const fetchHistorianTags = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/trends/tags');
      if (res.ok) {
        const json = await res.json();
        const arr = Array.isArray(json) ? json : (json.data || json.tags || []);
        setHistorianTags(arr.filter((t: HistorianTag) => !selectedRtu || t.rtu_station === selectedRtu));
      }
    } catch (error) {
      configLogger.error('Failed to fetch historian tags', error);
    }
  }, [selectedRtu]);

  useEffect(() => {
    fetchRtus();
  }, [fetchRtus]);

  useEffect(() => {
    if (selectedRtu) {
      fetchSlotConfigs();
      fetchHistorianTags();
    }
  }, [selectedRtu, fetchSlotConfigs, fetchHistorianTags]);

  const saveSlotConfig = async () => {
    if (!showEditModal) return;

    setLoading(true);
    try {
      const res = await fetch(`/api/v1/rtus/${showEditModal.rtu_station}/slots/${showEditModal.slot}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(showEditModal),
      });

      if (res.ok) {
        showMessage('success', `Slot ${showEditModal.slot} configuration saved`);
        setShowEditModal(null);
        fetchSlotConfigs();
      } else {
        const error = await res.json();
        showMessage('error', error.detail || 'Failed to save configuration');
      }
    } catch (error) {
      showMessage('error', 'Error saving configuration');
    } finally {
      setLoading(false);
    }
  };

  const saveHistorianTag = async () => {
    if (!showHistorianModal) return;

    setLoading(true);
    try {
      const method = showHistorianModal.id ? 'PUT' : 'POST';
      const url = showHistorianModal.id
        ? `/api/v1/trends/tags/${showHistorianModal.id}`
        : '/api/v1/trends/tags';

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(showHistorianModal),
      });

      if (res.ok) {
        showMessage('success', `Historian tag ${showHistorianModal.tag_name} saved`);
        setShowHistorianModal(null);
        fetchHistorianTags();
      } else {
        const error = await res.json();
        showMessage('error', error.detail || 'Failed to save historian tag');
      }
    } catch (error) {
      showMessage('error', 'Error saving historian tag');
    } finally {
      setLoading(false);
    }
  };

  const confirmDeleteHistorianTag = async () => {
    if (!tagToDelete) return;

    try {
      const res = await fetch(`/api/v1/trends/tags/${tagToDelete.id}`, { method: 'DELETE' });
      if (res.ok) {
        showMessage('success', 'Historian tag deleted');
        fetchHistorianTags();
      } else {
        showMessage('error', 'Failed to delete historian tag');
      }
    } catch (error) {
      showMessage('error', 'Error deleting historian tag');
    } finally {
      setTagToDelete(null);
    }
  };

  const autoDiscoverSlots = async () => {
    if (!selectedRtu) return;

    setLoading(true);
    try {
      const res = await fetch(`/api/v1/rtus/${selectedRtu}/discover`, { method: 'POST' });
      if (res.ok) {
        const result = await res.json();
        showMessage('success', `Discovered ${result.slots_configured} slots`);
        fetchSlotConfigs();
      } else {
        showMessage('error', 'Auto-discovery failed. RTU may be offline.');
      }
    } catch (error) {
      showMessage('error', 'Error during auto-discovery');
    } finally {
      setLoading(false);
    }
  };

  const exportConfig = () => {
    const data = {
      slot_configs: slotConfigs,
      historian_tags: historianTags.filter((t) => t.rtu_station === selectedRtu),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `io_config_${selectedRtu}_${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const importConfig = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const config = JSON.parse(text);

      // Import slot configs
      if (config.slot_configs) {
        for (const slot of config.slot_configs) {
          await fetch(`/api/v1/rtus/${slot.rtu_station}/slots/${slot.slot}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(slot),
          });
        }
      }

      // Import historian tags
      if (config.historian_tags) {
        for (const tag of config.historian_tags) {
          await fetch('/api/v1/trends/tags', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(tag),
          });
        }
      }

      showMessage('success', 'Configuration imported successfully');
      fetchSlotConfigs();
      fetchHistorianTags();
    } catch (error) {
      showMessage('error', 'Invalid configuration file');
    }

    event.target.value = '';
  };

  const getSlotTypeBadge = (type: string) => {
    const colors: { [key: string]: string } = {
      sensor: 'bg-status-info/10 text-status-info',
      actuator: 'bg-status-ok/10 text-status-ok',
      digital_in: 'bg-status-info/10 text-status-info',
      digital_out: 'bg-status-info/10 text-status-info',
    };
    return colors[type] || 'bg-hmi-muted/10 text-hmi-muted';
  };

  const currentRtu = rtus.find((r) => r.station_name === selectedRtu);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-hmi-text">I/O Configuration</h1>
        <div className="flex space-x-2">
          <label className="px-4 py-2 bg-hmi-panel hover:bg-hmi-border rounded text-hmi-text cursor-pointer">
            Import
            <input type="file" accept=".json" onChange={importConfig} className="hidden" />
          </label>
          <button
            onClick={exportConfig}
            className="px-4 py-2 bg-hmi-panel hover:bg-hmi-border rounded text-hmi-text"
          >
            Export
          </button>
        </div>
      </div>

      {/* RTU Selector */}
      <div className="hmi-card p-4">
        <div className="flex items-center gap-4">
          <label className="text-hmi-muted">Select RTU:</label>
          <select
            value={selectedRtu}
            onChange={(e) => setSelectedRtu(e.target.value)}
            className="px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text min-w-[200px]"
          >
            {rtus.map((rtu) => (
              <option key={rtu.station_name} value={rtu.station_name}>
                {rtu.station_name} ({rtu.ip_address})
              </option>
            ))}
          </select>
          <button
            onClick={autoDiscoverSlots}
            disabled={loading || !selectedRtu}
            className="px-4 py-2 bg-status-info hover:bg-status-info/90 rounded text-white disabled:opacity-50"
          >
            {loading ? 'Discovering...' : 'Auto-Discover Slots'}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex space-x-4 border-b border-hmi-border">
        {[
          { id: 'slots', label: `Slot Configuration (${currentRtu?.slot_count || 0} slots)` },
          { id: 'historian', label: 'Historian Tags' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as 'slots' | 'historian')}
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

      {/* Slots Tab */}
      {activeTab === 'slots' && (
        <div className="hmi-card p-6">
          <table className="w-full">
            <thead>
              <tr className="text-left text-hmi-muted text-sm border-b border-hmi-border">
                <th className="pb-3">Slot</th>
                <th className="pb-3">Type</th>
                <th className="pb-3">Name</th>
                <th className="pb-3">Measurement/Actuator</th>
                <th className="pb-3">Scale</th>
                <th className="pb-3">Unit</th>
                <th className="pb-3">Alarms</th>
                <th className="pb-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {slotConfigs.map((slot) => (
                <tr key={`${slot.rtu_station}-${slot.slot}`} className="border-b border-hmi-border">
                  <td className="py-3 font-mono text-hmi-text">{slot.slot}</td>
                  <td className="py-3">
                    <span className={`px-2 py-1 rounded text-xs ${getSlotTypeBadge(slot.slot_type)}`}>
                      {slot.slot_type}
                    </span>
                  </td>
                  <td className="py-3 text-hmi-text">{slot.name || '-'}</td>
                  <td className="py-3 text-hmi-muted">
                    {slot.measurement_type || slot.actuator_type || '-'}
                  </td>
                  <td className="py-3 text-hmi-muted font-mono text-sm">
                    {slot.scale_min} - {slot.scale_max}
                  </td>
                  <td className="py-3 text-hmi-muted">{slot.unit || '-'}</td>
                  <td className="py-3 text-hmi-muted text-sm">
                    {slot.alarm_low !== null || slot.alarm_high !== null ? (
                      <span className="text-status-warning">
                        {slot.alarm_low !== null && `L:${slot.alarm_low}`}
                        {slot.alarm_low !== null && slot.alarm_high !== null && ' / '}
                        {slot.alarm_high !== null && `H:${slot.alarm_high}`}
                      </span>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="py-3 text-right">
                    <button
                      onClick={() => setShowEditModal(slot)}
                      className="px-3 py-1 bg-hmi-panel hover:bg-hmi-border rounded text-sm text-hmi-text"
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {slotConfigs.length === 0 && (
            <p className="text-hmi-muted text-center py-3 text-sm">
              No slot configurations. Click &quot;Auto-Discover Slots&quot; to detect connected devices.
            </p>
          )}
        </div>
      )}

      {/* Historian Tab */}
      {activeTab === 'historian' && (
        <div className="hmi-card p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-hmi-text">Historian Tags</h2>
            <button
              onClick={() =>
                setShowHistorianModal({
                  id: 0,
                  rtu_station: selectedRtu,
                  slot: 1,
                  tag_name: '',
                  unit: '',
                  sample_rate_ms: 1000,
                  deadband: 0.1,
                  compression: 'swinging_door',
                })
              }
              className="px-4 py-2 bg-status-ok hover:bg-status-ok/90 rounded text-white"
            >
              + Add Tag
            </button>
          </div>

          <table className="w-full">
            <thead>
              <tr className="text-left text-hmi-muted text-sm border-b border-hmi-border">
                <th className="pb-3">Tag Name</th>
                <th className="pb-3">RTU / Slot</th>
                <th className="pb-3">Unit</th>
                <th className="pb-3">Sample Rate</th>
                <th className="pb-3">Deadband</th>
                <th className="pb-3">Compression</th>
                <th className="pb-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {historianTags.map((tag) => (
                <tr key={tag.id} className="border-b border-hmi-border">
                  <td className="py-3 text-hmi-text font-medium">{tag.tag_name}</td>
                  <td className="py-3 text-hmi-muted">
                    {tag.rtu_station} / Slot {tag.slot}
                  </td>
                  <td className="py-3 text-hmi-muted">{tag.unit || '-'}</td>
                  <td className="py-3 text-hmi-muted">{tag.sample_rate_ms}ms</td>
                  <td className="py-3 text-hmi-muted">{tag.deadband}</td>
                  <td className="py-3">
                    <span className="px-2 py-1 bg-hmi-muted/10 rounded text-xs text-hmi-muted">
                      {tag.compression}
                    </span>
                  </td>
                  <td className="py-3 text-right">
                    <div className="flex justify-end space-x-2">
                      <button
                        onClick={() => setShowHistorianModal(tag)}
                        className="px-3 py-1 bg-hmi-panel hover:bg-hmi-border rounded text-sm text-hmi-text"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => setTagToDelete(tag)}
                        className="px-3 py-1 bg-status-alarm hover:bg-status-alarm/90 rounded text-sm text-white"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {historianTags.length === 0 && (
            <p className="text-hmi-muted text-center py-3 text-sm">
              No historian tags configured. Add tags to start collecting historical data.
            </p>
          )}
        </div>
      )}

      {/* Edit Slot Modal */}
      {showEditModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-y-auto py-4">
          <div className="bg-white p-6 rounded-lg w-full max-w-2xl">
            <h2 className="text-xl font-semibold text-hmi-text mb-4">
              Edit Slot {showEditModal.slot} - {showEditModal.rtu_station}
            </h2>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-hmi-muted mb-1">Name</label>
                <input
                  type="text"
                  value={showEditModal.name || ''}
                  onChange={(e) => setShowEditModal({ ...showEditModal, name: e.target.value })}
                  placeholder="e.g., Tank_1_Level"
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Type</label>
                <select
                  value={showEditModal.slot_type}
                  onChange={(e) => setShowEditModal({ ...showEditModal, slot_type: e.target.value })}
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                >
                  <option value="sensor">Sensor (Analog Input)</option>
                  <option value="actuator">Actuator (Analog Output)</option>
                  <option value="digital_in">Digital Input</option>
                  <option value="digital_out">Digital Output</option>
                </select>
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Measurement Type</label>
                <select
                  value={showEditModal.measurement_type || ''}
                  onChange={(e) => setShowEditModal({ ...showEditModal, measurement_type: e.target.value })}
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                >
                  <option value="">Select...</option>
                  <option value="pH">pH</option>
                  <option value="temperature">Temperature</option>
                  <option value="tds">TDS (Total Dissolved Solids)</option>
                  <option value="turbidity">Turbidity</option>
                  <option value="level">Level</option>
                  <option value="flow">Flow Rate</option>
                  <option value="pressure">Pressure</option>
                  <option value="chlorine">Chlorine</option>
                  <option value="dissolved_oxygen">Dissolved Oxygen</option>
                  <option value="conductivity">Conductivity</option>
                  <option value="orp">ORP</option>
                </select>
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Unit</label>
                <input
                  type="text"
                  value={showEditModal.unit || ''}
                  onChange={(e) => setShowEditModal({ ...showEditModal, unit: e.target.value })}
                  placeholder="e.g., pH, degC, ppm"
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Scale Min</label>
                <input
                  type="number"
                  value={showEditModal.scale_min}
                  onChange={(e) =>
                    setShowEditModal({ ...showEditModal, scale_min: parseFloat(e.target.value) })
                  }
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Scale Max</label>
                <input
                  type="number"
                  value={showEditModal.scale_max}
                  onChange={(e) =>
                    setShowEditModal({ ...showEditModal, scale_max: parseFloat(e.target.value) })
                  }
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Alarm Low</label>
                <input
                  type="number"
                  value={showEditModal.alarm_low ?? ''}
                  onChange={(e) =>
                    setShowEditModal({
                      ...showEditModal,
                      alarm_low: e.target.value ? parseFloat(e.target.value) : null,
                    })
                  }
                  placeholder="Optional"
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Alarm High</label>
                <input
                  type="number"
                  value={showEditModal.alarm_high ?? ''}
                  onChange={(e) =>
                    setShowEditModal({
                      ...showEditModal,
                      alarm_high: e.target.value ? parseFloat(e.target.value) : null,
                    })
                  }
                  placeholder="Optional"
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Alarm Low-Low (Critical)</label>
                <input
                  type="number"
                  value={showEditModal.alarm_low_low ?? ''}
                  onChange={(e) =>
                    setShowEditModal({
                      ...showEditModal,
                      alarm_low_low: e.target.value ? parseFloat(e.target.value) : null,
                    })
                  }
                  placeholder="Optional"
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Alarm High-High (Critical)</label>
                <input
                  type="number"
                  value={showEditModal.alarm_high_high ?? ''}
                  onChange={(e) =>
                    setShowEditModal({
                      ...showEditModal,
                      alarm_high_high: e.target.value ? parseFloat(e.target.value) : null,
                    })
                  }
                  placeholder="Optional"
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                />
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Deadband</label>
                <input
                  type="number"
                  step="0.01"
                  value={showEditModal.deadband}
                  onChange={(e) =>
                    setShowEditModal({ ...showEditModal, deadband: parseFloat(e.target.value) })
                  }
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                />
              </div>

              <div className="flex items-center pt-6">
                <input
                  type="checkbox"
                  id="slotEnabled"
                  checked={showEditModal.enabled}
                  onChange={(e) => setShowEditModal({ ...showEditModal, enabled: e.target.checked })}
                />
                <label htmlFor="slotEnabled" className="ml-2 text-sm text-hmi-muted">
                  Slot Enabled
                </label>
              </div>
            </div>

            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowEditModal(null)}
                className="px-4 py-2 bg-hmi-panel hover:bg-hmi-border rounded text-hmi-text"
              >
                Cancel
              </button>
              <button
                onClick={saveSlotConfig}
                disabled={loading}
                className="px-4 py-2 bg-status-info hover:bg-status-info/90 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Historian Tag Modal */}
      {showHistorianModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white p-6 rounded-lg w-full max-w-md">
            <h2 className="text-xl font-semibold text-hmi-text mb-4">
              {showHistorianModal.id ? 'Edit' : 'Add'} Historian Tag
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-hmi-muted mb-1">Tag Name</label>
                <input
                  type="text"
                  value={showHistorianModal.tag_name}
                  onChange={(e) =>
                    setShowHistorianModal({ ...showHistorianModal, tag_name: e.target.value })
                  }
                  placeholder="e.g., TANK1_LEVEL"
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-hmi-muted mb-1">RTU</label>
                  <select
                    value={showHistorianModal.rtu_station}
                    onChange={(e) =>
                      setShowHistorianModal({ ...showHistorianModal, rtu_station: e.target.value })
                    }
                    className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                  >
                    {rtus.map((rtu) => (
                      <option key={rtu.station_name} value={rtu.station_name}>
                        {rtu.station_name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm text-hmi-muted mb-1">Slot</label>
                  <input
                    type="number"
                    min="1"
                    value={showHistorianModal.slot}
                    onChange={(e) =>
                      setShowHistorianModal({ ...showHistorianModal, slot: parseInt(e.target.value) })
                    }
                    className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Unit</label>
                <input
                  type="text"
                  value={showHistorianModal.unit || ''}
                  onChange={(e) =>
                    setShowHistorianModal({ ...showHistorianModal, unit: e.target.value })
                  }
                  placeholder="e.g., pH, degC, ppm"
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-hmi-muted mb-1">Sample Rate (ms)</label>
                  <input
                    type="number"
                    min="100"
                    step="100"
                    value={showHistorianModal.sample_rate_ms}
                    onChange={(e) =>
                      setShowHistorianModal({
                        ...showHistorianModal,
                        sample_rate_ms: parseInt(e.target.value),
                      })
                    }
                    className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                  />
                </div>

                <div>
                  <label className="block text-sm text-hmi-muted mb-1">Deadband</label>
                  <input
                    type="number"
                    step="0.01"
                    value={showHistorianModal.deadband}
                    onChange={(e) =>
                      setShowHistorianModal({
                        ...showHistorianModal,
                        deadband: parseFloat(e.target.value),
                      })
                    }
                    className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-hmi-muted mb-1">Compression Algorithm</label>
                <select
                  value={showHistorianModal.compression}
                  onChange={(e) =>
                    setShowHistorianModal({ ...showHistorianModal, compression: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-white border border-hmi-border rounded text-hmi-text"
                >
                  <option value="none">None (Store All)</option>
                  <option value="deadband">Deadband</option>
                  <option value="swinging_door">Swinging Door</option>
                  <option value="boxcar">Boxcar</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowHistorianModal(null)}
                className="px-4 py-2 bg-hmi-panel hover:bg-hmi-border rounded text-hmi-text"
              >
                Cancel
              </button>
              <button
                onClick={saveHistorianTag}
                disabled={loading}
                className="px-4 py-2 bg-status-info hover:bg-status-info/90 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={tagToDelete !== null}
        onClose={() => setTagToDelete(null)}
        onConfirm={confirmDeleteHistorianTag}
        title="Delete Historian Tag"
        message={`Are you sure you want to delete "${tagToDelete?.tag_name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
      />
    </div>
  );
}
