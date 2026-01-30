'use client';

/**
 * User Management Page (disabled)
 *
 * Disabled: requires backend user CRUD endpoints (/api/v1/users).
 * Current auth uses the hardcoded credential per CLAUDE.md.
 * Needs fastapi-users or equivalent before this page can function.
 */

export default function UsersPage() {
  return (
    <div className="p-6">
      <div className="max-w-2xl mx-auto">
        <div className="bg-yellow-900/20 border border-yellow-600/50 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <span className="text-yellow-500 text-2xl">[!]</span>
            <div>
              <h1 className="text-xl font-bold text-yellow-400 mb-2">
                User Management - Not Available
              </h1>
              <p className="text-gray-300 mb-4">
                User management requires a backend implementation.
                Recommended: fastapi-users library or Keycloak.
              </p>
              <div className="text-sm text-gray-400 space-y-1">
                <p><strong>Current authentication:</strong></p>
                <ul className="list-disc list-inside ml-2">
                  <li>Single hardcoded user (per CLAUDE.md - dev/test system)</li>
                  <li>Session-based auth via /auth/login</li>
                  <li>Control actions logged to command_audit table</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
