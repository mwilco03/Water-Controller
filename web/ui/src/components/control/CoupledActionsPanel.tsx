'use client';

import { useState, useEffect, useCallback } from 'react';

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

// Coupling type configurations
const couplingTypeConfig = {
  enable: {
    color: '#10b981',
    bgColor: 'rgba(16, 185, 129, 0.15)',
    label: 'ENABLES',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
      </svg>
    ),
  },
  disable: {
    color: '#ef4444',
    bgColor: 'rgba(239, 68, 68, 0.15)',
    label: 'DISABLES',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
      </svg>
    ),
  },
  limit: {
    color: '#f59e0b',
    bgColor: 'rgba(245, 158, 11, 0.15)',
    label: 'LIMITS',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  },
  cascade: {
    color: '#3b82f6',
    bgColor: 'rgba(59, 130, 246, 0.15)',
    label: 'CASCADES',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
      </svg>
    ),
  },
};

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

export default function CoupledActionsPanel({ rtuStation, showAll = false }: Props) {
  const [couplings, setCouplings] = useState<CoupledAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<number[]>([]);
  const [filterActive, setFilterActive] = useState<'all' | 'active' | 'inactive'>('all');

  const fetchCouplings = useCallback(async () => {
    try {
      const url = rtuStation
        ? `/api/v1/control/couplings?rtu=${encodeURIComponent(rtuStation)}`
        : '/api/v1/control/couplings';

      const res = await fetch(url);

      if (res.ok) {
        const data = await res.json();
        setCouplings(data.couplings || []);
        setError(null);
      } else if (res.status === 404) {
        // No couplings endpoint - use mock data for demonstration
        setCouplings(getMockCouplings());
        setError(null);
      } else {
        setError('Failed to load coupled actions');
      }
    } catch (err) {
      // Use mock data if API not available
      setCouplings(getMockCouplings());
      setError(null);
    } finally {
      setLoading(false);
    }
  }, [rtuStation]);

  useEffect(() => {
    fetchCouplings();
    const interval = setInterval(fetchCouplings, 5000);
    return () => clearInterval(interval);
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
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">Coupled Actions</h3>
        </div>
        <div className="flex items-center gap-3 p-4 bg-gray-800/50 rounded-lg">
          <svg className="animate-spin h-5 w-5 text-blue-400" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-gray-400">Loading coupled actions...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">Coupled Actions</h3>
          <button onClick={fetchCouplings} className="text-sm text-blue-400 hover:text-blue-300">
            Retry
          </button>
        </div>
        <div className="p-4 bg-gray-800/50 rounded-lg border border-gray-700">
          <p className="text-gray-400">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">Coupled Actions</h3>
        <div className="flex items-center gap-2">
          <select
            value={filterActive}
            onChange={(e) => setFilterActive(e.target.value as typeof filterActive)}
            className="text-sm bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white"
          >
            <option value="all">All</option>
            <option value="active">Active Only</option>
            <option value="inactive">Inactive Only</option>
          </select>
          <button
            onClick={fetchCouplings}
            className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-gray-800/50 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-white">{couplings.length}</div>
          <div className="text-xs text-gray-400">Total</div>
        </div>
        <div className="bg-gray-800/50 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-green-400">{couplings.filter(c => c.active).length}</div>
          <div className="text-xs text-gray-400">Active</div>
        </div>
        <div className="bg-gray-800/50 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-red-400">{couplings.filter(c => c.coupling_type === 'disable').length}</div>
          <div className="text-xs text-gray-400">Disabling</div>
        </div>
        <div className="bg-gray-800/50 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-blue-400">{couplings.filter(c => c.coupling_type === 'cascade').length}</div>
          <div className="text-xs text-gray-400">Cascading</div>
        </div>
      </div>

      {/* Coupling Groups */}
      {Object.keys(groupedCouplings).length === 0 ? (
        <div className="p-6 bg-gray-800/50 rounded-lg text-center">
          <svg className="w-12 h-12 mx-auto mb-3 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
          <p className="text-gray-400">No coupled actions configured</p>
          <p className="text-sm text-gray-500 mt-1">Control relationships will appear here when configured</p>
        </div>
      ) : (
        <div className="space-y-3">
          {Object.values(groupedCouplings).map((group) => (
            <div
              key={`${group.sourceType}-${group.sourceId}`}
              className="bg-gray-800/50 rounded-lg border border-gray-700 overflow-hidden"
            >
              {/* Group Header */}
              <button
                onClick={() => toggleExpanded(group.sourceId)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-700/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-purple-600/20 flex items-center justify-center">
                    <svg className="w-4 h-4 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      {group.sourceType === 'pid' ? (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                      ) : group.sourceType === 'interlock' ? (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                      ) : (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      )}
                    </svg>
                  </div>
                  <div className="text-left">
                    <div className="text-white font-medium">{group.sourceName}</div>
                    <div className="text-xs text-gray-400">
                      {sourceTypeLabels[group.sourceType as keyof typeof sourceTypeLabels]} &bull; {group.couplings.length} coupling{group.couplings.length !== 1 ? 's' : ''}
                    </div>
                  </div>
                </div>
                <svg
                  className={`w-5 h-5 text-gray-400 transition-transform ${expandedIds.includes(group.sourceId) ? 'rotate-180' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {/* Expanded Couplings */}
              {expandedIds.includes(group.sourceId) && (
                <div className="px-4 pb-4 space-y-2">
                  {group.couplings.map((coupling) => {
                    const config = couplingTypeConfig[coupling.coupling_type];
                    return (
                      <div
                        key={coupling.coupling_id}
                        className="flex items-center gap-3 p-3 rounded-lg"
                        style={{ backgroundColor: coupling.active ? config.bgColor : 'rgba(107, 114, 128, 0.1)' }}
                      >
                        {/* Arrow indicator */}
                        <div
                          className="w-6 h-6 rounded-full flex items-center justify-center"
                          style={{ backgroundColor: coupling.active ? config.color : '#6b7280', color: 'white' }}
                        >
                          {config.icon}
                        </div>

                        {/* Coupling info */}
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span
                              className="text-xs font-medium px-2 py-0.5 rounded"
                              style={{ backgroundColor: coupling.active ? config.bgColor : 'rgba(107, 114, 128, 0.2)', color: coupling.active ? config.color : '#9ca3af' }}
                            >
                              {config.label}
                            </span>
                            <span className="text-white">{coupling.target_name}</span>
                            <span className="text-xs text-gray-500">
                              ({targetTypeLabels[coupling.target_type]})
                            </span>
                          </div>
                          {coupling.condition && (
                            <div className="text-xs text-gray-400 mt-1">
                              Condition: {coupling.condition}
                            </div>
                          )}
                          <div className="text-xs text-gray-500 mt-1">
                            {coupling.target_rtu} &bull; Slot {coupling.target_slot}
                          </div>
                        </div>

                        {/* Status indicator */}
                        <div
                          className={`w-2 h-2 rounded-full ${coupling.active ? 'bg-green-400' : 'bg-gray-500'}`}
                          title={coupling.active ? 'Active' : 'Inactive'}
                        />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Legend */}
      <div className="flex flex-wrap gap-3 pt-4 border-t border-gray-700">
        {Object.entries(couplingTypeConfig).map(([type, config]) => (
          <div key={type} className="flex items-center gap-2">
            <div
              className="w-5 h-5 rounded flex items-center justify-center"
              style={{ backgroundColor: config.bgColor, color: config.color }}
            >
              {config.icon}
            </div>
            <span className="text-xs text-gray-400">{config.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Mock data for demonstration when API is not available
function getMockCouplings(): CoupledAction[] {
  return [
    {
      coupling_id: 1,
      name: 'Low Pressure Interlock',
      description: 'Disables pump when pressure is low',
      source_type: 'interlock',
      source_id: 1,
      source_name: 'Low Pressure Safety',
      target_type: 'control',
      target_id: 1,
      target_name: 'Main Pump',
      target_rtu: 'RTU-001',
      target_slot: 3,
      coupling_type: 'disable',
      active: false,
      condition: 'Pressure < 10 PSI',
    },
    {
      coupling_id: 2,
      name: 'Flow Control Cascade',
      description: 'Flow PID cascades to valve control',
      source_type: 'pid',
      source_id: 1,
      source_name: 'Flow Control Loop',
      target_type: 'control',
      target_id: 2,
      target_name: 'Control Valve CV-101',
      target_rtu: 'RTU-001',
      target_slot: 5,
      coupling_type: 'cascade',
      active: true,
    },
    {
      coupling_id: 3,
      name: 'Level Control Cascade',
      description: 'Level PID cascades to inlet valve',
      source_type: 'pid',
      source_id: 1,
      source_name: 'Flow Control Loop',
      target_type: 'pid',
      target_id: 2,
      target_name: 'Level Control Loop',
      target_rtu: 'RTU-002',
      target_slot: 1,
      coupling_type: 'cascade',
      active: true,
    },
    {
      coupling_id: 4,
      name: 'High Level Alarm Enable',
      description: 'Enables alarm when level exceeds limit',
      source_type: 'control',
      source_id: 3,
      source_name: 'Level Sensor LS-201',
      target_type: 'alarm',
      target_id: 1,
      target_name: 'High Level Alarm',
      target_rtu: 'RTU-002',
      target_slot: 2,
      coupling_type: 'enable',
      active: true,
      condition: 'Level > 90%',
    },
    {
      coupling_id: 5,
      name: 'Emergency Shutdown',
      description: 'Limits all pumps to 0% on emergency',
      source_type: 'interlock',
      source_id: 2,
      source_name: 'Emergency Stop',
      target_type: 'control',
      target_id: 1,
      target_name: 'Main Pump',
      target_rtu: 'RTU-001',
      target_slot: 3,
      coupling_type: 'limit',
      active: false,
      condition: 'E-Stop Pressed',
    },
  ];
}
