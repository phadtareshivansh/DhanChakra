import { t } from '../../i18n'
import { Link, useLocation } from 'react-router-dom'
import { NAV_GROUPS } from '../../config/navigation'
import { cn } from '../../utils/cn'

export interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
  isAdmin: boolean
  mobileOpen?: boolean
  onMobileClose?: () => void
}

export default function Sidebar({ collapsed, onToggle, isAdmin, mobileOpen = false, onMobileClose }: SidebarProps) {
  const location = useLocation()
  const effectiveCollapsed = collapsed && !mobileOpen

  const isActive = (path: string) =>
    path === '/' ? location.pathname === '/' : location.pathname.startsWith(path)

  return (
    <aside
      className={cn(
        'fixed inset-y-0 left-0 z-50 flex-col border-r border-border bg-surface',
        'transition-[width] duration-200 ease-out',
        mobileOpen ? 'flex' : 'hidden md:flex',
      )}
      style={{ width: mobileOpen ? 240 : collapsed ? 68 : 240 }}
      aria-label={t('Primary navigation')}
    >
      <div
        className={cn(
          'flex h-16 shrink-0 items-center border-b border-border',
          effectiveCollapsed ? 'justify-center px-2' : 'px-4',
        )}
      >
        <Link to="/" className="flex min-w-0 items-center gap-2.5" aria-label={t('Dhan-Chakra home')}>
          <img
            src="/favicon.svg"
            alt=""
            className="h-8 w-8 rounded-lg border border-border bg-surface object-cover"
          />
          {!effectiveCollapsed && (
            <div className="min-w-0">
              <div className="truncate text-md font-bold leading-tight">{t('Dhan-Chakra')}</div>
              <div className="truncate text-[10px] uppercase tracking-micro text-text-secondary">
                {t('Graph-AI Fraud Engine')}
              </div>
            </div>
          )}
        </Link>
        {mobileOpen && (
          <button
            type="button"
            onClick={onMobileClose}
            aria-label={t('Close navigation')}
            className="ml-auto rounded-md p-2 text-text-secondary hover:bg-raised hover:text-text-primary md:hidden"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      <nav aria-label={t('Primary navigation')} className="flex-1 space-y-5 overflow-y-auto overflow-x-hidden px-2.5 py-4">
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter((item) => !item.adminOnly || isAdmin)
          if (items.length === 0) return null
          return (
            <div key={group.label}>
              {!effectiveCollapsed && (
                <div className="mb-1.5 px-2.5 text-[10px] font-semibold uppercase tracking-micro text-text-disabled">
                  {group.label}
                </div>
              )}
              <div className="space-y-0.5">
                {items.map((item) => {
                  const active = isActive(item.path)
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      onClick={onMobileClose}
                      title={effectiveCollapsed ? item.label : undefined}
                      aria-current={active ? 'page' : undefined}
                      className={cn(
                        'flex items-center rounded-md text-sm font-medium transition-colors',
                        effectiveCollapsed ? 'justify-center px-0 py-2.5' : 'gap-3 px-2.5 py-2.5',
                        active
                          ? 'bg-accent/15 text-accent-ring'
                          : 'text-text-secondary hover:bg-raised hover:text-text-primary',
                      )}
                    >
                      <svg
                        className="h-5 w-5 shrink-0"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={item.icon} />
                      </svg>
                      {!effectiveCollapsed && <span className="truncate">{item.label}</span>}
                    </Link>
                  )
                })}
              </div>
            </div>
          )
        })}
      </nav>

      <div className="hidden shrink-0 border-t border-border p-2.5 md:block">
        <button
          type="button"
          onClick={onToggle}
          aria-label={effectiveCollapsed ? t('Expand sidebar') : t('Collapse sidebar')}
          aria-expanded={!effectiveCollapsed}
          title={effectiveCollapsed ? t('Expand sidebar') : t('Collapse sidebar')}
          className={cn(
            'flex w-full items-center rounded-md py-2 text-xs font-medium text-text-secondary transition-colors hover:bg-raised hover:text-text-primary',
            effectiveCollapsed ? 'justify-center px-0' : 'gap-2 px-2.5',
          )}
        >
          <svg
            className={cn('h-4 w-4 transition-transform', effectiveCollapsed && 'rotate-180')}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15 19l-7-7 7-7" />
          </svg>
          {!effectiveCollapsed && <span>{t('Collapse')}</span>}
        </button>
      </div>
    </aside>
  )
}
