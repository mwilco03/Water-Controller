/**
 * 404 Not Found Page
 * Displays when a route doesn't exist.
 *
 * ISA-101 Compliance:
 * - Yellow/warning color (not critical, but needs attention)
 * - Light background, clear text
 * - Clear navigation options
 */

import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-[60vh] bg-hmi-bg flex items-center justify-center p-4">
      <div className="max-w-sm w-full bg-hmi-panel rounded-lg shadow-lg border border-status-warning overflow-hidden text-center">
        {/* Header - ISA-101: Warning/amber for attention */}
        <div className="bg-status-warning/10 border-b border-status-warning/30 px-4 py-4">
          <div className="text-3xl font-bold text-status-warning mb-1">404</div>
          <h1 className="text-base font-semibold text-hmi-text">Page Not Found</h1>
        </div>

        {/* Content - ISA-101: Light background, dark text */}
        <div className="p-4 space-y-3">
          <p className="text-hmi-muted text-sm">
            The page you are looking for does not exist or has been moved.
          </p>

          {/* Navigation Options */}
          <div className="flex flex-col gap-2">
            <Link
              href="/"
              className="w-full px-3 py-2 bg-status-info hover:bg-status-info/90 text-white text-sm font-medium rounded transition-colors flex items-center justify-center gap-2"
            >
              <span>&#8962;</span>
              Go to Dashboard
            </Link>
            <Link
              href="/rtus"
              className="w-full px-3 py-2 bg-hmi-bg hover:bg-hmi-border text-hmi-text text-sm font-medium rounded transition-colors border border-hmi-border"
            >
              View RTUs
            </Link>
            <Link
              href="/alarms"
              className="w-full px-3 py-2 bg-hmi-bg hover:bg-hmi-border text-hmi-text text-sm font-medium rounded transition-colors border border-hmi-border"
            >
              View Alarms
            </Link>
          </div>
        </div>

        {/* Footer - ISA-101: Subtle gray */}
        <div className="bg-hmi-bg px-4 py-2 text-xs text-hmi-muted border-t border-hmi-border">
          Water Treatment Controller SCADA/HMI
        </div>
      </div>
    </div>
  );
}
