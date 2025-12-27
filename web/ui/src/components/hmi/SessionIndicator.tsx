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
        {/* Green dot or warning icon */}
        {isExpiringSoon ? (
          <svg
            className={`w-4 h-4 ${isExpiryCritical ? 'text-alarm-red animate-alarm-flash' : 'text-alarm-yellow'}`}
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        ) : (
          <div className="w-2 h-2 rounded-full bg-alarm-green" />
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
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
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
