'use client';

/**
 * HMI Select Component
 *
 * Touch-friendly select dropdown following SCADA HMI design principles:
 * - Minimum 44px touch target height
 * - Clear visual distinction between states
 * - Keyboard accessible
 * - Works with native select for mobile optimization
 */

import { forwardRef, SelectHTMLAttributes, ReactNode, useId } from 'react';
import clsx from 'clsx';

export type SelectSize = 'sm' | 'md' | 'lg';

interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  /** Select label */
  label: string;
  /** Options to display */
  options: SelectOption[];
  /** Placeholder text when no value selected */
  placeholder?: string;
  /** Helper text */
  helperText?: string;
  /** Error message */
  errorMessage?: string;
  /** Size variant */
  size?: SelectSize;
  /** Left icon */
  leftIcon?: ReactNode;
  /** Full width */
  fullWidth?: boolean;
  /** Hide label visually */
  hideLabel?: boolean;
}

const sizeClasses: Record<SelectSize, string> = {
  // All sizes meet 44px minimum touch target (WCAG 2.1)
  sm: 'min-h-touch px-3 py-2 text-sm pr-8',
  md: 'min-h-touch px-3.5 py-2.5 text-base pr-10',
  lg: 'min-h-touch-lg px-4 py-3 text-lg pr-12',
};

const labelSizeClasses: Record<SelectSize, string> = {
  sm: 'text-xs mb-1',
  md: 'text-sm mb-1.5',
  lg: 'text-base mb-2',
};

const iconSizeClasses: Record<SelectSize, string> = {
  sm: 'right-2 w-4 h-4',
  md: 'right-3 w-5 h-5',
  lg: 'right-4 w-6 h-6',
};

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      label,
      options,
      placeholder = 'Select an option',
      helperText,
      errorMessage,
      size = 'md',
      leftIcon,
      fullWidth = true,
      hideLabel = false,
      disabled,
      required,
      className,
      id,
      value,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const selectId = id || generatedId;
    const helperId = `${selectId}-helper`;

    const hasError = !!errorMessage;
    const message = errorMessage || helperText;

    return (
      <div className={clsx('flex flex-col', fullWidth && 'w-full', className)}>
        {/* Label */}
        <label
          htmlFor={selectId}
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

        {/* Select wrapper */}
        <div className="relative">
          {/* Left icon */}
          {leftIcon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-hmi-muted pointer-events-none">
              {leftIcon}
            </div>
          )}

          {/* Native select */}
          <select
            ref={ref}
            id={selectId}
            disabled={disabled}
            required={required}
            aria-invalid={hasError}
            aria-describedby={message ? helperId : undefined}
            value={value}
            className={clsx(
              // Base styles
              'w-full rounded-hmi border bg-hmi-panel text-hmi-text',
              'appearance-none cursor-pointer',
              'transition-colors duration-fast',
              'focus:outline-none focus:ring-2 focus:ring-status-info/20',
              // Touch feedback
              'touch-manipulation',
              // Size
              sizeClasses[size],
              // Error state
              hasError
                ? 'border-status-alarm bg-status-alarm-light focus:border-status-alarm'
                : 'border-hmi-border focus:border-status-info',
              // Disabled
              disabled && 'opacity-50 cursor-not-allowed bg-hmi-bg',
              // Padding for left icon
              leftIcon && 'pl-10',
              // Placeholder style (when empty)
              !value && 'text-hmi-muted'
            )}
            {...props}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {options.map((option) => (
              <option
                key={option.value}
                value={option.value}
                disabled={option.disabled}
              >
                {option.label}
              </option>
            ))}
          </select>

          {/* Dropdown arrow */}
          <div
            className={clsx(
              'absolute top-1/2 -translate-y-1/2 text-hmi-muted pointer-events-none',
              iconSizeClasses[size]
            )}
          >
            <svg
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </div>
        </div>

        {/* Helper/Error text */}
        {message && (
          <div
            id={helperId}
            className={clsx(
              'flex items-center gap-1.5 mt-1.5 text-sm',
              hasError ? 'text-status-alarm-dark' : 'text-hmi-muted'
            )}
            role={hasError ? 'alert' : undefined}
          >
            {hasError && (
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                  clipRule="evenodd"
                />
              </svg>
            )}
            <span>{message}</span>
          </div>
        )}
      </div>
    );
  }
);

Select.displayName = 'Select';

export default Select;
