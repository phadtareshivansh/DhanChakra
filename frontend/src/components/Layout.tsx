import { t } from '../i18n'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { RISK_THRESHOLDS } from '../config/risk'
import { useTheme } from '../hooks/useTheme'
import Breadcrumbs, { BreadcrumbItem } from './ui/Breadcrumbs'
import CommandPalette from './shell/CommandPalette'
import NotificationsBell from './shell/NotificationsBell'
import OrgSwitcher from './shell/OrgSwitcher'
import Sidebar from './shell/Sidebar'
import LanguageSwitcher from './shell/LanguageSwitcher'
import { cn } from '../utils/cn'
import UserMenu, { ShellUser } from './shell/UserMenu'

const SIDEBAR_KEY = 'dhanchakra_sidebar_collapsed'

const CRUMB_LABELS: Record<string, string> = {
  graph: 'Graph workspace',
  worklist: 'Worklist',
  entity: 'Entity',
  network: 'Network',
  cases: 'Cases',
  case: 'Case',
  export: 'Export',
  ingest: 'Ingest',
  settings: 'Settings',
  admin: 'Users',
  users: 'Users',
  search: 'Entity Search',
  loops: 'Loops',
}

function buildCrumbs(pathname: string): BreadcrumbItem[] {
  if (pathname === '/') return [{ label: t('Dashboard') }]
  const segments = pathname.split('/').filter(Boolean)
  return segments.map((segment, index) => {
    const fallback = segment
      .replace(/-/g, ' ')
      .replace(/^\w/, (character) => character.toUpperCase())
    return {
      label: t(CRUMB_LABELS[segment] || fallback),
      href: '/' + segments.slice(0, index + 1).join('/'),
    }
  })
}

export default function Layout() {
  const location = useLocation()
  const [user, setUser] = useState<ShellUser | null>(null)
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    const stored = localStorage.getItem(SIDEBAR_KEY)
    if (stored === '1' || stored === '0') return stored === '1'
    return window.innerWidth < 1024
  })
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [showLegend, setShowLegend] = useState(true)
  const { theme, toggleTheme } = useTheme()

  useEffect(() => {
    const stored = localStorage.getItem('dhanchakra_user')
    if (!stored) return
    try {
      setUser(JSON.parse(stored) as ShellUser)
    } catch {
      setUser(null)
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0')
  }, [collapsed])

  useEffect(() => {
    setMobileNavOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!mobileNavOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileNavOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [mobileNavOpen])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen((current) => !current)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  const crumbs = buildCrumbs(location.pathname)

  return (
    <div className="min-h-screen bg-canvas text-text-primary">
      <a
        href="#main-content"
        className="sr-only z-[100] rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        {t('Skip to main content')}
      </a>

      {mobileNavOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[1px] md:hidden"
          aria-hidden="true"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed((current) => !current)}
        isAdmin={user?.role === 'admin'}
        mobileOpen={mobileNavOpen}
        onMobileClose={() => setMobileNavOpen(false)}
      />

      <div className={cn('min-h-screen transition-[margin] duration-200 ease-out', collapsed ? 'md:ml-[68px]' : 'md:ml-[240px]')}>
        <header className="sticky top-0 z-30 border-b border-border bg-canvas/90 backdrop-blur">
          <div className="flex h-14 items-center gap-2 px-3 sm:gap-3 sm:px-6">
            <button
              type="button"
              onClick={() => setMobileNavOpen(true)}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-text-secondary hover:bg-raised hover:text-text-primary md:hidden"
              aria-label={t('Open navigation')}
              aria-expanded={mobileNavOpen}
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>

            <Breadcrumbs
              items={crumbs}
              className="hidden min-w-0 flex-1 md:block"
              renderLink={(item, children) => (
                <Link to={item.href ?? '/'} className="truncate hover:text-accent-ring">
                  {children}
                </Link>
              )}
            />

            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              className="flex h-9 flex-1 items-center gap-2 rounded-lg border border-border bg-canvas px-3 text-left text-xs text-text-disabled transition-colors hover:border-accent-ring/60 hover:text-text-secondary md:ml-auto md:max-w-xs md:flex-none"
              aria-label={t('Open global search')}
            >
              <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <span className="truncate">{t('Search entities…')}</span>
              <kbd className="ml-auto hidden shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] text-text-secondary sm:inline">
                {t('⌘K')}
              </kbd>
            </button>

            <div className="hidden lg:block">
              <OrgSwitcher />
            </div>

            <div className="hidden sm:block">
              <LanguageSwitcher compact />
            </div>

            <button
              type="button"
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? t('Switch to light theme') : t('Switch to dark theme')}
              title={theme === 'dark' ? t('Switch to light theme') : t('Switch to dark theme')}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-raised hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-ring"
            >
              {theme === 'dark' ? (
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              ) : (
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              )}
            </button>

            <NotificationsBell />
            <UserMenu user={user} />
          </div>
        </header>

        {showLegend && (
          <div className="px-4 pt-4 sm:px-6">
            <div className="panel flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2 text-[11px] text-text-secondary">
              <span className="micro-label">{t('Risk legend')}</span>
              <span>
                <span className="mr-1 inline-block h-2 w-2 rounded-full bg-risk-critical" />
                {t('Critical ≥')}{RISK_THRESHOLDS.critical}
              </span>
              <span>
                <span className="mr-1 inline-block h-2 w-2 rounded-full bg-risk-high" />
                {t('High')} {RISK_THRESHOLDS.high}–{RISK_THRESHOLDS.critical - 1}
              </span>
              <span>
                <span className="mr-1 inline-block h-2 w-2 rounded-full bg-risk-medium" />
                {t('Medium')} {RISK_THRESHOLDS.medium}–{RISK_THRESHOLDS.high - 1}
              </span>
              <span>
                <span className="mr-1 inline-block h-2 w-2 rounded-full bg-risk-low" />
                {t('Low <')}{RISK_THRESHOLDS.medium}
              </span>
              <button
                type="button"
                onClick={() => setShowLegend(false)}
                aria-label={t('Dismiss risk legend')}
                className="ml-auto text-text-disabled hover:text-text-primary"
              >
                ✕
              </button>
            </div>
          </div>
        )}

        <main id="main-content" tabIndex={-1} className="p-4 sm:p-6">
          <Outlet />
        </main>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        isAdmin={user?.role === 'admin'}
      />
    </div>
  )
}
