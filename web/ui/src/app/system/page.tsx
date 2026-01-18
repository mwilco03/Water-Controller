'use client';

/**
 * System Status Page
 *
 * Design Philosophy:
 * - TEXT is primary, icons are secondary
 * - Every pixel serves the operator or it's waste
 * - Data quality is always visible
 * - Actions are clear and unambiguous
 *
 * Required Panels:
 * 1. System Health - CPU, PROFINET cycle time, uptime, restart reason
 * 2. Resource Usage - Memory, storage, pending writes
 * 3. RTU Summary - Connected RTUs with navigation
 * 4. Services Health - API, Historian, PROFINET, Alarm service
 */

import { useEffect, useState, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { systemLogger } from '@/lib/logger';
import { useRTUStatusData } from '@/hooks/useRTUStatusData';
import {
  PROFINET_STATES,
  SERVICE_STATES,
  RESOURCE_THRESHOLDS,
  RESTART_REASONS,
  getProfinetStateLabel,
  getProfinetStateClass,
  getServiceStateLabel,
  getServiceStateClass,
  getRestartReasonLabel,
  isAbnormalRestart,
  getResourceHealthStatus,
} from '@/constants/system';
import type { ServiceState, RestartReason } from '@/constants/system';

const PAGE_TITLE = 'System Status - Water Treatment Controller';

// Type definitions
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
  last_restart_reason?: string;
  profinet_state?: string;
  profinet_cycle_time_ms?: number;
  profinet_expected_cycle_ms?: number;
}

interface ServiceStatus {
  name: string;
  status: ServiceState | string;
  description?: string;
  pid?: number | null;
  memory_mb?: number;
  cpu_percent?: number;
  uptime?: string;
}

interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  source: string;
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

// Status indicator styles
const STATUS_CLASSES = {
  ok: { bg: 'bg-status-ok-light', text: 'text-status-ok', dot: 'bg-status-ok' },
  warning: { bg: 'bg-status-warning-light', text: 'text-status-warning', dot: 'bg-status-warning' },
  alarm: { bg: 'bg-status-alarm-light', text: 'text-status-alarm', dot: 'bg-status-alarm' },
  offline: { bg: 'bg-hmi-bg', text: 'text-hmi-muted', dot: 'bg-hmi-equipment' },
};

type StatusType = keyof typeof STATUS_CLASSES;

// Progress bar component
function ProgressBar({
  value,
  status,
  showLabel = true,
}: {
  value: number;
  status: StatusType;
  showLabel?: boolean;
}) {
  const styles = STATUS_CLASSES[status];
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 bg-hmi-bg rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${styles.dot}`}
          style={{ width: `${Math.min(100, value)}%` }}
        />
      </div>
      {showLabel && (
        <span className={`text-sm font-mono font-medium min-w-[3rem] text-right ${styles.text}`}>
          {value.toFixed(1)}%
        </span>
      )}
    </div>
  );
}

// Metric display component
function MetricRow({
  label,
  value,
  unit,
  status,
  sublabel,
}: {
  label: string;
  value: string | number;
  unit?: string;
  status?: StatusType;
  sublabel?: string;
}) {
  const textClass = status ? STATUS_CLASSES[status].text : 'text-hmi-text';
  return (
    <div className="flex justify-between items-baseline py-2 border-b border-hmi-border last:border-0">
      <div>
        <span className="text-hmi-muted text-sm">{label}</span>
        {sublabel && <span className="text-hmi-muted text-xs ml-2">({sublabel})</span>}
      </div>
      <span className={`font-mono font-medium ${textClass}`}>
        {value}
        {unit && <span className="text-hmi-muted text-sm ml-1">{unit}</span>}
      </span>
    </div>
  );
}

// Service status row
function ServiceRow({
  name,
  status,
  description,
  onRestart,
}: {
  name: string;
  status: ServiceState | string;
  description?: string;
  onRestart?: () => void;
}) {
  const statusClass = getServiceStateClass(status);
  const styles = STATUS_CLASSES[statusClass];
  const statusLabel = getServiceStateLabel(status);

  return (
    <div className="flex items-center justify-between p-3 bg-hmi-bg rounded-lg">
      <div className="flex items-center gap-3">
        <span className={`w-2 h-2 rounded-full ${styles.dot}`} />
        <div>
          <div className="font-medium text-hmi-text">{name}</div>
          {description && <div className="text-xs text-hmi-muted">{description}</div>}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className={`text-sm font-medium ${styles.text}`}>{statusLabel}</span>
        {onRestart && (
          <button
            onClick={onRestart}
            className="px-3 py-1 text-xs font-medium text-hmi-text bg-hmi-panel border border-hmi-border rounded hover:bg-hmi-border transition-colors"
          >
            Restart
          </button>
        )}
      </div>
    </div>
  );
}

// RTU status row
function RTURow({
  stationName,
  state,
  ipAddress,
  alarmCount,
}: {
  stationName: string;
  state: string;
  ipAddress?: string;
  alarmCount: number;
}) {
  const isOnline = state === 'RUNNING';
  const isFault = state === 'FAULT' || state === 'ERROR';
  const status: StatusType = isOnline ? 'ok' : isFault ? 'alarm' : 'offline';
  const styles = STATUS_CLASSES[status];

  return (
    <Link
      href={`/rtus/${encodeURIComponent(stationName)}`}
      className="flex items-center justify-between p-3 bg-hmi-bg rounded-lg hover:bg-hmi-border/50 transition-colors"
    >
      <div className="flex items-center gap-3">
        <span className={`w-2 h-2 rounded-full ${styles.dot}`} />
        <div>
          <div className="font-medium text-hmi-text">{stationName}</div>
          {ipAddress && <div className="text-xs text-hmi-muted font-mono">{ipAddress}</div>}
        </div>
      </div>
      <div className="flex items-center gap-3">
        {alarmCount > 0 && (
          <span className="px-2 py-0.5 bg-status-alarm text-white text-xs font-medium rounded">
            {alarmCount} alarm{alarmCount !== 1 ? 's' : ''}
          </span>
        )}
        <span className={`text-sm font-medium ${styles.text}`}>
          {isOnline ? 'Online' : isFault ? 'Fault' : 'Offline'}
        </span>
        <svg className="w-4 h-4 text-hmi-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </div>
    </Link>
  );
}

export default function SystemPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [activeTab, setActiveTab] = useState<'overview' | 'logs' | 'audit' | 'support'>('overview');
  const [logFilter, setLogFilter] = useState<string>('all');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Get RTU data for RTU summary
  const { rtus, alarms } = useRTUStatusData();

  // Set page title
  useEffect(() => {
    document.title = PAGE_TITLE;
  }, []);

  // Fetch functions
  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/system/health');
      if (res.ok) {
        const data = await res.json();
        // Add defaults for missing fields
        setHealth({
          ...data,
          profinet_state: data.profinet_state || PROFINET_STATES.RUN,
          profinet_cycle_time_ms: data.profinet_cycle_time_ms || 1000,
          profinet_expected_cycle_ms: data.profinet_expected_cycle_ms || 1000,
          last_restart_reason: data.last_restart_reason || RESTART_REASONS.NORMAL,
        });
      }
    } catch (error) {
      systemLogger.error('Failed to fetch health', error);
    }
  }, []);

  const fetchServices = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/services');
      if (res.ok) {
        const data = await res.json();
        // Convert to array and add descriptions
        const serviceDescriptions: Record<string, string> = {
          api: 'FastAPI Backend',
          historian: 'Data Recording Service',
          profinet: 'PROFINET I/O Controller',
          alarm: 'Alarm Management Service',
        };
        if (!Array.isArray(data)) {
          const arr = Object.entries(data).map(([name, status]) => ({
            name,
            status: status as string,
            description: serviceDescriptions[name.toLowerCase()] || '',
          }));
          setServices(arr);
        } else {
          setServices(data.map((s: ServiceStatus) => ({
            ...s,
            description: serviceDescriptions[s.name.toLowerCase()] || s.description || '',
          })));
        }
      }
    } catch (error) {
      systemLogger.error('Failed to fetch services', error);
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

  // Initial fetch and polling
  useEffect(() => {
    fetchHealth();
    fetchServices();
    fetchLogs();
    fetchAuditLog();

    let interval: NodeJS.Timeout | null = null;
    if (autoRefresh) {
      interval = setInterval(() => {
        fetchHealth();
        fetchServices();
        if (activeTab === 'logs') fetchLogs();
      }, 5000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, activeTab, fetchHealth, fetchServices, fetchLogs, fetchAuditLog]);

  useEffect(() => {
    fetchLogs();
  }, [logFilter, fetchLogs]);

  // Utility functions
  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const formatUptime = (seconds: number): string => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };

  const formatDate = (dateStr: string) => new Date(dateStr).toLocaleString();

  const getLogLevelClass = (level: string): string => {
    const classes: Record<string, string> = {
      DEBUG: 'text-hmi-muted',
      INFO: 'text-status-info',
      WARNING: 'text-status-warning',
      ERROR: 'text-status-alarm',
      CRITICAL: 'text-white bg-status-alarm px-1 rounded',
    };
    return classes[level] || 'text-hmi-muted';
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
    } catch {
      showMessage('error', 'Error restarting service');
    } finally {
      setLoading(false);
    }
  };

  // Derived values
  const cpuStatus = health ? getResourceHealthStatus(health.cpu_percent, RESOURCE_THRESHOLDS.CPU) : 'offline';
  const memoryStatus = health ? getResourceHealthStatus(health.memory_percent, RESOURCE_THRESHOLDS.MEMORY) : 'offline';
  const diskStatus = health ? getResourceHealthStatus(health.disk_percent, RESOURCE_THRESHOLDS.DISK) : 'offline';

  const profinetStatus = health?.profinet_state
    ? getProfinetStateClass(health.profinet_state)
    : 'offline';

  const cycleTimeOk = health?.profinet_cycle_time_ms !== undefined &&
    health?.profinet_expected_cycle_ms !== undefined &&
    health.profinet_cycle_time_ms <= health.profinet_expected_cycle_ms + RESOURCE_THRESHOLDS.CYCLE_TIME.WARNING_DELTA_MS;

  const abnormalRestart = isAbnormalRestart(health?.last_restart_reason);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-hmi-text">System Status</h1>
          <p className="text-sm text-hmi-muted mt-1">
            PROFINET I/O Controller health and diagnostics
          </p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center text-sm text-hmi-muted cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="mr-2 rounded"
            />
            Auto-refresh (5s)
          </label>
          <button
            onClick={() => {
              fetchHealth();
              fetchServices();
              fetchLogs();
              fetchAuditLog();
            }}
            className="hmi-btn hmi-btn-secondary text-sm"
          >
            Refresh Now
          </button>
        </div>
      </div>

      {/* Message Banner */}
      {message && (
        <div
          className={`p-4 rounded-lg border ${
            message.type === 'success'
              ? 'bg-status-ok-light border-status-ok text-status-ok'
              : 'bg-status-alarm-light border-status-alarm text-status-alarm'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-hmi-border">
        {[
          { id: 'overview', label: 'Overview' },
          { id: 'logs', label: 'System Logs' },
          { id: 'audit', label: 'Audit Trail' },
          { id: 'support', label: 'Support' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'border-b-2 border-status-info text-status-info -mb-px'
                : 'text-hmi-muted hover:text-hmi-text'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* System Health Panel */}
          <div className="hmi-card">
            <div className="hmi-card-header">System Health</div>
            <div className="hmi-card-body space-y-4">
              {/* PROFINET Status */}
              <div className="p-3 bg-hmi-bg rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-hmi-text">PROFINET Controller</span>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    STATUS_CLASSES[profinetStatus].bg
                  } ${STATUS_CLASSES[profinetStatus].text}`}>
                    {health?.profinet_state ? getProfinetStateLabel(health.profinet_state) : 'Unknown'}
                  </span>
                </div>
                {health && (
                  <div className="text-sm text-hmi-muted">
                    Cycle time: <span className={`font-mono ${cycleTimeOk ? 'text-hmi-text' : 'text-status-warning'}`}>
                      {health.profinet_cycle_time_ms}ms
                    </span>
                    <span className="mx-1">/</span>
                    <span className="text-hmi-muted">{health.profinet_expected_cycle_ms}ms expected</span>
                  </div>
                )}
              </div>

              {/* CPU Usage */}
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-hmi-muted">CPU Usage</span>
                  <span className={`font-medium ${STATUS_CLASSES[cpuStatus].text}`}>
                    {health?.cpu_percent.toFixed(1) ?? '--'}%
                  </span>
                </div>
                <ProgressBar
                  value={health?.cpu_percent ?? 0}
                  status={cpuStatus}
                  showLabel={false}
                />
              </div>

              {/* Uptime */}
              <MetricRow
                label="System Uptime"
                value={health ? formatUptime(health.uptime_seconds) : '--'}
              />

              {/* Last Restart Reason */}
              <MetricRow
                label="Last Restart"
                value={getRestartReasonLabel(health?.last_restart_reason)}
                status={abnormalRestart ? 'warning' : undefined}
              />
            </div>
          </div>

          {/* Resource Usage Panel */}
          <div className="hmi-card">
            <div className="hmi-card-header">Resource Usage</div>
            <div className="hmi-card-body space-y-4">
              {/* Memory Usage */}
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-hmi-muted">Memory Usage</span>
                  <span className={`font-medium ${STATUS_CLASSES[memoryStatus].text}`}>
                    {health?.memory_percent.toFixed(1) ?? '--'}%
                  </span>
                </div>
                <ProgressBar
                  value={health?.memory_percent ?? 0}
                  status={memoryStatus}
                  showLabel={false}
                />
              </div>

              {/* Disk Usage */}
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-hmi-muted">Disk Usage</span>
                  <span className={`font-medium ${STATUS_CLASSES[diskStatus].text}`}>
                    {health?.disk_percent.toFixed(1) ?? '--'}%
                  </span>
                </div>
                <ProgressBar
                  value={health?.disk_percent ?? 0}
                  status={diskStatus}
                  showLabel={false}
                />
              </div>

              <div className="border-t border-hmi-border pt-4 space-y-2">
                <MetricRow
                  label="Configuration Database"
                  value={health?.database_size_mb.toFixed(2) ?? '--'}
                  unit="MB"
                />
                <MetricRow
                  label="Historian Data"
                  value={health?.historian_size_mb.toFixed(2) ?? '--'}
                  unit="MB"
                />
              </div>
            </div>
          </div>

          {/* Connected RTUs Panel */}
          <div className="hmi-card">
            <div className="hmi-card-header flex items-center justify-between">
              <span>Connected RTUs</span>
              <Link href="/rtus" className="text-sm text-status-info hover:underline">
                View All
              </Link>
            </div>
            <div className="hmi-card-body">
              {rtus.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-hmi-muted mb-4">No RTUs configured</p>
                  <Link href="/rtus" className="hmi-btn hmi-btn-primary text-sm">
                    Add RTU
                  </Link>
                </div>
              ) : (
                <div className="space-y-2">
                  {rtus.slice(0, 5).map((rtu) => (
                    <RTURow
                      key={rtu.station_name}
                      stationName={rtu.station_name}
                      state={rtu.state}
                      ipAddress={rtu.ip_address}
                      alarmCount={rtu.alarm_count ?? 0}
                    />
                  ))}
                  {rtus.length > 5 && (
                    <Link
                      href="/rtus"
                      className="block text-center text-sm text-status-info hover:underline py-2"
                    >
                      +{rtus.length - 5} more RTUs
                    </Link>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Services Health Panel */}
          <div className="hmi-card">
            <div className="hmi-card-header">Services Health</div>
            <div className="hmi-card-body">
              {services.length === 0 ? (
                <p className="text-hmi-muted text-center py-4">No services configured</p>
              ) : (
                <div className="space-y-2">
                  {services.map((service) => (
                    <ServiceRow
                      key={service.name}
                      name={service.name}
                      status={service.status}
                      description={service.description}
                      onRestart={() => restartService(service.name)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Logs Tab */}
      {activeTab === 'logs' && (
        <div className="hmi-card">
          <div className="hmi-card-header flex items-center justify-between">
            <span>System Logs</span>
            <div className="flex items-center gap-3">
              <select
                value={logFilter}
                onChange={(e) => setLogFilter(e.target.value)}
                className="px-3 py-1.5 bg-hmi-bg border border-hmi-border rounded text-sm"
              >
                <option value="all">All Levels</option>
                <option value="DEBUG">Debug</option>
                <option value="INFO">Info</option>
                <option value="WARNING">Warning</option>
                <option value="ERROR">Error</option>
                <option value="CRITICAL">Critical</option>
              </select>
            </div>
          </div>
          <div className="hmi-card-body">
            <div className="bg-hmi-bg rounded p-4 font-mono text-sm max-h-[500px] overflow-y-auto">
              {logs.length === 0 ? (
                <p className="text-hmi-muted text-center py-8">No log entries</p>
              ) : (
                <table className="w-full">
                  <tbody>
                    {logs.map((log, idx) => (
                      <tr key={idx} className="border-b border-hmi-border last:border-0">
                        <td className="py-2 pr-4 text-hmi-muted text-xs whitespace-nowrap align-top">
                          {formatDate(log.timestamp)}
                        </td>
                        <td className="py-2 pr-4 align-top">
                          <span className={`text-xs font-medium ${getLogLevelClass(log.level)}`}>
                            {log.level}
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-hmi-muted text-xs whitespace-nowrap align-top">
                          [{log.source}]
                        </td>
                        <td className="py-2 text-hmi-text break-all">{log.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Audit Tab */}
      {activeTab === 'audit' && (
        <div className="hmi-card">
          <div className="hmi-card-header">Audit Trail</div>
          <div className="hmi-card-body overflow-x-auto">
            {auditLog.length === 0 ? (
              <p className="text-hmi-muted text-center py-8">No audit entries</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-hmi-muted border-b border-hmi-border">
                    <th className="pb-3 font-medium">Timestamp</th>
                    <th className="pb-3 font-medium">User</th>
                    <th className="pb-3 font-medium">Action</th>
                    <th className="pb-3 font-medium">Resource</th>
                    <th className="pb-3 font-medium">Details</th>
                    <th className="pb-3 font-medium">IP</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLog.map((entry) => (
                    <tr key={entry.id} className="border-b border-hmi-border last:border-0">
                      <td className="py-3 text-hmi-muted whitespace-nowrap">{formatDate(entry.timestamp)}</td>
                      <td className="py-3 text-hmi-text">{entry.user}</td>
                      <td className="py-3">
                        <span className="px-2 py-0.5 bg-hmi-bg rounded text-xs">{entry.action}</span>
                      </td>
                      <td className="py-3 text-hmi-muted">
                        {entry.resource_type}
                        {entry.resource_id && `: ${entry.resource_id}`}
                      </td>
                      <td className="py-3 text-hmi-muted max-w-xs truncate">{entry.details}</td>
                      <td className="py-3 text-hmi-muted font-mono">{entry.ip_address}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Support Tab */}
      {activeTab === 'support' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Contact & Documentation */}
          <div className="hmi-card">
            <div className="hmi-card-header">Support & Documentation</div>
            <div className="hmi-card-body space-y-6">
              <div>
                <h3 className="text-sm font-medium text-hmi-muted uppercase mb-3">Contact</h3>
                <div className="space-y-2">
                  <a
                    href="mailto:support@water-controller.local"
                    className="flex items-center gap-2 text-status-info hover:underline"
                  >
                    support@water-controller.local
                  </a>
                  <a
                    href="https://github.com/mwilco03/Water-Controller/issues"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-status-info hover:underline"
                  >
                    GitHub Issues
                  </a>
                </div>
              </div>
              <div>
                <h3 className="text-sm font-medium text-hmi-muted uppercase mb-3">Documentation</h3>
                <div className="space-y-2">
                  <a href="#" className="block text-status-info hover:underline">Troubleshooting Guide</a>
                  <a href="#" className="block text-status-info hover:underline">Alarm Response Procedures</a>
                  <a href="#" className="block text-status-info hover:underline">Commissioning Procedure</a>
                </div>
              </div>
            </div>
          </div>

          {/* Diagnostic Export */}
          <div className="hmi-card">
            <div className="hmi-card-header">Diagnostic Export</div>
            <div className="hmi-card-body space-y-4">
              <p className="text-sm text-hmi-muted">
                Download system diagnostics for troubleshooting or support requests.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
                    } catch {
                      showMessage('error', 'Failed to download logs');
                    }
                  }}
                  className="hmi-btn hmi-btn-secondary text-sm"
                >
                  Download Logs
                </button>
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
                      a.download = `diagnostic-${new Date().toISOString().split('T')[0]}.json`;
                      a.click();
                      URL.revokeObjectURL(url);
                      showMessage('success', 'Diagnostic report downloaded');
                    } catch {
                      showMessage('error', 'Failed to generate diagnostic');
                    } finally {
                      setLoading(false);
                    }
                  }}
                  disabled={loading}
                  className="hmi-btn hmi-btn-primary text-sm"
                >
                  {loading ? 'Generating...' : 'Full Diagnostic'}
                </button>
              </div>
            </div>
          </div>

          {/* System Info */}
          <div className="hmi-card lg:col-span-2">
            <div className="hmi-card-header">System Information</div>
            <div className="hmi-card-body">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div>
                  <div className="text-sm text-hmi-muted">Version</div>
                  <div className="font-mono text-hmi-text">1.0.0</div>
                </div>
                <div>
                  <div className="text-sm text-hmi-muted">PROFINET Stack</div>
                  <div className="font-mono text-hmi-text">p-net 0.4.0</div>
                </div>
                <div>
                  <div className="text-sm text-hmi-muted">Database</div>
                  <div className="font-mono text-hmi-text">SQLite 3.x</div>
                </div>
                <div>
                  <div className="text-sm text-hmi-muted">Web Server</div>
                  <div className="font-mono text-hmi-text">FastAPI/Uvicorn</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
