'use client';

/**
 * Authentication Modal Component
 * Contextual modal for inline authentication when control action is attempted
 *
 * Features:
 * - Shows what control action operator is attempting
 * - Handles auth errors gracefully
 * - Closes and resumes action on success
 * - No redirect to separate login page
 */

import { useState, useEffect, useRef } from 'react';
import { useCommandMode } from '@/contexts/CommandModeContext';

interface AuthenticationModalProps {
  isOpen: boolean;
  actionDescription: string;
  onClose: () => void;
  onSuccess: () => void;
}

export default function AuthenticationModal({
  isOpen,
  actionDescription,
  onClose,
  onSuccess,
}: AuthenticationModalProps) {
  const { enterCommandMode } = useCommandMode();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const usernameRef = useRef<HTMLInputElement>(null);

  // Focus username input when modal opens
  useEffect(() => {
    if (isOpen && usernameRef.current) {
      usernameRef.current.focus();
    }
  }, [isOpen]);

  // Reset form when modal closes
  useEffect(() => {
    if (!isOpen) {
      setUsername('');
      setPassword('');
      setError(null);
      setLoading(false);
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const success = await enterCommandMode(username, password);

      if (success) {
        onSuccess();
        onClose();
      } else {
        setError('Invalid credentials or insufficient permissions. Operator or Admin role required.');
      }
    } catch (err) {
      setError('Authentication failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onKeyDown={handleKeyDown}
    >
      {/* Overlay */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-hmi-panel rounded-lg shadow-xl border border-hmi-border w-full max-w-md mx-4">
        {/* Header */}
        <div className="px-6 py-4 border-b border-hmi-border">
          <h2 className="text-lg font-semibold text-hmi-text">
            Authentication Required
          </h2>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-6">
          {/* Action context */}
          <div className="mb-6 p-3 bg-hmi-bg-alt rounded-lg">
            <div className="text-sm text-hmi-text-secondary mb-1">Action:</div>
            <div className="font-medium text-hmi-text">{actionDescription}</div>
          </div>

          {/* Error message */}
          {error && (
            <div className="mb-4 p-3 bg-quality-bad-bg border border-alarm-red rounded-lg text-sm text-alarm-red">
              {error}
            </div>
          )}

          {/* Username field */}
          <div className="mb-4">
            <label
              htmlFor="auth-username"
              className="block text-sm font-medium text-hmi-text-secondary mb-1"
            >
              Username
            </label>
            <input
              ref={usernameRef}
              type="text"
              id="auth-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 bg-hmi-bg border border-hmi-border rounded-lg text-hmi-text focus:outline-none focus:ring-2 focus:ring-alarm-blue focus:border-transparent"
              placeholder="Enter username"
              autoComplete="username"
              required
              disabled={loading}
            />
          </div>

          {/* Password field */}
          <div className="mb-6">
            <label
              htmlFor="auth-password"
              className="block text-sm font-medium text-hmi-text-secondary mb-1"
            >
              Password
            </label>
            <input
              type="password"
              id="auth-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 bg-hmi-bg border border-hmi-border rounded-lg text-hmi-text focus:outline-none focus:ring-2 focus:ring-alarm-blue focus:border-transparent"
              placeholder="Enter password"
              autoComplete="current-password"
              required
              disabled={loading}
            />
          </div>

          {/* Info text */}
          <p className="text-xs text-hmi-text-secondary mb-6">
            Session will remain active for subsequent control actions.
          </p>

          {/* Actions */}
          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-hmi-text-secondary hover:text-hmi-text bg-hmi-bg-alt hover:bg-hmi-border rounded-lg transition-colors"
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 text-sm font-medium text-white bg-alarm-blue hover:bg-alarm-blue/90 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={loading}
            >
              {loading ? 'Authenticating...' : 'Authenticate'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
