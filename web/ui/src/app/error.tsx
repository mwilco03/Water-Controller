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
      fetch('/api/v1/system/logs', {
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
            <span className="w-8 h-8 flex items-center justify-center text-white text-2xl font-bold">!</span>
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
              <span className="text-lg">&#8635;</span>
              Try Again
            </button>
            <a
              href="/"
              className="flex-1 px-4 py-3 bg-hmi-bg hover:bg-hmi-border text-hmi-text font-medium rounded-lg transition-colors flex items-center justify-center gap-2 border border-hmi-border"
            >
              <span className="text-lg">&#8962;</span>
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
