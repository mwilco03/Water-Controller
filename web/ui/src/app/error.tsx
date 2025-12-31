'use client';

/**
 * Global Error Boundary
 * Catches unhandled errors at the route level and provides recovery options.
 *
 * ISA-101 Compliance:
 * - Errors are displayed prominently (red header per ISA-101)
 * - Light background, clear text for readability
 * - Clear action buttons for recovery
 * - Error details available for troubleshooting
 */

import { useEffect } from 'react';

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function Error({ error, reset }: ErrorProps) {
  useEffect(() => {
    // Log error to monitoring service in production
    if (process.env.NODE_ENV === 'production') {
      // Send to error tracking service
      fetch('/api/v1/system/log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          level: 'error',
          message: error.message,
          stack: error.stack,
          digest: error.digest,
          timestamp: new Date().toISOString(),
          source: 'frontend',
        }),
      }).catch(() => {
        // Silently fail - don't create error loops
      });
    }
  }, [error]);

  return (
    <div className="min-h-screen bg-hmi-bg flex items-center justify-center p-6">
      <div className="max-w-lg w-full bg-hmi-panel rounded-lg shadow-lg border-2 border-status-alarm overflow-hidden">
        {/* Error Header - ISA-101: Red for critical/alarm state */}
        <div className="bg-status-alarm px-6 py-4">
          <div className="flex items-center gap-3">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <h1 className="text-xl font-bold text-white">System Error</h1>
              <p className="text-red-100 text-sm">An unexpected error has occurred</p>
            </div>
          </div>
        </div>

        {/* Error Content - ISA-101: Light background, dark text */}
        <div className="p-6 space-y-4">
          {/* Error Message */}
          <div className="bg-quality-bad border border-status-alarm/30 rounded-lg p-4">
            <h2 className="text-sm font-medium text-hmi-muted mb-1">Error Details</h2>
            <p className="text-hmi-text font-mono text-sm break-words">
              {error.message || 'An unknown error occurred'}
            </p>
            {error.digest && (
              <p className="text-xs text-hmi-muted mt-2">
                Error ID: <span className="font-mono">{error.digest}</span>
              </p>
            )}
          </div>

          {/* Recovery Instructions */}
          <div className="text-sm text-hmi-muted">
            <p>The HMI encountered an error. You can:</p>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li>Try again to reload this page</li>
              <li>Return to the main dashboard</li>
              <li>Contact support if the problem persists</li>
            </ul>
          </div>

          {/* Action Buttons - ISA-101: Clear, high-contrast buttons */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={reset}
              className="flex-1 px-4 py-3 bg-status-info hover:bg-status-info/90 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Try Again
            </button>
            <a
              href="/"
              className="flex-1 px-4 py-3 bg-hmi-bg hover:bg-hmi-border text-hmi-text font-medium rounded-lg transition-colors flex items-center justify-center gap-2 border border-hmi-border"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
              </svg>
              Dashboard
            </a>
          </div>

          {/* Support Link */}
          <div className="text-center pt-2">
            <a
              href="/system?tab=support"
              className="text-sm text-status-info hover:text-status-info/80 transition-colors"
            >
              Contact Support &rarr;
            </a>
          </div>
        </div>

        {/* Footer - ISA-101: Subtle gray background */}
        <div className="bg-hmi-bg px-6 py-3 text-xs text-hmi-muted text-center border-t border-hmi-border">
          Water Treatment Controller SCADA/HMI
        </div>
      </div>
    </div>
  );
}
