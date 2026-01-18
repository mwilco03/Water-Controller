'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
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

  const modalRef = useRef<HTMLDivElement>(null);

  // Handle escape key and body scroll lock
  useEffect(() => {
    if (!showDialog) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !loading) {
        handleClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.body.style.overflow = 'hidden';
    modalRef.current?.focus();

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [showDialog, loading, handleClose]);

  // Handle backdrop click
  const handleBackdropClick = useCallback((event: React.MouseEvent) => {
    if (event.target === event.currentTarget && !loading) {
      handleClose();
    }
  }, [loading, handleClose]);

  // Don't show button if already in command mode
  if (mode === 'command') {
    return null;
  }

  return (
    <>
      {showButton && (
        <button
          onClick={() => setShowDialog(true)}
          className="hmi-btn flex items-center gap-2 bg-status-warning hover:bg-status-warning/90 text-white font-medium text-sm"
        >
          <span className="text-sm font-bold">[+]</span>
          Enter Command Mode
        </button>
      )}

      {showDialog && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-modal p-4"
          onClick={handleBackdropClick}
        >
          <div
            ref={modalRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="command-mode-modal-title"
            tabIndex={-1}
            className="bg-hmi-panel border border-hmi-border rounded-lg shadow-hmi-modal w-full max-w-md outline-none"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-hmi-border">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-status-warning-light rounded-lg">
                  <span className="text-lg font-bold text-status-warning">[+]</span>
                </div>
                <div>
                  <h2 id="command-mode-modal-title" className="text-lg font-semibold text-hmi-text">Enter Command Mode</h2>
                  <p className="text-sm text-hmi-muted">Authenticate to send control commands</p>
                </div>
              </div>
              <button
                onClick={handleClose}
                className="text-hmi-muted hover:text-hmi-text transition-colors p-1 text-xl font-bold leading-none"
              >
                X
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-hmi-text mb-1">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text focus:border-status-info focus:ring-1 focus:ring-status-info outline-none"
                  placeholder="Enter username"
                  autoFocus
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-hmi-text mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2 bg-hmi-panel border border-hmi-border rounded text-hmi-text focus:border-status-info focus:ring-1 focus:ring-status-info outline-none"
                  placeholder="Enter password"
                  required
                />
              </div>

              {error && (
                <div className="p-3 bg-status-alarm-light border border-status-alarm/30 rounded text-status-alarm text-sm">
                  {error}
                </div>
              )}

              <div className="bg-hmi-bg p-3 rounded border border-hmi-border text-sm">
                <p className="font-medium text-hmi-text mb-2">Command Mode Info</p>
                <ul className="list-disc list-inside space-y-1 text-xs text-hmi-muted">
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
                  className="hmi-btn hmi-btn-secondary flex-1"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="hmi-btn hmi-btn-primary flex-1"
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
