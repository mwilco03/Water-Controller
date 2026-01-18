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

  // Format time remaining - shows hours:minutes for long durations
  const formatTime = (seconds: number | null) => {
    if (seconds === null) return '--:--';
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hours > 0) {
      return `${hours}h ${mins}m`;
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Warning when less than 5 minutes remaining
  const isWarning = timeRemaining !== null && timeRemaining < 300;

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
        <span className="w-5 h-5 shrink-0 flex items-center justify-center font-bold text-sm">(i)</span>
        <span className="font-semibold text-sm">COMMAND MODE</span>
        <span className="text-sm opacity-90">
          Logged in as <strong>{user?.username}</strong>
        </span>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-sm">
          <span className="w-4 h-4 flex items-center justify-center font-mono text-xs">[T]</span>
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
