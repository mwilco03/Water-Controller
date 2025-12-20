'use client';

import { useState, useCallback } from 'react';
import { refreshRTUInventory } from '@/lib/api';
import type { RTUInventory } from '@/lib/api';

interface Props {
  rtuStation: string;
  lastRefresh?: string | null;
  onRefreshComplete?: (inventory: RTUInventory) => void;
  onRefreshError?: (error: Error) => void;
}

export default function InventoryRefresh({
  rtuStation,
  lastRefresh,
  onRefreshComplete,
  onRefreshError,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRefresh = useCallback(async () => {
    if (loading) return;
    setLoading(true);
    setError(null);

    try {
      const inventory = await refreshRTUInventory(rtuStation);
      onRefreshComplete?.(inventory);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to refresh inventory';
      setError(errorMessage);
      onRefreshError?.(err instanceof Error ? err : new Error(errorMessage));
    } finally {
      setLoading(false);
    }
  }, [loading, rtuStation, onRefreshComplete, onRefreshError]);

  const formatLastRefresh = () => {
    if (!lastRefresh) return 'Never';
    const date = new Date(lastRefresh);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleRefresh}
        disabled={loading}
        className={`
          flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm
          transition-all duration-200
          ${loading
            ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
            : 'bg-blue-600 hover:bg-blue-500 text-white hover:shadow-lg hover:shadow-blue-600/25'
          }
        `}
      >
        <svg
          className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
        {loading ? 'Refreshing...' : 'Refresh Inventory'}
      </button>

      <div className="text-sm text-gray-400">
        <span className="text-gray-500">Last refresh:</span>{' '}
        <span className="text-gray-300">{formatLastRefresh()}</span>
      </div>

      {error && (
        <div className="text-sm text-red-400 flex items-center gap-1">
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
          {error}
        </div>
      )}
    </div>
  );
}
