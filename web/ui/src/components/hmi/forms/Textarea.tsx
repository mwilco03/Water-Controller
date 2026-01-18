'use client';

/**
 * HMI Textarea Component
 *
 * Touch-friendly multi-line text input following SCADA HMI design principles:
 * - Minimum 44px touch target for the input area
 * - Clear focus states for accessibility
 * - Visual feedback for validation states
 * - Auto-resize option for dynamic content
 * - Character count display
 */

import { forwardRef, TextareaHTMLAttributes, ReactNode, useId, useRef, useEffect } from 'react';
import clsx from 'clsx';

export type TextareaSize = 'sm' | 'md' | 'lg';
export type TextareaState = 'default' | 'error' | 'warning' | 'success';

interface TextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'size'> {
  /** Textarea label - always visible, required for accessibility */
  label: string;
  /** Helper text below the textarea */
  helperText?: string;
  /** Error message - replaces helper text when present */
  errorMessage?: string;
  /** Warning message */
  warningMessage?: string;
  /** Success message */
  successMessage?: string;
  /** Textarea size */
  size?: TextareaSize;
  /** Auto-resize to fit content */
  autoResize?: boolean;
  /** Minimum number of rows */
  minRows?: number;
  /** Maximum number of rows (only applies when autoResize is true) */
  maxRows?: number;
  /** Show character count */
  showCharCount?: boolean;
  /** Full width */
  fullWidth?: boolean;
  /** Hide the label visually (still accessible to screen readers) */
  hideLabel?: boolean;
}

const sizeClasses: Record<TextareaSize, string> = {
  // All sizes meet 44px minimum touch target (WCAG 2.1)
  sm: 'min-h-touch px-3 py-2 text-sm',
  md: 'min-h-touch px-3.5 py-2.5 text-base',
  lg: 'min-h-touch-lg px-4 py-3 text-lg',
};

const labelSizeClasses: Record<TextareaSize, string> = {
  sm: 'text-xs mb-1',
  md: 'text-sm mb-1.5',
  lg: 'text-base mb-2',
};

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  (
    {
      label,
      helperText,
      errorMessage,
      warningMessage,
      successMessage,
      size = 'md',
      autoResize = false,
      minRows = 3,
      maxRows = 10,
      showCharCount = false,
      fullWidth = true,
      hideLabel = false,
      className,
      disabled,
      required,
      maxLength,
      value,
      defaultValue,
      onChange,
      id,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const textareaId = id || generatedId;
    const helperId = `${textareaId}-helper`;
    const internalRef = useRef<HTMLTextAreaElement>(null);

    // Use forwarded ref or internal ref
    const textareaRef = (ref as React.RefObject<HTMLTextAreaElement>) || internalRef;

    // Determine current state from messages
    const state: TextareaState = errorMessage
      ? 'error'
      : warningMessage
        ? 'warning'
        : successMessage
          ? 'success'
          : 'default';

    const message = errorMessage || warningMessage || successMessage || helperText;

    const stateStyles: Record<TextareaState, string> = {
      default: 'border-hmi-border focus:border-status-info focus:ring-status-info/20',
      error: 'border-status-alarm bg-status-alarm-light focus:border-status-alarm focus:ring-status-alarm/20',
      warning: 'border-status-warning bg-status-warning-light focus:border-status-warning focus:ring-status-warning/20',
      success: 'border-status-ok focus:border-status-ok focus:ring-status-ok/20',
    };

    const stateTextStyles: Record<TextareaState, string> = {
      default: 'text-hmi-muted',
      error: 'text-status-alarm-dark',
      warning: 'text-status-warning-dark',
      success: 'text-status-ok-dark',
    };

    const stateIcons: Record<TextareaState, ReactNode> = {
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

    // Auto-resize logic
    useEffect(() => {
      if (!autoResize || !textareaRef.current) return;

      const textarea = textareaRef.current;
      const computedStyle = window.getComputedStyle(textarea);
      const lineHeight = parseFloat(computedStyle.lineHeight) || 20;
      const paddingTop = parseFloat(computedStyle.paddingTop) || 0;
      const paddingBottom = parseFloat(computedStyle.paddingBottom) || 0;

      // Reset height to calculate scrollHeight correctly
      textarea.style.height = 'auto';

      const minHeight = lineHeight * minRows + paddingTop + paddingBottom;
      const maxHeight = lineHeight * maxRows + paddingTop + paddingBottom;
      const newHeight = Math.min(Math.max(textarea.scrollHeight, minHeight), maxHeight);

      textarea.style.height = `${newHeight}px`;
    }, [value, defaultValue, autoResize, minRows, maxRows, textareaRef]);

    // Get current character count
    const currentLength = typeof value === 'string'
      ? value.length
      : typeof defaultValue === 'string'
        ? defaultValue.length
        : 0;

    return (
      <div className={clsx('flex flex-col', fullWidth && 'w-full', className)}>
        {/* Label */}
        <label
          htmlFor={textareaId}
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

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          id={textareaId}
          disabled={disabled}
          required={required}
          maxLength={maxLength}
          value={value}
          defaultValue={defaultValue}
          onChange={onChange}
          rows={autoResize ? minRows : minRows}
          aria-invalid={state === 'error'}
          aria-describedby={message ? helperId : undefined}
          className={clsx(
            // Base styles
            'w-full rounded-hmi border bg-hmi-panel text-hmi-text',
            'transition-colors duration-fast',
            'focus:outline-none focus:ring-2',
            'resize-y',
            // Touch feedback
            'touch-manipulation',
            // Size
            sizeClasses[size],
            // State
            stateStyles[state],
            // Disabled
            disabled && 'opacity-50 cursor-not-allowed bg-hmi-bg resize-none',
            // Auto-resize
            autoResize && 'resize-none overflow-hidden'
          )}
          {...props}
        />

        {/* Footer: helper text and character count */}
        <div className="flex items-start justify-between gap-2 mt-1.5">
          {/* Helper/Error/Warning/Success text */}
          {message ? (
            <div
              id={helperId}
              className={clsx(
                'flex items-center gap-1.5',
                'text-sm',
                stateTextStyles[state]
              )}
              role={state === 'error' ? 'alert' : undefined}
            >
              {stateIcons[state]}
              <span>{message}</span>
            </div>
          ) : (
            <div />
          )}

          {/* Character count */}
          {showCharCount && maxLength && (
            <span
              className={clsx(
                'text-xs tabular-nums',
                currentLength >= maxLength ? 'text-status-alarm-dark' : 'text-hmi-muted'
              )}
            >
              {currentLength}/{maxLength}
            </span>
          )}
        </div>
      </div>
    );
  }
);

Textarea.displayName = 'Textarea';

export default Textarea;
