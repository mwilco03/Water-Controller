'use client';

/**
 * Skeleton - Loading placeholder components
 *
 * Design principles:
 * - Match actual content dimensions for stable layout
 * - Subtle animation (respects reduced motion)
 * - Multiple variants for different content types
 */

import { ReactNode } from 'react';

interface SkeletonProps {
  className?: string;
  children?: ReactNode;
}

interface SkeletonTextProps extends SkeletonProps {
  lines?: number;
  width?: 'full' | 'lg' | 'md' | 'sm';
}

interface SkeletonCardProps extends SkeletonProps {
  hasHeader?: boolean;
  hasFooter?: boolean;
}

/**
 * Base skeleton element
 */
export function Skeleton({ className = '' }: SkeletonProps) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

/**
 * Skeleton text lines
 */
export function SkeletonText({
  lines = 1,
  width = 'full',
  className = '',
}: SkeletonTextProps) {
  const widthClass = {
    full: 'w-full',
    lg: 'w-3/4',
    md: 'w-1/2',
    sm: 'w-1/4',
  }[width];

  return (
    <div className={`space-y-2 ${className}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={`skeleton skeleton-text h-4 ${
            // Last line is shorter for natural look
            i === lines - 1 && lines > 1 ? 'w-2/3' : widthClass
          }`}
        />
      ))}
    </div>
  );
}

/**
 * Skeleton for RTU status card
 */
export function SkeletonRTUCard({ className = '' }: SkeletonProps) {
  return (
    <div className={`hmi-card overflow-hidden ${className}`} aria-hidden="true">
      {/* Header */}
      <div className="p-4 border-b border-hmi-border">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            <div className="skeleton skeleton-circle w-3 h-3" />
            <div>
              <div className="skeleton skeleton-text h-5 w-32 mb-1" />
              <div className="skeleton skeleton-text h-3 w-24" />
            </div>
          </div>
          <div className="skeleton h-6 w-16 rounded-full" />
        </div>
      </div>

      {/* Stats */}
      <div className="p-4">
        <div className="grid grid-cols-3 gap-3 text-center">
          {[1, 2, 3].map((i) => (
            <div key={i}>
              <div className="skeleton skeleton-text h-6 w-8 mx-auto mb-1" />
              <div className="skeleton skeleton-text h-3 w-12 mx-auto" />
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-3 bg-hmi-bg border-t border-hmi-border">
        <div className="skeleton skeleton-text h-4 w-24" />
      </div>
    </div>
  );
}

/**
 * Skeleton for alarm list item
 */
export function SkeletonAlarmItem({ className = '' }: SkeletonProps) {
  return (
    <div className={`touch-list-item ${className}`} aria-hidden="true">
      <div className="skeleton skeleton-circle w-3 h-3 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="skeleton skeleton-text h-4 w-3/4 mb-2" />
        <div className="skeleton skeleton-text h-3 w-1/2" />
      </div>
      <div className="skeleton h-8 w-20 rounded" />
    </div>
  );
}

/**
 * Skeleton for process value display
 */
export function SkeletonProcessValue({ className = '' }: SkeletonProps) {
  return (
    <div className={`flex items-center gap-2 ${className}`} aria-hidden="true">
      <div className="skeleton skeleton-text h-8 w-24" />
      <div className="skeleton skeleton-text h-4 w-8" />
    </div>
  );
}

/**
 * Skeleton for data table row
 */
export function SkeletonTableRow({
  columns = 4,
  className = '',
}: { columns?: number } & SkeletonProps) {
  return (
    <div className={`flex items-center gap-4 py-3 border-b border-hmi-border ${className}`} aria-hidden="true">
      {Array.from({ length: columns }).map((_, i) => (
        <div key={i} className="flex-1">
          <div className="skeleton skeleton-text h-4" style={{ width: `${60 + Math.random() * 40}%` }} />
        </div>
      ))}
    </div>
  );
}

/**
 * Full page loading skeleton
 */
export function SkeletonPage({ className = '' }: SkeletonProps) {
  return (
    <div className={`space-y-6 ${className}`} aria-label="Loading content...">
      {/* Header skeleton */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="skeleton skeleton-text h-7 w-48 mb-2" />
          <div className="skeleton skeleton-text h-4 w-72" />
        </div>
        <div className="flex items-center gap-4">
          <div className="skeleton h-10 w-20 rounded" />
          <div className="skeleton h-10 w-20 rounded" />
        </div>
      </div>

      {/* Grid of cards */}
      <div className="hmi-grid hmi-grid-auto">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <SkeletonRTUCard key={i} />
        ))}
      </div>
    </div>
  );
}

/**
 * Skeleton for dashboard summary stats
 */
export function SkeletonStats({ className = '' }: SkeletonProps) {
  return (
    <div className={`flex items-center gap-6 ${className}`} aria-hidden="true">
      {[1, 2, 3].map((i) => (
        <div key={i} className="text-center">
          <div className="skeleton skeleton-text h-8 w-16 mx-auto mb-1" />
          <div className="skeleton skeleton-text h-3 w-20 mx-auto" />
        </div>
      ))}
    </div>
  );
}

export default Skeleton;
