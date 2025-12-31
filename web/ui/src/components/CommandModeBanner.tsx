'use client';

/**
 * Command Mode Banner
 * Displays when user is in elevated command mode.
 *
 * ISA-101: Uses distinct color (blue) to indicate manual/command mode
 */

import { useCommandMode } from '@/contexts/CommandModeContext';

export default function CommandModeBanner() {
  const { mode, user, timeRemaining, exitCommandMode } = useCommandMode();

  if (mode !== 'command') {
    return null;
  }

  // Format time remaining
  const formatTime = (seconds: number | null) => {
    if (seconds === null) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Warning when less than 60 seconds remaining
  const isWarning = timeRemaining !== null && timeRemaining < 60;

  return (
    <div
      className={`px-4 py-2 flex items-center justify-between gap-4 flex-wrap ${
        isWarning
          ? 'bg-status-warning text-hmi-text'
          : 'bg-status-info text-white'
      }`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-3">
        <svg className="w-5 h-5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
            clipRule="evenodd"
          />
        </svg>
        <span className="font-semibold text-sm">COMMAND MODE</span>
        <span className="text-sm opacity-90">
          Logged in as <strong>{user?.username}</strong>
        </span>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-sm">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span className={isWarning ? 'font-bold' : ''}>
            {formatTime(timeRemaining)}
          </span>
        </div>

        <button
          onClick={exitCommandMode}
          className="px-3 py-1 bg-white/20 hover:bg-white/30 rounded text-sm font-medium transition-colors"
        >
          Exit
        </button>
      </div>
    </div>
  );
}
