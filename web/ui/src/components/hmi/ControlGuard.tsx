'use client';

/**
 * Control Guard Component
 * Wraps control elements to enforce authentication for control actions
 *
 * Features:
 * - Checks auth state on action attempt
 * - Shows inline authentication prompt if needed
 * - Completes action after successful auth
 */

import { useState, useCallback, ReactNode, cloneElement, isValidElement, ReactElement } from 'react';
import { useCommandMode } from '@/contexts/CommandModeContext';
import AuthenticationModal from './AuthenticationModal';

interface ControlGuardProps {
  /** Description of the control action for the auth modal */
  action: string;
  /** Callback to execute after successful authentication */
  onAuthenticated: () => void;
  /** The control element to wrap */
  children: ReactNode;
  /** Whether the control is disabled (independent of auth state) */
  disabled?: boolean;
  /** Show tooltip when hovering in view mode */
  showTooltip?: boolean;
}

export default function ControlGuard({
  action,
  onAuthenticated,
  children,
  disabled = false,
  showTooltip = true,
}: ControlGuardProps) {
  const { canCommand, mode } = useCommandMode();
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);

  const handleClick = useCallback((e: React.MouseEvent) => {
    // Prevent default if we're handling auth
    if (!canCommand) {
      e.preventDefault();
      e.stopPropagation();

      // Store the action to execute after auth
      setPendingAction(() => onAuthenticated);
      setShowAuthModal(true);
      return;
    }

    // Already authenticated, execute action
    onAuthenticated();
  }, [canCommand, onAuthenticated]);

  const handleAuthSuccess = useCallback(() => {
    // Execute the pending action
    if (pendingAction) {
      pendingAction();
      setPendingAction(null);
    }
    setShowAuthModal(false);
  }, [pendingAction]);

  const handleAuthClose = useCallback(() => {
    setPendingAction(null);
    setShowAuthModal(false);
  }, []);

  // Clone the child element and add our click handler
  const wrappedChild = isValidElement(children)
    ? cloneElement(children as ReactElement<{ onClick?: (e: React.MouseEvent) => void; disabled?: boolean }>, {
        onClick: disabled ? undefined : handleClick,
        disabled: disabled,
      })
    : children;

  return (
    <>
      <div className="relative inline-block">
        {wrappedChild}

        {/* Tooltip indicator for view mode */}
        {showTooltip && mode === 'view' && !disabled && (
          <div className="absolute -top-1 -right-1 w-3 h-3 bg-alarm-yellow rounded-full flex items-center justify-center text-white text-[8px] font-bold">
            !
          </div>
        )}
      </div>

      {/* Authentication Modal */}
      <AuthenticationModal
        isOpen={showAuthModal}
        actionDescription={action}
        onClose={handleAuthClose}
        onSuccess={handleAuthSuccess}
      />
    </>
  );
}

/**
 * Hook for programmatic control guard checks
 */
export function useControlGuard() {
  const { canCommand, enterCommandMode } = useCommandMode();
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [pendingAction, setPendingAction] = useState<{
    action: string;
    callback: () => void;
  } | null>(null);

  const guardAction = useCallback((action: string, callback: () => void) => {
    if (canCommand) {
      callback();
      return;
    }

    setPendingAction({ action, callback });
    setShowAuthModal(true);
  }, [canCommand]);

  const handleAuthSuccess = useCallback(() => {
    if (pendingAction) {
      pendingAction.callback();
      setPendingAction(null);
    }
    setShowAuthModal(false);
  }, [pendingAction]);

  const handleAuthClose = useCallback(() => {
    setPendingAction(null);
    setShowAuthModal(false);
  }, []);

  return {
    guardAction,
    canCommand,
    AuthModal: showAuthModal && pendingAction ? (
      <AuthenticationModal
        isOpen={showAuthModal}
        actionDescription={pendingAction.action}
        onClose={handleAuthClose}
        onSuccess={handleAuthSuccess}
      />
    ) : null,
  };
}
