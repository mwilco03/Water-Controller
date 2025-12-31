'use client';

/**
 * HMI Modal/Drawer Component
 *
 * Responsive modal that adapts to device:
 * - Mobile: Drawer slides up from bottom (thumb-friendly)
 * - Desktop: Centered modal dialog
 *
 * Design principles:
 * - ISA-101 compliant light theme
 * - Large touch targets (minimum 44px)
 * - Focus trap for accessibility
 * - Escape key and backdrop click to close
 * - Smooth animations
 */

import { Fragment, ReactNode, useEffect, useRef, useCallback } from 'react';
import clsx from 'clsx';

export type ModalSize = 'sm' | 'md' | 'lg' | 'xl' | 'full';

interface ModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Close handler */
  onClose: () => void;
  /** Modal title */
  title: string;
  /** Optional subtitle */
  subtitle?: string;
  /** Modal content */
  children: ReactNode;
  /** Footer content (usually action buttons) */
  footer?: ReactNode;
  /** Size variant */
  size?: ModalSize;
  /** Prevent closing on backdrop click */
  disableBackdropClose?: boolean;
  /** Prevent closing on escape key */
  disableEscapeClose?: boolean;
  /** Show close button */
  showCloseButton?: boolean;
  /** Custom close button label */
  closeLabel?: string;
  /** Additional class for the modal container */
  className?: string;
  /** Status indicator in header */
  status?: 'info' | 'warning' | 'alarm' | 'success';
}

const sizeClasses: Record<ModalSize, string> = {
  sm: 'lg:max-w-sm',
  md: 'lg:max-w-md',
  lg: 'lg:max-w-lg',
  xl: 'lg:max-w-xl',
  full: 'lg:max-w-4xl',
};

const statusConfig: Record<string, { bg: string; text: string; border: string }> = {
  info: {
    bg: 'bg-status-info-light',
    text: 'text-status-info-dark',
    border: 'border-status-info',
  },
  warning: {
    bg: 'bg-status-warning-light',
    text: 'text-status-warning-dark',
    border: 'border-status-warning',
  },
  alarm: {
    bg: 'bg-status-alarm-light',
    text: 'text-status-alarm-dark',
    border: 'border-status-alarm',
  },
  success: {
    bg: 'bg-status-ok-light',
    text: 'text-status-ok-dark',
    border: 'border-status-ok',
  },
};

export function Modal({
  isOpen,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = 'md',
  disableBackdropClose = false,
  disableEscapeClose = false,
  showCloseButton = true,
  closeLabel = 'Close',
  className,
  status,
}: ModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);

  // Handle escape key
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !disableEscapeClose) {
        onClose();
      }
    },
    [onClose, disableEscapeClose]
  );

  // Handle backdrop click
  const handleBackdropClick = (event: React.MouseEvent) => {
    if (event.target === event.currentTarget && !disableBackdropClose) {
      onClose();
    }
  };

  // Focus management
  useEffect(() => {
    if (isOpen) {
      // Store currently focused element
      previousActiveElement.current = document.activeElement as HTMLElement;

      // Focus the modal
      modalRef.current?.focus();

      // Add escape key listener
      document.addEventListener('keydown', handleKeyDown);

      // Prevent body scroll
      document.body.style.overflow = 'hidden';

      return () => {
        document.removeEventListener('keydown', handleKeyDown);
        document.body.style.overflow = '';

        // Restore focus
        previousActiveElement.current?.focus();
      };
    }
  }, [isOpen, handleKeyDown]);

  // Focus trap
  useEffect(() => {
    if (!isOpen || !modalRef.current) return;

    const modal = modalRef.current;
    const focusableElements = modal.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    const handleTabKey = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;

      if (event.shiftKey) {
        if (document.activeElement === firstElement) {
          event.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          event.preventDefault();
          firstElement?.focus();
        }
      }
    };

    modal.addEventListener('keydown', handleTabKey);
    return () => modal.removeEventListener('keydown', handleTabKey);
  }, [isOpen]);

  if (!isOpen) return null;

  const statusStyle = status ? statusConfig[status] : null;

  return (
    <Fragment>
      {/* Backdrop */}
      <div
        className={clsx(
          'fixed inset-0 z-modal-backdrop bg-black/50',
          'animate-fade-in'
        )}
        aria-hidden="true"
      />

      {/* Modal container */}
      <div
        className={clsx(
          'fixed inset-0 z-modal flex',
          // Mobile: align to bottom for drawer behavior
          'items-end',
          // Desktop: center the modal
          'lg:items-center lg:justify-center',
          'p-0 lg:p-4'
        )}
        onClick={handleBackdropClick}
        role="presentation"
      >
        {/* Modal panel */}
        <div
          ref={modalRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-title"
          aria-describedby={subtitle ? 'modal-subtitle' : undefined}
          tabIndex={-1}
          className={clsx(
            'relative flex flex-col',
            'w-full bg-hmi-panel',
            'shadow-hmi-card',
            'outline-none',
            // Mobile: drawer style with rounded top
            'rounded-t-hmi-lg max-h-[90vh]',
            'animate-slide-up',
            // Desktop: full rounded modal
            'lg:rounded-hmi-lg lg:max-h-[85vh]',
            'lg:animate-scale-in',
            sizeClasses[size],
            className
          )}
        >
          {/* Header */}
          <div
            className={clsx(
              'flex items-start justify-between gap-4 p-4 border-b border-hmi-border',
              statusStyle && [statusStyle.bg, statusStyle.border, 'border-l-4']
            )}
          >
            <div className="flex-1 min-w-0">
              <h2
                id="modal-title"
                className={clsx(
                  'text-lg font-semibold truncate',
                  statusStyle ? statusStyle.text : 'text-hmi-text'
                )}
              >
                {title}
              </h2>
              {subtitle && (
                <p id="modal-subtitle" className="text-sm text-hmi-muted mt-0.5">
                  {subtitle}
                </p>
              )}
            </div>

            {showCloseButton && (
              <button
                type="button"
                onClick={onClose}
                className={clsx(
                  'flex-shrink-0 p-2 -m-2',
                  'rounded-hmi-sm',
                  'text-hmi-muted hover:text-hmi-text hover:bg-hmi-bg',
                  'transition-colors duration-fast',
                  'touch-manipulation',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info',
                  // Ensure 44px touch target
                  'min-w-touch min-h-touch flex items-center justify-center'
                )}
                aria-label={closeLabel}
              >
                <svg
                  className="w-5 h-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            )}
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-4 overscroll-contain">
            {children}
          </div>

          {/* Footer */}
          {footer && (
            <div
              className={clsx(
                'flex flex-col-reverse sm:flex-row sm:justify-end gap-2 p-4',
                'border-t border-hmi-border bg-hmi-bg/50'
              )}
            >
              {footer}
            </div>
          )}

          {/* Mobile drag indicator */}
          <div
            className="absolute top-2 left-1/2 -translate-x-1/2 w-10 h-1 bg-hmi-border rounded-full lg:hidden"
            aria-hidden="true"
          />
        </div>
      </div>
    </Fragment>
  );
}

/**
 * Confirmation Modal - specialized variant for confirm/cancel actions
 */
interface ConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'danger' | 'warning';
  isLoading?: boolean;
}

const confirmVariantConfig: Record<string, { status: ModalProps['status']; buttonClass: string }> = {
  default: {
    status: 'info',
    buttonClass: 'bg-status-info hover:bg-status-info/90 text-white',
  },
  danger: {
    status: 'alarm',
    buttonClass: 'bg-status-alarm hover:bg-status-alarm/90 text-white',
  },
  warning: {
    status: 'warning',
    buttonClass: 'bg-status-warning hover:bg-status-warning/90 text-white',
  },
};

export function ConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  isLoading = false,
}: ConfirmModalProps) {
  const config = confirmVariantConfig[variant];

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      size="sm"
      status={config.status}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            disabled={isLoading}
            className={clsx(
              'min-h-touch px-4 py-2.5 rounded-hmi',
              'border border-hmi-border bg-hmi-panel text-hmi-text',
              'hover:bg-hmi-bg transition-colors duration-fast',
              'touch-manipulation',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className={clsx(
              'min-h-touch px-4 py-2.5 rounded-hmi font-medium',
              'transition-colors duration-fast',
              'touch-manipulation',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
              config.buttonClass,
              'disabled:opacity-50 disabled:cursor-not-allowed',
              isLoading && 'cursor-wait'
            )}
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <svg
                  className="animate-spin w-4 h-4"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Processing...
              </span>
            ) : (
              confirmLabel
            )}
          </button>
        </>
      }
    >
      <p className="text-hmi-text">{message}</p>
    </Modal>
  );
}

export default Modal;
