'use client';

/**
 * DataTableView - Tabular display for SCADA sensor/control data
 *
 * Design principles:
 * - Compact, scannable rows for monitoring
 * - Group by RTU with collapsible sections
 * - Inline sparklines for trend-at-a-glance
 * - Sortable columns
 * - No horizontal scroll on mobile (responsive columns)
 */

import { useState, useMemo } from 'react';
import Link from 'next/link';
import { Sparkline } from './Sparkline';

export interface DataPoint {
  id: string | number;
  rtuStation: string;
  name: string;
  type: string;
  value: number | null;
  unit: string;
  quality: 'good' | 'uncertain' | 'bad' | 'stale';
  timestamp: string;
  /** Historical data for sparkline */
  history?: Array<{ timestamp: string; value: number }>;
  /** Thresholds for alarming */
  highLimit?: number;
  lowLimit?: number;
  /** Is this point in alarm? */
  inAlarm?: boolean;
  /** For controls: is it in manual mode? */
  isManual?: boolean;
}

interface DataTableViewProps {
  data: DataPoint[];
  /** Group rows by RTU station */
  groupByRtu?: boolean;
  /** Show sparklines (requires history data) */
  showSparklines?: boolean;
  /** Columns to show on mobile (subset) */
  mobileColumns?: ('value' | 'trend' | 'quality')[];
  /** Click handler for row */
  onRowClick?: (point: DataPoint) => void;
  /** Enable sorting */
  sortable?: boolean;
  /** Compact mode for dense display */
  compact?: boolean;
}

type SortKey = 'name' | 'rtuStation' | 'value' | 'type' | 'timestamp';
type SortDir = 'asc' | 'desc';

export function DataTableView({
  data,
  groupByRtu = true,
  showSparklines = true,
  mobileColumns = ['value', 'trend'],
  onRowClick,
  sortable = true,
  compact = false,
}: DataTableViewProps) {
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  // Sort data
  const sortedData = useMemo(() => {
    if (!sortable) return data;

    return [...data].sort((a, b) => {
      let aVal: string | number | null;
      let bVal: string | number | null;

      switch (sortKey) {
        case 'name':
          aVal = a.name.toLowerCase();
          bVal = b.name.toLowerCase();
          break;
        case 'rtuStation':
          aVal = a.rtuStation.toLowerCase();
          bVal = b.rtuStation.toLowerCase();
          break;
        case 'value':
          aVal = a.value ?? -Infinity;
          bVal = b.value ?? -Infinity;
          break;
        case 'type':
          aVal = a.type.toLowerCase();
          bVal = b.type.toLowerCase();
          break;
        case 'timestamp':
          aVal = a.timestamp;
          bVal = b.timestamp;
          break;
        default:
          return 0;
      }

      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [data, sortKey, sortDir, sortable]);

  // Group by RTU
  const groupedData = useMemo(() => {
    if (!groupByRtu) {
      return { 'All Points': sortedData };
    }

    const groups: Record<string, DataPoint[]> = {};
    for (const point of sortedData) {
      if (!groups[point.rtuStation]) {
        groups[point.rtuStation] = [];
      }
      groups[point.rtuStation].push(point);
    }
    return groups;
  }, [sortedData, groupByRtu]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const toggleGroup = (group: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev);
      if (next.has(group)) {
        next.delete(group);
      } else {
        next.add(group);
      }
      return next;
    });
  };

  const SortHeader = ({ label, sortKeyName }: { label: string; sortKeyName: SortKey }) => (
    <button
      onClick={() => handleSort(sortKeyName)}
      className="flex items-center gap-1 hover:text-hmi-text transition-colors"
    >
      {label}
      {sortable && sortKey === sortKeyName && (
        <span className="text-xs">{sortDir === 'asc' ? '▲' : '▼'}</span>
      )}
    </button>
  );

  const getQualityIndicator = (quality: DataPoint['quality']) => {
    switch (quality) {
      case 'good':
        return null;
      case 'uncertain':
        return <span className="text-status-warning" title="Uncertain quality">?</span>;
      case 'bad':
        return <span className="text-status-alarm" title="Bad quality">✕</span>;
      case 'stale':
        return <span className="text-hmi-muted" title="Stale data">○</span>;
    }
  };

  const formatValue = (value: number | null, unit: string) => {
    if (value === null) return '--';
    return `${value.toFixed(1)} ${unit}`;
  };

  const rowPadding = compact ? 'py-1.5 px-2' : 'py-2 px-3';
  const fontSize = compact ? 'text-xs' : 'text-sm';

  if (data.length === 0) {
    return (
      <div className="hmi-card p-6 text-center">
        <span className="text-2xl text-hmi-muted mb-2 block">📊</span>
        <p className="text-hmi-muted">No data points to display</p>
      </div>
    );
  }

  return (
    <div className="hmi-card overflow-hidden">
      {/* Desktop Table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className={`border-b border-hmi-border bg-hmi-bg ${fontSize} text-hmi-muted font-medium`}>
              {!groupByRtu && (
                <th className={`${rowPadding} text-left`}>
                  <SortHeader label="RTU" sortKeyName="rtuStation" />
                </th>
              )}
              <th className={`${rowPadding} text-left`}>
                <SortHeader label="Name" sortKeyName="name" />
              </th>
              <th className={`${rowPadding} text-left`}>
                <SortHeader label="Type" sortKeyName="type" />
              </th>
              <th className={`${rowPadding} text-right`}>
                <SortHeader label="Value" sortKeyName="value" />
              </th>
              {showSparklines && (
                <th className={`${rowPadding} text-center`}>Trend</th>
              )}
              <th className={`${rowPadding} text-center`}>Status</th>
              <th className={`${rowPadding} text-right`}>
                <SortHeader label="Updated" sortKeyName="timestamp" />
              </th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(groupedData).map(([groupName, points]) => (
              <GroupedRows
                key={groupName}
                groupName={groupName}
                points={points}
                showGroup={groupByRtu}
                isCollapsed={collapsedGroups.has(groupName)}
                onToggle={() => toggleGroup(groupName)}
                showSparklines={showSparklines}
                onRowClick={onRowClick}
                rowPadding={rowPadding}
                fontSize={fontSize}
                formatValue={formatValue}
                getQualityIndicator={getQualityIndicator}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card List */}
      <div className="md:hidden">
        {Object.entries(groupedData).map(([groupName, points]) => (
          <div key={groupName}>
            {groupByRtu && (
              <button
                onClick={() => toggleGroup(groupName)}
                className="w-full flex items-center justify-between px-3 py-2 bg-hmi-bg border-b border-hmi-border"
              >
                <span className="font-medium text-hmi-text">{groupName}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-hmi-muted">{points.length} points</span>
                  <span className="text-hmi-muted">{collapsedGroups.has(groupName) ? '▶' : '▼'}</span>
                </div>
              </button>
            )}
            {!collapsedGroups.has(groupName) && (
              <div className="divide-y divide-hmi-border">
                {points.map((point) => (
                  <MobileRow
                    key={point.id}
                    point={point}
                    showSparklines={showSparklines}
                    mobileColumns={mobileColumns}
                    onRowClick={onRowClick}
                    formatValue={formatValue}
                    getQualityIndicator={getQualityIndicator}
                  />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// Desktop grouped rows
function GroupedRows({
  groupName,
  points,
  showGroup,
  isCollapsed,
  onToggle,
  showSparklines,
  onRowClick,
  rowPadding,
  fontSize,
  formatValue,
  getQualityIndicator,
}: {
  groupName: string;
  points: DataPoint[];
  showGroup: boolean;
  isCollapsed: boolean;
  onToggle: () => void;
  showSparklines: boolean;
  onRowClick?: (point: DataPoint) => void;
  rowPadding: string;
  fontSize: string;
  formatValue: (value: number | null, unit: string) => string;
  getQualityIndicator: (quality: DataPoint['quality']) => React.ReactNode;
}) {
  return (
    <>
      {showGroup && (
        <tr className="bg-hmi-bg/50">
          <td
            colSpan={showSparklines ? 6 : 5}
            className={`${rowPadding} font-medium text-hmi-text cursor-pointer hover:bg-hmi-bg`}
            onClick={onToggle}
          >
            <div className="flex items-center gap-2">
              <span className="text-xs text-hmi-muted">{isCollapsed ? '▶' : '▼'}</span>
              <span>📡 {groupName}</span>
              <span className="text-xs text-hmi-muted">({points.length})</span>
              {points.some(p => p.inAlarm) && (
                <span className="text-xs px-1.5 py-0.5 bg-status-alarm/10 text-status-alarm rounded">
                  ⚠️ {points.filter(p => p.inAlarm).length} alarm
                </span>
              )}
            </div>
          </td>
        </tr>
      )}
      {!isCollapsed && points.map((point) => (
        <tr
          key={point.id}
          className={`
            border-b border-hmi-border/50 ${fontSize}
            ${point.inAlarm ? 'bg-status-alarm/5' : 'hover:bg-hmi-bg/50'}
            ${onRowClick ? 'cursor-pointer' : ''}
          `}
          onClick={() => onRowClick?.(point)}
        >
          <td className={`${rowPadding} text-hmi-text`}>
            <div className="flex items-center gap-2">
              {point.isManual && (
                <span className="text-xs px-1 py-0.5 bg-orange-500/20 text-orange-400 rounded" title="Manual mode">
                  🔧
                </span>
              )}
              <span className="truncate max-w-[200px]" title={point.name}>{point.name}</span>
            </div>
          </td>
          <td className={`${rowPadding} text-hmi-muted`}>
            <TypeBadge type={point.type} />
          </td>
          <td className={`${rowPadding} text-right font-mono ${point.inAlarm ? 'text-status-alarm font-bold' : 'text-hmi-text'}`}>
            {formatValue(point.value, point.unit)}
          </td>
          {showSparklines && (
            <td className={`${rowPadding} text-center`}>
              {point.history && point.history.length > 1 ? (
                <Sparkline
                  data={point.history}
                  width={60}
                  height={16}
                  highThreshold={point.highLimit}
                  lowThreshold={point.lowLimit}
                />
              ) : (
                <span className="text-hmi-muted text-xs">--</span>
              )}
            </td>
          )}
          <td className={`${rowPadding} text-center`}>
            <div className="flex items-center justify-center gap-1">
              {getQualityIndicator(point.quality)}
              {point.inAlarm && <span className="text-status-alarm">⚠</span>}
              {!point.inAlarm && point.quality === 'good' && <span className="text-status-ok">✓</span>}
            </div>
          </td>
          <td className={`${rowPadding} text-right text-hmi-muted font-mono`}>
            {new Date(point.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </td>
        </tr>
      ))}
    </>
  );
}

// Mobile row
function MobileRow({
  point,
  showSparklines,
  mobileColumns,
  onRowClick,
  formatValue,
  getQualityIndicator,
}: {
  point: DataPoint;
  showSparklines: boolean;
  mobileColumns: ('value' | 'trend' | 'quality')[];
  onRowClick?: (point: DataPoint) => void;
  formatValue: (value: number | null, unit: string) => string;
  getQualityIndicator: (quality: DataPoint['quality']) => React.ReactNode;
}) {
  return (
    <div
      className={`px-3 py-2 ${onRowClick ? 'cursor-pointer active:bg-hmi-bg' : ''} ${point.inAlarm ? 'bg-status-alarm/5' : ''}`}
      onClick={() => onRowClick?.(point)}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <TypeBadge type={point.type} />
          <span className="text-sm text-hmi-text truncate">{point.name}</span>
          {point.isManual && (
            <span className="text-xs px-1 py-0.5 bg-orange-500/20 text-orange-400 rounded">🔧</span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {mobileColumns.includes('trend') && showSparklines && point.history && point.history.length > 1 && (
            <Sparkline
              data={point.history}
              width={50}
              height={14}
              showTrend={true}
              highThreshold={point.highLimit}
              lowThreshold={point.lowLimit}
            />
          )}
          {mobileColumns.includes('value') && (
            <span className={`font-mono text-sm ${point.inAlarm ? 'text-status-alarm font-bold' : 'text-hmi-text'}`}>
              {formatValue(point.value, point.unit)}
            </span>
          )}
          {mobileColumns.includes('quality') && (
            <span className="text-sm">{getQualityIndicator(point.quality)}</span>
          )}
          {point.inAlarm && <span className="text-status-alarm">⚠</span>}
        </div>
      </div>
    </div>
  );
}

// Type badge component
function TypeBadge({ type }: { type: string }) {
  const badges: Record<string, { label: string; color: string }> = {
    temperature: { label: 'T', color: 'text-orange-400 bg-orange-400/10' },
    level: { label: 'L', color: 'text-blue-400 bg-blue-400/10' },
    pressure: { label: 'P', color: 'text-purple-400 bg-purple-400/10' },
    flow: { label: 'F', color: 'text-cyan-400 bg-cyan-400/10' },
    ph: { label: 'pH', color: 'text-green-400 bg-green-400/10' },
    turbidity: { label: 'Tu', color: 'text-yellow-400 bg-yellow-400/10' },
    chlorine: { label: 'Cl', color: 'text-lime-400 bg-lime-400/10' },
    pump: { label: 'P', color: 'text-emerald-400 bg-emerald-400/10' },
    valve: { label: 'V', color: 'text-sky-400 bg-sky-400/10' },
    motor: { label: 'M', color: 'text-indigo-400 bg-indigo-400/10' },
  };

  const badge = badges[type.toLowerCase()] || { label: type.charAt(0).toUpperCase(), color: 'text-gray-400 bg-gray-400/10' };

  return (
    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${badge.color}`}>
      {badge.label}
    </span>
  );
}

export default DataTableView;
