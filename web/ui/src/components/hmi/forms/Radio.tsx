'use client';

/**
 * HMI Radio & RadioGroup Components
 *
 * Touch-friendly radio buttons following SCADA HMI design principles:
 * - Large touch target (minimum 44px)
 * - Clear selected/unselected states
 * - Grouped options with fieldset for accessibility
 * - Keyboard navigation support
 * - Never relies on color alone
 */

import { forwardRef, InputHTMLAttributes, createContext, useContext, useId, ReactNode } from 'react';
import clsx from 'clsx';

export type RadioSize = 'sm' | 'md' | 'lg';

// Context for RadioGroup
interface RadioGroupContextValue {
  name: string;
  value?: string;
  onChange?: (value: string) => void;
  size: RadioSize;
  disabled?: boolean;
  error?: boolean;
}

const RadioGroupContext = createContext<RadioGroupContextValue | null>(null);

// RadioGroup component
interface RadioGroupProps {
  /** Group name (required for form submission) */
  name: string;
  /** Group label */
  label: string;
  /** Currently selected value */
  value?: string;
  /** Change handler */
  onChange?: (value: string) => void;
  /** Radio options */
  children: ReactNode;
  /** Size variant */
  size?: RadioSize;
  /** Disabled state for all options */
  disabled?: boolean;
  /** Error state */
  error?: boolean;
  /** Error message */
  errorMessage?: string;
  /** Helper text */
  helperText?: string;
  /** Layout direction */
  direction?: 'vertical' | 'horizontal';
  /** Hide legend visually */
  hideLegend?: boolean;
  /** Additional class names */
  className?: string;
}

export function RadioGroup({
  name,
  label,
  value,
  onChange,
  children,
  size = 'md',
  disabled = false,
  error = false,
  errorMessage,
  helperText,
  direction = 'vertical',
  hideLegend = false,
  className,
}: RadioGroupProps) {
  const groupId = useId();

  return (
    <RadioGroupContext.Provider value={{ name, value, onChange, size, disabled, error }}>
      <fieldset
        className={clsx('flex flex-col', className)}
        aria-describedby={errorMessage || helperText ? `${groupId}-helper` : undefined}
      >
        <legend
          className={clsx(
            'font-medium text-hmi-text mb-2',
            size === 'sm' && 'text-sm',
            size === 'md' && 'text-base',
            size === 'lg' && 'text-lg',
            hideLegend && 'sr-only'
          )}
        >
          {label}
        </legend>

        <div
          className={clsx(
            'flex',
            direction === 'vertical' ? 'flex-col gap-1' : 'flex-wrap gap-4'
          )}
          role="radiogroup"
        >
          {children}
        </div>

        {/* Helper or error message */}
        {(errorMessage || helperText) && (
          <div
            id={`${groupId}-helper`}
            className={clsx(
              'flex items-center gap-1.5 mt-2 text-sm',
              error ? 'text-status-alarm-dark' : 'text-hmi-muted'
            )}
            role={error ? 'alert' : undefined}
          >
            {error && (
              <span className="font-bold" aria-hidden="true">!</span>
            )}
            <span>{errorMessage || helperText}</span>
          </div>
        )}
      </fieldset>
    </RadioGroupContext.Provider>
  );
}

// Individual Radio component
interface RadioProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size' | 'type'> {
  /** Radio label */
  label: string;
  /** Radio value */
  value: string;
  /** Description text */
  description?: string;
  /** Size variant (overrides group size) */
  size?: RadioSize;
  /** Hide label visually */
  hideLabel?: boolean;
}

// All sizes meet 44px minimum touch target
const sizeConfig: Record<RadioSize, {
  radio: string;
  dot: string;
  container: string;
  label: string;
}> = {
  sm: {
    radio: 'w-4 h-4',
    dot: 'w-2 h-2',
    container: 'min-h-touch gap-2',
    label: 'text-sm',
  },
  md: {
    radio: 'w-5 h-5',
    dot: 'w-2.5 h-2.5',
    container: 'min-h-touch gap-3',
    label: 'text-base',
  },
  lg: {
    radio: 'w-6 h-6',
    dot: 'w-3 h-3',
    container: 'min-h-touch-lg gap-3',
    label: 'text-lg',
  },
};

export const Radio = forwardRef<HTMLInputElement, RadioProps>(
  (
    {
      label,
      value,
      description,
      size: sizeProp,
      hideLabel = false,
      disabled: disabledProp,
      className,
      id,
      ...props
    },
    ref
  ) => {
    const context = useContext(RadioGroupContext);
    const generatedId = useId();
    const radioId = id || generatedId;
    const descriptionId = description ? `${radioId}-description` : undefined;

    // Use context values or props
    const name = context?.name || props.name || '';
    const size = sizeProp || context?.size || 'md';
    const disabled = disabledProp ?? context?.disabled ?? false;
    const error = context?.error ?? false;
    const isChecked = context ? context.value === value : props.checked;
    const config = sizeConfig[size];

    const handleChange = () => {
      if (context?.onChange) {
        context.onChange(value);
      }
    };

    return (
      <label
        htmlFor={radioId}
        className={clsx(
          'flex items-center cursor-pointer select-none',
          config.container,
          disabled && 'cursor-not-allowed opacity-50',
          className
        )}
      >
        {/* Custom radio */}
        <div className="relative flex-shrink-0">
          <input
            ref={ref}
            type="radio"
            id={radioId}
            name={name}
            value={value}
            disabled={disabled}
            checked={isChecked}
            onChange={handleChange}
            aria-describedby={descriptionId}
            className={clsx(
              'peer appearance-none',
              config.radio,
              'rounded-full border-2 bg-hmi-panel',
              'transition-colors duration-fast',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info focus-visible:ring-offset-2',
              'touch-manipulation',
              // Default state
              !error && 'border-hmi-border',
              // Error state
              error && 'border-status-alarm',
              // Checked state
              'checked:border-status-info',
              // Disabled
              disabled && 'cursor-not-allowed'
            )}
            {...props}
          />

          {/* Inner dot */}
          <div
            className={clsx(
              'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2',
              'rounded-full bg-status-info',
              'opacity-0 peer-checked:opacity-100',
              'scale-0 peer-checked:scale-100',
              'transition-all duration-fast',
              config.dot
            )}
            aria-hidden="true"
          />
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
    );
  }
);

Radio.displayName = 'Radio';

export default Radio;
