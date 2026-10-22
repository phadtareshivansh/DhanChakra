import { t } from '../../i18n'
import { cn } from '../../utils/cn'

export interface BreadcrumbItem {
  label: string
  href?: string
}

export interface BreadcrumbsProps {
  items: BreadcrumbItem[]
  /** Optional link renderer so the app can use React Router's <Link>. */
  renderLink?: (item: BreadcrumbItem, children: React.ReactNode) => React.ReactNode
  className?: string
}

export default function Breadcrumbs({ items, renderLink, className }: BreadcrumbsProps) {
  return (
    <nav aria-label={t('Breadcrumb')} className={cn('min-w-0', className)}>
      <ol className="flex items-center gap-1.5 text-xs text-text-secondary">
        {items.map((item, index) => {
          const isLast = index === items.length - 1
          const label = (
            <span className={cn('truncate', isLast && 'text-text-primary')} aria-current={isLast ? 'page' : undefined}>
              {item.label}
            </span>
          )
          return (
            <li key={`${item.label}-${index}`} className="flex min-w-0 items-center gap-1.5">
              {index > 0 && <span className="text-text-disabled">/</span>}
              {item.href && !isLast
                ? (renderLink?.(item, label) ?? (
                    <a href={item.href} className="truncate hover:text-accent-ring">
                      {item.label}
                    </a>
                  ))
                : label}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
