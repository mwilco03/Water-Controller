'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

type MessageHandler = (event: string, data: any) => void;

interface WebSocketState {
  connected: boolean;
  lastEvent: string | null;
  lastEventTime: Date | null;
}

interface UseWebSocketOptions {
  onMessage?: MessageHandler;
  onConnect?: () => void;
  onDisconnect?: () => void;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

/**
 * WebSocket hook for real-time updates from the Water Treatment Controller API.
 *
 * Replaces polling with push notifications for efficiency.
 * The server broadcasts events when data changes, eliminating unnecessary requests.
 *
 * Events:
 * - rtu_update: RTU connection state changed
 * - sensor_update: Sensor value changed
 * - actuator_command: Actuator command sent
 * - alarm_raised: New alarm
 * - alarm_acknowledged: Alarm acknowledged
 * - alarm_cleared: Alarm cleared
 * - network_scan_complete: Network scan finished
 * - pid_update: PID loop values changed
 * - rtu_test_complete: RTU test finished
 * - discovery_complete: Sensor discovery finished
 *
 * Usage:
 * ```tsx
 * const { connected, subscribe, lastEvent } = useWebSocket({
 *   onConnect: () => console.log('Connected'),
 *   onDisconnect: () => console.log('Disconnected'),
 * });
 *
 * // Subscribe to specific events
 * useEffect(() => {
 *   const unsubscribe = subscribe('sensor_update', (data) => {
 *     console.log('Sensor updated:', data);
 *   });
 *   return unsubscribe;
 * }, [subscribe]);
 * ```
 */
export function useWebSocket(options: UseWebSocketOptions = {}) {
  const {
    onMessage,
    onConnect,
    onDisconnect,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
  } = options;

  const [state, setState] = useState<WebSocketState>({
    connected: false,
    lastEvent: null,
    lastEventTime: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const subscribersRef = useRef<Map<string, Set<MessageHandler>>>(new Map());

  // Subscribe to a specific event type
  const subscribe = useCallback((event: string, handler: MessageHandler) => {
    if (!subscribersRef.current.has(event)) {
      subscribersRef.current.set(event, new Set());
    }
    subscribersRef.current.get(event)!.add(handler);

    // Return unsubscribe function
    return () => {
      subscribersRef.current.get(event)?.delete(handler);
    };
  }, []);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Determine WebSocket URL
    const protocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = typeof window !== 'undefined' ? window.location.host : 'localhost:8080';
    const wsUrl = `${protocol}//${host}/ws`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected');
        reconnectAttemptsRef.current = 0;
        setState(prev => ({ ...prev, connected: true }));
        onConnect?.();
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        setState(prev => ({ ...prev, connected: false }));
        onDisconnect?.();
        wsRef.current = null;

        // Attempt reconnection
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          console.log(`Reconnecting in ${reconnectInterval}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`);
          reconnectTimeoutRef.current = setTimeout(connect, reconnectInterval);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          const { type, data } = message;

          setState(prev => ({
            ...prev,
            lastEvent: type,
            lastEventTime: new Date(),
          }));

          // Call global handler
          onMessage?.(type, data);

          // Call event-specific subscribers
          subscribersRef.current.get(type)?.forEach(handler => {
            try {
              handler(type, data);
            } catch (e) {
              console.error(`Error in WebSocket handler for ${type}:`, e);
            }
          });

          // Also notify wildcard subscribers
          subscribersRef.current.get('*')?.forEach(handler => {
            try {
              handler(type, data);
            } catch (e) {
              console.error(`Error in WebSocket wildcard handler:`, e);
            }
          });

        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };

      wsRef.current = ws;
    } catch (e) {
      console.error('Failed to create WebSocket:', e);
    }
  }, [onConnect, onDisconnect, onMessage, reconnectInterval, maxReconnectAttempts]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    reconnectAttemptsRef.current = maxReconnectAttempts; // Prevent auto-reconnect
    wsRef.current?.close();
    wsRef.current = null;
  }, [maxReconnectAttempts]);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    connected: state.connected,
    lastEvent: state.lastEvent,
    lastEventTime: state.lastEventTime,
    subscribe,
    connect,
    disconnect,
  };
}

/**
 * Hook for subscribing to RTU updates.
 * Fetches initial data and updates via WebSocket.
 */
export function useRtuUpdates(initialFetch: () => Promise<void>) {
  const [loading, setLoading] = useState(true);
  const { connected, subscribe } = useWebSocket();

  useEffect(() => {
    // Initial fetch
    initialFetch().finally(() => setLoading(false));
  }, [initialFetch]);

  useEffect(() => {
    // Subscribe to RTU updates
    const unsubscribe = subscribe('rtu_update', () => {
      initialFetch();
    });
    return unsubscribe;
  }, [subscribe, initialFetch]);

  return { loading, connected };
}

/**
 * Hook for subscribing to sensor updates for a specific RTU.
 */
export function useSensorUpdates(stationName: string, onUpdate: (data: any) => void) {
  const { subscribe } = useWebSocket();

  useEffect(() => {
    const unsubscribe = subscribe('sensor_update', (event, data) => {
      if (data.station_name === stationName) {
        onUpdate(data);
      }
    });
    return unsubscribe;
  }, [subscribe, stationName, onUpdate]);
}

/**
 * Hook for subscribing to alarm updates.
 */
export function useAlarmUpdates(onAlarm: (type: string, data: any) => void) {
  const { subscribe } = useWebSocket();

  useEffect(() => {
    const unsub1 = subscribe('alarm_raised', (_, data) => onAlarm('raised', data));
    const unsub2 = subscribe('alarm_acknowledged', (_, data) => onAlarm('acknowledged', data));
    const unsub3 = subscribe('alarm_cleared', (_, data) => onAlarm('cleared', data));

    return () => {
      unsub1();
      unsub2();
      unsub3();
    };
  }, [subscribe, onAlarm]);
}

export default useWebSocket;
