'use client';

/**
 * HMI Checkbox Component
 *
 * Touch-friendly checkbox following SCADA HMI design principles:
 * - Large touch target (minimum 44px)
 * - Clear checked/unchecked states with visual feedback
 * - Supports indeterminate state for batch operations
 * - Keyboard accessible
 * - Never relies on color alone
 */

import { forwardRef, InputHTMLAttributes, useId } from 'react';
import clsx from 'clsx';

export type CheckboxSize = 'sm' | 'md' | 'lg';

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size' | 'type'> {
  /** Checkbox label */
  label: string;
  /** Description text */
  description?: string;
  /** Size variant */
  size?: CheckboxSize;
  /** Indeterminate state (for "select all" scenarios) */
  indeterminate?: boolean;
  /** Error state */
  error?: boolean;
  /** Error message */
  errorMessage?: string;
  /** Hide label visually (still accessible) */
  hideLabel?: boolean;
}

// All sizes meet 44px minimum touch target
const sizeConfig: Record<CheckboxSize, {
  checkbox: string;
  icon: string;
  container: string;
  label: string;
}> = {
  sm: {
    checkbox: 'w-4 h-4',
    icon: 'w-3 h-3',
    container: 'min-h-touch gap-2',
    label: 'text-sm',
  },
  md: {
    checkbox: 'w-5 h-5',
    icon: 'w-3.5 h-3.5',
    container: 'min-h-touch gap-3',
    label: 'text-base',
  },
  lg: {
    checkbox: 'w-6 h-6',
    icon: 'w-4 h-4',
    container: 'min-h-touch-lg gap-3',
    label: 'text-lg',
  },
};

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  (
    {
      label,
      description,
      size = 'md',
      indeterminate = false,
      error = false,
      errorMessage,
      hideLabel = false,
      disabled,
      className,
      id,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const checkboxId = id || generatedId;
    const descriptionId = description ? `${checkboxId}-description` : undefined;
    const config = sizeConfig[size];

    return (
      <div className={clsx('flex flex-col', className)}>
        <label
          htmlFor={checkboxId}
          className={clsx(
            'flex items-center cursor-pointer select-none',
            config.container,
            disabled && 'cursor-not-allowed opacity-50'
          )}
        >
          {/* Custom checkbox */}
          <div className="relative flex-shrink-0">
            <input
              ref={ref}
              type="checkbox"
              id={checkboxId}
              disabled={disabled}
              aria-describedby={descriptionId}
              aria-invalid={error}
              className={clsx(
                'peer appearance-none',
                config.checkbox,
                'rounded border-2 bg-hmi-panel',
                'transition-colors duration-fast',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info focus-visible:ring-offset-2',
                'touch-manipulation',
                // Default state
                !error && 'border-hmi-border',
                // Error state
                error && 'border-status-alarm',
                // Checked state
                'checked:bg-status-info checked:border-status-info',
                // Disabled
                disabled && 'cursor-not-allowed'
              )}
              {...props}
            />

            {/* Check icon */}
            <span
              className={clsx(
                'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2',
                'text-white pointer-events-none font-bold',
                'opacity-0 peer-checked:opacity-100',
                'transition-opacity duration-fast',
                'text-xs leading-none',
                indeterminate && 'hidden'
              )}
              aria-hidden="true"
            >
              ✓
            </span>

            {/* Indeterminate icon (minus) */}
            {indeterminate && (
              <span
                className={clsx(
                  'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2',
                  'text-white pointer-events-none font-bold',
                  'text-xs leading-none'
                )}
                aria-hidden="true"
              >
                −
              </span>
            )}
          </div>

          {/* Label and description */}
          <div className={clsx('flex flex-col', hideLabel && 'sr-only')}>
            <span className={clsx('font-medium text-hmi-text', config.label)}>
              {label}
            </span>
            {description && (
              <span
                id={descriptionId}
                className="text-sm text-hmi-muted mt-0.5"
              >
                {description}
              </span>
            )}
          </div>
        </label>

        {/* Error message */}
        {errorMessage && (
          <div
            className="flex items-center gap-1.5 mt-1.5 text-sm text-status-alarm-dark"
            role="alert"
          >
            <span className="font-bold" aria-hidden="true">!</span>
            <span>{errorMessage}</span>
          </div>
        )}
      </div>
    );
  }
);

Checkbox.displayName = 'Checkbox';

export default Checkbox;
