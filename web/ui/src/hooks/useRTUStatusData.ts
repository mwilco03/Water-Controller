'use client';

/**
 * useRTUStatusData Hook
 *
 * Manages RTU status data fetching, WebSocket real-time updates,
 * and polling fallback for the dashboard page.
 *
 * Encapsulates:
 * - Initial data fetch
 * - WebSocket subscriptions for real-time updates
 * - Polling fallback when WebSocket disconnects
 * - Tab visibility awareness for power efficiency
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { getRTUs, getAlarms, getRTUInventory } from '@/lib/api';
import { rtuLogger } from '@/lib/logger';
import type { RTUStatusData, AlarmData } from '@/components/hmi';
import { TIMING } from '@/constants';

export type DataMode = 'streaming' | 'polling' | 'disconnected';

interface SystemMetrics {
  cycleTimeMs: number;
  pendingWrites: number;
}

interface UseRTUStatusDataReturn {
  rtus: RTUStatusData[];
  alarms: AlarmData[];
  loading: boolean;
  error: string | null;
  dataMode: DataMode;
  metrics: SystemMetrics;
  connected: boolean;
  refetch: () => Promise<void>;
  setAlarms: React.Dispatch<React.SetStateAction<AlarmData[]>>;
  setRtus: React.Dispatch<React.SetStateAction<RTUStatusData[]>>;
}

export function useRTUStatusData(): UseRTUStatusDataReturn {
  const [rtus, setRtus] = useState<RTUStatusData[]>([]);
  const [alarms, setAlarms] = useState<AlarmData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dataMode, setDataMode] = useState<DataMode>('polling');
  const [metrics, setMetrics] = useState<SystemMetrics>({
    cycleTimeMs: 1000,
    pendingWrites: 0,
  });
  const [isVisible, setIsVisible] = useState(true);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch RTU and alarm data
  const fetchData = useCallback(async () => {
    try {
      const [rtusResponse, alarmsResponse] = await Promise.all([
        getRTUs(),
        getAlarms(),
      ]);

      // Defensive check - ensure we have arrays before mapping
      const rtuList = Array.isArray(rtusResponse) ? rtusResponse : [];

      // Fetch inventory for each RTU to get sensor/actuator counts
      const rtusWithInventory = await Promise.all(
        rtuList.map(async (rtu: { station_name: string; ip_address: string; state: string; slot_count?: number; last_seen?: string; healthy?: boolean }) => {
          try {
            const inventory = await getRTUInventory(rtu.station_name);
            return {
              station_name: rtu.station_name,
              ip_address: rtu.ip_address,
              state: rtu.state,
              slot_count: rtu.slot_count || 0,
              sensor_count: inventory?.sensors?.length || 0,
              actuator_count: inventory?.controls?.length || 0,
              last_communication: rtu.last_seen || new Date().toISOString(),
              alarm_count: 0,
              has_unacknowledged_alarms: false,
              healthy: rtu.healthy ?? true,
            };
          } catch {
            return {
              station_name: rtu.station_name,
              ip_address: rtu.ip_address,
              state: rtu.state,
              slot_count: rtu.slot_count || 0,
              sensor_count: 0,
              actuator_count: 0,
              last_communication: rtu.last_seen,
              alarm_count: 0,
              has_unacknowledged_alarms: false,
              healthy: rtu.healthy ?? true,
            };
          }
        })
      );

      // Process alarms - defensive check for array
      const alarmList = Array.isArray(alarmsResponse) ? alarmsResponse : [];
      const formattedAlarms: AlarmData[] = alarmList.map((alarm: { alarm_id?: number; id?: number; rtu_station?: string; station_name?: string; slot: number; severity?: string; priority?: string; message?: string; description?: string; state?: string; acknowledged?: boolean; timestamp?: string; raised_at?: string }) => ({
        alarm_id: alarm.alarm_id || alarm.id || 0,
        rtu_station: alarm.rtu_station || alarm.station_name || '',
        slot: alarm.slot,
        severity: (alarm.severity || alarm.priority || 'MEDIUM') as AlarmData['severity'],
        message: alarm.message || alarm.description || '',
        state: (alarm.state || (alarm.acknowledged ? 'ACTIVE_ACK' : 'ACTIVE')) as AlarmData['state'],
        timestamp: alarm.timestamp || alarm.raised_at || '',
        acknowledged: alarm.acknowledged,
      }));

      // Update RTU alarm counts
      const rtusWithAlarms = rtusWithInventory.map(rtu => {
        const rtuAlarms = formattedAlarms.filter(a => a.rtu_station === rtu.station_name && a.state !== 'CLEARED');
        return {
          ...rtu,
          alarm_count: rtuAlarms.length,
          has_unacknowledged_alarms: rtuAlarms.some(a => a.state === 'ACTIVE'),
        };
      });

      setRtus(rtusWithAlarms);
      setAlarms(formattedAlarms);
      setError(null);
    } catch (err) {
      rtuLogger.error('Error fetching data', err);
      setError('Failed to fetch system data');
      setDataMode('disconnected');
    } finally {
      setLoading(false);
    }
  }, []);

  // WebSocket for real-time updates
  const { connected, subscribe } = useWebSocket({
    onConnect: () => {
      setDataMode('streaming');
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    },
    onDisconnect: () => {
      setDataMode('polling');
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(fetchData, TIMING.POLLING.NORMAL);
      }
    },
  });

  // Subscribe to real-time updates
  useEffect(() => {
    const unsubRtu = subscribe('rtu_update', () => {
      fetchData();
    });

    const unsubAlarm = subscribe('alarm_raised', (_, alarm) => {
      setAlarms(prev => {
        const existing = prev.findIndex(a => a.alarm_id === alarm.alarm_id);
        if (existing >= 0) {
          const updated = [...prev];
          updated[existing] = { ...alarm, state: 'ACTIVE' };
          return updated;
        }
        return [{ ...alarm, state: 'ACTIVE' }, ...prev];
      });

      setRtus(prev => prev.map(rtu =>
        rtu.station_name === alarm.rtu_station
          ? {
              ...rtu,
              alarm_count: (rtu.alarm_count || 0) + 1,
              has_unacknowledged_alarms: true,
            }
          : rtu
      ));
    });

    const unsubAlarmAck = subscribe('alarm_acknowledged', (_, data) => {
      setAlarms(prev =>
        prev.map(a =>
          a.alarm_id === data.alarm_id ? { ...a, state: 'ACTIVE_ACK' as const } : a
        )
      );

      setRtus(prev => prev.map(rtu => {
        if (rtu.station_name === data.rtu_station) {
          return {
            ...rtu,
            has_unacknowledged_alarms: false,
          };
        }
        return rtu;
      }));
    });

    const unsubAlarmClear = subscribe('alarm_cleared', (_, data) => {
      setAlarms(prev => prev.filter(a => a.alarm_id !== data.alarm_id));

      setRtus(prev => prev.map(rtu =>
        rtu.station_name === data.rtu_station
          ? {
              ...rtu,
              alarm_count: Math.max(0, (rtu.alarm_count || 0) - 1),
            }
          : rtu
      ));
    });

    return () => {
      unsubRtu();
      unsubAlarm();
      unsubAlarmAck();
      unsubAlarmClear();
    };
  }, [subscribe, fetchData]);

  // Track tab visibility for power efficiency
  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsVisible(!document.hidden);
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  // Initial data fetch and polling setup
  useEffect(() => {
    fetchData();

    if (isVisible) {
      pollIntervalRef.current = setInterval(fetchData, TIMING.POLLING.NORMAL);
    }

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [fetchData, isVisible]);

  return {
    rtus,
    alarms,
    loading,
    error,
    dataMode,
    metrics,
    connected,
    refetch: fetchData,
    setAlarms,
    setRtus,
  };
}

export default useRTUStatusData;
