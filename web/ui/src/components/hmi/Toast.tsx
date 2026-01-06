'use client';

/**
 * HMI Toast Notification System
 *
 * Touch-friendly toast notifications following SCADA HMI design:
 * - ISA-101 compliant colors (light theme)
 * - Large touch targets for dismiss
 * - Clear icon + text + color distinction
 * - Positioned for mobile bottom nav compatibility
 * - Swipe to dismiss on mobile
 */

import { createContext, useContext, useState, useCallback, useEffect, ReactNode, useRef } from 'react';
import clsx from 'clsx';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface HMIToast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
  persistent?: boolean;
  action?: {
    label: string;
    onClick: () => void;
  };
}

interface ToastContextValue {
  toasts: HMIToast[];
  addToast: (toast: Omit<HMIToast, 'id'>) => string;
  removeToast: (id: string) => void;
  clearAll: () => void;
  success: (title: string, message?: string, options?: Partial<HMIToast>) => string;
  error: (title: string, message?: string, options?: Partial<HMIToast>) => string;
  warning: (title: string, message?: string, options?: Partial<HMIToast>) => string;
  info: (title: string, message?: string, options?: Partial<HMIToast>) => string;
  /** Convenience method for dynamic toast type selection */
  showMessage: (type: ToastType, title: string, message?: string) => string;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastId = 0;

export function HMIToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<HMIToast[]>([]);

  const addToast = useCallback((toast: Omit<HMIToast, 'id'>) => {
    const id = `hmi-toast-${++toastId}`;
    const newToast: HMIToast = {
      ...toast,
      id,
      duration: toast.persistent ? 0 : (toast.duration ?? 5000),
    };

    setToasts(prev => [...prev, newToast]);
    return id;
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setToasts([]);
  }, []);

  const success = useCallback((title: string, message?: string, options?: Partial<HMIToast>) => {
    return addToast({ type: 'success', title, message, ...options });
  }, [addToast]);

  const error = useCallback((title: string, message?: string, options?: Partial<HMIToast>) => {
    return addToast({ type: 'error', title, message, duration: 8000, ...options });
  }, [addToast]);

  const warning = useCallback((title: string, message?: string, options?: Partial<HMIToast>) => {
    return addToast({ type: 'warning', title, message, ...options });
  }, [addToast]);

  const info = useCallback((title: string, message?: string, options?: Partial<HMIToast>) => {
    return addToast({ type: 'info', title, message, ...options });
  }, [addToast]);

  const showMessage = useCallback((type: ToastType, title: string, message?: string) => {
    return addToast({ type, title, message });
  }, [addToast]);

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast, clearAll, success, error, warning, info, showMessage }}>
      {children}
      <HMIToastContainer toasts={toasts} removeToast={removeToast} />
    </ToastContext.Provider>
  );
}

export function useHMIToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useHMIToast must be used within an HMIToastProvider');
  }
  return context;
}

// Toast Container Component
function HMIToastContainer({
  toasts,
  removeToast,
}: {
  toasts: HMIToast[];
  removeToast: (id: string) => void;
}) {
  return (
    <div
      className={clsx(
        'fixed z-toast flex flex-col gap-2',
        // Mobile: above bottom nav
        'bottom-20 left-4 right-4',
        // Desktop: bottom right corner
        'lg:bottom-4 lg:left-auto lg:right-4 lg:max-w-sm'
      )}
      role="region"
      aria-label="Notifications"
      aria-live="polite"
    >
      {toasts.map(toast => (
        <HMIToastItem key={toast.id} toast={toast} onDismiss={() => removeToast(toast.id)} />
      ))}
    </div>
  );
}

// Toast type configuration
const typeConfig: Record<ToastType, {
  bg: string;
  border: string;
  text: string;
  icon: ReactNode;
  progressBg: string;
}> = {
  success: {
    bg: 'bg-status-ok-light',
    border: 'border-status-ok',
    text: 'text-status-ok-dark',
    icon: (
      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
      </svg>
    ),
    progressBg: 'bg-status-ok',
  },
  error: {
    bg: 'bg-status-alarm-light',
    border: 'border-status-alarm',
    text: 'text-status-alarm-dark',
    icon: (
      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
      </svg>
    ),
    progressBg: 'bg-status-alarm',
  },
  warning: {
    bg: 'bg-status-warning-light',
    border: 'border-status-warning',
    text: 'text-status-warning-dark',
    icon: (
      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
      </svg>
    ),
    progressBg: 'bg-status-warning',
  },
  info: {
    bg: 'bg-status-info-light',
    border: 'border-status-info',
    text: 'text-status-info-dark',
    icon: (
      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
      </svg>
    ),
    progressBg: 'bg-status-info',
  },
};

// Individual Toast Item
function HMIToastItem({
  toast,
  onDismiss,
}: {
  toast: HMIToast;
  onDismiss: () => void;
}) {
  const [progress, setProgress] = useState(100);
  const [isPaused, setIsPaused] = useState(false);
  const [isExiting, setIsExiting] = useState(false);
  const touchStartX = useRef<number | null>(null);
  const toastRef = useRef<HTMLDivElement>(null);

  const handleDismiss = useCallback(() => {
    setIsExiting(true);
    setTimeout(onDismiss, 200);
  }, [onDismiss]);

  // Auto-dismiss timer
  useEffect(() => {
    if (!toast.duration || toast.duration === 0) return;

    const startTime = Date.now();

    const tick = () => {
      if (isPaused) return;

      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, toast.duration! - elapsed);
      const percent = (remaining / toast.duration!) * 100;

      setProgress(percent);

      if (remaining <= 0) {
        handleDismiss();
      }
    };

    const interval = setInterval(tick, 50);
    return () => clearInterval(interval);
  }, [toast.duration, isPaused, handleDismiss]);

  // Swipe to dismiss
  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (touchStartX.current === null || !toastRef.current) return;

    const deltaX = e.touches[0].clientX - touchStartX.current;
    if (deltaX > 0) {
      toastRef.current.style.transform = `translateX(${deltaX}px)`;
      toastRef.current.style.opacity = `${1 - deltaX / 200}`;
    }
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (touchStartX.current === null || !toastRef.current) return;

    const deltaX = e.changedTouches[0].clientX - touchStartX.current;

    if (deltaX > 100) {
      handleDismiss();
    } else {
      toastRef.current.style.transform = '';
      toastRef.current.style.opacity = '';
    }

    touchStartX.current = null;
  };

  const config = typeConfig[toast.type];

  return (
    <div
      ref={toastRef}
      className={clsx(
        'relative overflow-hidden rounded-hmi border shadow-hmi-card',
        config.bg,
        config.border,
        'animate-slide-up',
        isExiting && 'opacity-0 translate-x-full transition-all duration-200'
      )}
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      role="alert"
    >
      <div className="p-4 pr-12">
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div className={clsx('flex-shrink-0', config.text)}>
            {config.icon}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <p className={clsx('font-semibold', config.text)}>
              {toast.title}
            </p>
            {toast.message && (
              <p className="text-sm text-hmi-text mt-0.5">
                {toast.message}
              </p>
            )}
            {toast.action && (
              <button
                onClick={() => {
                  toast.action!.onClick();
                  handleDismiss();
                }}
                className={clsx(
                  'mt-2 text-sm font-medium underline',
                  config.text,
                  'hover:no-underline focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2'
                )}
              >
                {toast.action.label}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Close button */}
      <button
        onClick={handleDismiss}
        className={clsx(
          'absolute top-2 right-2 p-2 rounded-hmi-sm',
          'text-hmi-muted hover:text-hmi-text hover:bg-hmi-panel/50',
          'transition-colors touch-manipulation',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info'
        )}
        aria-label="Dismiss"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Progress bar */}
      {toast.duration && toast.duration > 0 && (
        <div className="absolute bottom-0 left-0 right-0 h-1 bg-hmi-border/30">
          <div
            className={clsx('h-full transition-all duration-50', config.progressBg)}
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
    </div>
  );
}

export default HMIToastProvider;
