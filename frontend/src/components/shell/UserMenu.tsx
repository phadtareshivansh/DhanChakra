import { t } from '../../i18n'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../../utils/api'
import { cn } from '../../utils/cn'

export interface ShellUser {
  display_name?: string
  email?: string
  role?: string
}

export interface UserMenuProps {
  user: ShellUser | null
}

export default function UserMenu({ user }: UserMenuProps) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const logout = async () => {
    // Revoke the refresh token server-side first, so the session really ends
    // rather than merely being forgotten here (TASK C1).
    const refreshToken = localStorage.getItem('dhanchakra_refresh_token')
    if (refreshToken) {
      try {
        await api.post('/auth/logout', { refresh_token: refreshToken })
      } catch {
        // A failed revoke must not trap the user in the app.
      }
    }
    localStorage.removeItem('dhanchakra_token')
    localStorage.removeItem('dhanchakra_refresh_token')
    localStorage.removeItem('dhanchakra_user')
    navigate('/login')
  }

  const name = user?.display_name || user?.email || t('Analyst')
  const initial = name[0]?.toUpperCase() ?? 'U'

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-label={t('Account menu')}
        aria-expanded={open}
        aria-haspopup="menu"
        className={cn(
          'flex items-center gap-2 rounded-lg p-1 pr-2 transition-colors hover:bg-raised',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-ring',
        )}
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-sm font-semibold text-white">
          {initial}
        </span>
        <span className="hidden min-w-0 text-left lg:block">
          <span className="block max-w-[9rem] truncate text-xs font-medium text-text-primary">{name}</span>
          <span className="block text-[10px] uppercase tracking-micro text-text-secondary">
            {t(user?.role ?? 'guest')}
          </span>
        </span>
        <svg
          className={cn('hidden h-3.5 w-3.5 text-text-disabled transition-transform lg:block', open && 'rotate-180')}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-11 z-50 w-60 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg"
        >
          <div className="border-b border-border px-3 py-2.5">
            <div className="truncate text-sm font-medium text-text-primary">{name}</div>
            {user?.email && user.email !== name && (
              <div className="truncate text-[11px] text-text-secondary">{user.email}</div>
            )}
            <div className="mt-1 inline-flex rounded-full bg-raised px-2 py-0.5 text-[10px] uppercase tracking-micro text-text-secondary">
              {t(user?.role ?? 'guest')}
            </div>
          </div>
          <Link
            to="/settings"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="block px-3 py-2 text-xs text-text-secondary hover:bg-raised hover:text-text-primary"
          >
            {t('Settings')}
          </Link>
          {user?.role === 'admin' && (
            <Link
              to="/admin/users"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="block px-3 py-2 text-xs text-text-secondary hover:bg-raised hover:text-text-primary"
            >
              {t('User management')}
            </Link>
          )}
          <button
            type="button"
            role="menuitem"
            onClick={logout}
            className="block w-full border-t border-border px-3 py-2 text-left text-xs text-risk-critical hover:bg-raised"
          >
            {t('Log out')}
          </button>
        </div>
      )}
    </div>
  )
}
