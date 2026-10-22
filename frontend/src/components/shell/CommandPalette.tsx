import { t } from '../../i18n'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import api from '../../utils/api'
import { SearchResult } from '../../types/api'
import { ALL_NAV_ITEMS } from '../../config/navigation'
import { useOverlay } from '../ui/useOverlay'
import { cn } from '../../utils/cn'

export interface CommandPaletteProps {
  open: boolean
  onClose: () => void
  isAdmin?: boolean
}

interface CommandItem {
  id: string
  label: string
  hint?: string
  group: 'Navigation' | 'Entities'
  icon?: string
  onSelect: () => void
}

export default function CommandPalette({ open, onClose, isAdmin = false }: CommandPaletteProps) {
  const navigate = useNavigate()
  const containerRef = useOverlay(open, onClose)
  const inputRef = useRef<HTMLInputElement>(null)
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  useEffect(() => {
    if (!open) return
    setQuery('')
    setResults([])
    setActiveIndex(0)
    const timer = setTimeout(() => inputRef.current?.focus(), 0)
    return () => clearTimeout(timer)
  }, [open])

  useEffect(() => {
    const term = query.trim()
    if (term.length < 2) {
      setResults([])
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    const timer = setTimeout(async () => {
      try {
        const response = await api.get(`/entities/search?q=${encodeURIComponent(term)}&limit=6`)
        if (!cancelled) setResults(response.data.results ?? [])
      } catch {
        if (!cancelled) setResults([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, 200)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query])

  const items = useMemo<CommandItem[]>(() => {
    const term = query.trim().toLowerCase()
    const navigation = ALL_NAV_ITEMS.filter(
      (item) =>
        (!item.adminOnly || isAdmin) &&
        (term.length === 0 || item.label.toLowerCase().includes(term)),
    ).map<CommandItem>((item) => ({
      id: `nav:${item.path}`,
      label: item.label,
      hint: item.path,
      group: 'Navigation',
      icon: item.icon,
      onSelect: () => {
        navigate(item.path)
        onClose()
      },
    }))

    const entities = results.map<CommandItem>((result) => ({
      id: `entity:${result.id}`,
      label: result.name,
      hint: [result.identifier, result.type].filter(Boolean).join(' · '),
      group: 'Entities',
      onSelect: () => {
        navigate(`/entity/${result.id}/network`)
        onClose()
      },
    }))

    return [...navigation, ...entities]
  }, [query, results, navigate, onClose, isAdmin])

  useEffect(() => {
    setActiveIndex(0)
  }, [query, results])

  useEffect(() => {
    itemRefs.current[activeIndex]?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex])

  if (!open) return null

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((current) => (items.length === 0 ? 0 : (current + 1) % items.length))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((current) => (items.length === 0 ? 0 : (current - 1 + items.length) % items.length))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      items[activeIndex]?.onSelect()
    }
  }

  let runningIndex = -1

  return createPortal(
    <div className="fixed inset-0 z-[60] flex items-start justify-center p-4 pt-[12vh]">
      <div
        className="animate-fade-in absolute inset-0 bg-black/60 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-label={t('Command palette')}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className="animate-scale-in relative w-full max-w-xl overflow-hidden rounded-xl border border-border bg-surface shadow-lg focus:outline-none"
      >
        <div className="flex items-center gap-3 border-b border-border px-4">
          <svg
            className="h-4 w-4 shrink-0 text-text-disabled"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('Search entities or jump to a page…')}
            aria-label={t('Search entities or pages')}
            aria-controls="command-palette-results"
            className="h-12 flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-disabled focus:outline-none"
          />
          <kbd className="hidden rounded border border-border px-1.5 py-0.5 text-[10px] text-text-secondary sm:inline">
            {t('Esc')}
          </kbd>
        </div>

        <div id="command-palette-results" role="listbox" className="max-h-[52vh] overflow-y-auto p-2">
          {items.length === 0 && (
            <div className="px-3 py-8 text-center text-sm text-text-secondary">
              {loading ? 'Searching…' : query.trim().length >= 2 ? 'No matching entities or pages.' : 'Type to search.'}
            </div>
          )}
          {items.map((item) => {
            runningIndex += 1
            const index = runningIndex
            const showGroup = index === 0 || items[index - 1].group !== item.group
            return (
              <div key={item.id}>
                {showGroup && (
                  <div className="px-2.5 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-micro text-text-disabled">
                    {item.group}
                  </div>
                )}
                <button
                  ref={(element) => {
                    itemRefs.current[index] = element
                  }}
                  role="option"
                  aria-selected={index === activeIndex}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={item.onSelect}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors',
                    index === activeIndex ? 'bg-raised' : 'hover:bg-raised/60',
                  )}
                >
                  {item.icon ? (
                    <svg
                      className="h-4 w-4 shrink-0 text-text-secondary"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      aria-hidden="true"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d={item.icon} />
                    </svg>
                  ) : (
                    <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-accent/20 text-[9px] font-semibold text-accent-ring">
                      {t('E')}
                    </span>
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-text-primary">{item.label}</span>
                    {item.hint && (
                      <span className="block truncate font-mono text-[11px] text-text-secondary">{item.hint}</span>
                    )}
                  </span>
                  {index === activeIndex && (
                    <kbd className="shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] text-text-secondary">
                      ↵
                    </kbd>
                  )}
                </button>
              </div>
            )
          })}
          {loading && items.length > 0 && (
            <div className="px-3 py-2 text-center text-[11px] text-text-secondary">{t('Searching…')}</div>
          )}
        </div>

        <div className="flex items-center gap-4 border-t border-border px-4 py-2 text-[10px] text-text-secondary">
          <span className="flex items-center gap-1">
            <kbd className="rounded border border-border px-1 py-0.5">↑</kbd>
            <kbd className="rounded border border-border px-1 py-0.5">↓</kbd>
            {t('navigate')}
          </span>
          <span className="flex items-center gap-1">
            <kbd className="rounded border border-border px-1 py-0.5">↵</kbd>
            {t('open')}
          </span>
          <span className="ml-auto">{t('Global search')}</span>
        </div>
      </div>
    </div>,
    document.body,
  )
}
