'use client';

import { useState, useCallback } from 'react';
import { useCommandMode } from '@/contexts/CommandModeContext';

interface Props {
  onClose?: () => void;
  showButton?: boolean;
}

export default function CommandModeLogin({ onClose, showButton = true }: Props) {
  const { mode, enterCommandMode } = useCommandMode();
  const [showDialog, setShowDialog] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const success = await enterCommandMode(username, password);

    if (success) {
      setShowDialog(false);
      setUsername('');
      setPassword('');
      onClose?.();
    } else {
      setError('Login failed. Check credentials or insufficient permissions.');
    }

    setLoading(false);
  }, [username, password, enterCommandMode, onClose]);

  const handleClose = useCallback(() => {
    setShowDialog(false);
    setUsername('');
    setPassword('');
    setError(null);
    onClose?.();
  }, [onClose]);

  // Don't show button if already in command mode
  if (mode === 'command') {
    return null;
  }

  return (
    <>
      {showButton && (
        <button
          onClick={() => setShowDialog(true)}
          className="flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-500 rounded-lg text-white font-medium text-sm transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
          Enter Command Mode
        </button>
      )}

      {showDialog && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-lg shadow-xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-orange-600/20 rounded-lg">
                  <svg className="w-6 h-6 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                    />
                  </svg>
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-white">Enter Command Mode</h2>
                  <p className="text-sm text-gray-400">Authenticate to send control commands</p>
                </div>
              </div>
              <button
                onClick={handleClose}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-300 mb-1">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none"
                  placeholder="Enter username"
                  autoFocus
                  required
                />
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none"
                  placeholder="Enter password"
                  required
                />
              </div>

              {error && (
                <div className="p-3 bg-red-900/50 border border-red-700 rounded text-red-200 text-sm">
                  {error}
                </div>
              )}

              <div className="bg-gray-800/50 p-3 rounded text-sm text-gray-400">
                <p className="font-medium text-gray-300 mb-1">Command Mode</p>
                <ul className="list-disc list-inside space-y-1 text-xs">
                  <li>Allows sending control commands to RTU devices</li>
                  <li>Requires operator or admin role</li>
                  <li>Auto-exits after 5 minutes of inactivity</li>
                  <li>All commands are logged with username</li>
                </ul>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleClose}
                  className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 px-4 py-2 bg-orange-600 hover:bg-orange-500 rounded text-white font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Authenticating...' : 'Enter Command Mode'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
