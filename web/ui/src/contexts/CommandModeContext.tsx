'use client';

import { createContext, useContext, useState, useCallback, useEffect, useRef, ReactNode } from 'react';
import { setAuthToken } from '@/lib/api';

// Command mode configuration
const COMMAND_MODE_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

interface User {
  username: string;
  role: string;
  token: string;
}

interface CommandModeContextType {
  mode: 'view' | 'command';
  user: User | null;
  timeRemaining: number | null; // seconds remaining before auto-exit
  isAuthenticated: boolean;
  canCommand: boolean; // true if in command mode with sufficient role
  enterCommandMode: (username: string, password: string) => Promise<boolean>;
  exitCommandMode: () => void;
  extendTimeout: () => void;
}

const CommandModeContext = createContext<CommandModeContextType | undefined>(undefined);

interface CommandModeProviderProps {
  children: ReactNode;
}

export function CommandModeProvider({ children }: CommandModeProviderProps) {
  const [mode, setMode] = useState<'view' | 'command'>('view');
  const [user, setUser] = useState<User | null>(null);
  const [expiryTime, setExpiryTime] = useState<Date | null>(null);
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const countdownRef = useRef<NodeJS.Timeout | null>(null);

  // Update countdown timer
  useEffect(() => {
    if (mode === 'command' && expiryTime) {
      const updateCountdown = () => {
        const now = new Date();
        const remaining = Math.max(0, Math.floor((expiryTime.getTime() - now.getTime()) / 1000));
        setTimeRemaining(remaining);

        if (remaining <= 0) {
          exitCommandMode();
        }
      };

      updateCountdown();
      countdownRef.current = setInterval(updateCountdown, 1000);

      return () => {
        if (countdownRef.current) {
          clearInterval(countdownRef.current);
        }
      };
    } else {
      setTimeRemaining(null);
    }
    // exitCommandMode is stable (empty deps) but defined after this effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, expiryTime]);

  // Clear timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
      }
    };
  }, []);

  const enterCommandMode = useCallback(async (username: string, password: string): Promise<boolean> => {
    try {
      const response = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        console.error('Login failed');
        return false;
      }

      const data = await response.json();

      // Check role - must be at least operator
      if (data.role !== 'operator' && data.role !== 'admin') {
        console.error('Insufficient role for command mode');
        return false;
      }

      // Store token for API requests
      setAuthToken(data.token);

      setUser({
        username: data.username,
        role: data.role,
        token: data.token,
      });
      setMode('command');

      // Set expiry time
      const expiry = new Date(Date.now() + COMMAND_MODE_TIMEOUT_MS);
      setExpiryTime(expiry);

      // Set auto-exit timeout
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => {
        exitCommandMode();
      }, COMMAND_MODE_TIMEOUT_MS);

      return true;
    } catch (error) {
      console.error('Error entering command mode:', error);
      return false;
    }
  }, []);

  const exitCommandMode = useCallback(() => {
    setMode('view');
    setExpiryTime(null);
    setTimeRemaining(null);

    // Clear auth token - control actions require re-authentication
    // This implements the read-first model: view is always available,
    // but control requires fresh authentication
    setAuthToken(null);

    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const extendTimeout = useCallback(() => {
    if (mode === 'command') {
      const expiry = new Date(Date.now() + COMMAND_MODE_TIMEOUT_MS);
      setExpiryTime(expiry);

      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => {
        exitCommandMode();
      }, COMMAND_MODE_TIMEOUT_MS);
    }
  }, [mode, exitCommandMode]);

  const isAuthenticated = user !== null;
  const canCommand = mode === 'command' && user !== null &&
    (user.role === 'operator' || user.role === 'admin');

  return (
    <CommandModeContext.Provider
      value={{
        mode,
        user,
        timeRemaining,
        isAuthenticated,
        canCommand,
        enterCommandMode,
        exitCommandMode,
        extendTimeout,
      }}
    >
      {children}
    </CommandModeContext.Provider>
  );
}

export function useCommandMode(): CommandModeContextType {
  const context = useContext(CommandModeContext);
  if (context === undefined) {
    throw new Error('useCommandMode must be used within a CommandModeProvider');
  }
  return context;
}

// Helper hook for components that need command mode with auto-extend
export function useCommandModeWithActivity(): CommandModeContextType & { onActivity: () => void } {
  const commandMode = useCommandMode();

  const onActivity = useCallback(() => {
    if (commandMode.mode === 'command') {
      commandMode.extendTimeout();
    }
  }, [commandMode]);

  return {
    ...commandMode,
    onActivity,
  };
}
