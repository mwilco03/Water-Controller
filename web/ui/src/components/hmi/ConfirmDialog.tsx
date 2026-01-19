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

import { useEffect, useRef, useCallback, useState } from 'react';

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
      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-red-600 text-white text-sm font-bold">
        !
      </span>
    ),
  },
  warning: {
    headerClass: 'bg-quality-uncertain',
    confirmButtonClass: 'hmi-btn bg-status-warning text-white border-status-warning hover:bg-amber-600',
    icon: (
      <span className="inline-flex items-center justify-center px-2 py-0.5 rounded bg-amber-500 text-white text-xs font-bold">
        WARN
      </span>
    ),
  },
  confirm: {
    headerClass: '',
    confirmButtonClass: 'hmi-btn hmi-btn-primary',
    icon: (
      <span className="inline-flex items-center justify-center px-2 py-0.5 rounded bg-blue-500 text-white text-xs font-bold">
        INFO
      </span>
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
                <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
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
 * Hook for managing confirm dialog state with promise-based API.
 *
 * Usage:
 * ```tsx
 * const { isOpen, dialogProps, confirm } = useConfirmDialog();
 *
 * // In an event handler:
 * const confirmed = await confirm({
 *   title: 'Delete Item',
 *   message: 'Are you sure?',
 *   variant: 'destructive',
 * });
 * if (confirmed) {
 *   // proceed with action
 * }
 *
 * // In your JSX:
 * <ConfirmDialog {...dialogProps} />
 * ```
 */
export function useConfirmDialog() {
  const [isOpen, setIsOpen] = useState(false);
  const [dialogOptions, setDialogOptions] = useState<Omit<ConfirmDialogProps, 'isOpen' | 'onConfirm' | 'onCancel'> | null>(null);
  const resolveRef = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback(async (
    options: Omit<ConfirmDialogProps, 'isOpen' | 'onConfirm' | 'onCancel'>
  ): Promise<boolean> => {
    setDialogOptions(options);
    setIsOpen(true);

    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve;
    });
  }, []);

  const handleConfirm = useCallback(() => {
    setIsOpen(false);
    resolveRef.current?.(true);
    resolveRef.current = null;
  }, []);

  const handleCancel = useCallback(() => {
    setIsOpen(false);
    resolveRef.current?.(false);
    resolveRef.current = null;
  }, []);

  const dialogProps: ConfirmDialogProps = {
    isOpen,
    onConfirm: handleConfirm,
    onCancel: handleCancel,
    title: dialogOptions?.title ?? '',
    message: dialogOptions?.message ?? '',
    consequences: dialogOptions?.consequences,
    confirmLabel: dialogOptions?.confirmLabel,
    cancelLabel: dialogOptions?.cancelLabel,
    variant: dialogOptions?.variant,
    isLoading: dialogOptions?.isLoading,
  };

  return { isOpen, dialogProps, confirm };
}
