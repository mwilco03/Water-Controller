'use client';

import { useState, useEffect } from 'react';
import { getRegisteredShortcuts, formatShortcut, useKeyboardShortcuts, KeyboardShortcut } from '@/hooks/useKeyboardShortcuts';

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export default function KeyboardShortcutsHelp({ isOpen, onClose }: Props) {
  const [shortcuts, setShortcuts] = useState<KeyboardShortcut[]>([]);

  useEffect(() => {
    if (isOpen) {
      setShortcuts(getRegisteredShortcuts());
    }
  }, [isOpen]);

  // Close on Escape
  useKeyboardShortcuts(
    [
      {
        key: 'Escape',
        description: 'Close help',
        handler: onClose,
        enabled: isOpen,
      },
    ],
    { enabled: isOpen }
  );

  if (!isOpen) return null;

  // Group shortcuts by scope
  const groupedShortcuts = shortcuts.reduce((acc, shortcut) => {
    const scope = shortcut.scope || 'Global';
    if (!acc[scope]) {
      acc[scope] = [];
    }
    acc[scope].push(shortcut);
    return acc;
  }, {} as Record<string, KeyboardShortcut[]>);

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto border border-gray-600">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-blue-600/20 flex items-center justify-center">
              <svg className="w-6 h-6 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-white">Keyboard Shortcuts</h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Shortcut Groups */}
        {Object.entries(groupedShortcuts).length === 0 ? (
          <div className="text-center py-8 text-gray-400">
            <p>No keyboard shortcuts available on this page.</p>
          </div>
        ) : (
          <div className="space-y-6">
            {Object.entries(groupedShortcuts).map(([scope, scopeShortcuts]) => (
              <div key={scope}>
                <h3 className="text-sm font-medium text-gray-400 mb-3 uppercase tracking-wider">
                  {scope}
                </h3>
                <div className="grid gap-2">
                  {scopeShortcuts.map((shortcut, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-3 bg-gray-700/50 rounded-lg"
                    >
                      <span className="text-white">{shortcut.description}</span>
                      <kbd className="px-3 py-1 bg-gray-900 text-gray-300 rounded font-mono text-sm border border-gray-600">
                        {formatShortcut(shortcut)}
                      </kbd>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Footer */}
        <div className="mt-6 pt-4 border-t border-gray-700">
          <p className="text-sm text-gray-500 text-center">
            Press <kbd className="px-2 py-0.5 bg-gray-700 rounded text-gray-300 font-mono text-xs">Shift + ?</kbd> to toggle this help
          </p>
        </div>
      </div>
    </div>
  );
}

// Hook to easily add keyboard help to any page
export function useKeyboardHelp() {
  const [showHelp, setShowHelp] = useState(false);

  useKeyboardShortcuts(
    [
      {
        key: '?',
        shift: true,
        description: 'Show keyboard shortcuts',
        handler: () => setShowHelp(prev => !prev),
      },
    ],
    { scope: 'global' }
  );

  return {
    showHelp,
    setShowHelp,
    KeyboardHelpModal: () => (
      <KeyboardShortcutsHelp isOpen={showHelp} onClose={() => setShowHelp(false)} />
    ),
  };
}
