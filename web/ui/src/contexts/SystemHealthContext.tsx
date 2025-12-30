'use client';

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';

// Health check polling interval
const HEALTH_CHECK_INTERVAL_MS = 30000; // 30 seconds
const HEALTH_CHECK_TIMEOUT_MS = 5000; // 5 second timeout

// Subsystem status types
export type SubsystemStatus = 'ok' | 'error' | 'warning' | 'missing' | 'disconnected' | 'simulation' | 'uninitialized' | 'unknown';

// Individual subsystem health
export interface SubsystemHealth {
  status: SubsystemStatus;
  message?: string;
  error?: string;
  remedy?: string;
  latency_ms?: number;
  [key: string]: unknown; // Allow additional fields
}

// Overall health response from API
export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  subsystems: {
    database?: SubsystemHealth;
    profinet_controller?: SubsystemHealth;
    persistence?: SubsystemHealth;
    ui_build?: SubsystemHealth;
    [key: string]: SubsystemHealth | undefined;
  };
}

// Context state
interface SystemHealthContextType {
  health: HealthResponse | null;
  isLoading: boolean;
  lastCheck: Date | null;
  error: string | null;

  // Computed states
  isHealthy: boolean;
  isDegraded: boolean;
  isUnhealthy: boolean;
  isApiReachable: boolean;

  // Specific subsystem checks
  isUiBuilt: boolean;
  isControllerConnected: boolean;
  isDatabaseOk: boolean;

  // Degraded mode details
  degradedSubsystems: string[];
  criticalIssues: string[];

  // Actions
  refresh: () => Promise<void>;
}

const SystemHealthContext = createContext<SystemHealthContextType | undefined>(undefined);

interface SystemHealthProviderProps {
  children: ReactNode;
}

export function SystemHealthProvider({ children }: SystemHealthProviderProps) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkHealth = useCallback(async () => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), HEALTH_CHECK_TIMEOUT_MS);

      const response = await fetch('/health', {
        signal: controller.signal,
        headers: {
          'Accept': 'application/json',
        },
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`Health check failed: ${response.status}`);
      }

      const data: HealthResponse = await response.json();
      setHealth(data);
      setError(null);
      setLastCheck(new Date());
    } catch (err) {
      if (err instanceof Error) {
        if (err.name === 'AbortError') {
          setError('Health check timed out');
        } else {
          setError(err.message);
        }
      } else {
        setError('Unknown error checking health');
      }
      // Don't clear existing health data on error - keep last known state
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial check and periodic polling
  useEffect(() => {
    checkHealth();

    const interval = setInterval(checkHealth, HEALTH_CHECK_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [checkHealth]);

  // Computed states
  const isApiReachable = error === null && health !== null;
  const isHealthy = health?.status === 'healthy';
  const isDegraded = health?.status === 'degraded';
  const isUnhealthy = health?.status === 'unhealthy' || !isApiReachable;

  // Specific subsystem checks
  const isUiBuilt = health?.subsystems?.ui_build?.status === 'ok';
  const isControllerConnected = health?.subsystems?.profinet_controller?.status === 'ok' ||
                                health?.subsystems?.profinet_controller?.status === 'simulation';
  const isDatabaseOk = health?.subsystems?.database?.status === 'ok';

  // Get list of degraded subsystems
  const degradedSubsystems: string[] = [];
  const criticalIssues: string[] = [];

  if (health?.subsystems) {
    Object.entries(health.subsystems).forEach(([name, subsystem]) => {
      if (!subsystem) return;

      const displayName = name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

      switch (subsystem.status) {
        case 'error':
        case 'missing':
        case 'uninitialized':
          criticalIssues.push(`${displayName}: ${subsystem.error || subsystem.message || 'Error'}`);
          degradedSubsystems.push(name);
          break;
        case 'disconnected':
        case 'simulation':
          degradedSubsystems.push(name);
          break;
        case 'warning':
          degradedSubsystems.push(name);
          break;
      }
    });
  }

  // Add API unreachable as critical if needed
  if (!isApiReachable && error) {
    criticalIssues.push(`API: ${error}`);
  }

  return (
    <SystemHealthContext.Provider
      value={{
        health,
        isLoading,
        lastCheck,
        error,
        isHealthy,
        isDegraded,
        isUnhealthy,
        isApiReachable,
        isUiBuilt,
        isControllerConnected,
        isDatabaseOk,
        degradedSubsystems,
        criticalIssues,
        refresh: checkHealth,
      }}
    >
      {children}
    </SystemHealthContext.Provider>
  );
}

export function useSystemHealth(): SystemHealthContextType {
  const context = useContext(SystemHealthContext);
  if (context === undefined) {
    throw new Error('useSystemHealth must be used within a SystemHealthProvider');
  }
  return context;
}

// Helper hook for components that need to show degraded state warnings
export function useDegradedMode() {
  const health = useSystemHealth();

  return {
    showWarning: health.isDegraded || health.isUnhealthy,
    severity: health.isUnhealthy ? 'critical' : 'warning',
    issues: health.criticalIssues,
    subsystems: health.degradedSubsystems,
    isApiDown: !health.isApiReachable,
  };
}
