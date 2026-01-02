/**
 * Dashboard Page Tests
 *
 * Tests for the RTU Status (Dashboard) page covering:
 * - Loading states with skeleton UI
 * - Error handling and recovery
 * - RTU data display and status indicators
 * - Alarm banner display
 * - Connection status and data mode indicators
 *
 * Run with: npm test -- --testPathPattern=dashboard
 */

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock the hooks and components
jest.mock('@/hooks/useRTUStatusData', () => ({
  useRTUStatusData: jest.fn(),
}));

jest.mock('next/link', () => {
  return function MockLink({ children, href }: { children: React.ReactNode; href: string }) {
    return <a href={href}>{children}</a>;
  };
});

// Mock HMI components
jest.mock('@/components/hmi', () => ({
  AlarmBanner: ({ alarms }: { alarms: any[] }) => (
    <div data-testid="alarm-banner">
      {alarms.length > 0 && <span>Active Alarms: {alarms.length}</span>}
    </div>
  ),
  SkeletonRTUCard: () => <div data-testid="skeleton-rtu-card" />,
  SkeletonStats: () => <div data-testid="skeleton-stats" />,
  ErrorMessage: ({ title, description, action }: { title: string; description?: string; action?: () => void }) => (
    <div data-testid="error-message">
      <h2>{title}</h2>
      {description && <p>{description}</p>}
      {action && <button onClick={action}>Retry</button>}
    </div>
  ),
  ErrorPresets: {
    connectionFailed: (refetch: () => void) => ({
      title: 'Connection Failed',
      description: 'Unable to connect to server',
      action: refetch,
    }),
  },
  LiveTimestamp: () => <div data-testid="live-timestamp" />,
}));

import { useRTUStatusData } from '@/hooks/useRTUStatusData';
import RTUStatusPage from '@/app/page';

const mockUseRTUStatusData = useRTUStatusData as jest.MockedFunction<typeof useRTUStatusData>;

describe('Dashboard (RTU Status) Page', () => {
  const mockRefetch = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    // Reset document title
    document.title = '';
  });

  describe('Loading State', () => {
    it('shows skeleton loading UI while loading', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [],
        alarms: [],
        loading: true,
        error: null,
        dataMode: 'websocket',
        connected: true,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      expect(screen.getAllByTestId('skeleton-rtu-card')).toHaveLength(4);
      expect(screen.getByTestId('skeleton-stats')).toBeInTheDocument();
      expect(screen.getByLabelText('Loading RTU status...')).toBeInTheDocument();
    });
  });

  describe('Error State', () => {
    it('shows error message when error occurs with no data', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [],
        alarms: [],
        loading: false,
        error: 'Network error',
        dataMode: 'disconnected',
        connected: false,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      expect(screen.getByTestId('error-message')).toBeInTheDocument();
      expect(screen.getByText('Connection Failed')).toBeInTheDocument();
    });

    it('allows retry on error', async () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [],
        alarms: [],
        loading: false,
        error: 'Network error',
        dataMode: 'disconnected',
        connected: false,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      const retryButton = screen.getByRole('button', { name: /retry/i });
      await userEvent.click(retryButton);

      expect(mockRefetch).toHaveBeenCalledTimes(1);
    });
  });

  describe('Empty State', () => {
    it('shows empty state when no RTUs configured', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [],
        alarms: [],
        loading: false,
        error: null,
        dataMode: 'websocket',
        connected: true,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      expect(screen.getByText('No RTUs Configured')).toBeInTheDocument();
      expect(screen.getByText('Add RTU devices to start monitoring')).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Add RTU' })).toHaveAttribute('href', '/rtus');
    });
  });

  describe('RTU Display', () => {
    const mockRtus = [
      {
        station_name: 'water-rtu-01',
        ip_address: '192.168.1.50',
        state: 'RUNNING',
        sensor_count: 5,
        actuator_count: 3,
        alarm_count: 0,
      },
      {
        station_name: 'water-rtu-02',
        ip_address: '192.168.1.51',
        state: 'OFFLINE',
        sensor_count: 0,
        actuator_count: 0,
        alarm_count: 0,
      },
      {
        station_name: 'water-rtu-03',
        ip_address: '192.168.1.52',
        state: 'ERROR',
        sensor_count: 2,
        actuator_count: 1,
        alarm_count: 2,
      },
    ];

    it('displays RTU cards with correct data', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: mockRtus,
        alarms: [],
        loading: false,
        error: null,
        dataMode: 'websocket',
        connected: true,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      // Check RTU names are displayed
      expect(screen.getByText('water-rtu-01')).toBeInTheDocument();
      expect(screen.getByText('water-rtu-02')).toBeInTheDocument();
      expect(screen.getByText('water-rtu-03')).toBeInTheDocument();

      // Check IP addresses
      expect(screen.getByText('192.168.1.50')).toBeInTheDocument();
      expect(screen.getByText('192.168.1.51')).toBeInTheDocument();
    });

    it('displays correct summary statistics', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: mockRtus,
        alarms: [{ id: 1, state: 'ACTIVE' }, { id: 2, state: 'ACTIVE' }],
        loading: false,
        error: null,
        dataMode: 'websocket',
        connected: true,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      // Online RTUs: 1 out of 3 (only RUNNING)
      expect(screen.getByText(/1/)).toBeInTheDocument();
      expect(screen.getByText('RTUs Online')).toBeInTheDocument();

      // Active alarms
      expect(screen.getByText('Active Alarms')).toBeInTheDocument();
    });

    it('links to RTU detail page', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [mockRtus[0]],
        alarms: [],
        loading: false,
        error: null,
        dataMode: 'websocket',
        connected: true,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      const detailLink = screen.getByRole('link', { name: /view details/i });
      expect(detailLink).toHaveAttribute('href', '/rtus/water-rtu-01');
    });
  });

  describe('Connection Status', () => {
    it('shows connected status when websocket is connected', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [{ station_name: 'test', state: 'RUNNING', sensor_count: 1, actuator_count: 1, alarm_count: 0 }],
        alarms: [],
        loading: false,
        error: null,
        dataMode: 'websocket',
        connected: true,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      expect(screen.getByText('Connected')).toBeInTheDocument();
    });

    it('shows offline status when disconnected', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [{ station_name: 'test', state: 'RUNNING', sensor_count: 1, actuator_count: 1, alarm_count: 0 }],
        alarms: [],
        loading: false,
        error: null,
        dataMode: 'polling',
        connected: false,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      expect(screen.getByText('Offline')).toBeInTheDocument();
    });

    it('shows polling mode warning when in polling mode', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [{ station_name: 'test', state: 'RUNNING', sensor_count: 1, actuator_count: 1, alarm_count: 0 }],
        alarms: [],
        loading: false,
        error: null,
        dataMode: 'polling',
        connected: false,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      expect(screen.getByText(/polling mode/i)).toBeInTheDocument();
      expect(screen.getByText(/websocket disconnected/i)).toBeInTheDocument();
    });

    it('shows disconnected warning with retry button', async () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [{ station_name: 'test', state: 'RUNNING', sensor_count: 1, actuator_count: 1, alarm_count: 0 }],
        alarms: [],
        loading: false,
        error: null,
        dataMode: 'disconnected',
        connected: false,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      expect(screen.getByText(/disconnected/i)).toBeInTheDocument();
      expect(screen.getByText(/cannot reach api server/i)).toBeInTheDocument();

      const retryButton = screen.getByRole('button', { name: /retry/i });
      await userEvent.click(retryButton);

      expect(mockRefetch).toHaveBeenCalled();
    });
  });

  describe('Alarm Banner', () => {
    it('displays alarm banner when alarms are present', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [{ station_name: 'test', state: 'RUNNING', sensor_count: 1, actuator_count: 1, alarm_count: 1 }],
        alarms: [
          { id: 1, state: 'ACTIVE', severity: 2, message: 'High temperature' },
        ],
        loading: false,
        error: null,
        dataMode: 'websocket',
        connected: true,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      expect(screen.getByTestId('alarm-banner')).toBeInTheDocument();
      expect(screen.getByText(/active alarms: 1/i)).toBeInTheDocument();
    });

    it('renders alarm banner even when no alarms', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [{ station_name: 'test', state: 'RUNNING', sensor_count: 1, actuator_count: 1, alarm_count: 0 }],
        alarms: [],
        loading: false,
        error: null,
        dataMode: 'websocket',
        connected: true,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      expect(screen.getByTestId('alarm-banner')).toBeInTheDocument();
    });
  });

  describe('Page Title', () => {
    it('sets the document title on mount', async () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [],
        alarms: [],
        loading: false,
        error: null,
        dataMode: 'websocket',
        connected: true,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      await waitFor(() => {
        expect(document.title).toBe('RTU Status - Water Treatment Controller');
      });
    });
  });

  describe('RTU State Styling', () => {
    it('applies correct status class for RUNNING state', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [{ station_name: 'online-rtu', state: 'RUNNING', sensor_count: 1, actuator_count: 1, alarm_count: 0 }],
        alarms: [],
        loading: false,
        error: null,
        dataMode: 'websocket',
        connected: true,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      // Check for running state badge
      expect(screen.getByText('Running')).toBeInTheDocument();
    });

    it('applies correct status class for OFFLINE state', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [{ station_name: 'offline-rtu', state: 'OFFLINE', sensor_count: 0, actuator_count: 0, alarm_count: 0 }],
        alarms: [],
        loading: false,
        error: null,
        dataMode: 'websocket',
        connected: true,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      expect(screen.getByText('Offline')).toBeInTheDocument();
    });

    it('applies correct status class for FAULT state', () => {
      mockUseRTUStatusData.mockReturnValue({
        rtus: [{ station_name: 'fault-rtu', state: 'FAULT', sensor_count: 1, actuator_count: 1, alarm_count: 1 }],
        alarms: [],
        loading: false,
        error: null,
        dataMode: 'websocket',
        connected: true,
        refetch: mockRefetch,
      });

      render(<RTUStatusPage />);

      expect(screen.getByText('Fault')).toBeInTheDocument();
    });
  });
});
