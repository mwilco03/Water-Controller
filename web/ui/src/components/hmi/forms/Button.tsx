'use client';

/**
 * HMI Button Component
 *
 * Touch-friendly button following SCADA HMI design principles:
 * - Minimum 44px touch target
 * - Immediate feedback on press
 * - Clear visual distinction between variants
 * - Keyboard accessible with visible focus
 * - Loading state with spinner
 */

import { forwardRef, ButtonHTMLAttributes, ReactNode } from 'react';
import clsx from 'clsx';

export type ButtonSize = 'sm' | 'md' | 'lg';
export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Button variant */
  variant?: ButtonVariant;
  /** Button size */
  size?: ButtonSize;
  /** Left icon */
  leftIcon?: ReactNode;
  /** Right icon */
  rightIcon?: ReactNode;
  /** Show loading spinner */
  loading?: boolean;
  /** Loading text (replaces children when loading) */
  loadingText?: string;
  /** Full width button */
  fullWidth?: boolean;
}

const sizeClasses: Record<ButtonSize, string> = {
  // All sizes meet 44px minimum touch target (WCAG 2.1)
  sm: 'min-h-touch px-3 py-2 text-sm gap-1.5',
  md: 'min-h-touch px-4 py-2.5 text-base gap-2',
  lg: 'min-h-touch-lg px-6 py-3 text-lg gap-2.5',
};

const iconSizeClasses: Record<ButtonSize, string> = {
  sm: 'w-4 h-4',
  md: 'w-5 h-5',
  lg: 'w-6 h-6',
};

const variantClasses: Record<ButtonVariant, string> = {
  primary: clsx(
    'bg-status-info text-white border-status-info',
    'hover:bg-status-info-dark',
    'active:bg-status-info-dark'
  ),
  secondary: clsx(
    'bg-white text-hmi-text border-hmi-border',
    'hover:bg-hmi-bg',
    'active:bg-hmi-bg-alt'
  ),
  danger: clsx(
    'bg-status-alarm text-white border-status-alarm',
    'hover:bg-status-alarm-dark',
    'active:bg-status-alarm-dark'
  ),
  ghost: clsx(
    'bg-transparent text-hmi-text border-transparent',
    'hover:bg-hmi-bg',
    'active:bg-hmi-bg-alt'
  ),
  outline: clsx(
    'bg-transparent text-status-info border-status-info',
    'hover:bg-status-info-light',
    'active:bg-status-info-light'
  ),
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      leftIcon,
      rightIcon,
      loading = false,
      loadingText,
      fullWidth = false,
      disabled,
      className,
      children,
      ...props
    },
    ref
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={clsx(
          // Base styles
          'inline-flex items-center justify-center',
          'font-medium rounded-hmi border',
          'transition-all duration-fast',
          // Touch optimization
          'touch-manipulation select-none',
          '-webkit-tap-highlight-color-transparent',
          // Focus styles
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info focus-visible:ring-offset-2',
          // Active press feedback
          'active:scale-[0.98]',
          // Size
          sizeClasses[size],
          // Variant
          variantClasses[variant],
          // Disabled
          isDisabled && 'opacity-50 cursor-not-allowed active:scale-100',
          // Full width
          fullWidth && 'w-full',
          className
        )}
        {...props}
      >
        {/* Loading spinner */}
        {loading && (
          <svg
            className={clsx('animate-spin', iconSizeClasses[size])}
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
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

        {/* Left icon (hidden when loading) */}
        {!loading && leftIcon && (
          <span className={iconSizeClasses[size]} aria-hidden="true">
            {leftIcon}
          </span>
        )}

        {/* Button text */}
        <span>{loading && loadingText ? loadingText : children}</span>

        {/* Right icon (hidden when loading) */}
        {!loading && rightIcon && (
          <span className={iconSizeClasses[size]} aria-hidden="true">
            {rightIcon}
          </span>
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';

/**
 * Icon-only button variant
 * For actions where the icon alone is sufficient (with aria-label)
 */
interface IconButtonProps extends Omit<ButtonProps, 'leftIcon' | 'rightIcon' | 'children'> {
  /** Icon to display */
  icon: ReactNode;
  /** Accessible label (required for icon-only buttons) */
  'aria-label': string;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ icon, size = 'md', className, ...props }, ref) => {
    // All sizes meet 44px minimum touch target (WCAG 2.1)
    const sizeSquareClasses: Record<ButtonSize, string> = {
      sm: 'w-11 h-11 p-0',
      md: 'w-11 h-11 p-0',
      lg: 'w-12 h-12 p-0',
    };

    return (
      <Button
        ref={ref}
        size={size}
        className={clsx(sizeSquareClasses[size], className)}
        {...props}
      >
        <span className={iconSizeClasses[size]} aria-hidden="true">
          {icon}
        </span>
      </Button>
    );
  }
);

IconButton.displayName = 'IconButton';

export default Button;
