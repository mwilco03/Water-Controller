'use client';

import { useState } from 'react';
import { useDegradedMode, useSystemHealth } from '@/contexts/SystemHealthContext';

/**
 * DegradedModeBanner - Operator-visible warning when system is degraded
 *
 * This component displays a prominent warning banner when any subsystem
 * is in a degraded or error state. This ensures operators are always
 * aware of system issues and cannot mistake a partially-functional
 * UI for a healthy system.
 *
 * ISA-101 compliant: Uses alarm colors (yellow for warning, red for critical)
 */
export default function DegradedModeBanner() {
  const { showWarning, severity, issues, subsystems, isApiDown } = useDegradedMode();
  const { lastCheck, refresh, isLoading } = useSystemHealth();
  const [isExpanded, setIsExpanded] = useState(false);

  // Don't render if system is healthy
  if (!showWarning) {
    return null;
  }

  // Determine colors based on severity
  const colorClasses = severity === 'critical'
    ? 'bg-red-600 text-white border-red-700'
    : 'bg-yellow-500 text-yellow-900 border-yellow-600';

  const iconColorClass = severity === 'critical' ? 'text-white' : 'text-yellow-900';

  // Format last check time
  const formatLastCheck = () => {
    if (!lastCheck) return 'Never';
    const now = new Date();
    const diffSeconds = Math.floor((now.getTime() - lastCheck.getTime()) / 1000);
    if (diffSeconds < 60) return `${diffSeconds}s ago`;
    if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
    return lastCheck.toLocaleTimeString();
  };

  return (
    <div
      className={`sticky top-0 z-[60] px-4 py-2 border-b ${colorClasses}`}
      role="alert"
      aria-live="assertive"
    >
      <div className="flex items-center justify-between max-w-[1800px] mx-auto">
        {/* Left side - Icon and status */}
        <div className="flex items-center gap-3">
          {/* Warning/Error icon */}
          <div className={`flex-shrink-0 ${iconColorClass}`}>
            {severity === 'critical' ? (
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
            ) : (
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                  clipRule="evenodd"
                />
              </svg>
            )}
          </div>

          {/* Status text */}
          <div>
            <span className="font-bold text-sm uppercase tracking-wide">
              {severity === 'critical' ? 'SYSTEM ERROR' : 'SYSTEM DEGRADED'}
            </span>
            {isApiDown && (
              <span className="ml-2 text-sm opacity-90">
                - Backend API unreachable
              </span>
            )}
            {!isApiDown && issues.length > 0 && (
              <span className="ml-2 text-sm opacity-90">
                - {issues.length} issue{issues.length !== 1 ? 's' : ''} detected
              </span>
            )}
          </div>
        </div>

        {/* Right side - Actions */}
        <div className="flex items-center gap-4">
          {/* Last check time */}
          <span className="text-xs opacity-75">
            Checked: {formatLastCheck()}
          </span>

          {/* Refresh button */}
          <button
            onClick={() => refresh()}
            disabled={isLoading}
            className={`px-2 py-1 rounded text-sm font-medium transition-colors ${
              severity === 'critical'
                ? 'bg-white/20 hover:bg-white/30 disabled:opacity-50'
                : 'bg-yellow-600/20 hover:bg-yellow-600/30 disabled:opacity-50'
            }`}
            aria-label="Refresh health check"
          >
            {isLoading ? (
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            )}
          </button>

          {/* Expand/collapse button */}
          {(issues.length > 0 || subsystems.length > 0) && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                severity === 'critical'
                  ? 'bg-white/20 hover:bg-white/30'
                  : 'bg-yellow-600/20 hover:bg-yellow-600/30'
              }`}
              aria-expanded={isExpanded}
              aria-controls="degraded-details"
            >
              {isExpanded ? 'Hide Details' : 'Show Details'}
              <svg
                className={`w-4 h-4 inline-block ml-1 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Expanded details panel */}
      {isExpanded && (issues.length > 0 || subsystems.length > 0) && (
        <div
          id="degraded-details"
          className={`mt-3 pt-3 border-t max-w-[1800px] mx-auto ${
            severity === 'critical' ? 'border-red-500/50' : 'border-yellow-600/50'
          }`}
        >
          {/* Critical issues */}
          {issues.length > 0 && (
            <div className="mb-3">
              <h4 className="text-xs font-bold uppercase tracking-wide mb-2 opacity-75">
                Issues Detected
              </h4>
              <ul className="space-y-1">
                {issues.map((issue, index) => (
                  <li key={index} className="text-sm flex items-start gap-2">
                    <span className="flex-shrink-0 mt-0.5">
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                      </svg>
                    </span>
                    <span>{issue}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Affected subsystems */}
          {subsystems.length > 0 && (
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wide mb-2 opacity-75">
                Affected Subsystems
              </h4>
              <div className="flex flex-wrap gap-2">
                {subsystems.map((subsystem) => (
                  <span
                    key={subsystem}
                    className={`px-2 py-1 rounded text-xs font-medium ${
                      severity === 'critical'
                        ? 'bg-red-500/30'
                        : 'bg-yellow-600/30'
                    }`}
                  >
                    {subsystem.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Operator guidance */}
          <div className="mt-3 pt-3 border-t border-current/20">
            <p className="text-xs opacity-75">
              {severity === 'critical' ? (
                <>
                  <strong>Action Required:</strong> The system is not operating correctly.
                  Contact your system administrator or check the system logs for more information.
                </>
              ) : (
                <>
                  <strong>Note:</strong> The system is operating in a degraded state.
                  Some features may be unavailable or display stale data.
                </>
              )}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
