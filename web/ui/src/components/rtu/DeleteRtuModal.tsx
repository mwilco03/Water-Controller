'use client';

import { useState, useEffect, useCallback } from 'react';

interface DeletionImpact {
  slots: number;
  sensors: number;
  controls: number;
  alarms: number;
  pid_loops: number;
  samples: number;
  historian_tags: number;
  modbus_mappings: number;
}

interface DeletionResult {
  deleted: {
    alarm_rules: number;
    pid_loops: number;
    historian_tags: number;
    modbus_mappings: number;
    alarms: number;
  };
}

interface Props {
  isOpen: boolean;
  stationName: string;
  onClose: () => void;
  onSuccess: (result: DeletionResult) => void;
}

export default function DeleteRtuModal({
  isOpen,
  stationName,
  onClose,
  onSuccess,
}: Props) {
  const [impact, setImpact] = useState<DeletionImpact | null>(null);
  const [loadingImpact, setLoadingImpact] = useState(false);
  const [impactError, setImpactError] = useState<string | null>(null);
  const [confirmName, setConfirmName] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const fetchImpact = useCallback(async () => {
    setLoadingImpact(true);
    setImpactError(null);

    try {
      const res = await fetch(`/api/v1/rtus/${encodeURIComponent(stationName)}/deletion-impact`);

      if (res.ok) {
        const data = await res.json();
        setImpact(data);
      } else if (res.status === 404) {
        // RTU not found - might have been deleted already
        setImpact({
          slots: 0,
          sensors: 0,
          controls: 0,
          alarms: 0,
          pid_loops: 0,
          samples: 0,
          historian_tags: 0,
          modbus_mappings: 0,
        });
      } else {
        setImpactError('Failed to load deletion impact. Proceed with caution.');
        // Set default impact so user can still proceed
        setImpact({
          slots: 0,
          sensors: 0,
          controls: 0,
          alarms: 0,
          pid_loops: 0,
          samples: 0,
          historian_tags: 0,
          modbus_mappings: 0,
        });
      }
    } catch (err) {
      setImpactError('Unable to reach server. Proceed with caution.');
      setImpact({
        slots: 0,
        sensors: 0,
        controls: 0,
        alarms: 0,
        pid_loops: 0,
        samples: 0,
        historian_tags: 0,
        modbus_mappings: 0,
      });
    } finally {
      setLoadingImpact(false);
    }
  }, [stationName]);

  // Fetch impact when modal opens
  useEffect(() => {
    if (isOpen && stationName) {
      fetchImpact();
    }
    return () => {
      // Reset state when modal closes
      setImpact(null);
      setConfirmName('');
      setDeleteError(null);
      setImpactError(null);
    };
  }, [isOpen, stationName, fetchImpact]);

  const handleDelete = useCallback(async () => {
    if (confirmName !== stationName) {
      return;
    }

    setDeleting(true);
    setDeleteError(null);

    try {
      const res = await fetch(`/api/v1/rtus/${encodeURIComponent(stationName)}?cascade=true`, {
        method: 'DELETE',
      });

      if (res.ok) {
        const result = await res.json();
        onSuccess(result);
        return;
      }

      if (res.status === 404) {
        setDeleteError('RTU not found. It may have been deleted already.');
        return;
      }

      if (res.status === 409) {
        setDeleteError('Cannot delete: RTU is currently connected. Disconnect first.');
        return;
      }

      const data = await res.json().catch(() => ({}));
      setDeleteError(data.detail || 'Deletion failed. Some resources may remain. Contact admin.');
    } catch (err) {
      setDeleteError('Unable to reach server. Check connection and try again.');
    } finally {
      setDeleting(false);
    }
  }, [confirmName, stationName, onSuccess]);

  const handleClose = () => {
    if (!deleting) {
      onClose();
    }
  };

  if (!isOpen) return null;

  const nameMatches = confirmName === stationName;
  const canDelete = nameMatches && !deleting && !loadingImpact;

  const hasImpact = impact && (
    impact.slots > 0 ||
    impact.sensors > 0 ||
    impact.controls > 0 ||
    impact.alarms > 0 ||
    impact.pid_loops > 0 ||
    impact.historian_tags > 0
  );

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div
        className="bg-gray-900 rounded-lg w-full max-w-lg border border-gray-700 shadow-xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-red-600/20 flex items-center justify-center">
              <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-white">
              Delete RTU: <span className="text-red-400">{stationName}</span>
            </h2>
          </div>
          <button
            onClick={handleClose}
            disabled={deleting}
            className="text-gray-400 hover:text-white transition-colors disabled:opacity-50"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 space-y-4">
          {/* Delete Error Banner */}
          {deleteError && (
            <div className="flex items-start gap-3 p-3 bg-red-900/30 border border-red-800 rounded-lg">
              <svg className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div className="flex-1">
                <p className="text-red-300 text-sm">{deleteError}</p>
                <button
                  onClick={() => setDeleteError(null)}
                  className="text-red-400 text-xs hover:text-red-300 mt-1"
                >
                  Dismiss
                </button>
              </div>
            </div>
          )}

          {/* Warning Text */}
          <div className="text-gray-300">
            <p>This action will <span className="text-red-400 font-semibold">permanently remove</span> this RTU and all associated data:</p>
          </div>

          {/* Impact Summary */}
          {loadingImpact ? (
            <div className="flex items-center gap-3 p-4 bg-gray-800 rounded-lg">
              <svg className="animate-spin h-5 w-5 text-blue-400" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              <span className="text-gray-400">Loading deletion impact...</span>
            </div>
          ) : impactError ? (
            <div className="p-4 bg-amber-900/30 border border-amber-800 rounded-lg">
              <p className="text-amber-300 text-sm">{impactError}</p>
            </div>
          ) : hasImpact ? (
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <div className="grid grid-cols-2 gap-3 text-sm">
                {impact.slots > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">Slots:</span>
                    <span className="text-white font-medium">{impact.slots}</span>
                  </div>
                )}
                {impact.sensors > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">Sensors:</span>
                    <span className="text-white font-medium">{impact.sensors}</span>
                  </div>
                )}
                {impact.controls > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">Controls:</span>
                    <span className="text-white font-medium">{impact.controls}</span>
                  </div>
                )}
                {impact.alarms > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">Alarm Rules:</span>
                    <span className="text-white font-medium">{impact.alarms}</span>
                  </div>
                )}
                {impact.pid_loops > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">PID Loops:</span>
                    <span className="text-white font-medium">{impact.pid_loops}</span>
                  </div>
                )}
                {impact.historian_tags > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">Historian Tags:</span>
                    <span className="text-white font-medium">{impact.historian_tags}</span>
                  </div>
                )}
                {impact.samples > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">Data Samples:</span>
                    <span className="text-white font-medium">{impact.samples.toLocaleString()}</span>
                  </div>
                )}
                {impact.modbus_mappings > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">Modbus Mappings:</span>
                    <span className="text-white font-medium">{impact.modbus_mappings}</span>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
              <p className="text-gray-400 text-sm">No additional data associated with this RTU.</p>
            </div>
          )}

          {/* Confirmation Input */}
          <div className="pt-2">
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Type <span className="font-mono text-red-400 bg-red-900/30 px-1 rounded">{stationName}</span> to confirm:
            </label>
            <input
              type="text"
              value={confirmName}
              onChange={e => setConfirmName(e.target.value)}
              placeholder="Enter RTU name to confirm"
              disabled={deleting}
              className={`w-full px-3 py-2 bg-gray-800 border rounded text-white placeholder-gray-500 focus:outline-none focus:ring-2 disabled:opacity-50 ${
                confirmName && !nameMatches
                  ? 'border-red-500 focus:ring-red-500'
                  : nameMatches
                  ? 'border-green-500 focus:ring-green-500'
                  : 'border-gray-700 focus:ring-blue-500'
              }`}
            />
            {confirmName && !nameMatches && (
              <p className="text-red-400 text-xs mt-1">Name does not match</p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-700">
          <button
            onClick={handleClose}
            disabled={deleting}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleDelete}
            disabled={!canDelete}
            className="px-4 py-2 bg-red-600 hover:bg-red-500 rounded text-white font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {deleting && (
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
            )}
            {deleting ? 'Deleting...' : 'Delete RTU'}
          </button>
        </div>
      </div>
    </div>
  );
}
