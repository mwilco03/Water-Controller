'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { getRTUs, getRTUInventory, getSensors } from '@/lib/api';
import type { RTUDevice, RTUInventory, RTUSensor, RTUControl, SensorData } from '@/lib/api';

interface IOTag {
  rtu_station: string;
  slot: number;
  tag: string;
  type: 'sensor' | 'control';
  data_type: string;
  unit: string;
  value: number | null;
  quality: string;
}

export default function IOTagsPage() {
  const [tags, setTags] = useState<IOTag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | 'sensor' | 'control'>('all');
  const [collapsedRTUs, setCollapsedRTUs] = useState<Set<string>>(new Set());

  const fetchAllTags = useCallback(async () => {
    try {
      const rtus = await getRTUs();
      const allTags: IOTag[] = [];

      // Fetch inventory and live sensor values for each RTU in parallel
      const results = await Promise.all(
        rtus.map(async (rtu) => {
          try {
            const [inventory, liveSensors] = await Promise.all([
              getRTUInventory(rtu.station_name),
              getSensors(rtu.station_name).catch(() => []),
            ]);

            // Build live value lookup by sensor name/id
            const liveByName: Record<string, SensorData> = {};
            for (const s of liveSensors) {
              if (s.name) liveByName[s.name] = s;
            }

            const tags: IOTag[] = [];

            // Sensors
            for (const s of inventory.sensors || []) {
              const live = liveByName[s.sensor_id] || liveByName[s.name];
              tags.push({
                rtu_station: rtu.station_name,
                slot: s.register_address,
                tag: s.name || s.sensor_id,
                type: 'sensor',
                data_type: s.data_type || 'float32',
                unit: s.unit || '',
                value: live?.value ?? s.last_value ?? null,
                quality: live?.quality ?? (s.last_quality === 0 ? 'GOOD' : 'NOT_CONNECTED'),
              });
            }

            // Controls
            for (const c of inventory.controls || []) {
              tags.push({
                rtu_station: rtu.station_name,
                slot: c.register_address,
                tag: c.name || c.control_id,
                type: 'control',
                data_type: c.command_type || 'digital',
                unit: '',
                value: c.current_value ?? null,
                quality: c.current_state || 'unknown',
              });
            }

            return tags;
          } catch {
            return [];
          }
        })
      );

      for (const r of results) allTags.push(...r);
      setTags(allTags);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tags');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAllTags();
    const interval = setInterval(fetchAllTags, 5000);
    return () => clearInterval(interval);
  }, [fetchAllTags]);

  const toggleRTU = (station: string) => {
    setCollapsedRTUs((prev) => {
      const next = new Set(prev);
      if (next.has(station)) next.delete(station);
      else next.add(station);
      return next;
    });
  };

  // Filter tags
  const filtered = tags.filter((t) => {
    if (typeFilter !== 'all' && t.type !== typeFilter) return false;
    if (filter) {
      const q = filter.toLowerCase();
      return (
        t.tag.toLowerCase().includes(q) ||
        t.rtu_station.toLowerCase().includes(q) ||
        t.unit.toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Group by RTU
  const grouped = filtered.reduce((acc, tag) => {
    if (!acc[tag.rtu_station]) acc[tag.rtu_station] = [];
    acc[tag.rtu_station].push(tag);
    return acc;
  }, {} as Record<string, IOTag[]>);

  const qualityColor = (q: string) => {
    switch (q) {
      case 'GOOD': case 'good': return 'text-green-400';
      case 'UNCERTAIN': return 'text-yellow-400';
      case 'BAD': return 'text-red-400';
      default: return 'text-gray-500';
    }
  };

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold text-hmi-text mb-6">I/O Tags</h1>
        <div className="animate-pulse space-y-3">
          <div className="h-10 bg-hmi-panel rounded w-full"></div>
          <div className="h-10 bg-hmi-panel rounded w-full"></div>
          <div className="h-10 bg-hmi-panel rounded w-full"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-hmi-text">I/O Tags</h1>
        <span className="text-sm text-hmi-muted">{filtered.length} tags</span>
      </div>

      {error && (
        <div className="p-3 bg-red-900/20 border border-red-600/50 rounded text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-4 items-center">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search tags..."
          className="flex-1 px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text placeholder:text-hmi-muted"
        />
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as 'all' | 'sensor' | 'control')}
          className="px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
        >
          <option value="all">All Types</option>
          <option value="sensor">Sensors</option>
          <option value="control">Controls</option>
        </select>
        <button
          onClick={fetchAllTags}
          className="px-4 py-2 bg-status-info hover:bg-status-info/90 text-white rounded text-sm"
        >
          Refresh
        </button>
      </div>

      {/* Tags grouped by RTU */}
      {Object.entries(grouped).map(([station, rtuTags]) => (
        <div key={station} className="bg-hmi-panel border border-hmi-border rounded-lg overflow-hidden">
          {/* RTU Header */}
          <button
            onClick={() => toggleRTU(station)}
            className="w-full flex items-center justify-between px-4 py-3 bg-hmi-bg/50 hover:bg-hmi-bg border-b border-hmi-border text-left"
          >
            <div className="flex items-center gap-3">
              <span className="text-hmi-muted font-mono text-sm">
                {collapsedRTUs.has(station) ? '[+]' : '[-]'}
              </span>
              <Link
                href={`/rtus/${encodeURIComponent(station)}`}
                className="text-hmi-text font-semibold hover:text-status-info"
                onClick={(e) => e.stopPropagation()}
              >
                {station}
              </Link>
            </div>
            <span className="text-sm text-hmi-muted">{rtuTags.length} tags</span>
          </button>

          {/* Tags Table */}
          {!collapsedRTUs.has(station) && (
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-hmi-border">
                  <th className="px-4 py-2 text-xs font-medium text-hmi-muted">Slot</th>
                  <th className="px-4 py-2 text-xs font-medium text-hmi-muted">Tag</th>
                  <th className="px-4 py-2 text-xs font-medium text-hmi-muted">Type</th>
                  <th className="px-4 py-2 text-xs font-medium text-hmi-muted">Data Type</th>
                  <th className="px-4 py-2 text-xs font-medium text-hmi-muted">Unit</th>
                  <th className="px-4 py-2 text-xs font-medium text-hmi-muted text-right">Value</th>
                  <th className="px-4 py-2 text-xs font-medium text-hmi-muted">Quality</th>
                </tr>
              </thead>
              <tbody>
                {rtuTags.map((tag) => (
                  <tr key={`${tag.rtu_station}-${tag.slot}-${tag.tag}`} className="border-b border-hmi-border/50 hover:bg-hmi-bg/30">
                    <td className="px-4 py-2 text-hmi-muted font-mono text-sm">{tag.slot}</td>
                    <td className="px-4 py-2 text-hmi-text font-medium text-sm">{tag.tag}</td>
                    <td className="px-4 py-2">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        tag.type === 'sensor'
                          ? 'bg-blue-600/20 text-blue-400'
                          : 'bg-orange-600/20 text-orange-400'
                      }`}>
                        {tag.type}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-hmi-muted font-mono text-xs">{tag.data_type}</td>
                    <td className="px-4 py-2 text-hmi-muted text-sm">{tag.unit || '--'}</td>
                    <td className="px-4 py-2 text-right font-mono text-sm text-green-400">
                      {tag.value !== null ? tag.value.toFixed(1) : '--'}
                    </td>
                    <td className={`px-4 py-2 text-xs font-medium ${qualityColor(tag.quality)}`}>
                      {tag.quality}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}

      {Object.keys(grouped).length === 0 && !loading && (
        <div className="bg-hmi-panel border border-hmi-border rounded-lg p-8 text-center">
          <p className="text-hmi-muted">
            {filter || typeFilter !== 'all'
              ? 'No tags match the current filter.'
              : 'No I/O tags found. Add RTUs and refresh their inventory to see tags here.'}
          </p>
        </div>
      )}
    </div>
  );
}
