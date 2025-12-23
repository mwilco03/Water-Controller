'use client';

import { useEffect, useCallback, useRef } from 'react';

export interface KeyboardShortcut {
  key: string;
  ctrl?: boolean;
  alt?: boolean;
  shift?: boolean;
  meta?: boolean;
  description: string;
  handler: (event: KeyboardEvent) => void;
  enabled?: boolean;
  scope?: string;
}

interface UseKeyboardShortcutsOptions {
  enabled?: boolean;
  scope?: string;
  preventDefault?: boolean;
}

// Global registry of shortcuts for the help modal
const shortcutRegistry = new Map<string, KeyboardShortcut>();

export function getRegisteredShortcuts(scope?: string): KeyboardShortcut[] {
  const shortcuts = Array.from(shortcutRegistry.values());
  if (scope) {
    return shortcuts.filter(s => s.scope === scope || !s.scope);
  }
  return shortcuts;
}

export function formatShortcut(shortcut: KeyboardShortcut): string {
  const parts: string[] = [];
  if (shortcut.ctrl) parts.push('Ctrl');
  if (shortcut.alt) parts.push('Alt');
  if (shortcut.shift) parts.push('Shift');
  if (shortcut.meta) parts.push('Cmd');
  parts.push(shortcut.key.toUpperCase());
  return parts.join(' + ');
}

export function useKeyboardShortcuts(
  shortcuts: KeyboardShortcut[],
  options: UseKeyboardShortcutsOptions = {}
) {
  const { enabled = true, scope, preventDefault = true } = options;
  const shortcutsRef = useRef(shortcuts);
  shortcutsRef.current = shortcuts;

  // Register shortcuts
  useEffect(() => {
    if (!enabled) return;

    shortcuts.forEach(shortcut => {
      const key = `${scope || 'global'}-${formatShortcut(shortcut)}`;
      shortcutRegistry.set(key, { ...shortcut, scope });
    });

    return () => {
      shortcuts.forEach(shortcut => {
        const key = `${scope || 'global'}-${formatShortcut(shortcut)}`;
        shortcutRegistry.delete(key);
      });
    };
  }, [shortcuts, scope, enabled]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!enabled) return;

      // Skip if user is typing in an input field
      const target = event.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable
      ) {
        // Allow Escape to work even in inputs
        if (event.key !== 'Escape') {
          return;
        }
      }

      for (const shortcut of shortcutsRef.current) {
        if (shortcut.enabled === false) continue;

        const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase();
        const ctrlMatch = !!shortcut.ctrl === event.ctrlKey;
        const altMatch = !!shortcut.alt === event.altKey;
        const shiftMatch = !!shortcut.shift === event.shiftKey;
        const metaMatch = !!shortcut.meta === event.metaKey;

        if (keyMatch && ctrlMatch && altMatch && shiftMatch && metaMatch) {
          if (preventDefault) {
            event.preventDefault();
          }
          shortcut.handler(event);
          return;
        }
      }
    },
    [enabled, preventDefault]
  );

  useEffect(() => {
    if (!enabled) return;

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [enabled, handleKeyDown]);
}

// Pre-defined common shortcuts for SCADA HMI
export const commonShortcuts = {
  // Navigation
  goToDashboard: (handler: () => void): KeyboardShortcut => ({
    key: 'd',
    alt: true,
    description: 'Go to Dashboard',
    handler,
  }),
  goToRtus: (handler: () => void): KeyboardShortcut => ({
    key: 'r',
    alt: true,
    description: 'Go to RTUs',
    handler,
  }),
  goToAlarms: (handler: () => void): KeyboardShortcut => ({
    key: 'a',
    alt: true,
    description: 'Go to Alarms',
    handler,
  }),
  goToTrends: (handler: () => void): KeyboardShortcut => ({
    key: 't',
    alt: true,
    description: 'Go to Trends',
    handler,
  }),
  goToControl: (handler: () => void): KeyboardShortcut => ({
    key: 'c',
    alt: true,
    description: 'Go to Control',
    handler,
  }),

  // Actions
  refresh: (handler: () => void): KeyboardShortcut => ({
    key: 'r',
    ctrl: true,
    description: 'Refresh data',
    handler,
  }),
  acknowledge: (handler: () => void): KeyboardShortcut => ({
    key: 'Enter',
    description: 'Acknowledge selected alarm',
    handler,
  }),
  acknowledgeAll: (handler: () => void): KeyboardShortcut => ({
    key: 'a',
    ctrl: true,
    shift: true,
    description: 'Acknowledge all alarms',
    handler,
  }),
  escape: (handler: () => void): KeyboardShortcut => ({
    key: 'Escape',
    description: 'Close modal / Cancel',
    handler,
  }),
  help: (handler: () => void): KeyboardShortcut => ({
    key: '?',
    shift: true,
    description: 'Show keyboard shortcuts',
    handler,
  }),

  // Selection
  selectAll: (handler: () => void): KeyboardShortcut => ({
    key: 'a',
    ctrl: true,
    description: 'Select all',
    handler,
  }),
  selectNone: (handler: () => void): KeyboardShortcut => ({
    key: 'Escape',
    description: 'Clear selection',
    handler,
  }),

  // Navigation within lists
  moveUp: (handler: () => void): KeyboardShortcut => ({
    key: 'ArrowUp',
    description: 'Move up in list',
    handler,
  }),
  moveDown: (handler: () => void): KeyboardShortcut => ({
    key: 'ArrowDown',
    description: 'Move down in list',
    handler,
  }),
  pageUp: (handler: () => void): KeyboardShortcut => ({
    key: 'PageUp',
    description: 'Page up',
    handler,
  }),
  pageDown: (handler: () => void): KeyboardShortcut => ({
    key: 'PageDown',
    description: 'Page down',
    handler,
  }),
  first: (handler: () => void): KeyboardShortcut => ({
    key: 'Home',
    description: 'Go to first item',
    handler,
  }),
  last: (handler: () => void): KeyboardShortcut => ({
    key: 'End',
    description: 'Go to last item',
    handler,
  }),

  // Quick actions with numbers
  quickAction: (number: number, handler: () => void): KeyboardShortcut => ({
    key: String(number),
    alt: true,
    description: `Quick action ${number}`,
    handler,
  }),
};

export default useKeyboardShortcuts;
