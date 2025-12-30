'use client';

import { useEffect, useState, useCallback } from 'react';
import { systemLogger } from '@/lib/logger';

const PAGE_TITLE = 'System Status - Water Treatment Controller';

interface SystemHealth {
  status: string;
  uptime_seconds: number;
  connected_rtus: number;
  total_rtus: number;
  active_alarms: number;
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  database_size_mb: number;
  historian_size_mb: number;
}

interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  source: string;
}

interface ServiceStatus {
  name: string;
  status: string;
  pid: number | null;
  memory_mb: number;
  cpu_percent: number;
  uptime: string;
}

interface AuditEntry {
  id: number;
  timestamp: string;
  user: string;
  action: string;
  resource_type: string;
  resource_id: string;
  details: string;
  ip_address: string;
}

export default function SystemPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [activeTab, setActiveTab] = useState<'overview' | 'logs' | 'audit' | 'services' | 'support'>('overview');
  const [logFilter, setLogFilter] = useState<string>('all');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Set page title
  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/system/health');
      if (res.ok) {
        setHealth(await res.json());
      }
    } catch (error) {
      systemLogger.error('Failed to fetch health', error);
    }
  }, []);

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/system/logs?limit=100&level=${logFilter}`);
      if (res.ok) {
        setLogs(await res.json());
      }
    } catch (error) {
      systemLogger.error('Failed to fetch logs', error);
    }
  }, [logFilter]);

  const fetchServices = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/services');
      if (res.ok) {
        const data = await res.json();
        // Convert object to array if needed
        if (!Array.isArray(data)) {
          const arr = Object.entries(data).map(([name, status]) => ({
            name,
            status: status as string,
            pid: null,
            memory_mb: 0,
            cpu_percent: 0,
            uptime: '',
          }));
          setServices(arr);
        } else {
          setServices(data);
        }
      }
    } catch (error) {
      systemLogger.error('Failed to fetch services', error);
    }
  }, []);

  const fetchAuditLog = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/system/audit?limit=50');
      if (res.ok) {
        setAuditLog(await res.json());
      }
    } catch (error) {
      systemLogger.error('Failed to fetch audit log', error);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    fetchLogs();
    fetchServices();
    fetchAuditLog();

    let interval: NodeJS.Timeout | null = null;
    if (autoRefresh) {
      interval = setInterval(() => {
        fetchHealth();
        if (activeTab === 'logs') fetchLogs();
        if (activeTab === 'services') fetchServices();
      }, 5000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, activeTab, fetchHealth, fetchLogs, fetchServices, fetchAuditLog]);

  useEffect(() => {
    fetchLogs();
  }, [logFilter, fetchLogs]);

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const restartService = async (serviceName: string) => {
    if (!confirm(`Restart service "${serviceName}"?`)) return;

    setLoading(true);
    try {
      const res = await fetch(`/api/v1/services/${serviceName}/restart`, { method: 'POST' });
      if (res.ok) {
        showMessage('success', `Service ${serviceName} restarting...`);
        setTimeout(fetchServices, 2000);
      } else {
        showMessage('error', `Failed to restart ${serviceName}`);
      }
    } catch (error) {
      showMessage('error', 'Error restarting service');
    } finally {
      setLoading(false);
    }
  };

  const clearLogs = async () => {
    if (!confirm('Clear all system logs?')) return;

    try {
      const res = await fetch('/api/v1/system/logs', { method: 'DELETE' });
      if (res.ok) {
        showMessage('success', 'Logs cleared');
        fetchLogs();
      } else {
        showMessage('error', 'Failed to clear logs');
      }
    } catch (error) {
      showMessage('error', 'Error clearing logs');
    }
  };

  const formatUptime = (seconds: number): string => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (days > 0) {
      return `${days}d ${hours}h ${minutes}m`;
    }
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    return `${minutes}m`;
  };

  const getHealthColor = (value: number, thresholds: { warning: number; critical: number }) => {
    if (value >= thresholds.critical) return 'text-red-400';
    if (value >= thresholds.warning) return 'text-yellow-400';
    return 'text-green-400';
  };

  const getLogLevelBadge = (level: string) => {
    const colors: { [key: string]: string } = {
      DEBUG: 'bg-gray-700 text-gray-300',
      INFO: 'bg-blue-900 text-blue-300',
      WARNING: 'bg-yellow-900 text-yellow-300',
      ERROR: 'bg-red-900 text-red-300',
      CRITICAL: 'bg-red-700 text-red-100',
    };
    return colors[level] || 'bg-gray-700 text-gray-300';
  };

  const getServiceStatusBadge = (status: string) => {
    const colors: { [key: string]: string } = {
      active: 'bg-green-900 text-green-300',
      running: 'bg-green-900 text-green-300',
      inactive: 'bg-gray-700 text-gray-300',
      stopped: 'bg-gray-700 text-gray-300',
      failed: 'bg-red-900 text-red-300',
      error: 'bg-red-900 text-red-300',
    };
    return colors[status.toLowerCase()] || 'bg-gray-700 text-gray-300';
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-white">System Status</h1>
        <div className="flex items-center space-x-4">
          <label className="flex items-center text-sm text-gray-300">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="mr-2"
            />
            Auto-refresh
          </label>
          <button
            onClick={() => {
              fetchHealth();
              fetchLogs();
              fetchServices();
              fetchAuditLog();
            }}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white"
          >
            Refresh Now
          </button>
        </div>
      </div>

      {/* Message Banner */}
      {message && (
        <div
          className={`p-4 rounded-lg ${
            message.type === 'success' ? 'bg-green-900 text-green-200' : 'bg-red-900 text-red-200'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Health Overview Cards */}
      {health && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <div className="scada-panel p-4">
            <div className="text-sm text-gray-400">Status</div>
            <div
              className={`text-xl font-bold ${
                health.status === 'healthy' ? 'text-green-400' : 'text-red-400'
              }`}
            >
              {health.status.toUpperCase()}
            </div>
          </div>

          <div className="scada-panel p-4">
            <div className="text-sm text-gray-400">Uptime</div>
            <div className="text-xl font-bold text-white">{formatUptime(health.uptime_seconds)}</div>
          </div>

          <div className="scada-panel p-4">
            <div className="text-sm text-gray-400">RTUs Connected</div>
            <div
              className={`text-xl font-bold ${
                health.connected_rtus === health.total_rtus ? 'text-green-400' : 'text-yellow-400'
              }`}
            >
              {health.connected_rtus} / {health.total_rtus}
            </div>
          </div>

          <div className="scada-panel p-4">
            <div className="text-sm text-gray-400">Active Alarms</div>
            <div
              className={`text-xl font-bold ${
                health.active_alarms === 0 ? 'text-green-400' : 'text-red-400'
              }`}
            >
              {health.active_alarms}
            </div>
          </div>

          <div className="scada-panel p-4">
            <div className="text-sm text-gray-400">CPU Usage</div>
            <div className={`text-xl font-bold ${getHealthColor(health.cpu_percent, { warning: 70, critical: 90 })}`}>
              {health.cpu_percent.toFixed(1)}%
            </div>
          </div>

          <div className="scada-panel p-4">
            <div className="text-sm text-gray-400">Memory Usage</div>
            <div className={`text-xl font-bold ${getHealthColor(health.memory_percent, { warning: 80, critical: 95 })}`}>
              {health.memory_percent.toFixed(1)}%
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex space-x-4 border-b border-gray-700">
        {[
          { id: 'overview', label: 'Overview' },
          { id: 'services', label: 'Services' },
          { id: 'logs', label: 'System Logs' },
          { id: 'audit', label: 'Audit Log' },
          { id: 'support', label: 'Support' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={`px-4 py-2 -mb-px ${
              activeTab === tab.id
                ? 'border-b-2 border-blue-500 text-blue-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && health && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Storage Info */}
          <div className="scada-panel p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Storage</h2>
            <div className="space-y-4">
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-400">Disk Usage</span>
                  <span className={getHealthColor(health.disk_percent, { warning: 80, critical: 95 })}>
                    {health.disk_percent.toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${
                      health.disk_percent >= 95 ? 'bg-red-500' : health.disk_percent >= 80 ? 'bg-yellow-500' : 'bg-green-500'
                    }`}
                    style={{ width: `${health.disk_percent}%` }}
                  />
                </div>
              </div>

              <div className="flex justify-between py-2 border-t border-gray-700">
                <span className="text-gray-400">Configuration Database</span>
                <span className="text-white">{health.database_size_mb.toFixed(2)} MB</span>
              </div>

              <div className="flex justify-between py-2 border-t border-gray-700">
                <span className="text-gray-400">Historian Data</span>
                <span className="text-white">{health.historian_size_mb.toFixed(2)} MB</span>
              </div>
            </div>
          </div>

          {/* System Info */}
          <div className="scada-panel p-6">
            <h2 className="text-lg font-semibold text-white mb-4">System Information</h2>
            <div className="space-y-3">
              <div className="flex justify-between py-2 border-b border-gray-700">
                <span className="text-gray-400">Version</span>
                <span className="text-white">1.0.0</span>
              </div>
              <div className="flex justify-between py-2 border-b border-gray-700">
                <span className="text-gray-400">PROFINET Stack</span>
                <span className="text-white">p-net 0.4.0</span>
              </div>
              <div className="flex justify-between py-2 border-b border-gray-700">
                <span className="text-gray-400">Database</span>
                <span className="text-white">SQLite 3.x</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-gray-400">Web Server</span>
                <span className="text-white">FastAPI / Uvicorn</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Services Tab */}
      {activeTab === 'services' && (
        <div className="scada-panel p-6">
          <h2 className="text-lg font-semibold text-white mb-4">System Services</h2>

          {services.length === 0 ? (
            <p className="text-gray-400">No services configured</p>
          ) : (
            <div className="space-y-3">
              {services.map((service) => (
                <div
                  key={service.name}
                  className="flex items-center justify-between p-4 bg-gray-800 rounded"
                >
                  <div>
                    <div className="font-medium text-white">{service.name}</div>
                    {service.uptime && (
                      <div className="text-xs text-gray-500">Uptime: {service.uptime}</div>
                    )}
                  </div>
                  <div className="flex items-center space-x-4">
                    {service.memory_mb > 0 && (
                      <span className="text-sm text-gray-400">
                        {service.memory_mb.toFixed(1)} MB
                      </span>
                    )}
                    <span
                      className={`px-2 py-1 rounded text-xs ${getServiceStatusBadge(service.status)}`}
                    >
                      {service.status}
                    </span>
                    <button
                      onClick={() => restartService(service.name)}
                      disabled={loading}
                      className="px-3 py-1 bg-yellow-600 hover:bg-yellow-700 rounded text-sm text-white disabled:opacity-50"
                    >
                      Restart
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Logs Tab */}
      {activeTab === 'logs' && (
        <div className="scada-panel p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-white">System Logs</h2>
            <div className="flex items-center space-x-4">
              <select
                value={logFilter}
                onChange={(e) => setLogFilter(e.target.value)}
                className="px-3 py-1 bg-gray-800 border border-gray-700 rounded text-white text-sm"
              >
                <option value="all">All Levels</option>
                <option value="DEBUG">Debug</option>
                <option value="INFO">Info</option>
                <option value="WARNING">Warning</option>
                <option value="ERROR">Error</option>
                <option value="CRITICAL">Critical</option>
              </select>
              <button
                onClick={clearLogs}
                className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm text-white"
              >
                Clear Logs
              </button>
            </div>
          </div>

          <div className="bg-gray-950 rounded p-4 font-mono text-sm max-h-[500px] overflow-y-auto">
            {logs.length === 0 ? (
              <p className="text-gray-500">No log entries</p>
            ) : (
              logs.map((log, idx) => (
                <div key={idx} className="flex items-start gap-3 py-1 border-b border-gray-800">
                  <span className="text-gray-500 text-xs whitespace-nowrap">
                    {formatDate(log.timestamp)}
                  </span>
                  <span className={`px-1 rounded text-xs ${getLogLevelBadge(log.level)}`}>
                    {log.level}
                  </span>
                  <span className="text-gray-400 text-xs">[{log.source}]</span>
                  <span className="text-gray-200 flex-1">{log.message}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Audit Tab */}
      {activeTab === 'audit' && (
        <div className="scada-panel p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Audit Log</h2>

          <table className="w-full">
            <thead>
              <tr className="text-left text-gray-400 text-sm border-b border-gray-700">
                <th className="pb-3">Timestamp</th>
                <th className="pb-3">User</th>
                <th className="pb-3">Action</th>
                <th className="pb-3">Resource</th>
                <th className="pb-3">Details</th>
                <th className="pb-3">IP Address</th>
              </tr>
            </thead>
            <tbody>
              {auditLog.map((entry) => (
                <tr key={entry.id} className="border-b border-gray-800">
                  <td className="py-3 text-gray-400 text-sm">{formatDate(entry.timestamp)}</td>
                  <td className="py-3 text-white">{entry.user}</td>
                  <td className="py-3">
                    <span className="px-2 py-1 bg-gray-700 rounded text-xs text-gray-300">
                      {entry.action}
                    </span>
                  </td>
                  <td className="py-3 text-gray-400 text-sm">
                    {entry.resource_type}
                    {entry.resource_id && `: ${entry.resource_id}`}
                  </td>
                  <td className="py-3 text-gray-400 text-sm max-w-xs truncate">{entry.details}</td>
                  <td className="py-3 text-gray-500 text-sm font-mono">{entry.ip_address}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {auditLog.length === 0 && (
            <p className="text-gray-400 text-center py-8">No audit entries</p>
          )}
        </div>
      )}

      {/* Support Tab */}
      {activeTab === 'support' && (
        <div className="space-y-6">
          {/* Support Information */}
          <div className="scada-panel p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Support & Documentation</h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Contact Information */}
              <div className="space-y-4">
                <h3 className="text-sm font-medium text-gray-400 uppercase">Contact Support</h3>
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                    <a href="mailto:support@water-controller.local" className="text-sky-400 hover:text-sky-300">
                      support@water-controller.local
                    </a>
                  </div>
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                    </svg>
                    <a href="https://github.com/mwilco03/Water-Controller/issues" target="_blank" rel="noopener noreferrer" className="text-sky-400 hover:text-sky-300">
                      GitHub Issues
                    </a>
                  </div>
                </div>
              </div>

              {/* Documentation Links */}
              <div className="space-y-4">
                <h3 className="text-sm font-medium text-gray-400 uppercase">Documentation</h3>
                <div className="space-y-2">
                  <a href="https://github.com/mwilco03/Water-Controller/blob/main/docs/TROUBLESHOOTING_GUIDE.md" target="_blank" rel="noopener noreferrer" className="block text-sky-400 hover:text-sky-300">
                    Troubleshooting Guide →
                  </a>
                  <a href="https://github.com/mwilco03/Water-Controller/blob/main/docs/ALARM_RESPONSE_PROCEDURES.md" target="_blank" rel="noopener noreferrer" className="block text-sky-400 hover:text-sky-300">
                    Alarm Response Procedures →
                  </a>
                  <a href="https://github.com/mwilco03/Water-Controller/blob/main/docs/COMMISSIONING_PROCEDURE.md" target="_blank" rel="noopener noreferrer" className="block text-sky-400 hover:text-sky-300">
                    Commissioning Procedure →
                  </a>
                </div>
              </div>
            </div>
          </div>

          {/* Diagnostic Data Export */}
          <div className="scada-panel p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Diagnostic Data Export</h2>
            <p className="text-gray-400 mb-4">
              Download system logs and diagnostic information for troubleshooting or support requests.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Download System Logs */}
              <button
                onClick={async () => {
                  try {
                    const res = await fetch('/api/v1/system/logs?limit=1000&format=text');
                    if (res.ok) {
                      const text = await res.text();
                      const blob = new Blob([text], { type: 'text/plain' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `system-logs-${new Date().toISOString().split('T')[0]}.txt`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }
                  } catch (error) {
                    setMessage({ type: 'error', text: 'Failed to download logs' });
                  }
                }}
                className="flex items-center justify-center gap-2 px-4 py-3 bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Download System Logs
              </button>

              {/* Download Audit Trail */}
              <button
                onClick={async () => {
                  try {
                    const res = await fetch('/api/v1/system/audit?limit=1000&format=csv');
                    if (res.ok) {
                      const text = await res.text();
                      const blob = new Blob([text], { type: 'text/csv' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `audit-log-${new Date().toISOString().split('T')[0]}.csv`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }
                  } catch (error) {
                    setMessage({ type: 'error', text: 'Failed to download audit log' });
                  }
                }}
                className="flex items-center justify-center gap-2 px-4 py-3 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Download Audit Trail
              </button>

              {/* Download Full Diagnostic */}
              <button
                onClick={async () => {
                  try {
                    setLoading(true);
                    const [healthRes, logsRes, servicesRes] = await Promise.all([
                      fetch('/api/v1/system/health'),
                      fetch('/api/v1/system/logs?limit=500'),
                      fetch('/api/v1/services'),
                    ]);

                    const diagnostic = {
                      generated_at: new Date().toISOString(),
                      version: '1.0.0',
                      health: healthRes.ok ? await healthRes.json() : null,
                      logs: logsRes.ok ? await logsRes.json() : [],
                      services: servicesRes.ok ? await servicesRes.json() : [],
                    };

                    const blob = new Blob([JSON.stringify(diagnostic, null, 2)], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `diagnostic-report-${new Date().toISOString().split('T')[0]}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                    setMessage({ type: 'success', text: 'Diagnostic report downloaded' });
                  } catch (error) {
                    setMessage({ type: 'error', text: 'Failed to generate diagnostic report' });
                  } finally {
                    setLoading(false);
                  }
                }}
                disabled={loading}
                className="flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-600 text-white rounded-lg transition-colors"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                {loading ? 'Generating...' : 'Full Diagnostic Report'}
              </button>
            </div>
          </div>

          {/* System Information */}
          <div className="scada-panel p-6">
            <h2 className="text-lg font-semibold text-white mb-4">System Information</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <span className="text-gray-400">Version</span>
                <div className="text-white font-mono">1.0.0</div>
              </div>
              <div>
                <span className="text-gray-400">Build Date</span>
                <div className="text-white font-mono">{new Date().toISOString().split('T')[0]}</div>
              </div>
              <div>
                <span className="text-gray-400">Uptime</span>
                <div className="text-white font-mono">{health ? `${Math.floor(health.uptime_seconds / 3600)}h ${Math.floor((health.uptime_seconds % 3600) / 60)}m` : '--'}</div>
              </div>
              <div>
                <span className="text-gray-400">Connected RTUs</span>
                <div className="text-white font-mono">{health ? `${health.connected_rtus}/${health.total_rtus}` : '--'}</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
