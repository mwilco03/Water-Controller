'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

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
        setError(data.detail || 'Login failed');
      }
    } catch (err) {
      setError('Connection error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="w-full max-w-md">
        <div className="scada-panel p-8">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-white">Water Treatment Controller</h1>
            <p className="text-gray-400 mt-2">Sign in to continue</p>
          </div>

          {error && (
            <div className="bg-red-900 text-red-200 p-3 rounded mb-4">
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-6">
            <div>
              <label htmlFor="username" className="block text-sm text-gray-300 mb-2">
                Username
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter username"
                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm text-gray-300 mb-2">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-blue-600 hover:bg-blue-700 rounded text-white font-medium disabled:opacity-50"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-gray-700">
            <button
              onClick={() => setShowLdapConfig(!showLdapConfig)}
              className="text-sm text-gray-400 hover:text-white"
            >
              {showLdapConfig ? 'Hide' : 'Show'} Active Directory Settings
            </button>

            {showLdapConfig && (
              <div className="mt-4 space-y-4 text-sm">
                <p className="text-gray-400">
                  To configure Active Directory authentication, add users to the appropriate
                  AD group and configure the LDAP settings in the controller configuration.
                </p>
                <div className="bg-gray-800 p-3 rounded">
                  <div className="text-gray-400">Admin Group:</div>
                  <code className="text-green-400">CN=WTC-Admins,OU=Groups,DC=example,DC=com</code>
                </div>
                <div className="bg-gray-800 p-3 rounded">
                  <div className="text-gray-400">LDAP Server:</div>
                  <code className="text-green-400">ldap://dc.example.com:389</code>
                </div>
              </div>
            )}
          </div>
        </div>

        <p className="text-center text-gray-500 text-sm mt-4">
          Water Treatment Controller v1.0.0
        </p>
      </div>
    </div>
  );
}
