/**
 * 404 Not Found Page
 * Displays when a route doesn't exist.
 *
 * ISA-101 Compliance:
 * - Yellow/warning color (not critical, but needs attention)
 * - Clear navigation options
 */

import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen bg-hmi-bg flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-hmi-panel rounded-lg shadow-lg border border-alarm-yellow overflow-hidden text-center">
        {/* Header */}
        <div className="bg-alarm-yellow/10 border-b border-alarm-yellow/30 px-6 py-8">
          <div className="text-6xl font-bold text-alarm-yellow mb-2">404</div>
          <h1 className="text-xl font-semibold text-hmi-text">Page Not Found</h1>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          <p className="text-hmi-text-secondary">
            The page you are looking for does not exist or has been moved.
          </p>

          {/* Navigation Options */}
          <div className="flex flex-col gap-2">
            <Link
              href="/"
              className="w-full px-4 py-3 bg-alarm-blue hover:bg-alarm-blue/90 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
              </svg>
              Go to Dashboard
            </Link>
            <Link
              href="/rtus"
              className="w-full px-4 py-3 bg-hmi-bg-alt hover:bg-hmi-border text-hmi-text font-medium rounded-lg transition-colors"
            >
              View RTUs
            </Link>
            <Link
              href="/alarms"
              className="w-full px-4 py-3 bg-hmi-bg-alt hover:bg-hmi-border text-hmi-text font-medium rounded-lg transition-colors"
            >
              View Alarms
            </Link>
          </div>
        </div>

        {/* Footer */}
        <div className="bg-hmi-bg-alt px-6 py-3 text-xs text-hmi-text-secondary">
          Water Treatment Controller SCADA/HMI
        </div>
      </div>
    </div>
  );
}
