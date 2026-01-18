'use client';

/**
 * HMI Input Component
 *
 * Touch-friendly input field following SCADA HMI design principles:
 * - Minimum 44px touch target height
 * - Clear focus states for accessibility
 * - Visual feedback for validation states
 * - Monospace font for numeric values
 * - Never relies on color alone to convey meaning
 */

import { forwardRef, InputHTMLAttributes, ReactNode, useId } from 'react';
import clsx from 'clsx';

export type InputSize = 'sm' | 'md' | 'lg';
export type InputVariant = 'default' | 'filled';
export type InputState = 'default' | 'error' | 'warning' | 'success';

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  /** Input label - always visible, required for accessibility */
  label: string;
  /** Helper text below the input */
  helperText?: string;
  /** Error message - replaces helper text when present */
  errorMessage?: string;
  /** Warning message */
  warningMessage?: string;
  /** Success message */
  successMessage?: string;
  /** Input size */
  size?: InputSize;
  /** Visual variant */
  variant?: InputVariant;
  /** Use monospace font (for numeric values) */
  mono?: boolean;
  /** Left icon or prefix */
  leftIcon?: ReactNode;
  /** Right icon or suffix (unit label, etc) */
  rightElement?: ReactNode;
  /** Full width */
  fullWidth?: boolean;
  /** Hide the label visually (still accessible to screen readers) */
  hideLabel?: boolean;
}

const sizeClasses: Record<InputSize, string> = {
  // All sizes meet 44px minimum touch target (WCAG 2.1)
  sm: 'min-h-touch px-3 py-2 text-sm',
  md: 'min-h-touch px-3.5 py-2.5 text-base',
  lg: 'min-h-touch-lg px-4 py-3 text-lg',
};

const labelSizeClasses: Record<InputSize, string> = {
  sm: 'text-xs mb-1',
  md: 'text-sm mb-1.5',
  lg: 'text-base mb-2',
};

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      helperText,
      errorMessage,
      warningMessage,
      successMessage,
      size = 'md',
      variant = 'default',
      mono = false,
      leftIcon,
      rightElement,
      fullWidth = true,
      hideLabel = false,
      className,
      disabled,
      required,
      id,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const inputId = id || generatedId;
    const helperId = `${inputId}-helper`;

    // Determine current state from messages
    const state: InputState = errorMessage
      ? 'error'
      : warningMessage
        ? 'warning'
        : successMessage
          ? 'success'
          : 'default';

    const message = errorMessage || warningMessage || successMessage || helperText;

    const stateStyles: Record<InputState, string> = {
      default: 'border-hmi-border focus:border-status-info focus:ring-status-info/20',
      error: 'border-status-alarm bg-status-alarm-light focus:border-status-alarm focus:ring-status-alarm/20',
      warning: 'border-status-warning bg-status-warning-light focus:border-status-warning focus:ring-status-warning/20',
      success: 'border-status-ok focus:border-status-ok focus:ring-status-ok/20',
    };

    const stateTextStyles: Record<InputState, string> = {
      default: 'text-hmi-muted',
      error: 'text-status-alarm-dark',
      warning: 'text-status-warning-dark',
      success: 'text-status-ok-dark',
    };

    const stateIcons: Record<InputState, ReactNode> = {
      default: null,
      error: (
        <span className="font-bold" aria-hidden="true">!</span>
      ),
      warning: (
        <span className="font-bold" aria-hidden="true">!</span>
      ),
      success: (
        <span className="font-bold" aria-hidden="true">✓</span>
      ),
    };

    return (
      <div className={clsx('flex flex-col', fullWidth && 'w-full', className)}>
        {/* Label */}
        <label
          htmlFor={inputId}
          className={clsx(
            'font-medium text-hmi-text',
            labelSizeClasses[size],
            hideLabel && 'sr-only'
          )}
        >
          {label}
          {required && (
            <span className="text-status-alarm ml-0.5" aria-hidden="true">
              *
            </span>
          )}
        </label>

        {/* Input wrapper */}
        <div className="relative flex items-center">
          {/* Left icon */}
          {leftIcon && (
            <div className="absolute left-3 text-hmi-muted pointer-events-none">
              {leftIcon}
            </div>
          )}

          {/* Input */}
          <input
            ref={ref}
            id={inputId}
            disabled={disabled}
            required={required}
            aria-invalid={state === 'error'}
            aria-describedby={message ? helperId : undefined}
            className={clsx(
              // Base styles
              'w-full rounded-hmi border bg-hmi-panel text-hmi-text',
              'transition-colors duration-fast',
              'focus:outline-none focus:ring-2',
              // Touch feedback
              'touch-manipulation',
              // Size
              sizeClasses[size],
              // State
              stateStyles[state],
              // Variant
              variant === 'filled' && 'bg-hmi-bg-alt',
              // Font
              mono && 'font-mono',
              // Disabled
              disabled && 'opacity-50 cursor-not-allowed bg-hmi-bg',
              // Padding adjustments for icons
              leftIcon && 'pl-10',
              rightElement && 'pr-10'
            )}
            {...props}
          />

          {/* Right element */}
          {rightElement && (
            <div className="absolute right-3 text-hmi-muted">
              {rightElement}
            </div>
          )}
        </div>

        {/* Helper/Error/Warning/Success text */}
        {message && (
          <div
            id={helperId}
            className={clsx(
              'flex items-center gap-1.5 mt-1.5',
              'text-sm',
              stateTextStyles[state]
            )}
            role={state === 'error' ? 'alert' : undefined}
          >
            {stateIcons[state]}
            <span>{message}</span>
          </div>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

export default Input;
