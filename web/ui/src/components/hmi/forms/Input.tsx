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
  sm: 'min-h-[2.25rem] px-3 py-1.5 text-sm',
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
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
        </svg>
      ),
      warning: (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
          <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
        </svg>
      ),
      success: (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
        </svg>
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
