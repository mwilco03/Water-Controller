'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { controlLogger } from '@/lib/logger';

interface CoupledAction {
  coupling_id: number;
  name: string;
  description: string;
  source_type: 'pid' | 'interlock' | 'control';
  source_id: number;
  source_name: string;
  target_type: 'control' | 'pid' | 'alarm';
  target_id: number;
  target_name: string;
  target_rtu: string;
  target_slot: number;
  coupling_type: 'enable' | 'disable' | 'limit' | 'cascade';
  active: boolean;
  condition?: string;
}

interface Props {
  rtuStation?: string;
  showAll?: boolean;
}

const sourceTypeLabels = {
  pid: 'PID Loop',
  interlock: 'Interlock',
  control: 'Control',
};

const targetTypeLabels = {
  control: 'Control',
  pid: 'PID Loop',
  alarm: 'Alarm',
};

// Coupling type labels
const couplingTypeLabels: Record<string, string> = {
  enable: 'ENABLES',
  disable: 'DISABLES',
  limit: 'LIMITS',
  cascade: 'CASCADES',
};

export default function CoupledActionsPanel({ rtuStation }: Props) {
  const [couplings, setCouplings] = useState<CoupledAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<number[]>([]);
  const [filterActive, setFilterActive] = useState<'all' | 'active' | 'inactive'>('all');
  const isMountedRef = useRef(true);

  const fetchCouplings = useCallback(async (signal?: AbortSignal) => {
    try {
      const url = rtuStation
        ? `/api/v1/control/couplings?rtu=${encodeURIComponent(rtuStation)}`
        : '/api/v1/control/couplings';

      const res = await fetch(url, { signal });
      if (!isMountedRef.current) return;

      if (res.ok) {
        const data = await res.json();
        setCouplings(data.couplings || []);
        setError(null);
      } else if (res.status === 404) {
        setCouplings([]);
        setError(null);
      } else {
        setError('Failed to load coupled actions');
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return;
      if (!isMountedRef.current) return;
      controlLogger.error('Error fetching couplings', err);
      setError('Failed to load coupled actions');
      setCouplings([]);
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, [rtuStation]);

  useEffect(() => {
    isMountedRef.current = true;
    const controller = new AbortController();

    fetchCouplings(controller.signal);
    const interval = setInterval(() => {
      fetchCouplings(controller.signal);
    }, 5000);

    return () => {
      isMountedRef.current = false;
      controller.abort();
      clearInterval(interval);
    };
  }, [fetchCouplings]);

  const toggleExpanded = (id: number) => {
    setExpandedIds(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const filteredCouplings = couplings.filter(c => {
    if (filterActive === 'active') return c.active;
    if (filterActive === 'inactive') return !c.active;
    return true;
  });

  // Group by source
  const groupedCouplings = filteredCouplings.reduce((acc, coupling) => {
    const key = `${coupling.source_type}-${coupling.source_id}`;
    if (!acc[key]) {
      acc[key] = {
        sourceType: coupling.source_type,
        sourceId: coupling.source_id,
        sourceName: coupling.source_name,
        couplings: [],
      };
    }
    acc[key].couplings.push(coupling);
    return acc;
  }, {} as Record<string, { sourceType: string; sourceId: number; sourceName: string; couplings: CoupledAction[] }>);

  if (loading) {
    return (
      <div className="space-y-3">
        <h3 className="text-lg font-semibold text-hmi-text">Coupled Actions</h3>
        <div className="flex items-center gap-3 p-4 bg-hmi-bg rounded-lg border border-hmi-border">
          <div className="animate-spin h-5 w-5 border-2 border-status-info border-t-transparent rounded-full" />
          <span className="text-hmi-muted">Loading...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-hmi-text">Coupled Actions</h3>
          <button
            onClick={() => fetchCouplings()}
            className="text-sm text-status-info hover:underline"
          >
            Retry
          </button>
        </div>
        <div className="p-4 bg-status-alarm-light rounded-lg border border-status-alarm/30">
          <p className="text-status-alarm">{error}</p>
        </div>
      </div>
    );
  }

  const activeCount = couplings.filter(c => c.active).length;
  const disablingCount = couplings.filter(c => c.coupling_type === 'disable').length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-lg font-semibold text-hmi-text">Coupled Actions</h3>
        <div className="flex items-center gap-3">
          <select
            value={filterActive}
            onChange={(e) => setFilterActive(e.target.value as typeof filterActive)}
            className="text-sm bg-hmi-panel border border-hmi-border rounded px-2 py-1.5 text-hmi-text"
          >
            <option value="all">All ({couplings.length})</option>
            <option value="active">Active ({activeCount})</option>
            <option value="inactive">Inactive ({couplings.length - activeCount})</option>
          </select>
          <button
            onClick={() => fetchCouplings()}
            className="text-sm text-status-info hover:underline"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Summary - compact */}
      {couplings.length > 0 && (
        <div className="flex gap-4 text-sm">
          <span className="text-hmi-muted">
            <span className="font-semibold text-status-ok">{activeCount}</span> active
          </span>
          {disablingCount > 0 && (
            <span className="text-hmi-muted">
              <span className="font-semibold text-status-alarm">{disablingCount}</span> disabling
            </span>
          )}
        </div>
      )}

      {/* Coupling Groups */}
      {Object.keys(groupedCouplings).length === 0 ? (
        <div className="p-6 bg-hmi-bg rounded-lg border border-hmi-border text-center">
          <p className="text-hmi-muted">No coupled actions configured</p>
        </div>
      ) : (
        <div className="space-y-2">
          {Object.values(groupedCouplings).map((group) => (
            <div
              key={`${group.sourceType}-${group.sourceId}`}
              className="bg-hmi-panel rounded-lg border border-hmi-border overflow-hidden"
            >
              {/* Group Header */}
              <button
                onClick={() => toggleExpanded(group.sourceId)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-hmi-bg transition-colors text-left"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-status-info-light flex items-center justify-center">
                    <SourceIcon type={group.sourceType} />
                  </div>
                  <div>
                    <div className="text-hmi-text font-medium">{group.sourceName}</div>
                    <div className="text-xs text-hmi-muted">
                      {sourceTypeLabels[group.sourceType as keyof typeof sourceTypeLabels]} · {group.couplings.length} coupling{group.couplings.length !== 1 ? 's' : ''}
                    </div>
                  </div>
                </div>
                <span className={`text-hmi-muted transition-transform ${expandedIds.includes(group.sourceId) ? 'rotate-180 inline-block' : ''}`}>
                  {expandedIds.includes(group.sourceId) ? '[^]' : '[v]'}
                </span>
              </button>

              {/* Expanded Couplings */}
              {expandedIds.includes(group.sourceId) && (
                <div className="px-4 pb-3 space-y-2 border-t border-hmi-border pt-3">
                  {group.couplings.map((coupling) => (
                    <CouplingRow key={coupling.coupling_id} coupling={coupling} />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SourceIcon({ type }: { type: string }) {
  const className = "text-xs font-bold text-status-info";
  if (type === 'pid') {
    return <span className={className}>[PID]</span>;
  }
  if (type === 'interlock') {
    return <span className={className}>[ILK]</span>;
  }
  return <span className={className}>[CTL]</span>;
}

function CouplingRow({ coupling }: { coupling: CoupledAction }) {
  const typeColors: Record<string, { badge: string; dot: string }> = {
    enable: { badge: 'bg-status-ok-light text-status-ok-dark', dot: 'bg-status-ok' },
    disable: { badge: 'bg-status-alarm-light text-status-alarm-dark', dot: 'bg-status-alarm' },
    limit: { badge: 'bg-status-warning-light text-status-warning-dark', dot: 'bg-status-warning' },
    cascade: { badge: 'bg-status-info-light text-status-info-dark', dot: 'bg-status-info' },
  };

  const colors = typeColors[coupling.coupling_type] || typeColors.enable;

  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg ${coupling.active ? 'bg-hmi-bg' : 'bg-hmi-panel'} border border-hmi-border`}>
      {/* Type badge */}
      <span className={`text-xs font-medium px-2 py-0.5 rounded ${colors.badge}`}>
        {couplingTypeLabels[coupling.coupling_type]}
      </span>

      {/* Target info */}
      <div className="flex-1 min-w-0">
        <div className="text-sm text-hmi-text truncate">{coupling.target_name}</div>
        <div className="text-xs text-hmi-muted">
          {targetTypeLabels[coupling.target_type]} · {coupling.target_rtu}
        </div>
        {coupling.condition && (
          <div className="text-xs text-hmi-muted mt-0.5">
            When: {coupling.condition}
          </div>
        )}
      </div>

      {/* Status dot */}
      <div
        className={`w-2.5 h-2.5 rounded-full ${coupling.active ? colors.dot : 'bg-hmi-equipment'}`}
        title={coupling.active ? 'Active' : 'Inactive'}
      />
    </div>
  );
}
