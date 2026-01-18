/**
 * Spinner Component
 * Reusable loading spinner with consistent styling
 */

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  color?: string;
  className?: string;
  label?: string;
}

const SIZES = {
  sm: 'h-4 w-4',
  md: 'h-5 w-5',
  lg: 'h-8 w-8',
  xl: 'h-10 w-10',
};

export function Spinner({
  size = 'md',
  color = 'text-blue-400',
  className = '',
  label,
}: SpinnerProps) {
  return (
    <div className={`flex items-center gap-2 ${className}`} role="status">
      <svg
        className={`animate-spin ${SIZES[size]} ${color}`}
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
          fill="none"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      {label && <span className="text-gray-400">{label}</span>}
      <span className="sr-only">{label || 'Loading...'}</span>
    </div>
  );
}

/**
 * Full page loading spinner
 */
export function PageSpinner({ label = 'Loading...' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center py-8">
      <Spinner size="md" label={label} />
    </div>
  );
}

/**
 * Inline loading indicator for buttons
 */
export function ButtonSpinner({ className = '' }: { className?: string }) {
  return <Spinner size="sm" color="text-current" className={className} />;
}

export default Spinner;
