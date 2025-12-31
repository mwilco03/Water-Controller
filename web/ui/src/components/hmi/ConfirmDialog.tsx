'use client';

/**
 * ConfirmDialog - Confirmation dialog for destructive actions
 *
 * Design principles:
 * - Clear consequences shown before action
 * - Touch-friendly buttons (48px+)
 * - Destructive actions require deliberate reach
 * - Keyboard accessible (Escape to cancel)
 * - Focus trap for accessibility
 */

import { useEffect, useRef, useCallback } from 'react';

type DialogVariant = 'destructive' | 'warning' | 'confirm';

interface ConfirmDialogProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  title: string;
  message: string;
  consequences?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: DialogVariant;
  isLoading?: boolean;
}

const variantStyles: Record<DialogVariant, {
  headerClass: string;
  confirmButtonClass: string;
  icon: React.ReactNode;
}> = {
  destructive: {
    headerClass: 'bg-quality-bad',
    confirmButtonClass: 'hmi-btn hmi-btn-danger',
    icon: (
      <svg className="w-6 h-6 text-status-alarm" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  },
  warning: {
    headerClass: 'bg-quality-uncertain',
    confirmButtonClass: 'hmi-btn bg-status-warning text-white border-status-warning hover:bg-amber-600',
    icon: (
      <svg className="w-6 h-6 text-status-warning" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  confirm: {
    headerClass: '',
    confirmButtonClass: 'hmi-btn hmi-btn-primary',
    icon: (
      <svg className="w-6 h-6 text-status-info" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
};

export default function ConfirmDialog({
  isOpen,
  onConfirm,
  onCancel,
  title,
  message,
  consequences,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'confirm',
  isLoading = false,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  // Focus trap and keyboard handling
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape' && !isLoading) {
      onCancel();
    }

    // Focus trap
    if (e.key === 'Tab' && dialogRef.current) {
      const focusableElements = dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      if (e.shiftKey && document.activeElement === firstElement) {
        e.preventDefault();
        lastElement?.focus();
      } else if (!e.shiftKey && document.activeElement === lastElement) {
        e.preventDefault();
        firstElement?.focus();
      }
    }
  }, [isLoading, onCancel]);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      // Focus cancel button by default (safer option)
      cancelButtonRef.current?.focus();
      // Prevent body scroll
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, handleKeyDown]);

  if (!isOpen) return null;

  const styles = variantStyles[variant];

  return (
    <div
      className="confirm-dialog-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isLoading) {
          onCancel();
        }
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-description"
    >
      <div
        ref={dialogRef}
        className={`confirm-dialog ${variant === 'destructive' ? 'destructive' : ''}`}
      >
        {/* Header */}
        <div className={`confirm-dialog-header ${styles.headerClass}`}>
          <div className="flex items-center gap-3">
            {styles.icon}
            <h2 id="confirm-dialog-title">{title}</h2>
          </div>
        </div>

        {/* Body */}
        <div className="confirm-dialog-body">
          <p id="confirm-dialog-description">{message}</p>

          {consequences && (
            <div className="mt-4 p-3 bg-hmi-bg rounded-lg border border-hmi-border">
              <p className="text-sm font-medium text-hmi-text">Consequences:</p>
              <p className="text-sm text-hmi-muted mt-1">{consequences}</p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="confirm-dialog-actions">
          <button
            ref={cancelButtonRef}
            onClick={onCancel}
            disabled={isLoading}
            className="hmi-btn hmi-btn-secondary"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className={styles.confirmButtonClass}
          >
            {isLoading ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Processing...
              </>
            ) : (
              confirmLabel
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Hook for managing confirm dialog state
 */
export function useConfirmDialog() {
  const dialogRef = useRef<{
    resolve: (value: boolean) => void;
  } | null>(null);

  const confirm = useCallback(async (
    options: Omit<ConfirmDialogProps, 'isOpen' | 'onConfirm' | 'onCancel'>
  ): Promise<boolean> => {
    return new Promise((resolve) => {
      dialogRef.current = { resolve };
      // The actual dialog rendering would be handled by a parent component
      // that uses this hook's returned state
    });
  }, []);

  return { confirm };
}

export { ConfirmDialog };
