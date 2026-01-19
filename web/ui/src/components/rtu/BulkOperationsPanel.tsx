'use client';

import { useState, useCallback, useEffect } from 'react';

interface RTU {
  station_name: string;
  ip_address: string;
  state: string;
  slot_count: number;
  vendor_id: number;
  device_id: number;
}

interface OperationResult {
  station_name: string;
  success: boolean;
  message: string;
  duration_ms?: number;
}

interface BulkOperation {
  id: string;
  type: 'connect' | 'disconnect' | 'restart' | 'update_firmware' | 'export_config' | 'sync_time';
  status: 'pending' | 'running' | 'completed' | 'failed';
  selected_rtus: string[];
  results: OperationResult[];
  started_at?: string;
  completed_at?: string;
  progress: number;
}

type OperationType = BulkOperation['type'];

interface Props {
  rtus: RTU[];
  onRefresh?: () => void;
}

const operationConfig: Record<OperationType, {
  label: string;
  description: string;
  icon: JSX.Element;
  color: string;
  confirmMessage: string;
  requiresOnline?: boolean;
}> = {
  connect: {
    label: 'Connect All',
    description: 'Establish PROFINET connection to selected RTUs',
    icon: (
      <span className="text-sm font-bold">[+]</span>
    ),
    color: 'green',
    confirmMessage: 'Connect to all selected RTUs?',
  },
  disconnect: {
    label: 'Disconnect All',
    description: 'Gracefully disconnect from selected RTUs',
    icon: (
      <span className="text-sm font-bold">[X]</span>
    ),
    color: 'yellow',
    confirmMessage: 'Disconnect all selected RTUs? This will interrupt I/O data exchange.',
    requiresOnline: true,
  },
  restart: {
    label: 'Restart Communication',
    description: 'Restart PROFINET communication (AR reset)',
    icon: (
      <span className="text-sm font-bold">[R]</span>
    ),
    color: 'blue',
    confirmMessage: 'Restart communication on all selected RTUs? This will cause a brief interruption.',
    requiresOnline: true,
  },
  update_firmware: {
    label: 'Update Firmware',
    description: 'Deploy firmware update to selected RTUs',
    icon: (
      <span className="text-sm font-bold">[FW]</span>
    ),
    color: 'purple',
    confirmMessage: 'Update firmware on all selected RTUs? This requires a reboot and will cause downtime.',
  },
  export_config: {
    label: 'Export Config',
    description: 'Export configuration from selected RTUs',
    icon: (
      <span className="text-sm font-bold">[EXP]</span>
    ),
    color: 'gray',
    confirmMessage: 'Export configuration from all selected RTUs?',
  },
  sync_time: {
    label: 'Sync Time',
    description: 'Synchronize system time on selected RTUs',
    icon: (
      <span className="text-sm font-bold">[T]</span>
    ),
    color: 'cyan',
    confirmMessage: 'Synchronize time on all selected RTUs?',
    requiresOnline: true,
  },
};

export default function BulkOperationsPanel({ rtus, onRefresh }: Props) {
  const [selectedRtus, setSelectedRtus] = useState<string[]>([]);
  const [currentOperation, setCurrentOperation] = useState<BulkOperation | null>(null);
  const [showConfirm, setShowConfirm] = useState<OperationType | null>(null);
  const [operationHistory, setOperationHistory] = useState<BulkOperation[]>([]);

  const toggleSelection = (stationName: string) => {
    setSelectedRtus(prev =>
      prev.includes(stationName)
        ? prev.filter(n => n !== stationName)
        : [...prev, stationName]
    );
  };

  const selectAll = () => {
    setSelectedRtus(rtus.map(r => r.station_name));
  };

  const selectNone = () => {
    setSelectedRtus([]);
  };

  const selectByState = (state: string) => {
    setSelectedRtus(rtus.filter(r => r.state === state).map(r => r.station_name));
  };

  const executeOperation = useCallback(async (opType: OperationType) => {
    if (selectedRtus.length === 0) return;

    const operation: BulkOperation = {
      id: `op-${Date.now()}`,
      type: opType,
      status: 'running',
      selected_rtus: [...selectedRtus],
      results: [],
      started_at: new Date().toISOString(),
      progress: 0,
    };

    setCurrentOperation(operation);
    setShowConfirm(null);

    // Simulate operation execution with immutable state updates
    let currentResults: OperationResult[] = [];
    for (let i = 0; i < selectedRtus.length; i++) {
      const rtuName = selectedRtus[i];
      await new Promise(r => setTimeout(r, 500 + Math.random() * 1000));

      const success = Math.random() > 0.1; // 90% success rate
      const result: OperationResult = {
        station_name: rtuName,
        success,
        message: success ? `${opType} completed successfully` : 'Operation failed: timeout',
        duration_ms: Math.floor(Math.random() * 500) + 100,
      };

      // Use immutable update - create new array instead of mutating
      currentResults = [...currentResults, result];
      const progress = ((i + 1) / selectedRtus.length) * 100;
      setCurrentOperation(prev => prev ? {
        ...prev,
        results: currentResults,
        progress,
      } : null);
    }

    // Final status update with immutable pattern
    const finalStatus: BulkOperation['status'] = currentResults.every(r => r.success) ? 'completed' : 'failed';
    const completedOperation: BulkOperation = {
      ...operation,
      status: finalStatus,
      results: currentResults,
      completed_at: new Date().toISOString(),
    };
    setCurrentOperation(completedOperation);
    setOperationHistory(prev => [completedOperation, ...prev.slice(0, 9)]);

    // Auto-clear after 5 seconds
    setTimeout(() => {
      setCurrentOperation(null);
      onRefresh?.();
    }, 5000);
  }, [selectedRtus, onRefresh]);

  const onlineCount = rtus.filter(r => r.state === 'RUNNING').length;
  const offlineCount = rtus.filter(r => r.state === 'OFFLINE').length;
  const errorCount = rtus.filter(r => r.state === 'ERROR').length;

  return (
    <div className="space-y-4">
      {/* Selection Summary */}
      <div className="bg-gray-800/50 rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4">
            <h3 className="text-lg font-medium text-white">Bulk Operations</h3>
            <span className="text-sm text-gray-400">
              {selectedRtus.length} of {rtus.length} RTU{rtus.length !== 1 ? 's' : ''} selected
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={selectAll}
              className="text-sm text-blue-400 hover:text-blue-300"
            >
              Select All
            </button>
            <span className="text-gray-600">|</span>
            <button
              onClick={selectNone}
              className="text-sm text-blue-400 hover:text-blue-300"
            >
              Select None
            </button>
          </div>
        </div>

        {/* Quick Filters */}
        <div className="flex flex-wrap gap-2 mb-4">
          <button
            onClick={() => selectByState('RUNNING')}
            className="px-3 py-1 rounded text-sm bg-green-600/20 text-green-400 hover:bg-green-600/30"
          >
            Online ({onlineCount})
          </button>
          <button
            onClick={() => selectByState('OFFLINE')}
            className="px-3 py-1 rounded text-sm bg-gray-600/20 text-gray-400 hover:bg-gray-600/30"
          >
            Offline ({offlineCount})
          </button>
          {errorCount > 0 && (
            <button
              onClick={() => selectByState('ERROR')}
              className="px-3 py-1 rounded text-sm bg-red-600/20 text-red-400 hover:bg-red-600/30"
            >
              Error ({errorCount})
            </button>
          )}
        </div>

        {/* RTU Selection Grid */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 max-h-[200px] overflow-y-auto">
          {rtus.map((rtu) => (
            <label
              key={rtu.station_name}
              className={`flex items-center gap-2 p-2 rounded cursor-pointer transition-colors ${
                selectedRtus.includes(rtu.station_name)
                  ? 'bg-blue-600/20 border border-blue-500'
                  : 'bg-gray-700/30 border border-transparent hover:bg-gray-700/50'
              }`}
            >
              <input
                type="checkbox"
                checked={selectedRtus.includes(rtu.station_name)}
                onChange={() => toggleSelection(rtu.station_name)}
                className="rounded"
              />
              <div className="flex-1 min-w-0">
                <div className="text-sm text-white truncate">{rtu.station_name}</div>
                <div className="text-xs text-gray-500">{rtu.ip_address}</div>
              </div>
              <div className={`w-2 h-2 rounded-full ${
                rtu.state === 'RUNNING' ? 'bg-green-400' :
                rtu.state === 'ERROR' ? 'bg-red-400' :
                rtu.state === 'CONNECTING' ? 'bg-yellow-400 animate-pulse' :
                'bg-gray-400'
              }`} />
            </label>
          ))}
        </div>
      </div>

      {/* Operation Buttons */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {(Object.entries(operationConfig) as [OperationType, typeof operationConfig[OperationType]][]).map(([type, config]) => {
          const isDisabled = selectedRtus.length === 0 ||
            currentOperation !== null ||
            (config.requiresOnline && !selectedRtus.some(name => rtus.find(r => r.station_name === name)?.state === 'RUNNING'));

          return (
            <button
              key={type}
              onClick={() => setShowConfirm(type)}
              disabled={isDisabled}
              className={`flex flex-col items-center gap-2 p-4 rounded-lg transition-all ${
                isDisabled
                  ? 'bg-gray-700/30 text-gray-500 cursor-not-allowed'
                  : `bg-${config.color}-600/20 text-${config.color}-400 hover:bg-${config.color}-600/30`
              }`}
              style={{
                backgroundColor: isDisabled ? undefined : `rgba(var(--color-${config.color}), 0.2)`,
              }}
            >
              {config.icon}
              <span className="text-sm font-medium">{config.label}</span>
            </button>
          );
        })}
      </div>

      {/* Current Operation Progress */}
      {currentOperation && (
        <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              {currentOperation.status === 'running' && (
                <span className="inline-block w-5 h-5 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
              )}
              {currentOperation.status === 'completed' && (
                <span className="text-green-400 font-bold">[OK]</span>
              )}
              {currentOperation.status === 'failed' && (
                <span className="text-red-400 font-bold">[!]</span>
              )}
              <span className="text-white font-medium">
                {operationConfig[currentOperation.type].label}
              </span>
            </div>
            <span className="text-sm text-gray-400">
              {currentOperation.results.length} / {currentOperation.selected_rtus.length}
            </span>
          </div>

          {/* Progress Bar */}
          <div className="h-2 bg-gray-700 rounded-full overflow-hidden mb-3">
            <div
              className={`h-full transition-all duration-300 ${
                currentOperation.status === 'completed' ? 'bg-green-500' :
                currentOperation.status === 'failed' ? 'bg-red-500' :
                'bg-blue-500'
              }`}
              style={{ width: `${currentOperation.progress}%` }}
            />
          </div>

          {/* Results */}
          <div className="space-y-1 max-h-[150px] overflow-y-auto">
            {currentOperation.results.map((result) => (
              <div
                key={result.station_name}
                className={`flex items-center justify-between text-sm px-2 py-1 rounded ${
                  result.success ? 'bg-green-900/20' : 'bg-red-900/20'
                }`}
              >
                <span className={result.success ? 'text-green-400' : 'text-red-400'}>
                  {result.station_name}
                </span>
                <span className="text-gray-400 text-xs">
                  {result.success ? `${result.duration_ms}ms` : result.message}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Confirmation Modal */}
      {showConfirm && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-modal"
          onClick={(e) => e.target === e.currentTarget && setShowConfirm(null)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="bulk-confirm-modal-title"
        >
          <div className="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4 border border-gray-600" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-yellow-600/20 flex items-center justify-center text-yellow-400">
                {operationConfig[showConfirm].icon}
              </div>
              <h3 id="bulk-confirm-modal-title" className="text-lg font-semibold text-white">
                Confirm {operationConfig[showConfirm].label}
              </h3>
            </div>

            <p className="text-gray-300 mb-4">
              {operationConfig[showConfirm].confirmMessage}
            </p>

            <div className="bg-gray-700/50 rounded p-3 mb-4">
              <div className="text-sm text-gray-400 mb-2">
                This will affect {selectedRtus.length} RTU{selectedRtus.length !== 1 ? 's' : ''}:
              </div>
              <div className="flex flex-wrap gap-1">
                {selectedRtus.slice(0, 5).map(name => (
                  <span key={name} className="px-2 py-0.5 bg-gray-600 rounded text-xs text-white">
                    {name}
                  </span>
                ))}
                {selectedRtus.length > 5 && (
                  <span className="px-2 py-0.5 bg-gray-600 rounded text-xs text-gray-300">
                    +{selectedRtus.length - 5} more
                  </span>
                )}
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowConfirm(null)}
                className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => executeOperation(showConfirm)}
                className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded font-medium transition-colors"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Operation History */}
      {operationHistory.length > 0 && (
        <div className="bg-gray-800/50 rounded-lg p-4">
          <h4 className="text-sm font-medium text-gray-400 mb-3">Recent Operations</h4>
          <div className="space-y-2">
            {operationHistory.slice(0, 3).map((op) => (
              <div
                key={op.id}
                className="flex items-center justify-between text-sm p-2 bg-gray-700/30 rounded"
              >
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${
                    op.status === 'completed' ? 'bg-green-400' : 'bg-red-400'
                  }`} />
                  <span className="text-white">{operationConfig[op.type].label}</span>
                  <span className="text-gray-500">
                    on {op.selected_rtus.length} RTU{op.selected_rtus.length !== 1 ? 's' : ''}
                  </span>
                </div>
                <span className="text-gray-500 text-xs">
                  {op.completed_at ? new Date(op.completed_at).toLocaleTimeString() : ''}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
