'use client';

/**
 * HMI Toggle Switch Component
 *
 * Touch-friendly toggle switch for binary controls:
 * - Large touch target (minimum 44px)
 * - Clear on/off states with icon + text + color
 * - Immediate visual feedback
 * - Keyboard accessible
 * - Never relies on color alone
 */

import { forwardRef, ButtonHTMLAttributes, useId } from 'react';
import clsx from 'clsx';

export type ToggleSize = 'sm' | 'md' | 'lg';

interface ToggleProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onChange'> {
  /** Whether the toggle is on */
  checked: boolean;
  /** Change handler */
  onChange: (checked: boolean) => void;
  /** Label for the toggle */
  label: string;
  /** Description text */
  description?: string;
  /** Size variant */
  size?: ToggleSize;
  /** Label for on state */
  onLabel?: string;
  /** Label for off state */
  offLabel?: string;
  /** Show loading state */
  loading?: boolean;
  /** Hide label visually (still accessible) */
  hideLabel?: boolean;
  /** Show state label next to toggle */
  showStateLabel?: boolean;
}

const sizeConfig = {
  sm: {
    track: 'w-9 h-5',
    thumb: 'w-4 h-4',
    thumbTranslate: 'translate-x-4',
    container: 'min-h-[2.25rem]',
  },
  md: {
    track: 'w-11 h-6',
    thumb: 'w-5 h-5',
    thumbTranslate: 'translate-x-5',
    container: 'min-h-touch',
  },
  lg: {
    track: 'w-14 h-7',
    thumb: 'w-6 h-6',
    thumbTranslate: 'translate-x-7',
    container: 'min-h-touch-lg',
  },
};

export const Toggle = forwardRef<HTMLButtonElement, ToggleProps>(
  (
    {
      checked,
      onChange,
      label,
      description,
      size = 'md',
      onLabel = 'On',
      offLabel = 'Off',
      loading = false,
      hideLabel = false,
      showStateLabel = false,
      disabled,
      className,
      id,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const toggleId = id || generatedId;
    const descriptionId = description ? `${toggleId}-description` : undefined;
    const config = sizeConfig[size];

    const handleClick = () => {
      if (!disabled && !loading) {
        onChange(!checked);
      }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleClick();
      }
    };

    return (
      <div
        className={clsx(
          'flex items-center justify-between gap-4',
          config.container,
          className
        )}
      >
        {/* Label section */}
        <div className={clsx('flex flex-col', hideLabel && 'sr-only')}>
          <label
            htmlFor={toggleId}
            className="font-medium text-hmi-text cursor-pointer select-none"
          >
            {label}
          </label>
          {description && (
            <span
              id={descriptionId}
              className="text-sm text-hmi-muted mt-0.5"
            >
              {description}
            </span>
          )}
        </div>

        {/* Toggle control */}
        <div className="flex items-center gap-2">
          {/* State label */}
          {showStateLabel && (
            <span
              className={clsx(
                'text-sm font-medium min-w-[2rem] text-right',
                checked ? 'text-status-ok-dark' : 'text-hmi-muted'
              )}
              aria-hidden="true"
            >
              {checked ? onLabel : offLabel}
            </span>
          )}

          {/* Toggle button */}
          <button
            ref={ref}
            id={toggleId}
            type="button"
            role="switch"
            aria-checked={checked}
            aria-describedby={descriptionId}
            disabled={disabled || loading}
            onClick={handleClick}
            onKeyDown={handleKeyDown}
            className={clsx(
              // Track
              'relative inline-flex shrink-0 rounded-full',
              'border-2 border-transparent',
              'transition-colors duration-fast ease-in-out',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info focus-visible:ring-offset-2',
              'touch-manipulation',
              config.track,
              // States
              checked
                ? 'bg-status-ok'
                : 'bg-hmi-equipment',
              // Disabled
              (disabled || loading) && 'opacity-50 cursor-not-allowed'
            )}
            {...props}
          >
            <span className="sr-only">
              {checked ? onLabel : offLabel}
            </span>

            {/* Thumb */}
            <span
              aria-hidden="true"
              className={clsx(
                'pointer-events-none inline-block rounded-full',
                'bg-white shadow-md ring-0',
                'transition-transform duration-fast ease-in-out',
                config.thumb,
                checked ? config.thumbTranslate : 'translate-x-0',
                // Loading spinner
                loading && 'flex items-center justify-center'
              )}
            >
              {loading && (
                <svg
                  className="w-3 h-3 animate-spin text-hmi-muted"
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
              )}
              {!loading && checked && (
                <svg
                  className="w-3 h-3 text-status-ok"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                    clipRule="evenodd"
                  />
                </svg>
              )}
            </span>
          </button>
        </div>
      </div>
    );
  }
);

Toggle.displayName = 'Toggle';

export default Toggle;
