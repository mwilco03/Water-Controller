/**
 * React Query hooks for RTU data fetching and mutation
 *
 * Replaces manual useState + useEffect patterns with declarative queries.
 * Integrates with WebSocket for real-time updates.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

// Type definitions (would normally come from generated types)
interface RTU {
  id: number;
  station_name: string;
  ip_address: string;
  connection_state: 'ONLINE' | 'OFFLINE' | 'CONNECTING';
  last_seen?: string;
  sensor_count?: number;
  actuator_count?: number;
}

interface RTUDetail extends RTU {
  sensors: Sensor[];
  actuators: Actuator[];
  connection_quality: number;
}

interface Sensor {
  id: number;
  slot: number;
  name: string;
  value: number;
  unit: string;
  quality: 'GOOD' | 'BAD' | 'UNCERTAIN' | 'NOT_CONNECTED';
  timestamp: string;
}

interface Actuator {
  id: number;
  slot: number;
  name: string;
  state: boolean;
  mode: 'AUTO' | 'MANUAL';
}

/**
 * Query keys for RTU-related queries.
 *
 * Organized hierarchically for easy invalidation:
 * - ['rtus'] - invalidates all RTU queries
 * - ['rtus', 'list'] - invalidates only the list
 * - ['rtus', 'detail', id] - invalidates specific RTU detail
 */
const rtuKeys = {
  all: ['rtus'] as const,
  lists: () => [...rtuKeys.all, 'list'] as const,
  list: (filters?: object) => [...rtuKeys.lists(), filters] as const,
  details: () => [...rtuKeys.all, 'detail'] as const,
  detail: (id: number) => [...rtuKeys.details(), id] as const,
};

/**
 * Fetch all RTUs.
 *
 * Example usage:
 *   const { data: rtus, isLoading, error } = useRTUs();
 *
 *   if (isLoading) return <Spinner />;
 *   if (error) return <Error message={error.message} />;
 *   return <RTUList rtus={rtus} />;
 */
export function useRTUs() {
  return useQuery({
    queryKey: rtuKeys.lists(),
    queryFn: async (): Promise<RTU[]> => {
      const response = await fetch('/api/v1/rtus');
      if (!response.ok) {
        throw new Error(`Failed to fetch RTUs: ${response.statusText}`);
      }
      const data = await response.json();
      return data.data || [];
    },
    // Poll every 10 seconds as fallback if WebSocket is disconnected
    // WebSocket will provide real-time updates when connected
    refetchInterval: (query) => {
      // Only poll if we have data (initial fetch succeeded)
      return query.state.data ? 10000 : false;
    },
  });
}

/**
 * Fetch detailed information for a specific RTU.
 *
 * Example usage:
 *   const { data: rtu, isLoading } = useRTU(rtuId);
 */
export function useRTU(id: number) {
  return useQuery({
    queryKey: rtuKeys.detail(id),
    queryFn: async (): Promise<RTUDetail> => {
      const response = await fetch(`/api/v1/rtus/${id}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch RTU ${id}: ${response.statusText}`);
      }
      const data = await response.json();
      return data.data;
    },
    // Only fetch if we have a valid ID
    enabled: id > 0,
    // Refresh every 5 seconds for detailed view (operators watching this RTU)
    refetchInterval: 5000,
  });
}

/**
 * Mutation hook for controlling actuators/controls.
 *
 * Includes optimistic updates for instant UI feedback.
 *
 * Example usage:
 *   const controlActuator = useControlActuator();
 *
 *   <button onClick={() => controlActuator.mutate({
 *     rtuName: 'rtu-tank-1',
 *     controlTag: 'main-pump',
 *     command: 'ON'
 *   })}>
 *     Turn On Pump
 *   </button>
 */
export function useControlActuator() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: { rtuName: string; controlTag: string; command: 'ON' | 'OFF' }) => {
      // POST /rtus/{name}/controls/{tag}/command
      const response = await fetch(`/api/v1/rtus/${encodeURIComponent(params.rtuName)}/controls/${encodeURIComponent(params.controlTag)}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: params.command }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `Failed to control actuator: ${response.statusText}`);
      }

      return response.json();
    },

    // If mutation fails, log error
    onError: (err) => {
      console.error('Control command failed:', err);
    },

    // Always refetch after mutation to ensure consistency
    onSettled: () => {
      // Invalidate all RTU queries to refresh state
      queryClient.invalidateQueries({ queryKey: rtuKeys.all });
    },
  });
}

/**
 * Hook to sync React Query cache with WebSocket updates.
 *
 * Call this in the root layout to keep cache fresh with real-time data.
 *
 * Example usage:
 *   useRTUWebSocketSync(websocketMessage);
 */
export function useRTUWebSocketSync(message: any) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!message) return;

    switch (message.type) {
      case 'rtu_online':
      case 'rtu_offline':
      case 'rtu_updated':
        // Update specific RTU in cache
        if (message.rtu_id) {
          queryClient.invalidateQueries({ queryKey: rtuKeys.detail(message.rtu_id) });
        }
        // Update RTU list
        queryClient.invalidateQueries({ queryKey: rtuKeys.lists() });
        break;

      case 'sensor_updated':
        // Update RTU detail (includes sensors)
        if (message.rtu_id) {
          queryClient.setQueryData<RTUDetail>(
            rtuKeys.detail(message.rtu_id),
            (old) => {
              if (!old) return old;
              return {
                ...old,
                sensors: old.sensors.map((sensor) =>
                  sensor.id === message.sensor_id
                    ? { ...sensor, value: message.value, quality: message.quality, timestamp: message.timestamp }
                    : sensor
                ),
              };
            }
          );
        }
        break;

      case 'actuator_updated':
        // Update RTU detail (includes actuators)
        if (message.rtu_id) {
          queryClient.setQueryData<RTUDetail>(
            rtuKeys.detail(message.rtu_id),
            (old) => {
              if (!old) return old;
              return {
                ...old,
                actuators: old.actuators.map((actuator) =>
                  actuator.id === message.actuator_id
                    ? { ...actuator, state: message.state, mode: message.mode }
                    : actuator
                ),
              };
            }
          );
        }
        break;
    }
  }, [message, queryClient]);
}

/**
 * Hook to manually invalidate RTU queries.
 *
 * Useful for forcing a refresh after non-WebSocket events.
 *
 * Example usage:
 *   const { invalidateAll, invalidateRTU } = useInvalidateRTUs();
 *   <button onClick={() => invalidateAll()}>Refresh All</button>
 */
export function useInvalidateRTUs() {
  const queryClient = useQueryClient();

  return {
    invalidateAll: () => queryClient.invalidateQueries({ queryKey: rtuKeys.all }),
    invalidateList: () => queryClient.invalidateQueries({ queryKey: rtuKeys.lists() }),
    invalidateRTU: (id: number) => queryClient.invalidateQueries({ queryKey: rtuKeys.detail(id) }),
  };
}
