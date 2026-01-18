'use client';

import { Suspense, useEffect, useState, useRef, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';

const PAGE_TITLE = 'Trends - Water Treatment Controller';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useHMIToast } from '@/components/hmi';
import { exportTrendToCSV, exportTrendToJSON, exportTrendToExcel, TrendExportData } from '@/lib/exportUtils';
import { wsLogger, logger } from '@/lib/logger';

interface HistorianTag {
  tag_id: number;
  rtu_station: string;
  slot: number;
  tag_name: string;
  sample_rate_ms: number;
  deadband: number;
  compression: string;
}

interface TrendSample {
  timestamp: string;
  value: number;
  quality: number;
}

interface TrendData {
  tag_id: number;
  samples: TrendSample[];
}

// Loading fallback for Suspense
function TrendsLoading() {
  return (
    <div className="p-4">
      <div className="animate-pulse">
        <div className="h-6 bg-hmi-panel rounded w-40 mb-4"></div>
        <div className="h-40 bg-hmi-panel rounded mb-3"></div>
        <div className="grid grid-cols-3 gap-3">
          <div className="h-12 bg-hmi-panel rounded"></div>
          <div className="h-12 bg-hmi-panel rounded"></div>
          <div className="h-12 bg-hmi-panel rounded"></div>
        </div>
      </div>
    </div>
  );
}

// Wrapper component with Suspense boundary
export default function TrendsPage() {
  return (
    <Suspense fallback={<TrendsLoading />}>
      <TrendsContent />
    </Suspense>
  );
}

function TrendsContent() {
  const searchParams = useSearchParams();
  const rtuFilter = searchParams.get('rtu');
  const { showMessage } = useHMIToast();

  const [tags, setTags] = useState<HistorianTag[]>([]);
  const [selectedTags, setSelectedTags] = useState<number[]>([]);
  const [trendData, setTrendData] = useState<{ [tagId: number]: TrendSample[] }>({});
  const [timeRange, setTimeRange] = useState<'1h' | '6h' | '24h' | '7d' | '30d'>('1h');
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showExportMenu, setShowExportMenu] = useState(false);

  // Set page title
  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const prepareExportData = useCallback((): TrendExportData[] => {
    return Object.entries(trendData).map(([tagId, samples]) => {
      const tag = tags.find(t => t.tag_id === parseInt(tagId));
      return {
        tagId: parseInt(tagId),
        tagName: tag?.tag_name || `Tag ${tagId}`,
        samples,
      };
    });
  }, [trendData, tags]);

  const handleExport = useCallback((format: 'csv' | 'json' | 'excel') => {
    const data = prepareExportData();
    if (data.length === 0) {
      showMessage('error', 'No data to export. Select tags and fetch data first.');
      setShowExportMenu(false);
      return;
    }

    const filename = `trend_export_${timeRange}_${new Date().toISOString().split('T')[0]}`;

    try {
      switch (format) {
        case 'csv':
          exportTrendToCSV(data, { filename });
          break;
        case 'json':
          exportTrendToJSON(data, { filename });
          break;
        case 'excel':
          exportTrendToExcel(data, { filename });
          break;
      }
      showMessage('success', `Trend data exported as ${format.toUpperCase()}`);
    } catch (error) {
      showMessage('error', `Export failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
    setShowExportMenu(false);
  }, [prepareExportData, timeRange, showMessage]);

  const fetchTags = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/trends/tags');
      if (res.ok) {
        let data = await res.json();
        if (rtuFilter) {
          data = data.filter((t: HistorianTag) => t.rtu_station === rtuFilter);
        }
        setTags(data);
      }
    } catch (error) {
      logger.error('Failed to fetch tags', error);
    }
  }, [rtuFilter]);

  const fetchTrendData = useCallback(async () => {
    if (selectedTags.length === 0) return;

    setLoading(true);
    const now = new Date();
    const ranges: { [key: string]: number } = {
      '1h': 60 * 60 * 1000,
      '6h': 6 * 60 * 60 * 1000,
      '24h': 24 * 60 * 60 * 1000,
      '7d': 7 * 24 * 60 * 60 * 1000,
      '30d': 30 * 24 * 60 * 60 * 1000,
    };

    const startTime = new Date(now.getTime() - ranges[timeRange]);

    // Fetch all tags in parallel for efficiency
    const fetchPromises = selectedTags.map(async (tagId) => {
      try {
        const res = await fetch(
          `/api/v1/trends/${tagId}?` +
            new URLSearchParams({
              start_time: startTime.toISOString(),
              end_time: now.toISOString(),
            })
        );
        if (res.ok) {
          const data = await res.json();
          return { tagId, samples: data.samples || [] };
        }
        return { tagId, samples: [] };
      } catch (error) {
        logger.error(`Failed to fetch trend data for tag ${tagId}`, error);
        return { tagId, samples: [] };
      }
    });

    const results = await Promise.all(fetchPromises);

    const newData: { [tagId: number]: TrendSample[] } = {};
    for (const { tagId, samples } of results) {
      newData[tagId] = samples;
    }

    setTrendData(newData);
    setLoading(false);
  }, [selectedTags, timeRange]);

  // WebSocket for real-time sensor updates
  const { connected, subscribe } = useWebSocket({
    onConnect: () => {
      // When WebSocket connects, we can receive live updates for selected tags
      if (pollIntervalRef.current && autoRefresh) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
        wsLogger.info('WebSocket connected - trend polling disabled');
      }
    },
    onDisconnect: () => {
      // Restart polling when WebSocket disconnects
      if (!pollIntervalRef.current && autoRefresh && selectedTags.length > 0) {
        pollIntervalRef.current = setInterval(fetchTrendData, 5000);
        wsLogger.info('WebSocket disconnected - trend polling enabled');
      }
    },
  });

  // Subscribe to sensor updates for real-time trend data
  useEffect(() => {
    const unsub = subscribe('sensor_update', (_, data) => {
      // Find if this sensor belongs to any selected tag
      const matchingTag = tags.find(
        (t) => t.rtu_station === data.station_name && t.slot === data.slot
      );
      if (matchingTag && selectedTags.includes(matchingTag.tag_id)) {
        // Add the new sample to trend data
        setTrendData((prev) => {
          const tagSamples = prev[matchingTag.tag_id] || [];
          const newSample: TrendSample = {
            timestamp: new Date().toISOString(),
            value: data.value,
            quality: data.quality === 'good' ? 0 : 1,
          };
          return {
            ...prev,
            [matchingTag.tag_id]: [...tagSamples, newSample].slice(-500), // Keep last 500 samples
          };
        });
      }
    });

    return unsub;
  }, [subscribe, tags, selectedTags]);

  useEffect(() => {
    fetchTags();
  }, [fetchTags]);

  useEffect(() => {
    if (selectedTags.length > 0) {
      fetchTrendData();
    }
  }, [selectedTags, timeRange, fetchTrendData]);

  // Auto-refresh with polling fallback
  useEffect(() => {
    if (autoRefresh && selectedTags.length > 0 && !connected) {
      pollIntervalRef.current = setInterval(fetchTrendData, 5000);
      return () => {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      };
    } else if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, [autoRefresh, selectedTags, connected, fetchTrendData]);

  // Re-draw chart when trend data changes
  // Justification: drawChart reads trendData directly when invoked; including it as a
  // dependency would cause infinite re-renders since it's not memoized. The effect
  // correctly triggers on trendData changes and calls the current drawChart function.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    drawChart();
  }, [trendData]);

  const toggleTag = (tagId: number) => {
    setSelectedTags((prev) =>
      prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId]
    );
  };

  const drawChart = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    const padding = { top: 20, right: 60, bottom: 40, left: 60 };

    // Clear canvas - ISA-101 light background
    ctx.fillStyle = '#F5F5F5';
    ctx.fillRect(0, 0, width, height);

    // Get all samples and find min/max
    const allSamples: { time: number; value: number; tagId: number }[] = [];
    Object.entries(trendData).forEach(([tagId, samples]) => {
      samples.forEach((s) => {
        allSamples.push({
          time: new Date(s.timestamp).getTime(),
          value: s.value,
          tagId: parseInt(tagId),
        });
      });
    });

    if (allSamples.length === 0) {
      ctx.fillStyle = '#212121';
      ctx.textAlign = 'center';
      ctx.font = '14px sans-serif';
      ctx.fillText('No data to display', width / 2, height / 2);
      return;
    }

    const minTime = Math.min(...allSamples.map((s) => s.time));
    const maxTime = Math.max(...allSamples.map((s) => s.time));
    const minValue = Math.min(...allSamples.map((s) => s.value));
    const maxValue = Math.max(...allSamples.map((s) => s.value));
    const valueRange = maxValue - minValue || 1;

    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Draw grid - ISA-101 light grid lines
    ctx.strokeStyle = '#E0E0E0';
    ctx.lineWidth = 1;

    // Horizontal grid lines
    for (let i = 0; i <= 5; i++) {
      const y = padding.top + (chartHeight / 5) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();

      // Y-axis labels - ISA-101 dark text
      const value = maxValue - (valueRange / 5) * i;
      ctx.fillStyle = '#212121';
      ctx.textAlign = 'right';
      ctx.font = '12px sans-serif';
      ctx.fillText(value.toFixed(2), padding.left - 10, y + 4);
    }

    // Draw time axis
    const timeFormat = new Intl.DateTimeFormat('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
    for (let i = 0; i <= 4; i++) {
      const x = padding.left + (chartWidth / 4) * i;
      const time = new Date(minTime + ((maxTime - minTime) / 4) * i);
      ctx.fillStyle = '#212121';
      ctx.textAlign = 'center';
      ctx.fillText(timeFormat.format(time), x, height - padding.bottom + 20);
    }

    // Colors for different tags
    const colors = ['#4ade80', '#60a5fa', '#f472b6', '#facc15', '#a78bfa', '#fb923c'];

    // Draw lines for each tag
    Object.entries(trendData).forEach(([tagId, samples], index) => {
      if (samples.length === 0) return;

      ctx.strokeStyle = colors[index % colors.length];
      ctx.lineWidth = 2;
      ctx.beginPath();

      samples.forEach((sample, i) => {
        const x = padding.left + ((new Date(sample.timestamp).getTime() - minTime) / (maxTime - minTime)) * chartWidth;
        const y = padding.top + chartHeight - ((sample.value - minValue) / valueRange) * chartHeight;

        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      });

      ctx.stroke();
    });

    // Draw legend - ISA-101 dark text
    Object.entries(trendData).forEach(([tagId, _], index) => {
      const tag = tags.find((t) => t.tag_id === parseInt(tagId));
      if (!tag) return;

      const x = padding.left + index * 150;
      const y = 10;

      ctx.fillStyle = colors[index % colors.length];
      ctx.fillRect(x, y, 20, 10);

      ctx.fillStyle = '#212121';
      ctx.textAlign = 'left';
      ctx.font = '12px sans-serif';
      ctx.fillText(tag.tag_name, x + 25, y + 9);
    });
  };

  const groupedTags = tags.reduce((acc, tag) => {
    if (!acc[tag.rtu_station]) {
      acc[tag.rtu_station] = [];
    }
    acc[tag.rtu_station].push(tag);
    return acc;
  }, {} as { [key: string]: HistorianTag[] });

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-hmi-text">Historical Trends</h1>
        <div className="flex items-center space-x-4">
          <label className="flex items-center text-hmi-muted">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="mr-2"
            />
            Auto-refresh
          </label>
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value as any)}
            className="px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text"
          >
            <option value="1h">Last 1 Hour</option>
            <option value="6h">Last 6 Hours</option>
            <option value="24h">Last 24 Hours</option>
            <option value="7d">Last 7 Days</option>
            <option value="30d">Last 30 Days</option>
          </select>
          <button
            onClick={fetchTrendData}
            disabled={loading || selectedTags.length === 0}
            className="px-4 py-2 bg-status-info hover:bg-status-info rounded text-white disabled:opacity-50"
          >
            {loading ? 'Loading...' : 'Refresh'}
          </button>

          {/* Export Dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              disabled={Object.keys(trendData).length === 0}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span>&#8595;</span>
              Export
              <span>&#9662;</span>
            </button>

            {showExportMenu && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setShowExportMenu(false)}
                />
                <div className="absolute right-0 mt-2 w-48 bg-hmi-panel rounded-lg shadow-xl border border-hmi-border py-2 z-50">
                  <button
                    onClick={() => handleExport('csv')}
                    className="w-full px-4 py-2 text-left text-sm text-hmi-muted hover:text-hmi-text hover:bg-hmi-bg flex items-center gap-3"
                  >
                    <span className="text-green-400 font-mono text-xs">[CSV]</span>
                    Export as CSV
                  </button>
                  <button
                    onClick={() => handleExport('excel')}
                    className="w-full px-4 py-2 text-left text-sm text-hmi-muted hover:text-hmi-text hover:bg-hmi-bg flex items-center gap-3"
                  >
                    <span className="text-green-500 font-mono text-xs">[XLS]</span>
                    Export as Excel
                  </button>
                  <button
                    onClick={() => handleExport('json')}
                    className="w-full px-4 py-2 text-left text-sm text-hmi-muted hover:text-hmi-text hover:bg-hmi-bg flex items-center gap-3"
                  >
                    <span className="text-blue-400 font-mono text-xs">{'{}'}</span>
                    Export as JSON
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Tag Selection */}
        <div className="lg:col-span-1 hmi-card p-4 max-h-[600px] overflow-y-auto">
          <h2 className="text-lg font-semibold text-hmi-text mb-4">Available Tags</h2>

          {Object.entries(groupedTags).map(([rtuStation, rtuTags]) => (
            <div key={rtuStation} className="mb-4">
              <h3 className="text-sm font-medium text-hmi-muted mb-2">{rtuStation}</h3>
              <div className="space-y-1">
                {rtuTags.map((tag) => (
                  <label
                    key={tag.tag_id}
                    className="flex items-center p-2 rounded hover:bg-hmi-panel cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selectedTags.includes(tag.tag_id)}
                      onChange={() => toggleTag(tag.tag_id)}
                      className="mr-3"
                    />
                    <div>
                      <div className="text-hmi-text text-sm">{tag.tag_name}</div>
                      <div className="text-hmi-muted text-xs">Slot {tag.slot}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          ))}

          {tags.length === 0 && (
            <p className="text-hmi-muted text-sm">No historian tags configured</p>
          )}
        </div>

        {/* Chart */}
        <div className="lg:col-span-3 hmi-card p-4">
          <h2 className="text-lg font-semibold text-hmi-text mb-4">Trend Chart</h2>
          <canvas
            ref={canvasRef}
            width={800}
            height={400}
            className="w-full rounded bg-hmi-bg"
          />

          {selectedTags.length === 0 && (
            <div className="text-center text-hmi-muted mt-4">
              Select one or more tags from the left panel to view trends
            </div>
          )}
        </div>
      </div>

      {/* Data Table */}
      {selectedTags.length > 0 && Object.keys(trendData).length > 0 && (
        <div className="hmi-card p-4">
          <h2 className="text-lg font-semibold text-hmi-text mb-4">Recent Values</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-hmi-border">
                  <th className="pb-2 text-hmi-muted">Tag</th>
                  <th className="pb-2 text-hmi-muted">Current Value</th>
                  <th className="pb-2 text-hmi-muted">Min</th>
                  <th className="pb-2 text-hmi-muted">Max</th>
                  <th className="pb-2 text-hmi-muted">Average</th>
                  <th className="pb-2 text-hmi-muted">Samples</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(trendData).map(([tagId, samples]) => {
                  const tag = tags.find((t) => t.tag_id === parseInt(tagId));
                  if (!tag || samples.length === 0) return null;

                  const values = samples.map((s) => s.value);
                  const min = Math.min(...values);
                  const max = Math.max(...values);
                  const avg = values.reduce((a, b) => a + b, 0) / values.length;
                  const current = samples[samples.length - 1]?.value;

                  return (
                    <tr key={tagId} className="border-b border-hmi-border">
                      <td className="py-2 text-hmi-text">{tag.tag_name}</td>
                      <td className="py-2 text-green-400 font-mono">{current?.toFixed(3)}</td>
                      <td className="py-2 text-hmi-muted font-mono">{min.toFixed(3)}</td>
                      <td className="py-2 text-hmi-muted font-mono">{max.toFixed(3)}</td>
                      <td className="py-2 text-hmi-muted font-mono">{avg.toFixed(3)}</td>
                      <td className="py-2 text-hmi-muted">{samples.length}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
