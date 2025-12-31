/**
 * API Client Tests
 *
 * Tests the API client to ensure it correctly:
 * - Makes requests to the expected endpoints
 * - Handles responses correctly
 * - Handles errors appropriately
 */

import {
  getRTUs,
  getAlarms,
  setAuthToken,
  getAuthToken,
  isAuthenticated,
  RTUDevice,
  Alarm,
} from '../lib/api';

// Mock fetch globally
global.fetch = jest.fn();

const mockFetch = global.fetch as jest.Mock;

beforeEach(() => {
  mockFetch.mockClear();
  setAuthToken(null); // Clear auth state
});

describe('Authentication State', () => {
  it('should start without auth token', () => {
    expect(getAuthToken()).toBeNull();
    expect(isAuthenticated()).toBe(false);
  });

  it('should set and get auth token', () => {
    setAuthToken('test-token-123');
    expect(getAuthToken()).toBe('test-token-123');
    expect(isAuthenticated()).toBe(true);
  });

  it('should clear auth token', () => {
    setAuthToken('test-token');
    setAuthToken(null);
    expect(getAuthToken()).toBeNull();
    expect(isAuthenticated()).toBe(false);
  });
});

describe('getRTUs', () => {
  it('should fetch RTUs from correct endpoint', async () => {
    const mockRTUs: RTUDevice[] = [
      {
        station_name: 'RTU-001',
        state: 'RUNNING',
        ip_address: '192.168.1.10',
        vendor_id: 42,
        device_id: 1,
        slot_count: 8,
        sensors: [],
        actuators: [],
      },
      {
        station_name: 'RTU-002',
        state: 'OFFLINE',
        ip_address: '192.168.1.11',
        vendor_id: 42,
        device_id: 2,
        slot_count: 4,
        sensors: [],
        actuators: [],
      },
    ];

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ rtus: mockRTUs }),
    });

    const result = await getRTUs();

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/rtus'),
      expect.any(Object)
    );
    expect(result).toHaveLength(2);
    expect(result[0].station_name).toBe('RTU-001');
    expect(result[0].state).toBe('RUNNING');
  });

  it('should include auth header when token is set', async () => {
    setAuthToken('my-jwt-token');

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ rtus: [] }),
    });

    await getRTUs();

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer my-jwt-token',
        }),
      })
    );
  });

  it('should return empty array when response has no rtus', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });

    const result = await getRTUs();

    expect(result).toEqual([]);
  });

  it('should throw on API error', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      text: async () => 'Internal Server Error',
    });

    await expect(getRTUs()).rejects.toThrow('API Error 500');
  });

  it('should throw on network error', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'));

    await expect(getRTUs()).rejects.toThrow('Network error');
  });
});

describe('getAlarms', () => {
  it('should fetch alarms from correct endpoint', async () => {
    const mockAlarms: Alarm[] = [
      {
        alarm_id: 1,
        rule_id: 10,
        rtu_station: 'RTU-001',
        slot: 1,
        severity: 'HIGH',
        state: 'ACTIVE',
        message: 'Tank overflow',
        value: 95.5,
        threshold: 90.0,
        raise_time: '2024-01-15T10:30:00Z',
      },
      {
        alarm_id: 2,
        rule_id: 11,
        rtu_station: 'RTU-001',
        slot: 2,
        severity: 'LOW',
        state: 'ACKNOWLEDGED',
        message: 'Sensor offline',
        value: 0,
        threshold: 1,
        raise_time: '2024-01-15T10:25:00Z',
        ack_time: '2024-01-15T10:26:00Z',
        ack_user: 'operator1',
      },
    ];

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ alarms: mockAlarms }),
    });

    const result = await getAlarms();

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/alarms'),
      expect.any(Object)
    );
    expect(result).toHaveLength(2);
    expect(result[0].severity).toBe('HIGH');
    expect(result[0].state).toBe('ACTIVE');
  });

  it('should return empty array when no alarms', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ alarms: [] }),
    });

    const result = await getAlarms();

    expect(result).toEqual([]);
  });
});

describe('Error Handling', () => {
  it('should clear auth token on 401 response', async () => {
    setAuthToken('old-token');

    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      text: async () => 'Unauthorized',
    });

    await expect(getRTUs()).rejects.toThrow('Authentication required');

    // Token should be cleared
    expect(getAuthToken()).toBeNull();
  });

  it('should include status code in error message', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
      text: async () => 'Service Unavailable',
    });

    await expect(getRTUs()).rejects.toThrow('API Error 503');
  });
});

describe('Request Headers', () => {
  it('should include Content-Type header', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ rtus: [] }),
    });

    await getRTUs();

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
      })
    );
  });
});

describe('RTU Device Structure', () => {
  it('should parse RTU with all fields', async () => {
    const fullRTU: RTUDevice = {
      station_name: 'WATER-PLANT-01',
      ip_address: '10.0.1.100',
      vendor_id: 0x002a,
      device_id: 0x0405,
      state: 'RUNNING',
      slot_count: 8,
      sensors: [
        {
          slot: 1,
          name: 'Tank Level',
          value: 75.5,
          unit: 'ft',
          quality: 'GOOD',
          quality_code: 0x00,
          timestamp: '2024-01-15T10:30:00Z',
        },
      ],
      actuators: [
        {
          slot: 5,
          name: 'Inlet Valve',
          command: 'ON',
          pwm_duty: 100,
          forced: false,
        },
      ],
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ rtus: [fullRTU] }),
    });

    const result = await getRTUs();

    expect(result[0].station_name).toBe('WATER-PLANT-01');
    expect(result[0].sensors).toHaveLength(1);
    expect(result[0].sensors[0].quality).toBe('GOOD');
    expect(result[0].actuators).toHaveLength(1);
    expect(result[0].actuators[0].command).toBe('ON');
  });
});

describe('Alarm Structure', () => {
  it('should parse alarm with ISA-18.2 fields', async () => {
    const alarm: Alarm = {
      alarm_id: 100,
      rule_id: 5,
      rtu_station: 'RTU-001',
      slot: 2,
      severity: 'CRITICAL',
      state: 'ACTIVE',
      message: 'Emergency shutdown triggered',
      value: 120,
      threshold: 100,
      raise_time: '2024-01-15T10:30:00Z',
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ alarms: [alarm] }),
    });

    const result = await getAlarms();

    expect(result[0].alarm_id).toBe(100);
    expect(result[0].severity).toBe('CRITICAL');
    expect(result[0].state).toBe('ACTIVE');
    expect(result[0].raise_time).toBe('2024-01-15T10:30:00Z');
  });

  it('should handle acknowledged alarm with optional fields', async () => {
    const alarm: Alarm = {
      alarm_id: 101,
      rule_id: 6,
      rtu_station: 'RTU-002',
      slot: 3,
      severity: 'HIGH',
      state: 'CLEARED',
      message: 'High pressure',
      value: 150,
      threshold: 145,
      raise_time: '2024-01-15T09:00:00Z',
      ack_time: '2024-01-15T09:05:00Z',
      ack_user: 'operator2',
      clear_time: '2024-01-15T09:30:00Z',
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ alarms: [alarm] }),
    });

    const result = await getAlarms();

    expect(result[0].ack_time).toBe('2024-01-15T09:05:00Z');
    expect(result[0].ack_user).toBe('operator2');
    expect(result[0].clear_time).toBe('2024-01-15T09:30:00Z');
  });
});
