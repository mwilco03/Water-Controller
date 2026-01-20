'use client';

/**
 * TODO: I/O Tags Configuration Page
 *
 * This page is disabled because it calls non-existent backend endpoints.
 *
 * BACKGROUND:
 * The original implementation called /api/v1/rtus/{name}/slots endpoints,
 * but per architectural decision (CLAUDE.md), slots are PROFINET frame
 * positions, NOT database entities. The slots endpoints were removed.
 *
 * TO IMPLEMENT:
 * 1. Refactor to use /api/v1/rtus/{name}/sensors and /api/v1/rtus/{name}/controls
 * 2. Display sensors/controls with their slot_number as metadata
 * 3. Allow editing sensor/control configuration (scaling, alarms, etc.)
 * 4. Historian tag configuration can stay as-is (/api/v1/trends/tags works)
 *
 * ORIGINAL FILE: 32KB of commented code removed for clarity.
 * See git history for original implementation.
 */

export default function IOTagsPage() {
  return (
    <div className="p-6">
      <div className="max-w-2xl mx-auto">
        <div className="bg-yellow-900/20 border border-yellow-600/50 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <span className="text-yellow-500 text-2xl">[!]</span>
            <div>
              <h1 className="text-xl font-bold text-yellow-400 mb-2">
                I/O Tags Configuration - Not Available
              </h1>
              <p className="text-gray-300 mb-4">
                This feature requires refactoring to use the sensors/controls API
                instead of the removed slots endpoints.
              </p>
              <div className="text-sm text-gray-400 space-y-1">
                <p><strong>Current workaround:</strong></p>
                <ul className="list-disc list-inside ml-2">
                  <li>View sensors: RTU details page → Sensors tab</li>
                  <li>View controls: RTU details page → Controls tab</li>
                  <li>Historian tags: Trends page → Tag configuration</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
