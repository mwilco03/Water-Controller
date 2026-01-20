'use client';

/**
 * TODO: User Management Page
 *
 * This page is disabled because it calls non-existent backend endpoints.
 *
 * MISSING BACKEND:
 * - GET/POST/PUT/DELETE /api/v1/users
 * - GET /api/v1/auth/sessions (list all sessions)
 * - DELETE /api/v1/auth/sessions/{id} (terminate session)
 *
 * TO IMPLEMENT:
 * Option 1: Use fastapi-users library
 *   pip install 'fastapi-users[sqlalchemy]'
 *   Provides user CRUD, JWT auth, password hashing
 *
 * Option 2: Use Keycloak/Authentik for enterprise environments
 *   Self-hosted identity provider with LDAP/AD support
 *
 * SCADA REQUIREMENTS:
 * - Role-based access (viewer, operator, engineer, admin)
 * - Audit trail for all control actions (ISA-62443)
 * - Session management and timeout enforcement
 * - Password policies
 *
 * ORIGINAL FILE: 26KB of commented code removed for clarity.
 * See git history for original implementation.
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
