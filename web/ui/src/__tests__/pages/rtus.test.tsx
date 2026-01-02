/**
 * RTU Management Page Tests
 *
 * Tests for the RTU Management page covering:
 * - RTU list display and selection
 * - Add/Delete RTU modals
 * - Discovery panel toggling
 * - Connect/Disconnect actions
 * - Health status display
 * - WebSocket real-time updates
 *
 * Run with: npm test -- --testPathPattern=rtus
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

jest.mock('@/components/ui/Toast', () => ({
  useToast: jest.fn(() => ({
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
    warning: jest.fn(),
  })),
}));

jest.mock('@/lib/logger', () => ({
  wsLogger: { info: jest.fn(), error: jest.fn() },
  rtuLogger: { info: jest.fn(), error: jest.fn() },
}));

// Mock components
jest.mock('@/components/rtu', () => ({
  DiscoveryPanel: ({ onDeviceSelect }: { onDeviceSelect: (device: any) => void }) => (
    <div data-testid="discovery-panel">
      <button
        onClick={() => onDeviceSelect({
          device_name: 'discovered-rtu',
          ip_address: '192.168.1.100',
          mac_address: '00:1A:2B:3C:4D:5E',
          vendor_id: 0x1171,
          device_id: 0x0001,
        })}
      >
        Select Device
      </button>
    </div>
  ),
  RtuStateBadge: ({ state, size }: { state: string; size: string }) => (
    <span data-testid={`state-badge-${state}`} className={`badge-${size}`}>{state}</span>
  ),
  AddRtuModal: ({ isOpen, onClose, onSuccess, prefillData }: any) => (
    isOpen ? (
      <div data-testid="add-rtu-modal">
        <span>Add RTU Modal</span>
        {prefillData?.station_name && <span data-testid="prefill-name">{prefillData.station_name}</span>}
        <button onClick={onClose}>Cancel</button>
        <button onClick={() => onSuccess({ station_name: prefillData?.station_name || 'new-rtu' })}>
          Add
        </button>
      </div>
    ) : null
  ),
  DeleteRtuModal: ({ isOpen, stationName, onClose, onSuccess }: any) => (
    isOpen ? (
      <div data-testid="delete-rtu-modal">
        <span>Delete {stationName}?</span>
        <button onClick={onClose}>Cancel</button>
        <button onClick={() => onSuccess({ deleted: { alarm_rules: 1, pid_loops: 0, historian_tags: 2 } })}>
          Delete
        </button>
      </div>
    ) : null
  ),
  StaleIndicator: ({ lastUpdated }: { lastUpdated: string }) => (
    <span data-testid="stale-indicator">{lastUpdated}</span>
  ),
}));

jest.mock('next/link', () => {
  return function MockLink({ children, href }: { children: React.ReactNode; href: string }) {
    return <a href={href}>{children}</a>;
  };
});

import { useWebSocket } from '@/hooks/useWebSocket';
import { useToast } from '@/components/ui/Toast';
import RTUsPage from '@/app/rtus/page';

const mockUseWebSocket = useWebSocket as jest.MockedFunction<typeof useWebSocket>;
const mockUseToast = useToast as jest.MockedFunction<typeof useToast>;

describe('RTU Management Page', () => {
  const mockToast = {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
    warning: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    mockUseToast.mockReturnValue(mockToast);
    mockUseWebSocket.mockReturnValue({
      connected: true,
      subscribe: jest.fn(() => jest.fn()),
    });

    // Mock fetch
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  describe('Initial Load', () => {
    it('sets the page title', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(document.title).toBe('RTU Management - Water Treatment Controller');
      });
    });

    it('fetches RTUs on mount', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith('/api/v1/rtus');
      });
    });

    it('shows empty state when no RTUs', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('No RTUs registered')).toBeInTheDocument();
        expect(screen.getByText('Add Your First RTU')).toBeInTheDocument();
      });
    });
  });

  describe('RTU List Display', () => {
    const mockRtus = [
      {
        station_name: 'water-rtu-01',
        ip_address: '192.168.1.50',
        vendor_id: 0x1171,
        device_id: 0x0001,
        connection_state: 'RUNNING',
        slot_count: 16,
        last_seen: '2024-01-01T12:00:00Z',
      },
      {
        station_name: 'water-rtu-02',
        ip_address: '192.168.1.51',
        vendor_id: 0x1171,
        device_id: 0x0001,
        connection_state: 'OFFLINE',
        slot_count: 8,
      },
    ];

    it('displays RTU list after fetch', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockRtus,
      });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('water-rtu-01')).toBeInTheDocument();
        expect(screen.getByText('water-rtu-02')).toBeInTheDocument();
      });
    });

    it('shows RTU IP addresses', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockRtus,
      });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('192.168.1.50')).toBeInTheDocument();
        expect(screen.getByText('192.168.1.51')).toBeInTheDocument();
      });
    });

    it('shows state badges for RTUs', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockRtus,
      });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByTestId('state-badge-RUNNING')).toBeInTheDocument();
        expect(screen.getByTestId('state-badge-OFFLINE')).toBeInTheDocument();
      });
    });
  });

  describe('RTU Selection and Details', () => {
    const mockRtu = {
      station_name: 'water-rtu-01',
      ip_address: '192.168.1.50',
      vendor_id: 0x1171,
      device_id: 0x0001,
      connection_state: 'RUNNING',
      slot_count: 16,
    };

    it('shows selection prompt when no RTU selected', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [mockRtu],
      });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('Select an RTU to view details')).toBeInTheDocument();
      });
    });

    it('displays RTU details when selected', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => [mockRtu] })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ healthy: true, packet_loss_percent: 0.5, in_failover: false }) });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('water-rtu-01')).toBeInTheDocument();
      });

      // Click on RTU to select it
      await userEvent.click(screen.getByText('water-rtu-01'));

      await waitFor(() => {
        // Should show details panel with vendor/device IDs
        expect(screen.getByText('Vendor ID')).toBeInTheDocument();
        expect(screen.getByText('Device ID')).toBeInTheDocument();
        expect(screen.getByText('Slot Count')).toBeInTheDocument();
        expect(screen.getByText('16')).toBeInTheDocument();
      });
    });

    it('shows health status when available', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => [mockRtu] })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            station_name: 'water-rtu-01',
            connection_state: 'RUNNING',
            healthy: true,
            packet_loss_percent: 0.5,
            consecutive_failures: 0,
            in_failover: false,
          }),
        });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('water-rtu-01')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('water-rtu-01'));

      await waitFor(() => {
        expect(screen.getByText('Health Status')).toBeInTheDocument();
        expect(screen.getByText('Healthy')).toBeInTheDocument();
        expect(screen.getByText('Packet Loss')).toBeInTheDocument();
      });
    });
  });

  describe('Add RTU Modal', () => {
    it('opens add modal when Add RTU button clicked', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('Add RTU')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Add RTU'));

      expect(screen.getByTestId('add-rtu-modal')).toBeInTheDocument();
    });

    it('closes add modal when cancelled', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('Add RTU')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Add RTU'));
      await userEvent.click(screen.getByText('Cancel'));

      expect(screen.queryByTestId('add-rtu-modal')).not.toBeInTheDocument();
    });

    it('shows success toast after adding RTU', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => [] })
        .mockResolvedValueOnce({ ok: true, json: async () => [] });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('Add RTU')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Add RTU'));
      await userEvent.click(screen.getByText('Add'));

      expect(mockToast.success).toHaveBeenCalledWith(
        'RTU added successfully',
        expect.any(String)
      );
    });
  });

  describe('Delete RTU Modal', () => {
    const mockRtu = {
      station_name: 'water-rtu-01',
      ip_address: '192.168.1.50',
      vendor_id: 0x1171,
      device_id: 0x0001,
      connection_state: 'RUNNING',
      slot_count: 16,
    };

    it('opens delete modal when Delete button clicked', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => [mockRtu] })
        .mockResolvedValueOnce({ ok: true, json: async () => ({}) });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('water-rtu-01')).toBeInTheDocument();
      });

      // Select the RTU first
      await userEvent.click(screen.getByText('water-rtu-01'));

      await waitFor(() => {
        expect(screen.getByText('Delete')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Delete'));

      expect(screen.getByTestId('delete-rtu-modal')).toBeInTheDocument();
      expect(screen.getByText('Delete water-rtu-01?')).toBeInTheDocument();
    });

    it('shows success toast after deleting RTU', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => [mockRtu] })
        .mockResolvedValueOnce({ ok: true, json: async () => ({}) })
        .mockResolvedValueOnce({ ok: true, json: async () => [] });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('water-rtu-01')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('water-rtu-01'));

      await waitFor(() => {
        expect(screen.getByText('Delete')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Delete'));
      await userEvent.click(within(screen.getByTestId('delete-rtu-modal')).getByText('Delete'));

      expect(mockToast.success).toHaveBeenCalledWith(
        'RTU deleted',
        expect.stringContaining('alarm rules')
      );
    });
  });

  describe('Discovery Panel', () => {
    it('toggles discovery panel visibility', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('Scan Network')).toBeInTheDocument();
      });

      // Discovery panel should be hidden initially
      expect(screen.queryByTestId('discovery-panel')).not.toBeInTheDocument();

      // Click to show
      await userEvent.click(screen.getByText('Scan Network'));
      expect(screen.getByTestId('discovery-panel')).toBeInTheDocument();
      expect(screen.getByText('Hide Discovery')).toBeInTheDocument();

      // Click to hide
      await userEvent.click(screen.getByText('Hide Discovery'));
      expect(screen.queryByTestId('discovery-panel')).not.toBeInTheDocument();
    });

    it('prefills add modal when device selected from discovery', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('Scan Network')).toBeInTheDocument();
      });

      // Show discovery panel
      await userEvent.click(screen.getByText('Scan Network'));

      // Select a discovered device
      await userEvent.click(screen.getByText('Select Device'));

      // Add modal should open with prefilled data
      expect(screen.getByTestId('add-rtu-modal')).toBeInTheDocument();
      expect(screen.getByTestId('prefill-name')).toHaveTextContent('discovered-rtu');
    });
  });

  describe('Connect/Disconnect Actions', () => {
    it('shows Connect button for OFFLINE RTU', async () => {
      const offlineRtu = {
        station_name: 'offline-rtu',
        ip_address: '192.168.1.50',
        vendor_id: 0x1171,
        device_id: 0x0001,
        connection_state: 'OFFLINE',
        slot_count: 16,
      };

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => [offlineRtu] })
        .mockResolvedValueOnce({ ok: true, json: async () => ({}) });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('offline-rtu')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('offline-rtu'));

      await waitFor(() => {
        expect(screen.getByText('Connect')).toBeInTheDocument();
      });
    });

    it('shows Disconnect button for RUNNING RTU', async () => {
      const runningRtu = {
        station_name: 'running-rtu',
        ip_address: '192.168.1.50',
        vendor_id: 0x1171,
        device_id: 0x0001,
        connection_state: 'RUNNING',
        slot_count: 16,
      };

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => [runningRtu] })
        .mockResolvedValueOnce({ ok: true, json: async () => ({}) });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('running-rtu')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('running-rtu'));

      await waitFor(() => {
        expect(screen.getByText('Disconnect')).toBeInTheDocument();
      });
    });

    it('calls connect API when Connect clicked', async () => {
      const offlineRtu = {
        station_name: 'offline-rtu',
        ip_address: '192.168.1.50',
        vendor_id: 0x1171,
        device_id: 0x0001,
        connection_state: 'OFFLINE',
        slot_count: 16,
      };

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => [offlineRtu] })
        .mockResolvedValueOnce({ ok: true, json: async () => ({}) })
        .mockResolvedValueOnce({ ok: true })  // Connect call
        .mockResolvedValueOnce({ ok: true, json: async () => [offlineRtu] });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('offline-rtu')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('offline-rtu'));

      await waitFor(() => {
        expect(screen.getByText('Connect')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Connect'));

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          '/api/v1/rtus/offline-rtu/connect',
          { method: 'POST' }
        );
        expect(mockToast.info).toHaveBeenCalledWith(
          'Connecting...',
          expect.any(String)
        );
      });
    });
  });

  describe('Navigation Links', () => {
    it('has link to Setup Wizard', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

      render(<RTUsPage />);

      await waitFor(() => {
        const wizardLink = screen.getByRole('link', { name: 'Setup Wizard' });
        expect(wizardLink).toHaveAttribute('href', '/wizard');
      });
    });

    it('shows Full Details link for selected RTU', async () => {
      const mockRtu = {
        station_name: 'water-rtu-01',
        ip_address: '192.168.1.50',
        vendor_id: 0x1171,
        device_id: 0x0001,
        connection_state: 'RUNNING',
        slot_count: 16,
      };

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: true, json: async () => [mockRtu] })
        .mockResolvedValueOnce({ ok: true, json: async () => ({}) });

      render(<RTUsPage />);

      await waitFor(() => {
        expect(screen.getByText('water-rtu-01')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('water-rtu-01'));

      await waitFor(() => {
        const detailsLink = screen.getByRole('link', { name: 'Full Details' });
        expect(detailsLink).toHaveAttribute('href', '/rtus/water-rtu-01');
      });
    });
  });
});
