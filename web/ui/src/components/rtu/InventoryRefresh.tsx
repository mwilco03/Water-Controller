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
        {loading ? (
          <span className="inline-block w-4 h-4 border-2 border-gray-400/30 border-t-gray-400 rounded-full animate-spin" />
        ) : (
          <span className="font-bold">[R]</span>
        )}
        {loading ? 'Refreshing...' : 'Refresh Inventory'}
      </button>

      <div className="text-sm text-gray-400">
        <span className="text-gray-500">Last refresh:</span>{' '}
        <span className="text-gray-300">{formatLastRefresh()}</span>
      </div>

      {error && (
        <div className="text-sm text-red-400 flex items-center gap-1">
          <span className="font-bold">[!]</span>
          {error}
        </div>
      )}
    </div>
  );
}
