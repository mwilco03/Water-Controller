'use client';

/**
 * I/O Tags Configuration Page (disabled)
 *
 * Disabled: requires refactoring from removed /api/v1/rtus/{name}/slots
 * endpoints to the sensors/controls API. Slots are PROFINET frame
 * positions per CLAUDE.md, not database entities.
 *
 * Implementation path: use /api/v1/rtus/{name}/sensors and
 * /api/v1/rtus/{name}/controls with slot_number as metadata.
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
