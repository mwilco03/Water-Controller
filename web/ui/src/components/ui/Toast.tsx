'use client';

import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

type ToastType = 'success' | 'error' | 'warning' | 'info';

interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
  action?: {
    label: string;
    onClick: () => void;
  };
}

interface ToastContextValue {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, 'id'>) => string;
  removeToast: (id: string) => void;
  clearAll: () => void;
  success: (title: string, message?: string, duration?: number) => string;
  error: (title: string, message?: string, duration?: number) => string;
  warning: (title: string, message?: string, duration?: number) => string;
  info: (title: string, message?: string, duration?: number) => string;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = `toast-${++toastId}`;
    const newToast: Toast = {
      ...toast,
      id,
      duration: toast.duration ?? 5000,
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

  const success = useCallback((title: string, message?: string, duration?: number) => {
    return addToast({ type: 'success', title, message, duration });
  }, [addToast]);

  const error = useCallback((title: string, message?: string, duration?: number) => {
    return addToast({ type: 'error', title, message, duration: duration ?? 8000 });
  }, [addToast]);

  const warning = useCallback((title: string, message?: string, duration?: number) => {
    return addToast({ type: 'warning', title, message, duration });
  }, [addToast]);

  const info = useCallback((title: string, message?: string, duration?: number) => {
    return addToast({ type: 'info', title, message, duration });
  }, [addToast]);

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast, clearAll, success, error, warning, info }}>
      {children}
      <ToastContainer toasts={toasts} removeToast={removeToast} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}

// Toast Container Component
function ToastContainer({
  toasts,
  removeToast,
}: {
  toasts: Toast[];
  removeToast: (id: string) => void;
}) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map(toast => (
        <ToastItem key={toast.id} toast={toast} onDismiss={() => removeToast(toast.id)} />
      ))}
    </div>
  );
}

// Individual Toast Item
function ToastItem({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: () => void;
}) {
  const [progress, setProgress] = useState(100);
  const [isPaused, setIsPaused] = useState(false);

  useEffect(() => {
    if (!toast.duration || toast.duration === 0) return;

    const startTime = Date.now();
    let remainingTime = toast.duration;
    let pauseStart: number | null = null;

    const tick = () => {
      if (isPaused) {
        pauseStart = pauseStart ?? Date.now();
        return;
      }

      if (pauseStart) {
        remainingTime -= Date.now() - pauseStart - (startTime + toast.duration! - remainingTime - Date.now());
        pauseStart = null;
      }

      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, toast.duration! - elapsed);
      const percent = (remaining / toast.duration!) * 100;

      setProgress(percent);

      if (remaining <= 0) {
        onDismiss();
      }
    };

    const interval = setInterval(tick, 50);
    return () => clearInterval(interval);
  }, [toast.duration, isPaused, onDismiss]);

  const typeConfig = {
    success: {
      bg: 'bg-green-900/90',
      border: 'border-green-700',
      icon: (
        <svg className="w-5 h-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      progressBg: 'bg-green-500',
    },
    error: {
      bg: 'bg-red-900/90',
      border: 'border-red-700',
      icon: (
        <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      progressBg: 'bg-red-500',
    },
    warning: {
      bg: 'bg-amber-900/90',
      border: 'border-amber-700',
      icon: (
        <svg className="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      ),
      progressBg: 'bg-amber-500',
    },
    info: {
      bg: 'bg-blue-900/90',
      border: 'border-blue-700',
      icon: (
        <svg className="w-5 h-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      progressBg: 'bg-blue-500',
    },
  };

  const config = typeConfig[toast.type];

  return (
    <div
      className={`relative overflow-hidden rounded-lg border ${config.bg} ${config.border} shadow-lg backdrop-blur-sm animate-in slide-in-from-right-full duration-300`}
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
    >
      <div className="p-4 pr-10">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0">{config.icon}</div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white">{toast.title}</p>
            {toast.message && (
              <p className="text-sm text-gray-300 mt-1">{toast.message}</p>
            )}
            {toast.action && (
              <button
                onClick={toast.action.onClick}
                className="mt-2 text-sm font-medium text-blue-400 hover:text-blue-300"
              >
                {toast.action.label}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Close button */}
      <button
        onClick={onDismiss}
        className="absolute top-2 right-2 p-1 text-gray-400 hover:text-white transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Progress bar */}
      {toast.duration && toast.duration > 0 && (
        <div className="absolute bottom-0 left-0 right-0 h-1 bg-black/20">
          <div
            className={`h-full ${config.progressBg} transition-all duration-50`}
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
    </div>
  );
}

export default ToastProvider;
