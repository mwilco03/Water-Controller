'use client';

interface RTUSensorData {
  slot: number;
  name: string;
  value: number;
  unit: string;
  quality: string;
}

interface RTUDevice {
  station_name: string;
  ip_address: string;
  state: string;
  slot_count: number;
  sensors?: RTUSensorData[];
}

interface Props {
  rtus: RTUDevice[];
  onReconnect?: (stationName: string) => void;
}

export default function RTUOverview({ rtus, onReconnect }: Props) {
  const getStateClass = (state: string) => {
    switch (state) {
      case 'RUNNING':
        return 'online';
      case 'CONNECTING':
      case 'DISCOVERY':
        return 'connecting';
      default:
        return 'offline';
    }
  };

  const getStateLabel = (state: string) => {
    switch (state) {
      case 'RUNNING':
        return 'Online';
      case 'CONNECTING':
        return 'Connecting';
      case 'DISCOVERY':
        return 'Discovering';
      case 'ERROR':
        return 'Error';
      default:
        return 'Offline';
    }
  };

  return (
    <div className="scada-panel p-4">
      <h2 className="text-lg font-semibold mb-4 text-white">RTU Network Status</h2>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-left text-gray-400 text-sm border-b border-scada-accent">
              <th className="pb-3 pr-4">Status</th>
              <th className="pb-3 pr-4">Station Name</th>
              <th className="pb-3 pr-4">IP Address</th>
              <th className="pb-3 pr-4">Slots</th>
              <th className="pb-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rtus.map((rtu) => (
              <tr
                key={rtu.station_name}
                className="border-b border-scada-accent/50 hover:bg-scada-accent/30 transition-colors"
              >
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-2">
                    <span className={`status-indicator ${getStateClass(rtu.state)}`} />
                    <span className="text-sm text-gray-300">
                      {getStateLabel(rtu.state)}
                    </span>
                  </div>
                </td>
                <td className="py-3 pr-4 font-medium text-white">
                  {rtu.station_name}
                </td>
                <td className="py-3 pr-4 text-gray-300 font-mono text-sm">
                  {rtu.ip_address || 'N/A'}
                </td>
                <td className="py-3 pr-4 text-gray-300">
                  {rtu.slot_count} slots
                </td>
                <td className="py-3">
                  <div className="flex gap-2">
                    <a
                      href={`/rtus/${rtu.station_name}`}
                      className="text-xs bg-scada-accent hover:bg-scada-highlight px-3 py-1 rounded transition-colors"
                    >
                      Details
                    </a>
                    {onReconnect && (
                      <button
                        className="text-xs bg-scada-accent hover:bg-scada-highlight px-3 py-1 rounded transition-colors"
                        onClick={() => onReconnect(rtu.station_name)}
                        aria-label={`Reconnect to ${rtu.station_name}`}
                      >
                        Reconnect
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {rtus.length === 0 && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-gray-400">
                  No RTU devices found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
