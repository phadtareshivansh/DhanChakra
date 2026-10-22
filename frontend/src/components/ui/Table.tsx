import { t } from '../../i18n'
import { ReactNode, useMemo, useState } from 'react'
import { cn } from '../../utils/cn'

export type SortDirection = 'asc' | 'desc'

export interface TableSort {
  key: string
  direction: SortDirection
}

export interface TableColumn<T> {
  key: string
  header: ReactNode
  render: (row: T, index: number) => ReactNode
  /** Value used for sorting; falls back to `row[column.key]`. */
  sortValue?: (row: T) => string | number | null | undefined
  sortable?: boolean
  align?: 'left' | 'right' | 'center'
  width?: string
  /** Set false to always show the column in the visibility menu. */
  hideable?: boolean
}

export interface TableProps<T> {
  columns: TableColumn<T>[]
  rows: T[]
  rowKey: (row: T, index: number) => string | number
  initialSort?: TableSort
  onRowClick?: (row: T) => void
  emptyState?: ReactNode
  stickyHeader?: boolean
  /** CSS max-height for the scroll container, e.g. "32rem". */
  maxHeight?: string
  caption?: string
  dense?: boolean
  className?: string
  rowClassName?: (row: T, index: number) => string | undefined
}

const alignClasses = {
  left: 'text-left',
  right: 'text-right',
  center: 'text-center',
} as const

function compareValues(a: unknown, b: unknown): number {
  if (a === b) return 0
  if (a === null || a === undefined) return 1
  if (b === null || b === undefined) return -1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' })
}

export default function Table<T>({
  columns,
  rows,
  rowKey,
  initialSort,
  onRowClick,
  emptyState,
  stickyHeader = false,
  maxHeight,
  caption,
  dense = false,
  className,
  rowClassName,
}: TableProps<T>) {
  const [sort, setSort] = useState<TableSort | null>(initialSort ?? null)
  const [hiddenColumns, setHiddenColumns] = useState<string[]>([])

  const visibleColumns = useMemo(
    () => columns.filter((column) => !hiddenColumns.includes(column.key)),
    [columns, hiddenColumns],
  )

  const sortedRows = useMemo(() => {
    if (!sort) return rows
    const column = columns.find((candidate) => candidate.key === sort.key)
    if (!column) return rows
    const copy = [...rows]
    copy.sort((left, right) => {
      const leftValue = column.sortValue
        ? column.sortValue(left)
        : (left as Record<string, unknown>)[column.key]
      const rightValue = column.sortValue
        ? column.sortValue(right)
        : (right as Record<string, unknown>)[column.key]
      const result = compareValues(leftValue, rightValue)
      return sort.direction === 'asc' ? result : -result
    })
    return copy
  }, [rows, columns, sort])

  const toggleSort = (column: TableColumn<T>) => {
    if (!column.sortable) return
    setSort((current) => {
      if (!current || current.key !== column.key) return { key: column.key, direction: 'asc' }
      return { key: column.key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
    })
  }

  const toggleColumn = (key: string) => {
    setHiddenColumns((current) => {
      if (current.includes(key)) return current.filter((item) => item !== key)
      const remaining = visibleColumns.filter((column) => column.key !== key)
      if (remaining.length === 0) return current
      return [...current, key]
    })
  }

  const hideableColumns = columns.filter((column) => column.hideable !== false)
  const padding = dense ? 'px-3 py-2' : 'px-4 py-3'

  return (
    <div className={cn('panel', className)}>
      {hideableColumns.length > 1 && (
        <div className="flex items-center justify-end border-b border-border px-3 py-2">
          <details className="group relative">
            <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-text-secondary transition-colors hover:bg-raised hover:text-text-primary [&::-webkit-details-marker]:hidden">
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
              </svg>
              {t('Columns')}
            </summary>
            <div className="absolute right-0 z-20 mt-1 w-48 rounded-lg border border-border bg-surface p-1.5 shadow-lg">
              {hideableColumns.map((column) => {
                const checked = !hiddenColumns.includes(column.key)
                const isLastVisible = checked && visibleColumns.length === 1
                return (
                  <label
                    key={column.key}
                    className={cn(
                      'flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-xs text-text-secondary hover:bg-raised',
                      isLastVisible && 'cursor-not-allowed opacity-50',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={isLastVisible}
                      onChange={() => toggleColumn(column.key)}
                      className="h-3.5 w-3.5 accent-[var(--color-accent)]"
                    />
                    <span className="truncate">{column.header}</span>
                  </label>
                )
              })}
            </div>
          </details>
        </div>
      )}

      <div
        className={cn('rounded-b-lg', stickyHeader ? 'overflow-auto' : 'overflow-x-auto')}
        style={maxHeight ? { maxHeight } : undefined}
      >
        <table className="w-full border-collapse text-sm">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead className={cn('border-b border-border', stickyHeader && 'sticky top-0 z-10 bg-surface')}>
            <tr>
              {visibleColumns.map((column) => {
                const active = sort?.key === column.key
                return (
                  <th
                    key={column.key}
                    scope="col"
                    style={column.width ? { width: column.width } : undefined}
                    aria-sort={
                      active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'
                    }
                    className={cn(
                      'whitespace-nowrap px-4 py-3 text-micro font-semibold uppercase tracking-micro text-text-secondary',
                      alignClasses[column.align ?? 'left'],
                      dense && 'px-3 py-2',
                    )}
                  >
                    {column.sortable ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column)}
                        className={cn(
                          'inline-flex items-center gap-1 rounded transition-colors hover:text-text-primary',
                          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-ring',
                          column.align === 'right' && 'flex-row-reverse',
                        )}
                      >
                        {column.header}
                        <svg
                          className={cn('h-3 w-3 transition-transform', active ? 'opacity-100' : 'opacity-30')}
                          viewBox="0 0 20 20"
                          fill="currentColor"
                          aria-hidden="true"
                        >
                          {active && sort.direction === 'desc' ? (
                            <path d="M10 15l-5-5h10l-5 5z" />
                          ) : (
                            <path d="M10 5l5 5H5l5-5z" />
                          )}
                        </svg>
                      </button>
                    ) : (
                      column.header
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {sortedRows.length === 0 ? (
              <tr>
                <td colSpan={visibleColumns.length} className="px-4 py-2">
                  {emptyState ?? (
                    <div className="py-10 text-center text-sm text-text-secondary">{t('No rows to display.')}</div>
                  )}
                </td>
              </tr>
            ) : (
              sortedRows.map((row, index) => (
                <tr
                  key={rowKey(row, index)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={cn(
                    'border-b border-border last:border-0 transition-colors',
                    onRowClick && 'cursor-pointer hover:bg-raised',
                    rowClassName?.(row, index),
                  )}
                >
                  {visibleColumns.map((column) => (
                    <td
                      key={column.key}
                      className={cn(
                        padding,
                        'text-text-primary',
                        alignClasses[column.align ?? 'left'],
                        column.align === 'right' && 'font-mono',
                      )}
                    >
                      {column.render(row, index)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
