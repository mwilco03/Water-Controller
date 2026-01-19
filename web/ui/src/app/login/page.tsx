'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { extractErrorMessage } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showLdapConfig, setShowLdapConfig] = useState(false);

  // Client-side input sanitization
  const sanitizeInput = (input: string): string => {
    // Basic client-side sanitization for display purposes
    return input
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#x27;');
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    // Apply client-side sanitization before sending
    const sanitizedUsername = sanitizeInput(username);
    const sanitizedPassword = sanitizeInput(password);

    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: sanitizedUsername,
          password: sanitizedPassword,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        // Store token in localStorage
        localStorage.setItem('auth_token', data.token);
        localStorage.setItem('user', JSON.stringify(data.user));
        router.push('/');
      } else {
        const data = await res.json();
        setError(extractErrorMessage(data.detail, 'Login failed'));
      }
    } catch (err) {
      setError('Connection error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="w-full max-w-sm">
        <div className="bg-hmi-panel border border-hmi-border rounded-lg shadow-hmi-card p-4">
          <div className="text-center mb-4">
            <h1 className="text-lg font-bold text-hmi-text">Water Treatment Controller</h1>
            <p className="text-hmi-muted mt-1 text-sm">Sign in to continue</p>
          </div>

          {error && (
            <div className="bg-status-alarm/10 text-status-alarm p-3 rounded mb-4 border border-status-alarm/30">
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-6">
            <div>
              <label htmlFor="username" className="block text-sm text-hmi-muted mb-2">
                Username
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter username"
                className="w-full px-4 py-3 bg-white border border-hmi-border rounded text-hmi-text focus:ring-2 focus:ring-status-info focus:border-status-info focus:outline-none"
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm text-hmi-muted mb-2">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                className="w-full px-4 py-3 bg-white border border-hmi-border rounded text-hmi-text focus:ring-2 focus:ring-status-info focus:border-status-info focus:outline-none"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 bg-status-info hover:bg-status-info/90 rounded text-white text-sm font-medium disabled:opacity-50 transition-colors"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>

          <div className="mt-4 pt-4 border-t border-hmi-border">
            <button
              onClick={() => setShowLdapConfig(!showLdapConfig)}
              className="text-sm text-hmi-muted hover:text-hmi-text transition-colors"
            >
              {showLdapConfig ? 'Hide' : 'Show'} Active Directory Settings
            </button>

            {showLdapConfig && (
              <div className="mt-4 space-y-4 text-sm">
                <p className="text-hmi-muted">
                  To configure Active Directory authentication, add users to the appropriate
                  AD group and configure the LDAP settings in the controller configuration.
                </p>
                <div className="bg-hmi-panel p-3 rounded border border-hmi-border">
                  <div className="text-hmi-muted">Admin Group:</div>
                  <code className="text-hmi-text font-mono">CN=WTC-Admins,OU=Groups,DC=example,DC=com</code>
                </div>
                <div className="bg-hmi-panel p-3 rounded border border-hmi-border">
                  <div className="text-hmi-muted">LDAP Server:</div>
                  <code className="text-hmi-text font-mono">ldap://dc.example.com:389</code>
                </div>
              </div>
            )}
          </div>
        </div>

        <p className="text-center text-hmi-muted text-sm mt-4">
          Water Treatment Controller v1.0.0
        </p>
      </div>
    </div>
  );
}
