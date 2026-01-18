'use client';

/**
 * Session State Indicator Component
 * Shows current authentication state in header (non-intrusive)
 *
 * States:
 * - View Mode: Gray text, subtle, with Login action
 * - Authenticated: Small green dot, operator name, Logout action
 * - Session Expiring: Yellow warning icon, countdown timer
 */

import { useState } from 'react';
import { useCommandMode } from '@/contexts/CommandModeContext';

interface SessionIndicatorProps {
  onLoginClick?: () => void;
  className?: string;
}

export default function SessionIndicator({
  onLoginClick,
  className = '',
}: SessionIndicatorProps) {
  const { mode, user, timeRemaining, isAuthenticated, exitCommandMode } = useCommandMode();
  const [showMenu, setShowMenu] = useState(false);

  // Format time remaining
  const formatTimeRemaining = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Check if session is expiring soon (less than 5 minutes)
  const isExpiringSoon = timeRemaining !== null && timeRemaining <= 300;
  const isExpiryCritical = timeRemaining !== null && timeRemaining <= 60;

  // View Mode (not authenticated)
  if (!isAuthenticated || mode === 'view') {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <span className="text-sm text-hmi-text-secondary">View Mode</span>
        <span className="text-hmi-text-secondary">|</span>
        <button
          onClick={onLoginClick}
          className="text-sm text-alarm-blue hover:text-alarm-blue/80 font-medium transition-colors"
        >
          Login &rarr;
        </button>
      </div>
    );
  }

  // Authenticated in command mode
  return (
    <div className={`relative flex items-center gap-2 ${className}`}>
      {/* Status indicator */}
      <div className="flex items-center gap-2">
        {/* Green dot or warning badge */}
        {isExpiringSoon ? (
          <span
            className={`w-4 h-4 inline-flex items-center justify-center text-xs font-bold ${isExpiryCritical ? 'text-alarm-red animate-alarm-flash' : 'text-alarm-yellow'}`}
            aria-hidden="true"
          >/!\</span>
        ) : (
          <div className="w-2 h-2 rounded-full bg-status-ok" />
        )}

        {/* User info button */}
        <button
          onClick={() => setShowMenu(!showMenu)}
          className="flex items-center gap-2 text-sm text-hmi-text hover:text-hmi-text/80 transition-colors"
        >
          <span className="font-medium">{user?.username}</span>
          {timeRemaining !== null && isExpiringSoon && (
            <span className={`font-mono text-xs ${isExpiryCritical ? 'text-alarm-red' : 'text-alarm-yellow'}`}>
              {formatTimeRemaining(timeRemaining)}
            </span>
          )}
          <span className="w-3 h-3 inline-flex items-center justify-center text-xs" aria-hidden="true">v</span>
        </button>
      </div>

      {/* Dropdown menu */}
      {showMenu && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setShowMenu(false)}
          />
          <div className="absolute right-0 top-full mt-2 w-48 bg-hmi-panel rounded-lg shadow-lg border border-hmi-border py-2 z-50">
            <div className="px-4 py-2 border-b border-hmi-border">
              <div className="font-medium text-hmi-text">{user?.username}</div>
              <div className="text-xs text-hmi-text-secondary capitalize">{user?.role}</div>
              {timeRemaining !== null && (
                <div className="text-xs text-hmi-text-secondary mt-1">
                  Session: {formatTimeRemaining(timeRemaining)}
                </div>
              )}
            </div>
            <button
              onClick={() => {
                exitCommandMode();
                setShowMenu(false);
              }}
              className="w-full text-left px-4 py-2 text-sm text-hmi-text hover:bg-hmi-bg-alt transition-colors"
            >
              Exit Command Mode
            </button>
            <button
              onClick={() => {
                // Full logout - clear local storage and redirect
                localStorage.removeItem('auth_token');
                localStorage.removeItem('user');
                exitCommandMode();
                window.location.href = '/';
              }}
              className="w-full text-left px-4 py-2 text-sm text-alarm-red hover:bg-quality-bad-bg transition-colors"
            >
              Logout
            </button>
          </div>
        </>
      )}
    </div>
  );
}
