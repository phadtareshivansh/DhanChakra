import { t } from '../../i18n'
import { useEffect, useRef, useState } from 'react'
import { cn } from '../../utils/cn'

interface Organisation {
  id: string
  name: string
  role: string
}

const STORAGE_KEY = 'dhanchakra_org'
const DEFAULT_ORG: Organisation = { id: 'demo', name: 'Demo Organisation', role: 'Owner' }

function readOrganisation(): Organisation {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return DEFAULT_ORG
    const parsed = JSON.parse(stored) as Partial<Organisation>
    if (!parsed.id || !parsed.name) return DEFAULT_ORG
    return { id: parsed.id, name: parsed.name, role: parsed.role ?? 'Member' }
  } catch {
    return DEFAULT_ORG
  }
}

/**
 * Placeholder organisation switcher. Until organisation provisioning and
 * per-org sessions ship, only the current organisation is selectable; the
 * control reserves the interaction and shows where multi-tenant switching
 * will live.
 */
export default function OrgSwitcher() {
  const [organisation] = useState<Organisation>(readOrganisation)
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`Organisation: ${organisation.name}`}
        className="flex h-9 max-w-[13rem] items-center gap-2 rounded-lg border border-border px-2.5 text-xs font-medium text-text-primary transition-colors hover:bg-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-ring"
      >
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-accent/15 text-[10px] font-bold text-accent-ring">
          {organisation.name[0]?.toUpperCase()}
        </span>
        <span className="truncate">{organisation.name}</span>
        <svg
          className={cn('h-3 w-3 shrink-0 text-text-disabled transition-transform', open && 'rotate-180')}
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
          role="listbox"
          aria-label={t('Organisations')}
          className="absolute right-0 top-11 z-50 w-64 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg"
        >
          <div className="px-3 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-micro text-text-disabled">
            {t('Organisation')}
          </div>
          <div
            role="option"
            aria-selected
            className="flex items-center gap-2 bg-raised px-3 py-2 text-xs text-text-primary"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded bg-accent/15 text-[10px] font-bold text-accent-ring">
              {organisation.name[0]?.toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{organisation.name}</span>
              <span className="block text-[10px] text-text-secondary">{organisation.role}</span>
            </span>
            <span className="text-accent-ring">✓</span>
          </div>
          <div className="border-t border-border px-3 py-2 text-[10px] leading-relaxed text-text-secondary">
            {t('Switching organisations arrives with multi-tenant provisioning.')}
          </div>
        </div>
      )}
    </div>
  )
}
