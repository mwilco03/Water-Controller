'use client';

/**
 * HMI Data Table Component
 *
 * Touch-friendly data table for alarms, events, sensor readings:
 * - Mobile: Card-based layout (stacked)
 * - Desktop: Traditional table layout
 * - Sortable columns
 * - Row selection for batch operations
 * - Status row highlighting
 * - Touch-friendly row actions
 */

import { ReactNode, useState, useCallback, useMemo } from 'react';
import clsx from 'clsx';

export type SortDirection = 'asc' | 'desc' | null;
export type RowStatus = 'normal' | 'warning' | 'alarm' | 'selected' | 'disabled';

export interface Column<T> {
  /** Unique column key */
  key: string;
  /** Column header */
  header: string;
  /** Cell renderer */
  render: (row: T, index: number) => ReactNode;
  /** Sortable */
  sortable?: boolean;
  /** Sort comparator */
  sortFn?: (a: T, b: T) => number;
  /** Column width (CSS value) */
  width?: string;
  /** Hide on mobile (will still show in card view) */
  hideOnMobile?: boolean;
  /** Priority for mobile card view (lower = higher priority) */
  mobilePriority?: number;
  /** Align content */
  align?: 'left' | 'center' | 'right';
}

export interface RowAction<T> {
  /** Action key */
  key: string;
  /** Action label */
  label: string;
  /** Action icon */
  icon?: ReactNode;
  /** Action handler */
  onClick: (row: T, index: number) => void;
  /** Disabled predicate */
  disabled?: (row: T) => boolean;
  /** Variant */
  variant?: 'default' | 'danger';
}

export interface DataTableProps<T> {
  /** Table data */
  data: T[];
  /** Column definitions */
  columns: Column<T>[];
  /** Row key extractor */
  getRowKey: (row: T, index: number) => string | number;
  /** Row status extractor */
  getRowStatus?: (row: T) => RowStatus;
  /** Row actions */
  rowActions?: RowAction<T>[];
  /** Enable row selection */
  selectable?: boolean;
  /** Selected row keys */
  selectedKeys?: Set<string | number>;
  /** Selection change handler */
  onSelectionChange?: (keys: Set<string | number>) => void;
  /** Row click handler */
  onRowClick?: (row: T, index: number) => void;
  /** Empty state message */
  emptyMessage?: string;
  /** Empty state icon */
  emptyIcon?: ReactNode;
  /** Loading state */
  loading?: boolean;
  /** Sticky header */
  stickyHeader?: boolean;
  /** Compact mode */
  compact?: boolean;
  /** Additional class names */
  className?: string;
}

const statusStyles: Record<RowStatus, string> = {
  normal: '',
  warning: 'bg-status-warning-light border-l-4 border-l-status-warning',
  alarm: 'bg-status-alarm-light border-l-4 border-l-status-alarm',
  selected: 'bg-status-info-light',
  disabled: 'opacity-50',
};

export function DataTable<T>({
  data,
  columns,
  getRowKey,
  getRowStatus,
  rowActions,
  selectable = false,
  selectedKeys = new Set(),
  onSelectionChange,
  onRowClick,
  emptyMessage = 'No data available',
  emptyIcon,
  loading = false,
  stickyHeader = false,
  compact = false,
  className,
}: DataTableProps<T>) {
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);

  // Sort data
  const sortedData = useMemo(() => {
    if (!sortColumn || !sortDirection) return data;

    const column = columns.find((c) => c.key === sortColumn);
    if (!column?.sortFn) return data;

    const sorted = [...data].sort(column.sortFn);
    return sortDirection === 'desc' ? sorted.reverse() : sorted;
  }, [data, columns, sortColumn, sortDirection]);

  // Handle sort
  const handleSort = useCallback((columnKey: string) => {
    const column = columns.find((c) => c.key === columnKey);
    if (!column?.sortable) return;

    if (sortColumn === columnKey) {
      // Cycle: asc -> desc -> null
      if (sortDirection === 'asc') {
        setSortDirection('desc');
      } else if (sortDirection === 'desc') {
        setSortColumn(null);
        setSortDirection(null);
      }
    } else {
      setSortColumn(columnKey);
      setSortDirection('asc');
    }
  }, [columns, sortColumn, sortDirection]);

  // Handle selection
  const handleSelectAll = useCallback(() => {
    if (!onSelectionChange) return;

    if (selectedKeys.size === data.length) {
      onSelectionChange(new Set());
    } else {
      const allKeys = new Set(data.map((row, i) => getRowKey(row, i)));
      onSelectionChange(allKeys);
    }
  }, [data, getRowKey, selectedKeys.size, onSelectionChange]);

  const handleSelectRow = useCallback((key: string | number) => {
    if (!onSelectionChange) return;

    const newKeys = new Set(selectedKeys);
    if (newKeys.has(key)) {
      newKeys.delete(key);
    } else {
      newKeys.add(key);
    }
    onSelectionChange(newKeys);
  }, [selectedKeys, onSelectionChange]);

  // Get mobile-priority columns
  const mobileColumns = useMemo(() => {
    return [...columns]
      .sort((a, b) => (a.mobilePriority ?? 99) - (b.mobilePriority ?? 99))
      .slice(0, 3);
  }, [columns]);

  const allSelected = data.length > 0 && selectedKeys.size === data.length;
  const someSelected = selectedKeys.size > 0 && selectedKeys.size < data.length;

  // Loading state
  if (loading) {
    return (
      <div className={clsx('rounded-hmi border border-hmi-border bg-hmi-panel', className)}>
        <div className="p-4 text-center">
          <svg
            className="w-5 h-5 mx-auto text-hmi-muted animate-spin"
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
          <p className="mt-2 text-hmi-muted">Loading...</p>
        </div>
      </div>
    );
  }

  // Empty state
  if (data.length === 0) {
    return (
      <div className={clsx('rounded-hmi border border-hmi-border bg-hmi-panel', className)}>
        <div className="p-4 text-center">
          {emptyIcon || (
            <svg
              className="w-8 h-8 max-w-8 max-h-8 mx-auto text-hmi-muted"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
              />
            </svg>
          )}
          <p className="mt-2 text-sm text-hmi-muted">{emptyMessage}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={clsx('rounded-hmi border border-hmi-border bg-hmi-panel overflow-hidden', className)}>
      {/* Desktop table view */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full">
          <thead className={clsx(stickyHeader && 'sticky top-0 z-10')}>
            <tr className="bg-hmi-bg border-b border-hmi-border">
              {/* Selection checkbox */}
              {selectable && (
                <th className="w-12 p-3">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    ref={(el) => {
                      if (el) el.indeterminate = someSelected;
                    }}
                    onChange={handleSelectAll}
                    className="w-5 h-5 rounded border-hmi-border text-status-info focus:ring-status-info"
                    aria-label="Select all"
                  />
                </th>
              )}

              {/* Column headers */}
              {columns.map((column) => (
                <th
                  key={column.key}
                  className={clsx(
                    'p-3 text-left font-semibold text-hmi-text',
                    compact ? 'py-2' : 'py-3',
                    column.sortable && 'cursor-pointer select-none hover:bg-hmi-bg-alt',
                    column.align === 'center' && 'text-center',
                    column.align === 'right' && 'text-right'
                  )}
                  style={{ width: column.width }}
                  onClick={() => column.sortable && handleSort(column.key)}
                >
                  <div className="flex items-center gap-1">
                    <span>{column.header}</span>
                    {column.sortable && (
                      <span className="text-hmi-muted">
                        {sortColumn === column.key ? (
                          sortDirection === 'asc' ? (
                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M14.707 12.707a1 1 0 01-1.414 0L10 9.414l-3.293 3.293a1 1 0 01-1.414-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 010 1.414z" clipRule="evenodd" />
                            </svg>
                          ) : (
                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                            </svg>
                          )
                        ) : (
                          <svg className="w-4 h-4 opacity-30" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M5 12a1 1 0 102 0V6.414l1.293 1.293a1 1 0 001.414-1.414l-3-3a1 1 0 00-1.414 0l-3 3a1 1 0 001.414 1.414L5 6.414V12zM15 8a1 1 0 10-2 0v5.586l-1.293-1.293a1 1 0 00-1.414 1.414l3 3a1 1 0 001.414 0l3-3a1 1 0 00-1.414-1.414L15 13.586V8z" />
                          </svg>
                        )}
                      </span>
                    )}
                  </div>
                </th>
              ))}

              {/* Actions column */}
              {rowActions && rowActions.length > 0 && (
                <th className="w-24 p-3 text-right font-semibold text-hmi-text">
                  Actions
                </th>
              )}
            </tr>
          </thead>

          <tbody>
            {sortedData.map((row, index) => {
              const key = getRowKey(row, index);
              const status = getRowStatus?.(row) ?? 'normal';
              const isSelected = selectedKeys.has(key);

              return (
                <tr
                  key={key}
                  onClick={() => onRowClick?.(row, index)}
                  className={clsx(
                    'border-b border-hmi-border last:border-b-0',
                    'transition-colors',
                    statusStyles[status],
                    isSelected && statusStyles.selected,
                    onRowClick && 'cursor-pointer hover:bg-hmi-bg'
                  )}
                >
                  {/* Selection checkbox */}
                  {selectable && (
                    <td className="w-12 p-3" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => handleSelectRow(key)}
                        className="w-5 h-5 rounded border-hmi-border text-status-info focus:ring-status-info"
                        aria-label={`Select row ${index + 1}`}
                      />
                    </td>
                  )}

                  {/* Data cells */}
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={clsx(
                        'p-3',
                        compact ? 'py-2' : 'py-3',
                        column.align === 'center' && 'text-center',
                        column.align === 'right' && 'text-right'
                      )}
                    >
                      {column.render(row, index)}
                    </td>
                  ))}

                  {/* Row actions */}
                  {rowActions && rowActions.length > 0 && (
                    <td className="p-3 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-1">
                        {rowActions.map((action) => (
                          <button
                            key={action.key}
                            onClick={() => action.onClick(row, index)}
                            disabled={action.disabled?.(row)}
                            title={action.label}
                            className={clsx(
                              'p-2 rounded-hmi-sm transition-colors',
                              'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info',
                              action.variant === 'danger'
                                ? 'text-status-alarm hover:bg-status-alarm-light'
                                : 'text-hmi-muted hover:bg-hmi-bg hover:text-hmi-text',
                              action.disabled?.(row) && 'opacity-40 cursor-not-allowed'
                            )}
                          >
                            {action.icon || action.label}
                          </button>
                        ))}
                      </div>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile card view */}
      <div className="md:hidden divide-y divide-hmi-border">
        {sortedData.map((row, index) => {
          const key = getRowKey(row, index);
          const status = getRowStatus?.(row) ?? 'normal';
          const isSelected = selectedKeys.has(key);

          return (
            <div
              key={key}
              onClick={() => onRowClick?.(row, index)}
              className={clsx(
                'p-4 transition-colors',
                statusStyles[status],
                isSelected && statusStyles.selected,
                onRowClick && 'cursor-pointer active:bg-hmi-bg'
              )}
            >
              <div className="flex items-start gap-3">
                {/* Selection checkbox */}
                {selectable && (
                  <div onClick={(e) => e.stopPropagation()} className="pt-1">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => handleSelectRow(key)}
                      className="w-5 h-5 rounded border-hmi-border text-status-info focus:ring-status-info"
                      aria-label={`Select row ${index + 1}`}
                    />
                  </div>
                )}

                {/* Card content */}
                <div className="flex-1 min-w-0">
                  {/* Primary info (first 2-3 columns) */}
                  <div className="space-y-1">
                    {mobileColumns.map((column, colIndex) => (
                      <div
                        key={column.key}
                        className={clsx(
                          colIndex === 0 ? 'font-semibold text-hmi-text' : 'text-hmi-muted text-sm'
                        )}
                      >
                        {colIndex > 0 && (
                          <span className="text-hmi-muted">{column.header}: </span>
                        )}
                        {column.render(row, index)}
                      </div>
                    ))}
                  </div>

                  {/* Row actions */}
                  {rowActions && rowActions.length > 0 && (
                    <div
                      className="flex gap-2 mt-3 pt-3 border-t border-hmi-border/50"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {rowActions.map((action) => (
                        <button
                          key={action.key}
                          onClick={() => action.onClick(row, index)}
                          disabled={action.disabled?.(row)}
                          className={clsx(
                            'flex items-center gap-1.5 px-3 py-2 rounded-hmi-sm',
                            'text-sm font-medium transition-colors',
                            'touch-manipulation',
                            'focus:outline-none focus-visible:ring-2 focus-visible:ring-status-info',
                            action.variant === 'danger'
                              ? 'text-status-alarm bg-status-alarm-light'
                              : 'text-hmi-text bg-hmi-bg',
                            action.disabled?.(row) && 'opacity-40 cursor-not-allowed'
                          )}
                        >
                          {action.icon}
                          <span>{action.label}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default DataTable;
