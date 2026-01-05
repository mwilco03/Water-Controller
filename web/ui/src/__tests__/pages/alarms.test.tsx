/**
 * Alarms Page Tests
 *
 * Tests for the Alarm Management page covering:
 * - Alarm list display (active, shelved, history)
 * - Statistics display
 * - Tab navigation
 * - Shelve/Unshelve functionality
 * - Error handling
 * - WebSocket real-time updates
 *
 * Run with: npm test -- --testPathPattern=alarms
 */

import React from 'react';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock hooks
jest.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: jest.fn(() => ({
    connected: true,
    subscribe: jest.fn(() => jest.fn()),
  })),
}));

jest.mock('@/contexts/CommandModeContext', () => ({
  useCommandMode: jest.fn(() => ({
    canCommand: true,
    mode: 'command',
  })),
}));

jest.mock('@/lib/logger', () => ({
  wsLogger: { info: jest.fn(), error: jest.fn() },
  alarmLogger: { info: jest.fn(), error: jest.fn() },
}));

// Mock components
jest.mock('@/components/AlarmSummary', () => {
  return function MockAlarmSummary({ alarms, onShelve }: { alarms: any[]; onShelve?: (alarm: any) => void }) {
    return (
      <div data-testid="alarm-summary">
        {alarms.length === 0 ? (
          <p>No active alarms</p>
        ) : (
          <ul>
            {alarms.map((alarm) => (
              <li key={alarm.alarm_id} data-testid={`alarm-${alarm.alarm_id}`}>
                <span>{alarm.message}</span>
                <span>{alarm.severity}</span>
                {onShelve && (
                  <button onClick={() => onShelve(alarm)} data-testid={`shelve-${alarm.alarm_id}`}>
                    Shelve
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  };
});

jest.mock('@/components/CommandModeLogin', () => {
  return function MockCommandModeLogin({ showButton }: { showButton?: boolean }) {
    return showButton ? <button data-testid="command-login">Login</button> : null;
  };
});

import { useWebSocket } from '@/hooks/useWebSocket';
import { useCommandMode } from '@/contexts/CommandModeContext';
import AlarmsPage from '@/app/alarms/page';

const mockUseWebSocket = useWebSocket as jest.MockedFunction<typeof useWebSocket>;
const mockUseCommandMode = useCommandMode as jest.MockedFunction<typeof useCommandMode>;

describe('Alarms Page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseWebSocket.mockReturnValue({
      connected: true,
      subscribe: jest.fn(() => jest.fn()),
    });
    mockUseCommandMode.mockReturnValue({
      canCommand: true,
      mode: 'command',
    });

    // Mock fetch
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Initial Load', () => {
    it('sets the page title', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(document.title).toBe('Alarms - Water Treatment Controller');
      });
    });

    it('shows loading state initially', () => {
      (global.fetch as jest.Mock).mockImplementation(() => new Promise(() => {})); // Never resolves

      render(<AlarmsPage />);

      expect(screen.getByText('Loading alarms...')).toBeInTheDocument();
    });

    it('fetches alarms on mount', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith('/api/v1/alarms');
        expect(global.fetch).toHaveBeenCalledWith('/api/v1/alarms/history?limit=100');
        expect(global.fetch).toHaveBeenCalledWith('/api/v1/alarms/shelved');
      });
    });
  });

  describe('Statistics Display', () => {
    const mockAlarms = [
      { alarm_id: 1, severity: 'CRITICAL', state: 'ACTIVE_UNACK', message: 'Critical alarm' },
      { alarm_id: 2, severity: 'WARNING', state: 'ACTIVE_UNACK', message: 'Warning alarm' },
      { alarm_id: 3, severity: 'WARNING', state: 'ACTIVE_ACK', message: 'Acknowledged warning' },
    ];

    it('displays correct alarm statistics', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: mockAlarms }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [{ id: 1 }] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        // Total active alarms
        expect(screen.getByText('Active Alarms')).toBeInTheDocument();

        // Critical count
        expect(screen.getByText('Critical')).toBeInTheDocument();

        // Warning count
        expect(screen.getByText('Warning')).toBeInTheDocument();

        // Unacknowledged count
        expect(screen.getByText('Unacknowledged')).toBeInTheDocument();

        // Shelved count
        expect(screen.getByText('Shelved')).toBeInTheDocument();
      });
    });
  });

  describe('Tab Navigation', () => {
    it('shows active alarms tab by default', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        const activeTab = screen.getByRole('button', { name: /active alarms/i });
        expect(activeTab).toHaveClass('border-b-2');
      });
    });

    it('switches to shelved tab when clicked', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /shelved/i })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole('button', { name: /shelved/i }));

      expect(screen.getByText('No shelved alarms')).toBeInTheDocument();
    });

    it('switches to history tab when clicked', async () => {
      const mockHistory = [
        {
          alarm_id: 1,
          severity: 'CRITICAL',
          rtu_station: 'rtu-01',
          message: 'Past alarm',
          timestamp: '2024-01-01T12:00:00Z',
          value: 95.5,
          threshold: 80.0,
          ack_user: 'operator1',
        },
      ];

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: mockHistory }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /history/i })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole('button', { name: /history/i }));

      await waitFor(() => {
        expect(screen.getByText('Past alarm')).toBeInTheDocument();
        expect(screen.getByText('rtu-01')).toBeInTheDocument();
        expect(screen.getByText('operator1')).toBeInTheDocument();
      });
    });
  });

  describe('Active Alarms Display', () => {
    it('displays alarm list from AlarmSummary', async () => {
      const mockAlarms = [
        { alarm_id: 1, severity: 'CRITICAL', state: 'ACTIVE_UNACK', message: 'High temperature' },
        { alarm_id: 2, severity: 'WARNING', state: 'ACTIVE_ACK', message: 'Low pressure' },
      ];

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: mockAlarms }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByTestId('alarm-summary')).toBeInTheDocument();
        expect(screen.getByText('High temperature')).toBeInTheDocument();
        expect(screen.getByText('Low pressure')).toBeInTheDocument();
      });
    });

    it('shows empty state when no active alarms', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByText('No active alarms')).toBeInTheDocument();
      });
    });
  });

  describe('Shelve Functionality', () => {
    it('shows shelve hint when in command mode', async () => {
      const mockAlarms = [
        { alarm_id: 1, severity: 'WARNING', state: 'ACTIVE_UNACK', message: 'Test alarm' },
      ];

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: mockAlarms }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByText(/click the clock icon to shelve/i)).toBeInTheDocument();
      });
    });

    it('opens shelve dialog when shelve button clicked', async () => {
      const mockAlarms = [
        { alarm_id: 1, severity: 'WARNING', state: 'ACTIVE_UNACK', message: 'Shelve test', rtu_station: 'rtu-01', slot: 1 },
      ];

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: mockAlarms }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByTestId('shelve-1')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByTestId('shelve-1'));

      expect(screen.getByText('Shelve Alarm')).toBeInTheDocument();
      expect(screen.getByText(/shelve test/i)).toBeInTheDocument();
    });

    it('closes shelve dialog when cancelled', async () => {
      const mockAlarms = [
        { alarm_id: 1, severity: 'WARNING', state: 'ACTIVE_UNACK', message: 'Cancel test', rtu_station: 'rtu-01', slot: 1 },
      ];

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: mockAlarms }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByTestId('shelve-1')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByTestId('shelve-1'));
      expect(screen.getByText('Shelve Alarm')).toBeInTheDocument();

      await userEvent.click(screen.getByRole('button', { name: /cancel/i }));
      expect(screen.queryByText('Shelve Alarm')).not.toBeInTheDocument();
    });

    it('calls API when shelve confirmed', async () => {
      const mockAlarms = [
        { alarm_id: 1, severity: 'WARNING', state: 'ACTIVE_UNACK', message: 'API test', rtu_station: 'rtu-01', slot: 1 },
      ];

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: mockAlarms }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) })
        .mockResolvedValueOnce({ ok: true }) // Shelve API call
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByTestId('shelve-1')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByTestId('shelve-1'));

      // Fill in reason
      const reasonInput = screen.getByPlaceholderText(/scheduled maintenance/i);
      await userEvent.type(reasonInput, 'Test reason');

      // Confirm shelve
      await userEvent.click(screen.getByRole('button', { name: /shelve alarm/i }));

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith('/api/v1/alarms/shelve', expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }));
      });
    });
  });

  describe('Shelved Alarms Tab', () => {
    it('displays shelved alarms table', async () => {
      const mockShelved = [
        {
          id: 1,
          rtu_station: 'rtu-01',
          slot: 1,
          shelved_by: 'operator1',
          shelved_at: '2024-01-01T10:00:00Z',
          shelf_duration_minutes: 60,
          expires_at: '2024-01-01T11:00:00Z',
          reason: 'Maintenance',
          active: 1,
        },
      ];

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: mockShelved }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /shelved/i })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole('button', { name: /shelved/i }));

      await waitFor(() => {
        expect(screen.getByText('rtu-01')).toBeInTheDocument();
        expect(screen.getByText('operator1')).toBeInTheDocument();
        expect(screen.getByText('Maintenance')).toBeInTheDocument();
        expect(screen.getByText('1h')).toBeInTheDocument();
      });
    });

    it('shows unshelve button in command mode', async () => {
      const mockShelved = [
        {
          id: 1,
          rtu_station: 'rtu-01',
          slot: 1,
          shelved_by: 'operator1',
          shelved_at: '2024-01-01T10:00:00Z',
          shelf_duration_minutes: 60,
          expires_at: '2024-01-01T11:00:00Z',
          reason: null,
          active: 1,
        },
      ];

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: mockShelved }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /shelved/i })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole('button', { name: /shelved/i }));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /unshelve/i })).toBeInTheDocument();
      });
    });

    it('calls unshelve API when unshelve clicked', async () => {
      const mockShelved = [
        {
          id: 42,
          rtu_station: 'rtu-01',
          slot: 1,
          shelved_by: 'operator1',
          shelved_at: '2024-01-01T10:00:00Z',
          shelf_duration_minutes: 60,
          expires_at: '2024-01-01T11:00:00Z',
          reason: null,
          active: 1,
        },
      ];

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: mockShelved }) })
        .mockResolvedValueOnce({ ok: true }) // Unshelve call
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /shelved/i })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole('button', { name: /shelved/i }));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /unshelve/i })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole('button', { name: /unshelve/i }));

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith('/api/v1/alarms/shelved/42', { method: 'DELETE' });
      });
    });
  });

  describe('Error Handling', () => {
    it('displays error message on fetch failure', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: false, status: 500 })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByText('Error Loading Alarms')).toBeInTheDocument();
        expect(screen.getByText(/failed to fetch active alarms/i)).toBeInTheDocument();
      });
    });

    it('displays retry button on error', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: false, status: 500 })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });
    });

    it('retries fetch when retry clicked', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: false, status: 500 })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) })
        // Retry calls
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole('button', { name: /retry/i }));

      // Verify fetch was called again
      expect(global.fetch).toHaveBeenCalledTimes(6); // 3 initial + 3 retry
    });
  });

  describe('View Mode (No Command Access)', () => {
    it('shows login button in view mode', async () => {
      mockUseCommandMode.mockReturnValue({
        canCommand: false,
        mode: 'view',
      });

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByTestId('command-login')).toBeInTheDocument();
      });
    });

    it('hides shelve hint in view mode', async () => {
      mockUseCommandMode.mockReturnValue({
        canCommand: false,
        mode: 'view',
      });

      const mockAlarms = [
        { alarm_id: 1, severity: 'WARNING', state: 'ACTIVE_UNACK', message: 'Test' },
      ];

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: mockAlarms }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.queryByText(/click the clock icon to shelve/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('History Pagination', () => {
    it('shows load more button when history exceeds visible count', async () => {
      const mockHistory = Array.from({ length: 60 }, (_, i) => ({
        alarm_id: i + 1,
        severity: 'WARNING',
        rtu_station: 'rtu-01',
        message: `Alarm ${i + 1}`,
        timestamp: '2024-01-01T12:00:00Z',
        value: 100,
        threshold: 80,
      }));

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ alarms: mockHistory }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ shelved_alarms: [] }) });

      render(<AlarmsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /history/i })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole('button', { name: /history/i }));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /load more/i })).toBeInTheDocument();
        expect(screen.getByText(/10 remaining/i)).toBeInTheDocument();
      });
    });
  });
});
