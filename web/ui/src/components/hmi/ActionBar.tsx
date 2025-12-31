'use client';

/**
 * ActionBar Component
 *
 * Answers the question: "What can I do right now?"
 *
 * Design principles:
 * - Primary actions are prominent and touch-friendly
 * - Actions grouped by context/category
 * - Disabled actions are clearly indicated
 * - Dangerous actions require confirmation
 * - Responsive: wraps on all screen sizes for accessibility
 * - Can float at bottom of screen on mobile
 */

import { ReactNode, useState } from 'react';
import clsx from 'clsx';
import ConfirmDialog from './ConfirmDialog';

export type ActionVariant = 'primary' | 'secondary' | 'danger' | 'success' | 'warning';

export interface Action {
  /** Unique key */
  key: string;
  /** Action label */
  label: string;
  /** Icon */
  icon?: ReactNode;
  /** Action variant */
  variant?: ActionVariant;
  /** Disabled state */
  disabled?: boolean;
  /** Disabled reason (shown as tooltip/hint) */
  disabledReason?: string;
  /** Loading state */
  loading?: boolean;
  /** Click handler */
  onClick: () => void | Promise<void>;
  /** Requires confirmation before executing */
  requiresConfirmation?: boolean;
  /** Confirmation dialog options */
  confirmOptions?: {
    title?: string;
    message?: string;
    consequences?: string;
    confirmLabel?: string;
  };
}

export interface ActionGroup {
  /** Group label (optional) */
  label?: string;
  /** Actions in this group */
  actions: Action[];
}

interface ActionBarProps {
  /** Actions or action groups */
  actions: Action[] | ActionGroup[];
  /** Align actions */
  align?: 'start' | 'center' | 'end' | 'between';
  /** Show as floating bar (fixed at bottom on mobile) */
  floating?: boolean;
  /** Additional class names */
  className?: string;
}

const variantClasses: Record<ActionVariant, string> = {
  primary: clsx(
    'bg-status-info text-white border-status-info',
    'hover:bg-status-info-dark active:bg-status-info-dark'
  ),
  secondary: clsx(
    'bg-white text-hmi-text border-hmi-border',
    'hover:bg-hmi-bg active:bg-hmi-bg-alt'
  ),
  danger: clsx(
    'bg-status-alarm text-white border-status-alarm',
    'hover:bg-status-alarm-dark active:bg-status-alarm-dark'
  ),
  success: clsx(
    'bg-status-ok text-white border-status-ok',
    'hover:bg-status-ok-dark active:bg-status-ok-dark'
  ),
  warning: clsx(
    'bg-status-warning text-white border-status-warning',
    'hover:bg-status-warning-dark active:bg-status-warning-dark'
  ),
};

const alignClasses: Record<string, string> = {
  start: 'justify-start',
  center: 'justify-center',
  end: 'justify-end',
  between: 'justify-between',
};

function isActionGroup(item: Action | ActionGroup): item is ActionGroup {
  return 'actions' in item;
}

export function ActionBar({
  actions,
  align = 'start',
  floating = false,
  className,
}: ActionBarProps) {
  const [confirmingAction, setConfirmingAction] = useState<Action | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);

  // Normalize to groups
  const groups: ActionGroup[] = actions.length > 0 && isActionGroup(actions[0])
    ? (actions as ActionGroup[])
    : [{ actions: actions as Action[] }];

  const handleActionClick = async (action: Action) => {
    if (action.disabled || action.loading) return;

    if (action.requiresConfirmation) {
      setConfirmingAction(action);
      return;
    }

    await executeAction(action);
  };

  const executeAction = async (action: Action) => {
    setIsExecuting(true);
    try {
      await action.onClick();
    } finally {
      setIsExecuting(false);
      setConfirmingAction(null);
    }
  };

  const renderAction = (action: Action) => (
    <button
      key={action.key}
      onClick={() => handleActionClick(action)}
      disabled={action.disabled || action.loading || isExecuting}
      title={action.disabled ? action.disabledReason : undefined}
      className={clsx(
        // Base styles
        'inline-flex items-center justify-center gap-2',
        'min-h-touch px-4 py-2.5',
        'font-medium text-base rounded-hmi border',
        'transition-all duration-fast',
        // Touch optimization
        'touch-manipulation select-none',
        // Focus styles
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info focus-visible:ring-offset-2',
        // Active feedback
        'active:scale-[0.98]',
        // Variant
        variantClasses[action.variant || 'secondary'],
        // Disabled
        (action.disabled || isExecuting) && 'opacity-50 cursor-not-allowed active:scale-100'
      )}
      aria-disabled={action.disabled}
    >
      {/* Loading spinner */}
      {action.loading && (
        <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      )}

      {/* Icon */}
      {!action.loading && action.icon && (
        <span className="w-5 h-5" aria-hidden="true">
          {action.icon}
        </span>
      )}

      {/* Label */}
      <span>{action.label}</span>
    </button>
  );

  return (
    <>
      <div
        className={clsx(
          // Base styles
          'flex flex-wrap items-center gap-3',
          alignClasses[align],
          // Floating styles
          floating && [
            'fixed bottom-0 left-0 right-0 z-fixed',
            'p-4 bg-hmi-panel border-t border-hmi-border shadow-hmi-bottom-nav',
            // Safe area padding
            'pb-[max(1rem,env(safe-area-inset-bottom))]',
            // Hide on desktop if bottom nav is shown
            'lg:relative lg:bottom-auto lg:left-auto lg:right-auto',
            'lg:p-0 lg:bg-transparent lg:border-0 lg:shadow-none',
          ],
          className
        )}
        role="toolbar"
        aria-label="Actions"
      >
        {groups.map((group, groupIndex) => (
          <div
            key={group.label || groupIndex}
            className="flex flex-wrap items-center gap-2"
            role="group"
            aria-label={group.label}
          >
            {/* Group label */}
            {group.label && (
              <span className="text-sm text-hmi-muted font-medium mr-1">
                {group.label}:
              </span>
            )}

            {/* Actions */}
            {group.actions.map(renderAction)}
          </div>
        ))}
      </div>

      {/* Spacer for floating bar */}
      {floating && (
        <div className="h-20 lg:hidden" aria-hidden="true" />
      )}

      {/* Confirmation dialog */}
      <ConfirmDialog
        isOpen={!!confirmingAction}
        onConfirm={() => confirmingAction && executeAction(confirmingAction)}
        onCancel={() => setConfirmingAction(null)}
        title={confirmingAction?.confirmOptions?.title || `Confirm ${confirmingAction?.label}`}
        message={confirmingAction?.confirmOptions?.message || `Are you sure you want to ${confirmingAction?.label.toLowerCase()}?`}
        consequences={confirmingAction?.confirmOptions?.consequences}
        confirmLabel={confirmingAction?.confirmOptions?.confirmLabel || confirmingAction?.label}
        variant={confirmingAction?.variant === 'danger' ? 'destructive' : 'confirm'}
        isLoading={isExecuting}
      />
    </>
  );
}

export default ActionBar;
