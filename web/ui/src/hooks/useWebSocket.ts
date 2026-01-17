'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { wsLogger as logger } from '@/lib/logger';
import { TIMING } from '@/constants';
import { getWebSocketUrl, getCurrentHost } from '@/config/ports';

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
    reconnectInterval = TIMING.WEBSOCKET.RECONNECT_INTERVAL_MS,
    maxReconnectAttempts = TIMING.WEBSOCKET.MAX_RECONNECT_ATTEMPTS,
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
  const isMountedRef = useRef(true);

  // Store callbacks in refs to avoid dependency issues
  const onConnectRef = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);
  const onMessageRef = useRef(onMessage);

  // Update refs when callbacks change (without causing reconnects)
  useEffect(() => {
    onConnectRef.current = onConnect;
    onDisconnectRef.current = onDisconnect;
    onMessageRef.current = onMessage;
  }, [onConnect, onDisconnect, onMessage]);

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

  // Connect to WebSocket - uses refs to avoid dependency on callbacks
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Determine WebSocket URL from centralized config
    // See: src/config/ports.ts for port configuration
    const wsUrl = getWebSocketUrl();

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        if (!isMountedRef.current) return;
        logger.info('WebSocket connected');
        reconnectAttemptsRef.current = 0;
        setState(prev => ({ ...prev, connected: true }));
        onConnectRef.current?.();
      };

      ws.onclose = () => {
        if (!isMountedRef.current) return;
        logger.info('WebSocket disconnected');
        setState(prev => ({ ...prev, connected: false }));
        onDisconnectRef.current?.();
        wsRef.current = null;

        // Attempt reconnection only if still mounted
        if (isMountedRef.current && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          logger.info(`Reconnecting in ${reconnectInterval}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`);
          reconnectTimeoutRef.current = setTimeout(connect, reconnectInterval);
        }
      };

      ws.onerror = (error) => {
        logger.error('WebSocket error:', error);
      };

      ws.onmessage = (event) => {
        if (!isMountedRef.current) return;
        try {
          const message = JSON.parse(event.data);
          // Backend sends 'channel', frontend uses 'type' - support both
          const type = message.type || message.channel;
          const data = message.data;

          setState(prev => ({
            ...prev,
            lastEvent: type,
            lastEventTime: new Date(),
          }));

          // Call global handler
          onMessageRef.current?.(type, data);

          // Call event-specific subscribers
          subscribersRef.current.get(type)?.forEach(handler => {
            try {
              handler(type, data);
            } catch (e) {
              logger.error(`Error in WebSocket handler for ${type}:`, e);
            }
          });

          // Also notify wildcard subscribers
          subscribersRef.current.get('*')?.forEach(handler => {
            try {
              handler(type, data);
            } catch (e) {
              logger.error('Error in WebSocket wildcard handler:', e);
            }
          });

        } catch (e) {
          logger.error('Failed to parse WebSocket message:', e);
        }
      };

      wsRef.current = ws;
    } catch (e) {
      logger.error('Failed to create WebSocket:', e);
    }
  }, [reconnectInterval, maxReconnectAttempts]); // Removed callback deps - using refs instead

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

  // Connect on mount, disconnect and cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true;
    const subscribers = subscribersRef.current;
    connect();
    return () => {
      isMountedRef.current = false;
      disconnect();
      // Clear all subscribers to prevent memory leaks
      subscribers.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty deps intentional - only run on mount/unmount, callbacks use refs

  return {
    connected: state.connected,
    lastEvent: state.lastEvent,
    lastEventTime: state.lastEventTime,
    subscribe,
    connect,
    disconnect,
  };
}

export default useWebSocket;
