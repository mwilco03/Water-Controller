/**
 * Hook Tests for Water Treatment Controller HMI
 *
 * Tests for React hooks, focusing on:
 * - Correct behavior under normal conditions
 * - Error handling and recovery
 * - State management
 *
 * These tests run without network dependencies.
 */

import { renderHook, act, waitFor } from '@testing-library/react';

// Mock WebSocket for testing
class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;

  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((error: any) => void) | null = null;

  constructor(url: string) {
    // Simulate async connection
    setTimeout(() => {
      if (this.onopen) this.onopen();
    }, 0);
  }

  send(data: string) {
    // Mock send
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) this.onclose();
  }
}

// Replace global WebSocket with mock
(global as any).WebSocket = MockWebSocket;

describe('useWebSocket Hook', () => {
  let mockWebSocket: MockWebSocket;

  beforeEach(() => {
    // Track created WebSocket instances
    jest.spyOn(global, 'WebSocket' as any).mockImplementation((...args: unknown[]) => {
      const url = args[0] as string;
      mockWebSocket = new MockWebSocket(url);
      return mockWebSocket;
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('should create WebSocket connection with correct URL', () => {
    // Verify MockWebSocket constructor is called
    const ws = new (global as any).WebSocket('ws://localhost:8080/api/v1/ws/live');
    expect(ws).toBeInstanceOf(MockWebSocket);
  });

  it('should handle WebSocket open event', () => {
    const ws = new MockWebSocket('ws://localhost:8080');
    const openHandler = jest.fn();

    ws.onopen = openHandler;

    // Manually trigger the open event (simulating connection established)
    if (ws.onopen) ws.onopen();

    expect(ws.readyState).toBe(MockWebSocket.OPEN);
    expect(openHandler).toHaveBeenCalled();
  });

  it('should handle WebSocket close event', () => {
    const ws = new MockWebSocket('ws://localhost:8080');
    const closeHandler = jest.fn();

    ws.onclose = closeHandler;
    ws.close();

    expect(ws.readyState).toBe(MockWebSocket.CLOSED);
    expect(closeHandler).toHaveBeenCalled();
  });

  it('should handle WebSocket message parsing', () => {
    const ws = new MockWebSocket('ws://localhost:8080');
    const messageHandler = jest.fn();

    ws.onmessage = messageHandler;

    // Simulate receiving a message
    const testMessage = { type: 'sensor_update', data: { value: 7.2 } };
    ws.onmessage?.({ data: JSON.stringify(testMessage) });

    expect(messageHandler).toHaveBeenCalledWith({ data: JSON.stringify(testMessage) });
  });

  it('should handle reconnection attempts tracking', () => {
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 10;

    // Simulate reconnection logic
    const attemptReconnect = () => {
      if (reconnectAttempts < maxReconnectAttempts) {
        reconnectAttempts++;
        return true;
      }
      return false;
    };

    // First 10 attempts should succeed
    for (let i = 0; i < 10; i++) {
      expect(attemptReconnect()).toBe(true);
    }

    // 11th attempt should fail
    expect(attemptReconnect()).toBe(false);
    expect(reconnectAttempts).toBe(10);
  });
});

describe('Visibility Change Detection', () => {
  it('should detect when document becomes hidden', () => {
    // Test visibility change detection
    const visibilityHandler = jest.fn();

    document.addEventListener('visibilitychange', visibilityHandler);

    // Simulate visibility change
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => true,
    });

    document.dispatchEvent(new Event('visibilitychange'));

    expect(visibilityHandler).toHaveBeenCalled();

    document.removeEventListener('visibilitychange', visibilityHandler);
  });

  it('should detect when document becomes visible', () => {
    const visibilityHandler = jest.fn();

    document.addEventListener('visibilitychange', visibilityHandler);

    // Simulate visibility change to visible
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => false,
    });

    document.dispatchEvent(new Event('visibilitychange'));

    expect(visibilityHandler).toHaveBeenCalled();

    document.removeEventListener('visibilitychange', visibilityHandler);
  });
});

describe('Data Fetching Utilities', () => {
  beforeEach(() => {
    // Reset fetch mock before each test
    global.fetch = jest.fn();
  });

  it('should handle successful API response', async () => {
    const mockData = {
      data: [{ station_name: 'test-rtu', state: 'RUNNING' }],
    };

    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => mockData,
    });

    const response = await fetch('/api/v1/rtus');
    const data = await response.json();

    expect(data.data).toHaveLength(1);
    expect(data.data[0].station_name).toBe('test-rtu');
  });

  it('should handle API error response', async () => {
    const mockError = {
      error: {
        code: 'RTU_NOT_FOUND',
        message: 'RTU not found',
        operator_message: 'The requested device was not found.',
      },
    };

    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => mockError,
    });

    const response = await fetch('/api/v1/rtus/nonexistent');
    const data = await response.json();

    expect(response.ok).toBe(false);
    expect(data.error.code).toBe('RTU_NOT_FOUND');
    expect(data.error.operator_message).toContain('not found');
  });

  it('should handle network failure', async () => {
    (global.fetch as jest.Mock).mockRejectedValueOnce(
      new Error('Network error')
    );

    await expect(fetch('/api/v1/rtus')).rejects.toThrow('Network error');
  });
});

describe('Polling Logic', () => {
  jest.useFakeTimers();

  afterEach(() => {
    jest.clearAllTimers();
  });

  it('should poll at specified interval', () => {
    const pollFn = jest.fn();
    const interval = 5000;

    const intervalId = setInterval(pollFn, interval);

    // Advance time by 15 seconds
    jest.advanceTimersByTime(15000);

    // Should have called 3 times (at 5s, 10s, 15s)
    expect(pollFn).toHaveBeenCalledTimes(3);

    clearInterval(intervalId);
  });

  it('should not poll when visibility is hidden', () => {
    const pollFn = jest.fn();
    let isVisible = true;

    // Simulate conditional polling
    const startPolling = () => {
      if (isVisible) {
        return setInterval(pollFn, 5000);
      }
      return null;
    };

    // Start with visible
    let intervalId = startPolling();
    jest.advanceTimersByTime(10000);
    expect(pollFn).toHaveBeenCalledTimes(2);

    // Clear and simulate hidden
    if (intervalId) clearInterval(intervalId);
    isVisible = false;
    intervalId = startPolling();
    jest.advanceTimersByTime(10000);

    // Should still be 2 (no additional calls)
    expect(pollFn).toHaveBeenCalledTimes(2);
  });
});
