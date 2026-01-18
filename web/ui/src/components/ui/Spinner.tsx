/**
 * Spinner Component
 * Reusable loading spinner with consistent styling
 * CSS-only implementation (no SVG)
 */

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  color?: string;
  className?: string;
  label?: string;
}

const SIZES = {
  sm: 'h-4 w-4 border-2',
  md: 'h-5 w-5 border-2',
  lg: 'h-8 w-8 border-[3px]',
  xl: 'h-10 w-10 border-4',
};

export function Spinner({
  size = 'md',
  color = 'text-blue-400',
  className = '',
  label,
}: SpinnerProps) {
  return (
    <div className={`flex items-center gap-2 ${className}`} role="status">
      <div
        className={`animate-spin rounded-full border-current border-t-transparent ${SIZES[size]} ${color}`}
        aria-hidden="true"
      />
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
    <div className="flex items-center justify-center py-6">
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
