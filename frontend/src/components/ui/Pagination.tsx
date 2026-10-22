import { t } from '../../i18n'
import { cn } from '../../utils/cn'
import Button from './Button'

export interface PaginationProps {
  /** 1-based page number. */
  page: number
  pageSize: number
  total: number
  onChange: (page: number) => void
  className?: string
}

function pageWindow(page: number, pageCount: number): Array<number | 'ellipsis'> {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, index) => index + 1)
  const pages: Array<number | 'ellipsis'> = [1]
  const start = Math.max(2, page - 1)
  const end = Math.min(pageCount - 1, page + 1)
  if (start > 2) pages.push('ellipsis')
  for (let current = start; current <= end; current += 1) pages.push(current)
  if (end < pageCount - 1) pages.push('ellipsis')
  pages.push(pageCount)
  return pages
}

export default function Pagination({ page, pageSize, total, onChange, className }: PaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1
  const last = Math.min(page * pageSize, total)

  return (
    <div className={cn('flex flex-wrap items-center justify-between gap-3', className)}>
      <p className="text-xs text-text-secondary">
        {t('Showing')} <span className="font-mono text-text-primary">{first}</span>–
        <span className="font-mono text-text-primary">{last}</span> {t('of')}{' '}
        <span className="font-mono text-text-primary">{total}</span>
      </p>
      <div className="flex items-center gap-1">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          aria-label={t('Previous page')}
        >
          {t('Prev')}
        </Button>
        {pageWindow(page, pageCount).map((item, index) =>
          item === 'ellipsis' ? (
            <span key={`ellipsis-${index}`} className="px-1.5 text-xs text-text-disabled" aria-hidden="true">
              …
            </span>
          ) : (
            <Button
              key={item}
              variant={item === page ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => onChange(item)}
              aria-current={item === page ? 'page' : undefined}
              className={item === page ? undefined : 'font-mono'}
            >
              {item}
            </Button>
          ),
        )}
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onChange(page + 1)}
          disabled={page >= pageCount}
          aria-label={t('Next page')}
        >
          {t('Next')}
        </Button>
      </div>
    </div>
  )
}
