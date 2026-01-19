'use client';

import { useEffect, useRef, useCallback } from 'react';

interface UseModalBehaviorOptions {
  isOpen: boolean;
  onClose: () => void;
  disableEscapeClose?: boolean;
  disableBackdropClose?: boolean;
}

/**
 * Hook that provides consistent modal behavior:
 * - Escape key to close
 * - Body scroll lock when open
 * - Focus management
 * - Backdrop click handler
 */
export function useModalBehavior({
  isOpen,
  onClose,
  disableEscapeClose = false,
  disableBackdropClose = false,
}: UseModalBehaviorOptions) {
  const modalRef = useRef<HTMLDivElement>(null);

  // Handle escape key and body scroll lock
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !disableEscapeClose) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.body.style.overflow = 'hidden';
    modalRef.current?.focus();

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose, disableEscapeClose]);

  // Handle backdrop click
  const handleBackdropClick = useCallback(
    (event: React.MouseEvent) => {
      if (event.target === event.currentTarget && !disableBackdropClose) {
        onClose();
      }
    },
    [onClose, disableBackdropClose]
  );

  return {
    modalRef,
    handleBackdropClick,
  };
}

export default useModalBehavior;
