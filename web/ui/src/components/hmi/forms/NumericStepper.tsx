'use client';

/**
 * HMI Numeric Stepper Component
 *
 * Touch-friendly numeric input for setpoints and values:
 * - Large +/- buttons for gloved operation
 * - Direct input option with numeric keyboard
 * - Configurable step, min, max, precision
 * - Visual feedback for limits reached
 * - Engineering unit display
 */

import { forwardRef, useState, useCallback, useEffect, useId } from 'react';
import clsx from 'clsx';

export type StepperSize = 'sm' | 'md' | 'lg';

interface NumericStepperProps {
  /** Current value */
  value: number;
  /** Change handler */
  onChange: (value: number) => void;
  /** Label */
  label: string;
  /** Engineering unit */
  unit?: string;
  /** Minimum value */
  min?: number;
  /** Maximum value */
  max?: number;
  /** Step increment */
  step?: number;
  /** Decimal precision */
  precision?: number;
  /** Size variant */
  size?: StepperSize;
  /** Disabled state */
  disabled?: boolean;
  /** Read-only (show value but no controls) */
  readOnly?: boolean;
  /** Error state */
  error?: boolean;
  /** Error message */
  errorMessage?: string;
  /** Helper text */
  helperText?: string;
  /** Hide label visually */
  hideLabel?: boolean;
  /** Allow direct keyboard input */
  allowDirectInput?: boolean;
  /** Show min/max bounds */
  showBounds?: boolean;
  /** Callback when value reaches min */
  onMinReached?: () => void;
  /** Callback when value reaches max */
  onMaxReached?: () => void;
  /** Additional class names */
  className?: string;
}

const sizeConfig: Record<StepperSize, {
  button: string;
  icon: string;
  input: string;
  label: string;
  container: string;
}> = {
  sm: {
    button: 'w-9 h-9',
    icon: 'w-4 h-4',
    input: 'text-base h-9',
    label: 'text-sm',
    container: 'gap-1',
  },
  md: {
    button: 'w-10 h-10',
    icon: 'w-5 h-5',
    input: 'text-xl h-10',
    label: 'text-base',
    container: 'gap-2',
  },
  lg: {
    button: 'w-11 h-11',
    icon: 'w-6 h-6',
    input: 'text-2xl h-11',
    label: 'text-lg',
    container: 'gap-2',
  },
};

export const NumericStepper = forwardRef<HTMLInputElement, NumericStepperProps>(
  (
    {
      value,
      onChange,
      label,
      unit,
      min = -Infinity,
      max = Infinity,
      step = 1,
      precision = 0,
      size = 'md',
      disabled = false,
      readOnly = false,
      error = false,
      errorMessage,
      helperText,
      hideLabel = false,
      allowDirectInput = true,
      showBounds = false,
      onMinReached,
      onMaxReached,
      className,
    },
    ref
  ) => {
    const id = useId();
    const config = sizeConfig[size];
    const [isEditing, setIsEditing] = useState(false);
    const [editValue, setEditValue] = useState('');

    const atMin = value <= min;
    const atMax = value >= max;

    // Format value for display
    const formatValue = useCallback((val: number): string => {
      return val.toFixed(precision);
    }, [precision]);

    // Clamp value to bounds
    const clampValue = useCallback((val: number): number => {
      const clamped = Math.min(Math.max(val, min), max);
      // Round to precision to avoid floating point issues
      const multiplier = Math.pow(10, precision);
      return Math.round(clamped * multiplier) / multiplier;
    }, [min, max, precision]);

    // Increment value
    const increment = useCallback(() => {
      if (disabled || readOnly || atMax) return;
      const newValue = clampValue(value + step);
      onChange(newValue);
      if (newValue >= max && onMaxReached) {
        onMaxReached();
      }
    }, [value, step, disabled, readOnly, atMax, clampValue, onChange, max, onMaxReached]);

    // Decrement value
    const decrement = useCallback(() => {
      if (disabled || readOnly || atMin) return;
      const newValue = clampValue(value - step);
      onChange(newValue);
      if (newValue <= min && onMinReached) {
        onMinReached();
      }
    }, [value, step, disabled, readOnly, atMin, clampValue, onChange, min, onMinReached]);

    // Handle direct input
    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      setEditValue(e.target.value);
    };

    const handleInputBlur = () => {
      setIsEditing(false);
      const parsed = parseFloat(editValue);
      if (!isNaN(parsed)) {
        const newValue = clampValue(parsed);
        onChange(newValue);
      }
    };

    const handleInputKeyDown = (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        handleInputBlur();
      } else if (e.key === 'Escape') {
        setIsEditing(false);
        setEditValue(formatValue(value));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        increment();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        decrement();
      }
    };

    const handleInputFocus = () => {
      if (allowDirectInput && !disabled && !readOnly) {
        setIsEditing(true);
        setEditValue(formatValue(value));
      }
    };

    // Update edit value when value prop changes
    useEffect(() => {
      if (!isEditing) {
        setEditValue(formatValue(value));
      }
    }, [value, isEditing, formatValue]);

    const message = errorMessage || helperText;

    return (
      <div className={clsx('flex flex-col', className)}>
        {/* Label */}
        <label
          htmlFor={id}
          className={clsx(
            'font-medium text-hmi-text mb-1.5',
            config.label,
            hideLabel && 'sr-only'
          )}
        >
          {label}
        </label>

        {/* Stepper control */}
        <div
          className={clsx(
            'flex items-center',
            config.container
          )}
        >
          {/* Decrement button */}
          <button
            type="button"
            onClick={decrement}
            disabled={disabled || readOnly || atMin}
            aria-label={`Decrease ${label}`}
            className={clsx(
              'flex items-center justify-center',
              'rounded-hmi border border-hmi-border bg-hmi-panel',
              'transition-all duration-fast',
              'touch-manipulation select-none',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info',
              'active:scale-95',
              config.button,
              // Disabled/at-limit state
              (disabled || atMin) && 'opacity-40 cursor-not-allowed active:scale-100',
              !disabled && !atMin && 'hover:bg-hmi-bg active:bg-hmi-bg-alt'
            )}
          >
            <svg
              className={clsx(config.icon, 'text-hmi-text')}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M20 12H4" />
            </svg>
          </button>

          {/* Value display/input */}
          <div className="flex-1 flex flex-col items-center">
            <div
              className={clsx(
                'flex items-center justify-center gap-1',
                'w-full px-2'
              )}
            >
              <input
                ref={ref}
                id={id}
                type={isEditing ? 'number' : 'text'}
                inputMode="decimal"
                value={isEditing ? editValue : formatValue(value)}
                onChange={handleInputChange}
                onFocus={handleInputFocus}
                onBlur={handleInputBlur}
                onKeyDown={handleInputKeyDown}
                disabled={disabled}
                readOnly={readOnly || !allowDirectInput}
                aria-invalid={error}
                className={clsx(
                  'w-full text-center font-mono font-bold',
                  'bg-transparent border-none outline-none',
                  'focus:bg-hmi-bg rounded',
                  config.input,
                  error ? 'text-status-alarm-dark' : 'text-hmi-text',
                  disabled && 'opacity-50 cursor-not-allowed',
                  !allowDirectInput && 'cursor-default'
                )}
              />
              {unit && (
                <span className={clsx('text-hmi-muted', config.label)}>
                  {unit}
                </span>
              )}
            </div>

            {/* Bounds display */}
            {showBounds && (
              <div className="flex justify-between w-full px-2 text-xs text-hmi-muted">
                <span>{min > -Infinity ? formatValue(min) : '−∞'}</span>
                <span>{max < Infinity ? formatValue(max) : '∞'}</span>
              </div>
            )}
          </div>

          {/* Increment button */}
          <button
            type="button"
            onClick={increment}
            disabled={disabled || readOnly || atMax}
            aria-label={`Increase ${label}`}
            className={clsx(
              'flex items-center justify-center',
              'rounded-hmi border border-hmi-border bg-hmi-panel',
              'transition-all duration-fast',
              'touch-manipulation select-none',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info',
              'active:scale-95',
              config.button,
              // Disabled/at-limit state
              (disabled || atMax) && 'opacity-40 cursor-not-allowed active:scale-100',
              !disabled && !atMax && 'hover:bg-hmi-bg active:bg-hmi-bg-alt'
            )}
          >
            <svg
              className={clsx(config.icon, 'text-hmi-text')}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
          </button>
        </div>

        {/* Helper/error message */}
        {message && (
          <div
            className={clsx(
              'flex items-center gap-1.5 mt-1.5 text-sm',
              error ? 'text-status-alarm-dark' : 'text-hmi-muted'
            )}
            role={error ? 'alert' : undefined}
          >
            {error && (
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            )}
            <span>{message}</span>
          </div>
        )}
      </div>
    );
  }
);

NumericStepper.displayName = 'NumericStepper';

export default NumericStepper;
